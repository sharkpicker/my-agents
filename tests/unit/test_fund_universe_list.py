from data_tools.fund_universe import (
    is_offexchange_fund,
    fetch_fund_list_from_primary,
    fetch_fund_list,
    save_fund_list,
    load_fund_list,
    diff_fund_list,
)


def test_is_offexchange_fund_open_fund():
    assert is_offexchange_fund({"code": "000001", "name": "华夏成长混合", "type": "混合型-偏股"}) is True


def test_is_offexchange_fund_sh_etf():
    # 51xxxx 是上交所 ETF
    assert is_offexchange_fund({"code": "510300", "name": "华泰柏瑞沪深300ETF", "type": "指数型-股票"}) is False


def test_is_offexchange_fund_sz_etf():
    # 15xxxx 是深交所 ETF
    assert is_offexchange_fund({"code": "159915", "name": "易方达创业板ETF", "type": "指数型-股票"}) is False


def test_is_offexchange_fund_sz_lof():
    # 16xxxx 是深交所 LOF
    assert is_offexchange_fund({"code": "160219", "name": "国泰医药健康LOF", "type": "混合型"}) is False


def test_is_offexchange_fund_closed_end():
    # 18xxxx 是封闭式基金
    assert is_offexchange_fund({"code": "184801", "name": "鹏华前海万科REITs", "type": "封闭式"}) is False


def test_is_offexchange_fund_periodic_open_kept():
    # 定期开放属于场外开放式，不应被排除
    assert is_offexchange_fund({"code": "005753", "name": "某基金6个月定开债", "type": "债券型"}) is True


def test_fetch_fund_list_from_primary_parses_js_array(monkeypatch):
    """主端点返回 JS 数组格式时正确解析。"""
    sample = (
        'var db={"chars":["基金代码","基金简称"],'
        '"datas":[["000001","华夏成长"],'
        '["510300","沪深300ETF"],'
        '["005753","6个月定开债"]]};'
    )
    class FakeResp:
        status_code = 200
        text = sample
        def json(self): return {}
    def fake_get(url, params=None, headers=None, timeout=15):
        return FakeResp()
    monkeypatch.setattr("data_tools.fund_universe._fund_http_get", fake_get)
    rows = fetch_fund_list_from_primary()
    assert len(rows) == 3
    assert rows[0]["code"] == "000001"
    assert rows[0]["name"] == "华夏成长"


def test_fetch_fund_list_uses_fallback_when_primary_too_few(monkeypatch):
    """主端点返回 < 5000 条时降级到备用端点。"""
    class FakeRespPrimary:
        status_code = 200
        text = 'var db={"chars":["代码","名称"],"datas":[["000001","X"]]};'
        def json(self): return {}
    class FakeRespFallback:
        status_code = 200
        text = ""
        def json(self):
            return {"result": {"data": [
                {"FCODE": "000001", "SHORTNAME": "华夏成长", "FTYPE": "混合型"},
                {"FCODE": "005753", "SHORTNAME": "定开债", "FTYPE": "债券型"},
            ]}}
    calls = {"primary": 0, "fallback": 0}
    def fake_get(url, params=None, headers=None, timeout=15):
        if "Fund_JJJZ_Data" in url:
            calls["primary"] += 1
            return FakeRespPrimary()
        else:
            calls["fallback"] += 1
            return FakeRespFallback()
    monkeypatch.setattr("data_tools.fund_universe._fund_http_get", fake_get)
    rows = fetch_fund_list()
    assert calls["primary"] == 1
    assert calls["fallback"] == 1
    assert len(rows) >= 2
    assert all("code" in r and "name" in r for r in rows)


def test_fetch_fund_list_returns_offexchange_only(monkeypatch):
    """fetch_fund_list 只返回 is_offexchange=True 的基金。"""
    class FakeResp:
        status_code = 200
        text = ""
        def json(self):
            return {"result": {"data": [
                {"FCODE": "000001", "SHORTNAME": "华夏成长", "FTYPE": "混合型"},
                {"FCODE": "510300", "SHORTNAME": "沪深300ETF", "FTYPE": "指数型"},
                {"FCODE": "184801", "SHORTNAME": "鹏华前海", "FTYPE": "封闭式"},
                {"FCODE": "005753", "SHORTNAME": "定开债", "FTYPE": "债券型"},
            ]}}
    monkeypatch.setattr("data_tools.fund_universe._fund_http_get", lambda *a, **kw: FakeResp())
    rows = fetch_fund_list()
    codes = [r["code"] for r in rows]
    assert "000001" in codes
    assert "005753" in codes
    assert "510300" not in codes
    assert "184801" not in codes


def test_save_and_load_fund_list_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    funds = [{"code": "000001", "name": "华夏成长", "type": "混合型", "is_offexchange": True}]
    save_fund_list(funds)
    loaded = load_fund_list()
    assert loaded == funds


def test_diff_fund_list_returns_added_and_removed():
    old = [{"code": "000001"}, {"code": "005753"}]
    new = [{"code": "000001"}, {"code": "519677"}]
    diff = diff_fund_list(old, new)
    assert diff["added"] == ["519677"]
    assert diff["removed"] == ["005753"]
    assert diff["kept"] == ["000001"]
