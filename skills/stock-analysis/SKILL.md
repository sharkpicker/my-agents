---
name: stock-analysis
description: Use when user asks to analyze a stock (A股), mentions stock codes like 000001, 600519, or requests stock research, investment analysis, or market outlook for specific Chinese stocks. Trigger immediately when stock codes or stock analysis requests appear.
---

# A 股多智能体分析系统

你是一个 A 股多智能体分析系统的协调者。当用户请求分析股票时，你需要调度 14 个专业智能体，按照标准流程完成全面的股票分析，并输出最终的投资分析报告。

## 触发条件

**当用户输入包含以下内容时，立即调用本 Skill：**

- 股票代码（6位数字，如 000001、600519、300750、688981 等）
- "分析股票"、"股票分析"、"研究一下"、"帮我看看"
- "投资建议"、"买入还是卖出"、"能买吗"
- 股票名称（如 "平安银行"、"贵州茅台" 等）
- "A股"、"行情"、"走势" 等关键词 + 具体标的

**同时分析多只股票时**，对每只股票分别执行完整分析流程，最后汇总对比。

---

## 数据工具系统

项目提供了完整的 Python 数据获取工具，供各智能体通过 `run_command` 调用。数据自动保存到 `data/` 目录下，按股票代码组织子目录。

### 数据源

| 数据源 | 接口类型 | 覆盖内容 |
|--------|----------|----------|
| mootdx (通达信) | TCP | K线、财务快照、F10股东研究 |
| 腾讯财经 | HTTP | 实时报价、PE/PB/市值、换手率 |
| 东方财富 | HTTP | 龙虎榜、限售解禁、个股搜索、7x24资讯 |
| 新浪财经 | HTTP | K线备用、三大财报（资产负债表/利润表/现金流量表） |
| 同花顺 | HTTP | 一致预期EPS、涨停热门股、北向资金 |
| 财联社 | HTTP | 全球财经快讯 |
| 百度股市通 | HTTP | 概念板块、行业分类 |

### 数据目录结构

```
data/
├── 000001/                          # 按股票代码分子目录
│   ├── kline_2025-01-01_2025-06-01.csv    # K线数据
│   ├── fundamentals_20250601.txt          # 基本面数据
│   ├── indicator_rsi_2025-06-01.txt       # 技术指标
│   ├── indicator_macd_2025-06-01.txt
│   ├── news_2025-04-01_2025-06-01.md      # 新闻数据
│   ├── balance_sheet_quarterly.csv        # 资产负债表
│   ├── income_statement_quarterly.csv     # 利润表
│   ├── cashflow_quarterly.csv             # 现金流量表
│   ├── dragon_tiger_20250601.md           # 龙虎榜
│   ├── lockup_20250601.md                 # 限售解禁
│   ├── concept_blocks_20250601.md         # 概念板块
│   ├── insider_transactions_20250601.txt  # 股东研究
│   └── profit_forecast_20250601.md        # 盈利预测
├── global_news_2025-06-01.md              # 全球财经新闻
├── northbound_2025-06-01.md               # 北向资金
└── hot_stocks_2025-06-01.md               # 热门股
```

### CLI 工具命令清单

所有命令均在项目根目录 `d:\01_coding\my_agents` 下执行：

```bash
# --- 行情与技术指标 ---
python -m data_tools.cli kline <股票代码> --start <开始日期> --end <结束日期>
python -m data_tools.cli indicator <股票代码> <指标名> --date <日期> --days <回看天数>

# --- 基本面与财报 ---
python -m data_tools.cli fundamentals <股票代码>
python -m data_tools.cli balance-sheet <股票代码> --freq quarterly
python -m data_tools.cli income-statement <股票代码> --freq quarterly
python -m data_tools.cli cashflow <股票代码> --freq quarterly
python -m data_tools.cli forecast <股票代码>

# --- 新闻与资讯 ---
python -m data_tools.cli news <股票代码> --start <开始日期> --end <结束日期>
python -m data_tools.cli global-news --limit 20

# --- 资金与龙虎榜 ---
python -m data_tools.cli dragon-tiger <股票代码> --days 5
python -m data_tools.cli northbound
python -m data_tools.cli hot-stocks
python -m data_tools.cli concept <股票代码>

# --- 股东与解禁 ---
python -m data_tools.cli lockup <股票代码>
python -m data_tools.cli insider <股票代码>

# --- 工具 ---
python -m data_tools.cli data-dir
```

