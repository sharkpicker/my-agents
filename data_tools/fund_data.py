"""基金数据获取模块.

基于天天基金(东方财富)开放接口，提供基金净值/概况/重仓股/经理/业绩/申赎数据。
数据自动缓存到 data/<基金代码>/ 目录下，与股票数据保持相同的存储结构以便兼容。

数据源:
- 天天基金 lsjz 接口: 历史净值（单位净值/累计净值/日增长率）
- 天天基金 F10 详情页: 基金概况/重仓股/基金经理（HTML 表格）
- 东方财富 datacenter: 基金份额/规模变动
- 东方财富移动端 API: 基金业绩
"""

from __future__ import annotations

import os
import re
import json
import time
import random
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests

# 复用股票模块的存储与节流机制，保证数据落盘格式一致
from .stock_data import (
    save_fund_data_file,
    get_funds_dir,
    get_fund_data_dir,
    _UA,
    _em_get,
    _http_get,
)

# ---------------------------------------------------------------------------
# 基金接口端点
# ---------------------------------------------------------------------------

_FUND_LSJZ = "https://api.fund.eastmoney.com/f10/lsjz"          # 历史净值
_FUND_F10 = "https://fundf10.eastmoney.com"                       # F10 详情页
_FUND_MOB = "https://fundmobapi.eastmoney.com/FundMNewApi"       # 移动端 JSON API
_FUND_DATACENTER = "https://datacenter-web.eastmoney.com/api/data/v1/get"

_FUND_HEADERS = {
    "User-Agent": _UA,
    "Referer": "https://fundf10.eastmoney.com/",
}


def _fund_get(url, params=None, headers=None, timeout=15):
    """基金接口统一请求入口: 自动附加 Referer。"""
    h = dict(_FUND_HEADERS)
    if headers:
        h.update(headers)
    return requests.get(url, params=params, headers=h, timeout=timeout)


def _unescape_js_string(s: str) -> str:
    """反转义 JS 字符串中的转义序列，但保留原始 UTF-8 中文字符。

    天天基金接口返回的 content 字段中，HTML 属性使用单引号，
    因此通常不含 \" 转义；但为健壮性仍处理常见的转义序列。
    不能用 .decode('unicode_escape')，那样会破坏 UTF-8 多字节字符。
    """
    if not s:
        return s
    return (
        s.replace('\\"', '"')
        .replace("\\'", "'")
        .replace("\\/", "/")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
    )


