# 组合/持仓工作流 (C) - 通用版

**适用场景**: 用户输入包含"持仓/组合"关键词(持仓/组合/全部持有/我的基金/诊断组合 + 截图/列表),或用户提供截图形式的持仓页面。

**支持三种组合类型**:
- **C-1 全基金组合**: 持仓全部是公募基金(最常见,如支付宝、天天基金持仓截图)
- **C-2 全股票组合**: 持仓全部是 A 股股票(如券商账户持仓截图)
- **C-3 混合组合**: 持仓同时包含基金和股票(如部分券商账户、银行理财账户)

---

## ⚠️ 重要前提

- 组合工作流的输入识别和处理流程与单标的不同,**必须严格按本文件执行**。
- 即使组合只有 1 只标的,只要用了"持仓"等关键词,就按组合工作流跑(只是简化掉"组合层面分析"步骤)。
- 如果组合规模超过 15 只标的,需要在 Step 1 前先做"代表性标的筛选"(选取最大 5 只 + 最差 2 只 + 风险最高 1 只作为深度诊断对象,其余做轻量评估)。

---

## Step 0: 持仓识别 + 类型分流(主对话执行)

**目标**: 从用户输入中提取所有标的,识别每只的类型(基金/股票),把组合分为 {funds, stocks} 两组。

### 0.1 输入形式识别

| 输入形式 | 处理方式 |
|----------|----------|
| 文字列表 | 直接解析,如 "我有 001717 工银前沿医疗 5000 元, 还有 600519 贵州茅台 10000 元" |
| 截图 | 用视觉能力识别图片中的持仓列表(基金名/股票名/金额/占比/收益) |
| 模糊描述 | 询问用户确认标的清单 |

### 1.2 输出格式(完整 JSON,含类型)

提取完成后,主对话必须输出以下 JSON 格式的标的清单(用作后续 subagent 调度的输入):

```json
{
  "funds": [
    {"code": "007466", "name": "华泰柏瑞中证红利低波ETF联接A", "amount": 7920.75, "ratio": 26.07, "holding_return": -632.62, "holding_return_pct": -7.36, "type": "fund"},
    {"code": "015143", "name": "中欧智能制造混合A", "amount": 1779.64, "ratio": 5.86, "holding_return": 422.18, "holding_return_pct": 31.10, "type": "fund"}
  ],
  "stocks": [
    {"code": "600519", "name": "贵州茅台", "amount": 10000, "ratio": 30.0, "holding_return": -500, "holding_return_pct": -5.0, "type": "stock"},
    {"code": "000858", "name": "五粮液", "amount": 8000, "ratio": 24.0, "holding_return": 1200, "holding_return_pct": 15.0, "type": "stock"}
  ],
  "total_amount": 33347,
  "total_return": 489.18,
  "total_return_pct": 1.47
}
```

### 0.3 标的代码确认 + 类型探测

对每个识别出的标的,执行 `python -m data_tools.cli fund detect <代码>`:
- 返回 `FUND|<基金名称>` → 这是**基金**,归入 `funds` 数组
- 返回 `STOCK` → 这是**股票**,归入 `stocks` 数组

### 0.4 组合类型判定

根据 `funds.length` 和 `stocks.length`:

| 类型 | 判定条件 | 工作流分支 |
|------|----------|------------|
| **C-1 全基金组合** | `stocks.length == 0 && funds.length > 0` | 走 Step 4(基金 subagent) |
| **C-2 全股票组合** | `funds.length == 0 && stocks.length > 0` | 走 Step 4(股票 subagent) |
| **C-3 混合组合** | `stocks.length > 0 && funds.length > 0` | 同时走 Step 4(基金 + 股票 subagent) |

### 1.5 总标的数计算

```
total_count = funds.length + stocks.length
```

这个数字决定后续 Step 1 的分批策略。

---

## Step 2: 用户风险偏好采集(组合工作流 C-1 / C-3 必做)⭐ 增强

**目标**: 在跑每只标的前,先拿到用户的"风险等级 / 投资期限 / 偏好品类 / 排除品类",
让后续的组合诊断(Step 6)和候选推荐(Step 10)有据可依。

**执行主体**:**主对话直接执行**,不调用 subagent。

**适用条件**:
- 用户在请求中**未提供**风险等级 / 期限时,必须做 Step 2
- 用户已显式说"我是稳健型"等,仍建议做一次标准化落盘

