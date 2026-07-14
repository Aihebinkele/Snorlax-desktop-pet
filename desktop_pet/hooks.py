"""Claude Code Hooks 安装/卸载管理"""

import json
from pathlib import Path


def get_claude_settings_path():
    """获取项目级 Claude Code 设置文件路径 (PWD/.claude/settings.local.json)

    改为项目级设置，确保桌面宠物 hooks 仅在当前项目生效，
    不会污染其他项目的 Claude Code 会话。
    """
    return Path.cwd() / ".claude" / "settings.local.json"


def load_settings(path):
    """加载设置文件，不存在则返回空 dict"""
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_settings(path, settings):
    """保存设置文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _make_hook_entry(hook_event, matcher=None):
    """创建一个 hook 配置条目"""
    hook_item = {
        "type": "command",
        "command": "pet-notify",
        "timeout": 5,
        "_desktop_pet_managed": True,
    }

    if matcher:
        entry = {
            "matcher": matcher,
            "hooks": [hook_item],
        }
    else:
        entry = {
            "hooks": [hook_item],
        }

    return entry


def _is_managed_entry(entry):
    """检查 hook 条目是否由 desktop-pet 管理"""
    hooks = entry.get("hooks", [])
    return any(h.get("_desktop_pet_managed") for h in hooks)


def install_hooks():
    """安装 Claude Code Hooks 到项目级设置（PWD/.claude/settings.local.json）"""
    settings_path = get_claude_settings_path()
    settings = load_settings(settings_path)

    if "hooks" not in settings:
        settings["hooks"] = {}

    hooks = settings["hooks"]

    # 定义需要安装的 hooks
    hook_definitions = {
        "UserPromptSubmit": [_make_hook_entry("UserPromptSubmit")],
        "PreToolUse": [_make_hook_entry("PreToolUse", matcher="*")],
        "PostToolUse": [_make_hook_entry("PostToolUse", matcher="*")],
        "Stop": [_make_hook_entry("Stop")],
    }

    installed_count = 0
    for event_name, new_entries in hook_definitions.items():
        if event_name not in hooks:
            hooks[event_name] = new_entries
            installed_count += 1
        else:
            # 检查是否已有 managed entry
            existing = hooks[event_name]
            has_managed = any(_is_managed_entry(e) for e in existing)

            if has_managed:
                # 更新已有 managed entry
                updated = []
                for e in existing:
                    if _is_managed_entry(e):
                        updated.append(new_entries[0])
                    else:
                        updated.append(e)
                hooks[event_name] = updated
            else:
                # 追加 managed entry
                hooks[event_name] = existing + new_entries
                installed_count += 1

    save_settings(settings_path, settings)
    print(f"Hooks installed to {settings_path}")
    return 0


def uninstall_hooks():
    """从项目级设置移除 desktop-pet 管理的 Hooks"""
    settings_path = get_claude_settings_path()
    if not settings_path.exists():
        print("No Claude settings file found.")
        return 0

    settings = load_settings(settings_path)
    hooks = settings.get("hooks", {})
    if not hooks:
        print("No hooks found in settings.")
        return 0

    removed_count = 0
    empty_events = []

    for event_name, entries in hooks.items():
        filtered = [e for e in entries if not _is_managed_entry(e)]
        if len(filtered) < len(entries):
            removed_count += len(entries) - len(entries)
        hooks[event_name] = filtered
        if not filtered:
            empty_events.append(event_name)

    for event_name in empty_events:
        del hooks[event_name]

    if not hooks:
        del settings["hooks"]

    save_settings(settings_path, settings)
    print(f"Hooks uninstalled from {settings_path}")
    return 0