def _normalize_fund_code(symbol: str) -> str:
    """规范化基金代码为纯 6 位数字（去除后缀/前缀）。"""
    s = str(symbol).strip().upper()
    for suffix in (".OF", ".SH", ".SZ"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    s = re.sub(r"[^\d]", "", s)
    return s


# ---------------------------------------------------------------------------
# 路由探测: 判断代码是基金还是股票
# ---------------------------------------------------------------------------

# 明确的 A 股股票代码模式 —— 命中即直接判定为股票，不再探测基金接口。
# 注意: 000xxx 与基金代码空间重叠（如 000001 既是平安银行也是华夏成长基金），
# 默认按股票处理；用户若需分析同名基金，应在输入中附带基金关键词
# （基金/ETF/净值/申购/赎回/A类/C类/混合/联接 等）由 SKILL 层路由。
_STOCK_CODE_PATTERNS = [
    re.compile(r"^6\d{5}$"),       # 60xxxx / 600/601/603/605 上交所主板
    re.compile(r"^688\d{3}$"),     # 科创板
    re.compile(r"^689\d{3}$"),
    re.compile(r"^000\d{3}$"),     # 000xxx 深交所主板（默认股票，如 000001 平安银行）
    re.compile(r"^002\d{3}$"),     # 中小板
    re.compile(r"^003\d{3}$"),     # 深交所主板
    re.compile(r"^30\d{4}$"),      # 300xxx / 301xxx 创业板
    re.compile(r"^[489]\d{5}$"),   # 北交所 / 原新三板
]

# 基金关键词 —— SKILL 层据此将输入判定为基金
_FUND_KEYWORDS = (
    "基金", "ETF", "LOF", "联接", "申购", "赎回", "净值", "份额",
    "A类", "C类", "混合", "股票型", "债券型", "指数型", "QDII",
    "场内", "场外", "定投",
)


def has_fund_keyword(text: str) -> bool:
    """判断输入文本是否包含基金关键词（供 SKILL 路由使用）。"""
    if not text:
        return False
    return any(k in text for k in _FUND_KEYWORDS)


def is_fund_code(symbol: str) -> tuple[bool, str]:
    """探测代码是否为基金代码。

    路由策略:
    1. 命中明确的 A 股股票代码模式 → 直接判定为股票（不探测基金接口），
       避免与基金代码空间重叠导致的误判（如 000001 平安银行 vs 华夏成长基金）。
    2. 其余 6 位代码 → 探测天天基金概况接口，命中则判定为基金。

    返回 (是否基金, 基金简称)。
    """
    code = _normalize_fund_code(symbol)
    if not code or len(code) != 6:
        return False, ""
    # 明确的股票代码模式直接判定为股票
    if any(p.match(code) for p in _STOCK_CODE_PATTERNS):
        return False, ""
    try:
        name = _probe_fund_name(code)
        if name:
            return True, name
    except Exception:
        pass
    return False, ""


def _probe_fund_name(code: str) -> str:
    """从概况接口提取基金简称，失败返回空串。"""
    try:
        url = f"{_FUND_F10}/jbgk_{code}.html"
        r = _fund_get(url, timeout=10)
        r.encoding = "utf-8"
        # 概况页 <title> 通常为 "工银前沿医疗股票A(001717)基金概况"
        m = re.search(r"<title>(.*?)\(", r.text)
        if m:
            return m.group(1).strip()
        # 备用: 从正文中提取基金简称
        m = re.search(r"基金简称</th>\s*<td[^>]*>(.*?)</td>", r.text)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# 1. get_fund_nav - 历史净值
# ---------------------------------------------------------------------------

def _parse_nav_table(content_html: str) -> list[dict]:
    """从 F10DataApi 返回的 HTML 表格中解析净值记录。"""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", content_html, re.S)
    records = []
    for tr in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        cells = [c for c in cells if c != ""]
        # 表格列: 净值日期, 单位净值, 累计净值, 日增长率, 申购状态, 赎回状态, 分红送配
        if len(cells) >= 4 and re.match(r"\d{4}-\d{2}-\d{2}", cells[0]):
            records.append({
                "Date": cells[0],
                "单位净值": cells[1],
                "累计净值": cells[2],
                "日增长率(%)": cells[3],
            })
    return records


def get_fund_nav(
    symbol: str,
    start_date: str,
    end_date: str,
    save: bool = True,
) -> str:
    """获取基金历史净值（单位净值/累计净值/日增长率）。

    Args:
        symbol: 6 位基金代码
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        save: 是否保存到 data 目录

    Returns:
        格式化的净值数据文本 (CSV)
    """
    code = _normalize_fund_code(symbol)
    try:
        rows = []
        page = 1
        per = 49  # 每页条数（F10DataApi 默认 49）
        while True:
            params = {
                "type": "lsjz",
                "code": code,
                "page": str(page),
                "sdate": start_date,
                "edate": end_date,
                "per": str(per),
            }
            r = _fund_get(_FUND_F10 + "/F10DataApi.aspx", params=params, timeout=15)
            r.encoding = "utf-8"
            text = r.text
            # 返回格式: var apidata={ content:"...", records:49, pages:1, curpage:1 };
            cm = re.search(r'"content"\s*:\s*"(.*?)"\s*,\s*"records"', text, re.S)
            if not cm:
                cm = re.search(r"content:\s*\"(.*?)\"\s*,\s*records", text, re.S)
            if not cm:
                break
            content_html = _unescape_js_string(cm.group(1))
            page_rows = _parse_nav_table(content_html)
            if not page_rows:
                break
            rows.extend(page_rows)

            # 解析总页数
            pm = re.search(r"pages:\s*(\d+)", text)
            total_pages = int(pm.group(1)) if pm else 1
            if page >= total_pages:
                break
            page += 1
            time.sleep(random.uniform(0.3, 0.8))

        if not rows:
            return f"未找到 {code} 在 {start_date} 至 {end_date} 的净值数据"

        df = pd.DataFrame(rows)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])
        df = df[(df["Date"] >= pd.to_datetime(start_date)) & (df["Date"] <= pd.to_datetime(end_date))]
        df = df.sort_values("Date").reset_index(drop=True)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        csv_out = df.to_csv(index=False)
        header = f"# {code} 基金净值历史 {start_date} ~ {end_date}\n"
        header += f"# 数据条数: {len(df)}\n"
        header += f"# 数据源: 天天基金 F10DataApi (lsjz)\n"
        header += f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        result = header + csv_out

        if save:
            save_fund_data_file(code, f"nav_{start_date}_{end_date}.csv", result)
        return result

    except Exception as e:
        return f"获取 {code} 基金净值出错: {str(e)}"


