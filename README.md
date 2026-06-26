# A 股多智能体分析系统（TRAE 项目）

> 在 **TRAE** 中运行的多智能体投资分析系统 —— 由 14 个专业智能体角色化协作，完成 A 股全维度调研、辩论、风控与决策，并自动生成 HTML 投资报告。

## 项目简介

本项目是一个运行在 **TRAE**（AI 智能开发环境）中的**多智能体（Multi-Agent）分析框架**。

通过 TRAE 的技能系统（Skill）和智能体调度能力，14 个角色化的专业智能体分工协作，对 A 股个股进行全维度调研、多空辩论、风控审查，最终由组合经理给出投资建议，并自动生成可视化 HTML 报告。

工作方式：在 TRAE 中打开本项目 → 用户输入股票代码或分析请求 → TRAE 自动触发 `stock-analysis` 项目级技能 → 调度 14 个智能体协同完成分析 → 输出 HTML 报告。

系统特点：

- **TRAE 原生集成**：项目级技能（`.trae/skills/stock-analysis`）自动识别触发，智能体通过 `agents/*.agent.md` 定义
- **多智能体协同**：14 个角色化智能体分工协作，覆盖技术面、基本面、政策面、资金面、情绪面、风控、决策全流程
- **多数据源融合**：通达信、腾讯财经、东方财富、新浪财经、同花顺、财联社、百度股市通 7 大数据源
- **全量 A 股采集**：内置轻量级增量采集调度器，支持每日自动同步全市场数据
- **可扩展的数据工具**：Python CLI 接口，智能体通过 `run_command` 直接调用获取数据
- **统一报告模板**：严格遵循 HTML 报告格式规范，多只股票可对比

---

## 系统架构

```
用户输入（股票代码 / 分析请求）
        │
        ▼
┌─────────────────────────────────────────────┐
│          Step 1: 7 大分析师并行调研          │
│  技术 │ 舆情 │ 新闻 │ 基本面 │ 政策 │ 资金 │ 解禁 │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│        Step 2: 质量门控 + 数据源评估         │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│           Step 3: 多空辩论 (1~N 轮)         │
│       多头研究员  ◄────►  空头研究员          │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│           Step 4: 研究经理裁决               │
│         输出投资计划（Buy/Hold/Sell）         │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│           Step 5: 交易员制定方案             │
│     价位 / 仓位 / 止损 / 操作策略             │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│           Step 6: 风控辩论 + 裁决            │
│   激进派  ◄────►  保守派  ──►  中立派裁决     │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│        Step 7: 组合经理最终决策               │
│         输出最终投资报告                      │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│       Step 8: 生成 HTML 报告并保存            │
│   reports/<日期>/<代码>_<名称>.html           │
└─────────────────────────────────────────────┘
```

---

## 智能体阵容

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
| 保守风控师 | `agents/conservative-analyst.agent.md` | 反对 / 谨慎，强调风险 |
| 中立风控师 | `agents/neutral-analyst.agent.md` | 裁决，输出最终风控意见 |
| 组合经理 | `agents/portfolio-manager.agent.md` | 最终决策者，输出投资报告 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

依赖包：`mootdx`, `pandas`, `requests`, `stockstats`, `python-dateutil`

### 2. 触发分析

向系统输入股票代码（如 `000001`、`600519`）或分析请求（如"帮我分析平安银行"），智能体调度系统会自动启动完整分析流程。

### 3. 查看报告

分析完成后，HTML 报告保存在：

```
reports/<日期>/<股票代码>_<股票名称>.html
```

多只股票对比时，还会生成 `comparison_<代码1>_<代码2>_...html`。

---

## 数据工具 CLI

所有命令在项目根目录下执行：`python -m data_tools.cli <命令>`

### 行情与技术指标

```bash
python -m data_tools.cli kline <股票代码> --start <开始日期> --end <结束日期>
python -m data_tools.cli indicator <股票代码> <指标名> --date <日期> --days <回看天数>
```

**支持的技术指标**：`rsi`, `macd`, `macds`, `macdh`, `close_50_sma`, `close_200_sma`, `close_10_ema`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`, `mfi`

### 基本面与财报

```bash
python -m data_tools.cli fundamentals <股票代码>
python -m data_tools.cli balance-sheet <股票代码> --freq quarterly
python -m data_tools.cli income-statement <股票代码> --freq quarterly
python -m data_tools.cli cashflow <股票代码> --freq quarterly
python -m data_tools.cli forecast <股票代码>
```

### 新闻与资讯

```bash
python -m data_tools.cli news <股票代码> --start <开始日期> --end <结束日期>
python -m data_tools.cli global-news --limit 20
```

### 资金与龙虎榜

```bash
python -m data_tools.cli dragon-tiger <股票代码> --days 5
python -m data_tools.cli northbound
python -m data_tools.cli hot-stocks
python -m data_tools.cli fund-flow <股票代码>
python -m data_tools.cli concept <股票代码>
```

### 股东与解禁

```bash
python -m data_tools.cli lockup <股票代码>
python -m data_tools.cli insider <股票代码>
```

### 全量 A 股采集

```bash
# 初始化：拉取全市场股票列表
python -m data_tools.cli universe init

# 查看采集进度
python -m data_tools.cli universe status

