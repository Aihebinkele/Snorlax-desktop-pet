# 产品化计划：Desktop Pet pip install 分发

## 摘要

将 Desktop Pet 从"源码项目"转变为可通过 `pip install` 一键安装的 Python 包，删除旧的 IExpress 安装器，实现 Claude Code Hooks 自动配置与卸载清理。

## 当前状态分析

### 现有结构

- 扁平文件布局：`pet_app.py`, `pet_config.py`, `pet_state.py`, `pet_gui.py`, `pet_shared.py` 等直接放在项目根目录
- 无 Python 包结构（无 `__init__.py`、无 `pyproject.toml`）
- 资源路径依赖 `__file__` 相对路径 + PyInstaller `_MEIPASS` 兜底
- Hooks 配置硬编码在项目级 `.claude/settings.local.json`，命令为 `python "$CLAUDE_PROJECT_DIR"/hooks/pet-notify.py`
- 安装器基于 IExpress（`build_installer.ps1` + `installer/`），用户要求完全删除
- `pet_config.json` 中有已废弃的 `working` 状态配置，`pet_images/working.png` 为死资源

### 关键依赖

- Flask==3.1.3, Pillow==11.0.0, pystray==0.19.5
- Windows-only: `winsound`（标准库）, `tkinter`（标准库）

## 变更方案

### 1. 创建 Python 包结构

**目标**：将扁平文件重组为 `desktop_pet/` 包目录

**新结构**：

```
g:\projects\mypet\
├── desktop_pet/
│   ├── __init__.py          # 版本号 + 包元数据
│   ├── __main__.py          # python -m desktop_pet 入口
│   ├── app.py               # 原 pet_app.py
│   ├── config.py            # 原 pet_config.py
│   ├── state.py             # 原 pet_state.py
│   ├── gui.py               # 原 pet_gui.py
│   ├── shared.py            # 原 pet_shared.py
│   ├── launcher.py          # 原 claude_pet_launcher.py
│   ├── notify.py            # 原 hooks/pet-notify.py
│   ├── cli.py               # CLI 命令入口（desktop-pet, pet-notify, claude-pet）
│   ├── hooks.py             # Hooks 安装/卸载逻辑
│   ├── pet_images/          # 状态图片（package data）
│   │   ├── idle.png
│   │   ├── happy.png
│   │   ├── sad.png
│   │   ├── step_done.png
│   │   ├── waiting.png
│   │   ├── reading.png      # 需补充
│   │   ├── thinking.png     # 需补充
│   │   ├── tired.png        # 需补充
│   │   └── sleeping.png     # 需补充
│   └── default_config.json  # 默认配置（原 pet_config.json，清理废弃项）
├── tests/
│   ├── test_state.py        # 原 test_pet_state.py，更新 import
│   └── test_config.py       # 原 test_pet_config.py，更新 import
├── pyproject.toml           # 包定义
├── README.md
├── .gitignore
├── .claude/
│   └── settings.local.json  # 保留但更新 hooks 命令
├── AGENTS.md
├── CLAUDE.md
└── .mcp.json
```

**具体操作**：

- 移动 `pet_app.py` → `desktop_pet/app.py`，更新内部 import
- 移动 `pet_config.py` → `desktop_pet/config.py`，更新 `RESOURCE_DIR` 计算
- 移动 `pet_state.py` → `desktop_pet/state.py`
- 移动 `pet_gui.py` → `desktop_pet/gui.py`，更新 import
- 移动 `pet_shared.py` → `desktop_pet/shared.py`
- 移动 `claude_pet_launcher.py` → `desktop_pet/launcher.py`
- 移动 `hooks/pet-notify.py` → `desktop_pet/notify.py`
- 移动 `pet_images/` → `desktop_pet/pet_images/`
- 移动 `pet_config.json` → `desktop_pet/default_config.json`（清理 `working` 废弃项）
- 删除根目录原文件

### 2. 创建 pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68.0", "setuptools-scm"]
build-backend = "setuptools.build_meta"

[project]
name = "claude-desktop-pet"
version = "1.0.0"
description = "Claude Code 桌面宠物伴侣 - 实时感知开发状态"
readme = "README.md"
requires-python = ">=3.8"
license = {text = "MIT"}
dependencies = [
    "flask>=3.0",
    "Pillow>=10.0",
    "pystray>=0.19",
]

[project.scripts]
desktop-pet = "desktop_pet.cli:main"
pet-notify = "desktop_pet.cli:notify_main"
claude-pet = "desktop_pet.cli:launcher_main"

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[tool.setuptools.packages.find]
include = ["desktop_pet*"]

