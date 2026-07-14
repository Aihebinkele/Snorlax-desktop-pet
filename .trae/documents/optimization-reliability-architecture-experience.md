# 优化计划：可靠性 + 架构可维护性 + 体验优化

## 目标

对 Desktop Pet 项目进行三层面优化：可靠性修复、架构拆分重构、体验增强（新增状态 + 托盘图标）。

---

## 阶段一：可靠性修复（#1-3）

### 1.1 pet-notify.py 添加全局超时兜底

**问题**：如果 Flask 挂了或 urllib 卡住，Hook 进程可能永远不退出，阻塞 Claude Code。

**方案**：使用 `signal.alarm(5)` 在 5 秒后发送 SIGALRM 强制退出。Windows 不支持 `signal.alarm`，改用 `threading.Timer` + `os._exit(0)`。

**具体实现**：
```python
import threading, os
def _timeout_exit():
    os._exit(0)
timer = threading.Timer(5.0, _timeout_exit)
timer.daemon = True
timer.start()
```
在 `main()` 函数入口处启动，确保 5 秒后进程一定退出。

### 1.2 Flask 线程安全：last_event_time 加锁

**问题**：`last_event_time` 在 Flask 请求线程写入，在 Tkinter 主线程 `_poll_events` 中读取，无锁保护。

**方案**：将 `last_event_time` 的读写都放入 `app_state_lock` 保护范围。

**具体变更**：
- `handle_event()` 中写入 `last_event_time` 时加锁
- `_poll_events()` 中读取 `last_event_time` 时加锁
- 将 `last_event_time` 移入 `app_state` 字典，统一管理

### 1.3 事件队列改为有界队列

**问题**：`queue.Queue()` 无界，Tkinter 卡顿时可能内存增长。

**方案**：改为 `queue.Queue(maxsize=50)`，`put` 时使用 `block=False` + 异常捕获丢弃溢出事件。

---

## 阶段二：架构拆分（#4-6）

### 2.1 拆分 pet_app.py 为 4 个模块

**当前**：pet_app.py 627 行，包含配置、GUI、动画、状态机、HTTP 服务。

**目标结构**：

```
pet_config.py    — 配置系统（常量、加载、校验、持久化）
pet_state.py     — 状态机（STATE_CONFIG、EVENT_TO_STATE、CLICK_RESPONSES、状态转换逻辑）
pet_gui.py       — DesktopPet 类（Tkinter GUI + 动画 + 交互）
pet_app.py       — 入口 + Flask 路由（精简为启动逻辑 + HTTP 端点）
```

**拆分边界**：

#### pet_config.py（约 130 行）
- `BASE_DIR`, `RESOURCE_DIR`, `APP_DATA_DIR`, `CONFIG_PATH`, `DEFAULT_CONFIG_PATH`
- `DEFAULT_APP_CONFIG`, `ANIM_CONFIG`
- `_deep_merge()`, `_clamp_int()`, `normalize_app_config()`, `load_app_config()`, `save_app_config()`

#### pet_state.py（约 80 行）
- `STATE_CONFIG`, `EVENT_TO_STATE`, `CLICK_RESPONSES`
- `StateMachine` 类：
  - `__init__(self, on_state_change callback)`
  - `current_state`, `current_message` 属性
  - `process_event(event_type, message)` — 根据事件类型转换状态
  - `tick()` — 检查超时自动恢复
  - 内部管理 `_reset_timer` 逻辑（通过 callback 通知 GUI 层执行 `after()` 调度）
  - 新增状态的转换规则（tired/sleeping/thinking）

#### pet_gui.py（约 350 行）
- `DesktopPet` 类：
  - 接收 `StateMachine` 实例
  - Tkinter 窗口、Canvas、图片加载
  - 动画引擎 `_animate()`
  - 交互事件（单击/双击/拖拽/右键菜单）
  - 设置窗口
  - 系统托盘图标

#### pet_app.py（约 100 行）
- Flask app + 路由 + CORS
- `event_queue`, `events`, `app_state` 全局状态
- `is_port_in_use()`, `start_flask()`
- `__main__` 入口

### 2.2 状态机封装

**当前问题**：状态转换逻辑散落在 `_poll_events`（触发）、`update_state`（执行）、`_auto_reset_to_idle/working`（恢复）三处。

**方案**：`StateMachine` 类集中管理：

