# Desktop Pet — 卡比兽

> 一只可爱的卡比兽桌面宠物，能实时感知你的编程状态，陪你写代码、提醒你喝水吃饭、跟你聊天。

## ✨ 功能

- 🐱 **卡比兽人格** — 自称"咔比"，叫用户"主人"，可爱颜文字风格
- 🔌 **Claude Code Hooks 集成** — 实时感知编码状态，9种状态动画
- 💬 **Claude 对话** — 双击宠物直接跟 Claude Code 聊天，回复以气泡显示
- ⏰ **闹钟提醒** — 定时提醒吃饭、喝水、休息、下班
- 🗣️ **自言自语** — 52条随机短语，每1~3分钟冒泡卖萌
- 🎨 **卡通对话框** — 奶油色圆角气泡 + 暖棕边框 + 猫爪装饰
- 😴 **自动睡觉** — 10分钟不操作自动呼呼大睡

## 🚀 快速开始

```bash
# 1. 安装
pip install -e .

# 2. 配置 Hooks（可选，用于感知 Claude Code 状态）
desktop-pet install-hooks

# 3. 启动宠物
desktop-pet
```

## 🎮 交互

| 操作 | 效果 |
|------|------|
| **单击** | 显示对话气泡（睡觉时唤醒） |
| **双击** | 打开对话浮条，跟 Claude 聊天 |
| **拖拽** | 移动宠物位置 |
| **右键** | 菜单：交谈 / 设置 / 闹钟 / 重置 / 隐藏 / 退出 |

## ⏰ 闹钟预设

| 时间 | 提醒 |
|------|------|
| 10:00 / 11:00 / 14:00 / 16:00 | 💧 喝水 |
| 12:00 / 19:00 | 🍚 吃饭 |
| 15:00 | ☕ 休息活动 |
| 17:30 / 18:00 | 🏠 下班 |

右键 → **闹钟设置** 可自定义添加/修改。

## 🎭 状态一览

| 状态 | 标签 | 触发 |
|------|------|------|
| 🐱 呼噜噜~ | idle | 默认 |
| 📖 看看主人在干嘛... | reading | 读取文件 |
| ✅ 做完啦！ | step_done | 步骤完成 |
| 🎉 开心！ | happy | 任务完成 |
| 😴 呼呼呼...咔比~ | sleeping | 10分钟无操作 |
| 💭 咔比正在想... | thinking | Claude 思考中 |

## 📁 项目结构

```
desktop_pet/
├── app.py          # Flask + Tkinter 入口
├── gui.py          # GUI + 动画 + 气泡 + 自言自语
├── state.py        # 卡比兽状态机
├── alarm.py        # 闹钟管理
├── chat.py         # Claude 对话浮条
├── config.py       # 配置系统
├── notify.py       # Hook 脚本
├── hooks.py        # Hook 安装
├── launcher.py     # Claude CLI 生命周期
└── pet_images/     # 9张状态图片
```

## 🔧 需求

- Python 3.8+
- flask, Pillow, pystray
- `claude` CLI（交谈功能需要）
- Windows（winsound 音效）

## 📡 API

```
POST /event      # 发送事件 {event, message}
GET /events      # 事件历史 + 当前状态
GET /health      # 健康检查
```

服务监听 `http://127.0.0.1:3456`。

## 🧹 卸载

```bash
desktop-pet uninstall-hooks
pip uninstall claude-desktop-pet
# 删除配置：%LOCALAPPDATA%\DesktopPet\
```
