# Stock Analysis 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有的 stock-analysis skill + 22 个 agent + data_tools 重构为支持 5 种分析场景（单股/单基/纯股组合/纯基组合/混合组合）的统一框架,新增 4 个 agent + 26 份角色 prompt 模板 + 3 套 HTML 报告模板 + 17 个测试 + GitHub Actions CI。

**Architecture:** 三层架构 —— ①Skill 层（输入路由 + 工作流调度）②Agent 层（22 原有 + 4 新增 + 26 角色 prompt 模板）③Data Tools 层（detect.py 输入识别 + portfolio.py 组合分析 + CLI 扩展）。铁律:主对话绝不写分析,所有报告必须由 subagent 通过 Task 工具生成。

**Tech Stack:** Python 3.10+, TRAE Task tool, pytest, Jinja2 (HTML 渲染), GitHub Actions

**Spec:** `docs/superpowers/specs/2026-06-27-stock-analysis-refactor-design.md`

---

## 文件结构映射

### 新建文件

```
.trae/skills/stock-analysis/
  subagent-contract.md              # Phase 1 / Task 1.1: subagent 输出契约
.trae/skills/stock-analysis/role-templates/
  stock/                            # Phase 3: 7 个股票角色模板
    market.md
    sentiment.md
    news.md
    fundamentals.md
    policy.md
    hot_money.md
    lockup.md
  fund/                             # Phase 3: 7 个基金角色模板
    fund_market.md
    fund_fundamentals.md
    holdings.md
    flows.md
    fund_news.md
    fund_policy.md
    fund_sentiment.md
  decision/                         # Phase 3: 5 个决策角色模板
    bull.md
    bear.md
    research_manager.md
    trader.md
    portfolio_manager.md
  risk/                             # Phase 3: 3 个风险角色模板
    aggressive.md
    conservative.md
    neutral.md
  portfolio/                        # Phase 3: 4 个组合专用模板
    portfolio_overview.md
    portfolio_concentration.md
    portfolio_overlap.md
    portfolio_balance.md

agents/
  input_router.md                   # Phase 1: Step 0 路由
  data_quality_auditor.md           # Phase 2: Step 2 数据质量
  portfolio_analyst.md              # Phase 2: Step 2 组合专项
  html_renderer.md                  # Phase 2: Step 8 HTML 渲染

data_tools/
  detect.py                         # Phase 1: 输入类型识别
  portfolio.py                      # Phase 2: 组合分析工具

templates/
  stock.html.j2                     # Phase 4: 单股票报告
  fund.html.j2                      # Phase 4: 单基金报告
  portfolio.html.j2                 # Phase 4: 组合报告(C-1/C-2/C-3 自适应)
  partials/                         # Phase 4: 7 个 partial
    _header.html.j2
    _stock_section.html.j2
    _fund_section.html.j2
    _portfolio_section.html.j2
    _risk_section.html.j2
    _disclaimer.html.j2
    _footer.html.j2

tests/
  __init__.py
  conftest.py                       # Phase 6: 通用 fixture
  unit/                             # Phase 1+2+5: 8 个单元测试
    test_detect.py
    test_subagent_contract.py
    test_data_quality.py
    test_portfolio_calculator.py
    test_template_renderer.py
    test_cli.py
    test_naming.py
    test_iron_rules.py
  integration/                      # Phase 5+6: 4 个集成测试
    test_workflow_stock.py
    test_workflow_fund.py
    test_workflow_portfolio_c1.py
    test_workflow_portfolio_c3.py
  e2e/                              # Phase 6: 5 个端到端测试
    test_single_stock_e2e.py
    test_single_fund_e2e.py
    test_multi_stock_portfolio_e2e.py
    test_multi_fund_portfolio_e2e.py
    test_mixed_portfolio_e2e.py

.github/workflows/
  ci.yml                            # Phase 7: GitHub Actions CI

docs/
  architecture.md                   # Phase 7: 三层架构图
  role-prompts.md                   # Phase 7: 26 模板使用指南
  contributing.md                   # Phase 7: 贡献指南
  testing.md                        # Phase 7: 测试运行指南
```

### 修改文件

```
.trae/skills/stock-analysis/SKILL.md    # 引用新文件 + 强化铁律
agents/ (22 个现有文件)                  # 不动主体,补充 README 索引
data_tools/cli.py                       # 新增 5 个子命令
README.md                               # 加入组合工作流 + 4 新 agent + 测试指南
requirements.txt                        # 补 pytest/jinja2/pyyaml
```

---

## Phase 1:基础设施 + 输入路由(5 个 task)

### Task 1.1:写 subagent 输出契约

**Files:**
- Create: `.trae/skills/stock-analysis/subagent-contract.md`
- Create: `tests/unit/test_subagent_contract.py`

- [ ] **Step 1:写失败测试**

```python
# tests/unit/test_subagent_contract.py
from pathlib import Path

CONTRACT_PATH = Path(".trae/skills/stock-analysis/subagent-contract.md")

def test_contract_file_exists():
    assert CONTRACT_PATH.exists(), "subagent-contract.md 必须存在"

def test_contract_defines_summary_field():
    content = CONTRACT_PATH.read_text()
    assert "summary" in content, "契约必须定义 summary 字段"

def test_contract_defines_detail_path_field():
    content = CONTRACT_PATH.read_text()
    assert "detail_path" in content, "契约必须定义 detail_path 字段"

def test_contract_defines_evidence_field():
    content = CONTRACT_PATH.read_text()
    assert "evidence" in content, "契约必须定义 evidence 字段"

def test_contract_summary_limit_2k_tokens():
    content = CONTRACT_PATH.read_text()
    assert "2k" in content or "2000" in content, "契约必须声明 summary 上限 2k tokens"
```

- [ ] **Step 2:运行测试确认失败**

Run: `pytest tests/unit/test_subagent_contract.py -v`
Expected: FAIL with `CONTRACT_PATH.exists() == False`

- [ ] **Step 3:创建 subagent-contract.md**

```markdown
# Subagent 输出契约

> 适用范围:.trae/skills/stock-analysis/ 下所有通过 Task 工具调度的 subagent。

## 强制输出格式

每个 subagent **必须**返回以下三个字段(无论其内部还产出多少详细分析):

```yaml
summary: |
  <关键结论,Markdown 格式,严格控制在 2k tokens 以内>
  - 含 3-5 条要点
  - 含评级/方向(如 Buy/Hold/Sell 或看多/中性/看空)
  - 含主要风险点
