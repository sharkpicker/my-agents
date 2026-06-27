"""E2E:单基金场景(B)。"""


def test_single_fund_e2e(e2e_runner, today):
    """验证:输入 '001717' 跑 B 工作流,产出 001717 工银前沿医疗.html。"""
    # Step 0
    r0 = e2e_runner.run("input_router:001717")
    assert r0["type"] == "B"

    # Step 1: 7 基金角色并行
    fund_roles = ["fund_market", "fund_fundamentals", "holdings", "flows", "fund_news", "fund_policy", "fund_sentiment"]
    r1 = e2e_runner.run_parallel([f"{r}:001717" for r in fund_roles])
    assert len(r1) == 7

    # Step 2-7
    e2e_runner.run("data_quality")
    e2e_runner.run_parallel(["bull", "bear"])
    e2e_runner.run("research_manager")
    e2e_runner.run("trader")
    e2e_runner.run_parallel(["aggressive", "conservative", "neutral"])
    r7 = e2e_runner.run("portfolio_manager")

    # Step 8
    html_path = e2e_runner.render_html(
        r7, "fund",
        meta={"code": "001717", "name": "工银瑞信前沿医疗股票A", "date": today, "report_type": "B"},
    )
    assert html_path.exists()
    assert "001717" in html_path.name
    assert "工银" in html_path.name
    # 反向断言:文件名不应含 portfolio
    assert "portfolio" not in html_path.name.lower()