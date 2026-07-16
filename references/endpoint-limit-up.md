# 打板端点

| 端点 | 数据 | 数据源 |
|---|---|---|
| `em_zt_pool(date)` | 涨停池 | 东财 push2ex |
| `em_zb_pool(date)` | 炸板池 | 东财 push2ex |
| `em_dt_pool(date)` | 跌停池 | 东财 push2ex |
| `em_yzt_pool(date)` | 昨日涨停今日表现 | 东财 push2ex |
| `ths_limit_up_pool(date)` | 涨停原因、题材、封板质量 | 同花顺 |
| `limit_up_sentiment(date)` | 炸板率、连板高度、连板梯队 | 本地组合 |

日期格式通常是 `YYYYMMDD`。非交易日可能返回空。
