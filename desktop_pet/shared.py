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