**支持的技术指标：** `rsi`, `macd`, `macds`, `macdh`, `close_50_sma`, `close_200_sma`, `close_10_ema`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`, `mfi`

### 依赖安装

首次使用前需安装依赖：

```bash
pip install -r requirements.txt
```

依赖包：`mootdx`, `pandas`, `requests`, `stockstats`, `python-dateutil`

### 数据获取周期规范（固化标准）

**重要：以下数据获取周期已固化到各智能体定义中，所有分析师必须严格按照此规范执行数据采集。**

| 数据类型 | 获取周期 | 说明 | 示例命令 |
|----------|----------|------|----------|
| **K线数据** | **近 2 年** | 用于技术分析、趋势判断、周期识别（约 480 个交易日） | `kline 000001 --start 2024-06-24 --end 2026-06-24` |
| **技术指标** | **近 120 天** | 用于 RSI、MACD、布林带等指标计算 | `indicator 000001 rsi --date 2026-06-24 --days 120` |
| **个股新闻** | **近 3 个月** | 用于事件驱动、舆情分析 | `news 000001 --start 2026-03-24 --end 2026-06-24` |
| **财报数据** | **近 2 年季度** | 用于财务趋势分析（8 个季度） | `income-statement 000001 --freq quarterly` |
| **龙虎榜** | **近 6 个月** | 用于游资动向分析 | `dragon-tiger 000001 --days 180` |
| **限售解禁** | **近 6 个月** | 用于解禁压力评估 | `lockup 000001` |
| **股东研究** | **近 6 个月** | 用于大股东增减持分析 | `insider 000001` |
| **基本面数据** | **当前快照** | 用于估值、市值等实时指标 | `fundamentals 000001` |
| **北向资金** | **当前快照** | 用于外资动向分析 | `northbound` |
| **热门股** | **当前快照** | 用于市场热点判断 | `hot-stocks` |
| **概念板块** | **当前快照** | 用于行业分类、板块联动 | `concept 000001` |
| **全球新闻** | **当前快照** | 用于宏观政策分析 | `global-news --limit 30` |

**日期计算规则：**
- 以当前日期为基准向前推算（基准日期：2026-06-24）
- K线开始日期：`当前日期 - 2年`
- 新闻开始日期：`当前日期 - 3个月`
- 指标回看天数：`120天`
- 龙虎榜/解禁/股东回看：`180天`

**数据获取流程：**
1. 首先计算当前日期和对应的起始日期
2. 按照上表的周期规范传入日期参数
3. 数据自动保存到 `data/<股票代码>/` 目录
4. 后续分析直接读取已保存的数据文件

---

## 智能体阵容

项目包含 14 个专业智能体，分工协作完成全流程分析：

### 第一梯队：7 大分析师（数据采集与分析）

| 智能体 | 文件 | 职责 |
|--------|------|------|
| 技术分析师 | `agents/market-analyst.agent.md` | K线、技术指标、量价关系、支撑阻力 |
| 舆情分析师 | `agents/sentiment-analyst.agent.md` | 市场情绪、舆情热度、散户态度 |
| 新闻分析师 | `agents/news-analyst.agent.md` | 行业新闻、公司公告、宏观事件 |
| 基本面分析师 | `agents/fundamentals-analyst.agent.md` | 财务报表、盈利能力、估值水平 |
| 政策分析师 | `agents/policy-analyst.agent.md` | 监管政策、产业政策、窗口指导 |
| 游资追踪师 | `agents/hot-money-tracker.agent.md` | 龙虎榜、资金流向、板块轮动 |
| 解禁监控师 | `agents/lockup-watcher.agent.md` | 限售解禁、大股东减持、股权质押 |

### 第二梯队：辩论与决策

| 智能体 | 文件 | 职责 |
|--------|------|------|
| 多头研究员 | `agents/bull-researcher.agent.md` | 构建看涨论点，反驳看空观点 |
| 空头研究员 | `agents/bear-researcher.agent.md` | 构建看跌论点，反驳看多观点 |
| 研究经理 | `agents/research-manager.agent.md` | 裁判，综合评估，输出投资计划 |
| 交易员 | `agents/trader.agent.md` | 将投资计划转化为交易方案 |

### 第三梯队：风控与最终决策

| 智能体 | 文件 | 职责 |
|--------|------|------|
| 激进风控师 | `agents/aggressive-analyst.agent.md` | 支持交易，认为风险可控 |
| 保守风控师 | `agents/conservative-analyst.agent.md` | 反对/谨慎，强调风险 |
| 中立风控师 | `agents/neutral-analyst.agent.md` | 裁决，输出最终风控意见 |
| 组合经理 | `agents/portfolio-manager.agent.md` | 最终决策者，输出投资报告 |

---

## 分析流程

```
用户输入股票代码
    ↓
[Step 1] 7 大分析师并行调研
    技术面 / 舆情 / 新闻 / 基本面 / 政策 / 资金面 / 解禁
    ↓
[Step 2] 质量门控与数据源评估
    评估各数据源可用性（OK/不OK/部分）
    分析数据缺失对结论的影响（大/中/小）
    检查 7 份报告是否满足「必采清单」要求
    不满足 → 补充采集
    ↓
[Step 3] 多空辩论（1-N 轮）
    多头研究员 vs 空头研究员
    基于 7 份分析师报告展开辩论
    ↓
[Step 4] 研究经理裁决
    综合辩论结果 → 输出投资计划（Buy/Hold/Sell）
    ↓
[Step 5] 交易员制定方案
    将投资计划转化为具体交易方案（价位/仓位/止损）
    ↓
[Step 6] 风控辩论
    激进 vs 保守风控师辩论
    中立风控师最终裁决
    ↓
