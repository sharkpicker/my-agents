"""A股核心数据获取模块.

基于 TradingAgents-astock 的 a_stock.py 实现，提供多源 A 股数据获取能力。
数据自动缓存到项目 data/ 目录下，按股票代码 + 日期组织。
"""

from __future__ import annotations

import os
import re
import json
import time
import random
import socket
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# 数据存储目录
# ---------------------------------------------------------------------------
# 设计: 股票与基金均为 6 位代码,可能存在代码空间重叠,故物理上分目录存储。
#   - A 股股票 -> data/stocks/<code>/
#   - 公募基金 -> data/funds/<code>/
#   - 全局元数据(股票列表/采集进度) -> data/stocks/_meta/
# 这种隔离避免了代码冲突导致的数据互相覆盖。

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
STOCKS_DIR = os.path.join(DATA_DIR, "stocks")
FUNDS_DIR = os.path.join(DATA_DIR, "funds")
META_DIR = os.path.join(STOCKS_DIR, "_meta")

for _d in (DATA_DIR, STOCKS_DIR, FUNDS_DIR, META_DIR):
    os.makedirs(_d, exist_ok=True)


def get_data_dir() -> str:
    """返回数据存储根目录 (data/)."""
    return DATA_DIR


def get_stocks_dir() -> str:
    """返回股票数据根目录 (data/stocks/)."""
    return STOCKS_DIR


def get_funds_dir() -> str:
    """返回基金数据根目录 (data/funds/)."""
    return FUNDS_DIR


def get_meta_dir() -> str:
    """返回股票全局元数据目录 (data/stocks/_meta/)."""
    return META_DIR


def get_stock_data_dir(symbol: str) -> str:
    """获取某只股票的数据目录路径."""
    code = _normalize_ticker(symbol)
    stock_dir = os.path.join(STOCKS_DIR, code)
    os.makedirs(stock_dir, exist_ok=True)
    return stock_dir


def get_fund_data_dir(symbol: str) -> str:
    """获取某只基金的数据目录路径."""
    code = _normalize_ticker(symbol)
    fund_dir = os.path.join(FUNDS_DIR, code)
    os.makedirs(fund_dir, exist_ok=True)
    return fund_dir


