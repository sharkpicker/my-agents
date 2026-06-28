# 基金全量采集调度器设计

> 日期：2026-06-28
> 状态：待用户审查
> 主题：为 Trae 自动化定时任务提供 Python CLI 入口，定时拉取国内场外开放式基金数据

## 1. 背景与目标

### 1.1 现状

- 项目已实现 A 股全量采集调度器（`data_tools/universe.py`），通过 `python -m data_tools.cli universe {init,status,sync,update,refresh-list}` 命令管理。
- 基金侧仅有"单只获取"命令（`python -m data_tools.cli fund {info,nav,holdings,manager,performance,flows,news,detect}`），没有全量采集与定时调度能力。
- 数据落盘路径：`data/funds/<code>/`，文件命名格式与现有 `fund_data.py` 接口一致。
- 每日基金净值一般在 20:00–22:00 更新完毕。

### 1.2 目标

提供一个 Python CLI 入口，供用户（或第三方定时任务调度器）每日定时调用，拉取**国内场外开放式基金**全量数据并落地缓存，使后续基金分析工作流随时可读。

### 1.3 非目标

- 不提供 Trae Schedule 内置定时任务配置（用户自建）。
- 不采集场内 ETF/LOF/封闭式基金。
- 不实现并发采集（沿用串行 + 限流，避免对天天基金接口造成压力）。
- 不修改 `fund_data.py` 任何接口签名（仅复用其 7 个查询函数）。

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│  第三方定时任务调度器（用户自建，例如 Trae Schedule）     │
│      ↓                                                  │
│  python -m data_tools.cli fund universe sync            │
│      ↓                                                  │
│  data_tools/cli.py（argparse 入口）                      │
│      ↓                                                  │
│  data_tools/fund_universe.py（新增·调度器）              │
│      ↓                                                  │
│  data_tools/fund_data.py（既有·7 个数据接口）            │
│      ↓                                                  │
│  data/funds/<code>/（数据落盘）                          │
│  data/funds/_meta/（列表/进度/配置）                     │
└─────────────────────────────────────────────────────────┘
```

### 文件清单

| 操作 | 路径 | 说明 |
|------|------|------|
| 新增 | `data_tools/fund_universe.py` | 调度核心，约 250 行 |
| 修改 | `data_tools/cli.py` | 新增 `fund universe {init,status,sync,update,refresh-list}` 5 个子命令 |
| 复用 | `data_tools/fund_data.py` | 7 个查询接口，签名不变 |
| 复用 | `data_tools/stock_data.py` | 存储与节流辅助函数 |

---

## 3. CLI 子命令接口

完全镜像 `universe` 子命令结构，保持学习成本一致：

```bash
python -m data_tools.cli fund universe init
python -m data_tools.cli fund universe status
python -m data_tools.cli fund universe sync
python -m data_tools.cli fund universe sync --quota 200 --force
python -m data_tools.cli fund universe update 001717
python -m data_tools.cli fund universe refresh-list
```

### 3.1 子命令行为与退出码

| 子命令 | 必填参数 | 可选参数 | 行为 | 退出码 |
|--------|---------|---------|------|--------|
| `init` | 无 | 无 | 拉取全量场外基金列表 → `data/funds/_meta/fund_list.json`，返回总只数 | 0=成功 / 1=失败 |
| `status` | 无 | 无 | 打印进度表（总/已采/今日配额/今日已采/失败冷却中/下次同步建议时间） | 0=始终 |
| `sync` | 无 | `--quota <int>` `--force` | 按"上次失败/优先级/老化"顺序选出当日待采基金，每只调用 7 个 fund_data 接口，写入 `data/funds/<code>/`，更新 `universe_progress.json` | 0=全部成功 / 2=部分失败 / 1=致命错误 |
| `update <code>` | 基金代码 | 无 | 强制拉取该基金全 7 类数据，覆盖 `data/funds/<code>/` 下所有当日文件 | 0=成功 / 1=失败 |
| `refresh-list` | 无 | 无 | 重新拉取基金列表并与本地 diff，新增/退场基金同步更新 `fund_list.json` | 0=成功 / 1=失败 |

### 3.2 退出码语义

| 退出码 | 含义 | 调度器建议处理 |
|--------|------|----------------|
| 0 | 全部成功 | 正常 |
| 2 | 部分失败（≥1 只基金部分字段缺失或整只失败但队列完成） | 记录但不告警 |
| 1 | 致命错误（列表缺失、网络断、磁盘满、参数错误） | 触发告警 |

---

## 4. 基金列表获取与场外过滤

### 4.1 数据源

复用 `fund_data.py` 的请求通道（`requests.get` + 东方财富 / 天天基金 HTTP API），新增列表端点：

```python
_FUND_LIST_PRIMARY = "https://fund.eastmoney.com/Data/Fund_JJJZ_Data.aspx"  # 天天基金全量列表
_FUND_LIST_FALLBACK = "https://datacenter-web.eastmoney.com/api/data/v1/get"  # 东方财富数据中心
```

主备切换策略：先尝试主端点，失败或返回 < 5000 条时降级到备用端点。

### 4.2 场外过滤规则

每条基金记录字段：`code, name, type, abbr, pinyin` 等。判定为「场外开放式」需**同时满足**：

| 排除规则 | 说明 |
|---------|------|
| 排除代码前缀 `15`、`16`、`18` | 场内 ETF（5/15 开头）/ LOF（16 开头）/ 封闭式（18 开头） |
| 排除名称包含「定开」「封闭」 | 定期开放、封闭式 |
| 排除 `type` 字段含「封闭式」 | 双保险 |

**保留类型**：股票型、混合型、债券型、货币型、指数型、QDII、FOF、另类等开放份额。

预计过滤后规模：约 8000~12000 只场外开放式基金。

### 4.3 输出文件：`data/funds/_meta/fund_list.json`

```json
[
  {"code": "000001", "name": "华夏成长混合", "type": "混合型-偏股", "is_offexchange": true},
  {"code": "510300", "name": "华泰柏瑞沪深300ETF", "type": "指数型-股票", "is_offexchange": false},
  {"code": "001717", "name": "工银前沿医疗股票A", "type": "股票型", "is_offexchange": true}
]
```

### 4.4 刷新策略

- `init` 与 `refresh-list` 时全量重写 `fund_list.json`。
- diff 出的"新增/退场"基金分别加入 `pending_add` / `pending_remove` 队列。
- `sync` 时只同步 `pending_add` 中尚未采集的基金。

---

## 5. 数据流与存储

### 5.1 目录结构

```
data/funds/
├── _meta/
│   ├── fund_list.json              # 全量场外开放式基金列表
│   ├── universe_progress.json      # 每只基金的最后采集时间/状态/失败次数
│   └── universe_config.json        # 调度参数（quota/interval/cooldown…）
└── <基金代码>/
    ├── nav_<start>_<end>.csv                # 净值（来自 fund_data.get_fund_nav）
    ├── fund_info_<date>.txt                 # 概况
    ├── holdings_<date>.md                   # 重仓股
    ├── manager_<date>.md                    # 基金经理
    ├── performance_<date>.md                # 业绩
    ├── flows_<date>.md                      # 份额变动
    └── fund_news_<start>_<end>.md           # 基金新闻
