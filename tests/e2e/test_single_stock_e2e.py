"""E2E:单股票场景(A)。"""


def test_single_stock_e2e(e2e_runner, today):
    """验证:输入 '分析平安银行' 能完整跑通 8 步,产出 000001_平安银行.html。"""
    # Step 0: 路由
    r0 = e2e_runner.run("input_router:分析平安银行")
    assert r0["type"] == "A"
    assert r0["code"] == "000001"

    # Step 1: 7 角色并行
    roles = ["market", "sentiment", "news", "fundamentals", "policy", "hot_money", "lockup"]
    r1 = e2e_runner.run_parallel([f"{r}:000001" for r in roles])
    assert len(r1) == 7

    # Step 2-7(简化,只验证流程跑通)
    r2 = e2e_runner.run("data_quality")
    r3 = e2e_runner.run_parallel(["bull", "bear"])
    r4 = e2e_runner.run("research_manager")
    r5 = e2e_runner.run("trader")
    r6 = e2e_runner.run_parallel(["aggressive", "conservative", "neutral"])
    r7 = e2e_runner.run("portfolio_manager")

    assert "免责声明" in r7 or len(r7) > 0

    # Step 8: HTML 渲染
    html_path = e2e_runner.render_html(
        r7, "stock",
        meta={"code": "000001", "name": "平安银行", "date": today, "report_type": "A"},
    )
    assert html_path.exists()
    assert html_path.stat().st_size > 1000
    assert "000001" in html_path.name
    assert "平安银行" in html_path.name