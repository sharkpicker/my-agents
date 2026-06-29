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
# 5+. 候选基金深度评分(从 7 分析师报告 + 辩论报告中规则化抽取质量信号)
# ---------------------------------------------------------------------------

# 业绩持续性: 排名关键词 → 子分数
_PERFORMANCE_KEYWORDS = [
    ("优秀", 50.0),
    ("良好", 35.0),
    ("一般", 20.0),
    ("不佳", 5.0),
]
_PERF_RANKING_RE = re.compile(r"近\s*([1-5])\s*年[^。\n]*?排名[^\n]*?[:：]\s*([^\n]+)")

# 重仓股集中度: 前十大占比 → 子分数
_CONCENTRATION_RULES = [
    (50.0, 80.0),   # < 50% → 80 分
    (70.0, 60.0),
    (85.0, 40.0),
    (100.0, 20.0),  # 兜底
]
_HOLDING_CONCENTRATION_RE = re.compile(r"前十大重仓占比[^\n]*?[:：]\s*([\d.]+)\s*%")

# 规模: 数字 + 亿
_SCALE_RE = re.compile(r"基金规模[^\n]*?[:：]\s*([\d.]+)\s*亿")
_SCALE_RULES = [
    (10.0, 50.0),
    (2.0, 40.0),
    (0.5, 25.0),
    (0.0, 10.0),
]

# 经理: 任职年限
_MANAGER_TENURE_RE = re.compile(r"基金经理任职年限[^\n]*?[:：]\s*([\d.]+)\s*年")
_MANAGER_TENURE_RULES = [
    (5.0, 70.0),
    (3.0, 50.0),
    (1.0, 30.0),
    (0.0, 10.0),
]

# 申赎趋势
_FLOW_TREND_RE = re.compile(r"近\s*4\s*期趋势[^\n]*?[:：]\s*(\S+)")

# 政策/情绪关键词
_POLICY_GRADE_RE = re.compile(r"政策评级[^\n]*?[:：]\s*(\S+)")
_NEWS_BULL_RE = re.compile(r"利好[:：]\s*(\S+)")
_NEWS_BEAR_RE = re.compile(r"利空[:：]\s*(\S+)")
_SENTIMENT_RE = re.compile(r"情绪[^\n]*?[:：]\s*(\S+)")

# 5 维度权重
QUALITY_WEIGHTS = {
    "performance": 0.30,
    "concentration": 0.20,
    "scale": 0.20,
    "manager": 0.15,
    "policy_sentiment": 0.15,
}


def _extract_performance(md: str) -> tuple[float, dict, bool]:
    """业绩持续性: 综合近 1/3/5 年排名 → 0-100。"""
    if not md:
        return 0.0, {"raw": ""}, True
    matches = _PERF_RANKING_RE.findall(md)
    if not matches:
        return 0.0, {"raw": md[:200]}, True
    scores = []
    details = []
    for year, label in matches:
        for kw, s in _PERFORMANCE_KEYWORDS:
            if kw in label:
                scores.append(s)
                details.append(f"近{year}年:{kw}")
                break
    if not scores:
        return 0.0, {"raw": md[:200]}, True
    avg = sum(scores) / len(scores)
    return avg, {"yearly": details, "avg_score": avg}, False


def _extract_concentration(md: str) -> tuple[float, dict, bool]:
    """重仓股集中度: 前十大占比 → 0-100(越低越好但有下限)。"""
    if not md:
        return 0.0, {"raw": ""}, True
    m = _HOLDING_CONCENTRATION_RE.search(md)
    if not m:
        return 0.0, {"raw": md[:200]}, True
    pct = float(m.group(1))
    score = 20.0
    for threshold, s in sorted(_CONCENTRATION_RULES, key=lambda x: x[0]):
        if pct < threshold:
            score = s
            break
    return score, {"top10_pct": pct, "score": score}, False


