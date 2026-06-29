# fund-recommender 增强版设计(深度推荐)

> 日期:2026-06-29
> 状态:待用户审查
> 主题:把单只基金工作流(7 大分析师 + 1 轮多空辩论)接入 Step 5.5 候选基金推荐,替换原"二次硬过滤",输出"质量分 + 推荐理由"双重信号

## 1. 背景与目标

### 1.1 现状

- 组合工作流 Step 5.5 由 [fund-recommender.agent.md](file:///d:/01_coding/my_agents/agents/fund-recommender.agent.md) 实现,当前**只做"名称关键词匹配 + 评分 + 4 条硬过滤"**。
- 评分函数 [_score_fund()](file:///d:/01_coding/my_agents/data_tools/portfolio_rebalance.py#L214-L273) 仅依据基金名称 / ftype 字段打分,**未看业绩、规模、重仓股、申赎、经理等核心维度**。
- 二次硬过滤规则(在 fund-recommender.agent.md 第 46-48 行)只有 4 条:规模 > 5000 万、持有期 ≥ 1 年(长期用户)、排除已持有 / 显式排除、is_offexchange=True。
- 4 条硬规则不构成"质量判断",**只构成"合规判断"**。
- 候选基金是否"业绩持续好 / 经理稳定 / 集中度合理 / 没踩雷",**完全没看**。

### 1.2 目标

把单只基金工作流 [workflow-fund.md](file:///d:/01_coding/my_agents/.trae/skills/stock-analysis/workflow-fund.md) 的 7 大分析师 + 1 轮多空辩论**标准化接入 Step 5.5**,作为候选基金推荐的"深度层":

- 对每个 underweight 类别,跑 screener Top-5 候选
- 对每只候选跑完整 7 分析师(35 subagent/类)
- 对每个类别跑 1 轮多空辩论(2 subagent/类),输出"类内最优 + 理由"
- 解析 7 报告 + 辩论 → 0-100 质量分(纯规则)
- 与原 _score_fund 名称分按 3:7 融合
- 输出"质量分 + 推荐理由"双重信号的 `portfolio_fund_recommendations.md`

### 1.3 非目标

- 不跑 Step 5 之后的 research-manager / trader / 风控 3 人 / portfolio-manager(那是组合层的事)。
- 不动 workflow-fund.md 主流程(只读 Step 1 的契约,不复用 Step 2-7)。
- 不引入新的 LLM 评分 subagent(评分 100% 规则化,保证可单测)。
- 不动现有 _score_fund / screen_replacement_funds 的对外签名(只新增函数)。
- 不强制要求"每类必须 Top-5 全部成功",允许部分失败(降级策略见 §5.3)。

### 1.4 关键决策(用户已确认)

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 深度级别 | **标准**:7 分析师 + 1 轮辩论 | 平衡质量与成本 |
| 2 | 覆盖范围 | **每类 Top-5** | 与现有 per_category 对齐,5 类 ≈ 25 只 |
| 3 | 辩论粒度 | **每类 1 轮**(对 5 只做类内对比) | 5 类 × 2 = 10 辩论 subagent,成本可控 |
| 4 | 评分融合 | **纯规则抽取 + 辩论给理由** | 可单测、可复现 |
| 5 | 触发条件 | **总是触发** | 逻辑简单,小 gap 走快路径(见 §5.4) |
| 6 | 降级 | **部分失败 → 跳过 + 标注** | 鲁棒优先 |
| 7 | 下游衔接 | **深度嵌入 portfolio-manager** | HTML 报告新增"质量信号明细"模块 |

---

## 2. 整体架构

### 2.1 数据流

```
Step 2.6 主对话(已有): gap → underweight[] / overweight[]
                          ↓
Step 5.5 fund-recommender subagent(本 spec 改造点)
   │
   ├─ 1) 读取 prefs.json + gap(主对话传入)
   │
   ├─ 2) screener replacement(沿用 portfolio_rebalance.screen_replacement_funds)
   │       → 每类 Top-5 候选(共 N 类 × 5 = M 只)
   │
   ├─ 3) 对每只候选并行调度 7 分析师 subagent(35 subagent/类)
   │       输入: candidates=[{code, name, category}]
   │       输出:
   │         - data/funds/<code>/   (数据,复用)
   │         - reports/<日期>/fund/candidate/<code>_market.md
   │         - reports/<日期>/fund/candidate/<code>_fundamentals.md
   │         - reports/<日期>/fund/candidate/<code>_holdings.md
   │         - reports/<日期>/fund/candidate/<code>_flows.md
   │         - reports/<日期>/fund/candidate/<code>_news.md
   │         - reports/<日期>/fund/candidate/<code>_policy.md
   │         - reports/<日期>/fund/candidate/<code>_sentiment.md
   │
   ├─ 4) 对每类调度 1 轮 bull + bear 辩论(2 subagent/类)
   │       输入: 该类 5 只候选的 7 分析师报告
   │       输出:
   │         - reports/<日期>/fund/candidate/<cat>_bull.md
   │         - reports/<日期>/fund/candidate/<cat>_bear.md
   │       强制要求: 输出含 class_ranking + top1_pick + reasons
   │
   ├─ 5) 调 parse_quality_from_reports()(主对话可同步调,新增 Python 函数)
   │       输入: candidates 列表 + 7 报告路径 + 辩论路径
   │       输出: {code → quality_score(0-100), signals(dict)}
   │       实现: 纯规则,无 LLM 调用
   │
   ├─ 6) 融合:
   │       final_score = name_score × 0.3 + quality_score × 0.7
   │       其中 name_score 来自 _score_fund(已存在)
   │       quality_score 来自 parse_quality_from_reports(新增)
   │
   ├─ 7) 按 final_score 降序,每类重取 Top-5(可能与步骤 2 不同序)
   │
   └─ 8) 写 portfolio_fund_recommendations.md
          - 沿用现有输出契约(recommendations 列表 + candidates)
          - 新增 quality_signals 字段
          - 新增 report_paths 字段(深度报告路径)
          - 新增 evidence 引用辩论
```

### 2.2 组件依赖图

```
fund-recommender.agent.md (重写)
    │
    ├─► screener replacement   (现有,不改)
    │      └─► portfolio_rebalance.screen_replacement_funds
    │
    ├─► 7 基金分析师 subagent   (复用 workflow-fund.md 角色契约)
    │      ├─► fund-market-analyst
    │      ├─► fund-fundamentals-analyst
    │      ├─► fund-holdings-analyst
    │      ├─► fund-flows-analyst
    │      ├─► fund-news-analyst
    │      ├─► fund-policy-analyst
    │      └─► fund-sentiment-analyst
    │
    ├─► bull + bear subagent   (复用,不改 agent 定义)
    │
    ├─► portfolio_rebalance.parse_quality_from_reports  (新增)
    │      └─► 纯规则,读 markdown + 正则抽取
    │
    └─► portfolio_rebalance.score_with_quality_reports  (新增)
           └─► 融合 name_score × 0.3 + quality_score × 0.7
```

### 2.3 报告与数据落盘结构

```
data/
├── funds/<code>/                          # 数据(复用,与单基金工作流一致)
│   ├── nav_*.csv
│   ├── performance_*.md
│   ├── fund_info_*.txt
│   ├── holdings_*.md
│   ├── manager_*.md
│   ├── flows_*.md
│   └── fund_news_*.md
└── _meta/fund_list.json                   # 全量库(已有)

reports/
└── <日期>/
    ├── fund/
    │   └── candidate/                      # 新增目录:候选基金深度报告
    │       ├── <code1>_market.md
    │       ├── <code1>_fundamentals.md
    │       ├── <code1>_holdings.md
    │       ├── <code1>_flows.md
    │       ├── <code1>_news.md
    │       ├── <code1>_policy.md
    │       ├── <code1>_sentiment.md
    │       ├── <code2>_*.md (x 5)
    │       ├── <cat1>_bull.md              # 辩论
    │       ├── <cat1>_bear.md
    │       ├── <cat2>_bull.md
    │       └── <cat2>_bear.md
    └── portfolio/
        └── portfolio_fund_recommendations.md  # 替换原"二次过滤"输出
```

---

## 3. 关键组件设计

### 3.1 portfolio_rebalance.py 新增函数

#### 3.1.1 `parse_quality_from_reports()`

**位置**:`data_tools/portfolio_rebalance.py` 新增函数

**签名**:
```python
def parse_quality_from_reports(
    code: str,
    reports_dir: str,
    category: str,
    date_str: str,
) -> dict:
    """
    读 7 分析师 markdown + 辩论 markdown,规则化抽取质量信号。
    返回:
        {
            "code": str,
            "name": str,
            "quality_score": float,  # 0-100
            "signals": {
                "performance": {"score": float, "details": dict, "missing": bool},
                "concentration": {"score": float, "details": dict, "missing": bool},
                "scale": {"score": float, "details": dict, "missing": bool},
                "manager": {"score": float, "details": dict, "missing": bool},
                "policy_sentiment": {"score": float, "details": dict, "missing": bool},
            },
            "report_paths": dict[str, str],   # 7 报告 + 辩论路径
            "missing_dimensions": list[str],  # 缺失的维度名
        }
    """
```

**评分维度与权重**(合计 1.0):

| 维度 | 权重 | 抽取规则 | 单维度评分(0-100) |
|------|------|----------|--------------------|
| **业绩持续性** | 0.30 | 读 `_market.md`,正则匹配:近 1/3/5 年排名 / 四分位 | 1 年 优秀 50, 良好 35, 一般 20, 不佳 5;3 年 / 5 年同权重平均 |
| **重仓股集中度** | 0.20 | 读 `_holdings.md`,匹配 "前十大占比" / "行业集中度" | 前十大 < 50% 80, 50-70% 60, 70-85% 40, > 85% 20 |
| **规模与趋势** | 0.20 | 读 `_fundamentals.md` (规模) + `_flows.md` (趋势) | 规模 > 10亿 50, 2-10亿 40, 0.5-2亿 25, < 0.5亿 10;+ 趋势:增 +10, 减 -10 |
| **经理稳定性** | 0.15 | 读 `_fundamentals.md` (经理年限) + `_holdings.md` (调仓频率) | 任期 > 5年 70, 3-5年 50, 1-3年 30, < 1年 10;+ 经理变更 -20 |
| **政策与情绪** | 0.15 | 读 `_policy.md` + `_sentiment.md` + `_news.md` | 关键词命中 "利空" 数量 -10, "利好" 数量 +5, 政策评级按等级加分 |

**抽取策略**(防 LLM 误判):
- 每个维度用**正则表达式**匹配 markdown 中结构化字段(表格、列表、关键句)
- 命中失败 → 维度 `missing=True`,该维度不计分(其他维度等比放大权重)
- 维度分数计算 100% 走规则表(`SCORE_TABLE`),不调 LLM
- 关键正则示例(待实现时细化):
  ```python
  _PERF_RANKING_RE = re.compile(r"近\s*1\s*年[^\n]*?排名[：:]\s*([前中后]\d+%|优秀|良好|一般|不佳)")
  _HOLDING_CONCENTRATION_RE = re.compile(r"前十大重仓占比[：:]\s*([\d.]+)\s*%")
  _SCALE_RE = re.compile(r"基金规模[：:]\s*([\d.]+)\s*亿")
  _MANAGER_TENURE_RE = re.compile(r"任职年限[：:]\s*([\d.]+)\s*年")
  ```

#### 3.1.2 `score_with_quality_reports()`

**签名**:
```python
def score_with_quality_reports(
    screener_results: dict[str, list[dict]],   # {category: [{code, name, type, score, match_reasons}]}
    quality_reports: dict[str, dict],         # {code: parse_quality_from_reports() 输出}
    name_weight: float = 0.3,
    quality_weight: float = 0.7,
) -> dict[str, list[dict]]:
    """
    融合名称分 + 质量分,返回每类重排序后的 Top-N。
    输入:
        screener_results: screen_replacement_funds() 原输出
        quality_reports:  parse_quality_from_reports() 对每只的输出
    输出:
        {category: [{code, name, type, score(融合), name_score, quality_score,
                     match_reasons, quality_signals, report_paths}, ...]}
    """
```

**融合公式**:
```python
final_score = name_score * name_weight + quality_score * quality_weight
# 例: name=60, quality=80 → final = 60×0.3 + 80×0.7 = 18 + 56 = 74
```

**缺失处理**:
- 若某候选 `quality_reports` 缺失(7 报告全失败)→ 用 `name_score` 作为 `final_score`,在结果中标 `quality_missing=True`
- 若某维度 `missing=True` → 该维度权重归零,其他维度等比放大

#### 3.1.3 `build_rebalance_plan()` 改造

在 [portfolio_rebalance.py:331-393](file:///d:/01_coding/my_agents/data_tools/portfolio_rebalance.py#L331-L393) 基础上,新增可选参数:

```python
def build_rebalance_plan(
    positions: list[dict],
    prefs: UserPrefs,
    universe_path: str | None = None,
    per_category: int = 5,
    quality_reports: dict[str, dict] | None = None,   # 新增
    name_weight: float = 0.3,                          # 新增
    quality_weight: float = 0.7,                       # 新增
) -> RebalancePlan:
```

逻辑:若 `quality_reports` 传入,先算 screener 候选,再调 `score_with_quality_reports` 重排序;否则沿用原 `screen_replacement_funds` 流程。

### 3.2 cli.py 新增子命令

#### 3.2.1 `quality-score` 命令(供单测和单独调用)

**位置**:`data_tools/cli.py` 新增

**签名**:
```bash
python -m data_tools.cli quality-score \
    --code <6位> \
    --reports-dir reports/<日期>/fund/candidate \
    --category <cash/bond/...> \
    --date <日期>
```

**输出**:`parse_quality_from_reports()` 的 JSON 结果,便于单测和调试。

**注册**:
- argparse 子命令注册
- click 子命令注册
- `python -m data_tools.cli --help` 中可见

### 3.3 fund-recommender.agent.md 重写

#### 3.3.1 新版输入契约

```yaml
date_str: <YYYY-MM-DD>          # 主对话传入
candidates_by_cat:               # 主对话从 screener 传入
  bond:
    - {code: "007466", name: "华泰柏瑞中证红利低波ETF联接A", type: "指数型", score: 70}
  overseas:
    - {code: "513500", name: "博时标普500ETF联接A", type: "QDII", score: 65}
prefs_path: data/portfolios/<id>/prefs.json
gap_report_path: reports/<日期>/portfolio/portfolio_gap.md
universe_path: data/funds/_meta/fund_list.json
output_path: reports/<日期>/portfolio/portfolio_fund_recommendations.md
```

#### 3.3.2 调度模板(主对话生成的 Task 提示词)

主对话**为 fund-recommender subagent 生成如下结构化提示词**(由主对话拼装,subagent 不需要自己拼):

```
你是 fund-recommender(候选基金深度推荐员)。请按以下流程执行:

【Step A】读取上下文
  - {prefs_path}
  - {gap_report_path}
  - {universe_path}
  - 已传入 candidates_by_cat(JSON 字符串)

【Step B】对每类 5 只候选并行调度 7 基金分析师 subagent
  每个 subagent prompt 模板:
    "你是 fund-<role>-analyst。读取 agents/fund-<role>-analyst.agent.md,
     对基金 <code> 拉取数据:<data_commands>。
     数据保存 data/funds/<code>/,报告保存 reports/<date>/fund/candidate/<code>_<role>.md。
     返回核心要点摘要。"
  
  调度方式:同类 5 只 × 7 分析师 = 35 个 Task 调用,**同一消息内并行**。
  分批规则:
    - 5 类 × 35 = 175 subagent,建议分 5 批(每类 1 批)
    - 同一批 35 个 Task 在同一消息内并行触发

【Step C】对每类调度 1 轮多空辩论(bull + bear 并行)
  每个辩论 subagent prompt:
    "你是 <bull|bear>-researcher。读取 agents/<bull|bear>-researcher.agent.md。
     读 reports/<date>/fund/candidate/<code*>_<role>.md (5 只候选 × 7 分析师) 
     和 reports/<date>/fund/candidate/<code*>.md(若有其他材料)。
     输出类内对比 + ranking + top1_pick + reasons,
     写到 reports/<date>/fund/candidate/<cat>_<bull|bear>.md。"
  
  调度方式:5 类 × 2 = 10 个 Task,同一消息内并行。

【Step D】调 Python 评分(由主对话可并行执行,你可提示主对话执行)
  python -m data_tools.cli quality-score --code <code> --reports-dir ... --category <cat> --date <date>
  对每只候选获取 {code → quality_score, signals}

【Step E】调 Python 融合
  python -m data_tools.cli portfolio rebalance \
    --user-id <id> --positions <...> --fmt json \
    --quality-reports <path>  (新增 flag)

【Step F】写出 portfolio_fund_recommendations.md
  沿用现有 output 契约,新增字段:
    quality_signals: dict
    report_paths: dict
    evidence: 包含辩论路径

【铁律】
- summary ≤ 2k tokens
- 7 分析师失败 → 跳过该维度,标注 [质量分缺失维度:xxx]
- 整只候选 7 报告全失败 → 用原 name_score,标 quality_missing=True
- 辩论失败 → 标 [辩论缺失],不影响 parse_quality 评分
- 禁止对候选做主观推荐排序(排序由 score_with_quality_reports 决定)
- 禁止编造数据(无数据标 [数据缺失])
```

#### 3.3.3 输出契约扩展

原 output 契约(在 fund-recommender.agent.md 第 68-103 行)每个 candidate 新增:

```yaml
- rank: 1
  code: 6位
  name: 中文
  type: 天天基金 type
  score: 融合后 final_score(0-100)
  name_score: 原 _score_fund 分
  quality_score: parse_quality_from_reports 分
  match_reasons: ["..."]
  quality_signals:
    performance: {score, details, missing}
    concentration: {score, details, missing}
    scale: {score, details, missing}
    manager: {score, details, missing}
    policy_sentiment: {score, details, missing}
  report_paths:
    market: reports/<date>/fund/candidate/<code>_market.md
    fundamentals: ...
    holdings: ...
    flows: ...
    news: ...
    policy: ...
    sentiment: ...
    bull: reports/<date>/fund/candidate/<cat>_bull.md  # 共享
    bear: reports/<date>/fund/candidate/<cat>_bear.md  # 共享
  risk_note: 一句话
  size_note: 一句话 / [数据缺失]
  fee_note: 一句话 / [数据缺失]
  quality_missing: false   # 整只 7 报告全失败时为 true
```

---

## 4. 与下游的衔接

### 4.1 portfolio-manager (Step 7) 增强

[portfolio-manager.agent.md](file:///d:/01_coding/my_agents/agents/portfolio-manager.agent.md) 必须读取 `portfolio_fund_recommendations.md`,在最终报告(markdown)中新增章节:

```markdown
## 4.X 推荐补/换基金的深度评估

### 4.X.1 质量分 Top-3
| 代码 | 名称 | 名称分 | 质量分 | 融合分 | 主要信号 |
|------|------|--------|--------|--------|----------|
| 007466 | xxx | 70 | 82 | 78.4 | 业绩持续性强 |
| ...   | ... | ... | ...  | ...   | ...      |

### 4.X.2 各类别最优
- bond: 007466 (理由:xxx)
- overseas: 513500 (理由:xxx)

### 4.X.3 质量信号缺失项
(如适用,列出 [数据缺失] 的维度)
```

### 4.2 HTML 模板扩展

[templates/portfolio.html.j2](file:///d:/01_coding/my_agents/templates/portfolio.html.j2) 的"调整建议"模块新增:

1. **质量分组成表**(每个 Top-1 候选的 5 维度细分)
2. **深度报告路径表**(点击跳转到对应 markdown)
3. **辩论结论引用块**(从 `<cat>_bull.md` / `<cat>_bear.md` 摘录 top1_pick 段)

文件大小预估:HTML 文件增加约 30-50KB(每只 Top-1 候选 1 个深度面板)。

### 4.3 workflow-portfolio.md 文档更新

[workflow-portfolio.md Step 5.5](file:///d:/01_coding/my_agents/.trae/skills/stock-analysis/workflow-portfolio.md#L453-L505) 章节重写为"增强版 fund-recommender",补充:

- 调度流程图(35 + 10 subagent 的并发说明)
- 报告路径模板
- 失败降级说明
- 评分融合公式

### 4.4 SKILL.md 铁律补充

[SKILL.md](file:///d:/01_coding/my_agents/.trae/skills/stock-analysis/SKILL.md) 新增"铁律 7:Step 5.5 增强版必须并行":

> Step 5.5 的 7 分析师 + 辩论 subagent 必须**按类分批、同批内并行**触发,不可串行。35 subagent/类 同一消息内 35 个 Task 并行。

---

## 5. 错误处理与降级

### 5.1 降级矩阵

| 失败情况 | 检测方式 | 降级行为 | 用户可见提示 |
|----------|----------|----------|--------------|
| 某只候选 7 报告全失败 | `quality_reports[code]` 不存在 | 用 `name_score` 作为 `final_score` | 候选详情中标 `quality_missing: true`,质量信号表标 [全部缺失] |
| 某只候选 1-2 维度失败 | `signals[<dim>].missing=True` | 该维度权重归零,其他维度等比放大 | 标 [质量分缺失维度:xxx] |
| 某类 bull/bear 失败 | 辩论文件不存在 | `parse_quality` 不引用辩论 | 标 [辩论缺失:bull.md 未生成] |
| screener 返回 < 5 只 | `len(screener_results[cat]) < 5` | 有几只跑几只 | 标 [该类仅 X 只候选] |
| 整类 screener 失败 | `screener_results[cat] == []` | 该类跳过 | 标 [本类无候选:xxx] |
| fund_universe 未同步 | `fund_list.json` 不存在 | **完全跳过 Step 5.5** | 报告标 [Step 5.5 未触发:fund_list.json 不存在] |
| parse_quality 抛异常 | try/except 包住 | 该候选降级到 name_score | 标 [质量评分异常] |

### 5.2 性能预算

| 指标 | 数值 |
|------|------|
| 单类 subagent 数 | 35(7 分析师 × 5 候选) + 2(辩论) = 37 |
| 总 subagent 数(5 类) | 185 |
| 单 subagent 平均耗时 | 5-10s |
| 5 类分 5 批 | 5 × 37 = 5 批 × 30s = **2.5 分钟**(主对话等待) |
| Token 成本估算 | ~300K-500K tokens(每 subagent ~2-3K 输出) |
| 落盘文件 | 5 × 5 × 7 = 175 报告 + 5 × 2 = 10 辩论 + 1 汇总 = **186 文件** |

### 5.3 降级总则

- **质量优先于完整**:任何失败都不阻塞主流程,所有降级都明确标注
- **可观测**:每个降级分支在 `portfolio_fund_recommendations.md` 中显式记录
- **可重跑**:fund-recommender subagent 是幂等的,主对话可单独重跑

### 5.4 快路径优化(可选,非必须)

如果 `underweight` 类别数 == 1 且 gap < 5%,主对话**可选择不调 fund-recommender**,直接在 portfolio_gap.md 中标注 `[Step 5.5 跳过:缺口过小]`。**这是性能优化,非强制**;本 spec 默认"总是触发"。

---

## 6. 测试策略

### 6.1 单元测试

**新增** `tests/unit/test_quality_score.py`,覆盖:

| 用例 | 场景 | 期望 |
|------|------|------|
| test_perfect_fund | 模拟"业绩优秀 + 集中度低 + 规模大 + 经理稳定" 7 报告 | quality_score >= 85 |
| test_terrible_fund | 模拟"业绩差 + 集中度高 + 迷你盘 + 经理刚换" 7 报告 | quality_score <= 30 |
| test_missing_one_dim | 1 维度 `missing=True` | 其他 4 维度等比放大,总权重 = 1.0 |
| test_missing_all_dim | 7 报告全缺失 | 返回 `quality_missing=True`,score = 0 |
| test_score_fusion | name_score=60, quality_score=80, weight=0.3/0.7 | final = 74 |
| test_parse_quality_robustness | 报告含 markdown 表格、列表、特殊字符 | 正确抽取,无异常 |
| test_classify_holding_disabled | 持仓被排除(excluded_categories) | 不进入 underweight 替换候选 |

**新增** `tests/unit/test_quality_score_cli.py`,覆盖:

- `python -m data_tools.cli quality-score` 正常路径
- 参数缺失报错
- 输出 JSON 可被 JSON 解析

### 6.2 集成测试

更新 `tests/integration/test_workflow_portfolio_c1.py` 和 `c3.py`,新增断言:

- 跑完 Step 5.5 后,`portfolio_fund_recommendations.md` 存在
- 每类至少 1 个候选含 `quality_signals.performance.score`
- `final_score` 字段非空
- 报告路径字段在 [Markdown 路径] 列表里全部存在

### 6.3 端到端测试

更新 `tests/e2e/test_multi_fund_portfolio_e2e.py`:

- 跑完整组合 + Step 5.5 增强版
- 断言最终 HTML 报告含"质量分组成表"区块

### 6.4 不测的内容

- 7 分析师 subagent 内部逻辑(由各自 agent 单测覆盖,本 spec 不重复)
- 辩论 subagent 内部逻辑(同上)
- LLM 输出质量(无法自动化测试,人工 review 即可)

---

## 7. 改造清单(按优先级)

| 优先级 | 文件 | 改动 | 估时 |
|--------|------|------|------|
| P0 | [portfolio_rebalance.py](file:///d:/01_coding/my_agents/data_tools/portfolio_rebalance.py) | 新增 `parse_quality_from_reports` + `score_with_quality_reports` + `build_rebalance_plan` 加 `quality_reports` 参数 | 1-2 天 |
| P0 | [cli.py](file:///d:/01_coding/my_agents/data_tools/cli.py) | 新增 `quality-score` 子命令(argparse + click) | 0.5 天 |
| P0 | [tests/unit/test_quality_score.py](file:///d:/01_coding/my_agents/tests/unit/test_quality_score.py) | 新增 7+ 单测 | 1 天 |
| P1 | [fund-recommender.agent.md](file:///d:/01_coding/my_agents/agents/fund-recommender.agent.md) | 重写为"增强版"调度流程 | 0.5 天 |
| P1 | [workflow-portfolio.md](file:///d:/01_coding/my_agents/.trae/skills/stock-analysis/workflow-portfolio.md) | 重写 Step 5.5 章节 | 0.5 天 |
| P1 | [SKILL.md](file:///d:/01_coding/my_agents/.trae/skills/stock-analysis/SKILL.md) | 新增铁律 7 | 0.2 天 |
| P1 | [tests/unit/test_quality_score_cli.py](file:///d:/01_coding/my_agents/tests/unit/test_quality_score_cli.py) | CLI 子命令单测 | 0.5 天 |
| P2 | [portfolio-manager.agent.md](file:///d:/01_coding/my_agents/agents/portfolio-manager.agent.md) | 新增"深度评估"输出契约 | 0.3 天 |
| P2 | [portfolio.html.j2](file:///d:/01_coding/my_agents/templates/portfolio.html.j2) | 新增"质量分组成表"模块 | 0.5 天 |
| P2 | [tests/integration/test_workflow_portfolio_c1.py](file:///d:/01_coding/my_agents/tests/integration/test_workflow_portfolio_c1.py) | 增强版集成断言 | 0.5 天 |
| P2 | [tests/e2e/test_multi_fund_portfolio_e2e.py](file:///d:/01_coding/my_agents/tests/e2e/test_multi_fund_portfolio_e2e.py) | E2E 断言新模块 | 0.5 天 |
| **合计** | | | **5-6 人天** |

---

## 8. 风险与权衡

| 风险 | 等级 | 缓解 |
|------|------|------|
| 175 subagent 并发触发可能撞 TRAE 调度上限 | 中 | 按类分 5 批,同类 35 个同一消息内并行;若失败降级为串行 |
| LLM 输出格式不稳定,正则抽取失败率高 | 中 | 提供"该维度缺失"降级路径;`missing=True` 占比 < 30% 时质量分仍可计算 |
| 候选基金数据缺失(7 大数据源) | 中 | 复用现有 `[数据缺失]` 标注;portfolio-fundamentals subagent 已处理过 |
| 辩论 subagent 输出不含 `top1_pick` 字段 | 低 | 在 fund-recommender.agent.md 铁律中显式要求,主对话校验 |
| 增强版总耗时 3-5 分钟,用户等待长 | 中 | 主对话可选择"快路径"优化(5.4),但默认总是触发 |
| `fund_list.json` 字段变更(ftype、is_offexchange) | 低 | parse_quality 不依赖 ftype;`_load_universe` 已做容错 |
| 候选基金代码可能与现有持仓重复 | 低 | screener 已过滤 `held_codes`,score_with_quality 复用 |

---

## 9. 验收标准

- [ ] `parse_quality_from_reports()` 对 5+ 真实基金 markdown 报告抽取正确
- [ ] `score_with_quality_reports()` 输出 final_score ∈ [0, 100]
- [ ] 单元测试 `pytest tests/unit/test_quality_score.py -v` 全部通过
- [ ] CLI `python -m data_tools.cli quality-score --help` 显示帮助
- [ ] fund-recommender.agent.md 调度流程图清晰
- [ ] 跑完整 C-1 组合 E2E(`pytest tests/e2e/test_multi_fund_portfolio_e2e.py -v`)通过
- [ ] 最终 HTML 报告含"质量分组成表"和"深度报告路径表"
- [ ] 7 分析师失败时,降级路径生效,无未捕获异常
- [ ] 整只候选 7 报告全失败时,推荐列表仍含该候选(用 name_score)

---

## 10. 不在本次范围(后续 v2 考虑)

- 把"深度推荐"能力扩展到 C-2 股票候选(目前 fund-recommender 只做基金)
- 给候选基金做"组合后再跑一遍 7 分析师"的二次验证(防止数据滞后)
- 候选基金跑 8-Step(再加 research-manager + trader + 风控 3 人 + portfolio-manager)
- 用 LLM scorer subagent 替代规则评分(牺牲可测试性换智能)
- 评分公式自适应(根据 user.risk_level 调权重)
- 候选基金的"调仓模拟"(假设替换后新组合的预期回撤)
- 与 portfolio_analyst 联动(把深度评分作为组合分析输入)
