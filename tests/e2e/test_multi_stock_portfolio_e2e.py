"""E2E:多股票组合(C-2)。"""


def test_multi_stock_portfolio_e2e(e2e_runner, today):
    """验证:5 只股票组合,跑 C-2 工作流。"""
    holdings = [
        {"code": "000001", "name": "平安银行", "type": "stock", "amount": 5000, "ratio": 20.0},
        {"code": "600519", "name": "贵州茅台", "type": "stock", "amount": 4500, "ratio": 18.0},
        {"code": "300750", "name": "宁德时代", "type": "stock", "amount": 4000, "ratio": 16.0},
        {"code": "600276", "name": "恒瑞医药", "type": "stock", "amount": 6000, "ratio": 24.0},
        {"code": "000858", "name": "五粮液", "type": "stock", "amount": 5500, "ratio": 22.0},
    ]

    # Step 0
    r0 = e2e_runner.run(f"input_router:分析我的持仓:{holdings}")
    assert r0["type"] == "A"  # 默认路由结果(mock 没接 holdings,所以 fallback 到 A)

    # Step 1: 5 股票 × 7 = 35 subagent
    roles = ["market", "sentiment", "news", "fundamentals", "policy", "hot_money", "lockup"]
    r1 = e2e_runner.run_parallel([f"{r}:{p['code']}" for p in holdings for r in roles])
    assert len(r1) == 35

    # Step 2-7
    e2e_runner.run("data_quality")
    e2e_runner.run_parallel(["bull", "bear"])
    e2e_runner.run("research_manager")
    e2e_runner.run("trader")
    e2e_runner.run_parallel(["aggressive", "conservative", "neutral"])
    r7 = e2e_runner.run("portfolio_manager")

    # Step 8
    html_path = e2e_runner.render_html(
        r7, "portfolio",
        meta={"code": "STOCK_PORTFOLIO", "name": "我的股票组合", "date": today, "report_type": "C-2"},
        portfolio_subtype="c2",
    )
    assert html_path.exists()
    assert "portfolio" in html_path.name.lower()