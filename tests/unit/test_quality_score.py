# tests/unit/test_quality_score.py
"""parse_quality_from_reports + score_with_quality_reports 单元测试。"""
from __future__ import annotations

from data_tools.portfolio_rebalance import parse_quality_from_reports
from test_quality_score_fixtures import PERFECT_FUND_REPORTS, TERRIBLE_FUND_REPORTS


def test_parse_quality_perfect_fund(write_fake_reports, tmp_path):
    """业绩优秀 + 集中度低 + 规模大 + 经理稳定 + 政策正面 → quality_score >= 60。"""
    d = write_fake_reports("007466", PERFECT_FUND_REPORTS)
    result = parse_quality_from_reports(
        code="007466",
        reports_dir=str(d.parent),
        category="bond",
        date_str="2026-06-29",
    )
    assert result["quality_score"] >= 60
    assert result["missing_dimensions"] == []
