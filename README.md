# A 股与基金多智能体分析系统

> 在 **TRAE Work CN** 中运行的多智能体投资分析系统 —— 由 22 个专业智能体角色化协作，支持 **A 股股票** 与 **公募基金** 双工作流，完成全维度调研、辩论、风控与决策，并自动生成 HTML 投资报告。

## 项目简介

本项目是一个运行在 **TRAE Work CN** 中的**多智能体（Multi-Agent）分析框架**。

通过 TRAE Work CN 的技能系统（Skill）和智能体调度能力，22 个角色化的专业智能体分工协作，对 A 股股票和公募基金（场内 ETF/LOF + 场外开放基金）进行全维度调研、多空辩论、风控审查，最终由组合经理给出投资建议，并自动生成可视化 HTML 报告。

工作方式：在 TRAE Work CN 中打开本项目 → 用户输入股票/基金代码或分析请求 → 系统自动路由分发到对应工作流 → 调度智能体协同完成分析 → 输出 HTML 报告。

系统特点：

- **双工作流路由**：根据输入自动判定走股票分析（14 agent）还是基金分析（15 agent），共享辩论决策梯队
- **TRAE Work CN 原生集成**：项目级技能（`.trae/skills/stock-analysis`）自动识别触发，智能体通过 `agents/*.agent.md` 定义
- **多智能体协同**：22 个角色化智能体分工协作，覆盖技术面/基本面/政策面/资金面/情绪面/风控/决策全流程
- **多数据源融合**：通达信、腾讯财经、东方财富、新浪财经、同花顺、财联社、百度股市通、天天基金 8 大数据源
- **全量 A 股采集**：内置轻量级增量采集调度器，支持每日自动同步全市场数据
- **可扩展的数据工具**：Python CLI 接口，智能体通过 `run_command` 直接调用获取数据
- **统一报告模板**：严格遵循 HTML 报告格式规范，多只标的可对比

---

## 系统架构

```
用户输入（股票/基金代码 或 分析请求）
        │
        ▼
┌─────────────────────────────────────────────┐
│            路由分发（首要步骤）              │
│  关键词探测 → 代码探测 → 名称探测            │
│  基金关键词/ETF/净值 → 基金工作流            │
│  股票关键词/A股/行情  → 股票工作流           │
└────────────────────┬────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
┌─────────────────┐     ┌─────────────────────┐
│  股票工作流      │     │  基金工作流          │
│  7 大股票分析师  │     │  7 大基金分析师      │
│  技术/舆情/新闻  │     │  净值/基本面/重仓股  │
│  /基本面/政策    │     │  /份额/新闻/政策     │
│  /资金/解禁      │     │  /情绪              │
└────────┬────────┘     └──────────┬──────────┘
         │                         │
         └────────────┬────────────┘
                      ▼
┌─────────────────────────────────────────────┐
│        Step 2: 质量门控 + 数据源评估         │
└────────────────────┬────────────────────────┘
                     ▼
┌─────────────────────────────────────────────┐
│           Step 3: 多空辩论 (1~N 轮)         │
│       多头研究员  ◄────►  空头研究员          │
└────────────────────┬────────────────────────┘
                     ▼
┌─────────────────────────────────────────────┐
│           Step 4: 研究经理裁决               │
│         输出投资计划（Buy/Hold/Sell）         │
└────────────────────┬────────────────────────┘
                     ▼
┌─────────────────────────────────────────────┐
│           Step 5: 交易员制定方案             │
│     价位 / 仓位 / 止损 / 操作策略             │
└────────────────────┬────────────────────────┘
                     ▼
┌─────────────────────────────────────────────┐
│           Step 6: 风控辩论 + 裁决            │
│   激进派  ◄────►  保守派  ──►  中立派裁决     │
└────────────────────┬────────────────────────┘
                     ▼
┌─────────────────────────────────────────────┐
│        Step 7: 组合经理最终决策               │
│         输出最终投资报告                      │
└────────────────────┬────────────────────────┘
                     ▼
┌─────────────────────────────────────────────┐
│       Step 8: 生成 HTML 报告并保存            │
│   reports/<日期>/<代码>_<名称>.html           │
└─────────────────────────────────────────────┘
```

---

## 智能体阵容

项目包含 22 个智能体：股票分析师梯队 7 个 + 基金分析师梯队 7 个 + 共享辩论决策梯队 8 个。

### 股票分析师梯队：7 大分析师（股票工作流 Step 1）

