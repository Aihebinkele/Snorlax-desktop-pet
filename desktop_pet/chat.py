"""交谈模块 - 搜狗输入法风格迷你浮条，与 Claude Code 交互，回复以气泡显示"""

import logging
import subprocess
import threading
import tkinter as tk

logger = logging.getLogger()

import shutil as _shutil
_CLAUDE_CLI = _shutil.which("claude") or r"C:\Users\IES15c172\AppData\Roaming\npm\claude"

# ── 搜狗风格配色 ──
C_BAR_BG = "#FFFFFF"
C_BORDER = "#E0D8E8"
C_TEXT = "#4A3A50"
C_PLACEHOLDER = "#C0B0C8"
C_SEND_BG = "#FF7EB3"
C_SEND_HOVER = "#FF5A9C"
C_ICON = "#FF7EB3"

FONT_FAMILY = "Microsoft YaHei"


class ChatDialog:
    """搜狗输入法风格迷你浮条 — 双击宠物唤出"""

    def __init__(self, root, show_bubble_callback, state_machine=None):
        self._root = root
        self._show_bubble = show_bubble_callback
        self._state_machine = state_machine
        self._window = None
        self._entry = None
        self._is_processing = False
        self._bar_w = 320
        self._bar_h = 36

    def open(self):
        if self._window and self._window.winfo_exists():
            self._window.lift()
            self._window.focus_force()
            return

        win = tk.Toplevel(self._root)
        self._window = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)

        # 圆角用透明色 + Canvas 画背景
        win.configure(bg="#010101")
        win.attributes("-transparentcolor", "#010101")

        self._bar_w = 320
        self._bar_h = 36

        # 用 Canvas 画圆角背景条
        canvas = tk.Canvas(win, width=self._bar_w, height=self._bar_h,
                           bg="#010101", highlightthickness=0)
        canvas.pack()

        r = 12
        x1, y1, x2, y2 = 0, 0, self._bar_w, self._bar_h
        # 阴影
        canvas.create_oval(x1 + 1, y1 + 1, x1 + 2 * r + 1, y1 + 2 * r + 1,
                           fill="#E8E0EC", outline="", tags="shadow")
        canvas.create_oval(x2 - 2 * r - 1, y1 + 1, x2 - 1, y1 + 2 * r + 1,
                           fill="#E8E0EC", outline="", tags="shadow")
        canvas.create_oval(x1 + 1, y2 - 2 * r - 1, x1 + 2 * r + 1, y2 - 1,
                           fill="#E8E0EC", outline="", tags="shadow")
        canvas.create_oval(x2 - 2 * r - 1, y2 - 2 * r - 1, x2 - 1, y2 - 1,
                           fill="#E8E0EC", outline="", tags="shadow")
        canvas.create_rectangle(x1 + r + 1, y1 + 1, x2 - r - 1, y2 - 1,
                                fill="#E8E0EC", outline="", tags="shadow")
        canvas.create_rectangle(x1 + 1, y1 + r + 1, x2 - 1, y2 - r - 1,
                                fill="#E8E0EC", outline="", tags="shadow")
        # 主背景
        canvas.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r,
                           fill=C_BAR_BG, outline="")
        canvas.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r,
                           fill=C_BAR_BG, outline="")
        canvas.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2,
                           fill=C_BAR_BG, outline="")
        canvas.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2,
                           fill=C_BAR_BG, outline="")
        canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=C_BAR_BG, outline="")
        canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=C_BAR_BG, outline="")
        # 细边框
        canvas.create_oval(x1 + 1, y1 + 1, x1 + 2 * r - 1, y1 + 2 * r - 1,
                           outline=C_BORDER, width=1)
        canvas.create_oval(x2 - 2 * r + 1, y1 + 1, x2 - 1, y1 + 2 * r - 1,
                           outline=C_BORDER, width=1)
        canvas.create_oval(x1 + 1, y2 - 2 * r + 1, x1 + 2 * r - 1, y2 - 1,
                           outline=C_BORDER, width=1)
        canvas.create_oval(x2 - 2 * r + 1, y2 - 2 * r + 1, x2 - 1, y2 - 1,
                           outline=C_BORDER, width=1)
        canvas.create_line(x1 + r, y1 + 1, x2 - r, y1 + 1, fill=C_BORDER)
        canvas.create_line(x1 + r, y2 - 1, x2 - r, y2 - 1, fill=C_BORDER)
        canvas.create_line(x1 + 1, y1 + r, x1 + 1, y2 - r, fill=C_BORDER)
        canvas.create_line(x2 - 1, y1 + r, x2 - 1, y2 - r, fill=C_BORDER)

        # ── 猫咪图标 ──
        canvas.create_text(20, self._bar_h // 2, text="🐱", font=("Segoe UI Emoji", 14),
                           anchor="w")

        # ── 输入框（直接放在 Canvas 上） ──
        entry_x = 42
        entry_w = self._bar_w - 100

        self._entry = tk.Entry(
            win,
            font=(FONT_FAMILY, 11),
            bg=C_BAR_BG, fg=C_TEXT,
            relief="flat",
            insertbackground=C_SEND_BG,
            selectbackground="#FFD0DA",
            bd=0, highlightthickness=0,
        )
        self._entry.place(x=entry_x, y=3, width=entry_w, height=self._bar_h - 6)
        self._entry.bind("<Return>", self._on_enter)
        self._entry.bind("<Escape>", lambda e: self._on_close())

        # ── 发送按钮 ──
        btn_x = self._bar_w - 54
        btn_w = 48
        btn_y = 4
        btn_h = self._bar_h - 8

        s_btn = canvas.create_oval(
            btn_x, btn_y, btn_x + btn_w, btn_y + btn_h,
            fill=C_SEND_BG, outline="", tags="send",
        )

        send_text = canvas.create_text(
            btn_x + btn_w // 2, btn_y + btn_h // 2,
            text="✿", font=("Segoe UI Emoji", 13),
            fill="#FFFFFF", tags="send",
        )

        for tag in ("send",):
            canvas.tag_bind(tag, "<Button-1>", lambda e: self._send_message())
            canvas.tag_bind(tag, "<Enter>",
                            lambda e: canvas.itemconfig(s_btn, fill=C_SEND_HOVER))
            canvas.tag_bind(tag, "<Leave>",
                            lambda e: canvas.itemconfig(s_btn, fill=C_SEND_BG))

        # ── 拖拽支持 ──
        drag_data = {"x": 0, "y": 0}

        def on_press(e):
            drag_data["x"] = e.x
            drag_data["y"] = e.y

        def on_drag(e):
            dx = e.x - drag_data["x"]
            dy = e.y - drag_data["y"]
            nx = win.winfo_x() + dx
            ny = win.winfo_y() + dy
            win.geometry(f"+{nx}+{ny}")

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)

        # ── 定位：宠物上方 ──
        win.update_idletasks()
        pet_x = self._root.winfo_x()
        pet_y = self._root.winfo_y()
        pet_w = self._root.winfo_width()
        x = pet_x + (pet_w - self._bar_w) // 2
        y = max(20, pet_y - self._bar_h - 8)
        win.geometry(f"+{x}+{y}")

        self._entry.focus_set()

    def _on_enter(self, event):
        self._send_message()
        return "break"

    def _send_message(self):
        if self._is_processing:
            return
        text = self._entry.get().strip()
        if not text:
            return

        self._entry.delete(0, "end")
        self._entry.insert(0, "咔比正在想... ( '・ω・)゛")
        self._entry.configure(state="readonly", readonlybackground=C_BAR_BG,
                              fg=C_PLACEHOLDER)
        self._is_processing = True

        if self._state_machine:
            self._state_machine.transition("thinking", "咔比正在想...")

        thread = threading.Thread(target=self._call_claude, args=(text,), daemon=True)
        thread.start()

    def _call_claude(self, prompt_text):
        try:
            clean_prompt = prompt_text.replace('"', '\\"')
            cmd = [_CLAUDE_CLI, "-p", clean_prompt]
            logger.info(f"[CHAT] claude -p \"{prompt_text[:50]}...\"")

            env = {**__import__("os").environ, "CLAUDE_CODE_NO_INTERACTIVE": "1"}
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if __import__("sys").platform == "win32" else 0,
            )

            try:
                stdout, stderr = process.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                self._on_response("", "⏱️ 咔比想太久了... 主人换简单点的问题吧~", is_error=True)
                return

            if process.returncode != 0:
                err = stderr.strip()[:150] if stderr else f"错误码 {process.returncode}"
                self._on_response("", f"❌ {err}", is_error=True)
                return

            response = stdout.strip()
            if not response:
                self._on_response("", "🤔 Claude 什么都没说... 咔比也很困惑 (´・ω・`)", is_error=True)
                return

            logger.info(f"[CHAT] Got {len(response)} chars")
            self._on_response(response)

        except FileNotFoundError:
            self._on_response("", "❌ 咔比找不到 Claude... 主人检查一下安装？", is_error=True)
        except Exception as exc:
            logger.error(f"[CHAT] Error: {exc}")
            self._on_response("", f"❌ {str(exc)[:150]}", is_error=True)

    def _on_response(self, full_response="", error_msg="", is_error=False):
        self._root.after(0, self._handle_response, full_response, error_msg, is_error)

    def _handle_response(self, full_response, error_msg, is_error):
        self._is_processing = False

        if self._entry and self._entry.winfo_exists():
            self._entry.configure(state="normal")
            self._entry.delete(0, "end")
            self._entry.configure(fg=C_TEXT)
            self._entry.focus_set()

        if self._state_machine:
            if is_error:
                self._state_machine.transition("sad", "咔比出错了...")
            else:
                self._state_machine.transition("happy", "咔比收到回复啦！( o ・ω・) ノ")

        if is_error:
            self._show_bubble(error_msg[:200])
        else:
            self._show_bubble(full_response[:600])

        self._root.after(500, self._on_close)

    def _on_close(self):
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
