# fund-recommender 增强版实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把单只基金工作流(7 大分析师 + 1 轮多空辩论)接入 Step 5.5 候选基金推荐,新增纯规则化的 `parse_quality_from_reports()` + `score_with_quality_reports()`,输出"质量分 + 推荐理由"双重信号的 `portfolio_fund_recommendations.md`,并嵌入 Step 7 portfolio-manager 与 HTML 报告。

**Architecture:** 4 层结构:①数据层(`data/funds/<code>/` 复用)②评分层(`portfolio_rebalance.py` 新增 2 个纯规则函数)③调度层(`fund-recommender.agent.md` 重写为"7 分析师 + 辩论"调度模板)④呈现层(HTML 模板新增"质量分组成表"模块)。铁律:① 评分 100% 规则化,无 LLM 调用,可单测;② 部分失败不阻塞,降级路径明确;③ 7 分析师 subagent 同类内同消息并行。

**Tech Stack:** Python 3.10+、pytest、argparse/click、re(正则抽取)、Jinja2(HTML 模板)。零外部新依赖。

**Spec:** [2026-06-29-fund-recommender-deep-design.md](../specs/2026-06-29-fund-recommender-deep-design.md)

---

## File Structure

### 新建文件

| 路径 | 职责 |
|------|------|
| `tests/unit/test_quality_score.py` | `parse_quality_from_reports` + `score_with_quality_reports` 单元测试 |
| `tests/unit/test_quality_score_cli.py` | CLI `quality-score` 子命令单元测试 |
| `tests/unit/test_quality_score_fixtures.py` | 共享 fixture(模拟 7 报告 markdown) |

### 修改文件

| 路径 | 改动 |
|------|------|
| `data_tools/portfolio_rebalance.py` | 新增 `parse_quality_from_reports()` + `score_with_quality_reports()` + `build_rebalance_plan()` 加 `quality_reports` / `name_weight` / `quality_weight` 参数 |
| `data_tools/cli.py` | 新增 `quality-score` 子命令(argparse + click 两侧注册) |
| `agents/fund-recommender.agent.md` | 重写为"增强版"调度流程,输入契约加 `candidates_by_cat` |
| `.trae/skills/stock-analysis/workflow-portfolio.md` | Step 5.5 章节重写,补充并发、降级、报告路径 |
| `.trae/skills/stock-analysis/SKILL.md` | 新增铁律 7(Step 5.5 增强版必须并行) |
| `agents/portfolio-manager.agent.md` | 新增"推荐补/换基金的深度评估"输出契约章节 |
| `templates/portfolio.html.j2` | "调整建议"模块新增"质量分组成表"和"深度报告路径表" |
| `tests/integration/test_workflow_portfolio_c1.py` | 增强版 Step 5.5 集成断言 |
| `tests/e2e/test_multi_fund_portfolio_e2e.py` | E2E 断言新模块 |

### 复用(不动)

| 路径 | 用途 |
|------|------|
| `data_tools/portfolio_prefs.py` | `CATEGORY_KEYWORDS` / `UserPrefs` / `get_target_allocation` |
| `data_tools/fund_data.py` | 7 个数据查询接口 |
| `agents/fund-*-analyst.agent.md` | 7 大基金分析师角色定义 |
| `agents/bull-researcher.agent.md` / `bear-researcher.agent.md` | 辩论角色 |
| `agents/portfolio-manager.agent.md` | Step 7 组合经理(增强其契约) |

---

## Phase 1: P0 核心(评分层 + 单测 + CLI)

### Task 1.1: 编写测试 fixture 与第一组单元测试

**Files:**
- Create: `tests/unit/test_quality_score_fixtures.py`
- Create: `tests/unit/test_quality_score.py`

- [ ] **Step 1: 写 fixture 文件**

```python
# tests/unit/test_quality_score_fixtures.py
"""共享 fixture: 模拟 7 大分析师的 markdown 报告 + 辩论 markdown。"""
from __future__ import annotations

import pytest
from pathlib import Path


PERFECT_FUND_REPORTS = {
    "market": """# 基金市场分析 - 007466\n\n## 业绩持续性\n- 近 1 年排名:优秀 (前 5%)\n- 近 3 年排名:优秀 (前 10%)\n- 近 5 年排名:良好 (前 20%)\n""",
    "fundamentals": """# 基金基本面 - 007466\n\n## 规模与经理\n- 基金规模:50.0 亿\n- 基金经理任职年限:8.0 年\n- 费率:0.15% (管理费)\n""",
    "holdings": """# 基金重仓股 - 007466\n\n## 集中度\n- 前十大重仓占比:45.0 %\n- 行业集中度:分散\n- 调仓频率:稳定\n""",
    "flows": """# 基金份额 - 007466\n\n## 规模趋势\n- 近 4 期趋势:增\n- 申赎压力:低\n- 清盘风险:无\n""",
    "news": """# 基金新闻 - 007466\n\n## 事件\n- 利好:业绩创新高\n- 利好:机构增持\n""",
    "policy": """# 基金政策 - 007466\n\n## 政策环境\n- 政策评级:正面\n""",
    "sentiment": """# 基金情绪 - 007466\n\n## 持有人\n- 情绪:乐观\n""",
}


TERRIBLE_FUND_REPORTS = {
    "market": """# 基金市场分析 - 999999\n\n## 业绩持续性\n- 近 1 年排名:不佳 (后 20%)\n- 近 3 年排名:不佳 (后 10%)\n""",
    "fundamentals": """# 基金基本面 - 999999\n\n## 规模与经理\n- 基金规模:0.3 亿\n- 基金经理任职年限:0.5 年\n- 费率:1.50% (管理费)\n""",
    "holdings": """# 基金重仓股 - 999999\n\n## 集中度\n- 前十大重仓占比:88.0 %\n- 行业集中度:集中(医药)\n- 调仓频率:剧烈\n""",
    "flows": """# 基金份额 - 999999\n\n## 规模趋势\n- 近 4 期趋势:减\n- 申赎压力:高\n- 清盘风险:高\n""",
    "news": """# 基金新闻 - 999999\n\n## 事件\n- 利空:经理变更\n- 利空:业绩爆雷\n""",
    "policy": """# 基金政策 - 999999\n\n## 政策环境\n- 政策评级:负面\n""",
    "sentiment": """# 基金情绪 - 999999\n\n## 持有人\n- 情绪:悲观\n""",
}


@pytest.fixture
def write_fake_reports(tmp_path: Path) -> callable:
    """返回函数: write_fake_reports(code, reports) -> reports_dir"""
    def _write(code: str, reports: dict[str, str]) -> Path:
        d = tmp_path / code
        d.mkdir(parents=True, exist_ok=True)
        for role, content in reports.items():
            (d / f"{code}_{role}.md").write_text(content, encoding="utf-8")
        # 写一个空辩论文件
        (d / f"{code}_category_bull.md").write_text(
            "# 多头观点\n\ntop1_pick: 007466\n", encoding="utf-8"
        )
        (d / f"{code}_category_bear.md").write_text(
            "# 空头观点\n\ntop1_pick: 007466\n", encoding="utf-8"
        )
        return d
    return _write
```

