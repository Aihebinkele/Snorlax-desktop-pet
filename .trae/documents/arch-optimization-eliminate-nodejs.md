# 架构优化计划：消除 Node.js 中间层 + 修复硬编码路径

## 目标

将项目从 `Hook → Node.js(cjs) → HTTP POST → Flask → Tkinter` 简化为 `Hook → Python(py) → HTTP POST → Flask → Tkinter`，消除 Node.js 依赖，修复硬编码路径，清理冗余代码。

## 变更清单

### 1. 新建 `hooks/pet-notify.py`

- 用 Python 标准库 `urllib.request` 发送 HTTP POST，逻辑与 `pet-notify.cjs` 完全对等
- 从 stdin 读取 JSON，解析 `hook_event_name` 和 `tool_name`
- 映射规则不变：UserPromptSubmit→task_start, PreToolUse→task_start, PostToolUse+高价值工具→step_complete, Stop→task_complete
- 2 秒请求超时，5 秒全局超时兜底
- fallback 逻辑：JSON 解析失败时根据 argv[2] 推断事件类型
- 目标 URL：`http://localhost:3456/event`

### 2. 更新 `.claude/settings.local.json`

- hooks 部分：将所有 `node "$CLAUDE_PROJECT_DIR"/.claude/hooks/pet-notify.cjs` 改为 `python "$CLAUDE_PROJECT_DIR"/hooks/pet-notify.py`
- permissions.allow 部分：清理历史调试用的 Bash 权限，只保留必要的通用权限

### 3. 删除 `.codex/` 目录

- 删除 `.codex/hooks/pet-notify.cjs`
- 删除 `.codex/hooks.json`
- 删除 `.codex/config.toml`
- 删除 `.codex/` 目录本身

### 4. 删除 `.claude/hooks/pet-notify.cjs`

- 已被 `hooks/pet-notify.py` 替代

### 5. 删除 `cmd_autorun.cmd`

- 硬编码了旧路径 `G:\projects\mypet\claude-pet.cmd`，不再需要
- 安装器 `install_desktop_pet.ps1` 会动态生成自己的 cmd_autorun 内容，不受影响

### 6. 更新 `CLAUDE.md` 和 `AGENTS.md`

- 架构图：去掉 Node.js 中间层描述，改为 Python Hook 脚本
- Hooks Integration 部分：更新脚本路径和语言
- Key Files 部分：替换 `.claude/hooks/pet-notify.cjs` 为 `hooks/pet-notify.py`
- Dependencies 部分：去掉 Node.js 依赖说明
- AGENTS.md：去掉 Codex 相关描述
- 删除对 `.Codex/` 目录的引用

### 7. 更新 `.gitignore`

- 移除与 `.codex/` 相关的忽略规则（如有）

## 不变更

- `pet_app.py` — 主程序逻辑不变
- `claude_pet_launcher.py` — 生命周期管理不变
- `pet_config.json` — 配置不变
- `pet_images/` — 图片资源不变
- `build_installer.ps1` — 构建脚本不变（不涉及被删除文件）
- `installer/` — 安装脚本不变（动态生成 cmd_autorun 内容，不依赖根目录的 cmd_autorun.cmd）
- `claude-pet.ps1` / `claude-pet.cmd` — shim 脚本不变

## 验证步骤

1. 运行 `python hooks/pet-notify.py` 确认脚本无语法错误
2. 检查 `.claude/settings.local.json` 的 JSON 格式正确性
3. 确认 `.codex/` 目录已完全删除
4. 确认 `cmd_autorun.cmd` 已删除
5. 确认 `.claude/hooks/pet-notify.cjs` 已删除
6. 全文搜索确认无残留的 `pet-notify.cjs` 引用
7. 全文搜索确认无残留的 `.codex` 引用
8. 全文搜索确认无残留的 `G:\projects\mypet` 硬编码路径
