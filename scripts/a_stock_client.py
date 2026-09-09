#!/usr/bin/env python3
"""A 股全栈数据客户端。

This file centralizes endpoint implementations extracted from the original
a-stock-data SKILL.md. Except for optional mootdx and baostock TCP clients,
data sources are accessed directly through public HTTP endpoints.
"""

from __future__ import annotations
import argparse
import json
import math
import os
import re
import sys
import time
import random
import hashlib
import socket
from pathlib import Path
from typing import Any
import urllib.request
from urllib.parse import urljoin
from io import StringIO, BytesIO
import secrets
from datetime import date, datetime, timedelta, timezone
from collections import Counter
import uuid
import ssl
import io
from contextlib import contextmanager
from typing import Optional

_ctx = ssl.create_default_context()
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'

try:
    import requests  # type: ignore
except ModuleNotFoundError:
    requests = None  # type: ignore

try:
    import pandas as pd  # type: ignore
except ModuleNotFoundError:
    pd = None  # type: ignore

try:
    import numpy as np  # type: ignore
except ModuleNotFoundError:
    np = None  # type: ignore

_BS = None


def _require_requests():
    if requests is None:
        raise RuntimeError('缺少 Python 依赖 requests；安装后再调用 HTTP 端点。')
    return requests


def _require_pandas():
    if pd is None:
        raise RuntimeError('缺少 Python 依赖 pandas；安装后再调用返回 DataFrame 的端点。')
    return pd


def _require_numpy():
    if np is None:
        raise RuntimeError('缺少 Python 依赖 numpy；安装后再调用筹码分布端点。')
    return np


def _require_baostock():
    """按需导入 baostock，避免未使用该数据源时产生硬依赖。"""
    global _BS
    if _BS is None:
        try:
            import baostock as bs  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError('缺少 Python 依赖 baostock；安装后再调用估值历史端点。') from exc
        _BS = bs
    return _BS


def _new_session(trust_env: bool = False):
    req = _require_requests()
    session = req.Session()
    session.trust_env = trust_env
    session.headers.update({'User-Agent': UA})
    return session


_TICKER_RE = re.compile(
    r'^(?:(sh|sz|bj)(\d{6})|(\d{6})(?:\.(sh|sz|bj))?)$', re.IGNORECASE
)


def _natural_market(digits: str) -> str:
    """六位代码的自然市场；000xxx 的指数/个股歧义由调用方处理。"""
    if digits.startswith(('4', '8', '92')):
        return 'bj'
    if digits[0] in ('5', '6', '9'):
        return 'sh'
    return 'sz'


def normalize_code(code: str, stock_only: bool = False) -> str:
    """严格归一化 A 股代码，格式或市场矛盾时抛 ValueError。

    支持 688017、SH688017、688017.SH、SZ000001、BJ920982。
    ``stock_only=True`` 会拒绝显式写成沪市指数的 000xxx。
    """
    raw = str(code).strip()
    match = _TICKER_RE.match(raw)
    if not match:
        raise ValueError(
            f'无法把 {code!r} 解析为 6 位股票代码；支持 600519 / SH600519 / 600519.SH'
        )
    digits = match.group(2) or match.group(3)
    market = (match.group(1) or match.group(4) or '').lower()
    if market:
        if digits.startswith('000'):
            if market == 'bj':
                raise ValueError(f'{code!r} 市场标识与号段矛盾：000xxx 不属北交所。')
            if stock_only and market == 'sh':
                raise ValueError(
                    f'{code!r} 指向沪市指数而非个股；个股接口如需同号深市股票请传 sz{digits}。'
                )
        else:
            natural = _natural_market(digits)
            if market != natural:
                raise ValueError(
                    f'{code!r} 的市场标识与号段矛盾：{digits} 属 {natural} 市，而不是 {market} 市。'
                )
    return digits


norm_ticker = normalize_code

EM_HOT_BODY = {'appId': 'appId01', 'globalId': '786e4c21-70dc-435a-93bb-38'}
SINA_OPT_HDR = {'Referer': 'https://stock.finance.sina.com.cn/', 'User-Agent': UA}
ZTB_UT = '7eea3edcaed734bea9cbfc24409ed989'
_CNINFO_ORGID_MAP = {}
HSGT_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36', 'Host': 'data.hexin.cn', 'Referer': 'https://data.hexin.cn/'}
IWENCAI_KEY = os.environ.get('IWENCAI_API_KEY', '')
IWENCAI_BASE = os.environ.get('IWENCAI_BASE_URL', 'https://openapi.iwencai.com')
PDF_TPL = 'https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf'
REPORT_API = 'https://reportapi.eastmoney.com/report/list'
_em_last_call = [0.0]
EM_MIN_INTERVAL = 1.0
EM_SESSION = None
DATACENTER_URL = 'https://datacenter-web.eastmoney.com/api/data/v1/get' 

_TDX_SERVERS = [('119.97.185.59', 7709), ('124.70.133.119', 7709), ('116.205.183.150', 7709), ('123.60.73.44', 7709), ('116.205.163.254', 7709), ('121.36.225.169', 7709), ('123.60.70.228', 7709), ('124.71.9.153', 7709), ('110.41.147.114', 7709), ('124.71.187.122', 7709)]

def _probe(ip, port, timeout=2.0):
    """TCP 握手粗筛；握手成功不代表 mootdx 能真实取数。"""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False

def _validate_tdx_client(client, market: str='std') -> bool:
    """用真实 K 线请求验活；非 std 市场没有合适的 A 股样本，跳过验活。"""
    if market != 'std':
        return True
    try:
        frame = client.bars(symbol='000001', frequency=9, offset=1)
        return frame is not None and not frame.empty
    except Exception:
        return False

def tdx_client(market='std'):
    """创建 mootdx 客户端，并通过真实取数过滤握手成功但返回空数据的坏服务器。"""
    try:
        from mootdx.quotes import Quotes
    except ModuleNotFoundError as exc:
        raise RuntimeError('缺少 Python 依赖 mootdx；安装后再调用通达信 TCP 端点。') from exc
    for ip, port in _TDX_SERVERS:
        if not _probe(ip, port):
            continue
        try:
            client = Quotes.factory(market=market, server=(ip, port))
            if _validate_tdx_client(client, market):
                return client
        except Exception:
            continue
    for kwargs in ({'bestip': True}, {}):
        try:
            client = Quotes.factory(market=market, **kwargs)
            if _validate_tdx_client(client, market):
                return client
        except Exception:
            continue
    raise RuntimeError('所有 mootdx 服务器均无法取到数据（TCP 可达但可能返回空或被 reset）。海外网络通常全部超时（TCP 7709），请走国内代理或更新 _TDX_SERVERS 列表。')

def get_prefix(code: str) -> str:
    """代码 → 市场前缀；显式 sh/sz/bj 前缀或 .SH/.SZ/.BJ 后缀优先。"""
    raw = str(code).strip().lower()
    if raw.endswith(('.sh', '.sz', '.bj')):
        return raw[-2:]
    if raw.startswith(('sh', 'sz', 'bj')):
        return raw[:2]
    code = normalize_code(raw)
    sh_index = {'000300', '000905', '000016', '000688', '000852', '000010'}
    if code.startswith('92'):
        return 'bj'
    if code.startswith(('5', '6', '9')) or code in sh_index:
        return 'sh'
    if code.startswith(('4', '8')):
        return 'bj'
    return 'sz'


def em_market_code(code: str) -> int:
    """东财 secid 市场号：沪=1，深/北=0。"""
    return 1 if get_prefix(code) == 'sh' else 0


def em_secid(code: str) -> str:
    """东财 push2/push2his 的 secid，如 1.600519 / 0.300750。"""
    return f'{em_market_code(code)}.{norm_ticker(code)}'


def em_get(url: str, params: dict | None=None, headers: dict | None=None, timeout: int=15, allow_proxy_fallback: bool=True, **kwargs):
    """东财统一请求入口：自动节流 + 复用 session + 默认 UA。
    默认直连且不继承系统代理；直连失败后可尝试一次环境代理 fallback。"""
    req = _require_requests()
    global EM_SESSION
    if EM_SESSION is None:
        EM_SESSION = _new_session(trust_env=False)
    last_error = None
    for attempt in range(3):
        wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
        if wait > 0:
            time.sleep(wait + random.uniform(0.1, 0.5))
        try:
            resp = EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
            _em_last_call[0] = time.time()
            return resp
        except Exception as exc:
            last_error = exc
            _em_last_call[0] = time.time()
            if attempt < 2:
                time.sleep(0.8 + attempt * 0.8)
    if not allow_proxy_fallback:
        raise last_error
    try:
        resp = req.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
        _em_last_call[0] = time.time()
        return resp
    except Exception as exc:
        raise exc from last_error

