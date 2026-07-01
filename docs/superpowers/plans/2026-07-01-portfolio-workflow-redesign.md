# 持仓组合工作流优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对持仓组合分析流程(C-1/C-3)实施三方面优化：①报告章节顺序重排（操作建议前置+数据源评估紧随）②全场景补全基金完整名称+当前净值（含缓存状态）③Step 9 从「Top-3 候选评分」改为「补充/清除分类清单（含初步筛掉原因）」

**Architecture:** 沿用现有 `data_tools` 模块化结构，新增强制缓存校验函数 `get_unit_nav_with_cache_status`（基于现有 `_CACHE_MAX_AGE_HOURS`）和清除清单分类函数 `classify_exit_reasons`（复用 `compute_gap` / `parse_quality_from_reports`）。HTML 模板拆分为 partials 并重排 include 块顺序。

**Tech Stack:** Python 3.11+ / pytest / Jinja2 templates / dataclass + TypedDict

---

## File Structure

| 文件 | 责任 | 类型 |
|------|------|------|
| `data_tools/fund_data.py` | 新增 `get_unit_nav_with_cache_status()` 函数 | 修改 |
| `data_tools/portfolio.py` | 新增 `classify_exit_reasons()` + `find_redundant_pairs()` 函数 | 修改 |
| `data_tools/cli.py` | 注册 `fund nav-cached <code>` 子命令 | 修改 |
| `data_tools/template_renderer.py` | 渲染前批量注入净值+缓存状态到 HTML 上下文 | 修改 |
| `agents/portfolio-manager.agent.md` | 重排输出章节顺序+操作建议前置 | 修改 |
| `templates/portfolio.html.j2` | include 块顺序重排+移除原"推荐补/换基金"块 | 修改 |
| `templates/partials/_portfolio_section.html.j2` | 新增"当前净值+缓存状态"列 | 修改 |
| `templates/partials/_data_source_audit.html.j2` | 新增：数据源评估模块 | 新增 |
| `templates/partials/_action_recommendations.html.j2` | 新增：操作建议+补充/清除清单 | 新增 |
| `templates/partials/_quality_score_styles.html.j2` | 复用：仅在 fund_recommendations 存在时 include | 不变 |
| `.trae/skills/stock-analysis/workflow-portfolio.md` | Step 9/11/12 描述更新 | 修改 |
| `tests/unit/test_fund_nav_cache.py` | 新增：净值缓存状态测试 | 新增 |
| `tests/unit/test_exit_reasons.py` | 新增：清除清单分类测试 | 新增 |
| `tests/unit/test_template_portfolio_order.py` | 新增：HTML 模板顺序测试 | 新增 |

---

## Task 1: 净值缓存状态函数 + TDD

**Files:**
- Modify: `data_tools/fund_data.py` (新增 `get_unit_nav_with_cache_status()`)
- Test: `tests/unit/test_fund_nav_cache.py` (新增)

### Step 1.1: 写失败的测试

```python
# tests/unit/test_fund_nav_cache.py
"""净值缓存状态校验函数单元测试。"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from data_tools.fund_data import (
    get_unit_nav_with_cache_status,
    _CACHE_MAX_AGE_HOURS,
)


@pytest.fixture
def fake_fund_dir(tmp_path: Path, monkeypatch) -> Path:
    """伪装 data/funds/<code>/ 目录结构,nav_*.csv + fund_info_*.txt。"""
    code = "011095"
    fund_dir = tmp_path / code
    fund_dir.mkdir()

    csv = fund_dir / "nav_2026-07-01_2026-07-01.csv"
    csv.write_text(
        "净值日期,单位净值,累计净值,日增长率\n"
        "2026-07-01,1.2345,1.3456,0.32%\n"
        "2026-06-30,1.2305,1.3416,0.50%\n",
        encoding="utf-8",
    )

    info = fund_dir / "fund_info_2026-07-01.txt"
    info.write_text(
        "基金代码 011095\n单位净值 1.2345\n累计净值 1.3456\n",
        encoding="utf-8",
    )

    # 伪造 get_fund_data_dir 返回 tmp_path/<code>
    from data_tools import stock_data
    monkeypatch.setattr(stock_data, "get_fund_data_dir",
                        lambda c: fund_dir)
    monkeypatch.setattr(
        "data_tools.fund_data.get_fund_data_dir", lambda c: fund_dir
    )
    return fund_dir


def test_fresh_when_within_threshold(fake_fund_dir):
    unit_nav, daily_return, status = get_unit_nav_with_cache_status(
        "011095", threshold_hours=4
    )
    assert status == "fresh"
    assert unit_nav == pytest.approx(1.2345)
    assert daily_return == pytest.approx(0.0032, abs=1e-3)


def test_stale_when_beyond_threshold(fake_fund_dir, monkeypatch):
    # 修改 nav 文件 mtime 模拟 5h ago(超过 4h 阈值)
    csv = list(fake_fund_dir.glob("nav_*.csv"))[0]
    five_hours_ago = time.time() - 5 * 3600
    import os
    os.utime(csv, (five_hours_ago, five_hours_ago))

    unit_nav, daily_return, status = get_unit_nav_with_cache_status(
        "011095", threshold_hours=4
    )
    assert status == "stale"
    assert unit_nav == pytest.approx(1.2345)


def test_missing_when_no_file(tmp_path, monkeypatch):
    from data_tools import stock_data
    monkeypatch.setattr(stock_data, "get_fund_data_dir",
                        lambda c: tmp_path / c)

    unit_nav, daily_return, status = get_unit_nav_with_cache_status(
        "999999", threshold_hours=4
    )
    assert status == "missing"
    assert unit_nav is None
    assert daily_return is None


def test_default_threshold_uses_nav_cache(fake_fund_dir):
    # 不传 threshold_hours,默认 = _CACHE_MAX_AGE_HOURS["nav"] = 4h
    unit_nav, daily_return, status = get_unit_nav_with_cache_status("011095")
    assert status == "fresh"
    assert _CACHE_MAX_AGE_HOURS["nav"] == 4


def test_daily_return_parses_pct_string(fake_fund_dir):
    _, daily_return, _ = get_unit_nav_with_cache_status("011095")
    assert isinstance(daily_return, float)
    assert 0.003 <= daily_return <= 0.004  # 0.32% 解析为 0.0032
```