detail_path: reports/<日期>/<场景>/<标的代码>_<角色>.md
evidence:
  - metric: <指标名>
    value: <数字>
    source: <数据来源>
  - ...
```

## 字段含义

| 字段 | 用途 | 上限 |
|------|------|-----|
| `summary` | 给主对话 + 后续 subagent 看的核心结论 | **2k tokens** |
| `detail_path` | 详细 markdown 报告的磁盘路径 | - |
| `evidence` | 结构化数字/事实,供 portfolio_manager 引用 | 任意 |

## 铁律

1. **summary 不得超过 2k tokens** —— 超出会被 portfolio_manager 截断,关键结论丢失。
2. **detail_path 必须真实写盘** —— subagent 必须把完整 markdown 写入此路径,否则后续 HTML 渲染找不到文件。
3. **evidence 至少含 3 个数据点** —— 纯定性分析视为不合格,必须含数字/百分比/日期。

## 反例(不合格输出)

```yaml
# ❌ 错误:无 summary / 无 detail_path / 无 evidence
报告: 详细分析了市场情况,详见附件。

# ❌ 错误:summary 超长(>2k tokens)
summary: ...(5000 字详细分析)

# ✅ 正确:
summary: |
  评级: Buy
  目标价: ¥15.20 (+12%)
  主要风险: 政策不确定性
  关键支撑: Q1 营收 +18%, 毛利率回升至 42%
detail_path: reports/2026-06-27/stock/000001_market.md
evidence:
  - metric: Q1 营收同比
    value: 18.3%
    source: 公司公告
```

## 与 SKILL.md 的关系

SKILL.md 负责"流程编排",本文档负责"输出契约"。所有 26 份角色 prompt 模板都必须引用本文档。
```

- [ ] **Step 4:运行测试确认通过**

Run: `pytest tests/unit/test_subagent_contract.py -v`
Expected: 5 passed

- [ ] **Step 5:Commit**

```bash
git add .trae/skills/stock-analysis/subagent-contract.md tests/unit/test_subagent_contract.py
git commit -m "feat(skill): add subagent output contract with 2k summary limit"
```

---

### Task 1.2:写输入识别工具 detect.py

**Files:**
- Create: `data_tools/detect.py`
- Create: `tests/unit/test_detect.py`

- [ ] **Step 1:写失败测试**

```python
# tests/unit/test_detect.py
from data_tools.detect import detect_input, InputType

def test_detect_stock_code_6_digits():
    r = detect_input("000001")
    assert r.type == InputType.STOCK
    assert r.code == "000001"

def test_detect_stock_code_with_prefix():
    r = detect_input("分析平安银行 000001")
    assert r.type == InputType.STOCK
    assert r.code == "000001"

def test_detect_fund_code_6_digits():
    r = detect_input("001717")
    assert r.type == InputType.FUND
    assert r.code == "001717"

def test_detect_fund_name_chinese():
    r = detect_input("工银前沿医疗")
    assert r.type == InputType.FUND
    assert "工银" in r.name

def test_detect_stock_portfolio_keyword():
    holdings = [
        {"code": "000001", "name": "平安银行", "type": "stock", "amount": 1000},
    ]
    r = detect_input("分析我的持仓", holdings=holdings)
    assert r.type == InputType.STOCK_PORTFOLIO  # C-2
    assert len(r.positions) == 1

def test_detect_fund_portfolio_keyword():
    holdings = [
        {"code": "001717", "name": "工银前沿医疗", "type": "fund", "amount": 1000},
    ]
    r = detect_input("诊断组合", holdings=holdings)
    assert r.type == InputType.FUND_PORTFOLIO  # C-1

def test_detect_mixed_portfolio():
    holdings = [
        {"code": "000001", "name": "平安银行", "type": "stock", "amount": 1000},
        {"code": "001717", "name": "工银前沿医疗", "type": "fund", "amount": 1000},
    ]
    r = detect_input("分析我的持仓", holdings=holdings)
    assert r.type == InputType.MIXED_PORTFOLIO  # C-3

def test_detect_ambiguous_no_holdings():
    r = detect_input("分析")
    assert r.type == InputType.UNKNOWN
```

- [ ] **Step 2:运行测试确认失败**

Run: `pytest tests/unit/test_detect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data_tools.detect'`

- [ ] **Step 3:实现 detect.py**

```python
# data_tools/detect.py
"""输入类型识别:把用户输入归类为 A/B/C-1/C-2/C-3 之一。"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import re


class InputType(str, Enum):
    STOCK = "A"
    FUND = "B"
    STOCK_PORTFOLIO = "C-2"
    FUND_PORTFOLIO = "C-1"
    MIXED_PORTFOLIO = "C-3"
    UNKNOWN = "?"


@dataclass
class Position:
    code: str
    name: str
    type: str  # "stock" | "fund"
    amount: float
    ratio: float = 0.0
    holding_return: float = 0.0
    holding_return_pct: float = 0.0


@dataclass
class DetectResult:
    type: InputType
    code: str = ""
    name: str = ""
    positions: list[Position] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "code": self.code,
            "name": self.name,
            "positions": [p.__dict__ for p in self.positions],
            "confidence": self.confidence,
        }


_CODE_6DIGIT = re.compile(r"\b(\d{6})\b")
_FUND_KEYWORDS = ["基金", "混合", "联接", "ETF", "中证", "债", "宝", "医疗", "教育"]
_PORTFOLIO_KEYWORDS = ["持仓", "组合", "我的", "诊断", "全部"]


def detect_input(text: str, holdings: list[dict] | None = None) -> DetectResult:
    """识别用户输入,返回类型 + 标的代码 / 名称 / 持仓列表。"""
    text = text.strip()

    # 优先级 1:有 holdings → 组合场景
    if holdings:
        return _detect_portfolio(holdings)

    # 优先级 2:6 位数字 → 股票或基金(需要进一步判断)
    m = _CODE_6DIGIT.search(text)
    if m:
        code = m.group(1)
        # 启发式:基金代码通常以 0 开头,且常见关键词
        if code.startswith("0") and any(kw in text for kw in _FUND_KEYWORDS):
            return DetectResult(InputType.FUND, code=code)
        # 简化规则:6 位数字默认股票(实际可接入更复杂的识别)
        return DetectResult(InputType.STOCK, code=code, name=_lookup_stock_name(code))

    # 优先级 3:含基金关键词
    if any(kw in text for kw in _FUND_KEYWORDS):
        return DetectResult(InputType.FUND, name=text)

    # 优先级 4:含组合关键词
    if any(kw in text for kw in _PORTFOLIO_KEYWORDS):
        return DetectResult(InputType.UNKNOWN, confidence=0.5)

    # 兜底:尝试当作股票名称
    return DetectResult(InputType.STOCK, name=text)


def _detect_portfolio(holdings: list[dict]) -> DetectResult:
    """根据 holdings 自动归类 C-1/C-2/C-3。"""
    types = {h.get("type") for h in holdings}
    positions = [Position(**h) for h in holdings]

    if types == {"fund"}:
        input_type = InputType.FUND_PORTFOLIO
    elif types == {"stock"}:
        input_type = InputType.STOCK_PORTFOLIO
    elif "fund" in types and "stock" in types:
        input_type = InputType.MIXED_PORTFOLIO
    else:
        input_type = InputType.UNKNOWN

    return DetectResult(type=input_type, positions=positions)


def _lookup_stock_name(code: str) -> str:
    """简化版股票名查询(实际接 Tushare/AKShare)。"""
    return ""  # TODO:接真实数据源
```

