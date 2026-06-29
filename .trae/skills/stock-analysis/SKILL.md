---
name: stock-analysis
description: Use when user provides any of the following for A股 / 公募基金 analysis - (1) A股 stock code (6 digits like 000001/600519/688981), (2) A股 stock name (公司名称 like 平安银行/贵州茅台), (3) fund code (6 digits like 001717/510300), (4) fund name (基金名称 like 工银前沿医疗/华泰柏瑞中证红利低波), (5) portfolio/holdings list (我的持仓/持仓分析/全部持有/诊断组合 + screenshot of brokerage or fund app showing multiple positions), (6) any Chinese request to analyze/diagnose/review A股 or fund (分析/诊断/复盘/评估/推荐). Triggers on ANY of these inputs even if only a screenshot or "分析持仓" without specific items. MUST dispatch 7 specialist subagents in parallel via Task tool, run bull/bear debate, then research-manager/trader/risk/portfolio-manager subagents, and generate HTML report. Main session NEVER writes analysis reports - all reports come from subagents.
---

# A股与基金多智能体分析系统

## ⚡ 触发条件(必读 - 满足任意一条即触发)

| # | 输入类型 | 示例 |
|---|----------|------|
| 1 | A股股票代码(6位数字) | `000001`、`600519`、`688981` |
| 2 | A股股票名称 | `平安银行`、`贵州茅台`、`宁德时代` |
| 3 | 基金代码(6位数字) | `001717`、`510300`、`161725` |
| 4 | 基金名称 | `工银前沿医疗`、`华泰柏瑞中证红利低波ETF联接A` |
| 5 | **持仓/组合**(关键词: 持仓/组合/全部持有/我的基金/诊断组合 + 截图/列表) | `帮我分析持仓`、`看看我的基金`、`[持仓截图]`、`[基金列表]` |
| 6 | 分析/诊断类请求 | `分析`、`诊断`、`复盘`、`评估`、`推荐`、`能不能买` |

**重要**: 即使输入模糊(如只发一张截图,或说"分析持仓"没有具体标的),也必须触发本 skill 并按"组合工作流"执行。

---

## 🛑 铁律(违反任意一条 = 失败)

**Violating the letter of the rules is violating the spirit of the rules.**

### 铁律 1:必须用 Task 工具调度 subagent
- 所有分析师(技术/舆情/新闻/基本面/政策/资金/解禁 / 基金7大分析师)、辩论方(多头/空头)、研究经理、交易员、风控(激进/保守/中立)、组合经理 — **全部必须通过 `Task` 工具以 `subagent_type: "general_purpose_task"` 调用**。
- 每个 subagent 在其内部提示词中明确告知它扮演的角色,并提供 agent 定义文件路径 `agents/<name>.agent.md` 让其读取后按角色执行。

### 铁律 2:主对话绝不写分析报告
- 主对话(你自己)只负责:
  1. 接收用户输入
  2. 识别输入类型并选择工作流
  3. 用 Task 工具调度 subagent(把数据上下文传给 subagent)
  4. 收集 subagent 输出
  5. 将 subagent 输出传给下一个 subagent
  6. 最后用 HTML 模板把组合经理的最终报告渲染成 HTML 文件
- **禁止**: 主对话直接拉数据并写"分析报告"或"最终结论"。即使你认为"简单"也要走完整 subagent 流程。

### 铁律 3:Step 8 必须生成 HTML 报告
- 组合经理 subagent 输出最终报告后,主对话必须立即用 HTML 模板渲染并保存到 `reports/<日期>/` 目录。
- 文件命名:
  - 单股票: `<股票代码>_<股票简称>.html`(如 `000001_平安银行.html`)
  - 单基金: `<基金代码>_<基金简称>.html`(如 `001717_工银前沿医疗股票A.html`)
  - 组合: `portfolio_<日期>.html`(如 `portfolio_2026-06-27.html`)
- 路径不可变,不可跳过。

### 铁律 4:7 分析师必须并行
- Step 1 的 7 个分析师 subagent 必须**在同一消息中通过多次 Task 工具调用并行触发**,不可串行。
- 等待所有 7 份报告返回后,再进入 Step 5。

### 铁律 5:辩论至少 1 轮
- Step 7 至少进行 1 轮多空辩论。复杂标的可做 2-3 轮。
- 风控辩论(Step 6)同样至少 1 轮。

### 铁律 6:智能增量拉取
- 主对话在调度分析师之前，检查本地已有数据文件是否满足时效性要求
- 如数据不足或过期，主对话通过 `run_command` 增量拉取缺失数据
- 数据时效性规则：
  - K线/净值: 近2年/1年内
  - 新闻: 近3个月内
  - global_news/hot_stocks/northbound: 24小时内
  - 基本面/基金信息: 7天内
