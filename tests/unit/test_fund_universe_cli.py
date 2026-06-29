import subprocess
import sys
from click.testing import CliRunner
from data_tools.cli import cli


def test_cli_help_shows_fund_universe_subcommand():
    runner = CliRunner()
    result = runner.invoke(cli, ["fund", "universe", "--help"])
    assert result.exit_code == 0
    out = result.output
    for cmd in ["init", "status", "sync", "update", "refresh-list"]:
        assert cmd in out


def test_cli_fund_universe_status_runs(monkeypatch, tmp_path):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli, ["fund", "universe", "status"])
    assert result.exit_code == 0
    assert "Fund Universe" in result.output or "基金" in result.output


def test_cli_fund_universe_init_invokes_refresh(monkeypatch):
    called = {"n": 0}
    def fake_refresh():
        called["n"] += 1
        return 100
    monkeypatch.setattr("data_tools.fund_universe.refresh_fund_list", fake_refresh)
    runner = CliRunner()
    result = runner.invoke(cli, ["fund", "universe", "init"])
    assert result.exit_code == 0
    assert called["n"] == 1


def test_cli_fund_universe_sync_invokes_sync(monkeypatch):
    called = {"args": None}
    def fake_sync(quota=None, force=False):
        called["args"] = (quota, force)
        return {"status": "ok", "total": 0, "success": 0, "failed": 0}
    monkeypatch.setattr("data_tools.fund_universe.sync", fake_sync)
    runner = CliRunner()
    result = runner.invoke(cli, ["fund", "universe", "sync", "--quota", "5", "--force"])
    assert result.exit_code == 0
    assert called["args"] == (5, True)


def test_cli_fund_universe_sync_partial_returns_exit_2(monkeypatch):
    def fake_sync(quota=None, force=False):
        return {"status": "partial", "total": 3, "success": 2, "failed": 1}
    monkeypatch.setattr("data_tools.fund_universe.sync", fake_sync)
    runner = CliRunner()
    result = runner.invoke(cli, ["fund", "universe", "sync"])
    assert result.exit_code == 2
    assert "部分失败" in result.output


def test_cli_fund_universe_sync_error_returns_exit_1(monkeypatch):
    def fake_sync(quota=None, force=False):
        return {"status": "error", "message": "列表缺失", "total": 0, "success": 0, "failed": 0}
    monkeypatch.setattr("data_tools.fund_universe.sync", fake_sync)
    runner = CliRunner()
    result = runner.invoke(cli, ["fund", "universe", "sync"])
    assert result.exit_code == 1
    assert "列表缺失" in result.output


def test_cli_fund_universe_update_runs_for_code(monkeypatch):
    called = {"code": None}
    def fake_sync_single(code, config, existing_fields=None, force=False):
        called["code"] = code
        return {"last_status": "ok", "fail_count": 0, "fields": {}, "cooldown_until": None}
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund", fake_sync_single)
    monkeypatch.setattr("data_tools.fund_universe.update_progress", lambda *a, **kw: None)
    runner = CliRunner()
    result = runner.invoke(cli, ["fund", "universe", "update", "000001"])
    assert result.exit_code == 0
    assert called["code"] == "000001"


def test_cli_fund_universe_update_partial_returns_exit_2(monkeypatch):
    def fake_sync_single(code, config, existing_fields=None, force=False):
        return {"last_status": "partial", "fail_count": 1,
                "fields": {"nav": "ok", "info": "failed"}, "cooldown_until": None}
    monkeypatch.setattr("data_tools.fund_universe.sync_single_fund", fake_sync_single)
    monkeypatch.setattr("data_tools.fund_universe.update_progress", lambda *a, **kw: None)
    runner = CliRunner()
    result = runner.invoke(cli, ["fund", "universe", "update", "000001"])
    assert result.exit_code == 2
    assert "partial" in result.output


def test_cli_fund_universe_refresh_list_invokes_refresh(monkeypatch):
    called = {"n": 0}
    def fake_refresh():
        called["n"] += 1
        return 200
    monkeypatch.setattr("data_tools.fund_universe.refresh_fund_list", fake_refresh)
    runner = CliRunner()
    result = runner.invoke(cli, ["fund", "universe", "refresh-list"])
    assert result.exit_code == 0
    assert called["n"] == 1


def test_cli_help_via_subprocess():
    """真实 CLI 入口的 --help 输出包含 fund universe 子命令。"""
    res = subprocess.run(
        [sys.executable, "-m", "data_tools.cli", "fund", "universe", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode == 0
    for cmd in ["init", "status", "sync", "update", "refresh-list"]:
        assert cmd in res.stdout
