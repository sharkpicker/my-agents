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


# ==========================================================================
# Step 5.5 增强版集成测试(fund-recommender 深度推荐)
# ==========================================================================


def test_step_5_5_quality_score_fusion_contract():
    """Step 5.5 增强版跑完后,score_with_quality_reports 必须返回正确融合分。"""
    from data_tools.portfolio_rebalance import score_with_quality_reports

    quality_reports = {
        "007466": {
            "code": "007466", "category": "bond", "quality_score": 75.0,
            "signals": {
                "performance": {"score": 45.0, "missing": False},
                "concentration": {"score": 80.0, "missing": False},
            },
            "report_paths": {"market": "x"}, "missing_dimensions": [],
        },
    }
    screener = {"bond": [{"code": "007466", "name": "X", "type": "X",
                          "score": 60, "match_reasons": []}]}
    final = score_with_quality_reports(screener, quality_reports)
    # final = 60*0.3 + 75*0.7 = 18 + 52.5 = 70.5
    assert final["bond"][0]["score"] == 70.5
    assert "quality_signals" in final["bond"][0]
    assert final["bond"][0]["name_score"] == 60
    assert final["bond"][0]["quality_score"] == 75.0
    assert final["bond"][0]["quality_missing"] is False


def test_step_5_5_quality_missing_fallback_contract():
    """Step 5.5 增强版:某只候选 7 报告全失败 → 用 name_score 兜底。"""
    from data_tools.portfolio_rebalance import score_with_quality_reports

    screener = {"bond": [{"code": "AAA", "name": "Y", "type": "Y",
                          "score": 50, "match_reasons": []}]}
    final = score_with_quality_reports(screener, {}, name_weight=0.3, quality_weight=0.7)
    assert final["bond"][0]["score"] == 50
    assert final["bond"][0]["quality_missing"] is True
    assert final["bond"][0]["quality_score"] == 0.0


def test_step_5_5_parse_quality_5d_contract(write_fake_reports):
    """Step 5.5 增强版:parse_quality_from_reports 必须返回 5 维度 signals。"""
    from data_tools.portfolio_rebalance import parse_quality_from_reports
    from test_quality_score_fixtures import PERFECT_FUND_REPORTS

    d = write_fake_reports("007466", PERFECT_FUND_REPORTS)
    result = parse_quality_from_reports(
        code="007466", reports_dir=str(d.parent),
        category="bond", date_str="2026-06-27",
    )
    assert set(result["signals"].keys()) == {
        "performance", "concentration", "scale", "manager", "policy_sentiment"
    }
    assert 0 <= result["quality_score"] <= 100
    assert isinstance(result["missing_dimensions"], list)
