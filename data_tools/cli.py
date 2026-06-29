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


def cmd_fund_universe_repair(args):
    """argparse 版: 清理 fund_list 中的脏 type 字段,并补全 ftype。"""
    from . import fund_universe
    result = fund_universe.repair_fund_list(
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        force_repair=args.force,
    )
    if args.dry_run:
        print(json.dumps({
            "before_dirty": result["before_dirty"],
            "after_dirty": result["after_dirty"],
            "dry_run": True,
        }, ensure_ascii=False, indent=2))
        return
    print(f"修复前脏 type 数量 : {result['before_dirty']}")
    print(f"修复后脏 type 数量 : {result['after_dirty']}")
    print(f"新增 ftype 数量    : {result['ftype_added']}")
    print(f"是否已落盘         : {result['saved']}")
    if result.get("stats"):
        print("ftype 分布 Top-20:")
        for k, v in list(result["stats"].items())[:20]:
            print(f"  {k}: {v}")


def cmd_screener_replacement(args):
    """argparse 版: 场外基金全量库筛选."""
    prefs_obj = portfolio_prefs.UserPrefs(
        risk_level=args.risk_level,
        preferred_categories=[x.strip() for x in args.preferred.split(",") if x.strip()],
        excluded_categories=[x.strip() for x in args.excluded.split(",") if x.strip()],
        excluded_codes=[x.strip() for x in args.excluded_codes.split(",") if x.strip()],
    )
    cats = [x.strip() for x in args.categories.split(",") if x.strip()]
    out = portfolio_rebalance.screen_replacement_funds(
        categories=cats,
        prefs=prefs_obj,
        universe_path=args.universe,
        per_category=args.per_category,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 组合分析:传统 3 个 + 新增强 3 个
# ---------------------------------------------------------------------------


def cmd_portfolio_concentration(args):
    """argparse 版: HHI 集中度."""
    pos = []
    for item in args.positions.split(","):
        code, amount = item.split(":")
        pos.append({"code": code, "amount": float(amount)})
    hhi = calculate_concentration(pos)
    print(f"HHI={hhi:.4f}")


def cmd_portfolio_overlap(args):
    """argparse 版: 基金重仓 ∩ 直接持仓 重复检测."""
    fh = {}
    for item in args.fund_holdings.split(","):
        fund, stock = item.split(":")
        fh[fund] = {"top10": [{"code": stock, "ratio": 0.05}]}
    ds = []
    for item in args.direct_stocks.split(","):
        code, amount = item.split(":")
        ds.append({"code": code, "amount": float(amount)})
    overlaps = detect_overlap(fh, ds)
    print(json.dumps(overlaps, ensure_ascii=False, indent=2))


def cmd_portfolio_balance(args):
    """argparse 版: 穿透计算股债平衡."""
    h = []
    for item in args.holdings.split(","):
        parts = item.split(":")
        h.append({
            "code": parts[0],
            "amount": float(parts[1]),
            "type": parts[2],
            "stock_penetration": float(parts[3]) if len(parts) > 3 else 0.5,
        })
    result = calculate_balance(h)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_portfolio_prefs(args):
    """argparse 版: 用户偏好 / 目标配置(可 --save 落盘)."""
    base = portfolio_prefs.load_user_prefs(args.user_id) or portfolio_prefs.UserPrefs(user_id=args.user_id)
    if args.risk_level is not None:
        base.risk_level = args.risk_level
    if args.horizon is not None:
        base.horizon = args.horizon
    if args.preferred:
        base.preferred_categories = [x.strip() for x in args.preferred.split(",") if x.strip()]
    if args.excluded:
        base.excluded_categories = [x.strip() for x in args.excluded.split(",") if x.strip()]
    if args.equity_override is not None:
        base.target_equity_override = args.equity_override
    if args.save:
        path = portfolio_prefs.save_user_prefs(base)
        print(f"已保存: {path}")
    target = portfolio_prefs.get_target_allocation(base)
    print(portfolio_prefs.explain_template(base, target))
    print()
    print("目标配置 JSON:")
    print(json.dumps(target, ensure_ascii=False, indent=2))


def cmd_portfolio_screener(args):
    """argparse 版: 场外基金全量库筛选."""
    base = portfolio_prefs.UserPrefs(
        risk_level=args.risk_level,
        preferred_categories=[x.strip() for x in args.preferred.split(",") if x.strip()],
        excluded_categories=[x.strip() for x in args.excluded.split(",") if x.strip()],
        excluded_codes=[x.strip() for x in args.excluded_codes.split(",") if x.strip()],
    )
    cats = [x.strip() for x in args.categories.split(",") if x.strip()]
    out = portfolio_rebalance.screen_replacement_funds(
        categories=cats,
        prefs=base,
        universe_path=args.universe,
        per_category=args.per_category,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_portfolio_rebalance(args):
    """argparse 版: 端到端再平衡方案."""
    pos_list: list[dict] = []
    for item in args.positions.split(","):
        parts = item.split(":")
        d = {"code": parts[0], "amount": float(parts[1])}
        if len(parts) >= 3 and parts[2]:
            d["category"] = parts[2]
        if len(parts) >= 4 and parts[3]:
            d["name"] = parts[3]
        pos_list.append(d)

    base = portfolio_prefs.load_user_prefs(args.user_id) or portfolio_prefs.UserPrefs(user_id=args.user_id)
    if args.risk_level is not None:
        base.risk_level = args.risk_level
    if args.horizon is not None:
        base.horizon = args.horizon
    if args.equity_override is not None:
        base.target_equity_override = args.equity_override
    if args.preferred:
        base.preferred_categories = [x.strip() for x in args.preferred.split(",") if x.strip()]
    if args.excluded:
        base.excluded_categories = [x.strip() for x in args.excluded.split(",") if x.strip()]

    plan = portfolio_rebalance.build_rebalance_plan(
        positions=pos_list,
        prefs=base,
        universe_path=args.universe,
        per_category=args.per_category,
    )
    if args.format == "json":
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(portfolio_rebalance.plan_to_markdown(plan, base))


# ---------------------------------------------------------------------------
# Click 接口层（Phase 2 / Task 2.5: detect + portfolio）
# 与上方 argparse 入口并存,供测试与新子命令调用
# ---------------------------------------------------------------------------

from .portfolio import (
    calculate_concentration,
    detect_overlap,
    calculate_balance,
)
from . import portfolio_prefs
from . import portfolio_rebalance


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


@fund.group(name="universe")
def fund_universe_grp():
    """全量场外开放式基金采集调度器."""
    pass


@fund_universe_grp.command("init")
def fund_universe_init():
    """初始化:拉取并保存场外开放式基金列表."""
    from . import fund_universe as fu
    count = fu.refresh_fund_list()
    click.echo(f"初始化成功，共获取 {count} 只场外开放式基金")


@fund_universe_grp.command("status")
def fund_universe_status():
    """查看场外开放式基金采集进度."""
    from . import fund_universe as fu
    fu.show_status()


@fund_universe_grp.command()
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


@fund_universe_grp.command()
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


@fund_universe_grp.command("refresh-list")
def refresh_list():
    """刷新基金列表."""
    from . import fund_universe as fu
    count = fu.refresh_fund_list()
    click.echo(f"基金列表已刷新，共 {count} 只")


@fund_universe_grp.command("repair")
@click.option("--dry-run", is_flag=True, help="只统计不落盘")
@click.option("--batch-size", type=int, default=0, help="本次处理的基金数上限(0=全部)")
@click.option("--force", is_flag=True, help="强制清空 type 字段,统一走 ftype")
def repair(dry_run, batch_size, force):
    """清理 fund_list.json 中脏的 type 字段,并补全 ftype(基金类型)。

    用法:
        python -m data_tools.cli fund universe repair --dry-run          # 仅统计
        python -m data_tools.cli fund universe repair --batch-size 50    # 试补 50 只
        python -m data_tools.cli fund universe repair                   # 全量补
        python -m data_tools.cli fund universe repair --force           # 强制清空 type
    """
    from . import fund_universe as fu
    result = fu.repair_fund_list(
        dry_run=dry_run,
        batch_size=batch_size,
        force_repair=force,
    )
    if dry_run:
        click.echo(json.dumps({
            "before_dirty": result["before_dirty"],
            "after_dirty": result["after_dirty"],
            "dry_run": True,
        }, ensure_ascii=False, indent=2))
        return
    click.echo(f"修复前脏 type 数量 : {result['before_dirty']}")
    click.echo(f"修复后脏 type 数量 : {result['after_dirty']}")
    click.echo(f"新增 ftype 数量    : {result['ftype_added']}")
    click.echo(f"是否已落盘         : {result['saved']}")
    if result.get("stats"):
        click.echo("ftype 分布 Top-20:")
        for k, v in list(result["stats"].items())[:20]:
            click.echo(f"  {k}: {v}")


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


# ---------------------------------------------------------------------------
# 用户偏好 → 目标配置(C-1/C-3 增强,Step 0.5 / Step 2.6)
# ---------------------------------------------------------------------------


@portfolio.group()
def prefs():
    """用户投资偏好与目标资产配置."""
    pass


@prefs.command("show")
@click.option("--user-id", default="default", help="用户 ID(默认 default)")
@click.option("--from-file/--from-text", default=True, help="从 prefs.json 加载(true)或通过 stdin 文本提取")
@click.option("--text", default="", help="--from-text 时使用的自然语言描述")
def prefs_show(user_id, from_file, text):
    """显示用户偏好与目标资产配置."""
    prefs_obj = None
    if from_file:
        prefs_obj = portfolio_prefs.load_user_prefs(user_id)
        if prefs_obj is None:
            click.echo(f"未找到 {user_id} 的偏好文件,可通过 --from-text + --text 临时生成", err=True)
            sys.exit(1)
    else:
        prefs_obj = portfolio_prefs.parse_user_prefs_from_text(text, user_id=user_id)
    target = portfolio_prefs.get_target_allocation(prefs_obj)
    click.echo(portfolio_prefs.explain_template(prefs_obj, target))
    click.echo("")
    click.echo("目标配置 JSON:")
    click.echo(json.dumps(target, ensure_ascii=False, indent=2))


@prefs.command("save")
@click.option("--user-id", default="default", help="用户 ID")
@click.option("--risk-level", type=int, required=True, help="风险等级 1-5(1=保守,5=激进)")
@click.option("--horizon", type=click.Choice(["short", "medium", "long", "very_long"]), default="long", help="投资期限")
@click.option("--preferred", default="", help="偏好品类(逗号分隔,如 'index,sector')")
@click.option("--excluded", default="", help="排除品类(逗号分隔)")
@click.option("--excluded-codes", default="", help="排除基金代码(逗号分隔)")
@click.option("--equity-override", type=float, default=None, help="显式覆盖权益占比(0-1)")
@click.option("--amount", type=float, default=0.0, help="投资总金额(元)")
@click.option("--notes", default="", help="备注")
def prefs_save(user_id, risk_level, horizon, preferred, excluded, excluded_codes, equity_override, amount, notes):
    """保存用户偏好到 data/portfolios/<user_id>/prefs.json."""
    p = portfolio_prefs.UserPrefs(
        user_id=user_id,
        risk_level=risk_level,
        horizon=horizon,
        investment_amount=amount,
        preferred_categories=[x.strip() for x in preferred.split(",") if x.strip()],
        excluded_categories=[x.strip() for x in excluded.split(",") if x.strip()],
        excluded_codes=[x.strip() for x in excluded_codes.split(",") if x.strip()],
        target_equity_override=equity_override,
        notes=notes,
    )
    path = portfolio_prefs.save_user_prefs(p)
    target = portfolio_prefs.get_target_allocation(p)
    click.echo(f"已保存: {path}")
    click.echo(portfolio_prefs.explain_template(p, target))


# 扁平 prefs 入口(与 argparse 完全一致):
# 既能 `python -m data_tools.cli portfolio prefs --save --risk-level 2 ...`
# 也能 `python -c "from data_tools.cli import cli; cli()" prefs --save --risk-level 2 ...`
@portfolio.command("prefs")
@click.option("--user-id", default="default", help="用户 ID")
@click.option("--risk-level", type=int, default=None, help="覆盖风险等级 1-5")
@click.option("--horizon", type=click.Choice(["short", "medium", "long", "very_long"]), default=None)
@click.option("--preferred", default="", help="偏好品类(逗号)")
@click.option("--excluded", default="", help="排除品类(逗号)")
@click.option("--excluded-codes", default="", help="排除基金代码(逗号)")
@click.option("--equity-override", type=float, default=None)
@click.option("--amount", type=float, default=0.0, help="投资总金额(元)")
@click.option("--notes", default="", help="备注")
@click.option("--save/--no-save", default=True, help="是否落盘 prefs.json")
def portfolio_prefs_flat(user_id, risk_level, horizon, preferred, excluded, excluded_codes, equity_override, amount, notes, save):
    """扁平版 prefs(等同 argparse): 支持 --save/--no-save。"""
    base = portfolio_prefs.load_user_prefs(user_id) or portfolio_prefs.UserPrefs(user_id=user_id)
    if risk_level is not None:
        base.risk_level = risk_level
    if horizon is not None:
        base.horizon = horizon
    if preferred:
        base.preferred_categories = [x.strip() for x in preferred.split(",") if x.strip()]
    if excluded:
        base.excluded_categories = [x.strip() for x in excluded.split(",") if x.strip()]
    if excluded_codes:
        base.excluded_codes = [x.strip() for x in excluded_codes.split(",") if x.strip()]
    if equity_override is not None:
        base.target_equity_override = equity_override
    if amount > 0:
        base.investment_amount = amount
    if notes:
        base.notes = notes
    if save:
        path = portfolio_prefs.save_user_prefs(base)
        click.echo(f"已保存: {path}")
    target = portfolio_prefs.get_target_allocation(base)
    click.echo(portfolio_prefs.explain_template(base, target))
    click.echo("")
    click.echo("目标配置 JSON:")
    click.echo(json.dumps(target, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 基金全量库筛选(C-1/C-3 增强,Step 2.6 候选基金)
# ---------------------------------------------------------------------------


@cli.group()
def screener():
    """场外公募基金全量库筛选."""
    pass


@screener.command("replacement")
@click.option("--categories", required=True, help="需要加仓的品类,逗号分隔(如 'bond,index,sector')")
@click.option("--excluded-codes", default="", help="已持有/不想再持有的基金代码,逗号分隔")
@click.option("--preferred", default="", help="用户偏好品类(逗号分隔)")
@click.option("--excluded", default="", help="用户排除品类(逗号分隔)")
@click.option("--per-category", default=5, help="每个品类返回的候选数")
@click.option("--universe", default=None, help="基金全量库 JSON 路径(默认 _meta/fund_list.json)")
@click.option("--equity-override", type=float, default=None, help="显式权益占比覆盖")
@click.option("--risk-level", type=int, default=3, help="风险等级 1-5(用于生成偏好与排除规则)")
@click.option("--horizon", type=click.Choice(["short", "medium", "long", "very_long"]), default="long")
def screener_replacement(categories, excluded_codes, preferred, excluded, per_category, universe, equity_override, risk_level, horizon):
    """从国内场外公募基金全量库中,为指定品类筛选补/换候选。"""
    prefs_obj = portfolio_prefs.UserPrefs(
        risk_level=risk_level,
        horizon=horizon,
        preferred_categories=[x.strip() for x in preferred.split(",") if x.strip()],
        excluded_categories=[x.strip() for x in excluded.split(",") if x.strip()],
        excluded_codes=[x.strip() for x in excluded_codes.split(",") if x.strip()],
        target_equity_override=equity_override,
    )
    cats = [x.strip() for x in categories.split(",") if x.strip()]
    out = portfolio_rebalance.screen_replacement_funds(
        categories=cats,
        prefs=prefs_obj,
        universe_path=universe,
        per_category=per_category,
    )
    click.echo(json.dumps(out, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 端到端再平衡方案
# ---------------------------------------------------------------------------


@portfolio.command("rebalance")
@click.option("--positions", required=True, help="当前持仓,逗号分隔 code:amount:category(可省)")
@click.option("--user-id", default="default", help="用户 ID(对应 prefs.json)")
@click.option("--risk-level", type=int, default=None, help="覆盖 prefs 中的风险等级")
@click.option("--horizon", type=click.Choice(["short", "medium", "long", "very_long"]), default=None)
@click.option("--equity-override", type=float, default=None, help="显式覆盖权益占比(0-1)")
@click.option("--preferred", default="", help="覆盖偏好品类(逗号分隔)")
@click.option("--excluded", default="", help="覆盖排除品类(逗号分隔)")
@click.option("--per-category", default=5, help="每类补/换候选数")
@click.option("--universe", default=None, help="基金全量库 JSON 路径")
@click.option("--format", "fmt", type=click.Choice(["json", "md"]), default="json", help="输出格式")
def portfolio_rebalance_cmd(positions, user_id, risk_level, horizon, equity_override, preferred, excluded, per_category, universe, fmt):
    """基于用户风险偏好的端到端持仓再平衡方案(gap + 候选基金)。"""
    # 1) 解析持仓
    pos_list: list[dict] = []
    for item in positions.split(","):
        parts = item.split(":")
        d = {"code": parts[0], "amount": float(parts[1])}
        if len(parts) >= 3 and parts[2]:
            d["category"] = parts[2]
        if len(parts) >= 4 and parts[3]:
            d["name"] = parts[3]
        pos_list.append(d)

    # 2) 合并偏好(磁盘 → 命令行覆盖)
    base = portfolio_prefs.load_user_prefs(user_id) or portfolio_prefs.UserPrefs(user_id=user_id)
    if risk_level is not None:
        base.risk_level = risk_level
    if horizon is not None:
        base.horizon = horizon
    if equity_override is not None:
        base.target_equity_override = equity_override
    if preferred:
        base.preferred_categories = [x.strip() for x in preferred.split(",") if x.strip()]
    if excluded:
        base.excluded_categories = [x.strip() for x in excluded.split(",") if x.strip()]

    # 3) 计算再平衡方案
    plan = portfolio_rebalance.build_rebalance_plan(
        positions=pos_list,
        prefs=base,
        universe_path=universe,
        per_category=per_category,
    )

    if fmt == "json":
        click.echo(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    else:
        click.echo(portfolio_rebalance.plan_to_markdown(plan, base))


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

    # fund universe repair - 清理脏 type + 补全 ftype
    pfu2 = fund_universe_sub.add_parser("repair", help="清理 fund_list 中的脏 type,补全 ftype(基金类型)")
    pfu2.add_argument("--dry-run", action="store_true", help="只统计不落盘")
    pfu2.add_argument("--batch-size", type=int, default=0, help="本次处理的基金数上限(0=全部)")
    pfu2.add_argument("--force", action="store_true", help="强制清空 type,统一走 ftype")
    pfu2.set_defaults(func=cmd_fund_universe_repair)

    # portfolio - 组合分析(传统 3 个 + 新增强 3 个)
    pp = subparsers.add_parser("portfolio", help="组合分析(集中度/重叠/平衡/偏好/gap/再平衡)")
    portfolio_sub = pp.add_subparsers(dest="portfolio_cmd", help="可用子命令")

    # portfolio concentration
    pp2 = portfolio_sub.add_parser("concentration", help="计算 HHI 集中度")
    pp2.add_argument("--positions", required=True, help="code:amount,code:amount,...")
    pp2.set_defaults(func=cmd_portfolio_concentration)

    # portfolio overlap
    pp2 = portfolio_sub.add_parser("overlap", help="检测基金重仓 ∩ 直接持仓的重复")
    pp2.add_argument("--fund-holdings", required=True, help="fund_code:stock_code,...")
    pp2.add_argument("--direct-stocks", required=True, help="stock_code:amount,...")
    pp2.set_defaults(func=cmd_portfolio_overlap)

    # portfolio balance
    pp2 = portfolio_sub.add_parser("balance", help="穿透计算股债平衡")
    pp2.add_argument("--holdings", required=True, help="code:amount:type:penetration,...")
    pp2.set_defaults(func=cmd_portfolio_balance)

    # portfolio prefs (C-1/C-3 增强)
    pp2 = portfolio_sub.add_parser("prefs", help="用户偏好/目标配置")
    pp2.add_argument("--user-id", default="default", help="用户 ID")
    pp2.add_argument("--risk-level", type=int, default=None, help="覆盖风险等级 1-5")
    pp2.add_argument("--horizon", choices=["short", "medium", "long", "very_long"], default=None)
    pp2.add_argument("--preferred", default="", help="偏好品类(逗号)")
    pp2.add_argument("--excluded", default="", help="排除品类(逗号)")
    pp2.add_argument("--equity-override", type=float, default=None)
    pp2.add_argument("--save", action="store_true", help="落盘 prefs.json")
    pp2.add_argument("--show", action="store_true", help="仅显示,不要求 --save")
    pp2.set_defaults(func=cmd_portfolio_prefs)

    # portfolio screener (C-1/C-3 增强)
    pp2 = portfolio_sub.add_parser("screener", help="从场外公募基金全量库中筛选补/换候选")
    pp2.add_argument("--categories", required=True, help="目标品类,逗号分隔")
    pp2.add_argument("--excluded-codes", default="", help="已持有/不想再持有的代码")
    pp2.add_argument("--preferred", default="", help="用户偏好品类(逗号)")
    pp2.add_argument("--excluded", default="", help="用户排除品类(逗号)")
    pp2.add_argument("--per-category", type=int, default=5)
    pp2.add_argument("--universe", default=None)
    pp2.add_argument("--risk-level", type=int, default=3)
    pp2.set_defaults(func=cmd_portfolio_screener)

    # portfolio rebalance (C-1/C-3 增强:端到端)
    pp2 = portfolio_sub.add_parser("rebalance", help="端到端再平衡方案(gap + 候选基金)")
    pp2.add_argument("--positions", required=True, help="code:amount[:category[:name]],逗号")
    pp2.add_argument("--user-id", default="default")
    pp2.add_argument("--risk-level", type=int, default=None)
    pp2.add_argument("--horizon", default=None)
    pp2.add_argument("--equity-override", type=float, default=None)
    pp2.add_argument("--preferred", default="")
    pp2.add_argument("--excluded", default="")
    pp2.add_argument("--per-category", type=int, default=5)
    pp2.add_argument("--universe", default=None)
    pp2.add_argument("--format", choices=["json", "md"], default="json")
    pp2.set_defaults(func=cmd_portfolio_rebalance)

    # screener - 候选基金筛选(C-1/C-3 增强,与 Click 端口对齐)
    pscr = subparsers.add_parser("screener", help="场外公募基金全量库筛选")
    screener_sub = pscr.add_subparsers(dest="screener_cmd", help="可用子命令")
    pscr2 = screener_sub.add_parser("replacement", help="为指定品类筛选补/换候选")
    pscr2.add_argument("--categories", required=True, help="目标品类,逗号")
    pscr2.add_argument("--excluded-codes", default="")
    pscr2.add_argument("--preferred", default="")
    pscr2.add_argument("--excluded", default="")
    pscr2.add_argument("--per-category", type=int, default=5)
    pscr2.add_argument("--universe", default=None)
    pscr2.add_argument("--risk-level", type=int, default=3)
    pscr2.set_defaults(func=cmd_screener_replacement)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
