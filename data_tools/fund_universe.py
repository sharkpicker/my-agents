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
    "sync_strategy": "priority",
    "cooldown_steps": [1, 3, 7, 14],
    "skip_ok_fields": True,
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
    - type / ftype 字段含「封闭式」或「场内 ETF」

    兼容:
    - 同时认 `type`(脏数据) 和 `ftype`(enrich 后新字段) 两个字段
    - 任一字段命中排除词即排除
    """
    code = str(record.get("code", "")).strip()
    name = str(record.get("name", ""))
    ftype = str(record.get("type", "") or record.get("ftype", "") or "")

    if code.startswith(("50", "51", "56", "58", "15", "16", "18")):
        return False
    if "封闭" in name or "场内" in name:
        return False
    if "封闭式" in ftype or "场内 ETF" in ftype:
        return False
    return True


def _parse_primary_response(text: str) -> list:
    """解析天天基金主端点返回的 `var db={chars:[...],datas:[...]}` 格式。

    主端点的 `datas` 数组元素字段顺序(经实测):
        [0] 基金代码
        [1] 基金简称
        [2] 拼音缩写
        [3] 最近单位净值(可能为空)
        [4] 累计净值(可能为空)   <-- 注意: 不是基金类型!
        [5] 单位净值
        [6] 累计净值
        ...

    主端点 **不返回 FTYPE**(基金类型),因此本函数只输出 code/name,
    FTYPE 字段需由调用方通过 `enrich_fund_list_with_ftype()` 单独补齐。
    """
    import re
    data_str = text
    if data_str.startswith("var db="):
        data_str = data_str[7:]
    data_str = data_str.strip().rstrip(";")

    def _add_quotes(s: str) -> str:
        result = []
        in_string = False
        escape = False
        i = 0
        while i < len(s):
            c = s[i]
            if escape:
                result.append(c)
                escape = False
                i += 1
                continue
            if c == "\\":
                result.append(c)
                escape = True
                i += 1
                continue
            if c == '"':
                in_string = not in_string
                result.append(c)
                i += 1
                continue
            if not in_string and c.isalpha():
                j = i
                while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                    j += 1
                if j < len(s) and s[j] == ":":
                    word = s[i:j]
                    if word not in ("true", "false", "null"):
                        result.append('"')
                        result.append(word)
                        result.append('"')
                        i = j
                        continue
                result.extend(s[i:j])
                i = j
                continue
            result.append(c)
            i += 1
        return "".join(result)

    data_str = _add_quotes(data_str)
    data_str = re.sub(r",(\s*[}\]])", r"\1", data_str)
    try:
        db = json.loads(data_str)
    except Exception:
        return []
    datas = db.get("datas", [])
    rows = []
    for item in datas:
        if len(item) >= 2:
            rows.append({
                "code": item[0],
                "name": item[1],
            })
    return rows


def fetch_fund_list_from_primary() -> list:
    """从天天基金主端点分页拉取全量基金列表。"""
    all_rows: list = []
    page = 1
    while True:
        url = f"{_FUND_LIST_PRIMARY}?page={page},20000&dt=ref&ft=all"
        resp = _fund_http_get(url)
        rows = _parse_primary_response(resp.text)
        if not rows:
            break
        all_rows.extend(rows)
        # 单页少于 20000 说明已到末页
        if len(rows) < 20000:
            break
        page += 1
    return all_rows


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


# ---------------------------------------------------------------------------
# 增量:为 fund_list 补全 ftype(基金类型) — 修复主端点不带 FTYPE 的问题
# ---------------------------------------------------------------------------


# 判定 "type" 字段是不是脏数据(数字 / 长字符串 / 含特殊符号)
def _is_dirty_type(value) -> bool:
    """判定基金列表中的 `type` 字段是否是历史脏数据。

    干净 type:    "混合型-灵活" / "股票型" / "债券型-中短债" / "QDII" 等
    脏 type:      "113.1107" (实际是累计净值) / "0.00%" / "" / None / 超长字符串
    """
    if value is None:
        return True
    s = str(value).strip()
    if not s:
        return True
    # 纯数字 / 百分比 → 脏(主端点累计净值 / 净值变动率)
    if s.replace(".", "").replace("-", "").replace("%", "").isdigit():
        return True
    # 长度过短或过长
    if len(s) > 30 or len(s) < 2:
        return True
    # 含不应该出现在 type 中的特殊符号
    if any(ch in s for ch in ("/", "\\", "?", "=", "<", ">")):
        return True
    return False


def enrich_fund_list_with_ftype(
    funds: list,
    batch_size: int = 500,
    sleep_min: float = 0.3,
    sleep_max: float = 0.8,
    progress_callback=None,
) -> dict:
    """为 fund_list 补全 `ftype` 字段(基金类型)。

    实现:
    - 对每只基金调用 fund_data.get_fund_ftype(code) 拿 F10 概况页的"基金类型"
    - 写入新字段 `ftype`,原 `type` 字段保持(可能是脏数据,留待 repair 清理)
    - 单只失败不影响整体
    - 请求间随机 sleep(sleep_min~sleep_max 秒),防止被风控

    参数:
        funds:               输入基金列表(就地修改)
        batch_size:          处理的基金数上限(0 = 不限)
        sleep_min/sleep_max: 单次请求间的 sleep 区间
        progress_callback:   可选,签名 (idx, total, code, ftype),外部可用于进度条

    返回: {"ok": int, "fail": int, "skipped": int, "total": int, "stats": {}}
    """
    from . import fund_data

    total = len(funds)
    end = total if not batch_size else min(batch_size, total)
    ok = 0
    fail = 0
    skipped = 0
    stats: dict[str, int] = {}

    for i in range(end):
        fund = funds[i]
        code = str(fund.get("code", "")).strip()
        if not code:
            skipped += 1
            continue
        try:
            ftype = fund_data.get_fund_ftype(code) or ""
        except Exception as e:
            logger.warning("[%s] enrich 失败: %s", code, e)
            ftype = ""
        if ftype:
            fund["ftype"] = ftype
            ok += 1
            stats[ftype] = stats.get(ftype, 0) + 1
        else:
            fail += 1
        if progress_callback:
            try:
                progress_callback(i + 1, end, code, ftype)
            except Exception:
                pass
        if sleep_max > 0:
            time.sleep(random.uniform(sleep_min, sleep_max))

    logger.info("enrich_fund_list_with_ftype: ok=%d fail=%d skipped=%d total=%d",
                ok, fail, skipped, end)
    return {
        "ok": ok,
        "fail": fail,
        "skipped": skipped,
        "total": end,
        "stats": dict(sorted(stats.items(), key=lambda x: -x[1])[:20]),
    }


def repair_fund_list(
    funds: list | None = None,
    dry_run: bool = False,
    batch_size: int = 0,
    force_repair: bool = False,
) -> dict:
    """清理 fund_list.json 中的脏 type 字段,并补齐 ftype。

    步骤:
    1. 把 `type` 字段中 _is_dirty_type 判为脏数据的清成 ""(默认行为)
       - force_repair=True 时,即便 type 看起来正常也强制清空(走 ftype 唯一来源)
    2. 调用 enrich_fund_list_with_ftype 补齐 ftype
    3. dry_run=True 时只统计不落盘,不入改原文件

    返回: {"before_dirty": int, "after_dirty": int, "ftype_added": int,
           "stats": {...}, "dry_run": bool, "saved": bool}
    """
    if funds is None:
        funds = load_fund_list()
        in_place = True
    else:
        in_place = False

    if not funds:
        return {
            "before_dirty": 0, "after_dirty": 0, "ftype_added": 0,
            "stats": {}, "dry_run": dry_run, "saved": False,
            "message": "fund_list 为空,无需 repair",
        }

    # 1) 统计 / 清理脏 type
    before_dirty = sum(1 for f in funds if _is_dirty_type(f.get("type")))
    for f in funds:
        if force_repair or _is_dirty_type(f.get("type")):
            f["type"] = ""

    if dry_run:
        return {
            "before_dirty": before_dirty,
            "after_dirty": sum(1 for f in funds if _is_dirty_type(f.get("type"))),
            "ftype_added": 0,
            "stats": {},
            "dry_run": True,
            "saved": False,
        }

    # 2) 补齐 ftype
    result = enrich_fund_list_with_ftype(funds, batch_size=batch_size)
    ftype_added = result["ok"]

    # 3) 落盘:仅在 funds=None(调用方使用磁盘默认路径)时才落盘
    #    避免 caller 传入的测试数据被错误写回 fund_list.json
    saved = False
    if in_place:
        save_fund_list(funds)
        saved = True
    return {
        "before_dirty": before_dirty,
        "after_dirty": sum(1 for f in funds if _is_dirty_type(f.get("type"))),
        "ftype_added": ftype_added,
        "stats": result.get("stats", {}),
        "dry_run": False,
        "saved": saved,
    }


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


def sync_single_fund(code: str, config: dict, existing_fields: dict | None = None, force: bool = False) -> dict:
    """采集单只基金字段，支持跳过已 ok 的字段。

    Args:
        code: 基金代码
        config: 配置 dict
        existing_fields: 已有字段状态 {"nav": "ok", ...}
        force: 是否强制刷新所有字段

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
    skip_ok = config.get("skip_ok_fields", True) and not force
    for name, fetcher in _FIELD_FETCHERS:
        prev_status = (existing_fields or {}).get(name)
        if skip_ok and prev_status == "ok":
            fields[name] = "ok"
            all_failed = False
            continue
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
    """累计失败次数 > 0 就进入冷却(按阶梯计算冷却天数)。"""
    return new_fail_count > 0