[Step 7] 组合经理最终决策
    综合所有信息 → 输出最终投资报告
    ↓
[Step 8] 生成 HTML 报告并保存
    按照标准 HTML 模板生成报告
    保存到 reports/<日期>/<股票代码>_<股票名称>.html
    向用户展示文件路径
```

---

## 执行步骤

### Step 1：7 大分析师并行调研

**并行调用以下 7 个智能体**，每个智能体独立完成一份分析报告。

向每个智能体传入：
- 股票代码（格式：6 位数字，如 `000001`）
- 股票名称（如果知道的话）
- 分析要求：按照各自的输出格式完成报告

**分析师获取数据的方式：**
- 每个分析师智能体通过 `run_command` 调用 `python -m data_tools.cli <命令>` 获取所需数据
- 数据自动保存到 `data/<股票代码>/` 目录下
- 分析师也可以通过 `read_file` 读取已保存的数据文件
- 如果某些数据无法获取，标注 `[数据缺失: xxx]` 并继续分析

**数据获取时间范围（重要）：**
- **K线数据**：获取 **近 2 年** 的日K数据（约 480 个交易日），用于技术分析、趋势判断、周期识别
  - 示例：`python -m data_tools.cli kline 300750 --start 2024-06-24 --end 2026-06-24`
- **技术指标**：回看天数设为 **120 天**（约半年），用于指标计算
  - 示例：`python -m data_tools.cli indicator 300750 rsi --date 2026-06-24 --days 120`
- **个股新闻**：获取 **近 3 个月** 的新闻，覆盖近期事件驱动
  - 示例：`python -m data_tools.cli news 300750 --start 2026-03-24 --end 2026-06-24`
- **财报数据**：获取 **近 2 年** 的季度财报（8 个季度），用于财务趋势分析
- **龙虎榜/解禁/股东**：获取 **近 6 个月** 的数据
- **北向资金/热门股/全球新闻**：获取当前快照数据

**日期计算规则：**
- 以当前日期为基准（today），向前推算相应时间范围
- 使用 PowerShell 计算：`(Get-Date).AddYears(-2).ToString("yyyy-MM-dd")` 等

**各分析师推荐获取的数据：**

| 分析师 | 推荐获取的数据工具 |
|--------|-------------------|
| 技术分析师 | `kline` (K线) + `indicator` (RSI/MACD/布林带等3+个指标) |
| 舆情分析师 | `news` (个股新闻) + `global-news` (市场新闻) + `hot-stocks` (热门股) |
| 新闻分析师 | `news` (个股新闻) + `global-news` (全球财经) + `concept` (概念板块) |
| 基本面分析师 | `fundamentals` (基本面) + `income-statement` (利润表) + `balance-sheet` (资产负债表) + `cashflow` (现金流) + `forecast` (一致预期) |
| 政策分析师 | `global-news` (政策新闻) + `news` (个股新闻) + `concept` (行业板块) |
| 游资追踪师 | `kline` (量价) + `dragon-tiger` (龙虎榜) + `northbound` (北向资金) + `hot-stocks` (热门股) + `concept` (板块) + `insider` (股东) |
| 解禁监控师 | `lockup` (解禁) + `insider` (股东) + `fundamentals` (股本) + `news` (减持新闻) |

**并行执行说明**：
- 7 位分析师的工作相互独立，可以并行调度
- 等待所有 7 份报告完成后再进入下一步
- 如果某份报告缺失关键数据，标记并在质量门控阶段补充

### Step 2：质量门控与数据源评估

#### 2.1 数据源可用性评估

在 7 大分析师完成数据采集后，首先对各数据源的可用性进行评估，形成**数据源评估表**。该评估表将贯穿后续所有环节，并最终呈现在 HTML 报告中。

**评估方法：**

逐项检查每个数据获取命令的返回结果，按以下标准分类：

| 状态 | 标识 | 说明 |
|------|------|------|
| 正常 | ✅ OK | 数据成功获取，内容完整可用 |
| 异常 | ❌ 不OK | 接口报错、返回空数据、数据严重缺失 |
| 部分可用 | ⚠️ 部分 | 接口返回了数据但部分字段缺失或不完整 |

**数据源评估表格式：**

| 数据源 | 对应工具命令 | 获取时间范围 | 状态 | 缺失内容 | 对分析结论的影响 |
|--------|-------------|-------------|------|----------|-----------------|
| mootdx (通达信) | `kline` | 近2年 (2024-06-24 ~ 2026-06-24) | ✅ OK / ❌ 不OK / ⚠️ 部分 | - | 无 / 大 / 中 / 小 |
| mootdx (通达信) | `indicator` | 近120天 | ... | ... | ... |
| 腾讯财经 | `fundamentals` | 当前快照 | ... | ... | ... |
| 新浪财经 | `income-statement` | 近2年季度 | ... | ... | ... |
| 新浪财经 | `balance-sheet` | 近2年季度 | ... | ... | ... |
| 新浪财经 | `cashflow` | 近2年季度 | ... | ... | ... |
| 东方财富 | `news` | 近3个月 | ... | ... | ... |
| 东方财富 | `dragon-tiger` | 近6个月 | ... | ... | ... |
| 东方财富 | `lockup` | 近6个月 | ... | ... | ... |
| 东方财富 | `global-news` | 当前快照 | ... | ... | ... |
| 同花顺 | `hot-stocks` | 当前快照 | ... | ... | ... |
| 同花顺 | `northbound` | 当前快照 | ... | ... | ... |
| 同花顺 | `forecast` | 当前快照 | ... | ... | ... |
| 百度股市通 | `concept` | 当前快照 | ... | ... | ... |
| mootdx F10 | `insider` | 近6个月 | ... | ... | ... |

**获取时间范围说明：**
- 每个数据源必须标注实际获取的数据时间范围（如"近2年"、"近3个月"、"当前快照"等）
- 如果数据源返回的数据时间范围与预期不符（如请求近2年但只返回了3个月），需在"缺失内容"列说明
- 时间范围信息将体现在 HTML 报告的数据源评估表中

**影响程度判定标准：**

| 影响程度 | 说明 | 示例 |
|----------|------|------|
| **大** | 缺失数据直接导致某维度分析无法进行，结论可信度显著下降 | 基本面数据全部缺失 → 无法评估估值合理性 |
| **中** | 缺失数据影响部分指标计算，但可通过其他数据源补充或推断 | 利润表缺失但有基本面快照 → 可用 PE/营收增速粗略替代 |
| **小** | 缺失数据为辅助参考，不影响核心结论 | 概念板块缺失 → 不影响基本面和技术面判断 |
| **无** | 数据正常获取，无影响 | - |

**评估结论要求：**

评估完成后，需输出一段**数据质量总体评价**，说明：
1. 本次分析的数据覆盖率（正常 / 总数）
2. 关键数据源（K线、基本面、资金面）是否可用
3. 数据缺失对最终结论可信度的整体影响等级（高 / 中 / 低）
4. 哪些结论需要标注"数据受限"提示

#### 2.2 报告质量检查

检查每份分析师报告是否满足其「必采清单」要求：

- 技术面报告：收盘价、涨跌幅、成交量、至少 3 个指标、支撑阻力位
- 情绪面报告：新闻数量、正负比例、前 3 主题、情绪评分、趋势
- 新闻报告：事件时间线、利好/利空分类、关键事件数量
- 基本面报告：PE/PB、营收增速、净利润增速、ROE、负债率
- 政策报告：政策事件清单、影响力度、总体评级
- 资金面报告：成交量变化、主力资金、北向资金、板块热度
- 解禁报告：股本结构、增减持记录、减持压力评级

**如果某份报告不满足要求**：
- 指示该智能体补充缺失的数据
- 最多补充 1 次，仍缺失则标注 `[数据缺失]` 继续
- 在数据源评估表中记录该缺失及其影响

### Step 3：多空辩论

将 7 份分析师报告同时提交给**多头研究员**和**空头研究员**，展开第一轮辩论。

**辩论流程：**
1. 第一轮：多头和空头各自基于 7 份报告提出完整论点
2. （可选）第二轮及之后：双方阅读对方论点后，进行反驳和补充
3. 默认 1-2 轮辩论，复杂标的可增加至 3 轮

向双方智能体传入：
- 所有 7 份分析师报告全文
- 对方的上一轮论点（第 2 轮及以后）
- 辩论轮次

### Step 4：研究经理裁决

将完整的辩论历史和 7 份分析师报告提交给**研究经理**。

研究经理需要输出：
- 投资评级（Buy / Overweight / Hold / Underweight / Sell）
- 核心逻辑
- 多空评估
- 战略行动建议
- 风险提示

### Step 5：交易员制定方案

将研究经理的投资计划 + 7 份分析师报告提交给**交易员**。

交易员需要输出：
- 交易方向（买入/持有/卖出）
- 具体价位（入场、止损、目标）
- 仓位建议
- 操作策略
- 风险控制

### Step 6：风控辩论

将交易方案 + 研究计划 + 7 份分析师报告同时提交给**激进风控师**和**保守风控师**。

**风控辩论流程：**
1. 第一轮：激进派和保守派各自提出风控意见
2. （可选）第二轮：双方阅读对方意见后补充反驳
3. 默认 1 轮辩论

然后将双方意见提交给**中立风控师**裁决。

中立风控师需要输出：
- 风控审查结论（通过 / 有条件通过 / 不通过）
- 综合风险评估
- 风控参数调整建议
- 具体风控措施

### Step 7：组合经理最终决策

将所有材料（7 份分析师报告 + 辩论记录 + 投资计划 + 交易方案 + 风控报告 + 数据源评估表）提交给**组合经理**。

组合经理输出最终的**投资分析报告**，包含：
- 数据源评估（来自 Step 2 的数据源评估表 + 数据质量总体评价）
- 最终评级和建议仓位
- 核心观点
- 多维度分析摘要
- 投资逻辑
- 具体操作建议
- 关注要点
- 免责声明

**注意**：如果数据源评估显示关键数据缺失（影响程度为"大"），组合经理需在核心观点和最终评级中明确标注"数据受限"提示，并适当降低结论的确定性表述。

### Step 8：生成 HTML 报告并保存

**这是流程的最后一步，必须执行，不可跳过。**

组合经理完成最终投资报告后，立即按照下方的 HTML 模板规范，将报告内容生成为美观的 HTML 文件并保存。

#### 保存规则

报告与数据分离存放。数据保存在 `data/` 目录，报告保存在项目根目录下独立的 `reports/` 目录。

1. **报告根目录**：`reports/`（与 `data/` 同级，位于项目根目录下）
2. **目录结构**：按日期分组，每天一个子目录，文件名包含股票代码和股票名称
   ```
   reports/
   ├── 2025-06-24/                                    # 按日期分组
   │   ├── 600519_贵州茅台.html                        # 个股报告
   │   ├── 000001_平安银行.html                        # 个股报告
   │   └── comparison_000001_600519.html               # 多股对比报告
   ├── 2025-06-25/
   │   └── 300750_宁德时代.html
   └── ...
   ```
3. **文件命名规则**：
   - 个股报告：`<股票代码>_<股票名称>.html`
   - 对比报告：`comparison_<股票代码1>_<股票代码2>[_<股票代码N>].html`
4. **文件编码**：UTF-8
5. **保存方式**：使用 `write_file` 工具写入完整 HTML 内容
6. **保存后**：向用户展示文件的可点击路径链接，并简要说明报告已保存

#### HTML 模板规范

**重要：所有个股报告必须严格使用以下统一模板，确保多只股票报告的格式和样式完全一致。**

生成的 HTML 报告必须包含以下结构，使用内联 CSS（不依赖外部资源），确保浏览器直接打开即可美观显示：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>[股票名称]（[股票代码]）投资分析报告</title>
<style>
  /* === 基础样式 === */
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #f5f7fa; color: #333; line-height: 1.8; padding: 20px;
  }
  .container {
    max-width: 960px; margin: 0 auto; background: #fff;
    border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); overflow: hidden;
  }

  /* === 头部 === */
  .header {
    background: linear-gradient(135deg, #1a237e 0%, #283593 50%, #3949ab 100%);
    color: #fff; padding: 40px 36px;
  }
  .header h1 { font-size: 28px; margin-bottom: 8px; }
  .header .meta { font-size: 14px; opacity: 0.85; }
  .header-sub { margin-top: 16px; display: flex; gap: 24px; flex-wrap: wrap; }
  .header-tag {
    background: rgba(255,255,255,0.2); padding: 6px 14px;
    border-radius: 20px; font-size: 13px;
  }
  .price-box { display: flex; align-items: baseline; gap: 16px; margin-top: 12px; }
  .price-box .price { font-size: 42px; font-weight: 700; }
  .price-box .change.up { color: #ff6b6b; }
  .price-box .change.down { color: #51cf66; }
  .price-box .change { font-size: 18px; font-weight: 600; }

  /* === 内容区 === */
  .content { padding: 32px 36px; }
  h2 {
    font-size: 20px; color: #1a237e; border-left: 4px solid #3949ab;
    padding-left: 12px; margin: 28px 0 16px 0;
  }
  h3 { font-size: 16px; color: #283593; margin: 20px 0 10px 0; }
  h4 { font-size: 15px; color: #3949ab; margin: 14px 0 8px 0; }

  /* === 表格 === */
  table { width: 100%; border-collapse: collapse; margin: 12px 0 20px 0; font-size: 14px; }
  th {
    background: #e8eaf6; color: #283593; padding: 10px 14px;
    text-align: left; font-weight: 600; border: 1px solid #c5cae9;
  }
  td { padding: 10px 14px; border: 1px solid #e0e0e0; vertical-align: top; }
  tr:nth-child(even) td { background: #fafafa; }

  /* === 评级卡片 === */
  .rating-card {
    background: linear-gradient(135deg, #e8eaf6, #c5cae9);
    border-radius: 10px; padding: 20px 24px; margin: 16px 0;
  }
  .rating-card .label { font-size: 14px; color: #283593; margin-bottom: 6px; }
  .rating-card .value { font-size: 28px; font-weight: 700; color: #1a237e; }
  .final-rating {
    display: inline-block; padding: 4px 14px; border-radius: 6px;
    font-weight: 700; font-size: 15px; margin: 4px 0;
  }
  .final-rating.buy { background: #ff6b6b; color: #fff; }
  .final-rating.cautious { background: #ffd43b; color: #1a237e; }
  .final-rating.neutral { background: #adb5bd; color: #fff; }
  .final-rating.sell { background: #51cf66; color: #fff; }

  /* === 多维度评分网格 === */
  .rating-grid {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 16px; margin: 16px 0;
  }
  .rating-item {
    background: #f5f5f5; border-radius: 8px; padding: 14px 16px; text-align: center;
  }
  .rating-item .dim { font-size: 13px; color: #666; margin-bottom: 4px; }
  .rating-item .val { font-size: 16px; font-weight: 600; }
  .val.good { color: #51cf66; }
  .val.bad { color: #ff6b6b; }
  .val.mid { color: #f59f00; }
  .val.neutral { color: #868e96; }

  /* === 结论区 === */
  .conclusion {
    background: linear-gradient(135deg, #1a237e, #283593);
    color: #fff; border-radius: 10px; padding: 24px 28px; margin: 24px 0;
  }
  .conclusion h3 { color: #ffd700; margin-bottom: 12px; font-size: 18px; }

  /* === 智能体分析卡片 === */
  .agent-section { margin: 20px 0; }
  .agent-card {
    background: #f9fafb; border-radius: 8px; padding: 18px 22px;
    margin: 12px 0; border-left: 4px solid #3949ab;
  }
  .agent-card.bull { border-left-color: #51cf66; background: #f0fff4; }
  .agent-card.bear { border-left-color: #ff6b6b; background: #fff5f5; }
  .agent-card.manager { border-left-color: #ffd700; background: #fffbe6; }
  .agent-card.risk-aggressive { border-left-color: #ff922b; background: #fff4e6; }
  .agent-card.risk-conservative { border-left-color: #4dabf7; background: #e7f5ff; }
  .agent-card.risk-neutral { border-left-color: #9775fa; background: #f3f0ff; }
  .agent-card-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 10px; flex-wrap: wrap; gap: 8px;
  }
  .agent-name { font-size: 16px; font-weight: 700; color: #1a237e; }
  .agent-role { font-size: 12px; color: #666; background: #e8eaf6; padding: 2px 10px; border-radius: 12px; }
  .agent-rating {
    font-size: 13px; font-weight: 600; padding: 3px 10px;
    border-radius: 4px; color: #fff;
  }
  .agent-rating.good { background: #51cf66; }
  .agent-rating.bad { background: #ff6b6b; }
  .agent-rating.mid { background: #f59f00; }
  .agent-rating.neutral { background: #868e96; }
  .agent-content { font-size: 14px; color: #444; }
  .agent-content ul { margin: 6px 0 6px 20px; }
  .agent-content li { margin: 3px 0; }
  .agent-keypoint {
    background: #fff; border-radius: 6px; padding: 8px 12px;
    margin: 8px 0; font-size: 13px; border: 1px solid #e0e0e0;
  }

  /* === 多空辩论双栏 === */
  .debate-box {
    display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 16px 0;
  }
  .debate-col {
    border-radius: 8px; padding: 16px 18px;
  }
  .debate-col.bull { background: #f0fff4; border: 1px solid #b2f2bb; }
  .debate-col.bear { background: #fff5f5; border: 1px solid #ffc9c9; }
  .debate-col h4 { margin-bottom: 10px; }
  .debate-col.bull h4 { color: #2b8a3e; }
  .debate-col.bear h4 { color: #c92a2a; }

  /* === 其他组件 === */
  .section-card {
    background: #f9fafb; border-radius: 8px; padding: 18px 22px; margin: 12px 0;
  }
  .section-card h4 { color: #3949ab; margin-bottom: 8px; }
  ul, ol { padding-left: 24px; margin: 8px 0; }
  li { margin: 4px 0; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .agent-flow { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
  .agent-tag {
    background: #e3f2fd; color: #1565c0; padding: 4px 12px;
    border-radius: 16px; font-size: 12px;
  }

  /* === 数据源评估 === */
  .data-source-summary {
    display: flex; gap: 16px; margin: 12px 0; flex-wrap: wrap;
  }
  .ds-stat {
    background: #f5f5f5; border-radius: 8px; padding: 12px 18px; text-align: center; min-width: 100px;
  }
  .ds-stat .num { font-size: 24px; font-weight: 700; }
  .ds-stat .num.ok { color: #51cf66; }
  .ds-stat .num.fail { color: #ff6b6b; }
  .ds-stat .num.partial { color: #f59f00; }
  .ds-stat .label { font-size: 12px; color: #666; margin-top: 2px; }
  .ds-impact-badge {
    display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;
  }
  .ds-impact-badge.high { background: #ffe0e0; color: #c92a2a; }
  .ds-impact-badge.mid { background: #fff3cd; color: #856404; }
  .ds-impact-badge.low { background: #d3f9d8; color: #2b8a3e; }
  .ds-impact-badge.none { background: #e7f5ff; color: #1971c2; }
  .data-limited-warning {
    background: #fff3cd; border: 1px solid #ffec99; border-radius: 8px;
    padding: 12px 16px; margin: 12px 0; font-size: 14px; color: #856404;
  }

  /* === 免责声明 === */
  .disclaimer {
    margin-top: 24px; padding: 16px 20px; background: #fff3cd;
    border: 1px solid #ffec99; border-radius: 8px; font-size: 13px; color: #856404;
  }
  @media (max-width: 768px) {
    .rating-grid { grid-template-columns: repeat(2, 1fr); }
    .two-col { grid-template-columns: 1fr; }
    .debate-box { grid-template-columns: 1fr; }
    .content { padding: 20px 16px; }
    .header { padding: 24px 20px; }
  }
</style>
</head>
<body>
<div class="container">
  <!-- 头部：股票名称、代码、价格、涨跌幅、标签 -->
  <div class="header">...</div>
  <div class="content">

    <!-- ============ 第一部分：总览 ============ -->

    <!-- 1. 最终评级卡片（数据受限时显示警告提示） -->
    <!-- 2. 数据源评估：统计卡片(OK/不OK/部分) + 评估表格(含获取时间范围列) + 数据质量总体评价 + 数据受限警告(如有) -->
    <!-- 3. 多维度评分网格（6个维度：政策/基本面/资金/技术/情绪/风险） -->

    <!-- ============ 第二部分：7大分析师分析详情 ============ -->

    <!-- 4. 技术分析师报告卡片（agent-card）：
         含分析结论、关键指标表格、支撑阻力位、技术评级 -->
    <!-- 5. 舆情分析师报告卡片（agent-card）：
         含新闻数量、正负比例、情绪评分、舆情趋势、情绪评级 -->
    <!-- 6. 新闻分析师报告卡片（agent-card）：
         含事件时间线、利好/利空分类、关键事件、新闻评级 -->
    <!-- 7. 基本面分析师报告卡片（agent-card）：
         含PE/PB/营收增速/净利润增速/ROE/负债率、估值卡片、基本面评级 -->
    <!-- 8. 政策分析师报告卡片（agent-card）：
         含政策事件清单、影响力度、政策评级 -->
    <!-- 9. 游资追踪师报告卡片（agent-card）：
         含成交量变化、主力资金、北向资金、板块热度、资金评级 -->
    <!-- 10. 解禁监控师报告卡片（agent-card）：
         含股本结构、增减持记录、减持压力评级 -->

    <!-- ============ 第三部分：辩论与决策 ============ -->

    <!-- 11. 多空辩论（debate-box 双栏对比）：
         左栏绿色多头研究员论点（3-5条核心论据）
         右栏红色空头研究员论点（3-5条核心论据） -->
    <!-- 12. 研究经理裁决卡片（agent-card manager）：
         含投资评级、核心逻辑、多空评估、战略建议 -->
    <!-- 13. 交易员方案卡片（agent-card）：
         含交易方向、入场价、止损价、目标价、仓位、操作策略表格 -->
    <!-- 14. 风控辩论：
         激进风控师卡片（risk-aggressive）+ 保守风控师卡片（risk-conservative）
         中立风控师裁决卡片（risk-neutral）：含风控结论、风险等级、风控参数 -->

    <!-- ============ 第四部分：最终决策 ============ -->

    <!-- 15. 组合经理最终决策（conclusion 深色背景卡片）：
         含最终评级、建议仓位、核心观点、投资逻辑、操作建议 -->
    <!-- 16. 核心数据表格：PE/PB/市值/换手率等关键指标 -->
    <!-- 17. 参与分析的智能体标签列表（14个 agent-tag） -->
    <!-- 18. 关注要点：需跟踪的指标和事件列表 -->
    <!-- 19. 免责声明 -->

  </div>
</div>
</body>
</html>
```

