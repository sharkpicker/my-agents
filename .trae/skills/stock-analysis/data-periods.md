# 数据获取规范

所有 subagent 必须严格按本规范拉取数据。日期以当前日期为基准向前推算。

**当前日期计算(PowerShell)**:
```powershell
(Get-Date).ToString("yyyy-MM-dd")
```

---

## A. 股票数据获取周期

| 数据类型 | 获取周期 | 命令模板 | 示例(假设今天 2026-06-27) |
|----------|----------|----------|---------------------------|
| **K线数据** | **近 2 年**(约 480 个交易日) | `python -m data_tools.cli kline <code> --start <2年前> --end <今天>` | `kline 000001 --start 2024-06-27 --end 2026-06-27` |
| **技术指标** | **近 120 天** | `python -m data_tools.cli indicator <code> <指标> --date <今天> --days 120` | `indicator 000001 rsi --date 2026-06-27 --days 120` |
| **个股新闻** | **近 3 个月** | `python -m data_tools.cli news <code> --start <3月前> --end <今天>` | `news 000001 --start 2026-03-27 --end 2026-06-27` |
| **财报数据** | **近 2 年季度**(8 季) | `python -m data_tools.cli income-statement <code> --freq quarterly` | `income-statement 000001 --freq quarterly` |
| **资产负债表** | **近 2 年季度** | `python -m data_tools.cli balance-sheet <code> --freq quarterly` | `balance-sheet 000001 --freq quarterly` |
| **现金流量表** | **近 2 年季度** | `python -m data_tools.cli cashflow <code> --freq quarterly` | `cashflow 000001 --freq quarterly` |
| **龙虎榜** | **近 6 个月** | `python -m data_tools.cli dragon-tiger <code> --days 180` | `dragon-tiger 000001 --days 180` |
| **限售解禁** | **当前快照** | `python -m data_tools.cli lockup <code>` | `lockup 000001` |
| **股东研究** | **当前快照** | `python -m data_tools.cli insider <code>` | `insider 000001` |
| **基本面快照** | **当前快照** | `python -m data_tools.cli fundamentals <code>` | `fundamentals 000001` |
| **北向资金** | **当前快照** | `python -m data_tools.cli northbound` | `northbound` |
| **热门股** | **当前快照** | `python -m data_tools.cli hot-stocks` | `hot-stocks` |
| **概念板块** | **当前快照** | `python -m data_tools.cli concept <code>` | `concept 000001` |
| **全球新闻** | **当前快照** | `python -m data_tools.cli global-news --limit 30` | `global-news --limit 30` |
| **一致预期** | **当前快照** | `python -m data_tools.cli forecast <code>` | `forecast 000001` |

**支持的技术指标**:`rsi`, `macd`, `macds`, `macdh`, `close_50_sma`, `close_200_sma`, `close_10_ema`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`, `mfi`

---

## B. 基金数据获取周期

| 数据类型 | 获取周期 | 命令模板 | 示例 |
|----------|----------|----------|------|
| **净值数据** | **近 1 年**(约 240 个交易日) | `python -m data_tools.cli fund nav <code> --start <1年前> --end <今天>` | `fund nav 001717 --start 2025-06-27 --end 2026-06-27` |
| **业绩表现** | **当前快照** | `python -m data_tools.cli fund performance <code>` | `fund performance 001717` |
| **基金概况** | **当前快照** | `python -m data_tools.cli fund info <code>` | `fund info 001717` |
| **基金经理** | **当前快照** | `python -m data_tools.cli fund manager <code>` | `fund manager 001717` |
| **重仓股** | **当前快照** | `python -m data_tools.cli fund holdings <code>` | `fund holdings 001717` |
| **份额变动** | **近 8 期**(约 2 年季度报告) | `python -m data_tools.cli fund flows <code>` | `fund flows 001717` |
| **基金新闻** | **近 3 个月** | `python -m data_tools.cli fund news <code> --start <3月前> --end <今天>` | `fund news 001717 --start 2026-03-27 --end 2026-06-27` |
| **全球新闻** | **当前快照** | `python -m data_tools.cli fund global-news <code> --limit 30` | `fund global-news 001717 --limit 30` |
| **路由探测** | — | `python -m data_tools.cli fund detect <code>` | `fund detect 001717` |

---

## C. 组合数据获取策略

- **核心数据**: 对每只基金调用 `fund info / fund performance / fund manager / fund holdings / fund flows`
- **数据量控制**: 组合 > 10 只基金时,只对代表性标的(最大 5 + 最差 2 + 风险最高 1)拉取完整数据,其余只拉 `fund info` 和 `fund performance`
- **保存路径**: 数据按代码分散到 `data/funds/<code>/`

---

## D. 数据落盘规则(铁律 6)

**所有 subagent 拉取的数据必须先通过 `run_command` 调用 `data_tools.cli` 命令,数据会自动保存到 `data/` 目录。subagent 然后通过 `read_file` 读取已保存的数据文件进行分析。**

- A 股股票: `data/stocks/<代码>/`
- 公募基金: `data/funds/<代码>/`
- 全市场元数据: `data/stocks/_meta/`

**禁止**:
- subagent 在调用命令后直接基于 stdout 输出写报告(必须先落盘)
- 主对话绕过 subagent 直接拉数据并写"分析报告"(违反铁律 1/2)

---

## E. 日期计算(PowerShell)

```powershell
# 今天
(Get-Date).ToString("yyyy-MM-dd")

# 2 年前(用于 K 线)
(Get-Date).AddYears(-2).ToString("yyyy-MM-dd")

# 1 年前(用于基金净值)
(Get-Date).AddYears(-1).ToString("yyyy-MM-dd")

# 3 个月前(用于新闻)
(Get-Date).AddMonths(-3).ToString("yyyy-MM-dd")

# 6 个月前(用于龙虎榜/解禁)
(Get-Date).AddMonths(-6).ToString("yyyy-MM-dd")
```

---

## F. 依赖安装

首次使用前需安装依赖:

```bash
pip install -r requirements.txt
```

依赖包:`mootdx`, `pandas`, `requests`, `stockstats`, `python-dateutil`
