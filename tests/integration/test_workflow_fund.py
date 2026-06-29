"""集成测试:B 工作流(单基金 8 步)。"""


def test_workflow_b_full_8_steps(workflow_runner):
    """完整跑 B 工作流,验证基金特有维度。"""
    # Step 0: 路由
    r0 = workflow_runner.run_step_0_input_router("001717")
    assert r0["type"] == "B"
    assert r0["code"] == "001717"

    # Step 1: 7 基金角色并行
    r1 = workflow_runner.run_step_1_analysts("B", ["001717"])
    assert len(r1) == 7

    # Step 2-7
    r2 = workflow_runner.run_step_2_quality_audit()
    r3 = workflow_runner.run_step_3_bull_bear()
    r4 = workflow_runner.run_step_4_research_manager()
    r5 = workflow_runner.run_step_5_trader()
    r6 = workflow_runner.run_step_6_risk()
    r7 = workflow_runner.run_step_7_portfolio_manager()

    # Step 8
    r8 = workflow_runner.run_step_8_html_renderer(r7, "fund")
    assert r8.exists()
