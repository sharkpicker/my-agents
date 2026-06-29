"""集成测试:C-1 工作流(多基金组合)。"""


def test_workflow_c1_9_funds(workflow_runner):
    """9 只基金组合,验证 C-1 跑通 + portfolio_analyst 触发。"""
    holdings = [{"code": "001717", "name": "工银前沿医疗", "type": "fund", "amount": 5899.37}] * 1
    holdings += [{"code": f"00000{i}", "name": f"基金{i}", "type": "fund", "amount": 1000} for i in range(8)]

    # Step 0
    r0 = workflow_runner.run_step_0_input_router("分析我的持仓", holdings=holdings)
    assert r0["type"] == "C-1"
    assert len([p for p in r0["positions"] if p["type"] == "fund"]) == 9

    # Step 1: 9 基金 × 7 角色 = 63 subagent
    r1 = workflow_runner.run_step_1_analysts("C-1", [p["code"] for p in holdings])
    assert len(r1) == 63  # 9 × 7

    # Step 2-7(同单标)
    workflow_runner.run_step_2_quality_audit()
    workflow_runner.run_step_3_bull_bear()
    workflow_runner.run_step_4_research_manager()
    workflow_runner.run_step_5_trader()
    workflow_runner.run_step_6_risk()
    r7 = workflow_runner.run_step_7_portfolio_manager(scenario="portfolio")

    # Step 8
    r8 = workflow_runner.run_step_8_html_renderer(r7, "portfolio")
    assert r8.exists()