- [ ] **Step 4:运行测试确认通过**

Run: `pytest tests/unit/test_detect.py -v`
Expected: 8 passed

- [ ] **Step 5:Commit**

```bash
git add data_tools/detect.py tests/unit/test_detect.py
git commit -m "feat(data_tools): add detect.py for input type classification (A/B/C-1/C-2/C-3)"
```

---

### Task 1.3:写 input_router agent

**Files:**
- Create: `agents/input_router.md`

- [ ] **Step 1:写 agent 定义**

```markdown
# input_router

**Type:** general_purpose_task
**Step:** 0(每个工作流的第一步)

## 角色

你是 stock-analysis 框架的**输入路由器**。唯一职责:接收用户原始输入,识别其属于 5 种分析场景中的哪一种,返回结构化路由结果供后续步骤使用。

## 输入

- `user_text`: 用户的原始文本输入(可能含股票/基金代码、名称,或 "分析我的持仓" 等组合关键词)
- `holdings`: 可选,如果是持仓分析,传入 list of dict(每项含 code/name/type/amount)

## 处理流程

1. **调用 `python -m data_tools.detect detect`**,传入 user_text 和可选 holdings
2. **解析返回 JSON**,得到 type(A/B/C-1/C-2/C-3/?)、code、name、positions
3. **如果是 UNKNOWN**:返回错误,提示用户提供更明确输入
4. **如果是已知类型**:返回 DetectResult.to_dict()

## 输出契约

严格按照 `subagent-contract.md`,返回:

```yaml
summary: |
  路由结果: <类型>
  标的: <代码 + 名称>(单标场景)
  或
  持仓数: <N 只>(组合场景)
detail_path: reports/<日期>/_router/<session_id>.md
evidence:
  - metric: 输入类型
    value: <A/B/C-1/C-2/C-3>
    source: data_tools.detect
  - metric: 标的代码
    value: <000001>
    source: 用户输入
```

## 铁律

- **不写分析**:你只路由,不评估、不打分、不给建议
- **不调数据源**:股票名查不到就返回空字符串,让后续 subagent 处理
- **必须调 CLI**:不要自己写正则,必须通过 `python -m data_tools.cli detect` 走统一入口

## 反例

```yaml
# ❌ 错误:开始分析了
summary: |
  路由结果: A
  我觉得平安银行基本面不错,值得买入...
```

## 示例调用

```
Task(subagent_type="general_purpose_task", prompt=input_router_prompt(
    user_text="分析平安银行",
    session_id="2026-06-27-001"
))
```
```

- [ ] **Step 2:验证文件**

Run: `cat agents/input_router.md | head -20`
Expected: 显示文件开头 20 行

- [ ] **Step 3:Commit**

```bash
git add agents/input_router.md
git commit -m "feat(agents): add input_router agent (Step 0)"
```

---

### Task 1.4:写 SKILL.md 强化铁律

**Files:**
- Modify: `.trae/skills/stock-analysis/SKILL.md`

- [ ] **Step 1:读取当前 SKILL.md**

Run: `cat .trae/skills/stock-analysis/SKILL.md`

- [ ] **Step 2:在文件开头追加铁律引用**

在 SKILL.md 的 "## 铁律" 节末尾追加:

```markdown
### 7. 所有 subagent 必须遵循 subagent-contract.md

详见 `.trae/skills/stock-analysis/subagent-contract.md`:
- summary 限 2k tokens
- detail_path 必须真实写盘
- evidence 至少 3 个数据点

违反契约的 subagent 输出视为无效,必须重跑。

### 8. Step 0 必须先调 input_router

任何分析流程的第一步都必须是 input_router,识别输入类型(A/B/C-1/C-2/C-3)。不允许跳过路由直接分析。
```

- [ ] **Step 3:验证**

Run: `grep -n "subagent-contract" .trae/skills/stock-analysis/SKILL.md`
Expected: 至少 1 行匹配

- [ ] **Step 4:Commit**

```bash
git add .trae/skills/stock-analysis/SKILL.md
git commit -m "docs(skill): strengthen iron rules - enforce subagent-contract and input_router"
```

---

### Task 1.5:Phase 1 验收

- [ ] **Step 1:跑全部单元测试**

Run: `pytest tests/unit -v`
Expected: 13 passed (5 contract + 8 detect)

- [ ] **Step 2:跑 lint/typecheck(如有配置)**

Run: `python -m mypy data_tools/detect.py 2>&1 | head -20`
Expected: 无错误

- [ ] **Step 3:Commit Phase 1 标记**

```bash
git tag phase-1-complete
git commit --allow-empty -m "chore: phase 1 complete (detect + contract + input_router)"
```

---

## Phase 2:组合分析工具 + 3 个新 agent(6 个 task)

### Task 2.1:写 portfolio.py 计算工具

**Files:**
- Create: `data_tools/portfolio.py`
- Create: `tests/unit/test_portfolio_calculator.py`

