import copy
import json
import logging
import os
import sys

logger = logging.getLogger()


def _get_resource_dir():
    """获取包资源目录，兼容 pip install 和 PyInstaller"""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


RESOURCE_DIR = _get_resource_dir()
APP_DATA_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "DesktopPet"
)
CONFIG_PATH = os.path.join(APP_DATA_DIR, "pet_config.json")
DEFAULT_CONFIG_PATH = os.path.join(RESOURCE_DIR, "default_config.json")

ANIM_CONFIG = {
    "idle":       {"type": "float",       "amp_y": 3,   "speed": 0.05},
    "reading":    {"type": "pulse_slow",  "amp_y": 4,   "speed": 0.1},
    "step_done":  {"type": "pulse",       "amp_y": 6,   "speed": 0.2},
    "happy":      {"type": "bounce",      "amp_y": 8,   "speed": 0.2},
    "waiting":    {"type": "sway",        "amp_x": 6,   "speed": 0.04},
    "sad":        {"type": "droop",       "amp_y": 5,   "speed": 0.02},
    "tired":      {"type": "slow_tremble","amp": 0.75,  "speed": 0.015},
    "sleeping":   {"type": "breathe",     "amp_y": 2,   "speed": 0.02},
    "thinking":   {"type": "pulse_slow",  "amp_y": 4,   "speed": 0.1},
}

DEFAULT_APP_CONFIG = {
    "sound_enabled": True,
    "window": {
        "width": 380,
        "height": 260,
    },
    "state_durations": {
        "step_done": 1500,
        "happy": 5000,
        "waiting": 8000,
        "sad": 5000,
        "tired": 0,
        "sleeping": 0,
        "thinking": 0,
        "reading": 2000,
    },
    "step_done_timeout_ms": 5000,
    "thinking_tired_timeout_ms": 180000,
    "idle_sleeping_timeout_ms": 600000,
    "animations": ANIM_CONFIG,
    "alarms": [],
}


def _deep_merge(defaults, override):
    result = copy.deepcopy(defaults)
    if not isinstance(override, dict):
        return result

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _clamp_int(value, default, min_value, max_value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def normalize_app_config(config):
    config = _deep_merge(DEFAULT_APP_CONFIG, config)
    window = config["window"]
    window["width"] = _clamp_int(window.get("width"), 300, 220, 600)
    window["height"] = _clamp_int(window.get("height"), 240, 180, 500)

    sound_enabled = config.get("sound_enabled", True)
    if isinstance(sound_enabled, bool):
        config["sound_enabled"] = sound_enabled
    elif isinstance(sound_enabled, str):
        config["sound_enabled"] = sound_enabled.lower() not in ("false", "0", "no")
    else:
        config["sound_enabled"] = bool(sound_enabled)
    config["step_done_timeout_ms"] = _clamp_int(
        config.get("step_done_timeout_ms"), 5000, 1000, 60000
    )
    config["thinking_tired_timeout_ms"] = _clamp_int(
        config.get("thinking_tired_timeout_ms"), 180000, 10000, 600000
    )
    config["idle_sleeping_timeout_ms"] = _clamp_int(
        config.get("idle_sleeping_timeout_ms"), 600000, 60000, 1800000
    )

    for state, default_ms in DEFAULT_APP_CONFIG["state_durations"].items():
        config["state_durations"][state] = _clamp_int(
            config["state_durations"].get(state), default_ms, 0, 60000
        )

    # Normalize alarms
    alarms = config.get("alarms", [])
    if not isinstance(alarms, list):
        alarms = []
    normalized_alarms = []
    seen_ids = set()
    for alarm in alarms:
        if not isinstance(alarm, dict):
            continue
        alarm_id = str(alarm.get("id", ""))
        if not alarm_id or alarm_id in seen_ids:
            continue
        seen_ids.add(alarm_id)

        normalized = {
            "id": alarm_id,
            "time": str(alarm.get("time", "09:00")),
            "label": str(alarm.get("label", "⏰ 闹钟")),
            "enabled": bool(alarm.get("enabled", False)),
            "days": _normalize_days(alarm.get("days", [0, 1, 2, 3, 4])),
        }
        # Validate time format HH:MM
        try:
            parts = normalized["time"].split(":")
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                normalized["time"] = "09:00"
        except (ValueError, IndexError):
            normalized["time"] = "09:00"

        normalized_alarms.append(normalized)
    config["alarms"] = normalized_alarms

    return config


def _normalize_days(days):
    """标准化星期数组，返回排序后的合法值列表"""
    if not isinstance(days, list):
        return [0, 1, 2, 3, 4]
    result = []
    seen = set()
    for d in days:
        try:
            day = int(d)
            if 0 <= day <= 6 and day not in seen:
                result.append(day)
                seen.add(day)
        except (TypeError, ValueError):
            continue
    result.sort()
    return result if result else [0, 1, 2, 3, 4]


def load_app_config():
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        config = normalize_app_config({})
        if os.path.exists(DEFAULT_CONFIG_PATH):
            try:
                with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = normalize_app_config(json.load(f))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(f"Failed to load bundled config, using defaults: {exc}")
        save_app_config(config)
        return config

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return normalize_app_config(json.load(f))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"Failed to load config, using defaults: {exc}")
        return normalize_app_config({})


def save_app_config(config):
    try:
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(normalize_app_config(config), f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as exc:
        logger.error(f"Failed to save config: {exc}")
