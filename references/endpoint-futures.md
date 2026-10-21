# 期货与大宗商品端点（上游 v3.9.0 新增层）

实现位置：`scripts/a_stock_client.py`。七家来源里五家期货交易所官方 + 新浪 + 上金所，全部零鉴权。

| 端点 | 数据 | 数据源 |
|---|---|---|
| `futures_daily(date, exchange)` | 期货日行情（收盘官方数据） | 上期所 / 上期能源 / 郑商所 / 中金所 / 广期所 |
| `options_daily(date, exchange)` | 商品期权、股指期权日行情 | 同上 |
| `futures_position_rank(date, exchange, symbol=None)` | 会员成交量 / 持买单 / 持卖单前 20 名 | 上期所 / 上期能源 / 郑商所 / 中金所 |
| `futures_realtime(symbols)` | 实时或收盘快照，六家交易所全覆盖 | 新浪 |
| `futures_kline(symbol, start, end)` | 逐日 K 线，含大商所 | 新浪 |
| `a50_futures()` | 富时中国 A50 期指连续合约 | 新浪 |
| `sge_spot(instrument="Au99.99")` | 黄金 / 白银 / 铂金现货日线 | 上金所 |

## 交易所与日期边界

`exchange` 取值 `SHFE` / `INE` / `CZCE` / `CFFEX` / `GFEX`。**大商所（DCE）官方日行情未接入**
（官网 JS 反爬，纯 HTTP 返回 412），大商所品种走 `futures_kline('M0')` 与 `futures_realtime(['M0'])`。

- 中金所、广期所只能走 HTTP：2026-09-20 实测中金所 443 握手即断，广期所 443 返回的是 `*.unionpayintl.com` 证书。
- 实测可用起点：上期所 2002-01-07（2021 年及以前没有成交额，`turnover_10k` 为 None）、中金所 2010-04-16、
  上期能源 2018-03 开业、郑商所 2015-09-21（更早是另一套无表头格式）、广期所 2022-12 开业。
- 上期能源首个交易日之前、持仓排名 2020-07-03 之前、期权 2021-06-21 之前按「当时还没有」抛 `ValueError`，不当成格式改变。
- 非交易日抛 `ValueError`（周六请求返回空表，不会回退到最近交易日）。
- 交易日校验靠来源自身：上期所 / 能源中心 / 郑商所核对文件里的交易日，中金所 CSV 没有交易日列 → 用同目录 `index.xml` 每行的 `tradingday` 核对并逐合约比对成交量 / 收盘价 / 持仓量，广期所核对它回显的请求参数。

## 字段口径

| 端点 | 关键字段 |
|---|---|
| `futures_daily` | `date/exchange/symbol/product/open/high/low/close/settle/pre_settle/volume/open_interest/oi_change/turnover_10k`；一行一个合约（不含小计），`settle` 为当日结算价，价格为 0 的统一成 None |
| `options_daily` | 上表 + `series/option_type/strike/delta/iv_pct/series_iv_pct` |
| `futures_position_rank` | `level/symbol/rank/volume_member/volume/volume_chg/long_member/long_oi/long_chg/short_member/short_oi/short_chg` |

- 单位：成交量与持仓量为手，成交额万元；`sge_spot` 黄金元/克、白银元/千克。
- `futures_daily` 的上期所文件也含上期能源品种（原油、20 号胶等），函数按能源中心同日文件剔除，SHFE 与 INE 两次调用不重复计数。
- `options_daily` 的 `series`：商品期权是标的期货合约（如 `cu2610`）；中金所是 `HO/IO/MO` + 月份；郑商所部分品种另有 `CF701MS` 这类带后缀系列，按官方代码原样保留，与 `CF701` 分开。`delta` 是交易所公布值（中金所不公布，为 None）；`iv_pct` 逐合约公布（郑商所、广期所），`series_iv_pct` 是上期所 / 能源中心按系列公布的隐含波动率（官方 SIGMA × 100）。ETF 期权不在这里，见期权端点。
- `futures_position_rank`：`level='contract'` 是单个合约，`level='product'` 是品种合计（只有郑商所公布，`symbol` 为品种字母如 `AP`）。上期所 / 能源中心文件里的 `cuall` 行是按会员类型的汇总、没有名次，已剔除。中金所按 `IF/IH/IC/IM/TS/TF/T/TL` 各取一个文件，当天已上市的品种缺任何一个都抛 `RuntimeError`，不返回部分品种；各品种上市日见脚本里的 `CFFEX_RANK_FIRST_DAY`（2026-09-20 逐个二分实测）。2015 年前后的旧文件在排名段之前还有「会员类别」合计段，函数兼容。
- `sge_spot` 无成交日交易所填 0，这里剔除；代码不存在时上金所返回全 0，抛 `ValueError`。少数日子收盘价略超出高低区间是原始数据如此，日期列在 `frame.attrs['ohlc_anomaly_dates']`。

## 实时与 K 线

- `futures_realtime(symbols)`：`'RB0'`（主力连续）/ `'CU2610'` / `'IF2609'` / `'M0'`，可传列表、带不带 `nf_` 前缀都行。中金所品种另有 `pre_close` 与涨跌停价。盘中是实时价，收盘后是当日收盘快照，**结算价以 `futures_daily` 为准**。无效代码抛 `ValueError`。
- `futures_kline(symbol, start, end)`：主力连续最早到 2005 年，具体合约约 2022 年起到期的。主力连续换月当天跳空，**未做复权**。结算价新浪给得不全（中金所基本没有，主力连续早年也缺），给 0 的统一成 `None`；需要结算价用 `futures_daily`。实测价格与官方 `futures_daily` 逐日一致，成交量 / 持仓偶有 ≤0.1% 出入。中金所主力连续（IF0 / IC0 / IH0 / T0 / TF0）只从 2017-01-17 起，更早的用 `futures_daily`；新浪每次都返回该代码的全部历史（RB0 约 0.5 MB），`start` / `end` 是取回后本地筛选。该请求走 `V39_RETRY_SESSION`（单次超时 (5, 20) 秒），新浪握手卡住时自动重试。

## 使用边界

期货与现货（`sge_spot`）口径不同，不要混用；跨交易所比较时先确认合约乘数与单位。官方日行情是收盘后的权威数据，实时行情用于盘中情绪与夜景参考。
