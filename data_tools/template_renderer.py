"""Jinja2 模板渲染器。"""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)


def render(template: str, **kwargs) -> str:
    """渲染模板,template 是模板名(不含 .html.j2 后缀)。"""
    tpl = env.get_template(f"{template}.html.j2")
    return tpl.render(**kwargs)


def enrich_portfolio_context(context: dict) -> dict:
    """为 portfolio 渲染上下文注入净值缓存状态、操作建议、数据源评估。"""
    positions = context.get("portfolio", {}).get("positions", [])
    if not positions:
        return context

    from .fund_data import get_unit_nav_with_cache_status

    for p in positions:
        if p.get("type") == "fund":
            try:
                unit_nav, daily_return, status = get_unit_nav_with_cache_status(
                    p["code"]
                )
                p["unit_nav"] = unit_nav
                p["daily_return"] = daily_return
                p["cache_status"] = status
            except Exception:
                p.setdefault("unit_nav", None)
                p.setdefault("daily_return", None)
                p.setdefault("cache_status", "missing")

    context["data_source_audit"] = [
        {
            "code": p["code"],
            "name": p.get("name", ""),
            "unit_nav": p.get("unit_nav"),
            "daily_return": p.get("daily_return"),
            "cache_status": p.get("cache_status", "missing"),
            "reports_count": 7,
            "missing_dimensions": [],
        }
        for p in positions
    ]

    try:
        from .portfolio import classify_exit_reasons
        from .portfolio_prefs import load_user_prefs

        user_id = context.get("user_id")
        prefs = load_user_prefs(user_id) if user_id else None
        fund_reports = context.get("fund_reports", {})
        gap_report = context.get("gap_report", {"overweight": []})

        if prefs is not None:
            exit_items = classify_exit_reasons(
                positions, fund_reports, gap_report, prefs
            )
            critical_codes = {
                "clear_liquidation_risk",
                "clear_redemption_pressure",
                "clear_user_excluded",
            }
            p0 = [
                it for it in exit_items
                if any(r.code in critical_codes for r in it["reasons"])
            ]
            p1 = [
                it for it in exit_items
                if it not in p0 and it["reasons"]
            ]
            p0.sort(key=lambda x: -len(x["reasons"]))
            p1.sort(key=lambda x: -len(x["reasons"]))

            p2 = []
            for g in gap_report.get("gaps", []):
                if g.get("action") == "add":
                    p2.append({
                        "category": g.get("category", ""),
                        "target_pct": g.get("target_pct", 0.0),
                        "current_pct": g.get("current_pct", 0.0),
                        "delta_amount": g.get("delta_amount", 0.0),
                        "feature_tags": _feature_tags_for(g.get("category", "")),
                    })

            exit_codes = {it["code"] for it in p0 + p1}
            p3 = [it for it in exit_items if it["code"] not in exit_codes]

            context["action_recommendations"] = {
                "p0_clear": p0,
                "p1_trim": p1,
                "p2_add": p2,
                "p3_hold": p3,
            }
        else:
            context.setdefault("action_recommendations", {
                "p0_clear": [], "p1_trim": [], "p2_add": [], "p3_hold": []
            })
    except Exception:
        context.setdefault("action_recommendations", {
            "p0_clear": [], "p1_trim": [], "p2_add": [], "p3_hold": []
        })

    return context


def _feature_tags_for(category: str) -> list[str]:
    """按品类返回期望特征标签。"""
    tags_map = {
        "bond": ["短债", "中短债", "7日年化"],
        "equity": ["高股息", "低估值", "红利"],
        "balanced": ["固收+", "最大回撤 < 2%", "夏普 > 1"],
        "index": ["宽基", "Smart Beta", "费率 < 0.5%"],
    }
    return tags_map.get(category, [])[:3]


def render_portfolio(context: dict) -> str:
    """渲染组合诊断报告 HTML，自动注入净值缓存与操作建议上下文。"""
    context = enrich_portfolio_context(context)
    return render("portfolio", **context)
