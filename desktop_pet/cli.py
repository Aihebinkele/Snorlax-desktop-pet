"""Desktop Pet CLI 入口"""

import sys

from desktop_pet import __version__


def main():
    """desktop-pet 命令入口"""
    args = sys.argv[1:]

    if not args:
        from desktop_pet.app import run_pet
        return run_pet()

    if args[0] == "--version":
        print(f"claude-desktop-pet {__version__}")
        return 0

    if args[0] == "install-hooks":
        from desktop_pet.hooks import install_hooks
        return install_hooks()

    if args[0] == "uninstall-hooks":
        from desktop_pet.hooks import uninstall_hooks
        return uninstall_hooks()

    print(f"Unknown argument: {args[0]}", file=sys.stderr)
    print("Usage: desktop-pet [--version] [install-hooks|uninstall-hooks]", file=sys.stderr)
    return 1


def notify_main():
    """pet-notify 命令入口"""
    from desktop_pet.notify import run_notify
    run_notify()
    return 0


def launcher_main():
    """claude-pet 命令入口"""
    from desktop_pet.launcher import run_launcher
    return run_launcher()
