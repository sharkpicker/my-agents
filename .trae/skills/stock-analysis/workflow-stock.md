# 单股票工作流 (A)

**适用场景**: 用户输入 1 只 A 股股票代码或名称(关键词含"股票/A股/行情/走势"等)。

---

## Step 1: 7 大股票分析师并行调研

**并行调度以下 7 个 subagent**(同 [`workflow-fund.md`](workflow-fund.md) 调度方式):

| # | subagent 角色 | agent 文件 | 推荐数据命令 |
|---|--------------|-----------|--------------|
| 1 | 技术分析师 | `market-analyst.agent.md` | `kline <code> --start <近2年起> --end <今天>` + `indicator <code> rsi --days 120` + `indicator <code> macd --days 120` + `indicator <code> boll --days 120` |
| 2 | 舆情分析师 | `sentiment-analyst.agent.md` | `news <code> --start <近3月起> --end <今天>` + `global-news --limit 20` + `hot-stocks` |
| 3 | 新闻分析师 | `news-analyst.agent.md` | `news <code> --start <近3月起> --end <今天>` + `global-news --limit 20` + `concept <code>` |
| 4 | 基本面分析师 | `fundamentals-analyst.agent.md` | `fundamentals <code>` + `income-statement <code> --freq quarterly` + `balance-sheet <code> --freq quarterly` + `cashflow <code> --freq quarterly` + `forecast <code>` |
| 5 | 政策分析师 | `policy-analyst.agent.md` | `global-news --limit 30`(政策新闻) + `news <code> --start <近3月起> --end <今天>` + `concept <code>`(行业板块) |
| 6 | 游资追踪师 | `hot-money-tracker.agent.md` | `kline <code>`(量价) + `dragon-tiger <code> --days 180` + `northbound` + `hot-stocks` + `concept <code>` + `insider <code>` |
| 7 | 解禁监控师 | `lockup-watcher.agent.md` | `lockup <code>` + `insider <code>` + `fundamentals <code>`(股本) + `news <code> --start <近3月起> --end <今天>`(减持新闻) |

**重要**: 7 个 subagent 必须在同一消息中通过多次 Task 工具调用**并行**触发。

**输出归档**:
- 数据文件: `data/stocks/<code>/`
- 分析报告: `reports/<日期>/stock/<code>_<role>.md`

---

## Step 2: 质量门控与数据源评估

主对话收集 7 份报告后,生成**数据源评估表**:

| 数据源 | 对应工具命令 | 获取时间范围 | 状态 | 缺失内容 | 对分析结论的影响 |
|--------|-------------|-------------|------|----------|-----------------|
| mootdx (通达信) | `kline` | 近2年 | ✅ OK / ❌ 不OK / ⚠️ 部分 | - | 无 / 大 / 中 / 小 |
| 腾讯财经 | `fundamentals` | 当前快照 | ... | ... | ... |
| 东方财富 | `news` | 近3个月 | ... | ... | ... |
| 新浪财经 | `income-statement` | 近2年季度 | ... | ... | ... |
| 同花顺 | `forecast` | 当前快照 | ... | ... | ... |
| 百度股市通 | `concept` | 当前快照 | ... | ... | ... |

**影响程度判定标准**:
| 影响程度 | 说明 |
|----------|------|
| **大** | 缺失数据直接导致某维度分析无法进行,结论可信度显著下降 |
| **中** | 缺失数据影响部分指标计算,但可通过其他数据源补充或推断 |
| **小** | 缺失数据为辅助参考,不影响核心结论 |

---

## Step 3: 多空辩论

```
Task({description: "多头辩论", prompt: "你是 bull-researcher(多头研究员)。读取 agents/bull-researcher.agent.md,基于 7 份股票分析师报告(路径:reports/<日期>/stock/<code>_*.md)构建完整看涨论点并反驳可能的看空观点。", subagent_type: "general_purpose_task"})

Task({description: "空头辩论", prompt: "你是 bear-researcher(空头研究员)。读取 agents/bear-researcher.agent.md,基于 7 份股票分析师报告构建完整看跌论点并反驳多头观点。", subagent_type: "general_purpose_task"})
```

**轮次**: 默认 1 轮,复杂标的可 2-3 轮。

---

## Step 4: 研究经理裁决

```
Task({description: "研究经理裁决", prompt: "你是 research-manager。读取 agents/research-manager.agent.md,基于 7 份分析师报告 + 多空辩论记录输出投资计划:Buy/Overweight/Hold/Underweight/Sell 评级、核心逻辑、战略行动建议、风险提示。", subagent_type: "general_purpose_task"})
```

---

## Step 5: 交易员方案

```
Task({description: "交易员方案", prompt: "你是 trader。读取 agents/trader.agent.md,基于研究计划输出交易方案:交易方向(买入/持有/卖出)、具体价位(入场/止损/目标)、仓位建议、操作策略、风险控制。", subagent_type: "general_purpose_task"})
```

---

## Step 6: 风控辩论 + 中立裁决

```
Task({description: "激进风控", prompt: "你是 aggressive-analyst。读取 agents/aggressive-analyst.agent.md,基于交易方案给出支持意见。", subagent_type: "general_purpose_task"})

Task({description: "保守风控", prompt: "你是 conservative-analyst。读取 agents/conservative-analyst.agent.md,基于交易方案给出谨慎意见。", subagent_type: "general_purpose_task"})

Task({description: "中立风控裁决", prompt: "你是 neutral-analyst。读取 agents/neutral-analyst.agent.md,综合两派意见给出最终风控审查结论和参数调整建议。", subagent_type: "general_purpose_task"})
```

---

## Step 7: 组合经理最终报告

```
Task({description: "组合经理最终报告", prompt: "你是 portfolio-manager。读取 agents/portfolio-manager.agent.md,综合所有材料输出最终 A股投资分析报告:数据源评估、最终评级(强烈推荐买入/推荐买入/谨慎推荐/中性/回避)、建议仓位、核心观点、多维度分析摘要(政策面/基本面/资金面/技术面/情绪面/风险)、投资逻辑、操作建议、关注要点、免责声明。", subagent_type: "general_purpose_task"})
```

---

## Step 8: HTML 报告生成与保存(主对话执行)

保存路径: `reports/<日期>/<股票代码>_<股票简称>.html`(如 `reports/2026-06-27/000001_平安银行.html`)

**HTML 报告必须包含**:
- 投资评级 + 建议仓位
- 数据源评估表
- 核心观点
- 多维度分析摘要
- 投资逻辑(核心利好 + 主要风险)
- 操作建议(买入/持有/卖出,含入场策略、止损策略、止盈策略、持有周期)
- 关注要点
- 免责声明
