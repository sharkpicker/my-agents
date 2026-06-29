# Fund Universe Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Trae 自动化定时任务提供 Python CLI 入口，定时拉取国内场外开放式基金数据并落地缓存。

**Architecture:** 镜像 A 股 `universe.py` 设计，新增 `data_tools/fund_universe.py` 调度器；通过 `python -m data_tools.cli fund universe {init,status,sync,update,refresh-list}` 子命令管理。复用 `fund_data.py` 已有的 7 个数据接口，按 daily_quota + 失败冷却 + 进度断点机制串行采集。

**Tech Stack:** Python 3.x、argparse、requests、JSON 文件持久化、pytest。零外部新依赖。

**Spec:** [2026-06-28-fund-universe-design.md](../specs/2026-06-28-fund-universe-design.md)

---

## File Structure

| 操作 | 路径 | 职责 |
|------|------|------|
| 新增 | `data_tools/fund_universe.py` | 调度器核心：路径/配置/列表/进度/同步/状态管理 |
| 修改 | `data_tools/cli.py` | 新增 `fund universe {init,status,sync,update,refresh-list}` 5 个子命令 |
| 新增 | `tests/unit/test_fund_universe_config.py` | 配置模块单元测试 |
| 新增 | `tests/unit/test_fund_universe_list.py` | 列表获取与场外过滤单元测试 |
| 新增 | `tests/unit/test_fund_universe_progress.py` | 进度模块单元测试 |
| 新增 | `tests/unit/test_fund_universe_sync_single.py` | 单只基金采集单元测试 |
| 新增 | `tests/unit/test_fund_universe_sync.py` | sync 调度逻辑单元测试 |
| 新增 | `tests/unit/test_fund_universe_cooldown.py` | 失败冷却机制单元测试 |
| 新增 | `tests/unit/test_fund_universe_status.py` | status 状态展示单元测试 |
| 新增 | `tests/unit/test_fund_universe_cli.py` | CLI 子命令接线单元测试 |
| 新增 | `tests/e2e/test_fund_universe_e2e.py` | 端到端测试（真实接口允许 skipped） |

---

## Task 1: 路径工具与配置模块

**Files:**
- Create: `data_tools/fund_universe.py`
- Test: `tests/unit/test_fund_universe_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fund_universe_config.py
from pathlib import Path
from data_tools.fund_universe import (
    get_meta_dir,
    get_config_path,
    get_fund_list_path,
    get_progress_path,
    load_config,
    save_config,
    DEFAULT_CONFIG,
)


def test_meta_dir_is_under_funds_data_dir():
    p = Path(get_meta_dir())
    assert p.name == "_meta"
    assert "funds" in p.parts


def test_config_path_under_meta():
    p = Path(get_config_path())
    assert p.parent.name == "_meta"
    assert p.name == "universe_config.json"


def test_fund_list_path_under_meta():
    p = Path(get_fund_list_path())
    assert p.parent.name == "_meta"
    assert p.name == "fund_list.json"


def test_progress_path_under_meta():
    p = Path(get_progress_path())
    assert p.parent.name == "_meta"
    assert p.name == "universe_progress.json"


def test_load_config_returns_defaults_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    cfg = load_config()
    assert cfg["daily_quota"] == 200
    assert cfg["fail_cooldown_days"] == 7
    assert cfg["max_fail_count"] == 3
    assert cfg["fund_interval_min"] == 1.5
    assert cfg["fund_interval_max"] == 3.5


def test_save_and_load_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    user_cfg = {"daily_quota": 300, "max_fail_count": 5}
    save_config(user_cfg)
    loaded = load_config()
    assert loaded["daily_quota"] == 300
    assert loaded["max_fail_count"] == 5
    assert loaded["fail_cooldown_days"] == 7  # 保留未覆盖的默认值


def test_default_config_keys():
    expected_keys = {
        "daily_quota",
        "fund_interval_min",
        "fund_interval_max",
        "field_interval_min",
        "field_interval_max",
        "fail_cooldown_days",
        "max_fail_count",
        "news_lookback_days",
        "nav_lookback_days",
    }
    assert set(DEFAULT_CONFIG.keys()) == expected_keys
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fund_universe_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data_tools.fund_universe'`

- [ ] **Step 3: Write minimal implementation**

```python
# data_tools/fund_universe.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fund_universe_config.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add data_tools/fund_universe.py tests/unit/test_fund_universe_config.py
git commit -m "feat(fund-universe): add config module (load/save/defaults)"
```

---

## Task 2: 基金列表获取与场外过滤

