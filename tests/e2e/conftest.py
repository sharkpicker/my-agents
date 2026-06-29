"""E2E 测试 fixture:更接近真实场景的 runner。"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock


@pytest.fixture
def today():
    return "2026-06-27"


@pytest.fixture
def e2e_runner(tmp_path, today):
    """E2E 测试 runner:用 unittest.mock 模拟所有 subagent。"""
    class E2ERunner:
        def __init__(self):
            self.reports_dir = tmp_path / "reports" / today
            self.reports_dir.mkdir(parents=True, exist_ok=True)
            self.calls = []

        def run(self, prompt_or_name: str) -> dict:
            """模拟单 subagent 调用,基于 prompt name 返回结构化结果。"""
            self.calls.append(prompt_or_name)
            name = prompt_or_name if isinstance(prompt_or_name, str) else str(prompt_or_name)

            # 路由
            if "input_router" in name or "router" in name.lower():
                if "001717" in name and "amount" not in name:
                    return {"type": "B", "code": "001717", "name": "工银瑞信前沿医疗股票A"}
                return {"type": "A", "code": "000001", "name": "平安银行"}

            # 单标分析师
            if any(r in name for r in ["market", "sentiment", "news", "fundamentals", "policy", "hot_money", "lockup"]):
                return {"status": "ok", "summary": "mock analysis", "detail_path": f"reports/2026-06-27/stock/000001_{name.split(':')[-1] if ':' in name else 'mock'}.md"}

            # 决策流程
            if "bull" in name.lower():
                return {"summary": "看多", "rating": "Buy"}
            if "bear" in name.lower():
                return {"summary": "看空", "rating": "Sell"}
            if "portfolio_manager" in name.lower():
                return "mock report\n## 结论\nBuy\n## 免责声明\n免责"
            return {"status": "ok", "summary": "mock"}

        def run_parallel(self, prompts: list) -> list:
            return [self.run(p) for p in prompts]

        def render_html(self, content: str, template: str, meta: dict, **extra) -> Path:
            from data_tools.template_renderer import render
            defaults = {
                "sections": [{"title": "t", "content": content}],
                "stock_items": [],
                "risk_views": [],
                "fund_meta": {},
                "trade": {},
                "portfolio": {},
                "overlaps": [],
                "balance": {},
                "portfolio_subtype": "c1",
                "target_allocation": [],
            }
            defaults.update(extra)
            html = render(template=template, meta=meta, **defaults)
            fname = f"{meta['code']}_{meta['name']}.html" if template in ("stock", "fund") else f"portfolio_{template}_{today}.html"
            path = self.reports_dir / fname
            path.write_text(html, encoding="utf-8")
            return path

    return E2ERunner()