import collections
import os
import queue
import threading

MAX_EVENTS = 100
MAX_QUEUE_SIZE = 50
PET_PORT = int(os.environ.get("PET_PORT", "3456"))

events = collections.deque(maxlen=MAX_EVENTS)
event_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
app_state = {"current_state": "idle", "current_message": "", "last_event_time": None}
app_state_lock = threading.Lock()

# 数据条相关单例（Flask 线程写、Tkinter 线程读）
from desktop_pet.stats import StatsTracker  # noqa: E402
from desktop_pet.balance import BalanceFetcher  # noqa: E402
from desktop_pet.gitinfo import GitInfo  # noqa: E402

stats_tracker = StatsTracker()
balance_fetcher = BalanceFetcher()
git_info = GitInfo()
