import datetime
import logging
import math
import os
import random
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False

from PIL import Image, ImageTk
import pystray
from pystray import MenuItem, Menu

from desktop_pet.config import RESOURCE_DIR, load_app_config, normalize_app_config, save_app_config, CONFIG_PATH
from desktop_pet.state import StateMachine, STATE_CONFIG, CLICK_RESPONSES
from desktop_pet.shared import event_queue, app_state, app_state_lock
from desktop_pet.alarm import DAY_NAMES
from desktop_pet.chat import ChatDialog
import queue
import uuid

logger = logging.getLogger()

_FONT_FAMILY = None


def _get_font_family():
    global _FONT_FAMILY
    if _FONT_FAMILY is not None:
        return _FONT_FAMILY
    available = set(tkfont.families())
    for candidate in ("Microsoft YaHei", "Microsoft JhengHei", "Segoe UI", "Arial", "TkDefaultFont"):
        if candidate in available:
            _FONT_FAMILY = candidate
            return _FONT_FAMILY
    _FONT_FAMILY = "TkDefaultFont"
    return _FONT_FAMILY


# ── 宠物自言自语词库 ──
_SELF_TALK = [
    # 吃东西 / 贪吃
    "咔比肚子饿了... 主人有小饼干吗？(´・ω・`)",
    "🍩 甜甜圈~ 咔比做梦都在想！",
    "咔比刚刚梦见自己在吃蛋糕... 醒来发现是假的 (´;ω;`)",
    "🍚 主人！该吃饭了！咔比帮你记着呢~",
    "咔比今天想吃拉面... 但是要保持身材！( o ・ω・) ノ",
    "🍎 咔比虽然爱吃，但也知道要健康饮食！",
    "主人记得吃水果！咔比的份呢... 啊哈哈开玩笑~",
    "咔比觉得世界上最好听的声音是打开零食袋的声音！",
    "🍰 下午茶时间到了吧？咔比替主人检查一下~",
    "咔比想吃炸鸡... 不行不行，要忍住！(๑•̀ㅂ•́)و✧",

    # 喝水提醒
    "💧 主人！该喝水了！咔比也一起喝~ 吨吨吨...",
    "咔比记得主人上次喝水是很久以前了！快喝！",
    "💦 咔比监督主人喝水！每天八杯不能少！(｀・ω・´)",
    "喝水喝水！主人皮肤好好，咔比看了都羡慕~",
    "🧊 咔比喜欢冰水... 但主人还是喝温水比较好！",

    # 睡觉 / 犯困
    "呼啊... 咔比有点困了... ( '・ω・)゛",
    "🛏️ 咔比最大的梦想就是吃饱了睡睡饱了吃~",
    "主人你困吗？咔比可以把肩膀借你靠！（虽然很软）",
    "咔比打个盹... 就五分钟... zzz... 呼...",
    "😴 昨晚咔比梦到被一堆甜甜圈追着跑... 好幸福！",
    "咔比觉得世界上最舒服的地方就是被窝！",
    "主人工作太久了！陪咔比休息一会儿吧~ (´・ω・`)",

    # 陪主人 / 关心
    "咔比会一直陪着主人的！( o ・ω・) ノ ♡",
    "💕 主人辛苦了！咔比给你加油打气！",
    "咔比虽然很懒，但是关心主人这件事从不偷懒！",
    "主人今天开心吗？不开心的话咔比讲个笑话给你听~",
    "🤗 主人需要抱抱吗？咔比肚子很软很好抱！",
    "有咔比在，主人永远不会孤单！(๑•̀ㅂ•́)و✧",
    "咔比会提醒主人吃饭喝水休息！交给咔比吧~",

    # 天气 / 环境
    "☀️ 今天太阳好好！咔比想出去晒太阳~",
    "咔比查了一下天气... 嗯... 适合睡觉！(´・ω・`)",
    "🌧️ 下雨天最适合窝在家里了！咔比陪主人！",
    "咔比觉得今天很适合吃火锅... 主人觉得呢？",
    "外面好热！咔比都快变成烤肉了... 开玩笑的~",

    # 鼓励 / 工作
    "💪 主人加油！咔比虽然帮不上忙但会一直看着你！",
    "咔比知道主人很努力！但也要记得休息哦~",
    "🎉 主人完成了任务！咔比好骄傲！",
    "主人是最棒的！咔比可以作证！",
    "咔比虽然帮不上什么忙... 但是精神支持拉满！(๑•̀ㅂ•́)و✧",
    "🧘 深呼吸~ 咔比教主人放松：吸气... 呼气... 然后吃零食~",

    # 卖萌 / 搞笑
    "咔比！咔比咔比！(这是在唱歌，不是卡住了)",
    "🐟 咔比虽然叫卡比兽但不是鱼！不过鱼确实很好吃...",
    "如果咔比翻个身，会不会滚下桌面？算了太懒了不试了~",
    "咔比今天的运动量：翻了个身！厉害吧！( o ・ω・) ノ",
    "主人你知道吗，咔比在宝可梦里是睡神级别的存在！",
    "📱 咔比也想玩手机... 但是爪子太短点不到屏幕...",
    "咔比觉得自己圆滚滚的身材很完美！不接受反驳！",
    "今天咔比的懒惰值达到了历史新高... 啊已经下午了！",

    # 下午茶 / 零食时间
    "🍪 咔比嗅到了零食的味道！在哪里在哪里？",
    "下午三点！咔比的生物钟响了：该吃东西了！",
    "咔比觉得主人该休息一下了，比如... 吃个下午茶？",
    "🍵 咔比给主人泡了杯茶（想象中），趁热喝！",
]