# ---------------------------------------------------------------------------
# 2. get_fund_info - 基金概况
# ---------------------------------------------------------------------------

def get_fund_info(symbol: str, save: bool = True) -> str:
    """获取基金概况（名称/类型/成立日/规模/经理/费率/托管人等）。"""
    code = _normalize_fund_code(symbol)
    try:
        url = f"{_FUND_F10}/jbgk_{code}.html"
        r = _fund_get(url, timeout=15)
        r.encoding = "utf-8"
        html = r.text

        lines = [f"# {code} 基金概况", f"# 数据源: 天天基金 F10",
                 f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]

        # 解析概况页表格中的键值对
        # 结构: <th>字段名</th><td>值</td>
        pairs = re.findall(
            r"<th[^>]*>\s*(.*?)\s*</th>\s*<td[^>]*>\s*(.*?)\s*</td>",
            html,
            re.S,
        )
        seen = set()
        for k, v in pairs:
            key = re.sub(r"<[^>]+>", "", k).strip()
            val = re.sub(r"<[^>]+>", "", v).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            # 过滤掉明显的非字段内容
            if len(key) > 20 or len(val) > 200:
                continue
            lines.append(f"{key}: {val}")

        if len(lines) <= 3:
            return f"未找到 {code} 的基金概况数据（可能不是有效基金代码）"

        result = "\n".join(lines)
        if save:
            save_fund_data_file(code, f"fund_info_{datetime.now().strftime('%Y%m%d')}.txt", result)
        return result

    except Exception as e:
        return f"获取 {code} 基金概况出错: {str(e)}"


# ---------------------------------------------------------------------------
# 2.5 get_fund_ftype - 轻量级"基金类型"抽取(供 fund_universe enrich 用)
# ---------------------------------------------------------------------------

# F10 jbgk_{code}.html 中"基金类型"字段是独立的 <th>基金类型</th><td>...</td>
_FTYPE_RE = re.compile(
    r'<th[^>]*>\s*基金类型\s*</th>\s*<td[^>]*>\s*([^<]+?)\s*</td>',
    re.S,
)


def get_fund_ftype(symbol: str, save: bool = False) -> str:
    """从天天基金 F10 概况页抽"基金类型"字段(轻量,只下载 jbgk 页)。

    返回示例:
    - "混合型-灵活"
    - "股票型"
    - "债券型-中短债"
    - "指数型-股票"
    - "QDII"
    - "货币型"
    - ""   (未匹配到 / 网络失败)

    用途: 修正 fund_universe 中主端点不返回 FTYPE 的问题。
    """
    code = _normalize_fund_code(symbol)
    try:
        url = f"{_FUND_F10}/jbgk_{code}.html"
        r = _fund_get(url, timeout=15)
        r.encoding = "utf-8"
        m = _FTYPE_RE.search(r.text)
        if not m:
            return ""
        ftype = re.sub(r"\s+", " ", m.group(1)).strip()
        return ftype
    except Exception as e:
        logger.warning("[%s] get_fund_ftype 失败: %s", code, e)
        return ""


# ---------------------------------------------------------------------------
# 3. get_fund_holdings - 重仓股
# ---------------------------------------------------------------------------

