from data_tools.template_renderer import render


def test_render_stock_template():
    meta = {"code": "000001", "name": "平安银行", "date": "2026-06-27", "report_type": "A"}
    sections = [{"title": "技术面", "content": "看多"}]
    stock_items = [{"dimension": "技术面", "conclusion": "看多"}]
    risk_views = [{"view": "neutral", "risk_level": "Medium", "max_drawdown": 15, "suggested_position": 50}]
    html = render(template="stock", meta=meta, sections=sections, stock_items=stock_items, risk_views=risk_views)
    assert "<h1>" in html
    assert "平安银行" in html
    assert "免责声明" in html


def test_render_fund_template():
    meta = {"code": "001717", "name": "工银前沿医疗", "date": "2026-06-27", "report_type": "B"}
    fund_meta = {
        "type": "股票型",
        "scale": "73.42亿",
        "nav_date": "2026-06-26",
        "holdings": [{"code": "600276", "name": "恒瑞医药", "ratio": 9.41}],
    }
    trade = {"target_type": "A", "position": 50, "batch_schedule": "3 周分批", "stop_loss": "¥10.50"}
    risk_views = [{"view": "neutral", "risk_level": "Medium", "max_drawdown": 20, "suggested_position": 40}]
    html = render(template="fund", meta=meta, fund_meta=fund_meta, trade=trade, risk_views=risk_views)
    assert "工银前沿医疗" in html
    assert "恒瑞医药" in html
    assert "免责声明" in html


def test_render_portfolio_template_c3():
    meta = {"code": "MIXED", "name": "我的混合持仓", "date": "2026-06-27", "report_type": "C-3"}
    portfolio_subtype = "c3"
    portfolio = {
        "fund_count": 5,
        "stock_count": 3,
        "positions": [
            {"code": "001717", "name": "工银前沿医疗", "type": "fund", "amount": 5000, "ratio": 20.0, "holding_return": -300},
            {"code": "600276", "name": "恒瑞医药", "type": "stock", "amount": 3000, "ratio": 12.0, "holding_return": -150},
        ],
    }
    overlaps = [{"fund": "001717", "stock": "600276", "combined_exposure_ratio": 13.88}]
    balance = {"equity_ratio": 63.0, "bond_ratio": 37.0}
    risk_views = []
    target_allocation = []
    html = render(
        template="portfolio", meta=meta, portfolio_subtype=portfolio_subtype,
        portfolio=portfolio, overlaps=overlaps, balance=balance,
        risk_views=risk_views, target_allocation=target_allocation,
    )
    assert "我的混合持仓" in html
    assert "重复持仓" in html
    assert "恒瑞医药" in html
    assert "免责声明" in html