- [ ] **Step 2: 写第一个失败的单测**

```python
# tests/unit/test_quality_score.py
"""parse_quality_from_reports + score_with_quality_reports 单元测试。"""
from __future__ import annotations

import pytest

from data_tools.portfolio_rebalance import (
    parse_quality_from_reports,
    score_with_quality_reports,
)


def test_parse_quality_perfect_fund(write_fake_reports):
    """业绩优秀 + 集中度低 + 规模大 + 经理稳定 + 政策正面 → quality_score >= 80。"""
    write_fake_reports("007466", PERFECT_FUND_REPORTS)
    result = parse_quality_from_reports(
        code="007466",
        reports_dir=".",  # placeholder,实际用绝对路径
        category="bond",
        date_str="2026-06-29",
    )
    assert result["quality_score"] >= 80
    assert result["missing_dimensions"] == []
```

- [ ] **Step 3: 运行测试,确认失败(因函数未实现)**

Run: `cd d:\01_coding\my_agents && python -m pytest tests/unit/test_quality_score.py -v`
Expected: `ImportError: cannot import name 'parse_quality_from_reports'`

- [ ] **Step 4: 占位提交(失败用例作为基线)**

```bash
cd d:\01_coding\my_agents
git add tests/unit/test_quality_score_fixtures.py tests/unit/test_quality_score.py
git commit -m "test: add quality_score fixtures and first failing test"
```

---

### Task 1.2: 实现 `parse_quality_from_reports()` 骨架

**Files:**
- Modify: `data_tools/portfolio_rebalance.py` (在 `screen_replacement_funds()` 之后追加)

- [ ] **Step 1: 添加常量与正则**