def eastmoney_datacenter(report_name: str, columns: str='ALL', filter_str: str='', page_size: int=50, sort_columns: str='', sort_types: str='-1') -> list[dict]:
    """东财数据中心统一查询 — 龙虎榜/解禁/融资融券/大宗交易/股东户数/分红 共用（已内置限流）"""
    params = {'reportName': report_name, 'columns': columns, 'filter': filter_str, 'pageNumber': '1', 'pageSize': str(page_size), 'sortColumns': sort_columns, 'sortTypes': sort_types, 'source': 'WEB', 'client': 'WEB'}
    r = em_get(DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if d.get('result') and d['result'].get('data'):
        return d['result']['data']
    return []

def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """
    批量拉取腾讯财经实时行情。
    codes: ["688017", "300476", "002463"]
    也支持指数: ["000001", "000300", "399006"]
    也支持ETF: ["510050", "510300"]
    返回: {code: {name, price, pe_ttm, pb, mcap, ...}}
    """
    prefixed = []
    key_of = {}
    for original in codes:
        c = str(original).strip()
        low = c.lower()
        if low.startswith(('sh', 'sz', 'bj')):
            query_code = low
        else:
            normalized = normalize_code(c)
            query_code = f'{get_prefix(c)}{normalized}'
        prefixed.append(query_code)
        key_of[query_code] = c
    url = 'https://qt.gtimg.cn/q=' + ','.join(prefixed)
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode('gbk')
    result = {}
    for line in data.strip().split(';'):
        if not line.strip() or '=' not in line or '"' not in line:
            continue
        key = line.split('=')[0].split('_')[-1]
        vals = line.split('"')[1].split('~')
        if len(vals) < 53:
            continue
        code = key_of.get(key, key[2:])
        result[code] = {'name': vals[1], 'price': float(vals[3]) if vals[3] else 0, 'last_close': float(vals[4]) if vals[4] else 0, 'open': float(vals[5]) if vals[5] else 0, 'change_amt': float(vals[31]) if vals[31] else 0, 'change_pct': float(vals[32]) if vals[32] else 0, 'high': float(vals[33]) if vals[33] else 0, 'low': float(vals[34]) if vals[34] else 0, 'amount_wan': float(vals[37]) if vals[37] else 0, 'turnover_pct': float(vals[38]) if vals[38] else 0, 'pe_ttm': float(vals[39]) if vals[39] else 0, 'amplitude_pct': float(vals[43]) if vals[43] else 0, 'float_mcap_yi': float(vals[44]) if vals[44] else 0, 'mcap_yi': float(vals[45]) if vals[45] else 0, 'pb': float(vals[46]) if vals[46] else 0, 'limit_up': float(vals[47]) if vals[47] else 0, 'limit_down': float(vals[48]) if vals[48] else 0, 'vol_ratio': float(vals[49]) if vals[49] else 0, 'pe_static': float(vals[52]) if vals[52] else 0}
        quote = result[code]
        quote['is_stale'] = quote['amount_wan'] == 0 and quote['price'] == quote['last_close'] and quote['price'] > 0
        if quote['is_stale'] and key[2:4] in ('43', '83', '87'):
            quote['stale_reason'] = '北交所老号段，多数已迁至 920xxx，请按名称反查现行代码'
        elif quote['is_stale']:
            quote['stale_reason'] = '成交量为 0（停牌 / 未开盘 / 废码），报价非当日真实成交'
    return result

def baidu_kline_with_ma(code: str, start_time: str='') -> dict:
    """百度股市通K线 — 独有能力: 返回时自带 ma5/ma10/ma20 均价"""
    _require_requests()
    url = 'https://finance.pae.baidu.com/selfselect/getstockquotation'
    params = {'all': '1', 'isIndex': 'false', 'isBk': 'false', 'isBlock': 'false', 'isFutures': 'false', 'isStock': 'true', 'newFormat': '1', 'group': 'quotation_kline_ab', 'finClientType': 'pc', 'code': code, 'start_time': start_time, 'ktype': '1'}
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/vnd.finance-web.v1+json', 'Origin': 'https://gushitong.baidu.com', 'Referer': 'https://gushitong.baidu.com/'}
    r = requests.get(url, params=params, headers=headers, timeout=10)
    d = r.json()
    result = d.get('Result', {})
    md = result.get('newMarketData', {})
    keys = md.get('keys', [])
    rows = md.get('marketData', '').split(';')
    return {'keys': keys, 'rows': rows}

def eastmoney_reports(code: str, max_pages: int=5) -> list[dict]:
    """拉取指定股票的研报列表；错误格式或北交所废弃老码不会静默返回空。"""
    code = normalize_code(code, stock_only=True)
    all_records = []
    for page in range(1, max_pages + 1):
        params = {'industryCode': '*', 'pageSize': '100', 'industry': '*', 'rating': '*', 'ratingChange': '*', 'beginTime': '2000-01-01', 'endTime': '2030-01-01', 'pageNo': str(page), 'fields': '', 'qType': '0', 'orgCode': '', 'code': code, 'rcode': '', 'p': str(page), 'pageNum': str(page), 'pageNumber': str(page)}
        r = em_get(REPORT_API, params=params, headers={'Referer': 'https://data.eastmoney.com/'}, timeout=30)
        d = r.json()
        rows = d.get('data') or []
        if not rows:
            break
        all_records.extend(rows)
        if page >= (d.get('TotalPage', 1) or 1):
            break
    if not all_records and code[:2] in ('43', '83', '87'):
        raise ValueError(
            f'{code} 属北交所老号段（43/83/87），东财研报库已不再按老码索引。'
            '北交所存量标的已基本迁至 920xxx（如 832982→920982）；请按名称反查现行代码。'
        )
    return all_records

def download_pdf(record: dict, target_dir: str='./reports') -> str | None:
    """下载单份研报PDF，返回保存路径或None"""
    info_code = record.get('infoCode', '')
    if not info_code:
        return None
    date = (record.get('publishDate') or '')[:10]
    org = re.sub('[\\\\/:*?"<>|]', '_', record.get('orgSName') or '未知')[:40]
    title = re.sub('[\\\\/:*?"<>|]', '_', record.get('title', ''))[:80]
    fname = f'{date}_{org}_{title}.pdf'
    target = Path(target_dir) / fname
    if target.exists():
        return str(target)
    url = PDF_TPL.format(info_code=info_code)
    r = em_get(url, headers={'Referer': 'https://data.eastmoney.com/'}, timeout=60)
    if r.status_code == 200 and len(r.content) >= 1024:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(r.content)
        return str(target)
    return None

def eastmoney_industry_reports(industry_code: str='*', max_pages: int=5, begin: str='') -> list[dict]:
    """拉取行业研报列表（qType=1）。
    industry_code="*" = 全行业；传东财行业码（如 "1238"=IT服务Ⅱ）= 单行业。
    行业名 / 行业码在每条 record 的 industryName / industryCode 字段。
    begin 留空时默认查询相对今天近两年。"""
    if not begin:
        begin = (date.today() - timedelta(days=730)).isoformat()
    all_records = []
    for page in range(1, max_pages + 1):
        params = {'industryCode': industry_code, 'pageSize': '100', 'industry': '*', 'rating': '*', 'ratingChange': '*', 'beginTime': begin, 'endTime': '2030-01-01', 'pageNo': str(page), 'fields': '', 'qType': '1'}
        r = em_get(REPORT_API, params=params, headers={'Referer': 'https://data.eastmoney.com/'}, timeout=30)
        d = r.json()
        rows = d.get('data') or []
        if not rows:
            break
        all_records.extend(rows)
        if page >= (d.get('TotalPage', 1) or 1):
            break
    return all_records

def ths_eps_forecast(code: str) -> pd.DataFrame:
    """
    同花顺机构一致预期EPS。
    直连 basic.10jqka.com.cn，解析HTML表格。
    返回 DataFrame: 年度, 预测机构数, 最小值, 均值, 最大值
    "均值" = 机构一致预期EPS
    """
    code = normalize_code(code, stock_only=True)
    _require_requests()
    _require_pandas()
    url = f'https://basic.10jqka.com.cn/new/{code}/worth.html'
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36', 'Referer': 'https://basic.10jqka.com.cn/'}
    r = requests.get(url, headers=headers, timeout=15)
    r.encoding = 'gbk'
    dfs = pd.read_html(StringIO(r.text))
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any(('每股收益' in c or '均值' in c for c in cols)):
            return df
    return dfs[0] if dfs else pd.DataFrame()

def _claw_headers(call_type: str='normal') -> dict:
    """SkillHub 2.0 必须的 X-Claw 鉴权头"""
    return {'X-Claw-Call-Type': call_type, 'X-Claw-Skill-Id': 'report-search', 'X-Claw-Skill-Version': '2.0.0', 'X-Claw-Plugin-Id': 'none', 'X-Claw-Plugin-Version': 'none', 'X-Claw-Trace-Id': secrets.token_hex(32)}

def iwencai_search(query: str, channel: str='report', size: int=50) -> list[dict]:
    """
    iwencai 语义搜索。
    channel: "report"(研报) / "announcement"(公告) / "news"(新闻)
    size: 默认10, 实测可调到50（隐藏参数）
    """
    _require_requests()
    headers = {'Authorization': f'Bearer {IWENCAI_KEY}', 'Content-Type': 'application/json', **_claw_headers()}
    payload = {'channels': [channel], 'app_id': 'AIME_SKILL', 'query': query, 'size': size}
    r = requests.post(f'{IWENCAI_BASE}/v1/comprehensive/search', json=payload, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'iwencai HTTP {r.status_code}: {r.text[:200]}')
    data = r.json()
    if data.get('status_code', 0) != 0:
        raise RuntimeError(f"iwencai error: {data.get('status_msg', '')}")
    return data.get('data') or []

def iwencai_query(query: str, page: int=1, limit: int=50) -> list[dict]:
    """
    iwencai NL数据查询（结构化字段）。
    例: "贵州茅台 ROE" → DataFrame-like rows
    """
    _require_requests()
    headers = {'Authorization': f'Bearer {IWENCAI_KEY}', 'Content-Type': 'application/json', **_claw_headers()}
    payload = {'query': query, 'page': str(page), 'limit': str(limit), 'is_cache': '1', 'expand_index': 'true'}
    r = requests.post(f'{IWENCAI_BASE}/v1/query2data', json=payload, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'iwencai HTTP {r.status_code}: {r.text[:200]}')
    data = r.json()
    if data.get('status_code', 0) != 0:
        raise RuntimeError(f"iwencai error: {data.get('status_msg', '')}")
    return data.get('datas') or []

def dedup_articles(articles: list[dict]) -> list[dict]:
    """同一uid仅保留score最高的段落"""
    best = {}
    for a in articles:
        uid = a.get('uid', '') or f"{a.get('title', '')}|{a.get('publish_date', '')}"
        score = float(a.get('score', 0))
        if uid not in best or score > float(best[uid].get('score', 0)):
            best[uid] = a
    return sorted(best.values(), key=lambda x: x.get('publish_date', ''), reverse=True)

def ths_hot_reason(date: str=None) -> pd.DataFrame:
    """
    同花顺当日强势股归因。
    date: 'YYYY-MM-DD' 格式，None=今天
    返回 DataFrame，含每只股票的题材标签 (reason)。

    实测: 73ms 拿到 ~125 只 + 完整字段
    """
    _require_requests()
    _require_pandas()
    from datetime import date as _date
    if date is None:
        date = _date.today().strftime('%Y-%m-%d')
    url = f'http://zx.10jqka.com.cn/event/api/getharden/date/{date}/orderby/date/orderway/desc/charset/GBK/'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36'}
    r = requests.get(url, headers=headers, timeout=10)
    data = r.json()
    if data.get('errocode', 0) != 0:
        raise RuntimeError(f"同花顺热点错误: {data.get('errormsg', '')}")
    rows = data.get('data') or []
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    rename_map = {'name': '名称', 'code': '代码', 'reason': '题材归因', 'close': '收盘价', 'zhangdie': '涨跌额', 'zhangfu': '涨幅%', 'huanshou': '换手率%', 'chengjiaoe': '成交额', 'chengjiaoliang': '成交量', 'ddejingliang': '大单净量', 'market': '市场'}
    df = df.rename(columns=rename_map)
    return df

def hsgt_realtime() -> pd.DataFrame:
    """
    沪深股通当日实时分钟流向（含集合竞价 09:10–15:00，262 个时间点）。
    返回字段: time, hgt(沪股通累计净买入), sgt(深股通累计净买入)
    单位: 亿元
    """
    _require_requests()
    _require_pandas()
    url = 'https://data.hexin.cn/market/hsgtApi/method/dayChart/'
    r = requests.get(url, headers=HSGT_HEADERS, timeout=10)
    d = r.json()
    times = d.get('time', [])
    hgt = d.get('hgt', [])
    sgt = d.get('sgt', [])
    n = len(times)
    return pd.DataFrame({'time': times, 'hgt_yi': hgt[:n] + [None] * (n - len(hgt)), 'sgt_yi': sgt[:n] + [None] * (n - len(sgt))})

def _northbound_cache_path() -> Path:
    """北向资金本地 CSV 缓存路径"""
    p = Path.home() / '.tradingagents' / 'cache' / 'northbound_daily.csv'
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def _save_northbound_snapshot(date: str, hgt: float, sgt: float):
    """写入/更新当天北向收盘数据到 CSV"""
    path = _northbound_cache_path()
    rows = {}
    if path.exists():
        for line in path.read_text().strip().split('\n')[1:]:
            parts = line.split(',')
            if len(parts) == 3:
                rows[parts[0]] = line
    rows[date] = f'{date},{hgt},{sgt}'
    with open(path, 'w') as f:
        f.write('date,hgt,sgt\n')
        for d in sorted(rows.keys()):
            f.write(rows[d] + '\n')

def _load_northbound_history(n: int=20) -> pd.DataFrame:
    """读取最近 N 天北向历史"""
    _require_pandas()
    path = _northbound_cache_path()
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    return df.tail(n)

def eastmoney_concept_blocks(code: str) -> dict:
    """
    个股所属板块/概念归属（东财 slist，一次请求拿全，已内置限流）。
    返回: {total, boards: [{name, code(BK码), change_pct, lead_stock}], concept_tags: [板块名...]}
    boards 混合 行业/概念/地域，板块名自解释；concept_tags 是所有板块名的便捷列表。
    """
    market_code = em_market_code(code)
    params = {'fltt': '2', 'invt': '2', 'secid': f'{market_code}.{norm_ticker(code)}', 'spt': '3', 'pi': '0', 'pz': '200', 'po': '1', 'fields': 'f12,f14,f3,f128'}
    headers = {'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/'}
    try:
        r = em_get('https://push2.eastmoney.com/api/qt/slist/get', params=params, headers=headers, timeout=15)
        d = r.json()
    except Exception as e:
        print(f'[WARN] 东财板块归属请求失败: {e}')
        return {'total': 0, 'boards': [], 'concept_tags': []}
    diff = (d.get('data') or {}).get('diff') or {}
    items = diff.values() if isinstance(diff, dict) else diff
    boards = []
    for it in items:
        boards.append({'name': it.get('f14', ''), 'code': it.get('f12', ''), 'change_pct': it.get('f3', ''), 'lead_stock': it.get('f128', '')})
    return {'total': len(boards), 'boards': boards, 'concept_tags': [b['name'] for b in boards]}

def eastmoney_fund_flow_minute(code: str) -> list[dict]:
    """
    个股资金流向（分钟级，当日盘中）。
    code: 6位股票代码
    返回: [{time, main_net, small_net, mid_net, large_net, super_net}, ...]
    单位: 元
    """
    secid = em_secid(code)
    url = 'https://push2.eastmoney.com/api/qt/stock/fflow/kline/get'
    params = {'secid': secid, 'klt': 1, 'fields1': 'f1,f2,f3,f7', 'fields2': 'f51,f52,f53,f54,f55,f56,f57'}
    headers = {'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/', 'Origin': 'https://quote.eastmoney.com'}
    try:
        r = em_get(url, params=params, headers=headers, timeout=10)
        d = r.json()
    except Exception as e:
        print(f'[WARN] push2 资金流请求失败: {e}')
        return []
    rows = []
    for line in (d.get('data') or {}).get('klines') or []:
        parts = line.split(',')
        if len(parts) >= 6:
            rows.append({'time': parts[0], 'main_net': float(parts[1]), 'small_net': float(parts[2]), 'mid_net': float(parts[3]), 'large_net': float(parts[4]), 'super_net': float(parts[5])})
    return rows

def dragon_tiger_board(code: str, trade_date: str, look_back: int=30) -> dict:
    """
    龙虎榜数据聚合。
    trade_date: YYYY-MM-DD
    look_back: 回看天数
    返回: {records: [...], seats: {buy: [...], sell: [...]}, institution: {...}}
    """
    start = datetime.strptime(trade_date, '%Y-%m-%d') - timedelta(days=look_back)
    start_str = start.strftime('%Y-%m-%d')
    records = []
    data = eastmoney_datacenter('RPT_DAILYBILLBOARD_DETAILSNEW', filter_str=f'''(TRADE_DATE>='{start_str}')(TRADE_DATE<='{trade_date}')(SECURITY_CODE="{code}")''', page_size=50, sort_columns='TRADE_DATE', sort_types='-1')
    for row in data:
        records.append({'date': str(row.get('TRADE_DATE', ''))[:10], 'reason': row.get('EXPLANATION', ''), 'net_buy': round((row.get('BILLBOARD_NET_AMT') or 0) / 10000, 1), 'turnover': round(float(row.get('TURNOVERRATE') or 0), 2)})
    # 第 3 步会无条件统计机构席位；回看窗口无上榜记录时也必须有空列表，
    # 否则 buy_data/sell_data 未绑定并抛 UnboundLocalError（upstream #45）。
    buy_data, sell_data = [], []
    seats = {'buy': [], 'sell': []}
    if records:
        latest_date = records[0]['date']
        buy_data = eastmoney_datacenter('RPT_BILLBOARD_DAILYDETAILSBUY', filter_str=f'''(TRADE_DATE='{latest_date}')(SECURITY_CODE="{code}")''', page_size=10, sort_columns='BUY', sort_types='-1')
        for row in buy_data[:5]:
            seats['buy'].append({'name': row.get('OPERATEDEPT_NAME', ''), 'buy_amt': round((row.get('BUY') or 0) / 10000, 1), 'sell_amt': round((row.get('SELL') or 0) / 10000, 1), 'net': round((row.get('NET') or 0) / 10000, 1)})
        sell_data = eastmoney_datacenter('RPT_BILLBOARD_DAILYDETAILSSELL', filter_str=f'''(TRADE_DATE='{latest_date}')(SECURITY_CODE="{code}")''', page_size=10, sort_columns='SELL', sort_types='-1')
        for row in sell_data[:5]:
            seats['sell'].append({'name': row.get('OPERATEDEPT_NAME', ''), 'buy_amt': round((row.get('BUY') or 0) / 10000, 1), 'sell_amt': round((row.get('SELL') or 0) / 10000, 1), 'net': round((row.get('NET') or 0) / 10000, 1)})
    institution = {'buy_amt': 0, 'sell_amt': 0, 'net_amt': 0}
    for detail_data, side in [(buy_data, 'buy'), (sell_data, 'sell')]:
        for row in detail_data:
            if str(row.get('OPERATEDEPT_CODE', '')) == '0':
                amt = row.get('BUY') or 0 if side == 'buy' else row.get('SELL') or 0
                if side == 'buy':
                    institution['buy_amt'] += amt
                else:
                    institution['sell_amt'] += amt
    institution['buy_amt'] = round(institution['buy_amt'] / 10000, 1)
    institution['sell_amt'] = round(institution['sell_amt'] / 10000, 1)
    institution['net_amt'] = round(institution['buy_amt'] - institution['sell_amt'], 1)
    return {'records': records, 'seats': seats, 'institution': institution}

def lockup_expiry(code: str, trade_date: str, forward_days: int=90) -> dict:
    """
    限售解禁日历。
    返回: {history: [...], upcoming: [...]}
    """
    history_data = eastmoney_datacenter('RPT_LIFT_STAGE', filter_str=f'(SECURITY_CODE="{code}")', page_size=15, sort_columns='FREE_DATE', sort_types='-1')
    history = []
    for row in history_data:
        history.append({'date': str(row.get('FREE_DATE', ''))[:10], 'type': row.get('FREE_SHARES_TYPE', ''), 'shares': row.get('FREE_SHARES', 0), 'able_shares': row.get('ABLE_FREE_SHARES', 0), 'ratio': row.get('FREE_RATIO', 0)})
    end_date = datetime.strptime(trade_date, '%Y-%m-%d') + timedelta(days=forward_days)
    end_str = end_date.strftime('%Y-%m-%d')
    upcoming_data = eastmoney_datacenter('RPT_LIFT_STAGE', filter_str=f"""(SECURITY_CODE="{code}")(FREE_DATE>='{trade_date}')(FREE_DATE<='{end_str}')""", page_size=20, sort_columns='FREE_DATE', sort_types='1')
    upcoming = []
    for row in upcoming_data:
        upcoming.append({'date': str(row.get('FREE_DATE', ''))[:10], 'type': row.get('FREE_SHARES_TYPE', ''), 'shares': row.get('FREE_SHARES', 0), 'able_shares': row.get('ABLE_FREE_SHARES', 0), 'ratio': row.get('FREE_RATIO', 0)})
    return {'history': history, 'upcoming': upcoming}

def industry_comparison(top_n: int=20) -> dict:
    """
    全行业涨跌幅排名（东财行业板块，~100 个行业）。
    返回: {top: [...], bottom: [...], total: int}
    """
    url = 'https://push2.eastmoney.com/api/qt/clist/get'
    params = {'pn': '1', 'pz': '100', 'po': '1', 'np': '1', 'fltt': '2', 'invt': '2', 'fid': 'f3', 'fs': 'm:90+t:2', 'fields': 'f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207'}
    headers = {'User-Agent': UA}
    r = em_get(url, params=params, headers=headers, timeout=15)
    d = r.json()
    items = (d.get('data') or {}).get('diff') or []
    if not items:
        return {'top': [], 'bottom': [], 'total': 0}
    rows = []
    for i, item in enumerate(items):
        rows.append({'rank': i + 1, 'name': item.get('f14', ''), 'change_pct': item.get('f3', 0), 'code': item.get('f12', ''), 'up_count': item.get('f104', 0), 'down_count': item.get('f105', 0), 'leader': item.get('f140', ''), 'leader_change': item.get('f136', 0)})
    return {'top': rows[:top_n], 'bottom': rows[-top_n:], 'total': len(rows)}

_BOARD_FS = {'industry': 'm:90+t:2', 'concept': 'm:90+t:3', 'region': 'm:90+t:1'}
_BOARD_PERIOD = {
    'today': ('f62', 'f62', 'f184', 'f3', 'f204'),
    '5d': ('f164', 'f164', 'f165', 'f109', 'f257'),
    '10d': ('f174', 'f174', 'f175', 'f160', None),
}

def board_fund_flow(board_type: str='industry', period: str='today', top_n: int=20) -> dict:
    """板块资金流排名：行业/概念/地域 × 今日/5日/10日，按主力净流入降序。"""
    if board_type not in _BOARD_FS:
        raise ValueError(f'board_type 须为 {list(_BOARD_FS)}')
    if period not in _BOARD_PERIOD:
        raise ValueError(f'period 须为 {list(_BOARD_PERIOD)}')
    if top_n < 0:
        raise ValueError('top_n 须为非负整数')
    fid, f_main, f_pct, f_chg, f_leader = _BOARD_PERIOD[period]
    fields = ['f12', 'f14', f_chg, f_main, f_pct]
    if f_leader:
        fields.append(f_leader)
    if period == 'today':
        fields += ['f66', 'f72', 'f78', 'f84']
    url = 'https://push2.eastmoney.com/api/qt/clist/get'
    page_size = 200
    base = {'pz': str(page_size), 'po': '1', 'np': '1', 'fltt': '2', 'invt': '2', 'fid': fid, 'fs': _BOARD_FS[board_type], 'fields': ','.join(dict.fromkeys(fields))}

    def page(number: int):
        response = em_get(url, params={**base, 'pn': str(number)}, headers={'User-Agent': UA}, timeout=15)
        data = response.json().get('data') or {}
        return data.get('diff') or [], int(data.get('total') or 0)

    items, total = page(1)
    page_number = 2
    while len(items) < top_n:
        if total and len(items) >= total:
            break
        more, _ = page(page_number)
        if not more:
            break
        items += more
        page_number += 1
        if len(more) < page_size:
            break
    total = max(total, len(items))
    rows = []
    for index, item in enumerate(items):
        row = {'rank': index + 1, 'name': item.get('f14', ''), 'code': item.get('f12', ''), 'change_pct': item.get(f_chg, 0), 'main_net': item.get(f_main, 0), 'main_pct': item.get(f_pct, 0), 'leader': item.get(f_leader, '') if f_leader else ''}
        if period == 'today':
            row.update({'super_large_net': item.get('f66', 0), 'large_net': item.get('f72', 0), 'medium_net': item.get('f78', 0), 'small_net': item.get('f84', 0)})
        rows.append(row)
    return {'board_type': board_type, 'period': period, 'total': total, 'rows': rows[:top_n]}

def daily_dragon_tiger(trade_date: str=None, min_net_buy: float=None) -> dict:
    """
    全市场龙虎榜。
    trade_date: YYYY-MM-DD（默认当日）
    min_net_buy: 净买入下限（万元），None 不过滤
    返回: {date, total_records, stocks: [{code, name, reason, close, change_pct,
           net_buy_wan, buy_wan, sell_wan, turnover_pct}]}
    """
    if trade_date is None:
        trade_date = datetime.now().strftime('%Y-%m-%d')
    data = eastmoney_datacenter('RPT_DAILYBILLBOARD_DETAILSNEW', filter_str=f"(TRADE_DATE>='{trade_date}')(TRADE_DATE<='{trade_date}')", page_size=500, sort_columns='BILLBOARD_NET_AMT', sort_types='-1')
    if not data:
        return {'date': trade_date, 'total_records': 0, 'stocks': [], 'note': '无数据（非交易日或盘后未更新）'}
    actual_date = str(data[0].get('TRADE_DATE', ''))[:10] if data else trade_date
    stocks = []
    for row in data:
        net_buy = (row.get('BILLBOARD_NET_AMT') or 0) / 10000
        if min_net_buy is not None and net_buy < min_net_buy:
            continue
        stocks.append({'code': row.get('SECURITY_CODE', ''), 'name': row.get('SECURITY_NAME_ABBR', ''), 'reason': row.get('EXPLANATION', ''), 'close': row.get('CLOSE_PRICE') or 0, 'change_pct': round(float(row.get('CHANGE_RATE') or 0), 2), 'net_buy_wan': round(net_buy, 1), 'buy_wan': round((row.get('BILLBOARD_BUY_AMT') or 0) / 10000, 1), 'sell_wan': round((row.get('BILLBOARD_SELL_AMT') or 0) / 10000, 1), 'turnover_pct': round(float(row.get('TURNOVERRATE') or 0), 2)})
    return {'date': actual_date, 'total_records': len(stocks), 'stocks': stocks}

def margin_trading(code: str, page_size: int=30) -> list[dict]:
    """
    融资融券明细（日级）。
    返回: [{date, rzye(融资余额), rzmre(融资买入), rqye(融券余额), ...}]
    """
    data = eastmoney_datacenter('RPTA_WEB_RZRQ_GGMX', filter_str=f'(SCODE="{code}")', page_size=page_size, sort_columns='DATE', sort_types='-1')
    rows = []
    for row in data:
        rows.append({'date': str(row.get('DATE', ''))[:10], 'rzye': row.get('RZYE', 0), 'rzmre': row.get('RZMRE', 0), 'rzche': row.get('RZCHE', 0), 'rqye': row.get('RQYE', 0), 'rqmcl': row.get('RQMCL', 0), 'rqchl': row.get('RQCHL', 0), 'rzrqye': row.get('RZRQYE', 0)})
    return rows

def block_trade(code: str, page_size: int=20) -> list[dict]:
    """
    大宗交易记录。
    返回: [{date, price, vol, amount, buyer, seller, premium_pct}]
    """
    data = eastmoney_datacenter('RPT_DATA_BLOCKTRADE', filter_str=f'(SECURITY_CODE="{code}")', page_size=page_size, sort_columns='TRADE_DATE', sort_types='-1')
    rows = []
    for row in data:
        close = row.get('CLOSE_PRICE') or 0
        deal_price = row.get('DEAL_PRICE') or 0
        premium = (deal_price / close - 1) * 100 if close else 0
        rows.append({'date': str(row.get('TRADE_DATE', ''))[:10], 'price': deal_price, 'close': close, 'premium_pct': round(premium, 2), 'vol': row.get('DEAL_VOLUME', 0), 'amount': row.get('DEAL_AMT', 0), 'buyer': row.get('BUYER_NAME', ''), 'seller': row.get('SELLER_NAME', '')})
    return rows

def holder_num_change(code: str, page_size: int=10) -> list[dict]:
    """
    股东户数变化（季度级）。
    返回: [{date, holder_num, change_num, change_ratio, avg_shares}]
    """
    data = eastmoney_datacenter('RPT_HOLDERNUMLATEST', filter_str=f'(SECURITY_CODE="{code}")', page_size=page_size, sort_columns='END_DATE', sort_types='-1')
    rows = []
    for row in data:
        rows.append({'date': str(row.get('END_DATE', ''))[:10], 'holder_num': row.get('HOLDER_NUM', 0), 'change_num': row.get('HOLDER_NUM_CHANGE', 0), 'change_ratio': row.get('HOLDER_NUM_RATIO', 0), 'avg_shares': row.get('AVG_FREE_SHARES', 0)})
    return rows

def dividend_history(code: str, page_size: int=20) -> list[dict]:
    """
    分红送转历史。
    返回: [{date, bonus_rmb(每股派息), transfer_ratio(转增比例), bonus_ratio(送股比例)}]
    """
    data = eastmoney_datacenter('RPT_SHAREBONUS_DET', filter_str=f'(SECURITY_CODE="{code}")', page_size=page_size, sort_columns='EX_DIVIDEND_DATE', sort_types='-1')
    rows = []
    for row in data:
        rows.append({'date': str(row.get('EX_DIVIDEND_DATE', ''))[:10], 'bonus_rmb': row.get('PRETAX_BONUS_RMB', 0), 'transfer_ratio': row.get('TRANSFER_RATIO', 0), 'bonus_ratio': row.get('BONUS_RATIO', 0), 'plan': row.get('ASSIGN_PROGRESS', '')})
    return rows

def stock_fund_flow_120d(code: str) -> list[dict]:
    """
    个股资金流（日级，最近120个交易日）。
    返回: [{date, main_net(主力净流入), small_net, mid_net, large_net, super_net}]
    单位: 元
    """
    market_code = em_market_code(code)
    url = 'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get'
    params = {'secid': f'{market_code}.{norm_ticker(code)}', 'fields1': 'f1,f2,f3,f7', 'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65', 'lmt': '120'}
    headers = {'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/', 'Origin': 'https://quote.eastmoney.com'}
    try:
        r = em_get(url, params=params, headers=headers, timeout=15)
        d = r.json()
    except Exception as e:
        print(f'[WARN] push2 资金流请求失败: {e}')
        return []
    klines = (d.get('data') or {}).get('klines') or []
    rows = []
    for line in klines:
        parts = line.split(',')
        if len(parts) >= 7:
            rows.append({'date': parts[0], 'main_net': float(parts[1]) if parts[1] != '-' else 0, 'small_net': float(parts[2]) if parts[2] != '-' else 0, 'mid_net': float(parts[3]) if parts[3] != '-' else 0, 'large_net': float(parts[4]) if parts[4] != '-' else 0, 'super_net': float(parts[5]) if parts[5] != '-' else 0})
    return rows

def eastmoney_stock_news(code: str, page_size: int=20) -> list[dict]:
    """
    东财个股新闻（JSONP 接口）。
    返回: [{title, content, time, source, url}]
    """
    cb = 'jQuery_news'
    url = 'https://search-api-web.eastmoney.com/search/jsonp'
    inner_params = json.dumps({'uid': '', 'keyword': code, 'type': ['cmsArticleWebOld'], 'client': 'web', 'clientType': 'web', 'clientVersion': 'curr', 'param': {'cmsArticleWebOld': {'searchScope': 'default', 'sort': 'default', 'pageIndex': 1, 'pageSize': page_size, 'preTag': '', 'postTag': ''}}}, separators=(',', ':'))
    params = {'cb': cb, 'param': inner_params}
    headers = {'User-Agent': UA, 'Referer': 'https://so.eastmoney.com/'}
    r = em_get(url, params=params, headers=headers, timeout=15)
    text = r.text
    json_str = text[text.index('(') + 1:text.rindex(')')]
    d = json.loads(json_str)
    rows = []
    articles = d.get('result', {}).get('cmsArticleWebOld', []) or []
    for a in articles:
        rows.append({'title': re.sub('<[^>]+>', '', a.get('title', '')), 'content': re.sub('<[^>]+>', '', a.get('content', ''))[:200], 'time': a.get('date', ''), 'source': a.get('mediaName', ''), 'url': a.get('url', '')})
    return rows

def cls_telegraph(page_size: int=50) -> list[dict]:
    """
    财联社电报（全市场实时快讯）。v1 API + 本地签名，零 key。
    返回: [{title, content, time}]  time 已转为 'YYYY-MM-DD HH:MM:SS'
    """
    _require_requests()
    params = {'appName': 'CailianpressWeb', 'os': 'web', 'sv': '7.7.5', 'last_time': '', 'refresh_type': '1', 'rn': str(page_size)}
    qs = '&'.join((f'{k}={params[k]}' for k in sorted(params)))
    sign = hashlib.md5(hashlib.sha1(qs.encode()).hexdigest().encode()).hexdigest()
    url = f'https://www.cls.cn/v1/roll/get_roll_list?{qs}&sign={sign}'
    headers = {'User-Agent': UA, 'Referer': 'https://www.cls.cn/'}
    r = requests.get(url, headers=headers, timeout=10)
    d = r.json()
    rows = []
    for item in (d.get('data') or {}).get('roll_data') or []:
        ts = item.get('ctime')
        t = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else ''
        rows.append({'title': item.get('title', '') or item.get('brief', ''), 'content': item.get('content', '') or item.get('brief', ''), 'time': t})
    return rows

def eastmoney_global_news(page_size: int=50) -> list[dict]:
    """
    东方财富全球财经资讯（7x24 滚动）。
    返回: [{title, summary, time}]
    """
    url = 'https://np-weblist.eastmoney.com/comm/web/getFastNewsList'
    params = {'client': 'web', 'biz': 'web_724', 'fastColumn': '102', 'sortEnd': '', 'pageSize': str(page_size), 'req_trace': str(uuid.uuid4())}
    headers = {'User-Agent': UA, 'Referer': 'https://kuaixun.eastmoney.com/'}
    r = em_get(url, params=params, headers=headers, timeout=10)
    d = r.json()
    rows = []
    for item in (d.get('data') or {}).get('fastNewsList') or []:
        rows.append({'title': item.get('title', ''), 'summary': item.get('summary', '')[:200], 'time': item.get('showTime', '')})
    return rows

def eastmoney_stock_info(code: str) -> dict:
    """
    东财个股基本面信息。
    返回: {code, name, industry, total_shares, float_shares, mcap, float_mcap, list_date}
    """
    market_code = em_market_code(code)
    url = 'https://push2.eastmoney.com/api/qt/stock/get'
    params = {'fltt': '2', 'invt': '2', 'fields': 'f57,f58,f84,f85,f127,f116,f117,f189,f43', 'secid': f'{market_code}.{norm_ticker(code)}'}
    headers = {'User-Agent': UA}
    r = em_get(url, params=params, headers=headers, timeout=10)
    d = r.json().get('data') or {}
    return {'code': d.get('f57', ''), 'name': d.get('f58', ''), 'industry': d.get('f127', ''), 'total_shares': d.get('f84', 0), 'float_shares': d.get('f85', 0), 'mcap': d.get('f116', 0), 'float_mcap': d.get('f117', 0), 'list_date': str(d.get('f189', '')), 'price': d.get('f43', 0)}

def sina_financial_report(code: str, report_type: str='lrb', num: int=8) -> list[dict]:
    """
    新浪财报三表。
    code: 6位代码
    report_type: "fzb"(资产负债表) / "lrb"(利润表) / "llb"(现金流量表)
    num: 取最近 N 期（默认 8 期）
    返回: 按报告期倒序的记录列表，每期一条 dict：
          {"报告期": "2026-03-31", "<科目>": "<值>", "<科目>_同比": <同比>, ...}
          （item_value 为新浪原始字符串数值，仅在有同比时附 "_同比" 键）
    """
    _require_requests()
    prefix = get_prefix(code)
    paper_code = f'{prefix}{norm_ticker(code)}'
    url = 'https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022'
    params = {'paperCode': paper_code, 'source': report_type, 'type': '0', 'page': '1', 'num': str(num)}
    headers = {'User-Agent': UA}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    payload = r.json() or {}
    report_list = ((payload.get('result') or {}).get('data') or {}).get('report_list') or {}
    rows = []
    for period in sorted(report_list.keys(), reverse=True)[:num]:
        obj = report_list[period]
        rec = {'报告期': f'{period[:4]}-{period[4:6]}-{period[6:8]}'}
        for it in obj.get('data', []) or []:
            title = it.get('item_title', '')
            if not title or it.get('item_value') is None:
                continue
            rec[title] = it.get('item_value')
            tongbi = it.get('item_tongbi')
            if tongbi not in (None, ''):
                rec[title + '_同比'] = tongbi
        rows.append(rec)
    return rows

def _cninfo_ts_to_date(ts):
    """巨潮 announcementTime 返回 Unix 毫秒整数，需转换为日期字符串。"""
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d')
    return str(ts)[:10] if ts else ''

def _cninfo_orgid(code: str) -> str:
    """查股票真实 orgId。巨潮 orgId 并非统一 `gssx0{code}` 格式（如 601318→9900002221、
    601398→jjxt0000019、688017→9900041602），硬编码会导致大量股票（尤其 601xxx 段）
    返回 totalAnnouncement=0、查不到公告（#19）。优先动态查官方映射表，查不到再回退硬编码。"""
    _require_requests()
    global _CNINFO_ORGID_MAP
    if not _CNINFO_ORGID_MAP:
        try:
            r = requests.get('http://www.cninfo.com.cn/new/data/szse_stock.json', headers={'User-Agent': UA}, timeout=15)
            _CNINFO_ORGID_MAP = {s['code']: s['orgId'] for s in r.json().get('stockList', [])}
        except Exception as e:
            print(f'[WARN] 巨潮 orgId 映射表拉取失败，回退硬编码规则: {e}')
    org = _CNINFO_ORGID_MAP.get(code)
    if org:
        return org
    return f'gs{get_prefix(code)}0{norm_ticker(code)}'

def cninfo_announcements(code: str, page_size: int=30) -> list[dict]:
    """
    巨潮公告全文检索。
    返回: [{title, type, date, url}]
    """
    _require_requests()
    url = 'https://www.cninfo.com.cn/new/hisAnnouncement/query'
    org_id = _cninfo_orgid(code)
    payload = {'stock': f'{code},{org_id}', 'tabName': 'fulltext', 'pageSize': str(page_size), 'pageNum': '1', 'column': '', 'category': '', 'plate': '', 'seDate': '', 'searchkey': '', 'secid': '', 'sortName': '', 'sortType': '', 'isHLtitle': 'true'}
    headers = {'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded', 'Referer': 'https://www.cninfo.com.cn/new/disclosure', 'Origin': 'https://www.cninfo.com.cn'}
    r = requests.post(url, data=payload, headers=headers, timeout=15)
    d = r.json()
    rows = []
    for item in d.get('announcements', []) or []:
        rows.append({'title': item.get('announcementTitle', ''), 'type': item.get('announcementTypeName', ''), 'date': _cninfo_ts_to_date(item.get('announcementTime')), 'url': f"https://www.cninfo.com.cn/new/disclosure/detail?annoId={item.get('announcementId', '')}"})
    return rows

def _fmt_zt_time(t) -> str:
    """涨停板时间整数 → HH:MM:SS（92500 → 09:25:00）。"""
    s = str(t).zfill(6)
    return f'{s[0:2]}:{s[2:4]}:{s[4:6]}'

def _em_zt_api(endpoint: str, sort: str, date: str) -> list[dict]:
    """东财涨停板行情中心通用请求（push2ex，走 em_get 限流）。
    endpoint: getTopicZTPool / getTopicZBPool / getTopicDTPool / getYesterdayZTPool
    返回 data.pool 原始列表（data 为 null = 非交易日 / 参数错）。"""
    url = f'https://push2ex.eastmoney.com/{endpoint}'
    params = {'ut': ZTB_UT, 'dpt': 'wz.ztzt', 'Pageindex': 0, 'pagesize': 10000, 'sort': sort, 'date': date}
    headers = {'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/'}
    try:
        r = em_get(url, params=params, headers=headers, timeout=10)
        return (r.json().get('data') or {}).get('pool') or []
    except Exception as e:
        print(f'[WARN] 涨停板池 {endpoint} 请求失败: {e}')
        return []

def em_zt_pool(date: str) -> list[dict]:
    """涨停池。date=YYYYMMDD（交易日）。
    返回每只: code/name/price/pct/amount/float_cap/turnover/limit_days(连板数)/
    first_seal/last_seal(封板时间)/seal_fund(封板资金,元)/break_times(炸板次数)/
    industry/zt_stat(N天M板)"""
    out = []
    for p in _em_zt_api('getTopicZTPool', 'fbt:asc', date):
        out.append({'code': p['c'], 'name': p['n'], 'price': p['p'] / 1000, 'pct': round(p['zdp'], 2), 'amount': p['amount'], 'float_cap': p['ltsz'], 'turnover': round(p['hs'], 2), 'limit_days': p['lbc'], 'first_seal': _fmt_zt_time(p['fbt']), 'last_seal': _fmt_zt_time(p['lbt']), 'seal_fund': p['fund'], 'break_times': p['zbc'], 'industry': p.get('hybk', ''), 'zt_stat': f"{(p.get('zttj') or {}).get('days', '?')}天{(p.get('zttj') or {}).get('ct', '?')}板"})
    return out

def em_zb_pool(date: str) -> list[dict]:
    """炸板池（涨停后开板）。返回 code/name/price/limit_price(涨停价)/pct/turnover/
    first_seal/break_times/amplitude(振幅)/speed(涨速)/industry/zt_stat"""
    out = []
    for p in _em_zt_api('getTopicZBPool', 'fbt:asc', date):
        out.append({'code': p['c'], 'name': p['n'], 'price': p['p'] / 1000, 'limit_price': p['ztp'] / 1000, 'pct': round(p['zdp'], 2), 'turnover': round(p['hs'], 2), 'first_seal': _fmt_zt_time(p['fbt']), 'break_times': p['zbc'], 'amplitude': round(p['zf'], 2), 'speed': round(p['zs'], 2), 'industry': p.get('hybk', ''), 'zt_stat': f"{(p.get('zttj') or {}).get('days', '?')}天{(p.get('zttj') or {}).get('ct', '?')}板"})
    return out

def em_dt_pool(date: str) -> list[dict]:
    """跌停池。返回 code/name/price/pct/turnover/pe/seal_fund(封单资金)/last_seal/
    board_amount(板上成交额)/dt_days(连续跌停)/open_times(开板次数)/industry"""
    out = []
    for p in _em_zt_api('getTopicDTPool', 'fund:asc', date):
        out.append({'code': p['c'], 'name': p['n'], 'price': p['p'] / 1000, 'pct': round(p['zdp'], 2), 'turnover': round(p['hs'], 2), 'pe': p.get('pe'), 'seal_fund': p['fund'], 'last_seal': _fmt_zt_time(p['lbt']), 'board_amount': p.get('fba'), 'dt_days': p.get('days'), 'open_times': p.get('oc'), 'industry': p.get('hybk', '')})
    return out

def em_yzt_pool(date: str) -> list[dict]:
    """昨日涨停池（昨涨停今表现，算晋级率/赚钱效应）。返回 code/name/price/
    pct(今日涨幅)/turnover/amplitude/speed/y_first_seal(昨封板时间)/
    y_limit_days(昨连板)/industry/zt_stat"""
    out = []
    for p in _em_zt_api('getYesterdayZTPool', 'zs:desc', date):
        out.append({'code': p['c'], 'name': p['n'], 'price': p['p'] / 1000, 'pct': round(p['zdp'], 2), 'turnover': round(p['hs'], 2), 'amplitude': round(p['zf'], 2), 'speed': round(p['zs'], 2), 'y_first_seal': _fmt_zt_time(p['yfbt']), 'y_limit_days': p['ylbc'], 'industry': p.get('hybk', ''), 'zt_stat': f"{(p.get('zttj') or {}).get('days', '?')}天{(p.get('zttj') or {}).get('ct', '?')}板"})
    return out

def ths_limit_up_pool(date: str) -> list[dict]:
    """同花顺涨停揭秘（涨停原因 + 封板质量增强源）。date=YYYYMMDD。
    返回每只: code/name/price/pct/reason(涨停原因题材)/board_type(换手板/一字板/T字板)/
    seal_rate(封板成功率,0~1)/break_times(炸板次数)/seal_amount(封单额,元)/
    high_days(几天几板)/first_time(首次涨停时间)/is_again(是否回封 0/1)"""
    _require_requests()
    url = 'https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool'
    params = {'page': 1, 'limit': 200, 'field': '199112,10,9001,330323,330324,330325,9002,330329,133971,133970,1968584,3475914,9003,9004', 'filter': 'HS,GEM2STAR', 'order_field': '330324', 'order_type': '0', 'date': date}
    try:
        r = requests.get(url, params=params, headers={'User-Agent': UA}, timeout=10)
        info = (r.json().get('data') or {}).get('info', [])
    except Exception as e:
        print(f'[WARN] 同花顺涨停揭秘请求失败: {e}')
        return []
    out = []
    for it in info:
        ft = it.get('first_limit_up_time')
        out.append({'code': it.get('code'), 'name': it.get('name'), 'price': it.get('latest'), 'pct': it.get('change_rate'), 'reason': it.get('reason_type', ''), 'board_type': it.get('limit_up_type', ''), 'seal_rate': it.get('limit_up_suc_rate'), 'break_times': it.get('open_num') or 0, 'seal_amount': it.get('order_amount'), 'high_days': it.get('high_days', ''), 'first_time': datetime.fromtimestamp(int(ft)).strftime('%H:%M:%S') if ft else '', 'is_again': it.get('is_again_limit')})
    return out

def limit_up_sentiment(date: str) -> dict:
    """打板情绪温度计：连板梯队 + 炸板率 + 涨跌停对比。"""
    zt, zb, dt = (em_zt_pool(date), em_zb_pool(date), em_dt_pool(date))
    ladder = {}
    for s in zt:
        ladder[s['limit_days']] = ladder.get(s['limit_days'], 0) + 1
    zt_n, zb_n = (len(zt), len(zb))
    return {'date': date, 'zt_count': zt_n, 'zb_count': zb_n, 'dt_count': len(dt), 'break_rate': round(zb_n / (zt_n + zb_n) * 100, 1) if zt_n + zb_n else 0, 'max_height': max((s['limit_days'] for s in zt), default=0), 'ladder': dict(sorted(ladder.items()))}


CN_TZ = timezone(timedelta(hours=8))
MONITOR_URL = 'https://mobappconfig.securities.eastmoney.com/emcfg/stock_monitor.json'
_MONITOR_MARKET = {'1': 'SH', '0': 'SZ', 'B': 'BJ'}


def cn_today() -> str:
    """北京时间的今天（YYYY-MM-DD）。"""
    return datetime.now(CN_TZ).date().isoformat()


def em_stock_monitor(only_active: bool = True) -> list[dict]:
    """东财重点监控池；返回代码、名称、市场和监控生效时间窗。"""
    response = em_get(MONITOR_URL, headers={'Referer': 'https://vipmoney.eastmoney.com/'}, timeout=20)
    rows = response.json() or []
    today = cn_today()
    result = []
    for item in rows:
        start = item.get('VALIDATESTARTDATE', '')
        end = item.get('VALIDATEENDDATE', '')
        if only_active and not (start <= today <= end):
            continue
        raw_market = str(item.get('MARKET', '')).upper()
        result.append({
            'code': item.get('STKCODE', ''), 'name': item.get('STKNAME', ''),
            'market': _MONITOR_MARKET.get(raw_market, f'?{raw_market}'),
            'start': start, 'end': end, 'link': item.get('LINK_URL', ''),
        })
    return result


ANOMALY_BASE = 'https://dycalchis.eastmoney.com/price-anomaly'
HQ_PARAMS = {'team': 'h5', 'product': 'EastMoney', 'client': 'WAP', 'version': '9001', 'name': 'WAP', 'user': '123'}
ANOMALY_RULES = {
    1: '主板连续10个交易日内4次出现同向异常波动', 2: '创业板连续10个交易日内3次出现同向异常波动',
    3: '科创板连续10个交易日内3次出现同向异常波动', 4: '连续十个交易日内日收盘价涨跌幅偏离值累计达到+100%',
    5: '连续十个交易日内日收盘价涨跌幅偏离值累计达到-50%', 6: '连续三十个交易日内日收盘价涨跌幅偏离值累计达到+200%',
    7: '连续三十个交易日内日收盘价涨跌幅偏离值累计达到-70%', 8: '北交所连续10个交易日内3次出现同向异常波动',
    40: '连续十个交易日内日收盘价涨跌幅偏离值累计达到+150%', 50: '连续十个交易日内日收盘价涨跌幅偏离值累计达到-60%',
    60: '连续30个交易日内日收盘价涨跌幅偏离值累计达到+300%', 70: '连续30个交易日内日收盘价涨跌幅偏离值累计达到-75%',
}


def _anomaly_market(code, market, board=None) -> str:
    value = str(code or '')
    if value.startswith(('4', '8', '92')) or board == 8:
        return 'BJ'
    return 'SH' if market == 1 else 'SZ'


def _anomaly_get(path: str, page_size: int, page_no: int, **extra) -> dict:
    params = {**HQ_PARAMS, 'pageSize': str(page_size), 'pageNo': str(page_no), **extra}
    response = em_get(f'{ANOMALY_BASE}/{path}', params=params, headers={'Referer': 'https://vipmoney.eastmoney.com/'}, timeout=20)
    payload = response.json()
    if payload.get('result') != 0:
        raise RuntimeError(f"东财异动接口拒绝: result={payload.get('result')} msg={payload.get('msg')!r}")
    return payload


def em_price_anomaly(page_size: int = 200, page_no: int = 1) -> dict:
    """日内严重异常波动明细；返回 date/pages/items。"""
    payload = _anomaly_get('list', page_size, page_no)
    items = []
    for item in payload.get('data') or []:
        rule = item.get('e')
        key = rule * 10 if item.get('s') == 6 and rule in (4, 5, 6, 7) else rule
        items.append({
            'code': item.get('c'), 'name': item.get('n'),
            'market': _anomaly_market(item.get('c'), item.get('m'), item.get('s')),
            'change_pct': item.get('a'), 'deviation': item.get('x'), 'days': item.get('d'),
            'board': item.get('s'), 'rule_code': key, 'rule': ANOMALY_RULES.get(key, f'未知规则码 {key}'),
            'is_today': item.get('o') != 2,
        })
    return {'date': str(payload.get('date', '')), 'pages': payload.get('pages', 0), 'items': items}


def em_price_anomaly_count(page_size: int = 50, page_no: int = 1, sort_key: str = '', sort_dir: str = '') -> dict:
    """按标的聚合的严重异常波动次数、现价和累计偏离值。"""
    payload = _anomaly_get('count', page_size, page_no, sortKey=sort_key, sortDir=sort_dir)
    items = [{
        'code': item.get('c'), 'name': item.get('n'),
        'market': _anomaly_market(item.get('c'), item.get('m'), item.get('s')),
        'price': item.get('p'), 'change_pct': item.get('a'), 'times': item.get('t'),
        'deviation': item.get('x'), 'days': item.get('d'), 'board': item.get('s'),
    } for item in payload.get('data') or []]
    return {'date': str(payload.get('date', '')), 'pages': payload.get('pages', 0), 'items': items}

def _opt_f(x):
    try:
        return float(x)
    except Exception:
        return x

def _sina_opt_list(param: str) -> list:
    """新浪 hq.sinajs.cn 取值（GBK，逗号分隔，去 var hq_str_XXX="..." 壳）。"""
    _require_requests()
    r = requests.get(f'https://hq.sinajs.cn/list={param}', headers=SINA_OPT_HDR, timeout=10)
    r.encoding = 'gbk'
    t = r.text
    return t.split('"')[1].split(',') if '"' in t else []

def sina_option_codes(underlying: str='510050', call: bool=True) -> dict:
    """ETF期权合约清单。underlying: 510050/510300/588000/510500。call=True认购/False认沽。
    返回 {月份YYMM: [合约代码,...]}，第一个 key 即近月。"""
    _require_requests()
    cate = {'510050': '50ETF', '510300': '300ETF', '588000': '科创50ETF', '510500': '500ETF'}.get(underlying, '50ETF')
    url = f'https://stock.finance.sina.com.cn/futures/api/openapi.php/StockOptionService.getStockName?exchange=null&cate={cate}'
    try:
        months = requests.get(url, headers=SINA_OPT_HDR, timeout=10).json()['result']['data']['contractMonth']
    except Exception as e:
        print(f'[WARN] 期权月份获取失败: {e}')
        return {}
    months = [m.replace('-', '')[2:] for m in months[1:]]
    flag = 'OP_UP_' if call else 'OP_DOWN_'
    out = {}
    for m in months:
        codes = [c.replace('CON_OP_', '') for c in _sina_opt_list(f'{flag}{underlying}{m}') if c.startswith('CON_OP_')]
        if codes:
            out[m] = codes
    return out

def sina_option_tquote(code: str) -> dict:
    """期权T型报价。返回 bid_vol/bid/last/ask/ask_vol/open_interest(持仓量)/pct/
    strike(行权价)/prev_close/open/limit_up/limit_down/name/amplitude/high/low/volume/amount。"""
    v = _sina_opt_list(f'CON_OP_{code}')
    if len(v) < 43:
        return {}
    return {'bid_vol': _opt_f(v[0]), 'bid': _opt_f(v[1]), 'last': _opt_f(v[2]), 'ask': _opt_f(v[3]), 'ask_vol': _opt_f(v[4]), 'open_interest': _opt_f(v[5]), 'pct': _opt_f(v[6]), 'strike': _opt_f(v[7]), 'prev_close': _opt_f(v[8]), 'open': _opt_f(v[9]), 'limit_up': _opt_f(v[10]), 'limit_down': _opt_f(v[11]), 'name': v[37], 'amplitude': _opt_f(v[38]), 'high': _opt_f(v[39]), 'low': _opt_f(v[40]), 'volume': _opt_f(v[41]), 'amount': _opt_f(v[42])}

def sina_option_greeks(code: str) -> dict:
    """期权希腊字母 + 隐含波动率。返回 name/volume/delta/gamma/theta/vega/
    iv(隐含波动率,小数)/high/low/trade_code/strike/last/theory(理论价值)。"""
    raw = _sina_opt_list(f'CON_SO_{code}')
    if len(raw) < 16:
        return {}
    v = [raw[0]] + raw[4:]
    return {'name': v[0], 'volume': _opt_f(v[1]), 'delta': _opt_f(v[2]), 'gamma': _opt_f(v[3]), 'theta': _opt_f(v[4]), 'vega': _opt_f(v[5]), 'iv': _opt_f(v[6]), 'high': _opt_f(v[7]), 'low': _opt_f(v[8]), 'trade_code': v[9], 'strike': _opt_f(v[10]), 'last': _opt_f(v[11]), 'theory': _opt_f(v[12])}

def cninfo_irm(code: str, page_size: int=30, page_num: int=1) -> list[dict]:
    """互动易问答（深沪统一走巨潮）。code: 6位代码。
    返回每条: code/company/question(投资者提问)/answer(公司回复,None=未回复)/
    answerer(回答方)/ask_time。"""
    _require_requests()
    _require_pandas()
    try:
        r1 = requests.post('https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo', data={'keyWord': code}, headers={'User-Agent': UA}, timeout=10)
        d1 = r1.json().get('data') or []
        if not d1:
            return []
        org_id = d1[0].get('secid')
        params = {'_t': 1, 'stockcode': code, 'orgId': org_id, 'pageSize': page_size, 'pageNum': page_num, 'keyWord': '', 'startDay': '', 'endDay': ''}
        r2 = requests.post('https://irm.cninfo.com.cn/newircs/company/question', params=params, headers={'User-Agent': UA}, timeout=10)
        rows = r2.json().get('rows') or []
    except Exception as e:
        print(f'[WARN] 互动易请求失败: {e}')
        return []
    out = []
    for it in rows:
        pd = it.get('pubDate')
        out.append({'code': it.get('stockCode'), 'company': it.get('companyShortName'), 'question': it.get('mainContent'), 'answer': it.get('attachedContent'), 'answerer': it.get('attachedAuthor'), 'ask_time': datetime.fromtimestamp(pd / 1000).strftime('%Y-%m-%d %H:%M') if pd else ''})
    return out

def ths_hot_list(period: str='hour') -> list[dict]:
    """同花顺热榜（单接口拿名称+人气+概念标签+排名变化）。period: hour/day。
    返回每只: rank/code/name/heat(人气值)/pct/rank_chg(排名变化)/concepts(概念标签)/tag。"""
    _require_requests()
    try:
        r = requests.get('https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock', params={'stock_type': 'a', 'type': period, 'list_type': 'normal'}, headers={'User-Agent': UA}, timeout=10)
        lst = (r.json().get('data') or {}).get('stock_list') or []
    except Exception as e:
        print(f'[WARN] 同花顺热榜失败: {e}')
        return []
    out = []
    for it in lst:
        tag = it.get('tag') or {}
        out.append({'rank': it.get('order'), 'code': it.get('code'), 'name': it.get('name'), 'heat': it.get('rate'), 'pct': it.get('rise_and_fall'), 'rank_chg': it.get('hot_rank_chg'), 'concepts': tag.get('concept_tag') or [], 'tag': tag.get('popularity_tag', '')})
    return out

def em_hot_rank(top: int=50) -> list[dict]:
    """东财人气榜（排名 + 排名变化 + 名称/价格）。返回 rank/code/name/price/pct/rank_chg。"""
    _require_requests()
    try:
        r = requests.post('https://emappdata.eastmoney.com/stockrank/getAllCurrentList', json={**EM_HOT_BODY, 'marketType': '', 'pageNo': 1, 'pageSize': top}, headers={'User-Agent': UA}, timeout=10)
        data = r.json().get('data') or []
        if not data:
            return []
        secids = [('0.' if it['sc'].startswith('SZ') else '1.') + it['sc'][2:] for it in data]
        u = requests.get('https://push2.eastmoney.com/api/qt/ulist.np/get', params={'ut': 'f057cbcbce2a86e2866ab8877db1d059', 'fltt': 2, 'invt': 2, 'fields': 'f14,f3,f12,f2', 'secids': ','.join(secids)}, headers={'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/'}, timeout=10)
        diff = (u.json().get('data') or {}).get('diff') or []
        if isinstance(diff, dict):
            diff = list(diff.values())
        nm = {x['f12']: (x.get('f14'), x.get('f2'), x.get('f3')) for x in diff}
    except Exception as e:
        print(f'[WARN] 东财人气榜失败: {e}')
        return []
    out = []
    for it in data:
        code = it['sc'][2:]
        name, price, pct = nm.get(code, ('', None, None))
        out.append({'rank': it['rk'], 'code': code, 'name': name, 'price': price, 'pct': pct, 'rank_chg': it.get('hisRc')})
    return out

def em_hot_concept(code: str) -> list[dict]:
    """东财个股热门概念命中（这只票当下被市场归到哪些概念在炒）。
    返回 [{concept, bk, hit(命中热度)}, ...]，按热度降序。"""
    _require_requests()
    try:
        prefix = get_prefix(code).upper()
        r = requests.post('https://emappdata.eastmoney.com/stockrank/getHotStockRankList', json={**EM_HOT_BODY, 'srcSecurityCode': prefix + norm_ticker(code)}, headers={'User-Agent': UA}, timeout=10)
        data = r.json().get('data') or []
    except Exception as e:
        print(f'[WARN] 东财个股概念失败: {e}')
        return []
    return [{'concept': x.get('conceptName'), 'bk': x.get('conceptId'), 'hit': x.get('hitCount')} for x in data]

def forward_pe(price: float, eps_forecast: float) -> float:
    """前向PE = 当前股价 / 未来年度一致预期EPS"""
    if eps_forecast <= 0:
        return float('inf')
    return price / eps_forecast

def pe_digestion(current_pe: float, cagr: float, target_pe: float=30) -> float:
    """
    当前PE消化到目标PE需要多少年。
    target_pe 固定30x（A股成长股合理估值锚点）。
    cagr: 用 下一年EPS / 当年EPS - 1
    """
    if current_pe <= target_pe:
        return 0.0
    if cagr <= 0:
        return float('inf')
    return math.log(current_pe / target_pe) / math.log(1 + cagr)

def calc_peg(pe: float, cagr: float) -> float:
    """
    PEG = 前向PE / (CAGR * 100)
    PEG < 1   → 便宜
    PEG 1-1.5 → 合理
    PEG > 1.5 → 贵
    """
    if cagr <= 0:
        return float('inf')
    return pe / (cagr * 100)

def full_valuation(code: str) -> dict:
    """单票完整估值分析"""
    _require_pandas()
    prefix = 'bj' if code.startswith(('92', '8')) else 'sh' if code.startswith(('6', '9')) else 'sz'
    url = f'https://qt.gtimg.cn/q={prefix}{code}'
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode('gbk')
    vals = data.split('"')[1].split('~')
    price = float(vals[3])
    mcap = float(vals[44])
    pe_ttm = float(vals[39]) if vals[39] else 0
    pb = float(vals[46]) if vals[46] else 0
    df = ths_eps_forecast(code)
    eps_cur = eps_next = None
    analyst_count = 0
    if not df.empty and len(df.columns) >= 3:

        def _pick(row, name):
            for c in df.columns:
                if name in str(c):
                    return row.get(c)
            return None
        try:
            r0 = df.iloc[0]
            v = _pick(r0, '均值')
            eps_cur = float(v) if pd.notna(v) else None
            cnt = _pick(r0, '预测机构数')
            analyst_count = int(cnt) if pd.notna(cnt) else 0
            if len(df) >= 2:
                vn = _pick(df.iloc[1], '均值')
                eps_next = float(vn) if pd.notna(vn) else None
        except (ValueError, TypeError) as e:
            print(f'[WARN] full_valuation EPS 解析失败({e})，估值可能不完整')
    pe_fwd = price / eps_cur if eps_cur else float('inf')
    cagr = eps_next / eps_cur - 1 if eps_cur and eps_next else 0
    peg = pe_fwd / (cagr * 100) if cagr > 0 else float('inf')
    digest = math.log(pe_fwd / 30) / math.log(1 + cagr) if pe_fwd > 30 and cagr > 0 else 0
    return {'name': vals[1], 'price': price, 'mcap_yi': mcap, 'pe_ttm': pe_ttm, 'pb': pb, 'eps_cur': eps_cur, 'eps_next': eps_next, 'pe_fwd': round(pe_fwd, 1) if eps_cur else None, 'cagr_pct': round(cagr * 100, 0) if cagr else None, 'peg': round(peg, 2) if peg != float('inf') else None, 'digest_years': round(digest, 1), 'analyst_count': analyst_count}

def dragon_tiger_backup(trade_date: str) -> dict:
    """龙虎榜官方备用源（东财被封时用）：上交所+深交所官方，零鉴权权威一手，含营业部席位。"""
    out = {'date': trade_date, 'sse_raw': '', 'szse': []}
    su = f'https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1842_xxpl&TABKEY=tab1&txtStart={trade_date}&txtEnd={trade_date}&random=0.9'
    req = urllib.request.Request(su, headers={'User-Agent': UA, 'Referer': 'https://www.szse.cn/disclosure/supervision/dealinfo/index.html'})
    with urllib.request.urlopen(req, timeout=15, context=_ctx) as r:
        d = json.loads(r.read())
    for row in d[0].get('data', []):
        out['szse'].append({'code': row.get('zqdm'), 'name': row.get('zqjc'), 'amount': row.get('cjje'), 'reason': row.get('plyy')})
    eu = f'https://query.sse.com.cn/infodisplay/showTradePublicFile.do?jsonCallBack=cb&isPagination=false&dateTx={trade_date}'
    req = urllib.request.Request(eu, headers={'User-Agent': UA, 'Referer': 'https://www.sse.com.cn/disclosure/diclosure/public/'})
    with urllib.request.urlopen(req, timeout=15) as r:
        t = r.read().decode('utf-8', 'ignore')
    out['sse_raw'] = '\n'.join(json.loads(t[t.index('(') + 1:t.rindex(')')]).get('fileContents', []))
    return out

def fund_flow_backup(code: str, days: int=60) -> list:
    """个股资金流备用源（东财被封时用）：新浪，日度四档单净额。"""
    pre = ('bj' if code.startswith(('92', '8')) else 'sh' if code.startswith(('6', '9')) else 'sz') + code
    u = f'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs?page=1&num={days}&sort=opendate&asc=0&daima={pre}'
    req = urllib.request.Request(u, headers={'User-Agent': UA, 'Referer': 'https://finance.sina.com.cn/'})
    with urllib.request.urlopen(req, timeout=15) as r:
        t = r.read().decode('utf-8', 'ignore')
    arr = json.loads(t[t.index('['):t.rindex(']') + 1])
    return [{'date': x.get('opendate'), 'close': x.get('trade'), 'net_amount': x.get('netamount'), 'turnover': x.get('turnover')} for x in arr]

def announcements_backup(code: str, page_size: int=20) -> list:
    """公告备用源（巨潮被封时用）：深市走深交所官方，沪市走东财，均带 PDF 直链。"""
    if code.startswith(('0', '3')):
        body = json.dumps({'channelCode': ['listedNotice_disc'], 'pageSize': page_size, 'pageNum': 1, 'stock': [code]}).encode()
        req = urllib.request.Request('https://www.szse.cn/api/disc/announcement/annList', data=body, headers={'User-Agent': UA, 'Content-Type': 'application/json', 'Referer': 'https://www.szse.cn/disclosure/listed/notice/index.html'})
        with urllib.request.urlopen(req, timeout=15, context=_ctx) as r:
            d = json.loads(r.read())
        return [{'title': a.get('title'), 'time': a.get('publishTime', '')[:10], 'pdf': 'https://disc.static.szse.cn/download' + a.get('attachPath', '')} for a in d.get('data', [])]
    u = f'https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size={page_size}&page_index=1&ann_type=A&client_source=web&stock_list={code}&f_node=0&s_node=0'
    req = urllib.request.Request(u, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read())
    return [{'title': a.get('title'), 'time': a.get('notice_date', '')[:10], 'pdf': f"https://pdf.dfcfw.com/pdf/H2_{a.get('art_code', '')}_1.pdf"} for a in (d.get('data') or {}).get('list') or []]



def sina_adjust_factor(code: str, kind: str = 'qfq') -> list:
    """新浪复权因子序列；kind=qfq(前复权) 或 hfq(后复权)，最新在前。"""
    req = _require_requests()
    if kind not in ('qfq', 'hfq'):
        raise ValueError(f"kind 只能是 'qfq' 或 'hfq'，收到 {kind!r}")
    raw, digits = str(code).strip(), norm_ticker(code)
    explicit = re.match(r'^(sh|sz|bj)', raw, re.I) or re.search(r'\.(sh|sz|bj)$', raw, re.I)
    prefix = explicit.group(1).lower() if explicit else get_prefix(digits)
    symbol = f'{prefix}{digits}'
    response = req.get(f'https://finance.sina.com.cn/realstock/company/{symbol}/{kind}.js', headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}, timeout=10)
    response.raise_for_status()
    brace = response.text.find('{')
    if brace < 0:
        raise RuntimeError(f'新浪复权因子响应无 JSON（{symbol}/{kind}）: {response.text[:120]}')
    try:
        data, _ = json.JSONDecoder().raw_decode(response.text[brace:])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'新浪复权因子 JSON 解析失败（{symbol}/{kind}）: {exc}') from exc
    return [{'date': item['d'], 'factor': float(item['f'])} for item in data.get('data', [])]


