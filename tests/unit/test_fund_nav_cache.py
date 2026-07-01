"""净值缓存状态校验函数单元测试。"""
from __future__ import annotations

import csv
import os
import time
from pathlib import Path

import pytest

from data_tools import stock_data
from data_tools.fund_data import (
    _CACHE_MAX_AGE_HOURS,
    get_unit_nav_with_cache_status,
)


@pytest.fixture
def fake_fund_dir(tmp_path: Path, monkeypatch) -> Path:
    code = "011095"
    fund_dir = tmp_path / code
    fund_dir.mkdir()

    csv_path = fund_dir / "nav_2026-07-01_2026-07-01.csv"
    csv_path.write_text(
        "净值日期,单位净值,累计净值,日增长率\n"
        "2026-07-01,1.2345,1.3456,0.32%\n"
        "2026-06-30,1.2305,1.3416,0.50%\n",
        encoding="utf-8",
    )

    (fund_dir / "fund_info_2026-07-01.txt").write_text(
        "基金代码 011095\n单位净值 1.2345\n累计净值 1.3456\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(stock_data, "get_fund_data_dir", lambda c: fund_dir)
    monkeypatch.setattr(
        "data_tools.fund_data.get_fund_data_dir", lambda c: fund_dir
    )
    return fund_dir


def test_fresh_when_within_threshold(fake_fund_dir):
    unit_nav, daily_return, status = get_unit_nav_with_cache_status(
        "011095", threshold_hours=4,
    )
    assert status == "fresh"
    assert unit_nav == pytest.approx(1.2345)
    assert daily_return == pytest.approx(0.0032, abs=1e-3)


def test_stale_when_beyond_threshold(fake_fund_dir):
    csv_files = list(fake_fund_dir.glob("nav_*.csv"))
    assert csv_files, "fixture must have nav_*.csv"
    csv_path = csv_files[0]
    five_hours_ago = time.time() - 5 * 3600
    os.utime(csv_path, (five_hours_ago, five_hours_ago))

    unit_nav, daily_return, status = get_unit_nav_with_cache_status(
        "011095", threshold_hours=4,
    )
    assert status == "stale"
    assert unit_nav == pytest.approx(1.2345)


def test_missing_when_no_file(tmp_path, monkeypatch):
    fund_dir = tmp_path / "999999"
    fund_dir.mkdir()
    monkeypatch.setattr(stock_data, "get_fund_data_dir", lambda c: fund_dir)
    monkeypatch.setattr(
        "data_tools.fund_data.get_fund_data_dir", lambda c: fund_dir
    )

    unit_nav, daily_return, status = get_unit_nav_with_cache_status(
        "999999", threshold_hours=4,
    )
    assert status == "missing"
    assert unit_nav is None
    assert daily_return is None


def test_default_threshold_uses_nav_cache(fake_fund_dir):
    unit_nav, daily_return, status = get_unit_nav_with_cache_status("011095")
    assert status == "fresh"
    assert _CACHE_MAX_AGE_HOURS["nav"] == 4


def test_daily_return_parses_pct_string(fake_fund_dir):
    _, daily_return, _ = get_unit_nav_with_cache_status("011095")
    assert isinstance(daily_return, float)
    assert 0.003 <= daily_return <= 0.004
