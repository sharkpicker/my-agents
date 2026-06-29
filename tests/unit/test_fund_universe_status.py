import json
from datetime import datetime, timedelta
from data_tools.fund_universe import (
    show_status,
    load_progress,
    save_progress,
    save_fund_list,
    load_fund_list,
)


def _seed_list(codes):
    save_fund_list([{"code": c, "name": f"基金{c}", "type": "混合型", "is_offexchange": True} for c in codes])


def test_status_returns_dict_with_expected_keys(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    _seed_list(["000001", "000002"])
    result = show_status()
    expected_keys = {
            "total_funds", "in_cooldown", "needs_sync",
            "last_run", "status_breakdown", "progress_size",
            "field_stats",
        }
    assert set(result.keys()) == expected_keys


def test_status_handles_missing_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    # 不要 seed 任何文件
    result = show_status()
    assert result["total_funds"] == 0
    assert result["in_cooldown"] == 0
    assert result["needs_sync"] == 0
    assert result["last_run"] is None
    out = capsys.readouterr().out
    assert "基金总数" in out


def test_status_counts_in_cooldown(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    _seed_list(["000001", "000002", "000003"])
    future = (datetime.now() + timedelta(days=2)).isoformat()
    save_progress({
        "000001": {"last_sync_at": None, "fail_count": 3,
                   "last_status": "failed", "fields": {}, "cooldown_until": future},
        "000002": {"last_sync_at": None, "fail_count": 0,
                   "last_status": None, "fields": {}, "cooldown_until": None},
    })
    result = show_status()
    assert result["total_funds"] == 3
    assert result["in_cooldown"] == 1
    assert result["needs_sync"] == 2  # 000002 + 000003


def test_status_status_breakdown(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    _seed_list(["000001", "000002"])
    save_progress({
        "000001": {"last_sync_at": "2026-06-27T22:00:00", "fail_count": 0,
                   "last_status": "ok", "fields": {}, "cooldown_until": None},
        "000002": {"last_sync_at": "2026-06-27T22:00:00", "fail_count": 1,
                   "last_status": "partial", "fields": {}, "cooldown_until": None},
    })
    result = show_status()
    assert result["status_breakdown"]["ok"] == 1
    assert result["status_breakdown"]["partial"] == 1


def test_status_last_run_most_recent(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    _seed_list(["000001", "000002"])
    save_progress({
        "000001": {"last_sync_at": "2026-06-26T22:00:00", "fail_count": 0,
                   "last_status": "ok", "fields": {}, "cooldown_until": None},
        "000002": {"last_sync_at": "2026-06-27T22:00:00", "fail_count": 0,
                   "last_status": "ok", "fields": {}, "cooldown_until": None},
    })
    result = show_status()
    assert result["last_run"] == "2026-06-27T22:00:00"


def test_status_prints_summary(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    _seed_list(["000001"])
    show_status()
    out = capsys.readouterr().out
    assert "1" in out  # 至少一个数字
    assert "基金" in out or "Fund" in out


def test_status_field_stats(tmp_path, monkeypatch):
    """show_status 返回字段级统计 field_stats。"""
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    _seed_list(["000001", "000002", "000003"])
    save_progress({
        "000001": {"last_sync_at": "2026-06-27T22:00:00", "fail_count": 0,
                   "last_status": "ok", "cooldown_until": None,
                   "fields": {"nav": "ok", "info": "ok", "holdings": "ok"}},
        "000002": {"last_sync_at": "2026-06-27T22:00:00", "fail_count": 1,
                   "last_status": "partial", "cooldown_until": None,
                   "fields": {"nav": "ok", "info": "failed", "holdings": "ok"}},
    })
    result = show_status()
    assert "field_stats" in result
    fs = result["field_stats"]
    assert fs["nav"]["ok"] == 2
    assert fs["info"]["ok"] == 1
    assert fs["info"]["failed"] == 1
    assert fs["holdings"]["ok"] == 2
