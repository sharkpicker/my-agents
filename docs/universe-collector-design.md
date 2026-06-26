# 全量A股数据采集系统设计文档

> 设计日期：2026-06-26
> 方案：方案A - 轻量级采集器（最小化改造）

---

## 1. 设计目标

在不改动现有 `stock_data.py` 和智能体的前提下，新增全量A股数据的增量式采集能力：

- ✅ **完全兼容**：现有数据格式、CLI命令、智能体调用方式全部不变
- ✅ **增量采集**：每天采集一部分，避免触发数据源封禁
- ✅ **进度追踪**：自动记录每只股票每个数据类型的更新时间
- ✅ **失败重试**：失败自动标记，下次优先重试
- ✅ **防封保护**：复用现有防封机制 + 批量级限流

---

## 2. 整体架构

```
my_agents/
├── data_tools/
│   ├── __init__.py
│   ├── stock_data.py      # 现有，不动
│   ├── cli.py             # 现有，增加 universe 子命令组
│   └── universe.py        # 【新增】全量采集调度模块
├── data/
│   ├── _meta/
│   │   ├── stock_list.json           # 全量股票列表
│   │   ├── universe_progress.json    # 采集进度追踪
│   │   └── universe_config.json      # 采集配置
│   └── <股票代码>/...                # 现有结构，完全不变
└── docs/
    └── universe-collector-design.md  # 本文档
```

### 设计原则

1. `stock_data.py` 零改动 - 所有现有接口保持不变
2. `universe.py` 只负责调度 - 数据获取全部复用现有函数
3. 智能体零感知 - 数据格式、存储路径完全一致
4. CLI 向后兼容 - 新增 `universe` 子命令组，不影响现有命令

---

## 3. 数据类型与更新频率

### 个股数据（每只股票）

| 数据类型 | 函数 | 更新频率 | 失败判定 |
|----------|------|----------|----------|
| K线数据 | `get_stock_data` | 每日 | 返回<1行 或 含"失败/出错" |
| 基本面 | `get_fundamentals` | 每日 | 含"失败/出错"字样 |
| 技术指标 | `get_indicators` (RSI/MACD) | 每日 | 含"失败/出错"字样 |
| 资金流向 | `get_fund_flow` | 每日 | 实时+历史都无数据 |
| 个股新闻 | `get_news` | 每日 | 0条=部分成功(可能真没新闻) |
| 龙虎榜 | `get_dragon_tiger` | 每日 | 没上榜=正常(empty) |
| 财报-利润表 | `get_income_statement` | 每周 | 返回<500字符 或 含"未找到/失败" |
| 财报-资产负债表 | `get_balance_sheet` | 每周 | 同上 |
| 财报-现金流量表 | `get_cashflow` | 每周 | 同上 |
| 盈利预测 | `get_profit_forecast` | 每周 | 含"失败/出错"字样 |
| 限售解禁 | `get_lockup` | 每周 | 无数据=正常(empty) |
| 股东研究 | `get_insider_transactions` | 每周 | 含"失败/出错"字样 |
| 概念板块 | `get_concept_blocks` | 每周 | 含"失败/出错"字样 |

### 全局数据（每天一份，非个股）

| 数据类型 | 函数 | 更新频率 |
|----------|------|----------|
| 全球新闻 | `get_global_news` | 每日 |
| 热门股 | `get_hot_stocks` | 每日 |
| 北向资金 | `get_northbound_flow` | 每日 |

---

## 4. 核心模块设计（`universe.py`）

### 4.1 配置文件

**文件**：`data/_meta/universe_config.json`

