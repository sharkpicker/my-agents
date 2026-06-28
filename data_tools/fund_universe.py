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
