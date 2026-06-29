"""组合再平衡:gap 分析 + 候选基金筛选.

输入:
- 当前持仓: [{code, name, type, amount, category?}, ...]
- 目标配置: {category: weight} (来自 portfolio_prefs.get_target_allocation)
- 用户偏好: UserPrefs (用于排除已持有的、不想要的)
- 基金全量库: data/funds/_meta/fund_list.json (已通过 fund_universe 落盘)

输出:
- gap: 每类资产的当前 vs 目标差异(权重 + 金额)
- underweight_categories: 需要加仓的资产大类
- overweight_categories: 需要减仓的资产大类
- replacements: 每个 underweight 类别下,从场外基金全量库中筛出的候选补/换基金
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from .portfolio_prefs import (
    ASSET_CATEGORIES,
    CATEGORY_KEYWORDS,
    UserPrefs,
    get_target_allocation,
    iter_category_keywords,
)
from .quality_scorer import (
    QUALITY_WEIGHTS,
    parse_quality_from_reports,
    score_with_quality_reports,
)


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class PositionLike:
    """最小化的持仓视图,组合工作流 Step 2 之后透传。"""
    code: str
    name: str = ""
    type: str = "fund"             # fund / stock
    amount: float = 0.0
    category: str | None = None    # 已分类的资产大类(由调用方/portfolio_analyst 填充)

    @classmethod
    def from_dict(cls, d: dict) -> "PositionLike":
        return cls(
            code=str(d.get("code", "")),
            name=str(d.get("name", "")),
            type=str(d.get("type", "fund")),
            amount=float(d.get("amount", 0) or 0),
            category=d.get("category"),
        )


@dataclass
class GapItem:
    category: str
    current_pct: float
    target_pct: float
    delta_pct: float        # target - current, 正=需加,负=需减
    current_amount: float
    target_amount: float
    delta_amount: float
    action: str             # hold / add / trim

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RebalancePlan:
    total_amount: float
    target_allocation: dict[str, float]
    current_allocation: dict[str, float]
    gaps: list[GapItem]
    underweight: list[str]
    overweight: list[str]
    replacements: dict[str, list[dict]]   # category -> [{code, name, type, score, match_reasons}]
    excluded_holdings: list[dict]         # 当前持仓中需要清出的标的

    def to_dict(self) -> dict:
        return {
            "total_amount": self.total_amount,
            "target_allocation": self.target_allocation,
            "current_allocation": self.current_allocation,
            "gaps": [g.to_dict() for g in self.gaps],
            "underweight": self.underweight,
            "overweight": self.overweight,
            "replacements": self.replacements,
            "excluded_holdings": self.excluded_holdings,
        }


# ---------------------------------------------------------------------------
# 1. 持仓 → 资产大类分类
# ---------------------------------------------------------------------------

# 基金名称 → 资产大类(按 CATEGORY_KEYWORDS 顺序,先匹配者优先)
_NAME_TO_CATEGORY: list[tuple[str, str]] = []
for _cat, _kws in CATEGORY_KEYWORDS.items():
    for _kw in _kws:
        _NAME_TO_CATEGORY.append((_kw, _cat))


def classify_position(pos: PositionLike) -> str:
    """根据基金/股票名称或代码,把单条持仓归到 9 类资产大类之一。"""
    if pos.category and pos.category in ASSET_CATEGORIES:
        return pos.category
    if pos.type == "stock":
        # 直接持股默认归 equity
        return "equity"
    name = pos.name or ""
    for kw, cat in _NAME_TO_CATEGORY:
        if kw in name:
            return cat
    # 默认归到 balanced (无法识别时给一个折中档)
    return "balanced"


def classify_positions(positions: Iterable[dict | PositionLike]) -> list[PositionLike]:
    out: list[PositionLike] = []
    for p in positions:
        pp = p if isinstance(p, PositionLike) else PositionLike.from_dict(p)
        if pp.category is None:
            pp.category = classify_position(pp)
        out.append(pp)
    return out


# ---------------------------------------------------------------------------
# 2. 计算当前资产配置
# ---------------------------------------------------------------------------

def compute_current_allocation(positions: list[PositionLike]) -> dict[str, float]:
    total = sum(p.amount for p in positions)
    if total <= 0:
        return {c: 0.0 for c in ASSET_CATEGORIES}
    out = {c: 0.0 for c in ASSET_CATEGORIES}
    for p in positions:
        out[p.category] = out.get(p.category, 0.0) + p.amount
    return {c: round(v / total, 4) for c, v in out.items()}


# ---------------------------------------------------------------------------
# 3. gap 分析
# ---------------------------------------------------------------------------

# 触发动作的阈值(权重绝对值)
ADD_THRESHOLD = 0.03
TRIM_THRESHOLD = 0.03


def compute_gap(
    positions: list[PositionLike],
    target_allocation: dict[str, float],
) -> tuple[dict[str, float], list[GapItem], list[str], list[str]]:
    """计算当前 vs 目标的 gap,返回 (current_alloc, gaps, underweight, overweight)。"""
    total = sum(p.amount for p in positions)
    if total <= 0:
        total = 0.0
    current = compute_current_allocation(positions)

    gaps: list[GapItem] = []
    underweight: list[str] = []
    overweight: list[str] = []
    for cat in ASSET_CATEGORIES:
        cur_pct = current.get(cat, 0.0)
        tgt_pct = target_allocation.get(cat, 0.0)
        delta_pct = round(tgt_pct - cur_pct, 4)
        cur_amt = round(cur_pct * total, 2)
        tgt_amt = round(tgt_pct * total, 2)
        delta_amt = round(tgt_amt - cur_amt, 2)
        if delta_pct > ADD_THRESHOLD:
            action = "add"
            underweight.append(cat)
        elif delta_pct < -TRIM_THRESHOLD:
            action = "trim"
            overweight.append(cat)
        else:
            action = "hold"
        gaps.append(GapItem(
            category=cat,
            current_pct=cur_pct,
            target_pct=tgt_pct,
            delta_pct=delta_pct,
            current_amount=cur_amt,
            target_amount=tgt_amt,
            delta_amount=delta_amt,
            action=action,
        ))

    return current, gaps, underweight, overweight


# ---------------------------------------------------------------------------
# 4. 从场外基金全量库中筛选补/换基金
# ---------------------------------------------------------------------------

def _load_universe(path: str | None) -> list[dict]:
    """加载基金全量列表: 优先参数 path,否则 _meta/fund_list.json。"""
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    from .fund_universe import get_fund_list_path, load_fund_list
    p = path or get_fund_list_path()
    if not os.path.exists(p):
        return []
    return load_fund_list()


def _score_fund(fund: dict, cat: str, prefs: UserPrefs) -> tuple[float, list[str]]:
    """对单只基金打分(0-100),并返回命中关键词列表(供报告引用)。"""
    name = str(fund.get("name", ""))
    # 优先使用 enrich 后的 ftype;fallback 到 type(历史脏数据)
    ftype = str(fund.get("ftype", "") or fund.get("type", ""))
    is_off = bool(fund.get("is_offexchange", True))
    score = 0.0
    reasons: list[str] = []

    # 0) 场外过滤(用户明确要求场外公募)
    if not is_off:
        return -1.0, ["场内基金,已排除"]

    # 1) 名称关键词匹配(主信号,占 50 分)
    kws = CATEGORY_KEYWORDS.get(cat, ())
    hit = [k for k in kws if k in name]
    if hit:
        score += 50.0
        reasons.append(f"名称含 {cat} 关键词 {hit[:3]}")

    # 2) FTYPE 字段(天天基金分类)与 cat 强关联 — 仅在 ftype 看起来像分类名时加分
    #    防御: 历史脏数据时 type 是数字(累计净值),不能误判。ftype 字段经 enrich 后一定非数字。
    ftype_map = {
        "bond":         ("债券型",),
        "conservative": ("混合型", "二级债基", "偏债", "FOF-稳健", "FOF-保守"),
        "balanced":     ("混合型", "平衡", "FOF-平衡"),
        "equity":       ("股票型", "偏股"),
        "index":        ("指数型", "ETF联接", "增强"),
        "sector":       ("股票型", "混合型", "主题"),
        "overseas":     ("QDII", "海外", "指数型-海外", "QDII-股票"),
        "alternative":  ("另类", "REITs", "商品"),
        "cash":         ("货币型",),
    }
    # 当 ftype 为空时(未 enrich),不进行 ftype 评分,避免误判
    if ftype and not ftype.replace(".", "").replace("-", "").replace(" ", "").isdigit():
        for kw in ftype_map.get(cat, ()):
            if kw in ftype:
                score += 20.0
                reasons.append(f"FTYPE {ftype} 与 {cat} 匹配")
                break
    elif ftype and ftype.replace(".", "").replace("-", "").isdigit():
        # 显式标注 ftype 是脏数据(便于报告引用)
        reasons.append(f"FTYPE 脏数据 ({ftype}),未参与评分")

    # 3) 偏好品类加权
    if cat in prefs.preferred_categories:
        score += 10.0
        reasons.append(f"用户偏好 {cat}")

    # 4) 排除品类扣分
    if cat in prefs.excluded_categories:
        score -= 100.0
        reasons.append(f"用户排除 {cat}")

    # 5) 排除代码
    if fund.get("code") in prefs.excluded_codes:
        score -= 100.0
        reasons.append("用户已显式排除")

    return score, reasons


def screen_replacement_funds(
    categories: list[str],
    prefs: UserPrefs,
    universe_path: str | None = None,
    per_category: int = 5,
    held_codes: set[str] | None = None,
) -> dict[str, list[dict]]:
    """从基金全量库中,为每个 underweight 类别筛选 Top-N 候选基金。

    评分:
    - 名称关键词命中 +50
    - type 字段匹配 +20
    - 用户偏好品类 +10
    - 用户排除品类 -100(直接淘汰)

    返回: {category: [{code, name, type, score, match_reasons}, ...]}
    """
    universe = _load_universe(universe_path)
    held = held_codes or set()
    out: dict[str, list[dict]] = {}

    for cat in categories:
        kws = CATEGORY_KEYWORDS.get(cat, ())
        if not kws:
            out[cat] = []
            continue
        scored: list[tuple[float, dict, list[str]]] = []
        for fund in universe:
            code = str(fund.get("code", ""))
            if code in held:
                continue
            score, reasons = _score_fund(fund, cat, prefs)
            if score <= 0:
                continue
            scored.append((score, fund, reasons))

        scored.sort(key=lambda x: (-x[0], str(x[1].get("name", ""))))
        top = scored[:per_category]
        out[cat] = [
            {
                "code": str(f[1].get("code", "")),
                "name": str(f[1].get("name", "")),
                "type": str(f[1].get("type", "")),
                "score": round(f[0], 1),
                "match_reasons": f[2],
            }
            for f in top
        ]
    return out


# ---------------------------------------------------------------------------
# 5. 端到端:生成再平衡方案
# ---------------------------------------------------------------------------

def build_rebalance_plan(
    positions: list[dict],
    prefs: UserPrefs,
    universe_path: str | None = None,
    per_category: int = 5,
    quality_reports: dict[str, dict] | None = None,
    name_weight: float | None = None,
    quality_weight: float | None = None,
    risk_level: int | None = None,
) -> RebalancePlan:
    """生成完整的再平衡方案。

    1. 持仓分类
    2. 算当前配置
    3. 算目标配置
    4. 算 gap
    5. 从全量场外公募中筛补/换基金
       - 若 quality_reports 传入,调 score_with_quality_reports 融合
    6. 标记需清出的持仓(用户排除品类)
    """
    # 风险等级: 优先参数 > prefs.risk_level > 默认 3
    if risk_level is None:
        risk_level = prefs.risk_level
    classified = classify_positions(positions)
    target = get_target_allocation(prefs)
    total = sum(p.amount for p in classified)
    current, gaps, underweight, overweight = compute_gap(classified, target)

    # 替换候选
    held_codes = {p.code for p in classified}
    raw_replacements = screen_replacement_funds(
        categories=underweight,
        prefs=prefs,
        universe_path=universe_path,
        per_category=per_category,
        held_codes=held_codes,
    )
    if quality_reports:
        replacements = score_with_quality_reports(
            screener_results=raw_replacements,
            quality_reports=quality_reports,
            name_weight=name_weight,
            quality_weight=quality_weight,
            risk_level=risk_level,
        )
    else:
        replacements = raw_replacements

    # 标记需清出的持仓(用户排除品类中的标的 + 出现在 overweight 名单中)
    excluded: list[dict] = []
    excl_set = set(prefs.excluded_categories)
    for p in classified:
        if p.category in excl_set:
            excluded.append({
                "code": p.code,
                "name": p.name,
                "amount": p.amount,
                "category": p.category,
                "reason": f"用户排除品类 {p.category}",
            })
        elif p.category in overweight and p.amount > 0:
            # 减仓(不放进 excluded 严格清仓列表,但写 reason)
            excluded.append({
                "code": p.code,
                "name": p.name,
                "amount": p.amount,
                "category": p.category,
                "reason": f"超配 {p.category},建议减仓",
                "soft": True,
            })

    return RebalancePlan(
        total_amount=round(total, 2),
        target_allocation=target,
        current_allocation=current,
        gaps=gaps,
        underweight=underweight,
        overweight=overweight,
        replacements=replacements,
        excluded_holdings=excluded,
    )


# ---------------------------------------------------------------------------
# 6. 报告渲染(markdown,供 subagent / HTML 模板直接消费)
# ---------------------------------------------------------------------------

def plan_to_markdown(plan: RebalancePlan, prefs: UserPrefs) -> str:
    """把再平衡方案渲染成 markdown,供 portfolio-manager / HTML 模板直接引用。"""
    from .portfolio_prefs import explain_template

    lines: list[str] = []
    lines.append("## 1. 用户偏好与目标配置")
    lines.append("```")
    lines.append(explain_template(prefs, plan.target_allocation))
    lines.append("```")
    lines.append("")

    lines.append("## 2. 资产 gap 矩阵")
    lines.append("| 资产大类 | 当前权重 | 目标权重 | 差额 | 当前金额(¥) | 目标金额(¥) | 调整金额(¥) | 动作 |")
    lines.append("|----------|---------|---------|------|------------|------------|------------|------|")
    for g in plan.gaps:
        if g.current_pct == 0 and g.target_pct == 0:
            continue
        action_cn = {"hold": "维持", "add": "加仓", "trim": "减仓"}.get(g.action, g.action)
        lines.append(
            f"| {g.category} | {g.current_pct:.1%} | {g.target_pct:.1%} | "
            f"{g.delta_pct:+.1%} | {g.current_amount:,.0f} | {g.target_amount:,.0f} | "
            f"{g.delta_amount:+,.0f} | {action_cn} |"
        )
    lines.append("")

    if plan.underweight:
        lines.append("## 3. 需要加仓的资产大类")
        lines.append(", ".join(plan.underweight))
        lines.append("")

    if plan.overweight:
        lines.append("## 4. 需要减仓的资产大类")
        lines.append(", ".join(plan.overweight))
        lines.append("")

    if plan.replacements:
        lines.append("## 5. 推荐补/换基金(国内场外公募)")
        lines.append("")
        for cat, cands in plan.replacements.items():
            if not cands:
                continue
            lines.append(f"### 5.{ASSET_CATEGORIES.index(cat) + 1} {cat}")
            lines.append("| 代码 | 名称 | 类型 | 评分 | 命中理由 |")
            lines.append("|------|------|------|------|----------|")
            for c in cands:
                reasons = "; ".join(c.get("match_reasons", []))
                lines.append(
                    f"| {c['code']} | {c['name']} | {c['type']} | "
                    f"{c['score']:.1f} | {reasons} |"
                )
            lines.append("")

    if plan.excluded_holdings:
        lines.append("## 6. 当前持仓中需关注的标的")
        lines.append("| 代码 | 名称 | 金额(¥) | 资产大类 | 原因 |")
        lines.append("|------|------|---------|---------|------|")
        for e in plan.excluded_holdings:
            soft = "(建议减仓)" if e.get("soft") else "(建议清仓)"
            lines.append(
                f"| {e['code']} | {e['name']} | {e['amount']:,.0f} | "
                f"{e['category']} | {e['reason']} {soft} |"
            )
        lines.append("")

    lines.append("## 7. 调整后目标配置(示意)")
    lines.append("按上述补/换方案执行后,组合应逼近: " + ", ".join(
        f"{c}={plan.target_allocation.get(c, 0):.0%}"
        for c in ASSET_CATEGORIES
        if plan.target_allocation.get(c, 0) > 0
    ))
    lines.append("")
    lines.append("> 本方案基于用户风险偏好 + 目标配置 + 场外公募基金全量库(国内场外)生成,仅供研究参考,不构成投资建议。")
    return "\n".join(lines)
