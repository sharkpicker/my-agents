from pathlib import Path
from data_tools.fund_universe import (
    get_meta_dir,
    get_config_path,
    get_fund_list_path,
    get_progress_path,
    load_config,
    save_config,
    DEFAULT_CONFIG,
)


def test_meta_dir_is_under_funds_data_dir():
    p = Path(get_meta_dir())
    assert p.name == "_meta"
    assert "funds" in p.parts


def test_config_path_under_meta():
    p = Path(get_config_path())
    assert p.parent.name == "_meta"
    assert p.name == "universe_config.json"


def test_fund_list_path_under_meta():
    p = Path(get_fund_list_path())
    assert p.parent.name == "_meta"
    assert p.name == "fund_list.json"


def test_progress_path_under_meta():
    p = Path(get_progress_path())
    assert p.parent.name == "_meta"
    assert p.name == "universe_progress.json"


def test_load_config_returns_defaults_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    cfg = load_config()
    assert cfg["daily_quota"] == 200
    assert cfg["fail_cooldown_days"] == 7
    assert cfg["max_fail_count"] == 3
    assert cfg["fund_interval_min"] == 1.5
    assert cfg["fund_interval_max"] == 3.5


def test_save_and_load_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    user_cfg = {"daily_quota": 300, "max_fail_count": 5}
    save_config(user_cfg)
    loaded = load_config()
    assert loaded["daily_quota"] == 300
    assert loaded["max_fail_count"] == 5
    assert loaded["fail_cooldown_days"] == 7  # 保留未覆盖的默认值


def test_default_config_keys():
    expected_keys = {
        "daily_quota",
        "fund_interval_min",
        "fund_interval_max",
        "field_interval_min",
        "field_interval_max",
        "fail_cooldown_days",
        "max_fail_count",
        "news_lookback_days",
        "nav_lookback_days",
    }
    assert set(DEFAULT_CONFIG.keys()) == expected_keys
