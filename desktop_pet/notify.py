"""Claude Code Hook 脚本：将 Hook 事件转为 HTTP POST 发送到宠物应用"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

PET_APP_URL = f"http://localhost:{os.environ.get('PET_PORT', '3456')}/event"

HIGH_VALUE_TOOLS = frozenset(["Write", "Edit", "MultiEdit", "Bash"])
READ_TOOLS = frozenset(["Read", "Glob", "Grep"])

_TIMEOUT_SECONDS = 5.0
_WAITING_THRESHOLD = 10.0

_TS_FILE = os.path.join(
    os.environ.get("TEMP", os.environ.get("TMP", "/tmp")),
    f"mypet_tool_start_ts_{os.getpid()}.txt",
)


def _log(msg):
    print(f"[pet-notify] {msg}", file=sys.stderr)


def _write_timestamp():
    try:
        with open(_TS_FILE, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def _check_waiting():
    try:
        if os.path.exists(_TS_FILE):
            with open(_TS_FILE) as f:
                start_ts = float(f.read().strip())
            return time.time() - start_ts > _WAITING_THRESHOLD
    except (OSError, ValueError):
        pass
    return False


def _timeout_exit():
    sys.exit(0)


def send_event(event_type, tool_name=""):
    data = json.dumps({"event": event_type, "message": tool_name}).encode("utf-8")
    req = urllib.request.Request(
        PET_APP_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2):
            pass
    except (OSError, urllib.error.URLError) as e:
        _log(f"Failed to send {event_type}: {e}")


def _get_exit_code(parsed):
    top_level = parsed.get("exit_code")
    if top_level is not None:
        return top_level
    top_level = parsed.get("exitCode")
    if top_level is not None:
        return top_level

    tool_output = parsed.get("tool_output", {})
    if isinstance(tool_output, dict):
        ec = tool_output.get("exit_code")
        if ec is not None:
            return ec
        ec = tool_output.get("exitCode")
        return ec if ec is not None else 0
    return 0


def run_notify():
    """Hook 脚本主函数"""
    timer = threading.Timer(_TIMEOUT_SECONDS, _timeout_exit)
    timer.daemon = True
    timer.start()

    input_data = sys.stdin.read()
    try:
        parsed = json.loads(input_data)
        tool_name = parsed.get("tool_name", "unknown")
        hook_event = parsed.get("hook_event_name", "")

        if hook_event == "UserPromptSubmit":
            send_event("task_start", "用户指令")
        elif hook_event == "PreToolUse":
            _write_timestamp()
            if tool_name in READ_TOOLS:
                send_event("reading_start", tool_name)
            else:
                send_event("tool_start", tool_name)
        elif hook_event == "PostToolUse":
            if _check_waiting():
                send_event("user_confirmation_needed", "等待确认")
            if tool_name == "Bash" and _get_exit_code(parsed) != 0:
                send_event("error", f"Bash error: {tool_name}")
                return
            if tool_name in HIGH_VALUE_TOOLS:
                send_event("step_complete", tool_name)
        elif hook_event == "Stop":
            send_event("task_complete", "任务完成")
    except (json.JSONDecodeError, AttributeError):
        if len(sys.argv) >= 3:
            arg = sys.argv[2]
            if arg == "pre":
                send_event("tool_start", "unknown")
            elif arg == "post":
                send_event("step_complete", "unknown")
            elif arg == "stop":
                send_event("task_complete", "unknown")
    finally:
        try:
            if os.path.exists(_TS_FILE):
                os.remove(_TS_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    run_notify()
