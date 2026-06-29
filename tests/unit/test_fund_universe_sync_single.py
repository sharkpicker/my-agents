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
