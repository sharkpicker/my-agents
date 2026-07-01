"""组合分析工具:HHI 集中度 + 重复持仓检测 + 股债平衡穿透。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


class Overlap(TypedDict):
    fund: str
    stock: str
    combined_exposure_ratio: float


def calculate_concentration(positions: list[dict]) -> float:
    """计算 HHI(Herfindahl-Hirschman Index)集中度。

    HHI = Σ(权重²),值域 0~1,>0.25 为高集中,<0.15 为分散。
    """
    total = sum(p["amount"] for p in positions)
    if total == 0:
        return 0.0
    weights = [p["amount"] / total for p in positions]
    return sum(w * w for w in weights)


def detect_overlap(
    fund_holdings: dict[str, dict], direct_stocks: list[dict]
) -> list[Overlap]:
    """检测基金重仓股 ∩ 直接持仓的重复持仓。

    Args:
        fund_holdings: {基金代码: {top10: [{code, ratio}, ...]}}
        direct_stocks: [{code, amount}, ...]

    Returns:
        [{fund, stock, combined_exposure_ratio}]
    """
    direct_codes = {s["code"]: s["amount"] for s in direct_stocks}
    overlaps = []
    total_amount = sum(direct_codes.values())

    for fund_code, data in fund_holdings.items():
        for holding in data.get("top10", []):
            stock_code = holding["code"]
            if stock_code in direct_codes:
                combined = (
                    direct_codes[stock_code] / total_amount
                    if total_amount > 0
                    else 0
                )
                overlaps.append(
                    Overlap(
                        fund=fund_code,
                        stock=stock_code,
                        combined_exposure_ratio=round(combined, 4),
                    )
                )
    return overlaps


def calculate_balance(holdings: list[dict]) -> dict:
    """穿透计算整体权益/债券占比。

    Args:
        holdings: [{code, type, amount, stock_penetration?}, ...]
            - stock_penetration: 基金持仓中股票占比(默认 0)

    Returns:
        {equity_ratio, bond_ratio, equity_amount, bond_amount}
    """
    total = sum(h["amount"] for h in holdings)
    if total == 0:
        return {"equity_ratio": 0, "bond_ratio": 0, "equity_amount": 0, "bond_amount": 0}

    equity_amount = 0.0
    for h in holdings:
        if h["type"] == "stock":
            equity_amount += h["amount"]
        elif h["type"] == "fund":
            penetration = h.get("stock_penetration", 0.5)
            equity_amount += h["amount"] * penetration

    bond_amount = total - equity_amount
    return {
        "equity_ratio": round(equity_amount / total, 4),
        "bond_ratio": round(bond_amount / total, 4),
        "equity_amount": round(equity_amount, 2),
        "bond_amount": round(bond_amount, 2),
    }


EXIT_REASON_CATALOG: dict[str, str] = {
    "clear_liquidation_risk": "🔴 临近清盘线（净资产 < 5000 万）",
    "clear_redemption_pressure": "🔴 持续大额净赎回（季度净赎回 > 20%）",
    "clear_underperform_3y": "🟡 长期跑输基准（3 年排名 < 1/2）",
    "clear_manager_change": "🟡 经理刚变更（磨合期）",
    "clear_redundancy": "🟡 重复暴露（与组合内其他持仓相关系数 > 0.85）",
    "clear_concentration_violation": "🟡 单一占比超纪律（> 25%）",
    "clear_category_overweight": "🟢 风格/品类超配",
    "clear_user_excluded": "🟢 用户已显式排除",
    "manual_flag": "🔵 用户手工标记",
}


@dataclass
class ExitReasonItem:
    code: str
    label: str


def find_redundant_pairs(
    positions: list[dict],
    fund_reports: dict[str, dict] | None = None,
    threshold: float = 0.85,
) -> list[tuple[str, str, float]]:
    """检测组合内风格重复暴露（启发式：同 category 且合计占比 > 40%）。"""
    if fund_reports is None:
        return []
    total = sum(p["amount"] for p in positions) or 1.0
    by_cat: dict[str, list[dict]] = {}
    for p in positions:
        by_cat.setdefault(p.get("category", "balanced"), []).append(p)
    pairs = []
    for cat, items in by_cat.items():
        if len(items) < 2:
            continue
        combined = sum(p["amount"] for p in items) / total
        if combined < 0.40:
            continue
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                pairs.append((items[i]["code"], items[j]["code"], 0.90))
    return pairs


def classify_exit_reasons(
    holdings: list[dict],
    fund_reports: dict[str, dict],
    gap_report: dict,
    prefs,
    total_amount: float | None = None,
) -> list[dict]:
    """为每只持仓基金生成「初步筛掉原因」清单。"""
    if total_amount is None:
        total_amount = sum(h["amount"] for h in holdings) or 1.0
    overweight_set = set(gap_report.get("overweight", []))
    excluded_codes = set(getattr(prefs, "excluded_codes", set()) or set())

    redundant_pairs = find_redundant_pairs(holdings, fund_reports)
    redundant_codes = {c for pair in redundant_pairs for c in (pair[0], pair[1])}

    out: list[dict] = []
    for h in holdings:
        code = h["code"]
        name = h.get("name", "")
        amount = float(h.get("amount", 0))
        category = h.get("category")

        report = fund_reports.get(code, {})
        has_reports = report.get("has_reports", False)
        quality_missing = not has_reports
        signals = report.get("quality_signals", {})

        reasons: list[ExitReasonItem] = []
        if has_reports and signals:
            scale = signals.get("scale", {})
            if scale.get("score", 100) < 25:
                reasons.append(
                    ExitReasonItem(
                        "clear_liquidation_risk",
                        EXIT_REASON_CATALOG["clear_liquidation_risk"],
                    )
                )
            performance = signals.get("performance", {})
            if performance.get("score", 100) < 30:
                reasons.append(
                    ExitReasonItem(
                        "clear_underperform_3y",
                        EXIT_REASON_CATALOG["clear_underperform_3y"],
                    )
                )
            manager = signals.get("manager", {})
            if manager.get("manager_change", False) or manager.get("score", 100) < 40:
                reasons.append(
                    ExitReasonItem(
                        "clear_manager_change",
                        EXIT_REASON_CATALOG["clear_manager_change"],
                    )
                )

        if amount / total_amount > 0.25:
            reasons.append(
                ExitReasonItem(
                    "clear_concentration_violation",
                    EXIT_REASON_CATALOG["clear_concentration_violation"],
                )
            )

        if code in redundant_codes:
            reasons.append(
                ExitReasonItem(
                    "clear_redundancy",
                    EXIT_REASON_CATALOG["clear_redundancy"],
                )
            )

        if category in overweight_set:
            reasons.append(
                ExitReasonItem(
                    "clear_category_overweight",
                    EXIT_REASON_CATALOG["clear_category_overweight"],
                )
            )

        if code in excluded_codes:
            reasons.append(
                ExitReasonItem(
                    "clear_user_excluded",
                    EXIT_REASON_CATALOG["clear_user_excluded"],
                )
            )

        out.append(
            {
                "code": code,
                "name": name,
                "amount": amount,
                "category": category,
                "unit_nav": None,
                "daily_return": None,
                "cache_status": "missing",
                "reasons": reasons,
                "quality_missing": quality_missing,
            }
        )

    return out
