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
