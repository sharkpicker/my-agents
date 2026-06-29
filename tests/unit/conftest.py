"""unit 测试专用 fixture。"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def write_fake_reports(tmp_path: Path) -> Callable[[str, dict[str, str]], Path]:
    """返回函数: write_fake_reports(code, reports) -> reports_dir"""
    def _write(code: str, reports: dict[str, str]) -> Path:
        d = tmp_path / code
        d.mkdir(parents=True, exist_ok=True)
        for role, content in reports.items():
            (d / f"{code}_{role}.md").write_text(content, encoding="utf-8")
        # 写一个空辩论文件
        (d / f"{code}_category_bull.md").write_text(
            f"# 多头观点\n\ntop1_pick: {code}\n", encoding="utf-8"
        )
        (d / f"{code}_category_bear.md").write_text(
            f"# 空头观点\n\ntop1_pick: {code}\n", encoding="utf-8"
        )
        return d
    return _write
