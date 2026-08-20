"""工作目录 git 状态（懒刷新 30s，cwd 变化立即刷新）。"""

import os
import subprocess
import threading
import time


class GitInfo:
    REFRESH_SECONDS = 30.0

    def __init__(self):
        self._lock = threading.Lock()
        self._cwd = None
        self._snapshot = None  # dict 或 None（无仓库/未刷出）
        self._last_refresh = 0.0
        self._fetching = False

    def set_cwd(self, cwd):
        with self._lock:
            if cwd != self._cwd:
                self._cwd = cwd
                self._last_refresh = 0.0   # 切目录强制立即刷新
                self._snapshot = None

    def get(self):
        """返回 git 快照 dict 或 None；到刷新窗口时触发一次后台刷新。"""
        with self._lock:
            cwd = self._cwd
            snapshot = self._snapshot
            last = self._last_refresh
        if not cwd:
            return None
        if time.time() - last >= self.REFRESH_SECONDS:
            self._refresh(cwd)
        with self._lock:
            return self._snapshot

    def force_refresh(self):
        """立即触发一次后台刷新（抽打按钮用）。"""
        with self._lock:
            cwd = self._cwd
            self._last_refresh = 0.0
        if cwd:
            self._refresh(cwd)

    def _refresh(self, cwd):
        with self._lock:
            if self._fetching:
                return
            self._fetching = True

        def worker():
            try:
                snap = self._run(cwd)
                with self._lock:
                    self._snapshot = snap
                    self._last_refresh = time.time()
                    self._fetching = False
            except Exception:
                with self._lock:
                    self._fetching = False

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _run(cwd):
        def git(*args):
            try:
                kwargs = {"cwd": cwd, "capture_output": True, "text": True, "timeout": 10}
                if os.name == "nt":
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                r = subprocess.run(["git", *args], **kwargs)
                return r.stdout if r.returncode == 0 else ""
            except Exception:
                return ""

        branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
        head = git("rev-parse", "--short", "HEAD").strip()
        porcelain = git("status", "--porcelain")

        # 空输出 = 干净仓库；但「非 git 仓库」时 branch/head/status 都是空，
        # 用 rev-parse 是否成功来区分（branch 为 HEAD 表示 detached）。
        if branch == "" and head == "":
            return None

        dirty = untracked = conflicts = 0
        for line in porcelain.splitlines():
            if not line.strip():
                continue
            xy = line[:2]
            if xy == "??":
                untracked += 1
            elif "U" in xy or "DD" in xy or "AA" in xy:
                conflicts += 1
            else:
                dirty += 1

        return {
            "branch": "" if branch == "HEAD" else branch,
            "head": head,
            "dirty": dirty,
            "untracked": untracked,
            "conflicts": conflicts,
        }