### 0.5.1 第一步: 从用户文本中解析已知偏好

主对话调用本地 Python 函数尝试从用户输入中提取:

```python
from data_tools.portfolio_prefs import parse_user_prefs_from_text
prefs = parse_user_prefs_from_text(user_text, user_id=user_id)
```

**可识别的关键词**(示例):
- 风险等级: 保守/稳健/平衡/成长/激进 / 低风险/中风险/高风险 / 不能亏/追求高收益
- 投资期限: 短期(<1年) / 中期(1-3年) / 长期(3-5年) / 超长期(5年+)
- 偏好品类: 喜欢医药/新能源/红利/债券 等
- 排除品类: 不碰科技/不买QDII 等

### 0.5.2 第二步: 缺失字段用 AskUserQuestion 反问

关键字段缺失时,主对话用 `AskUserQuestion` 工具一次性反问(最多 3 题):

| 必填字段 | 选项 | 默认值 |
|----------|------|--------|
| **风险等级** | 1保守型 / 2稳健型 / 3平衡型 / 4成长型 / 5激进型 | 3平衡型 |
| **投资期限** | 短期(<1年) / 中期(1-3年) / 长期(3-5年) / 超长期(5年+) | 中期(1-3年) |

**反问规则**:
- 缺失的字段一次性问完(同一 AskUserQuestion 调用中多题)
- 必须给选项,不问开放式问题
- 最多追问 1 轮,用户跳过则用默认值

### 2.3 第三步: 生成目标配置并落盘

收集到完整偏好后,主对话调用 CLI 生成目标资产配置并保存:

```bash
python -m data_tools.cli portfolio prefs --user-id <id> --risk-level <lvl> --horizon <h> \
  --preferred "<cats>" --excluded "<cats>" --equity-override <pct> --save
```

**校验产出**:
- `risk_level ∈ {1,2,3,4,5}`
- `horizon ∈ {short, medium, long, very_long}`
- `target_allocation` 的 9 类权重合计 ∈ [0.99, 1.01]

### 0.5.4 5 档风险等级速查

| 等级 | 名称 | 典型画像 | 目标权益占比 |
|------|------|---------|-------------|
| 1 | 保守型 | 不能亏、存款级 | ≤ 15% |
| 2 | 稳健型 | 低风险、保本为主 | 15-30% |
| 3 | 平衡型 | 中等风险收益 | 30-60% |
| 4 | 成长型 | 中高风险、追求高收益 | 60-80% |
| 5 | 激进型 | 能承受大波动、梭哈 | 80%+ |

### 0.5.5 跳过条件

- 组合 < 3 只标的(轻量评估)且用户已显式说"不需要风险匹配"
- 单只基金分析(走 B 单基金工作流,不需要 Step 0.5)

---

## Step 3: 数据预拉取（主对话执行）

**目标**: 在调度分析师之前，确保组合中所有标的的数据已预拉取完成。

### 3.1 全局数据（只拉1次，所有标的共享）

```bash
python -m data_tools.cli global-news --limit 30
python -m data_tools.cli hot-stocks
python -m data_tools.cli northbound
```

### 3.2 标的独立数据（逐只标的增量拉取）

对每只基金/股票执行增量拉取，参考 workflow-fund.md / workflow-stock.md 的 Step 2 数据拉取清单。

### 3.3 分析师视角

分析师读取 `data/funds/<code>/` 或 `data/stocks/<code>/` 下的已有文件，如发现数据缺失可自行补充拉取。

---

## Step 4: 标的分析师并行（每只标的7个分析师）

**目标**: 对组合中每只标的运行对应的7大分析师并行调研。

### 4.0 调度策略

| 组合类型 | 调度方式 |
|----------|----------|
| C-1 全基金 | 走 Step 4.1,基金标的分批调度 |
| C-2 全股票 | 走 Step 4.2,股票标的分批调度 |
| C-3 混合 | 同时走 Step 4.1 + Step 4.2,**先调度所有基金(一批),再调度所有股票(一批)**,避免一消息太多 subagent |

**分批规则**(以基金为例,股票同):
- 组合 ≤ 5 只: 一次性并行调度所有标的的 7 大分析师 subagent
- 组合 6-15 只: 分 2-3 批并行,每批 3-5 只
- 组合 > 15 只: 先做代表性筛选,只对筛选后的标的跑完整流程