| 智能体 | 文件 | 职责 |
|--------|------|------|
| 技术分析师 | `agents/market-analyst.agent.md` | K线、技术指标、量价关系、支撑阻力 |
| 舆情分析师 | `agents/sentiment-analyst.agent.md` | 市场情绪、舆情热度、散户态度 |
| 新闻分析师 | `agents/news-analyst.agent.md` | 行业新闻、公司公告、宏观事件 |
| 基本面分析师 | `agents/fundamentals-analyst.agent.md` | 财务报表、盈利能力、估值水平 |
| 政策分析师 | `agents/policy-analyst.agent.md` | 监管政策、产业政策、窗口指导 |
| 游资追踪师 | `agents/hot-money-tracker.agent.md` | 龙虎榜、资金流向、板块轮动 |
| 解禁监控师 | `agents/lockup-watcher.agent.md` | 限售解禁、大股东减持、股权质押 |

### 基金分析师梯队：7 大分析师（基金工作流 Step 1）

| 智能体 | 文件 | 职责 |
|--------|------|------|
| 基金市场分析师 | `agents/fund-market-analyst.agent.md` | 净值走势、各阶段业绩、同类排名、四分位排名 |
| 基金基本面分析师 | `agents/fund-fundamentals-analyst.agent.md` | 基金概况、类型、规模、费率、经理评估 |
| 基金重仓股分析师 | `agents/fund-holdings-analyst.agent.md` | 重仓股结构、行业分布、集中度、季度调仓 |
| 基金份额分析师 | `agents/fund-flows-analyst.agent.md` | 份额变动、申赎压力、规模趋势、清盘风险 |
| 基金新闻分析师 | `agents/fund-news-analyst.agent.md` | 基金公告、重仓股新闻、行业事件 |
| 基金政策分析师 | `agents/fund-policy-analyst.agent.md` | 行业监管、宏观政策、产业政策对基金主题的影响 |
| 基金情绪分析师 | `agents/fund-sentiment-analyst.agent.md` | 持有人行为、申赎情绪、市场热度、情绪周期 |

### 共享辩论与决策梯队：8 个（股票/基金工作流复用）

| 智能体 | 文件 | 职责 |
|--------|------|------|
| 多头研究员 | `agents/bull-researcher.agent.md` | 构建看涨论点，反驳看空观点 |
| 空头研究员 | `agents/bear-researcher.agent.md` | 构建看跌论点，反驳看多观点 |
| 研究经理 | `agents/research-manager.agent.md` | 裁判，综合评估，输出投资计划 |
| 交易员 | `agents/trader.agent.md` | 将投资计划转化为交易方案 |
| 激进风控师 | `agents/aggressive-analyst.agent.md` | 支持交易，认为风险可控 |
| 保守风控师 | `agents/conservative-analyst.agent.md` | 反对 / 谨慎，强调风险 |
| 中立风控师 | `agents/neutral-analyst.agent.md` | 裁决，输出最终风控意见 |
| 组合经理 | `agents/portfolio-manager.agent.md` | 最终决策者，输出投资报告 |

---

## 快速开始（在 TRAE 中运行）

### 1. 在 TRAE 中打开项目

1. 本地电脑安装并启动 **TRAE Work CN**（AI 智能开发环境）。
2. 通过 `Work` 选择`本地` ，文件夹选择本项目根目录 `my_agents/`。
3. TRAE 会自动识别项目结构，**项目级技能 `stock-analysis`**（位于 `.trae/skills/stock-analysis/SKILL.md`）会被自动加载到当前会话。

### 2. 触发分析

在 TRAE 的对话窗口中，直接输入以下任一内容即可触发对应工作流：

**股票分析触发示例：**
- 股票代码：如 `000001`、`600519`、`300750`、`688981`
- 股票名称：如「分析平安银行股票」「看看贵州茅台股票」
- 自然语言：如「帮我研究一下宁德时代股票，评估买入风险」

**基金分析触发示例：**
- 基金代码：如 `001717`（工银前沿医疗股票A）、`510300`（沪深300ETF华泰柏瑞）
- 基金名称：如「分析工银前沿医疗基金」「易方达蓝筹精选」
- 含基金关键词：如「510300 ETF 净值」「001717 申购赎回」

系统会自动判定输入类型并路由到对应工作流：
- 含基金关键词（基金/ETF/LOF/净值/申购/赎回/A类/C类等）→ 基金工作流
- 6 位数字代码 → 执行 `fund detect` 探测 → FUND/STOCK
- 中文名称且无关键词 → 默认股票工作流

