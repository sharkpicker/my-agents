"""集成测试:C-3 工作流(混合组合 + 重复持仓检测)。"""


def test_workflow_c3_mixed(workflow_runner):
    """5 基金 + 3 股票混合组合,验证 C-3 跑通。"""
    holdings = [
        {"code": "001717", "name": "工银前沿医疗", "type": "fund", "amount": 5000},
        {"code": "005313", "name": "万家中证1000", "type": "fund", "amount": 3000},
        {"code": "014767", "name": "景顺长城稳健", "type": "fund", "amount": 2500},
        {"code": "004069", "name": "南方证券", "type": "fund", "amount": 2000},
        {"code": "007466", "name": "华泰柏瑞红利", "type": "fund", "amount": 1500},
        {"code": "600519", "name": "贵州茅台", "type": "stock", "amount": 4000},
        {"code": "600276", "name": "恒瑞医药", "type": "stock", "amount": 3000},
        {"code": "300750", "name": "宁德时代", "type": "stock", "amount": 1500},
    ]

    # Step 0
    r0 = workflow_runner.run_step_0_input_router("分析我的混合持仓", holdings=holdings)
    assert r0["type"] == "C-3"
    assert len(r0["positions"]) == 8

    # Step 1: 5 基金 × 7 + 3 股票 × 7 = 56 subagent
    fund_codes = [p["code"] for p in holdings if p["type"] == "fund"]
    stock_codes = [p["code"] for p in holdings if p["type"] == "stock"]
    r1_funds = workflow_runner.run_step_1_analysts("C-1", fund_codes)
    r1_stocks = workflow_runner.run_step_1_analysts("A", stock_codes)
    assert len(r1_funds) == 35  # 5 × 7
    assert len(r1_stocks) == 21  # 3 × 7

    # Step 2-7
    workflow_runner.run_step_2_quality_audit()
    workflow_runner.run_step_3_bull_bear()
    workflow_runner.run_step_4_research_manager()
    workflow_runner.run_step_5_trader()
    workflow_runner.run_step_6_risk()
    r7 = workflow_runner.run_step_7_portfolio_manager(scenario="portfolio")

    # Step 8
    r8 = workflow_runner.run_step_8_html_renderer(r7, "portfolio")
    assert r8.exists()
