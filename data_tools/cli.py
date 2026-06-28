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
import json
import argparse
from datetime import datetime

import click

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
    get_data_dir,
    get_stocks_dir,
    get_funds_dir,
    get_meta_dir,
)
from . import universe
from . import fund_data


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


def cmd_data_dir(args):
    """显示数据存储目录."""
    print(f"数据存储根目录: {get_data_dir()}")
    print(f"  - 股票目录: {get_stocks_dir()}")
    print(f"  - 基金目录: {get_funds_dir()}")
    print(f"  - 元数据:   {get_meta_dir()}")


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


# ---------------------------------------------------------------------------
# 基金数据命令
# ---------------------------------------------------------------------------

def cmd_fund_detect(args):
    """探测代码是否为基金（用于工作流路由）。"""
    is_fund, name = fund_data.is_fund_code(args.symbol)
    if is_fund:
        print(f"FUND|{name}")
    else:
        print("STOCK")


def cmd_fund_nav(args):
    """获取基金历史净值."""
    print(fund_data.get_fund_nav(args.symbol, args.start, args.end))


def cmd_fund_info(args):
    """获取基金概况."""
    print(fund_data.get_fund_info(args.symbol))


def cmd_fund_holdings(args):
    """获取基金重仓股."""
    print(fund_data.get_fund_holdings(args.symbol))


def cmd_fund_manager(args):
    """获取基金经理."""
    print(fund_data.get_fund_manager(args.symbol))


def cmd_fund_performance(args):
    """获取基金业绩表现."""
    print(fund_data.get_fund_performance(args.symbol))


def cmd_fund_flows(args):
    """获取基金份额/规模变动."""
    print(fund_data.get_fund_flows(args.symbol))


def cmd_fund_news(args):
    """获取基金相关新闻."""
    print(fund_data.get_fund_news(args.symbol, args.start, args.end))


def cmd_fund_global_news(args):
    """获取行业/主题财经新闻."""
    print(fund_data.get_fund_global_news(args.symbol, limit=args.limit))


def cmd_fund_universe_init(args):
    """初始化全量场外开放式基金采集：拉取并保存基金列表。"""
    from . import fund_universe
    try:
        count = fund_universe.refresh_fund_list()
    except Exception as e:
        print(f"初始化失败: {e}")
        sys.exit(1)
    print(f"初始化成功，共获取 {count} 只场外开放式基金")


def cmd_fund_universe_status(args):
    """查看场外开放式基金采集进度."""
    from . import fund_universe
    fund_universe.show_status()


def cmd_fund_universe_sync(args):
    """执行一次基金增量采集."""
    from . import fund_universe
    result = fund_universe.sync(quota=args.quota, force=args.force)
    if result["status"] == "error":
        print(f"错误: {result.get('message')}")
        sys.exit(1)
    if result["status"] == "partial":
        print(f"采集完成(部分失败): 共 {result['total']} 只，成功 {result['success']}，失败 {result['failed']}")
        sys.exit(2)
    print(f"采集完成: 共 {result['total']} 只，全部成功")


def cmd_fund_universe_update(args):
    """强制更新单只基金."""
    from . import fund_universe
    config = fund_universe.load_config()
    single = fund_universe.sync_single_fund(args.symbol, config)
    fund_universe.update_progress(
        args.symbol,
        last_status=single["last_status"],
        fail_count=single["fail_count"],
        fields=single["fields"],
        cooldown_until=single["cooldown_until"],
    )
    print(f"{args.symbol} 更新完成: {single['last_status']}")
    for k, v in single["fields"].items():
        print(f"  {k}: {v}")
    if single["last_status"] != "ok":
        sys.exit(2)


def cmd_fund_universe_refresh_list(args):
    """刷新基金列表."""
    from . import fund_universe
    count = fund_universe.refresh_fund_list()
    print(f"基金列表已刷新，共 {count} 只")


# ---------------------------------------------------------------------------
# Click 接口层（Phase 2 / Task 2.5: detect + portfolio）
# 与上方 argparse 入口并存,供测试与新子命令调用
# ---------------------------------------------------------------------------