def _extract_scale(fundamentals_md: str, flows_md: str) -> tuple[float, dict, bool]:
    """规模 + 趋势: 规模 +10/-10。"""
    if not fundamentals_md:
        return 0.0, {"raw": ""}, True
    m = _SCALE_RE.search(fundamentals_md)
    if not m:
        return 0.0, {"raw": fundamentals_md[:200]}, True
    scale = float(m.group(1))
    base = 10.0
    for threshold, s in sorted(_SCALE_RULES, key=lambda x: -x[0]):
        if scale >= threshold:
            base = s
            break
    # 趋势调整
    trend_adj = 0.0
    if flows_md:
        tm = _FLOW_TREND_RE.search(flows_md)
        if tm:
            trend = tm.group(1)
            if "增" in trend:
                trend_adj = 10.0
            elif "减" in trend:
                trend_adj = -10.0
    final = max(0.0, min(100.0, base + trend_adj))
    return final, {"scale_yi": scale, "trend_adj": trend_adj, "score": final}, False


def _extract_manager(fundamentals_md: str) -> tuple[float, dict, bool]:
    """经理稳定性: 任期 → 0-100。"""
    if not fundamentals_md:
        return 0.0, {"raw": ""}, True
    m = _MANAGER_TENURE_RE.search(fundamentals_md)
    if not m:
        return 0.0, {"raw": fundamentals_md[:200]}, True
    tenure = float(m.group(1))
    base = 10.0
    for threshold, s in sorted(_MANAGER_TENURE_RULES, key=lambda x: -x[0]):
        if tenure >= threshold:
            base = s
            break
    # 经理变更检测
    if "经理变更" in fundamentals_md:
        base = max(0.0, base - 20.0)
    return base, {"tenure_years": tenure, "score": base}, False


def _extract_policy_sentiment(news_md: str, policy_md: str, sentiment_md: str) -> tuple[float, dict, bool]:
    """政策与情绪: 政策评级 + 利好/利空计数 + 情绪,基础 50。"""
    if not (news_md or policy_md or sentiment_md):
        return 0.0, {"raw": ""}, True
    base = 50.0
    details = {}
    # 政策评级
    if policy_md:
        pm = _POLICY_GRADE_RE.search(policy_md)
        if pm:
            grade = pm.group(1)
            if "正面" in grade:
                base += 10.0
                details["policy"] = "正面+10"
            elif "负面" in grade:
                base -= 10.0
                details["policy"] = "负面-10"
            else:
                details["policy"] = "中性"
    # 利好/利空计数
    if news_md:
        bulls = len(_NEWS_BULL_RE.findall(news_md))
        bears = len(_NEWS_BEAR_RE.findall(news_md))
        adj = bulls * 5.0 - bears * 10.0
        base += adj
        details["bulls"] = bulls
        details["bears"] = bears
    # 情绪
    if sentiment_md:
        sm = _SENTIMENT_RE.search(sentiment_md)
        if sm:
            mood = sm.group(1)
            if "乐观" in mood:
                base += 5.0
                details["mood"] = "乐观+5"
            elif "悲观" in mood:
                base -= 5.0
                details["mood"] = "悲观-5"
    final = max(0.0, min(100.0, base))
    return final, details, False