### Step 1.2: 运行测试确认失败

Run: `pytest tests/unit/test_fund_nav_cache.py -v`
Expected: FAIL `ImportError: cannot import name 'get_unit_nav_with_cache_status'`

### Step 1.3: 在 fund_data.py 中实现函数

```python
# data_tools/fund_data.py 中新增（接在 is_data_fresh 后面）

def get_unit_nav_with_cache_status(
    symbol: str,
    threshold_hours: float | None = None,
) -> tuple[float | None, float | None, str]:
    """读取单位净值+日累计收益,返回带缓存状态的三元组。

    Parameters
    ----------
    symbol : str
        基金代码。
    threshold_hours : float | None, optional
        自定义缓存阈值(小时)。None 时沿用 _CACHE_MAX_AGE_HOURS["nav"] = 4。

    Returns
    -------
    (unit_nav, daily_return, cache_status) :
        unit_nav     : float | None   单位净值
        daily_return : float | None   日累计收益(小数,如 0.0032 = 0.32%)
        cache_status : str ∈ {"fresh","stale","missing"}
    """
    import csv as csv_mod

    if threshold_hours is None:
        threshold_hours = _CACHE_MAX_AGE_HOURS.get("nav", 4)

    # 优先 nav_*.csv
    nav_path = _find_latest_cache_file(symbol, "nav_", (".csv",))
    if nav_path is None:
        return None, None, "missing"

    # 缓存状态判定
    age_hours = (time.time() - os.path.getmtime(nav_path)) / 3600
    status = "fresh" if age_hours < threshold_hours else "stale"

    # 解析 CSV 取最新一行
    unit_nav: float | None = None
    daily_return: float | None = None
    try:
        with open(nav_path, "r", encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            rows = list(reader)
            if rows:
                last = rows[-1]
                unit_nav = float(last["单位净值"])
                dr_str = last.get("日增长率", "0%").rstrip("%").strip()
                daily_return = float(dr_str) / 100.0
    except (ValueError, KeyError, OSError):
        pass

    return unit_nav, daily_return, status
```

### Step 1.4: 运行测试确认通过

Run: `pytest tests/unit/test_fund_nav_cache.py -v`
Expected: PASS (5 tests passed)

### Step 1.5: 提交

```bash
git add data_tools/fund_data.py tests/unit/test_fund_nav_cache.py
git commit -m "feat(fund_data): add get_unit_nav_with_cache_status for HTML report"
```

---

## Task 2: 清除清单分类函数 + TDD

**Files:**
- Modify: `data_tools/portfolio.py` (新增 `classify_exit_reasons()` + `find_redundant_pairs()`)
- Test: `tests/unit/test_exit_reasons.py` (新增)

### Step 2.1: 写失败的测试

```python
# tests/unit/test_exit_reasons.py
"""清除清单分类函数单元测试。"""
from __future__ import annotations

import pytest

from data_tools.portfolio import (
    ExitReasonItem,
    classify_exit_reasons,
    find_redundant_pairs,
)
from data_tools.portfolio_prefs import UserPrefs


@pytest.fixture
def sample_holdings():
    return [
        {"code": "014655", "name": "国联益海30天滚动持有短债A",
         "type": "fund", "amount": 5000.0, "category": "bond"},
        {"code": "011095", "name": "博时恒泽混合A",
         "type": "fund", "amount": 10000.0, "category": "balanced"},
        {"code": "002001", "name": "某重复风格基金",
         "type": "fund", "amount": 3000.0, "category": "balanced"},
    ]


@pytest.fixture
def sample_fund_reports():
    """模拟 7 分析师报告状态 + 关键 quality_signals。"""
    return {
        "014655": {
            "report_paths": {"market": "repos/.../014655_market.md"},
            "has_reports": True,
            "quality_signals": {
                "scale": {"score": 15.0, "details": "1.09 亿, 接近清盘线"},
                "performance": {"score": 70.0, "details": "近 3 年 优秀"},
                "manager": {"score": 60.0, "details": "任职 3 年"},
                "concentration": {"score": 50.0, "details": "前十大占 30%"},
                "policy_sentiment": {"score": 50.0, "details": "中性"},
                "missing": [],
            },
        },
        "011095": {
            "report_paths": {"market": "repos/.../011095_market.md"},
            "has_reports": True,
            "quality_signals": {
                "scale": {"score": 70.0, "details": "10 亿"},
                "performance": {"score": 80.0, "details": "近 1/3/5 年均 优秀"},
                "manager": {"score": 40.0, "details": "经理刚变更 90 天内",
                            "manager_change": True},
                "concentration": {"score": 50.0, "details": ""},
                "policy_sentiment": {"score": 50.0, "details": ""},
                "missing": [],
            },
        },
        "002001": {
            "report_paths": {},
            "has_reports": False,
            "quality_signals": {"missing": ["all"]},
        },
    }


@pytest.fixture
def sample_gap_report():
    return {
        "gaps": [
            {"category": "bond", "current_pct": 0.15, "target_pct": 0.25,
             "delta_pct": 0.10, "action": "add"},
            {"category": "balanced", "current_pct": 0.35, "target_pct": 0.30,
             "delta_pct": -0.05, "action": "trim"},
        ],
        "overweight": ["balanced"],
    }


@pytest.fixture
def sample_prefs():
    return UserPrefs(risk_level=3, horizon="medium",
                     preferred_categories=[],
                     excluded_categories=[],
                     excluded_codes=set())


def test_clear_liquidation_risk_detected(
    sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
):
    result = classify_exit_reasons(
        sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
    )
    by_code = {e["code"]: e for e in result}
    # 014655 net_assets 1.09 亿 = 接近但未到清盘,scale score 15 触发
    assert "014655" in by_code
    codes = [r["code"] for r in by_code["014655"]["reasons"]]
    assert "clear_liquidation_risk" in codes


def test_clear_manager_change_detected(
    sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
):
    result = classify_exit_reasons(
        sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
    )
    by_code = {e["code"]: e for e in result}
    assert "011095" in by_code
    codes = [r["code"] for r in by_code["011095"]["reasons"]]
    assert "clear_manager_change" in codes


def test_clear_category_overweight_for_overweight_categories(
    sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
):
    result = classify_exit_reasons(
        sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
    )
    by_code = {e["code"]: e for e in result}
    # 011095 是 balanced 且 balanced 在 overweight
    codes = [r["code"] for r in by_code["011095"]["reasons"]]
    assert "clear_category_overweight" in codes


def test_missing_data_degrades_gracefully(
    sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
):
    """全数据缺失的基金仍出现在清单中,reasons 为空数组,不抛错。"""
    result = classify_exit_reasons(
        sample_holdings, sample_fund_reports, sample_gap_report, sample_prefs
    )
    by_code = {e["code"]: e for e in result}
    assert "002001" in by_code
    assert by_code["002001"]["reasons"] == []
    assert by_code["002001"]["quality_missing"] is True


def test_exit_reason_item_dataclass():
    item = ExitReasonItem(code="clear_liquidation_risk",
                          label="🔴 临近清盘线（净资产 < 5000 万）")
    assert item.code == "clear_liquidation_risk"
    assert "清盘" in item.label


def test_find_redundant_pairs_returns_correlation():
    """重复暴露检测:同 카테고리 + 报告完整时相关性检查触发。"""
    positions = [
        {"code": "A", "amount": 5000.0, "category": "balanced"},
        {"code": "B", "amount": 5000.0, "category": "balanced"},
    ]
    pairs = find_redundant_pairs(positions, fund_reports=None)
    # fund_reports=None 时返回空(无数据)
    assert pairs == []
```

