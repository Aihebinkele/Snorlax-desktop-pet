"""闹钟管理模块 - 定时提醒吃饭、喝水、休息、下班等"""

import datetime
import logging
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox

from desktop_pet.config import RESOURCE_DIR

logger = logging.getLogger()

# 预设闹钟模板
PRESET_ALARMS = [
    {"time": "09:00", "label": "📋 查看今日待办", "days": [0, 1, 2, 3, 4]},
    {"time": "10:00", "label": "💧 该喝水啦！", "days": [0, 1, 2, 3, 4]},
    {"time": "11:00", "label": "💧 补充水分时间", "days": [0, 1, 2, 3, 4]},
    {"time": "12:00", "label": "🍚 中午了，吃饭啦！", "days": [0, 1, 2, 3, 4, 5, 6]},
    {"time": "14:00", "label": "💧 下午第一杯水", "days": [0, 1, 2, 3, 4]},
    {"time": "15:00", "label": "☕ 休息一下，活动活动", "days": [0, 1, 2, 3, 4]},
    {"time": "16:00", "label": "💧 该喝水了~", "days": [0, 1, 2, 3, 4]},
    {"time": "17:30", "label": "🏠 快下班啦，整理一下", "days": [0, 1, 2, 3, 4]},
    {"time": "18:00", "label": "🌙 下班时间到！", "days": [0, 1, 2, 3, 4]},
    {"time": "19:00", "label": "🍚 晚饭时间，记得吃饭", "days": [0, 1, 2, 3, 4, 5, 6]},
]

DAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ── 科技风配色（与 gui.py 数据条/面板一致）──
_BG = "#0A0E17"          # 深空藏青（主背景）
_FG = "#EAF2FF"          # 冷白主文字
_MUTED = "#8AA0BE"       # 次要文字
_GREEN = "#39FF14"       # 荧光绿（主按钮 / 电子钟）
_BORDER = "#343A44"      # 分隔线（细深灰）


def _hex_rgb(hex_color):
    """#RRGGBB → (r, g, b)"""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _find_text_font():
    """优先返回微软雅黑粗体，其次雅黑、Segoe UI。"""
    for p in (
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\segoeui.ttf",
    ):
        if os.path.exists(p):
            return p
    return None


def _pill_button_photo(master, label, accent_hex):
    """渲染「8px 圆角 + 描边 + 深色半透明底」按钮图片（与统计窗口一致）。

    返回 (normal_photo, hover_photo)；hover 在边框外叠一层同色微光晕。
    渲染失败返回 None（调用方回退普通 Button）。
    """
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageFilter
        font_path = _find_text_font()
        if not font_path:
            return None
        r, g, b = _hex_rgb(accent_hex)
        fsize = 15
        font = ImageFont.truetype(font_path, fsize)
        probe = Image.new("RGBA", (1, 1))
        d = ImageDraw.Draw(probe)
        tb = d.textbbox((0, 0), label, font=font)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        pad_x, pad_y, radius = 18, 8, 8
        w = pad_x * 2 + tw
        h = pad_y * 2 + th
        glow = 6
        W, H = w + glow * 2, h + glow * 2

        def _render(hover):
            img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ox, oy = glow, glow
            if hover:
                halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(halo).rounded_rectangle(
                    [ox, oy, ox + w, oy + h], radius=radius,
                    outline=(r, g, b, 120), width=2,
                )
                halo = halo.filter(ImageFilter.GaussianBlur(3))
                img = Image.alpha_composite(img, halo)
            dr = ImageDraw.Draw(img)
            dr.rounded_rectangle(
                [ox, oy, ox + w, oy + h], radius=radius,
                fill=(r, g, b, 40),
            )
            dr.rounded_rectangle(
                [ox, oy, ox + w, oy + h], radius=radius,
                outline=(r, g, b, 255), width=1,
            )
            ty = oy + (h - th) // 2 - tb[1]
            dr.text((ox + pad_x, ty), label, font=font, fill=(r, g, b, 255))
            return img

        normal = ImageTk.PhotoImage(_render(False), master=master)
        hover = ImageTk.PhotoImage(_render(True), master=master)
        return normal, hover
    except Exception:
        logger.exception("渲染闹钟按钮图片失败：%r", label)
        return None


