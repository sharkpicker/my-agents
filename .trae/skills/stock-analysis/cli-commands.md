# CLI 工具命令清单

`data_tools.cli` 完整命令参考。所有命令在项目根目录 `d:\01_coding\my_agents` 下执行。

---

## 工具查看

```bash
# 查看所有子命令
python -m data_tools.cli --help

# 查看数据保存目录
python -m data_tools.cli data-dir
```

---

## 股票命令

### 行情与技术指标

```bash
python -m data_tools.cli kline <股票代码> --start <YYYY-MM-DD> --end <YYYY-MM-DD>
python -m data_tools.cli indicator <股票代码> <指标名> --date <YYYY-MM-DD> --days <N>
```

**支持的技术指标**:`rsi`, `macd`, `macds`, `macdh`, `close_50_sma`, `close_200_sma`, `close_10_ema`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`, `mfi`

### 基本面与财报

```bash
python -m data_tools.cli fundamentals <股票代码>
python -m data_tools.cli balance-sheet <股票代码> --freq quarterly
python -m data_tools.cli income-statement <股票代码> --freq quarterly
python -m data_tools.cli cashflow <股票代码> --freq quarterly
python -m data_tools.cli forecast <股票代码>
```

### 新闻与资讯

```bash
python -m data_tools.cli news <股票代码> --start <YYYY-MM-DD> --end <YYYY-MM-DD>
python -m data_tools.cli global-news --limit 20
```

### 资金与龙虎榜

```bash
python -m data_tools.cli dragon-tiger <股票代码> --days 180
python -m data_tools.cli northbound
python -m data_tools.cli hot-stocks
python -m data_tools.cli concept <股票代码>
```

### 股东与解禁

```bash
python -m data_tools.cli lockup <股票代码>
python -m data_tools.cli insider <股票代码>
```

---

## 基金命令

### 路由探测

```bash
python -m data_tools.cli fund detect <代码>
```

**输出格式**:
- `FUND|<基金名称>` → 这是基金
- `STOCK` → 这是股票

### 净值与业绩

```bash
python -m data_tools.cli fund nav <基金代码> --start <YYYY-MM-DD> --end <YYYY-MM-DD>
python -m data_tools.cli fund performance <基金代码>
```

### 概况与经理

```bash
python -m data_tools.cli fund info <基金代码>
python -m data_tools.cli fund manager <基金代码>
```

### 重仓股与份额

```bash
python -m data_tools.cli fund holdings <基金代码>
python -m data_tools.cli fund flows <基金代码>
```

### 新闻

```bash
python -m data_tools.cli fund news <基金代码> --start <YYYY-MM-DD> --end <YYYY-MM-DD>
python -m data_tools.cli fund global-news <基金代码> --limit 20
```

### 基金全量库(fund_universe)

> 用于 Step 5.5:从国内场外开放式基金全量库中筛选补/换候选。

```bash
# 初始化(拉取全部基金列表到 _meta/fund_list.json)
python -m data_tools.cli fund universe init

# 查看采集进度
python -m data_tools.cli fund universe status

# 增量同步(默认遵守每日配额)
python -m data_tools.cli fund universe sync --quota 200

# 强制更新单只基金
python -m data_tools.cli fund universe update <基金代码>

# 刷新基金列表(主动重拉)
python -m data_tools.cli fund universe refresh-list

# 清理脏 type + 补全 ftype(基金类型,显著提升 screener 评分质量)
python -m data_tools.cli fund universe repair --dry-run          # 仅统计
python -m data_tools.cli fund universe repair --batch-size 50    # 试补 50 只
python -m data_tools.cli fund universe repair                   # 全量补(慢,推荐后台)
python -m data_tools.cli fund universe repair --force           # 强制清空 type 字段
```

**fund_list.json 字段约定**:
- `code` / `name`:基金代码 / 简称(主端点直接拿)
- `type`:历史字段,主端点误填过累计净值数字(脏)。**已不再被主端点填入**;只在 `repair` 清理后保留为 `""`
- `ftype`:天天基金 F10 概况页的"基金类型"(如"混合型-灵活"、"指数型-股票"、 "QDII"),`repair` 阶段补全
- `is_offexchange`:是否场外基金(主端点过滤后写入)

**screener 评分规则**(优先用 `ftype`):
- 名称含品类关键词 → +50
- `ftype` 与品类匹配 → +20
- 用户偏好品类 → +10
- 用户排除品类 → -100
- 脏 `type` 字段(数字)不参与评分,会在报告中显式标注"FTYPE 脏数据"

---

## 组合命令(portfolio) ⭐ C-1/C-3 增强

> 用于 Step 0.5 / 2.6 / 5.5:从用户风险偏好到目标资产配置再到候选基金补/换的端到端链路。

### 用户偏好 → 目标资产配置

```bash
# 保存用户偏好(落盘 prefs.json)
python -m data_tools.cli portfolio prefs save \
  --user-id default --risk-level 2 --horizon long \
  --preferred "index,sector" --excluded "alternative" \
  --equity-override 0.25