def save_data_file(symbol: str, filename: str, content: str) -> str:
    """保存数据文件到股票数据目录，返回文件路径."""
    stock_dir = get_stock_data_dir(symbol)
    filepath = os.path.join(stock_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


def save_fund_data_file(symbol: str, filename: str, content: str) -> str:
    """保存数据文件到基金数据目录，返回文件路径."""
    fund_dir = get_fund_data_dir(symbol)
    filepath = os.path.join(fund_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


# ---------------------------------------------------------------------------
# 股票代码格式化
# ---------------------------------------------------------------------------

def _get_prefix(code: str) -> str:
    """6位股票代码 -> 市场前缀 (sh/sz/bj)."""
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    return "sz"


def _normalize_ticker(symbol: str) -> str:
    """规范化股票代码为纯6位数字."""
    s = symbol.strip().upper()
    for suffix in (".SH", ".SZ", ".BJ"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    for prefix in ("SH", "SZ", "BJ"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    return s


# ---------------------------------------------------------------------------
# mootdx 客户端 (单例)
# ---------------------------------------------------------------------------

_mootdx_client = None

_TDX_SERVERS = [
    ("119.97.185.59", 7709), ("124.70.133.119", 7709), ("116.205.183.150", 7709),
    ("123.60.73.44", 7709), ("116.205.163.254", 7709), ("121.36.225.169", 7709),
    ("123.60.70.228", 7709), ("124.71.9.153", 7709), ("110.41.147.114", 7709),
    ("124.71.187.122", 7709),
]


def _probe_tdx(ip: str, port: int, timeout: float = 2.0) -> bool:
    """TCP探测通达信服务器是否可达."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _get_mootdx_client():
    """获取mootdx客户端 (懒加载, 带容错)."""
    global _mootdx_client
    if _mootdx_client is not None:
        return _mootdx_client

    from mootdx.quotes import Quotes

    for ip, port in _TDX_SERVERS:
        if _probe_tdx(ip, port):
            _mootdx_client = Quotes.factory(market="std", server=(ip, port))
            return _mootdx_client
    try:
        _mootdx_client = Quotes.factory(market="std", bestip=True)
        return _mootdx_client
    except Exception:
        pass
    try:
        _mootdx_client = Quotes.factory(market="std")
        return _mootdx_client
    except Exception as e:
        raise RuntimeError(f"通达信服务器不可达: {e}") from e


# ---------------------------------------------------------------------------
# 腾讯财经实时报价
# ---------------------------------------------------------------------------

def _tencent_quote(codes: list[str]) -> dict[str, dict]:
    """从腾讯财经获取批量实时报价."""
    prefixed = [f"{_get_prefix(c)}{c}" for c in codes]
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode("gbk")

    result = {}
    for line in raw.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key[2:]
        result[code] = {
            "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "mcap_yi": float(vals[44]) if vals[44] else 0,
            "float_mcap_yi": float(vals[45]) if vals[45] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "limit_up": float(vals[47]) if vals[47] else 0,
            "limit_down": float(vals[48]) if vals[48] else 0,
            "pe_static": float(vals[52]) if vals[52] else 0,
        }
    return result


# ---------------------------------------------------------------------------
# 东方财富 HTTP 请求 (带节流防封)
# ---------------------------------------------------------------------------

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_EM_SESSION = requests.Session()
_EM_SESSION.headers.update({"User-Agent": _UA})
_EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]


def _http_get(url, params=None, headers=None, timeout=15, **kwargs):
    """通用HTTP GET请求封装."""
    return requests.get(url, params=params, headers=headers, timeout=timeout, **kwargs)


def _em_get(url, params=None, headers=None, timeout=15, **kwargs):
    """东方财富统一请求入口: 自动节流 + 会话复用."""
    wait = _EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return _EM_SESSION.get(
            url, params=params, headers=headers, timeout=timeout, **kwargs
        )
    finally:
        _em_last_call[0] = time.time()


# ---------------------------------------------------------------------------
# 新浪K线备用源
# ---------------------------------------------------------------------------

def _sina_kline_fallback(code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """从新浪财经获取日线K线 (mootdx备用)."""
    prefix = "sh" if code.startswith("6") else "sz"
    url = (
        "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "CN_MarketData.getKLineData"
    )
    params = {
        "symbol": f"{prefix}{code}",
        "scale": "240",
        "ma": "no",
        "datalen": "800",
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = json.loads(r.text)

    if not data:
        return pd.DataFrame()

    rows = []
    for item in data:
        rows.append({
            "Date": item["day"],
            "Open": float(item["open"]),
            "High": float(item["high"]),
            "Low": float(item["low"]),
            "Close": float(item["close"]),
            "Volume": int(item["volume"]),
        })

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])

    if start_date:
        df = df[df["Date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["Date"] <= pd.to_datetime(end_date)]

    return df


# ---------------------------------------------------------------------------
# OHLCV 辅助函数
# ---------------------------------------------------------------------------

def _normalize_ohlcv_dates(df: pd.DataFrame) -> pd.DataFrame:
    """规范化OHLCV日期."""
    if df is None or df.empty or "Date" not in df.columns:
        return df
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
    return df.dropna(subset=["Date"])

def _merge_ohlcv(primary: pd.DataFrame, supplement: pd.DataFrame) -> pd.DataFrame:
    """合并两个OHLCV DataFrame."""
    frames = [f for f in (primary, supplement) if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    combined = pd.concat(frames, ignore_index=True)
    combined = _normalize_ohlcv_dates(combined)
    combined = combined.drop_duplicates(subset=["Date"], keep="last")
    combined = combined.sort_values("Date").reset_index(drop=True)
    return combined


# ===========================================================================
# 1. get_stock_data - 获取K线数据
# ===========================================================================

def get_stock_data(
    symbol: str,
    start_date: str,
    end_date: str,
    save: bool = True,
) -> str:
    """获取股票OHLCV K线数据.

    Args:
        symbol: 6位A股代码
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        save: 是否保存到data目录

    Returns:
        格式化的K线数据文本
    """
    code = _normalize_ticker(symbol)
    data_source = "mootdx (TCP)"

    try:
        client = _get_mootdx_client()
        df = client.bars(symbol=code, category=4, offset=800)

        if df is None or df.empty:
            raise ValueError(f"No data from mootdx for {code}")

        df = df.drop(
            columns=["datetime", "year", "month", "day", "hour", "minute"],
            errors="ignore",
        )
        df = df.reset_index()
        df = df.rename(
            columns={
                "datetime": "Date",
                "open": "Open",
                "close": "Close",
                "high": "High",
                "low": "Low",
                "volume": "Volume",
                "amount": "Amount",
            }
        )
        df = _normalize_ohlcv_dates(df)

    except Exception as e:
        print(f"mootdx K线失败 {code}: {e}, 使用新浪备用源")
        try:
            df = _sina_kline_fallback(code, start_date, end_date)
            if df.empty:
                return f"K线数据获取失败: {code}"
            data_source = "sina HTTP (fallback)"
        except Exception:
            return f"K线数据获取失败: {code} (所有源均不可用)"

    # 日期过滤
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    df = df[(df["Date"] >= start_dt) & (df["Date"] <= end_dt)]

    if df.empty:
        return f"未找到 {code} 在 {start_date} 至 {end_date} 的数据"

    for col in ["Open", "High", "Low", "Close"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    csv_out = df[["Date", "Open", "High", "Low", "Close", "Volume"]].to_csv(
        index=False
    )

    header = f"# {code} K线数据 (A股) {start_date} ~ {end_date}\n"
    header += f"# 数据条数: {len(df)}\n"
    header += f"# 数据源: {data_source}\n"
    header += f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    result = header + csv_out

    if save:
        save_data_file(code, f"kline_{start_date}_{end_date}.csv", result)

    return result


# ===========================================================================
# 2. get_indicators - 获取技术指标
# ===========================================================================

_INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50日均线: 中期趋势指标",
    "close_200_sma": "200日均线: 长期趋势基准",
    "close_10_ema": "10日EMA: 短期快速均线",
    "macd": "MACD: 指数平滑异同移动平均线",
    "macds": "MACD信号线: MACD的EMA平滑",
    "macdh": "MACD柱状图: MACD与信号线差值",
    "rsi": "RSI: 相对强弱指标 (超买>70, 超卖<30)",
    "boll": "布林带中轨: 20日均线",
    "boll_ub": "布林带上轨: 中轨+2倍标准差",
    "boll_lb": "布林带下轨: 中轨-2倍标准差",
    "atr": "ATR: 平均真实波幅",
    "vwma": "VWMA: 成交量加权移动均线",
    "mfi": "MFI: 资金流量指标",
}


def get_indicators(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int = 60,
    save: bool = True,
) -> str:
    """计算技术指标 (基于stockstats).

    Args:
        symbol: 6位A股代码
        indicator: 指标名称 (如 rsi, macd, close_50_sma)
        curr_date: 当前日期 (YYYY-MM-DD)
        look_back_days: 回看天数
        save: 是否保存到data目录

    Returns:
        格式化的指标数据文本
    """
    code = _normalize_ticker(symbol)

    if indicator not in _INDICATOR_DESCRIPTIONS:
        return f"不支持的指标 {indicator}，可选: {list(_INDICATOR_DESCRIPTIONS.keys())}"

    try:
        from stockstats import wrap

        # 获取K线数据
        client = _get_mootdx_client()
        df = client.bars(symbol=code, category=4, offset=800)

        if df is None or df.empty:
            raise ValueError(f"No OHLCV data for {code}")

        df = df.drop(
            columns=["datetime", "year", "month", "day", "hour", "minute"],
            errors="ignore",
        )
        df = df.reset_index()
        df = df.rename(
            columns={
                "datetime": "Date",
                "open": "Open",
                "close": "Close",
                "high": "High",
                "low": "Low",
                "volume": "Volume",
            }
        )
        df = _normalize_ohlcv_dates(df)
        df = df[df["Date"] <= pd.to_datetime(curr_date)]

        df_wrap = wrap(df)
        df_wrap["Date"] = df_wrap["Date"].dt.strftime("%Y-%m-%d")
        _ = df_wrap[indicator]

        ind_dict = {}
        for _, row in df_wrap.iterrows():
            d = row["Date"]
            v = row[indicator]
            ind_dict[d] = "N/A" if pd.isna(v) else str(round(float(v), 4))

        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        before = curr_dt - timedelta(days=look_back_days)

        lines = []
        dt = curr_dt
        while dt >= before:
            ds = dt.strftime("%Y-%m-%d")
            val = ind_dict.get(ds, "N/A (非交易日)")
            lines.append(f"{ds}: {val}")
            dt -= timedelta(days=1)

        result = (
            f"## {code} {indicator} 指标 ({before.strftime('%Y-%m-%d')} ~ {curr_date})\n\n"
            + "\n".join(lines)
            + f"\n\n指标说明: {_INDICATOR_DESCRIPTIONS.get(indicator, '')}"
        )

        if save:
            save_data_file(code, f"indicator_{indicator}_{curr_date}.txt", result)

        return result

    except Exception as e:
        return f"计算 {code} 的 {indicator} 指标出错: {str(e)}"


# ===========================================================================
# 3. get_fundamentals - 获取基本面数据
# ===========================================================================

def get_fundamentals(
    ticker: str,
    curr_date: str = None,
    save: bool = True,
) -> str:
    """获取公司基本面数据 (腾讯+东财+同花顺).

    Args:
        ticker: 6位A股代码
        curr_date: 当前日期 (可选)
        save: 是否保存到data目录

    Returns:
        格式化的基本面数据文本
    """
    code = _normalize_ticker(ticker)

    try:
        lines = []

        # 腾讯财经: 实时估值
        try:
            tq = _tencent_quote([code])
            if code in tq:
                q = tq[code]
                lines.extend([
                    f"股票名称: {q['name']}",
                    f"最新价: {q['price']}",
                    f"涨跌幅: {q['change_pct']}%",
                    f"市盈率(TTM): {q['pe_ttm']}",
                    f"市盈率(静态): {q['pe_static']}",
                    f"市净率: {q['pb']}",
                    f"总市值(亿元): {q['mcap_yi']}",
                    f"流通市值(亿元): {q['float_mcap_yi']}",
                    f"换手率: {q['turnover_pct']}%",
                    f"涨停价: {q['limit_up']}",
                    f"跌停价: {q['limit_down']}",
                ])
        except Exception as e:
            print(f"腾讯报价失败 {code}: {e}")

        # mootdx: 财务快照
        try:
            client = _get_mootdx_client()
            fin = client.finance(symbol=code)
            if fin is not None and not (isinstance(fin, pd.DataFrame) and fin.empty):
                row = fin.iloc[0] if isinstance(fin, pd.DataFrame) else fin
                field_map = {
                    "eps": "每股收益(季度)",
                    "bvps": "每股净资产",
                    "roe": "净资产收益率(%)",
                    "profit": "净利润",
                    "income": "营业收入",
                }
                idx = row.index if hasattr(row, "index") else []
                for field, label in field_map.items():
                    if field in idx:
                        val = row[field]
                        if val is not None and str(val) != "nan":
                            lines.append(f"{label}: {val}")
        except Exception as e:
            print(f"mootdx财务快照失败 {code}: {e}")

        # 东方财富: 基本信息
        try:
            market_code = 1 if code.startswith("6") else 0
            info_url = "https://push2.eastmoney.com/api/qt/stock/get"
            info_params = {
                "fltt": "2",
                "invt": "2",
                "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43",
                "secid": f"{market_code}.{code}",
            }
            r = _em_get(info_url, params=info_params, timeout=10)
            d = r.json().get("data", {})
            if d:
                if d.get("f127"):
                    lines.append(f"所属行业: {d['f127']}")
                if d.get("f189"):
                    lines.append(f"上市日期: {d['f189']}")
        except Exception as e:
            print(f"东财基本信息失败 {code}: {e}")

        if not lines:
            return f"未找到 {code} 的基本面数据"

        header = f"# {code} 基本面数据 (A股)\n"
        header += f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        result = header + "\n".join(lines)

        if save:
            save_data_file(code, f"fundamentals_{datetime.now().strftime('%Y%m%d')}.txt", result)

        return result

    except Exception as e:
        return f"获取 {code} 基本面数据出错: {str(e)}"


# ===========================================================================
# 4. 财报数据 (资产负债表/利润表/现金流量表)
# ===========================================================================

def _get_financial_report_sina(
    code: str, report_type: str, freq: str = "quarterly", curr_date: str = None,
) -> pd.DataFrame:
    """从新浪财经获取财报数据.

    report_type: 'balance' | 'income' | 'cashflow'
    """
    _report_type_map = {
        "balance": "fzb",
        "income": "lrb",
        "cashflow": "llb",
    }
    source_type = _report_type_map.get(report_type, "lrb")

    prefix = "sh" if code.startswith("6") else "sz"
    paper_code = f"{prefix}{code}"
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": paper_code,
        "source": source_type,
        "type": "0",
        "page": "1",
        "num": "20",
    }
    r = requests.get(url, params=params, headers={"User-Agent": _UA}, timeout=15)
    d = r.json()

    result = d.get("result", {}).get("data", {})
    items = result.get(source_type, [])
    if isinstance(items, list) and items:
        df = pd.DataFrame(items)
    else:
        # 新版返回结构: report_list (科创板等)
        report_list = result.get("report_list", {})
        if not report_list:
            return pd.DataFrame()
        rows = []
        for date_str, report in report_list.items():
            row = {"报告日": date_str}
            for item in report.get("data", []):
                title = item.get("item_title", "")
                value = item.get("item_value", "")
                if title:
                    row[title] = value
            rows.append(row)
        df = pd.DataFrame(rows)

    if curr_date and "报告日" in df.columns:
        df["报告日"] = pd.to_datetime(df["报告日"], errors="coerce")
        cutoff = pd.to_datetime(curr_date)
        df = df[df["报告日"] <= cutoff]

    if freq.lower() == "annual" and "报告日" in df.columns:
        months = pd.to_datetime(df["报告日"], errors="coerce").dt.month
        df = df[months == 12]

    return df.head(8)


def get_balance_sheet(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str = None,
    save: bool = True,
) -> str:
    """获取资产负债表."""
    code = _normalize_ticker(ticker)
    try:
        df = _get_financial_report_sina(code, "balance", freq, curr_date)
        if df.empty:
            return f"未找到 {code} 的资产负债表数据"
        csv_out = df.to_csv(index=False)
        header = f"# {code} 资产负债表 (A股, {freq})\n"
        header += f"# 数据源: 新浪财经\n"
        header += f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        result = header + csv_out
        if save:
            save_data_file(code, f"balance_sheet_{freq}.csv", result)
        return result
    except Exception as e:
        return f"获取 {code} 资产负债表出错: {str(e)}"


def get_income_statement(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str = None,
    save: bool = True,
) -> str:
    """获取利润表."""
    code = _normalize_ticker(ticker)
    try:
        df = _get_financial_report_sina(code, "income", freq, curr_date)
        if df.empty:
            return f"未找到 {code} 的利润表数据"
        csv_out = df.to_csv(index=False)
        header = f"# {code} 利润表 (A股, {freq})\n"
        header += f"# 数据源: 新浪财经\n"
        header += f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        result = header + csv_out
        if save:
            save_data_file(code, f"income_statement_{freq}.csv", result)
        return result
    except Exception as e:
        return f"获取 {code} 利润表出错: {str(e)}"


def get_cashflow(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str = None,
    save: bool = True,
) -> str:
    """获取现金流量表."""
    code = _normalize_ticker(ticker)
    try:
        df = _get_financial_report_sina(code, "cashflow", freq, curr_date)
        if df.empty:
            return f"未找到 {code} 的现金流量表数据"
        csv_out = df.to_csv(index=False)
        header = f"# {code} 现金流量表 (A股, {freq})\n"
        header += f"# 数据源: 新浪财经\n"
        header += f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        result = header + csv_out
        if save:
            save_data_file(code, f"cashflow_{freq}.csv", result)
        return result
    except Exception as e:
        return f"获取 {code} 现金流量表出错: {str(e)}"


# ===========================================================================
# 5. get_news - 个股新闻
# ===========================================================================

def _fetch_news_eastmoney(code: str, page_size: int = 20) -> list[dict]:
    """从东方财富获取个股新闻."""
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    inner_param = {
        "uid": "",
        "keyword": code,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "",
                "postTag": "",
            }
        },
    }
    params = {
        "cb": "callback",
        "param": json.dumps(inner_param, ensure_ascii=False),
        "_": "1",
    }
    headers = {
        "Referer": "https://so.eastmoney.com/",
        "User-Agent": _UA,
    }
    resp = _em_get(url, params=params, headers=headers, timeout=15)
    text = resp.text
    text = text[text.index("(") + 1: text.rindex(")")]
    data = json.loads(text)

    articles = []
    for item in data.get("result", {}).get("cmsArticleWebOld", []):
        articles.append({
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "time": item.get("date", ""),
            "source": item.get("mediaName", "东方财富"),
            "url": item.get("url", ""),
        })
    return articles


def get_news(
    ticker: str,
    start_date: str,
    end_date: str,
    save: bool = True,
) -> str:
    """获取个股新闻.

    Args:
        ticker: 6位A股代码
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        save: 是否保存到data目录

    Returns:
        格式化的新闻列表
    """
    code = _normalize_ticker(ticker)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    articles = []
    try:
        articles = _fetch_news_eastmoney(code)
    except Exception as e:
        print(f"东财新闻获取失败 {code}: {e}")

    if not articles:
        return f"未找到 {code} 的新闻数据"

    news_str = ""
    count = 0
    for art in articles:
        pub_time = art.get("time", "")
        try:
            pub_dt = datetime.strptime(pub_time[:10], "%Y-%m-%d")
            if pub_dt < start_dt or pub_dt > end_dt:
                continue
        except (ValueError, IndexError):
            pass

        title = art["title"]
        content = art.get("content", "")
        source = art.get("source", "东方财富")
        link = art.get("url", "")

        news_str += f"### {title} (来源: {source})\n"
        if content:
            snippet = content[:300] + "..." if len(content) > 300 else content
            news_str += f"{snippet}\n"
        if link and link != "nan":
            news_str += f"链接: {link}\n"
        news_str += "\n"
        count += 1

    if count == 0:
        return f"在 {start_date} 至 {end_date} 期间未找到 {code} 的新闻"

    result = f"## {code} 新闻 ({start_date} ~ {end_date})\n\n共 {count} 条\n\n" + news_str

    if save:
        save_data_file(code, f"news_{start_date}_{end_date}.md", result)

    return result


# ===========================================================================
# 6. get_global_news - 全球/市场新闻
# ===========================================================================

def get_global_news(
    curr_date: str = None,
    look_back_days: int = 7,
    limit: int = 15,
    save: bool = True,
) -> str:
    """获取财联社+东财7x24全球财经新闻."""
    if not curr_date:
        curr_date = datetime.now().strftime("%Y-%m-%d")

    all_news = []

    # 财联社快讯
    try:
        cls_url = "https://www.cls.cn/nodeapi/telegraphList"
        cls_params = {"rn": str(limit), "page": "1"}
        cls_headers = {"User-Agent": _UA, "Referer": "https://www.cls.cn/"}
        r_cls = requests.get(cls_url, params=cls_params, headers=cls_headers, timeout=10)
        d_cls = r_cls.json()
        for item in d_cls.get("data", {}).get("roll_data", []):
            title = item.get("title", "") or item.get("brief", "")
            content = item.get("content", "") or item.get("brief", "")
            ctime = item.get("ctime", "")
            pub_time = ""
            if ctime:
                try:
                    pub_time = datetime.fromtimestamp(int(ctime)).strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError, OSError):
                    pub_time = str(ctime)
            all_news.append({
                "title": title,
                "content": content,
                "time": pub_time,
                "source": "财联社",
            })
    except Exception as e:
        print(f"财联社新闻失败: {e}")

    # 东财7x24
    try:
        em_url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
        em_params = {
            "client": "web",
            "biz": "web_724",
            "fastColumn": "102",
            "sortEnd": "",
            "pageSize": str(limit),
        }
        em_headers = {"User-Agent": _UA, "Referer": "https://kuaixun.eastmoney.com/"}
        r_em = _em_get(em_url, params=em_params, headers=em_headers, timeout=10)
        d_em = r_em.json()
        for item in d_em.get("data", {}).get("fastNewsList", []):
            title = item.get("title", "")
            summary = item.get("summary", "")[:200]
            pub_time = item.get("showTime", "")
            all_news.append({
                "title": title,
                "content": summary,
                "time": pub_time,
                "source": "东方财富",
            })
    except Exception as e:
        print(f"东财全球新闻失败: {e}")

    if not all_news:
        return f"未获取到 {curr_date} 的全球新闻"

    seen = set()
    unique = []
    for n in all_news:
        if n["title"] not in seen:
            seen.add(n["title"])
            unique.append(n)

    news_str = ""
    for n in unique[:limit]:
        news_str += f"### {n['title']} (来源: {n['source']})\n"
        if n.get("time"):
            news_str += f"时间: {n['time']}\n"
        if n.get("content"):
            snippet = n["content"][:300] + "..." if len(n["content"]) > 300 else n["content"]
            news_str += f"{snippet}\n"
        news_str += "\n"

    start_dt = datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)
    result = f"## 全球财经新闻 ({start_dt.strftime('%Y-%m-%d')} ~ {curr_date})\n\n" + news_str

    if save:
        filepath = os.path.join(DATA_DIR, f"global_news_{curr_date}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(result)

    return result


# ===========================================================================
# 7. get_dragon_tiger - 龙虎榜数据
# ===========================================================================

def get_dragon_tiger(
    ticker: str,
    days: int = 5,
    save: bool = True,
) -> str:
    """获取个股龙虎榜数据."""
    code = _normalize_ticker(ticker)
    try:
        datacenter_url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
            "columns": "ALL",
            "filter": f"(SECURITY_CODE=\"{code}\")",
            "pageNumber": "1",
            "pageSize": str(days * 5),
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        }
        r = _em_get(datacenter_url, params=params, timeout=15)
        d = r.json()
        data = d.get("result", {}).get("data", [])

        if not data:
            return f"近期 {code} 未上榜龙虎榜"

        lines = [f"# {code} 龙虎榜数据", f"# 共 {len(data)} 条记录", ""]
        for item in data[:days * 3]:
            trade_date = item.get("TRADE_DATE", "")[:10]
            name = item.get("SECURITY_NAME_ABBR", "")
            change_pct = item.get("CHANGE_PERCENT", "")
            buy_amount = item.get("BUY_AMOUNT", "")
            sell_amount = item.get("SELL_AMOUNT", "")
            reason = item.get("EXPLAIN", "")
            lines.append(
                f"## {trade_date} {name}\n"
                f"涨跌幅: {change_pct}%\n"
                f"买入额: {buy_amount}\n"
                f"卖出额: {sell_amount}\n"
                f"上榜原因: {reason}\n"
            )

        result = "\n".join(lines)

        if save:
            save_data_file(code, f"dragon_tiger_{datetime.now().strftime('%Y%m%d')}.md", result)

        return result

    except Exception as e:
        return f"获取 {code} 龙虎榜数据出错: {str(e)}"


# ===========================================================================
# 8. get_lockup - 限售解禁数据
# ===========================================================================

def get_lockup(
    ticker: str,
    save: bool = True,
) -> str:
    """获取限售解禁数据."""
    code = _normalize_ticker(ticker)
    try:
        datacenter_url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPT_ORGSTOCKEXPIRE_NEW",
            "columns": "ALL",
            "filter": f"(SECURITY_CODE=\"{code}\")",
            "pageNumber": "1",
            "pageSize": "20",
            "sortColumns": "FREE_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        }
        r = _em_get(datacenter_url, params=params, timeout=15)
        d = r.json()
        data = d.get("result", {}).get("data", [])

        if not data:
            return f"未找到 {code} 的限售解禁数据"

        lines = [f"# {code} 限售解禁数据", f"# 共 {len(data)} 条记录", "",
                 "| 解禁日期 | 解禁数量(万股) | 占总股本比例 | 解禁类型 | 解禁股东 |",
                 "|----------|---------------|-------------|----------|----------|"]

        for item in data[:15]:
            free_date = item.get("FREE_DATE", "")[:10] if item.get("FREE_DATE") else ""
            free_qty = item.get("FREE_QTY", "")
            free_pct = item.get("FREE_SRNEW_RATIO", "")
            free_type = item.get("FREE_TYPE", "")
            holders = item.get("LOCKER_NAME", "")
            lines.append(f"| {free_date} | {free_qty} | {free_pct}% | {free_type} | {holders} |")

        result = "\n".join(lines)

        if save:
            save_data_file(code, f"lockup_{datetime.now().strftime('%Y%m%d')}.md", result)

        return result

    except Exception as e:
        return f"获取 {code} 限售解禁数据出错: {str(e)}"


# ===========================================================================
# 9. get_northbound_flow - 北向资金
# ===========================================================================

def get_northbound_flow(
    curr_date: str = None,
    include_history: bool = True,
    save: bool = True,
) -> str:
    """获取北向资金 (沪深股通) 数据."""
    if not curr_date:
        curr_date = datetime.now().strftime("%Y-%m-%d")

    hsgt_headers = {
        "User-Agent": _UA,
        "Host": "data.hexin.cn",
        "Referer": "https://data.hexin.cn/",
    }

    lines = [
        f"# 北向资金数据 ({curr_date})",
        "# 数据源: 同花顺 hsgtApi",
        "",
    ]

    try:
        url_rt = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
        r = requests.get(url_rt, headers=hsgt_headers, timeout=10)
        d = r.json()

        times = d.get("time", [])
        hgt = d.get("hgt", [])
        sgt = d.get("sgt", [])

        if times:
            lines.append("## 实时累计净流入 (亿元)")
            n = len(times)
            start_idx = max(0, n - 8)
            for i in range(start_idx, n):
                t = times[i]
                h = hgt[i] if i < len(hgt) else "N/A"
                s = sgt[i] if i < len(sgt) else "N/A"
                lines.append(f"  {t}: 沪股通={h}  深股通={s}")

            hgt_close = float(hgt[-1]) if hgt else 0
            sgt_close = float(sgt[-1]) if sgt else 0
            total = hgt_close + sgt_close
            lines.append(
                f"\n合计: 沪股通={hgt_close:.2f}亿  "
                f"深股通={sgt_close:.2f}亿  "
                f"总计={total:.2f}亿"
            )
            if total > 0:
                lines.append("信号: 北向资金净流入 (偏多)")
            elif total < 0:
                lines.append("信号: 北向资金净流出 (偏空)")
        else:
            lines.append("暂无实时数据 (非交易时间或节假日)")

        result = "\n".join(lines)

        if save:
            filepath = os.path.join(DATA_DIR, f"northbound_{curr_date}.md")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(result)

        return result

    except Exception as e:
        return f"获取北向资金数据出错: {str(e)}"


# ===========================================================================
# 10. get_hot_stocks - 热门股 (涨停股+题材标签)
# ===========================================================================

def get_hot_stocks(
    curr_date: str = "",
    save: bool = True,
) -> str:
    """获取同花顺涨停股+题材标签."""
    if not curr_date:
        curr_date = datetime.now().strftime("%Y-%m-%d")

    try:
        url = (
            f"http://zx.10jqka.com.cn/event/api/getharden/"
            f"date/{curr_date}/orderby/date/orderway/desc/charset/GBK/"
        )
        headers = {"User-Agent": _UA}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()

        if data.get("errocode", 0) != 0:
            return f"同花顺热门股API错误: {data.get('errormsg', 'unknown')}"

        rows = data.get("data") or []
        if not rows:
            return f"{curr_date} 无热门股数据 (可能是非交易日或数据尚未更新)"

        lines = [
            f"# 热门股涨停榜 ({curr_date})",
            f"# 数据源: 同花顺 (人工标注题材标签)",
            f"# 共 {len(rows)} 只涨停股",
            "",
        ]

        from collections import Counter
        all_tags = []

        for row in rows[:30]:
            code = row.get("code", "")
            name = row.get("name", "")
            reason = row.get("reason", "")
            zhangfu = row.get("zhangfu", "")
            lines.append(f"{code} {name}: +{zhangfu}% | {reason}")
            if reason:
                tags = [t.strip() for t in str(reason).split("+") if t.strip()]
                all_tags.extend(tags)

        if all_tags:
            cnt = Counter(all_tags)
            lines.append(f"\n## 题材热度排行 (Top 15)")
            for tag, n in cnt.most_common(15):
                lines.append(f"  {tag}: {n} 只")

        result = "\n".join(lines)

        if save:
            filepath = os.path.join(DATA_DIR, f"hot_stocks_{curr_date}.md")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(result)

        return result

    except Exception as e:
        return f"获取热门股数据出错: {str(e)}"


# ===========================================================================
# 11. get_concept_blocks - 概念板块
# ===========================================================================

def get_concept_blocks(
    ticker: str,
    save: bool = True,
) -> str:
    """获取股票所属概念板块 (百度股市通)."""
    code = _normalize_ticker(ticker)
    try:
        url = (
            "https://finance.pae.baidu.com/api/getrelatedblock"
            f'?stock=[{{"code":"{code}","market":"ab","type":"stock"}}]'
            "&finClientType=pc"
        )
        headers = {
            "Host": "finance.pae.baidu.com",
            "User-Agent": _UA,
            "Accept": "application/vnd.finance-web.v1+json",
            "Origin": "https://gushitong.baidu.com",
            "Referer": "https://gushitong.baidu.com/",
        }
        r = requests.get(url, headers=headers, timeout=15)
        d = r.json()

        if d.get("ResultData"):
            result_data = d["ResultData"]
        else:
            result_data = d.get("data", {})

        lines = [f"# {code} 所属概念板块", ""]

        if isinstance(result_data, dict):
            for key in ["industry", "concept", "region"]:
                blocks = result_data.get(key, [])
                if blocks:
                    label_map = {"industry": "行业板块", "concept": "概念板块", "region": "地区板块"}
                    lines.append(f"## {label_map.get(key, key)}")
                    for b in blocks:
                        if isinstance(b, dict):
                            name = b.get("name", b.get("blockName", ""))
                            change = b.get("change", b.get("changeRatio", ""))
                            lines.append(f"  - {name} ({change}%)")
                        else:
                            lines.append(f"  - {b}")
                    lines.append("")

        result = "\n".join(lines)

        if save:
            save_data_file(code, f"concept_blocks_{datetime.now().strftime('%Y%m%d')}.md", result)

        return result

    except Exception as e:
        return f"获取 {code} 概念板块出错: {str(e)}"


# ===========================================================================
# 12. get_insider_transactions - 内部人/股东交易
# ===========================================================================

def get_insider_transactions(
    ticker: str,
    save: bool = True,
) -> str:
    """获取股东研究/内部人交易数据."""
    code = _normalize_ticker(ticker)
    try:
        client = _get_mootdx_client()
        text = client.F10(symbol=code, name="股东研究")

        if not text or not text.strip():
            return f"未找到 {code} 的股东研究数据"

        result = f"# {code} 股东研究 (A股)\n"
        result += f"# 数据源: mootdx F10\n"
        result += f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        # 截取股东变化部分
        sec4_hits = list(re.finditer(r"\r?\n【4\.股东变化】\r?\n", text))
        if sec4_hits:
            sec4_pos = sec4_hits[-1].start()
            result += text[:sec4_pos] + "\n---\n" + text[sec4_pos:sec4_pos + 2000]
        else:
            result += text[:3000]

        if save:
            save_data_file(code, f"insider_transactions_{datetime.now().strftime('%Y%m%d')}.txt", result)

        return result

    except Exception as e:
        return f"获取 {code} 股东数据出错: {str(e)}"


# ===========================================================================
# 13. get_profit_forecast - 一致预期/盈利预测
# ===========================================================================

def get_profit_forecast(
    ticker: str,
    save: bool = True,
) -> str:
    """获取一致预期EPS预测 (同花顺)."""
    code = _normalize_ticker(ticker)
    try:
        url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
        headers = {"User-Agent": _UA, "Referer": "https://basic.10jqka.com.cn/"}
        r = requests.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
        dfs = pd.read_html(r.text)

        forecast_df = None
        for df in dfs:
            cols = [str(c) for c in df.columns]
            if any("每股收益" in c or "均值" in c for c in cols):
                forecast_df = df
                break

        if forecast_df is None or forecast_df.empty:
            return f"未找到 {code} 的一致预期数据"

        lines = [
            f"# {code} 一致预期EPS预测",
            f"# 数据源: 同花顺",
            f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        eps_by_year = {}
        for _, row in forecast_df.iterrows():
            year = str(row.iloc[0]) if len(row) > 0 else ""
            count_val = row.iloc[1] if len(row) > 1 else 0
            mean_eps_val = row.iloc[3] if len(row) > 3 else 0
            min_eps_val = row.iloc[2] if len(row) > 2 else "N/A"
            max_eps_val = row.iloc[4] if len(row) > 4 else "N/A"
            try:
                count = int(count_val)
            except (ValueError, TypeError):
                count = 0
            try:
                mean_eps = float(mean_eps_val)
            except (ValueError, TypeError):
                mean_eps = 0
            lines.append(
                f"FY{year}: EPS={mean_eps} (区间 {min_eps_val}~{max_eps_val}), "
                f"覆盖机构={count}家"
            )
            if count < 3:
                lines.append("  提示: 机构覆盖较少 (<3家)")
            eps_by_year[year] = mean_eps

        # 前向估值
        try:
            tq = _tencent_quote([code])
            if code in tq:
                price = tq[code]["price"]
                pe_ttm = tq[code]["pe_ttm"]
                lines.append(f"\n当前股价: {price}元, PE(TTM): {pe_ttm}")

                years_sorted = sorted(eps_by_year.keys())
                if years_sorted and eps_by_year.get(years_sorted[0], 0) > 0:
                    eps_cur = eps_by_year[years_sorted[0]]
                    fwd_pe = price / eps_cur
                    lines.append(f"前瞻PE (FY{years_sorted[0]}): {fwd_pe:.1f}x")
        except Exception:
            pass

        result = "\n".join(lines)

        if save:
            save_data_file(code, f"profit_forecast_{datetime.now().strftime('%Y%m%d')}.md", result)

        return result

    except Exception as e:
        return f"获取 {code} 盈利预测出错: {str(e)}"


# ===========================================================================
# 14. get_fund_flow - 资金流向 (stub)
# ===========================================================================

def get_fund_flow(
    ticker: str,
    include_history: bool = True,
    save: bool = True,
) -> str:
    """获取个股资金流向数据 (stub)."""
    code = _normalize_ticker(ticker)
    result = f"# {code} 资金流向数据\n# 数据源: 未实现\n"
    if save:
        save_data_file(code, f"fund_flow_{datetime.now().strftime('%Y%m%d')}.md", result)
    return result