```python
class StateMachine:
    TRANSITIONS = {
        "task_start": "working",
        "step_complete": "step_done",
        "task_complete": "happy",
        "user_confirmation_needed": "waiting",
        "error": "sad",
    }

    AUTO_RECOVERY = {
        "step_done": ("working", 1500),
        "happy": ("idle", 5000),
        "waiting": ("idle", 8000),
        "sad": ("idle", 5000),
        "tired": ("idle", 0),      # 不自动恢复
        "sleeping": ("idle", 0),    # 不自动恢复
    }

    def process_event(self, event_type, message):
        ...

    def check_timeouts(self, last_event_time, working_timeout_ms):
        ...
```

GUI 层通过回调响应状态变化，不再直接管理转换逻辑。

### 2.3 添加测试

**新增文件**：`tests/test_pet_config.py` + `tests/test_pet_state.py`

**测试覆盖**：

#### test_pet_config.py
- `test_normalize_default` — 空配置归一化
- `test_normalize_window_clamp` — 窗口尺寸边界值
- `test_normalize_working_timeout_clamp` — 超时边界值
- `test_deep_merge_nested` — 嵌套合并
- `test_deep_merge_override` — 覆盖而非合并

#### test_pet_state.py
- `test_event_to_state_mapping` — 事件→状态映射
- `test_auto_recovery_step_done` — step_done 自动恢复到 working
- `test_auto_recovery_happy` — happy 自动恢复到 idle
- `test_working_timeout_to_happy` — working 超时→happy
- `test_tired_transition` — working 长时间→tired
- `test_sleeping_transition` — idle 长时间→sleeping
- `test_thinking_vs_working` — thinking 与 working 区分

---

## 阶段三：体验优化（#7-9）

### 3.1 新增 3 个宠物状态

| 状态 | 标签 | 触发条件 | 自动恢复 | 恢复到 | 动画 |
|------|------|----------|----------|--------|------|
| tired | 累了... | working 持续 3 分钟 | 无（需新事件触发） | - | slow_tremble：慢速颤抖，振幅减半 |
| sleeping | Zzz... | idle 持续 10 分钟 | 单击唤醒 | idle | breathe：缓慢呼吸式缩放 |
| thinking | 思考中... | PreToolUse 触发 | 无 | - | pulse_slow：慢速脉冲 |

**状态转换规则更新**：

```
idle ──(10min)──→ sleeping ──(click)──→ idle
working ──(3min)──→ tired ──(task_start/step_complete)──→ working
PreToolUse → thinking（替代原来的 task_start）
UserPromptSubmit → working（保持不变）
thinking ──(PostToolUse)──→ step_done
thinking ──(5s timeout)──→ working
```

**EVENT_TO_STATE 更新**：

| HTTP Event | 状态 | 变更说明 |
|-----------|------|---------|
| task_start | working | 保持不变（UserPromptSubmit 触发） |
| tool_start | thinking | **新增**，PreToolUse 触发 |
| step_complete | step_done | 保持不变 |
| task_complete | happy | 保持不变 |
| user_confirmation_needed | waiting | 保持不变 |
| error | sad | 保持不变 |

**pet-notify.py 变更**：
- `PreToolUse` 事件发送 `tool_start` 而非 `task_start`
- Flask `/event` 端点支持新事件类型 `tool_start`

**新增图片**：
- `pet_images/tired.png`
- `pet_images/sleeping.png`
- `pet_images/thinking.png`

**新增动画**：
- `slow_tremble`：与 tremble 相同算法，amp 减半，speed 减半
- `breathe`：`sin(t * 0.02)` 缓慢缩放效果（通过微调 y 偏移模拟）
- `pulse_slow`：与 pulse 相同算法，speed 减半

**新增 CLICK_RESPONSES**：
- tired: "好累啊...让我歇会儿"
- sleeping: "Zzz...（被吵醒了）"
- thinking: "嗯...让我想想..."

**新增 STATE_CONFIG**：
```python
"tired":     {"emoji": "😴", "label": "累了...",     "bg": "#1A1A2E", "fg": "#7986CB"},
"sleeping":  {"emoji": "💤", "label": "Zzz...",      "bg": "#1A1A2E", "fg": "#5C6BC0"},
"thinking":  {"emoji": "🤔", "label": "思考中...",    "bg": "#1A237E", "fg": "#90CAF9"},
```

### 3.2 系统托盘图标

**依赖**：`pystray` + `Pillow`（项目已有 Pillow 依赖）

**新增文件**：无需新文件，逻辑集成在 `pet_gui.py`