def _make_pill_button(parent, label, accent_hex, command):
    """创建描边圆角按钮；PIL 渲染失败时回退普通 Button。"""
    photos = _pill_button_photo(parent, label, accent_hex)
    if photos is not None:
        normal, hover = photos
        btn = tk.Button(
            parent, image=normal, command=command,
            relief="flat", bd=0, highlightthickness=0,
            bg=_BG, activebackground=_BG,
            cursor="hand2", takefocus=False,
        )
        btn._pill_normal = normal
        btn._pill_hover = hover
        btn.bind("<Enter>", lambda e: btn.configure(image=hover))
        btn.bind("<Leave>", lambda e: btn.configure(image=normal))
        return btn
    return tk.Button(
        parent, text=label, command=command,
        font=("Microsoft YaHei", 10, "bold"),
        bg=accent_hex, fg=_BG,
        activebackground=_BORDER, activeforeground=_BG,
        relief="flat", padx=16, pady=6, cursor="hand2",
    )


def _default_alarms():
    """生成默认闹钟列表（带唯一ID）"""
    alarms = []
    for i, preset in enumerate(PRESET_ALARMS):
        alarm = dict(preset)
        alarm["id"] = f"preset_{i}"
        alarm["enabled"] = False  # 默认关闭，用户自行开启
        alarms.append(alarm)
    return alarms