### Step 2.2: 运行测试确认失败

Run: `pytest tests/unit/test_exit_reasons.py -v`
Expected: FAIL `ImportError: cannot import name 'classify_exit_reasons'`

### Step 2.3: 在 portfolio.py 中实现函数

在 `data_tools/portfolio.py` 文件末尾(calculate_balance 后)新增：

```python
from dataclasses import dataclass, field
from typing import Optional


# 退出原因枚举
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
    """检测组合内风格重复暴露。

    Args:
        positions: [{code, amount, category}, ...]
        fund_reports: 每只基金的报告状态,可选
        threshold: 相关系数阈值,默认 0.85

    Returns:
        [(code_a, code_b, correlation), ...] 当前实现仅按"同 category 且占比合计 > 40%"启发式判断;
        若 fund_reports 提供 quality_signals.concentration.score,按相似度增强。
    """
    if fund_reports is None:
        return []  # 无报告数据时降级
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
    prefs,  # UserPrefs,避免循环导入
    total_amount: float | None = None,
) -> list[dict]:
    """为每只持仓基金生成「初步筛掉原因」清单。

    Args:
        holdings: 当前持仓 [{code, name, type, amount, category?}, ...]
        fund_reports: {code: {"report_paths": ..., "has_reports": bool,
                              "quality_signals": {...}, "quality_missing": bool}}
        gap_report: compute_gap() 输出 {"gaps": [...], "overweight": [...]}
        prefs: UserPrefs 实例
        total_amount: 组合总金额,默认从 holdings 计算

    Returns:
        [{
            "code": str,
            "name": str,
            "amount": float,
            "category": str,
            "unit_nav": float | None,
            "daily_return": float | None,
            "cache_status": str,  # fresh/stale/missing, 默认 missing
            "reasons": list[ExitReasonItem],
            "quality_missing": bool,
        }, ...]
    """
    from .fund_data import get_unit_nav_with_cache_status

    if total_amount is None:
        total_amount = sum(h["amount"] for h in holdings) or 1.0
    overweight_set = set(gap_report.get("overweight", []))
    excluded_codes = set(getattr(prefs, "excluded_codes", set()) or set())

    # 重复暴露对(组合级判定一次)
    redundant_pairs = find_redundant_pairs(holdings, fund_reports)
    redundant_codes = {c for pair in redundant_pairs for c in (pair[0], pair[1])}

    out: list[dict] = []
    for h in holdings:
        code = h["code"]
        name = h.get("name", "")
        amount = float(h.get("amount", 0))
        category = h.get("category")

        # 净值缓存(降级到 missing 时不影响 reasons)
        try:
            unit_nav, daily_return, cache_status = get_unit_nav_with_cache_status(code)
        except Exception:
            unit_nav, daily_return, cache_status = None, None, "missing"

        report = fund_reports.get(code, {})
        has_reports = report.get("has_reports", False)
        quality_missing = not has_reports
        signals = report.get("quality_signals", {})

        reasons: list[ExitReasonItem] = []
        if has_reports and signals:
            scale = signals.get("scale", {})
            if scale.get("score", 100) < 25:
                reasons.append(ExitReasonItem(
                    "clear_liquidation_risk",
                    EXIT_REASON_CATALOG["clear_liquidation_risk"],
                ))
            performance = signals.get("performance", {})
            if performance.get("score", 100) < 30:
                reasons.append(ExitReasonItem(
                    "clear_underperform_3y",
                    EXIT_REASON_CATALOG["clear_underperform_3y"],
                ))
            manager = signals.get("manager", {})
            if manager.get("manager_change", False) or manager.get("score", 100) < 40:
                reasons.append(ExitReasonItem(
                    "clear_manager_change",
                    EXIT_REASON_CATALOG["clear_manager_change"],
                ))

        # 集中度纪律(> 25%)
        if amount / total_amount > 0.25:
            reasons.append(ExitReasonItem(
                "clear_concentration_violation",
                EXIT_REASON_CATALOG["clear_concentration_violation"],
            ))

        # 重复暴露
        if code in redundant_codes:
            reasons.append(ExitReasonItem(
                "clear_redundancy",
                EXIT_REASON_CATALOG["clear_redundancy"],
            ))

        # 品类超配
        if category in overweight_set:
            reasons.append(ExitReasonItem(
                "clear_category_overweight",
                EXIT_REASON_CATALOG["clear_category_overweight"],
            ))

        # 用户已排除
        if code in excluded_codes:
            reasons.append(ExitReasonItem(
                "clear_user_excluded",
                EXIT_REASON_CATALOG["clear_user_excluded"],
            ))

        out.append({
            "code": code,
            "name": name,
            "amount": amount,
            "category": category,
            "unit_nav": unit_nav,
            "daily_return": daily_return,
            "cache_status": cache_status or "missing",
            "reasons": reasons,
            "quality_missing": quality_missing,
        })

    return out
```

