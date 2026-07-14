import datetime
import logging
import threading

logger = logging.getLogger()

STATE_CONFIG = {
    "idle":       {"emoji": "\U0001F431", "label": "\u547c\u565c\u565c~",       "bg": "#2D2D2D", "fg": "#4CAF50"},
    "reading":    {"emoji": "\U0001F4D6", "label": "\u770b\u770b\u4e3b\u4eba\u5728\u5e72\u561b...", "bg": "#E8F5E9", "fg": "#2E7D32"},
    "step_done":  {"emoji": "\u2705",     "label": "\u505a\u5b8c\u5566\uff01\u5389\u5bb3~", "bg": "#1A237E", "fg": "#81C784"},
    "happy":      {"emoji": "\U0001F389", "label": "\u5f00\u5fc3\uff01( \u00b4\u30fb\u2200\u30fb)\uff89", "bg": "#1B5E20", "fg": "#FFD54F"},
    "waiting":    {"emoji": "\U0001F914", "label": "\u4e3b\u4eba\u4f60\u5728\u54ea\uff1f",  "bg": "#E65100", "fg": "#FFB74D"},
    "sad":        {"emoji": "\U0001F635", "label": "\u545c\u545c...\u4e0d\u5f00\u5fc3",     "bg": "#B71C1C", "fg": "#EF9A9A"},
    "tired":      {"emoji": "\U0001F634", "label": "\u56f0\u56f0...\u60f3\u7761\u89c9( '\u30fb\u03c9\u30fb)\u309b", "bg": "#1A1A2E", "fg": "#7986CB"},
    "sleeping":   {"emoji": "\U0001F4A4", "label": "\u547c\u547c\u547c...\u5494\u6bd4~",    "bg": "#1A1A2E", "fg": "#5C6BC0"},
    "thinking":   {"emoji": "\U0001F914", "label": "\u5494\u6bd4\u6b63\u5728\u60f3...",     "bg": "#1A237E", "fg": "#90CAF9"},
}

CLICK_RESPONSES = {
    "idle":      "\u5494\u6bd4\uff01\u4e3b\u4eba\u4f60\u597d~ \u6709\u5403\u7684\u5417\uff1f(\u00b4\u30fb\u03c9\u30fb`)",
    "reading":   "\u5494\u6bd4\u6b63\u5728\u770b\u4e3b\u4eba\u5199\u4ee3\u7801... \u597d\u5389\u5bb3\uff01",
    "happy":     "\u4efb\u52a1\u5b8c\u6210\u5566\uff01\u5956\u52b1\u4e3b\u4eba\u4e00\u4e2a\u62b1\u62b1\uff01( o \u30fb\u03c9\u30fb) \u30ce",
    "waiting":   "\u4e3b\u4eba\u522b\u53d1\u5446\u4e86\u5feb\u56de\u6765~ \u5494\u6bd4\u60f3\u4f60\u4e86\uff01",
    "sad":       "\u4e0d\u5f00\u5fc3... \u4e3b\u4eba\u80fd\u62b1\u62b1\u5494\u6bd4\u5417\uff1f( '\u30fb\u03c9\u30fb)\u309b",
    "tired":     "\u5494\u6bd4\u597d\u56f0... \u4e3b\u4eba\u4e5f\u8be5\u4f11\u606f\u4e86\u5594~",
    "sleeping":  "\u547c...\u554a\uff01\u4e3b\u4eba\u4f60\u628a\u5494\u6bd4\u5435\u9192\u4e86... \u6709\u5c0f\u86cb\u7cd5\u5417\uff1f",
    "thinking":  "\u5494\u6bd4\u7684\u8111\u888b\u5728\u8f6c... \u4e0d\u8981\u50ac\u6211\u561b~",
    "step_done": "\u5494\u6bd4\u5e2e\u4e3b\u4eba\u8bb0\u4e0b\u4e86\uff01\u8fdb\u5ea6+1\uff01( o \u30fb\u03c9\u30fb) \u30ce",
}

