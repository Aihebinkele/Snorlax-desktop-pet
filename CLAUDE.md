# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Desktop Pet — 卡比兽 (Snorlax)** — 一只可爱的宝可梦桌面宠物，通过 Claude Code Hooks 实时感知开发状态变化。宠物以程序化微动效呈现不同状态，拥有自言自语、闹钟提醒、Claude 对话等陪伴功能。

## Architecture

```
Claude Code Hooks → pet-notify → HTTP POST → Flask (desktop_pet.app:3456) → Queue → Tkinter 动画
                                                    ↑
                                            闹钟管理器 (AlarmManager)
                                            自言自语循环 (Self-Talk)
                                            交谈模块 (ChatDialog ↔ Claude CLI)
```

- **Hooks** (`.claude/settings.local.json`): 拦截 Claude Code 的 UserPromptSubmit / PreToolUse / PostToolUse / Stop 事件（**仅项目级**，不影响其他项目）
- **notify.py** (`desktop_pet/`): Hook 脚本，将 Hook 事件转为 HTTP POST 发送到宠物应用
- **app.py** (`desktop_pet/`): Flask HTTP 服务器 + Tkinter 桌面宠物 + 闹钟启动
- **config.py** (`desktop_pet/`): 配置系统（加载、校验、持久化），含闹钟配置
- **state.py** (`desktop_pet/`): 状态机（StateMachine 类，卡比兽人格状态转换逻辑）
- **gui.py** (`desktop_pet/`): DesktopPet 类（Tkinter GUI + 动画 + 交互 + 系统托盘 + 自言语气泡 + 卡通对话框绘制）
- **alarm.py** (`desktop_pet/`): 闹钟管理器（定时提醒吃饭/喝水/休息/下班）
- **chat.py** (`desktop_pet/`): 交谈对话框（搜狗输入法风格浮条，调用 Claude CLI 获取回复）

## Commands

```bash
pip install -e .              # 开发模式安装
desktop-pet                   # 启动桌面宠物（Flask on :3456 + Tkinter 窗口）
desktop-pet install-hooks     # 安装 Claude Code Hooks
desktop-pet --version         # 查看版本号
python -m pytest tests/       # 运行测试
```

启动前需确保：Python 3.8+ + flask、Pillow、pystray 已安装；端口 3456 未被占用。

## Personality — 卡比兽