def apply_adjust(bars, factors: list, kind: str = 'qfq', price_keys=('open', 'high', 'low', 'close')):
    """将新浪因子套到不复权 K 线；DataFrame 输入返回 DataFrame，list 输入返回 list。"""
    if kind not in ('qfq', 'hfq'):
        raise ValueError(f"kind 只能是 'qfq' 或 'hfq'，收到 {kind!r}")
    if not factors:
        raise ValueError('复权因子列表为空，无法复权；不要把未复权价当作复权价继续计算。')
    is_df = hasattr(bars, 'columns') and hasattr(bars, 'to_dict')
    date_col = None
    if is_df:
        date_col = next((c for c in ('date', 'datetime') if c in bars.columns), None)
        if date_col is None:
            raise ValueError(f'DataFrame 需含 date 或 datetime 列，实际列={list(bars.columns)}')
        rows = bars.to_dict('records')
        for row in rows: row['date'] = str(row[date_col])[:10]
    else:
        rows = [dict(bar) for bar in bars]
        for row in rows:
            if 'date' not in row: raise ValueError(f"每根 K 线需含 'date' 键，实际键={sorted(row)}")
            row['date'] = str(row['date'])[:10]
    fac = sorted(factors, key=lambda item: item['date'])
    out, index, current = [], 0, None
    for bar in sorted(rows, key=lambda item: item['date']):
        while index < len(fac) and fac[index]['date'] <= bar['date']:
            current = fac[index]['factor']; index += 1
        if current is None: raise RuntimeError(f"K 线日期 {bar['date']} 早于因子序列最早日 {fac[0]['date']}，无法复权")
        if current == 0: raise RuntimeError(f"复权因子为 0（{bar['date']}），无法换算")
        adjusted = dict(bar)
        for key in price_keys:
            if key in adjusted and adjusted[key] is not None:
                value = float(adjusted[key]); adjusted[key] = round(value / current if kind == 'qfq' else value * current, 4)
        adjusted['adj_factor'] = current; out.append(adjusted)
    if is_df:
        pandas = _require_pandas(); result = pandas.DataFrame(out)
        if getattr(bars, 'index', None) is not None and not isinstance(bars.index, pandas.RangeIndex):
            order = sorted(range(len(bars)), key=lambda n: str(bars.iloc[n][date_col])[:10])
            result.index = bars.index[order]; result.index.name = bars.index.name
        return result
    return out


