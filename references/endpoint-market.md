# 行情端点

实现位置：`scripts/a_stock_client.py`。

| 端点 | 数据 | 说明 |
|---|---|---|
| `normalize_code(code)` | 代码归一化 | 支持 `SH688017`、`688017.SH` 等格式 |
| `get_prefix(code)` | 市场前缀 | 返回 `sh`、`sz`、`bj` |
| `tdx_client(market, check)` | mootdx client | 财务快照 / F10 的底层入口；`check='bars'` 的行情命令 2026-09 起普遍返回空 |
| `tencent_quote(codes)` | 实时行情 | 最新价、PE/PB、市值、换手、涨跌停、指数、ETF |
| `tencent_kline(code, period, adjust, start, end, count)` | K线 | 日/周/月前复权 + 1~60 分钟；不支持北交所 |
| `tdx_daily_package(date)` | 全市场日线 | 某交易日沪深北全部证券，**含成交额** |
| `tencent_ticks(code)` | 逐笔成交 | 当日分笔，替代失效的 mootdx `transaction()` |
| `baidu_kline_with_ma(code)` | K线 | 日 K，带 MA5/MA10/MA20 |

## mootdx 用法（行情命令已失效，见下）

⚠️ 2026-09 起通达信公开服务器的 K 线 / 五档 / 逐笔命令普遍返回 0 行（上游 #52，10 台服务器逐台实测：
TCP 都可达、财务与除权除息正常、F10 只剩「最新提示」一类）。财务 / 公告类调用改用 `tdx_client(check='finance')`，
行情类改用 `tencent_kline()`、`tdx_daily_package()`、`tencent_ticks()`。

`tdx_client()` 返回 mootdx client，然后调用：

- `.bars()`：K线。参数名是 `frequency`，不是 `category`。
- `.quotes()`：五档盘口、实时报价。
- `.transaction()`：逐笔成交。

mootdx K 线是不复权原始价，跨除权除息日估值或回测前需自行复权。

## 腾讯 K 线 `tencent_kline()`（上游 v3.9.0 §1.2）

- `period`：`day` / `week` / `month` / `m1` / `m5` / `m15` / `m30` / `m60`；日周月默认前复权，分钟线默认不复权，可用 `adjust='qfq'|'hfq'|''` 显式指定。
- `start/end` 仅日周月可用；给了 `start` 会自动按段分页（单次最多 640 根）。不给 `start` 时取最近 `count` 根（日周月 ≤640，分钟 ≤320）。
- 三个腾讯入口轮换（`web.ifzq.gtimg.cn` / `proxy.finance.qq.com/ifzqgtimg` / `ifzq.gtimg.cn`），某入口失败后暂停 120 秒，单域名约 600 次后返回空 JSON。
- 成交量单位是**手**；本端点**没有成交额**，要成交额用 `tdx_daily_package()`。
- **不支持北交所**：腾讯对北交所只返回最新 1 根日线、分钟线为空，函数直接抛 `ValueError` 并指向盘后包。
- 前复权是等差口径，遇 ≤0 价格抛错；分段结果会自动去重（同一天或同一分钟出现两次即报错）。

## 通达信官网盘后包 `tdx_daily_package()`（上游 v3.9.0 §1.3）

- 走 HTTP 下载某交易日全市场日线包（约 2.7MB），与失效的 TCP 行情命令是两条路。
- 个股 `volume` 单位是**股**、`amount` 单位是**元**；指数等特殊代码的 `volume` 为通达信原值。
- 非交易日或当日包尚未发布时官网返回 404，函数抛 `ValueError`，不返回空表。
- 历史上限：2021-08-16 起可下载（更早 404）；2022-05-06 之前的包没有北交所文件，只返回沪深，之后缺北交所文件会报错。
- 各市场有价记录低于实测下限（沪 1 万 / 深 3000 / 京 50 条）、代码不是 6 位或重复、块序号重复、代码表与行情块条数对不上、价格 / 成交额不是有限数，都按文件残缺抛 `RuntimeError`。

## 腾讯逐笔 `tencent_ticks()`（上游 v3.10.0 §1.4）

- 最近一个交易日的全部成交明细（约 3 秒一笔的分笔，不是 Level-2 逐笔），覆盖沪深个股（含创业板、科创板）与 ETF。
- 字段：`date/code/time/seq/price/change/volume（手）/amount（元）/side（B 主动买 · S 主动卖 · M 中性）`。
- 只有最近一个交易日；北交所、指数、代码不存在、当日没有成交抛 `ValueError`。
- 收盘后调用会用行情快照的当日成交额核对连续竞价段，对不上抛 `RuntimeError`；盘后定价段腾讯偶尔缺几笔，缺的序号在 `frame.attrs["missing_seq"]`。

## 上游 § 编号对照

上游 v3.10.0 把行情层重新编号为「可用来源在前」：1.1 腾讯行情、1.2 腾讯 K 线、1.3 通达信盘后包、1.4 腾讯逐笔、
1.5 百度、1.6 新浪复权因子、1.7 mootdx（留档）。函数名与签名都没变，只影响按编号查找。

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

腾讯字段口径：`vals[44]` 是流通市值，`vals[45]` 是总市值；两者曾被标反。总股本与流通股本差异较大的股票尤其要避免混用。

## mootdx 验活

`tdx_client()` 不只做 TCP 握手，还会对 `market='std'` 候选服务器真实拉取一根 K 线；握手成功但返回空数据的坏服务器会被跳过。非 `std` 市场跳过 A 股样本验活，避免把正常扩展行情服务器误判为失效。

## 复权因子与价格换算（v3.7）

- `sina_adjust_factor(code, kind="qfq"|"hfq")`：新浪因子序列；响应尾部带注释，脚本用 `JSONDecoder.raw_decode()`。北交所当前返回 404，无自动备用源。
- `apply_adjust(bars, factors, kind)`：接收 DataFrame 或 records；qfq 为不复权价格 **除以** factor，hfq 为 **乘以** factor。DataFrame 会保留时间索引。
- 空因子、零因子或 K 线早于最早因子会抛错，避免在同一结果中混入未复权价。
- `get_prefix()` 将前缀和后缀显式市场视为等价；`em_secid()` 统一生成东财市场号。