# 自言自语间隔范围（秒）
_TALK_INTERVAL_MIN = 60    # 1分钟
_TALK_INTERVAL_MAX = 180   # 3分钟


class DesktopPet:
    BUBBLE_TOP = 80

    def __init__(self, state_machine):
        self.state_machine = state_machine
        self.config = load_app_config()

        self.root = tk.Tk()
        self.root.title("Desktop Pet")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#010101")
        self.root.configure(bg="#010101")

        self.current_state = "idle"
        self.current_message = ""
        self._reset_timer_id = None
        self._drag_data = {"x": 0, "y": 0}
        self._anim_tick = 0
        self._settings_window = None
        self._tray_icon = None
        self._visible = True
        self._chat_dialog = None
        self._self_talk_timer_id = None
        self._last_interaction_time = datetime.datetime.now()

        self.PET_WIDTH = self.config["window"]["width"]
        self.PET_HEIGHT = self.config["window"]["height"]
        self.CANVAS_HEIGHT = self.PET_HEIGHT + self.BUBBLE_TOP

        self._setup_ui()
        self._center_window()
        self._bind_events()
        self._setup_tray_icon()
        self._poll_events()
        self._animate()
        self._schedule_self_talk()

    def _on_state_change(self, new_state, message):
        self.root.after(0, self._apply_state, new_state, message)

    def _apply_state(self, new_state, message):
        if self._reset_timer_id:
            self.root.after_cancel(self._reset_timer_id)
            self._reset_timer_id = None

        self.current_state = new_state
        self.current_message = message

        cfg = STATE_CONFIG[new_state]
        self._anim_tick = 0
        self.canvas.coords(self.state_image, 0, self.BUBBLE_TOP)

        self.canvas.itemconfig(self.state_image, image=self._state_images[new_state])
        self.canvas.itemconfig(self.state_label, text=cfg["label"], fill=cfg["fg"])

        display_msg = message if len(message) <= 80 else message[:77] + "..."
        self.canvas.itemconfig(self.message_label, text=display_msg)

        if new_state == "happy":
            self._play_complete_sound()

        target, duration = self.state_machine.get_auto_recovery(new_state, self.config)
        if target and duration > 0:
            self._reset_timer_id = self.root.after(
                duration, lambda t=target: self.state_machine.transition(t, "")
            )

    def _setup_ui(self):
        self.canvas = tk.Canvas(
            self.root,
            width=self.PET_WIDTH,
            height=self.CANVAS_HEIGHT,
            bg="#010101",
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack()

        cfg = STATE_CONFIG[self.current_state]

        self._raw_pet_images = {}
        self._state_images = {}
        img_dir = os.path.join(RESOURCE_DIR, "pet_images")
        for state in STATE_CONFIG:
            img_path = os.path.join(img_dir, f"{state}.png")
            if os.path.exists(img_path):
                raw_img = Image.open(img_path).convert("RGBA")
                self._raw_pet_images[state] = raw_img
            else:
                placeholder = Image.new("RGBA", (128, 128), (100, 100, 100, 200))
                self._raw_pet_images[state] = placeholder
        self._reload_state_images()

        self.state_image = self.canvas.create_image(
            0, self.BUBBLE_TOP,
            image=self._state_images[self.current_state],
            anchor="nw"
        )

        self.state_label = self.canvas.create_text(
            self.PET_WIDTH // 2, self.BUBBLE_TOP + int(self.PET_HEIGHT * 0.82),
            text=cfg["label"],
            font=(_get_font_family(), 11, "bold"),
            fill=cfg["fg"]
        )

        self.message_label = self.canvas.create_text(
            self.PET_WIDTH // 2, self.BUBBLE_TOP + int(self.PET_HEIGHT * 0.92),
            text="",
            font=(_get_font_family(), 8),
            fill="#AAAAAA",
            width=170
        )

        # 气泡相关（绘制卡通对话框 + 文字）
        self._bubble_ids = []          # 气泡背景图元 ID 列表
        self._bubble_text_id = None    # 气泡文字 ID
        self._bubble_timer_id = None
        self._layout_static_items()

    def _reload_state_images(self):
        self._state_images = {
            state: self._create_state_image(raw_img)
            for state, raw_img in self._raw_pet_images.items()
        }

    def _create_state_image(self, raw_img):
        img_w, img_h = self.PET_WIDTH, self.CANVAS_HEIGHT
        canvas_img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))

        max_pet_size = max(64, min(220, int(min(img_w * 0.45, (self.PET_HEIGHT) * 0.5))))
        w, h = raw_img.size
        scale = min(max_pet_size / w, max_pet_size / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        pet_resized = raw_img.resize((new_w, new_h), Image.LANCZOS)

        pet_x = (img_w - new_w) // 2
        pet_y = self.BUBBLE_TOP + int(self.PET_HEIGHT * 0.24) - new_h // 2
        canvas_img.paste(pet_resized, (pet_x, pet_y), pet_resized)

        return ImageTk.PhotoImage(canvas_img)

    def _layout_static_items(self):
        self.canvas.coords(self.state_label, self.PET_WIDTH // 2, self.BUBBLE_TOP + int(self.PET_HEIGHT * 0.82))
        self.canvas.coords(self.message_label, self.PET_WIDTH // 2, self.BUBBLE_TOP + int(self.PET_HEIGHT * 0.92))
        self.canvas.itemconfig(self.message_label, width=max(120, self.PET_WIDTH - 130))

    def _center_window(self):
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = screen_w - self.PET_WIDTH - 40
        y = screen_h - self.CANVAS_HEIGHT - 80
        self.root.geometry(f"+{x}+{y}")

    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Button-3>", self._show_context_menu)

        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="\ud83d\udcac \u4ea4\u8c08", command=self._open_chat)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="\u8bbe\u7f6e", command=self._open_settings)
        self.context_menu.add_command(label="\u95f9\u949f\u8bbe\u7f6e", command=self._open_alarm_settings)
        self.context_menu.add_command(label="\u91cd\u7f6e\u72b6\u6001", command=self.state_machine.reset_to_idle)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="\u9690\u85cf", command=self._do_toggle_visibility)
        self.context_menu.add_command(label="\u9000\u51fa", command=self._quit_app)

    def _show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _on_click(self, event):
        self._last_interaction_time = datetime.datetime.now()
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        self._drag_data["dragging"] = False

    def _on_drag(self, event):
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        if abs(dx) > 3 or abs(dy) > 3:
            self._drag_data["dragging"] = True
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")

    def _on_release(self, event):
        if not self._drag_data.get("dragging", False):
            if self.current_state == "sleeping":
                self.state_machine.wake_up()
            else:
                self._show_bubble(CLICK_RESPONSES.get(self.current_state, "\u55b5~"))

    def _on_double_click(self, event):
        self._last_interaction_time = datetime.datetime.now()
        self._open_chat()

    # ── 卡通对话框 ──
    _BUBBLE_BG = "#FFF8E1"       # 暖奶油色背景
    _BUBBLE_BORDER = "#C4956A"   # 暖棕边框
    _BUBBLE_TEXT_COLOR = "#4E342E"  # 深棕文字

    def _show_bubble(self, text, duration_ms=10000):
        """绘制卡通对话框：圆角矩形 + 小尾巴 + 文字"""
        self._hide_bubble()
        w = self.PET_WIDTH
        screen_w = self.root.winfo_screenwidth()
        bubble_w = w - 4  # 比宠物略窄
        pad_x, pad_y = 14, 10
        tail_h = 10
        text_width = bubble_w - pad_x * 2

        # 计算文字高度
        font = (_get_font_family(), 11)
        tmp_id = self.canvas.create_text(0, 0, text=text, font=font, width=text_width)
        bbox = self.canvas.bbox(tmp_id)
        self.canvas.delete(tmp_id)
        text_h = (bbox[3] - bbox[1]) if bbox else 20
        bh = text_h + pad_y * 2

        # 气泡居中在上方，不超出 Canvas
        bx = 2
        by = self.BUBBLE_TOP - bh - tail_h - 4
        if by < 2:
            by = 2

        # 绘制圆角矩形背景
        r = 12
        ids = []
        x1, y1, x2, y2 = bx, by, bx + bubble_w, by + bh

        # 用 ovals + rectangles 拼圆角矩形
        ids.append(self.canvas.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r,
                     fill=self._BUBBLE_BG, outline=""))
        ids.append(self.canvas.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r,
                     fill=self._BUBBLE_BG, outline=""))
        ids.append(self.canvas.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2,
                     fill=self._BUBBLE_BG, outline=""))
        ids.append(self.canvas.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2,
                     fill=self._BUBBLE_BG, outline=""))
        ids.append(self.canvas.create_rectangle(x1 + r, y1, x2 - r, y2,
                     fill=self._BUBBLE_BG, outline=""))
        ids.append(self.canvas.create_rectangle(x1, y1 + r, x2, y2 - r,
                     fill=self._BUBBLE_BG, outline=""))

        # 暖棕圆角边框（四个角各90°弧线）
        corners = [
            (x1, y1, x1 + 2 * r, y1 + 2 * r, 90),           # 左上
            (x2 - 2 * r, y1, x2, y1 + 2 * r, 0),            # 右上
            (x2 - 2 * r, y2 - 2 * r, x2, y2, 270),          # 右下
            (x1, y2 - 2 * r, x1 + 2 * r, y2, 180),          # 左下
        ]
        for (ox1, oy1, ox2, oy2, start) in corners:
            ids.append(self.canvas.create_arc(
                ox1, oy1, ox2, oy2, start=start, extent=90,
                outline=self._BUBBLE_BORDER, width=1.5, style="arc"))
        ids.append(self.canvas.create_line(
            x1 + r, y1, x2 - r, y1, fill=self._BUBBLE_BORDER, width=1.5))
        ids.append(self.canvas.create_line(
            x1 + r, y2, x2 - r, y2, fill=self._BUBBLE_BORDER, width=1.5))
        ids.append(self.canvas.create_line(
            x1, y1 + r, x1, y2 - r, fill=self._BUBBLE_BORDER, width=1.5))
        ids.append(self.canvas.create_line(
            x2, y1 + r, x2, y2 - r, fill=self._BUBBLE_BORDER, width=1.5))

        # 小尾巴（指向宠物，与对话框不重叠）
        tail_cx = w // 2
        tail_top = by + bh + 1       # 留1px间隙
        tail_bottom = tail_top + tail_h
        ids.append(self.canvas.create_polygon(
            tail_cx - 7, tail_top,
            tail_cx + 7, tail_top,
            tail_cx, tail_bottom,
            fill=self._BUBBLE_BG,
            outline=self._BUBBLE_BORDER, width=1.5,
        ))

        # ── 猫爪装饰（暖棕，45°倾斜） ──
        paw_color = "#C4956A"  # 暖棕肉垫
        ids.extend(self._draw_paw(bx + 14, by + bh - 14, 7, 45, paw_color))
        ids.extend(self._draw_paw(bx + bubble_w - 14, by + bh - 14, 7, 45, paw_color))
        ids.extend(self._draw_paw(bx + 10, by + 12, 5, 45, paw_color))

        # 文字（画在气泡上层）
        text_id = self.canvas.create_text(
            bx + bubble_w // 2, by + bh // 2,
            text=text, font=font,
            fill=self._BUBBLE_TEXT_COLOR,
            width=text_width,
            justify="center",
        )
        self._bubble_text_id = text_id

        # 保存背景 ID
        self._bubble_ids = ids
        self._bubble_timer_id = self.root.after(duration_ms, self._hide_bubble)

    def _hide_bubble(self):
        """清除卡通对话框"""
        if self._bubble_timer_id:
            self.root.after_cancel(self._bubble_timer_id)
            self._bubble_timer_id = None
        for bid in self._bubble_ids:
            self.canvas.delete(bid)
        self._bubble_ids.clear()
        if self._bubble_text_id:
            self.canvas.delete(self._bubble_text_id)
            self._bubble_text_id = None

    def _draw_paw(self, cx, cy, size, angle_deg, color):
        """绘制猫爪图案（可旋转角度），返回 canvas item ID 列表"""
        import math
        ids = []
        r = size
        rad = math.radians(angle_deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)

        def rot(dx, dy):
            return dx * cos_a - dy * sin_a, dx * sin_a + dy * cos_a

        # ── 主肉垫（大三瓣） ──
        # 中心椭圆
        ox, oy = rot(0, r * 0.5)
        ids.append(self.canvas.create_oval(
            cx + ox - r * 0.55, cy + oy - r * 0.65,
            cx + ox + r * 0.55, cy + oy + r * 0.55,
            fill=color, outline=""))
        # 左瓣
        ox_l, oy_l = rot(-r * 0.5, r * 0.25)
        ids.append(self.canvas.create_oval(
            cx + ox_l - r * 0.4, cy + oy_l - r * 0.4,
            cx + ox_l + r * 0.4, cy + oy_l + r * 0.5,
            fill=color, outline=""))
        # 右瓣
        ox_r, oy_r = rot(r * 0.5, r * 0.25)
        ids.append(self.canvas.create_oval(
            cx + ox_r - r * 0.4, cy + oy_r - r * 0.4,
            cx + ox_r + r * 0.4, cy + oy_r + r * 0.5,
            fill=color, outline=""))

        # ── 4个脚趾豆 ──
        toe_r = r * 0.25
        for dx in [-0.7, -0.23, 0.23, 0.7]:
            tx, ty = rot(dx * r * 0.75, -r * 0.45)
            ids.append(self.canvas.create_oval(
                cx + tx - toe_r, cy + ty - toe_r,
                cx + tx + toe_r, cy + ty + toe_r,
                fill=color, outline=""))

        return ids

    def _schedule_self_talk(self):
        """安排下一次自言自语"""
        if self._self_talk_timer_id:
            self.root.after_cancel(self._self_talk_timer_id)
            self._self_talk_timer_id = None

        delay = random.randint(_TALK_INTERVAL_MIN, _TALK_INTERVAL_MAX) * 1000
        self._self_talk_timer_id = self.root.after(delay, self._do_self_talk)

    def _do_self_talk(self):
        """随机说一句话，然后安排下一次"""
        self._self_talk_timer_id = None

        # 睡觉中不弹气泡
        if self.current_state == "sleeping":
            self._schedule_self_talk()
            return

        # 已经有气泡在显示时，30% 概率跳过
        if self._bubble_timer_id and random.random() < 0.3:
            self._schedule_self_talk()
            return

        phrase = random.choice(_SELF_TALK)
        self._show_bubble(phrase)
        self._schedule_self_talk()

    def _setup_tray_icon(self):
        try:
            icon_path = os.path.join(RESOURCE_DIR, "pet_images", "idle.png")
            if os.path.exists(icon_path):
                icon_image = Image.open(icon_path)
            else:
                icon_image = Image.new("RGBA", (64, 64), (100, 200, 100, 255))

            menu = Menu(
                MenuItem("\u663e\u793a/\u9690\u85cf", self._toggle_visibility),
                MenuItem("\u91cd\u7f6e\u72b6\u6001", lambda: self.root.after(0, self.state_machine.reset_to_idle)),
                Menu.SEPARATOR,
                MenuItem("\u9000\u51fa", self._quit_app),
            )

            self._tray_icon = pystray.Icon("DesktopPet", icon_image, "Desktop Pet", menu)
            tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
            tray_thread.start()
        except Exception as exc:
            logger.warning(f"Failed to setup tray icon: {exc}")

    def _toggle_visibility(self, icon=None, item=None):
        self.root.after(0, self._do_toggle_visibility)

    def _do_toggle_visibility(self):
        if self._visible:
            self.root.withdraw()
            self._visible = False
        else:
            self.root.deiconify()
            self._visible = True

    def _quit_app(self, icon=None, item=None):
        if self._tray_icon:
            self._tray_icon.stop()
        self.root.after(0, self.root.destroy)

    def _open_settings(self):
        if self._settings_window and self._settings_window.winfo_exists():
            self._settings_window.lift()
            self._settings_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self._settings_window = window
        window.title("\u5ba0\u7269\u8bbe\u7f6e")
        window.resizable(False, False)
        window.attributes("-topmost", True)
        window.protocol("WM_DELETE_WINDOW", window.destroy)

        frame = tk.Frame(window, padx=14, pady=12)
        frame.pack(fill="both", expand=True)

        sound_var = tk.BooleanVar(value=self.config["sound_enabled"])
        width_var = tk.IntVar(value=self.PET_WIDTH)
        height_var = tk.IntVar(value=self.PET_HEIGHT)

        tk.Checkbutton(frame, text="\u5b8c\u6210\u65f6\u64ad\u653e\u97f3\u6548", variable=sound_var).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        tk.Label(frame, text="\u7a97\u53e3\u5bbd\u5ea6").grid(row=1, column=0, sticky="w", pady=4)
        tk.Spinbox(frame, from_=220, to=600, increment=10, textvariable=width_var, width=8).grid(
            row=1, column=1, sticky="e", pady=4
        )

        tk.Label(frame, text="\u7a97\u53e3\u9ad8\u5ea6").grid(row=2, column=0, sticky="w", pady=4)
        tk.Spinbox(frame, from_=180, to=500, increment=10, textvariable=height_var, width=8).grid(
            row=2, column=1, sticky="e", pady=4
        )

        button_row = tk.Frame(frame)
        button_row.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))

        tk.Button(button_row, text="\u53d6\u6d88", command=window.destroy).pack(side="right")
        tk.Button(
            button_row,
            text="\u4fdd\u5b58",
            command=lambda: self._save_settings(window, sound_var, width_var, height_var)
        ).pack(side="right", padx=(0, 8))

        x = self.root.winfo_x() - 20
        y = max(20, self.root.winfo_y() - 40)
        window.geometry(f"+{x}+{y}")

    def _save_settings(self, window, sound_var, width_var, height_var):
        self.config["sound_enabled"] = bool(sound_var.get())
        self.config["window"]["width"] = width_var.get()
        self.config["window"]["height"] = height_var.get()
        self.config = normalize_app_config(self.config)
        save_app_config(self.config)
        self._apply_window_size()
        window.destroy()
        logger.info(f"[PET] Config saved: {CONFIG_PATH}")

    def _open_chat(self):
        """打开交谈对话框"""
        if self._chat_dialog is None:
            self._chat_dialog = ChatDialog(
                root=self.root,
                show_bubble_callback=self._show_bubble,
                state_machine=self.state_machine,
            )
        self._chat_dialog.open()

    def _open_alarm_settings(self):
        """打开闹钟设置窗口"""
        if hasattr(self, '_alarm_window') and self._alarm_window and self._alarm_window.winfo_exists():
            self._alarm_window.lift()
            self._alarm_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self._alarm_window = window
        window.title("⏰ 闹钟设置")
        window.resizable(False, False)
        window.attributes("-topmost", True)
        window.configure(bg="#2D2D2D")
        window.protocol("WM_DELETE_WINDOW", self._on_alarm_window_close)

        # 主容器
        main_frame = tk.Frame(window, bg="#2D2D2D", padx=16, pady=12)
        main_frame.pack(fill="both", expand=True)

        # 标题
        tk.Label(
            main_frame,
            text="⏰ 闹钟设置",
            font=(_get_font_family(), 14, "bold"),
            bg="#2D2D2D",
            fg="#FFFFFF",
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            main_frame,
            text="设置定时提醒，到点弹出对话框",
            font=(_get_font_family(), 9),
            bg="#2D2D2D",
            fg="#888888",
        ).pack(anchor="w", pady=(0, 12))

        # 闹钟列表区域（可滚动）
        list_container = tk.Frame(main_frame, bg="#1E1E1E", highlightbackground="#444", highlightthickness=1)
        list_container.pack(fill="both", expand=True, pady=(0, 10))

        # 表头
        header_frame = tk.Frame(list_container, bg="#333333")
        header_frame.pack(fill="x")

        tk.Label(header_frame, text="启用", font=(_get_font_family(), 9, "bold"),
                 bg="#333333", fg="#AAAAAA", width=5, anchor="w").pack(side="left", padx=(8, 4), pady=4)
        tk.Label(header_frame, text="时间", font=(_get_font_family(), 9, "bold"),
                 bg="#333333", fg="#AAAAAA", width=7, anchor="w").pack(side="left", padx=4, pady=4)
        tk.Label(header_frame, text="提醒内容", font=(_get_font_family(), 9, "bold"),
                 bg="#333333", fg="#AAAAAA", width=22, anchor="w").pack(side="left", padx=4, pady=4)
        tk.Label(header_frame, text="重复", font=(_get_font_family(), 9, "bold"),
                 bg="#333333", fg="#AAAAAA", width=18, anchor="w").pack(side="left", padx=4, pady=4)
        tk.Label(header_frame, text="操作", font=(_get_font_family(), 9, "bold"),
                 bg="#333333", fg="#AAAAAA", width=8, anchor="center").pack(side="left", padx=4, pady=4)

        # 可滚动的闹钟列表
        canvas_frame = tk.Frame(list_container, bg="#1E1E1E")
        canvas_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(canvas_frame, bg="#1E1E1E", height=260, highlightthickness=0)
        scrollbar = tk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#1E1E1E")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 鼠标滚轮支持
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ---- 添加闹钟表单 ----
        form_frame = tk.Frame(main_frame, bg="#2D2D2D")
        form_frame.pack(fill="x", pady=(0, 10))

        tk.Label(form_frame, text="新增闹钟:", font=(_get_font_family(), 10, "bold"),
                 bg="#2D2D2D", fg="#FFFFFF").pack(anchor="w", pady=(0, 6))

        row1 = tk.Frame(form_frame, bg="#2D2D2D")
        row1.pack(fill="x", pady=(0, 4))

        tk.Label(row1, text="时间", font=(_get_font_family(), 9),
                 bg="#2D2D2D", fg="#AAAAAA").pack(side="left", padx=(0, 6))

        # 时间选择：小时和分钟下拉
        hour_var = tk.StringVar(value="09")
        minute_var = tk.StringVar(value="00")

        hour_spin = tk.Spinbox(row1, from_=0, to=23, textvariable=hour_var,
                               width=3, format="%02.0f", font=(_get_font_family(), 10),
                               bg="#3D3D3D", fg="#FFFFFF", buttonbackground="#555555",
                               relief="flat", justify="center")
        hour_spin.pack(side="left")

        tk.Label(row1, text=":", font=(_get_font_family(), 10, "bold"),
                 bg="#2D2D2D", fg="#FFFFFF").pack(side="left", padx=2)

        minute_spin = tk.Spinbox(row1, from_=0, to=59, textvariable=minute_var,
                                 width=3, format="%02.0f", font=(_get_font_family(), 10),
                                 bg="#3D3D3D", fg="#FFFFFF", buttonbackground="#555555",
                                 relief="flat", justify="center")
        minute_spin.pack(side="left")

        tk.Label(row1, text="  内容", font=(_get_font_family(), 9),
                 bg="#2D2D2D", fg="#AAAAAA").pack(side="left", padx=(12, 6))

        label_var = tk.StringVar(value="")
        label_entry = tk.Entry(row1, textvariable=label_var, font=(_get_font_family(), 10),
                               bg="#3D3D3D", fg="#FFFFFF", insertbackground="#FFFFFF",
                               relief="flat", width=24)
        label_entry.pack(side="left", fill="x", expand=True)

        # 星期选择
        row2 = tk.Frame(form_frame, bg="#2D2D2D")
        row2.pack(fill="x", pady=(4, 6))

        tk.Label(row2, text="重复", font=(_get_font_family(), 9),
                 bg="#2D2D2D", fg="#AAAAAA").pack(side="left", padx=(0, 8))

        day_vars = []
        for i, day_name in enumerate(DAY_NAMES):
            var = tk.BooleanVar(value=(i < 5))  # 周一至周五默认选中
            day_vars.append(var)
            cb = tk.Checkbutton(
                row2, text=day_name, variable=var,
                font=(_get_font_family(), 8),
                bg="#2D2D2D", fg="#CCCCCC",
                selectcolor="#2D2D2D", activebackground="#2D2D2D",
                activeforeground="#FFFFFF",
            )
            cb.pack(side="left", padx=1)

        # 添加按钮行
        row3 = tk.Frame(form_frame, bg="#2D2D2D")
        row3.pack(fill="x")

        def add_alarm():
            h = hour_var.get().zfill(2)
            m = minute_var.get().zfill(2)
            time_str = f"{h}:{m}"
            label = label_var.get().strip()
            if not label:
                label = "⏰ 闹钟提醒"
            days = [i for i, v in enumerate(day_vars) if v.get()]
            if not days:
                days = [0, 1, 2, 3, 4]

            new_alarm = {
                "id": str(uuid.uuid4())[:8],
                "time": time_str,
                "label": label,
                "days": days,
                "enabled": True,
            }
            alarms = self.config.get("alarms", [])
            alarms.append(new_alarm)
            self.config["alarms"] = alarms
            save_app_config(self.config)
            logger.info(f"[PET] Alarm added: {new_alarm}")

            # 清空表单
            label_var.set("")

            # 刷新列表
            refresh_alarm_list()

        tk.Button(
            row3, text="＋ 添加闹钟", command=add_alarm,
            font=(_get_font_family(), 10),
            bg="#4CAF50", fg="#FFFFFF",
            activebackground="#388E3C", activeforeground="#FFFFFF",
            relief="flat", padx=16, pady=4, cursor="hand2",
        ).pack(side="left")

        # 预设模板按钮
        def load_presets():
            """加载预设闹钟模板"""
            from desktop_pet.alarm import PRESET_ALARMS
            existing_times = {(a.get("time", ""), a.get("label", "")) for a in self.config.get("alarms", [])}
            added = 0
            alarms = list(self.config.get("alarms", []))
            for i, preset in enumerate(PRESET_ALARMS):
                key = (preset["time"], preset["label"])
                if key in existing_times:
                    continue
                new_alarm = dict(preset)
                new_alarm["id"] = f"preset_{i}_{str(uuid.uuid4())[:4]}"
                new_alarm["enabled"] = False
                alarms.append(new_alarm)
                existing_times.add(key)
                added += 1
            self.config["alarms"] = alarms
            save_app_config(self.config)
            logger.info(f"[PET] Loaded {added} preset alarms")
            refresh_alarm_list()

        tk.Button(
            row3, text="📋 加载预设模板", command=load_presets,
            font=(_get_font_family(), 10),
            bg="#555555", fg="#CCCCCC",
            activebackground="#444444", activeforeground="#CCCCCC",
            relief="flat", padx=12, pady=4, cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        # ---- 刷新闹钟列表 ----
        def refresh_alarm_list():
            for widget in scrollable_frame.winfo_children():
                widget.destroy()

            alarms = self.config.get("alarms", [])
            if not alarms:
                empty_label = tk.Label(
                    scrollable_frame,
                    text="暂无闹钟，请添加或加载预设模板",
                    font=(_get_font_family(), 10),
                    bg="#1E1E1E", fg="#666666", pady=40,
                )
                empty_label.pack(fill="x")
            else:
                for alarm in alarms:
                    self._create_alarm_row(scrollable_frame, alarm, refresh_alarm_list)

        def _on_mousewheel_local(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        # 用局部绑定替换全局绑定
        def bind_scroll(e):
            canvas.bind("<Enter>", lambda ev: canvas.bind_all("<MouseWheel>", _on_mousewheel_local))
            canvas.bind("<Leave>", lambda ev: canvas.unbind_all("<MouseWheel>"))

        canvas.bind("<Enter>", lambda ev: canvas.bind_all("<MouseWheel>", _on_mousewheel_local))
        canvas.bind("<Leave>", lambda ev: canvas.unbind_all("<MouseWheel>"))

        refresh_alarm_list()

        # 关闭按钮
        tk.Button(
            main_frame,
            text="关闭",
            command=self._on_alarm_window_close,
            font=(_get_font_family(), 10),
            bg="#555555", fg="#CCCCCC",
            activebackground="#444444", activeforeground="#CCCCCC",
            relief="flat", padx=20, pady=6, cursor="hand2",
        ).pack(anchor="e", pady=(6, 0))

        # 定位窗口
        x = self.root.winfo_x() - 60
        y = max(20, self.root.winfo_y() - 40)
        window.geometry(f"+{x}+{y}")
        window.minsize(520, 480)

    def _create_alarm_row(self, parent, alarm, refresh_callback):
        """创建单个闹钟行"""
        row_frame = tk.Frame(parent, bg="#2D2D2D", padx=4, pady=2)
        row_frame.pack(fill="x", pady=1)

        # 启用开关
        enabled_var = tk.BooleanVar(value=alarm.get("enabled", False))

        def toggle_enabled():
            alarm["enabled"] = enabled_var.get()
            save_app_config(self.config)

        cb = tk.Checkbutton(
            row_frame, variable=enabled_var, command=toggle_enabled,
            bg="#2D2D2D", activebackground="#2D2D2D",
            selectcolor="#2D2D2D",
        )
        cb.pack(side="left", padx=(4, 8))

        # 时间
        tk.Label(row_frame, text=alarm.get("time", "09:00"),
                 font=(_get_font_family(), 11, "bold"),
                 bg="#2D2D2D", fg="#FFD54F", width=7, anchor="w").pack(side="left", padx=2)

        # 标签
        tk.Label(row_frame, text=alarm.get("label", "⏰ 闹钟"),
                 font=(_get_font_family(), 10),
                 bg="#2D2D2D", fg="#FFFFFF", width=24, anchor="w").pack(side="left", padx=2)

        # 星期显示
        days = alarm.get("days", [0, 1, 2, 3, 4])
        if len(days) == 7:
            day_text = "每天"
        elif days == [0, 1, 2, 3, 4] and len(days) == 5:
            day_text = "工作日"
        elif days == [5, 6] and len(days) == 2:
            day_text = "周末"
        else:
            day_abbr = ["一", "二", "三", "四", "五", "六", "日"]
            day_text = "周" + "/".join(day_abbr[d] for d in days)

        tk.Label(row_frame, text=day_text,
                 font=(_get_font_family(), 8),
                 bg="#2D2D2D", fg="#888888", width=18, anchor="w").pack(side="left", padx=2)

        # 删除按钮
        def delete_alarm(aid=alarm.get("id")):
            self.config["alarms"] = [a for a in self.config.get("alarms", []) if a.get("id") != aid]
            save_app_config(self.config)
            refresh_callback()

        tk.Button(
            row_frame, text="✕", command=delete_alarm,
            font=(_get_font_family(), 10, "bold"),
            bg="#2D2D2D", fg="#FF5252",
            activebackground="#B71C1C", activeforeground="#FFFFFF",
            relief="flat", padx=8, pady=0, cursor="hand2",
            bd=0,
        ).pack(side="left", padx=(4, 0))

    def _on_alarm_window_close(self):
        """关闭闹钟窗口时的清理"""
        if hasattr(self, '_alarm_window') and self._alarm_window:
            self._alarm_window.destroy()
            self._alarm_window = None

    def _apply_window_size(self):
        self.PET_WIDTH = self.config["window"]["width"]
        self.PET_HEIGHT = self.config["window"]["height"]
        self.CANVAS_HEIGHT = self.PET_HEIGHT + self.BUBBLE_TOP

        self.canvas.config(width=self.PET_WIDTH, height=self.CANVAS_HEIGHT)
        self._reload_state_images()
        self.canvas.itemconfig(self.state_image, image=self._state_images[self.current_state])
        self._layout_static_items()
        self.canvas.coords(self.state_image, 0, self.BUBBLE_TOP)
        if self._visible:
            x, y = self.root.winfo_x(), self.root.winfo_y()
        else:
            x = self.root.winfo_screenwidth() - self.PET_WIDTH - 40
            y = self.root.winfo_screenheight() - self.CANVAS_HEIGHT - 80
        self.root.geometry(f"{self.PET_WIDTH}x{self.CANVAS_HEIGHT}+{x}+{y}")

    def _animate(self):
        cfg = self.config["animations"].get(self.current_state)
        if cfg:
            self._anim_tick += 1
            t = self._anim_tick
            anim_type = cfg["type"]
            dx, dy = 0.0, 0.0

            if anim_type == "float":
                dy = math.sin(t * cfg["speed"]) * cfg["amp_y"]

            elif anim_type == "tremble":
                dx = (math.sin(t * 0.31) * 1.2 + math.sin(t * 0.73) * 0.6) * cfg["amp"] / 1.8
                dy = (math.sin(t * 0.43) * 0.8 + math.sin(t * 0.91) * 0.4) * cfg["amp"] / 1.2

            elif anim_type == "slow_tremble":
                dx = (math.sin(t * cfg["speed"]) * 1.2 + math.sin(t * cfg["speed"] * 2.3) * 0.6) * cfg["amp"] / 1.8
                dy = (math.sin(t * cfg["speed"] * 1.4) * 0.8 + math.sin(t * cfg["speed"] * 2.9) * 0.4) * cfg["amp"] / 1.2

            elif anim_type in ("pulse", "pulse_slow"):
                progress = t * cfg["speed"]
                if progress < math.pi:
                    dy = -math.sin(progress) * cfg["amp_y"]
                else:
                    dy = 0.0

            elif anim_type == "bounce":
                dy = -abs(math.sin(t * cfg["speed"])) * cfg["amp_y"]

            elif anim_type == "sway":
                dx = math.sin(t * cfg["speed"]) * cfg["amp_x"]
                dy = -abs(math.sin(t * cfg["speed"])) * 2

            elif anim_type == "droop":
                dy = cfg["amp_y"] * (1 - math.exp(-t * cfg["speed"])) + math.sin(t * 0.03) * 1.5

            elif anim_type == "breathe":
                dy = math.sin(t * cfg["speed"]) * cfg["amp_y"]

            self.canvas.coords(self.state_image, dx, self.BUBBLE_TOP + dy)

        self.root.after(50, self._animate)

    def _play_complete_sound(self):
        if not self.config["sound_enabled"] or not _HAS_WINSOUND:
            return
        try:
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            try:
                winsound.Beep(880, 200)
                winsound.Beep(1100, 200)
                winsound.Beep(1320, 300)
            except Exception:
                pass

    def _poll_events(self):
        try:
            while True:
                event_type, message = event_queue.get_nowait()
                self._last_interaction_time = datetime.datetime.now()
                self.state_machine.process_event(event_type, message)
        except queue.Empty:
            pass

        self.state_machine.check_timeouts(self.config)

        # 10分钟无任何交互 → 睡觉
        idle_sec = (datetime.datetime.now() - self._last_interaction_time).total_seconds()
        if idle_sec > 600 and self.current_state != "sleeping":
            self.state_machine.transition("sleeping", "Zzz...")
        # 有交互时如果正在睡觉则唤醒
        elif idle_sec < 10 and self.current_state == "sleeping":
            self.state_machine.wake_up()

        state, msg = self.state_machine.get_snapshot()
        with app_state_lock:
            app_state["current_state"] = state
            app_state["current_message"] = msg

        self.root.after(200, self._poll_events)

    def run(self):
        self.root.mainloop()