**具体实现**：

1. 在 `DesktopPet.__init__` 中创建托盘图标线程
2. 托盘图标使用 `pet_images/idle.png` 缩小版
3. 托盘右键菜单：
   - "显示/隐藏" — 切换窗口可见性
   - "重置状态" — 重置为 idle
   - "退出" — 退出应用
4. 窗口关闭按钮（当前无，因为 overrideredirect）改为最小化到托盘
5. 双击托盘图标 — 显示窗口

**依赖安装**：`pip install pystray`

**build_installer.ps1 更新**：PyInstaller 打包时需要 `--hidden-import pystray._win32`

### 3.3 _poll_events 增加状态超时检测

在 `_poll_events` 的 200ms 轮询中增加：

- **idle 超时检测**：记录进入 idle 的时间，超过 10 分钟切换为 sleeping
- **working 超时检测**：记录进入 working 的时间，超过 3 分钟切换为 tired（替代原来的 5 秒→happy 逻辑）

**注意**：原来的 working 5 秒无事件→happy 逻辑保留，但优先级低于 tired。即：
- working 3 分钟 → tired
- working/step_done 5 秒无新事件 → happy（仅在未进入 tired 时生效）

---

## 阶段四：文档与配置更新

### 4.1 更新 CLAUDE.md

- 状态系统表格：新增 tired/sleeping/thinking
- 事件映射表格：新增 tool_start
- 动画系统表格：新增 slow_tremble/breathe/pulse_slow
- Key Files：新增 pet_config.py、pet_state.py、pet_gui.py
- Dependencies：新增 pystray

### 4.2 更新 AGENTS.md

同 CLAUDE.md 的变更，加上：
- 架构图更新模块名

### 4.3 更新 README.md

- 状态映射表格新增 3 个状态
- 依赖新增 pystray

### 4.4 更新 pet_config.json

新增默认配置：
```json
{
  "state_durations": {
    "tired": 0,
    "sleeping": 0,
    "thinking": 0
  },
  "working_tired_timeout_ms": 180000,
  "idle_sleeping_timeout_ms": 600000,
  "animations": {
    "tired": {"type": "slow_tremble", "amp": 0.75, "speed": 0.015},
    "sleeping": {"type": "breathe", "amp_y": 2, "speed": 0.02},
    "thinking": {"type": "pulse_slow", "amp_y": 4, "speed": 0.1}
  }
}
```

### 4.5 更新 .gitignore

新增：`tests/__pycache__/`

### 4.6 更新 build_installer.ps1

- PyInstaller 命令新增 `--hidden-import pystray._win32`
- `--add-data` 新增 `hooks;hooks`（可选，让打包后用户可查看 hook 脚本）

---

## 实施顺序

1. **阶段一**：可靠性修复（pet-notify.py 超时、last_event_time 加锁、队列有界化）
2. **阶段二**：架构拆分（pet_config.py → pet_state.py → pet_gui.py → pet_app.py 重构）
3. **阶段三**：体验优化（新增状态 + 托盘图标 + 超时检测）
4. **阶段四**：文档与配置更新

阶段二必须在阶段三之前完成，因为新增状态需要 StateMachine 类。阶段一可以在阶段二之前或同时完成。

---

## 验证步骤

1. `python -m py_compile` 检查所有新模块语法
2. `python -m pytest tests/` 运行测试
3. 手动启动 `python pet_app.py` 验证：
   - 宠物窗口正常显示
   - 单击/双击/拖拽交互正常
   - 右键菜单正常
   - 系统托盘图标出现
   - 托盘菜单功能正常
4. 发送 HTTP 事件验证状态切换：
   - `curl -X POST http://localhost:3456/event -H "Content-Type: application/json" -d '{"event":"task_start","message":"test"}'` → working
   - `curl -X POST http://localhost:3456/event -H "Content-Type: application/json" -d '{"event":"tool_start","message":"Write"}'` → thinking
   - `curl -X POST http://localhost:3456/event -H "Content-Type: application/json" -d '{"event":"step_complete","message":"Write"}'` → step_done
   - `curl -X POST http://localhost:3456/event -H "Content-Type: application/json" -d '{"event":"task_complete","message":"done"}'` → happy
5. 等待超时验证：
   - idle 10 分钟后 → sleeping（可临时将超时改为 30 秒测试）
   - working 3 分钟后 → tired（可临时将超时改为 10 秒测试）
6. 全文搜索确认无残留的旧模块引用
