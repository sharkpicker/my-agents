# 26 份角色预设 Prompt 模板使用指南

## 总览

26 个模板分布在 5 个子目录:

| 目录 | 数量 | 角色 | 用于场景 |
|------|------|------|---------|
| `role-prompts/stock/` | 7 | market / sentiment / news / fundamentals / policy / hot_money / lockup | A, C-2, C-3(股票部分) |
| `role-prompts/fund/` | 7 | fund_market / fund_fundamentals / holdings / flows / fund_news / fund_policy / fund_sentiment | B, C-1, C-3(基金部分) |
| `role-prompts/decision/` | 5 | bull / bear / research_manager / trader / portfolio_manager | 所有场景 |
| `role-prompts/risk/` | 3 | aggressive / conservative / neutral | 所有场景 |
| `role-prompts/portfolio/` | 4 | input_router / data_quality_auditor / portfolio_analyst / html_renderer | 跨场景 |

## 使用方式

主对话读取模板 → 注入占位符 → 通过 Task 工具调度 subagent。

```python
template = read_prompt("stock/market-analyst.md")
prompt = template.format(
    code="000001",
    name="平安银行",
    date="2026-06-27",
    output_dir="reports/2026-06-27/stock",
)
result = Task(subagent_type="general_purpose_task", prompt=prompt)
```

## 占位符规范

| 占位符 | 含义 | 示例 |
|--------|------|------|
| `{code}` | 标的代码 | 000001 / 001717 |
| `{name}` | 标的名称 | 平安银行 |
| `{date}` | 数据快照日期 | 2026-06-27 |
| `{output_dir}` | 报告输出目录 | reports/2026-06-27/stock |
| `{reports_dir}` | 多份报告目录 | reports/2026-06-27 |
| `{output_path}` | 单文件输出路径 | reports/2026-06-27/_audit/quality_audit.md |
| `{positions_json}` | 持仓列表 JSON | [...] |
| `{user_input}` | 用户原始输入 | 分析平安银行 |
| `{markdown_path}` | markdown 源文件 | reports/2026-06-27/stock/000001_pm.md |
| `{template}` | 模板名 | stock / fund / portfolio |
| `{output_html}` | HTML 输出路径 | reports/2026-06-27/stock/000001.html |