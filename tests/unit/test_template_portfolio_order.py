"""模板顺序 + 包含块顺序的单元测试。"""
from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader


TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"


@pytest.fixture
def jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
        trim_blocks=False,
    )


@pytest.fixture
def fake_context() -> dict:
    return {
        "meta": {"name": "测试组合"},
        "portfolio_subtype": "c1",
        "portfolio": {
            "fund_count": 2,
            "stock_count": 0,
            "positions": [
                {
                    "code": "014655",
                    "name": "国联益海30天滚动持有短债A",
                    "type": "fund",
                    "amount": 5000.0,
                    "ratio": 25.0,
                    "holding_return": 100.0,
                    "unit_nav": 1.2345,
                    "daily_return": 0.0032,
                    "cache_status": "fresh",
                },
            ],
        },
        "data_source_audit": [
            {
                "code": "014655",
                "name": "国联益海30天滚动持有短债A",
                "unit_nav": 1.2345,
                "daily_return": 0.0032,
                "cache_status": "fresh",
                "reports_count": 7,
                "missing_dimensions": [],
            },
        ],
        "action_recommendations": {
            "p0_clear": [],
            "p1_trim": [],
            "p2_add": [
                {
                    "category": "bond",
                    "target_pct": 0.25,
                    "current_pct": 0.15,
                    "delta_amount": 5000.0,
                    "feature_tags": ["短债", "中短债", "7日年化"],
                    "rec_code": "003547",
                    "rec_name": "鹏华0-5年利率债A",
                },
            ],
            "p3_hold": [
                {
                    "code": "011095",
                    "name": "博时恒泽混合A",
                    "amount": 10000.0,
                    "unit_nav": 1.2345,
                    "opportunity": "历史业绩优秀；经理稳定",
                    "risk_hint": "暂无明显风险",
                },
            ],
        },
        "balance": {"equity_ratio": 30.0, "bond_ratio": 70.0},
        "target_allocation": [
            {"name": "债券", "target_ratio": 25.0, "current_ratio": 15.0},
        ],
    }


def test_portfolio_template_renders_without_error(jinja_env, fake_context):
    """主模板可成功渲染。"""
    template = jinja_env.get_template("portfolio.html.j2")
    output = template.render(**fake_context)
    assert "测试组合" in output


def test_portfolio_section_displays_unit_nav(jinja_env, fake_context):
    """_portfolio_section.html.j2 表格含当前净值列。"""
    template = jinja_env.get_template(
        "partials/_portfolio_section.html.j2"
    )
    output = template.render(**fake_context)
    assert "1.2345" in output
    assert "当前净值" in output
    assert "[净值缺失]" not in output


def test_data_source_audit_partial_renderable(jinja_env, fake_context):
    """数据源评估 partial 可独立渲染。"""
    template = jinja_env.get_template(
        "partials/_data_source_audit.html.j2"
    )
    output = template.render(**fake_context)
    assert "数据源评估" in output
    assert "014655" in output
    assert "🟢" in output


def test_action_recommendations_partial_renderable(jinja_env, fake_context):
    """操作建议 partial 可独立渲染,补充类清单含期望特征标签+推荐基金。"""
    template = jinja_env.get_template(
        "partials/_action_recommendations.html.j2"
    )
    output = template.render(**fake_context)
    assert "操作建议" in output
    assert "P2 增量配置" in output
    assert "短债" in output
    assert "003547" in output
    assert "鹏华0-5年利率债A" in output
    assert "推荐基金" in output


def test_p3_hold_renders_as_table_with_opportunity_and_risk(jinja_env, fake_context):
    """P3 维持当前以表格展示，含机会要点和风险提示列。"""
    template = jinja_env.get_template(
        "partials/_action_recommendations.html.j2"
    )
    output = template.render(**fake_context)
    assert "P3 维持当前" in output
    assert "011095" in output
    assert "历史业绩优秀" in output
    assert "暂无明显风险" in output
    assert "机会要点" in output
    assert "风险提示" in output


def test_full_template_include_order_audit():
    """验证 portfolio.html.j2 的 include 块顺序:操作建议在前。"""
    text = (TEMPLATE_DIR / "portfolio.html.j2").read_text(encoding="utf-8")

    pos_portfolio = text.find("_portfolio_section")
    pos_audit = text.find("_data_source_audit")
    pos_action = text.find("_action_recommendations")

    assert pos_portfolio > 0
    assert pos_audit > 0
    assert pos_action > 0
    assert pos_portfolio < pos_audit < pos_action, (
        "include 块必须按以下顺序:持仓 -> 数据源评估 -> 操作建议"
    )


def test_full_template_excludes_old_recommendation_block():
    """portfolio.html.j2 不再包含原'推荐补/换基金的深度评估'块。"""
    text = (TEMPLATE_DIR / "portfolio.html.j2").read_text(encoding="utf-8")
    assert "推荐补/换基金的深度评估" not in text