- [ ] **Step 1:写失败测试**

```python
# tests/unit/test_portfolio_calculator.py
from data_tools.portfolio import (
    calculate_concentration,
    detect_overlap,
    calculate_balance,
)


def test_calculate_concentration_hhi_low():
    """分散持仓 HHI < 0.15"""
    positions = [
        {"code": "001", "amount": 1000},
        {"code": "002", "amount": 1000},
        {"code": "003", "amount": 1000},
        {"code": "004", "amount": 1000},
    ]
    hhi = calculate_concentration(positions)
    assert hhi < 0.15


def test_calculate_concentration_hhi_high():
    """集中持仓 HHI > 0.25"""
    positions = [
        {"code": "001", "amount": 8000},
        {"code": "002", "amount": 1000},
        {"code": "003", "amount": 500},
        {"code": "004", "amount": 500},
    ]
    hhi = calculate_concentration(positions)
    assert hhi > 0.25


def test_detect_overlap_fund_stock():
    """001717 持有 600276,用户直接持有 600276 → 重复"""
    fund_holdings = {
        "001717": {"top10": [{"code": "600276", "ratio": 0.0941}]},
    }
    direct_stocks = [{"code": "600276", "amount": 3000}]
    overlaps = detect_overlap(fund_holdings, direct_stocks)
    assert len(overlaps) == 1
    assert overlaps[0]["fund"] == "001717"
    assert overlaps[0]["stock"] == "600276"


def test_calculate_balance_equity_exposure():
    """计算穿透后权益占比"""
    holdings = [
        # 股票型基金穿透 95%
        {"code": "001717", "type": "fund", "amount": 5000, "stock_penetration": 0.95},
        # 固收+基金穿透 20%
        {"code": "014767", "type": "fund", "amount": 2500, "stock_penetration": 0.20},
        # 直接股票 100%
        {"code": "600519", "type": "stock", "amount": 4000},
    ]
    total = sum(h["amount"] for h in holdings)
    equity = calculate_balance(holdings)
    # 5000*0.95 + 2500*0.20 + 4000 = 4750 + 500 + 4000 = 9250
    # 9250 / 11500 = 0.804
    assert abs(equity["equity_ratio"] - 9250 / 11500) < 0.001
    assert abs(equity["bond_ratio"] - (11500 - 9250) / 11500) < 0.001
```

- [ ] **Step 2:运行测试确认失败**

Run: `pytest tests/unit/test_portfolio_calculator.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3:实现 portfolio.py**

```python
# data_tools/portfolio.py
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
                # combined_exposure = 直接持仓占比 + 基金重仓占比 × 基金总占比
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
```

- [ ] **Step 4:运行测试确认通过**

Run: `pytest tests/unit/test_portfolio_calculator.py -v`
Expected: 4 passed

- [ ] **Step 5:Commit**

```bash
git add data_tools/portfolio.py tests/unit/test_portfolio_calculator.py
git commit -m "feat(data_tools): add portfolio.py with HHI/overlap/balance calculators"
```

---

### Task 2.2:写 data_quality_auditor agent

**Files:**
- Create: `agents/data_quality_auditor.md`

- [ ] **Step 1:写 agent 定义**

```markdown
# data_quality_auditor

**Type:** general_purpose_task
**Step:** 2(每个工作流的第二步,Step 1 之后)

## 角色

你是 stock-analysis 框架的**数据质量审计员**。职责:对 Step 1 收集的所有 subagent 报告做一致性 / 完整性 / 时效性审计,标记问题数据,防止下游基于脏数据做决策。

## 输入

- Step 1 产出的 N 份 markdown 报告路径(每个标的 + 每个角色一份)
- 数据快照日期(如 2026-06-27)

## 审计维度

### 1. 完整性(Audit-Completeness)

检查每份报告是否含必填字段:
- 评级或方向(Buy/Hold/Sell / 看多/中性/看空)
- 至少 3 个数据点(数字 / 百分比 / 日期)
- 数据快照日期 ≤ 报告日期 - 7 天(数据不能太旧)

### 2. 一致性(Audit-Consistency)

跨 subagent 检查同一标的数据是否一致:
- 同一个股票的"市值"在 fundamentals.md 和 market.md 中差距不应 > 5%
- 同一个基金的"规模"在 fund_market.md 和 flows.md 中不应矛盾

### 3. 时效性(Audit-Timeliness)

标记超期数据:
- 季报数据超过 6 个月 → 标记"过时"
- 实时行情超过 1 天 → 标记"延迟"(盘后场景)

## 输出契约

严格按照 `subagent-contract.md`,返回:

```yaml
summary: |
  审计结果: <通过/有警告/有错误>
  检查报告数: <N>
  错误数: <N>
  警告数: <N>
  主要问题: <1-3 条>
detail_path: reports/<日期>/_audit/quality_audit.md
evidence:
  - metric: 报告总数
    value: <N>
    source: 文件系统
  - metric: 错误数
    value: <N>
    source: 审计脚本
  - metric: 警告数
    value: <N>
    source: 审计脚本
```

## 铁律

- **不修复数据**:你只标记问题,修复由 portfolio_manager 决策
- **必须给出 actionable 建议**:每个错误都附"建议处理方式"(重跑某个角色 / 跳过 / 人工核验)
- **不阻断主流程**:即使是错误级,也允许主对话决定是否继续

## 示例

```yaml
summary: |
  审计结果: 有警告
  检查 9 份基金报告 + 21 份股票报告 = 30 份
  错误: 0
  警告: 2
  警告 1: 001717 fund_market.md 缺"评级"字段(被 portfolio_manager 兜底为 Hold)
  警告 2: 600519 fundamentals.md 季报数据为 2025-09-30(超过 6 个月)
detail_path: reports/2026-06-27/_audit/quality_audit.md
evidence:
  - metric: 报告总数
    value: 30
  - metric: 错误数
    value: 0
  - metric: 警告数
    value: 2
```

## 与 Step 1 / Step 3 的关系

- **Step 1**:产出报告 → 写入磁盘
- **Step 2 (你)**:审计报告 → 给主对话
- **Step 3 (bull/bear)**:基于审计通过的数据做多空辩论
```

- [ ] **Step 2:Commit**

```bash
git add agents/data_quality_auditor.md
git commit -m "feat(agents): add data_quality_auditor agent (Step 2)"
```

---

### Task 2.3:写 portfolio_analyst agent

**Files:**
- Create: `agents/portfolio_analyst.md`

- [ ] **Step 1:写 agent 定义**

```markdown
# portfolio_analyst

