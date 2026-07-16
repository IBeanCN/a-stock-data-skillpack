"""a-stock-data 端点迁移 smoke test。

默认只做导入、函数存在性和无网络公式校验。传入 --network 后执行少量真实 API
best-effort 探测：函数抛异常记为 WARN，返回空但无异常记为 OK，避免单个外部源波动阻断整体验证。
"""

from __future__ import annotations

import argparse
import importlib.util
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIENT = ROOT / "a_stock_client.py"

REQUIRED_FUNCTIONS = [
    "normalize_code",
    "get_prefix",
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
    assert client.get_prefix("SH688017") == "sh"
    assert client.forward_pe(20, 2) == 10
    assert client.calc_peg(30, 0.3) == 1
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
