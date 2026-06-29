from pathlib import Path

CONTRACT_PATH = Path(".trae/skills/stock-analysis/subagent-contract.md")

def test_contract_file_exists():
    assert CONTRACT_PATH.exists(), "subagent-contract.md 必须存在"

def test_contract_defines_summary_field():
    content = CONTRACT_PATH.read_text()
    assert "summary" in content, "契约必须定义 summary 字段"

def test_contract_defines_detail_path_field():
    content = CONTRACT_PATH.read_text()
    assert "detail_path" in content, "契约必须定义 detail_path 字段"

def test_contract_defines_evidence_field():
    content = CONTRACT_PATH.read_text()
    assert "evidence" in content, "契约必须定义 evidence 字段"

def test_contract_summary_limit_2k_tokens():
    content = CONTRACT_PATH.read_text()
    assert "2k" in content or "2000" in content, "契约必须声明 summary 上限 2k tokens"