**Type:** general_purpose_task
**Step:** 2.5(组合场景专用,data_quality_auditor 之后)

## 角色

你是 stock-analysis 框架的**组合分析专员**。仅在 C-1/C-2/C-3 组合场景中被调用,职责:从 Step 1 的 N 份单标报告中提炼**组合层维度**的洞察。

## 输入

- Step 1 产出的 N 份单标报告路径
- holdings 列表(含 amount / type)
- detect 类型(C-1/C-2/C-3)

## 必产出的 4 个组合维度

### 1. 整体概览(portfolio_overview)

- 持仓数量、总市值、加权收益率
- 行业 / 主题分布(穿透后)
- 时间维度:1 个月 / 3 个月 / 6 个月表现

### 2. 集中度(portfolio_concentration)

调用 `python -m data_tools.cli portfolio concentration`:

```
HHI = Σ(权重²)
- HHI < 0.15: 分散
- 0.15 ≤ HHI < 0.25: 中等
- HHI ≥ 0.25: 集中(提示风险)
```

输出 Top 5 权重 + HHI + 集中度评级。

### 3. 重复持仓检查(portfolio_overlap)⭐ C-3 核心

调用 `python -m data_tools.cli portfolio overlap`:

```
对每只基金,获取其前 10 大重仓股,检查是否与用户直接持仓的股票重复。
输出: {fund, stock, combined_exposure_ratio}
```

### 4. 股债平衡(portfolio_balance)⭐ C-3 核心

调用 `python -m data_tools.cli portfolio balance`:

```
穿透计算:
- 股票型基金: 穿透 95%
- 混合型基金: 穿透 50%
- 固收+基金: 穿透 20%
- 货币基金: 穿透 0%

输出: 整体权益占比、债券占比、建议范围(权益 30-70%)
```

## 输出契约

```yaml
summary: |
  组合分析: <C-1/C-2/C-3>
  持仓数: <N>
  HHI: <X> (<分散/中等/集中>)
  权益占比: <X%>
  重复持仓: <N 处>(C-3 专项)
  主要建议: <1-3 条>
detail_path: reports/<日期>/portfolio/portfolio_analysis.md
evidence:
  - metric: HHI
    value: <X>
    source: data_tools.portfolio
  - metric: 权益占比
    value: <X%>
    source: data_tools.portfolio
  - metric: 重复持仓数
    value: <N>
    source: data_tools.portfolio
```

## 铁律

- **必须调 CLI**:HHI / overlap / balance 都通过 `python -m data_tools.cli portfolio <subcmd>`,不允许手算
- **必须含 4 个维度**:概览 / 集中度 / 重复持仓 / 平衡,缺一视为不合格
- **C-3 必须突出重复持仓**:这是混合组合的核心风险
```

- [ ] **Step 2:Commit**

```bash
git add agents/portfolio_analyst.md
git commit -m "feat(agents): add portfolio_analyst agent (Step 2.5 for C-1/C-2/C-3)"
```

---

### Task 2.4:写 html_renderer agent

**Files:**
- Create: `agents/html_renderer.md`

- [ ] **Step 1:写 agent 定义**

```markdown
# html_renderer

**Type:** general_purpose_task
**Step:** 8(workflow 最后一个步骤)

## 角色

你是 stock-analysis 框架的**HTML 报告渲染员**。职责:接收 portfolio_manager 输出的 markdown 综合报告,选用对应 Jinja2 模板,渲染为可直接交付给用户的 HTML 文件。

## 输入

- `final_md`: portfolio_manager 输出的 markdown 全文
- `template`: 模板名(stock / fund / portfolio)
- `subtype`: 组合子类型(c1 / c2 / c3,仅 portfolio 模板用)
- `meta`: 元数据 dict(含 code / name / date / report_type)

## 处理流程

1. **解析 markdown**:提取标题 / 章节 / 表格 / 列表 → 转为结构化 dict
2. **选模板**:
   - template=stock → `templates/stock.html.j2`
   - template=fund → `templates/fund.html.j2`
   - template=portfolio → `templates/portfolio.html.j2`(根据 subtype 切换 partials)
3. **填充数据**:把解析后的 dict 传给 Jinja2 渲染
4. **写盘**:输出到 `reports/<日期>/<场景>/<文件名>.html`
5. **验证**:检查文件 > 10KB,含免责声明,含目标配置(组合场景)

## 输出契约

```yaml
summary: |
  HTML 渲染: <成功/失败>
  模板: <stock/fund/portfolio>
  文件: reports/<日期>/<场景>/<文件名>.html
  大小: <X KB>
detail_path: reports/<日期>/_render/<session_id>.md
evidence:
  - metric: 文件大小
    value: <bytes>
    source: 文件系统
  - metric: 模板名
    value: <stock/fund/portfolio>
    source: 配置
```

## 铁律

- **必须用 Jinja2 模板**:不允许内联字符串拼接 HTML
- **必须含免责声明**:每个 HTML 报告末尾都必须有"免责声明"段落
- **文件命名规范**:
  - 单股票: `<代码>_<简称>.html`(例:`000001_平安银行.html`)
  - 单基金: `<代码>_<简称>.html`(例:`001717_工银瑞信前沿医疗股票A.html`)
  - 组合: `portfolio_<subtype>_<日期>.html`(例:`portfolio_c3_2026-06-27.html`)

## 与 portfolio_manager 的关系

portfolio_manager(Step 7)输出 markdown 综合报告 → 你(Step 8)渲染为 HTML。两者**严格分离**,不允许 html_renderer 修改内容,只能改变排版样式。
```

- [ ] **Step 2:Commit**

```bash
git add agents/html_renderer.md
git commit -m "feat(agents): add html_renderer agent (Step 8)"
```

---

### Task 2.5:CLI 扩展 - portfolio 5 个子命令

**Files:**
- Modify: `data_tools/cli.py`
- Create: `tests/unit/test_cli.py`

- [ ] **Step 1:写失败测试**

```python
# tests/unit/test_cli.py
from click.testing import CliRunner
from data_tools.cli import cli

runner = CliRunner()