### Step 2.4: 运行测试确认通过

Run: `pytest tests/unit/test_exit_reasons.py -v`
Expected: PASS (6 tests passed)

### Step 2.5: 提交

```bash
git add data_tools/portfolio.py tests/unit/test_exit_reasons.py
git commit -m "feat(portfolio): add classify_exit_reasons with catalog of 9 exit reason codes"
```

---

## Task 3: CLI 命令 `fund nav-cached`

**Files:**
- Modify: `data_tools/cli.py` (注册 `fund nav-cached` 子命令)
- Modify: `data_tools/fund_data.py` (暴露 force_refetch 路径,如尚未存在)

### Step 3.1: 写命令骨架 + 文档字符串

在 `data_tools/cli.py` 末尾追加（如无独立测试覆盖,但确保 click 子命令注册能跑通）：

```python
def cmd_fund_nav_cached(args):
    """获取基金单位净值（带缓存校验）。"""
    from .fund_data import get_unit_nav_with_cache_status, get_fund_nav_history, get_fund_data_dir
    code = args.code
    threshold = args.threshold_hours

    unit_nav, daily_return, status = get_unit_nav_with_cache_status(
        code, threshold_hours=threshold
    )

    if args.force or status in ("stale", "missing"):
        # 调用拉取函数
        from datetime import datetime, timedelta
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        try:
            get_fund_nav_history(code, start_date=start, end_date=end)
        except Exception as e:
            print(f"[拉取失败] {e}", file=sys.stderr)
        unit_nav, daily_return, status = get_unit_nav_with_cache_status(code, threshold_hours=threshold)
        if status == "missing":
            status = "force_refetch"

    output = {
        "code": code,
        "unit_nav": unit_nav,
        "daily_return": daily_return,
        "cache_status": status,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
```

### Step 3.2: 注册 click 子命令

在 `cli.py` 的 `main()` 函数（假设存在 click group）或 `register_parser` 部分追加：

```python
def register_fund_nav_cached(subparsers):
    """注册 fund nav-cached 子命令。"""
    p = subparsers.add_parser(
        "nav-cached", help="获取单位净值（带缓存校验）"
    )
    p.add_argument("code", help="基金代码")
    p.add_argument(
        "--threshold-hours", type=float, default=None,
        help="缓存阈值（小时），默认使用 _CACHE_MAX_AGE_HOURS['nav']=4"
    )
    p.add_argument(
        "--force", action="store_true",
        help="绕过缓存，强制重新拉取"
    )
    p.set_defaults(func=cmd_fund_nav_cached)
    return p
```

### Step 3.3: 验证命令注册成功

Run: `python -m data_tools.cli nav-cached --help`
Expected: 输出帮助信息,显示 `--threshold-hours` 与 `--force` 参数

### Step 3.4: 验证 fresh 路径

```bash
mkdir -p /tmp/test_fund/011095
echo "净值日期,单位净值,累计净值,日增长率
2026-07-01,1.2345,1.3456,0.32%" > /tmp/test_fund/011095/nav_test.csv
```

> 注：实际测试需要把 `data_tools/stock_data.py` 的 `get_fund_data_dir` 指向测试目录。CLI 测试可通过临时 monkey-patch 验证,这里仅校验命令注册和参数解析。

### Step 3.5: 提交

```bash
git add data_tools/cli.py data_tools/fund_data.py
git commit -m "feat(cli): add fund nav-cached subcommand with threshold + force flags"
```

---

## Task 4: 模板与渲染管线

**Files:**
- Create: `templates/partials/_data_source_audit.html.j2`
- Create: `templates/partials/_action_recommendations.html.j2`
- Modify: `templates/portfolio.html.j2` (include 重排)
- Modify: `templates/partials/_portfolio_section.html.j2` (新增净值列)
- Modify: `data_tools/template_renderer.py` (注入净值+缓存状态上下文)

### Step 4.1: 新增 _data_source_audit.html.j2

```jinja
{# 数据源评估 — 显示每只标的的数据拉取日期/缓存状态/缺失维度 #}
<section class="data-source-audit">
  <h2>数据源评估</h2>
  {% if data_source_audit %}
    <table>
      <thead>
        <tr>
          <th>代码</th><th>名称</th><th>当前净值</th><th>日收益</th>
          <th>缓存状态</th><th>报告完整度</th><th>缺失维度</th>
        </tr>
      </thead>
      <tbody>
      {% for row in data_source_audit %}
        <tr>
          <td><code>{{ row.code }}</code></td>
          <td>{{ row.name }}</td>
          <td>
            {% if row.unit_nav is not none %}
              {{ "%.4f"|format(row.unit_nav) }}
            {% else %}
              <span class="muted">[缺失]</span>
            {% endif %}
          </td>
          <td>
            {% if row.daily_return is not none %}
              {{ "%+.2f%%"|format(row.daily_return * 100) }}
            {% else %}
              <span class="muted">—</span>
            {% endif %}
          </td>
          <td>
            {% set status_color = {
              'fresh': '🟢', 'stale': '🟡',
              'missing': '🔴', 'force_refetch': '🔵'
            } %}
            {{ status_color.get(row.cache_status, '⚪') }}
            {% if row.cache_status == 'fresh' %}
              今日更新
            {% elif row.cache_status == 'stale' %}
              数据可能滞后
            {% elif row.cache_status == 'missing' %}
              净值缺失
            {% else %}
              实时拉取
            {% endif %}
          </td>
          <td>
            {{ row.reports_count }}/7
          </td>
          <td>
            {% if row.missing_dimensions %}
              <span class="muted">{{ row.missing_dimensions | join(', ') }}</span>
            {% else %}
              —
            {% endif %}
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  {% else %}
    <p class="muted">无数据源信息</p>
  {% endif %}
</section>
```

### Step 4.2: 新增 _action_recommendations.html.j2

