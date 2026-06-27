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