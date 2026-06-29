# 单基金工作流 (B)

**适用场景**: 用户输入 1 只基金代码或名称(关键词含"基金/ETF/联接/净值/份额"等)。

---

## Step 1: 7 大基金分析师并行调研

**并行调度以下 7 个 subagent**,每个 subagent 通过 Task 工具以 `subagent_type: "general_purpose_task"` 调用。

**调度方式(每个 subagent)**:

```
Task({
  description: "<基金名> <角色>分析",
  prompt: "你是一位<角色>(<agent-name>)。请:
    1. 读取 agents/<agent-name>.agent.md 文件,严格按照其中的输出格式完成报告
    2. 对基金 <代码> 拉取数据:<数据命令列表>
    3. 数据保存到 data/funds/<代码>/ 目录
    4. 基于数据完成你的分析报告并保存到 reports/<日期>/fund/<代码>_<角色>.md
    5. 返回报告核心要点摘要给我",
  subagent_type: "general_purpose_task"
})
```

| # | subagent 角色 | agent 文件 | 推荐数据命令 |
|---|--------------|-----------|--------------|
| 1 | 基金市场分析师 | `fund-market-analyst.agent.md` | `fund performance <code>` + `fund nav <code> --start <近1年起> --end <今天>` |
| 2 | 基金基本面分析师 | `fund-fundamentals-analyst.agent.md` | `fund info <code>` + `fund manager <code>` |
| 3 | 基金重仓股分析师 | `fund-holdings-analyst.agent.md` | `fund holdings <code>` |
| 4 | 基金份额分析师 | `fund-flows-analyst.agent.md` | `fund flows <code>` + `fund info <code>`(补充规模) |
| 5 | 基金新闻分析师 | `fund-news-analyst.agent.md` | `fund news <code> --start <近3月起> --end <今天>` + `fund global-news <code> --limit 30` + `fund holdings <code>`(关联重仓股) |
| 6 | 基金政策分析师 | `fund-policy-analyst.agent.md` | `fund info <code>`(投资主题) + `fund global-news <code> --limit 30` + `fund news <code> --start <近3月起> --end <今天>`(政策筛选) + `fund holdings <code>`(行业) |
| 7 | 基金情绪分析师 | `fund-sentiment-analyst.agent.md` | `fund news <code> --start <近3月起> --end <今天>`(讨论热度) + `fund flows <code>`(持有人行为) + `fund info <code>`(持有人结构) + `fund global-news <code> --limit 30`(市场情绪) |

**重要**: 7 个 subagent 必须在同一消息中通过多次 Task 工具调用**并行**触发。

---

## Step 2: 质量门控与数据源评估

主对话收集 7 份报告后,生成**基金数据源评估表**:

| 数据源 | 对应工具命令 | 获取时间范围 | 状态 | 缺失内容 | 对分析结论的影响 |
|--------|-------------|-------------|------|----------|-----------------|
| 天天基金 lsjz | `fund nav` | 近1年 | ✅ OK / ❌ 不OK / ⚠️ 部分 | - | 无 / 大 / 中 / 小 |
| 天天基金 F10 | `fund info` | 当前快照 | ... | ... | ... |
| 天天基金 F10 | `fund holdings` | 当前快照 | ... | ... | ... |
| 天天基金 F10 | `fund manager` | 当前快照 | ... | ... | ... |
| 天天基金 jdzf | `fund performance` | 当前快照 | ... | ... | ... |
| 东方财富 datacenter | `fund flows` | 近8期 | ... | ... | ... |
| 东方财富搜索 | `fund news` | 近3个月 | ... | ... | ... |
| 财联社 | `fund global-news` | 当前快照 | ... | ... | ... |

**评估结论要求**:
1. 本次分析的数据覆盖率(正常 / 总数)
2. 关键数据源(净值、重仓股、份额变动)是否可用
3. 数据缺失对最终结论可信度的整体影响等级(高 / 中 / 低)
4. 哪些结论需要标注"数据受限"提示

**报告质量检查**(必采清单):
- 净值业绩报告:最新净值、波动率、最大回撤、各阶段涨幅、同类排名、四分位排名
- 基本面报告:基金类型、规模、费率、经理任职年限与回报
- 重仓股报告:前十明细、集中度、行业分布、调仓方向
- 份额报告:份额趋势、申赎方向、反弹即赎评估、清盘风险
- 新闻报告:新闻数量、利好利空事件、事件驱动评估
- 政策报告:政策清单、影响方向、政策环境评级
- 情绪报告:持有人行为、情绪周期、情绪面评估

如果某份报告缺失关键数据:指示该 subagent 补充,最多补充 1 次,仍缺失则标注 `[数据缺失]` 继续。

---

## Step 3: 多空辩论

将 7 份基金分析师报告同时提交给**多头研究员**和**空头研究员**,展开第一轮辩论。

**调度方式**:

