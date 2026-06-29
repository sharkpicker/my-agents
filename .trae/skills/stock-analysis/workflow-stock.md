# 单股票工作流 (A)

**适用场景**: 用户输入 1 只 A 股股票代码或名称(关键词含"股票/A股/行情/走势"等)。

---

## Step 2: 数据预拉取（主对话执行）

**目标**: 在调度分析师之前，确保本地有满足时效性要求的数据。

### 2.1 增量拉取判断

| 数据类型 | 有效期限 | 判断依据 |
|---------|---------|---------|
| K线/技术指标 | 近2年/120天 | 文件内日期范围 |
| 基本面/财报 | 7天 | 文件修改时间 |
| 新闻/概念 | 近3个月 | 文件内日期范围 |
| global_news/hot_stocks/northbound | 24小时 | 文件修改时间 |
| 龙虎榜/解禁 | 7天 | 文件修改时间 |

### 2.2 增量拉取执行

主对话执行以下命令（只拉缺失/过期的）：

```bash
python -m data_tools.cli kline <code> --start <近2年起> --end <今天>
python -m data_tools.cli indicator <code> rsi --days 120
python -m data_tools.cli indicator <code> macd --days 120
python -m data_tools.cli indicator <code> boll --days 120
python -m data_tools.cli fundamentals <code>
python -m data_tools.cli income-statement <code> --freq quarterly
python -m data_tools.cli balance-sheet <code> --freq quarterly
python -m data_tools.cli cashflow <code> --freq quarterly
python -m data_tools.cli forecast <code>
python -m data_tools.cli news <code> --start <近3月前> --end <今天>
python -m data_tools.cli global-news --limit 30
python -m data_tools.cli concept <code>
python -m data_tools.cli dragon-tiger <code> --days 180
python -m data_tools.cli northbound
python -m data_tools.cli hot-stocks
python -m data_tools.cli lockup <code>
python -m data_tools.cli insider <code>
```

### 2.3 分析师视角

分析师读取 `data/stocks/<code>/` 下的已有文件，如发现数据缺失可自行补充拉取。

---

## Step 3: 7 大股票分析师并行调研

**并行调度以下 7 个 subagent**,每个 subagent 通过 Task 工具以 `subagent_type: "general_purpose_task"` 调用。

**调度方式(每个 subagent)**:

```
Task({
  description: "<股票名> <角色>分析",
  prompt: "角色: <agent-name>
标的: <code>（<股票名称>）
数据目录: data/stocks/<code>/
输出路径: reports/<日期>/stock/<code>_<role>.md

请:
1. 读取 agents/<agent-name>.agent.md 获取角色定义和输出格式
2. 读取数据目录下的相关数据（数据已由主对话预拉取）
3. 完成分析报告并写入输出路径
4. 返回契约格式(summary/detail_path/evidence)",
  subagent_type: "general_purpose_task"
})
```

| # | subagent 角色 | agent 文件 | 读取数据 |
|---|--------------|-----------|----------|
| 1 | 技术分析师 | `market-analyst.agent.md` | kline, indicator(rsi/macd/boll) |
| 2 | 舆情分析师 | `sentiment-analyst.agent.md` | news, global_news, hot_stocks |
| 3 | 新闻分析师 | `news-analyst.agent.md` | news, global_news, concept |
| 4 | 基本面分析师 | `fundamentals-analyst.agent.md` | fundamentals, income_statement, balance_sheet, cashflow, forecast |
| 5 | 政策分析师 | `policy-analyst.agent.md` | global_news, news, concept |
| 6 | 游资追踪师 | `hot-money-tracker.agent.md` | kline, dragon_tiger, northbound, hot_stocks, concept, insider |
| 7 | 解禁监控师 | `lockup-watcher.agent.md` | lockup, insider, fundamentals, news |

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

## Step 6: 研究经理裁决

```
Task({description: "研究经理裁决", prompt: "你是 research-manager。读取 agents/research-manager.agent.md,基于 7 份分析师报告 + 多空辩论记录输出投资计划:Buy/Overweight/Hold/Underweight/Sell 评级、核心逻辑、战略行动建议、风险提示。", subagent_type: "general_purpose_task"})
```

---

## Step 7: 交易员方案

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

## Step 10: HTML 报告生成与保存(主对话执行)

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
