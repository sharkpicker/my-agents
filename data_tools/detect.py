"""输入类型识别:把用户输入归类为 A/B/C-1/C-2/C-3 之一。"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import re


class InputType(str, Enum):
    STOCK = "A"
    FUND = "B"
    STOCK_PORTFOLIO = "C-2"
    FUND_PORTFOLIO = "C-1"
    MIXED_PORTFOLIO = "C-3"
    UNKNOWN = "?"


@dataclass
class Position:
    code: str
    name: str
    type: str
    amount: float
    ratio: float = 0.0
    holding_return: float = 0.0
    holding_return_pct: float = 0.0


@dataclass
class DetectResult:
    type: InputType
    code: str = ""
    name: str = ""
    positions: list = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "code": self.code,
            "name": self.name,
            "positions": [p.__dict__ if hasattr(p, "__dict__") else p for p in self.positions],
            "confidence": self.confidence,
        }


_CODE_6DIGIT = re.compile(r"\b(\d{6})\b")
_FUND_KEYWORDS = ["基金", "混合", "联接", "ETF", "中证", "债", "宝", "医疗", "教育"]
_PORTFOLIO_KEYWORDS = ["持仓", "组合", "我的", "诊断", "全部"]

_OFFSHORE_FUND_PREFIXES = (
    "001", "002", "003", "004", "005", "006", "007", "008", "009",
    "010", "011", "012", "013", "014", "015", "016", "017", "018", "019", "020",
)
_OFFSHORE_FUND_PREFIXES_2 = ("15", "16", "17", "18")


def _is_fund_code(code: str) -> bool:
    """通过代码段判断是否为基金代码。

    场内基金: 5xxxxx(沪)、1xxxxx(深)。
    场外基金: 001-020 段及 15/16/17/18 段。
    """
    if code.startswith(("5", "1")):
        return True
    if code[:3] in _OFFSHORE_FUND_PREFIXES:
        return True
    if code[:2] in _OFFSHORE_FUND_PREFIXES_2:
        return True
    return False


def detect_input(text: str, holdings: list | None = None) -> DetectResult:
    """识别用户输入,返回类型 + 标的代码 / 名称 / 持仓列表。"""
    text = text.strip()

    if holdings:
        return _detect_portfolio(holdings)

    m = _CODE_6DIGIT.search(text)
    if m:
        code = m.group(1)
        if _is_fund_code(code):
            return DetectResult(InputType.FUND, code=code)
        if code.startswith("0") and any(kw in text for kw in _FUND_KEYWORDS):
            return DetectResult(InputType.FUND, code=code)
        return DetectResult(InputType.STOCK, code=code, name=_lookup_stock_name(code))

    if any(kw in text for kw in _FUND_KEYWORDS):
        return DetectResult(InputType.FUND, name=text)

    if any(kw in text for kw in _PORTFOLIO_KEYWORDS):
        return DetectResult(InputType.UNKNOWN, confidence=0.5)

    return DetectResult(InputType.UNKNOWN, confidence=0.3)


def _detect_portfolio(holdings: list) -> DetectResult:
    types = {h.get("type") for h in holdings}
    positions = [Position(**h) if isinstance(h, dict) else h for h in holdings]

    if types == {"fund"}:
        input_type = InputType.FUND_PORTFOLIO
    elif types == {"stock"}:
        input_type = InputType.STOCK_PORTFOLIO
    elif "fund" in types and "stock" in types:
        input_type = InputType.MIXED_PORTFOLIO
    else:
        input_type = InputType.UNKNOWN

    return DetectResult(type=input_type, positions=positions)


def _lookup_stock_name(code: str) -> str:
    return ""