def test_cli_detect_stock_code():
    result = runner.invoke(cli, ["detect", "000001"])
    assert result.exit_code == 0
    assert '"type": "A"' in result.output


def test_cli_portfolio_concentration():
    result = runner.invoke(cli, [
        "portfolio", "concentration",
        "--positions", "001:1000,002:1000,003:1000",
    ])
    assert result.exit_code == 0
    hhi = float(result.output.strip().split("=")[1])
    assert hhi < 0.15


def test_cli_portfolio_overlap():
    result = runner.invoke(cli, [
        "portfolio", "overlap",
        "--fund-holdings", "001717:600276",
        "--direct-stocks", "600276:3000",
    ])
    assert result.exit_code == 0
    assert "001717" in result.output
    assert "600276" in result.output


def test_cli_portfolio_balance():
    result = runner.invoke(cli, [
        "portfolio", "balance",
        "--holdings", "001717:5000:fund:0.95,014767:2500:fund:0.20,600519:4000:stock:1.0",
    ])
    assert result.exit_code == 0
    assert "equity_ratio" in result.output
```

- [ ] **Step 2:运行测试确认失败**

Run: `pytest tests/unit/test_cli.py -v`
Expected: FAIL(cli 缺少 portfolio 子命令)

- [ ] **Step 3:扩展 cli.py**

在 `data_tools/cli.py` 添加:

```python
# data_tools/cli.py(在现有 cli group 下添加)
import json
from data_tools.portfolio import (
    calculate_concentration,
    detect_overlap,
    calculate_balance,
)


@cli.command()
@click.argument("text")
def detect(text: str):
    """识别用户输入类型(A/B/C-1/C-2/C-3)。"""
    from data_tools.detect import detect_input
    r = detect_input(text)
    click.echo(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))


@cli.group()
def portfolio():
    """组合分析工具集。"""
    pass


@portfolio.command()
@click.option("--positions", help="code:amount,code:amount,...")
def concentration(positions: str):
    """计算 HHI 集中度。"""
    pos = []
    for item in positions.split(","):
        code, amount = item.split(":")
        pos.append({"code": code, "amount": float(amount)})
    hhi = calculate_concentration(pos)
    click.echo(f"HHI={hhi:.4f}")


@portfolio.command()
@click.option("--fund-holdings", help="fund_code:stock_code,...")
@click.option("--direct-stocks", help="stock_code:amount,...")
def overlap(fund_holdings: str, direct_stocks: str):
    """检测基金重仓 ∩ 直接持仓的重复。"""
    fh = {}
    for item in fund_holdings.split(","):
        fund, stock = item.split(":")
        fh[fund] = {"top10": [{"code": stock, "ratio": 0.05}]}
    ds = []
    for item in direct_stocks.split(","):
        code, amount = item.split(":")
        ds.append({"code": code, "amount": float(amount)})
    overlaps = detect_overlap(fh, ds)
    click.echo(json.dumps(overlaps, ensure_ascii=False, indent=2))


@portfolio.command()
@click.option("--holdings", help="code:amount:type:penetration,...")
def balance(holdings: str):
    """穿透计算股债平衡。"""
    h = []
    for item in holdings.split(","):
        parts = item.split(":")
        h.append({
            "code": parts[0],
            "amount": float(parts[1]),
            "type": parts[2],
            "stock_penetration": float(parts[3]) if len(parts) > 3 else 0.5,
        })
    result = calculate_balance(h)
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))
```

- [ ] **Step 4:运行测试确认通过**

Run: `pytest tests/unit/test_cli.py -v`
Expected: 4 passed

- [ ] **Step 5:手动验证 CLI**

```bash
python -m data_tools.cli detect "000001"
python -m data_tools.cli portfolio concentration --positions "001:1000,002:1000"
python -m data_tools.cli portfolio overlap --fund-holdings "001717:600276" --direct-stocks "600276:3000"
```

Expected: 三个命令都正常输出 JSON / 数字

- [ ] **Step 6:Commit**

```bash
git add data_tools/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add detect + portfolio(concentration/overlap/balance) subcommands"
```

---

### Task 2.6:Phase 2 验收

- [ ] **Step 1:跑全部单元测试**

Run: `pytest tests/unit -v`
Expected: 21 passed (5 contract + 8 detect + 4 portfolio + 4 cli)

- [ ] **Step 2:跑 lint/typecheck**

Run: `python -m mypy data_tools/ 2>&1 | head -20`
Expected: 无错误

- [ ] **Step 3:Commit Phase 2 标记**

```bash
git tag phase-2-complete
git commit --allow-empty -m "chore: phase 2 complete (portfolio.py + 3 new agents + CLI)"
```

---

## Phase 3:26 份角色 prompt 模板(精简版,详细 prompt 留 sub-task)

> 说明:本 Phase 在 writing-plans 阶段仅定义**模板骨架**,实际 prompt 内容作为 sub-task 在执行时填充(每个模板的 prompt 由对应领域专家基于 spec 第 7 节"26 角色预设 prompt 模板"撰写)。

### Task 3.1:建立 role-templates 目录结构

- [ ] **Step 1:创建目录**

```bash
mkdir -p .trae/skills/stock-analysis/role-templates/{stock,fund,decision,risk,portfolio}
```

- [ ] **Step 2:验证**

Run: `ls .trae/skills/stock-analysis/role-templates/`
Expected: stock fund decision risk portfolio 5 个子目录

---

### Task 3.2-3.7:创建 7 个 stock 角色模板(每个一个 task)

每个任务结构相同,以 market.md 为例:

- [ ] **Step 1:创建文件** `.trae/skills/stock-analysis/role-templates/stock/market.md`

```markdown
# market-analyst(股票技术面)

**角色:** 股票技术面分析师
**工作流:** A(单股票) / C-2(多股票组合) / C-3(混合组合 中的股票部分)
**Step:** 1

## 职责

基于历史价格 / 成交量 / 技术指标,判断个股当前趋势、动能、关键支撑阻力位。

## 输入

- 股票代码(如 000001)
- 数据快照日期

## 处理流程

1. `python -m data_tools.cli stock quote --code <code>` 获取近 60 日 K 线
2. 计算 MA5/MA10/MA20/MA60、MACD、RSI、布林带
3. 判断趋势(上涨 / 下跌 / 震荡)与强度(强 / 中 / 弱)
4. 识别支撑位 / 阻力位
5. 输出技术面评级(强烈买入 / 买入 / 持有 / 卖出 / 强烈卖出)