### 3. 观察调度过程

TRAE 会按以下阶段推进，你可以在对话流中实时看到：

1. 7 大分析师并行调研（股票：技术/舆情/新闻/基本面/政策/资金/解禁；基金：净值/基本面/重仓股/份额/新闻/政策/情绪）
2. 质量门控 + 数据源评估
3. 多头 ⇄ 空头 辩论（1~N 轮）
4. 研究经理裁决 → 交易员出方案
5. 激进 / 保守 / 中立 风控辩论与裁决
6. 组合经理最终决策
7. 自动生成 HTML 报告

### 4. 查看生成的报告

分析完成后，HTML 报告保存在：

```
reports/<日期>/<代码>_<名称>.html
```

多只标的对比时，还会生成 `comparison_<代码1>_<代码2>_...html`。

可直接在 TRAE 内预览，也可用浏览器打开查看完整可视化报告。

---

## 数据工具 CLI

所有命令在项目根目录下执行：`python -m data_tools.cli <命令>`

### 股票数据命令

#### 行情与技术指标

```bash
python -m data_tools.cli kline <股票代码> --start <开始日期> --end <结束日期>
python -m data_tools.cli indicator <股票代码> <指标名> --date <日期> --days <回看天数>
```

**支持的技术指标**：`rsi`, `macd`, `macds`, `macdh`, `close_50_sma`, `close_200_sma`, `close_10_ema`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`, `mfi`

#### 基本面与财报

```bash
python -m data_tools.cli fundamentals <股票代码>
python -m data_tools.cli balance-sheet <股票代码> --freq quarterly
python -m data_tools.cli income-statement <股票代码> --freq quarterly
python -m data_tools.cli cashflow <股票代码> --freq quarterly
python -m data_tools.cli forecast <股票代码>
```

#### 新闻与资讯

```bash
python -m data_tools.cli news <股票代码> --start <开始日期> --end <结束日期>
python -m data_tools.cli global-news --limit 20
```

#### 资金与龙虎榜

```bash
python -m data_tools.cli dragon-tiger <股票代码> --days 5
python -m data_tools.cli northbound
python -m data_tools.cli hot-stocks
python -m data_tools.cli concept <股票代码>
```

#### 股东与解禁

```bash
python -m data_tools.cli lockup <股票代码>
python -m data_tools.cli insider <股票代码>
```

### 基金数据命令

```bash
# 路由探测（输出 FUND|<名称> 或 STOCK）
python -m data_tools.cli fund detect <代码>

# 净值与业绩
python -m data_tools.cli fund nav <基金代码> --start <开始日期> --end <结束日期>
python -m data_tools.cli fund performance <基金代码>

# 概况与经理
python -m data_tools.cli fund info <基金代码>
python -m data_tools.cli fund manager <基金代码>

# 重仓股与份额
python -m data_tools.cli fund holdings <基金代码>
python -m data_tools.cli fund flows <基金代码>

