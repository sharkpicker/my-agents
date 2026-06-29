from datetime import datetime, timedelta
from data_tools.fund_universe import (
    sync,
    load_progress,
    save_progress,
    save_fund_list,
    update_progress,
    is_in_cooldown,
    sync_single_fund,
)


def _seed_progress(records):
    save_progress(records)


def _seed_list(codes):
    save_fund_list([{"code": c, "name": f"基金{c}", "type": "股票型", "is_offexchange": True} for c in codes])


def test_sync_processes_in_quota(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund",
                        lambda *a, **kw: {"last_status": "ok", "fail_count": 0,
                                           "fields": {}, "cooldown_until": None})
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list([f"{i:06d}" for i in range(10)])
    result = sync(quota=3, force=True)
    assert result["total"] == 3
    assert result["success"] == 3
    assert result["failed"] == 0
    assert len(load_progress()) == 3


def test_sync_skips_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund",
                        lambda *a, **kw: {"last_status": "ok", "fail_count": 0,
                                           "fields": {}, "cooldown_until": None})
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001", "000002"])
    until = (datetime.now() + timedelta(days=2)).isoformat()
    _seed_progress({"000001": {"cooldown_until": until, "fail_count": 5,
                                "last_status": "failed", "fields": {}, "last_sync_at": None}})

    result = sync(quota=10, force=False)
    progress = load_progress()
    assert "000001" in progress  # 冷却中跳过，但旧记录保留
    assert progress["000001"]["cooldown_until"] == until  # cooldown 信息未丢
    assert "000002" in progress  # 本次选中，正常写入


def test_sync_force_overrides_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund",
                        lambda *a, **kw: {"last_status": "ok", "fail_count": 0,
                                           "fields": {}, "cooldown_until": None})
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001"])
    until = (datetime.now() + timedelta(days=2)).isoformat()
    _seed_progress({"000001": {"cooldown_until": until, "fail_count": 5,
                                "last_status": "failed", "fields": {}, "last_sync_at": None}})

    result = sync(quota=10, force=True)
    assert "000001" in load_progress()


def test_sync_priority_three_tiers(monkeypatch, tmp_path):
    """三级优先级: P0 新基金 > P1 部分失败 > P2 全部成功。"""
    picked_order = []
    def fake_sync(code, cfg, existing_fields=None, force=False):
        picked_order.append(code)
        return {"last_status": "ok", "fail_count": 0,
                "fields": {}, "cooldown_until": None}
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund", fake_sync)
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001", "000002", "000003", "000004"])
    now = datetime.now().isoformat(timespec="seconds")
    _seed_progress({
        "000001": {"last_sync_at": now, "fail_count": 0, "last_status": "ok",
                   "fields": {}, "cooldown_until": None},
        "000002": {"last_sync_at": now, "fail_count": 1, "last_status": "partial",
                   "fields": {"nav": "ok", "info": "failed"}, "cooldown_until": None},
        "000004": {"last_sync_at": now, "fail_count": 0, "last_status": "ok",
                   "fields": {}, "cooldown_until": None},
    })

    result = sync(quota=3, force=True)
    assert result["total"] == 3
    assert picked_order[0] == "000003"
    assert picked_order[1] == "000002"
    assert picked_order[2] in ("000001", "000004")


def test_sync_failure_triggers_cooldown(monkeypatch, tmp_path):
    """连续失败 max_fail_count 次的基金进入冷却期。"""
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund",
                        lambda *a, **kw: {"last_status": "failed", "fail_count": 7,
                                           "fields": {"nav": "failed"}, "cooldown_until": None})
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001"])
    # 此前已有 fail_count=2，再失败一次 → 3 次 → 触发冷却
    save_progress({
        "000001": {"last_sync_at": None, "fail_count": 2, "last_status": "failed",
                   "fields": {}, "cooldown_until": None}
    })
    cfg = {"max_fail_count": 3, "fail_cooldown_days": 7, "daily_quota": 1,
           "field_interval_min": 0, "field_interval_max": 0}
    monkeypatch.setattr("data_tools.fund_universe.load_config", lambda: cfg)

    sync(quota=1, force=True)
    rec = load_progress()["000001"]
    assert rec["cooldown_until"] is not None


def test_sync_init_if_list_missing(monkeypatch, tmp_path):
    """列表不存在时自动调用 init 逻辑。"""
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    init_called = {"n": 0}
    def fake_init():
        init_called["n"] += 1
        save_fund_list([{"code": "000001", "name": "X", "type": "Y", "is_offexchange": True}])
    monkeypatch.setattr("data_tools.fund_universe.refresh_fund_list", fake_init)
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund",
                        lambda *a, **kw: {"last_status": "ok", "fail_count": 0,
                                           "fields": {}, "cooldown_until": None})
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    sync(quota=1, force=True)
    assert init_called["n"] == 1
    assert "000001" in load_progress()


def test_sync_returns_summary(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund",
                        lambda *a, **kw: {"last_status": "ok", "fail_count": 0,
                                           "fields": {}, "cooldown_until": None})
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001"])
    result = sync(quota=1, force=True)
    assert set(result.keys()) >= {"status", "total", "success", "failed"}
    assert result["status"] in ("ok", "partial", "error")
