import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from desktop_pet.hooks import install_hooks, uninstall_hooks, load_settings, save_settings


def test_install_hooks_creates_new_settings():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings_path = Path(tmpdir) / "settings.json"
        with mock.patch("desktop_pet.hooks.get_claude_settings_path", return_value=settings_path):
            result = install_hooks()

        assert result == 0
        settings = load_settings(settings_path)
        assert "hooks" in settings
        assert "UserPromptSubmit" in settings["hooks"]
        assert "PreToolUse" in settings["hooks"]
        assert "PostToolUse" in settings["hooks"]
        assert "Stop" in settings["hooks"]

        # Verify hook command uses pet-notify
        for event_hooks in settings["hooks"].values():
            for entry in event_hooks:
                for hook in entry.get("hooks", []):
                    assert hook["command"] == "pet-notify"
                    assert hook.get("_desktop_pet_managed") is True


def test_install_hooks_preserves_existing():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings_path = Path(tmpdir) / "settings.json"
        existing = {
            "hooks": {
                "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "other-script"}]}]
            }
        }
        save_settings(settings_path, existing)

        with mock.patch("desktop_pet.hooks.get_claude_settings_path", return_value=settings_path):
            install_hooks()

        settings = load_settings(settings_path)
        # Should have both the existing hook and the managed hook
        ups_hooks = settings["hooks"]["UserPromptSubmit"]
        assert len(ups_hooks) == 2
        commands = [h["hooks"][0]["command"] for h in ups_hooks]
        assert "other-script" in commands
        assert "pet-notify" in commands


def test_uninstall_hooks_removes_managed():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings_path = Path(tmpdir) / "settings.json"
        with mock.patch("desktop_pet.hooks.get_claude_settings_path", return_value=settings_path):
            install_hooks()
            result = uninstall_hooks()

        assert result == 0
        settings = load_settings(settings_path)
        # All managed hooks should be removed, hooks key should be gone
        assert "hooks" not in settings or not settings.get("hooks", {})


def test_uninstall_hooks_preserves_other_hooks():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings_path = Path(tmpdir) / "settings.json"
        existing = {
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": "other-script"}]},
                    {"hooks": [{"type": "command", "command": "pet-notify", "_desktop_pet_managed": True}]}
                ]
            }
        }
        save_settings(settings_path, existing)

        with mock.patch("desktop_pet.hooks.get_claude_settings_path", return_value=settings_path):
            uninstall_hooks()

        settings = load_settings(settings_path)
        ups_hooks = settings["hooks"]["UserPromptSubmit"]
        assert len(ups_hooks) == 1
        assert ups_hooks[0]["hooks"][0]["command"] == "other-script"


def test_uninstall_hooks_no_settings_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings_path = Path(tmpdir) / "settings.json"
        with mock.patch("desktop_pet.hooks.get_claude_settings_path", return_value=settings_path):
            result = uninstall_hooks()
        assert result == 0
