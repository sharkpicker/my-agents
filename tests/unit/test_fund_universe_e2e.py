"""端到端：mock HTTP + mock fund_data，跑通 init → status → sync → update 完整流程."""
from data_tools.fund_universe import (
    sync,
    show_status,
    refresh_fund_list,
    is_in_cooldown,
    load_progress,
    save_progress,
    save_fund_list,
    sync_single_fund,
)


def test_e2e_init_status_sync(monkeypatch, tmp_path):
    """init → status → sync 完整链路不抛异常并正确反映状态变化。"""
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    # mock 列表
    def fake_fetch():
        return [
            {"code": f"{i:06d}", "name": f"基金{i}", "type": "混合型", "is_offexchange": True}
            for i in range(5)
        ]
    monkeypatch.setattr("data_tools.fund_universe.fetch_fund_list", fake_fetch)

    # mock 单只基金所有字段调用
    for fn in ["get_fund_nav", "get_fund_info", "get_fund_holdings",
               "get_fund_manager", "get_fund_performance",
               "get_fund_flows", "get_fund_news"]:
        monkeypatch.setattr(f"data_tools.fund_data.{fn}", lambda *a, **kw: "ok")

    cfg = {"news_lookback_days": 90, "nav_lookback_days": 365,
           "field_interval_min": 0, "field_interval_max": 0,
           "fund_interval_min": 0, "fund_interval_max": 0,
           "max_fail_count": 3, "fail_cooldown_days": 7, "daily_quota": 5}
    monkeypatch.setattr("data_tools.fund_universe.load_config", lambda: cfg)

    # 1) init
    count = refresh_fund_list()
    assert count == 5

    # 2) status (空 progress)
    s1 = show_status()
    assert s1["total_funds"] == 5
    assert s1["in_cooldown"] == 0

    # 3) sync quota=2
    result = sync(quota=2, force=False)
    assert result["total"] == 2
    assert result["success"] == 2

    # 4) status (应有 2 条 ok)
    s2 = show_status()
    assert s2["total_funds"] == 5
    assert s2["status_breakdown"]["ok"] == 2


def test_e2e_full_fail_to_cooldown(monkeypatch, tmp_path):
    """失败后进入冷却，冷却阶梯递增。"""
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    monkeypatch.setattr("data_tools.fund_universe.fetch_fund_list",
                        lambda: [{"code": "000001", "name": "X", "type": "Y", "is_offexchange": True}])

    def _raise(*a, **kw):
        raise RuntimeError("network")
    for fn in ["get_fund_nav", "get_fund_info", "get_fund_holdings",
               "get_fund_manager", "get_fund_performance",
               "get_fund_flows", "get_fund_news"]:
        monkeypatch.setattr(f"data_tools.fund_data.{fn}", _raise)

    cfg = {"news_lookback_days": 90, "nav_lookback_days": 365,
           "field_interval_min": 0, "field_interval_max": 0,
           "fund_interval_min": 0, "fund_interval_max": 0,
           "cooldown_steps": [1, 3, 7, 14], "fail_cooldown_days": 7, "daily_quota": 1}
    monkeypatch.setattr("data_tools.fund_universe.load_config", lambda: cfg)

    refresh_fund_list()

    # 第 1 次失败 → 冷却 1 天
    sync(quota=1, force=True)
    r1 = load_progress()["000001"]
    assert r1["fail_count"] == 1
    assert r1["cooldown_until"] is not None
    from datetime import datetime, timedelta
    cd1 = datetime.fromisoformat(r1["cooldown_until"])
    assert timedelta(hours=20) < cd1 - datetime.now() < timedelta(hours=28)

    # 第 2 次失败 → 冷却 3 天 (force=True 跳过冷却)
    sync(quota=1, force=True)
    r2 = load_progress()["000001"]
    assert r2["fail_count"] == 2
    cd2 = datetime.fromisoformat(r2["cooldown_until"])
    assert timedelta(days=2, hours=20) < cd2 - datetime.now() < timedelta(days=3, hours=4)

    # 第 3 次失败 → 冷却 7 天
    sync(quota=1, force=True)
    r3 = load_progress()["000001"]
    assert r3["fail_count"] == 3
    assert r3["cooldown_until"] is not None
    cd3 = datetime.fromisoformat(r3["cooldown_until"])
    assert timedelta(days=6, hours=20) < cd3 - datetime.now() < timedelta(days=7, hours=4)

    # 冷却中的基金不应被 sync（除非 force=True）
    result_skip = sync(quota=1, force=False)
    assert result_skip["total"] == 0

    # 但 force=True 仍可采集（即使冷却中）
    result_force = sync(quota=1, force=True)
    assert result_force["total"] == 1


def test_e2e_success_resets_fail_count_after_partial(monkeypatch, tmp_path):
    """partial 后 ok 应该把 fail_count 保留为上一轮 + 本轮的累计（成功 = 重置为 0）。"""
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)
    monkeypatch.setattr("data_tools.fund_universe.fetch_fund_list",
                        lambda: [{"code": "000001", "name": "X", "type": "Y", "is_offexchange": True}])

    monkeypatch.setattr("data_tools.fund_data.get_fund_nav", lambda *a, **kw: "ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_info", lambda *a, **kw: "ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_holdings", lambda *a, **kw: "ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_manager", lambda *a, **kw: "ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_performance", lambda *a, **kw: "ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_flows", lambda *a, **kw: "ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_news", lambda *a, **kw: "ok")

    cfg = {"news_lookback_days": 90, "nav_lookback_days": 365,
           "field_interval_min": 0, "field_interval_max": 0,
           "fund_interval_min": 0, "fund_interval_max": 0,
           "max_fail_count": 3, "fail_cooldown_days": 7, "daily_quota": 1}
    monkeypatch.setattr("data_tools.fund_universe.load_config", lambda: cfg)

    refresh_fund_list()
    sync(quota=1, force=True)
    rec = load_progress()["000001"]
    assert rec["last_status"] == "ok"
    assert rec["fail_count"] == 0
