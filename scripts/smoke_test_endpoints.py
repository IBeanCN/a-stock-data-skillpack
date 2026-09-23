"""a-stock-data 端点迁移 smoke test。

默认只做导入、函数存在性和无网络公式校验。传入 --network 后执行少量真实 API
best-effort 探测：函数抛异常记为 WARN，返回空但无异常记为 OK，避免单个外部源波动阻断整体验证。
"""

from __future__ import annotations

import argparse
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIENT = ROOT / "a_stock_client.py"

REQUIRED_FUNCTIONS = [
    "normalize_code",
    "norm_ticker",
    "get_prefix",
    "em_market_code",
    "em_secid",
    "tdx_client",
    "em_get",
    "eastmoney_datacenter",
    "tencent_quote",
    "baidu_kline_with_ma",
    "eastmoney_reports",
    "eastmoney_industry_reports",
    "download_pdf",
    "ths_eps_forecast",
    "iwencai_search",
    "iwencai_query",
    "dedup_articles",
    "ths_hot_reason",
    "hsgt_realtime",
    "eastmoney_concept_blocks",
    "eastmoney_fund_flow_minute",
    "dragon_tiger_board",
    "lockup_expiry",
    "industry_comparison",
    "board_fund_flow",
    "daily_dragon_tiger",
    "margin_trading",
    "block_trade",
    "holder_num_change",
    "dividend_history",
    "stock_fund_flow_120d",
    "eastmoney_stock_news",
    "cls_telegraph",
    "eastmoney_global_news",
    "eastmoney_stock_info",
    "sina_financial_report",
    "cninfo_announcements",
    "em_zt_pool",
    "em_zb_pool",
    "em_dt_pool",
    "em_yzt_pool",
    "ths_limit_up_pool",
    "limit_up_sentiment",
    "em_stock_monitor",
    "em_price_anomaly",
    "em_price_anomaly_count",
    "sina_option_codes",
    "sina_option_tquote",
    "sina_option_greeks",
    "cninfo_irm",
    "ths_hot_list",
    "em_hot_rank",
    "em_hot_concept",
    "forward_pe",
    "pe_digestion",
    "calc_peg",
    "full_valuation",
    "dragon_tiger_backup",
    "fund_flow_backup",
    "announcements_backup",
    "sina_adjust_factor",
    "apply_adjust",
    "chip_distribution",
    "baostock_valuation_history",
    "baostock_stock_basic",
    "sw_industry_history",
    "sw_industry_as_of",
    "pboc_social_financing",
    "nbs_pmi",
    "tencent_kline",
    "tdx_daily_package",
    "tencent_ticks",
    "sina_research_reports",
    "etf_shares",
    "wallstreetcn_lives",
    "cctv_news",
    "st_stock_list",
    "sse_e_interaction",
    "chinabond_yield_curve",
    "repo_fixing_rates",
    "lpr_history",
    "macro_calendar",
    "futures_daily",
    "options_daily",
    "futures_position_rank",
    "futures_realtime",
    "futures_kline",
    "a50_futures",
    "sge_spot",
    "earnings_forecast",
    "institution_survey",
    "holder_trades",
    "share_buyback",
    "equity_pledge",
    "ipo_calendar",
    "convertible_bonds",
    "to_joinquant",
]