# 执行一次增量采集（建议挂定时任务每日运行）
python -m data_tools.cli universe sync
python -m data_tools.cli universe sync --quota 200 --force

# 强制更新单只股票
python -m data_tools.cli universe update 000001

# 刷新股票列表
python -m data_tools.cli universe refresh-list
```

### 工具命令

```bash
python -m data_tools.cli data-dir   # 显示数据存储目录
```

---

## 数据获取周期规范

| 数据类型 | 获取周期 | 说明 |
|----------|----------|------|
| K 线数据 | 近 2 年 | 用于技术分析、趋势判断（约 480 个交易日） |
| 技术指标 | 近 120 天 | 用于 RSI、MACD、布林带等指标计算 |
| 个股新闻 | 近 3 个月 | 用于事件驱动、舆情分析 |
| 财报数据 | 近 2 年季度 | 用于财务趋势分析（8 个季度） |
| 龙虎榜 / 解禁 / 股东 | 近 6 个月 | 用于资金面 / 解禁压力评估 |
| 基本面 / 北向 / 热门股 | 当前快照 | 用于实时估值 / 资金动向 |
| 全球新闻 | 当前快照 | 用于宏观政策分析 |

---

## 数据目录结构

```
data/
├── _meta/                                  # 元数据
│   ├── stock_list.json                     # 全量股票列表
│   ├── universe_progress.json              # 采集进度追踪
│   └── universe_config.json                # 采集配置
├── <股票代码>/                             # 按股票代码分子目录
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
│   └── profit_forecast_<日期>.md           # 盈利预测
├── global_news_<日期>.md                   # 全球财经新闻
├── northbound_<日期>.md                    # 北向资金
└── hot_stocks_<日期>.md                    # 热门股

reports/
└── <日期>/
    ├── <股票代码>_<股票名称>.html            # 个股报告
    └── comparison_<代码1>_<代码2>...html    # 多股对比报告
```

---

## 数据源

| 数据源 | 接口类型 | 覆盖内容 |
|--------|----------|----------|
| mootdx（通达信） | TCP | K线、财务快照、F10 股东研究 |
| 腾讯财经 | HTTP | 实时报价、PE/PB/市值、换手率 |
| 东方财富 | HTTP | 龙虎榜、限售解禁、个股搜索、7x24 资讯 |
| 新浪财经 | HTTP | K线备用、三大财报（资产负债表 / 利润表 / 现金流量表） |
| 同花顺 | HTTP | 一致预期 EPS、涨停热门股、北向资金 |
| 财联社 | HTTP | 全球财经快讯 |
| 百度股市通 | HTTP | 概念板块、行业分类 |

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

### A 股特殊考量

- T+1 制度限制交易灵活性
- 涨跌停制度影响流动性
- 政策变化快，需要灵活调整
- 散户占比高，情绪波动大
- 信息不对称明显

---

## 项目结构

```
my_agents/
├── agents/                                 # 14 个智能体定义
│   ├── market-analyst.agent.md
│   ├── sentiment-analyst.agent.md
│   ├── news-analyst.agent.md
│   ├── fundamentals-analyst.agent.md
│   ├── policy-analyst.agent.md
│   ├── hot-money-tracker.agent.md
│   ├── lockup-watcher.agent.md
│   ├── bull-researcher.agent.md
│   ├── bear-researcher.agent.md
│   ├── research-manager.agent.md
│   ├── trader.agent.md
│   ├── aggressive-analyst.agent.md
│   ├── conservative-analyst.agent.md
│   ├── neutral-analyst.agent.md
│   └── portfolio-manager.agent.md
├── data_tools/                             # 数据获取工具
│   ├── __init__.py
│   ├── stock_data.py                       # 数据源封装
│   ├── universe.py                         # 全量采集调度器
│   └── cli.py                              # CLI 入口
├── .trae/skills/                           # 项目级 TRAE 技能
│   └── stock-analysis/SKILL.md             # 股票分析触发技能
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

以下输入会触发本系统的分析流程：

- 股票代码（6 位数字，如 `000001`、`600519`、`300750`、`688981`）
- "分析股票"、"股票分析"、"研究一下"、"帮我看看"
- "投资建议"、"买入还是卖出"、"能买吗"
- 股票名称（如"平安银行"、"贵州茅台"等）
- "A 股"、"行情"、"走势"等关键词 + 具体标的

---

## 注意事项

1. **数据真实性**：所有分析基于公开可获取的信息。如果某些数据无法获取，标注 `[数据缺失: xxx]` 并继续分析，不要编造数据。
2. **A 股特殊性**：所有分析必须考虑 A 股的特殊规则（T+1、涨跌停、政策市、散户占比高等）。
3. **免责声明**：最终报告包含免责声明，明确说明分析仅供研究参考，不构成投资建议。
4. **效率优先**：7 位分析师并行执行，辩论轮次控制在 1-2 轮。
5. **报告必做**：每次分析完成后，必须生成 HTML 报告并保存。HTML 报告是分析的最终交付物。

---

## 免责声明

本项目基于公开信息和多智能体协同分析生成，仅供研究参考，不构成任何投资建议。

投资者应根据自身风险承受能力独立做出投资决策，并自行承担投资风险。**股市有风险，投资需谨慎。**