# 展示偏好与目标配置
python -m data_tools.cli portfolio prefs show --user-id default

# argparse 等价:
python -m data_tools.cli portfolio prefs \
  --user-id default --risk-level 2 --horizon long \
  --preferred "index,sector" --excluded "alternative" --save
```

### 候选基金筛选(从场外公募全量库)

```bash
python -m data_tools.cli screener replacement \
  --categories "bond,index,overseas" \
  --excluded-codes "007466,015143" \
  --preferred "index" --excluded "alternative" \
  --per-category 5 --risk-level 2

# argparse 等价:
python -m data_tools.cli portfolio screener \
  --categories "bond,index,overseas" --per-category 5 --risk-level 2
```

### 端到端再平衡方案(gap + 候选基金)

```bash
python -m data_tools.cli portfolio rebalance \
  --positions "007466:7920.75,015143:1779.64,014767:476.11:conservative" \
  --risk-level 2 --format md

# argparse 等价:
python -m data_tools.cli portfolio rebalance \
  --positions "007466:7920.75,015143:1779.64,014767:476.11:conservative" \
  --risk-level 2 --format md
```

### 传统 3 个(集中度/重叠/穿透)

```bash
python -m data_tools.cli portfolio concentration --positions "007466:7920.75,015143:1779.64"
python -m data_tools.cli portfolio overlap --fund-holdings "007466:000001" --direct-stocks "000001:10000"
python -m data_tools.cli portfolio balance --holdings "007466:7920.75:fund:0.3"
```

**闭集关键词参考**:
- `cash` 货币/现金管理
- `bond` 纯债/短债/信用债/债基
- `conservative` 固收+/偏债/二级债基
- `balanced` 平衡/均衡/灵活配置
- `equity` 主动/偏股/股票型
- `index` 指数/联接/增强/中证/沪深300/红利
- `sector` 医药/科技/新能源/消费/半导体/军工/银行/券商
- `overseas` QDII/纳斯达克/港股/海外
- `alternative` REITs/商品/黄金

详细映射见 `data_tools/portfolio_prefs.CATEGORY_KEYWORDS`。

---

## 数据源覆盖

| 数据源 | 接口类型 | 覆盖内容 |
|--------|----------|----------|
| mootdx (通达信) | TCP | K线、财务快照、F10股东研究 |
| 腾讯财经 | HTTP | 实时报价、PE/PB/市值、换手率 |
| 东方财富 | HTTP | 龙虎榜、限售解禁、个股搜索、7x24资讯、基金净值/概况/重仓股/经理/业绩 |
| 新浪财经 | HTTP | K线备用、三大财报(资产负债表/利润表/现金流量表) |
| 同花顺 | HTTP | 一致预期EPS、涨停热门股、北向资金 |
| 财联社 | HTTP | 全球财经快讯 |
| 百度股市通 | HTTP | 概念板块、行业分类 |
| 天天基金 | HTTP | 基金净值/概况/重仓股/经理/业绩/份额变动 |

---

## 常见错误处理

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `ModuleNotFoundError: No module named 'data_tools'` | 未在项目根目录运行 | `cd d:\01_coding\my_agents` 后重试 |
| 接口超时 | 网络问题 | 等待后重试,或标注 `[数据缺失]` 继续 |
| 返回空数据 | 数据源无该标的 | 尝试 `fund detect` 确认代码正确性 |
| 基金代码错误 | 用了股票代码 | 用 `fund detect <6位>` 探测确认 |

---

## 快速参考

**单只基金完整数据采集**:
```bash
CODE=001717
python -m data_tools.cli fund info $CODE
python -m data_tools.cli fund performance $CODE
python -m data_tools.cli fund manager $CODE
python -m data_tools.cli fund holdings $CODE
python -m data_tools.cli fund flows $CODE
python -m data_tools.cli fund nav $CODE --start $(Get-Date).AddYears(-1).ToString("yyyy-MM-dd") --end $(Get-Date).ToString("yyyy-MM-dd")
python -m data_tools.cli fund news $CODE --start $(Get-Date).AddMonths(-3).ToString("yyyy-MM-dd") --end $(Get-Date).ToString("yyyy-MM-dd")
```

**单只股票完整数据采集**:
```bash
CODE=000001
python -m data_tools.cli kline $CODE --start $(Get-Date).AddYears(-2).ToString("yyyy-MM-dd") --end $(Get-Date).ToString("yyyy-MM-dd")
python -m data_tools.cli indicator $CODE rsi --date $(Get-Date).ToString("yyyy-MM-dd") --days 120
python -m data_tools.cli indicator $CODE macd --date $(Get-Date).ToString("yyyy-MM-dd") --days 120
python -m data_tools.cli fundamentals $CODE
python -m data_tools.cli income-statement $CODE --freq quarterly
python -m data_tools.cli balance-sheet $CODE --freq quarterly
python -m data_tools.cli cashflow $CODE --freq quarterly
python -m data_tools.cli news $CODE --start $(Get-Date).AddMonths(-3).ToString("yyyy-MM-dd") --end $(Get-Date).ToString("yyyy-MM-dd")
```
