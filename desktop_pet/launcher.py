"""
Launch Claude Code with the desktop pet tied to the CLI lifecycle.

The launcher starts pet_app when needed, forwards all arguments to the real
Claude CLI, and stops only the pet process that it started itself.
"""

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _get_base_dir():
    """获取包目录，兼容 pip install 和 PyInstaller"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = _get_base_dir()
PET_HEALTH_URL = f"http://127.0.0.1:{os.environ.get('PET_PORT', '3456')}/health"
APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DesktopPet"
PET_LOG = APP_DATA_DIR / "pet_launcher.log"
DEFAULT_CLAUDE = Path(
    r"d:\Program Files\nodejs\node_modules\@anthropic-ai\claude-code\bin\claude.exe"
)
COMMON_CLAUDE_PATHS = [
    DEFAULT_CLAUDE,
    Path(r"C:\Program Files\nodejs\node_modules\@anthropic-ai\claude-code\bin\claude.exe"),
    Path(r"C:\Program Files (x86)\nodejs\node_modules\@anthropic-ai\claude-code\bin\claude.exe"),
]


def is_pet_running():
    try:
        with urllib.request.urlopen(PET_HEALTH_URL, timeout=0.4) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def wait_for_pet(timeout_seconds=8):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if is_pet_running():
            return True
        time.sleep(0.2)
    return False


def start_pet():
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(PET_LOG, "a", encoding="utf-8")
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    if getattr(sys, "frozen", False):
        command = [str(BASE_DIR / "DesktopPet.exe")]
        cwd = str(BASE_DIR)
    else:
        command = [sys.executable, "-m", "desktop_pet.app"]
        cwd = str(BASE_DIR)

    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        process._pet_log_file = log_file
        return process
    except Exception:
        log_file.close()
        raise


def stop_pet(process):
    if not process:
        return

    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
    finally:
        log_file = getattr(process, "_pet_log_file", None)
        if log_file:
            log_file.close()


def real_claude_path():
    configured = os.environ.get("CLAUDE_PET_REAL_CLAUDE")
    if configured:
        return Path(configured)

    for candidate in COMMON_CLAUDE_PATHS:
        if candidate.exists():
            return candidate

    for command_name in ("claude.exe", "claude.cmd", "claude"):
        found = shutil.which(command_name)
        if found:
            return Path(found)

    return DEFAULT_CLAUDE


def run_launcher():
    """Claude 生命周期启动器主函数"""
    pet_process = None
    started_pet = False

    if not is_pet_running():
        pet_process = start_pet()
        started_pet = True
        if not wait_for_pet():
            stop_pet(pet_process)
            print("Desktop pet failed to start. See pet_launcher.log.", file=sys.stderr)
            return 1

    claude = real_claude_path()
    if not claude.exists():
        if started_pet:
            stop_pet(pet_process)
        print(f"Claude CLI not found: {claude}", file=sys.stderr)
        print("Set CLAUDE_PET_REAL_CLAUDE to override the path.", file=sys.stderr)
        return 1

    try:
        completed = subprocess.run([str(claude), *sys.argv[1:]], cwd=os.getcwd())
        return completed.returncode
    except KeyboardInterrupt:
        return 130
    finally:
        if started_pet:
            stop_pet(pet_process)


if __name__ == "__main__":
    raise SystemExit(run_launcher())
