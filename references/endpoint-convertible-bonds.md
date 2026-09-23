# 可转债端点（上游 v3.9.0 新增层）

| 端点 | 数据 | 数据源 |
|---|---|---|
| `convertible_bonds(include_delisted=False)` | 可转债全表：条款 + 最新转股价 / 债价 / 正股价 / 转股价值 / 溢价率 | 东财数据中心（`RPT_BOND_CB_LIST`） |

## 状态判定

| `status` | 条件 |
|---|---|
| `upcoming` | 已发行未上市（上市日不晚于今天才算交易中） |
| `listed` | 交易中（上市日不晚于今天、摘牌日不晚于今天才算已摘牌） |
| `delisted` | 已摘牌；退市板块转债（代码 `404xxx`，`TRADE_MARKET=STAS00`）东财不填上市日与摘牌日，按已摘牌处理，默认结果里不返回（`include_delisted=True` 才返回） |
| `unknown` | 交易市场不认识，或既没有上市日也没有申购日，不猜 |

东财会提前填上未来的日期（2026-09-20 实测 113710 上市日填的是 09-23），所以判定必须把日期与今天比较，不能只看字段有没有值。时间基准是北京时间，不看本机时区。

## 字段与公式

关键字段：`code/name/status/stock_code/stock_name/rating/issue_size_100m/apply_date/apply_code/listing_date/delist_date/expire_date/convert_start/initial_convert_price/convert_price/bond_price/stock_price/convert_value/premium_pct`。

- 转股价值 = 100 / 转股价 × 正股价。
- 溢价率 `premium_pct` = 债价 / 转股价值 − 1（%）。
- `issue_size_100m` 单位亿元。
- 行情类字段由东财服务端按最新报价填入：盘中为实时价，停牌或未上市为 None。

## 使用边界

可转债条款（下修、强赎、回售）会改变转股价与存续期，本端点只给当前快照，做条款推演要另外核对募集说明书与公司公告。评级字段来自东财，与评级机构的原始报告可能有差异。
