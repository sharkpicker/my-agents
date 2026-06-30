# 工作流优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保证分析精度不变的前提下，通过智能增量拉取、流程精简、Prompt优化，实现Token消耗减少50-70%、调度次数减少50%。

**Architecture:** 
- Phase 1: 数据预拉取（智能增量拉取，主对话先检查本地+增量拉取）
- Phase 2: 组合流程精简（每只标的只跑7分析师，研判上移到组合层面）
- Phase 3: Prompt精简（角色收归agent.md，调用只传必要参数）
- Phase 4: Step编号重命名（按阶段分组，方案A）

**Tech Stack:** Markdown文档编辑（workflow/*.md, SKILL.md, agents-roster.md）

---

## 文件影响范围

| 文件 | 改动内容 | 优先级 |
|------|---------|--------|
| `.trae/skills/stock-analysis/SKILL.md` | 更新铁律、Step编号、引用 | P0 |
| `.trae/skills/stock-analysis/workflow-stock.md` | 新编号+数据预拉取+Prompt精简 | P0 |
| `.trae/skills/stock-analysis/workflow-fund.md` | 新编号+数据预拉取+Prompt精简 | P0 |
| `.trae/skills/stock-analysis/workflow-portfolio.md` | 新编号+数据预拉取+流程精简+Prompt精简 | P0 |
| `.trae/skills/stock-analysis/agents-roster.md` | 更新Step引用 | P1 |

---

## Phase 1: 数据预拉取 + Prompt精简

### Task 1: 更新 SKILL.md 铁律

**Files:**
- Modify: `.trae/skills/stock-analysis/SKILL.md`

**Changes:**
- 铁律6: 更新为"智能增量拉取"模式（主对话检查本地+增量拉取）
- 铁律8（新增）: Prompt精简规范（调用只传必要参数，角色定义收归agent.md）

- [ ] **Step 1: 更新铁律6**

原铁律6：
```
### 铁律 6:数据先保存后读取
- 所有 subagent 拉取的数据必须先通过 `run_command` 调用 `data_tools.cli` 命令保存到 `data/` 目录...
```

更新为：
```
### 铁律 6:智能增量拉取
- 主对话在调度分析师之前，检查本地已有数据文件是否满足时效性要求
- 如数据不足或过期，主对话通过 `run_command` 增量拉取缺失数据
- 数据时效性规则：
  - K线/净值: 近2年/1年内
  - 新闻: 近3个月内
  - global_news/hot_stocks/northbound: 24小时内
  - 基本面/基金信息: 7天内
- 分析师直接读取本地已有文件，如发现数据缺失可自行补充拉取（回退机制）
```

- [ ] **Step 2: 新增铁律8（Prompt精简）**

```
### 铁律 8:Prompt精简规范
- Subagent调用prompt只传必要参数，不重复角色定义
- 调用模板：
  ```
  角色: <agent-name>
  标的: <code>（<name>）
  数据目录: data/funds/<code>/
  输出路径: reports/<日期>/fund/<code>_<role>.md
  
  请:
  1. 读取 agents/<agent-name>.agent.md 获取角色定义和输出格式
  2. 读取数据目录下的相关数据
  3. 完成分析/研判并写入输出路径
  4. 返回契约格式(summary/detail_path/evidence)
  ```
```

- [ ] **Step 3: Commit**

```bash
git add .trae/skills/stock-analysis/SKILL.md
git commit -m "docs: 更新SKILL.md铁律(数据预拉取+Prompt精简)"
```

---

### Task 2: 更新 workflow-fund.md

**Files:**
- Modify: `.trae/skills/stock-analysis/workflow-fund.md`

- [ ] **Step 1: 更新Step编号（单基金工作流）**

旧编号 → 新编号：
- Step 1: 7大分析师 → Step 3: 7大分析师并行调研（新增Step 2数据预拉取）
- Step 2: 质量门控 → Step 4: 质量门控与数据源评估
- Step 3: 多空辩论 → Step 5: 多空辩论
- Step 4: 研究经理 → Step 6: 研究经理裁决
- Step 5: 交易员 → Step 7: 交易员方案
- Step 6: 风控辩论 → Step 8: 风控辩论与中立裁决
- Step 7: 组合经理 → Step 9: 组合经理最终报告
- Step 8: HTML报告 → Step 10: HTML报告生成与保存

- [ ] **Step 2: 新增Step 2（数据预拉取）**

在Step 1之前新增：

```
## Step 2: 数据预拉取（主对话执行）

**目标**: 在调度分析师之前，确保本地有满足时效性要求的数据。

### 2.1 增量拉取判断

| 数据类型 | 有效期限 | 判断依据 |
|---------|---------|---------|
| 基金净值(nav) | 近1年 | 文件内日期范围 |
| 基金业绩(performance) | 7天 | 文件修改时间 |
| 基金概况(info) | 7天 | 文件修改时间 |
| 基金经理(manager) | 7天 | 文件修改时间 |
| 基金重仓股(holdings) | 7天 | 文件修改时间 |
| 基金份额(flows) | 7天 | 文件修改时间 |
| 基金新闻(news) | 近3个月 | 文件内日期范围 |
| 全球财经新闻(global_news) | 24小时 | 文件修改时间 |

### 2.2 增量拉取执行

主对话执行以下命令（只拉缺失/过期的）：

```bash
# 检查并增量拉取基金数据
python -m data_tools.cli fund nav <code> --start <近1年起> --end <今天>
python -m data_tools.cli fund performance <code>
python -m data_tools.cli fund info <code>
python -m data_tools.cli fund manager <code>
python -m data_tools.cli fund holdings <code>
python -m data_tools.cli fund flows <code>
python -m data_tools.cli fund news <code> --start <近3月前> --end <今天>
python -m data_tools.cli fund global-news <code> --limit 30
```

### 2.3 分析师视角

分析师读取 `data/funds/<code>/` 下的已有文件，如发现数据缺失可自行补充拉取。
```

- [ ] **Step 3: 更新Step 1（Prompt精简）**

原Prompt模板：
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

更新为：
```
Task({
  description: "<基金名> <角色>分析",
  prompt: "角色: <agent-name>
标的: <code>（<基金名称>）
数据目录: data/funds/<code>/
输出路径: reports/<日期>/fund/<code>_<role>.md

请:
1. 读取 agents/<agent-name>.agent.md 获取角色定义和输出格式
2. 读取数据目录下的相关数据（数据已由主对话预拉取）
3. 完成分析报告并写入输出路径
4. 返回契约格式(summary/detail_path/evidence)",
  subagent_type: "general_purpose_task"
})
```

- [ ] **Step 4: Commit**

```bash
git add .trae/skills/stock-analysis/workflow-fund.md
git commit -m "docs: 更新workflow-fund.md(新编号+数据预拉取+Prompt精简)"
```

---

### Task 3: 更新 workflow-stock.md

**Files:**
- Modify: `.trae/skills/stock-analysis/workflow-stock.md`

- [ ] **Step 1: 更新Step编号（单股票工作流）**

新编号与单基金一致，共10步。

- [ ] **Step 2: 新增Step 2（数据预拉取）**

```
## Step 2: 数据预拉取（主对话执行）

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
```

- [ ] **Step 3: 更新Step 1（Prompt精简）**

Prompt模板与单基金一致，替换为股票相关参数。

- [ ] **Step 4: Commit**

```bash
git add .trae/skills/stock-analysis/workflow-stock.md
git commit -m "docs: 更新workflow-stock.md(新编号+数据预拉取+Prompt精简)"
```

---

### Task 4: 更新 agents-roster.md

**Files:**
- Modify: `.trae/skills/stock-analysis/agents-roster.md`

- [ ] **Step 1: 更新Step引用**

将所有旧Step编号引用更新为新编号。

- [ ] **Step 2: Commit**

```bash
git add .trae/skills/stock-analysis/agents-roster.md
git commit -m "docs: 更新agents-roster.md(Step编号)"
```

---

## Phase 2: 组合流程精简

### Task 5: 更新 workflow-portfolio.md（核心改动）

**Files:**
- Modify: `.trae/skills/stock-analysis/workflow-portfolio.md`

- [ ] **Step 1: 删除Step 1.3（单标的研判）**

删除以下内容：
- 原 Step 1.3 "单标的 subagent 后续流程(Step 3-7)"
- 原 Step 1.4 "代表性筛选"

这些内容不再需要在每只标的层面执行，改为在组合层面统一执行。

- [ ] **Step 2: 更新Step编号（组合工作流）**

旧编号 → 新编号：
- Step 0 → Step 1: 持仓识别与类型分流
- Step 0.5 → Step 2: 用户风险偏好采集
- Step 1 → Step 3-4: 数据预拉取 + 标的分析师并行（拆分）
- Step 1.1/1.2 → 合并到 Step 4
- Step 1.3 → **删除**（精简）
- Step 2 → Step 5: 组合层面诊断
- Step 2.6 → Step 6: Gap分析
- Step 3 → Step 7: 多空辩论
- Step 4 → Step 8: 研究经理裁决
- Step 5 → Step 9: 交易员方案
- Step 5.5 → Step 10: 候选基金推荐
- Step 6 → Step 11: 风控审查
- Step 7 → Step 12: 组合经理最终报告
- Step 8 → Step 13: HTML报告生成

- [ ] **Step 3: 新增Step 3（数据预拉取）**

与单基金/单股票一致，但组合场景支持批量预拉取：

```
## Step 3: 数据预拉取（主对话执行）

### 3.1 全局数据（只拉1次）

```bash
python -m data_tools.cli global-news --limit 30
python -m data_tools.cli hot-stocks
python -m data_tools.cli northbound
```

### 3.2 标的独立数据（逐只拉取）

对每只基金/股票执行增量拉取，逻辑同单基金/单股票。
```

- [ ] **Step 4: 更新Step 4（Prompt精简）**

分析师调用模板与单基金一致，移除数据拉取命令。

- [ ] **Step 5: 更新组合层面研判（Step 7-12）**

明确组合层面的研判输入：读取所有标的的分析师报告（`reports/<日期>/fund/<code>_*.md`）。

- [ ] **Step 6: Commit**

```bash
git add .trae/skills/stock-analysis/workflow-portfolio.md
git commit -m "docs: 更新workflow-portfolio.md(流程精简+新编号+数据预拉取)"
```

---

## Phase 3: Step编号重命名（SKILL.md引用更新）

### Task 6: 更新 SKILL.md 的工作流引用

**Files:**
- Modify: `.trae/skills/stock-analysis/SKILL.md`

- [ ] **Step 1: 更新所有Step引用**

将SKILL.md中所有旧Step编号引用更新为新编号。

- [ ] **Step 2: 更新工作流总览图**

更新"三套工作流"部分的编号说明。

- [ ] **Step 3: Commit**

```bash
git add .trae/skills/stock-analysis/SKILL.md
git commit -m "docs: 更新SKILL.md工作流编号引用"
```

---

## Phase 4: Step 5.5 适配优化

### Task 7: 更新 fund-recommender.agent.md

**Files:**
- Modify: `agents/fund-recommender.agent.md`

- [ ] **Step 1: 在Step B增加数据预拉取**

候选基金分析师调度前，先批量预拉取候选基金数据。

- [ ] **Step 2: Commit**

```bash
git add agents/fund-recommender.agent.md
git commit -m "docs: 更新fund-recommender.md(数据预拉取)"
```

---

## 验收测试

### 测试清单

- [ ] **单基金测试**: 运行 `python -m data_tools.cli fund performance 001717`，确认数据拉取正常
- [ ] **单股票测试**: 运行 `python -m data_tools.cli kline 000001 --start 2024-06-29 --end 2026-06-29`，确认数据拉取正常
- [ ] **文档一致性**: 检查SKILL.md、工作流文档、agents-roster.md的Step编号引用是否一致
- [ ] **Prompt精简验证**: 检查workflow文档中的subagent调用模板是否符合精简规范
- [ ] **组合流程验证**: 对比新旧workflow-portfolio.md，确认Step 1.3已删除

---

## 回退计划

如实施过程中发现问题，可按以下顺序回退：

1. **Phase 4 回退**: 恢复fund-recommender.agent.md
2. **Phase 3 回退**: 恢复SKILL.md引用
3. **Phase 2 回退**: 恢复workflow-portfolio.md
4. **Phase 1 回退**: 恢复workflow-fund.md/workflow-stock.md/SKILL.md铁律

---

## 实施顺序

1. Task 1 → Task 2 → Task 3 → Task 4（Phase 1）
2. Task 5（Phase 2）
3. Task 6（Phase 3）
4. Task 7（Phase 4）

建议按顺序执行，每完成一个Phase后运行验收测试。