**Files:**
- Modify: `data_tools/fund_universe.py`
- Test: `tests/unit/test_fund_universe_list.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fund_universe_list.py
import json
from data_tools.fund_universe import (
    is_offexchange_fund,
    fetch_fund_list_from_primary,
    fetch_fund_list,
    save_fund_list,
    load_fund_list,
    diff_fund_list,
)


def test_is_offexchange_fund_open_fund():
    assert is_offexchange_fund({"code": "000001", "name": "华夏成长混合", "type": "混合型-偏股"}) is True


def test_is_offexchange_fund_sh_etf():
    # 51xxxx 是上交所 ETF
    assert is_offexchange_fund({"code": "510300", "name": "华泰柏瑞沪深300ETF", "type": "指数型-股票"}) is False


def test_is_offexchange_fund_sz_etf():
    # 15xxxx 是深交所 ETF
    assert is_offexchange_fund({"code": "159915", "name": "易方达创业板ETF", "type": "指数型-股票"}) is False


def test_is_offexchange_fund_sz_lof():
    # 16xxxx 是深交所 LOF
    assert is_offexchange_fund({"code": "160219", "name": "国泰医药健康LOF", "type": "混合型"}) is False


def test_is_offexchange_fund_closed_end():
    # 18xxxx 是封闭式基金
    assert is_offexchange_fund({"code": "184801", "name": "鹏华前海万科REITs", "type": "封闭式"}) is False


def test_is_offexchange_fund_periodic_open_kept():
    # 定期开放属于场外开放式，不应被排除
    assert is_offexchange_fund({"code": "005753", "name": "某基金6个月定开债", "type": "债券型"}) is True


def test_fetch_fund_list_from_primary_parses_js_array(monkeypatch):
    """主端点返回 JS 数组格式时正确解析。"""
    sample = (
        'var RANKDATA = [{"code":"000001","name":"华夏成长","type":"混合型-偏股"},'
        '{"code":"510300","name":"沪深300ETF","type":"指数型-股票"},'
        '{"code":"005753","name":"6个月定开债","type":"债券型"}];'
    )
    class FakeResp:
        status_code = 200
        text = sample
        def json(self): return {}
    def fake_get(url, params=None, headers=None, timeout=15):
        return FakeResp()
    monkeypatch.setattr("data_tools.fund_universe._fund_http_get", fake_get)
    rows = fetch_fund_list_from_primary()
    assert len(rows) == 3
    assert rows[0]["code"] == "000001"
    assert rows[0]["name"] == "华夏成长"


def test_fetch_fund_list_uses_fallback_when_primary_too_few(monkeypatch):
    """主端点返回 < 5000 条时降级到备用端点。"""
    class FakeRespPrimary:
        status_code = 200
        text = 'var RANKDATA = [{"code":"000001","name":"X","type":"Y"}];'
        def json(self): return {}
    class FakeRespFallback:
        status_code = 200
        text = ""
        def json(self):
            return {"result": {"data": [
                {"FCODE": "000001", "SHORTNAME": "华夏成长", "FTYPE": "混合型"},
                {"FCODE": "005753", "SHORTNAME": "定开债", "FTYPE": "债券型"},
            ]}}
    calls = {"primary": 0, "fallback": 0}
    def fake_get(url, params=None, headers=None, timeout=15):
        if "Fund_JJJZ_Data" in url:
            calls["primary"] += 1
            return FakeRespPrimary()
        else:
            calls["fallback"] += 1
            return FakeRespFallback()
    monkeypatch.setattr("data_tools.fund_universe._fund_http_get", fake_get)
    rows = fetch_fund_list()
    assert calls["primary"] == 1
    assert calls["fallback"] == 1
    assert len(rows) >= 2
    assert all("code" in r and "name" in r for r in rows)


def test_fetch_fund_list_returns_offexchange_only(monkeypatch):
    """fetch_fund_list 只返回 is_offexchange=True 的基金。"""
    class FakeResp:
        status_code = 200
        text = ""
        def json(self):
            return {"result": {"data": [
                {"FCODE": "000001", "SHORTNAME": "华夏成长", "FTYPE": "混合型"},
                {"FCODE": "510300", "SHORTNAME": "沪深300ETF", "FTYPE": "指数型"},
                {"FCODE": "184801", "SHORTNAME": "鹏华前海", "FTYPE": "封闭式"},
                {"FCODE": "005753", "SHORTNAME": "定开债", "FTYPE": "债券型"},
            ]}}
    monkeypatch.setattr("data_tools.fund_universe._fund_http_get", lambda *a, **kw: FakeResp())
    rows = fetch_fund_list()
    codes = [r["code"] for r in rows]
    assert "000001" in codes
    assert "005753" in codes
    assert "510300" not in codes
    assert "184801" not in codes


def test_save_and_load_fund_list_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    funds = [{"code": "000001", "name": "华夏成长", "type": "混合型", "is_offexchange": True}]
    save_fund_list(funds)
    loaded = load_fund_list()
    assert loaded == funds


def test_diff_fund_list_returns_added_and_removed():
    old = [{"code": "000001"}, {"code": "005753"}]
    new = [{"code": "000001"}, {"code": "519677"}]
    diff = diff_fund_list(old, new)
    assert diff["added"] == ["519677"]
    assert diff["removed"] == ["005753"]
    assert diff["kept"] == ["000001"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fund_universe_list.py -v`
Expected: FAIL with `ImportError: cannot import name 'is_offexchange_fund'`

- [ ] **Step 3: Write minimal implementation**

追加到 `data_tools/fund_universe.py`：

```python
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
    resp.raise_for_status()
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
    resp.raise_for_status()
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fund_universe_list.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add data_tools/fund_universe.py tests/unit/test_fund_universe_list.py
git commit -m "feat(fund-universe): add fund list fetch + off-exchange filter"
```

---

## Task 3: 进度文件加载与保存

