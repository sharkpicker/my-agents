# 架构图

## 三层架构

```
┌─────────────────────────────────────────┐
│  Skill 层 (.trae/skills/stock-analysis/)  │
│  - SKILL.md(铁律 + 工作流定义)             │
│  - subagent-contract.md(subagent 契约)     │
│  - role-prompts/(26 角色模板)             │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  Agent 层 (agents/)                     │
│  - 22 个老 agent(.agent.md, TRAE IDE)    │
│  - 4 个新 agent(.md, workflow 层)         │
│    ├─ input_router                       │
│    ├─ data_quality_auditor               │
│    ├─ portfolio_analyst                  │
│    └─ html_renderer                      │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  Data Tools 层 (data_tools/)            │
│  - detect.py(输入类型识别)                │
│  - portfolio.py(HHI/overlap/balance)     │
│  - stock_data.py + fund_data.py(原有)    │
│  - template_renderer.py(Jinja2)          │
│  - cli.py(argparse + click 双层)          │
└─────────────────────────────────────────┘
```

## 数据流(单股票 A 工作流)

```
用户输入 "000001"
    ↓
Step 0: input_router → detect.py → type=A
    ↓
Step 1: 7 角色并行(market/sentiment/.../lockup)
    ↓
Step 2: data_quality_auditor → 审计 N 份报告
    ↓
Step 3: bull + bear 并行辩论
    ↓
Step 4: research_manager → 综合评级
    ↓
Step 5: trader → 交易方案
    ↓
Step 6: aggressive + conservative + neutral 并行
    ↓
Step 7: portfolio_manager → 最终 markdown
    ↓
Step 8: html_renderer → Jinja2 渲染 → HTML 文件
```

## 五种分析场景

| 类型 | 触发 | subagent 数 | 输出 |
|------|------|------------|------|
| A 单股票 | 6 位股票代码 / 股票名称 | 7 | `reports/<日期>/stock/<代码>_<简称>.html` |
| B 单基金 | 6 位基金代码 / 基金名称 | 7 | `reports/<日期>/fund/<代码>_<简称>.html` |
| C-1 多基金组合 | 持仓列表(全基金) | N × 7 | `reports/<日期>/portfolio_fund_<日期>.html` |
| C-2 多股票组合 | 持仓列表(全股票) | N × 7 | `reports/<日期>/portfolio_stock_<日期>.html` |
| C-3 混合组合 | 持仓列表(基金+股票) | N × 7 × 2 | `reports/<日期>/portfolio_mixed_<日期>.html` |