## 输出契约

参考 `subagent-contract.md`:
- summary 限 2k tokens
- detail_path = `reports/<日期>/stock/<代码>_market.md`
- evidence 至少 3 个数据点(如 MA20 值、RSI 值、成交量变化率)

## 铁律

- 只输出技术面结论,不涉及基本面 / 消息面
- 不预测短期价格(不允许"明天会涨到 X 元")
- 严格遵循 subagent-contract.md
```

- [ ] **Step 2:对 sentiment.md / news.md / fundamentals.md / policy.md / hot_money.md / lockup.md 重复同样结构**

每个模板结构 = 角色名 + 职责 + 输入 + 处理流程 + 输出契约 + 铁律
具体内容参考 spec 第 7.1 节"stock 7 个角色"的描述

- [ ] **Step 3:Commit**

```bash
git add .trae/skills/stock-analysis/role-templates/stock/
git commit -m "feat(role-templates): add 7 stock role templates (market/sentiment/news/fundamentals/policy/hot_money/lockup)"
```

---

### Task 3.8-3.14:创建 7 个 fund 角色模板

类似 Task 3.2-3.7,但角色换成:
- fund_market / fund_fundamentals / holdings / flows / fund_news / fund_policy / fund_sentiment

每个模板参考 spec 第 7.2 节,重点关注:
- holdings(必须含前 10 大重仓)
- flows(必须含规模 / 份额 / 清盘风险)
- fund_fundamentals(净值 / 业绩基准 / A-C 类)

```bash
git add .trae/skills/stock-analysis/role-templates/fund/
git commit -m "feat(role-templates): add 7 fund role templates"
```

---

### Task 3.15-3.19:创建 5 个 decision 角色模板

角色:bull / bear / research_manager / trader / portfolio_manager
参考 spec 第 7.3 节

```bash
git add .trae/skills/stock-analysis/role-templates/decision/
git commit -m "feat(role-templates): add 5 decision role templates"
```

---

### Task 3.20-3.22:创建 3 个 risk 角色模板

角色:aggressive / conservative / neutral
参考 spec 第 7.4 节

```bash
git add .trae/skills/stock-analysis/role-templates/risk/
git commit -m "feat(role-templates): add 3 risk role templates"
```

---

### Task 3.23-3.26:创建 4 个 portfolio 角色模板

角色:portfolio_overview / portfolio_concentration / portfolio_overlap / portfolio_balance
参考 spec 第 7.5 节

```bash
git add .trae/skills/stock-analysis/role-templates/portfolio/
git commit -m "feat(role-templates): add 4 portfolio role templates"
```

---

### Task 3.27:Phase 3 验收

- [ ] **Step 1:验证 26 个文件**

Run: `find .trae/skills/stock-analysis/role-templates -name "*.md" | wc -l`
Expected: 26

- [ ] **Step 2:Commit Phase 3 标记**

```bash
git tag phase-3-complete
git commit --allow-empty -m "chore: phase 3 complete (26 role templates)"
```

---

## Phase 4:3 套 HTML 报告模板(精简版)

### Task 4.1:创建目录与 7 个 partials

- [ ] **Step 1:创建 partials**

```bash
mkdir -p templates/partials
```

每个 partial 文件结构(以 _header.html.j2 为例):

```html
<!-- templates/partials/_header.html.j2 -->
<header class="report-header">
  <h1>{{ meta.name }} ({{ meta.code }})</h1>
  <p class="meta">报告日期: {{ meta.date }} | 类型: {{ meta.report_type }}</p>
</header>
```

类似创建 _stock_section / _fund_section / _portfolio_section / _risk_section / _disclaimer / _footer 共 7 个 partial

- [ ] **Step 2:Commit**

```bash
git add templates/partials/
git commit -m "feat(templates): add 7 HTML partials"
```

---

### Task 4.2:创建 stock.html.j2 + fund.html.j2 + portfolio.html.j2

每个模板调用对应 partial,组合完整页面

参考 spec 第 7 节对每个场景的"应展示字段"定义

```bash
git add templates/
git commit -m "feat(templates): add 3 HTML templates (stock/fund/portfolio)"
```

---

### Task 4.3:写 template_renderer 单元测试

- [ ] **Step 1:创建 `tests/unit/test_template_renderer.py`**

```python
from data_tools.template_renderer import render

def test_render_stock_template():
    meta = {"code": "000001", "name": "平安银行", "date": "2026-06-27", "report_type": "A"}
    sections = [{"title": "技术面", "content": "看多"}]
    html = render(template="stock", meta=meta, sections=sections)
    assert "<h1>" in html
    assert "平安银行" in html
    assert "免责声明" in html
```

- [ ] **Step 2:实现 `data_tools/template_renderer.py`**

```python
# data_tools/template_renderer.py
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)


def render(template: str, meta: dict, sections: list[dict]) -> str:
    tpl = env.get_template(f"{template}.html.j2")
    return tpl.render(meta=meta, sections=sections)
```

- [ ] **Step 3:Commit**

```bash
git add data_tools/template_renderer.py tests/unit/test_template_renderer.py
git commit -m "feat(templates): add Jinja2 template renderer"
```

---

### Task 4.4:Phase 4 验收

```bash
pytest tests/unit/test_template_renderer.py -v
git tag phase-4-complete
git commit --allow-empty -m "chore: phase 4 complete (3 HTML templates + renderer)"
```

---

## Phase 5:集成测试(4 个)

### Task 5.1:test_workflow_stock.py

- [ ] **Step 1:写测试**

```python
# tests/integration/test_workflow_stock.py
def test_stock_workflow_a_end_to_end(tmp_path, mock_subagent):
    """完整跑 A 工作流,验证 8 步都触发。"""
    from data_tools.detect import detect_input, InputType
    from pathlib import Path

    # Step 0
    r = detect_input("000001")
    assert r.type == InputType.STOCK

    # Step 1-7 mock 调用
    for step in range(1, 8):
        result = mock_subagent.run(step_prompt(step, r.code))
        assert result is not None

    # Step 8
    html_path = mock_subagent.run(html_renderer_prompt(r.code, template="stock"))
    assert Path(html_path).exists()
