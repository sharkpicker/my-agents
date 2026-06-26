#!/usr/bin/env python3
"""A股数据获取 CLI 工具.

供各智能体通过命令行调用获取A股数据。
数据自动保存到项目 data/ 目录下。

使用方式:
    python -m data_tools.cli kline 000001 --start 2025-01-01 --end 2025-06-01
    python -m data_tools.cli indicator 000001 rsi --date 2025-06-01
    python -m data_tools.cli fundamentals 000001
    python -m data_tools.cli news 000001 --start 2025-05-01 --end 2025-06-01
    python -m data_tools.cli dragon-tiger 000001
    python -m data_tools.cli lockup 000001
    python -m data_tools.cli northbound
    python -m data_tools.cli hot-stocks
    python -m data_tools.cli concept 000001
    python -m data_tools.cli balance-sheet 000001
    python -m data_tools.cli income-statement 000001
    python -m data_tools.cli cashflow 000001
    python -m data_tools.cli insider 000001
    python -m data_tools.cli forecast 000001
    python -m data_tools.cli global-news
"""

import sys
import argparse
from datetime import datetime

from .stock_data import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_income_statement,
    get_balance_sheet,
    get_cashflow,
    get_news,
    get_global_news,
    get_dragon_tiger,
    get_lockup,
    get_northbound_flow,
    get_hot_stocks,
    get_concept_blocks,
    get_insider_transactions,
    get_profit_forecast,
    get_fund_flow,
    get_data_dir,
)
from . import universe


def cmd_kline(args):
    """获取K线数据."""
    result = get_stock_data(
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
    )
    print(result)


def cmd_indicator(args):
    """获取技术指标."""
    result = get_indicators(
        symbol=args.symbol,
        indicator=args.indicator,
        curr_date=args.date,
        look_back_days=args.days,
    )
    print(result)


def cmd_fundamentals(args):
    """获取基本面数据."""
    result = get_fundamentals(ticker=args.symbol)
    print(result)


def cmd_news(args):
    """获取个股新闻."""
    result = get_news(
        ticker=args.symbol,
        start_date=args.start,
        end_date=args.end,
    )
    print(result)


def cmd_global_news(args):
    """获取全球财经新闻."""
    result = get_global_news(limit=args.limit)
    print(result)


def cmd_dragon_tiger(args):
    """获取龙虎榜数据."""
    result = get_dragon_tiger(ticker=args.symbol, days=args.days)
    print(result)


def cmd_lockup(args):
    """获取限售解禁数据."""
    result = get_lockup(ticker=args.symbol)
    print(result)


def cmd_northbound(args):
    """获取北向资金数据."""
    result = get_northbound_flow()
    print(result)


def cmd_hot_stocks(args):
    """获取热门股数据."""
    result = get_hot_stocks()
    print(result)


def cmd_concept(args):
    """获取概念板块数据."""
    result = get_concept_blocks(ticker=args.symbol)
    print(result)


def cmd_balance_sheet(args):
    """获取资产负债表."""
    result = get_balance_sheet(ticker=args.symbol, freq=args.freq)
    print(result)


def cmd_income_statement(args):
    """获取利润表."""
    result = get_income_statement(ticker=args.symbol, freq=args.freq)
    print(result)


def cmd_cashflow(args):
    """获取现金流量表."""
    result = get_cashflow(ticker=args.symbol, freq=args.freq)
    print(result)


def cmd_insider(args):
    """获取内部人/股东交易数据."""
    result = get_insider_transactions(ticker=args.symbol)
    print(result)


def cmd_forecast(args):
    """获取盈利预测数据."""
    result = get_profit_forecast(ticker=args.symbol)
    print(result)


def cmd_fund_flow(args):
    """获取资金流向数据."""
    result = get_fund_flow(ticker=args.symbol, include_history=args.history)
    print(result)


def cmd_data_dir(args):
    """显示数据存储目录."""
    print(f"数据存储目录: {get_data_dir()}")


def cmd_universe_init(args):
    """初始化全量采集：拉取股票列表."""
    count = universe.refresh_stock_list()
    if count > 0:
        print(f"初始化成功，共获取 {count} 只A股")
    else:
        print("获取股票列表失败")
        sys.exit(1)


def cmd_universe_status(args):
    """查看采集进度."""
    status = universe.get_status()
    print(universe.format_status(status))


def cmd_universe_sync(args):
    """执行一次增量采集."""
    result = universe.sync(quota=args.quota, force=args.force)
    if result["status"] == "error":
        print(f"错误: {result.get('message')}")
        sys.exit(1)
    elif result["status"] == "skipped":
        print(f"跳过: {result.get('message')}")
    else:
        print(f"采集完成: 共 {result['total']} 只，成功 {result['success']}，失败 {result['failed']}")
        if "global" in result:
            g = result["global"]
            print(f"全局数据: 新闻={g.get('global_news')} 热门={g.get('hot_stocks')} 北向={g.get('northbound')}")


def cmd_universe_update(args):
    """强制更新单只股票."""
    results = universe.update_single(args.symbol)
    ok = sum(1 for v in results.values() if v in ("ok", "empty", "partial"))
    fail = sum(1 for v in results.values() if v == "failed")
    print(f"{args.symbol} 更新完成: 成功 {ok} 项，失败 {fail} 项")
    for k, v in results.items():
        print(f"  {k}: {v}")