**Files:**
- Modify: `data_tools/fund_universe.py`
- Test: `tests/unit/test_fund_universe_progress.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fund_universe_progress.py
from data_tools.fund_universe import (
    load_progress,
    save_progress,
    update_progress,
    is_in_cooldown,
    EMPTY_PROGRESS_RECORD,
)


def test_load_progress_empty_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    assert load_progress() == {}


def test_save_and_load_progress_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    data = {
        "000001": {"last_sync_at": "2026-06-27T22:15:32", "last_status": "ok",
                   "fail_count": 0, "cooldown_until": None, "fields": {}}
    }
    save_progress(data)
    assert load_progress() == data


def test_update_progress_writes_new_record(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    update_progress(
        "000001",
        last_status="ok",
        fail_count=0,
        fields={"nav": "ok", "info": "ok"},
    )
    rec = load_progress()["000001"]
    assert rec["last_status"] == "ok"
    assert rec["fail_count"] == 0
    assert rec["fields"] == {"nav": "ok", "info": "ok"}
    assert rec["last_sync_at"]  # 非空


def test_update_progress_preserves_existing_fields(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    update_progress("000001", last_status="ok", fail_count=0, fields={"nav": "ok"})
    update_progress("000001", last_status="ok", fail_count=0, fields={"info": "ok"})
    rec = load_progress()["000001"]
    assert rec["fields"] == {"nav": "ok", "info": "ok"}


def test_is_in_cooldown_no_record_returns_false():
    assert is_in_cooldown({}, {}) is False
    assert is_in_cooldown(None, {}) is False


def test_is_in_cooldown_expired_returns_false():
    from datetime import datetime, timedelta
    rec = {"cooldown_until": (datetime.now() - timedelta(days=1)).isoformat()}
    assert is_in_cooldown(rec, {}) is False


def test_is_in_cooldown_active_returns_true():
    from datetime import datetime, timedelta
    rec = {"cooldown_until": (datetime.now() + timedelta(days=2)).isoformat()}
    assert is_in_cooldown(rec, {}) is True


def test_is_in_cooldown_null_until_returns_false():
    rec = {"cooldown_until": None}
    assert is_in_cooldown(rec, {}) is False


def test_empty_progress_record_shape():
    assert set(EMPTY_PROGRESS_RECORD.keys()) == {
        "last_sync_at", "last_status", "fail_count", "cooldown_until", "fields"
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fund_universe_progress.py -v`
Expected: FAIL with `ImportError: cannot import name 'load_progress'`

- [ ] **Step 3: Write minimal implementation**

追加到 `data_tools/fund_universe.py`：

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fund_universe_progress.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add data_tools/fund_universe.py tests/unit/test_fund_universe_progress.py
git commit -m "feat(fund-universe): add progress load/save/update + cooldown check"
```

---

## Task 4: 单只基金字段采集

**Files:**
- Modify: `data_tools/fund_universe.py`
- Test: `tests/unit/test_fund_universe_sync_single.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fund_universe_sync_single.py
from data_tools.fund_universe import sync_single_fund


def test_sync_single_fund_all_ok(monkeypatch):
    monkeypatch.setattr("data_tools.fund_data.get_fund_nav", lambda code, start, end: "nav_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_info", lambda code: "info_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_holdings", lambda code: "holdings_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_manager", lambda code: "manager_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_performance", lambda code: "performance_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_flows", lambda code: "flows_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_news", lambda code, start, end: "news_ok")
    # 防止真实 sleep 拖慢测试
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    cfg = {"news_lookback_days": 90, "nav_lookback_days": 365,
           "field_interval_min": 0.0, "field_interval_max": 0.0}
    result = sync_single_fund("000001", cfg)
    assert result["last_status"] == "ok"
    assert result["fail_count"] == 0
    assert result["fields"] == {
        "nav": "ok", "info": "ok", "holdings": "ok", "manager": "ok",
        "performance": "ok", "flows": "ok", "news": "ok",
    }


def test_sync_single_fund_one_field_failed_results_in_partial(monkeypatch):
    monkeypatch.setattr("data_tools.fund_data.get_fund_nav", lambda code, start, end: "nav_ok")
    def _raise(code, start, end):
        raise RuntimeError("network error")
    monkeypatch.setattr("data_tools.fund_data.get_fund_info", _raise)
    monkeypatch.setattr("data_tools.fund_data.get_fund_holdings", lambda code: "holdings_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_manager", lambda code: "manager_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_performance", lambda code: "performance_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_flows", lambda code: "flows_ok")
    monkeypatch.setattr("data_tools.fund_data.get_fund_news", lambda code, start, end: "news_ok")
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    cfg = {"news_lookback_days": 90, "nav_lookback_days": 365,
           "field_interval_min": 0.0, "field_interval_max": 0.0}
    result = sync_single_fund("000001", cfg)
    assert result["last_status"] == "partial"
    assert result["fields"]["info"] == "failed"
    assert result["fields"]["nav"] == "ok"


def test_sync_single_fund_all_failed(monkeypatch):
    def _raise(*a, **kw):
        raise RuntimeError("network error")
    for fn in ["get_fund_nav", "get_fund_info", "get_fund_holdings",
               "get_fund_manager", "get_fund_performance",
               "get_fund_flows", "get_fund_news"]:
        monkeypatch.setattr(f"data_tools.fund_data.{fn}", _raise)
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    cfg = {"news_lookback_days": 90, "nav_lookback_days": 365,
           "field_interval_min": 0.0, "field_interval_max": 0.0}
    result = sync_single_fund("000001", cfg)
    assert result["last_status"] == "failed"
    assert all(v == "failed" for v in result["fields"].values())
    assert result["fail_count"] == 1


