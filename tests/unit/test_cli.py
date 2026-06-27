from click.testing import CliRunner
from data_tools.cli import cli

runner = CliRunner()


def test_cli_detect_stock_code():
    result = runner.invoke(cli, ["detect", "000001"])
    assert result.exit_code == 0, result.output
    assert '"type": "A"' in result.output


def test_cli_portfolio_concentration():
    result = runner.invoke(cli, [
        "portfolio", "concentration",
        "--positions", "001:1000,002:1000,003:1000",
    ])
    assert result.exit_code == 0, result.output
    hhi = float(result.output.strip().split("=")[1])
    assert 0.30 < hhi < 0.35, f"HHI={hhi} 不在 1/3 附近"


def test_cli_portfolio_overlap():
    result = runner.invoke(cli, [
        "portfolio", "overlap",
        "--fund-holdings", "001717:600276",
        "--direct-stocks", "600276:3000",
    ])
    assert result.exit_code == 0, result.output
    assert "001717" in result.output
    assert "600276" in result.output


def test_cli_portfolio_balance():
    result = runner.invoke(cli, [
        "portfolio", "balance",
        "--holdings",
        "001717:5000:fund:0.95,014767:2500:fund:0.20,600519:4000:stock:1.0",
    ])
    assert result.exit_code == 0, result.output
    assert "equity_ratio" in result.output
