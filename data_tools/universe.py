#!/usr/bin/env python3
"""全量A股数据采集调度模块.

基于现有的 stock_data.py 接口，实现增量式全量A股数据采集。
支持每日配额、进度追踪、失败重试、防封限流。

使用方式:
    见 cli.py universe 子命令
"""

import os
import json
import time
import random
import logging
from datetime import datetime, timedelta
from typing import Optional

from .stock_data import (
    get_data_dir,
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
    _normalize_ticker,
    _http_get,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据类型定义
# ---------------------------------------------------------------------------

DATA_TYPES_DAILY = [
    "kline",
    "fundamentals",
    "indicators_rsi",
    "indicators_macd",
    "news",
    "dragon_tiger",
]

DATA_TYPES_WEEKLY = [
    "financials",
    "forecast",
    "lockup",
    "insider",
    "concept",
]

ALL_DATA_TYPES = DATA_TYPES_DAILY + DATA_TYPES_WEEKLY

DEFAULT_CONFIG = {
    "daily_quota": 500,
    "stock_interval_min": 1.0,
    "stock_interval_max": 3.0,
    "fail_cooldown_days": 7,
    "max_fail_count": 3,
    "weekly_update_interval_days": 7,
    "kline_lookback_days": 365,
    "news_lookback_days": 90,
}

# ---------------------------------------------------------------------------
# 路径工具
# ---------------------------------------------------------------------------


def _meta_dir() -> str:
    path = os.path.join(get_data_dir(), "_meta")
    os.makedirs(path, exist_ok=True)
    return path


def _config_path() -> str:
    return os.path.join(_meta_dir(), "universe_config.json")


def _stock_list_path() -> str:
    return os.path.join(_meta_dir(), "stock_list.json")


def _progress_path() -> str:
    return os.path.join(_meta_dir(), "universe_progress.json")


# ---------------------------------------------------------------------------
# 配置管理
# ---------------------------------------------------------------------------


def load_config() -> dict:
    path = _config_path()
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg.update(user_cfg)
        except Exception as e:
            logger.warning("读取配置文件失败，使用默认值: %s", e)
    return cfg


def save_config(cfg: dict) -> None:
    path = _config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    logger.info("配置已保存: %s", path)


# ---------------------------------------------------------------------------
# 股票列表
# ---------------------------------------------------------------------------


def load_stock_list() -> list:
    path = _stock_list_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("加载股票列表失败: %s", e)
        return []


def save_stock_list(stocks: list) -> None:
    path = _stock_list_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False, indent=2)
    logger.info("股票列表已保存: %d 只，路径: %s", len(stocks), path)


def fetch_stock_list_from_sina() -> list:
    """从新浪财经获取全量A股列表."""
    import json as json_lib

    stocks = []
    url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    seen = set()

    page = 1
    page_size = 100
    max_pages = 70

    while page <= max_pages:
        params = {
            "page": page,
            "num": page_size,
            "sort": "symbol",
            "asc": 1,
            "node": "hs_a",
            "symbol": "",
            "_s_r_a": "page",
        }
        try:
            resp = _http_get(url, params=params, timeout=15)
            text = resp.text

            data = json_lib.loads(text) if text.startswith("[") else []

            if not data:
                break

            page_stocks = 0
            for item in data:
                code = item.get("code", "")
                name = item.get("name", "")

                # 过滤沪深A股：沪市6开头，深市0/3开头
                if code and code.isdigit() and len(code) == 6 and code.startswith(("6", "0", "3")):
                    if code not in seen:
                        seen.add(code)
                        market = "sh" if code.startswith("6") else "sz"
                        stocks.append({
                            "code": code,
                            "name": name,
                            "market": market,
                            "industry": "",
                        })
                        page_stocks += 1

            if len(data) < page_size:
                break

            page += 1
            time.sleep(0.2)

        except Exception as e:
            logger.warning("新浪股票列表第 %d 页失败: %s", page, e)
            break

    logger.info("从新浪获取股票列表: %d 只", len(stocks))
    return stocks


