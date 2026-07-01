# 持仓组合工作流优化设计 Spec

> 设计日期：2026-07-01
> 目标项目：`d:\01_coding\my_agents`
> 适用场景：C-1 全基金组合 / C-3 混合组合（持仓组合工作流）
> Spec 状态：brainstorming 阶段，已完成用户共识，待用户复审

---

## 1. 背景与目标

当前持仓组合工作流（C-1/C-3）的最终报告存在以下三个痛点：

1. **章节顺序不利于决策**：投资经理最终报告把"操作建议"放在文末，用户最关心的内容需要翻到最底部。
2. **数据源评估缺失**：整个报告没有显式呈现每只标的的数据拉取日期、缓存命中状态、缺失维度，用户对结论背后的数据健康度无感。
3. **Step 9 给出明确基金推荐过重**：原方案对每个 underweight 类别跑 7 分析师 + 类内辩论 + 融合分排名（Top-3 候选），提供"质量分 + 推荐理由"双重信号。该方案在用户看来"决策负担过重"，希望改为**只输出"补充类"（品类缺口 + 待补特征）和"清除类"（具体持仓基金 + 初步筛掉原因）**两份清单。

配套改进点：

- **展示补全**：所有出现基金代码的位置同时展示完整中文名称 + 当前净值（含单位净值和日累计收益），净值显示遵循现有缓存机制并显式标注缓存状态。

---

## 2. 优化目标（YAGNI）

| # | 目标 | 不做的事 |
|---|------|---------|
| G1 | 报告章节重排：操作建议前置、数据源评估随后 | 不调整单标的工作流（A/B 流程） |
| G2 | 显示完整基金名称 + 当前净值（带缓存状态） | 不引入新缓存阈值常量（沿用 fund_data.py 的 `_CACHE_MAX_AGE_HOURS`） |
| G3 | Step 9 输出从「Top-3 候选评分」改为「补充/清除分类清单」 | 不删除 `fund-recommender` subagent 与 `screen_replacement_funds` 函数（保留为数据底座） |
| G4 | 清除清单附「初步筛掉原因」（枚举化） | 不引入新评分模型，复用 `quality_scorer.parse_quality_from_reports` 已有信号 |
| G5 | 工程改动遵循「最小改动 + 复用现有公共模块」 | 不新增数据库表、不改动 CLI 入参兼容性 |

---

## 3. 设计要点

### 3.1 报告章节顺序（Markdown + HTML 同步重排）

#### Markdown 输出（portfolio-manager.agent.md）

**变更前**（八章结构）：
```
一、投资评级
二、核心观点
三、多维度分析摘要（6 维度）
四、投资逻辑
五、操作建议  ← 位于中后段
六、关注要点
七、免责声明
八、推荐补/换基金深度评估（Step 5.5 增强版输出）
```

**变更后**（八章结构）：
```
一、操作建议（分优先级 P0/P1/P2/P3 直接放最前）
二、数据源评估（新增：列每只标的的数据拉取日期/缓存状态/缺失维度）
三、核心观点（评级 + 一句话总结）
四、多维度分析摘要（6 维度，简版）
五、投资逻辑（含核心利好/主要风险）
六、补充类清单 + 清除类清单（替换原"八、推荐补/换基金"独立章节）
七、关注要点
八、免责声明
```

#### HTML 渲染（portfolio.html.j2 + _portfolio_section.html.j2）

- `portfolio.html.j2` 的 `{% include %}` 块顺序同步重排：
  1. `_portfolio_section.html.j2`（持仓总览 + 明细）→ 第一屏
  2. **新增 `data_source_audit.html.j2`**（数据源评估）→ 第二屏
  3. **新增 `action_recommendations.html.j2`**（操作建议 + 补充/清除清单）→ 第三屏（原第六屏位置）
  4. `_risk_section.html.j2`（风险）→ 第四屏
  5. `target_allocation` 对比 → 第五屏
  6. `_disclaimer.html.j2` + `_footer.html.j2` → 末屏