EVENT_TO_STATE = {
    "task_start": "thinking",
    "tool_start": "thinking",
    "reading_start": "reading",
    "step_complete": "step_done",
    "task_complete": "happy",
    "user_confirmation_needed": "waiting",
    "error": "sad",
}

CLICK_RESPONSES = {
    "idle":      "\u55b5~ \u4e3b\u4eba\u4f60\u597d\u5440!",
    "reading":   "\u6b63\u5728\u67e5\u770b\u6587\u4ef6...",
    "happy":     "\u4efb\u52a1\u5b8c\u6210\u5566! \u2605\u2192\u2606",
    "waiting":   "\u4e3b\u4eba\u5feb\u6765\u770b\u770b!",
    "sad":       "\u5509\uff0c\u51fa\u9519\u4e86...",
    "tired":     "\u597d\u7d2f\u554a...\u8ba9\u6211\u6b47\u4f1a\u513f",
    "sleeping":  "Zzz...\uff08\u88ab\u5436\u9192\u4e86\uff09",
    "thinking":  "\u55ef...\u8ba9\u6211\u60f3\u60f3...",
    "step_done": "\u8fdb\u5ea6+1!",
}

AUTO_RECOVERY = {
    "step_done": ("thinking", 1500),
    "reading":   ("thinking", 2000),
    "happy":     ("idle", 5000),
    "waiting":   ("idle", 8000),
    "sad":       ("idle", 5000),
}


class StateMachine:
    def __init__(self, on_state_change=None):
        self._on_state_change = on_state_change or (lambda s, m: None)
        self._lock = threading.Lock()
        self.current_state = "idle"
        self.current_message = ""
        self._state_entered_at = datetime.datetime.now()
        self._last_event_at = None

    def set_callback(self, callback):
        with self._lock:
            self._on_state_change = callback

    def process_event(self, event_type, message=""):
        new_state = EVENT_TO_STATE.get(event_type)
        if not new_state:
            return

        with self._lock:
            self._last_event_at = datetime.datetime.now()

        self.transition(new_state, message)

    def transition(self, new_state, message=""):
        if new_state not in STATE_CONFIG:
            logger.warning(f"[PET] Invalid state: {new_state}, ignoring transition")
            return
        cb = None
        with self._lock:
            old_state = self.current_state
            if old_state == new_state and not message:
                return

            self.current_state = new_state
            self.current_message = message
            if old_state != new_state:
                self._state_entered_at = datetime.datetime.now()
            cb = self._on_state_change

        logger.info(f"[PET] State -> {new_state}" + (f" | {message}" if message else ""))
        if cb:
            cb(new_state, message)

    def check_timeouts(self, config):
        now = datetime.datetime.now()

        with self._lock:
            state = self.current_state
            entered_at = self._state_entered_at
            last_event = self._last_event_at

        if state == "step_done" and last_event:
            step_done_timeout = config.get("step_done_timeout_ms", 5000) / 1000
            elapsed = (now - last_event).total_seconds()
            if elapsed > step_done_timeout:
                self.transition("thinking", "")
                return

        if state == "thinking":
            tired_timeout = config.get("thinking_tired_timeout_ms", 180000) / 1000
            elapsed = (now - entered_at).total_seconds()
            if elapsed > tired_timeout:
                self.transition("tired", "")
                return

        if state == "idle":
            sleep_timeout = config.get("idle_sleeping_timeout_ms", 600000) / 1000
            elapsed = (now - entered_at).total_seconds()
            if elapsed > sleep_timeout:
                self.transition("sleeping", "")
                return

    def get_auto_recovery(self, state, config):
        if state in AUTO_RECOVERY:
            target, default_ms = AUTO_RECOVERY[state]
            duration = config.get("state_durations", {}).get(state, default_ms)
            if duration > 0:
                return target, duration
        return None, 0

    def get_snapshot(self):
        with self._lock:
            return self.current_state, self.current_message

    def wake_up(self):
        with self._lock:
            should_wake = self.current_state == "sleeping"
        if should_wake:
            self.transition("idle", "")

    def reset_to_idle(self):
        self.transition("idle", "")