class AlarmManager:
    """闹钟管理器 - 后台线程定时检查并触发提醒"""

    def __init__(self, get_config, save_config, root):
        """
        Args:
            get_config: 获取当前配置的回调函数，返回 dict
            save_config: 保存配置的回调函数
            root: Tkinter 根窗口，用于在主线程显示弹窗
        """
        self._get_config = get_config
        self._save_config = save_config
        self._root = root
        self._running = False
        self._thread = None
        self._last_triggered = {}  # alarm_id -> date_str，防止同一分钟重复触发

    def start(self):
        """启动闹钟后台线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("[ALARM] Alarm manager started")

    def stop(self):
        """停止闹钟后台线程"""
        self._running = False
        logger.info("[ALARM] Alarm manager stopped")

    def _run_loop(self):
        """后台循环，每30秒检查一次"""
        while self._running:
            try:
                self._check_alarms()
            except Exception as exc:
                logger.error(f"[ALARM] Check error: {exc}")
            time.sleep(30)

    def _check_alarms(self):
        """检查是否有闹钟需要触发"""
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M")
        current_weekday = now.weekday()  # 0=周一, 6=周日
        today_str = now.strftime("%Y-%m-%d")

        config = self._get_config()
        alarms = config.get("alarms", [])

        for alarm in alarms:
            if not alarm.get("enabled", False):
                continue

            alarm_time = alarm.get("time", "")
            if alarm_time != current_time:
                continue

            # 检查星期
            days = alarm.get("days", [0, 1, 2, 3, 4, 5, 6])
            if current_weekday not in days:
                continue

            # 防止同一分钟重复触发
            alarm_id = alarm.get("id", "")
            if self._last_triggered.get(alarm_id) == today_str:
                continue

            self._last_triggered[alarm_id] = today_str
            label = alarm.get("label", "⏰ 闹钟提醒")

            logger.info(f"[ALARM] Triggered: {label} at {current_time}")
            self._show_popup(label)

    def _show_popup(self, message):
        """在主线程显示提醒弹窗"""
        self._root.after(0, self._do_show_popup, self._root, message)

    @staticmethod
    def _do_show_popup(root, message):
        """实际显示弹窗（必须在主线程调用）"""
        try:
            popup = tk.Toplevel(root)
            _ico = os.path.join(RESOURCE_DIR, "pet_images", "idle.ico")
            if os.path.exists(_ico):
                try:
                    popup.iconbitmap(_ico)
                except Exception:
                    pass
            popup.title("闹钟提醒")
            popup.resizable(False, False)
            popup.attributes("-topmost", True)
            popup.configure(bg=_BG)

            # 窗口大小
            popup_width = 380
            popup_height = 240

            # 居中显示
            popup.update_idletasks()
            screen_w = popup.winfo_screenwidth()
            screen_h = popup.winfo_screenheight()
            x = (screen_w - popup_width) // 2
            y = (screen_h - popup_height) // 2
            popup.geometry(f"{popup_width}x{popup_height}+{x}+{y}")

            # ── 电子钟（当前时间，科技感，每 0.5s 刷新、冒号闪烁）──
            clock_frame = tk.Frame(popup, bg=_BG)
            clock_frame.pack(fill="x", padx=20, pady=(18, 4))

            clock_canvas = tk.Canvas(
                clock_frame, width=340, height=66, bg=_BG, highlightthickness=0
            )
            clock_canvas.pack()

            # 点亮段（荧光绿）
            clock_text = clock_canvas.create_text(
                170, 33, text="--:--:--",
                font=("Consolas", 40, "bold"), fill=_GREEN,
            )

            date_label = tk.Label(
                clock_frame, text="",
                font=("Microsoft YaHei", 10), bg=_BG, fg=_MUTED,
            )
            date_label.pack(pady=(2, 0))

            _blink = {"on": True}

            def update_clock():
                if not popup.winfo_exists():
                    return
                now = datetime.datetime.now()
                t = now.strftime("%H:%M:%S")
                if not _blink["on"]:
                    t = t.replace(":", " ")
                clock_canvas.itemconfigure(clock_text, text=t)
                date_label.configure(
                    text=f"{now.strftime('%Y-%m-%d')} {DAY_NAMES[now.weekday()]}"
                )
                _blink["on"] = not _blink["on"]
                popup.after(500, update_clock)

            update_clock()

            # 分隔线
            tk.Frame(popup, bg=_BORDER, height=1).pack(fill="x", padx=20, pady=(10, 0))

            # 提醒内容
            msg_frame = tk.Frame(popup, bg=_BG)
            msg_frame.pack(fill="x", padx=20, pady=(10, 4))
            tk.Label(
                msg_frame,
                text=message,
                font=("Microsoft YaHei", 12),
                bg=_BG,
                fg=_FG,
                wraplength=330,
                justify="center",
            ).pack(anchor="center")

            # 按钮区域（胶囊描边按钮）
            btn_frame = tk.Frame(popup, bg=_BG)
            btn_frame.pack(fill="x", padx=20, pady=(8, 18))

            def close_popup():
                popup.destroy()

            def snooze():
                popup.destroy()
                root.after(5 * 60 * 1000, AlarmManager._do_show_popup, root, f"{message}\n（5分钟后再次提醒）")

            _make_pill_button(btn_frame, "5分钟后提醒", _MUTED, snooze).pack(
                side="right", padx=(0, 8)
            )
            _make_pill_button(btn_frame, "知道了", _GREEN, close_popup).pack(
                side="right"
            )

            # 播放系统提示音
            try:
                import winsound
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
            except Exception:
                pass

            # 自动关闭（5分钟后）
            popup.after(5 * 60 * 1000, close_popup)

            popup.focus_force()
            popup.lift()

        except Exception as exc:
            logger.error(f"[ALARM] Failed to show popup: {exc}")


def show_alarm_popup(root, message):
    """在主线程弹出一条闹钟提醒弹窗（供闹钟触发与 GUI 预览复用）。"""
    AlarmManager._do_show_popup(root, message)