# 新闻
python -m data_tools.cli fund news <基金代码> --start <开始日期> --end <结束日期>
python -m data_tools.cli fund global-news <基金代码> --limit 20
```

### 全量 A 股采集

```bash
python -m data_tools.cli universe init          # 初始化：拉取全市场股票列表
python -m data_tools.cli universe status        # 查看采集进度
python -m data_tools.cli universe sync          # 执行一次增量采集
python -m data_tools.cli universe sync --quota 200 --force
python -m data_tools.cli universe update 000001 # 强制更新单只股票
python -m data_tools.cli universe refresh-list  # 刷新股票列表
```

### 工具命令

```bash
python -m data_tools.cli data-dir   # 显示数据存储目录
```

---

## 数据获取周期规范

### 股票数据

| 数据类型 | 获取周期 | 说明 |
|----------|----------|------|
| K 线数据 | 近 2 年 | 用于技术分析、趋势判断（约 480 个交易日） |
| 技术指标 | 近 120 天 | 用于 RSI、MACD、布林带等指标计算 |
| 个股新闻 | 近 3 个月 | 用于事件驱动、舆情分析 |
| 财报数据 | 近 2 年季度 | 用于财务趋势分析（8 个季度） |
| 龙虎榜 / 解禁 / 股东 | 近 6 个月 | 用于资金面 / 解禁压力评估 |
| 基本面 / 北向 / 热门股 | 当前快照 | 用于实时估值 / 资金动向 |
| 全球新闻 | 当前快照 | 用于宏观政策分析 |

### 基金数据

| 数据类型 | 获取周期 | 说明 |
|----------|----------|------|
| 净值数据 | 近 1 年 | 用于净值趋势分析（约 240 个交易日） |
| 业绩表现 | 当前快照 | 各阶段收益/同类排名/四分位排名 |
| 基金概况 | 当前快照 | 类型/规模/费率/经理/托管人 |
| 基金经理 | 当前快照 | 任职时间/管理规模/历史业绩 |
| 重仓股 | 当前快照 | 最新报告期前十大重仓股 |
| 份额变动 | 近 8 期 | 约 2 年季度报告，用于申赎压力分析 |
| 基金新闻 | 近 3 个月 | 用于事件驱动分析 |
| 全球新闻 | 当前快照 | 用于政策与宏观分析 |

---

## 数据目录结构

```
data/
├── _meta/                                  # 元数据
│   ├── stock_list.json                     # 全量股票列表
│   ├── universe_progress.json              # 采集进度追踪
│   └── universe_config.json                # 采集配置
├── <股票代码>/                             # 按代码分子目录（股票/基金共用）
│   ├── kline_<开始日期>_<结束日期>.csv      # K线数据
│   ├── fundamentals_<日期>.txt              # 基本面快照
│   ├── indicator_<指标名>_<日期>.txt        # 技术指标
│   ├── news_<开始日期>_<结束日期>.md        # 个股新闻
│   ├── balance_sheet_quarterly.csv         # 资产负债表
│   ├── income_statement_quarterly.csv      # 利润表
│   ├── cashflow_quarterly.csv              # 现金流量表
│   ├── dragon_tiger_<日期>.md              # 龙虎榜
│   ├── lockup_<日期>.md                    # 限售解禁
│   ├── concept_blocks_<日期>.md            # 概念板块
│   ├── insider_transactions_<日期>.txt     # 股东研究
│   ├── profit_forecast_<日期>.md           # 盈利预测
│   ├── nav_<开始日期>_<结束日期>.csv       # 基金净值（基金专属）
│   ├── info_<日期>.md                      # 基金概况（基金专属）
│   ├── holdings_<日期>.md                  # 基金重仓股（基金专属）
│   ├── manager_<日期>.md                   # 基金经理（基金专属）
│   ├── performance_<日期>.md               # 基金业绩表现（基金专属）
│   └── flows_<日期>.md                     # 基金份额变动（基金专属）
├── global_news_<日期>.md                   # 全球财经新闻
├── northbound_<日期>.md                    # 北向资金
└── hot_stocks_<日期>.md                    # 热门股

reports/
└── <日期>/
    ├── <股票代码>_<股票名称>.html            # 个股报告
    ├── <基金代码>_<基金简称>.html            # 基金报告
    └── comparison_<代码1>_<代码2>...html    # 多标的对比报告
