import datetime

from desktop_pet import pricing


def test_is_peak_hour_morning():
    assert pricing.is_peak_hour(datetime.datetime(2026, 8, 19, 9, 0)) is True
    assert pricing.is_peak_hour(datetime.datetime(2026, 8, 19, 11, 59)) is True
    assert pricing.is_peak_hour(datetime.datetime(2026, 8, 19, 12, 0)) is False


def test_is_peak_hour_afternoon():
    assert pricing.is_peak_hour(datetime.datetime(2026, 8, 19, 14, 0)) is True
    assert pricing.is_peak_hour(datetime.datetime(2026, 8, 19, 17, 59)) is True
    assert pricing.is_peak_hour(datetime.datetime(2026, 8, 19, 18, 0)) is False


def test_is_peak_hour_offpeak():
    assert pricing.is_peak_hour(datetime.datetime(2026, 8, 19, 0, 0)) is False
    assert pricing.is_peak_hour(datetime.datetime(2026, 8, 19, 13, 0)) is False
    assert pricing.is_peak_hour(datetime.datetime(2026, 8, 19, 20, 0)) is False


def test_is_peak_hour_default_now():
    # 无参数时不抛异常，返回布尔
    assert pricing.is_peak_hour() in (True, False)


def test_pricing_constants_peak_off_half():
    assert pricing.PRICE_CACHE_HIT_OFF == pricing.PRICE_CACHE_HIT_PEAK / 2
    assert pricing.PRICE_UNCACHED_OFF == pricing.PRICE_UNCACHED_PEAK / 2
    assert pricing.PRICE_OUTPUT_OFF == pricing.PRICE_OUTPUT_PEAK / 2