def _triangular_weights(grid, low: float, high: float, avg: float):
    """当日筹码在价格网格上的三角分布权重。"""
    numpy = _require_numpy(); weights = numpy.zeros_like(grid)
    if not numpy.isfinite([low, high, avg]).all() or high < low: return weights
    if high - low < 1e-9:
        weights[numpy.argmin(numpy.abs(grid - low))] = 1.0; return weights
    avg = min(max(avg, low), high); left = (grid >= low) & (grid <= avg); right = (grid > avg) & (grid <= high)
    weights[left] = (grid[left] - low) / (avg - low) if avg - low > 1e-9 else 1.0
    weights[right] = (high - grid[right]) / (high - avg) if high - avg > 1e-9 else 1.0
    total = weights.sum()
    if total > 0: return weights / total
    weights[numpy.argmin(numpy.abs(grid - avg))] = 1.0; return weights


def chip_distribution(data, grid_size: int = 300, decay: float = 1.0) -> dict:
    """按 OHLC 与百分数换手率推演筹码分布；输入含 date/high/low/close/turn。"""
    numpy, pandas = _require_numpy(), _require_pandas()
    df = data.copy() if hasattr(data, 'columns') else pandas.DataFrame(data)
    need = {'date', 'high', 'low', 'close', 'turn'}; missing = need - set(df.columns)
    if missing: raise ValueError(f'chip_distribution 缺少列: {sorted(missing)}（date 用于强制时间升序）')
    data = df.dropna(subset=['high', 'low', 'close', 'turn']).copy(); data = data[data['high'] > 0]
    if data.empty: raise ValueError('chip_distribution: 有效行数为 0（检查是否全是停牌日，或字段类型不对）')
    data = data.sort_values('date').reset_index(drop=True); low, high = float(data['low'].min()), float(data['high'].max())
    pad = (high - low) * 0.02 or max(low * 0.02, 0.01); grid = numpy.linspace(low - pad, high + pad, grid_size); chips = None
    for row in data.itertuples(index=False):
        turnover = min(max(float(row.turn) / 100.0 * decay, 0.0), 1.0); avg = (float(row.high) + float(row.low) + float(row.close)) / 3.0
        weights = _triangular_weights(grid, float(row.low), float(row.high), avg)
        if weights.sum() <= 0: continue
        if chips is None: chips = weights.copy(); continue
        chips = chips * (1.0 - turnover) + weights * turnover
    if chips is None: raise RuntimeError('chip_distribution: 所有交易日的价格区间都无效，无法构建分布')
    total = chips.sum()
    if total <= 0: raise RuntimeError('chip_distribution: 筹码总量为 0，无法计算指标')
    chips = chips / total; price = float(data['close'].iloc[-1]); cumulative = numpy.cumsum(chips)
    price_at = lambda q: float(numpy.interp(q, cumulative, grid)); p05, p15, p85, p95 = (price_at(q) for q in (0.05, 0.15, 0.85, 0.95)); peak = int(numpy.argmax(chips))
    return {'price': price, 'profit_ratio': float(chips[grid <= price].sum()), 'avg_cost': float((grid * chips).sum()), 'cost_90': (p05, p95), 'cost_70': (p15, p85), 'concentration_90': float((p95-p05)/(p95+p05)) if p95+p05 else None, 'concentration_70': float((p85-p15)/(p85+p15)) if p85+p15 else None, 'peak_price': float(grid[peak]), 'histogram': [(float(pp), float(cc)) for pp, cc in zip(grid, chips) if cc > 1e-6]}


