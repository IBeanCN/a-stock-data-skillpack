# 资金面 / 筹码端点

| 端点 | 数据 | 数据源 |
|---|---|---|
| `margin_trading(code)` | 融资余额、买入、偿还、融券余额 | 东财 datacenter |
| `block_trade(code)` | 大宗交易价格、量、买卖方、溢价率 | 东财 datacenter |
| `holder_num_change(code)` | 股东户数、环比、户均持股 | 东财 datacenter |
| `dividend_history(code)` | 派息、送股、转增、进度 | 东财 datacenter |
| `stock_fund_flow_120d(code)` | 120 日主力/大单/中单/小单净流入 | 东财 push2his |

批量调用这些端点时调大 `EM_MIN_INTERVAL`，避免东财风控。

## 筹码分布 CYQ（本地推演）

`chip_distribution(data, grid_size=300, decay=1.0)` 接收 `date/high/low/close/turn`，其中 `turn` 是百分数。算法将首日视为期初全部流通筹码，后续按换手率衰减，并把当日成交量按 `[low, high]` 三角分布撒入价格网格。

输出包括 `profit_ratio`、`avg_cost`、70%/90% 成本区间及集中度、`peak_price` 和直方图。输入必须使用前复权价格并过滤停牌日；这是基于历史 OHLC/换手的估计，不是交易所真实持仓。