- 分析师直接读取本地已有文件，如发现数据缺失可自行补充拉取（回退机制）

### 铁律 7:Prompt精简规范
- Subagent调用prompt只传必要参数，不重复角色定义
- 调用模板：
  ```
  角色: <agent-name>
  标的: <code>（<name>）
  数据目录: data/funds/<code>/
  输出路径: reports/<日期>/fund/<code>_<role>.md

  请:
  1. 读取 agents/<agent-name>.agent.md 获取角色定义和输出格式
  2. 读取数据目录下的相关数据
  3. 完成分析/研判并写入输出路径
  4. 返回契约格式(summary/detail_path/evidence)
  ```

### 铁律 8:Step 10 增强版必须按类分批并行
- 组合工作流 Step 10(增强版)的 7 分析师 + 辩论 subagent 必须**按 underweight 类别分批**、**同类内同消息并行**触发,不可串行、不可跨类合并。
- 调度规则:
  - 单类 underweight: 1 批(35 个 7 分析师 + 2 个辩论 = 37 Task 同一消息内并行)
  - 多类 underweight: 每类 1 批,批间串行(主对话等待)
- 7 分析师 subagent 的报告路径必须使用 `reports/<日期>/fund/candidate/<code>_<role>.md` 模板,不可混用单基金工作流的 `<code>_<role>.md` 路径(避免污染)。
- 质量分必须用 `data_tools.portfolio_rebalance.parse_quality_from_reports()` 规则化生成,禁止 subagent 主观打分。

---

## 📥 输入识别与路由(执行前第一步)

按以下优先级判定输入类型并选择工作流:

### 判定优先级

1. **关键词探测**(最高优先级)
   - 输入包含**持仓/组合关键词**(持仓/组合/全部持有/我的基金/诊断组合/portfolio/positions/截图) → **组合工作流 (C)**
   - 输入包含**基金关键词**(基金/ETF/LOF/联接/申购/赎回/净值/份额/A类/C类/混合/股票型/债券型/指数型/QDII/场内/场外/定投) → **单基金工作流 (B)**
   - 输入包含**股票关键词**(股票/A股/行情/走势/买入/卖出/能买吗/涨停) → **单股票工作流 (A)**

2. **代码探测**(输入为 6 位数字且无关键词时)
   - 执行 `python -m data_tools.cli fund detect <代码>`
   - 返回 `FUND|<基金名称>` → **单基金工作流 (B)**
   - 返回 `STOCK` → **单股票工作流 (A)**

3. **名称探测**(输入为中文名称且无关键词时)
   - 默认走**单股票工作流 (A)**(如"分析平安银行"、"贵州茅台")
   - 例外: 若名称中含"基金/ETF/联接"则走**单基金工作流 (B)**

### 路由示例

| 用户输入 | 判定依据 | 工作流 |
|----------|----------|--------|
| `001717` | 代码探测 → FUND | B 单基金 |
| `510300` | 代码探测 → FUND | B 单基金 |
| `000001` | 代码探测 → STOCK | A 单股票 |
| `688981` | 代码探测 → STOCK | A 单股票 |
| `工银前沿医疗基金` | 关键词"基金" | B 单基金 |
| `平安银行` | 名称探测 | A 单股票 |
| `帮我分析持仓` | 关键词"持仓" | **C 组合** |
| `[持仓截图 9 只基金]` | 关键词 + 截图 | **C 组合** |
| `诊断我的基金组合` | 关键词"组合"+"基金" | **C 组合** |
| `分析000001这只股票` | 关键词"股票" | A 单股票 |
| `001717基金净值` | 关键词"基金"+"净值" | B 单基金 |

---

## 🔀 三套工作流(选择对应文件)

### A. 单股票工作流
→ 见 [`workflow-stock.md`](workflow-stock.md)
- 适用: 1 只 A 股
- 流程: 7 股票分析师并行 → 多空辩论 → 研究经理 → 交易员 → 风控辩论 → 组合经理 → HTML

### B. 单基金工作流
→ 见 [`workflow-fund.md`](workflow-fund.md)
- 适用: 1 只公募基金(场内 ETF/场外联接/LOF/主动管理)
- 流程: 7 基金分析师并行 → 多空辩论 → 研究经理 → 交易员 → 风控辩论 → 组合经理 → HTML

