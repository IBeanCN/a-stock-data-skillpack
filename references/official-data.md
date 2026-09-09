# 官方指数与交易所数据（v3.8.0）

本版本新增 6 个能力入口，直接访问官方源，不新增 AKShare 等运行时依赖：

- `index_constituents(index_code, provider=\"csi\")`：中证/国证最近公布成分快照。
- `index_weights(index_code, provider=\"csi\")`：指数权重，`weight_percent` 为百分数，不是小数。
- `index_valuation(index_code)`：中证近期 PE 与股息率，保留总股本/计算用股本两种口径，不提供 PB。
- `trading_calendar(year, month)`：深交所完整自然月交易标志；未发布或缺日直接报错。
- `margin_trading_backup(trade_date, exchange, code=None)`：按沪/深交易所分别获取两融备胎，金额单位元、余量单位股/份。
- `bse_quote_backup(trade_date, code=None)`：北交所当前行情和五档快照；不使用当前行情回填历史日期。

## 边界与校验

所有官方解析器保留 `source`、`source_url`、`fetched_at`，并严格校验代码、日期、字段、分页总数、重复记录和快照完整性。国证文件中的港股五位代码不会被补零成深市代码；北交所代码必须以 `4`、`8` 或 `92` 开头。

中证/国证权重文件可能不是同一日期；交易日历必须覆盖目标月份的每个自然日。两融缺少官方字段时保留允许为空的字段，未发布数据不解释为零。北交所匿名会话遇到 302 只重建一次，不无限跟随。

## 数据源

实现直接访问 CSI、CNI、SZSE、SSE 和 BSE 官方域名。端点发现参考 AKShare、Qlib、CNEquity 等项目，但它们不是本项目运行时依赖。