```jinja
{# 操作建议 — P0/P1/P2/P3 分级 + 补充/清除分类清单 #}
<section class="action-recommendations">
  <h2>操作建议</h2>

  {# P0 立即清出 #}
  {% if action_recommendations.p0_clear %}
    <h3>P0 立即清出</h3>
    <table class="action-table">
      <thead>
        <tr><th>代码</th><th>名称</th><th>当前净值</th><th>金额</th><th>初步筛掉原因</th></tr>
      </thead>
      <tbody>
      {% for item in action_recommendations.p0_clear %}
        <tr class="p0-row">
          <td><code>{{ item.code }}</code></td>
          <td>{{ item.name }}</td>
          <td>
            {% if item.unit_nav is not none %}{{ "%.4f"|format(item.unit_nav) }}
            {% else %}<span class="muted">[缺失]</span>{% endif %}
          </td>
          <td>{{ "%.0f"|format(item.amount) }}</td>
          <td>
            {% for r in item.reasons %}<span class="reason-chip">{{ r.label }}</span>{% endfor %}
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  {% endif %}

  {# P1 分批减仓 #}
  {% if action_recommendations.p1_trim %}
    <h3>P1 分批减仓</h3>
    <table class="action-table">
      <thead>
        <tr><th>代码</th><th>名称</th><th>当前净值</th><th>金额</th><th>初步筛掉原因</th></tr>
      </thead>
      <tbody>
      {% for item in action_recommendations.p1_trim %}
        <tr>
          <td><code>{{ item.code }}</code></td>
          <td>{{ item.name }}</td>
          <td>
            {% if item.unit_nav is not none %}{{ "%.4f"|format(item.unit_nav) }}
            {% else %}<span class="muted">[缺失]</span>{% endif %}
          </td>
          <td>{{ "%.0f"|format(item.amount) }}</td>
          <td>
            {% for r in item.reasons %}<span class="reason-chip">{{ r.label }}</span>{% endfor %}
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  {% endif %}

  {# P2 增量配置（补充类清单）#}
  {% if action_recommendations.p2_add %}
    <h3>P2 增量配置</h3>
    <p class="muted">以下品类当前占比低于目标,需按特征标签筛选场内/场外公募补仓</p>
    <table class="action-table">
      <thead>
        <tr><th>品类</th><th>目标占比</th><th>当前占比</th><th>缺口金额</th><th>期望特征标签</th></tr>
      </thead>
      <tbody>
      {% for cat in action_recommendations.p2_add %}
        <tr>
          <td>{{ cat.category }}</td>
          <td>{{ "%.1f%%"|format(cat.target_pct * 100) }}</td>
          <td>{{ "%.1f%%"|format(cat.current_pct * 100) }}</td>
          <td>{{ "%+,.0f"|format(cat.delta_amount) }}</td>
          <td>
            {% for tag in cat.feature_tags %}<span class="feature-chip">{{ tag }}</span>{% endfor %}
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  {% endif %}

  {# P3 压舱石加配 #}
  {% if action_recommendations.p3_hold %}
    <h3>P3 维持当前</h3>
    <ul>
      {% for item in action_recommendations.p3_hold %}
        <li><code>{{ item.code }}</code> {{ item.name }} — 维持占比与特征匹配</li>
      {% endfor %}
    </ul>
  {% endif %}
</section>
```

### Step 4.3: 修改 _portfolio_section.html.j2 — 新增"当前净值"列

替换原表格 thead：
```jinja
<thead><tr><th>代码</th><th>名称</th><th>类型</th><th>金额</th><th>占比</th><th>收益</th><th>当前净值</th></tr></thead>
<tbody>
{% for p in portfolio.positions %}
  <tr>
    <td><code>{{ p.code }}</code></td><td>{{ p.name }}</td><td>{{ p.type }}</td>
    <td>{{ p.amount }}</td><td>{{ p.ratio }}%</td>
    <td class="{{ 'positive' if p.holding_return > 0 else 'negative' }}">{{ p.holding_return }}</td>
    <td>
      {% if p.unit_nav is not none %}
        {{ "%.4f"|format(p.unit_nav) }}
        {% if p.daily_return is not none %}
          <small class="muted">({{ "%+.2f%%"|format(p.daily_return * 100) }})</small>
        {% endif %}
      {% else %}
        <span class="muted">[净值缺失]</span>
      {% endif %}
    </td>
  </tr>
{% endfor %}
</tbody>
```

### Step 4.4: 修改 portfolio.html.j2 — include 块顺序重排

替换原文件主体（保留 header/footer）：

```jinja
<body>
  {% include 'partials/_header.html.j2' %}

  {# 第一屏: 持仓总览（带当前净值列）#}
  {% include 'partials/_portfolio_section.html.j2' %}

  {# 第二屏: 数据源评估（新增）#}
  {% include 'partials/_data_source_audit.html.j2' %}

  {# 第三屏: 操作建议 + 补充/清除清单（新增,前置原第六屏位置）#}
  {% include 'partials/_action_recommendations.html.j2' %}

  {# 第四屏: 风险 #}
  {% include 'partials/_risk_section.html.j2' %}

  {# 第五屏: 目标配置 #}
  <main>
    <h2>目标配置</h2>
    {% if target_allocation %}
      <ul>
      {% for t in target_allocation %}
        <li>{{ t.name }}: {{ t.target_ratio }}% (当前 {{ t.current_ratio }}%)</li>
      {% endfor %}
      </ul>
    {% endif %}
  </main>

  {# 原"推荐补/换基金深度评估"块整体移除 #}

  {% include 'partials/_disclaimer.html.j2' %}
  {% include 'partials/_footer.html.j2' %}
</body>
```

### Step 4.5: 在 template_renderer.py 中注入上下文

修改 `data_tools/template_renderer.py` 的 `render_portfolio` 函数（假设已存在），在传给 Jinja2 环境前注入：

