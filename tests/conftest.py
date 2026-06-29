"""pytest 全局 fixture:mock subagent 调度。"""
import pytest
from pathlib import Path


@pytest.fixture
def today() -> str:
    return "2026-06-27"


@pytest.fixture
def reports_dir(tmp_path, today):
    d = tmp_path / "reports" / today
    d.mkdir(parents=True)
    return d


@pytest.fixture
def mock_subagent():
    """模拟 subagent 调度,返回固定 mock 结果。"""
    class MockRunner:
        def __init__(self):
            self.calls = []

        def run(self, prompt: str) -> dict | str:
            self.calls.append(prompt)
            return {"status": "ok", "summary": "mock result"}

        def run_parallel(self, prompts: list) -> list:
            return [self.run(p) for p in prompts]

    return MockRunner()


@pytest.fixture
def workflow_runner(tmp_path, today, mock_subagent):
    """集成测试用 workflow runner:detect → 7 analysts → decision → html。"""
    class WorkflowRunner:
        def __init__(self):
            self.context = {}
            self.mock = mock_subagent

        def run_step_0_input_router(self, user_text: str, holdings=None):
            from data_tools.detect import detect_input
            r = detect_input(user_text, holdings=holdings)
            return r.to_dict()

        def run_step_1_analysts(self, type_, codes: list[str]):
            """并行跑 N 个标的的 M 个角色 subagent。"""
            if type_ == "A":
                roles = ["market", "sentiment", "news", "fundamentals", "policy", "hot_money", "lockup"]
            elif type_ in ("B", "C-1"):
                roles = ["fund_market", "fund_fundamentals", "holdings", "flows", "fund_news", "fund_policy", "fund_sentiment"]
            else:
                roles = []
            return self.mock.run_parallel([f"{r}:{c}" for c in codes for r in roles])

        def run_step_2_quality_audit(self):
            return self.mock.run("audit")

        def run_step_3_bull_bear(self):
            return self.mock.run_parallel(["bull", "bear"])

        def run_step_4_research_manager(self):
            return self.mock.run("research")

        def run_step_5_trader(self):
            return self.mock.run("trade")

        def run_step_6_risk(self):
            return self.mock.run_parallel(["aggressive", "conservative", "neutral"])

        def run_step_7_portfolio_manager(self, scenario="single"):
            summary = "mock portfolio manager report\n\n## 结论\nBuy\n\n## 免责声明\n本报告..."
            return summary

        def run_step_8_html_renderer(self, content: str, template: str):
            from data_tools.template_renderer import render
            meta = {"code": "MOCK", "name": "Mock Report", "date": "2026-06-27", "report_type": template}
            html = render(template=template, meta=meta, sections=[{"title": "t", "content": "c"}], stock_items=[], risk_views=[], fund_meta={}, trade={}, portfolio={}, overlaps=[], balance={}, portfolio_subtype="c1", target_allocation=[])
            path = tmp_path / "reports" / "2026-06-27" / f"mock_{template}.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
            return path

    return WorkflowRunner()
