# tests/unit/test_quality_score_cli.py
"""CLI `quality-score` 子命令单元测试。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from data_tools.portfolio_rebalance import parse_quality_from_reports
from test_quality_score_fixtures import PERFECT_FUND_REPORTS


PROJECT_ROOT = Path(__file__).parent.parent.parent


def _run(args: list[str]) -> subprocess.CompletedProcess:
    """Run `python -m data_tools.cli quality-score ...` and capture output."""
    return subprocess.run(
        [sys.executable, "-m", "data_tools.cli", "quality-score", *args],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )


def test_quality_score_help():
    """`quality-score --help` 应包含所有 4 个必要参数。"""
    result = _run(["--help"])
    assert result.returncode == 0
    assert "--code" in result.stdout
    assert "--reports-dir" in result.stdout
    assert "--category" in result.stdout
    assert "--date" in result.stdout


def test_quality_score_missing_code(tmp_path):
    """--code 缺失应返回非 0。"""
    result = _run([
        "--reports-dir", str(tmp_path),
        "--category", "bond",
        "--date", "2026-06-29",
    ])
    assert result.returncode != 0


def test_quality_score_runs_and_outputs_json(write_fake_reports):
    """给一份完整 PERFECT 报告,CLI 应输出 JSON 且 quality_score >= 60。"""
    d = write_fake_reports("007466", PERFECT_FUND_REPORTS)
    result = _run([
        "--code", "007466",
        "--reports-dir", str(d.parent),
        "--category", "bond",
        "--date", "2026-06-29",
    ])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads(result.stdout)
    assert data["code"] == "007466"
    assert data["category"] == "bond"
    assert data["quality_score"] >= 60
    assert data["missing_dimensions"] == []
