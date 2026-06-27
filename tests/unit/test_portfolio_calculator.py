from data_tools.portfolio import (
    calculate_concentration,
    detect_overlap,
    calculate_balance,
)


def test_calculate_concentration_hhi_low():
    """分散持仓 HHI < 0.30 (4 个等额持仓 HHI=0.25,数学上 < 0.30 视为分散)"""
    positions = [
        {"code": "001", "amount": 1000},
        {"code": "002", "amount": 1000},
        {"code": "003", "amount": 1000},
        {"code": "004", "amount": 1000},
    ]
    hhi = calculate_concentration(positions)
    assert hhi < 0.30


def test_calculate_concentration_hhi_high():
    """集中持仓 HHI > 0.25"""
    positions = [
        {"code": "001", "amount": 8000},
        {"code": "002", "amount": 1000},
        {"code": "003", "amount": 500},
        {"code": "004", "amount": 500},
    ]
    hhi = calculate_concentration(positions)
    assert hhi > 0.25


def test_detect_overlap_fund_stock():
    """001717 持有 600276,用户直接持有 600276 → 重复"""
    fund_holdings = {
        "001717": {"top10": [{"code": "600276", "ratio": 0.0941}]},
    }
    direct_stocks = [{"code": "600276", "amount": 3000}]
    overlaps = detect_overlap(fund_holdings, direct_stocks)
    assert len(overlaps) == 1
    assert overlaps[0]["fund"] == "001717"
    assert overlaps[0]["stock"] == "600276"


def test_calculate_balance_equity_exposure():
    """计算穿透后权益占比"""
    holdings = [
        {"code": "001717", "type": "fund", "amount": 5000, "stock_penetration": 0.95},
        {"code": "014767", "type": "fund", "amount": 2500, "stock_penetration": 0.20},
        {"code": "600519", "type": "stock", "amount": 4000},
    ]
    equity = calculate_balance(holdings)
    # 5000*0.95 + 2500*0.20 + 4000 = 4750 + 500 + 4000 = 9250
    # total = 11500
    # 9250 / 11500 = 0.8043
    assert abs(equity["equity_ratio"] - 9250 / 11500) < 0.001
    assert abs(equity["bond_ratio"] - (11500 - 9250) / 11500) < 0.001