def parse_quality_from_reports(
    code: str,
    reports_dir: str,
    category: str,
    date_str: str,
) -> dict:
    """读 7 分析师 markdown + 辩论 markdown,规则化抽取质量信号。

    Args:
        code: 6 位基金代码
        reports_dir: 报告目录(包含 <code>_<role>.md 文件)
        category: 资产大类(用于报告完整性检查)
        date_str: 日期字符串(用于追溯,目前未使用)

    Returns:
        {
            "code": str,
            "category": str,
            "quality_score": float,  # 0-100
            "signals": {
                "performance": {"score", "details", "missing"},
                "concentration": {"score", "details", "missing"},
                "scale": {"score", "details", "missing"},
                "manager": {"score", "details", "missing"},
                "policy_sentiment": {"score", "details", "missing"},
            },
            "report_paths": dict[str, str],
            "missing_dimensions": list[str],
        }
    """
    base = Path(reports_dir) / code
    ROLES = ["market", "fundamentals", "holdings", "flows", "news", "policy", "sentiment"]
    contents: dict[str, str] = {}
    paths: dict[str, str] = {}
    for role in ROLES:
        p = base / f"{code}_{role}.md"
        if p.exists():
            contents[role] = p.read_text(encoding="utf-8")
            paths[role] = str(p)
        else:
            contents[role] = ""
            paths[role] = ""

    # 5 维度抽取
    perf_score, perf_det, perf_miss = _extract_performance(contents["market"])
    conc_score, conc_det, conc_miss = _extract_concentration(contents["holdings"])
    scale_score, scale_det, scale_miss = _extract_scale(contents["fundamentals"], contents["flows"])
    mgr_score, mgr_det, mgr_miss = _extract_manager(contents["fundamentals"])
    ps_score, ps_det, ps_miss = _extract_policy_sentiment(contents["news"], contents["policy"], contents["sentiment"])

    signals = {
        "performance": {"score": round(perf_score, 2), "details": perf_det, "missing": perf_miss},
        "concentration": {"score": round(conc_score, 2), "details": conc_det, "missing": conc_miss},
        "scale": {"score": round(scale_score, 2), "details": scale_det, "missing": scale_miss},
        "manager": {"score": round(mgr_score, 2), "details": mgr_det, "missing": mgr_miss},
        "policy_sentiment": {"score": round(ps_score, 2), "details": ps_det, "missing": ps_miss},
    }

    # 计算 quality_score: 缺失维度权重归零,其他等比放大
    missing_dims = [k for k, v in signals.items() if v["missing"]]
    if len(missing_dims) == 5:
        return {
            "code": code,
            "category": category,
            "quality_score": 0.0,
            "signals": signals,
            "report_paths": paths,
            "missing_dimensions": missing_dims,
        }
    active_total = sum(QUALITY_WEIGHTS[k] for k in signals if not signals[k]["missing"])
    if active_total <= 0:
        active_total = 1.0
    weighted = 0.0
    for k, w in QUALITY_WEIGHTS.items():
        if not signals[k]["missing"]:
            weighted += signals[k]["score"] * (w / active_total)

    return {
        "code": code,
        "category": category,
        "quality_score": round(weighted, 2),
        "signals": signals,
        "report_paths": paths,
        "missing_dimensions": missing_dims,
    }


# ---------------------------------------------------------------------------
# 5. 评分融合:name_score × w_name + quality_score × w_quality
# ---------------------------------------------------------------------------


def score_with_quality_reports(
    screener_results: dict[str, list[dict]],
    quality_reports: dict[str, dict],
    name_weight: float = 0.3,
    quality_weight: float = 0.7,
) -> dict[str, list[dict]]:
    """STUB: 完整实现在 Task 1.4。"""
    if not math.isclose(name_weight + quality_weight, 1.0, abs_tol=1e-6):
        raise ValueError(f"name_weight + quality_weight must = 1.0, got {name_weight + quality_weight}")
    out = {}
    for cat, cands in screener_results.items():
        new_list = []
        for c in cands:
            code = str(c.get("code", ""))
            name_score = float(c.get("score", 0))
            qr = quality_reports.get(code)
            if qr is None:
                new_list.append({**c, "name_score": name_score, "quality_score": 0.0,
                                 "score": name_score, "quality_signals": None,
                                 "report_paths": None, "quality_missing": True})
            else:
                q_score = float(qr.get("quality_score", 0))
                final = round(name_score * name_weight + q_score * quality_weight, 2)
                new_list.append({**c, "name_score": round(name_score, 2),
                                 "quality_score": round(q_score, 2), "score": final,
                                 "quality_signals": qr.get("signals", {}),
                                 "report_paths": qr.get("report_paths", {}),
                                 "missing_dimensions": qr.get("missing_dimensions", []),
                                 "quality_missing": False})
        new_list.sort(key=lambda x: (-x["score"], str(x.get("name", ""))))
        out[cat] = new_list
    return out


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
) -> RebalancePlan:
    """生成完整的再平衡方案。

    1. 持仓分类
    2. 算当前配置
    3. 算目标配置
    4. 算 gap
    5. 从全量场外公募中筛补/换基金
    6. 标记需清出的持仓(用户排除品类)
    """
    classified = classify_positions(positions)
    target = get_target_allocation(prefs)
    total = sum(p.amount for p in classified)
    current, gaps, underweight, overweight = compute_gap(classified, target)

    # 替换候选
    held_codes = {p.code for p in classified}
    replacements = screen_replacement_funds(
        categories=underweight,
        prefs=prefs,
        universe_path=universe_path,
        per_category=per_category,
        held_codes=held_codes,
    )

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
