# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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

- **Hooks** (`.claude/settings.local.json`): 拦截 Claude Code 的 UserPromptSubmit / PreToolUse / PostToolUse / Stop 事件
- **notify.py** (`desktop_pet/`): Hook 脚本，将 Hook 事件转为 HTTP POST 发送到宠物应用
- **app.py** (`desktop_pet/`): Flask HTTP 服务器 + Tkinter 桌面宠物 + 闹钟启动
- **config.py** (`desktop_pet/`): 配置系统（加载、校验、持久化），含闹钟配置
- **state.py** (`desktop_pet/`): 状态机（StateMachine 类，卡比兽人格状态转换）
- **gui.py** (`desktop_pet/`): DesktopPet 类（Tkinter GUI + 动画 + 交互 + 托盘 + 自言自语气泡 + 卡通对话框绘制）
- **alarm.py** (`desktop_pet/`): 闹钟管理器（定时提醒吃饭/喝水/休息/下班）
- **chat.py** (`desktop_pet/`): 交谈对话框（搜狗输入法风格浮条，调用 Claude CLI）
- **cli.py** (`desktop_pet/`): CLI 入口（desktop-pet、pet-notify、claude-pet 命令）
- **hooks.py** (`desktop_pet/`): Claude Code Hooks 安装/卸载管理
- **launcher.py** (`desktop_pet/`): Claude CLI 生命周期管理器

## Installation

```bash
pip install -e .                    # 开发模式安装
desktop-pet                        # 启动桌面宠物
desktop-pet install-hooks          # 安装 Claude Code Hooks
desktop-pet --version              # 查看版本号
```

## Commands

```bash
desktop-pet                        # 启动桌面宠物（Flask on :3456 + Tkinter 窗口）
desktop-pet install-hooks          # 安装 Claude Code Hooks 到 PWD/.claude/settings.local.json
desktop-pet uninstall-hooks        # 卸载 Claude Code Hooks
desktop-pet --version              # 显示版本号
pet-notify                         # Hook 脚本入口（由 Claude Code 调用）
claude-pet                         # Claude CLI 生命周期启动器
python -m pytest tests/            # 运行测试
```

启动前需确保：Python 3.8+ + flask、Pillow、pystray 已安装；端口 3456 未被占用。

## Personality — 卡比兽 (Snorlax)

桌面宠物采用 **卡比兽** 人格设定：

