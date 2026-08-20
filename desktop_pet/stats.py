"""会话统计：解析 Claude Code transcript JSONL，累计 token 用量与花费。

数据源与 Claude Code 状态栏（StatsLine）同一份 transcript 的 `message.usage`，
不自算 token——只把官方给出的四桶（input/cache_read/cache_creation/output）
按 DeepSeek 峰谷定价分档累计成花费，并派生效率/饱腹度/口粮/性能。

分档按 assistant 消息的本地时间戳（`timestamp`，ISO UTC）判断高峰/空闲。
累计为服务级：持久化到 `%LOCALAPPDATA%/DesktopPet/pet_stats.json`，跨会话/重启保留。
"""

import datetime
import json
import os
import threading

from desktop_pet import pricing
from desktop_pet.config import APP_DATA_DIR

STATS_PATH = os.path.join(APP_DATA_DIR, "pet_stats.json")


def _est_tokens(text):
    """粗略 token 估算：中文≈1 token/字、英文≈1 token/4 字符，混合取 2 字符。"""
    if not text:
        return 0
    return max(1, round(len(text) / 2))


def _parse_ts(ts):
    """ISO 时间戳（含 Z）→ 本地 datetime；失败返回 None。"""
    if not ts:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt
    except (ValueError, TypeError):
        return None


def _num(value):
    try:
        f = float(value)
        return f if f == f else 0.0  # NaN guard
    except (TypeError, ValueError):
        return 0.0


class StatsTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._context_window = pricing.DEFAULT_CONTEXT_WINDOW

        # 累计四桶（Anthropic usage 口径）
        self._input_tokens = 0       # 未命中输入（已排除 cache_read、含 cache_creation）
        self._cache_read = 0         # 缓存命中输入
        self._output_tokens = 0      # 输出

        # 累计花费（元）
        self._peak_cost = 0.0
        self._off_peak_cost = 0.0
        self._legacy_cost = 0.0

        # 性能（尽力而为，近似）
        self._llm_ms = 0.0
        self._tool_ms = 0.0

        # 口粮估算（字符数估算）
        self._chat_tokens = 0
        self._tool_tokens = 0

        # 最近一次请求的输入量（饱腹度分子）
        self._last_billed_input = 0

        # transcript 增量偏移：{path: byte_offset}
        self._offsets = {}

        # 跨 ingest 的工具计时（内存态，不持久化）
        self._tool_start = {}

        self._load()

    # ── 持久化 ──
    def _load(self):
        try:
            if not os.path.exists(STATS_PATH):
                return
            with open(STATS_PATH, encoding="utf-8") as f:
                d = json.load(f)
            self._input_tokens = int(_num(d.get("input_tokens")))
            self._cache_read = int(_num(d.get("cache_read")))
            self._output_tokens = int(_num(d.get("output_tokens")))
            self._peak_cost = _num(d.get("peak_cost"))
            self._off_peak_cost = _num(d.get("off_peak_cost"))
            self._legacy_cost = _num(d.get("legacy_cost"))
            self._llm_ms = _num(d.get("llm_ms"))
            self._tool_ms = _num(d.get("tool_ms"))
            self._chat_tokens = int(_num(d.get("chat_tokens")))
            self._tool_tokens = int(_num(d.get("tool_tokens")))
            self._last_billed_input = int(_num(d.get("last_billed_input")))
            self._offsets = {
                str(k): int(_num(v)) for k, v in (d.get("offsets") or {}).items()
            }
        except Exception:
            pass

    def _save(self):
        try:
            with self._lock:
                d = {
                    "input_tokens": self._input_tokens,
                    "cache_read": self._cache_read,
                    "output_tokens": self._output_tokens,
                    "peak_cost": self._peak_cost,
                    "off_peak_cost": self._off_peak_cost,
                    "legacy_cost": self._legacy_cost,
                    "llm_ms": self._llm_ms,
                    "tool_ms": self._tool_ms,
                    "chat_tokens": self._chat_tokens,
                    "tool_tokens": self._tool_tokens,
                    "last_billed_input": self._last_billed_input,
                    "offsets": dict(self._offsets),
                }
            with open(STATS_PATH, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── 配置 ──
    def set_context_window(self, window):
        try:
            w = int(window)
        except (TypeError, ValueError):
            w = pricing.DEFAULT_CONTEXT_WINDOW
        with self._lock:
            self._context_window = max(1, w)

    # ── 事件入口（后台线程解析，非阻塞） ──
    def on_activity(self, transcript_path, cwd=None):
        if transcript_path:
            threading.Thread(
                target=self._ingest, args=(transcript_path,), daemon=True
            ).start()

    # ── 增量解析 ──
    def _ingest(self, path):
        try:
            if not os.path.isfile(path):
                return
            with self._lock:
                offset = self._offsets.get(path, 0)
            size = os.path.getsize(path)
            if size < offset:
                offset = 0  # 文件被截断/轮换（罕见，append-only 正常不触发）
            with open(path, "rb") as f:
                f.seek(offset)
                data = f.read()
                end_offset = f.tell()
            if not data:
                return
            text = data.decode("utf-8", errors="replace")

            delta = self._parse_lines(text)
            with self._lock:
                self._apply_delta(delta)
                self._offsets[path] = end_offset
            self._save()
        except Exception:
            pass

    def _parse_lines(self, text):
        """解析新增行，返回增量 dict；不持有锁。"""
        delta = {
            "input_tokens": 0, "cache_read": 0, "output_tokens": 0,
            "peak_cost": 0.0, "off_peak_cost": 0.0, "legacy_cost": 0.0,
            "llm_ms": 0.0, "tool_ms": 0.0,
            "chat_tokens": 0, "tool_tokens": 0,
            "last_billed_input": 0,
        }
        prev_ts = None

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(obj, dict):
                continue

            msg = obj.get("message") or {}
            ts = _parse_ts(obj.get("timestamp"))

            if obj.get("type") == "assistant":
                content = msg.get("content") or []
                has_tool_use = False
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "text" and block.get("text"):
                        delta["chat_tokens"] += _est_tokens(block["text"])
                    elif btype == "tool_use":
                        has_tool_use = True
                        if ts is not None:
                            self._tool_start[block.get("id")] = ts
                        args = block.get("input")
                        if isinstance(args, (dict, list)):
                            try:
                                delta["tool_tokens"] += _est_tokens(json.dumps(args, ensure_ascii=False))
                            except (TypeError, ValueError):
                                pass

                usage = msg.get("usage")
                if isinstance(usage, dict):
                    inp = int(_num(usage.get("input_tokens")))
                    cache_read = int(_num(usage.get("cache_read_input_tokens")))
                    out = int(_num(usage.get("output_tokens")))
                    delta["input_tokens"] += inp
                    delta["cache_read"] += cache_read
                    delta["output_tokens"] += out

                    peak = pricing.is_peak_hour(ts or datetime.datetime.now())
                    hit = pricing.PRICE_CACHE_HIT_PEAK if peak else pricing.PRICE_CACHE_HIT_OFF
                    uncached = pricing.PRICE_UNCACHED_PEAK if peak else pricing.PRICE_UNCACHED_OFF
                    out_p = pricing.PRICE_OUTPUT_PEAK if peak else pricing.PRICE_OUTPUT_OFF
                    billed = (cache_read * hit + inp * uncached + out * out_p) / 1e6
                    if peak:
                        delta["peak_cost"] += billed
                    else:
                        delta["off_peak_cost"] += billed
                    legacy = (cache_read * pricing.PRICE_CACHE_HIT_LEGACY
                              + inp * pricing.PRICE_UNCACHED_LEGACY
                              + out * pricing.PRICE_OUTPUT_LEGACY) / 1e6
                    delta["legacy_cost"] += legacy

                    delta["last_billed_input"] = inp + cache_read

                # LLM 耗时近似：纯文本/思考回合（无工具调用）的相邻消息时间差。
                if ts is not None and not has_tool_use and prev_ts is not None:
                    gap = (ts - prev_ts).total_seconds()
                    if 0 < gap < 3600:
                        delta["llm_ms"] += gap * 1000.0

            elif obj.get("type") == "user":
                content = msg.get("content") or []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "text" and block.get("text"):
                        delta["chat_tokens"] += _est_tokens(block["text"])
                    elif btype == "tool_result":
                        owner = self._tool_start.pop(block.get("tool_use_id"), None)
                        if owner is not None and ts is not None:
                            gap = (ts - owner).total_seconds()
                            if 0 < gap < 3600:
                                delta["tool_ms"] += gap * 1000.0
                        tc = block.get("content")
                        if isinstance(tc, str):
                            delta["tool_tokens"] += _est_tokens(tc)
                        elif isinstance(tc, list):
                            for item in tc:
                                if isinstance(item, dict) and item.get("text"):
                                    delta["tool_tokens"] += _est_tokens(str(item["text"]))

            if ts is not None:
                prev_ts = ts

        return delta

    def _apply_delta(self, d):
        self._input_tokens += d["input_tokens"]
        self._cache_read += d["cache_read"]
        self._output_tokens += d["output_tokens"]
        self._peak_cost += d["peak_cost"]
        self._off_peak_cost += d["off_peak_cost"]
        self._legacy_cost += d["legacy_cost"]
        self._llm_ms += d["llm_ms"]
        self._tool_ms += d["tool_ms"]
        self._chat_tokens += d["chat_tokens"]
        self._tool_tokens += d["tool_tokens"]
        if d["last_billed_input"] > 0:
            self._last_billed_input = d["last_billed_input"]

    # ── 快照 ──
    def snapshot(self):
        with self._lock:
            input_tokens = self._input_tokens
            cache_read = self._cache_read
            output_tokens = self._output_tokens
            peak_cost = self._peak_cost
            off_peak_cost = self._off_peak_cost
            legacy_cost = self._legacy_cost
            llm_ms = self._llm_ms
            tool_ms = self._tool_ms
            chat_tokens = self._chat_tokens
            tool_tokens = self._tool_tokens
            last_billed_input = self._last_billed_input
            context_window = self._context_window

        total_input = input_tokens + cache_read
        cost = peak_cost + off_peak_cost

        efficiency = None
        if total_input > 0:
            efficiency = round(cache_read / total_input * 100)

        percent = 0
        if context_window > 0 and last_billed_input > 0:
            percent = min(100, round(last_billed_input / context_window * 100))
        satiety = {
            "percent": percent,
            "used_tokens": last_billed_input,
            "context_window": context_window,
        }

        system_tokens = max(0, total_input - chat_tokens - tool_tokens)
        food = {
            "system_tokens": system_tokens,
            "tool_tokens": tool_tokens,
            "chat_tokens": chat_tokens,
        }

        tokens_per_sec = None
        if llm_ms > 0:
            tokens_per_sec = round(output_tokens / (llm_ms / 1000.0))

        return {
            "cost": cost,
            "peak_cost": peak_cost,
            "off_peak_cost": off_peak_cost,
            "legacy_cost": legacy_cost,
            "efficiency": efficiency,
            "satiety": satiety,
            "food": food,
            "stats": {
                "llm_ms": round(llm_ms),
                "tool_ms": round(tool_ms),
                "tokens_per_sec": tokens_per_sec,
            },
            "input_tokens": input_tokens,
            "cache_read": cache_read,
            "output_tokens": output_tokens,
        }