### 4.1 基金 subagent 调度(走 [`workflow-fund.md`](workflow-fund.md))

对每只基金,需要调度的 **7 个基金分析师 subagent**(并行触发):

| # | subagent 角色 | agent 文件 | 读取数据 |
|---|--------------|-----------|----------|
| 1 | 基金市场分析师 | `fund-market-analyst.agent.md` | nav, performance |
| 2 | 基金基本面分析师 | `fund-fundamentals-analyst.agent.md` | info, manager |
| 3 | 基金重仓股分析师 | `fund-holdings-analyst.agent.md` | holdings |
| 4 | 基金份额分析师 | `fund-flows-analyst.agent.md` | flows, info |
| 5 | 基金新闻分析师 | `fund-news-analyst.agent.md` | news, global_news, holdings |
| 6 | 基金政策分析师 | `fund-policy-analyst.agent.md` | info, global_news, news, holdings |
| 7 | 基金情绪分析师 | `fund-sentiment-analyst.agent.md` | news, flows, info, global_news |

**调度模板**(每只基金 7 次 Task 调用,**同一消息内并行**):

```
Task({description: "<基金名> <角色>分析", prompt: "角色: <agent-name>
标的: <code>（<基金名称>）
数据目录: data/funds/<code>/
输出路径: reports/<日期>/fund/<code>_<role>.md

请:
1. 读取 agents/<agent-name>.agent.md 获取角色定义和输出格式
2. 读取数据目录下的相关数据（数据已由主对话预拉取）
3. 完成分析报告并写入输出路径
4. 返回契约格式(summary/detail_path/evidence)", subagent_type: "general_purpose_task"})
```

### 4.2 股票 subagent 调度(走 [`workflow-stock.md`](workflow-stock.md))

对每只股票,需要调度的 **7 个股票分析师 subagent**(并行触发):

| # | subagent 角色 | agent 文件 | 读取数据 |
|---|--------------|-----------|----------|
| 1 | 技术分析师 | `market-analyst.agent.md` | kline, indicator(rsi/macd/boll) |
| 2 | 舆情分析师 | `sentiment-analyst.agent.md` | news, global_news, hot_stocks |
| 3 | 新闻分析师 | `news-analyst.agent.md` | news, global_news, concept |
| 4 | 基本面分析师 | `fundamentals-analyst.agent.md` | fundamentals, income_statement, balance_sheet, cashflow, forecast |
| 5 | 政策分析师 | `policy-analyst.agent.md` | global_news, news, concept |
| 6 | 游资追踪师 | `hot-money-tracker.agent.md` | kline, dragon_tiger, northbound, hot_stocks, concept, insider |
| 7 | 解禁监控师 | `lockup-watcher.agent.md` | lockup, insider, fundamentals, news |

**调度模板**(每只股票 7 次 Task 调用,**同一消息内并行**):

```
Task({description: "<股票名> <角色>分析", prompt: "角色: <agent-name>
标的: <code>（<股票名称>）
数据目录: data/stocks/<code>/
输出路径: reports/<日期>/stock/<code>_<role>.md

请:
1. 读取 agents/<agent-name>.agent.md 获取角色定义和输出格式
2. 读取数据目录下的相关数据（数据已由主对话预拉取）
3. 完成分析报告并写入输出路径
4. 返回契约格式(summary/detail_path/evidence)", subagent_type: "general_purpose_task"})
```

### 4.3 输出归档