- **自称 "咔比"**，称呼用户 **"主人"**
- 说话语气轻松可爱，用 `(´・ω・`)` `(๑•̀ㅂ•́)و✧` `( o ・ω・) ノ` 等颜文字
- 贪吃 🍩、爱睡 😴、温暖关心主人 💕
- 52 条自言自语短语，涵盖：吃东西、喝水提醒、睡觉犯困、陪主人、天气、鼓励、卖萌、下午茶

## State System

**STATE_CONFIG** (`desktop_pet/state.py`): 9 种状态，每种含 emoji、标签、配色、自动恢复时长。

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

**EVENT_TO_STATE** (`desktop_pet/state.py`):

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

**ANIM_CONFIG** (`desktop_pet/config.py`): 程序化微动效，基于 `math` 三角函数 + Canvas `coords()` 位移，50ms 刷新（20fps）。

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

核心方法 `_animate()` (`desktop_pet/gui.py`): 永久循环，读取 `current_state` 计算偏移量，仅移动宠物图片。状态切换时 `_anim_tick` 归零，动画从起点重新开始。

## Interaction

### 基础交互

| 操作 | 行为 |
|------|------|
| 单击 | 显示对话气泡（sleeping 单击唤醒） |
| 双击 | 打开 Claude 交谈输入框 |
| 拖拽 | 移动窗口（>3px 阈值） |
| 右键 | 菜单：💬 交谈 / 设置 / 闹钟设置 / 重置状态 / 隐藏 / 退出 |

### 交谈功能 (`desktop_pet/chat.py`)

- 双击宠物 → 弹出搜狗输入法风格迷你浮条（320×36px）
- 输入文字按 Enter → 后台调用 `claude -p` 获取回复
- 回复以卡通对话框气泡显示在宠物头顶（10秒）
- Esc 关闭浮条，可拖拽移动
- 卡比兽风格提示文字和颜文字

### 自言自语

- 宠物每隔 1~3 分钟随机说一句话（52 条卡比兽风格短语）
- 以卡通对话框气泡显示（10秒后消失）
- sleeping 状态不弹气泡
- 已显示气泡时有 30% 概率跳过

### 卡通对话框

气泡使用 Canvas 绘制的卡通风格对话框：
- 奶油色 (#FFF8E1) 圆角矩形背景
- 暖棕 (#C4956A) 圆角边框
- 深棕 (#4E342E) 文字
- 45°倾斜暖棕猫爪装饰（左下、右下、左上各一个）
- 三角小尾巴指向宠物

### 10分钟无操作自动睡觉

- 追踪单击、双击、Claude Code 事件时间
- 10分钟无任何交互 → 自动切换到 sleeping 状态
- 有交互时自动唤醒

## Alarm System

### 闹钟功能 (`desktop_pet/alarm.py`)

- 右键 → "闹钟设置" 打开管理窗口
- 支持手动添加自定义闹钟（时间 + 内容 + 星期选择）
- 一键加载 10 个预设模板：喝水 (×4)、吃饭 (×2)、休息、下班 (×2)、查看待办
- 到点弹出居中提醒弹窗，附带系统提示音
- 弹窗支持 "知道了" 关闭 和 "5分钟后提醒" 贪睡
- 后台线程每 30 秒检查系统时间
- 闹钟配置持久化到 `pet_config.json`

### 预设闹钟

| 时间 | 提醒 | 重复 |
|------|------|------|
| 09:00 | 📋 查看今日待办 | 工作日 |
| 10:00 | 💧 该喝水啦！ | 工作日 |
| 11:00 | 💧 补充水分时间 | 工作日 |
| 12:00 | 🍚 中午了，吃饭啦！ | 每天 |
| 14:00 | 💧 下午第一杯水 | 工作日 |
| 15:00 | ☕ 休息一下，活动活动 | 工作日 |
| 16:00 | 💧 该喝水了~ | 工作日 |
| 17:30 | 🏠 快下班啦，整理一下 | 工作日 |
| 18:00 | 🌙 下班时间到！ | 工作日 |
| 19:00 | 🍚 晚饭时间，记得吃饭 | 每天 |

## Hooks Integration

**pet-notify** (`desktop_pet/notify.py`): CLI 命令，从 stdin 读取 Hook JSON，映射到宠物事件。

| Hook 事件 | 宠物事件 | 说明 |
|-----------|---------|------|
| UserPromptSubmit | task_start | 用户提交指令 |
| PreToolUse (Read/Glob/Grep) | reading_start | 读取类工具 |
| PreToolUse (其他) | tool_start | 工具调用开始（思考状态） |
| PostToolUse (Write/Edit/Bash) | step_complete | 高价值工具调用完成 |
| PostToolUse (Bash error) | error | Bash 命令出错 |
| Stop | task_complete | 任务结束 |

**超时自动恢复**: step_done 超过 5s 无新事件 → thinking；thinking 超过 180s → tired；idle 超过 600s → sleeping；**任意状态 10min 无交互 → sleeping**。

## System Tray

- 基于 `pystray` 实现系统托盘图标与右键菜单
- 关闭窗口时最小化到托盘而非退出
- 托盘菜单：显示/隐藏、重置状态、退出
- 托盘图标随宠物状态变化

## API Endpoints

- `POST /event` - 接收事件 `{event, message}`，触发状态变更
- `GET /events` - 获取事件历史 + 当前状态
- `GET /health` - 健康检查

## Key Files

| 文件 | 说明 |
|------|------|
| `desktop_pet/__init__.py` | 包入口，版本号 |
| `desktop_pet/app.py` | Flask HTTP + 启动逻辑 + 闹钟初始化 |
| `desktop_pet/config.py` | 配置系统：加载、校验、持久化，含闹钟 |
| `desktop_pet/state.py` | 状态机 + 卡比兽人格标签和回复 |
| `desktop_pet/gui.py` | GUI + 动画 + 交互 + 托盘 + 自言自语 + 卡通气泡 |
| `desktop_pet/alarm.py` | 闹钟管理器：定时提醒 + 预设模板 + 弹窗 |
| `desktop_pet/chat.py` | 交谈模块：搜狗风格浮条 + Claude CLI 调用 |
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
- 外部工具: `claude` CLI（交谈功能需要）