**智能体分析卡片使用说明：**

每个智能体的分析结果使用 `agent-card` 组件展示，必须包含：
1. **卡片头部**（agent-card-header）：智能体名称 + 角色标签 + 评级标签
2. **分析内容**（agent-content）：该智能体的核心分析结论，使用列表展示关键点
3. **关键数据**（agent-keypoint）：该智能体引用的关键数据或指标

示例：
```html
<div class="agent-card">
  <div class="agent-card-header">
    <div>
      <span class="agent-name">技术分析师</span>
      <span class="agent-role">市场技术面</span>
    </div>
    <span class="agent-rating mid">震荡偏多</span>
  </div>
  <div class="agent-content">
    <ul>
      <li>MACD 底背离，下跌动能减弱</li>
      <li>RSI 45，中性偏弱</li>
      <li>成交量放量反弹</li>
    </ul>
    <div class="agent-keypoint">
      <strong>关键价位：</strong>支撑 230 元 / 阻力 270 元
    </div>
  </div>
</div>
```

#### HTML 报告必含章节

生成的 HTML 报告必须包含以下章节（按顺序），**所有个股报告必须严格遵循此结构，确保格式统一**：

| 序号 | 章节 | 内容来源 | 必含元素 |
|------|------|----------|----------|
| 1 | 头部 | 基本面数据 | 股票名称、代码、最新价、涨跌幅、行业标签、数据获取周期 |
| 2 | 最终评级 | 组合经理 | 评级标签、建议仓位、风险等级、核心观点（数据受限时标注） |
| 3 | 数据源评估 | Step 2 评估表 | 统计卡片、评估表格（含获取时间范围列）、数据质量总体评价、覆盖率 |
| 4 | 多维度评分 | 组合经理 | 6维度评分网格（政策/基本面/资金/技术/情绪/风险） |
| 5 | 技术分析师报告 | 技术分析师 | agent-card：分析结论、指标表格、支撑阻力、技术评级 |
| 6 | 舆情分析师报告 | 舆情分析师 | agent-card：新闻数量、正负比例、情绪评分、趋势、情绪评级 |
| 7 | 新闻分析师报告 | 新闻分析师 | agent-card：事件时间线、利好/利空分类、关键事件、新闻评级 |
| 8 | 基本面分析师报告 | 基本面分析师 | agent-card：PE/PB/营收增速/净利润增速/ROE/负债率、基本面评级 |
| 9 | 政策分析师报告 | 政策分析师 | agent-card：政策事件清单、影响力度、政策评级 |
| 10 | 游资追踪师报告 | 游资追踪师 | agent-card：成交量、主力资金、北向资金、板块热度、资金评级 |
| 11 | 解禁监控师报告 | 解禁监控师 | agent-card：股本结构、增减持、减持压力评级 |
| 12 | 多空辩论 | 多头+空头研究员 | debate-box 双栏：绿色多头论点 / 红色空头论点 |
| 13 | 研究经理裁决 | 研究经理 | agent-card manager：投资评级、核心逻辑、战略建议 |
| 14 | 交易员方案 | 交易员 | agent-card：交易参数表格、操作策略 |
| 15 | 风控辩论 | 激进+保守+中立风控师 | 3个 agent-card：激进派意见、保守派意见、中立派裁决 |
| 16 | 组合经理最终决策 | 组合经理 | conclusion 深色卡片：最终评级、仓位、核心观点、投资逻辑 |
| 17 | 核心数据 | 基本面分析师 | PE/PB/市值/换手率等关键指标表格 |
| 18 | 智能体阵容 | 系统信息 | 14个智能体标签列表 |
| 19 | 关注要点 | 组合经理 | 需跟踪的指标和事件列表 |
| 20 | 免责声明 | 固定文本 | 标准免责声明 |