[tool.setuptools.package-data]
desktop_pet = ["pet_images/*.png", "default_config.json"]
```

### 3. 创建 CLI 入口 (`desktop_pet/cli.py`)

提供三个命令入口：

- **`desktop-pet`**：启动宠物应用（等同原 `python pet_app.py`）
- **`pet-notify`**：Hook 脚本入口（等同原 `python hooks/pet-notify.py`）
- **`claude-pet`**：Claude 生命周期启动器（等同原 `python claude_pet_launcher.py`）

额外子命令：

- **`desktop-pet install-hooks`**：安装 Claude Code Hooks 到用户级配置 `~/.claude/settings.json`
- **`desktop-pet uninstall-hooks`**：从用户级配置移除 Hooks
- **`desktop-pet --version`**：显示版本号

### 4. Hooks 安装/卸载逻辑 (`desktop_pet/hooks.py`)

**安装逻辑**：

1. 读取 `~/.claude/settings.json`（不存在则创建）
2. 在 `hooks` 字段中添加/更新 4 个 Hook 事件：
   - `UserPromptSubmit` → `pet-notify`
   - `PreToolUse` → `pet-notify`
   - `PostToolUse` → `pet-notify`
   - `Stop` → `pet-notify`
3. Hook 命令使用 `pet-notify`（pip 安装后的 CLI 入口），不再依赖 `$CLAUDE_PROJECT_DIR`
4. 保留用户已有的其他 hooks 配置（合并而非覆盖）
5. 添加标记字段（如 `_desktop_pet_managed: true`）便于卸载时识别

**卸载逻辑**：

1. 读取 `~/.claude/settings.json`
2. 移除所有带 `_desktop_pet_managed` 标记的 hooks
3. 清理空 hooks 字段

### 5. 更新资源路径计算 (`desktop_pet/config.py`)

当前 `RESOURCE_DIR` 逻辑：

```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
```

更新为：

```python
import importlib.resources

def _get_resource_dir():
    """获取包资源目录，兼容 pip install 和 PyInstaller"""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    # pip install 后，资源在包目录内
    return os.path.dirname(os.path.abspath(__file__))

RESOURCE_DIR = _get_resource_dir()
```

`DEFAULT_CONFIG_PATH` 更新为指向 `default_config.json`（而非 `pet_config.json`）。

### 6. 删除安装器相关文件

删除以下文件/目录：

- `build_installer.ps1`
- `installer/` 目录（`install_desktop_pet.ps1`, `install_desktop_pet.cmd`）
- `claude-pet.ps1`
- `claude-pet.cmd`
- `requirements.txt`（被 `pyproject.toml` 替代）

### 7. 清理废弃数据

- 从 `default_config.json` 中移除 `working` 相关配置（`working_timeout_ms`, `working_tired_timeout_ms`, `animations.working`）
- 删除 `pet_images/working.png`（死资源）
- 补充缺失的状态图片（`reading.png`, `thinking.png`, `tired.png`, `sleeping.png`）—— 当前代码用灰色占位图兜底，产品化应有完整图片

### 8. 更新测试

- 移动 `tests/test_pet_state.py` → `tests/test_state.py`
- 移动 `tests/test_pet_config.py` → `tests/test_config.py`
- 更新 import：`from pet_state import ...` → `from desktop_pet.state import ...`
- 更新 import：`from pet_config import ...` → `from desktop_pet.config import ...`
- 新增 `tests/test_hooks.py`：测试 hooks 安装/卸载逻辑

### 9. 更新 .gitignore

移除不再需要的条目：

- `build_installer/`
- `release/`
- `*.spec`

保留：

- `*.egg-info/`
- `dist/`
- `build/`

### 10. 更新项目文档

- 更新 `AGENTS.md` 和 `CLAUDE.md` 中的文件路径、命令、架构描述
- 更新 `.claude/settings.local.json` 中的 hooks 命令为 `pet-notify`

## 假设与决策

| 决策项        | 选择                            | 理由                             |
| ---------- | ----------------------------- | ------------------------------ |
| 包名         | `claude-desktop-pet`          | PyPI 包名，避免与通用 `desktop-pet` 冲突 |
| import 名   | `desktop_pet`                 | Python 导入名，符合 PEP 8            |
| 包布局        | 扁平布局（无 src/）                  | 项目规模小，简单直接                     |
| Hooks 安装位置 | 用户级 `~/.claude/settings.json` | 全局生效，所有项目自动可用                  |
| 版本号        | 1.0.0                         | 首次产品化发布                        |
| 依赖版本       | 宽松下限（`>=`）                    | 避免过度锁定，兼容更多环境                  |
| 缺失图片       | 用代码生成简单占位图                    | 产品化不能缺图，但不需要精美设计               |

## 验证步骤

1. `pip install -e .` 成功安装
2. `desktop-pet --version` 输出 `1.0.0`
3. `desktop-pet` 启动宠物窗口，状态切换正常
4. `desktop-pet install-hooks` 成功写入 `~/.claude/settings.json`
5. `pet-notify` 从 stdin 读取 JSON 并发送 HTTP 请求
6. `desktop-pet uninstall-hooks` 成功清理 hooks
7. `pip uninstall claude-desktop-pet` 干净卸载
8. `python -m pytest tests/` 全部通过
9. `python -m desktop_pet` 等同 `desktop-pet` 命令