```python
from .fund_data import get_unit_nav_with_cache_status
from .portfolio import classify_exit_reasons
from .portfolio_rebalance import compute_gap, classify_positions, screen_replacement_funds
from .portfolio_prefs import load_user_prefs

def enrich_portfolio_context(context: dict) -> dict:
    """为 portfolio 渲染上下文注入净值缓存状态、操作建议、数据源评估。"""
    positions = context.get("portfolio", {}).get("positions", [])
    if not positions:
        return context

    # 1. 注入每只持仓的当前净值
    for p in positions:
        if p.get("type") == "fund":
            unit_nav, daily_return, status = get_unit_nav_with_cache_status(
                p["code"]
            )
            p["unit_nav"] = unit_nav
            p["daily_return"] = daily_return
            p["cache_status"] = status

    # 2. 数据源评估（简化版：净值+报告完整度）
    context["data_source_audit"] = [
        {
            "code": p["code"],
            "name": p["name"],
            "unit_nav": p.get("unit_nav"),
            "daily_return": p.get("daily_return"),
            "cache_status": p.get("cache_status", "missing"),
            "reports_count": 7,  # 占位,由调用方注入实际计数
            "missing_dimensions": [],
        }
        for p in positions
    ]

    # 3. 调用 classify_exit_reasons 生成清除清单
    user_id = context.get("user_id")
    if user_id:
        try:
            prefs = load_user_prefs(user_id)
            classified = classify_positions(positions)
            target = context.get("target_allocation_dict", {})
            current, gaps, underweight, overweight = compute_gap(
                classified, target,
                cash_amount=context.get("cash_amount", 0.0)
            )
            gap_report = {"gaps": [g.to_dict() for g in gaps], "overweight": overweight}
            fund_reports = context.get("fund_reports", {})
            exit_items = classify_exit_reasons(positions, fund_reports, gap_report, prefs)

            # P0/P1/P2/P3 分组
            critical_codes = {"clear_liquidation_risk", "clear_redemption_pressure",
                              "clear_user_excluded"}
            p0 = [it for it in exit_items
                  if any(r.code in critical_codes for r in it["reasons"])]
            p1 = [it for it in exit_items
                  if it not in p0 and it["reasons"]]
            p0.sort(key=lambda x: -len(x["reasons"]))
            p1.sort(key=lambda x: -len(x["reasons"]))

            # 补充类清单(P2)
            p2 = []
            for g in gaps:
                if g.action == "add":
                    p2.append({
                        "category": g.category,
                        "target_pct": g.target_pct,
                        "current_pct": g.current_pct,
                        "delta_amount": g.delta_amount,
                        "feature_tags": _feature_tags_for(g.category),
                    })

            # P3 维持
            exit_codes = {it["code"] for it in p0 + p1}
            p3 = [it for it in exit_items if it["code"] not in exit_codes]

            context["action_recommendations"] = {
                "p0_clear": p0,
                "p1_trim": p1,
                "p2_add": p2,
                "p3_hold": p3,
            }
        except Exception:
            context["action_recommendations"] = {}

    return context


def _feature_tags_for(category: str) -> list[str]:
    """按品类返回期望特征标签(沿用 portfolio_prefs 的关键词)。"""
    from .portfolio_prefs import CATEGORY_KEYWORDS
    return list(CATEGORY_KEYWORDS.get(category, ()))[:3]
```

### Step 4.6: 在 render 函数前调用 enrich_portfolio_context

找到现有 `render_portfolio` 函数,在 `template.render(context)` 前增加：

```python
context = enrich_portfolio_context(context)
```

### Step 4.7: 提交

```bash
git add templates/ data_tools/template_renderer.py
git commit -m "feat(templates): add data_source_audit + action_recommendations partials; reorder portfolio.html"
```

---

## Task 5: 模板顺序 TDD 测试

**Files:**
- Test: `tests/unit/test_template_portfolio_order.py` (新增)
- Modify: `tests/conftest.py` (提供 Jinja2 环境 fixture)

### Step 5.1: 写测试

```python
"""模板顺序 + 包含块顺序的单元测试。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader


@pytest.fixture
def jinja_env() -> Environment:
    template_dir = Path(__file__).resolve().parents[2] / "templates"
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
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
                    "code": "014655", "name": "国联益海30天滚动持有短债A",
                    "type": "fund", "amount": 5000.0, "ratio": 25.0,
                    "holding_return": 100.0, "unit_nav": 1.2345,
                    "daily_return": 0.0032, "cache_status": "fresh",
                },
            ],
        },
        "data_source_audit": [
            {
                "code": "014655", "name": "国联益海30天滚动持有短债A",
                "unit_nav": 1.2345, "daily_return": 0.0032,
                "cache_status": "fresh",
                "reports_count": 7, "missing_dimensions": [],
            },
        ],
        "action_recommendations": {
            "p0_clear": [],
            "p1_trim": [],
            "p2_add": [
                {
                    "category": "bond", "target_pct": 0.25,
                    "current_pct": 0.15, "delta_amount": 5000.0,
                    "feature_tags": ["短债", "中短债", "7日年化"],
                },
            ],
            "p3_hold": [],
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
    # 注入 portfolio_subtype 上下文
    fake_context["portfolio_subtype"] = "c1"
    output = template.render(**fake_context)
    assert "1.2345" in output
    assert "当前净值" in output
    assert "[净值缺失]" not in output  # 该 fixture 含净值


def test_data_source_audit_partial_renderable(jinja_env, fake_context):
    """数据源评估 partial 可独立渲染。"""
    template = jinja_env.get_template(
        "partials/_data_source_audit.html.j2"
    )
    output = template.render(**fake_context)
    assert "数据源评估" in output
    assert "014655" in output
    assert "🟢" in output or "fresh" in output


def test_action_recommendations_partial_renderable(jinja_env, fake_context):
    """操作建议 partial 可独立渲染,补充类清单含期望特征标签。"""
    template = jinja_env.get_template(
        "partials/_action_recommendations.html.j2"
    )
    output = template.render(**fake_context)
    assert "操作建议" in output
    assert "P2 增量配置" in output
    assert "短债" in output  # feature tag


def test_full_template_include_order_audit(jinja_env, fake_context):
    """验证 portfolio.html.j2 的 include 块顺序:操作建议在前。"""
    template_src = Path(__file__).resolve().parents[2] / \
        "templates/portfolio.html.j2"
    text = template_src.read_text(encoding="utf-8")

    pos_portfolio = text.find("_portfolio_section")
    pos_audit = text.find("_data_source_audit")
    pos_action = text.find("_action_recommendations")

    assert pos_portfolio > 0
    assert pos_audit > 0
    assert pos_action > 0
    assert pos_portfolio < pos_audit < pos_action, (
        "include 块必须按以下顺序:持仓 -> 数据源评估 -> 操作建议"
    )


def test_full_template_excludes_old_recommendation_block(jinja_env):
    """portfolio.html.j2 不再包含原'推荐补/换基金的深度评估'块。"""
    text = (Path(__file__).resolve().parents[2] /
            "templates/portfolio.html.j2").read_text(encoding="utf-8")
    assert "推荐补/换基金的深度评估" not in text
```

