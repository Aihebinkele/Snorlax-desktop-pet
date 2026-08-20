import json
import os
import tempfile

import desktop_pet.stats as stats_mod
from desktop_pet.stats import StatsTracker, _est_tokens, _parse_ts, _num

# 无 pytest 依赖：pytest 与自写运行器均可直接运行（tempfile + 手动 patch）
_ORIG_STATS_PATH = stats_mod.STATS_PATH


def _temp_stats_path():
    tmp = tempfile.mkdtemp()
    stats_mod.STATS_PATH = os.path.join(tmp, "stats.json")
    return tmp


def _restore_stats_path():
    stats_mod.STATS_PATH = _ORIG_STATS_PATH


def test_est_tokens():
    assert _est_tokens("") == 0
    assert _est_tokens(None) == 0
    assert _est_tokens("a") == 1
    assert _est_tokens("abcd") == 2


def test_num():
    assert _num(1.5) == 1.5
    assert _num("2.5") == 2.5
    assert _num("abc") == 0.0
    assert _num(None) == 0.0
    assert _num(float("nan")) == 0.0


def test_parse_ts_z_suffix():
    dt = _parse_ts("2026-08-19T10:00:00Z")
    assert dt is not None
    # naive 时间戳保持 naive，小时字段可精确断言
    naive = _parse_ts("2026-08-19T13:00:00")
    assert naive.hour == 13
    assert _parse_ts("") is None
    assert _parse_ts("not-a-date") is None


def test_parse_lines_peak_cost():
    _temp_stats_path()
    try:
        t = StatsTracker()
        line = json.dumps({
            "type": "assistant",
            "timestamp": "2026-08-19T10:00:00",  # 高峰（本地 10 点）
            "message": {
                "content": [{"type": "text", "text": "hello"}],
                "usage": {
                    "input_tokens": 1000,
                    "cache_read_input_tokens": 3000,
                    "output_tokens": 500,
                },
            },
        })
        delta = t._parse_lines(line)
        assert delta["input_tokens"] == 1000
        assert delta["cache_read"] == 3000
        assert delta["output_tokens"] == 500
        expected_peak = (3000 * 0.10 + 1000 * 3.00 + 500 * 9.00) / 1e6
        assert abs(delta["peak_cost"] - expected_peak) < 1e-12
        assert delta["off_peak_cost"] == 0.0
    finally:
        _restore_stats_path()


def test_parse_lines_offpeak_cost():
    _temp_stats_path()
    try:
        t = StatsTracker()
        line = json.dumps({
            "type": "assistant",
            "timestamp": "2026-08-19T13:00:00",  # 空闲（本地 13 点）
            "message": {
                "content": [],
                "usage": {
                    "input_tokens": 2000,
                    "cache_read_input_tokens": 8000,
                    "output_tokens": 100,
                },
            },
        })
        delta = t._parse_lines(line)
        expected_off = (8000 * 0.05 + 2000 * 1.50 + 100 * 4.50) / 1e6
        assert abs(delta["off_peak_cost"] - expected_off) < 1e-12
        assert delta["peak_cost"] == 0.0
        expected_legacy = (8000 * 0.02 + 2000 * 1.00 + 100 * 2.00) / 1e6
        assert abs(delta["legacy_cost"] - expected_legacy) < 1e-12
    finally:
        _restore_stats_path()


def test_snapshot_efficiency():
    _temp_stats_path()
    try:
        t = StatsTracker()
        line = json.dumps({
            "type": "assistant",
            "timestamp": "2026-08-19T13:00:00",
            "message": {
                "content": [],
                "usage": {
                    "input_tokens": 2000,
                    "cache_read_input_tokens": 8000,
                    "output_tokens": 100,
                },
            },
        })
        t._apply_delta(t._parse_lines(line))
        snap = t.snapshot()
        assert snap["efficiency"] == 80          # 8000 / 10000
        assert snap["input_tokens"] == 2000
        assert snap["cache_read"] == 8000
        assert snap["cost"] == snap["peak_cost"] + snap["off_peak_cost"]
        # 饱腹度 = last_billed_input / context_window（10000 / 1M = 1%）
        assert snap["satiety"]["percent"] == 1
        assert snap["satiety"]["used_tokens"] == 10000
        assert snap["food"]["chat_tokens"] == 0
    finally:
        _restore_stats_path()


def test_incremental_dedup_via_offset():
    _temp_stats_path()
    try:
        t = StatsTracker()
        tmp = os.path.dirname(stats_mod.STATS_PATH)
        path = os.path.join(tmp, "transcript.jsonl")
        line = json.dumps({
            "type": "assistant",
            "timestamp": "2026-08-19T13:00:00",
            "message": {
                "content": [],
                "usage": {"input_tokens": 100, "cache_read_input_tokens": 0, "output_tokens": 10},
            },
        }) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(line)

        t._ingest(path)
        first = t.snapshot()
        t._ingest(path)  # 无新增，offset 已到末尾
        second = t.snapshot()
        assert second["input_tokens"] == first["input_tokens"]
        assert second["input_tokens"] == 100
    finally:
        _restore_stats_path()