def get_fund_holdings(symbol: str, save: bool = True) -> str:
    """获取基金最新重仓股（前十重仓股/持仓比例/所属板块）。"""
    code = _normalize_fund_code(symbol)
    try:
        url = f"{_FUND_F10}/FundArchivesDatas.aspx"
        params = {
            "type": "jjcc",
            "code": code,
            "topline": "10",
            "year": "",
            "month": "",
        }
        r = _fund_get(url, params=params, timeout=15)
        r.encoding = "utf-8"
        text = r.text
        # 返回格式: var apidata={ content:"<html>",arryear:[...],curyear:2026};
        # content 键不带引号，提取至 ",arryear" 之前
        cm = re.search(r'content:\s*"(.*?)"\s*,\s*arryear', text, re.S)
        if not cm:
            cm = re.search(r'"content"\s*:\s*"(.*?)"\s*,\s*"arryear"', text, re.S)
        if not cm:
            return f"未找到 {code} 的重仓股数据"
        content_html = _unescape_js_string(cm.group(1))

        # 解析报告期与截止日期
        cutoff = ""
        cm2 = re.search(r"截止至[：:]\s*</font>\s*<font[^>]*>(\d{4}-\d{2}-\d{2})", content_html)
        if cm2:
            cutoff = cm2.group(1)

        # 解析表格行
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", content_html, re.S)
        lines = [f"# {code} 重仓股", f"# 数据源: 天天基金 F10",
                 f"# 报告期截止: {cutoff or '未知'}",
                 f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
        lines.append("| 序号 | 股票代码 | 股票名称 | 占净值比例(%) | 持股数(万股) | 持仓市值(万元) | 季度增减 |")
        lines.append("|------|----------|----------|-------------|-------------|---------------|----------|")
        # 导航链接文本（非数据单元格），需过滤
        _LINK_NOISE = ("变动详情", "股吧行情", "行情", "详情")
        count = 0
        for tr in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            cells = [c.replace("\r", "").replace("\n", "").replace("&nbsp;", "") for c in cells if c]
            # 过滤含导航链接文本的单元格（"变动详情股吧行情" 等）
            cells = [c for c in cells if not any(n in c for n in _LINK_NOISE)]
            if len(cells) < 4:
                continue
            # 重仓股行: 序号 / 股票代码(6位) / 股票名称 / 占净值比例 ...
            # 找到包含 6 位股票代码的单元格
            code_cell = next((c for c in cells if re.fullmatch(r"\d{6}", c)), None)
            if not code_cell:
                continue
            count += 1
            # 对齐单元格: 跳过到股票代码开始
            idx = cells.index(code_cell)
            relevant = cells[idx:]  # [代码, 名称, 比例, 持股数, 市值, 增减]
            row_cells = relevant[:6]
            # 补齐到 6 列
            while len(row_cells) < 6:
                row_cells.append("")
            lines.append(f"| {count} | " + " | ".join(row_cells) + " |")

        if count == 0:
            return f"未解析到 {code} 的重仓股明细"
        lines.append("")
        lines.append(f"共解析 {count} 只重仓股")

        result = "\n".join(lines)
        if save:
            save_fund_data_file(code, f"holdings_{datetime.now().strftime('%Y%m%d')}.md", result)
        return result

    except Exception as e:
        return f"获取 {code} 重仓股出错: {str(e)}"


# ---------------------------------------------------------------------------
# 4. get_fund_manager - 基金经理
# ---------------------------------------------------------------------------

def get_fund_manager(symbol: str, save: bool = True) -> str:
    """获取基金经理信息（现任经理/任职时间/管理规模/历史业绩）。"""
    code = _normalize_fund_code(symbol)
    try:
        url = f"{_FUND_F10}/jjjl_{code}.html"
        r = _fund_get(url, timeout=15)
        r.encoding = "utf-8"
        html = r.text

        lines = [f"# {code} 基金经理", f"# 数据源: 天天基金 F10",
                 f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]

        # 经理姓名
        names = re.findall(r'class="manager"[^>]*>\s*<a[^>]*>(.*?)</a>', html, re.S)
        # 任职时间/简历
        # 解析经理块
        mgr_blocks = re.findall(
            r'<div class="manager_info[^"]*">(.*?)(?=<div class="manager_info|</div>\s*</div>)',
            html, re.S,
        )
        if not mgr_blocks:
            mgr_blocks = re.findall(r"<table[^>]*class=\"[^\"]*w782[^\"]*\"[^>]*>(.*?)</table>", html, re.S)

        if mgr_blocks:
            for block in mgr_blocks[:3]:
                text = re.sub(r"<[^>]+>", " ", block)
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    lines.append(text)
                    lines.append("")
        else:
            # 备用: 提取所有经理相关文本
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text)
            # 截取经理相关段落
            idx = text.find("基金经理")
            if idx >= 0:
                lines.append(text[idx:idx + 1500])

        # 任职回报表（若有表格）
        try:
            dfs = pd.read_html(html)
            for df in dfs:
                cols = [str(c) for c in df.columns]
                if any("回报" in c or "收益" in c or "任职" in c for c in cols):
                    lines.append("\n## 任职回报")
                    lines.append(df.to_markdown(index=False))
                    break
        except Exception:
            pass

        if len(lines) <= 3:
            return f"未找到 {code} 的基金经理数据"

        result = "\n".join(lines)
        if save:
            save_fund_data_file(code, f"manager_{datetime.now().strftime('%Y%m%d')}.md", result)
        return result

    except Exception as e:
        return f"获取 {code} 基金经理出错: {str(e)}"