```

所有文件名格式与现有 `fund_data.py` 完全一致，落盘函数无需修改。

### 5.2 `universe_progress.json` 结构

```json
{
  "000001": {
    "last_sync_at": "2026-06-27T22:15:32",
    "last_status": "ok",
    "fail_count": 0,
    "cooldown_until": null,
    "fields": {
      "nav": "ok",
      "info": "ok",
      "holdings": "ok",
      "manager": "ok",
      "performance": "ok",
      "flows": "ok",
      "news": "ok"
    }
  },
  "001717": {
    "last_sync_at": "2026-06-26T22:08:11",
    "last_status": "partial",
    "fail_count": 1,
    "cooldown_until": null,
    "fields": {
      "nav": "ok",
      "info": "failed",
      "holdings": "ok",
      "manager": "ok",
      "performance": "ok",
      "flows": "ok",
      "news": "ok"
    }
  }
}
```

`last_status` 取值：`ok`（全部成功）/ `partial`（部分字段失败）/ `failed`（整只失败）。

### 5.3 `universe_config.json` 默认值

```json
{
  "daily_quota": 200,
  "fund_interval_min": 1.5,
  "fund_interval_max": 3.5,
  "field_interval_min": 0.5,
  "field_interval_max": 1.5,
  "fail_cooldown_days": 7,
  "max_fail_count": 3,
  "news_lookback_days": 90,
  "nav_lookback_days": 365
}
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `daily_quota` | 200 | 单次 `sync` 最多处理基金只数；用户可通过 `--quota` 覆盖 |
| `fund_interval_min/max` | 1.5 / 3.5 | 单只基金完成后到下一只基金前的随机 sleep 区间（秒） |
| `field_interval_min/max` | 0.5 / 1.5 | 单只基金内 7 个字段之间的随机 sleep 区间（秒） |
| `fail_cooldown_days` | 7 | 连续失败达到阈值后进入冷却的天数 |
| `max_fail_count` | 3 | 触发冷却所需的连续失败次数 |
| `news_lookback_days` | 90 | 拉取新闻回溯天数 |
| `nav_lookback_days` | 365 | 拉取净值回溯天数 |

