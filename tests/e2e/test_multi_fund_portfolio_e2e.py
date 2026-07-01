"""E2E:多基金组合(C-1)。"""


def test_multi_fund_portfolio_e2e(e2e_runner, today):
    """验证:9 只基金组合,跑 C-1 工作流。"""
    holdings = [
        {"code": "007466", "name": "华泰柏瑞中证红利低波ETF联接A", "type": "fund", "amount": 7920.75, "ratio": 26.07},
        {"code": "080005", "name": "长盛量化红利策略混合A", "type": "fund", "amount": 1768.88, "ratio": 5.82},
        {"code": "024419", "name": "华夏创业板新能源ETF联接A", "type": "fund", "amount": 567.20, "ratio": 1.87},
        {"code": "014767", "name": "景顺长城华城稳健6个月持有A", "type": "fund", "amount": 476.11, "ratio": 1.57},
        {"code": "005313", "name": "万家中证1000指数增强A", "type": "fund", "amount": 1980.94, "ratio": 6.52},
        {"code": "010673", "name": "兴全中证800六个月持有期指数增强A", "type": "fund", "amount": 832.96, "ratio": 2.74},
        {"code": "004069", "name": "南方中证全指证券公司ETF联接A", "type": "fund", "amount": 1316.72, "ratio": 4.33},
        {"code": "001717", "name": "工银瑞信前沿医疗股票A", "type": "fund", "amount": 5899.37, "ratio": 19.42},
        {"code": "015143", "name": "中欧智能制造混合A", "type": "fund", "amount": 1779.64, "ratio": 5.86},
    ]

    # Step 0
    r0 = e2e_runner.run(f"input_router:分析我的持仓:{holdings}")
    assert r0["type"] == "A"  # mock fallback

    # Step 1: 9 基金 × 7 = 63 subagent
    fund_roles = ["fund_market", "fund_fundamentals", "holdings", "flows", "fund_news", "fund_policy", "fund_sentiment"]
    r1 = e2e_runner.run_parallel([f"{r}:{p['code']}" for p in holdings for r in fund_roles])
    assert len(r1) == 63

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
        meta={"code": "FUND_PORTFOLIO", "name": "我的基金组合", "date": today, "report_type": "C-1"},
        portfolio_subtype="c1",
    )
    assert html_path.exists()
    assert "portfolio" in html_path.name.lower()


# ==========================================================================
# Step 5.5 增强版 E2E:原"质量分组成表 + 深度报告路径表"模块已于 2026-07-01 移除
# 改为"操作建议(P0/P1/P2/P3) + 数据源评估"两个新模块
# ==========================================================================


def test_e2e_html_omits_quality_module_when_no_recommendations(e2e_runner, today):
    """没 fund_recommendations 参数时,模板不应渲染质量分模块(无副作用)。"""
    html_path = e2e_runner.render_html(
        "mock content", "portfolio",
        meta={"code": "FUND_PORTFOLIO", "name": "我的基金组合", "date": today, "report_type": "C-1"},
        portfolio_subtype="c1",
    )
    assert html_path.exists()
    html_text = html_path.read_text(encoding="utf-8")
    # 不应该渲染质量分模块
    assert "推荐补/换基金的深度评估" not in html_text
    assert "质量分组成表" not in html_text