| 属性 | 设定 |
|------|------|
| 自称 | 咔比 |
| 称呼用户 | 主人 |
| 口头禅 | `(´・ω・`)` `(๑•̀ㅂ•́)و✧` `( o ・ω・) ノ` |
| 性格 | 贪吃 🍩、爱睡 😴、关心主人健康 💕 |
| 自言自语 | 52条短语，每1~3分钟随机弹出 |
| 最爱的 | 吃饭、睡觉、陪主人 |

## State System

**STATE_CONFIG**: 9 种卡比兽风格状态。

| 状态 | 标签 | 自动恢复 | 恢复到 |
|------|------|----------|--------|
| idle | 呼噜噜~ | 无 | - |
| reading | 看看主人在干嘛... | 2s | thinking |
| step_done | 做完啦！厉害~ | 1.5s | thinking |
| happy | 开心！( ´・∀・)ﾉ | 5s | idle |
| waiting | 主人你在哪？ | 8s | idle |
| sad | 呜呜...不开心 | 5s | idle |
| tired | 困困...想睡觉( '・ω・)゛ | 无 | - |
| sleeping | 呼呼呼...咔比~ | 无 | - |
| thinking | 咔比正在想... | 无 | - |

**EVENT_TO_STATE**:

| HTTP Event | 状态 |
|-----------|------|
| task_start | thinking |
| tool_start | thinking |
| reading_start | reading |
| step_complete | step_done |
| task_complete | happy |
| user_confirmation_needed | waiting |
| error | sad |

## Animation System

**ANIM_CONFIG**: 程序化微动效，基于 `math` 三角函数 + Canvas `coords()` 位移，50ms 刷新（20fps）。

| 状态 | 动画类型 | 效果 | 原理 |
|------|----------|------|------|
| idle | float | 缓慢上下浮动 | `sin(t * 0.05)` 周期 ~6s，振幅 3px |
| reading | pulse_slow | 慢速脉冲 | 减速版 pulse |
| step_done | pulse | 向上弹一下 | 单周期 sin 弧线，~0.8s 完成 |
| happy | bounce | 持续弹跳 | `|sin(t * 0.2)|` 连续弹跳，振幅 8px |
| waiting | sway | 左右摇摆+微抬 | 水平摆动 + 同步轻微上浮 |
| sad | droop | 缓慢下沉停住 | 指数衰减渐进下沉，~5s 到位 |
| tired | slow_tremble | 慢速颤抖 | 振幅减半的颤抖 |
| sleeping | breathe | 缓慢呼吸 | sin(t * 0.02) 呼吸式浮动 |
| thinking | pulse_slow | 慢速脉冲 | 减速版 pulse |

核心方法 `_animate()`: 永久循环，读取 `current_state` 计算偏移量，仅移动宠物图片（文字保持稳定）。状态切换时 `_anim_tick` 归零，动画从起点重新开始。

## Interaction

| 操作 | 行为 |
|------|------|
| 单击 | 显示卡通对话气泡；sleeping 状态单击唤醒 |
| 双击 | 打开 Claude 交谈输入框（搜狗风格浮条） |
| 拖拽 | 移动窗口 |
| 右键 | 菜单：💬 交谈 / 设置 / 闹钟设置 / 重置状态 / 隐藏 / 退出 |

### 交谈功能 (`chat.py`)

- 双击宠物 → 弹出搜狗输入法风格迷你浮条（320×36px，圆角，猫咪图标）
- 输入文字按 Enter → 后台调用 `claude -p` 获取回复
- 回复以卡通气泡显示在宠物头顶（10秒）
- 120秒超时保护
- 回复后浮条自动关闭

### 自言自语

- 每 1~3 分钟随机弹出卡比兽风格气泡（52 条短语）
- sleeping 状态不弹；已有气泡时 30% 概率跳过
- 气泡停留 10 秒后消失

### 10分钟无操作自动睡觉

- 追踪单击/双击/Claude Code 事件时间
- 任意状态超过 600 秒无交互 → sleeping
- 有交互时自动唤醒

## Cartoon Speech Bubble

气泡使用 Canvas 程序化绘制：
- 奶油色 (#FFF8E1) 圆角矩形背景
- 暖棕 (#C4956A) 1.5px 圆角边框
- 深棕 (#4E342E) 11pt 文字
- 45° 倾斜暖棕猫爪装饰
- 三角小尾巴（带暖棕边框，与对话框不重叠）

## Alarm System (`alarm.py`)

- 右键 → "闹钟设置" 打开管理窗口
- 10 个预设模板：喝水 (×4)、吃饭 (×2)、休息、下班 (×2)、查看待办
- 支持添加/删除/启用自定义闹钟
- 后台线程每 30 秒检查系统时间
- 到点弹出居中提醒弹窗 + 系统提示音
- "知道了" + "5分钟后提醒" 按钮

## Hooks Integration

**pet-notify** (`desktop_pet/notify.py`): CLI 命令，从 stdin 读取 Hook JSON，映射到宠物事件。

| Hook 事件 | 宠物事件 | 说明 |
|-----------|---------|------|
| UserPromptSubmit | task_start | 用户提交指令 |
| PreToolUse (Read/Glob/Grep) | reading_start | 读取类工具 |
| PreToolUse (其他) | tool_start | 工具调用开始（思考状态） |
| PostToolUse (Write/Edit/Bash) | step_complete | 高价值工具调用完成 |
| Stop | task_complete | 任务结束 |

**超时自动恢复**: step_done > 5s → thinking；thinking > 180s → tired；idle > 600s → sleeping；**任意状态 10min 无交互 → sleeping**。

## System Tray

- 系统托盘图标（pystray），右键菜单：显示/隐藏、重置状态、退出
- 双击托盘图标显示窗口

## API Endpoints

- `POST /event` - 接收事件 `{event, message}`，触发状态变更
- `GET /events` - 获取事件历史 + 当前状态
- `GET /health` - 健康检查

## Key Files

| 文件 | 说明 |
|------|------|
| `desktop_pet/app.py` | 入口：Flask HTTP + 启动逻辑 + 闹钟初始化 |
| `desktop_pet/config.py` | 配置系统：加载、校验、持久化，含闹钟 |
| `desktop_pet/state.py` | 状态机：StateMachine 类 + 卡比兽人格 |
| `desktop_pet/gui.py` | GUI：Tkinter + 动画 + 交互 + 托盘 + 自言自语 + 卡通气泡 |
| `desktop_pet/alarm.py` | 闹钟管理器：定时提醒 + 预设模板 |
| `desktop_pet/chat.py` | 交谈模块：搜狗浮条 + Claude CLI 子进程 |
| `desktop_pet/notify.py` | Hook 脚本：Claude Code 事件 → HTTP 通知 |
| `desktop_pet/cli.py` | CLI 入口：desktop-pet、pet-notify、claude-pet |
| `desktop_pet/hooks.py` | Hooks 安装/卸载管理 |
| `desktop_pet/launcher.py` | Claude CLI 生命周期管理器 |
| `desktop_pet/pet_images/{state}.png` | 9 张状态图片 |
| `desktop_pet/default_config.json` | 默认配置（含闹钟模板） |
| `pyproject.toml` | 包定义与依赖 |
| `.claude/settings.local.json` | Hook 配置 + 权限白名单 |

## Dependencies

- Python: `flask>=3.0`, `Pillow>=10.0`, `pystray>=0.19`
- Windows-only: `winsound`（happy 状态音效 + 闹钟提示音）
- 交谈功能需要 `claude` CLI 在 PATH 中
