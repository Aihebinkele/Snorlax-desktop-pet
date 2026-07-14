"""闹钟管理模块 - 定时提醒吃饭、喝水、休息、下班等"""

import datetime
import logging
import threading
import time
import tkinter as tk
from tkinter import messagebox

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
        self._root.after(0, self._do_show_popup, message)

    def _do_show_popup(self, message):
        """实际显示弹窗（必须在主线程调用）"""
        try:
            popup = tk.Toplevel(self._root)
            popup.title("⏰ 闹钟提醒")
            popup.resizable(False, False)
            popup.attributes("-topmost", True)
            popup.configure(bg="#2D2D2D")

            # 窗口大小
            popup_width = 380
            popup_height = 180

            # 居中显示
            popup.update_idletasks()
            screen_w = popup.winfo_screenwidth()
            screen_h = popup.winfo_screenheight()
            x = (screen_w - popup_width) // 2
            y = (screen_h - popup_height) // 2
            popup.geometry(f"{popup_width}x{popup_height}+{x}+{y}")

            # 图标和标题
            title_frame = tk.Frame(popup, bg="#2D2D2D")
            title_frame.pack(fill="x", padx=20, pady=(20, 10))

            tk.Label(
                title_frame,
                text="⏰",
                font=("Segoe UI Emoji", 32),
                bg="#2D2D2D",
                fg="#FFD54F",
            ).pack(side="left", padx=(0, 12))

            info_frame = tk.Frame(title_frame, bg="#2D2D2D")
            info_frame.pack(side="left", fill="both", expand=True)

            tk.Label(
                info_frame,
                text="闹钟提醒",
                font=("Microsoft YaHei", 14, "bold"),
                bg="#2D2D2D",
                fg="#FFFFFF",
            ).pack(anchor="w")

            tk.Label(
                info_frame,
                text=message,
                font=("Microsoft YaHei", 12),
                bg="#2D2D2D",
                fg="#AAAAAA",
                wraplength=260,
                justify="left",
            ).pack(anchor="w", pady=(4, 0))

            # 按钮区域
            btn_frame = tk.Frame(popup, bg="#2D2D2D")
            btn_frame.pack(fill="x", padx=20, pady=(10, 20))

            def close_popup():
                popup.destroy()

            tk.Button(
                btn_frame,
                text="知道了 ✓",
                command=close_popup,
                font=("Microsoft YaHei", 11),
                bg="#4CAF50",
                fg="#FFFFFF",
                activebackground="#388E3C",
                activeforeground="#FFFFFF",
                relief="flat",
                padx=24,
                pady=6,
                cursor="hand2",
            ).pack(side="right")

            # 5分钟后再次提醒按钮
            def snooze():
                popup.destroy()
                self._root.after(5 * 60 * 1000, self._do_show_popup, f"🔔 {message}\n（5分钟后再次提醒）")

            tk.Button(
                btn_frame,
                text="5分钟后提醒",
                command=snooze,
                font=("Microsoft YaHei", 10),
                bg="#555555",
                fg="#CCCCCC",
                activebackground="#444444",
                activeforeground="#CCCCCC",
                relief="flat",
                padx=16,
                pady=6,
                cursor="hand2",
            ).pack(side="right", padx=(0, 8))

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
