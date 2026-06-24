"""A股数据获取工具包.

基于 TradingAgents-astock 的数据获取范式，提供多源 A 股数据获取能力。

数据源:
- mootdx (TCP): K线、财务快照
- 腾讯财经 (HTTP): 实时报价、PE/PB/市值
- 东方财富 (HTTP): 龙虎榜、解禁、资讯
- 新浪财经 (HTTP): K线备用、财报
- 同花顺 (HTTP): 一致预期、热门股、北向资金
- 财联社 (HTTP): 全球快讯
- 百度股市通 (HTTP): 概念板块

数据存储:
- 每次分析的数据存放在项目 data/ 目录下
- 按股票代码 + 日期组织子目录
"""

from .stock_data import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_income_statement,
    get_balance_sheet,
    get_cashflow,
    get_news,
    get_global_news,
    get_dragon_tiger,
    get_lockup,
    get_northbound_flow,
    get_hot_stocks,
    get_concept_blocks,
    get_insider_transactions,
    get_profit_forecast,
)

__all__ = [
    "get_stock_data",
    "get_indicators",
    "get_fundamentals",
    "get_income_statement",
    "get_balance_sheet",
    "get_cashflow",
    "get_news",
    "get_global_news",
    "get_dragon_tiger",
    "get_lockup",
    "get_northbound_flow",
    "get_hot_stocks",
    "get_concept_blocks",
    "get_insider_transactions",
    "get_profit_forecast",
]
