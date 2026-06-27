# Stock-Analysis 重构设计文档

> **日期**: 2026-06-27
> **类型**: 架构重构
> **作者**: brainstorming session (with user)
> **状态**: 已批准,等待 writing-plans

---

## 0. 背景与目标

### 0.1 项目现状
项目 `my_agents/` 当前提供基于 TRAE skill + agent 的多场景(A股 / 公募基金)分析能力。经过实际使用发现:

1. **Skill 触发不可靠**: 输入"持仓"或截图时,模型不严格按照 skill 流程跑
2. **缺少组合工作流**: 当前 skill 只支持单标的工作流(单股/单基),没有"组合/持仓"工作流
3. **流程执行不严格**: 模型经常跳过 subagent 调度,自己拉数据写报告
4. **缺少测试**: 没有端到端验证,无法确认重构不破坏现有功能
5. **缺少 CI**: 提交后没有自动验证

### 0.2 重构目标

- ✅ 实现"自动完整"的多场景分析(单股/单基/纯股组合/纯基组合/混合组合)
- ✅ 找出架构/实现不合理的地方,全面重构
- ✅ 重构后**原有功能全部正常**
- ✅ 新增完整测试 + GitHub Actions CI

### 0.3 重构后兼容性保证

| 原有功能 | 状态 | 兼容性保证 |
|---------|------|----------|
| 单股票分析 | ✅ 保留 | workflow-stock.md 不动,只增加 subagent 调度细节 |
| 单基金分析 | ✅ 保留 | workflow-fund.md 不动 |
| data_tools CLI 所有现有命令 | ✅ 保留 | 不修改 stock_data.py / fund_data.py |
| 22 个 agent 文件 | ✅ 保留 | 只在 agents/ 增加 4 个新文件 |
| 8 大数据源封装 | ✅ 保留 | 数据源封装不动 |
| .trae/skills/stock-analysis/SKILL.md | ✅ 兼容 | 触发条件不变,内部流程优化 |

---

## 1. 设计原则

1. **三层分离**: Skill 触发层 / Agent 定义层 / 数据工具层 各司其职
2. **铁律执行**: 所有报告必须由 subagent 生成,主对话绝不写分析
3. **模板驱动**: 26 份角色预设 prompt 模板 + 3 套 HTML 模板
4. **场景自适应**: 组合工作流 C-1/C-2/C-3 自适应不同维度
5. **测试覆盖**: 8 单元 + 4 集成 + 3 端到端
6. **CI 自动化**: 每次 PR 自动验证

---