def fetch_stock_list() -> list:
    """获取全量A股列表，优先东财，失败则用新浪."""
    # 先尝试东财
    logger.info("尝试从东财获取股票列表...")
    stocks = _fetch_stock_list_from_em()
    if stocks:
        return stocks
    
    # 东财失败，尝试新浪
    logger.info("东财失败，尝试从新浪获取...")
    stocks = fetch_stock_list_from_sina()
    return stocks


def _fetch_stock_list_from_em() -> list:
    """从东方财富获取全量A股列表（分页）."""
    stocks = []
    page = 1
    page_size = 500
    max_pages = 20

    while page <= max_pages:
        url = "http://80.push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": page,
            "pz": page_size,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:7,m:1+t:3",
            "fields": "f12,f14,f100",
        }
        try:
            resp = _http_get(url, params=params, timeout=15)
            data = resp.json()
            diff = data.get("data", {}).get("diff", [])
            if not diff:
                break

            for item in diff:
                code = item.get("f12", "")
                name = item.get("f14", "")
                industry = item.get("f100", "") or ""
                if code and code.isdigit() and len(code) == 6:
                    market = "sh" if code.startswith("6") else "sz"
                    stocks.append({
                        "code": code,
                        "name": name,
                        "market": market,
                        "industry": industry,
                    })

            if len(diff) < page_size:
                break
            page += 1
            time.sleep(0.3)

        except Exception as e:
            logger.error("获取股票列表第 %d 页失败: %s", page, e)
            break

    logger.info("获取股票列表成功: %d 只", len(stocks))
    return stocks


def refresh_stock_list() -> int:
    stocks = fetch_stock_list()
    if stocks:
        save_stock_list(stocks)
    return len(stocks)


# ---------------------------------------------------------------------------
# 进度追踪
# ---------------------------------------------------------------------------