def cmd_universe_refresh(args):
    """刷新股票列表."""
    count = universe.refresh_stock_list()
    print(f"股票列表已刷新，共 {count} 只")


def main():
    parser = argparse.ArgumentParser(
        description="A股数据获取工具 - 供智能体调用",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # kline
    p = subparsers.add_parser("kline", help="获取K线数据")
    p.add_argument("symbol", help="股票代码 (6位数字)")
    p.add_argument("--start", required=True, help="开始日期 YYYY-MM-DD")
    p.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
    p.set_defaults(func=cmd_kline)

    # indicator
    p = subparsers.add_parser("indicator", help="获取技术指标")
    p.add_argument("symbol", help="股票代码")
    p.add_argument("indicator", help="指标名称 (rsi/macd/close_50_sma等)")
    p.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                   help="当前日期 YYYY-MM-DD")
    p.add_argument("--days", type=int, default=60, help="回看天数")
    p.set_defaults(func=cmd_indicator)

    # fundamentals
    p = subparsers.add_parser("fundamentals", help="获取基本面数据")
    p.add_argument("symbol", help="股票代码")
    p.set_defaults(func=cmd_fundamentals)

    # news
    p = subparsers.add_parser("news", help="获取个股新闻")
    p.add_argument("symbol", help="股票代码")
    p.add_argument("--start", required=True, help="开始日期 YYYY-MM-DD")
    p.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
    p.set_defaults(func=cmd_news)

    # global-news
    p = subparsers.add_parser("global-news", help="获取全球财经新闻")
    p.add_argument("--limit", type=int, default=15, help="新闻条数")
    p.set_defaults(func=cmd_global_news)

    # dragon-tiger
    p = subparsers.add_parser("dragon-tiger", help="获取龙虎榜数据")
    p.add_argument("symbol", help="股票代码")
    p.add_argument("--days", type=int, default=5, help="回看天数")
    p.set_defaults(func=cmd_dragon_tiger)

    # lockup
    p = subparsers.add_parser("lockup", help="获取限售解禁数据")
    p.add_argument("symbol", help="股票代码")
    p.set_defaults(func=cmd_lockup)

    # northbound
    p = subparsers.add_parser("northbound", help="获取北向资金数据")
    p.set_defaults(func=cmd_northbound)

    # hot-stocks
    p = subparsers.add_parser("hot-stocks", help="获取热门涨停股")
    p.set_defaults(func=cmd_hot_stocks)

    # concept
    p = subparsers.add_parser("concept", help="获取概念板块")
    p.add_argument("symbol", help="股票代码")
    p.set_defaults(func=cmd_concept)

    # balance-sheet
    p = subparsers.add_parser("balance-sheet", help="获取资产负债表")
    p.add_argument("symbol", help="股票代码")
    p.add_argument("--freq", default="quarterly", help="频率: quarterly/annual")
    p.set_defaults(func=cmd_balance_sheet)

    # income-statement
    p = subparsers.add_parser("income-statement", help="获取利润表")
    p.add_argument("symbol", help="股票代码")
    p.add_argument("--freq", default="quarterly", help="频率: quarterly/annual")
    p.set_defaults(func=cmd_income_statement)

    # cashflow
    p = subparsers.add_parser("cashflow", help="获取现金流量表")
    p.add_argument("symbol", help="股票代码")
    p.add_argument("--freq", default="quarterly", help="频率: quarterly/annual")
    p.set_defaults(func=cmd_cashflow)

    # insider
    p = subparsers.add_parser("insider", help="获取股东/内部人交易数据")
    p.add_argument("symbol", help="股票代码")
    p.set_defaults(func=cmd_insider)

    # forecast
    p = subparsers.add_parser("forecast", help="获取一致预期/盈利预测")
    p.add_argument("symbol", help="股票代码")
    p.set_defaults(func=cmd_forecast)

    # fund-flow
    p = subparsers.add_parser("fund-flow", help="获取资金流向数据")
    p.add_argument("symbol", help="股票代码")
    p.add_argument("--no-history", dest="history", action="store_false",
                   default=True, help="不包含历史数据")
    p.set_defaults(func=cmd_fund_flow)

    # data-dir
    p = subparsers.add_parser("data-dir", help="显示数据存储目录")
    p.set_defaults(func=cmd_data_dir)

    # universe - 全量A股采集
    pu = subparsers.add_parser("universe", help="全量A股数据采集管理")
    universe_sub = pu.add_subparsers(dest="universe_cmd", help="可用子命令")

    # universe init
    p2 = universe_sub.add_parser("init", help="初始化：拉取股票列表")
    p2.set_defaults(func=cmd_universe_init)

    # universe status
    p2 = universe_sub.add_parser("status", help="查看采集进度")
    p2.set_defaults(func=cmd_universe_status)

    # universe sync
    p2 = universe_sub.add_parser("sync", help="执行一次增量采集")
    p2.add_argument("--quota", type=int, default=None, help="今日采集配额（覆盖配置）")
    p2.add_argument("--force", action="store_true", help="强制执行，忽略今日已运行标记")
    p2.set_defaults(func=cmd_universe_sync)

    # universe update
    p2 = universe_sub.add_parser("update", help="强制更新单只股票")
    p2.add_argument("symbol", help="股票代码")
    p2.set_defaults(func=cmd_universe_update)

    # universe refresh-list
    p2 = universe_sub.add_parser("refresh-list", help="刷新股票列表")
    p2.set_defaults(func=cmd_universe_refresh)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