# ---------------------------------------------------------------------------
# 5. get_fund_performance - 业绩表现
# ---------------------------------------------------------------------------

def get_fund_performance(symbol: str, save: bool = True) -> str:
    """获取基金各阶段业绩表现（近1周/1月/3月/6月/1年/2年/3年/5年/今年来/成立来）。

    数据源: FundArchivesDatas.aspx?type=jdzf —— 返回 var apidata={ content:"<ul>..</ul>"};
    content 中为 <ul>/<li> 结构：首行为表头，后续每行一个阶段。
    """
    code = _normalize_fund_code(symbol)
    try:
        url = f"{_FUND_F10}/FundArchivesDatas.aspx"
        params = {"type": "jdzf", "code": code, "rt": str(random.random())}
        r = _fund_get(url, params=params, timeout=15)
        r.encoding = "utf-8"
        text = r.text

        # content 字段以 "}; 结尾，用非贪婪匹配到首个未转义引号
        cm = re.search(r'content:\s*"([^"]*)"', text, re.S)
        if not cm:
            return f"未找到 {code} 的业绩数据"
        content_html = _unescape_js_string(cm.group(1))

        # 解析 <ul>/<li> 结构
        uls = re.findall(r"<ul[^>]*>(.*?)</ul>", content_html, re.S)
        if len(uls) < 2:
            return f"未找到 {code} 的业绩数据"

        # 固定表头（首 ul 为表头，含 tooltip 噪声，故不解析）
        headers = ["阶段", "涨幅", "同类平均", "沪深300", "同类排名", "排名变动", "四分位排名"]
        lines = [f"# {code} 基金业绩表现", f"# 数据源: 天天基金 F10 (FundArchivesDatas jdzf)",
                 f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
        lines.append("## 各阶段业绩表现")
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "|".join(["------"] * len(headers)) + "|")

        # 数据行: ul[1:] 每个对应一个阶段
        # li[0]=阶段名 li[1]=涨幅 li[2]=同类平均 li[3]=沪深300 li[4]=排名 li[5]=变动 li[6]=四分位
        _PERIOD_ORDER = (
            "今年来", "近1周", "近1月", "近3月", "近6月",
            "近1年", "近2年", "近3年", "近5年", "成立来",
        )
        rows_parsed = 0
        for ul in uls[1:]:
            lis = re.findall(r"<li[^>]*>(.*?)</li>", ul, re.S)
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in lis]
            cells = [c.replace("&nbsp;", "") for c in cells if c.strip()]
            if len(cells) < 7 or cells[0] not in _PERIOD_ORDER:
                continue
            # 取前 7 列对齐表头
            row = cells[:7]
            lines.append("| " + " | ".join(row) + " |")
            rows_parsed += 1

        if rows_parsed == 0:
            return f"未找到 {code} 的业绩数据"
        lines.append("")
        lines.append(f"共解析 {rows_parsed} 个阶段")

        result = "\n".join(lines)
        if save:
            save_fund_data_file(code, f"performance_{datetime.now().strftime('%Y%m%d')}.md", result)
        return result

    except Exception as e:
        return f"获取 {code} 业绩表现出错: {str(e)}"


# ---------------------------------------------------------------------------
# 6. get_fund_flows - 份额/规模变动
# ---------------------------------------------------------------------------