---

## 6. 调度策略

| 行为 | 规则 |
|------|------|
| **优先级** | sync 队列按 `last_sync_at` 升序 → 最久没采的优先 |
| **配额** | 单次 `sync` 最多处理 `daily_quota` 只；超额顺延到次日（进度文件中不存在的基金视作 `last_sync_at=null`，排在最前） |
| **失败冷却** | 连续失败 `max_fail_count=3` 次的基金进入冷却期（`fail_cooldown_days=7`），到期自动恢复 |
| **限流** | 每只基金调用 7 个字段之间随机 sleep `field_interval_min~max`；单只完成后额外 sleep `fund_interval_min~max` |
| **降级** | 单个字段失败不影响其他字段，标记为 `partial`；仅当整只 7 个字段全部失败才标记 `failed` |
| **原子性** | 每只基金 7 个字段全部写完后才更新 `universe_progress.json`，断电也不会产生半成品进度 |
| **强制覆盖** | `update <code>` 与 `--force` 跳过冷却期与今日配额 |
| **空跑保护** | 若 `sync` 时 `fund_list.json` 不存在，先自动调用 `init` 逻辑拉取列表，避免静默失败 |

### 6.1 sync 流程伪代码

```python
def sync(quota=None, force=False):
    config = load_config()
    quota = quota or config["daily_quota"]
    funds = load_fund_list()              # 仅含 is_offexchange=True
    progress = load_progress()

    # 1. 过滤出待采队列
    candidates = []
    for f in funds:
        rec = progress.get(f["code"], {})
        if not force and is_in_cooldown(rec, config):
            continue
        candidates.append((f, rec.get("last_sync_at") or ""))
    candidates.sort(key=lambda x: x[1])    # 按 last_sync_at 升序

    # 2. 按配额执行
    picked = candidates[:quota]
    for fund, _ in picked:
        result = sync_single_fund(fund["code"], config)
        update_progress(fund["code"], result)

    # 3. 返回摘要
    return summarize_results(picked)
```

---

## 7. 测试与验收标准

### 7.1 单元测试

