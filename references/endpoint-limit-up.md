# 打板端点

| 端点 | 数据 | 数据源 |
|---|---|---|
| `em_zt_pool(date)` | 涨停池 | 东财 push2ex |
| `em_zb_pool(date)` | 炸板池 | 东财 push2ex |
| `em_dt_pool(date)` | 跌停池 | 东财 push2ex |
| `em_yzt_pool(date)` | 昨日涨停今日表现 | 东财 push2ex |
| `ths_limit_up_pool(date)` | 涨停原因、题材、封板质量 | 同花顺 |
| `limit_up_sentiment(date)` | 炸板率、连板高度、连板梯队 | 本地组合 |
| `em_stock_monitor(only_active=True)` | 交易所风险警示/重点监控名单及生效时间窗 | 东财静态 JSON |
| `em_price_anomaly(page_size=200)` | 日内严重异常波动明细与规则解释 | 东财 price-anomaly |
| `em_price_anomaly_count(page_size=50)` | 按标的聚合的异动次数、现价、累计偏离值 | 东财 price-anomaly |

日期格式通常是 `YYYYMMDD`。非交易日可能返回空。

## 重点监控与日内异动

- 监控池按北京时间判断 `VALIDATESTARTDATE` 至 `VALIDATEENDDATE` 的生效窗口。
- 监控池 `MARKET` 是三值：`1=SH`、`0=SZ`、`B=BJ`，不能把 `B` 当深市。
- 异动接口必须携带固定 `team=h5` 等公共参数；脚本已封装。若响应 `result != 0` 会抛 `RuntimeError`，不会静默返回空。
- 北交所不能只看东财 `m` 字段；脚本优先按 `920/43/83/87` 号段和板块码 `8` 判断。
- `em_price_anomaly()` 的 `rule` 已解释 12 种规则码；非交易时段通常返回上一交易日数据。
