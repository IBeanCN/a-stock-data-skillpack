# 行情端点

实现位置：`scripts/a_stock_client.py`。

| 端点 | 数据 | 说明 |
|---|---|---|
| `normalize_code(code)` | 代码归一化 | 支持 `SH688017`、`688017.SH` 等格式 |
| `get_prefix(code)` | 市场前缀 | 返回 `sh`、`sz`、`bj` |
| `tdx_client()` | mootdx client | K线、盘口、逐笔、财务快照、F10 的底层入口 |
| `tencent_quote(codes)` | 实时行情 | 最新价、PE/PB、市值、换手、涨跌停、指数、ETF |
| `baidu_kline_with_ma(code)` | K线 | 日 K，带 MA5/MA10/MA20 |

## mootdx 用法

`tdx_client()` 返回 mootdx client，然后调用：

- `.bars()`：K线。参数名是 `frequency`，不是 `category`。
- `.quotes()`：五档盘口、实时报价。
- `.transaction()`：逐笔成交。

mootdx K 线是不复权原始价，跨除权除息日估值或回测前需自行复权。

## 腾讯字段口径

| 字段 | 口径 |
|---|---|
| `price` | 最新价，元 |
| `last_close` | 昨收，元 |
| `change_pct` | 涨跌幅，百分数 |
| `amount_wan` | 成交额，万元 |
| `turnover_pct` | 换手率，百分数 |
| `pe_ttm` | 滚动市盈率 |
| `pe_static` | 静态市盈率 |
| `pb` | 市净率 |
| `mcap_yi` | 总市值，亿元 |
| `float_mcap_yi` | 流通市值，亿元 |
| `limit_up` / `limit_down` | 涨跌停价，元 |
