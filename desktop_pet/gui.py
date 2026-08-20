import datetime
import logging
import math
import os
import random
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False

from PIL import Image, ImageDraw, ImageFont, ImageTk
import pystray
from pystray import MenuItem, Menu

from desktop_pet.config import RESOURCE_DIR, load_app_config, normalize_app_config, save_app_config, CONFIG_PATH
from desktop_pet.state import StateMachine, STATE_CONFIG, CLICK_RESPONSES
from desktop_pet.shared import event_queue, app_state, app_state_lock
from desktop_pet.shared import stats_tracker, balance_fetcher, git_info
from desktop_pet import pricing
from desktop_pet import providers
from desktop_pet.alarm import DAY_NAMES, show_alarm_popup
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


_EMOJI_FONT_PATH = None


def _find_emoji_font():
    """定位可渲染彩色 Emoji 的字体（Windows Segoe UI Emoji / macOS / Linux）。"""
    global _EMOJI_FONT_PATH
    if _EMOJI_FONT_PATH is not None:
        return _EMOJI_FONT_PATH
    windir = os.environ.get("WINDIR", r"C:\Windows")
    candidates = [
        os.path.join(windir, "Fonts", "seguiemj.ttf"),
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            _EMOJI_FONT_PATH = path
            return path
    _EMOJI_FONT_PATH = ""
    return _EMOJI_FONT_PATH


_TEXT_FONT_PATH = None


def _find_text_font():
    """定位中文正文字体（Microsoft YaHei / 微软雅黑），供发光文字渲染用。"""
    global _TEXT_FONT_PATH
    if _TEXT_FONT_PATH is not None:
        return _TEXT_FONT_PATH
    windir = os.environ.get("WINDIR", r"C:\Windows")
    candidates = [
        os.path.join(windir, "Fonts", "msyh.ttc"),
        os.path.join(windir, "Fonts", "msyhbd.ttc"),
        os.path.join(windir, "Fonts", "segoeui.ttf"),
    ]
    for path in candidates:
        if os.path.exists(path):
            _TEXT_FONT_PATH = path
            return path
    _TEXT_FONT_PATH = ""
    return _TEXT_FONT_PATH


def _split_emoji_prefix(text):
    """把字符串开头的 Emoji 前缀拆出来，返回 (emoji, 剩余文本)。

    用于闹钟「提醒内容」：Emoji 单独渲染成彩色图片，其余文字正常显示。
    """
    if not text:
        return "", text
    i = 0
    n = len(text)
    while i < n:
        cp = ord(text[i])
        # Emoji 区段 + 变体选择符 + ZWJ + 键帽组合符
        if (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF
                or 0x2300 <= cp <= 0x23FF or 0x2B00 <= cp <= 0x2BFF
                or cp in (0xFE0F, 0x200D, 0x20E3)):
            i += 1
        else:
            break
    return text[:i], text[i:]


def _apply_window_icon(window):
    """给根窗口 / 各 Toplevel 弹窗设置左上角（标题栏）图标为宠物 idle.ico。"""
    _ico = os.path.join(RESOURCE_DIR, "pet_images", "idle.ico")
    if os.path.exists(_ico):
        try:
            window.iconbitmap(_ico)
        except Exception:
            pass


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
    STATS_BAR_H = 24

    def __init__(self, state_machine):
        self.state_machine = state_machine
        self.config = load_app_config()

        # 统计单例注入配置（监控供应商 key + 上下文窗口）
        stats_tracker.set_context_window(self.config.get("context_window"))
        monitor = self.config.get("monitor", {})
        _provider = monitor.get("provider", "deepseek")
        _keys = monitor.get("keys", {})
        _key = _keys.get(_provider) or os.environ.get("DEEPSEEK_API_KEY", "")
        balance_fetcher.set_provider_key(_provider, _key)

        self.root = tk.Tk()
        self.root.title("Desktop Pet")
        # 窗口图标（左上角 / 任务栏 / 各 Toplevel 标题栏左上角统一用宠物 idle.ico）
        _apply_window_icon(self.root)
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

        # 统计条 / 面板状态
        self._stats_bar_ids = []
        self._stats_enabled = bool(self.config.get("stats_bar", {}).get("enabled", True))
        self._stats_enabled_var = tk.BooleanVar(value=self._stats_enabled)
        self._stats_panel = None
        self._last_satiety_percent = 0
        self._emoji_cache = {}  # (char, size) -> ImageTk.PhotoImage（彩色 Emoji）

        self.PET_WIDTH = self.config["window"]["width"]
        self.PET_HEIGHT = self.config["window"]["height"]
        self.CANVAS_HEIGHT = self.PET_HEIGHT + self.BUBBLE_TOP + (self.STATS_BAR_H if self._stats_enabled else 0)

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

        self._setup_stats_bar()
        self._refresh_stats_loop()

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

    # ── 底部常驻数据条 + 统计面板（UI 对齐 dsh-blubby） ──
    # ── 科技风（深空霓虹）配色 ──
    _BAR_BG = "#0A0E17"       # 深空藏青（主背景）
    _BAR_FG = "#C9D6E8"       # 条带主文字（冷调浅蓝灰）
    _BAR_DIM = "#45536B"      # 分隔符/占位
    _BAR_MUTED = "#8AA0BE"    # 次要文字
    _BAR_RED = "#FF4D6D"      # 霓虹红（危险/冲突/余额告警）
    _BAR_GREEN = "#35E6A0"    # 霓虹薄荷绿（余额充足）
    _BAR_TEAL = "#00E5FF"     # 霓虹青（主强调色/饱腹度环正常）
    _BAR_ORANGE = "#FFB020"   # 霓虹琥珀（好撑/⚡ 效率闪电）
    _BAR_YELLOW = "#FFD34D"   # 金色（💰 余额钱袋）
    _BAR_TRACK = "#1C2842"    # 环背景轨道（深蓝）
    _BAR_BORDER = "#15304F"   # 胶囊边框（深蓝霓虹底）
    _PANEL_FG = "#EAF2FF"     # 面板主文字（冷白）
    _SURFACE = "#0E1524"      # 卡片/输入框底
    _SURFACE_2 = "#16213A"    # 表头/更深一档表面
    # ── 窗口/菜单 chrome（Obsidian 深色风：荧光绿强调、细深灰边框、悬浮轻微提亮）──
    _UI_BORDER = "#343A44"        # 细深灰边框
    _UI_BORDER_HOVER = "#4A515C"  # 悬浮边框轻微提亮
    _UI_HOVER = "#2A2F3A"         # 菜单项/按钮悬浮底色
    _UI_ACCENT = "#39FF14"        # 荧光绿（主按钮/高亮/选中）
    _UI_ACCENT_HOVER = "#5DFF33"  # 主按钮悬浮（更亮一档）
    _UI_ACCENT_FG = "#071005"     # 荧光绿按钮上的深色文字（保证可读）
    _RING_D = 16              # 饱腹度环直径
    _EMOJI_SIZE = 16          # 彩色 Emoji 图标边长（与环同高）
    _PANEL_EMOJI_SIZE = 14    # 统计面板内嵌彩色 Emoji 边长
    _PANEL_EMOJIS = ("🍖", "⚡", "💰", "🕰", "💳", "⏱", "🚀", "🛠",
                     "✏️", "➕", "⚠️", "✅", "📝")

    @staticmethod
    def _fmt_cost(cost):
        if cost >= 1:
            return f"¥{cost:.2f}"
        if cost >= 0.01:
            return f"¥{cost:.3f}"
        return f"¥{cost:.4f}"

    @staticmethod
    def _fmt_tokens(n):
        def scaled(v):
            return str(round(v)) if v >= 100 else str(round(v * 10) / 10)
        if n < 1000:
            return str(n)
        if n < 1_000_000:
            return f"{scaled(n / 1000)}K"
        return f"{scaled(n / 1_000_000)}M"

    @staticmethod
    def _fmt_satiety(percent, used):
        if percent is None:
            return "--%"
        if percent > 0:
            return f"{percent}%"
        if (used or 0) > 0:
            return "<1%"
        return "0%"

    @staticmethod
    def _fmt_duration(ms):
        s = ms / 1000
        if s < 60:
            return f"{round(s * 10) / 10}s"
        whole = round(s)
        return f"{whole // 60}m{whole % 60}s"

    def _emoji_pil(self, char, size):
        """把单个 Emoji 渲染成居中 RGBA PIL Image，失败返回 None。

        去掉变体选择符（FE0F/FE0E）：否则 PIL 的 textbbox 会把宽度算成两倍
        （如 ⚙️ 19px→38px），导致 x 偏移为负、图标被裁切出画布。
        """
        font_path = _find_emoji_font()
        if not font_path:
            return None
        try:
            clean = char.replace("️", "").replace("︎", "")
            font = ImageFont.truetype(font_path, size)
            probe = Image.new("RGBA", (1, 1))
            d2 = ImageDraw.Draw(probe)
            bbox = d2.textbbox((0, 0), clean, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.text(
                ((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]),
                clean, font=font, embedded_color=True,
            )
            return img
        except Exception:
            logger.exception("渲染彩色 Emoji 失败：%r", char)
            return None

    def _emoji_photo(self, char, size):
        """把单个 Emoji 渲染成彩色 PhotoImage（按 (char,size) 缓存）。

        Tk canvas 的文字渲染不支持彩色 Emoji（只会画出单色线条），
        所以用 PIL + 系统彩色 Emoji 字体（Segoe UI Emoji 等）渲染成图片，
        再用 create_image 贴上去。找不到彩色字体时返回 None（回退单色文字）。
        """
        key = (char, size)
        cache = self._emoji_cache
        if key in cache:
            return cache[key]
        pil = self._emoji_pil(char, size)
        if pil is None:
            cache[key] = None
            return None
        photo = ImageTk.PhotoImage(pil, master=self.canvas)
        cache[key] = photo
        return photo

    @staticmethod
    def _hex_rgb(hex_str):
        hex_str = hex_str.lstrip("#")
        return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))

    def _pt_to_px(self, pt):
        """Tk 字号（pt）→ 像素高度，让 PIL 发光文字与普通文字等高。

        用屏幕实际 DPI 把 pt 换算成像素 em 高（与 Tk 渲染字号一致）。
        """
        try:
            dpi = self.root.winfo_fpixels("1i")
            return max(1, int(round(pt * dpi / 72.0)))
        except Exception:
            return int(pt * 96 / 72)

    def _glow_text_photo(self, text, size, color="#39FF14", glow_alpha=80, blur=2):
        """把文字渲染成带「极微弱绿色外发光」的 PhotoImage（用于高亮项）。

        前景用纯色文字，底层叠一层同色高斯模糊光晕，模拟 Obsidian 风高亮。
        找不到中文字体或渲染失败时返回 None（调用方回退纯色文字）。
        """
        key = ("glow", text, size, color, glow_alpha, blur)
        cache = self._emoji_cache
        if key in cache:
            return cache[key]
        font_path = _find_text_font()
        if not font_path:
            cache[key] = None
            return None
        try:
            from PIL import ImageFilter
            font = ImageFont.truetype(font_path, size)
            probe = Image.new("RGBA", (1, 1))
            d = ImageDraw.Draw(probe)
            bbox = d.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            pad = blur * 2 + 2
            w = tw + pad
            h = th + pad
            cx = (w - tw) / 2 - bbox[0]
            cy = (h - th) / 2 - bbox[1]
            r, g, b = self._hex_rgb(color)
            glow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(glow_layer).text((cx, cy), text, font=font,
                                            fill=(r, g, b, glow_alpha))
            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(blur))
            fg_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(fg_layer).text((cx, cy), text, font=font,
                                          fill=(r, g, b, 255))
            out = Image.alpha_composite(glow_layer, fg_layer)
            photo = ImageTk.PhotoImage(out, master=self.canvas)
            cache[key] = photo
            return photo
        except Exception:
            logger.exception("渲染发光文字失败：%r", text)
            cache[key] = None
            return None

    def _pill_button_photo(self, label, emoji, accent_hex):
        """渲染「8px 圆角 + 描边 + 深色半透明底」按钮图片（投喂/抽打用）。

        accent_hex: 描边与文字颜色（投喂绿 #39FF14、抽打红 #FF4D6D）。
        返回 (normal_photo, hover_photo)；hover 在边框外叠一层同色微光晕。
        渲染失败返回 None（调用方回退普通 Button）。
        """
        key = ("pill", label, emoji, accent_hex)
        cache = self._emoji_cache
        if key in cache:
            return cache[key]
        try:
            from PIL import ImageFilter
            r, g, b = self._hex_rgb(accent_hex)
            fsize = self._pt_to_px(10)
            font_path = _find_text_font()
            bold_path = os.path.join(os.path.dirname(font_path), "msyhbd.ttc")
            if not os.path.exists(bold_path):
                bold_path = font_path
            font = ImageFont.truetype(bold_path, fsize)

            # 文本尺寸
            probe = Image.new("RGBA", (1, 1))
            d = ImageDraw.Draw(probe)
            tb = d.textbbox((0, 0), label, font=font)
            tw = tb[2] - tb[0]
            th = tb[3] - tb[1]

            emoji_size = 14
            gap = 6
            emoji_img = self._emoji_pil(emoji, emoji_size) if emoji else None
            emoji_w = emoji_size if emoji_img is not None else 0
            pad_x = 18
            pad_y = 8
            radius = 8
            content_h = max(th, emoji_size)
            w = pad_x * 2 + emoji_w + (gap if emoji_w else 0) + tw
            h = pad_y * 2 + content_h
            glow = 6
            W = w + glow * 2
            H = h + glow * 2

            def _render(hover):
                img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ox, oy = glow, glow
                # hover：边框外发光（同色高斯模糊光晕，先画再叠半透明底）
                if hover:
                    halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    ImageDraw.Draw(halo).rounded_rectangle(
                        [ox, oy, ox + w, oy + h], radius=radius,
                        outline=(r, g, b, 120), width=2,
                    )
                    halo = halo.filter(ImageFilter.GaussianBlur(3))
                    img = Image.alpha_composite(img, halo)
                dr = ImageDraw.Draw(img)
                # 深色半透明底
                dr.rounded_rectangle(
                    [ox, oy, ox + w, oy + h], radius=radius,
                    fill=(r, g, b, 40),
                )
                # 描边
                dr.rounded_rectangle(
                    [ox, oy, ox + w, oy + h], radius=radius,
                    outline=(r, g, b, 255), width=1,
                )
                # emoji
                cx = ox + pad_x
                if emoji_img is not None:
                    ey = oy + (h - emoji_size) // 2
                    img.paste(emoji_img, (cx, ey), emoji_img)
                    cx += emoji_size + gap
                # 文字（加粗，颜色同描边）
                ty = oy + (h - th) // 2 - tb[1]
                dr.text((cx, ty), label, font=font, fill=(r, g, b, 255))
                return img

            normal = ImageTk.PhotoImage(_render(False), master=self.canvas)
            hover = ImageTk.PhotoImage(_render(True), master=self.canvas)
            cache[key] = (normal, hover)
            return normal, hover
        except Exception:
            logger.exception("渲染按钮图片失败：%r", label)
            cache[key] = None
            return None

    def _make_pill_button(self, parent, label, emoji, accent_hex, command):
        """创建一枚描边圆角按钮（投喂/抽打）；PIL 渲染失败时回退普通 Button。"""
        photos = self._pill_button_photo(label, emoji, accent_hex)
        if photos is not None:
            normal, hover = photos
            btn = tk.Button(
                parent, image=normal, command=command,
                relief="flat", bd=0, highlightthickness=0,
                bg=self._BAR_BG, activebackground=self._BAR_BG,
                cursor="hand2", takefocus=False,
            )
            btn._pill_hover = hover
            btn.bind("<Enter>", lambda e: btn.configure(image=hover))
            btn.bind("<Leave>", lambda e: btn.configure(image=normal))
            return btn
        # 回退：普通扁平按钮
        return tk.Button(
            parent, text=label, command=command,
            image=self._emoji_photo(emoji, 14), compound="left",
            font=(_get_font_family(), 10, "bold"),
            bg=self._BAR_BG, fg=accent_hex,
            activebackground=self._UI_HOVER, activeforeground=accent_hex,
            relief="flat", padx=16, pady=6, cursor="hand2",
        )

    def _insert_panel_text(self, box, text, tag):
        """向统计面板 Text 插入文本，其中的已知 Emoji 换成彩色内嵌图片。

        tk.Text 同样不支持彩色 Emoji，所以把 _PANEL_EMOJIS 里的字符逐个
        替换为 image_create 图片，其余文本正常插入。
        """
        if not text:
            return
        while text:
            idx, emoji = -1, None
            for e in self._PANEL_EMOJIS:
                j = text.find(e)
                if j != -1 and (idx == -1 or j < idx):
                    idx, emoji = j, e
            if emoji is None:
                box.insert("end", text, tag)
                return
            if idx > 0:
                box.insert("end", text[:idx], tag)
            photo = self._emoji_photo(emoji, self._PANEL_EMOJI_SIZE)
            if photo is not None:
                box.image_create("end", image=photo, padx=0, pady=-1)
            else:
                box.insert("end", emoji, tag)
            text = text[idx + len(emoji):]

    def _setup_stats_bar(self):
        self._stats_enabled = bool(self.config.get("stats_bar", {}).get("enabled", True))
        self._stats_bar_ids = []
        self._draw_stats_bar()

    def _build_bar_items(self):
        """条带元素：("ring", pct) / ("sep",) / ("text", t, color) / ("emoji", char, color)。

        emoji 元素用彩色图片渲染（见 _emoji_photo），color 仅作无彩色字体时的回退。
        顺序对齐 dsh-blubby。
        """
        snap = stats_tracker.snapshot()
        balance = balance_fetcher.get()
        git = git_info.get()
        sat = snap["satiety"]
        sat_hot = sat["percent"] > pricing.SATIETY_BURP_PERCENT

        items = []
        # 🍖 饱腹度（emoji 图标 + 环 + 百分比，最前）
        items.append(("emoji", "🍖", self._BAR_ORANGE if sat_hot else self._BAR_FG))
        items.append(("ring", sat["percent"]))
        items.append(("text",
                      self._fmt_satiety(sat["percent"], sat["used_tokens"]),
                      self._BAR_ORANGE if sat_hot else self._BAR_FG))
        # 💸 花费
        items.append(("sep",))
        items.append(("emoji", "💸", self._BAR_FG))
        items.append(("text", self._fmt_cost(snap["cost"]), self._BAR_FG))
        # ⚡ 效率（闪电橙色，数值跟随主文字）
        items.append(("sep",))
        eff = snap["efficiency"]
        items.append(("emoji", "⚡", self._BAR_ORANGE))
        items.append(("text", f"{eff}%" if eff is not None else "--",
                      self._BAR_FG if eff is not None else self._BAR_DIM))
        # 💰 余额（钱袋黄色，数值保留红/绿告警语义）
        if balance is not None:
            items.append(("sep",))
            items.append(("emoji", "💰", self._BAR_YELLOW))
            items.append(("text", self._fmt_cost(balance),
                          self._BAR_RED if balance < 10 else self._BAR_GREEN))
        # 🛠 git（有改动时追加 📝N，冲突整段标红）
        if git is not None:
            branch = git.get("branch") or git.get("head") or "?"
            n = git["dirty"] + git["untracked"]
            gcolor = self._BAR_RED if git["conflicts"] > 0 else self._BAR_MUTED
            items.append(("sep",))
            items.append(("emoji", "🛠", gcolor))
            items.append(("text", branch, gcolor))
            if n:
                items.append(("emoji", "📝", gcolor))
                items.append(("text", str(n), gcolor))
        return items

    def _bar_measure(self, items, font):
        widths = []
        total = 0
        for it in items:
            kind = it[0]
            if kind == "ring":
                wp = self._RING_D
            elif kind == "emoji":
                wp = self._EMOJI_SIZE
            elif kind == "sep":
                tmp = self.canvas.create_text(0, 0, text="|", font=font)
                b = self.canvas.bbox(tmp)
                self.canvas.delete(tmp)
                wp = (b[2] - b[0]) if b else 4
            else:
                tmp = self.canvas.create_text(0, 0, text=it[1], font=font)
                b = self.canvas.bbox(tmp)
                self.canvas.delete(tmp)
                wp = (b[2] - b[0]) if b else 0
            widths.append(wp)
            total += wp
        return widths, total

    def _bar_items_width(self, items, font_size):
        font = (_get_font_family(), font_size)
        _, total = self._bar_measure(items, font)
        return total + 6 * (len(items) - 1) + 20  # gap + pad_x*2

    def _draw_stats_bar(self):
        for iid in self._stats_bar_ids:
            self.canvas.delete(iid)
        self._stats_bar_ids = []

        if not self._stats_enabled:
            return

        items = self._build_bar_items()
        if not items:
            return

        w = self.PET_WIDTH
        y0 = self.CANVAS_HEIGHT - self.STATS_BAR_H + 1
        y1 = self.CANVAS_HEIGHT - 1
        cy = (y0 + y1) // 2

        # 选择能容纳的字体大小（10 → 9 → 8）
        font_size = 10
        while font_size > 8 and self._bar_items_width(items, font_size) > w - 4:
            font_size -= 1
        font = (_get_font_family(), font_size)

        widths, total = self._bar_measure(items, font)
        gap = 6
        pad_x = 10
        total += gap * (len(items) - 1) + pad_x * 2

        pill_x0 = max(2, (w - total) // 2)
        pill_x1 = pill_x0 + total
        r = (y1 - y0) / 2

        ids = []
        # 胶囊背景
        ids.append(self.canvas.create_oval(pill_x0, y0, pill_x0 + 2 * r, y1, fill=self._BAR_BG, outline=""))
        ids.append(self.canvas.create_oval(pill_x1 - 2 * r, y0, pill_x1, y1, fill=self._BAR_BG, outline=""))
        ids.append(self.canvas.create_rectangle(pill_x0 + r, y0, pill_x1 - r, y1, fill=self._BAR_BG, outline=""))
        # 胶囊边框
        ids.append(self.canvas.create_arc(pill_x0, y0, pill_x0 + 2 * r, y1, start=90, extent=180,
                                          style="arc", outline=self._BAR_BORDER, width=1))
        ids.append(self.canvas.create_arc(pill_x1 - 2 * r, y0, pill_x1, y1, start=270, extent=180,
                                          style="arc", outline=self._BAR_BORDER, width=1))
        ids.append(self.canvas.create_line(pill_x0 + r, y0, pill_x1 - r, y0, fill=self._BAR_BORDER))
        ids.append(self.canvas.create_line(pill_x0 + r, y1, pill_x1 - r, y1, fill=self._BAR_BORDER))

        # 逐项布局
        x = pill_x0 + pad_x
        for it, wp in zip(items, widths):
            kind = it[0]
            if kind == "ring":
                percent = it[1] or 0
                cx = x + self._RING_D / 2
                rp = self._RING_D / 2 - 1.5
                rx0, ry0, rx1, ry1 = cx - rp, cy - rp, cx + rp, cy + rp
                ids.append(self.canvas.create_oval(rx0, ry0, rx1, ry1, outline=self._BAR_TRACK, width=2))
                extent = -360 * min(100, percent) / 100
                if extent < -0.1:
                    ids.append(self.canvas.create_arc(
                        rx0, ry0, rx1, ry1, start=90, extent=extent, style="arc",
                        outline=self._BAR_ORANGE if percent > pricing.SATIETY_BURP_PERCENT else self._BAR_TEAL,
                        width=2))
            elif kind == "emoji":
                photo = self._emoji_photo(it[1], self._EMOJI_SIZE)
                if photo is not None:
                    ids.append(self.canvas.create_image(
                        x + self._EMOJI_SIZE / 2, cy, image=photo, anchor="center"))
                else:
                    ids.append(self.canvas.create_text(
                        x, cy, text=it[1], font=font, fill=it[2], anchor="w"))
            elif kind == "sep":
                ids.append(self.canvas.create_text(x, cy, text="|", font=font, fill=self._BAR_DIM, anchor="w"))
            else:
                ids.append(self.canvas.create_text(x, cy, text=it[1], font=font, fill=it[2], anchor="w"))
            x += wp + gap

        self._stats_bar_ids = ids

    def _refresh_stats_loop(self):
        try:
            self._draw_stats_bar()
            if self._stats_panel is not None and self._stats_panel.winfo_exists():
                self._refresh_stats_panel()

            sat = stats_tracker.snapshot()["satiety"]["percent"]
            if sat > pricing.SATIETY_BURP_PERCENT and sat > self._last_satiety_percent:
                if self._bubble_timer_id is None:
                    self._show_bubble("好撑…吃不下啦")
            self._last_satiety_percent = sat
        except Exception:
            pass
        self.root.after(1000, self._refresh_stats_loop)

    def _toggle_stats_bar(self):
        """显示/隐藏底部数据条（菜单点击切换）。"""
        self._stats_enabled = not self._stats_enabled_var.get()
        self._stats_enabled_var.set(self._stats_enabled)
        self.config.setdefault("stats_bar", {})["enabled"] = self._stats_enabled
        save_app_config(self.config)
        self._apply_window_size()

    def _toggle_stats_panel(self):
        if self._stats_panel is not None and self._stats_panel.winfo_exists():
            self._close_stats_panel()
        else:
            self._open_stats_panel()

    def _open_stats_panel(self):
        window = tk.Toplevel(self.root)
        self._stats_panel = window
        _apply_window_icon(window)
        window.title("统计")
        window.resizable(True, True)
        window.attributes("-topmost", True)
        window.configure(bg=self._BAR_BG)
        window.protocol("WM_DELETE_WINDOW", self._close_stats_panel)

        pad = tk.Frame(window, bg=self._BAR_BG, padx=16, pady=14)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="卡比兽 · 本次运行", font=(_get_font_family(), 14, "bold"),
                 bg=self._BAR_BG, fg=self._PANEL_FG).pack(anchor="w", pady=(0, 2))
        tk.Label(pad, text="用量 · 花费 · 余额明细", font=(_get_font_family(), 9),
                 bg=self._BAR_BG, fg=self._BAR_DIM).pack(anchor="w", pady=(0, 12))

        # 顶部：饱腹度进度环 + 明细文字
        top = tk.Frame(pad, bg=self._BAR_BG)
        top.pack(fill="both", expand=True)

        left_col = tk.Frame(top, bg=self._BAR_BG)
        left_col.pack(side="left", fill="y", padx=(0, 16))
        ring_canvas = tk.Canvas(left_col, width=76, height=76, bg=self._BAR_BG, highlightthickness=0)
        ring_canvas.pack()
        tk.Label(left_col, text="饱腹度", font=(_get_font_family(), 8),
                 bg=self._BAR_BG, fg=self._BAR_MUTED).pack(pady=(4, 0))
        self._stats_ring_canvas = ring_canvas

        self._stats_panel_text = tk.Text(
            top, bg=self._BAR_BG, fg=self._PANEL_FG, font=("Consolas", 10),
            bd=0, highlightthickness=0, relief="flat", wrap="word",
            width=44, height=12, cursor="arrow",
        )
        # 颜色标签（余额绿/红、git 冲突红、修改橙、未跟踪青）
        self._stats_panel_text.tag_configure("muted", foreground=self._BAR_MUTED)
        self._stats_panel_text.tag_configure("dim", foreground=self._BAR_DIM)
        self._stats_panel_text.tag_configure("red", foreground=self._BAR_RED)
        self._stats_panel_text.tag_configure("green", foreground=self._BAR_GREEN)
        self._stats_panel_text.tag_configure("orange", foreground=self._BAR_ORANGE)
        self._stats_panel_text.tag_configure("teal", foreground=self._BAR_TEAL)
        self._stats_panel_text.pack(side="left", fill="both", expand=True)

        # 底部按钮栏
        btn_bar = tk.Frame(pad, bg=self._BAR_BG)
        btn_bar.pack(fill="x", pady=(12, 0))

        self._make_pill_button(btn_bar, "投喂", "💰", self._UI_ACCENT,
                               self._open_recharge).pack(side="left")
        self._make_pill_button(btn_bar, "抽打", "⚡", self._BAR_RED,
                               self._force_refresh).pack(side="left", padx=(10, 0))

        self._refresh_stats_panel()

        # 定位到宠物左侧 + 初始尺寸（可拖拽缩放）
        window.update_idletasks()
        w = window.winfo_reqwidth() or 440
        h = window.winfo_reqheight() or 360
        window.geometry(f"{w}x{h}")
        x = self.root.winfo_x() - w - 10
        if x < 0:
            x = self.root.winfo_x()
        y = self.root.winfo_y()
        if y < 0:
            y = 0
        window.geometry(f"{w}x{h}+{x}+{y}")
        window.minsize(420, 320)

    def _open_recharge(self):
        """投喂：打开当前 AI 供应商平台的充值/用量页面。"""
        provider = balance_fetcher.get_provider()
        url = providers.provider_recharge_url(provider)
        if url:
            try:
                webbrowser.open(url)
            except Exception as exc:
                logger.error(f"[PET] 打开充值页失败: {exc}")

    def _force_refresh(self):
        """抽打：立刻强制重读余额 / git / stats，并刷新面板与数据条。"""
        balance_fetcher.get(force=True)
        git_info.force_refresh()
        stats_tracker.snapshot()
        self._draw_stats_bar()
        self._refresh_stats_panel()

    def _close_stats_panel(self):
        if self._stats_panel is not None:
            try:
                self._stats_panel.destroy()
            except Exception:
                pass
            self._stats_panel = None
            self._stats_ring_canvas = None

    def _refresh_stats_panel(self):
        if self._stats_panel is None or not self._stats_panel.winfo_exists():
            return
        snap = stats_tracker.snapshot()
        balance = balance_fetcher.get()
        git = git_info.get()

        sat = snap["satiety"]
        food = snap["food"]
        st = snap["stats"]
        f = self._fmt_tokens
        eff = snap["efficiency"]
        tps = st["tokens_per_sec"]

        # 饱腹度进度环
        ring = getattr(self, "_stats_ring_canvas", None)
        if ring is not None:
            ring.delete("all")
            pct = sat["percent"]
            pct = max(0.0, min(100.0, float(pct) if isinstance(pct, (int, float)) else 0.0))
            cx = cy = 38
            R = 26
            tw = 6
            ring.create_oval(cx - R, cy - R, cx + R, cy + R, outline=self._BAR_TRACK, width=tw)
            if pct > 0:
                color = self._BAR_ORANGE if pct > pricing.SATIETY_BURP_PERCENT else self._BAR_TEAL
                ring.create_arc(cx - R, cy - R, cx + R, cy + R, start=90,
                                extent=-360 * pct / 100, style="arc", outline=color, width=tw)
            ring.create_text(cx, cy, text=self._fmt_satiety(pct, sat["used_tokens"]),
                             font=(_get_font_family(), 11, "bold"), fill=self._PANEL_FG)

        box = self._stats_panel_text
        box.configure(state="normal")
        box.delete("1.0", "end")

        def add(text, tag=None):
            self._insert_panel_text(box, text, tag)

        def line(segments):
            for text, tag in segments:
                add(text, tag)
            add("\n")

        # 上下文 + 三种口粮（字符估算）
        line([
            ("上下文 ", None),
            (f"{f(sat['used_tokens'])} / {f(sat['context_window'])} tokens", None),
        ])
        line([
            (f"系统 {f(food['system_tokens'])} · 工具 {f(food['tool_tokens'])}"
             f" · 对话 {f(food['chat_tokens'])}", "muted"),
        ])
        add("\n")
        # 工作效率
        line([
            ("⚡ 工作效率 ", None),
            (f"{eff}%（缓存命中）" if eff is not None else "--（缓存命中）", None),
        ])
        # 花费（高峰/空闲分档）
        line([
            ("💰 花费 ", None),
            (self._fmt_cost(snap['cost']), None),
            (f" · 高峰 {self._fmt_cost(snap['peak_cost'])} / 空闲 {self._fmt_cost(snap['off_peak_cost'])}", "muted"),
        ])
        # 涨价前对比
        line([
            (f"🕰 涨价前约 {self._fmt_cost(snap['legacy_cost'])}（同用量旧价）", "muted"),
        ])
        # 余额（绿/红告警）
        pname = providers.provider_name(balance_fetcher.get_provider())
        if balance is not None:
            line([
                (f"💳 {pname} 余额 ", None),
                (self._fmt_cost(balance), "green" if balance >= 10 else "red"),
            ])
        elif not providers.supports_balance(balance_fetcher.get_provider()):
            line([(f"💳 {pname} 余额 --（该服务未开放公开余额接口）", "dim")])
        else:
            line([(f"💳 {pname} 余额 --（未配置 key / 查询失败）", "dim")])

        add("\n")
        # 性能（尽力而为）
        tool_s = f" · 工具 {self._fmt_duration(st['tool_ms'])}" if st["tool_ms"] > 0 else ""
        line([(f"⏱ LLM {self._fmt_duration(st['llm_ms'])}{tool_s}", None)])
        line([(f"🚀 首 token -- · {f'{tps} tok/s' if tps is not None else '--'}", None)])
        add("\n")

        # git 详情
        if git is None:
            line([("🛠 git --", "dim")])
        else:
            branch = git.get("branch") or "(detached)"
            segs = [("🛠 ", None), (branch, None)]
            if git["head"]:
                segs.append((f" · {git['head']}", "muted"))
            if git["conflicts"] > 0:
                segs.append((f" ⚠️ 冲突 {git['conflicts']}", "red"))
            line(segs)
            d = git["dirty"]
            u = git["untracked"]
            if d or u:
                segs2 = []
                if d:
                    segs2.append((f"✏️ {d} 修改", "orange"))
                if d and u:
                    segs2.append((" · ", "muted"))
                if u:
                    segs2.append((f"➕ {u} 未跟踪", "teal"))
                line(segs2)
            else:
                line([("✅ 工作区干净", "green")])

        box.configure(state="disabled")

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

        # 右键菜单改为自绘无边框（细深灰边框 + 彩色 emoji，见 _popup_menu）

    def _show_context_menu(self, event):
        self._popup_menu(event.x_root, event.y_root)

    def _popup_menu(self, x, y):
        """自绘无边框右键菜单：细深灰边框 + 彩色 emoji（对齐数据条，极简 IDE 风）。"""
        # 右键再右键时，先关闭上一个菜单
        if getattr(self, "_menu_win", None) is not None:
            try:
                self._menu_win.destroy()
            except Exception:
                pass
            self._menu_win = None
        win = tk.Toplevel(self.root)
        self._menu_win = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=self._UI_BORDER)  # 1px 深灰边框 = 外层底色

        inner = tk.Frame(win, bg=self._BAR_BG)
        inner.pack(padx=1, pady=1)

        rows = [
            ("💬", "交谈", self._open_chat),
            ("📊", "统计", self._toggle_stats_panel),
            ("💻", "监控Token", self._open_monitor_dialog),
            None,
            ("📈", "显示数据条", self._toggle_stats_bar, True),
            None,
            ("⚙️", "设置", self._open_settings),
            ("⏰", "闹钟设置", self._open_alarm_settings),
            ("🔄", "重置状态", self.state_machine.reset_to_idle),
            None,
            ("", "隐藏", self._do_toggle_visibility),
            ("", "退出", self._quit_app),
        ]

        def _close(_e=None):
            try:
                self.root.unbind("<Button-1>")
            except Exception:
                pass
            if getattr(self, "_menu_win", None) is win:
                self._menu_win = None
            try:
                win.destroy()
            except Exception:
                pass

        def _click(cmd):
            _close()
            if cmd:
                self.root.after(20, cmd)

        def _row_hover(rowf, on):
            bg = self._UI_HOVER if on else self._BAR_BG
            try:
                rowf.configure(bg=bg)
                for c in rowf.winfo_children():
                    c.configure(bg=bg)
            except Exception:
                pass

        for row in rows:
            if row is None:
                tk.Frame(inner, bg=self._UI_BORDER, height=1).pack(fill="x", padx=6, pady=3)
                continue
            highlight = False
            if len(row) == 4:
                emoji, text, cmd, _check = row
                highlight = bool(self._stats_enabled_var.get())
            else:
                emoji, text, cmd = row

            rowf = tk.Frame(inner, bg=self._BAR_BG, cursor="hand2")
            rowf.pack(fill="x")

            # 图标（彩色 emoji）：左侧留白 14，右侧 4 与文字隔开（用 pack 外部留白）
            if emoji:
                eimg = self._emoji_photo(emoji, 14)
                tk.Label(rowf, image=eimg, bg=self._BAR_BG, anchor="center",
                         cursor="hand2").pack(side="left", padx=(14, 4), pady=4)

            # 文字（高亮项用发光图片，字号与普通项一致）；右侧留白 16 加宽菜单
            left_pad = 0 if emoji else 14
            if highlight:
                glow = self._glow_text_photo(text, self._pt_to_px(10))
                if glow is not None:
                    tlbl = tk.Label(rowf, image=glow, bg=self._BAR_BG, anchor="w",
                                    cursor="hand2")
                else:
                    tlbl = tk.Label(rowf, text=text, font=(_get_font_family(), 10),
                                    bg=self._BAR_BG, fg=self._UI_ACCENT, anchor="w",
                                    cursor="hand2")
            else:
                tlbl = tk.Label(rowf, text=text, font=(_get_font_family(), 10),
                                bg=self._BAR_BG, fg=self._PANEL_FG, anchor="w",
                                cursor="hand2")
            tlbl.pack(side="left", fill="x", expand=True, padx=(left_pad, 16), pady=4)

            for w in (rowf, *rowf.winfo_children()):
                w.bind("<Enter>", lambda e: _row_hover(rowf, True))
                w.bind("<Leave>", lambda e: _row_hover(rowf, False))
                w.bind("<Button-1>", lambda e, c=cmd: _click(c))

        win.bind("<Escape>", _close)
        # 左键点击菜单外任意处关闭
        self.root.bind("<Button-1>", lambda e: _close(), add="+")

        win.update_idletasks()
        w = win.winfo_reqwidth()
        h = win.winfo_reqheight()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        if x + w > sw:
            x = sw - w - 4
        if y + h > sh:
            y = sh - h - 4
        win.geometry(f"+{x}+{y}")
        win.focus_force()

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
            # \u70b9\u51fb\u5e95\u90e8\u6570\u636e\u6761 \u2192 \u5207\u6362\u7edf\u8ba1\u9762\u677f
            if self._stats_enabled and event.y >= self.CANVAS_HEIGHT - self.STATS_BAR_H:
                self._toggle_stats_panel()
                return
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
        _apply_window_icon(window)
        window.title("\u8bbe\u7f6e")
        window.resizable(False, False)
        window.attributes("-topmost", True)
        window.configure(bg=self._BAR_BG)
        window.protocol("WM_DELETE_WINDOW", window.destroy)

        frame = tk.Frame(window, padx=14, pady=12, bg=self._BAR_BG)
        frame.pack(fill="both", expand=True)

        sound_var = tk.BooleanVar(value=self.config["sound_enabled"])
        width_var = tk.IntVar(value=self.PET_WIDTH)
        height_var = tk.IntVar(value=self.PET_HEIGHT)

        tk.Checkbutton(frame, text="\u5b8c\u6210\u65f6\u64ad\u653e\u97f3\u6548", variable=sound_var,
                       bg=self._BAR_BG, fg=self._PANEL_FG,
                       selectcolor=self._SURFACE_2, activebackground=self._BAR_BG,
                       activeforeground=self._PANEL_FG).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        tk.Label(frame, text="\u7a97\u53e3\u5bbd\u5ea6", bg=self._BAR_BG, fg=self._PANEL_FG).grid(
            row=1, column=0, sticky="w", pady=4
        )
        tk.Spinbox(frame, from_=220, to=600, increment=10, textvariable=width_var, width=8,
                   bg=self._SURFACE_2, fg=self._PANEL_FG, buttonbackground=self._UI_BORDER,
                   relief="flat", justify="center").grid(
            row=1, column=1, sticky="e", pady=4
        )

        tk.Label(frame, text="\u7a97\u53e3\u9ad8\u5ea6", bg=self._BAR_BG, fg=self._PANEL_FG).grid(
            row=2, column=0, sticky="w", pady=4
        )
        tk.Spinbox(frame, from_=180, to=500, increment=10, textvariable=height_var, width=8,
                   bg=self._SURFACE_2, fg=self._PANEL_FG, buttonbackground=self._UI_BORDER,
                   relief="flat", justify="center").grid(
            row=2, column=1, sticky="e", pady=4
        )

        stats_bar_var = tk.BooleanVar(value=self._stats_enabled)
        tk.Checkbutton(frame, text="\u663e\u793a\u5e95\u90e8\u6570\u636e\u6761", variable=stats_bar_var,
                       bg=self._BAR_BG, fg=self._PANEL_FG,
                       selectcolor=self._SURFACE_2, activebackground=self._BAR_BG,
                       activeforeground=self._PANEL_FG).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        button_row = tk.Frame(frame, bg=self._BAR_BG)
        button_row.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))

        self._make_pill_button(button_row, "\u53d6\u6d88", "", self._BAR_MUTED,
                               window.destroy).pack(side="right")
        self._make_pill_button(button_row, "\u4fdd\u5b58", "", self._UI_ACCENT,
                               lambda: self._save_settings(window, sound_var, width_var, height_var, stats_bar_var)).pack(side="right", padx=(0, 8))

        x = self.root.winfo_x() - 20
        y = max(20, self.root.winfo_y() - 40)
        window.geometry(f"+{x}+{y}")

    def _save_settings(self, window, sound_var, width_var, height_var, stats_bar_var):
        self.config["sound_enabled"] = bool(sound_var.get())
        self.config["window"]["width"] = width_var.get()
        self.config["window"]["height"] = height_var.get()
        self._stats_enabled = bool(stats_bar_var.get())
        self._stats_enabled_var.set(self._stats_enabled)
        self.config.setdefault("stats_bar", {})["enabled"] = self._stats_enabled
        self.config = normalize_app_config(self.config)
        save_app_config(self.config)
        self._apply_window_size()
        window.destroy()
        logger.info(f"[PET] Config saved: {CONFIG_PATH}")

    def _show_dropdown_menu(self, anchor, items, on_select):
        """在 anchor 正下方弹出细边框、无勾选的下拉菜单（极简 IDE 风）。

        items: [(label, value), ...]；点击某项后调用 on_select(value)。
        """
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=self._UI_BORDER)  # 1px 深灰边框 = 外层底色

        inner = tk.Frame(win, bg=self._SURFACE_2)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        def _close(_e=None):
            try:
                self.root.unbind_all("<Button-1>")
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass

        def _choose(v):
            _close()
            if on_select:
                self.root.after(0, on_select, v)

        for label, value in items:
            it = tk.Label(inner, text=label, bg=self._SURFACE_2, fg=self._PANEL_FG,
                          font=(_get_font_family(), 10), anchor="w",
                          padx=12, pady=4, cursor="hand2")
            it.pack(fill="x")
            it.bind("<Enter>", lambda e, l=it: l.configure(bg=self._UI_HOVER))
            it.bind("<Leave>", lambda e, l=it: l.configure(bg=self._SURFACE_2))
            it.bind("<Button-1>", lambda e, v=value: _choose(v))

        win.bind("<Escape>", _close)
        self.root.bind_all("<Button-1>", lambda e: _close(), add="+")

        win.update_idletasks()
        ax = anchor.winfo_rootx()
        ay = anchor.winfo_rooty() + anchor.winfo_height() + 2
        aw = anchor.winfo_width()
        w = max(win.winfo_reqwidth(), aw)
        h = win.winfo_reqheight()
        sh = win.winfo_screenheight()
        if ay + h > sh:
            ay = anchor.winfo_rooty() - h - 2
        win.geometry(f"{w}x{h}+{ax}+{ay}")
        win.focus_force()

    def _open_supplier_dropdown(self, anchor_box, entry, on_select):
        """供应商下拉：预设供应商 + 「其他」（选其他后可自由输入自定义名字）。"""
        items = [(p["name"], p["name"]) for p in providers.PROVIDERS] + [("其他", "")]

        def _choose(name):
            entry.delete(0, "end")
            if name:
                entry.insert(0, name)
            else:
                entry.focus_set()
            if on_select:
                on_select(name)

        self._show_dropdown_menu(anchor_box, items, _choose)

    def _open_monitor_dialog(self):
        """打开「监控 Token」弹窗：切换要监控的 AI 供应商 + 查看/编辑 API Key。"""
        if hasattr(self, "_monitor_window") and self._monitor_window and self._monitor_window.winfo_exists():
            self._monitor_window.lift()
            self._monitor_window.focus_force()
            return

        monitor = self.config.get("monitor", {})
        keys = dict(monitor.get("keys", {}))
        current_provider = balance_fetcher.get_provider() or monitor.get("provider", "deepseek")

        name_to_id = {p["name"]: p["id"] for p in providers.PROVIDERS}
        id_to_name = {p["id"]: p["name"] for p in providers.PROVIDERS}
        current_name = id_to_name.get(current_provider, current_provider)

        BG = self._BAR_BG
        FG = self._PANEL_FG
        DIM = self._BAR_MUTED
        FIELD = self._SURFACE_2  # 输入框底（比面板略亮，增加对比）
        BORDER = self._UI_BORDER

        window = tk.Toplevel(self.root)
        self._monitor_window = window
        _apply_window_icon(window)
        window.title("监控 Token")
        window.resizable(False, False)
        window.attributes("-topmost", True)
        window.configure(bg=BG)
        window.protocol("WM_DELETE_WINDOW", window.destroy)

        frame = tk.Frame(window, padx=14, pady=12, bg=BG)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="监控供应商", bg=BG, fg=FG, anchor="w").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        provider_var = tk.StringVar(value=current_name)

        # 切换供应商时先保存当前编辑，再载入目标供应商的 key（下拉选择时触发）
        _state = {"provider": current_provider}

        def _apply_provider(name):
            pid = name_to_id.get(name, name) if name else providers.DEFAULT_PROVIDER
            keys[_state["provider"]] = key_var.get()
            _state["provider"] = pid
            if providers.supports_balance(pid):
                note_var.set("✅ 余额可实时查询，将显示在数据条「💰」处。")
            else:
                note_var.set("⚠️ 该供应商未开放公开余额接口，数据条余额显示 --（Key 仅存档）。")
            key_var.set(keys.get(pid, ""))

        # 供应商字段：文本框 + 右侧 ▼ 下拉箭头（与 API Key 输入框同宽）
        supplier_box = tk.Frame(frame, bg=FIELD, highlightthickness=1, highlightbackground=BORDER)
        supplier_entry = tk.Entry(
            supplier_box, textvariable=provider_var,
            bg=FIELD, fg=FG, insertbackground=FG, relief="flat", bd=0,
            highlightthickness=0, font=(_get_font_family(), 10),
        )
        supplier_entry.pack(side="left", fill="both", expand=True, padx=(8, 0))
        arrow_btn = tk.Button(
            supplier_box, text="▼",
            command=lambda: self._open_supplier_dropdown(supplier_box, supplier_entry, _apply_provider),
            bg=FIELD, fg=DIM, activebackground=BORDER, activeforeground=FG,
            relief="flat", bd=0, highlightthickness=0, font=(_get_font_family(), 8),
            padx=8, cursor="hand2",
        )
        arrow_btn.pack(side="right", fill="y")
        supplier_box.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        tk.Label(frame, text="API Key", bg=BG, fg=FG, anchor="w").grid(
            row=2, column=0, sticky="w", pady=(0, 4)
        )
        key_var = tk.StringVar(value=keys.get(current_provider, ""))
        show_var = tk.BooleanVar(value=False)
        key_entry = tk.Entry(
            frame, textvariable=key_var, show="●",
            bg=FIELD, fg=FG, insertbackground=FG, relief="flat",
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=self._UI_ACCENT,
        )
        key_entry.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        tk.Checkbutton(
            frame, text="显示", variable=show_var, bg=BG, fg=DIM,
            selectcolor=FIELD, activebackground=BG, activeforeground=FG,
            command=lambda: key_entry.configure(show="" if show_var.get() else "●"),
        ).grid(row=3, column=1, sticky="w", padx=(8, 0), pady=(0, 6))

        note_var = tk.StringVar()
        note_label = tk.Label(
            frame, textvariable=note_var, bg=BG, fg=DIM,
            justify="left", wraplength=320, anchor="w",
        )
        note_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 10))

        # 让供应商框与 API Key 输入框共享列宽（同宽）
        frame.grid_columnconfigure(0, weight=1, minsize=280)

        # 初始化备注（当前供应商）
        _apply_provider(current_name)

        button_row = tk.Frame(frame, bg=BG)
        button_row.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))
        self._make_pill_button(button_row, "取消", "", DIM,
                               window.destroy).pack(side="right")
        self._make_pill_button(button_row, "保存", "", self._UI_ACCENT,
                               lambda: self._save_monitor(window, name_to_id, provider_var, key_var)).pack(side="right", padx=(0, 8))

        x = self.root.winfo_x() - 20
        y = max(20, self.root.winfo_y() - 40)
        window.geometry(f"+{x}+{y}")

    def _save_monitor(self, window, name_to_id, provider_var, key_var):
        name = (provider_var.get() or "").strip()
        provider = name_to_id.get(name, name) if name else providers.DEFAULT_PROVIDER
        key = (key_var.get() or "").strip()
        monitor = self.config.setdefault("monitor", {})
        monitor["provider"] = provider
        keys = dict(monitor.get("keys", {}))
        keys[provider] = key
        monitor["keys"] = keys
        self.config = normalize_app_config(self.config)
        save_app_config(self.config)
        balance_fetcher.set_provider_key(provider, key)
        window.destroy()
        logger.info(f"[PET] 监控供应商切换为 {providers.provider_name(provider)}")

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
        _apply_window_icon(window)
        window.title("闹钟设置")
        window.resizable(False, False)
        window.attributes("-topmost", True)
        window.configure(bg=self._BAR_BG)
        window.protocol("WM_DELETE_WINDOW", self._on_alarm_window_close)

        # 主容器
        main_frame = tk.Frame(window, bg=self._BAR_BG, padx=16, pady=12)
        main_frame.pack(fill="both", expand=True)

        # 标题
        tk.Label(
            main_frame,
            text="闹钟设置",
            image=self._emoji_photo("⏰", 18), compound="left",
            font=(_get_font_family(), 14, "bold"),
            bg=self._BAR_BG,
            fg=self._PANEL_FG,
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            main_frame,
            text="设置定时提醒，到点弹出对话框",
            font=(_get_font_family(), 9),
            bg=self._BAR_BG,
            fg=self._BAR_DIM,
        ).pack(anchor="w", pady=(0, 12))

        # 闹钟列表区域（可滚动）
        list_container = tk.Frame(main_frame, bg=self._SURFACE, highlightbackground=self._UI_BORDER, highlightthickness=1)
        list_container.pack(fill="both", expand=True, pady=(0, 10))
        list_container.grid_columnconfigure(0, weight=1)
        list_container.grid_rowconfigure(1, weight=1)

        # 表头（grid 表格：固定列宽 + 1px 网格线；与 canvas 同列宽，保证上下对齐）
        header_frame = tk.Frame(list_container, bg=self._UI_BORDER)
        header_frame.grid(row=0, column=0, sticky="ew")
        self._configure_alarm_grid(header_frame)
        for col, text in enumerate(["启用", "时间", "提醒内容", "重复", "操作"]):
            cell = tk.Frame(header_frame, bg=self._SURFACE_2)
            cell.grid(row=0, column=col, sticky="nsew", padx=1, pady=1)
            tk.Label(cell, text=text, font=(_get_font_family(), 9, "bold"),
                     bg=self._SURFACE_2, fg=self._BAR_MUTED,
                     anchor="w", padx=6, pady=4).pack(fill="x")

        # 可滚动的闹钟列表（canvas 与表头同列，scrollbar 独占右侧一列）
        canvas = tk.Canvas(list_container, bg=self._SURFACE, height=260, highlightthickness=0)
        scrollbar = tk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self._SURFACE)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        # 让行宽跟随 canvas 宽度，保证与表头列对齐
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")

        # 鼠标滚轮支持
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ---- 添加闹钟表单 ----
        form_frame = tk.Frame(main_frame, bg=self._BAR_BG)
        form_frame.pack(fill="x", pady=(0, 10))

        tk.Label(form_frame, text="新增闹钟:", font=(_get_font_family(), 10, "bold"),
                 bg=self._BAR_BG, fg=self._PANEL_FG).pack(anchor="w", pady=(0, 6))

        row1 = tk.Frame(form_frame, bg=self._BAR_BG)
        row1.pack(fill="x", pady=(0, 4))

        tk.Label(row1, text="时间", font=(_get_font_family(), 9),
                 bg=self._BAR_BG, fg=self._BAR_MUTED).pack(side="left", padx=(0, 6))

        # 时间选择：小时和分钟下拉
        hour_var = tk.StringVar(value="09")
        minute_var = tk.StringVar(value="00")

        hour_spin = tk.Spinbox(row1, from_=0, to=23, textvariable=hour_var,
                               width=3, format="%02.0f", font=(_get_font_family(), 10),
                               bg=self._SURFACE_2, fg=self._PANEL_FG, buttonbackground=self._UI_BORDER,
                               relief="flat", justify="center")
        hour_spin.pack(side="left")

        tk.Label(row1, text=":", font=(_get_font_family(), 10, "bold"),
                 bg=self._BAR_BG, fg=self._PANEL_FG).pack(side="left", padx=2)

        minute_spin = tk.Spinbox(row1, from_=0, to=59, textvariable=minute_var,
                                 width=3, format="%02.0f", font=(_get_font_family(), 10),
                                 bg=self._SURFACE_2, fg=self._PANEL_FG, buttonbackground=self._UI_BORDER,
                                 relief="flat", justify="center")
        minute_spin.pack(side="left")

        tk.Label(row1, text="  内容", font=(_get_font_family(), 9),
                 bg=self._BAR_BG, fg=self._BAR_MUTED).pack(side="left", padx=(12, 6))

        label_var = tk.StringVar(value="")
        label_entry = tk.Entry(row1, textvariable=label_var, font=(_get_font_family(), 10),
                               bg=self._SURFACE_2, fg=self._PANEL_FG, insertbackground=self._PANEL_FG,
                               relief="flat", width=24)
        label_entry.pack(side="left", fill="x", expand=True)

        # 星期选择
        row2 = tk.Frame(form_frame, bg=self._BAR_BG)
        row2.pack(fill="x", pady=(4, 6))

        tk.Label(row2, text="重复", font=(_get_font_family(), 9),
                 bg=self._BAR_BG, fg=self._BAR_MUTED).pack(side="left", padx=(0, 8))

        day_vars = []
        for i, day_name in enumerate(DAY_NAMES):
            var = tk.BooleanVar(value=(i < 5))  # 周一至周五默认选中
            day_vars.append(var)
            cb = tk.Checkbutton(
                row2, text=day_name, variable=var,
                font=(_get_font_family(), 8),
                bg=self._BAR_BG, fg=self._BAR_MUTED,
                selectcolor=self._SURFACE_2, activebackground=self._BAR_BG,
                activeforeground="#FFFFFF",
            )
            cb.pack(side="left", padx=1)

        # 添加按钮行
        row3 = tk.Frame(form_frame, bg=self._BAR_BG)
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

        self._make_pill_button(row3, "添加闹钟", "➕", self._UI_ACCENT,
                               add_alarm).pack(side="left")

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

        self._make_pill_button(row3, "加载预设模板", "📋", self._BAR_MUTED,
                               load_presets).pack(side="left", padx=(8, 0))

        # 预览按钮：预览闹钟提醒弹窗
        def preview_alarm():
            msg = label_var.get().strip() or "💧 该喝水啦！"
            show_alarm_popup(self.root, msg)

        self._make_pill_button(row3, "预览", "👁", self._BAR_MUTED,
                               preview_alarm).pack(side="left", padx=(8, 0))

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
                    bg=self._SURFACE, fg="#666666", pady=40,
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
        self._make_pill_button(main_frame, "关闭", "", self._BAR_MUTED,
                               self._on_alarm_window_close).pack(anchor="e", pady=(6, 0))

        # 定位窗口
        x = self.root.winfo_x() - 60
        y = max(20, self.root.winfo_y() - 40)
        window.geometry(f"+{x}+{y}")
        window.minsize(520, 480)

    def _configure_alarm_grid(self, frame):
        """闹钟表格列宽（表头与行共用，保证对齐）。"""
        frame.grid_columnconfigure(0, minsize=44)      # 启用
        frame.grid_columnconfigure(1, minsize=56)      # 时间
        frame.grid_columnconfigure(2, weight=1, minsize=150)  # 提醒内容（弹性）
        frame.grid_columnconfigure(3, minsize=120)     # 重复
        frame.grid_columnconfigure(4, minsize=70)      # 操作

    def _create_alarm_row(self, parent, alarm, refresh_callback):
        """创建单个闹钟行（grid 表格，与表头列对齐）"""
        row_frame = tk.Frame(parent, bg=self._UI_BORDER)
        row_frame.pack(fill="x", pady=1)
        self._configure_alarm_grid(row_frame)

        # 启用开关
        enabled_var = tk.BooleanVar(value=alarm.get("enabled", False))

        def toggle_enabled():
            alarm["enabled"] = enabled_var.get()
            save_app_config(self.config)

        cell0 = tk.Frame(row_frame, bg=self._BAR_BG)
        cell0.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        tk.Checkbutton(
            cell0, variable=enabled_var, command=toggle_enabled,
            bg=self._BAR_BG, activebackground=self._BAR_BG,
            selectcolor=self._SURFACE_2,
        ).pack(anchor="center")

        # 时间
        cell1 = tk.Frame(row_frame, bg=self._BAR_BG)
        cell1.grid(row=0, column=1, sticky="nsew", padx=1, pady=1)
        tk.Label(cell1, text=alarm.get("time", "09:00"),
                 font=(_get_font_family(), 11, "bold"),
                 bg=self._BAR_BG, fg=self._BAR_YELLOW, anchor="w").pack(fill="x", padx=6, pady=4)

        # 提醒内容：开头 emoji 单独渲染彩色图片，其余文字正常显示
        raw_label = alarm.get("label", "⏰ 闹钟") or "⏰ 闹钟"
        emoji, rest = _split_emoji_prefix(raw_label)
        lbl_img = self._emoji_photo(emoji, 14) if emoji else None
        cell2 = tk.Frame(row_frame, bg=self._BAR_BG)
        cell2.grid(row=0, column=2, sticky="nsew", padx=1, pady=1)
        tk.Label(
            cell2,
            text=rest if emoji else raw_label,
            image=lbl_img, compound="left",
            font=(_get_font_family(), 10),
            bg=self._BAR_BG, fg=self._PANEL_FG, anchor="w",
        ).pack(fill="x", padx=6, pady=4)

        # 重复（星期显示）
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

        cell3 = tk.Frame(row_frame, bg=self._BAR_BG)
        cell3.grid(row=0, column=3, sticky="nsew", padx=1, pady=1)
        tk.Label(cell3, text=day_text,
                 font=(_get_font_family(), 8),
                 bg=self._BAR_BG, fg=self._BAR_DIM, anchor="w").pack(fill="x", padx=6, pady=4)

        # 操作（删除）
        def delete_alarm(aid=alarm.get("id")):
            self.config["alarms"] = [a for a in self.config.get("alarms", []) if a.get("id") != aid]
            save_app_config(self.config)
            refresh_callback()

        del_img = self._emoji_photo("🗑️", 13)
        cell4 = tk.Frame(row_frame, bg=self._BAR_BG)
        cell4.grid(row=0, column=4, sticky="nsew", padx=1, pady=1)
        tk.Button(
            cell4, command=delete_alarm,
            text="删除", image=del_img, compound="left",
            font=(_get_font_family(), 9),
            bg=self._BAR_BG, fg=self._BAR_RED,
            activebackground=self._UI_HOVER, activeforeground=self._BAR_RED,
            relief="flat", padx=6, pady=0, cursor="hand2",
            bd=0,
        ).pack(anchor="center", pady=4)

    def _on_alarm_window_close(self):
        """关闭闹钟窗口时的清理"""
        if hasattr(self, '_alarm_window') and self._alarm_window:
            self._alarm_window.destroy()
            self._alarm_window = None

    def _apply_window_size(self):
        self.PET_WIDTH = self.config["window"]["width"]
        self.PET_HEIGHT = self.config["window"]["height"]
        self.CANVAS_HEIGHT = self.PET_HEIGHT + self.BUBBLE_TOP + (self.STATS_BAR_H if self._stats_enabled else 0)

        self.canvas.config(width=self.PET_WIDTH, height=self.CANVAS_HEIGHT)
        self._reload_state_images()
        self.canvas.itemconfig(self.state_image, image=self._state_images[self.current_state])
        self._layout_static_items()
        self.canvas.coords(self.state_image, 0, self.BUBBLE_TOP)
        self._draw_stats_bar()
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
                if event_type == "show_bubble":
                    self._show_bubble(message)
                elif event_type == "show_bubble_persist":
                    self._show_bubble(message, duration_ms=300000)  # 5 min
                else:
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