@contextmanager
def bs_session():
    """按需创建 baostock 登录会话，异常路径也保证 logout。"""
    bs = _require_baostock(); login = bs.login()
    if login.error_code != '0': raise RuntimeError(f'baostock 登录失败: {login.error_code} {login.error_msg}')
    try: yield bs
    finally: bs.logout()


def _rs_to_df(result) -> pd.DataFrame:
    """baostock ResultData 转 DataFrame；错误码转异常。"""
    pandas = _require_pandas()
    if result.error_code != '0': raise RuntimeError(f'baostock 查询失败: {result.error_code} {result.error_msg}')
    rows = []
    while result.next(): rows.append(result.get_row_data())
    return pandas.DataFrame(rows, columns=result.fields)


def _bs_code(code: str) -> str:
    """六位代码转 baostock 格式；不支持的市场在登录前拦截。"""
    digits = norm_ticker(code)
    if digits[:2] in ('60', '68', '90'): return f'sh.{digits}'
    if digits[:2] in ('00', '30', '20'): return f'sz.{digits}'
    raise ValueError(f'baostock 不支持该代码: {digits}（北交所 4/8/92/920 号段会被服务端拒绝）')


def baostock_valuation_history(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """日频估值历史：PE/PB/PS/PCF、换手率、停牌和 ST 状态。"""
    pandas = _require_pandas(); bs_code = _bs_code(code)
    fields = 'date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM,turn,tradestatus,isST'
    with bs_session() as bs:
        result = bs.query_history_k_data_plus(bs_code, fields, start_date=start_date, end_date=end_date, frequency='d', adjustflag='3')
        frame = _rs_to_df(result)
    for column in ('close', 'peTTM', 'pbMRQ', 'psTTM', 'pcfNcfTTM', 'turn'):
        frame[column] = pandas.to_numeric(frame[column], errors='coerce')
    return frame


def baostock_stock_basic(code: str) -> dict:
    """标的上市日、退市日和状态。"""
    bs_code = _bs_code(code)
    with bs_session() as bs: frame = _rs_to_df(bs.query_stock_basic(code=bs_code))
    return frame.iloc[0].to_dict() if not frame.empty else {}


SW_URL = 'https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls'


def sw_industry_history() -> pd.DataFrame:
    """申万行业归属变迁史；每只股票每次行业调整一行。"""
    req, pandas = _require_requests(), _require_pandas()
    try:
        response = req.get(SW_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60); response.raise_for_status()
    except req.exceptions.SSLError as exc:
        raise RuntimeError('申万站点 SSL 握手失败；请更新本机 CA/certifi 或检查中间人代理。') from exc
    frame = pandas.read_excel(io.BytesIO(response.content))
    frame = frame.rename(columns={'股票代码': 'code', '计入日期': 'start_date', '行业代码': 'industry_code', '更新日期': 'update_date'})
    missing = {'code', 'start_date', 'industry_code'} - set(frame.columns)
    if missing: raise RuntimeError(f'申万表结构变了，缺列 {sorted(missing)}；实际列={list(frame.columns)}')
    frame['code'] = frame['code'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(6)
    frame['industry_code'] = frame['industry_code'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(6)
    frame['l1_code'] = frame['industry_code'].str[:2] + '0000'; frame['l2_code'] = frame['industry_code'].str[:4] + '00'
    frame['start_date'] = pandas.to_datetime(frame['start_date'], errors='coerce')
    return frame.sort_values(['code', 'start_date']).reset_index(drop=True)


def sw_industry_as_of(data, code: str, as_of: str) -> Optional[dict]:
    """返回标的在指定日期所属申万行业，避免行业前视偏差。"""
    pandas = _require_pandas(); digits = norm_ticker(code)
    df = data.copy() if hasattr(data, 'columns') else pandas.DataFrame(data)
    if 'start_date' in df.columns:
        df['start_date'] = pandas.to_datetime(df['start_date'], errors='coerce')
    subset = df[(df['code'] == digits) & (df['start_date'] <= pandas.Timestamp(as_of))]
    if subset.empty: return None
    row = subset.iloc[-1]
    return {'code': digits, 'as_of': as_of, 'industry_code': row['industry_code'], 'l1_code': row['l1_code'], 'l2_code': row['l2_code'], 'since': row['start_date'].strftime('%Y-%m-%d')}

PBC_BASE = 'https://www.pbc.gov.cn'
PBC_INDEX = f'{PBC_BASE}/diaochatongjisi/116219/116319/index.html'
NBS_INDEX = 'https://www.stats.gov.cn/sj/zxfb/'
_MACRO_HEADERS = {'User-Agent': 'Mozilla/5.0'}


def _macro_get(url: str, timeout: int = 30) -> str:
    req = _require_requests()
    response = req.get(url, headers=_MACRO_HEADERS, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or 'utf-8'
    return response.text


def _abs_pbc(href: str) -> str:
    return urljoin(PBC_BASE + '/', href)


def _pbc_month_label(value) -> Optional[str]:
    """人民银行 Excel 月份：2026.01→01；被 Excel 吃尾零的 2026.1→10。"""
    match = re.match(r'^(\d{4})\.(\d{1,2})$', str(value).strip())
    if not match:
        return None
    year, month = match.groups()
    if len(month) == 1:
        month += '0'
    number = int(month)
    return f'{year}-{number:02d}' if 1 <= number <= 12 else None


def pboc_social_financing(year: Optional[int] = None) -> pd.DataFrame:
    """人民银行社会融资规模增量统计表；月度 12 列，单位亿元，支持 2021 年起。"""
    req, pandas = _require_requests(), _require_pandas()
    index_html = _macro_get(PBC_INDEX)
    years = re.findall(r'''href=["']([^"']+)["'][^>]*>\s*(\d{4})年统计数据\s*</a>''', index_html)
    if not years:
        raise RuntimeError('人民银行索引页未找到“XXXX年统计数据”链接，页面结构可能已变更')
    table = {int(item_year): href for href, item_year in years}
    target = max(table) if year is None else int(year)
    if target not in table:
        raise ValueError(f'人民银行无 {target} 年数据，可选年份: {sorted(table, reverse=True)[:8]}')
    year_html = _macro_get(_abs_pbc(table[target]))
    topics = re.findall(r'''href=["']([^"']+)["'][^>]*>\s*(社会融资规模)\s*</a>''', year_html)
    if not topics:
        raise RuntimeError(f'{target} 年页未找到“社会融资规模”专题链接')
    topic_html = _macro_get(_abs_pbc(topics[0][0]))
    books = re.findall(r'''href=["']([^"']+\.xlsx?)["']''', topic_html)
    if not books:
        raise RuntimeError(f'{target} 年社融专题页未找到 xls/xlsx 附件')
    response = req.get(_abs_pbc(books[0]), headers=_MACRO_HEADERS, timeout=60)
    response.raise_for_status()
    raw = pandas.read_excel(io.BytesIO(response.content), header=None)
    start = next((i for i in range(len(raw)) if str(raw.iloc[i, 0]).strip() == '月份'), None)
    if start is None:
        raise RuntimeError(f'{target} 年社融表没有独立“月份”表头；本端点仅支持 2021 年起的新格式')
    columns = ['month', 'afre_total', 'rmb_loans', 'fx_loans', 'entrusted_loans',
               'trust_loans', 'undiscounted_bankers_acceptance', 'corporate_bonds',
               'government_bonds', 'equity_financing', 'abs_by_depository', 'loans_written_off']
    frame = raw.iloc[start + 3:].copy().iloc[:, :len(columns)]
    frame.columns = columns
    frame = frame[frame['month'].astype(str).str.match(r'^\d{4}\.\d{1,2}$', na=False)].copy()
    for column in columns[1:]:
        frame[column] = pandas.to_numeric(frame[column], errors='coerce')
    frame['month'] = [_pbc_month_label(value) for value in frame['month']]
    frame = frame[frame['month'].notna()]
    frame = frame[frame['month'].str.startswith(f'{target}-')]
    frame = frame.dropna(subset=['afre_total']).reset_index(drop=True)
    if frame.empty:
        raise RuntimeError(f'社融表解析后无有效月份（{target} 年），格式可能已变更')
    return frame


def _parse_nbs_pmi_text(title: str, html: str, source_url: str) -> dict:
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.S)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[\s\u3000\xa0]+', '', text)
    def grab(pattern):
        match = re.search(pattern, text)
        return float(match.group(1)) if match else None
    year_month = re.search(r'(\d{4})年(\d{1,2})月', title)
    large = medium = small = None
    combined = re.search(r'大、中、小型企业PMI分别为([\d.]+)%、([\d.]+)%和([\d.]+)%', text)
    if combined:
        large, medium, small = (float(value) for value in combined.groups())
    else:
        medium_small = re.search(r'中、小型企业PMI分别为([\d.]+)%和([\d.]+)%', text)
        if medium_small:
            medium, small = (float(value) for value in medium_small.groups())
        for name, pattern in (('large', r'大型企业PMI为([\d.]+)%'),
                              ('medium', r'中型企业PMI为([\d.]+)%'),
                              ('small', r'小型企业PMI为([\d.]+)%')):
            match = re.search(pattern, text)
            if match:
                value = float(match.group(1))
                if name == 'large': large = value
                elif name == 'medium' and medium is None: medium = value
                elif name == 'small' and small is None: small = value
    result = {
        'title': title.strip(),
        'period': f'{year_month.group(1)}-{int(year_month.group(2)):02d}' if year_month else None,
        'manufacturing_pmi': grab(r'(?<!非)制造业采购经理指数（PMI）为([\d.]+)%'),
        'non_manufacturing_pmi': grab(r'非制造业商务活动指数为([\d.]+)%'),
        'composite_pmi': grab(r'综合PMI产出指数为([\d.]+)%'),
        'pmi_large': large, 'pmi_medium': medium, 'pmi_small': small,
        'source_url': source_url,
    }
    absent = [key for key in ('manufacturing_pmi', 'non_manufacturing_pmi', 'composite_pmi') if result[key] is None]
    if absent:
        raise RuntimeError(f'PMI 正文措辞可能已变更，无法解析 {absent}；请核对页面：{source_url}')
    return result


def nbs_pmi() -> dict:
    """国家统计局最新 PMI：制造业、非制造业、综合产出及大中小型企业。"""
    index_html = _macro_get(NBS_INDEX)
    links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]{6,80}?)\s*</a>', index_html)
    hit = next(((href, title) for href, title in links if '采购经理指数' in title), None)
    if not hit:
        raise RuntimeError('国家统计局最新发布页未找到“采购经理指数”条目')
    href, title = hit
    url = urljoin(NBS_INDEX, href)
    return _parse_nbs_pmi_text(title, _macro_get(url), url)



# v3.8.0 official index, calendar, margin, and BSE fallbacks
import calendar
import math
import re
from datetime import datetime, timezone
from io import BytesIO



def _official_code(value):
    value = str(value).strip()
    if not re.fullmatch(r"[0-9]{6}", value):
        raise ValueError("代码必须是 6 位纯数字；指数 provider 与证券交易所不是同一概念")
    return value


def _official_date(value):
    value = str(value).strip()
    fmt = "%Y%m%d" if re.fullmatch(r"[0-9]{8}", value) else "%Y-%m-%d"
    return datetime.strptime(value, fmt).date().isoformat()


def _official_number(value, required=False):
    if pd.isna(value) or str(value).strip() in ("", "-", "--"):
        if required:
            raise RuntimeError("官方源缺少必需数值")
        return None
    number = float(str(value).replace(",", ""))
    if not math.isfinite(number):
        raise RuntimeError("官方源返回非有限数值")
    return number


def _official_get(url, params=None, referer=None):
    response = requests.get(
        url, params=params,
        headers={"User-Agent": "Mozilla/5.0", "Referer": referer or url},
        timeout=(10, 40),
    )
    response.raise_for_status()
    return response


def _official_excel(response):
    try:
        frame = pd.read_excel(BytesIO(response.content), dtype=str)
    except (ValueError, OSError) as exc:
        raise RuntimeError("官方源未返回可解析的 Excel；可能未发布或响应结构改变") from exc
    # 两种中证文件的表头空格略有差异，按完整列名去空白后匹配。
    frame.columns = [re.sub(r"\s+", "", str(c)) for c in frame.columns]
    return frame


def _official_columns(frame, names):
    missing = set(names) - set(frame.columns)
    if missing:
        raise RuntimeError("官方数据列缺失: " + ", ".join(sorted(missing)))


def _official_frame(rows, keys, source, url):
    frame = pd.DataFrame(rows)
    if frame.empty or frame.duplicated(keys).any():
        raise RuntimeError("官方数据为空或主键重复，不能当成完整快照")
    frame["source"] = source
    frame["source_url"] = url
    frame["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return frame.sort_values(keys).reset_index(drop=True)


def _official_index_members(index_code, provider, weights):
    index_code = _official_code(index_code)
    if provider not in ("csi", "cni"):
        raise ValueError("provider 必须是 csi（中证）或 cni（国证）")
    if provider == "csi":
        kind = "closeweight" if weights else "cons"
        url = ("https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/"
               f"autofile/{kind}/{index_code}{kind}.xls")
        response = _official_get(url)
        data = _official_excel(response)
        cols = ["日期Date", "指数代码IndexCode", "成份券代码ConstituentCode",
                "成份券名称ConstituentName", "交易所Exchange"]
        if weights:
            cols.append("权重(%)weight")
    else:
        url = "https://www.cnindex.com.cn/sample-detail/download-history"
        response = _official_get(url, {"indexcode": index_code})
        data = _official_excel(response)
        cols = ["日期", "样本代码", "样本简称", "权重（%）"]
    _official_columns(data, cols)
    rows = []
    for rec in data.to_dict("records"):
        if provider == "csi":
            if str(rec["指数代码IndexCode"]).zfill(6) != index_code:
                raise RuntimeError("中证返回了不同指数的数据")
            code = str(rec["成份券代码ConstituentCode"]).zfill(6)
            exchanges = {"上海证券交易所": "SH", "深圳证券交易所": "SZ", "北京证券交易所": "BJ"}
            exchange = exchanges.get(rec["交易所Exchange"])
            if exchange is None:
                raise ValueError("本端点仅支持沪深北成分，请使用相应市场的数据工具")
            row = {"date": _official_date(rec["日期Date"]), "index_code": index_code,
                   "code": _official_code(code), "name": rec["成份券名称ConstituentName"],
                   "exchange": exchange}
            weight = rec.get("权重(%)weight")
        else:
            # 国证没有交易所列；A 股文件保留六位文本。港股 00700 不能补成 000700/SZ。
            code = _official_code(rec["样本代码"])
            exchange = ("SH" if code.startswith("6") else "SZ" if code.startswith(("0", "3"))
                        else "BJ" if code.startswith(("4", "8", "92")) else None)
            if exchange is None:
                raise ValueError("国证该指数包含本端点不支持的证券类型")
            row = {"date": _official_date(rec["日期"]), "index_code": index_code,
                   "code": code, "name": rec["样本简称"], "exchange": exchange}
            weight = rec["权重（%）"]
        if weights:
            row["weight_percent"] = _official_number(weight, required=True)
        rows.append(row)
    frame = _official_frame(rows, ["date", "code", "exchange"], provider, response.url)
    if frame["date"].nunique() != 1:
        raise RuntimeError("成分文件混有多个日期，不能当作单日快照")
    if weights and (not frame.weight_percent.between(0, 100).all()
                    or not 99 <= frame.weight_percent.sum() <= 101):
        raise RuntimeError("权重范围或合计异常；可能文件残缺或不是百分数口径")
    return frame


def index_constituents(index_code, provider="csi"):
    """最近公布的沪深北成分；date 是源文件日期，不是抓取日。"""
    return _official_index_members(index_code, provider, weights=False)


def index_weights(index_code, provider="csi"):
    """最近公布的指数权重，weight_percent 单位为百分数。"""
    return _official_index_members(index_code, provider, weights=True)


def index_valuation(index_code):
    """中证近期 PE/股息率文件；不含 PB，两种股本口径不混用。"""
    index_code = _official_code(index_code)
    url = ("https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/"
           f"autofile/indicator/{index_code}indicator.xls")
    response = _official_get(url)
    data = _official_excel(response)
    mapping = {"市盈率1（总股本）P/E1": "pe_total",
               "市盈率2（计算用股本）P/E2": "pe_calculation",
               "股息率1（总股本）D/P1": "dividend_yield_total_percent",
               "股息率2（计算用股本）D/P2": "dividend_yield_calculation_percent"}
    _official_columns(data, ["日期Date", "指数代码IndexCode", *mapping])
    rows = []
    for rec in data.to_dict("records"):
        if str(rec["指数代码IndexCode"]).zfill(6) != index_code:
            raise RuntimeError("中证估值文件返回了不同指数")
        rows.append({"date": _official_date(rec["日期Date"]), "index_code": index_code,
                     **{dest: _official_number(rec[src]) for src, dest in mapping.items()}})
    return _official_frame(rows, ["date", "index_code"], "csi", response.url)


def trading_calendar(year, month):
    """深交所完整自然月日历。未发布或缺日抛错，周末调休不视为交易日。"""
    if type(year) is not int or type(month) is not int or not 1 <= month <= 12:
        raise ValueError("year/month 必须为整数，month 在 1–12 之间")
    last = calendar.monthrange(year, month)[1]
    expected = {datetime(year, month, day).date().isoformat() for day in range(1, last + 1)}
    url = "https://www.szse.cn/api/report/exchange/onepersistenthour/monthList"
    response = _official_get(url, {"month": f"{year}-{month}"})
    data = response.json().get("data")
    if not isinstance(data, list) or not data:
        raise RuntimeError("深交所尚未返回该月日历；不能推断全月休市")
    rows = []
    for rec in data:
        if str(rec.get("jybz")) not in ("0", "1") or not rec.get("jyrq"):
            raise RuntimeError("深交所日历字段异常")
        rows.append({"date": _official_date(rec["jyrq"]), "is_open": str(rec["jybz"]) == "1"})
    frame = _official_frame(rows, ["date"], "szse", response.url)
    if set(frame.date) != expected:
        raise RuntimeError("日历月份错位或日期不完整，不能继续调度")
    return frame

import json
import time


def _official_total(value):
    if not re.fullmatch(r"[0-9]+", str(value)):
        raise RuntimeError("官方分页总数必须为非负整数")
    return int(value)


def _official_margin_code(value, exchange):
    code = _official_code(value)
    prefixes = ("5", "6", "900") if exchange == "SH" else ("0", "1", "2", "3")
    if not code.startswith(prefixes):
        raise ValueError("两融证券代码与请求的交易所不符")
    return code


def margin_trading_backup(trade_date, exchange, code=None):
    """一次只取一个交易所。未发布抛错；完整源中筛不到 code 才返回空表。"""
    trade_date = _official_date(trade_date)
    exchange = str(exchange).upper()
    if exchange not in ("SH", "SZ"):
        raise ValueError("exchange 必须为 SH 或 SZ；本函数不覆盖北交所两融")
    if code is not None:
        code = _official_margin_code(code, exchange)
    if exchange == "SH":
        url = "https://query.sse.com.cn/marketdata/tradedata/queryMargin.do"
        response = _official_get(url, {
            "isPagination": "true", "tabType": "mxtype", "detailsDate": trade_date.replace("-", ""),
            "pageHelp.pageSize": 5000, "pageHelp.pageNo": 1, "pageHelp.beginPage": 1,
            "pageHelp.cacheSize": 1, "pageHelp.endPage": 1,
        }, "https://www.sse.com.cn/")
        page = response.json().get("pageHelp") or {}
        data = page.get("data")
        if not isinstance(data, list) or not data or len(data) != _official_total(page.get("total")):
            raise RuntimeError("上交所该日数据未发布或分页不完整")
        fields = {"rzye": "margin_balance", "rzmre": "margin_buy", "rqylje": "short_balance",
                  "rqyl": "short_volume", "rqmcl": "short_sell_volume"}
        rows = []
        for rec in data:
            if _official_date(rec.get("opDate")) != trade_date:
                raise RuntimeError("上交所两融数据日期不符")
            if not set(fields).issubset(rec):
                raise RuntimeError("上交所两融字段发生变化")
            rows.append({"date": trade_date, "code": _official_margin_code(rec["stockCode"], exchange),
                         "name": rec.get("securityAbbr"), "exchange": exchange,
                         **{dest: _official_number(rec[src], required=(src != "rqylje"))
                            for src, dest in fields.items()}})
    else:
        url = "https://www.szse.cn/api/report/ShowReport"
        response = _official_get(url, {"SHOWTYPE": "xlsx", "CATALOGID": "1837_xxpl",
                                      "TABKEY": "tab2", "txtDate": trade_date}, "https://www.szse.cn/")
        data = _official_excel(response)
        fields = {"融资余额(元)": "margin_balance", "融资买入额(元)": "margin_buy",
                  "融券余额(元)": "short_balance", "融券余量(股/份)": "short_volume",
                  "融券卖出量(股/份)": "short_sell_volume"}
        _official_columns(data, ["证券代码", "证券简称", *fields])
        rows = [{"date": trade_date, "code": _official_margin_code(str(rec["证券代码"]).zfill(6), exchange),
                 "name": rec["证券简称"], "exchange": exchange,
                 **{dest: _official_number(rec[src], required=True) for src, dest in fields.items()}}
                for rec in data.to_dict("records")]
    frame = _official_frame(rows, ["date", "code"], "sse" if exchange == "SH" else "szse", response.url)
    return frame if code is None else frame.loc[frame.code == code].reset_index(drop=True)


def bse_quote_backup(trade_date, code=None):
    """北交所当前全板/单票快照；拒绝用当前数据回填其他交易日。"""
    trade_date = _official_date(trade_date)
    if code is not None:
        code = _official_code(code)
        if not code.startswith(("4", "8", "92")):
            raise ValueError("请输入北交所代码（4/8/92 开头）")
    page_url = "https://www.bse.cn/nq/quotation.html"
    url = "https://www.bse.cn/nqhqController/nqhq_en.do"
    raw_rows = []
    total = None
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": page_url,
                                "Accept": "application/json, text/javascript, */*; q=0.01"})
        # 官网有时设置匿名 Cookie 后 302 回自己；不跟随重定向，避免循环。
        session.get(page_url, timeout=(10, 40), allow_redirects=False).raise_for_status()
        for page_number in range(100):
            form = {"page": page_number, "type_en": '["B"]', "sortfield": "hqzqdm",
                    "sorttype": "asc", "xxfcbj_en": "[2]", "zqdm": code or ""}
            response = session.post(url, data=form, timeout=(10, 40), allow_redirects=False)
            if 300 <= response.status_code < 400:
                session.get(page_url, timeout=(10, 40), allow_redirects=False).raise_for_status()
                response = session.post(url, data=form, timeout=(10, 40), allow_redirects=False)
            response.raise_for_status()
            if response.status_code != 200:
                raise RuntimeError("北交所匿名会话尚未建立")
            payload = response.text.strip()
            match = re.fullmatch(r"[A-Za-z_$][\w$]*\((.*)\);?", payload, re.S)
            data = json.loads(match.group(1) if match else payload)
            if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0].get("content"), list):
                raise RuntimeError("北交所行情响应结构异常")
            current_total = _official_total(data[0].get("totalElements"))
            if total is not None and total != current_total:
                raise RuntimeError("分页期间北交所记录总数变化，请重试")
            total = current_total
            batch = data[0]["content"]
            if total < 0 or not batch:
                raise RuntimeError("北交所未返回目标行情或分页提前结束")
            raw_rows.extend(batch)
            if len(raw_rows) >= total:
                break
            time.sleep(0.2)
        if len(raw_rows) != total:
            raise RuntimeError("北交所分页不完整，不能标记全板成功")
    fields = {"hqjrkp": "open", "hqzgcj": "high", "hqzdcj": "low", "hqzjcj": "close",
              "hqzrsp": "previous_close", "hqcjsl": "volume", "hqcjje": "amount"}
    rows = []
    for rec in raw_rows:
        if _official_date(rec.get("hqjsrq")) != trade_date:
            raise RuntimeError("北交所快照不是请求的交易日；本接口不提供历史回填")
        ticker = _official_code(rec.get("hqzqdm"))
        if not ticker.startswith(("4", "8", "92")) or (code is not None and ticker != code):
            raise RuntimeError("北交所返回了请求范围之外的标的")
        row = {"date": trade_date, "code": ticker, "name": rec.get("hqzqjc"), "exchange": "BJ",
               "quote_time": str(rec.get("hqgxsj", "")), "pe_source": _official_number(rec.get("hqsyl1")),
               **{dest: _official_number(rec.get(src), required=True) for src, dest in fields.items()}}
        for level in range(1, 6):
            for src, dest in (("hqbjw", "bid_price"), ("hqbsl", "bid_volume"),
                              ("hqsjw", "ask_price"), ("hqssl", "ask_volume")):
                row[f"{dest}_{level}"] = _official_number(rec.get(f"{src}{level}"), required=True)
        rows.append(row)
    return _official_frame(rows, ["date", "code"], "bse", url)