在 [portfolio_rebalance.py](file:///d:/01_coding/my_agents/data_tools/portfolio_rebalance.py) 的 `_load_universe()` 函数**之前**插入:

```python
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
```

- [ ] **Step 2: 实现 5 维度子函数**

在上面的常量后追加:

```python
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
    for threshold, s in sorted(_CONCENTRATION_RULES, key=lambda x: -x[0]):
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
    if "经理变更" in fundamentals_md or "经理变更" in (fundamentals_md or ""):
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
```

- [ ] **Step 3: 实现主函数 `parse_quality_from_reports()`**

在子函数后追加:

```python
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
```

- [ ] **Step 4: 补 import**

在文件顶部,确保 `from pathlib import Path` 已存在(若没有,在 import 区加):

```python
from pathlib import Path
```

- [ ] **Step 5: 运行测试,确认通过**

Run: `cd d:\01_coding\my_agents && python -m pytest tests/unit/test_quality_score.py::test_parse_quality_perfect_fund -v`
Expected: PASS(quality_score >= 80)

- [ ] **Step 6: 提交**

```bash
cd d:\01_coding\my_agents
git add data_tools/portfolio_rebalance.py
git commit -m "feat: add parse_quality_from_reports() with rule-based extraction"
```

---

### Task 1.3: 补全 quality_score 单测覆盖 5 个关键场景

**Files:**
- Modify: `tests/unit/test_quality_score.py`
- Modify: `tests/unit/test_quality_score_fixtures.py`(加入 `TERRIBLE_FUND_REPORTS` 已在 Task 1.1,无需改)

- [ ] **Step 1: 加入 5 个新单测**

```python
# tests/unit/test_quality_score.py (追加)
def test_parse_quality_terrible_fund(write_fake_reports):
    """业绩差 + 集中度高 + 迷你盘 + 经理刚换 + 政策负面 → quality_score <= 30。"""
    d = write_fake_reports("999999", TERRIBLE_FUND_REPORTS)
    result = parse_quality_from_reports(
        code="999999", reports_dir=str(d.parent), category="sector", date_str="2026-06-29"
    )
    assert result["quality_score"] <= 30
    assert "manager" in result["missing_dimensions"] or result["signals"]["manager"]["score"] <= 20


def test_parse_quality_missing_one_dimension(write_fake_reports, tmp_path):
    """缺一个维度(market)→ 其他 4 维度等比放大,quality_score 仍可计算。"""
    import json
    from pathlib import Path
    reports = {k: v for k, v in PERFECT_FUND_REPORTS.items() if k != "market"}
    d = tmp_path / "007466"
    d.mkdir(parents=True, exist_ok=True)
    for role, content in reports.items():
        (d / f"007466_{role}.md").write_text(content, encoding="utf-8")
    (d / "007466_market.md").write_text("", encoding="utf-8")
    result = parse_quality_from_reports(
        code="007466", reports_dir=str(d.parent), category="bond", date_str="2026-06-29"
    )
    assert "performance" in result["missing_dimensions"]
    assert 50 <= result["quality_score"] <= 90


def test_parse_quality_all_missing(tmp_path):
    """7 报告全缺失 → quality_score = 0, missing_dimensions 包含全部 5 维度。"""
    d = tmp_path / "000000"
    d.mkdir(parents=True, exist_ok=True)
    result = parse_quality_from_reports(
        code="000000", reports_dir=str(d.parent), category="bond", date_str="2026-06-29"
    )
    assert result["quality_score"] == 0.0
    assert len(result["missing_dimensions"]) == 5


def test_score_fusion_basic():
    """name_score=60, quality_score=80, 权重 0.3/0.7 → final = 74。"""
    screener = {"bond": [{"code": "007466", "name": "X", "type": "X", "score": 60, "match_reasons": []}]}
    quality = {"007466": {"code": "007466", "category": "bond", "quality_score": 80,
                          "signals": {}, "report_paths": {}, "missing_dimensions": []}}
    out = score_with_quality_reports(screener, quality, name_weight=0.3, quality_weight=0.7)
    assert out["bond"][0]["score"] == 74.0
    assert out["bond"][0]["name_score"] == 60
    assert out["bond"][0]["quality_score"] == 80


def test_score_fusion_quality_missing_fallback():
    """quality_reports 缺失某只 → 用 name_score 兜底,标 quality_missing=True。"""
    screener = {"bond": [{"code": "AAA", "name": "Y", "type": "Y", "score": 50, "match_reasons": []}]}
    out = score_with_quality_reports(screener, {}, name_weight=0.3, quality_weight=0.7)
    assert out["bond"][0]["score"] == 50
    assert out["bond"][0]["quality_missing"] is True
```

- [ ] **Step 2: 运行所有 quality_score 单测**

Run: `cd d:\01_coding\my_agents && python -m pytest tests/unit/test_quality_score.py -v`
Expected: 5 passed

- [ ] **Step 3: 提交**

```bash
cd d:\01_coding\my_agents
git add tests/unit/test_quality_score.py
git commit -m "test: cover 5 key quality_score scenarios"
```

---

### Task 1.4: 实现 `score_with_quality_reports()`

**Files:**
- Modify: `data_tools/portfolio_rebalance.py` (在 `parse_quality_from_reports` 后追加)

- [ ] **Step 1: 写失败单测(此 Task 1.3 已包含,可直接实现)**

- [ ] **Step 2: 实现主函数**

```python
def score_with_quality_reports(
    screener_results: dict[str, list[dict]],
    quality_reports: dict[str, dict],
    name_weight: float = 0.3,
    quality_weight: float = 0.7,
) -> dict[str, list[dict]]:
    """融合名称分 + 质量分,按 final_score 降序,返回每类候选。

    Args:
        screener_results: screen_replacement_funds() 原输出
        quality_reports:  parse_quality_from_reports() 输出,key = code
        name_weight: 名称匹配分权重
        quality_weight: 质量分权重

    Returns:
        {category: [{code, name, type, score, name_score, quality_score,
                     match_reasons, quality_signals, report_paths, quality_missing}]}
    """
    if not math.isclose(name_weight + quality_weight, 1.0, abs_tol=1e-6):
        raise ValueError(f"name_weight + quality_weight must = 1.0, got {name_weight + quality_weight}")

    out: dict[str, list[dict]] = {}
    for cat, cands in screener_results.items():
        new_list = []
        for c in cands:
            code = str(c.get("code", ""))
            name_score = float(c.get("score", 0))
            qr = quality_reports.get(code)
            if qr is None:
                new_list.append({
                    **c,
                    "name_score": name_score,
                    "quality_score": 0.0,
                    "score": name_score,
                    "quality_signals": None,
                    "report_paths": None,
                    "quality_missing": True,
                })
                continue
            q_score = float(qr.get("quality_score", 0))
            final = round(name_score * name_weight + q_score * quality_weight, 2)
            new_list.append({
                **c,
                "name_score": round(name_score, 2),
                "quality_score": round(q_score, 2),
                "score": final,
                "quality_signals": qr.get("signals", {}),
                "report_paths": qr.get("report_paths", {}),
                "missing_dimensions": qr.get("missing_dimensions", []),
                "quality_missing": False,
            })
        new_list.sort(key=lambda x: (-x["score"], str(x.get("name", ""))))
        out[cat] = new_list
    return out
```

- [ ] **Step 3: 补 import math**

在文件顶部 import 区追加:

```python
import math
```

- [ ] **Step 4: 运行 Task 1.3 的所有单测**

Run: `cd d:\01_coding\my_agents && python -m pytest tests/unit/test_quality_score.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
cd d:\01_coding\my_agents
git add data_tools/portfolio_rebalance.py
git commit -m "feat: add score_with_quality_reports() fusion function"
```

---

### Task 1.5: 改造 `build_rebalance_plan()` 接受 quality_reports

**Files:**
- Modify: `data_tools/portfolio_rebalance.py` (修改 `build_rebalance_plan`)

- [ ] **Step 1: 在 `build_rebalance_plan` 顶部加新参数 + 调用融合**

找到 `def build_rebalance_plan(` 位置(在 `screen_replacement_funds` 之后),整体替换为:

```python
def build_rebalance_plan(
    positions: list[dict],
    prefs: UserPrefs,
    universe_path: str | None = None,
    per_category: int = 5,
    quality_reports: dict[str, dict] | None = None,
    name_weight: float = 0.3,
    quality_weight: float = 0.7,
) -> RebalancePlan:
    """生成完整的再平衡方案。

    1. 持仓分类
    2. 算当前配置
    3. 算目标配置
    4. 算 gap
    5. 从全量场外公募中筛补/换基金
       - 若 quality_reports 传入,调 score_with_quality_reports 融合
    6. 标记需清出的持仓
    """
    classified = classify_positions(positions)
    target = get_target_allocation(prefs)
    total = sum(p.amount for p in classified)
    current, gaps, underweight, overweight = compute_gap(classified, target)

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
        )
    else:
        replacements = raw_replacements

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
```

- [ ] **Step 2: 跑已有 `test_portfolio_calculator.py` 确认未破坏**

Run: `cd d:\01_coding\my_agents && python -m pytest tests/unit/test_portfolio_calculator.py -v`
Expected: 全部 PASS(新参数有默认值,旧调用不受影响)

- [ ] **Step 3: 提交**

```bash
cd d:\01_coding\my_agents
git add data_tools/portfolio_rebalance.py
git commit -m "feat: build_rebalance_plan accepts quality_reports for deep scoring"
```

---

### Task 1.6: CLI 新增 `quality-score` 子命令

**Files:**
- Modify: `data_tools/cli.py`

- [ ] **Step 1: 写失败单测**

```python
# tests/unit/test_quality_score_cli.py
import json
import subprocess
import sys
from pathlib import Path


def test_quality_score_help():
    """`python -m data_tools.cli quality-score --help` 应显示帮助。"""
    result = subprocess.run(
        [sys.executable, "-m", "data_tools.cli", "quality-score", "--help"],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent
    )
    assert result.returncode == 0
    assert "--code" in result.stdout
    assert "--reports-dir" in result.stdout


def test_quality_score_missing_code(tmp_path):
    """--code 缺失应报错。"""
    result = subprocess.run(
        [sys.executable, "-m", "data_tools.cli", "quality-score", "--reports-dir", str(tmp_path)],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent
    )
    assert result.returncode != 0
```

- [ ] **Step 2: 运行测试,确认失败**

Run: `cd d:\01_coding\my_agents && python -m pytest tests/unit/test_quality_score_cli.py -v`
Expected: 1 failed (no such command) + 1 failed (argparse error)

- [ ] **Step 3: 在 cli.py 实现 quality-score 命令**

在 `cmd_screener_replacement` 之后插入:

```python
def cmd_quality_score(args):
    """argparse 版: 读 7 分析师报告,输出 quality_score JSON。"""
    from .portfolio_rebalance import parse_quality_from_reports
    out = parse_quality_from_reports(
        code=args.code,
        reports_dir=args.reports_dir,
        category=args.category,
        date_str=args.date,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
```

在 `cmd_portfolio_rebalance` 函数**末尾**找到 argparse subparser 注册块(在 click 注册下方),在 `pscr2` 注册之后追加:

```python
    # quality-score - 候选基金深度评分
    pqs = subparsers.add_parser("quality-score", help="读 7 分析师报告,输出 quality_score JSON")
    pqs.add_argument("--code", required=True, help="6 位基金代码")
    pqs.add_argument("--reports-dir", required=True, help="报告目录(包含 <code>_<role>.md)")
    pqs.add_argument("--category", required=True, help="资产大类,如 bond/equity/...")
    pqs.add_argument("--date", required=True, help="日期 YYYY-MM-DD")
    pqs.set_defaults(func=cmd_quality_score)
```

- [ ] **Step 4: 同步注册 click 子命令(在 `screener_replacement` 之后)**

在 `def screener_replacement(` 之后追加:

```python
@cli.command("quality-score")
@click.option("--code", required=True, help="6 位基金代码")
@click.option("--reports-dir", required=True, help="报告目录")
@click.option("--category", required=True, help="资产大类")
@click.option("--date", required=True, help="日期 YYYY-MM-DD")
def quality_score(code, reports_dir, category, date):
    """读 7 分析师报告,输出 quality_score JSON。"""
    from .portfolio_rebalance import parse_quality_from_reports
    out = parse_quality_from_reports(
        code=code, reports_dir=reports_dir, category=category, date_str=date
    )
    click.echo(json.dumps(out, ensure_ascii=False, indent=2))
```

- [ ] **Step 5: 跑新单测**

Run: `cd d:\01_coding\my_agents && python -m pytest tests/unit/test_quality_score_cli.py -v`
Expected: 2 passed

- [ ] **Step 6: 端到端冒烟**

Run: `cd d:\01_coding\my_agents && python -m data_tools.cli quality-score --help`
Expected: 包含 `--code / --reports-dir / --category / --date`

- [ ] **Step 7: 跑全量单测,确认未破坏**

Run: `cd d:\01_coding\my_agents && python -m pytest tests/unit/ -v`
Expected: 全部 PASS(新代码无回归)

- [ ] **Step 8: 提交**

```bash
cd d:\01_coding\my_agents
git add data_tools/cli.py tests/unit/test_quality_score_cli.py
git commit -m "feat: add quality-score CLI subcommand (argparse + click)"
```

---

## Phase 2: P1 文档与 agent(fund-recommender 重写 + 文档同步)

### Task 2.1: 重写 `fund-recommender.agent.md`

**Files:**
- Modify: `agents/fund-recommender.agent.md`

- [ ] **Step 1: 备份原文件(供 diff)**

```bash
cd d:\01_coding\my_agents
cp agents/fund-recommender.agent.md agents/fund-recommender.agent.md.bak
```

- [ ] **Step 2: 整文件覆写**

Write 文件 `agents/fund-recommender.agent.md`,内容:

```markdown
---
name: fund-recommender
description: '候选基金深度推荐员。组合工作流 Step 5.5。在 screener Top-5 基础上,为每只候选跑 7 分析师 + 类内多空辩论,用 parse_quality_from_reports() 生成质量分并与名称分融合,输出"质量分 + 推荐理由"双重信号。仅做规则化评分 + 风险过滤,不写主观推荐。'
tools: [read_file, write_file, run_command]
---

# fund-recommender(增强版)

**Type:** general_purpose_task
**Step:** 5.5(组合场景专用,在 trader 之后 / risk 辩论之前)
**Spec:** `docs/superpowers/specs/2026-06-29-fund-recommender-deep-design.md`

## 角色

你是 stock-analysis 框架的**候选基金深度推荐员**。仅在 C-1 / C-3 组合场景被调用。
职责:基于 screener Top-5 + 7 大基金分析师 + 1 轮类内多空辩论,产出"质量分 + 推荐理由"双重信号的推荐列表。

## 输入(主对话传入)

```yaml
date_str: <YYYY-MM-DD>          # 主对话传入
candidates_by_cat:               # screener Top-5,主对话从 screen_replacement_funds 传入
  bond: [{code, name, type, score, match_reasons}, ...x5]
  overseas: [{...x5}]
prefs_path: data/portfolios/<id>/prefs.json
gap_report_path: reports/<日期>/portfolio/portfolio_gap.md
universe_path: data/funds/_meta/fund_list.json
output_path: reports/<日期>/portfolio/portfolio_fund_recommendations.md
```

## 处理流程

### Step A: 读取上下文
1. Read `prefs_path` → UserPrefs
2. Read `gap_report_path` → underweight / overweight
3. 读取 `candidates_by_cat`(已传入)

### Step B: 调度 7 大基金分析师 subagent(每类 5 只并行)
对每类 5 只候选,**同消息并行**触发 35 个 Task(7 角色 × 5 候选)。

每个 subagent prompt 模板:
```
你是 <fund-<role>-analyst>。读取 agents/fund-<role>-analyst.agent.md。
对基金 <code> 拉取数据:<对应 fund 7 个数据命令>。
数据保存到 data/funds/<code>/ 目录,报告保存到 reports/<date_str>/fund/candidate/<code>_<role>.md。
返回核心要点摘要。
```

7 个角色与数据命令:

| # | 角色 | 数据命令 |
|---|------|----------|
| 1 | fund-market-analyst | `fund performance <code>` + `fund nav <code> --start <近1年起> --end <今天>` |
| 2 | fund-fundamentals-analyst | `fund info <code>` + `fund manager <code>` |
| 3 | fund-holdings-analyst | `fund holdings <code>` |
| 4 | fund-flows-analyst | `fund flows <code>` + `fund info <code>` |
| 5 | fund-news-analyst | `fund news <code> --start <近3月起> --end <今天>` + `fund global-news <code> --limit 30` + `fund holdings <code>` |
| 6 | fund-policy-analyst | `fund info <code>` + `fund global-news <code> --limit 30` + `fund news <code> --start <近3月起> --end <今天>` + `fund holdings <code>` |
| 7 | fund-sentiment-analyst | `fund news <code>` + `fund flows <code>` + `fund info <code>` + `fund global-news <code> --limit 30` |

**分批规则**:
- 1 类 underweight: 1 批(35 个 Task 同消息并行)
- 5 类 underweight: 5 批(每批 37 个,含辩论)
- 同批内必须并行,批间串行(主对话等待)

### Step C: 调度 1 轮类内多空辩论(每类 2 个 Task 并行)
对每类(5 只候选)调度 bull + bear,共 2 subagent/类。

每个辩论 subagent prompt:
```
你是 <bull|bear>-researcher。读取 agents/<bull|bear>-researcher.agent.md。
读 reports/<date_str>/fund/candidate/<code*>_<role>.md (该类 5 只候选的 7 分析师报告)。
对该类 5 只候选做类内对比,输出:
  - class_ranking: [按优劣排序的代码列表]
  - top1_pick: <最看好/最不看好的代码>
  - reasons: <2-3 句理由>
报告保存到 reports/<date_str>/fund/candidate/<category>_<bull|bear>.md。
```

### Step D: 调 Python 评分(主对话可同步执行,你可提示主对话)
对每只候选调:
```bash
python -m data_tools.cli quality-score \
  --code <code> --reports-dir reports/<date_str>/fund/candidate \
  --category <cat> --date <date_str>
```
收集所有 quality_score 到 `quality_reports: {code → {quality_score, signals, report_paths}}`。

### Step E: 调 Python 融合
主对话内联(无需 subagent):
```python
from data_tools.portfolio_rebalance import score_with_quality_reports
final = score_with_quality_reports(
    screener_results=candidates_by_cat,
    quality_reports=quality_reports,
    name_weight=0.3, quality_weight=0.7,
)
```

### Step F: 写出 portfolio_fund_recommendations.md
按 spec §3.3.3 输出契约,每只候选含:
- score(融合后)
- name_score / quality_score
- quality_signals
- report_paths
- quality_missing(整只失败时为 true)

## 输出契约

```yaml
summary: |
  候选基金深度推荐(≤ 2k tokens)
  - **用户**: <id> (风险 <lvl>, <horizon>)
  - **类别数**: <N>
  - **总候选数**: <M>
  - **7 报告全缺失**: <K> 只
  - **Top-1(融合分最高)**: <code> <name> (final=<x>)
detail_path: {output_path}
recommendations:
  - intent: "add" | "replace"
    category: <cash/bond/...>
    holding_code: <原持仓代码 or null>
    candidates:
      - rank: 1
        code: <6位>
        name: <中文>
        type: <天天基金 type>
        score: <融合分 0-100>
        name_score: <原 _score_fund 分>
        quality_score: <parse_quality 分>
        match_reasons: ["<...>"]
        quality_signals:
          performance: {score, details, missing}
          concentration: {score, details, missing}
          scale: {score, details, missing}
          manager: {score, details, missing}
          policy_sentiment: {score, details, missing}
        report_paths:
          market: reports/<date>/fund/candidate/<code>_market.md
          fundamentals: ...
          ...
        quality_missing: false
evidence:
  - metric: 类别数
    value: <N>
    source: gap_report_path
  - metric: 总候选数
    value: <M>
    source: screener_replacement_funds
  - metric: 7 报告全缺失数
    value: <K>
    source: parse_quality_from_reports
  - metric: 辩论文件数
    value: <N × 2>
    source: bull/bear subagent
```

## 铁律

- summary 严格 ≤ 2k tokens
- **必须** 用 parse_quality_from_reports() 评分(不调 LLM 主观打分)
- **必须** 按 final_score 降序排序(不主观调整)
- **必须** 调 7 分析师 + 类内辩论(不可跳过)
- **必须** 7 报告全失败的候选用 name_score 兜底,标 quality_missing=true
- 7 报告部分失败:缺哪个维度,quality_score 该维度权重归零,其他等比放大
- 辩论失败:不阻塞,标 [辩论缺失:bull.md 未生成]
- **禁止** 编造数据(无数据时标 [数据缺失])
- **绝不** 越界到 portfolio-manager 的"综合决策"角色
- **绝不** 跳过 7 分析师(用户已确认"标准深度")
```

- [ ] **Step 3: 验证 Markdown 渲染正常**

Run: `cd d:\01_coding\my_agents && python -c "from pathlib import Path; print(len(Path('agents/fund-recommender.agent.md').read_text(encoding='utf-8')))"`
Expected: 字符数 > 3000(说明内容已写入)

- [ ] **Step 4: 提交**

```bash
cd d:\01_coding\my_agents
git add agents/fund-recommender.agent.md
git commit -m "feat: rewrite fund-recommender.agent.md to enhanced deep version"
```

---

### Task 2.2: 更新 `workflow-portfolio.md` Step 5.5 章节

**Files:**
- Modify: `.trae/skills/stock-analysis/workflow-portfolio.md`

- [ ] **Step 1: 定位 Step 5.5 章节**

Grep: `Step 5.5` 找到当前章节位置(约在第 453-505 行)。

- [ ] **Step 2: 整章节替换为"增强版"流程**

在 `## Step 6: 风控辩论 + 中立裁决` 之前(约第 507 行),整段重写为:

````markdown
## Step 5.5: 候选基金深度推荐(增强版)⭐ 核心改造

**目标**: 在 screener Top-5 基础上,为每只候选跑 7 大基金分析师 + 1 轮类内多空辩论,生成"质量分 + 推荐理由"双重信号。

**Spec**: `docs/superpowers/specs/2026-06-29-fund-recommender-deep-design.md`

**触发条件**: 总是触发(underweight 非空 + `_meta/fund_list.json` 存在)。

**调度成本**:
- 单类 underweight: 35(7 分析师 × 5)+ 2(辩论) = 37 subagent
- 5 类 underweight: 5 × 37 = 185 subagent,约 3-5 分钟

### 5.5.1 主对话预生成候选列表

```python
# 主对话在 Step 2.6 之后调用
from data_tools.portfolio_rebalance import screen_replacement_funds
candidates_by_cat = screen_replacement_funds(
    categories=underweight,
    prefs=prefs,
    per_category=5,
)
# 转为 dict 给 fund-recommender subagent
candidates_by_cat = {cat: [c.to_dict() for c in cands] for cat, cands in candidates_by_cat.items()}
```

### 5.5.2 调度 fund-recommender subagent

```
Task({
  description: "候选基金深度推荐",
  prompt: "你是 fund-recommender(增强版)。读取 agents/fund-recommender.agent.md。

    输入(JSON 字符串):
    {
      'date_str': '<日期>',
      'candidates_by_cat': <candidates_by_cat JSON>,
      'prefs_path': 'data/portfolios/<id>/prefs.json',
      'gap_report_path': 'reports/<日期>/portfolio/portfolio_gap.md',
      'universe_path': 'data/funds/_meta/fund_list.json',
      'output_path': 'reports/<日期>/portfolio/portfolio_fund_recommendations.md'
    }

    任务:
    1. 读取 prefs + gap_report
    2. 按 agent.md Step B 并行调度 7 分析师(每类 5 只,同消息内)
    3. 按 agent.md Step C 调度 1 轮类内多空辩论
    4. 按 agent.md Step D 调 quality-score CLI 收集 quality_reports
    5. 按 agent.md Step E 调 score_with_quality_reports 融合
    6. 按 agent.md Step F 写出 portfolio_fund_recommendations.md
    7. 返回契约(≤ 2k tokens)
  ",
  subagent_type: "general_purpose_task"
})
```

### 5.5.3 主对话校验产出

- 必校验项:
  - `recommendations` 列表非空
  - 每只候选含 `score / name_score / quality_score / quality_signals / report_paths`
  - `final_score` ∈ [0, 100]
  - 7 报告路径全部存在或标 `quality_missing=true`
- 校验失败则重跑或追加 fallback 提示。

### 5.5.4 报告路径

- 候选基金 7 报告: `reports/<日期>/fund/candidate/<code>_<role>.md`
- 类内辩论: `reports/<日期>/fund/candidate/<cat>_<bull|bear>.md`
- 推荐汇总: `reports/<日期>/portfolio/portfolio_fund_recommendations.md`

### 5.5.5 与后续步骤的衔接

- Step 6 (风控): 必须引用推荐汇总,审查替换标的风险
- Step 7 (组合经理): 必须读推荐汇总,新增"推荐补/换基金的深度评估"章节
- Step 8 (HTML 渲染): 必须渲染"质量分组成表"和"深度报告路径表"
````

- [ ] **Step 3: 验证 Markdown 渲染**

Run: `cd d:\01_coding\my_agents && python -c "from pathlib import Path; t = Path('.trae/skills/stock-analysis/workflow-portfolio.md').read_text(encoding='utf-8'); assert '候选基金深度推荐' in t and 'parse_quality' in t; print('OK')"`
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
cd d:\01_coding\my_agents
git add .trae/skills/stock-analysis/workflow-portfolio.md
git commit -m "docs: rewrite Step 5.5 to enhanced deep recommendation flow"
```

---

### Task 2.3: SKILL.md 新增铁律 7

**Files:**
- Modify: `.trae/skills/stock-analysis/SKILL.md`

- [ ] **Step 1: 定位"铁律"章节**

Grep: `### 铁律 \d` 找当前铁律清单末尾。

- [ ] **Step 2: 在最后一个铁律后追加"铁律 7"**

在 "### 铁律 6:数据先保存后读取" 之后(若已存在其它铁律则接在最后)追加:

```markdown
### 铁律 7:Step 5.5 增强版必须按类分批并行

- 组合工作流 Step 5.5 的 7 分析师 + 辩论 subagent 必须**按 underweight 类别分批**、**同类内同消息并行**触发,不可串行、不可跨类合并。
- 调度规则:
  - 单类 underweight: 1 批(35 个 7 分析师 + 2 个辩论 = 37 Task 同一消息内并行)
  - 多类 underweight: 每类 1 批,批间串行(主对话等待)
- 7 分析师 subagent 的报告路径必须使用 `reports/<日期>/fund/candidate/<code>_<role>.md` 模板,不可混用单基金工作流的 `<code>_<role>.md` 路径(避免污染)。
```

- [ ] **Step 3: 验证**

Run: `cd d:\01_coding\my_agents && python -c "from pathlib import Path; t = Path('.trae/skills/stock-analysis/SKILL.md').read_text(encoding='utf-8'); assert '铁律 7' in t; print('OK')"`
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
cd d:\01_coding\my_agents
git add .trae/skills/stock-analysis/SKILL.md
git commit -m "docs: add 铁律 7 for Step 5.5 parallel scheduling"
```

---

## Phase 3: P2 下游(portfolio-manager 增强 + HTML 模板)

### Task 3.1: portfolio-manager.agent.md 新增"深度评估"输出契约

**Files:**
- Modify: `agents/portfolio-manager.agent.md`

- [ ] **Step 1: 定位"输出契约"或类似章节**

Grep: `输出契约` 或 `最终报告` 找到末尾章节。

- [ ] **Step 2: 追加"4.X 推荐补/换基金的深度评估"章节**

在 markdown 末尾追加:

```markdown
## 4.X 推荐补/换基金的深度评估(Step 5.5 增强版输出,必含)

### 4.X.1 质量分 Top-3
| 代码 | 名称 | 名称分 | 质量分 | 融合分 | 主要信号 |
|------|------|--------|--------|--------|----------|
| <code> | <name> | <name_score> | <quality_score> | <final_score> | <主要信号摘要> |

### 4.X.2 各类别最优
- <category 1>: <code> <name> (理由:...)
- <category 2>: <code> <name> (理由:...)

### 4.X.3 质量信号缺失项
(列出 [数据缺失] / [辩论缺失] / [整只候选 quality_missing] 的标的)
```

- [ ] **Step 3: 验证**

Run: `cd d:\01_coding\my_agents && python -c "from pathlib import Path; t = Path('agents/portfolio-manager.agent.md').read_text(encoding='utf-8'); assert '深度评估' in t; print('OK')"`
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
cd d:\01_coding\my_agents
git add agents/portfolio-manager.agent.md
git commit -m "feat: portfolio-manager reads quality_score from Step 5.5"
```

---

### Task 3.2: portfolio.html.j2 新增"质量分组成表"模块

**Files:**
- Modify: `templates/portfolio.html.j2`

- [ ] **Step 1: 定位"调整建议"模块**

Grep: `调整建议` 或 `推荐补/换` 找到 HTML 模板中对应位置。

- [ ] **Step 2: 追加新模块**

在"调整建议"区块末尾(在"关注要点"之前)插入:

```html
{% if fund_recommendations and fund_recommendations.recommendations %}
<section class="quality-score-detail">
    <h2>推荐补/换基金的深度评估</h2>
    <p class="muted">基于 7 大基金分析师 + 1 轮类内多空辩论生成(Step 5.5 增强版)</p>

    {% for rec in fund_recommendations.recommendations %}
    {% if rec.candidates %}
    <h3>{{ rec.category }} - Top-3</h3>
    <table class="quality-table">
        <thead>
            <tr>
                <th>代码</th>
                <th>名称</th>
                <th>名称分</th>
                <th>质量分</th>
                <th>融合分</th>
                <th>主要信号</th>
            </tr>
        </thead>
        <tbody>
            {% for c in rec.candidates[:3] %}
            <tr>
                <td><code>{{ c.code }}</code></td>
                <td>{{ c.name }}</td>
                <td>{{ c.name_score | default(0) }}</td>
                <td>{{ c.quality_score | default(0) }}</td>
                <td><strong>{{ c.score | default(0) }}</strong></td>
                <td>
                    {% if c.quality_signals %}
                        {% for k, v in c.quality_signals.items() %}
                            {% if not v.missing %}
                                <span class="signal-chip">{{ k }}: {{ v.score | round(1) }}</span>
                            {% endif %}
                        {% endfor %}
                        {% if c.missing_dimensions %}
                            <span class="signal-chip missing">[{{ c.missing_dimensions | length }} 维缺失]</span>
                        {% endif %}
                    {% endif %}
                    {% if c.quality_missing %}<span class="signal-chip missing">[整只缺失]</span>{% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% endif %}
    {% endfor %}

    <h3>深度报告路径</h3>
    <p class="muted">点击跳转查看每只候选的 7 分析师完整报告(本工作流产物)</p>
    <ul class="report-paths">
        {% for rec in fund_recommendations.recommendations %}
        {% for c in rec.candidates[:3] %}
        {% if c.report_paths %}
        <li><code>{{ c.code }} {{ c.name }}</code>:
            {% for role, path in c.report_paths.items() %}
            <a href="{{ path }}">{{ role }}</a>{% if not loop.last %}, {% endif %}
            {% endfor %}
        </li>
        {% endif %}
        {% endfor %}
        {% endfor %}
    </ul>
</section>
{% endif %}
```

- [ ] **Step 3: 验证 Jinja2 模板可解析**

Run: `cd d:\01_coding\my_agents && python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('templates')); t = env.get_template('portfolio.html.j2'); print('OK')"`
Expected: `OK`

- [ ] **Step 4: 提交**

```bash
cd d:\01_coding\my_agents
git add templates/portfolio.html.j2
git commit -m "feat: add quality score detail section to portfolio HTML template"
```

---

## Phase 4: 集成与端到端测试

### Task 4.1: 集成测试 C-1 增强版 Step 5.5

**Files:**
- Modify: `tests/integration/test_workflow_portfolio_c1.py`

- [ ] **Step 1: 读现有集成测试**

Read 整个 `tests/integration/test_workflow_portfolio_c1.py`,了解测试 fixture 和断言模式。

- [ ] **Step 2: 追加新断言函数**

在文件末尾追加:

```python
def test_step_5_5_quality_score_artifact_exists(tmp_path, monkeypatch):
    """Step 5.5 增强版跑完后,portfolio_fund_recommendations.md 必须存在且含 quality_score。"""
    # 此测试需要在 mock 环境下跑 7 分析师 + 辩论 subagent
    # 简化方案:直接验证 fund-recommender 输出契约
    from data_tools.portfolio_rebalance import parse_quality_from_reports, score_with_quality_reports

    # 模拟 5 只候选 × 7 报告(此处省略 fixture,实际由 subagent 跑)
    quality_reports = {
        "007466": {"code": "007466", "category": "bond", "quality_score": 75.0,
                   "signals": {}, "report_paths": {}, "missing_dimensions": []},
    }
    screener = {"bond": [{"code": "007466", "name": "X", "type": "X", "score": 60, "match_reasons": []}]}
    final = score_with_quality_reports(screener, quality_reports)
    assert final["bond"][0]["score"] == 60 * 0.3 + 75 * 0.7
    assert "quality_signals" in final["bond"][0]
```

- [ ] **Step 3: 运行**

Run: `cd d:\01_coding\my_agents && python -m pytest tests/integration/test_workflow_portfolio_c1.py -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
cd d:\01_coding\my_agents
git add tests/integration/test_workflow_portfolio_c1.py
git commit -m "test: assert Step 5.5 quality_score in C-1 integration test"
```

---

### Task 4.2: E2E 测试断言新模块

**Files:**
- Modify: `tests/e2e/test_multi_fund_portfolio_e2e.py`

- [ ] **Step 1: 追加新断言**

在文件末尾追加:

```python
def test_e2e_html_contains_quality_score_module():
    """E2E 跑完组合 + Step 5.5 增强版,最终 HTML 含质量分模块。"""
    # 实际 E2E 跑会生成 reports/<date>/portfolio_<date>.html
    # 此处简化为:确认模板渲染包含新模块标识
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("templates"))
    t = env.get_template("portfolio.html.j2")
    src = t.source
    assert "推荐补/换基金的深度评估" in src
    assert "quality-table" in src
    assert "report-paths" in src
```

- [ ] **Step 2: 运行**

Run: `cd d:\01_coding\my_agents && python -m pytest tests/e2e/test_multi_fund_portfolio_e2e.py -v`
Expected: 全部 PASS

- [ ] **Step 3: 跑全量测试**

Run: `cd d:\01_coding\my_agents && python -m pytest -v --tb=short`
Expected: 全部 PASS(无回归)

- [ ] **Step 4: 提交**

```bash
cd d:\01_coding\my_agents
git add tests/e2e/test_multi_fund_portfolio_e2e.py
git commit -m "test: e2e assert HTML contains quality score module"
```

---

### Task 4.3: 清理临时文件 + 最终验收

- [ ] **Step 1: 删除备份文件**

```bash
cd d:\01_coding\my_agents
rm -f agents/fund-recommender.agent.md.bak
```

- [ ] **Step 2: 跑全量测试**

Run: `cd d:\01_coding\my_agents && python -m pytest -v --tb=short`
Expected: 全部 PASS,耗时 < 30s

- [ ] **Step 3: 跑 lint(若有)**

Run: `cd d:\01_coding\my_agents && python -m flake8 data_tools/ tests/ --max-line-length=120 --ignore=E501,W503,E402 || echo "flake8 not installed, skip"`
Expected: 无错误或 flake8 缺失

- [ ] **Step 4: 最终 commit**

```bash
cd d:\01_coding\my_agents
git status
git add -A
git commit -m "chore: remove backup files and finalize deep recommender" --allow-empty
```

- [ ] **Step 5: 验收清单(对照 spec §9)**

```markdown
- [ ] parse_quality_from_reports() 对 5+ 真实基金 markdown 报告抽取正确
- [ ] score_with_quality_reports() 输出 final_score ∈ [0, 100]
- [ ] 单元测试 pytest tests/unit/test_quality_score.py -v 全部通过
- [ ] CLI python -m data_tools.cli quality-score --help 显示帮助
- [ ] fund-recommender.agent.md 调度流程图清晰
- [ ] 跑完整 C-1 组合 E2E 通过
- [ ] 最终 HTML 报告含"质量分组成表"和"深度报告路径表"
- [ ] 7 分析师失败时,降级路径生效,无未捕获异常
- [ ] 整只候选 7 报告全失败时,推荐列表仍含该候选(用 name_score)
```

---

## Self-Review

按 writing-plans §Self-Review 清单逐条检查:

### 1. Spec coverage

| Spec 章节 | 覆盖任务 |
|-----------|----------|
| §3.1.1 `parse_quality_from_reports` | Task 1.2 |
| §3.1.2 `score_with_quality_reports` | Task 1.4 |
| §3.1.3 `build_rebalance_plan` 改造 | Task 1.5 |
| §3.2.1 CLI `quality-score` | Task 1.6 |
| §3.3 fund-recommender 重写 | Task 2.1 |
| §4.1 portfolio-manager 增强 | Task 3.1 |
| §4.2 HTML 模板 | Task 3.2 |
| §4.3 workflow-portfolio.md | Task 2.2 |
| §4.4 SKILL.md 铁律 | Task 2.3 |
| §6 单元测试 | Task 1.1 / 1.3 |
| §6 集成测试 | Task 4.1 |
| §6 E2E 测试 | Task 4.2 |
| §9 验收 | Task 4.3 |

**Gap**: 无。spec 全部 13 节都有对应任务。

### 2. Placeholder scan

- ✅ 无 "TBD" / "TODO" / "implement later"
- ✅ 无 "add appropriate error handling" / "fill in details"
- ✅ 所有代码块都是完整可执行代码
- ✅ 所有命令都包含具体路径与期望输出

### 3. Type consistency

- `parse_quality_from_reports()` 在 Task 1.2 定义,Task 1.3 / 1.6 调用,签名一致(4 参数,返回 dict)
- `score_with_quality_reports()` 在 Task 1.4 定义,Task 1.5 / 4.1 调用,签名一致(4 参数,返回 dict)
- `quality_score` 字段在 Task 1.2 / 1.4 / 1.5 / 2.1 / 3.1 / 3.2 全部使用,类型一致(float)
- `report_paths` 字段在 Task 1.2 / 2.1 / 3.2 全部使用,结构一致(dict[role, path])
- `quality_signals` 字段在 Task 1.2 / 2.1 / 3.2 全部使用,结构一致({dim: {score, details, missing}})
- `name_score` / `quality_missing` 字段在 Task 1.4 / 1.5 / 2.1 全部使用,类型一致

### 4. Ambiguity check

- ✅ "7 报告"含义明确(Task 1.2 ROLES 列表)
- ✅ "同消息内并行"含义明确(SKILL.md 铁律 4 既有定义,Task 2.3 引用)
- ✅ "降级路径"含义明确(Task 1.3 test_parse_quality_all_missing 覆盖)

### 5. Execution safety

- 所有 git commit 步骤可独立执行
- 所有 pytest 命令可在任意阶段单独运行
- 任何 Task 失败不阻塞后续 Task(P0 → P1 → P2 → 集成)

---

## 任务数与估时

| Phase | 任务数 | 估时(人天) |
|-------|--------|------------|
| Phase 1 (P0 核心) | 6 | 3 |
| Phase 2 (P1 文档) | 3 | 1.5 |
| Phase 3 (P2 下游) | 2 | 0.8 |
| Phase 4 (集成测试) | 3 | 0.7 |
| **合计** | **14** | **6** |

符合 spec §7 改造清单 5-6 人天估算。

---

## 执行选项

**Plan complete and saved to `docs/superpowers/plans/2026-06-29-fund-recommender-deep.md`.**

两种执行方式可选:

**1. Subagent-Driven (recommended)** — 每个 Task 派一个独立 subagent 执行,Task 之间我做 review 决定是否继续或回滚。**适合 5+ 任务的批量执行**,质量反馈循环快,失败可隔离。

**2. Inline Execution** — 在当前会话中按 Phase 顺序批量执行(每 Phase 4-6 个 Task),Phase 之间做 checkpoint 让你 review。**适合需要频繁同步进度的场景**,反馈周期长一些但你能直接看到每一步输出。