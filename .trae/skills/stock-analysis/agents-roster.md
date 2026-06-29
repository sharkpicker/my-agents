# Agent 阵容清单

项目根目录: `d:\01_coding\my_agents`。所有 agent 定义文件在 `agents/` 目录下。每个 subagent 通过读取自己的 .agent.md 文件获取角色定义和输出格式。

---

## 1. 股票分析师梯队(7 个)

| # | 角色 | agent 文件 | 职责 | 推荐数据 |
|---|------|-----------|------|----------|
| 1 | 技术分析师 | `market-analyst.agent.md` | K线、技术指标、量价关系、支撑阻力 | `kline` + `indicator`(RSI/MACD/布林带 ≥3 个) |
| 2 | 舆情分析师 | `sentiment-analyst.agent.md` | 市场情绪、舆情热度、散户态度 | `news`(个股) + `global-news` + `hot-stocks` |
| 3 | 新闻分析师 | `news-analyst.agent.md` | 行业新闻、公司公告、宏观事件 | `news` + `global-news` + `concept` |
| 4 | 基本面分析师 | `fundamentals-analyst.agent.md` | 财务报表、盈利能力、估值水平 | `fundamentals` + `income-statement` + `balance-sheet` + `cashflow` + `forecast` |
| 5 | 政策分析师 | `policy-analyst.agent.md` | 监管政策、产业政策、窗口指导 | `global-news` + `news` + `concept` |
| 6 | 游资追踪师 | `hot-money-tracker.agent.md` | 龙虎榜、资金流向、板块轮动 | `kline`(量价) + `dragon-tiger` + `northbound` + `hot-stocks` + `concept` + `insider` |
| 7 | 解禁监控师 | `lockup-watcher.agent.md` | 限售解禁、大股东减持、股权质押 | `lockup` + `insider` + `fundamentals` + `news` |

---

## 2. 基金分析师梯队(7 个)

| # | 角色 | agent 文件 | 职责 | 推荐数据 |
|---|------|-----------|------|----------|
| 1 | 基金市场分析师 | `fund-market-analyst.agent.md` | 净值走势、各阶段业绩、同类排名、四分位排名 | `fund nav` + `fund performance` |
| 2 | 基金基本面分析师 | `fund-fundamentals-analyst.agent.md` | 基金概况、类型、规模、费率、经理评估 | `fund info` + `fund manager` |
| 3 | 基金重仓股分析师 | `fund-holdings-analyst.agent.md` | 重仓股结构、行业分布、集中度、季度调仓 | `fund holdings` |
| 4 | 基金份额分析师 | `fund-flows-analyst.agent.md` | 份额变动、申赎压力、规模趋势、清盘风险 | `fund flows` + `fund info` |
| 5 | 基金新闻分析师 | `fund-news-analyst.agent.md` | 基金公告、重仓股新闻、行业事件 | `fund news` + `fund global-news` + `fund holdings` |
| 6 | 基金政策分析师 | `fund-policy-analyst.agent.md` | 行业监管、宏观政策、产业政策对基金主题的影响 | `fund info`(投资主题) + `fund global-news` + `fund news`(政策筛选) + `fund holdings`(行业) |
| 7 | 基金情绪分析师 | `fund-sentiment-analyst.agent.md` | 持有人行为、申赎情绪、市场热度、情绪周期 | `fund news`(讨论热度) + `fund flows`(持有人行为) + `fund info`(持有人结构) + `fund global-news`(市场情绪) |

---

## 3. 辩论与决策梯队(8 个,股票/基金共用)

| # | 角色 | agent 文件 | 立场/职责 |
|---|------|-----------|----------|
| 1 | 多头研究员 | `bull-researcher.agent.md` | 构建看涨论点,反驳看空观点 |
| 2 | 空头研究员 | `bear-researcher.agent.md` | 构建看跌论点,反驳看多观点 |
| 3 | 研究经理 | `research-manager.agent.md` | 裁判,综合评估,输出投资计划(Buy/Hold/Sell 评级) |
| 4 | 交易员 | `trader.agent.md` | 将投资计划转化为交易方案(具体价位、仓位、操作策略) |
| 5 | 激进风控师 | `aggressive-analyst.agent.md` | 支持交易,认为风险可控 |
| 6 | 保守风控师 | `conservative-analyst.agent.md` | 反对/谨慎,强调风险控制 |
| 7 | 中立风控师 | `neutral-analyst.agent.md` | 裁决,综合两派,输出最终风控意见 |
| 8 | 组合经理 | `portfolio-manager.agent.md` | 最终决策者,输出最终投资报告 |

---

## 4. 组合分析专用 subagent(组合工作流使用)

| 角色 | agent 文件 | 描述 | 调度方式 |
|------|-----------|------|----------|
| 组合分析师 | `portfolio_analyst.md` | 整合所有单标的报告,做组合层面诊断(集中度/行业暴露/相关性/申赎压力/风格漂移) | Step 5 通过 Task 工具调度 |
| 数据质量审计员 | `data-quality-auditor.md` | 审计 Step 3 报告完整性 / 一致性 / 时效性 | `data_quality_auditor` step 调度 |
| HTML 渲染员 | `html-renderer.md` | 把 markdown 报告渲染为 HTML | Step 10 主对话直接调用 |
| 风险偏好采集员 ⚠️ 废弃 | `risk-profile-collector.agent.md` | **已废弃**,Step 2 改由主对话直接执行(本地规则解析 + AskUserQuestion 反问) | 不再使用 |
| 候选基金推荐员 ⭐ | `fund-recommender.agent.md` | 从国内场外公募全量库中筛选补/换候选 | **Step 10**(C-1/C-3) |

---

## 5. Subagent 调度模板

每个 subagent 通过 `Task` 工具以 `subagent_type: "general_purpose_task"` 调用,prompt 模板:

```
角色: <agent-name>
标的: <code>（<名称>）
数据目录: data/<stocks|funds>/<code>/
输出路径: reports/<日期>/<stock|fund>/<code>_<role>.md

请:
1. 读取 agents/<agent-name>.agent.md 获取角色定义和输出格式
2. 读取数据目录下的相关数据（数据已由主对话预拉取）
3. 完成分析/研判并写入输出路径
4. 返回契约格式(summary/detail_path/evidence)
```

**重要**: subagent 的返回值就是给主对话的"上下文材料",主对话不需要重写报告,只需转发给下一阶段的 subagent。

---

## 6. 输出归档结构

```
reports/
  <日期>/
    stock/
      <股票代码>/
        <股票代码>_market.md          # 技术分析
        <股票代码>_sentiment.md       # 舆情分析
        ... (7 个角色)
        <股票代码>_bull.md            # 多头辩论
        <股票代码>_bear.md            # 空头辩论
        <股票代码>_research_plan.md   # 投资计划
        <股票代码>_trade_plan.md      # 交易方案
        <股票代码>_risk_*.md          # 风控辩论
        <股票代码>_final.md           # 最终报告(markdown)
        <股票代码>_<简称>.html        # 最终报告(HTML)
    fund/
      <基金代码>/
        ... 类似结构
    portfolio/
      portfolio_analysis.md           # 组合分析报告(markdown)
      portfolio_<日期>.html           # 组合诊断报告(HTML)
```