```

---

## 数据源

| 数据源 | 接口类型 | 覆盖内容 |
|--------|----------|----------|
| mootdx（通达信） | TCP | K线、财务快照、F10 股东研究 |
| 腾讯财经 | HTTP | 实时报价、PE/PB/市值、换手率 |
| 东方财富 | HTTP | 龙虎榜、限售解禁、个股搜索、7x24 资讯、基金份额变动 |
| 新浪财经 | HTTP | K线备用、三大财报（资产负债表 / 利润表 / 现金流量表） |
| 同花顺 | HTTP | 一致预期 EPS、涨停热门股、北向资金 |
| 财联社 | HTTP | 全球财经快讯 |
| 百度股市通 | HTTP | 概念板块、行业分类 |
| 天天基金 | HTTP | 基金净值/概况/重仓股/经理/业绩/份额变动 |

---

## 决策框架

### 决策维度权重

| 维度 | 权重 | 说明 |
|------|------|------|
| 政策面 | 25% | A 股是政策市 |
| 基本面 | 20% | 长期价值的基础 |
| 资金面 | 20% | 短期走势的关键 |
| 风险评估 | 15% | 决定仓位的核心 |
| 技术面 | 10% | 入场时机的参考 |
| 情绪面 | 10% | 短期波动的放大器 |

### 五级评级体系

| 评级 | 含义 | 建议仓位 |
|------|------|----------|
| 强烈推荐买入 | 确定性高，收益空间大 | 15-20% |
| 推荐买入 | 看好，有较好收益空间 | 10-15% |
| 谨慎推荐 | 有机会但风险也大 | 5-10% |
| 中性 | 机会风险平衡 | 0-5% 或观望 |
| 回避 | 风险大于收益 | 0%，不建议参与 |

### A 股与基金特殊考量

**股票分析：**
- T+1 制度限制交易灵活性
- 涨跌停制度影响流动性
- 政策变化快，需要灵活调整
- 散户占比高，情绪波动大
- 信息不对称明显

**基金分析：**
- 申赎压力（"反弹即赎回"陷阱）
- 规模魔咒（规模膨胀后业绩下滑）
- 清盘风险（规模 <5000 万元持续 60 个工作日）
- 经理更替风险
- A/C 类份额选择（短期 C 类，长期 A 类）

---

## 项目结构

```
my_agents/
├── agents/                                 # 22 个智能体定义
│   ├── 【股票分析师 7 个】
│   │   ├── market-analyst.agent.md
│   │   ├── sentiment-analyst.agent.md
│   │   ├── news-analyst.agent.md
│   │   ├── fundamentals-analyst.agent.md
│   │   ├── policy-analyst.agent.md
│   │   ├── hot-money-tracker.agent.md
│   │   └── lockup-watcher.agent.md
│   ├── 【基金分析师 7 个】
│   │   ├── fund-market-analyst.agent.md
│   │   ├── fund-fundamentals-analyst.agent.md
│   │   ├── fund-holdings-analyst.agent.md
│   │   ├── fund-flows-analyst.agent.md
│   │   ├── fund-news-analyst.agent.md
│   │   ├── fund-policy-analyst.agent.md
│   │   └── fund-sentiment-analyst.agent.md
│   └── 【共享辩论决策 8 个】
│       ├── bull-researcher.agent.md
│       ├── bear-researcher.agent.md
│       ├── research-manager.agent.md
│       ├── trader.agent.md
│       ├── aggressive-analyst.agent.md
│       ├── conservative-analyst.agent.md
│       ├── neutral-analyst.agent.md
│       └── portfolio-manager.agent.md
├── data_tools/                             # 数据获取工具
│   ├── __init__.py
│   ├── stock_data.py                       # 股票数据源封装
│   ├── fund_data.py                        # 基金数据源封装
│   ├── universe.py                         # 全量采集调度器
│   └── cli.py                              # CLI 入口（股票+基金命令）
├── .trae/skills/                           # 项目级 TRAE 技能
│   └── stock-analysis/SKILL.md             # 股票+基金分析触发技能（含路由分发）
├── docs/                                   # 设计文档
│   └── universe-collector-design.md
├── data/                                   # 数据缓存（运行时生成）
├── reports/                                # HTML 报告（运行时生成）
├── requirements.txt
└── README.md
```

---

## 设计文档

- [全量 A 股数据采集系统设计](docs/universe-collector-design.md) — 介绍 `universe.py` 增量采集调度器的架构、调度算法、防封与限流策略

---

## 触发关键词

### 股票分析触发

- 股票代码（6 位数字，如 `000001`、`600519`、`300750`、`688981`）
- "分析股票"、"股票分析"、"研究一下"、"帮我看看"
- "投资建议"、"买入还是卖出"、"能买吗"
- 股票名称（如"平安银行"、"贵州茅台"等）
- "A 股"、"行情"、"走势"等关键词 + 具体标的

### 基金分析触发

- 基金代码（6 位数字，如 `001717`、`510300`、`110011`）
- 基金名称（如"工银前沿医疗基金"、"易方达蓝筹精选"）
- 基金关键词：基金/ETF/LOF/联接/申购/赎回/净值/份额/A类/C类/混合/股票型/债券型/指数型/QDII/场内/场外/定投
- "分析基金"、"基金净值"、"基金申购"、"基金定投"等

---

## 补充说明

1. **数据真实性**：所有分析基于公开可获取的信息。如果某些数据无法获取，会标注 `[数据缺失: xxx]` 并继续分析。
2. **A 股与基金特殊性**：所有分析完整考虑了 A 股的特殊规则（T+1、涨跌停、政策市、散户占比高）与基金的特殊现象（申赎压力、规模魔咒、清盘风险等）。
3. **路由准确性**：系统会优先根据关键词判定，其次通过代码探测（`fund detect`），最后按名称默认走股票工作流，确保股票和基金走对各自的分析框架。

---

## 免责声明

本项目基于公开信息和多智能体协同分析生成，仅供研究参考，不构成任何投资建议。

投资者应根据自身风险承受能力独立做出投资决策，并自行承担投资风险。**股市有风险，投资需谨慎。基金有风险，投资需谨慎。**