def _to_jsonable(value: Any) -> Any:
    """Convert common endpoint return types to JSON-friendly objects."""
    try:
        import pandas as pd  # type: ignore
        if isinstance(value, pd.DataFrame):
            return value.where(pd.notnull(value), None).to_dict(orient="records")
        if isinstance(value, pd.Series):
            return value.where(pd.notnull(value), None).to_dict()
    except Exception:
        pass
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _endpoint_registry() -> dict[str, Any]:
    hidden = {"Any", "main"}
    registry = {}
    for name, value in globals().items():
        if name.startswith("_") or name in hidden:
            continue
        if callable(value) and getattr(value, "__module__", None) == __name__:
            registry[name] = value
    return dict(sorted(registry.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A-stock data client: direct endpoints extracted from a-stock-data SKILL.md")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List available endpoint functions")

    call_p = sub.add_parser("call", help="Call an endpoint by function name")
    call_p.add_argument("function", help="Function name, e.g. tencent_quote")
    call_p.add_argument("--args", default="[]", help="JSON array positional args")
    call_p.add_argument("--kwargs", default="{}", help="JSON object keyword args")
    call_p.add_argument("--indent", type=int, default=2, help="JSON indent; use 0 for compact output")

    ns = parser.parse_args(argv)
    registry = _endpoint_registry()

    if ns.command == "list":
        for name, func in registry.items():
            doc = (getattr(func, "__doc__", "") or "").strip().splitlines()
            summary = doc[0].strip() if doc else ""
            print(f"{name}\t{summary}")
        return 0

    if ns.command == "call":
        if ns.function not in registry:
            print(f"Unknown function: {ns.function}", file=sys.stderr)
            print("Use `list` to see available endpoints.", file=sys.stderr)
            return 2
        try:
            args = json.loads(ns.args)
            kwargs = json.loads(ns.kwargs)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON arguments: {exc}", file=sys.stderr)
            return 2
        if not isinstance(args, list):
            print("--args must be a JSON array", file=sys.stderr)
            return 2
        if not isinstance(kwargs, dict):
            print("--kwargs must be a JSON object", file=sys.stderr)
            return 2
        result = registry[ns.function](*args, **kwargs)
        indent = None if ns.indent == 0 else ns.indent
        print(json.dumps(_to_jsonable(result), ensure_ascii=False, indent=indent))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