#### 多股票分析的 HTML 报告

当分析多只股票时：
1. 每只股票分别生成独立的 HTML 报告，保存到 `reports/<日期>/` 目录下
2. 额外生成一份**对比汇总报告**，保存到同目录下，文件名以 `comparison_` 开头
3. 对比报告包含：对比汇总表格、各股票评级卡片、组合配置建议

示例（分析 000001 和 600519）：
```
reports/
└── 2025-06-24/
    ├── 600519_贵州茅台.html              # 茅台完整报告
    ├── 000001_平安银行.html              # 平安银行完整报告
    └── comparison_000001_600519.html     # 对比汇总报告
```

---

## 多股票分析流程

当用户要求分析多只股票时（如 "对比分析 000001 和 600519"）：

1. 对每只股票**分别执行完整的 7 步分析流程**
2. 所有股票分析完成后，输出**对比汇总表**
3. 最后给出**组合配置建议**

### 对比汇总表格式

| 维度 | 股票A | 股票B | 股票C |
|------|-------|-------|-------|
| 最终评级 | ... | ... | ... |
| 建议仓位 | ... | ... | ... |
| 政策面 | ... | ... | ... |
| 基本面 | ... | ... | ... |
| 资金面 | ... | ... | ... |
| 技术面 | ... | ... | ... |
| 风险等级 | ... | ... | ... |