from .portfolio import (
    calculate_concentration,
    detect_overlap,
    calculate_balance,
)


@click.group()
def cli():
    """A股数据/分析工具集 (Click 接口)."""
    pass


@cli.command()
@click.argument("text")
def detect(text: str):
    """识别用户输入类型(A/B/C-1/C-2/C-3)。"""
    from .detect import detect_input
    r = detect_input(text)
    click.echo(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))


@cli.group()
def fund():
    """基金数据获取工具集."""
    pass


@fund.group()
def universe():
    """全量场外开放式基金采集调度器."""
    pass


@universe.command("init")
def fund_universe_init():
    """初始化:拉取并保存场外开放式基金列表."""
    from . import fund_universe as fu
    count = fu.refresh_fund_list()
    click.echo(f"初始化成功，共获取 {count} 只场外开放式基金")


@universe.command("status")
def fund_universe_status():
    """查看场外开放式基金采集进度."""
    from . import fund_universe as fu
    fu.show_status()


@universe.command()
@click.option("--quota", type=int, default=None, help="今日采集配额（覆盖配置）")
@click.option("--force", is_flag=True, help="强制执行，忽略冷却中的基金")
def sync(quota, force):
    """执行一次场外开放式基金增量采集."""
    from . import fund_universe as fu
    result = fu.sync(quota=quota, force=force)
    if result["status"] == "error":
        click.echo(f"错误: {result.get('message')}")
        sys.exit(1)
    if result["status"] == "partial":
        click.echo(f"采集完成(部分失败): 共 {result['total']} 只，成功 {result['success']}，失败 {result['failed']}")
        sys.exit(2)
    click.echo(f"采集完成: 共 {result['total']} 只，全部成功")


@universe.command()
@click.argument("symbol")
def update(symbol):
    """强制更新单只基金."""
    from . import fund_universe as fu
    config = fu.load_config()
    single = fu.sync_single_fund(symbol, config)
    fu.update_progress(
        symbol,
        last_status=single["last_status"],
        fail_count=single["fail_count"],
        fields=single["fields"],
        cooldown_until=single["cooldown_until"],
    )
    click.echo(f"{symbol} 更新完成: {single['last_status']}")
    for k, v in single["fields"].items():
        click.echo(f"  {k}: {v}")
    if single["last_status"] != "ok":
        sys.exit(2)


@universe.command("refresh-list")
def refresh_list():
    """刷新基金列表."""
    from . import fund_universe as fu
    count = fu.refresh_fund_list()
    click.echo(f"基金列表已刷新，共 {count} 只")


@cli.group()
def portfolio():
    """组合分析工具集."""
    pass


@portfolio.command()
@click.option("--positions", help="code:amount,code:amount,...")
def concentration(positions: str):
    """计算 HHI 集中度."""
    pos = []
    for item in positions.split(","):
        code, amount = item.split(":")
        pos.append({"code": code, "amount": float(amount)})
    hhi = calculate_concentration(pos)
    click.echo(f"HHI={hhi:.4f}")


@portfolio.command()
@click.option("--fund-holdings", help="fund_code:stock_code,...")
@click.option("--direct-stocks", help="stock_code:amount,...")
def overlap(fund_holdings: str, direct_stocks: str):
    """检测基金重仓 ∩ 直接持仓的重复."""
    fh = {}
    for item in fund_holdings.split(","):
        fund, stock = item.split(":")
        fh[fund] = {"top10": [{"code": stock, "ratio": 0.05}]}
    ds = []
    for item in direct_stocks.split(","):
        code, amount = item.split(":")
        ds.append({"code": code, "amount": float(amount)})
    overlaps = detect_overlap(fh, ds)
    click.echo(json.dumps(overlaps, ensure_ascii=False, indent=2))