每只基金的 subagent 输出报告必须保存到:
- 数据文件: `data/funds/<代码>/`
- 分析报告: `reports/<日期>/fund/<代码>/<角色>.md

每只股票的 subagent 输出报告必须保存到:
- 数据文件: `data/stocks/<代码>/`
- 分析报告: `reports/<日期>/stock/<代码>/<角色>.md`

---

## Step 2: 组合层面分析(主对话收集 subagent 输出后,调度 1 个"组合分析师"subagent)

**目标**: 整合所有单标的报告,做组合层面的诊断。**根据组合类型(C-1/C-2/C-3)自适应不同维度**。

### 5.1 调度模板(通用)

```
Task({description: "组合层面分析", prompt: "你是一位组合分析师(portfolio-analyst),负责整合所有单标的报告做组合层面诊断。

    组合类型:<C-1 全基金 | C-2 全股票 | C-3 混合>
    待分析的标的清单(JSON):
    <标的清单 JSON>
    
    各标的的 subagent 报告位置:
    - 基金: data/funds/<代码>/ + reports/<日期>/fund/<代码>/*.md
    - 股票: data/stocks/<代码>/ + reports/<日期>/stock/<代码>/*.md
    
    请完成以下分析并输出报告:
    
    ## 1. 持仓总览
    - 总市值、总收益、收益率
    - 标的数(funds.length + stocks.length)
    - 现金占比、股票占比(直接持股 + 股票型基金穿透)、债券占比、混合占比
    - 资产类别拆分(基金 vs 股票)
    
    ## 2. <共性维度 - 所有组合类型都必做>
    - 行业/风格暴露矩阵
    - 集中度与风险(前 1/3/5 大占比,单一标的 > 25% 提示,单一行业 > 40% 提示)
    - 相关性结构(标的间风格重复 / 互补)
    - 经理集中度
    
    ## 3. <C-1 全基金专项 - 见 2.2>
    
    ## 4. <C-2 全股票专项 - 见 2.3>
    
    ## 5. <C-3 混合专项 - 见 2.4>
    
    ## 6. 优化建议(分优先级)
    - 优先级 1: 立即清出的标的
    - 优先级 2: 分批减仓的标的
    - 优先级 3: 增量配置的标的
    - 优先级 4: 压舱石加配
    
    ## 7. 目标配置 vs 当前配置对比表
    
    请将完整报告保存到 reports/<日期>/portfolio/portfolio_analysis.md,然后返回核心摘要给我。", subagent_type: "general_purpose_task"})
```

### 2.2 C-1 全基金专项维度(只在 funds.length > 0 且 stocks.length == 0 时输出)

```
## 3. 基金专项分析

### 3.1 申赎压力与清盘风险
- 各基金规模(重点关注 < 2 亿清盘线、< 1 亿预警、< 0.5 亿高危)
- 距清盘线距离
- 高风险基金清单(🔴 必须赎回)
- A/C 类选择: 长期持有(>1年)推荐 C 类,短期持有推荐 A 类

### 3.2 基金特有集中度
- 单一基金占比 > 25% 提示(超纪律线)
- 红利策略占比 > 30% 提示(风格过度集中)
- 主题型基金(医药/新能源/科技)总占比 > 40% 提示

### 3.3 经理依赖
- 经理人数、单一经理依赖
- 任期回报为负的经理(赵蓓式翻车)标记
- 经理刚变更的基金(磨合期风险)

### 3.4 业绩持续性
- 跑赢基准的基金(超 4 个阶段排名"优秀")
- 跑输基准的基金(近 1 年 / 3 年 / 5 年排名"不佳")
- 排名剧烈波动的基金(策略不稳定)
```

### 5.3 C-2 全股票专项维度(只在 stocks.length > 0 且 funds.length == 0 时输出)

```
## 4. 股票专项分析

### 4.1 行业暴露
- 按申万一级行业汇总各股票占比
- 单一行业占比 > 40% 提示(行业过度集中)
- 周期性行业(银行/地产/有色/化工)总占比 > 30% 提示

### 4.2 市值与风格
- 大盘(>1000亿)/ 中盘(300-1000亿)/ 小盘(<300亿)占比
- 价值 / 成长风格拆分(看 PE、PB、ROE)
- 组合整体 Beta 估算(基于个股 Beta 加权)

### 4.3 估值水平
- 组合加权 PE / PB / PS
- 高估值标的(PE > 行业均值 2 倍)清单
- 低估值标的(PE < 行业均值 0.5 倍)清单
- PEG 比率(< 1 为低估)

### 4.4 财报与盈利能力
- 组合加权 ROE / 毛利率 / 净利率
- 财报爆雷风险标的(ST / *ST / 连续亏损)
- 商誉占比 > 30% 的标的(减值风险)

### 4.5 资金面与解禁
- 北向资金近 1 月净流入/流出
- 龙虎榜游资关注度
- 6 个月内解禁压力
- 大股东减持计划
```

### 2.4 C-3 混合专项维度(只在 funds.length > 0 且 stocks.length > 0 时输出)⭐ 核心

```
## 5. 混合组合专项分析

### 5.1 股债平衡
- 直接股票(stocks): x.xx%
- 股票型基金(股票仓位 > 70% 的基金穿透): xx.xx%
- 混合型基金(股票仓位 30-70%): xx.xx%
- 债券型基金 + 货基 + 现金: xx.xx%
- **整体权益类暴露 = 直接股票 + 股票型基金 + 混合型基金 × 50%**
- 评估: 权益占比是否在用户风险偏好内(保守型建议 < 30%,平衡型 30-70%,激进型 > 70%)

### 5.2 跨类别相关性
- 直接股票 vs 股票型基金的相关性(应该高,>0.8)
- 直接股票 vs 混合型基金的相关性(中等,0.5-0.8)
- 直接股票 vs 固收+基金的相关性(应该低,<0.3)
- 重复暴露: 同行业股票 + 同行业基金的占比合计

### 5.3 重复持仓检查(关键)
- 股票型基金的重仓股 vs 直接持有的股票,是否有重叠(双倍下注)
  - 例: 持有 001717 工银前沿医疗(重仓恒瑞医药) + 同时直接持有 600276 恒瑞医药 → 重复暴露
- 重叠标的合计占比 / 单一标的占比 → 是否过度集中

### 5.4 资产类别纪律
- 直接股票 + 股票型基金总占比 > 80% 提示(权益过重)
- 债券 + 现金占比 < 10% 提示(无安全垫)
- 混合型基金占比 < 5% 提示(缺乏过渡资产)

### 5.5 跨类别优化建议
- 用股票型基金替代直接股票(降低个股风险,提高分散度)
- 用混合型基金做"压舱石"(降低组合波动)
- 用固收+基金替代部分现金(提升收益)
```

### 5.5 Step 5 输出归档

- 数据: 由 subagent 在 analysis 中引用
- 报告: `reports/<日期>/portfolio/portfolio_analysis.md`

---

## Step 6: Gap 分析(C-1 / C-3 必做)⭐ 增强

**目标**: 把 Step 5 输出的"组合层诊断"和 Step 2 输出的"用户目标配置"对齐,算出每个
资产大类的 gap,并标记需要加仓 / 减仓的品类。**为 Step 10 的"自动补/换基金"提供输入**。

**前提**: 已完成 Step 0.5,`data/portfolios/<user_id>/prefs.json` 已落盘。

### 2.6.1 持仓分类 + 算当前配置

主对话用本地规则把每只持仓归到 9 类资产大类(cash / bond / conservative / balanced / equity / index / sector / overseas / alternative):

```python
from data_tools.portfolio_rebalance import (
    classify_positions, compute_current_allocation, compute_gap,
)
from data_tools.portfolio_prefs import load_user_prefs, get_target_allocation

positions = classify_positions(holdings)
current_alloc = compute_current_allocation(positions)
prefs = load_user_prefs(user_id)
target_alloc = get_target_allocation(prefs)
```

### 6.2 算 gap(主对话可内联完成,不调 subagent)

```python
current, gaps, underweight, overweight = compute_gap(positions, target_alloc)
# gaps: list[GapItem] 含 9 类(0 权重的类也保留)
# underweight: 需要加仓的品类列表(delta > 3%)
# overweight: 需要减仓的品类列表(delta < -3%)
```

### 6.3 输出 gap 报告(主对话渲染,不需要 subagent)

`reports/<日期>/portfolio/portfolio_gap.md`,**必含**:

1. 偏好与目标配置块
2. 当前 vs 目标权重对比表
3. 调整金额表(按当前总市值算)
4. **underweight 清单** + **overweight 清单**
5. 调整后目标配置(示意)

### 2.6.4 跳过条件

- 用户明确说"不需要调整 / 只看诊断"
- Step 0.5 未跑(没有 prefs.json)

---

## Step 3: 多空辩论(可选,组合 > 5 只时强烈建议)

对组合整体做 1 轮多空辩论:

- **多头 subagent (bull-researcher)**: 强调组合的 alpha 来源(如万家中证1000增强、中欧智能制造、贵州茅台)、压舱石稳定性
- **空头 subagent (bear-researcher)**: 强调集中度风险、清盘风险、风格漂移、宏观系统性风险

如果组合 < 5 只且没有明显冲突,可跳过辩论。

**调度**:
```
Task({description: "组合多头辩论", prompt: "你是 bull-researcher(多头研究员)。读取 agents/bull-researcher.agent.md,基于 portfolio_analysis.md 报告构建组合整体的看涨论点并反驳可能的看空观点。保存到 reports/<日期>/portfolio/portfolio_bull.md。", subagent_type: "general_purpose_task"})

Task({description: "组合空头辩论", prompt: "你是 bear-researcher(空头研究员)。读取 agents/bear-researcher.agent.md,基于 portfolio_analysis.md 报告构建组合整体的看跌论点并反驳多头观点。保存到 reports/<日期>/portfolio/portfolio_bear.md。", subagent_type: "general_purpose_task"})
```

---

## Step 8: 研究经理裁决 → 投资计划

调用 `research-manager` subagent(general_purpose_task),传入组合分析师报告 + 多空辩论记录,输出整体投资计划(战略再平衡 vs 维持现状 vs 大幅调整):

```
Task({description: "组合研究经理裁决", prompt: "你是 research-manager(研究经理)。读取 agents/research-manager.agent.md,基于组合分析报告 + 多空辩论记录输出整体投资计划:整体评级(战略再平衡 / 维持现状 / 大幅调整)、核心逻辑、多空评估、战略行动建议、风险提示。保存到 reports/<日期>/portfolio/portfolio_research_plan.md。", subagent_type: "general_purpose_task"})
```

---

## Step 5: 交易员方案

调用 `trader` subagent,将组合投资计划转化为具体交易方案:

```
Task({description: "组合交易员方案", prompt: "你是 trader(交易员)。读取 agents/trader.agent.md,基于研究计划 + 组合分析报告输出组合调整的具体交易方案:每只标的的交易方向(申购/赎回/持有/买入/卖出)、具体价位/净值区间、仓位调整比例、分批策略、时间窗口、风险控制。保存到 reports/<日期>/portfolio/portfolio_trade_plan.md。", subagent_type: "general_purpose_task"})
```

---

## Step 5.5: 候选基金深度推荐(增强版)⭐ 核心改造

**目标**: 在 screener Top-5 基础上,为每只候选跑 7 大基金分析师 + 1 轮类内多空辩论,
用 `parse_quality_from_reports()` 规则化生成质量分,与原 _score_fund 名称分按 3:7 融合,
输出"质量分 + 推荐理由"双重信号的 `portfolio_fund_recommendations.md`。

**Spec**: `docs/superpowers/specs/2026-06-29-fund-recommender-deep-design.md`

**触发条件**: 总是触发(underweight 非空 + `_meta/fund_list.json` 存在)。

**调度成本**:
- 单类 underweight: 35(7 分析师 × 5) + 2(辩论) = 37 subagent
- 5 类 underweight: 5 × 37 = 185 subagent,约 3-5 分钟

### 5.5.1 主对话预生成候选列表

```python
from data_tools.portfolio_rebalance import screen_replacement_funds
candidates_by_cat = screen_replacement_funds(
    categories=underweight,
    prefs=prefs,
    per_category=5,
)
candidates_by_cat = {cat: [c.to_dict() for c in cands] for cat, cands in candidates_by_cat.items()}
```

### 5.5.2 调度 fund-recommender subagent

```
Task({
  description: "候选基金深度推荐",
  prompt: "你是 fund-recommender(增强版)。读取 agents/fund-recommender.agent.md。

    输入(JSON 字符串):
    {
      'date_str': '<日期>',
      'candidates_by_cat': <candidates_by_cat JSON>,
      'prefs_path': 'data/portfolios/<id>/prefs.json',
      'gap_report_path': 'reports/<日期>/portfolio/portfolio_gap.md',
      'universe_path': 'data/funds/_meta/fund_list.json',
      'output_path': 'reports/<日期>/portfolio/portfolio_fund_recommendations.md'
    }

    任务:
    1. 读取 prefs + gap_report
    2. 按 agent.md Step B 并行调度 7 分析师(每类 5 只,同消息内)
    3. 按 agent.md Step C 调度 1 轮类内多空辩论
    4. 按 agent.md Step D 调 quality-score CLI 收集 quality_reports
    5. 按 agent.md Step E 调 score_with_quality_reports 融合
    6. 按 agent.md Step F 写出 portfolio_fund_recommendations.md
    7. 返回契约(≤ 2k tokens)
  ",
  subagent_type: "general_purpose_task"
})
```

### 5.5.3 主对话校验产出

- 必校验项:
  - `recommendations` 列表非空
  - 每只候选含 `score / name_score / quality_score / quality_signals / report_paths`
  - `final_score` ∈ [0, 100]
  - 7 报告路径全部存在或标 `quality_missing=true`
- 校验失败则重跑或追加 fallback 提示。

### 5.5.4 报告路径

- 候选基金 7 报告: `reports/<日期>/fund/candidate/<code>_<role>.md`
- 类内辩论: `reports/<日期>/fund/candidate/<cat>_<bull|bear>.md`
- 推荐汇总: `reports/<日期>/portfolio/portfolio_fund_recommendations.md`

### 5.5.5 与后续步骤的衔接

- Step 6 (风控): 必须引用推荐汇总,审查替换标的风险
- Step 7 (组合经理): 必须读推荐汇总,新增"推荐补/换基金的深度评估"章节
- Step 8 (HTML 渲染): 必须渲染"质量分组成表"和"深度报告路径表"

### 5.5.6 降级路径(部分失败不阻塞)

- 单只候选 7 报告全失败 → 用 name_score 兜底,标 `quality_missing=true`
- 单只候选 1-2 维度失败 → 该维度权重归零,其他等比放大,标 [质量分缺失维度:xxx]
- 某类 bull/bear 失败 → 标 [辩论缺失:bull.md 未生成],不影响 parse_quality 评分
- 整类 screener 失败 → 该类跳过,标 [本类无候选:xxx]
- fund_list.json 不存在 → 整个 Step 5.5 跳过,portfolio_final 标 [Step 5.5 未触发:fund_list.json 不存在]

---

## Step 6: 风控辩论 + 中立裁决

```
Task({description: "激进风控意见", prompt: "你是 aggressive-analyst(激进风控师)。读取 agents/aggressive-analyst.agent.md,基于交易方案 + 研究计划 + 组合分析报告给出支持意见,认为风险可控。保存到 reports/<日期>/portfolio/portfolio_risk_aggressive.md。", subagent_type: "general_purpose_task"})

Task({description: "保守风控意见", prompt: "你是 conservative-analyst(保守风控师)。读取 agents/conservative-analyst.agent.md,基于交易方案 + 研究计划 + 组合分析报告给出谨慎意见,强调风险。保存到 reports/<日期>/portfolio/portfolio_risk_conservative.md。", subagent_type: "general_purpose_task"})

Task({description: "中立风控裁决", prompt: "你是 neutral-analyst(中立风控师)。读取 agents/neutral-analyst.agent.md,综合激进派和保守派意见,给出最终风控审查结论(通过/有条件通过/不通过)和具体参数调整建议。保存到 reports/<日期>/portfolio/portfolio_risk_neutral.md。", subagent_type: "general_purpose_task"})
```

---

## Step 7: 组合经理最终报告

调用 `portfolio-manager` subagent,输出最终组合诊断报告(markdown 格式):

```
Task({description: "组合经理最终报告", prompt: "你是 portfolio-manager(组合经理)。读取 agents/portfolio-manager.agent.md,综合所有材料(组合分析报告 + 多空辩论 + 研究计划 + 交易方案 + 风控报告)输出最终组合诊断报告:数据源评估、组合整体评级、调整方向、核心观点、多维度分析摘要(根据组合类型 C-1/C-2/C-3 选择对应维度)、投资逻辑、具体操作建议(分标的)、关注要点、免责声明。保存到 reports/<日期>/portfolio/portfolio_final.md。", subagent_type: "general_purpose_task"})
```

---

## Step 13: HTML 报告生成与保存(主对话执行)

**这一步主对话执行,不调用 subagent。**

将组合经理的 markdown 报告渲染为 HTML。

保存路径: `reports/<日期>/portfolio_<日期>.html`

文件命名: `portfolio_<日期>.html`(如 `portfolio_2026-06-27.html`)

**HTML 报告必须包含**:
- 持仓总览表(代码/名称/类型/金额/占比/收益/评级)
- 数据源评估表
- **根据组合类型自适应的维度**(C-1 基金专项 / C-2 股票专项 / C-3 混合专项)
- 集中度分析
- 相关性结构
- 操作建议(分优先级)
- 调整后目标配置对比
- 关注要点
- 免责声明
- **C-1 / C-3 增强模块**(由 Step 2 / 6 / 10 产出):
  - **用户偏好与目标配置**(`data/portfolios/<id>/prefs.json`)
  - **资产 gap 矩阵**(当前 vs 目标权重 + 调整金额)
  - **推荐补/换基金清单**(从 `portfolio_fund_recommendations.md`)
  - **调整后目标配置对比表**(当前 vs 推荐后)

---

## 📊 组合工作流总览

```
用户输入"分析持仓"或截图
    ↓
[Step 1] 主对话识别所有标的(代码+名称+金额+占比+收益)
        ↓
        [1.3] 用 fund detect 确认每只标的类型
        ↓
        [1.4] 分流为 {funds, stocks} → 组合类型 C-1 / C-2 / C-3
    ↓
[Step 2] ⭐ C-1/C-3 增强: 主对话直接采集(文本解析 + AskUserQuestion) → prefs.json
    ↓
[Step 3] 主对话智能增量拉取数据(global_news/hot_stocks/northbound + 各标的独立数据)
    ↓
[Step 4] 按类型分批调度 subagent:
        - 基金 → 7 基金分析师 subagent(并行,分批)
        - 股票 → 7 股票分析师 subagent(并行,分批)
    ↓
[Step 5] 调度 1 个组合分析师 subagent 做组合层面诊断(自适应 C-1/C-2/C-3 维度)
    ↓
[Step 6] ⭐ C-1/C-3 增强: 主对话内联算 gap(当前 vs 目标) → portfolio_gap.md
    ↓
[Step 7] (可选) 多空辩论(bull + bear subagent 并行)
    ↓
[Step 8] research-manager subagent → 投资计划
    ↓
[Step 9] trader subagent → 交易方案
    ↓
[Step 10] ⭐ C-1/C-3 增强: fund-recommender subagent → portfolio_fund_recommendations.md
        (从国内场外公募基金全量库自动筛选补/换候选)
    ↓
[Step 11] 风控辩论 + 中立裁决(3 个 subagent)
    ↓
[Step 12] portfolio-manager subagent → 最终报告
    ↓
[Step 13] 主对话渲染 HTML → 保存 reports/<日期>/portfolio_<日期>.html
        (C-1/C-3 增强:新增"用户偏好 / 资产 gap / 推荐补/换 / 调整后配置"模块)
    ↓
向用户报告路径 + 核心结论
```

---

## 📋 三种组合类型对照表

| 维度 | C-1 全基金 | C-2 全股票 | C-3 混合 |
|------|------------|------------|----------|
| **典型场景** | 支付宝/天天基金持仓 | 券商账户持仓 | 部分券商 + 银行理财 |
| **Step 1 类型探测** | fund detect 全返回 FUND | fund detect 全返回 STOCK | 都有 |
| **Step 4 subagent 调度** | 只调 7 基金分析师 | 只调 7 股票分析师 | 两者都调,分两批 |
| **Step 5 专项维度** | 清盘风险 / 申赎 / 经理依赖 | 行业 / 市值 / 估值 / 财报 / 解禁 | **股债平衡 / 跨类别相关性 / 重复持仓检查** |
| **Step 5 必查纪律** | 单一基金 > 25% / 单一行业 > 40% / 经理集中 | 单一股票 > 20% / 单一行业 > 30% / 财报爆雷 | 权益占比 / 跨类别相关性 / 重复暴露 |
| **Step 13 HTML 专项模块** | 清盘风险表 / 经理表 | 行业表 / 估值表 / 解禁表 | **股债饼图 / 重复持仓清单** |

---

## ⚠️ 易错点提醒

1. **不要把组合工作流简化为"主对话直接读数据写报告"** — 必须走 subagent 流程。
2. **不要每只标的都串行跑完整辩论流程** — 单只标的只跑 7 分析师,辩论在组合层面做 1 次。
3. **不要忽略"标的类型分流"** — Step 1.3 必须用 `fund detect` 探测每只标的类型,不要假设。
4. **不要遗漏混合组合的重复持仓检查** — 这是 C-3 特有的核心风险维度。
5. **不要遗漏清盘风险分析** — 这是基金(C-1 和 C-3)特有的核心风险维度。
6. **不要遗漏"集中度纪律"** — 单一标的 > 25%、单一行业 > 40% 必须提示。
7. **Step 13 HTML 不可跳过** — 必须在所有 subagent 完成后立即渲染保存。
