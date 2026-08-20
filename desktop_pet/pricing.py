"""DeepSeek 峰谷定价常量 + 高峰时段判断（口径照搬 dsh-blubby event-projection）。"""

import datetime


# 当前模型 deepseek-v4-flash（元 / 百万 tokens）
PRICE_CACHE_HIT_PEAK = 0.10
PRICE_CACHE_HIT_OFF = 0.05
PRICE_UNCACHED_PEAK = 3.00
PRICE_UNCACHED_OFF = 1.50
PRICE_OUTPUT_PEAK = 9.00
PRICE_OUTPUT_OFF = 4.50

# 涨价前（2026-08-16 及之前）一口价（元 / 百万 tokens）
PRICE_CACHE_HIT_LEGACY = 0.02
PRICE_UNCACHED_LEGACY = 1.00
PRICE_OUTPUT_LEGACY = 2.00

# 上下文窗口兜底（deepseek-v4-flash 官方 1M；config 可覆盖）
DEFAULT_CONTEXT_WINDOW = 1_000_000

# 饱腹度超过此百分比触发「好撑」特效
SATIETY_BURP_PERCENT = 85


def is_peak_hour(dt=None):
    """高峰时段：本地时间 9:00–12:00、14:00–18:00（官方公告口径）。

    dt 为带时区的 datetime 时按其自身时区的小时判断；为 naive 时按本地时间。
    缺省用当前本地时间。
    """
    if dt is None:
        dt = datetime.datetime.now()
    h = dt.hour
    return (9 <= h < 12) or (14 <= h < 18)