## 2. 三层架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: Skill 触发层 (.trae/skills/stock-analysis/)           │
│  ├─ SKILL.md              入口:6 类输入触发 + 6 铁律 + 路由表    │
│  ├─ workflow-{stock,fund,portfolio}.md  3 套工作流             │
│  ├─ agents-roster.md      22 个 agent 索引                      │
│  ├─ role-prompts/         【新增】26 份角色预设 prompt 模板      │
│  ├─ data-periods.md       数据获取周期规范                      │
│  ├─ cli-commands.md       CLI 命令速查                          │
│  └─ html-templates/       【新增】3 套 HTML 报告模板             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2: Agent 定义层 (agents/*.agent.md)                       │
│  ├─ 7 股票分析师 + 7 基金分析师 + 8 决策角色 = 22 个(已有)      │
│  └─ 【新增】4 个:                                              │
│     - input-router          输入识别(标的类型 + JSON 化)        │
│     - data-quality-auditor  数据源评估                          │
│     - portfolio-analyst     组合层面分析                        │
│     - html-renderer         HTML 渲染                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: 数据工具层 (data_tools/)                              │
│  ├─ stock_data.py / fund_data.py / universe.py (已有,不动)     │
│  ├─ 【新增】detect.py     通用代码识别                          │
│  └─ 【新增】portfolio.py  组合诊断核心逻辑                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 五种分析场景

| 场景 | 工作流 | 输入示例 | 输出文件 |
|------|--------|---------|---------|
| **1. 单股票** | A | `000001` / "分析平安银行" | `reports/<日期>/stock/<代码>_<简称>.html` |
| **2. 单基金** | B | `001717` / "工银前沿医疗" | `reports/<日期>/fund/<代码>_<简称>.html` |
| **3. 纯股票组合** | C-2 | 持仓截图 + 全是股票 | `reports/<日期>/portfolio_stock_<日期>.html` |
| **4. 纯基金组合** | C-1 | 持仓截图 + 全是基金 | `reports/<日期>/portfolio_fund_<日期>.html` |
| **5. 混合组合** | C-3 | 持仓截图 + 股票 + 基金 | `reports/<日期>/portfolio_mixed_<日期>.html` |

---

## 4. 工作流协调

```
                   用户输入
                      │
                      ▼
              ┌──────────────┐
              │ input-router │ ← 标的信息结构化(JSON)
              └──────┬───────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   单股票 (A)    单基金 (B)    组合 (C)
        │            │            │
        │            │      ┌─────┴─────┐
        │            │      ▼           ▼
        │            │   C-1 全基金   C-2 全股票   C-3 混合
        │            │      │           │           │
        │            │      └─────┬─────┴───────────┘
        │            │            ▼
        │            │    ┌──────────────────┐
        │            │    │ portfolio-analyst│ ← 组合分析
        │            │    └──────────────────┘
        │            │
        └────────┬───┘
                 ▼
         7 大分析师并行
                 │
                 ▼
        ┌──────────────────┐
        │ data-quality-    │ ← 数据源评估
        │    auditor       │
        └────────┬─────────┘
                 ▼
         bull ⇄ bear 辩论
                 ▼
         research-manager
                 ▼
              trader
                 ▼
    aggressive ⇄ conservative
                 ▼
            neutral 裁决
                 ▼
         portfolio-manager
                 ▼
         ┌──────────────┐
         │ html-renderer│ ← 统一渲染
         └──────┬───────┘
                ▼
        reports/<日期>/*.html
```

---

## 5. 26 份角色预设 Prompt 模板

存放路径:`.trae/skills/stock-analysis/role-prompts/`

### 5.1 模板清单

| # | 模板文件 | 角色 | 占位符 |
|---|---------|------|--------|
| 1 | `market-analyst.md` | 股票技术分析 | `{code}` `{name}` `{date_range}` `{output_dir}` |
| 2 | `sentiment-analyst.md` | 股票舆情 | 同上 |
| 3 | `news-analyst.md` | 股票新闻 | 同上 |
| 4 | `fundamentals-analyst.md` | 股票基本面 | 同上 |
| 5 | `policy-analyst.md` | 股票政策 | 同上 |
| 6 | `hot-money-tracker.md` | 游资 | 同上 |
| 7 | `lockup-watcher.md` | 解禁 | 同上 |
| 8 | `fund-market-analyst.md` | 基金净值 | `{code}` `{name}` `{output_dir}` |
| 9 | `fund-fundamentals-analyst.md` | 基金基本面 | 同上 |
| 10 | `fund-holdings-analyst.md` | 基金重仓股 | 同上 |
| 11 | `fund-flows-analyst.md` | 基金份额 | 同上 |
| 12 | `fund-news-analyst.md` | 基金新闻 | 同上 |
| 13 | `fund-policy-analyst.md` | 基金政策 | 同上 |
| 14 | `fund-sentiment-analyst.md` | 基金情绪 | 同上 |
| 15 | **`input-router.md`** ⭐ | 输入识别 | `{user_input}` `{output_path}` |
| 16 | **`data-quality-auditor.md`** ⭐ | 数据源评估 | `{reports_dir}` `{output_path}` |
| 17 | **`portfolio-analyst.md`** ⭐ | 组合分析 | `{positions_json}` `{type}`(C-1/C-2/C-3) |
| 18 | **`html-renderer.md`** ⭐ | HTML 渲染 | `{markdown_path}` `{template}` `{output_html}` |
| 19 | `bull-researcher.md` | 多头辩论 | `{reports_dir}` `{output_path}` |
| 20 | `bear-researcher.md` | 空头辩论 | 同上 |
| 21 | `research-manager.md` | 研究经理 | 同上 |
| 22 | `trader.md` | 交易员 | 同上 |
| 23 | `aggressive-analyst.md` | 激进风控 | 同上 |
| 24 | `conservative-analyst.md` | 保守风控 | 同上 |
| 25 | `neutral-analyst.md` | 中立裁决 | 同上 |
| 26 | `portfolio-manager.md` | 组合经理 | 同上 |

### 5.2 模板示例:`fund-market-analyst.md`

```markdown
# 你是基金市场分析师 (fund-market-analyst)

## 角色职责
评估基金的净值走势、各阶段业绩(1m/3m/6m/1y/2y/3y/5y/今年来)、
同类排名与四分位排名、波动率与最大回撤。

## 分析标的
- 基金代码:{code}
- 基金名称:{name}
- 数据日期:{date}

## 数据获取(必须先调用并保存)
```bash
python -m data_tools.cli fund performance {code}
python -m data_tools.cli fund nav {code} --start {date_range_start} --end {date_range_end}
```
数据自动保存到 `data/funds/{code}/`,报告保存到 `{output_dir}/{code}_market.md`。

## 输出格式(严格遵守)
```markdown
# {name} 基金市场分析
## 一、最新业绩快照
...
## 二、各阶段业绩(%)
...
## 三、波动与回撤
...
## 四、业绩持续性
...
## 五、结论
- 核心优势: ...
- 主要风险: ...
- 业绩评分(0-10): ...
```

## 返回值
主对话只需你的报告摘要(200 字内),不是完整 markdown。
```

### 5.3 主对话调度协议

```python
from role_prompts import render_prompt
from workflows import detect_workflow

def dispatch(user_input):
    # Step 0: 路由识别
    router_prompt = render_prompt("input-router", user_input=user_input)
    router_output = Task(subagent_type="general_purpose_task", prompt=router_prompt)
    workflow = detect_workflow(router_output)  # A / B / C-1 / C-2 / C-3
    
    if workflow in ("A",):
        return run_single_stock_workflow(router_output)
    elif workflow in ("B",):
        return run_single_fund_workflow(router_output)
    else:  # C-1/C-2/C-3
        return run_portfolio_workflow(router_output, workflow)
```

---

## 6. HTML 报告模板(3 套)

存放路径:`.trae/skills/stock-analysis/html-templates/`

### 6.1 目录结构

```
html-templates/
├── _base.css                      共享 CSS
├── _base.js                       共享 JS
├── _partials/
│   ├── header.html                标题 + 数据时点 + KPI
│   ├── data-source-table.html     数据源评估
│   ├── positions-table.html       持仓总览表
│   ├── industry-exposure.html     行业暴露
│   ├── risk-analysis.html         风险分析
│   ├── optimization.html          优化建议
│   └── disclaimer.html            免责声明
├── template-stock.html            单股报告
├── template-fund.html             单基报告
└── template-portfolio.html        组合报告(自适应 C-1/C-2/C-3)
```

### 6.2 单股模板(template-stock.html - 13 章节)

| # | 章节 | 内容来源 |
|---|------|---------|
| 1 | header | 标题/数据时点/评级卡 |
| 2 | 数据源评估表 | data-quality-auditor |
| 3 | 核心观点 | portfolio-manager |
| 4 | 技术面分析摘要 | market-analyst |
| 5 | 基本面分析摘要 | fundamentals-analyst |
| 6 | 政策面分析摘要 | policy-analyst |
| 7 | 资金面分析摘要 | hot-money-tracker |
| 8 | 情绪面分析摘要 | sentiment-analyst |
| 9 | 风险评估 | lockup-watcher |
| 10 | 投资逻辑 | research-manager + 辩论 |
| 11 | 操作建议 | trader + 中立风控 |
| 12 | 关注要点 | portfolio-manager |
| 13 | 免责声明 | 固定模板 |

### 6.3 单基模板(template-fund.html - 13 章节)

| # | 章节 | 内容来源 |
|---|------|---------|
| 1 | header | 标题/数据时点/评级卡 |
| 2 | 数据源评估表 | data-quality-auditor |
| 3 | 核心观点 | portfolio-manager |
| 4 | 净值业绩分析 | fund-market-analyst |
| 5 | 基金基本面 | fund-fundamentals-analyst |
| 6 | 重仓股分析 | fund-holdings-analyst |
| 7 | 份额变动与清盘风险 | fund-flows-analyst |
| 8 | 新闻与事件 | fund-news-analyst |
| 9 | 政策与情绪 | fund-policy + fund-sentiment |
| 10 | 投资逻辑 | research-manager + 辩论 |
| 11 | 操作建议 | trader + 中立风控 |
| 12 | 关注要点 | portfolio-manager |
| 13 | 免责声明 | 固定模板 |

### 6.4 组合模板(template-portfolio.html - 自适应 17 章节)

| # | 章节 | C-1 全基金 | C-2 全股票 | C-3 混合 |
|---|------|:---:|:---:|:---:|
| 1 | header(组合 KPI) | ✅ | ✅ | ✅ |
| 2 | 数据源评估表 | ✅ | ✅ | ✅ |
| 3 | 持仓总览表 | ✅ | ✅ | ✅ |
| 4 | 核心观点 | ✅ | ✅ | ✅ |
| 5 | 行业/风格暴露矩阵 | ✅ | ✅ | ✅ |
| 6 | 集中度与纪律 | ✅ | ✅ | ✅ |
| 7 | 相关性结构 | ✅ | ✅ | ✅ |
| 8 | 经理集中度 | ✅ | ✅ | ✅ |
| 9 | 申赎压力与清盘风险 | ✅ | ❌ | ✅ |
| 10 | 行业/Beta/估值 | ❌ | ✅ | ✅ |
| 11 | **股债平衡 + 重复持仓检查** | ❌ | ❌ | ✅ |
| 12 | 多维度分析摘要 | ✅ | ✅ | ✅ |
| 13 | 投资逻辑 | ✅ | ✅ | ✅ |
| 14 | 操作建议(分优先级) | ✅ | ✅ | ✅ |
| 15 | 调整后目标配置对比 | ✅ | ✅ | ✅ |
| 16 | 关注要点 | ✅ | ✅ | ✅ |
| 17 | 免责声明 | ✅ | ✅ | ✅ |

### 6.5 报告命名规范

| 场景 | 路径 | 命名示例 |
|------|------|---------|
| 单股票 | `reports/<日期>/stock/<代码>_<简称>.html` | `reports/2026-06-27/stock/000001_平安银行.html` |
| 单基金 | `reports/<日期>/fund/<代码>_<简称>.html` | `reports/2026-06-27/fund/001717_工银前沿医疗.html` |
| 组合 | `reports/<日期>/portfolio_<类型>_<日期>.html` | `reports/2026-06-27/portfolio_mixed_2026-06-27.html` |

---

## 7. data_tools CLI 扩展

### 7.1 新增 5 个子命令

```bash
# 1. 通用类型识别(替代 fund detect,覆盖基金/股票/ETF)
python -m data_tools.cli detect <6位代码>
# 输出:
#   FUND|<基金名称>
#   STOCK|<股票名称>|market(沪深/京/...)
#   ETF|<ETF名称>
#   UNKNOWN

# 2. 组合诊断 - 重叠检查(C-3 混合组合专项)
python -m data_tools.cli portfolio overlap --input positions.json

# 3. 组合诊断 - 行业暴露汇总
python -m data_tools.cli portfolio sector --input positions.json

# 4. 组合诊断 - 相关性矩阵
python -m data_tools.cli portfolio correlation --input positions.json

# 5. 组合诊断 - HHI 集中度指标
python -m data_tools.cli portfolio hhi --input positions.json
```

### 7.2 新增 Python 模块

```
data_tools/
├── __init__.py
├── cli.py              ← 入口(扩展 detect + portfolio 子命令组)
├── stock_data.py       ← 不动
├── fund_data.py        ← 不动
├── universe.py         ← 不动
├── detect.py           ← 【新增】通用代码识别
└── portfolio.py        ← 【新增】组合诊断核心逻辑
```

### 7.3 portfolio.py 核心算法

```python
def compute_overlap(positions: List[Position]) -> Dict:
    """检查基金重仓股 vs 直接持仓股票的重复"""
    ...

def compute_hhi(positions: List[Position]) -> float:
    """HHI = Σ(占比%)²"""
    return sum(p.ratio ** 2 for p in positions)

def compute_sector_exposure(positions: List[Position]) -> Dict[str, float]:
    """穿透到个股,按行业汇总"""
    ...

def compute_correlation_matrix(positions: List[Position]) -> pd.DataFrame:
    """计算持仓标的之间的相关性"""
    ...
```

### 7.4 数据契约:positions.json

```json
{
  "user_id": "optional",
  "snapshot_date": "2026-06-27",
  "positions": [
    {
      "code": "007466",
      "name": "华泰柏瑞中证红利低波ETF联接A",
      "type": "fund",
      "amount": 7920.75,
      "ratio": 26.07,
      "holding_return": -632.62,
      "holding_return_pct": -7.36
    }
  ]
}
```

---

## 8. 单股票完整流程模板

### 8.1 端到端数据流

```
用户输入 → Step 0(input-router) → Step 1(7 分析师并行)
    → Step 2(data-quality) → Step 3(bull/bear 辩论)
    → Step 4(research-manager) → Step 5(trader)
    → Step 6(aggressive/conservative/neutral 风控)
    → Step 7(portfolio-manager) → Step 8(html-renderer)
    → reports/<日期>/stock/<代码>_<简称>.html
```

### 8.2 每 Step 输入/输出/保存路径

| Step | 角色 | 输入 | 输出 | 保存路径 |
|------|------|------|------|---------|
| 0 | input-router | 用户原文 | JSON | `reports/<日期>/stock/<code>_input.json` |
| 1a | market-analyst | Step 0 JSON | 技术分析报告 | `reports/<日期>/stock/<code>_market.md` |
| 1b | sentiment-analyst | 同上 | 舆情报告 | `reports/<日期>/stock/<code>_sentiment.md` |
| 1c | news-analyst | 同上 | 新闻报告 | `reports/<日期>/stock/<code>_news.md` |
| 1d | fundamentals-analyst | 同上 | 基本面报告 | `reports/<日期>/stock/<code>_fundamentals.md` |
| 1e | policy-analyst | 同上 | 政策报告 | `reports/<日期>/stock/<code>_policy.md` |
| 1f | hot-money-tracker | 同上 | 资金报告 | `reports/<日期>/stock/<code>_hot_money.md` |
| 1g | lockup-watcher | 同上 | 解禁报告 | `reports/<日期>/stock/<code>_lockup.md` |
| 2 | data-quality-auditor | Step 1 的 7 份 | 评估表 | `reports/<日期>/stock/<code>_data_quality.md` |
| 3a | bull-researcher | Step 1+2 | 看涨论点 | `reports/<日期>/stock/<code>_bull.md` |
| 3b | bear-researcher | Step 1+2 | 看跌论点 | `reports/<日期>/stock/<code>_bear.md` |
| 4 | research-manager | Step 1+2+3 | 投资计划 | `reports/<日期>/stock/<code>_research_plan.md` |
| 5 | trader | Step 4 | 交易方案 | `reports/<日期>/stock/<code>_trade_plan.md` |
| 6a | aggressive-analyst | Step 4+5 | 支持意见 | `reports/<日期>/stock/<code>_risk_aggressive.md` |
| 6b | conservative-analyst | Step 4+5 | 谨慎意见 | `reports/<日期>/stock/<code>_risk_conservative.md` |
| 6c | neutral-analyst | Step 6a+6b | 裁决 | `reports/<日期>/stock/<code>_risk_neutral.md` |
| 7 | portfolio-manager | Step 1-6 | 最终报告 | `reports/<日期>/stock/<code>_final.md` |
| 8 | html-renderer | Step 7 | HTML | `reports/<日期>/stock/<code>_<简称>.html` |

### 8.3 并发调度矩阵

| Step | 并发 subagent 数 | 同消息 Task 调用数 | 等待前置 |
|------|------------------|------------------|---------|
| 0 | 1 | 1 | 无 |
| 1 | 7 | **7(同消息)** | Step 0 |
| 2 | 1 | 1 | Step 1 全部 |
| 3 | 2 | **2(同消息)** | Step 2 |
| 4 | 1 | 1 | Step 3 |
| 5 | 1 | 1 | Step 4 |
| 6a+6b | 2 | **2(同消息)** | Step 5 |
| 6c | 1 | 1 | Step 6a+6b |
| 7 | 1 | 1 | Step 6 |
| 8 | 1 | 1 | Step 7 |

**铁律**: 同 Step 内 subagent 必须同消息并行,不同 Step 间必须串行等待。

### 8.4 Token 消耗估算

| Step | 单 subagent token | Step 总 token |
|------|------------------|---------------|
| Step 1 (7 并行) | ~15k | ~105k |
| Step 3 (2 并行) | ~10k | ~20k |
| Step 6 (3 并行) | ~8k | ~24k |
| 其它 6 个 | ~10k | ~60k |
| **合计** | | **~210k tokens** |

### 8.5 Step 1a (market-analyst) 输出格式示例

```markdown
# 平安银行 (000001) 技术分析

## 趋势判断
- 当前趋势: 上涨
- 趋势强度: 中
- 趋势持续天数: ...

## 关键技术指标
| 指标 | 当前值 | 信号 | 解读 |
|------|--------|------|------|
| RSI(14) | 65.3 | 中性偏多 | 接近超买但未触发 |
| MACD | 金叉 | 看多 | DIF 上穿 DEA |
| 布林带 | 中轨上方 | 看多 | 价格运行于上中轨之间 |
| SMA50 | 13.20 | 上方 | 中期均线支撑 |
| SMA200 | 12.50 | 上方 | 长期均线支撑 |

## 支撑阻力位
- 强支撑: 12.50(200日均线 + 前期平台)
- 弱支撑: 13.00(整数关口)
- 强阻力: 14.50(前高 + 布林带上轨)
- 弱阻力: 14.00(整数关口)

## 量价关系
- 近 5 日均量: 1.2 亿股
- 今日成交量: 1.5 亿股(放大 25%)
- 量价配合: 良好

## 技术面结论
- 短期: 看多
- 中期: 看多
- 长期: 中性偏多
- 技术评分: 7/10
```

---

## 9. 测试策略

### 9.1 测试金字塔

```
                 ┌──────────────┐
                 │   E2E(3个)   │ 端到端
                 ├──────────────┤
                 │ 集成(4个)    │ workflow 关键节点 + 模板渲染
                 ├──────────────┤
                 │  单元(8个)   │ data_tools 函数 + 模板片段
                 └──────────────┘
```

### 9.2 8 个单元测试

| # | 测试文件 | 覆盖范围 | 用例 |
|---|---------|---------|------|
| 1 | `tests/unit/test_detect.py` | `data_tools.detect` | 6 位代码 → FUND/STOCK/ETF/UNKNOWN |
| 2 | `tests/unit/test_fund_data.py` | `data_tools.fund_data` | 数据解析/格式化 |
| 3 | `tests/unit/test_stock_data.py` | `data_tools.stock_data` | K线/指标解析 |
| 4 | `tests/unit/test_portfolio_overlap.py` | `compute_overlap` | 基金重仓股 ∩ 直接持仓 |
| 5 | `tests/unit/test_portfolio_hhi.py` | `compute_hhi` | HHI 计算 + 风险评级 |
| 6 | `tests/unit/test_portfolio_sector.py` | `compute_sector_exposure` | 穿透行业汇总 |
| 7 | `tests/unit/test_role_prompts.py` | `role-prompts/*` | 模板必填占位符校验 |
| 8 | `tests/unit/test_html_partials.py` | `html-templates/_partials/*` | 片段渲染无报错 |

### 9.3 4 个集成测试

| # | 测试文件 | 覆盖范围 |
|---|---------|---------|
| 1 | `tests/integration/test_cli_fund.py` | `fund info/performance/holdings/flows` 端到端调用 |
| 2 | `tests/integration/test_cli_stock.py` | `kline/indicator/fundamentals` 端到端调用 |
| 3 | `tests/integration/test_workflow_routing.py` | `input-router` agent:6 类输入正确路由 |
| 4 | `tests/integration/test_html_render.py` | `html-renderer` agent:markdown → HTML 渲染 |

### 9.4 5 个端到端用例(详见第 10 节)

> **覆盖说明**: 本设计覆盖全部 5 种场景的端到端用例(单股票 / 单基金 / 多股票组合 / 多基金组合 / 混合组合)。

### 9.5 测试运行策略

```bash
pytest tests/unit -v                    # 单元(< 5 秒)
pytest tests/unit tests/integration -v  # 单元+集成(< 30 秒)
pytest -v                                # 全量(< 5 分钟)
pytest --cov=data_tools --cov-report=term-missing  # 覆盖率
```

### 9.6 Mock 策略(`tests/conftest.py`)

```python
@pytest.fixture
def mock_fund_data():
    """模拟基金 API 返回"""
    return {
        "001717": {
            "info": {"name": "工银前沿医疗股票A", "scale": "73.42亿", ...},
            "performance": {"近1年": "-4.89%", "近3年": "-14.54%", ...},
        }
    }

@pytest.fixture(autouse=True)
def mock_network(monkeypatch):
    """禁止所有真实网络调用"""
    monkeypatch.setattr("data_tools.fund_data._http_get", lambda url: {"mock": True})
```

---

## 10. 端到端用例(3 个)

存放路径:`tests/e2e/`

### 10.1 用例 1:test_single_stock_e2e.py(单股票场景)

#### 测试目标
验证用户输入"分析平安银行"或"000001",能完整跑完 8 步工作流,产出正确的 markdown 中间报告 + 最终 HTML 报告。

#### 测试输入

```python
USER_INPUT = "分析平安银行"
EXPECTED_CODE = "000001"
EXPECTED_NAME = "平安银行"
TODAY = "2026-06-27"
```

#### 验证点(断言清单)

```python
def test_single_stock_e2e(runner, tmp_path):
    # Step 0
    result = runner.run(input_router_prompt(USER_INPUT))
    assert result["type"] == "A"
    assert result["code"] == EXPECTED_CODE
    assert (tmp_path / f"reports/{TODAY}/stock/{EXPECTED_CODE}_input.json").exists()
    
    # Step 1: 7 分析师
    roles = ["market", "sentiment", "news", "fundamentals", 
             "policy", "hot_money", "lockup"]
    runner.run_parallel([analyst_prompt(r, EXPECTED_CODE) for r in roles])
    for role in roles:
        md_path = tmp_path / f"reports/{TODAY}/stock/{EXPECTED_CODE}_{role}.md"
        assert md_path.exists()
        assert len(md_path.read_text()) > 500
    
    # Step 2-7
    quality = runner.run(data_quality_prompt(EXPECTED_CODE))
    bull, bear = runner.run_parallel([bull_prompt(), bear_prompt()])
    plan = runner.run(research_manager_prompt())
    assert plan in ["Buy", "Overweight", "Hold", "Underweight", "Sell"]
    trade = runner.run(trader_prompt())
    assert "入场" in trade or "止损" in trade
    risk_agg, risk_con = runner.run_parallel([
        aggressive_prompt(), conservative_prompt()
    ])
    risk_neu = runner.run(neutral_prompt())
    final = runner.run(portfolio_manager_prompt())
    assert "免责声明" in final
    assert len(final) > 2000
    
    # Step 8: HTML
    html_path = runner.run(html_renderer_prompt(final, template="stock"))
    assert html_path.suffix == ".html"
    assert html_path.stat().st_size > 10_000
    assert "免责声明" in html_path.read_text()
    assert f"{EXPECTED_CODE}_{EXPECTED_NAME}.html" in str(html_path)
```

### 10.2 用例 2:test_multi_stock_portfolio_e2e.py(多股票组合 - C-2 场景)

#### 测试目标
验证从用户输入"分析持仓" + 5 只 A 股持仓,组合工作流 C-2 完整跑通,产出含 C-2 专项维度(行业/Beta/估值)的组合诊断报告。

#### 测试输入

```python
HOLDINGS = [
    {"code": "600519", "name": "贵州茅台", "type": "stock", 
     "amount": 10000, "ratio": 30.0, "holding_return": 500, "holding_return_pct": 5.0},
    {"code": "000858", "name": "五粮液",   "type": "stock", 
     "amount": 8000,  "ratio": 24.0, "holding_return": -200, "holding_return_pct": -2.5},
    {"code": "600276", "name": "恒瑞医药", "type": "stock", 
     "amount": 7000,  "ratio": 21.0, "holding_return": 350, "holding_return_pct": 5.0},
    {"code": "000333", "name": "美的集团", "type": "stock", 
     "amount": 5000,  "ratio": 15.0, "holding_return": 100, "holding_return_pct": 2.0},
    {"code": "300750", "name": "宁德时代", "type": "stock", 
     "amount": 3333,  "ratio": 10.0, "holding_return": -333, "holding_return_pct": -10.0},
]
EXPECTED_TYPE = "C-2"
EXPECTED_HHI = 30**2 + 24**2 + 21**2 + 15**2 + 10**2  # = 2206
```

#### 验证点

```python
def test_multi_stock_portfolio_e2e(runner, tmp_path):
    # Step 0
    result = runner.run(input_router_prompt("分析持仓", holdings=HOLDINGS))
    assert result["type"] == EXPECTED_TYPE, "应识别为 C-2 全股票组合"
    assert len(result["positions"]) == 5
    
    # Step 1: 35 分析师(分批 4+1)
    for batch in chunks(HOLDINGS, 4):
        runner.run_parallel([stock_analyst_prompt(s) for s in batch])
    
    # Step 2: portfolio-analyst C-2 专项
    portfolio_report = runner.run(portfolio_analyst_prompt(
        holdings=HOLDINGS, type=EXPECTED_TYPE
    ))
    assert "行业暴露" in portfolio_report
    assert "市值分布" in portfolio_report or "Beta" in portfolio_report
    assert "估值水平" in portfolio_report
    assert "清盘风险" not in portfolio_report  # C-2 不应含
    assert "股债平衡" not in portfolio_report
    assert "重复持仓" not in portfolio_report
    assert str(EXPECTED_HHI) in portfolio_report or "2206" in portfolio_report
    
    # Step 3-7
    bull, bear = runner.run_parallel([bull_prompt(scope="portfolio"), 
                                       bear_prompt(scope="portfolio")])
    final = runner.run(portfolio_manager_prompt(scope="portfolio"))
    
    # Step 8
    html_path = runner.run(html_renderer_prompt(
        final, template="portfolio", subtype="stock"
    ))
    assert "portfolio_stock_2026-06-27.html" in str(html_path)
    html_content = html_path.read_text()
    assert "行业暴露" in html_content
    assert "清盘风险" not in html_content  # C-2 不应含
```

### 10.3 用例 3:test_multi_fund_portfolio_e2e.py(多基金组合 - C-1 场景)

#### 测试目标
验证从用户输入"分析我的基金持仓" + 9 只基金持仓,组合工作流 C-1 完整跑通,产出含 C-1 专项维度(清盘/规模/经理)的组合诊断报告。

#### 测试输入(模拟用户真实持仓)

```python
HOLDINGS = [
    {"code": "007466", "name": "华泰柏瑞中证红利低波ETF联接A", "type": "fund",
     "amount": 7920.75, "ratio": 26.07, "holding_return": -632.62, "holding_return_pct": -7.36},
    {"code": "001717", "name": "工银瑞信前沿医疗股票A", "type": "fund",
     "amount": 5899.37, "ratio": 19.42, "holding_return": 97.51, "holding_return_pct": 1.68},
    {"code": "005313", "name": "万家中证1000指数增强A", "type": "fund",
     "amount": 1980.94, "ratio": 6.52, "holding_return": 5.94, "holding_return_pct": 0.30},
    {"code": "015143", "name": "中欧智能制造混合A", "type": "fund",
     "amount": 1779.64, "ratio": 5.86, "holding_return": 422.18, "holding_return_pct": 31.10},
    {"code": "080005", "name": "长盛量化红利策略混合A", "type": "fund",
     "amount": 1768.88, "ratio": 5.82, "holding_return": -151.12, "holding_return_pct": -7.87},
    {"code": "004069", "name": "南方中证全指证券公司ETF联接A", "type": "fund",
     "amount": 1316.72, "ratio": 4.33, "holding_return": 66.72, "holding_return_pct": 5.34},
    {"code": "010673", "name": "兴全中证800六个月持有期指数增强A", "type": "fund",
     "amount": 832.96, "ratio": 2.74, "holding_return": 6.28, "holding_return_pct": 0.76},
    {"code": "024419", "name": "华夏创业板新能源ETF联接A", "type": "fund",
     "amount": 567.20, "ratio": 1.87, "holding_return": -49.52, "holding_return_pct": -8.03},
    {"code": "014767", "name": "景顺长城华城稳健6个月持有A", "type": "fund",
     "amount": 476.11, "ratio": 1.57, "holding_return": -9.04, "holding_return_pct": -1.86},
]
EXPECTED_TYPE = "C-1"
```

#### 验证点

```python
def test_multi_fund_portfolio_e2e(runner, tmp_path):
    # Step 0
    result = runner.run(input_router_prompt("分析我的基金持仓", holdings=HOLDINGS))
    assert result["type"] == EXPECTED_TYPE
    assert len(result["positions"]) == 9
    
    # Step 1: 63 分析师(分批 3+3+3)
    for batch in chunks(HOLDINGS, 3):
        runner.run_parallel([fund_analyst_prompt(f) for f in batch])
    
    # Step 2: portfolio-analyst C-1 专项
    portfolio_report = runner.run(portfolio_analyst_prompt(
        holdings=HOLDINGS, type=EXPECTED_TYPE
    ))
    assert "清盘风险" in portfolio_report
    assert "规模" in portfolio_report
    assert "经理" in portfolio_report
    assert "024419" in portfolio_report, "024419 应被标记"
    assert "0.79" in portfolio_report or "清盘预警" in portfolio_report
    assert "080005" in portfolio_report
    assert "015143" in portfolio_report
    assert "Beta" not in portfolio_report
    assert "股债平衡" not in portfolio_report
    assert "重复持仓" not in portfolio_report
    assert ("25%" in portfolio_report or "纪律线" in portfolio_report)
    assert "优先级 1" in portfolio_report or "立即" in portfolio_report
    
    # Step 3-7
    final = runner.run(portfolio_manager_prompt(scope="portfolio"))
    assert "免责声明" in final
    assert "目标配置" in final
    assert len(final) > 3000
    
    # Step 8
    html_path = runner.run(html_renderer_prompt(
        final, template="portfolio", subtype="fund"
    ))
    assert "portfolio_fund_2026-06-27.html" in str(html_path)
    html_content = html_path.read_text()
    assert "清盘风险" in html_content
    assert "Beta" not in html_content
```

### 10.4 用例 4:test_single_fund_e2e.py(单基金 - B 场景)

#### 测试目标
**验证**: 用户输入"分析工银前沿医疗"或"001717",能完整跑完 8 步工作流 B(单基金),产出正确的基金分析报告 + HTML。重点验证:**基金特有维度**(净值/重仓股/份额/清盘/A-C 类选择)与**不应含股票维度**(行业/Beta/估值)的反向断言。

#### 测试输入

```python
# tests/e2e/test_single_fund_e2e.py

USER_INPUT = "分析工银前沿医疗"
EXPECTED_CODE = "001717"
EXPECTED_NAME = "工银瑞信前沿医疗股票A"
EXPECTED_FUND_TYPE = "股票型"
EXPECTED_SCALE = "73.42亿"  # 季报快照
TODAY = "2026-06-27"
```

#### 验证点(断言清单)

```python
def test_single_fund_e2e(runner, tmp_path):
    # ====== Step 0: 输入识别 → B ======
    result = runner.run(input_router_prompt(USER_INPUT))
    assert result["type"] == "B", "应识别为单基金工作流"
    assert result["code"] == EXPECTED_CODE
    assert result["name"] == EXPECTED_NAME
    
    # ====== Step 1: 7 基金分析师并行 ======
    fund_roles = ["fund_market", "fund_fundamentals", "holdings", 
                  "flows", "fund_news", "fund_policy", "fund_sentiment"]
    runner.run_parallel([fund_analyst_prompt(r, EXPECTED_CODE) for r in fund_roles])
    for role in fund_roles:
        md_path = tmp_path / f"reports/{TODAY}/fund/{EXPECTED_CODE}_{role}.md"
        assert md_path.exists(), f"缺少基金分析报告: {md_path}"
        assert len(md_path.read_text()) > 500
    
    # 持仓报告含前 10 大重仓
    holdings_md = (tmp_path / f"reports/{TODAY}/fund/{EXPECTED_CODE}_holdings.md").read_text()
    assert "恒瑞医药" in holdings_md, "001717 重仓恒瑞医药"
    assert "信立泰" in holdings_md, "001717 重仓信立泰"
    
    # 份额/规模报告
    flows_md = (tmp_path / f"reports/{TODAY}/fund/{EXPECTED_CODE}_flows.md").read_text()
    assert EXPECTED_SCALE in flows_md, "规模 73.42 亿应在报告中"
    assert "清盘" in flows_md, "应评估清盘风险(规模 > 2 亿为低风险)"
    assert "低" in flows_md or "正常" in flows_md, "73.42 亿规模应判定为低风险"
    
    # ====== Step 2: 数据质量 ======
    quality = runner.run(data_quality_prompt(EXPECTED_CODE))
    assert "fund performance" in quality.lower() or "业绩" in quality
    
    # ====== Step 3: 多空辩论 ======
    bull, bear = runner.run_parallel([bull_prompt(), bear_prompt()])
    assert bull and bear
    
    # ====== Step 4-7: 决策流程 ======
    plan = runner.run(research_manager_prompt())
    assert plan in ["Buy", "Overweight", "Hold", "Underweight", "Sell"]
    
    trade = runner.run(trader_prompt())
    # 基金特有: A/C 类选择 + 分批策略
    assert "A 类" in trade or "C 类" in trade, "应建议 A/C 类选择"
    assert "分批" in trade or "定投" in trade, "应有分批/定投策略"
    
    risk_agg, risk_con = runner.run_parallel([
        aggressive_prompt(), conservative_prompt()
    ])
    risk_neu = runner.run(neutral_prompt())
    final = runner.run(portfolio_manager_prompt())
    
    # ====== 反向断言: 不应含股票工作流维度 ======
    assert "Beta" not in final, "单基金报告不应含 Beta"
    assert "贝塔" not in final, "单基金报告不应含贝塔"
    assert "行业分布" not in final or "重仓股行业" in final, \
        "单基金可以谈重仓股行业,但不应含直接行业分析章节"
    
    # ====== Step 8: HTML 渲染 ======
    html_path = runner.run(html_renderer_prompt(final, template="fund"))
    assert html_path.exists()
    assert html_path.stat().st_size > 10_000
    
    # 命名规范
    assert f"{EXPECTED_CODE}_{EXPECTED_NAME}.html" in str(html_path)
    
    html_content = html_path.read_text()
    assert "净值业绩" in html_content
    assert "重仓股" in html_content
    assert "清盘风险" in html_content
    assert "A 类" in html_content or "C 类" in html_content
    assert "免责声明" in html_content
    
    # 反向断言 HTML 不应含
    assert "portfolio" not in html_path.name.lower(), \
        "单基金报告文件名不应含 portfolio"
    assert "Beta" not in html_content
```

#### 用例 4 关键设计

1. **正向断言**: 验证基金特有维度(净值/重仓股/规模/A-C 类/分批)齐全
2. **反向断言**: 验证股票维度(Beta/贝塔)缺失 — 防止误把单基金当股票处理
3. **命名规范**: `<基金代码>_<基金简称>.html`,不带 portfolio 前缀
4. **模板正确性**: 使用 template-fund.html(非 template-stock.html)

---

### 10.5 用例 5:test_mixed_portfolio_e2e.py(混合组合 - C-3 场景)⭐ 核心

#### 测试目标
**验证**: 用户输入"分析我的混合持仓" + 5 只基金 + 3 只股票(典型混合组合),组合工作流 C-3 完整跑通,产出含 **"股债平衡 + 重复持仓检查"** 专项的报告。这是 5 种场景中**最复杂**的一种,验证:
- 基金 + 股票的混合调度(分两批 subagent)
- **重复持仓检测**(基金重仓股 ∩ 直接持仓)
- **股债平衡计算**(穿透权益类暴露)
- C-1/C-2/C-3 自适应维度

#### 测试输入

```python
# tests/e2e/test_mixed_portfolio_e2e.py

# 5 只基金 + 3 只股票(典型混合持仓)
HOLDINGS = [
    # === 基金部分(56%) ===
    {"code": "001717", "name": "工银瑞信前沿医疗股票A", "type": "fund",
     "amount": 5000, "ratio": 20.0, "holding_return": -300, "holding_return_pct": -6.0},
    {"code": "005313", "name": "万家中证1000指数增强A", "type": "fund",
     "amount": 3000, "ratio": 12.0, "holding_return": 100, "holding_return_pct": 3.3},
    {"code": "014767", "name": "景顺长城华城稳健6个月持有A", "type": "fund",
     "amount": 2500, "ratio": 10.0, "holding_return": 50, "holding_return_pct": 2.0},
    {"code": "004069", "name": "南方中证全指证券公司ETF联接A", "type": "fund",
     "amount": 2000, "ratio": 8.0, "holding_return": 100, "holding_return_pct": 5.0},
    {"code": "007466", "name": "华泰柏瑞中证红利低波ETF联接A", "type": "fund",
     "amount": 1500, "ratio": 6.0, "holding_return": -50, "holding_return_pct": -3.3},
    
    # === 股票部分(34%) — 关键:600276 与 001717 重仓股重复 ===
    {"code": "600519", "name": "贵州茅台", "type": "stock",
     "amount": 4000, "ratio": 16.0, "holding_return": 200, "holding_return_pct": 5.0},
    {"code": "600276", "name": "恒瑞医药", "type": "stock",  # ⭐ 与 001717 重复
     "amount": 3000, "ratio": 12.0, "holding_return": -150, "holding_return_pct": -5.0},
    {"code": "300750", "name": "宁德时代", "type": "stock",
     "amount": 1500, "ratio": 6.0, "holding_return": -100, "holding_return_pct": -6.7},
]
EXPECTED_TYPE = "C-3"
EXPECTED_FUND_COUNT = 5
EXPECTED_STOCK_COUNT = 3
EXPECTED_TOTAL_RATIO = 100.0
# 关键预期:001717 重仓恒瑞 + 直接持有 600276 → 重复持仓警告
EXPECTED_OVERLAP = {
    "fund": "001717",
    "stock": "600276",
    "combined_exposure_ratio": 12.0 + 20.0 * 0.0941  # 假设恒瑞占 001717 9.41%
}
TODAY = "2026-06-27"
```

#### 测试步骤

| Step | 调用 |
|------|------|
| 0 | input-router → 识别 C-3 |
| 1a | 5 只基金 × 7 基金分析师 = 35 subagent(分批 3+2) |
| 1b | 3 只股票 × 7 股票分析师 = 21 subagent(分批 2+1) |
| 2 | portfolio-analyst → C-3 专项(股债平衡 + 重复持仓) |
| 3-7 | 标准决策流程 |
| 8 | html-renderer → portfolio_mixed_<日期>.html |

#### 验证点(断言清单)

```python
def test_mixed_portfolio_e2e(runner, tmp_path):
    # ====== Step 0: 输入识别 → C-3 ======
    result = runner.run(input_router_prompt("分析我的混合持仓", holdings=HOLDINGS))
    assert result["type"] == EXPECTED_TYPE, "应识别为 C-3 混合组合"
    assert len([p for p in result["positions"] if p["type"] == "fund"]) == EXPECTED_FUND_COUNT
    assert len([p for p in result["positions"] if p["type"] == "stock"]) == EXPECTED_STOCK_COUNT
    
    # ====== Step 1a: 35 基金分析师(分批 3+2) ======
    funds = [p for p in HOLDINGS if p["type"] == "fund"]
    for batch in chunks(funds, 3):
        runner.run_parallel([fund_analyst_prompt(f) for f in batch])
    
    # ====== Step 1b: 21 股票分析师(分批 2+1) ======
    stocks = [p for p in HOLDINGS if p["type"] == "stock"]
    for batch in chunks(stocks, 2):
        runner.run_parallel([stock_analyst_prompt(s) for s in batch])
    
    # 验证 5 只基金 × 7 角色 = 35 份
    for fund in funds:
        for role in ["fund_market", "fund_fundamentals", "holdings",
                     "flows", "fund_news", "fund_policy", "fund_sentiment"]:
            md_path = tmp_path / f"reports/{TODAY}/fund/{fund['code']}_{role}.md"
            assert md_path.exists(), f"缺少基金报告: {md_path}"
    
    # 验证 3 只股票 × 7 角色 = 21 份
    for stock in stocks:
        for role in ["market", "sentiment", "news", "fundamentals",
                     "policy", "hot_money", "lockup"]:
            md_path = tmp_path / f"reports/{TODAY}/stock/{stock['code']}_{role}.md"
            assert md_path.exists(), f"缺少股票报告: {md_path}"
    
    # ====== Step 2: portfolio-analyst(C-3 专项) ======
    portfolio_report = runner.run(portfolio_analyst_prompt(
        holdings=HOLDINGS, type=EXPECTED_TYPE
    ))
    
    # C-3 必含维度
    assert "重复持仓" in portfolio_report, "C-3 必含重复持仓章节"
    assert "股债平衡" in portfolio_report, "C-3 必含股债平衡章节"
    
    # ⭐ 关键: 重复持仓检测
    assert "001717" in portfolio_report and "600276" in portfolio_report
    assert "恒瑞医药" in portfolio_report, "重复持仓应为恒瑞医药"
    assert "重复" in portfolio_report or "暴露" in portfolio_report
    
    # 股债平衡计算
    assert "权益" in portfolio_report
    assert "固收" in portfolio_report or "债券" in portfolio_report
    # 权益占比 = 100% - 014767(固收+, 假设权益 20% × 10% = 2%)
    #           - 余额(无) = 大约 70-80%
    
    # 行业暴露(穿透到基金重仓股)
    assert "行业" in portfolio_report
    # 医药行业 = 001717(医药主题 20%) + 600276(12%) + 部分 001717 重仓股 = 应 > 30%
    
    # 共性维度
    assert "清盘风险" in portfolio_report, "C-3 基金部分必含清盘风险"
    assert "Beta" in portfolio_report or "贝塔" in portfolio_report, \
        "C-3 股票部分必含 Beta"
    assert "经理" in portfolio_report, "C-3 共性维度含经理"
    
    # ====== Step 3-7: 决策流程 ======
    bull, bear = runner.run_parallel([bull_prompt(scope="portfolio"), 
                                       bear_prompt(scope="portfolio")])
    plan = runner.run(research_manager_prompt(scope="portfolio"))
    trade = runner.run(trader_prompt(scope="portfolio"))
    
    # 交易方案应针对混合组合
    assert "赎回" in trade or "申购" in trade or "再平衡" in trade
    
    risk_agg, risk_con = runner.run_parallel([
        aggressive_prompt(scope="portfolio"), 
        conservative_prompt(scope="portfolio")
    ])
    risk_neu = runner.run(neutral_prompt(scope="portfolio"))
    
    final = runner.run(portfolio_manager_prompt(scope="portfolio"))
    
    # 最终报告必含
    assert "免责声明" in final
    assert "目标配置" in final
    assert "股债" in final or "权益" in final
    assert "重复持仓" in final
    assert len(final) > 4000  # 混合组合报告最长
    
    # ====== Step 8: HTML 渲染 ======
    html_path = runner.run(html_renderer_prompt(
        final, template="portfolio", subtype="mixed"
    ))
    assert "portfolio_mixed_2026-06-27.html" in str(html_path)
    
    html_content = html_path.read_text()
    # C-3 HTML 必含
    assert "重复持仓" in html_content
    assert "股债" in html_content or "权益" in html_content
    assert "清盘风险" in html_content, "基金部分应有清盘风险"
    assert "Beta" in html_content, "股票部分应有 Beta"
    assert "免责声明" in html_content
    
    # C-3 不应只有 C-1 或 C-2 的特征(必须有所有维度)
    assert "重复持仓" in html_content and "Beta" in html_content and "清盘风险" in html_content
```

#### 用例 5 关键设计

1. **重复持仓 fixture**: 精心构造 001717(医药主题) + 600276(恒瑞医药) 的重复场景
2. **两批调度**: 35 基金 subagent + 21 股票 subagent 分开并行(不混合调度,避免混淆)
3. **C-3 三维度全覆盖**: 同时验证 C-1 专项(清盘) + C-2 专项(Beta) + C-3 专项(重复持仓/股债平衡)
4. **行业穿透**: 验证医药行业的合并暴露(基金 + 直接持仓)

#### 用例 5 输出报告示例(`portfolio_mixed_2026-06-27.html`)

```markdown
## 11. 股债平衡 + 重复持仓检查 ⭐ C-3 核心

### 11.1 资产类别穿透
| 类别 | 占比 | 标的 |
|------|------|------|
| 直接股票 | 34.0% | 贵州茅台 / 恒瑞医药 / 宁德时代 |
| 股票型基金(穿透) | 20.0% | 工银前沿医疗(医药) |
| 混合型基金(穿透 50%) | 6.0% | 万家中证1000 + 南方证券 |
| 固收+基金(穿透 20%) | 2.0% | 景顺长城稳健 |
| 红利低波(穿透 50%) | 3.0% | 华泰柏瑞红利低波 |
| **整体权益暴露** | **63.0%** | — |
| 现金 + 货基 | 0% | — |

### 11.2 ⚠️ 重复持仓检查
| 基金 | 基金重仓股 | 直接持仓 | 重复暴露 |
|------|-----------|---------|---------|
| **001717 工银前沿医疗** | 恒瑞医药 9.41% | **600276 恒瑞医药 12%** | ⚠️ 合计 13.88% |

**建议**: 减持 600276 恒瑞医药,或减持 001717,降低重复暴露。

### 11.3 跨类别相关性
- 直接股票 vs 股票型基金: 相关性高(0.85) — 医药板块联动
- 直接股票 vs 固收+基金: 相关性低(0.15) — 分散有效
```

---

### 10.6 E2E Fixture(`tests/e2e/conftest.py`)

```python
@pytest.fixture
def runner():
    """模拟主对话调度流程"""
    class WorkflowRunner:
        def __init__(self):
            self.context = {}
        
        def run(self, prompt):
            return mock_subagent_response(prompt, self.context)
        
        def run_parallel(self, prompts):
            return [mock_subagent_response(p, self.context) for p in prompts]
        
        def run_chained(self, prompts):
            return [mock_subagent_response(p, self.context) for p in prompts]
    
    return WorkflowRunner()

@pytest.fixture
def tmp_path(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    return tmp_path
```

### 10.7 E2E 用例执行矩阵

| # | 用例 | 输入 | 工作流 | 期望报告 | 关键断言数 |
|---|------|------|--------|---------|----------|
| 1 | 单股票 | "分析平安银行" | A | `000001_平安银行.html` | ~12 |
| 2 | 单基金 | "分析工银前沿医疗" | B | `001717_工银瑞信前沿医疗股票A.html` | ~18 |
| 3 | 多股票组合 | 5 只股票 | C-2 | `portfolio_stock_2026-06-27.html` | ~25 |
| 4 | 多基金组合 | 9 只基金 | C-1 | `portfolio_fund_2026-06-27.html` | ~30 |
| 5 | 混合组合 | 5 基金 + 3 股票 | C-3 | `portfolio_mixed_2026-06-27.html` | ~40 |

**总计**: 5 个 e2e 用例,覆盖全部 5 种分析场景,~125 个关键断言。

---

## 11. CI 设计(GitHub Actions)

文件:`.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]
  schedule:
    - cron: '0 2 * * *'  # 每日 02:00 跑全量(含 e2e)
  workflow_dispatch:       # 手动触发全量

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
      - name: Cache data
        uses: actions/cache@v4
        with:
          path: data/
          key: data-${{ hashFiles('data/_meta/**') }}
      - name: Run unit tests
        run: pytest tests/unit -v --tb=short
      - name: Run integration tests
        run: pytest tests/integration -v --tb=short
        env:
          MOCK_NETWORK: "true"
      - name: Run e2e tests (manual/scheduled only)
        if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
        run: pytest tests/e2e -v --tb=short
      - name: Upload coverage
        if: github.event_name == 'workflow_dispatch'
        uses: codecov/codecov-action@v4
```

### CI 触发矩阵

| 触发条件 | 跑哪些测试 | 期望耗时 |
|---------|----------|---------|
| PR 提交 | unit + integration | < 30s |
| main 推送 | unit + integration | < 30s |
| 定时任务(每日 02:00) | unit + integration + e2e | < 5min |
| 手动触发 | 全量 + 覆盖率报告 | < 5min |

---

## 12. 文档同步更新

| 文档 | 更新内容 |
|------|---------|
| **README.md** | 加入"组合工作流 C"章节(单股/单基/组合 3 个并列),加入 4 个新 agent 介绍,加入测试运行指南 |
| **docs/architecture.md** | 【新增】三层层架构图 + 数据流图 |
| **docs/role-prompts.md** | 【新增】26 份角色模板使用指南 |
| **docs/contributing.md** | 【新增】如何新增 agent / 新增工作流 / 新增测试 |
| **docs/testing.md** | 【新增】测试运行指南 + Mock 策略 |
| **docs/superpowers/specs/2026-06-27-stock-analysis-refactor-design.md** | 本文档 |

---

## 13. 实施阶段(供 writing-plans 参考)

### 阶段 1:基础补全(优先)
- 4 个新 agent 文件(input-router/data-quality-auditor/portfolio-analyst/html-renderer)
- 26 份角色预设 prompt 模板
- 单元测试(8 个)
- 集成测试(4 个)

### 阶段 2:HTML 模板 + CLI 扩展
- 3 套 HTML 报告模板 + 7 个 partials
- data_tools 扩展(detect.py + portfolio.py)
- portfolio 5 个 CLI 子命令

### 阶段 3:端到端用例 + CI
- 3 个端到端用例
- E2E fixture
- GitHub Actions CI

### 阶段 4:文档同步
- README.md 更新
- docs/ 目录补全
- 注释与 docstring

### 阶段 5:回归验证
- 在历史持仓上重跑,确保产出正确
- 性能 baseline 对比

---

## 14. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 重构破坏现有功能 | 单元/集成测试覆盖原有 CLI 命令 + 端到端覆盖原有工作流 |
| LLM 调度不可靠 | E2E 用例用 mock,验证调度逻辑而非 LLM 输出 |
| Token 消耗过大 | 组合 > 10 只时做代表性筛选 |
| 数据源变更 | data_tools 内部封装,上层不感知 |
| CI 网络限制 | Mock fixture + 缓存 data/ |

---

## 15. 验收标准

- ✅ 5 种场景(单股/单基/纯股组合/纯基组合/混合组合)全部能跑通
- ✅ 原有 22 个 agent 文件全部保留
- ✅ data_tools 现有命令全部保留
- ✅ 8 单元 + 4 集成 + 5 e2e 测试全部通过
- ✅ GitHub Actions CI 绿
- ✅ README + docs 同步更新
- ✅ 报告命名规范统一
- ✅ HTML 报告风格统一

---

## 附录 A:P2 Backlog(性能优化策略,本次不做)

> 状态:**待性能数据触发**。本次按原设计跑通 5 种场景,收集真实 token / 时间 baseline 后,再决定启用哪些策略。

| # | 策略 | 预估节省 | 触发条件 | 优先级 |
|---|------|---------|---------|-------|
| P2-1 | **上下文裁剪**:subagent 只返 2k 摘要 + 写盘完整 markdown | token -30~50% | 9 基金组合实际 > 800k tokens | 高 |
| P2-2 | **角色精简**:组合场景从 7 角色 → 4 核心角色 | token -43%,时间 -40% | 9 基金组合 Step 1 > 6 分钟 | 高 |
| P2-3 | **Step 1 全并发**:3+3+3 串行 → 9 并发 | 时间 -50% | API/模型支持同时 9 路 subagent | 中 |
| P2-4 | **Step 6 风险评估降级**:3 → 1(neutral) | token -16k,时间 -1min | 组合场景风险评估明显冗余 | 中 |
| P2-5 | **共享数据层**:宏观/政策单次生成,不再每个 subagent 重复 | token -10% | news/policy 角色大量重复内容 | 低 |
| P2-6 | **代表性筛选**:> 10 只时按金额 Top N=8 | token -12~30% | 用户持仓 > 10 只时 | 低 |
| P2-7 | **报告缓存**:同名基金 24h 内复用 | 跨调用有效 | 同一基金被重复分析 | 低 |

**启用原则**:任意一条触发条件成立且节省 > 20% 时,在 writing-plans skill 的实施计划里加 Phase 6(性能优化)。

---

**文档结束。等待用户审查后调用 writing-plans skill。**
