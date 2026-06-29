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
# Step 5.5 增强版 E2E:验证 HTML 模板渲染包含质量分组成表 + 深度报告路径表
# ==========================================================================


def test_e2e_html_contains_quality_score_module(e2e_runner, today):
    """Step 5.5 增强版跑完后,portfolio.html 必须包含质量分组成表模块。"""
    mock_fund_recommendations = {
        "recommendations": [
            {
                "intent": "add",
                "category": "bond",
                "holding_code": None,
                "candidates": [
                    {
                        "rank": 1,
                        "code": "007466",
                        "name": "华泰柏瑞中证红利低波ETF联接A",
                        "type": "指数型",
                        "score": 78.4,
                        "name_score": 60.0,
                        "quality_score": 82.0,
                        "match_reasons": ["名称含 '低波'", "用户偏好 bond"],
                        "quality_signals": {
                            "performance": {"score": 50.0, "details": {}, "missing": False},
                            "concentration": {"score": 80.0, "details": {}, "missing": False},
                            "scale": {"score": 60.0, "details": {}, "missing": False},
                            "manager": {"score": 70.0, "details": {}, "missing": False},
                            "policy_sentiment": {"score": 75.0, "details": {}, "missing": False},
                        },
                        "report_paths": {
                            "market": "reports/2026-06-27/fund/candidate/007466_market.md",
                            "fundamentals": "reports/2026-06-27/fund/candidate/007466_fundamentals.md",
                            "holdings": "reports/2026-06-27/fund/candidate/007466_holdings.md",
                            "flows": "reports/2026-06-27/fund/candidate/007466_flows.md",
                            "news": "reports/2026-06-27/fund/candidate/007466_news.md",
                            "policy": "reports/2026-06-27/fund/candidate/007466_policy.md",
                            "sentiment": "reports/2026-06-27/fund/candidate/007466_sentiment.md",
                        },
                        "quality_missing": False,
                        "missing_dimensions": [],
                    },
                ],
            },
        ],
    }
    html_path = e2e_runner.render_html(
        "mock content", "portfolio",
        meta={"code": "FUND_PORTFOLIO", "name": "我的基金组合", "date": today, "report_type": "C-1"},
        portfolio_subtype="c1",
        fund_recommendations=mock_fund_recommendations,
    )
    assert html_path.exists()
    html_text = html_path.read_text(encoding="utf-8")
    assert "推荐补/换基金的深度评估" in html_text
    assert "007466" in html_text
    assert "华泰柏瑞中证红利低波ETF联接A" in html_text
    # 5 维度信号 chips 必须渲染
    assert "performance" in html_text
    assert "concentration" in html_text
    # 深度报告路径表
    assert "深度报告路径" in html_text
    assert "_market" in html_text


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