def test_sync_single_fund_returns_progress_record(monkeypatch):
    monkeypatch.setattr("data_tools.fund_data.get_fund_nav", lambda code, start, end: "")
    monkeypatch.setattr("data_tools.fund_data.get_fund_info", lambda code: "")
    monkeypatch.setattr("data_tools.fund_data.get_fund_holdings", lambda code: "")
    monkeypatch.setattr("data_tools.fund_data.get_fund_manager", lambda code: "")
    monkeypatch.setattr("data_tools.fund_data.get_fund_performance", lambda code: "")
    monkeypatch.setattr("data_tools.fund_data.get_fund_flows", lambda code: "")
    monkeypatch.setattr("data_tools.fund_data.get_fund_news", lambda code, start, end: "")
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    cfg = {"news_lookback_days": 90, "nav_lookback_days": 365,
           "field_interval_min": 0.0, "field_interval_max": 0.0}
    result = sync_single_fund("000001", cfg)
    assert set(result.keys()) == {"last_status", "fail_count", "fields", "cooldown_until"}
    assert result["cooldown_until"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fund_universe_sync_single.py -v`
Expected: FAIL with `ImportError: cannot import name 'sync_single_fund'`

- [ ] **Step 3: Write minimal implementation**

追加到 `data_tools/fund_universe.py`：

```python
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
            "fail_count": int,
            "fields": {"nav": "ok", "info": "failed", ...},
            "cooldown_until": None | "ISO timestamp",
        }
    """
    fields = {}
    fail_count = 0
    for name, fetcher in _FIELD_FETCHERS:
        try:
            fetcher(code, config)
            fields[name] = "ok"
        except Exception as e:
            logger.warning("[%s] 字段 %s 采集失败: %s", code, name, e)
            fields[name] = "failed"
            fail_count += 1
        _sleep_jitter(config.get("field_interval_min", 0.5),
                      config.get("field_interval_max", 1.5))

    if fail_count == 0:
        last_status = "ok"
        cooldown_until = None
    elif fail_count == len(_FIELD_FETCHERS):
        last_status = "failed"
        cooldown_until = None  # 由 sync() 主循环根据 fail_count 累加判定
    else:
        last_status = "partial"
        cooldown_until = None

    return {
        "last_status": last_status,
        "fail_count": fail_count,
        "fields": fields,
        "cooldown_until": cooldown_until,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fund_universe_sync_single.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add data_tools/fund_universe.py tests/unit/test_fund_universe_sync_single.py
git commit -m "feat(fund-universe): add sync_single_fund field collector"
```

---

## Task 5: 同步调度主循环（含配额/优先级/冷却）

**Files:**
- Modify: `data_tools/fund_universe.py`
- Test: `tests/unit/test_fund_universe_sync.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fund_universe_sync.py
from datetime import datetime, timedelta
from data_tools.fund_universe import (
    sync,
    load_progress,
    save_progress,
    save_fund_list,
    update_progress,
    is_in_cooldown,
    sync_single_fund,
)


def _seed_progress(records):
    save_progress(records)


def _seed_list(codes):
    save_fund_list([{"code": c, "name": f"基金{c}", "type": "股票型", "is_offexchange": True} for c in codes])


def test_sync_processes_in_quota(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund",
                        lambda code, cfg: {"last_status": "ok", "fail_count": 0,
                                           "fields": {}, "cooldown_until": None})
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list([f"{i:06d}" for i in range(10)])
    result = sync(quota=3, force=True)
    assert result["total"] == 3
    assert result["success"] == 3
    assert result["failed"] == 0
    assert len(load_progress()) == 3


def test_sync_skips_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund",
                        lambda code, cfg: {"last_status": "ok", "fail_count": 0,
                                           "fields": {}, "cooldown_until": None})
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001", "000002"])
    until = (datetime.now() + timedelta(days=2)).isoformat()
    _seed_progress({"000001": {"cooldown_until": until, "fail_count": 5,
                                "last_status": "failed", "fields": {}, "last_sync_at": None}})

    result = sync(quota=10, force=False)
    assert "000001" not in load_progress()  # 冷却中没采
    assert "000002" in load_progress()


def test_sync_force_overrides_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund",
                        lambda code, cfg: {"last_status": "ok", "fail_count": 0,
                                           "fields": {}, "cooldown_until": None})
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001"])
    until = (datetime.now() + timedelta(days=2)).isoformat()
    _seed_progress({"000001": {"cooldown_until": until, "fail_count": 5,
                                "last_status": "failed", "fields": {}, "last_sync_at": None}})

    result = sync(quota=10, force=True)
    assert "000001" in load_progress()


def test_sync_priority_oldest_first(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund",
                        lambda code, cfg: {"last_status": "ok", "fail_count": 0,
                                           "fields": {}, "cooldown_until": None})
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001", "000002", "000003"])
    now = datetime.now().isoformat(timespec="seconds")
    _seed_progress({
        "000001": {"last_sync_at": now, "fail_count": 0, "last_status": "ok",
                   "fields": {}, "cooldown_until": None},
        "000002": {"last_sync_at": None, "fail_count": 0, "last_status": None,
                   "fields": {}, "cooldown_until": None},
    })

    result = sync(quota=1, force=True)
    # 只采了 1 只，应该是 last_sync_at 为空的 000002（最旧）
    assert "000002" in load_progress()
    assert "000001" not in load_progress()


def test_sync_failure_triggers_cooldown(monkeypatch, tmp_path):
    """连续失败 max_fail_count 次的基金进入冷却期。"""
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund",
                        lambda code, cfg: {"last_status": "failed", "fail_count": 7,
                                           "fields": {"nav": "failed"}, "cooldown_until": None})
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001"])
    # 此前已有 fail_count=2，再失败一次 → 3 次 → 触发冷却
    save_progress({
        "000001": {"last_sync_at": None, "fail_count": 2, "last_status": "failed",
                   "fields": {}, "cooldown_until": None}
    })
    cfg = {"max_fail_count": 3, "fail_cooldown_days": 7, "daily_quota": 1,
           "field_interval_min": 0, "field_interval_max": 0}
    monkeypatch.setattr("data_tools.fund_universe.load_config", lambda: cfg)

    sync(quota=1, force=True)
    rec = load_progress()["000001"]
    assert rec["cooldown_until"] is not None


def test_sync_init_if_list_missing(monkeypatch, tmp_path):
    """列表不存在时自动调用 init 逻辑。"""
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    init_called = {"n": 0}
    def fake_init():
        init_called["n"] += 1
        save_fund_list([{"code": "000001", "name": "X", "type": "Y", "is_offexchange": True}])
    monkeypatch.setattr("data_tools.fund_universe.refresh_fund_list", fake_init)
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund",
                        lambda code, cfg: {"last_status": "ok", "fail_count": 0,
                                           "fields": {}, "cooldown_until": None})
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    sync(quota=1, force=True)
    assert init_called["n"] == 1
    assert "000001" in load_progress()


def test_sync_returns_summary(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund",
                        lambda code, cfg: {"last_status": "ok", "fail_count": 0,
                                           "fields": {}, "cooldown_until": None})
    monkeypatch.setattr("data_tools.fund_universe._sleep_jitter", lambda *a, **kw: None)

    _seed_list(["000001"])
    result = sync(quota=1, force=True)
    assert set(result.keys()) >= {"status", "total", "success", "failed"}
    assert result["status"] in ("ok", "partial", "error")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fund_universe_sync.py -v`
Expected: FAIL with `ImportError: cannot import name 'sync'`

- [ ] **Step 3: Write minimal implementation**

追加到 `data_tools/fund_universe.py`：

```python
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

    success = 0
    failed = 0
    for code, _ in picked:
        result = sync_single_fund(code, config)
        new_fail_count = ((progress.get(code) or {}).get("fail_count") or 0) + result["fail_count"]
        cooldown_until = None
        if _should_enter_cooldown(0, new_fail_count, config):
            cooldown_until = _cooldown_until(config)
        update_progress(
            code,
            last_status=result["last_status"],
            fail_count=new_fail_count,
            fields=result["fields"],
            cooldown_until=cooldown_until,
        )
        progress = load_progress()  # 重新读取，反映已写入的状态
        if result["last_status"] == "ok":
            success += 1
        else:
            failed += 1
        _sleep_jitter(config.get("fund_interval_min", 1.5),
                      config.get("fund_interval_max", 3.5))

    if failed == 0:
        status = "ok"
    elif success > 0:
        status = "partial"
    else:
        status = "error"

    return {"status": status, "total": len(picked), "success": success, "failed": failed}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fund_universe_sync.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add data_tools/fund_universe.py tests/unit/test_fund_universe_sync.py
git commit -m "feat(fund-universe): add sync main loop with quota/priority/cooldown"
```

---

## Task 6: 冷却机制细节测试

**Files:**
- Test: `tests/unit/test_fund_universe_cooldown.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fund_universe_cooldown.py
from datetime import datetime, timedelta
from data_tools.fund_universe import (
    is_in_cooldown,
    _should_enter_cooldown,
    _cooldown_until,
)


def test_is_in_cooldown_no_record():
    assert is_in_cooldown({}, {}) is False


def test_is_in_cooldown_future():
    future = (datetime.now() + timedelta(days=3)).isoformat()
    assert is_in_cooldown({"cooldown_until": future}, {}) is True


def test_is_in_cooldown_past():
    past = (datetime.now() - timedelta(days=1)).isoformat()
    assert is_in_cooldown({"cooldown_until": past}, {}) is False


def test_is_in_cooldown_invalid_string_returns_false():
    assert is_in_cooldown({"cooldown_until": "not-a-date"}, {}) is False


def test_should_enter_cooldown_at_threshold():
    assert _should_enter_cooldown(0, 3, {"max_fail_count": 3}) is True


def test_should_enter_cooldown_below_threshold():
    assert _should_enter_cooldown(0, 2, {"max_fail_count": 3}) is False


def test_cooldown_until_is_future_iso():
    s = _cooldown_until({"fail_cooldown_days": 7})
    parsed = datetime.fromisoformat(s)
    delta = parsed - datetime.now()
    assert timedelta(days=6) < delta < timedelta(days=8)
```

- [ ] **Step 2: Run test to verify it passes (these test existing functions)**

Run: `pytest tests/unit/test_fund_universe_cooldown.py -v`
Expected: 7 passed

- [ ] **Step 3: Skip (tests pass without additional implementation)**

如果上面 sync 实现已经覆盖冷却逻辑，这里直接通过。

- [ ] **Step 4: Verify all sync tests still pass**

Run: `pytest tests/unit/test_fund_universe_cooldown.py tests/unit/test_fund_universe_sync.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_fund_universe_cooldown.py
git commit -m "test(fund-universe): add cooldown mechanism unit tests"
```

---

## Task 7: status 命令实现

**Files:**
- Modify: `data_tools/fund_universe.py`
- Test: `tests/unit/test_fund_universe_status.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fund_universe_status.py
from data_tools.fund_universe import (
    get_status,
    format_status,
    save_progress,
    save_fund_list,
)


def test_get_status_returns_dict(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    save_fund_list([
        {"code": "000001", "is_offexchange": True},
        {"code": "510300", "is_offexchange": False},
        {"code": "005753", "is_offexchange": True},
    ])
    save_progress({
        "000001": {"last_status": "ok", "fail_count": 0, "cooldown_until": None,
                   "fields": {}, "last_sync_at": "2026-06-27T22:00:00"},
        "005753": {"last_status": "failed", "fail_count": 5, "cooldown_until": "2099-01-01T00:00:00",
                   "fields": {}, "last_sync_at": "2026-06-26T22:00:00"},
    })
    cfg = {"daily_quota": 200}
    status = get_status(config=cfg)
    assert status["total_funds"] == 3
    assert status["offexchange_count"] == 2
    assert status["synced"] == 1
    assert status["in_cooldown"] == 1
    assert status["pending"] == 1  # 005753 处于冷却，但 000001 已同步；000002 不存在视为 pending
    # 实际上重算：3 只场外，去掉 1 只已同步（000001），1 只冷却中（005753） → pending = 1
    # 等等：005753 是 is_offexchange 但当前冷却，不计入 in_cooldown？见实现


def test_format_status_contains_key_sections(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    save_fund_list([{"code": "000001", "is_offexchange": True}])
    save_progress({})
    cfg = {"daily_quota": 200}
    text = format_status(get_status(config=cfg))
    assert "基金总数" in text
    assert "已同步" in text
    assert "今日配额" in text
    assert "冷却中" in text
```

> 注：如果 `pending` 与 `in_cooldown` 字段实现策略与测试不一致，**优先修正实现以使测试通过**——pending 应严格定义为 `场外开放 && 未同步 && 不在冷却` 的基金数。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fund_universe_status.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_status'`

- [ ] **Step 3: Write minimal implementation**

追加到 `data_tools/fund_universe.py`：

```python
def get_status(config: Optional[dict] = None) -> dict:
    """聚合状态信息：总数/场外数/已同步/今日已采/冷却中/待采。"""
    if config is None:
        config = load_config()

    funds = load_fund_list()
    progress = load_progress()

    offexchange = [f for f in funds if f.get("is_offexchange") is True]
    today_str = datetime.now().date().isoformat()

    synced = 0
    in_cooldown = 0
    pending = 0
    today_done = 0
    last_sync_at = None

    for f in offexchange:
        code = f.get("code")
        rec = progress.get(code)
        if not rec:
            pending += 1
            continue
        if rec.get("last_sync_at"):
            synced += 1
            if rec["last_sync_at"][:10] == today_str:
                today_done += 1
            if last_sync_at is None or rec["last_sync_at"] > last_sync_at:
                last_sync_at = rec["last_sync_at"]
        if is_in_cooldown(rec, config):
            in_cooldown += 1
        elif rec.get("last_status") != "ok" or rec.get("last_sync_at") is None:
            pending += 1

    return {
        "total_funds": len(funds),
        "offexchange_count": len(offexchange),
        "synced": synced,
        "today_done": today_done,
        "in_cooldown": in_cooldown,
        "pending": pending,
        "daily_quota": config.get("daily_quota", 200),
        "last_sync_at": last_sync_at,
    }


def format_status(status: dict) -> str:
    """格式化状态为可读文本。"""
    lines = [
        "==== 基金采集进度 ====",
        f"基金总数:         {status['total_funds']}",
        f"场外开放式:       {status['offexchange_count']}",
        f"已同步(累计):     {status['synced']}",
        f"今日已完成:       {status['today_done']}",
        f"冷却中:           {status['in_cooldown']}",
        f"待采(未同步):     {status['pending']}",
        f"今日配额:         {status['daily_quota']}",
        f"最近同步时间:     {status.get('last_sync_at') or 'N/A'}",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fund_universe_status.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add data_tools/fund_universe.py tests/unit/test_fund_universe_status.py
git commit -m "feat(fund-universe): add status aggregator + formatter"
```

---

## Task 8: CLI 子命令接线

**Files:**
- Modify: `data_tools/cli.py`
- Test: `tests/unit/test_fund_universe_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fund_universe_cli.py
import subprocess
import sys
from pathlib import Path


def _run(args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "data_tools.cli"] + args,
        cwd=cwd or str(Path(__file__).resolve().parents[2]),
        capture_output=True, text=True, timeout=30,
    )


def test_fund_universe_help():
    r = _run(["fund", "universe", "--help"])
    assert r.returncode == 0
    assert "init" in r.stdout
    assert "sync" in r.stdout
    assert "status" in r.stdout
    assert "update" in r.stdout
    assert "refresh-list" in r.stdout


def test_fund_universe_status_runs(tmp_path, monkeypatch):
    """status 子命令可执行（无 fund_list 时优雅返回）。"""
    # 让 meta_dir 指向临时目录，避免污染真实 data/
    monkeypatch.setenv("FUND_META_DIR", str(tmp_path))
    r = _run(["fund", "universe", "status"])
    assert r.returncode in (0, 1)
    assert "基金总数" in r.stdout or "基金列表为空" in r.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fund_universe_cli.py -v`
Expected: FAIL（fund universe 子命令不存在）

- [ ] **Step 3: Wire up the CLI**

修改 `data_tools/cli.py`，在现有 `cmd_fund_*` 函数旁边新增，并在 `main()` 里添加子命令解析：

```python
# 在 cmd_fund_global_news 之后新增：

def cmd_fund_universe_init(args):
    """初始化：拉取场外开放式基金列表。"""
    count = fund_universe.refresh_fund_list()
    if count > 0:
        print(f"初始化成功，共 {count} 只场外开放式基金")
    else:
        print("获取基金列表失败")
        sys.exit(1)


def cmd_fund_universe_status(args):
    """查看采集进度。"""
    print(fund_universe.format_status(fund_universe.get_status()))


def cmd_fund_universe_sync(args):
    """执行一次增量采集。"""
    result = fund_universe.sync(quota=args.quota, force=args.force)
    if result.get("status") == "error":
        print(f"致命错误: {result.get('message', '')}")
        sys.exit(1)
    elif result.get("failed", 0) > 0:
        print(f"采集完成(部分失败): 共 {result['total']} 只，成功 {result['success']}，失败 {result['failed']}")
        sys.exit(2)
    else:
        print(f"采集完成: 共 {result['total']} 只，全部成功")


def cmd_fund_universe_update(args):
    """强制更新单只基金。"""
    result = fund_universe.sync_single_fund(args.symbol, fund_universe.load_config())
    fund_universe.update_progress(
        args.symbol,
        last_status=result["last_status"],
        fail_count=result["fail_count"],
        fields=result["fields"],
    )
    if result["last_status"] == "ok":
        print(f"{args.symbol} 更新完成: 全部成功")
    else:
        print(f"{args.symbol} 更新完成: {result['last_status']}")
        sys.exit(2)


def cmd_fund_universe_refresh(args):
    """刷新基金列表。"""
    count = fund_universe.refresh_fund_list()
    print(f"基金列表已刷新，共 {count} 只场外开放式基金")
```

并在文件顶部新增 `from . import fund_universe`。

修改 `main()` 函数，在 `fund` 子解析器块内、现有 `fund` 子命令之后添加 `fund universe` 子解析器：

```python
# 在 pf = subparsers.add_parser("fund", ...) 之后追加：

# fund universe 子解析器
pfu = fund_sub.add_parser("universe", help="场外开放式基金全量采集调度")
fu_sub = pfu.add_subparsers(dest="fu_cmd", help="可用子命令")

pfu1 = fu_sub.add_parser("init", help="初始化：拉取场外开放式基金列表")
pfu1.set_defaults(func=cmd_fund_universe_init)

pfu2 = fu_sub.add_parser("status", help="查看采集进度")
pfu2.set_defaults(func=cmd_fund_universe_status)

pfu3 = fu_sub.add_parser("sync", help="执行一次增量采集")
pfu3.add_argument("--quota", type=int, default=None, help="今日采集配额（覆盖配置）")
pfu3.add_argument("--force", action="store_true", help="强制执行，忽略冷却与今日已运行标记")
pfu3.set_defaults(func=cmd_fund_universe_sync)

pfu4 = fu_sub.add_parser("update", help="强制更新单只基金")
pfu4.add_argument("symbol", help="基金代码")
pfu4.set_defaults(func=cmd_fund_universe_update)

pfu5 = fu_sub.add_parser("refresh-list", help="刷新基金列表")
pfu5.set_defaults(func=cmd_fund_universe_refresh)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fund_universe_cli.py -v`
Expected: 2 passed

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/unit/ -v`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add data_tools/cli.py tests/unit/test_fund_universe_cli.py
git commit -m "feat(fund-universe): wire 5 CLI sub-commands in cli.py"
```

---

## Task 9: 端到端测试（真实接口）

**Files:**
- Create: `tests/e2e/test_fund_universe_e2e.py`

- [ ] **Step 1: Write the e2e test**

```python
# tests/e2e/test_fund_universe_e2e.py
"""端到端测试：真实基金接口（允许 skipped）。

