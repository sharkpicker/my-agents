# tests/unit/test_quality_score.py
"""parse_quality_from_reports + score_with_quality_reports 单元测试。"""
from __future__ import annotations

from data_tools.portfolio_rebalance import (
    parse_quality_from_reports,
    score_with_quality_reports,
)
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


def test_parse_quality_terrible_fund(write_fake_reports, tmp_path):
    """业绩差 + 集中度高 + 迷你盘 + 经理刚换 + 政策负面 → quality_score <= 30。"""
    d = write_fake_reports("999999", TERRIBLE_FUND_REPORTS)
    result = parse_quality_from_reports(
        code="999999",
        reports_dir=str(d.parent),
        category="sector",
        date_str="2026-06-29",
    )
    assert result["quality_score"] <= 30
    assert (
        "manager" in result["missing_dimensions"]
        or result["signals"]["manager"]["score"] <= 20
    )


def test_parse_quality_missing_one_dimension(tmp_path):
    """缺一个维度(market)→ 其他 4 维度等比放大,quality_score 仍可计算。"""
    d = tmp_path / "007466"
    d.mkdir(parents=True, exist_ok=True)
    for role, content in PERFECT_FUND_REPORTS.items():
        if role != "market":
            (d / f"007466_{role}.md").write_text(content, encoding="utf-8")
    (d / "007466_market.md").write_text("", encoding="utf-8")
    result = parse_quality_from_reports(
        code="007466",
        reports_dir=str(d.parent),
        category="bond",
        date_str="2026-06-29",
    )
    assert "performance" in result["missing_dimensions"]
    assert 50 <= result["quality_score"] <= 90


def test_parse_quality_all_missing(tmp_path):
    """7 报告全缺失 → quality_score = 0, missing_dimensions 包含全部 5 维度。"""
    d = tmp_path / "000000"
    d.mkdir(parents=True, exist_ok=True)
    result = parse_quality_from_reports(
        code="000000",
        reports_dir=str(d.parent),
        category="bond",
        date_str="2026-06-29",
    )
    assert result["quality_score"] == 0.0
    assert len(result["missing_dimensions"]) == 5


def test_score_fusion_basic():
    """name_score=60, quality_score=80, 权重 0.3/0.7 → final = 74。"""
    screener = {
        "bond": [
            {
                "code": "007466",
                "name": "X",
                "type": "X",
                "score": 60,
                "match_reasons": [],
            }
        ]
    }
    quality = {
        "007466": {
            "code": "007466",
            "category": "bond",
            "quality_score": 80,
            "signals": {},
            "report_paths": {},
            "missing_dimensions": [],
        }
    }
    out = score_with_quality_reports(
        screener, quality, name_weight=0.3, quality_weight=0.7
    )
    assert out["bond"][0]["score"] == 74.0
    assert out["bond"][0]["name_score"] == 60
    assert out["bond"][0]["quality_score"] == 80


def test_score_fusion_quality_missing_fallback():
    """quality_reports 缺失某只 → 用 name_score 兜底,标 quality_missing=True。"""
    screener = {
        "bond": [
            {
                "code": "AAA",
                "name": "Y",
                "type": "Y",
                "score": 50,
                "match_reasons": [],
            }
        ]
    }
    out = score_with_quality_reports(
        screener, {}, name_weight=0.3, quality_weight=0.7
    )
    assert out["bond"][0]["score"] == 50
    assert out["bond"][0]["quality_missing"] is True