---

## 智能体调用方式

每个智能体的定义文件位于 `agents/` 目录下，文件名格式为 `<agent-name>.agent.md`。

调用智能体时：
1. 读取对应的 `.agent.md` 文件获取系统提示
2. 将任务输入（股票代码、报告等）作为用户消息传入
3. 获取智能体的输出作为该阶段的结果
4. 将结果传递给下一个阶段的智能体

---

## 注意事项

1. **数据真实性**：所有分析基于公开可获取的信息。如果某些数据无法获取，标注 `[数据缺失: xxx]` 并继续分析，不要编造数据。

2. **A 股特殊性**：所有分析必须考虑 A 股的特殊规则（T+1、涨跌停、政策市、散户占比高等）。

3. **免责声明**：最终报告必须包含免责声明，明确说明分析仅供研究参考，不构成投资建议。

4. **语言**：所有输出使用中文。

5. **效率优先**：在保证质量的前提下，尽量提高效率。7 位分析师应并行执行，辩论轮次控制在 1-2 轮。

6. **HTML 报告必做**：每次分析完成后，**必须**执行 Step 8 生成 HTML 报告并保存。HTML 报告是分析的最终交付物，不可省略。报告使用内联 CSS，不依赖外部资源，确保浏览器直接打开即可美观显示。

---

## 快速开始

当用户提到股票代码或请求股票分析时，按以下顺序操作：

1. 确认股票代码和分析范围（单只还是多只）
2. 启动 Step 1：调用 7 大分析师（通过 `run_command` 获取数据）
3. 按流程逐步推进（Step 2 ~ Step 7）
4. **Step 8：生成 HTML 报告并保存到 `reports/<日期>/<股票代码>_<股票名称>.html`**
5. 向用户展示报告文件路径，并简要总结分析结论

**现在开始：检查用户输入中是否包含股票代码或分析请求，如果有，立即启动分析流程。**