### C. 组合/持仓工作流(**核心修复点 - 通用版**)
→ 见 [`workflow-portfolio.md`](workflow-portfolio.md)
- 适用: 多只基金/股票构成的持仓,或截图形式的持仓页面
- **支持三种组合类型**(Step 1.4 自动判定):
  - **C-1 全基金组合**: 持仓全部是公募基金 → 走 Step 4.1(7 基金分析师 subagent)
  - **C-2 全股票组合**: 持仓全部是 A 股股票 → 走 Step 4.2(7 股票分析师 subagent)
  - **C-3 混合组合**: 持仓同时包含基金和股票 → 同时走 Step 4.1 + 4.2,分两批调度
- 流程:
  1. **Step 1**: 识别所有标的 + 用 `fund detect` 探测每只类型,分流为 {funds, stocks} → C-1/C-2/C-3
  2. **Step 2** ⭐ C-1/C-3 增强: 主对话直接采集用户风险等级/期限/偏好(本地规则解析 + AskUserQuestion 反问),落盘 `prefs.json`
  3. **Step 3**: 主对话智能增量拉取数据
  4. **Step 4**: 按类型分批调度对应的 7 大分析师 subagent(并行)
  5. **Step 5**: 调度 1 个组合分析师 subagent 做组合层面诊断(**根据 C-1/C-2/C-3 自适应不同维度**:C-1 查清盘风险 / C-2 查行业估值 / C-3 查股债平衡 + 重复持仓)
  6. **Step 6** ⭐ C-1/C-3 增强: 主对话内联算 **当前 vs 目标 gap**,产出 `portfolio_gap.md`
  7. Step 7-12: 辩论 + 研究经理 + 交易员 + 风控 + 组合经理
  8. **Step 10** ⭐ C-1/C-3 增强: `fund-recommender` subagent 从**国内场外公募基金全量库**(`_meta/fund_list.json`)自动筛选补/换候选
  9. Step 13: 输出 `portfolio_<日期>.html` 报告(含偏好/gap/推荐补换/调整后配置模块)

---

## 📊 数据获取规范
→ 见 [`data-periods.md`](data-periods.md)

股票 / 基金 / 组合三套数据获取周期与命令清单。所有 subagent 必须严格按此规范拉取数据。

---

## 🤖 Agent 阵容
→ 见 [`agents-roster.md`](agents-roster.md)

7 大股票分析师 + 7 大基金分析师 + 8 大辩论/决策角色。每个角色的职责、立场、输出格式。

---

## 🛠️ CLI 工具命令
→ 见 [`cli-commands.md`](cli-commands.md)

`data_tools.cli` 的所有子命令(行情/财报/新闻/资金/基金净值/份额等),含参数说明。

---

## ⚠️ 注意事项

1. **数据真实性**: 所有分析基于公开可获取的信息。如果某些数据无法获取,标注 `[数据缺失: xxx]` 并继续,不要编造数据。
2. **路由准确性**: 务必先执行路由分发,股票和基金/组合的分析框架不同,走错工作流会导致分析失真。
3. **A 股特殊性**: T+1、涨跌停、政策市、散户占比高、申赎 T+1(场外基金 T+1 到账)、7 日内赎回 1.5% 惩罚费。
4. **基金特殊性**: 申赎压力、规模魔咒、反弹即赎回、清盘风险(连续 60 日规模 < 5000 万)、持有期锁定。
5. **免责声明**: 每个 HTML 报告必须包含"本报告仅供研究参考,不构成投资建议"。
6. **效率优先**: 单标的流程 7 分析师并行 + 辩论 1-2 轮;组合流程每只基金独立跑完整流程,组合层面再做整合分析。
7. **HTML 报告必做**: 每次分析完成后,**必须**生成 HTML 报告并保存,不可跳过。

---

## 🚀 快速开始(伪代码)

```
1. 接收用户输入
2. 路由分发 → A / B / C
3. (若 C) 识别所有标的(代码+名称),列出 subagent 任务清单
4. 调用 Task 工具并行/分批调度 subagent
   - subagent 内部: read_file(agents/<name>.agent.md) → run_command(拉数据) → 输出报告
5. 主对话收集 subagent 输出,传给下一阶段
6. 最终组合经理 subagent 输出报告 → 主对话渲染 HTML → 保存
7. 向用户报告 HTML 路径 + 简要总结
```

**主对话绝不写分析报告。所有报告必须由 subagent 生成。**

### 7. 所有 subagent 必须遵循 subagent-contract.md

详见 `.trae/skills/stock-analysis/subagent-contract.md`:
- summary 限 2k tokens
- detail_path 必须真实写盘
- evidence 至少 3 个数据点

违反契约的 subagent 输出视为无效,必须重跑。

### 8. Step 0 必须先调 input_router

任何分析流程的第一步都必须是 input_router,识别输入类型(A/B/C-1/C-2/C-3)。不允许跳过路由直接分析。