| 测试文件 | 覆盖点 |
|---------|--------|
| `tests/unit/test_fund_universe_init.py` | `init` 拉取列表 → 写入 `fund_list.json`；验证 `is_offexchange` 过滤后只含场外；主备端点切换 |
| `tests/unit/test_fund_universe_sync.py` | `sync --quota 5` → 验证 5 只基金被采集 + 进度更新；mock 所有 HTTP 接口避免真实请求 |
| `tests/unit/test_fund_universe_cooldown.py` | 连续失败 3 次 → 验证 `cooldown_until` 设置正确；冷却期内被跳过 |
| `tests/unit/test_fund_universe_update.py` | `update <code>` 跳过冷却期强制执行；进度被覆盖 |
| `tests/unit/test_fund_universe_partial.py` | 模拟某只基金 1 个字段失败 → 验证整只标 `partial`，其余字段落盘仍完整 |
| `tests/unit/test_fund_universe_config.py` | 配置文件读取/合并默认值；参数校验 |

### 7.2 E2E 集成测试

`tests/e2e/test_fund_universe_e2e.py`：

1. `init` 后断言 `fund_list.json` 长度 > 5000。
2. `sync --quota 3 --force` 后断言 `data/funds/<code>/` 下 7 类文件均存在。
3. `status` 输出含完整进度统计字段。
4. 真实接口允许失败（标记 skipped），但 CLI 退出码行为必须正确。

### 7.3 验收标准

- 所有单元测试通过（mock 真实接口）。
- E2E 测试在真实接口上成功执行 3 只基金采集。
- `init` 在 30 秒内完成（依赖天天基金列表接口响应）。
- 单只基金 `sync` 全 7 字段 ≤ 15 秒（含 sleep）。
- 退出码语义与设计一致（0/1/2）。
- `pytest -v` 全部测试 < 60 秒。

---

## 8. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 天天基金列表接口字段格式变更 | 主备双端点；解析失败时降级 |
| 基金接口 IP 限流 | 随机 sleep 区间 + 单日配额；连续失败进入冷却 |
| 全市场基金数 < 8000（数据源覆盖不全） | 在 `status` 与文档中明确说明；允许用户后续扩展备用端点 |
| 用户每日手动触发误传 `--quota 10000` 触发限流 | 默认 200 + 文档说明上限建议 |
| `fund_data.py` 落盘文件名变化 | 本设计文档硬约束文件名格式与现有完全一致，破坏需走变更流程 |

---

## 9. 后续扩展（不在本次范围）

- 多并发 worker（当前明确不做）
- 场内 ETF/LOF 单独采集（当前明确不做）
- 数据质量审计（参考 stock-analysis 的 `data_quality_auditor`）
- 失败重试指数退避（当前固定冷却 7 天）
- 与 `docs/universe-collector-design.md` 合并章节（实现完成后补一节"基金调度器对称设计"）

---

## 10. 设计决策记录

| 决策点 | 选择 | 备选 | 理由 |
|--------|------|------|------|
| 包装脚本 | ❌ 不提供 | ✅ .bat + .sh | 用户明确表示由第三方调度器直接调用 CLI |
| Trae 定时任务 | ❌ 不配置 | ✅ 提供 cron 模板 | 用户表示人工自建 |
| 基金范围 | 仅场外开放式 | 含场内 / 全公募 | 与用户原始需求一致 |
| 采集字段 | 全 7 字段 | 仅净值 | 用户指定"全字段" |
| 调度能力 | 配额 + 断点 | + 失败冷却 + 限流 | 用户基础需求；冷却与限流作为基础安全措施默认加上 |
| 默认 daily_quota | 200 | 100 / 500 | 基金接口比股票慢 1.5~2 倍，留保守值 |
| 退出码 | 0/1/2 三级 | 仅 0/1 | 让调度器可区分部分失败与致命错误 |
| 进度文件位置 | `data/funds/_meta/` | `logs/` | 与 A 股 `data/stocks/_meta/` 对称 |