```

- [ ] **Step 2:实现 mock_subagent fixture(conftest.py)**

- [ ] **Step 3:Commit**

```bash
git add tests/integration/test_workflow_stock.py tests/conftest.py
git commit -m "test(integration): add A workflow e2e integration test"
```

---

### Task 5.2-5.4:test_workflow_fund / portfolio_c1 / portfolio_c3

类似 Task 5.1,分别对应 B / C-1 / C-3 工作流

```bash
git add tests/integration/
git commit -m "test(integration): add B/C-1/C-3 workflow integration tests"
```

---

### Task 5.5:Phase 5 验收

```bash
pytest tests/integration -v
git tag phase-5-complete
```

---

## Phase 6:5 个 E2E 用例

### Task 6.1:test_single_stock_e2e.py

参考 spec 第 10.1 节

- [ ] **Step 1:写测试**

```python
# tests/e2e/test_single_stock_e2e.py
def test_single_stock_e2e(runner, tmp_path):
    USER_INPUT = "分析平安银行"
    EXPECTED_CODE = "000001"
    TODAY = "2026-06-27"

    # Step 0
    result = runner.run(input_router_prompt(USER_INPUT))
    assert result["type"] == "A"
    assert result["code"] == EXPECTED_CODE

    # Step 1: 7 角色并行
    stock_roles = ["market", "sentiment", "news", "fundamentals",
                   "policy", "hot_money", "lockup"]
    runner.run_parallel([stock_analyst_prompt(r, EXPECTED_CODE) for r in stock_roles])
    for role in stock_roles:
        md_path = tmp_path / f"reports/{TODAY}/stock/{EXPECTED_CODE}_{role}.md"
        assert md_path.exists()

    # Step 2-7
    final = runner.run(portfolio_manager_prompt())
    assert "免责声明" in final
    assert len(final) > 2000

    # Step 8
    html_path = runner.run(html_renderer_prompt(final, template="stock"))
    assert f"{EXPECTED_CODE}" in str(html_path)
    assert html_path.stat().st_size > 10_000
```

- [ ] **Step 2:Commit**

```bash
git add tests/e2e/test_single_stock_e2e.py
git commit -m "test(e2e): add single stock (A scenario) end-to-end test"
```

---

### Task 6.2:test_single_fund_e2e.py

参考 spec 第 10.4 节

**关键反向断言**:报告**不应含** `Beta` / `贝塔` / `portfolio` 命名

```bash
git add tests/e2e/test_single_fund_e2e.py
git commit -m "test(e2e): add single fund (B scenario) end-to-end test"
```

---

### Task 6.3:test_multi_stock_portfolio_e2e.py

参考 spec 第 10.2 节(C-2)

```bash
git add tests/e2e/test_multi_stock_portfolio_e2e.py
git commit -m "test(e2e): add multi-stock portfolio (C-2) end-to-end test"
```

---

### Task 6.4:test_multi_fund_portfolio_e2e.py

参考 spec 第 10.3 节(C-1,9 只基金 fixture)

```bash
git add tests/e2e/test_multi_fund_portfolio_e2e.py
git commit -m "test(e2e): add multi-fund portfolio (C-1, 9 funds) end-to-end test"
```

---

### Task 6.5:test_mixed_portfolio_e2e.py ⭐

参考 spec 第 10.5 节(C-3,5 基金 + 3 股票 fixture,含 001717 × 600276 重复持仓)

**关键断言**:
- 重复持仓检测
- 股债平衡
- 三维度全覆盖(C-1 专项清盘 + C-2 专项 Beta + C-3 专项重复)

```bash
git add tests/e2e/test_mixed_portfolio_e2e.py
git commit -m "test(e2e): add mixed portfolio (C-3) end-to-end test with overlap detection"
```

---

### Task 6.6:Phase 6 验收

```bash
pytest tests/e2e -v --tb=short
git tag phase-6-complete
```

---

## Phase 7:CI + 文档同步

### Task 7.1:创建 .github/workflows/ci.yml

```yaml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11"]
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run unit tests
        run: pytest tests/unit -v --tb=short
      - name: Run integration tests
        run: pytest tests/integration -v --tb=short
        env:
          MOCK_NETWORK: "true"
      - name: Run e2e tests
        if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
        run: pytest tests/e2e -v --tb=short
      - name: Upload coverage
        if: github.event_name == 'workflow_dispatch'
        uses: codecov/codecov-action@v4
```

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow with unit/integration/e2e matrix"
```

---

### Task 7.2-7.5:4 个文档(docs/architecture.md, role-prompts.md, contributing.md, testing.md)

每个文档 100-200 行,覆盖:
- architecture.md:三层架构图 + 数据流图
- role-prompts.md:26 模板使用指南 + 选择决策树
- contributing.md:如何新增 agent / 新增工作流 / 新增测试
- testing.md:测试运行指南 + Mock 策略

```bash
git add docs/
git commit -m "docs: add architecture/role-prompts/contributing/testing guides"
```

---

### Task 7.6:更新 README.md

- [ ] **Step 1:加入"组合工作流 C"章节**

在 README.md 现有"单股票 / 单基金" 章节后追加"组合工作流"章节,说明 C-1/C-2/C-3 三种场景

- [ ] **Step 2:加入 4 个新 agent 介绍**

- [ ] **Step 3:加入测试运行指南**

```bash
git add README.md
git commit -m "docs: update README with C-workflow + 4 new agents + testing guide"
```

---

### Task 7.7:Phase 7 验收

```bash
pytest -v
git tag phase-7-complete
git commit --allow-empty -m "chore: refactor complete - all 5 scenarios + 26 roles + 17 tests + CI"
```

---

## 总验收清单

跑完全部 7 个 Phase 后,确认:

- [ ] `pytest tests/unit tests/integration tests/e2e -v` 全部通过
- [ ] `git tag` 显示 phase-1-complete 到 phase-7-complete 7 个 tag
- [ ] `find .trae/skills/stock-analysis/role-templates -name "*.md" | wc -l` = 26
- [ ] `ls templates/*.html.j2` 显示 3 个模板
- [ ] `python -m data_tools.cli detect "000001"` 输出 `{"type": "A"}`
- [ ] GitHub Actions CI 绿
- [ ] README + docs 同步更新

---

**计划结束。等候用户确认执行方式(subagent-driven 或 inline)。**