- 移除原"推荐补/换基金的深度评估"块（[portfolio.html.j2:55-122](file:///d:/01_coding/my_agents/templates/portfolio.html.j2#L55-L122)）。

#### 章节顺序联动

`workflow-portfolio.md` 的"📊 组合工作流总览"章节编号保持 Step 1-12 顺次执行不变，仅调整最终 markdown 报告的章节排版约定。

### 3.2 全场景名称 + 当前净值展示

#### 范围

所有出现基金代码的地方同步显示完整名称：
- 持仓明细表（自动满足）
- 操作建议表（按优先级分块）
- 补充类清单
- 清除类清单（含筛掉原因）
- 数据源评估表
- 任何 subagent 报告里引用 `<code>` 的位置（不修改 subagent 输出，由 portfolio-manager 在整合时统一加 `<name>` 后缀）

#### 当前净值数据来源

**优先路径**（沿用现有缓存机制）：

1. 从 `data/funds/<code>/nav_*.csv` 取最新一行（"单位净值"/"累计净值"/"日增长率"）
2. 若 `nav_*.csv` 不存在 → 退到 `fund_info_<code>.txt` 的"单位净值"字段
3. 若都不存在 → 标 `[净值缺失]`

#### 缓存校验（新增 G2 要求）

**新增函数**：`data_tools.fund_data.get_unit_nav_with_cache_status(code, threshold_hours=None)`

- `threshold_hours=None`：使用 `_CACHE_MAX_AGE_HOURS["nav"] = 4` 作为默认阈值
- 返回三元组 `(unit_nav: float | None, daily_return: float | None, cache_status: str)`
- `cache_status` 枚举：
  - `"fresh"`：本地缓存未过期（age < threshold）
  - `"stale"`：本地缓存过期但文件存在（age ≥ threshold）
  - `"missing"`：本地无文件
  - `"force_refetch"`：调用方显式传入 `force=True` 触发实时拉取

**HTML 显示规则**：

| 状态 | 标签样式 | 文案 |
|------|---------|------|
| fresh | 🟢 绿点 | `今日更新 HH:MM` |
| stale | 🟡 黄点 | `已过 Xh ago,数据可能滞后` |
| missing | 🔴 红点 | `净值缺失,点击拉取` |
| force_refetch | 🔵 蓝点 | `实时拉取中...` |

点击触发前端 JS 调用 `python -m data_tools.cli fund nav-cached <code> --force`（仅 UI 提示，**不修改 HTML 报告**）。

**新增 CLI**：

```bash
python -m data_tools.cli fund nav-cached <code>
python -m data_tools.cli fund nav-cached <code> --force
python -m data_tools.cli fund nav-cached <code> --threshold-hours 4
```

- 默认行为：调用 `get_unit_nav_with_cache_status(code)`，fresh 时直接返回缓存；stale 时静默重拉一次
- `--force`：绕过缓存，直接调用 `get_fund_nav_history(...)` 拉取并写盘

**复用现有**：

- `fund_data._find_latest_cache_file`（按前缀 + mtime 排序找最新文件）
- `fund_data.is_data_fresh`（按 `data_type` 类型键查 `_CACHE_MAX_AGE_HOURS`）
- `fund_data.get_fund_nav_history`（实际拉取，封装东方财富接口）
- `stock_data.save_fund_data_file`（统一落盘格式）

### 3.3 Step 9 改造：补充/清除分类清单

#### 补充类清单（按品类缺口展示，不点名具体基金）

**输入**：来自 `compute_gap()` 的 `underweight` 列表 + `gaps` 字段

**展示列**：

| 品类 | 目标占比 | 当前占比 | 缺口金额(¥) | 期望特征标签 |
|------|---------|---------|------------|-------------|
| 债券/固收+ | 25.0% | 15.2% | +9,820 | 「短债优先」「回撤 < 0.5%」「近 1 年 > 货币基金 +1.5%」 |
| 红利低波 | 10.0% | 4.8% | +2,080 | 「股息率 > 5%」「PE < 行业均值」 |

**期望特征标签**来源：

- `data_tools/portfolio_prefs.py` 的 `CATEGORY_KEYWORDS[cat]` → 品类典型关键词（短债/中短债/红利/QDII 等）
- 用户 `prefs.preferred_categories` → 用户偏好的子品类关键词
- 复用 `_score_fund` 的 `match_reasons` 思路：从 `_NAME_TO_CATEGORY` 反推"目标品类典型名称片段"

**输出层**：纯描述性，不出现任何具体基金代码，**完全避免 Top-3 排名**。

#### 清除类清单（具体持仓基金 + 初步筛掉原因）

**输入**：当前 `holdings` + `fund_report_summary`（每只基金的 7 分析师报告存在性 + quality_signals）+ `gap_report` 的 `excluded_holdings` + `manual_flag`

**筛掉原因枚举**（与现有质量信号对齐）：

| 原因代码 | 中文文案 | 触发条件 | 数据来源 |
|---------|---------|---------|---------|
| `clear_liquidation_risk` | 🔴 临近清盘线（净资产 < 5000 万） | `info.txt` 净资产 < 5e7 | `fund_data` |
| `clear_redemption_pressure` | 🔴 持续大额净赎回（季度净赎回 > 20%） | `flows.md` 近 1 季度净赎回率 > 20% | `fund_data` |
| `clear_underperform_3y` | 🟡 长期跑输基准（3 年排名 < 1/2） | `performance.md` 3 年排名后 50% | `fund_data` |
| `clear_manager_change` | 🟡 经理刚变更（磨合期） | `manager.md` 中 `manager_change=true` 或 `days_since_change < 90` | `fund_data` |
| `clear_redundancy` | 🟡 重复暴露（与组合内其他持仓相关系数 > 0.85） | 由 `data_tools.portfolio.detect_overlap` 变体提供 | 新增函数 |
| `clear_concentration_violation` | 🟡 单一占比超纪律（> 25%） | 单只基金 ratio > 25% | 持仓数据 |
| `clear_category_overweight` | 🟢 风格超配（gap 中 overweight） | `compute_gap()` 中 `delta_pct < -0.03` | `portfolio_rebalance` |
| `clear_user_excluded` | 🟢 用户已显式排除 | `prefs.excluded_codes` 命中 | `portfolio_prefs` |
| `manual_flag` | 🔵 用户手工标记 | 来自用户输入文本解析 | `portfolio_prefs.parse_user_prefs_from_text` |

**新增函数**：`data_tools/portfolio.py → classify_exit_reasons(holdings, fund_reports, gap_report, prefs) -> list[ExitReason]`

- 入参：
  - `holdings`：当前持仓（与 portfolio_rebalance 入参一致）
  - `fund_reports`：每只基金的报告状态 `{"<code>": {"report_paths": {...}, "quality_signals": {...}, "has_reports": bool}}`
  - `gap_report`：`compute_gap()` 输出的 `gaps` + `overweight`
  - `prefs`：`UserPrefs` 实例（用于排除代码匹配）
- 出参：`list[ExitReason]`，每个元素含 `{code, name, amount, unit_nav, daily_return, cache_status, reasons: [ExitReasonItem]}`，`ExitReasonItem` 含 `{code, label}`

**复用现有**：

- `data_tools/portfolio.calculate_concentration` 已提供 HHI；新增 `find_redundant_pairs(positions, fund_reports) -> list[(code_a, code_b, correlation)]` 实现相关性检测
- `data_tools/quality_scorer.parse_quality_from_reports` 的 `quality_signals` 子项 `scale/manager/performance` 已有"差值信号"，可通过阈值（如 `performance < 50`）映射到 `clear_underperform_3y`

**降级**：

- 某只基金的 `fund_reports` 完全缺失（Step 4 subagent 全失败）→ 沿用 [fund-recommender.agent.md:91-95](file:///d:/01_coding/my_agents/agents/fund-recommender.agent.md#L91-L95) 的 `quality_missing=true` 兜底，标 `[本只数据全缺失,初步筛掉原因基于数据快照]`
- 净值缺失（无 `info.txt` 且无 `nav_*.csv`）→ 标 `单位净值: [缺失]`，但仍展示筛掉原因

#### Step 9 在 workflow 中的角色调整

| 子项 | 变更前 | 变更后 |
|------|--------|--------|
| fund-recommender subagent 调度 | 7 分析师 × Top-5 候选 + 类内辩论 | **保留调度逻辑不变**（作为数据底座） |
| portfolio_fund_recommendations.md | 含 Top-3 表格 + 融合分 + 信号 | **保留文件结构不变**（后续渲染层不再引用此文件） |
| 输出到 portfolio_final.md 的章节 | 第八章"推荐补/换基金深度评估" | 第六章"补充/清除分类清单" |
| C-1/C-3 跳过条件 | 保持不变（[workflow-portfolio.md:579-587](file:///d:/01_coding/my_agents/.trae/skills/stock-analysis/workflow-portfolio.md#L579-L587)） | 同左 |

**核心点**：portfolio-manager 在写 markdown 第六章时，**不再引用 `portfolio_fund_recommendations.md`**，而是直接调用 `classify_exit_reasons()` 生成清除清单 + 从 `compute_gap()` 的 `underweight` 生成补充清单。

---

## 4. 工程改动清单

| 改动点 | 文件 | 关键变更 | 优先级 |
|------|------|---------|--------|
| 报告章节顺序 | [agents/portfolio-manager.agent.md](file:///d:/01_coding/my_agents/agents/portfolio-manager.agent.md) | 重排输出章节：操作建议前置、新增数据源评估章节、第六章节改为补充/清除清单、移除原第八章 | P0 |
| HTML 重排 + 新增 | [templates/portfolio.html.j2](file:///d:/01_coding/my_agents/templates/portfolio.html.j2) | include 块重排；新增 `data_source_audit.html.j2` + `action_recommendations.html.j2` 两个 partial | P0 |
| 持仓表增强 | [templates/partials/_portfolio_section.html.j2](file:///d:/01_coding/my_agents/templates/partials/_portfolio_section.html.j2) | 新增"当前净值"列（含缓存状态标签）；调整列宽 | P0 |
| 新增净值缓存函数 | [data_tools/fund_data.py](file:///d:/01_coding/my_agents/data_tools/fund_data.py) | 新增 `get_unit_nav_with_cache_status(code, threshold_hours=None, force=False)` | P0 |
| 新增 CLI 命令 | [data_tools/cli.py](file:///d:/01_coding/my_agents/data_tools/cli.py) | 注册 `fund nav-cached <code> [--force] [--threshold-hours N]` 子命令 | P0 |
| 新增清除清单分类 | [data_tools/portfolio.py](file:///d:/01_coding/my_agents/data_tools/portfolio.py) | 新增 `classify_exit_reasons(holdings, fund_reports, gap_report, prefs)` + `find_redundant_pairs(positions, fund_reports)` | P0 |
| 渲染管线 | [data_tools/template_renderer.py](file:///d:/01_coding/my_agents/data_tools/template_renderer.py) | 渲染前批量调 `get_unit_nav_with_cache_status`，注入 portfolio.html 上下文 | P0 |
| 新增 partials | [templates/partials/data_source_audit.html.j2](file:///d:/01_coding/my_agents/templates/partials/data_source_audit.html.j2) (新增) | 数据源评估模块（含缓存状态可视化） | P1 |
| 新增 partials | [templates/partials/action_recommendations.html.j2](file:///d:/01_coding/my_agents/templates/partials/action_recommendations.html.j2) (新增) | 操作建议 + 补充/清除清单（含筛掉原因） | P1 |
| workflow 文档 | [.trae/skills/stock-analysis/workflow-portfolio.md](file:///d:/01_coding/my_agents/.trae/skills/stock-analysis/workflow-portfolio.md) | Step 9 描述改为"补充/清除分类（不再打分排名）"；Step 11 输出契约更新；Step 12 HTML 模块清单更新 | P1 |
| 测试 (TDD) | tests/unit/test_fund_nav_cache.py (新增) | `test_get_unit_nav_with_cache_status_*` 覆盖 fresh/stale/missing/force 四态 | P0 |
| 测试 (TDD) | tests/unit/test_exit_reasons.py (新增) | `test_classify_exit_reasons_*` 覆盖 8 种筛掉原因 + 净值缺失兜底 | P0 |
| 测试 (TDD) | tests/unit/test_template_portfolio_order.py (新增) | 断言 include 块顺序、操作建议块在最前、数据源评估在第二 | P0 |

---

## 5. 验收标准

| 维度 | 标准 |
|------|------|
| 章节顺序 | `portfolio_<日期>.html` 第一屏必须包含操作建议块（含 P0/P1/P2/P3 四档）；第二屏必须包含数据源评估块 |
| 名称展示 | 所有 `<code>` 单元格同行必须包含中文全称（不允许纯代码） |
| 净值展示 | C-1/C-3 场景每只持仓基金的 HTML 表格必须含"单位净值 + 日累计收益"列，且缓存状态可见 |
| 净值缓存 | `fund nav-cached <code>` 在 4h 内的二次调用必须返回 `cache_status='fresh'` 且不发起网络请求 |
| 清除清单 | 每条清除项必须含至少 1 个 `reasons[*]`；`code/name/amount/unit_nav` 任一字段缺失时显式标 `[缺失]` 而非抛错 |
| 补充清单 | 每条品类必须含"目标占比 + 当前占比 + 缺口金额 + 至少 1 个期望特征标签" |
| 跳过条件 | `underweight` 为空时清除清单照常输出（即使补充清单为空） |
| 复用约束 | 未引入新数据库表；CLI 入参兼容性不破坏；所有新函数复用 `_CACHE_MAX_AGE_HOURS` / `parse_quality_from_reports` / `compute_gap` |
| 测试覆盖率 | 新增模块 `data_tools/portfolio.classify_exit_reasons` / `fund_data.get_unit_nav_with_cache_status` 单元测试 ≥ 90% |
| 兼容性 | 原 `portfolio_fund_recommendations.md` 仍可生成（fund-recommender subagent 不修改），但 HTML 不再包含其引用 |

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 净值缓存阈值在交易日 15:00 前误判 stale | 用户看到黄标签 | `get_unit_nav_with_cache_status` 在交易日 15:00 前用 24h 阈值，15:00 后用 4h（沿用现有 `is_data_fresh` 逻辑但增强对 nav 类型的判断） |
| `find_redundant_pairs` 相关性计算依赖历史收益数据，缺失时无法判断 | 清除清单少一个原因 | 新增原因缺失时显式标 `[相关性数据缺失,未排查]` |
| 排序变化导致历史报告对比失效 | 用户回顾历史报告时不一致 | 在 `portfolio_<日期>.html` 顶部加 "本报告章节顺序已优化,详情见 workflow-portfolio.md" 提示（一次性） |
| 部分 subagent 报告全失败 | 清除清单"初步筛掉原因"无法拿到 quality_signals | `classify_exit_reasons` 对缺失的报告降级到只用 `info.txt + nav.csv` 做快照级判断 |
| Nav CSV 大小写字段不一致 | 净值解析失败 | 复用现有 `fund_data._parse_nav_csv`（已处理 "单位净值" vs "net_value" 等差异） |

---

## 7. 不在范围内（YAGNI）

- 不调整 A/B 单标的工作流的章节顺序
- 不调整 Step 1-12 的整体流程顺序
- 不删除 `fund-recommender` subagent 或 `screen_replacement_funds` 函数
- 不引入 cron 兜底刷新机制（手动 `--force` 即可）
- 不对 `<code>` 同时显示完整名称做 CSS 截断配置（直接用 `text-overflow: clip`）
- 不修改 `universe_config.json` 的缓存阈值

---

## 8. Spec 自检

- [x] **占位符扫描**：无 "TBD"/"TODO" 残留
- [x] **内部一致性**：章节顺序前后一致；数据源评估位置在第二章同步出现在 HTML 与 markdown
- [x] **范围检查**：单 spec 可对应单一实施计划
- [x] **歧义检查**：明确 G2 的"当前净值"列优先从 `nav_*.csv` 取、缺失时退化到 `info.txt`；明确 `cache_status` 枚举四态
- [x] **决策待定项**：无（如有未来追加项会列在第 7 节）

---

## 9. 待用户审阅（User Review Gate）

> Spec 已落到 `docs/superpowers/specs/2026-07-01-portfolio-workflow-redesign-design.md`，请用户审阅并确认：
> 1. 第 3.1 节章节顺序调整是否符合"操作建议→数据源评估→各分析结论"的要求
> 2. 第 3.2 节"当前净值"缓存阈值是否沿用 4h（交易日 15:00 后）/ 24h（其他时段）
> 3. 第 3.3 节筛掉原因枚举是否完整（如有新增场景请补到第 3.3 节）
> 4. 第 4 节工程改动清单是否符合"最小改动+复用"原则

确认后调用 `writing-plans` 技能拆分实施计划。
