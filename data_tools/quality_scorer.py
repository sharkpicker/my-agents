"""候选基金深度质量评分器.

从 7 分析师报告 + 辩论报告中规则化抽取质量信号,计算 5 维度质量分,
并与名称匹配分融合,生成最终推荐排序。

5 维度:
- performance (业绩持续性, 30%)
- concentration (重仓股集中度, 20%)
- scale (规模 + 申赎趋势, 20%)
- manager (经理稳定性, 15%)
- policy_sentiment (政策与情绪, 15%)
"""

from __future__ import annotations

import math
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# 常量: 正则、规则表、权重
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

# 5 维度权重(平衡型默认, risk_level=3)
QUALITY_WEIGHTS = {
    "performance": 0.30,
    "concentration": 0.20,
    "scale": 0.20,
    "manager": 0.15,
    "policy_sentiment": 0.15,
}

# v2: 5 档风险等级评分配置
# name_weight: 名称匹配分权重; quality_weight: 质量分权重
# dimension_weights: 质量分内部 5 维度权重
RISK_LEVEL_SCORE_CONFIG: dict[int, dict] = {
    1: {
        "name_weight": 0.20,
        "quality_weight": 0.80,
        "dimension_weights": {
            "performance": 0.20,
            "concentration": 0.25,
            "scale": 0.25,
            "manager": 0.20,
            "policy_sentiment": 0.10,
        },
    },
    2: {
        "name_weight": 0.25,
        "quality_weight": 0.75,
        "dimension_weights": {
            "performance": 0.25,
            "concentration": 0.225,
            "scale": 0.225,
            "manager": 0.175,
            "policy_sentiment": 0.125,
        },
    },
    3: {
        "name_weight": 0.30,
        "quality_weight": 0.70,
        "dimension_weights": {
            "performance": 0.30,
            "concentration": 0.20,
            "scale": 0.20,
            "manager": 0.15,
            "policy_sentiment": 0.15,
        },
    },
    4: {
        "name_weight": 0.35,
        "quality_weight": 0.65,
        "dimension_weights": {
            "performance": 0.35,
            "concentration": 0.175,
            "scale": 0.175,
            "manager": 0.125,
            "policy_sentiment": 0.175,
        },
    },
    5: {
        "name_weight": 0.40,
        "quality_weight": 0.60,
        "dimension_weights": {
            "performance": 0.40,
            "concentration": 0.15,
            "scale": 0.15,
            "manager": 0.10,
            "policy_sentiment": 0.20,
        },
    },
}


def get_score_weights(risk_level: int = 3) -> dict:
    """根据风险等级获取评分权重配置。

    Args:
        risk_level: 1-5 风险等级(1保守, 5激进)

    Returns:
        {name_weight, quality_weight, dimension_weights}
    """
    if risk_level not in RISK_LEVEL_SCORE_CONFIG:
        risk_level = 3
    return RISK_LEVEL_SCORE_CONFIG[risk_level]


# ---------------------------------------------------------------------------
# 单维度抽取函数
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 核心函数: 从报告抽取质量分
# ---------------------------------------------------------------------------


def parse_quality_from_reports(
    code: str,
    reports_dir: str,
    category: str,
    date_str: str,
    risk_level: int = 3,
) -> dict:
    """读 7 分析师 markdown + 辩论 markdown,规则化抽取质量信号。

    Args:
        code: 6 位基金代码
        reports_dir: 报告目录(包含 <code>_<role>.md 文件)
        category: 资产大类(用于报告完整性检查)
        date_str: 日期字符串(用于追溯,目前未使用)
        risk_level: 1-5 风险等级(1保守, 5激进),默认 3 平衡型

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
            "risk_level": int,
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

    # 根据风险等级获取维度权重
    weights = get_score_weights(risk_level)
    dim_weights = weights["dimension_weights"]

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
            "risk_level": risk_level,
        }
    active_total = sum(dim_weights[k] for k in signals if not signals[k]["missing"])
    if active_total <= 0:
        active_total = 1.0
    weighted = 0.0
    for k, w in dim_weights.items():
        if not signals[k]["missing"]:
            weighted += signals[k]["score"] * (w / active_total)

    return {
        "code": code,
        "category": category,
        "quality_score": round(weighted, 2),
        "signals": signals,
        "report_paths": paths,
        "missing_dimensions": missing_dims,
        "risk_level": risk_level,
    }


# ---------------------------------------------------------------------------
# 评分融合: name_score × w_name + quality_score × w_quality
# ---------------------------------------------------------------------------


def score_with_quality_reports(
    screener_results: dict[str, list[dict]],
    quality_reports: dict[str, dict],
    name_weight: float | None = None,
    quality_weight: float | None = None,
    risk_level: int = 3,
) -> dict[str, list[dict]]:
    """融合名称分 + 质量分,按 final_score 降序,返回每类候选。

    Args:
        screener_results: screen_replacement_funds() 原输出
        quality_reports:  parse_quality_from_reports() 输出,key = code
        name_weight: 名称匹配分权重(默认 None,则从 risk_level 推导)
        quality_weight: 质量分权重(默认 None,则从 risk_level 推导)
        risk_level: 1-5 风险等级,用于推导默认权重(默认 3 平衡型)

    Returns:
        {category: [{code, name, type, score, name_score, quality_score,
                     match_reasons, quality_signals, report_paths, quality_missing}]}
    """
    # 若未显式指定权重,则从 risk_level 推导
    if name_weight is None or quality_weight is None:
        weights = get_score_weights(risk_level)
        name_weight = weights["name_weight"]
        quality_weight = weights["quality_weight"]
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
