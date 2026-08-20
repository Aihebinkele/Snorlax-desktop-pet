# Desktop Pet — 卡比兽

> 一只可爱的卡比兽桌面宠物，能实时感知你的编程状态，陪你写代码、提醒你喝水吃饭、跟你聊天。

## ✨ 功能

- 🐱 **卡比兽人格** — 自称"咔比"，叫用户"主人"，可爱颜文字风格
- 🔌 **Claude Code Hooks 集成** — 实时感知编码状态，9 种状态动画
- 💬 **Claude 对话** — 双击宠物直接跟 Claude Code 聊天，回复以气泡显示
- 📊 **常驻数据条 + 统计面板** — 宠物下方实时显示花费 / 涨价前对比 / 缓存命中率 / 饱腹度 / 余额 / git 状态，点开看完整明细
- 💰 **监控 Token** — 监控 DeepSeek / 豆包 / 千问 / 智谱 / 混元等供应商，余额实时查询（<10 元告警）
- 🛠 **Git 状态** — 自动读取工作目录分支与改动 / 冲突数
- ⏰ **闹钟提醒** — 定时提醒吃饭、喝水、休息、下班（电子钟提醒弹窗）
- 🗣️ **自言自语** — 52 条随机短语，每 1~3 分钟冒泡卖萌
- 🎨 **卡通对话框** — 奶油色圆角气泡 + 暖棕边框 + 猫爪装饰
- 😴 **自动睡觉** — 10 分钟不操作自动呼呼大睡

## 🚀 快速开始

```bash
# 1. 安装
pip install -e .

# 2. 配置 Hooks（可选，用于感知 Claude Code 状态 + 用量统计）
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
| **单击底部数据条** | 展开 / 收起统计面板 |
| **右键** | 菜单：交谈 / 统计 / 监控Token / 显示数据条 / 设置 / 闹钟设置 / 重置状态 / 隐藏 / 退出 |

## 📊 数据条与统计面板

宠物正下方常驻一条数据条，实时显示：

| 图标 | 含义 |
|------|------|
| 🍖 | 饱腹度（上下文窗口占用，>85% 橙色） |
| 💸 | 本轮累计花费（按 DeepSeek 高峰/空闲分档计价） |
| ⚡ | 缓存命中率 |
| 💰 | DeepSeek 余额（<10 元变红） |
| 🛠 | 工作目录 git 分支 + 改动数（冲突变红） |

单击数据条打开完整统计面板，展示花费高峰/空闲分档、涨价前对比、三种口粮（系统/工具/对话）、效率、性能（LLM/工具/首 token/吞吐）与 git 详情。

数据来源：解析 Claude Code transcript JSONL（hook 传入 `transcript_path`），与 Claude Code 状态栏同源；累计量持久化到 `%LOCALAPPDATA%\DesktopPet\pet_stats.json`。

## 🔑 配置与 API Key

配置文件：`%LOCALAPPDATA%\DesktopPet\pet_config.json`

监控供应商的 API Key 写在这里的 `monitor.keys` 字段（按供应商 id 区分）：

```json
{
  "monitor": {
    "provider": "deepseek",
    "keys": {
      "deepseek": "sk-...",
      "doubao": "",
      "qwen": "",
      "zhipu": "",
      "hunyuan": ""
    }
  }
}
```

> 密钥只写本地 `pet_config.json`，不会写进仓库里打包的 `default_config.json`（那里 key 均为空串）。

## ⏰ 闹钟预设

| 时间 | 提醒 |
|------|------|
| 10:00 / 11:00 / 14:00 / 16:00 | 💧 喝水 |
| 12:00 / 19:00 | 🍚 吃饭 |
| 15:00 | ☕ 休息活动 |
| 17:30 / 18:00 | 🏠 下班 |

右键 → **闹钟设置** 可自定义添加/修改，支持「预览」提醒弹窗。

## 🎭 状态一览

| 状态 | 标签 | 触发 |
|------|------|------|
| 🐱 呼噜噜~ | idle | 默认 |
| 📖 看看主人在干嘛... | reading | 读取文件 |
| ✅ 做完啦！厉害~ | step_done | 步骤完成 |
| 🎉 开心！( ´・∀・)ﾉ | happy | 任务完成 |
| 🤔 主人你在哪？ | waiting | 等待输入 |
| 😵 呜呜...不开心 | sad | 出错 |
| 😴 困困...想睡觉 | tired | 疲劳 |
| 💤 呼呼呼...咔比~ | sleeping | 10 分钟无操作 |
| 🤔 咔比正在想... | thinking | Claude 思考中 |

## 📁 项目结构

```
desktop_pet/
├── app.py          # Flask + Tkinter 入口
├── gui.py          # GUI + 动画 + 气泡 + 数据条/统计面板
├── state.py        # 卡比兽状态机
├── stats.py        # 用量统计（花费/效率/饱腹度）
├── pricing.py      # DeepSeek 定价常量
├── balance.py      # 余额查询（懒刷新）
├── gitinfo.py      # 工作目录 git 状态
├── providers.py    # AI 供应商注册表
├── alarm.py        # 闹钟管理 + 提醒弹窗
├── chat.py         # Claude 对话浮条
├── config.py       # 配置系统
├── shared.py       # 共享单例（stats/balance/git）
├── notify.py       # Hook 脚本
├── hooks.py        # Hook 安装
├── launcher.py     # Claude CLI 生命周期
└── pet_images/     # 9 张状态图片
```

## 🔧 需求

- Python 3.8+
- flask, Pillow, pystray
- `claude` CLI（交谈功能需要）
- Windows（winsound 音效）

## 📡 API

```
POST /event      # 发送事件 {event, message, transcript_path, cwd}
GET /events      # 事件历史 + 当前状态
GET /health      # 健康检查
GET /stats       # 完整统计（花费/效率/饱腹度/余额/git）
GET /balance     # 余额
```

服务监听 `http://127.0.0.1:3456`。

## 🧹 卸载

```bash
desktop-pet uninstall-hooks
pip uninstall claude-desktop-pet
# 删除配置：%LOCALAPPDATA%\DesktopPet\
```
