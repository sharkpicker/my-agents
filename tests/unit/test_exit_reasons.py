"""清除清单分类函数单元测试。"""
from __future__ import annotations

import pytest

from data_tools.portfolio import (
    ExitReasonItem,
    classify_exit_reasons,
    find_redundant_pairs,
)
from data_tools.portfolio_prefs import UserPrefs


@pytest.fixture
def sample_holdings():
    return [
        {
            "code": "014655",
            "name": "国联益海30天滚动持有短债A",
            "type": "fund",
            "amount": 5000.0,
            "category": "bond",
        },
        {
            "code": "011095",
            "name": "博时恒泽混合A",
            "type": "fund",
            "amount": 10000.0,
            "category": "balanced",
        },
        {
            "code": "002001",
            "name": "某重复风格基金",
            "type": "fund",
            "amount": 3000.0,
            "category": "balanced",
        },
    ]


@pytest.fixture
def sample_fund_reports():
    return {
        "014655": {
            "report_paths": {"market": "repos/.../014655_market.md"},
            "has_reports": True,
            "quality_signals": {
                "scale": {"score": 15.0, "details": "1.09 亿, 接近清盘线"},
                "performance": {"score": 70.0, "details": "近 3 年 优秀"},
                "manager": {"score": 60.0, "details": "任职 3 年"},
                "concentration": {"score": 50.0, "details": "前十大占 30%"},
                "policy_sentiment": {"score": 50.0, "details": "中性"},
            },
        },
        "011095": {
            "report_paths": {"market": "repos/.../011095_market.md"},
            "has_reports": True,
            "quality_signals": {
                "scale": {"score": 70.0, "details": "10 亿"},
                "performance": {"score": 80.0, "details": "近 1/3/5 年均 优秀"},
                "manager": {
                    "score": 40.0,
                    "details": "经理刚变更 90 天内",
                    "manager_change": True,
                },
                "concentration": {"score": 50.0, "details": ""},
                "policy_sentiment": {"score": 50.0, "details": ""},
            },
        },
        "002001": {
            "report_paths": {},
            "has_reports": False,
            "quality_signals": {},
        },
    }


@pytest.fixture
def sample_gap_report():
    return {
        "gaps": [
            {
                "category": "bond",
                "current_pct": 0.15,
                "target_pct": 0.25,
                "delta_pct": 0.10,
                "action": "add",
            },
            {
                "category": "balanced",
                "current_pct": 0.35,
                "target_pct": 0.30,
                "delta_pct": -0.05,
                "action": "trim",
            },
        ],
        "overweight": ["balanced"],
    }


@pytest.fixture
def sample_prefs():
    return UserPrefs(
        risk_level=3,
        horizon="medium",
        preferred_categories=[],
        excluded_categories=[],
        excluded_codes=set(),
    )


def test_clear_liquidation_risk_detected(
    sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
):
    result = classify_exit_reasons(
        sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
    )
    by_code = {e["code"]: e for e in result}
    assert "014655" in by_code
    codes = [r.code for r in by_code["014655"]["reasons"]]
    assert "clear_liquidation_risk" in codes


def test_clear_manager_change_detected(
    sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
):
    result = classify_exit_reasons(
        sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
    )
    by_code = {e["code"]: e for e in result}
    assert "011095" in by_code
    codes = [r.code for r in by_code["011095"]["reasons"]]
    assert "clear_manager_change" in codes


def test_clear_category_overweight_for_overweight_categories(
    sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
):
    result = classify_exit_reasons(
        sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
    )
    by_code = {e["code"]: e for e in result}
    codes = [r.code for r in by_code["011095"]["reasons"]]
    assert "clear_category_overweight" in codes


def test_missing_data_degrades_gracefully(
    sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
):
    result = classify_exit_reasons(
        sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
    )
    by_code = {e["code"]: e for e in result}
    assert "002001" in by_code
    assert by_code["002001"]["quality_missing"] is True
    codes = [r.code for r in by_code["002001"]["reasons"]]
    assert "clear_redundancy" in codes
    assert "clear_category_overweight" in codes


def test_exit_reason_item_dataclass():
    item = ExitReasonItem(
        code="clear_liquidation_risk",
        label="🔴 临近清盘线（净资产 < 5000 万）",
    )
    assert item.code == "clear_liquidation_risk"
    assert "清盘" in item.label


def test_find_redundant_pairs_returns_empty_when_no_reports():
    positions = [
        {"code": "A", "amount": 5000.0, "category": "balanced"},
        {"code": "B", "amount": 5000.0, "category": "balanced"},
    ]
    pairs = find_redundant_pairs(positions, fund_reports=None)
    assert pairs == []