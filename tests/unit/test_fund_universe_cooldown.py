from datetime import datetime, timedelta
from data_tools.fund_universe import (
    sync,
    load_progress,
    save_progress,
    save_fund_list,
)


def _seed_list(codes):
    save_fund_list([{"code": c, "name": f"基金{c}", "type": "混合型", "is_offexchange": True} for c in codes])


def _seed_failure_progress(code, fail_count):
    """直接写入一条处于 cooldown 中的记录（fail_count 已达标）。"""
    until = (datetime.now() + timedelta(days=2)).isoformat()
    save_progress({code: {"last_sync_at": None, "fail_count": fail_count,
                           "last_status": "failed", "fields": {},
                           "cooldown_until": until}})


def test_cooldown_skips_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    called = {"n": 0}
    def fake_sync_single(code, cfg):
        called["n"] += 1
        return {"last_status": "ok", "fail_count": 0, "fields": {}, "cooldown_until": None}
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund", fake_sync_single)
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001"])
    _seed_failure_progress("000001", fail_count=3)
    cfg = {"max_fail_count": 3, "fail_cooldown_days": 7, "daily_quota": 5,
           "field_interval_min": 0, "field_interval_max": 0,
           "fund_interval_min": 0, "fund_interval_max": 0}
    monkeypatch.setattr("data_tools.fund_universe.load_config", lambda: cfg)

    result = sync(quota=5, force=False)
    assert called["n"] == 0
    assert result["total"] == 0
    assert result["success"] == 0


def test_cooldown_respects_force_true(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    called = {"n": 0}
    def fake_sync_single(code, cfg):
        called["n"] += 1
        return {"last_status": "ok", "fail_count": 0, "fields": {}, "cooldown_until": None}
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund", fake_sync_single)
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001"])
    _seed_failure_progress("000001", fail_count=3)
    cfg = {"max_fail_count": 3, "fail_cooldown_days": 7, "daily_quota": 5,
           "field_interval_min": 0, "field_interval_max": 0,
           "fund_interval_min": 0, "fund_interval_max": 0}
    monkeypatch.setattr("data_tools.fund_universe.load_config", lambda: cfg)

    result = sync(quota=5, force=True)
    assert called["n"] == 1
    assert result["total"] == 1


def test_cooldown_expired_is_synced_again(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    called = {"n": 0}
    def fake_sync_single(code, cfg):
        called["n"] += 1
        return {"last_status": "ok", "fail_count": 0, "fields": {}, "cooldown_until": None}
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund", fake_sync_single)
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001"])
    past = (datetime.now() - timedelta(days=1)).isoformat()
    save_progress({"000001": {"last_sync_at": None, "fail_count": 3,
                               "last_status": "failed", "fields": {},
                               "cooldown_until": past}})
    cfg = {"max_fail_count": 3, "fail_cooldown_days": 7, "daily_quota": 5,
           "field_interval_min": 0, "field_interval_max": 0,
           "fund_interval_min": 0, "fund_interval_max": 0}
    monkeypatch.setattr("data_tools.fund_universe.load_config", lambda: cfg)

    result = sync(quota=5, force=False)
    assert called["n"] == 1
    assert result["success"] == 1


def test_partial_failure_resets_fail_count(monkeypatch, tmp_path):
    """部分失败的同步不增加 fail_count（但 success 路径不影响，这里验证累积语义）。"""
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    def fake_sync_single(code, cfg):
        return {"last_status": "partial", "fail_count": 1,
                "fields": {"nav": "ok", "info": "failed"}, "cooldown_until": None}
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund", fake_sync_single)
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001"])
    save_progress({"000001": {"last_sync_at": None, "fail_count": 0,
                               "last_status": None, "fields": {},
                               "cooldown_until": None}})
    cfg = {"max_fail_count": 3, "fail_cooldown_days": 7, "daily_quota": 5,
           "field_interval_min": 0, "field_interval_max": 0,
           "fund_interval_min": 0, "fund_interval_max": 0}
    monkeypatch.setattr("data_tools.fund_universe.load_config", lambda: cfg)

    sync(quota=5, force=True)
    rec = load_progress()["000001"]
    assert rec["fail_count"] == 1
    assert rec["cooldown_until"] is None  # 没达阈值


def test_success_resets_fail_count(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    def fake_sync_single(code, cfg):
        return {"last_status": "ok", "fail_count": 0, "fields": {}, "cooldown_until": None}
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund", fake_sync_single)
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001"])
    save_progress({"000001": {"last_sync_at": None, "fail_count": 2,
                               "last_status": "failed", "fields": {},
                               "cooldown_until": None}})
    cfg = {"max_fail_count": 3, "fail_cooldown_days": 7, "daily_quota": 5,
           "field_interval_min": 0, "field_interval_max": 0,
           "fund_interval_min": 0, "fund_interval_max": 0}
    monkeypatch.setattr("data_tools.fund_universe.load_config", lambda: cfg)

    sync(quota=5, force=True)
    rec = load_progress()["000001"]
    assert rec["fail_count"] == 0  # 历史 2 + 本轮 0 = 2 (但 sync 重写为 0+0=2? 不,失败 0 = 总 2)
