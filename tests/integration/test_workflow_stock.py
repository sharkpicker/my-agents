"""集成测试:A 工作流(单股票 8 步全跑通)。"""
import pytest


def test_workflow_a_full_8_steps(workflow_runner):
    """完整跑 A 工作流,验证 8 步都触发。"""
    # Step 0: 路由
    r0 = workflow_runner.run_step_0_input_router("000001")
    assert r0["type"] == "A"
    assert r0["code"] == "000001"

    # Step 1: 7 角色并行
    r1 = workflow_runner.run_step_1_analysts("A", ["000001"])
    assert len(r1) == 7

    # Step 2: 数据质量
    r2 = workflow_runner.run_step_2_quality_audit()
    assert r2["status"] == "ok"

    # Step 3: 多空辩论
    r3 = workflow_runner.run_step_3_bull_bear()
    assert len(r3) == 2

    # Step 4: 研究经理
    r4 = workflow_runner.run_step_4_research_manager()
    assert r4["status"] == "ok"

    # Step 5: 交易员
    r5 = workflow_runner.run_step_5_trader()
    assert r5["status"] == "ok"

    # Step 6: 风险评估(3 路并行)
    r6 = workflow_runner.run_step_6_risk()
    assert len(r6) == 3

    # Step 7: 组合经理
    r7 = workflow_runner.run_step_7_portfolio_manager()
    assert "免责声明" in r7 or len(r7) > 0

    # Step 8: HTML 渲染
    r8 = workflow_runner.run_step_8_html_renderer(r7, "stock")
    assert r8.exists()
    assert r8.stat().st_size > 1000