```
Task({description: "多头辩论", prompt: "你是 bull-researcher(多头研究员)。请读取 agents/bull-researcher.agent.md,基于 7 份基金分析师报告(路径:reports/<日期>/fund/<代码>_*.md)构建完整看涨论点并反驳可能的看空观点,输出到 reports/<日期>/fund/<代码>_bull.md。返回核心论点摘要给我。", subagent_type: "general_purpose_task"})

Task({description: "空头辩论", prompt: "你是 bear-researcher(空头研究员)。请读取 agents/bear-researcher.agent.md,基于 7 份基金分析师报告构建完整看跌论点并反驳多头观点,输出到 reports/<日期>/fund/<代码>_bear.md。返回核心论点摘要给我。", subagent_type: "general_purpose_task"})
```

**辩论重点(基金特有)**:
- 多头:强调业绩持续性、经理能力、政策利好、资金稳定
- 空头:强调申赎压力、规模萎缩、重仓股风险、政策利空、情绪周期顶部
- 核心矛盾:政策利好 vs "反弹即赎回"压力、业绩历史 vs 未来可持续性

**轮次**: 默认 1 轮,复杂标的可 2-3 轮(用 Read 工具读取对方论点后反驳)。

---

## Step 4: 研究经理裁决

```
Task({description: "研究经理裁决", prompt: "你是 research-manager(研究经理)。请读取 agents/research-manager.agent.md,基于 7 份分析师报告 + 多空辩论记录输出投资计划:Buy/Overweight/Hold/Underweight/Sell 评级、核心逻辑、战略行动建议、风险提示。保存到 reports/<日期>/fund/<代码>_research_plan.md。", subagent_type: "general_purpose_task"})
```

---

## Step 5: 交易员方案

```
Task({description: "交易员方案", prompt: "你是 trader(交易员)。请读取 agents/trader.agent.md,基于研究计划 + 7 份分析师报告输出交易方案:交易方向(申购/持有/赎回)、具体价位(场内:入场/止损/目标;场外:净值区间)、仓位建议、操作策略(一次性/分批/定投)、风险控制。保存到 reports/<日期>/fund/<代码>_trade_plan.md。", subagent_type: "general_purpose_task"})
```

---

## Step 6: 风控辩论 + 中立裁决

```
Task({description: "激进风控意见", prompt: "你是 aggressive-analyst(激进风控师)。读取 agents/aggressive-analyst.agent.md,基于交易方案 + 研究计划 + 7 份分析师报告给出支持意见,认为风险可控。保存到 reports/<日期>/fund/<代码>_risk_aggressive.md。", subagent_type: "general_purpose_task"})

Task({description: "保守风控意见", prompt: "你是 conservative-analyst(保守风控师)。读取 agents/conservative-analyst.agent.md,基于交易方案 + 研究计划 + 7 份分析师报告给出谨慎意见,强调风险。保存到 reports/<日期>/fund/<代码>_risk_conservative.md。", subagent_type: "general_purpose_task"})
```

然后调度中立风控师裁决:

```
Task({description: "中立风控裁决", prompt: "你是 neutral-analyst(中立风控师)。读取 agents/neutral-analyst.agent.md,综合激进派和保守派意见,给出最终风控审查结论(通过/有条件通过/不通过)和具体参数调整建议。保存到 reports/<日期>/fund/<代码>_risk_neutral.md。", subagent_type: "general_purpose_task"})
```

---

## Step 7: 组合经理最终报告

```
Task({description: "组合经理最终报告", prompt: "你是 portfolio-manager(组合经理)。读取 agents/portfolio-manager.agent.md,综合所有材料(7 份分析师报告 + 辩论记录 + 投资计划 + 交易方案 + 风控报告 + 数据源评估)输出最终投资分析报告:数据源评估、最终评级(强烈推荐买入/推荐买入/谨慎推荐/中性/回避)、建议仓位、核心观点、多维度分析摘要(净值业绩/基本面/重仓股/份额/新闻/政策/情绪)、投资逻辑、具体操作建议(A/C 类选择、分批策略、止损位)、关注要点、免责声明。保存到 reports/<日期>/fund/<代码>_final.md。", subagent_type: "general_purpose_task"})
```

---

## Step 8: HTML 报告生成与保存(主对话执行)

将组合经理的最终 markdown 报告渲染为 HTML,保存到:
- `reports/<日期>/<基金代码>_<基金简称>.html`(如 `reports/2026-06-27/001717_工银前沿医疗股票A.html`)

**HTML 报告必须包含**:
- 投资评级(强烈推荐买入/推荐买入/谨慎推荐/中性/回避)+ 建议仓位
- 数据源评估表
- 核心观点
- 多维度分析摘要(净值业绩/基本面/重仓股/份额/新闻/政策/情绪)
- 投资逻辑(核心利好 + 主要风险)
- 操作建议(申购/持有/赎回,含 A/C 类选择、分批策略、止损位)
- 关注要点
- 免责声明

---

## 📊 单基金工作流总览

```
用户输入 1 只基金
    ↓
[Step 1] 7 基金分析师 subagent 并行 → 7 份报告
    ↓
[Step 2] 主对话收集报告 + 数据源评估
    ↓
[Step 3] 多头 + 空头 subagent 并行辩论
    ↓
[Step 4] research-manager subagent → 投资计划
    ↓
[Step 5] trader subagent → 交易方案
    ↓
[Step 6] 激进 + 保守 风控 subagent 并行 → 中立裁决
    ↓
[Step 7] portfolio-manager subagent → 最终报告
    ↓
[Step 8] 主对话渲染 HTML → 保存
```