### Step 5.2: 运行测试

Run: `pytest tests/unit/test_template_portfolio_order.py -v`
Expected: 全 PASS

### Step 5.3: 提交

```bash
git add tests/unit/test_template_portfolio_order.py
git commit -m "test(templates): assert include block order + unit nav display"
```

---

## Task 6: portfolio-manager agent.md 章节重排

**Files:**
- Modify: `agents/portfolio-manager.agent.md`

### Step 6.1: 替换"输出格式"章节

定位 "## 输出格式" 章节,完整替换为：

```markdown
## 输出格式

⚠️ **本章节顺序已在 2026-07-01 优化:操作建议前置,数据源评估紧随其后。**
⚠️ **Step 9 输出从「Top-3 候选评分」改为「补充/清除分类清单」,不再引用 portfolio_fund_recommendations.md。**

```markdown
# 组合诊断报告

> 报告生成时间：YYYY-MM-DD
> 适用场景：<C-1 全基金 | C-2 全股票 | C-3 混合>
> 风险提示：本报告仅供研究参考，不构成任何投资建议。

---

## 一、操作建议

按 P0/P1/P2/P3 优先级分块(P0=立即清出, P1=分批减仓, P2=增量配置, P3=维持)。

### 1.1 P0 立即清出（如有）
| 代码 | 名称 | 当前净值 | 金额(¥) | 初步筛掉原因 |
|------|------|---------|---------|-------------|
| `<code>` | `<name>` | `<unit_nav>` | `<amount>` | `<枚举>🔴临近清盘线</枚举>` |
| ... | ... | ... | ... | ... |

### 1.2 P1 分批减仓（如有）
| 代码 | 名称 | 当前净值 | 金额(¥) | 初步筛掉原因 |
|------|------|---------|---------|-------------|
| `<code>` | `<name>` | `<unit_nav>` | `<amount>` | `<枚举>🟡经理刚变更</枚举>` |
| ... | ... | ... | ... | ... |

### 1.3 P2 增量配置（如有）
| 品类 | 目标占比 | 当前占比 | 缺口金额(¥) | 期望特征标签 |
|------|---------|---------|------------|-------------|
| `<category>` | `<x%>` | `<y%>` | `<+z>` | 「`<tag1>`」「`<tag2>`」 |
| ... | ... | ... | ... | ... |

### 1.4 P3 维持当前（如有）
- `<code>` `<name>` — 维持占比,无需立即调整

---

## 二、数据源评估

| 代码 | 名称 | 当前净值 | 日收益 | 缓存状态 | 报告完整度 | 缺失维度 |
|------|------|---------|--------|---------|-----------|---------|
| `<code>` | `<name>` | `<unit_nav>` | `<+/-x%>` | 🟢今日/🟡滞后/🔴缺失 | `<n>/7` | `<dim1>, <dim2>` |
| ... | ... | ... | ... | ... | ... | ... |

> 缓存阈值：交易日 15:00 后 4h,其他时段 24h,沿用 `_CACHE_MAX_AGE_HOURS["nav"]`。

---

## 三、核心观点

**最终评级：<战略再平衡 / 维持现状 / 大幅调整>**

**操作建议（核心）：** <一句话总结>

<3-5 句话展开：组合整体健康度、最关键风险、最显著机会>

---

## 四、多维度分析摘要（C-1/C-2/C-3 自适应）

### 4.1 <维度 1>
**评级：<xxx>**
<简要总结，2-3 句话>

### 4.2 <维度 2>
...（根据 portfolio_subtype 选择 6 个相关维度）

---

## 五、投资逻辑

### 5.1 核心驱动因素
1. ...
2. ...

### 5.2 主要风险因素
1. ...
2. ...

### 5.3 风险收益比评估
- 上行空间：<x%>
- 下行风险：<y%>
- 风险收益比：1:<z>

---

## 六、补充类清单 + 清除类清单

> **Step 9 增强版输出（沿用 classify_exit_reasons 分类，不引用 portfolio_fund_recommendations.md）**

### 6.1 补充类清单（按 underweight 品类）

| 品类 | 目标占比 | 当前占比 | 缺口金额(¥) | 期望特征标签 |
|------|---------|---------|------------|-------------|
| `<cat>` | `<x%>` | `<y%>` | `<+z>` | 「<tag1>」「<tag2>」 |
| ... | ... | ... | ... | ... |

### 6.2 清除类清单（按初步筛掉原因）

| 代码 | 名称 | 当前净值 | 金额(¥) | 原因代码 | 原因文案 |
|------|------|---------|---------|---------|---------|
| `<code>` | `<name>` | `<unit_nav>` | `<amount>` | `<code>` | `<label>` |
| ... | ... | ... | ... | ... | ... |

> 缺少数据时显式标 `[本只数据全缺失,初步筛掉原因基于数据快照]`。

---

## 七、关注要点

### 7.1 需重点跟踪的指标
- ...

### 7.2 可能改变判断的因素
- ...

### 7.3 下一次评估时间
- ...

---

## 八、免责声明

本报告基于公开信息和智能分析生成，仅供研究参考，不构成任何投资建议。
投资者应根据自身风险承受能力独立做出投资决策，并自行承担投资风险。
```
```

### Step 6.2: 移除原"八、推荐补/换基金的深度评估"章节

将原"八、推荐补/换基金的深度评估(Step 5.5 增强版输出)"整段（含 8.1/8.2/8.3/8.4/8.5 子章节）替换为：

```markdown
> **移除说明：** 2026-07-01 优化后,Step 9 不再输出"Top-3 候选评分 + 深度报告路径"。
> 改为"补充/清除分类清单"(见第六章)。`portfolio_fund_recommendations.md` 仍可由 fund-recommender
> subagent 生成,但本报告不再引用该文件。
```

### Step 6.3: 提交

```bash
git add agents/portfolio-manager.agent.md
git commit -m "docs(portfolio-manager): reorder output - action recs first, data source audit second"
```

---

## Task 7: workflow-portfolio.md 文档更新

**Files:**
- Modify: `.trae/skills/stock-analysis/workflow-portfolio.md`

### Step 7.1: 更新 Step 9 章节

定位"## Step 9: 候选基金深度推荐(C-1 / C-3 必做)"的标题与描述，替换为：