def _cooldown_days(fail_count: int, config: dict) -> int:
    """根据累计失败次数计算冷却天数(指数阶梯)。"""
    steps = config.get("cooldown_steps", [1, 3, 7, 14])
    if fail_count <= 0:
        return 0
    idx = min(fail_count - 1, len(steps) - 1)
    return steps[idx]


def _cooldown_until(fail_count: int, config: dict) -> str:
    days = _cooldown_days(fail_count, config)
    return (datetime.now() + timedelta(days=days)).isoformat()


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
        if not rec or not rec.get("last_sync_at"):
            priority = 0
        elif rec.get("last_status") in ("partial", "failed"):
            priority = 1
        else:
            priority = 2
        last_sync = (rec or {}).get("last_sync_at") or ""
        candidates.append((code, priority, last_sync))

    candidates.sort(key=lambda x: (x[1], x[2]))
    picked = [c[0] for c in candidates[:quota]]

    new_progress: dict = {}
    success = 0
    failed = 0
    for code in picked:
        existing = progress.get(code, dict(EMPTY_PROGRESS_RECORD))
        existing_fields = existing.get("fields") or {}
        result = sync_single_fund(code, config, existing_fields, force=force)
        prev_fail = (progress.get(code) or {}).get("fail_count") or 0
        if result["last_status"] == "ok":
            new_fail_count = 0
        else:
            new_fail_count = prev_fail + result["fail_count"]
        cooldown_until = None
        if _should_enter_cooldown(0, new_fail_count, config):
            cooldown_until = _cooldown_until(new_fail_count, config)

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

    merged_progress = dict(progress)
    merged_progress.update(new_progress)
    save_progress(merged_progress)

    if failed == 0:
        status = "ok"
    elif success > 0:
        status = "partial"
    else:
        status = "error"

    return {"status": status, "total": len(picked), "success": success, "failed": failed}


