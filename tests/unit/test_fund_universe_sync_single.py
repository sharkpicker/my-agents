from data_tools.fund_universe import sync_single_fund


def test_sync_single_fund_all_ok(monkeypatch):
    monkeypatch.setattr("data_tools.fund_data.get_fund_nav", lambda code, start, end: "nav_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_info", lambda code: "info_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_holdings", lambda code: "holdings_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_manager", lambda code: "manager_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_performance", lambda code: "performance_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_flows", lambda code: "flows_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_news", lambda code, start, end: "news_ok")
    # 防止真实 sleep 拖慢测试
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    cfg = {"news_lookback_days": 90, "nav_lookback_days": 365,
           "field_interval_min": 0.0, "field_interval_max": 0.0}
    result = sync_single_fund("000001", cfg)
    assert result["last_status"] == "ok"
    assert result["fail_count"] == 0
    assert result["fields"] == {
        "nav": "ok", "info": "ok", "holdings": "ok", "manager": "ok",
        "performance": "ok", "flows": "ok", "news": "ok",
    }


def test_sync_single_fund_one_field_failed_results_in_partial(monkeypatch):
    monkeypatch.setattr("data_tools.fund_data.get_fund_nav", lambda code, start, end: "nav_ok")
    def _raise(code, start, end):
        raise RuntimeError("network error")
    monkeypatch.setattr("data_tools.fund_data.get_fund_info", _raise)
    monkeypatch.setattr("data_tools.fund_data.get_fund_holdings", lambda code: "holdings_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_manager", lambda code: "manager_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_performance", lambda code: "performance_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_flows", lambda code: "flows_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_news", lambda code, start, end: "news_ok")
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    cfg = {"news_lookback_days": 90, "nav_lookback_days": 365,
           "field_interval_min": 0.0, "field_interval_max": 0.0}
    result = sync_single_fund("000001", cfg)
    assert result["last_status"] == "partial"
    assert result["fields"]["info"] == "failed"
    assert result["fields"]["nav"] == "ok"


def test_sync_single_fund_all_failed(monkeypatch):
    def _raise(*a, **kw):
        raise RuntimeError("network error")
    for fn in ["get_fund_nav", "get_fund_info", "get_fund_holdings",
               "get_fund_manager", "get_fund_performance",
               "get_fund_flows", "get_fund_news"]:
        monkeypatch.setattr(f"data_tools.fund_data.{fn}", _raise)
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    cfg = {"news_lookback_days": 90, "nav_lookback_days": 365,
           "field_interval_min": 0.0, "field_interval_max": 0.0}
    result = sync_single_fund("000001", cfg)
    assert result["last_status"] == "failed"
    assert all(v == "failed" for v in result["fields"].values())
    assert result["fail_count"] == 1


def test_sync_single_fund_returns_progress_record(monkeypatch):
    monkeypatch.setattr("data_tools.fund_data.get_fund_nav", lambda code, start, end: "")
    monkeypatch.setattr("data_tools.fund_data.get_fund_info", lambda code: "")
    monkeypatch.setattr("data_tools.fund_data.get_fund_holdings", lambda code: "")
    monkeypatch.setattr("data_tools.fund_data.get_fund_manager", lambda code: "")
    monkeypatch.setattr("data_tools.fund_data.get_fund_performance", lambda code: "")
    monkeypatch.setattr("data_tools.fund_data.get_fund_flows", lambda code: "")
    monkeypatch.setattr("data_tools.fund_data.get_fund_news", lambda code, start, end: "")
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    cfg = {"news_lookback_days": 90, "nav_lookback_days": 365,
           "field_interval_min": 0.0, "field_interval_max": 0.0}
    result = sync_single_fund("000001", cfg)
    assert set(result.keys()) == {"last_status", "fail_count", "fields", "cooldown_until"}
    assert result["cooldown_until"] is None


def test_sync_single_fund_skips_ok_fields_when_enabled(monkeypatch):
    """skip_ok_fields=True 时跳过已有 ok 状态的字段。"""
    call_count = {"nav": 0, "info": 0}
    def fake_nav(code, start, end):
        call_count["nav"] += 1
        return "nav_ok"
    def fake_info(code):
        call_count["info"] += 1
        return "info_ok"
    monkeypatch.setattr("data_tools.fund_data.get_fund_nav", fake_nav)
    monkeypatch.setattr("data_tools.fund_data.get_fund_info", fake_info)
    monkeypatch.setattr("data_tools.fund_data.get_fund_holdings", lambda code: "holdings_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_manager", lambda code: "manager_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_performance", lambda code: "performance_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_flows", lambda code: "flows_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_news", lambda code, start, end: "news_ok")
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    cfg = {"news_lookback_days": 90, "nav_lookback_days": 365,
           "field_interval_min": 0.0, "field_interval_max": 0.0,
           "skip_ok_fields": True}
    existing = {"nav": "ok", "info": "failed"}
    result = sync_single_fund("000001", cfg, existing_fields=existing)
    assert result["last_status"] == "ok"
    assert call_count["nav"] == 0
    assert call_count["info"] == 1
    assert result["fields"]["nav"] == "ok"
    assert result["fields"]["info"] == "ok"


def test_sync_single_fund_force_overrides_skip(monkeypatch):
    """force=True 时即使 skip_ok_fields=True 也强制刷新所有字段。"""
    call_count = {"nav": 0}
    def fake_nav(code, start, end):
        call_count["nav"] += 1
        return "nav_ok"
    monkeypatch.setattr("data_tools.fund_data.get_fund_nav", fake_nav)
    monkeypatch.setattr("data_tools.fund_data.get_fund_info", lambda code: "info_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_holdings", lambda code: "holdings_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_manager", lambda code: "manager_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_performance", lambda code: "performance_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_flows", lambda code: "flows_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_news", lambda code, start, end: "news_ok")
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    cfg = {"news_lookback_days": 90, "nav_lookback_days": 365,
           "field_interval_min": 0.0, "field_interval_max": 0.0,
           "skip_ok_fields": True}
    existing = {"nav": "ok"}
    result = sync_single_fund("000001", cfg, existing_fields=existing, force=True)
    assert result["last_status"] == "ok"
    assert call_count["nav"] == 1


def test_cooldown_days_step_calculation():
    """_cooldown_days 按阶梯计算冷却天数。"""
    from data_tools.fund_universe import _cooldown_days
    cfg = {"cooldown_steps": [1, 3, 7, 14]}
    assert _cooldown_days(0, cfg) == 0
    assert _cooldown_days(1, cfg) == 1
    assert _cooldown_days(2, cfg) == 3
    assert _cooldown_days(3, cfg) == 7
    assert _cooldown_days(4, cfg) == 14
    assert _cooldown_days(5, cfg) == 14