```json
{
  "daily_quota": 500,
  "stock_interval_min": 1,
  "stock_interval_max": 3,
  "fail_cooldown_days": 7,
  "max_fail_count": 3,
  "weekly_update_interval_days": 7
}
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `daily_quota` | 500 | 每日最多采集多少只股票 |
| `stock_interval_min` | 1 | 每只股票之间最小间隔（秒） |
| `stock_interval_max` | 3 | 每只股票之间最大间隔（秒） |
| `fail_cooldown_days` | 7 | 连续失败后的冷却天数 |
| `max_fail_count` | 3 | 连续失败多少次后进入冷却 |
| `weekly_update_interval_days` | 7 | 周频数据的更新间隔（天） |

**配置优先级**：CLI 参数 > 配置文件 > 默认值

### 4.2 股票列表

**文件**：`data/_meta/stock_list.json`

```json
[
  {"code": "000001", "name": "平安银行", "market": "sz", "industry": "银行"},
  {"code": "600519", "name": "贵州茅台", "market": "sh", "industry": "白酒"}
]
```

**刷新频率**：每周一次（新股少）

**数据来源**：东方财富（最稳定）

### 4.3 进度追踪

**文件**：`data/_meta/universe_progress.json`

```json
{
  "last_update": "2026-06-26",
  "daily_quota": 500,
  "stocks": {
    "000001": {
      "kline":         {"last": "2026-06-26", "status": "ok", "fail_count": 0},
      "fundamentals":  {"last": "2026-06-26", "status": "ok", "fail_count": 0},
      "indicators":    {"last": "2026-06-26", "status": "ok", "fail_count": 0},
      "fund_flow":     {"last": "2026-06-26", "status": "ok", "fail_count": 0},
      "news":          {"last": "2026-06-26", "status": "ok", "fail_count": 0},
      "dragon_tiger":  {"last": "2026-06-26", "status": "empty", "fail_count": 0},
      "financials":    {"last": "2026-06-22", "status": "ok", "fail_count": 0},
      "forecast":      {"last": "2026-06-22", "status": "ok", "fail_count": 0},
      "lockup":        {"last": "2026-06-19", "status": "empty", "fail_count": 0},
      "insider":       {"last": "2026-06-19", "status": "ok", "fail_count": 0},
      "concept":       {"last": "2026-06-19", "status": "ok", "fail_count": 0}
    }
  }
}
```

**状态说明**：
- `ok` - 成功获取
- `partial` - 部分成功（如资金流实时失败但历史有）
- `failed` - 完全失败
- `empty` - 无数据但正常（如没上龙虎榜）

**失败处理**：
- `fail_count` 连续失败计数
- 连续失败 ≥ 3 次 → 标记为问题股票，冷却 7 天
- 冷却期过后自动重试

### 4.4 调度算法

**每日 sync 流程**：

```
1. 加载股票列表和进度
2. 计算每只股票的"优先级分数"：
   - 失败的股票优先级最高
   - 其次是最久没更新的
   - 日频数据到期 vs 周频数据到期 → 日频优先
3. 按优先级排序，取前 daily_quota 只
4. 对每只股票：
   a. 检查哪些数据类型到期了（日频每天都到，周频7天到）
   b. 逐个采集到期的数据类型
   c. 更新进度和状态
   d. 随机等待 1~3 秒再下一只
5. 更新全局数据（全球新闻/热门股/北向资金）
6. 保存进度文件
```

---

## 5. CLI 命令设计

新增 `universe` 子命令组：

```bash
# 初始化（首次使用，拉取股票列表）
python -m data_tools.cli universe init

# 查看采集进度
python -m data_tools.cli universe status

# 执行一次采集（定时任务入口）
python -m data_tools.cli universe sync
#   --quota 200    今日采集配额（默认200）
#   --force        强制执行，忽略今日已运行标记

# 强制更新某只股票
python -m data_tools.cli universe update 000001

# 刷新股票列表
python -m data_tools.cli universe refresh-list
```

---

## 6. 防封与限流策略

分层保护，复用现有机制：

| 层级 | 机制 | 来源 |
|------|------|------|
| 请求级 | 指数退避重试（最多2次） | 已有 `_http_get` |
| 东财级 | 串行限流（1秒间隔+随机抖动）+ 会话复用 | 已有 `_em_get` |
| 个股级 | 每只股票之间随机间隔 1~3 秒 | 新增 |
| 每日级 | 最多 500 只/天 | 新增 |
| 失败级 | 连续失败3次 → 冷却7天 | 新增 |

---

## 7. 兼容性保证

### 对智能体

- ✅ 零改动，所有现有命令继续工作
- ✅ 数据文件格式、路径完全一致
- ✅ 先有缓存先读缓存，智能体查询更快

### 对 `stock_data.py`

- ✅ 零改动，所有函数签名不变
- ✅ `universe.py` 只调用，不修改
- ✅ 未来 `stock_data.py` 优化，采集器自动受益

---

## 8. 实施计划

### Phase 1：基础框架
- 新建 `universe.py` 模块
- 股票列表获取功能
- 进度追踪读写

### Phase 2：采集引擎
- 单只股票全量采集
- 批量调度算法
- 失败重试与冷却机制

### Phase 3：CLI 接入
- `universe` 子命令组
- 状态展示（友好的输出格式）
- 全局数据采集

### Phase 4：测试验证
- 小规模测试（10只股票）
- 进度验证、失败重试验证
- 智能体兼容性验证