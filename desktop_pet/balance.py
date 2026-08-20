"""多供应商账户余额查询（60s 懒刷新，失败保留上次值）。

余额查询逻辑与供应商差异已下沉到 providers.fetch_balance；
本类只负责缓存、节流与线程安全，通过 set_provider_key 切换监控对象。
"""

import threading
import time

from desktop_pet import providers

REFRESH_SECONDS = 60.0
RETRY_SECONDS = 30.0


class BalanceFetcher:
    def __init__(self):
        self._lock = threading.Lock()
        self._provider = providers.DEFAULT_PROVIDER
        self._api_key = None
        self._value = None  # float 或 None（未配置 key / 查询失败）
        self._last_fetch = 0.0
        self._fetching = False

    def set_provider_key(self, provider, key):
        """切换监控供应商 + key；切换后立即重置缓存以触发重查。"""
        with self._lock:
            self._provider = providers.normalize_provider(provider)
            self._api_key = (key or "").strip() or None
            self._value = None
            self._last_fetch = 0.0

    def set_api_key(self, key):
        """兼容旧调用：仍视为 DeepSeek key。"""
        self.set_provider_key(providers.DEFAULT_PROVIDER, key)

    def get_provider(self):
        with self._lock:
            return self._provider

    def get(self, force=False):
        """返回余额（元）或 None；懒刷新（60s 节奏），失败保留上次值。"""
        with self._lock:
            provider = self._provider
            key = self._api_key
            value = self._value
            last = self._last_fetch
            fetching = self._fetching
        if not key:
            return None
        if not force and time.time() - last < REFRESH_SECONDS:
            return value
        if fetching:
            return value
        with self._lock:
            self._fetching = True
        self._fetch_async(provider, key)
        return value

    def _fetch_async(self, provider, key):
        def worker():
            try:
                v = providers.fetch_balance(provider, key)
                with self._lock:
                    self._value = v
                    self._last_fetch = time.time()
                    self._fetching = False
            except Exception:
                # 网络/API 失败：保留上次值，30s 后重试。
                with self._lock:
                    self._last_fetch = time.time() - (REFRESH_SECONDS - RETRY_SECONDS)
                    self._fetching = False

        threading.Thread(target=worker, daemon=True).start()
