"""组合分析工具:HHI 集中度 + 重复持仓检测 + 股债平衡穿透。"""
from __future__ import annotations
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
