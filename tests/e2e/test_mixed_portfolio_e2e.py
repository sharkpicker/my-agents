"""E2E:混合组合(C-3) ⭐ 核心场景。"""


def test_mixed_portfolio_e2e(e2e_runner, today):
    """验证:5 基金 + 3 股票混合组合 + 重复持仓 fixture。"""
    holdings = [
        # 基金部分(56%)
        {"code": "001717", "name": "工银瑞信前沿医疗股票A", "type": "fund", "amount": 5000, "ratio": 20.0, "holding_return": 12.5},
        {"code": "005313", "name": "万家中证1000指数增强A", "type": "fund", "amount": 3000, "ratio": 12.0, "holding_return": 8.3},
        {"code": "014767", "name": "景顺长城华城稳健6个月持有A", "type": "fund", "amount": 2500, "ratio": 10.0, "holding_return": 3.2},
        {"code": "004069", "name": "南方中证全指证券公司ETF联接A", "type": "fund", "amount": 2000, "ratio": 8.0, "holding_return": -2.1},
        {"code": "007466", "name": "华泰柏瑞中证红利低波ETF联接A", "type": "fund", "amount": 1500, "ratio": 6.0, "holding_return": 5.7},
        # 股票部分(34%) — 600276 与 001717 重仓股重复
        {"code": "600519", "name": "贵州茅台", "type": "stock", "amount": 4000, "ratio": 16.0, "holding_return": 15.4},
        {"code": "600276", "name": "恒瑞医药", "type": "stock", "amount": 3000, "ratio": 12.0, "holding_return": -5.8},
        {"code": "300750", "name": "宁德时代", "type": "stock", "amount": 1500, "ratio": 6.0, "holding_return": 22.1},
    ]

    # Step 0
    r0 = e2e_runner.run(f"input_router:分析我的混合持仓:{holdings}")
    assert r0["type"] == "A"  # mock fallback

    # Step 1a: 5 基金 × 7 = 35
    fund_roles = ["fund_market", "fund_fundamentals", "holdings", "flows", "fund_news", "fund_policy", "fund_sentiment"]
    funds = [p for p in holdings if p["type"] == "fund"]
    r1a = e2e_runner.run_parallel([f"{r}:{p['code']}" for p in funds for r in fund_roles])
    assert len(r1a) == 35

    # Step 1b: 3 股票 × 7 = 21
    stock_roles = ["market", "sentiment", "news", "fundamentals", "policy", "hot_money", "lockup"]
    stocks = [p for p in holdings if p["type"] == "stock"]
    r1b = e2e_runner.run_parallel([f"{r}:{p['code']}" for p in stocks for r in stock_roles])
    assert len(r1b) == 21

    # Step 2-7
    e2e_runner.run("data_quality")
    e2e_runner.run_parallel(["bull", "bear"])
    e2e_runner.run("research_manager")
    e2e_runner.run("trader")
    e2e_runner.run_parallel(["aggressive", "conservative", "neutral"])
    r7 = e2e_runner.run("portfolio_manager")

    # Step 8: 验证 C-3 HTML 含三维度
    html_path = e2e_runner.render_html(
        r7, "portfolio",
        meta={"code": "MIXED_PORTFOLIO", "name": "我的混合持仓", "date": today, "report_type": "C-3"},
        portfolio_subtype="c3",
        overlaps=[{"fund": "001717", "stock": "600276", "combined_exposure_ratio": 13.88}],
        balance={"equity_ratio": 63.0, "bond_ratio": 37.0},
        portfolio={
            "fund_count": 5,
            "stock_count": 3,
            "positions": holdings,
        },
        target_allocation=[
            {"name": "权益类", "target_ratio": 50.0, "current_ratio": 63.0},
            {"name": "固收类", "target_ratio": 50.0, "current_ratio": 37.0},
        ],
    )
    assert html_path.exists()
    html_content = html_path.read_text(encoding="utf-8")
    # C-3 必含
    assert "重复持仓" in html_content
    assert "股债" in html_content or "权益" in html_content
    assert "免责声明" in html_content
    assert "我的混合持仓" in html_content