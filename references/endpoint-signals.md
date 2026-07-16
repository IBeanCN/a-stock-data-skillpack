# 信号端点

| 端点 | 数据 | 数据源 |
|---|---|---|
| `ths_hot_reason(date=None)` | 当日强势股、题材归因 | 同花顺 |
| `hsgt_realtime()` | 沪深股通分钟流向 | 同花顺 |
| `_load_northbound_history(n=20)` | 北向本地自缓存历史 | 本地 CSV |
| `eastmoney_concept_blocks(code)` | 个股行业/概念/地域归属 | 东财 slist |
| `eastmoney_fund_flow_minute(code)` | 个股分钟资金流 | 东财 push2 |
| `dragon_tiger_board(code, date)` | 个股龙虎榜和席位 | 东财 datacenter |
| `daily_dragon_tiger(date)` | 全市场龙虎榜 | 东财 datacenter |
| `lockup_expiry(code, date)` | 限售解禁 | 东财 datacenter |
| `industry_comparison()` | 行业涨跌排名 | 东财 clist |

## 北向 caveat

深股通分钟序列在披露收紧后不可靠，仅供参考；权威北向应使用 HKEX 日统计。

## 资金流 caveat

分钟资金流、120 日资金流、备用新浪资金流不是同一口径，不要混算。