@portfolio.command()
@click.option("--holdings", help="code:amount:type:penetration,...")
def balance(holdings: str):
    """穿透计算股债平衡."""
    h = []
    for item in holdings.split(","):
        parts = item.split(":")
        h.append({
            "code": parts[0],
            "amount": float(parts[1]),
            "type": parts[2],
            "stock_penetration": float(parts[3]) if len(parts) > 3 else 0.5,
        })
    result = calculate_balance(h)
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


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

    # fund - 基金数据获取
    pf = subparsers.add_parser("fund", help="基金数据获取（净值/概况/重仓股/经理/业绩/申赎）")
    fund_sub = pf.add_subparsers(dest="fund_cmd", help="可用子命令")

    # fund detect（路由探测）
    pf2 = fund_sub.add_parser("detect", help="探测代码是否为基金（输出 FUND|名称 或 STOCK）")
    pf2.add_argument("symbol", help="6位代码")
    pf2.set_defaults(func=cmd_fund_detect)

    # fund nav
    pf2 = fund_sub.add_parser("nav", help="获取基金历史净值")
    pf2.add_argument("symbol", help="基金代码 (6位)")
    pf2.add_argument("--start", required=True, help="开始日期 YYYY-MM-DD")
    pf2.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
    pf2.set_defaults(func=cmd_fund_nav)

    # fund info
    pf2 = fund_sub.add_parser("info", help="获取基金概况")
    pf2.add_argument("symbol", help="基金代码")
    pf2.set_defaults(func=cmd_fund_info)

    # fund holdings
    pf2 = fund_sub.add_parser("holdings", help="获取基金重仓股")
    pf2.add_argument("symbol", help="基金代码")
    pf2.set_defaults(func=cmd_fund_holdings)

    # fund manager
    pf2 = fund_sub.add_parser("manager", help="获取基金经理")
    pf2.add_argument("symbol", help="基金代码")
    pf2.set_defaults(func=cmd_fund_manager)

    # fund performance
    pf2 = fund_sub.add_parser("performance", help="获取基金业绩表现")
    pf2.add_argument("symbol", help="基金代码")
    pf2.set_defaults(func=cmd_fund_performance)

    # fund flows
    pf2 = fund_sub.add_parser("flows", help="获取基金份额/规模变动")
    pf2.add_argument("symbol", help="基金代码")
    pf2.set_defaults(func=cmd_fund_flows)

    # fund news
    pf2 = fund_sub.add_parser("news", help="获取基金相关新闻")
    pf2.add_argument("symbol", help="基金代码")
    pf2.add_argument("--start", required=True, help="开始日期 YYYY-MM-DD")
    pf2.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
    pf2.set_defaults(func=cmd_fund_news)

    # fund global-news
    pf2 = fund_sub.add_parser("global-news", help="获取行业/主题财经新闻")
    pf2.add_argument("symbol", help="基金代码（用于标识，实际拉取全局新闻）")
    pf2.add_argument("--limit", type=int, default=20, help="新闻条数")
    pf2.set_defaults(func=cmd_fund_global_news)

    # fund universe - 全量场外开放式基金采集
    pfu = fund_sub.add_parser("universe", help="全量场外开放式基金采集管理")
    fund_universe_sub = pfu.add_subparsers(dest="fund_universe_cmd", help="可用子命令")

    # fund universe init
    pfu2 = fund_universe_sub.add_parser("init", help="初始化：拉取并保存基金列表")
    pfu2.set_defaults(func=cmd_fund_universe_init)

    # fund universe status
    pfu2 = fund_universe_sub.add_parser("status", help="查看基金采集进度")
    pfu2.set_defaults(func=cmd_fund_universe_status)

    # fund universe sync
    pfu2 = fund_universe_sub.add_parser("sync", help="执行一次基金增量采集")
    pfu2.add_argument("--quota", type=int, default=None, help="今日采集配额（覆盖配置）")
    pfu2.add_argument("--force", action="store_true", help="强制执行，忽略冷却中的基金")
    pfu2.set_defaults(func=cmd_fund_universe_sync)

    # fund universe update
    pfu2 = fund_universe_sub.add_parser("update", help="强制更新单只基金")
    pfu2.add_argument("symbol", help="基金代码 (6位)")
    pfu2.set_defaults(func=cmd_fund_universe_update)

    # fund universe refresh-list
    pfu2 = fund_universe_sub.add_parser("refresh-list", help="刷新基金列表")
    pfu2.set_defaults(func=cmd_fund_universe_refresh_list)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
