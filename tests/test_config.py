from desktop_pet.config import normalize_app_config, _deep_merge, _clamp_int, DEFAULT_APP_CONFIG


def test_normalize_default():
    config = normalize_app_config({})
    assert config["sound_enabled"] is True
    assert config["window"]["width"] == 300
    assert config["window"]["height"] == 240
    assert config["step_done_timeout_ms"] == 5000


def test_normalize_window_clamp():
    config = normalize_app_config({"window": {"width": 100, "height": 50}})
    assert config["window"]["width"] == 220
    assert config["window"]["height"] == 180

    config = normalize_app_config({"window": {"width": 9999, "height": 9999}})
    assert config["window"]["width"] == 600
    assert config["window"]["height"] == 500


def test_normalize_step_done_timeout_clamp():
    config = normalize_app_config({"step_done_timeout_ms": 0})
    assert config["step_done_timeout_ms"] == 1000

    config = normalize_app_config({"step_done_timeout_ms": 999999})
    assert config["step_done_timeout_ms"] == 60000


def test_deep_merge_nested():
    defaults = {"a": {"b": 1, "c": 2}, "d": 3}
    override = {"a": {"b": 10}}
    result = _deep_merge(defaults, override)
    assert result == {"a": {"b": 10, "c": 2}, "d": 3}


def test_deep_merge_override():
    defaults = {"a": 1, "b": 2}
    override = {"b": 20, "c": 30}
    result = _deep_merge(defaults, override)
    assert result == {"a": 1, "b": 20, "c": 30}


def test_deep_merge_non_dict_override():
    result = _deep_merge({"a": 1}, "not a dict")
    assert result == {"a": 1}


def test_clamp_int_normal():
    assert _clamp_int(5, 0, 1, 10) == 5


def test_clamp_int_below_min():
    assert _clamp_int(-1, 0, 0, 10) == 0


def test_clamp_int_above_max():
    assert _clamp_int(999, 0, 0, 10) == 10


def test_clamp_int_invalid():
    assert _clamp_int(None, 42, 0, 100) == 42
    assert _clamp_int("abc", 42, 0, 100) == 42


def test_normalize_tired_timeout():
    config = normalize_app_config({"thinking_tired_timeout_ms": 5000})
    assert config["thinking_tired_timeout_ms"] == 10000

    config = normalize_app_config({"thinking_tired_timeout_ms": 9999999})
    assert config["thinking_tired_timeout_ms"] == 600000


def test_normalize_sleeping_timeout():
    config = normalize_app_config({"idle_sleeping_timeout_ms": 1000})
    assert config["idle_sleeping_timeout_ms"] == 60000

    config = normalize_app_config({"idle_sleeping_timeout_ms": 99999999})
    assert config["idle_sleeping_timeout_ms"] == 1800000


def test_no_working_config_keys():
    config = normalize_app_config({})
    assert "working_timeout_ms" not in config
    assert "working_tired_timeout_ms" not in config
    assert "thinking_timeout_ms" not in config


def test_reading_in_config():
    config = normalize_app_config({})
    assert "reading" in config["state_durations"]
    assert config["state_durations"]["reading"] == 2000