def show_status() -> dict:
    """输出当前调度器状态摘要。"""
    funds = load_fund_list()
    progress = load_progress()
    config = load_config()

    total_funds = len(funds)
    in_cooldown = 0
    needs_sync = 0
    status_breakdown = {"ok": 0, "partial": 0, "failed": 0, "unknown": 0}
    field_stats = {}
    last_run = None

    progressed_codes = set(progress.keys())
    for code in progressed_codes:
        rec = progress[code]
        if is_in_cooldown(rec, config):
            in_cooldown += 1
        st = rec.get("last_status")
        if st in status_breakdown:
            status_breakdown[st] += 1
        else:
            status_breakdown["unknown"] += 1
        ts = rec.get("last_sync_at")
        if ts and (last_run is None or ts > last_run):
            last_run = ts
        fields = rec.get("fields") or {}
        for fname, fstatus in fields.items():
            if fname not in field_stats:
                field_stats[fname] = {"ok": 0, "failed": 0}
            if fstatus == "ok":
                field_stats[fname]["ok"] += 1
            elif fstatus == "failed":
                field_stats[fname]["failed"] += 1

    needs_sync = total_funds - len(progressed_codes)
    for code in progressed_codes:
        rec = progress[code]
        if not is_in_cooldown(rec, config) and rec.get("last_status") != "ok":
            needs_sync += 1

    result = {
        "total_funds": total_funds,
        "in_cooldown": in_cooldown,
        "needs_sync": needs_sync,
        "last_run": last_run,
        "status_breakdown": status_breakdown,
        "progress_size": len(progress),
        "field_stats": field_stats,
    }

    print(f"=== Fund Universe 状态 ===")
    print(f"基金总数     : {result['total_funds']}")
    print(f"已同步进度   : {result['progress_size']}")
    print(f"冷却中       : {result['in_cooldown']}")
    print(f"待同步       : {result['needs_sync']}")
    print(f"最近同步时间 : {result['last_run'] or 'N/A'}")
    print(f"状态分布     : ok={status_breakdown['ok']} "
          f"partial={status_breakdown['partial']} "
          f"failed={status_breakdown['failed']} "
          f"unknown={status_breakdown['unknown']}")
    if field_stats:
        print(f"字段级统计   :")
        for fname, fstats in sorted(field_stats.items()):
            total = fstats["ok"] + fstats["failed"]
            pct = (fstats["ok"] / total * 100) if total > 0 else 0
            print(f"  {fname:12s}: ok={fstats['ok']:5d} "
                  f"failed={fstats['failed']:4d} ({pct:5.1f}%)")
    return result