def load_client():
    spec = importlib.util.spec_from_file_location("a_stock_client", CLIENT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", action="store_true", help="执行少量真实网络端点检查")
    args = parser.parse_args()

    client = load_client()
    missing = [name for name in REQUIRED_FUNCTIONS if not callable(getattr(client, name, None))]
    if missing:
        print("FAIL 缺失函数:", ", ".join(missing))
        return 1
    print(f"OK 函数清单完整: {len(REQUIRED_FUNCTIONS)}")

    assert client.normalize_code("SH688017") == "688017"
    assert client.normalize_code("688017.SH") == "688017"
    assert client.normalize_code("BJ920982") == "920982"
    for invalid_code in ("SZ600519", "BJ000001", "SH000001.SZ"):
        try:
            client.normalize_code(invalid_code)
        except ValueError:
            pass
        else:
            raise AssertionError(f"ticker 严格校验失效: {invalid_code}")
    try:
        client.normalize_code("SH000001", stock_only=True)
    except ValueError:
        pass
    else:
        raise AssertionError("个股接口未拒绝显式沪市 000xxx 指数")
    assert client.get_prefix("SH688017") == "sh"
    assert client.get_prefix("510300") == "sh"
    assert client.get_prefix("000300") == "sh"
    assert client.get_prefix("920002") == "bj"
    assert client.get_prefix("400001") == "bj"
    assert client.get_prefix("000001") == "sz"
    assert client.get_prefix("000016.SH") == "sh"
    assert client.get_prefix("000016.SZ") == "sz"
    assert client.get_prefix("920982.BJ") == "bj"
    assert client.em_secid("000016.SH") == "1.000016"
    adjusted_qfq = client.apply_adjust(
        [{"date": "2020-01-01", "open": 20, "high": 22, "low": 18, "close": 20}],
        [{"date": "1900-01-01", "factor": 2}], "qfq")
    adjusted_hfq = client.apply_adjust(
        [{"date": "2020-01-01", "open": 20, "high": 22, "low": 18, "close": 20}],
        [{"date": "1900-01-01", "factor": 2}], "hfq")
    assert adjusted_qfq[0]["close"] == 10 and adjusted_hfq[0]["close"] == 40
    try:
        client.apply_adjust([{"date": "2020-01-01", "close": 20}], [], "qfq")
    except ValueError:
        pass
    else:
        raise AssertionError("apply_adjust 未拒绝空因子")
    chips = client.chip_distribution([
        {"date": "2020-01-01", "high": 10, "low": 10, "close": 10, "turn": 1},
        {"date": "2020-01-02", "high": 100, "low": 100, "close": 100, "turn": 1},
    ])
    assert chips["avg_cost"] < 20, chips
    assert client._pbc_month_label("2026.01") == "2026-01"
    assert client._pbc_month_label("2026.1") == "2026-10"
    pmi = client._parse_nbs_pmi_text(
        "2026年7月采购经理指数",
        "制造业采购经理指数（ PMI ）为49.2% 非制造业商务活动指数为49.0% "
        "综合PMI产出指数为49.3% 大、中、小型企业PMI分别为49.5%、49.7%和47.4%",
        "https://example.invalid/pmi")
    assert (pmi["manufacturing_pmi"], pmi["pmi_small"]) == (49.2, 47.4)
    try:
        client._bs_code("920982")
    except ValueError:
        pass
    else:
        raise AssertionError("baostock 未在登录前拒绝北交所")
    for invalid_args in (("unknown", "today", 20), ("industry", "3d", 20)):
        try:
            client.board_fund_flow(*invalid_args)
        except ValueError:
            pass
        else:
            raise AssertionError(f"board_fund_flow 参数校验失效: {invalid_args}")
    assert client.forward_pe(20, 2) == 10
    assert client.calc_peg(30, 0.3) == 1
    original_datacenter = client.eastmoney_datacenter
    client.eastmoney_datacenter = lambda *args, **kwargs: []
    try:
        empty_lhb = client.dragon_tiger_board("600519", "2026-08-09")
    finally:
        client.eastmoney_datacenter = original_datacenter
    assert empty_lhb == {
        "records": [],
        "seats": {"buy": [], "sell": []},
        "institution": {"buy_amt": 0.0, "sell_amt": 0.0, "net_amt": 0.0},
    }
    # ── 上游 v3.9.0 / v3.10.0 同步：聚宽代码（#55）、tdx 验活分流（#52）、新端点参数契约 ──
    assert client.to_joinquant("sh000001") == "000001.XSHG"
    assert client.to_joinquant("000001") == "000001.XSHE"
    assert client.to_joinquant("600519") == "600519.XSHG"
    try:
        client.to_joinquant("920982")
    except ValueError:
        pass
    else:
        raise AssertionError("to_joinquant 未拒绝北交所（聚宽无北交所后缀）")
    assert client.normalize_code("600519.XSHG") == "600519"
    assert client.normalize_code("000001.XSHE") == "000001"
    for invalid_jq in ("600519.XSHE", "SH600519.XSHG"):
        try:
            client.normalize_code(invalid_jq)
        except ValueError:
            pass
        else:
            raise AssertionError(f"聚宽后缀校验失效: {invalid_jq}")
    assert client.get_prefix("000001.XSHG") == "sh"
    assert client.get_prefix("000001.XSHE") == "sz"
    assert client.sina_adjust_factor.__doc__
    try:
        client.tdx_client("std", "bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("tdx_client 未拒绝非法 check（#52 验活分流）")
    assert client._v39_num("1,234.50") == 1234.5
    assert client._v39_num("--") is None
    try:
        client._v39_num(True)
    except RuntimeError:
        pass
    else:
        raise AssertionError("_v39_num 未拒绝布尔值")
    try:
        client.macro_calendar("2026-01-01", "2026-06-01")
    except ValueError:
        pass
    else:
        raise AssertionError("macro_calendar 未拒绝超过 92 天的区间")
    try:
        client.macro_calendar("2026-09-14", "2026-09-20", min_importance=9)
    except ValueError:
        pass
    else:
        raise AssertionError("macro_calendar 未拒绝非法 min_importance")
    try:
        client.futures_realtime([])
    except ValueError:
        pass
    else:
        raise AssertionError("futures_realtime 未拒绝空列表")
    try:
        client.equity_pledge(code="600519", date="2026-09-18")
    except ValueError:
        pass
    else:
        raise AssertionError("equity_pledge 未拒绝 code 与 date 同时给")
    try:
        client.equity_pledge(code="920982")
    except ValueError:
        pass
    else:
        raise AssertionError("equity_pledge 未拒绝北交所（中国结算只覆盖沪深）")
    try:
        client.futures_kline("RB")
    except ValueError:
        pass
    else:
        raise AssertionError("futures_kline 未拒绝非法合约代码")
    try:
        client.tencent_kline("920982")
    except ValueError:
        pass
    else:
        raise AssertionError("tencent_kline 未拒绝北交所")
    try:
        client.tencent_ticks("sh000001")
    except ValueError:
        pass
    else:
        raise AssertionError("tencent_ticks 未拒绝指数")
    _sse_now = datetime(2026, 9, 23, 10, 0)
    assert client._sse_time("2026年09月21日 11:02", _sse_now) == "2026-09-21 11:02"
    assert client._sse_time("昨天 10:35", _sse_now) == "2026-09-22 10:35"
    assert client._sse_time("今天 09:00", _sse_now) == "2026-09-23 09:00"
    assert client._sse_time("25分钟前", _sse_now) == "2026-09-23 09:35"
    assert client._sse_time("3小时前", _sse_now) == "2026-09-23 07:00"
    assert client._sse_time("前天 09:00", _sse_now) is None
    print("OK 无网络基础校验通过")

    if args.network:
        today_dash = datetime.now().strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y%m%d")
        checks = [
            ("腾讯行情", lambda: client.tencent_quote(["600519"])),
            ("百度K线", lambda: client.baidu_kline_with_ma("600519")),
            ("东财研报", lambda: client.eastmoney_reports("600519", max_pages=1)),
            ("同花顺热点", lambda: client.ths_hot_reason()),
            ("东财板块归属", lambda: client.eastmoney_concept_blocks("600519")),
            ("龙虎榜席位", lambda: client.dragon_tiger_board("600519", today_dash)),
            ("全市场龙虎榜", lambda: client.daily_dragon_tiger(today_dash)),
            ("个股新闻", lambda: client.eastmoney_stock_news("600519", page_size=3)),
            ("全球资讯", lambda: client.eastmoney_global_news(page_size=3)),
            ("东财个股信息", lambda: client.eastmoney_stock_info("600519")),
            ("巨潮公告", lambda: client.cninfo_announcements("600519", page_size=3)),
            ("涨停池", lambda: client.em_zt_pool(today)),
            ("重点监控池", lambda: client.em_stock_monitor()),
            ("日内异动池", lambda: client.em_price_anomaly(page_size=20)),
            ("腾讯K线", lambda: client.tencent_kline("600519", count=20)),
            ("腾讯逐笔", lambda: client.tencent_ticks("600519")),
            ("新浪研报", lambda: client.sina_research_reports("600519")),
            ("华尔街见闻快讯", lambda: client.wallstreetcn_lives(limit=5)),
            ("央视新闻联播", lambda: client.cctv_news((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"), with_content=False)),
            ("ST名单", lambda: client.st_stock_list()),
            ("上证e互动", lambda: client.sse_e_interaction("600000")),
            ("LPR", lambda: client.lpr_history()),
            ("回购定盘利率", lambda: client.repo_fixing_rates("FR")),
            ("中债收益率曲线", lambda: client.chinabond_yield_curve((datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d"))),
            ("期货实时", lambda: client.futures_realtime(["RB0", "M0"])),
            ("期货日K", lambda: client.futures_kline("RB0", start=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"))),
            ("A50期货", lambda: client.a50_futures()),
            ("上金所现货", lambda: client.sge_spot("Au99.99")),
            ("可转债", lambda: client.convertible_bonds()),
            ("ETF份额", lambda: client.etf_shares((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"), "SH")),
            ("ETF期权代码", lambda: client.sina_option_codes("510050")),
        ]
        ok = warn = 0
        for name, fn in checks:
            try:
                result = fn()
                size = len(result) if hasattr(result, "__len__") else 1
                print(f"OK {name}: size={size}")
                ok += 1
            except Exception as exc:
                print(f"WARN {name}: {type(exc).__name__}: {str(exc)[:160]}")
                warn += 1
        print(f"网络验证完成: OK={ok}, WARN={warn}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