def load_progress() -> dict:
    path = _progress_path()
    if not os.path.exists(path):
        return {"last_update": "", "stocks": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("加载进度文件失败: %s", e)
        return {"last_update": "", "stocks": {}}


def save_progress(progress: dict) -> None:
    path = _progress_path()
    progress["last_update"] = datetime.now().strftime("%Y-%m-%d")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def _get_stock_progress(progress: dict, code: str) -> dict:
    if code not in progress["stocks"]:
        progress["stocks"][code] = {}
    return progress["stocks"][code]


def _get_data_progress(progress: dict, code: str, dtype: str) -> dict:
    sp = _get_stock_progress(progress, code)
    if dtype not in sp:
        sp[dtype] = {"last": "", "status": "pending", "fail_count": 0}
    return sp[dtype]


def _update_data_status(progress: dict, code: str, dtype: str, status: str) -> None:
    dp = _get_data_progress(progress, code, dtype)
    dp["status"] = status
    if status == "ok" or status == "empty" or status == "partial":
        dp["last"] = datetime.now().strftime("%Y-%m-%d")
        dp["fail_count"] = 0
    elif status == "failed":
        dp["fail_count"] = dp.get("fail_count", 0) + 1


# ---------------------------------------------------------------------------
# 调度算法
# ---------------------------------------------------------------------------


def _is_due(dp: dict, is_weekly: bool, cfg: dict) -> bool:
    last_str = dp.get("last", "")
    if not last_str:
        return True
    try:
        last_date = datetime.strptime(last_str, "%Y-%m-%d").date()
    except ValueError:
        return True
    today = datetime.now().date()
    interval_days = (today - last_date).days
    if is_weekly:
        return interval_days >= cfg.get("weekly_update_interval_days", 7)
    return interval_days >= 1


def _is_in_cooldown(dp: dict, cfg: dict) -> bool:
    fc = dp.get("fail_count", 0)
    if fc < cfg.get("max_fail_count", 3):
        return False
    last_str = dp.get("last", "")
    if not last_str:
        return False
    try:
        last_date = datetime.strptime(last_str, "%Y-%m-%d").date()
    except ValueError:
        return False
    today = datetime.now().date()
    cooldown = cfg.get("fail_cooldown_days", 7)
    return (today - last_date).days < cooldown


def _priority_score(progress: dict, code: str, cfg: dict) -> float:
    sp = progress["stocks"].get(code, {})
    score = 0.0
    today = datetime.now().date()

    has_failed = False
    oldest_daily_due = 999
    oldest_weekly_due = 999

    for dtype in ALL_DATA_TYPES:
        dp = sp.get(dtype, {"last": "", "status": "pending", "fail_count": 0})
        is_weekly = dtype in DATA_TYPES_WEEKLY

        if dp.get("status") == "failed":
            has_failed = True
            if not _is_in_cooldown(dp, cfg):
                score += 1000

        if not _is_due(dp, is_weekly, cfg):
            continue

        last_str = dp.get("last", "")
        if last_str:
            try:
                last_dt = datetime.strptime(last_str, "%Y-%m-%d").date()
                days_ago = (today - last_dt).days
            except ValueError:
                days_ago = 365
        else:
            days_ago = 365

        if is_weekly:
            oldest_weekly_due = min(oldest_weekly_due, days_ago)
        else:
            oldest_daily_due = min(oldest_daily_due, days_ago)

    if has_failed:
        pass

    score += oldest_daily_due * 10
    score += oldest_weekly_due

    return score


def select_stocks_for_today(progress: dict, stock_list: list, cfg: dict) -> list:
    quota = cfg.get("daily_quota", 500)
    today = datetime.now().strftime("%Y-%m-%d")

    already_today = []
    need_update = []

    for s in stock_list:
        code = s["code"]
        sp = progress["stocks"].get(code, {})

        all_done_today = True
        any_due = False

        for dtype in ALL_DATA_TYPES:
            dp = sp.get(dtype, {"last": "", "status": "pending"})
            is_weekly = dtype in DATA_TYPES_WEEKLY

            if _is_due(dp, is_weekly, cfg) and not _is_in_cooldown(dp, cfg):
                any_due = True
                all_done_today = False
                break

            if dp.get("last") != today:
                all_done_today = False

        if all_done_today:
            already_today.append(s)
        elif any_due:
            need_update.append(s)

    scored = []
    for s in need_update:
        score = _priority_score(progress, s["code"], cfg)
        scored.append((score, s))

    scored.sort(key=lambda x: -x[0])

    selected = [s for _, s in scored[:quota]]
    logger.info(
        "今日选股: %d 只 (配额 %d)，已完成: %d 只，待更新: %d 只",
        len(selected), quota, len(already_today), len(need_update),
    )
    return selected


# ---------------------------------------------------------------------------
# 单只股票采集
# ---------------------------------------------------------------------------


def _check_result_status(result: str, dtype: str) -> str:
    if not result or not result.strip():
        return "empty" if dtype in ("dragon_tiger", "lockup") else "failed"

    r = result

    fail_keywords = ["失败", "出错", "error", "Error", "未找到", "异常"]
    for kw in fail_keywords:
        if kw in r:
            return "failed"

    if dtype == "kline":
        if "未找到" in r or "数据条数: 0" in r:
            return "failed"

    if dtype == "news":
        if "0 条" in r or "未找到" in r:
            return "partial"

    return "ok"


def collect_stock(code: str, progress: dict, cfg: dict) -> dict:
    code = _normalize_ticker(code)
    logger.info("开始采集: %s", code)

    today = datetime.now().strftime("%Y-%m-%d")
    start_date_kline = (datetime.now() - timedelta(days=cfg.get("kline_lookback_days", 365))).strftime("%Y-%m-%d")
    start_date_news = (datetime.now() - timedelta(days=cfg.get("news_lookback_days", 90))).strftime("%Y-%m-%d")

    results = {}

    for dtype in DATA_TYPES_DAILY:
        dp = _get_data_progress(progress, code, dtype)
        if not _is_due(dp, False, cfg) and not _is_in_cooldown(dp, cfg):
            results[dtype] = dp.get("status", "ok")
            continue
        if _is_in_cooldown(dp, cfg):
            results[dtype] = "cooldown"
            continue

        try:
            if dtype == "kline":
                result = get_stock_data(code, start_date_kline, today, save=True)
            elif dtype == "fundamentals":
                result = get_fundamentals(code, save=True)
            elif dtype == "indicators_rsi":
                result = get_indicators(code, "rsi", today, 60, save=True)
            elif dtype == "indicators_macd":
                result = get_indicators(code, "macd", today, 60, save=True)
            elif dtype == "news":
                result = get_news(code, start_date_news, today, save=True)
            elif dtype == "dragon_tiger":
                result = get_dragon_tiger(code, days=5, save=True)
            else:
                continue

            status = _check_result_status(result, dtype)
            _update_data_status(progress, code, dtype, status)
            results[dtype] = status
            logger.debug("  %-20s: %s", dtype, status)

        except Exception as e:
            logger.warning("  %-20s: 异常 - %s", dtype, e)
            _update_data_status(progress, code, dtype, "failed")
            results[dtype] = "failed"

    for dtype in DATA_TYPES_WEEKLY:
        dp = _get_data_progress(progress, code, dtype)
        if not _is_due(dp, True, cfg) and not _is_in_cooldown(dp, cfg):
            results[dtype] = dp.get("status", "ok")
            continue
        if _is_in_cooldown(dp, cfg):
            results[dtype] = "cooldown"
            continue

        try:
            if dtype == "financials":
                r1 = get_balance_sheet(code, save=True)
                r2 = get_income_statement(code, save=True)
                r3 = get_cashflow(code, save=True)
                combined = f"{r1}\n{r2}\n{r3}"
                status = _check_result_status(combined, "financials")
            elif dtype == "forecast":
                result = get_profit_forecast(code, save=True)
                status = _check_result_status(result, "forecast")
            elif dtype == "lockup":
                result = get_lockup(code, save=True)
                status = _check_result_status(result, "lockup")
            elif dtype == "insider":
                result = get_insider_transactions(code, save=True)
                status = _check_result_status(result, "insider")
            elif dtype == "concept":
                result = get_concept_blocks(code, save=True)
                status = _check_result_status(result, "concept")
            else:
                continue

            _update_data_status(progress, code, dtype, status)
            results[dtype] = status
            logger.debug("  %-20s: %s", dtype, status)

        except Exception as e:
            logger.warning("  %-20s: 异常 - %s", dtype, e)
            _update_data_status(progress, code, dtype, "failed")
            results[dtype] = "failed"

    ok_count = sum(1 for v in results.values() if v in ("ok", "empty", "partial"))
    fail_count = sum(1 for v in results.values() if v == "failed")
    logger.info("完成采集: %s (成功:%d 失败:%d", code, ok_count, fail_count)

    return results


# ---------------------------------------------------------------------------
# 全局数据采集
# ---------------------------------------------------------------------------


def collect_global_data() -> dict:
    logger.info("开始采集全局数据")
    results = {}

    try:
        get_global_news(limit=30)
        results["global_news"] = "ok"
    except Exception as e:
        logger.warning("全球新闻采集失败: %s", e)
        results["global_news"] = "failed"

    try:
        get_hot_stocks()
        results["hot_stocks"] = "ok"
    except Exception as e:
        logger.warning("热门股采集失败: %s", e)
        results["hot_stocks"] = "failed"

    try:
        get_northbound_flow()
        results["northbound"] = "ok"
    except Exception as e:
        logger.warning("北向资金采集失败: %s", e)
        results["northbound"] = "failed"

    return results


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def sync(quota: int = None, force: bool = False) -> dict:
    cfg = load_config()
    if quota is not None:
        cfg["daily_quota"] = quota

    stock_list = load_stock_list()
    if not stock_list:
        logger.warning("股票列表为空，请先运行 universe init")
        return {"status": "error", "message": "股票列表为空"}

    progress = load_progress()
    today = datetime.now().strftime("%Y-%m-%d")

    if not force and progress.get("last_update") == today:
        logger.info("今日已运行过，使用 --force 强制执行")
        return {"status": "skipped", "message": "今日已运行"}

    selected = select_stocks_for_today(progress, stock_list, cfg)

    if not selected:
        logger.info("没有需要更新的股票")
        save_progress(progress)
        return {"status": "done", "updated": 0}

    interval_min = cfg.get("stock_interval_min", 1.0)
    interval_max = cfg.get("stock_interval_max", 3.0)

    success_count = 0
    fail_count = 0

    for i, stock in enumerate(selected):
        code = stock["code"]
        logger.info("[%d/%d] %s %s", i + 1, len(selected), code, stock.get("name", ""))

        try:
            results = collect_stock(code, progress, cfg)
            all_failed = all(v == "failed" for v in results.values())
            if all_failed:
                fail_count += 1
            else:
                success_count += 1
        except Exception as e:
            logger.error("采集 %s 时发生未预期错误: %s", code, e)
            fail_count += 1

        if i < len(selected) - 1:
            sleep_time = random.uniform(interval_min, interval_max)
            time.sleep(sleep_time)

        if (i + 1) % 10 == 0:
            save_progress(progress)
            logger.info("进度保存: 已处理 %d/%d", i + 1, len(selected))

    global_results = collect_global_data()

    save_progress(progress)

    summary = {
        "status": "done",
        "total": len(selected),
        "success": success_count,
        "failed": fail_count,
        "global": global_results,
        "date": today,
    }

    logger.info(
        "采集完成: 共 %d 只，成功 %d，失败 %d",
        len(selected), success_count, fail_count,
    )

    return summary


# ---------------------------------------------------------------------------
# 单只股票强制更新
# ---------------------------------------------------------------------------


def update_single(code: str) -> dict:
    cfg = load_config()
    progress = load_progress()
    results = collect_stock(code, progress, cfg)
    save_progress(progress)
    return results


# ---------------------------------------------------------------------------
# 状态统计
# ---------------------------------------------------------------------------


def get_status() -> dict:
    stock_list = load_stock_list()
    progress = load_progress()
    cfg = load_config()

    total = len(stock_list)
    today = datetime.now().strftime("%Y-%m-%d")

    completed_first_round = 0
    partially_failed_stocks = 0
    fully_failed_stocks = 0
    updated_today = 0

    total_data_points = 0
    ok_data_points = 0
    failed_data_points = 0

    for s in stock_list:
        code = s["code"]
        sp = progress["stocks"].get(code, {})

        has_any_data = False
        all_data_ok = True
        all_data_failed = True
        all_today = True

        for dtype in ALL_DATA_TYPES:
            dp = sp.get(dtype, {"last": "", "status": "pending"})
            status = dp.get("status", "pending")
            last = dp.get("last", "")

            if status in ("ok", "empty", "partial"):
                has_any_data = True
                all_data_failed = False
                ok_data_points += 1
                total_data_points += 1
            elif status == "failed":
                all_data_ok = False
                all_data_failed = False
                failed_data_points += 1
                total_data_points += 1
            else:
                all_data_ok = False
                all_data_failed = False

            if not last:
                all_today = False
            elif last != today:
                all_today = False

        if has_any_data and all_data_ok:
            completed_first_round += 1
        elif has_any_data and not all_data_ok and not all_data_failed:
            partially_failed_stocks += 1
        elif all_data_failed and total_data_points > 0:
            fully_failed_stocks += 1

        if all_today and has_any_data:
            updated_today += 1

    data_success_pct = round(ok_data_points / total_data_points * 100, 1) if total_data_points else 0

    return {
        "total_stocks": total,
        "completed_first_round": completed_first_round,
        "completion_pct": round(completed_first_round / total * 100, 1) if total else 0,
        "partially_failed": partially_failed_stocks,
        "fully_failed": fully_failed_stocks,
        "updated_today": updated_today,
        "data_success_pct": data_success_pct,
        "daily_quota": cfg.get("daily_quota", 500),
        "last_update": progress.get("last_update", ""),
    }


def format_status(status: dict) -> str:
    lines = [
        "=== 全量A股采集状态 ===",
        f"股票总数: {status['total_stocks']}",
        f"首轮完成(全项成功): {status['completed_first_round']} ({status['completion_pct']}%)",
        f"部分完成(有个别失败): {status['partially_failed']}",
        f"完全失败: {status['fully_failed']}",
        f"今日已更新: {status['updated_today']}",
        f"数据项成功率: {status['data_success_pct']}%",
        f"每日配额: {status['daily_quota']}",
        f"最后更新: {status['last_update']}",
    ]
    return "\n".join(lines)
