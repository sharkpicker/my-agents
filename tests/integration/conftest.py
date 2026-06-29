"""集成测试的 conftest:复用 unit 目录的 fixture 与共享数据。"""
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

# 让 integration 测试可以 from test_quality_score_fixtures import ...
sys.path.insert(0, str(Path(__file__).parent.parent / "unit"))


@pytest.fixture
def write_fake_reports(tmp_path: Path) -> Callable[[str, dict[str, str]], Path]:
    """复用 tests/unit/conftest.py 的 write_fake_reports 行为。

    把 PERFECT_FUND_REPORTS / TERRIBLE_FUND_REPORTS 风格的 7 报告写到
    tmp_path / <code> 目录,返回该目录路径。
    """
    def _write(code: str, reports: dict[str, str]) -> Path:
        d = tmp_path / code
        d.mkdir(parents=True, exist_ok=True)
        for role, content in reports.items():
            (d / f"{code}_{role}.md").write_text(content, encoding="utf-8")
        return d
    return _write