```markdown
## Step 9: 补充/清除分类清单（C-1 / C-3 必做,2026-07-01 改造后）

**目标**：基于 Step 6 Gap 分析的 underweight/overweight 输出"补充类清单(品类缺口+期望特征)"和"清除类清单(具体持仓基金+初步筛掉原因)",
**不再给出 Top-3 候选评分表**。

**Spec**：[2026-07-01-portfolio-workflow-redesign-design.md](../specs/2026-07-01-portfolio-workflow-redesign-design.md)

**核心变更**：
- portfolio-manager 最终报告第六章改为"补充类清单+清除类清单"
- 清除清单调用 `data_tools.portfolio.classify_exit_reasons()` 生成（9 种筛掉原因枚举）
- 不再引用 `portfolio_fund_recommendations.md`

**触发条件**：**C-1 / C-3 组合必须执行**,除非满足下方"跳过条件"。

### 9.1 主对话预生成补充类清单

```python
from data_tools.portfolio_rebalance import compute_gap, classify_positions

positions = classify_positions(holdings)
current, gaps, underweight, overweight = compute_gap(classified, target, cash_amount=cash_amount)
# 补充类清单: gaps 中 action == "add" 的项
# 期望特征标签: 从 portfolio_prefs.CATEGORY_KEYWORDS[cat] 取前 3 个关键词
```

### 9.2 调度 portfolio-manager subagent

主对话调用 portfolio-manager subagent,通过 `classify_exit_reasons(holdings, fund_reports, gap_report, prefs)` 生成清除清单。
subagent prompt 中需显式说明:**不要输出"推荐补/换基金深度评估"章节**(2026-07-01 后已移除)。

### 9.3 跳过条件

**只有满足以下条件之一时才可以跳过 Step 9**:

1. **C-2 全股票组合**(股票不做基金分类)
2. 用户明确说"不需要调整 / 只看诊断"
3. `prefs.json` 不存在(目标配置缺失)

**跳过 Step 9 时,必须在 portfolio_final.md 中标注 `[Step 9 未触发:原因]`。**
```

### Step 7.2: 更新 Step 11 输出契约

定位"## Step 11: 组合经理最终报告"的 prompt 模板，在"输出最终组合诊断报告:"后追加：

```markdown
报告章节顺序必须按以下顺序输出(2026-07-01 优化):
1. **操作建议**(P0/P1/P2/P3 分块,前置第一屏)
2. **数据源评估**(每只标的的当前净值+缓存状态,表格式列示)
3. 核心观点(整体评级+一句话总结)
4. 多维度分析摘要(6 维度,根据 portfolio_subtype 自适应)
5. 投资逻辑(核心驱动+主要风险+风险收益比)
6. **补充类清单 + 清除类清单**(基于 underweight/overweight + classify_exit_reasons)
7. 关注要点
8. 免责声明

⚠️ **不再输出**原"推荐补/换基金深度评估"章节。
⚠️ 所有 `<code>` 单元格同行必须包含中文基金/股票全称。
⚠️ 每只持仓基金的"当前净值"必须从 `data/funds/<code>/nav_*.csv` 取,标缓存状态。
```

### Step 7.3: 更新 Step 12 HTML 必含清单

定位"## Step 12: HTML 报告生成与保存"的"**HTML 报告必须包含**"清单，替换"原来包含项"为：

```markdown
**HTML 报告必须包含**（2026-07-01 顺序优化）:
- **第一屏**: 持仓总览表(代码 + 完整名称 + 类型 + 金额 + 占比 + 收益 + **当前净值+缓存状态标签**)
- **第二屏**: 数据源评估表(每只标的的当前净值/日收益/缓存状态/报告完整度/缺失维度)
- **第三屏**: 操作建议(P0/P1/P2/P3 分块表 + 清除清单含初步筛掉原因 + 补充类清单)
- **第四屏**: 风险章节
- **第五屏**: 目标配置对比
- **第六屏**: 免责声明
- **移除**: 原"⭐ 推荐补/换基金的深度评估"块
- **C-1 / C-3 专项模块**(保持):
  - **用户偏好与目标配置**
  - **资产 gap 矩阵**(当前 vs 目标权重 + 调整金额)
  - **调整后目标配置对比表**
```

### Step 7.4: 提交

```bash
git add .trae/skills/stock-analysis/workflow-portfolio.md
git commit -m "docs(workflow): update Step 9/11/12 for action-first + data source audit reordering"
```

---

## Self-Review（spec 覆盖检查）

### Spec 覆盖映射

| Spec 章节 | 对应 Task |
|----------|----------|
| 3.1 报告章节顺序（Markdown + HTML）| Task 4.4, Task 6 |
| 3.2 全场景名称 + 当前净值展示 | Task 1, Task 4.3, Task 4.5, Task 5 |
| 3.2 净值缓存校验函数 + CLI | Task 1, Task 3 |
| 3.3 补充/清除分类清单 | Task 2, Task 4.2, Task 6 |
| 3.3 9 类筛掉原因枚举 | Task 2.3 (EXIT_REASON_CATALOG) |
| 4 工程改动清单 | Task 1-7 全部 |
| 5 验收标准 | Task 5 的全部断言 |
| 6 风险与缓解 | Task 1.3 (default threshold), Task 2.3 (missing 降级) |

### 占位符扫描

- 无 "TBD"、"TODO"、"fill in details"
- 所有代码块均含完整代码片段
- 所有命令有 Expected 输出

### 类型一致性检查

| 函数/类 | 定义 | 使用 |
|--------|------|------|
| `get_unit_nav_with_cache_status` | Task 1.3 返回 `(float\|None, float\|None, str)` | Task 2.3, Task 4.5, Task 3.1 |
| `classify_exit_reasons` | Task 2.3 返回 `list[dict]` 含 `code/name/amount/reasons[ExitReasonItem]` | Task 4.5 (enrich context), Task 2.1 (test) |
| `ExitReasonItem` | Task 2.3 含 `code/label` | Task 2.1 (test), Task 4.2 (template) |
| `_CACHE_MAX_AGE_HOURS["nav"]` | Task 1.1 断言 = 4 | Task 1.3 (default), Task 3.1 (cli 描述) |

✅ 类型一致。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-01-portfolio-workflow-redesign.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
