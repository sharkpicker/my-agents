import os, re, json, time, random, socket, urllib.request
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

def get_data_dir() -> str:
    return DATA_DIR

def get_stock_data_dir(symbol: str) -> str:
    code = _normalize_ticker(symbol)
    stock_dir = os.path.join(DATA_DIR, code)
    os.makedirs(stock_dir, exist_ok=True)
    return stock_dir

def save_data_file(symbol: str, filename: str, content: str) -> str:
    stock_dir = get_stock_data_dir(symbol)
    filepath = os.path.join(stock_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath

def _get_prefix(code: str) -> str:
    if code.startswith(("6", "9")): return "sh"
    elif code.startswith("8"): return "bj"
    return "sz"

def _normalize_ticker(symbol: str) -> str:
    s = symbol.strip().upper()
    for suffix in (".SH", ".SZ", ".BJ"):
        if s.endswith(suffix): s = s[:-len(suffix)]; break
    for prefix in ("SH", "SZ", "BJ"):
        if s.startswith(prefix): s = s[len(prefix):]; break
    return s

_mootdx_client = None
_TDX_SERVERS = [
    ("119.97.185.59", 7709), ("124.70.133.119", 7709), ("116.205.183.150", 7709),
    ("123.60.73.44", 7709), ("116.205.163.254", 7709), ("121.36.225.169", 7709),
    ("123.60.70.228", 7709), ("124.71.9.153", 7709), ("110.41.147.114", 7709),
    ("124.71.187.122", 7709),
]

def _probe_tdx(ip: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout): return True
    except OSError: return False

def _get_mootdx_client():
    global _mootdx_client
    if _mootdx_client is not None: return _mootdx_client
    from mootdx.quotes import Quotes
    for ip, port in _TDX_SERVERS:
        if _probe_tdx(ip, port):
            _mootdx_client = Quotes.factory(market="std", server=(ip, port))
            return _mootdx_client
    try:
        _mootdx_client = Quotes.factory(market="std", bestip=True)
        return _mootdx_client
    except Exception: pass
    try:
        _mootdx_client = Quotes.factory(market="std")
        return _mootdx_client
    except Exception as e:
        raise RuntimeError(f"通达信服务器不可达: {e}") from e

def _tencent_quote(codes: list) -> dict:
    prefixed = [f"{_get_prefix(c)}{c}" for c in codes]
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode("gbk")
    result = {}
    for line in raw.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line: continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53: continue
        code = key[2:]
        result[code] = {
            "name": vals[1], "price": float(vals[3]) if vals[3] else 0,
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

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_EM_SESSION = requests.Session()
_EM_SESSION.headers.update({"User-Agent": _UA})
_EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]

def _em_get(url, params=None, headers=None, timeout=15, **kwargs):
    wait = _EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0: time.sleep(wait + random.uniform(0.1, 0.5))
    try: return _EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
    finally: _em_last_call[0] = time.time()

def _sina_kline_fallback(code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    prefix = "sh" if code.startswith("6") else "sz"
    url = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {"symbol": f"{prefix}{code}", "scale": "240", "ma": "no", "datalen": "800"}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = json.loads(r.text)
    if not data: return pd.DataFrame()
    rows = []
    for item in data:
        rows.append({"Date": item["day"], "Open": float(item["open"]), "High": float(item["high"]), "Low": float(item["low"]), "Close": float(item["close"]), "Volume": int(item["volume"])})
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    if start_date: df = df[df["Date"] >= pd.to_datetime(start_date)]
    if end_date: df = df[df["Date"] <= pd.to_datetime(end_date)]
    return df

def _normalize_ohlcv_dates(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "Date" not in df.columns: return df
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
    return df.dropna(subset=["Date"])

def _merge_ohlcv(primary: pd.DataFrame, supplement: pd.DataFrame) -> pd.DataFrame:
    frames = [f for f in (primary, supplement) if f is not None and not f.empty]
    if not frames: return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    combined = pd.concat(frames, ignore_index=True)
    combined = _normalize_ohlcv_dates(combined)
    combined = combined.drop_duplicates(subset=["Date"], keep="last")
    combined = combined.sort_values("Date").reset_index(drop=True)
    return combined