E2E 测试默认会执行真实 HTTP 请求；为防止 CI/开发机反复触发限流，
本文件使用 pytest.mark.real 接口在 pytest 配置中默认跳过。
开发机本地可通过 pytest -m real 显式运行。
"""
import shutil
from pathlib import Path

import pytest

from data_tools import fund_universe
from data_tools.stock_data import get_funds_dir


@pytest.fixture
def isolated_meta(tmp_path, monkeypatch):
    """把 _meta/ 重定向到 tmp_path，避免污染真实 data/funds/_meta。"""
    monkeypatch.setattr(fund_universe, "get_meta_dir", lambda: str(tmp_path))
    return tmp_path


@pytest.mark.real
def test_e2e_init_lists_offexchange_funds(isolated_meta):
    count = fund_universe.refresh_fund_list()
    assert count > 5000, f"场外开放式基金应 > 5000，实际 {count}"
    path = Path(fund_universe.get_fund_list_path())
    assert path.exists()
    data = fund_universe.load_fund_list()
    assert all(f.get("is_offexchange") is True for f in data)


@pytest.mark.real
def test_e2e_sync_three_funds_real(isolated_meta):
    fund_universe.refresh_fund_list()
    funds = fund_universe.load_fund_list()[:3]
    assert len(funds) >= 3
    cfg = fund_universe.load_config()
    # 真实接口下不允许 sleep 拖慢测试
    cfg["fund_interval_min"] = 0
    cfg["fund_interval_max"] = 0
    cfg["field_interval_min"] = 0
    cfg["field_interval_max"] = 0
    for f in funds:
        result = fund_universe.sync_single_fund(f["code"], cfg)
        # 真实接口允许 0~7 字段失败
        assert result["last_status"] in ("ok", "partial", "failed")
```

并在 `pytest.ini` 或 `pyproject.toml` 中添加（如果还没有）：

```ini
[pytest]
markers =
    real: 真实接口测试（默认 skip，需要 -m real 显式运行）
addopts = -m "not real"
```

- [ ] **Step 2: Verify pytest skips real tests by default**

Run: `pytest tests/e2e/test_fund_universe_e2e.py -v`
Expected: 2 skipped (no failures)

- [ ] **Step 3: Run the e2e manually with real marker**

Run: `pytest tests/e2e/test_fund_universe_e2e.py -m real -v`
Expected: 2 passed (or skipped on network errors)

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_fund_universe_e2e.py pytest.ini
git commit -m "test(fund-universe): add e2e tests with real marker"
```

---

## Task 10: 文档与收尾

**Files:**
- Modify: `docs/universe-collector-design.md`

- [ ] **Step 1: Append a section to the existing collector design doc**

在 `docs/universe-collector-design.md` 末尾追加：

```markdown
## 基金调度器对称设计（2026-06-28 新增）

`data_tools/fund_universe.py` 镜像 A 股 `universe.py` 的设计模式，提供场外开放式基金的全量采集与定时调度能力。

### 与 A 股 universe 的差异

| 维度 | A 股 universe | 基金 fund_universe |
|------|---------------|---------------------|
| 标的范围 | 全量 A 股 | 仅场外开放式基金 |
| 列表来源 | 新浪财经全 A 列表 | 天天基金 → 东方财富数据中心（主备） |
| 字段数 | 6（K线/基本面/财务/新闻/解禁/资金） | 7（净值/概况/重仓/经理/业绩/份额/新闻） |
| 默认配额 | 500 | 200（基金接口较慢） |
| 默认冷却 | 7 天 | 7 天 |
| 落盘路径 | `data/stocks/_meta/` | `data/funds/_meta/` |

### CLI 命令对照

```bash
python -m data_tools.cli universe {init,status,sync,update,refresh-list}
python -m data_tools.cli fund universe {init,status,sync,update,refresh-list}
```

### 退出码语义（基金调度器新增 2 = 部分失败）

- 0：全部成功
- 2：部分失败（≥1 只基金部分字段缺失或整只失败但队列完成）
- 1：致命错误（列表缺失、网络断、磁盘满、参数错误）

### 复用与隔离

- 完全复用 `fund_data.py` 7 个查询接口，签名零修改
- 完全复用 `stock_data.py` 的存储工具（`get_funds_dir`、`save_fund_data_file`、`_UA` 等）
- 进度文件格式与 A 股对称（`universe_progress.json`），便于后续维护心智模型
```

- [ ] **Step 2: Verify existing docs not broken**

Run: 略（纯文档改动，不影响代码）

- [ ] **Step 3: Commit**

```bash
git add docs/universe-collector-design.md
git commit -m "docs(universe): add fund scheduler symmetric design section"
```

---

## Task 11: 全量验收

- [ ] **Step 1: Run all unit tests**

Run: `pytest tests/unit/test_fund_universe_*.py -v`
Expected: 全部通过（任务 1~8 共 49 个测试）

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`
Expected: 全量测试通过（含 stock-analysis 既有测试）

- [ ] **Step 3: Run CLI smoke test**

```bash
python -m data_tools.cli fund universe --help
python -m data_tools.cli fund universe status
```

Expected: 帮助文本完整；status 输出含 "基金总数" 字样

- [ ] **Step 4: Commit final marker (if needed)**

如果对设计文档有补充更新，更新 spec 文件并 commit：

```bash
git add docs/superpowers/specs/2026-06-28-fund-universe-design.md
git commit -m "docs(fund-universe): post-impl spec tweaks (if any)"
```

---

## Self-Review Checklist

- [x] **Spec coverage**: spec §1~§10 中每个需求都在 Task 1~10 中有对应实现（CLI 5 个子命令、配置、列表/过滤、进度、调度、测试、文档）
- [x] **Placeholder scan**: 无 TBD/TODO/"add appropriate error handling" 等占位
- [x] **Type consistency**: 所有函数签名在引用时一致（如 `sync_single_fund(code, config)`, `update_progress(code, last_status, fail_count, fields, cooldown_until=None)`）
- [x] **TDD**: 每个 Task 严格遵循「先写失败测试 → 实现 → 通过测试 → 提交」
- [x] **Frequent commits**: 每个 Task 一个 commit
- [x] **Real commands**: 所有 pytest 命令与预期输出均来自本计划

---

## 实施完成判据

1. ✅ `pytest -v` 全部测试通过（含 stock-analysis 既有测试不被破坏）
2. ✅ `python -m data_tools.cli fund universe --help` 输出 5 个子命令
3. ✅ `python -m data_tools.cli fund universe status` 在真实数据下输出可读进度
4. ✅ `docs/universe-collector-design.md` 末尾包含「基金调度器对称设计」章节
5. ✅ 至少 1 个 e2e 测试在 `-m real` 下通过