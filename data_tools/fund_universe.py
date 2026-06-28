"""基金全量采集调度器.

为 Trae 自动化定时任务提供 Python CLI 入口，定时拉取国内场外开放式基金数据。
镜像 data_tools.universe.py 的设计模式。

CLI 入口:
    python -m data_tools.cli fund universe {init,status,sync,update,refresh-list}
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

from .stock_data import (
    get_funds_dir,
    get_meta_dir,
    _UA,
)

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "daily_quota": 200,
    "fund_interval_min": 1.5,
    "fund_interval_max": 3.5,
    "field_interval_min": 0.5,
    "field_interval_max": 1.5,
    "fail_cooldown_days": 7,
    "max_fail_count": 3,
    "news_lookback_days": 90,
    "nav_lookback_days": 365,
}


def get_meta_dir() -> str:
    """基金元数据目录 (data/funds/_meta/)."""
    return os.path.join(get_funds_dir(), "_meta")


def get_config_path() -> str:
    return os.path.join(get_meta_dir(), "universe_config.json")


def get_fund_list_path() -> str:
    return os.path.join(get_meta_dir(), "fund_list.json")


def get_progress_path() -> str:
    return os.path.join(get_meta_dir(), "universe_progress.json")


def _ensure_meta_dir() -> None:
    os.makedirs(get_meta_dir(), exist_ok=True)


def load_config() -> dict:
    """读取调度配置；文件不存在或损坏时返回默认值。"""
    path = get_config_path()
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
    """保存调度配置到 _meta/universe_config.json。"""
    _ensure_meta_dir()
    path = get_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    logger.info("配置已保存: %s", path)


_FUND_LIST_PRIMARY = "https://fund.eastmoney.com/Data/Fund_JJJZ_Data.aspx"
_FUND_LIST_FALLBACK = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_FUND_LIST_REFERER = "https://fund.eastmoney.com/data/fundranking.html"

_FUND_HEADERS = {
    "User-Agent": _UA,
    "Referer": _FUND_LIST_REFERER,
}


def _fund_http_get(url, params=None, headers=None, timeout=15):
    h = dict(_FUND_HEADERS)
    if headers:
        h.update(headers)
    return requests.get(url, params=params, headers=h, timeout=timeout)


def is_offexchange_fund(record: dict) -> bool:
    """判定单条基金记录是否为场外开放式基金。

    排除规则（任一命中即排除）:
    - 代码前缀 5 (50/51/56/58xxxx) → 上交所 ETF/LOF
    - 代码前缀 15 → 深交所 ETF
    - 代码前缀 16 → 深交所 LOF
    - 代码前缀 18 → 封闭式基金
    - 名称包含「封闭」或「场内」
    - type 字段含「封闭式」或「场内 ETF」
    """
    code = str(record.get("code", "")).strip()
    name = str(record.get("name", ""))
    ftype = str(record.get("type", ""))

    if code.startswith(("50", "51", "56", "58", "15", "16", "18")):
        return False
    if "封闭" in name or "场内" in name:
        return False
    if "封闭式" in ftype or "场内 ETF" in ftype:
        return False
    return True


def _parse_primary_response(text: str) -> list:
    """天天基金主端点返回 `var RANKDATA = [...];` 格式。"""
    import re
    m = re.search(r"=\s*(\[.*?\]);", text, re.DOTALL)
    if not m:
        return []
    raw = m.group(1)
    return json.loads(raw)


def fetch_fund_list_from_primary() -> list:
    """从天天基金主端点拉取全量基金列表。"""
    resp = _fund_http_get(_FUND_LIST_PRIMARY)
    return _parse_primary_response(resp.text)


def fetch_fund_list_from_fallback() -> list:
    """从东方财富数据中心备用端点拉取全量基金列表。"""
    params = {
        "reportName": "RPT_FUND_LIST",
        "columns": "ALL",
        "pageSize": "20000",
        "pageNumber": "1",
    }
    resp = _fund_http_get(_FUND_LIST_FALLBACK, params=params)
    payload = resp.json()
    data = payload.get("result", {}).get("data", [])
    rows = []
    for item in data:
        rows.append({
            "code": item.get("FCODE", ""),
            "name": item.get("SHORTNAME", ""),
            "type": item.get("FTYPE", ""),
        })
    return rows


def fetch_fund_list() -> list:
    """拉取全量基金列表并过滤出场外开放式基金。

    优先使用天天基金主端点；若返回 < 5000 条则降级到东方财富数据中心。
    返回的每条记录额外带 `is_offexchange=True` 字段。
    """
    rows: list = []
    try:
        rows = fetch_fund_list_from_primary()
    except Exception as e:
        logger.warning("主端点拉取失败，降级到备用: %s", e)

    if len(rows) < 5000:
        try:
            rows = fetch_fund_list_from_fallback()
        except Exception as e:
            logger.error("备用端点拉取失败: %s", e)
            raise

    out = []
    for r in rows:
        if is_offexchange_fund(r):
            r2 = dict(r)
            r2["is_offexchange"] = True
            out.append(r2)
    logger.info("场外开放式基金共 %d 只", len(out))
    return out


def save_fund_list(funds: list) -> None:
    """保存基金列表到 _meta/fund_list.json。"""
    _ensure_meta_dir()
    path = get_fund_list_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(funds, f, ensure_ascii=False, indent=2)
    logger.info("基金列表已保存: %d 只，路径: %s", len(funds), path)


def load_fund_list() -> list:
    """从 _meta/fund_list.json 加载基金列表。"""
    path = get_fund_list_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("加载基金列表失败: %s", e)
        return []


def diff_fund_list(old: list, new: list) -> dict:
    """对比新旧基金列表，返回新增/退场/保留的代码集合。"""
    old_codes = {f.get("code") for f in old}
    new_codes = {f.get("code") for f in new}
    return {
        "added": sorted(new_codes - old_codes),
        "removed": sorted(old_codes - new_codes),
        "kept": sorted(old_codes & new_codes),
    }


EMPTY_PROGRESS_RECORD = {
    "last_sync_at": None,
    "last_status": None,
    "fail_count": 0,
    "cooldown_until": None,
    "fields": {},
}


def load_progress() -> dict:
    """读取 _meta/universe_progress.json；不存在时返回空 dict。"""
    path = get_progress_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("加载进度文件失败: %s", e)
        return {}


def save_progress(progress: dict) -> None:
    """保存进度到 _meta/universe_progress.json。"""
    _ensure_meta_dir()
    path = get_progress_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)
    logger.info("进度已保存: %d 条", len(progress))


def update_progress(
    code: str,
    last_status: str,
    fail_count: int,
    fields: dict,
    cooldown_until: Optional[str] = None,
) -> None:
    """更新单只基金的进度记录并立即落盘。"""
    progress = load_progress()
    existing = progress.get(code, dict(EMPTY_PROGRESS_RECORD))
    merged_fields = dict(existing.get("fields") or {})
    merged_fields.update(fields)
    existing["last_sync_at"] = datetime.now().isoformat(timespec="seconds")
    existing["last_status"] = last_status
    existing["fail_count"] = fail_count
    existing["cooldown_until"] = cooldown_until
    existing["fields"] = merged_fields
    progress[code] = existing
    save_progress(progress)


def is_in_cooldown(record: Optional[dict], _config: dict) -> bool:
    """判定该基金当前是否处于冷却期。"""
    if not record:
        return False
    until = record.get("cooldown_until")
    if not until:
        return False
    try:
        return datetime.fromisoformat(until) > datetime.now()
    except Exception:
        return False


from . import fund_data


def _sleep_jitter(min_s: float, max_s: float) -> None:
    """在 [min_s, max_s] 之间随机 sleep，min_s == max_s == 0 时直接返回。"""
    if max_s <= 0:
        return
    time.sleep(random.uniform(min_s, max_s))


def _compute_window(days: int) -> tuple:
    """返回 (start_date, end_date) ISO 字符串。"""
    end = datetime.now().date()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


_FIELD_FETCHERS = [
    ("nav",         lambda code, cfg: fund_data.get_fund_nav(code, *_compute_window(cfg["nav_lookback_days"]))),
    ("info",        lambda code, cfg: fund_data.get_fund_info(code)),
    ("holdings",    lambda code, cfg: fund_data.get_fund_holdings(code)),
    ("manager",     lambda code, cfg: fund_data.get_fund_manager(code)),
    ("performance", lambda code, cfg: fund_data.get_fund_performance(code)),
    ("flows",       lambda code, cfg: fund_data.get_fund_flows(code)),
    ("news",        lambda code, cfg: fund_data.get_fund_news(code, *_compute_window(cfg["news_lookback_days"]))),
]


def sync_single_fund(code: str, config: dict) -> dict:
    """采集单只基金全部 7 个字段，返回进度记录 dict。

    返回结构:
        {
            "last_status": "ok" | "partial" | "failed",
            "fail_count": int (0/1 二值标记，本轮是否失败),
            "fields": {"nav": "ok", "info": "failed", ...},
            "cooldown_until": None | "ISO timestamp",
        }
    """
    fields = {}
    failed_any = False
    all_failed = True
    for name, fetcher in _FIELD_FETCHERS:
        try:
            fetcher(code, config)
            fields[name] = "ok"
            all_failed = False
        except Exception as e:
            logger.warning("[%s] 字段 %s 采集失败: %s", code, name, e)
            fields[name] = "failed"
            failed_any = True
        _sleep_jitter(config.get("field_interval_min", 0.5),
                      config.get("field_interval_max", 1.5))

    if not failed_any:
        last_status = "ok"
        fail_count = 0
    elif all_failed:
        last_status = "failed"
        fail_count = 1
    else:
        last_status = "partial"
        fail_count = 1

    return {
        "last_status": last_status,
        "fail_count": fail_count,
        "fields": fields,
        "cooldown_until": None,
    }


def refresh_fund_list() -> int:
    """refresh-list 子命令：全量重写 _meta/fund_list.json，返回基金总数。"""
    funds = fetch_fund_list()
    save_fund_list(funds)
    return len(funds)


def _should_enter_cooldown(prev_fail_count: int, new_fail_count: int, config: dict) -> bool:
    """本轮累计失败次数是否达到 max_fail_count 阈值。"""
    return new_fail_count >= config.get("max_fail_count", 3)


def _cooldown_until(config: dict) -> str:
    return (datetime.now() + timedelta(days=config.get("fail_cooldown_days", 7))).isoformat()


def sync(quota: Optional[int] = None, force: bool = False) -> dict:
    """同步主循环：按配额/优先级/冷却规则执行单只采集。

    progress 文件语义：仅保留本次 sync 周期涉及的基金记录。
    跨周期的累计失败通过 progress 中的 cooldown_until 字段间接保留。

    Returns:
        {
            "status": "ok" | "partial" | "error",
            "total": int,
            "success": int,
            "failed": int,
        }
    """
    config = load_config()
    quota = quota if quota is not None else config.get("daily_quota", 200)

    funds = load_fund_list()
    if not funds:
        try:
            refresh_fund_list()
            funds = load_fund_list()
        except Exception as e:
            logger.error("fund_list.json 缺失且自动 init 失败: %s", e)
            return {"status": "error", "total": 0, "success": 0, "failed": 0,
                    "message": f"fund_list.json 缺失且自动 init 失败: {e}"}

    if not funds:
        return {"status": "error", "total": 0, "success": 0, "failed": 0,
                "message": "基金列表为空"}

    progress = load_progress()

    candidates = []
    for f in funds:
        code = f.get("code")
        if not code:
            continue
        rec = progress.get(code)
        if not force and is_in_cooldown(rec, config):
            continue
        candidates.append((code, (rec or {}).get("last_sync_at") or ""))

    candidates.sort(key=lambda x: x[1])
    picked = candidates[:quota]

    new_progress: dict = {}
    success = 0
    failed = 0
    for code, _ in picked:
        result = sync_single_fund(code, config)
        prev_fail = (progress.get(code) or {}).get("fail_count") or 0
        if result["last_status"] == "ok":
            new_fail_count = 0
        else:
            new_fail_count = prev_fail + result["fail_count"]
        cooldown_until = None
        if _should_enter_cooldown(0, new_fail_count, config):
            cooldown_until = _cooldown_until(config)

        existing = progress.get(code, dict(EMPTY_PROGRESS_RECORD))
        merged_fields = dict(existing.get("fields") or {})
        merged_fields.update(result["fields"])
        new_progress[code] = {
            "last_sync_at": datetime.now().isoformat(timespec="seconds"),
            "last_status": result["last_status"],
            "fail_count": new_fail_count,
            "cooldown_until": cooldown_until,
            "fields": merged_fields,
        }

        if result["last_status"] == "ok":
            success += 1
        else:
            failed += 1
        _sleep_jitter(config.get("fund_interval_min", 1.5),
                      config.get("fund_interval_max", 3.5))

    save_progress(new_progress)

    if failed == 0:
        status = "ok"
    elif success > 0:
        status = "partial"
    else:
        status = "error"

    return {"status": status, "total": len(picked), "success": success, "failed": failed}
