from data_tools.detect import detect_input, InputType

def test_detect_stock_code_6_digits():
    r = detect_input("000001")
    assert r.type == InputType.STOCK
    assert r.code == "000001"

def test_detect_stock_code_with_prefix():
    r = detect_input("分析平安银行 000001")
    assert r.type == InputType.STOCK
    assert r.code == "000001"

def test_detect_fund_code_6_digits():
    r = detect_input("001717")
    assert r.type == InputType.FUND
    assert r.code == "001717"

def test_detect_fund_name_chinese():
    r = detect_input("工银前沿医疗")
    assert r.type == InputType.FUND
    assert "工银" in r.name

def test_detect_stock_portfolio_keyword():
    holdings = [
        {"code": "000001", "name": "平安银行", "type": "stock", "amount": 1000},
    ]
    r = detect_input("分析我的持仓", holdings=holdings)
    assert r.type == InputType.STOCK_PORTFOLIO
    assert len(r.positions) == 1

def test_detect_fund_portfolio_keyword():
    holdings = [
        {"code": "001717", "name": "工银前沿医疗", "type": "fund", "amount": 1000},
    ]
    r = detect_input("诊断组合", holdings=holdings)
    assert r.type == InputType.FUND_PORTFOLIO

def test_detect_mixed_portfolio():
    holdings = [
        {"code": "000001", "name": "平安银行", "type": "stock", "amount": 1000},
        {"code": "001717", "name": "工银前沿医疗", "type": "fund", "amount": 1000},
    ]
    r = detect_input("分析我的持仓", holdings=holdings)
    assert r.type == InputType.MIXED_PORTFOLIO

def test_detect_ambiguous_no_holdings():
    r = detect_input("分析")
    assert r.type == InputType.UNKNOWN