def get_fund_flows(symbol: str, save: bool = True) -> str:
    """获取基金份额与规模变动（近 8 期，反映申赎压力）。"""
    code = _normalize_fund_code(symbol)
    try:
        # 东方财富 datacenter: 基金规模变动
        params = {
            "reportName": "RPT_FUND_SCALE",
            "columns": "ALL",
            "filter": f"(FCODE=\"{code}\")",
            "pageNumber": "1",
            "pageSize": "20",
            "sortColumns": "REPORTDATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        }
        r = _em_get(_FUND_DATACENTER, params=params, timeout=15)
        d = r.json()
        result = d.get("result") or {}
        data = result.get("data", []) or []

        lines = [f"# {code} 基金份额/规模变动", f"# 数据源: 东方财富 datacenter",
                 f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]

        if not data:
            # 备用: 从概况页提取最新规模
            try:
                info = get_fund_info(code, save=False)
                for line in info.split("\n"):
                    if any(k in line for k in ("规模", "份额", "净资产")):
                        lines.append(line)
                if len(lines) > 3:
                    result = "\n".join(lines)
                    if save:
                        save_fund_data_file(code, f"flows_{datetime.now().strftime('%Y%m%d')}.md", result)
                    return result
            except Exception:
                pass
            return f"未找到 {code} 的份额变动数据"

        lines.append("| 报告日 | 份额(亿份) | 规模(亿元) | 份额变化 |")
        lines.append("|--------|-----------|-----------|----------|")
        prev_share = None
        for item in data[:12]:
            rpt = (item.get("REPORTDATE") or "")[:10]
            share = item.get("FSRQ") or item.get("ENDSHARE") or item.get("NETSHARE")
            scale = item.get("NETASSET") or item.get("RZDF") or item.get("ENDNETASSET")
            chg = ""
            try:
                if prev_share is not None and share:
                    chg = f"{float(share) - float(prev_share):+.2f}"
            except (ValueError, TypeError):
                pass
            lines.append(f"| {rpt} | {share} | {scale} | {chg} |")
            prev_share = share

        result = "\n".join(lines)
        if save:
            save_fund_data_file(code, f"flows_{datetime.now().strftime('%Y%m%d')}.md", result)
        return result

    except Exception as e:
        return f"获取 {code} 份额变动出错: {str(e)}"


# ---------------------------------------------------------------------------
# 7. get_fund_news - 基金相关新闻
# ---------------------------------------------------------------------------

def get_fund_news(
    symbol: str,
    start_date: str,
    end_date: str,
    save: bool = True,
) -> str:
    """获取基金相关新闻（基于基金代码+名称搜索）。"""
    code = _normalize_fund_code(symbol)
    try:
        # 先取基金简称用于搜索
        name = _probe_fund_name(code) or code
        keyword = f"{code} {name}".strip()

        url = "https://search-api-web.eastmoney.com/search/jsonp"
        inner_param = {
            "uid": "",
            "keyword": keyword,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": 1,
                    "pageSize": 30,
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
        headers = {"Referer": "https://so.eastmoney.com/", "User-Agent": _UA}
        resp = _em_get(url, params=params, headers=headers, timeout=15)
        text = resp.text
        text = text[text.index("(") + 1: text.rindex(")")]
        d = json.loads(text)

        articles = []
        for item in d.get("result", {}).get("cmsArticleWebOld", []):
            articles.append({
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "time": item.get("date", ""),
                "source": item.get("mediaName", "东方财富"),
                "url": item.get("url", ""),
            })

        if not articles:
            return f"未找到 {code} 的基金新闻"

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
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
            news_str += f"### {title} (来源: {art.get('source', '东方财富')})\n"
            if content:
                snippet = content[:300] + "..." if len(content) > 300 else content
                news_str += f"{snippet}\n"
            if art.get("url") and art["url"] != "nan":
                news_str += f"链接: {art['url']}\n"
            news_str += "\n"
            count += 1

        if count == 0:
            return f"在 {start_date} 至 {end_date} 期间未找到 {code} 的基金新闻"

        result = f"## {code} 基金新闻 ({start_date} ~ {end_date})\n\n共 {count} 条\n\n" + news_str
        if save:
            save_fund_data_file(code, f"fund_news_{start_date}_{end_date}.md", result)
        return result

    except Exception as e:
        return f"获取 {code} 基金新闻出错: {str(e)}"


# ---------------------------------------------------------------------------
# 8. get_fund_global_news - 行业/主题政策新闻（复用股票模块）
# ---------------------------------------------------------------------------

def get_fund_global_news(symbol: str, limit: int = 20, save: bool = True) -> str:
    """获取与基金主题相关的全球财经新闻（复用股票模块的 get_global_news）。"""
    from .stock_data import get_global_news
    return get_global_news(curr_date=datetime.now().strftime("%Y-%m-%d"),
                           look_back_days=7, limit=limit, save=save)
