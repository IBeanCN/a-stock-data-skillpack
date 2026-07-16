# 资金面 / 筹码端点

| 端点 | 数据 | 数据源 |
|---|---|---|
| `margin_trading(code)` | 融资余额、买入、偿还、融券余额 | 东财 datacenter |
| `block_trade(code)` | 大宗交易价格、量、买卖方、溢价率 | 东财 datacenter |
| `holder_num_change(code)` | 股东户数、环比、户均持股 | 东财 datacenter |
| `dividend_history(code)` | 派息、送股、转增、进度 | 东财 datacenter |
| `stock_fund_flow_120d(code)` | 120 日主力/大单/中单/小单净流入 | 东财 push2his |

批量调用这些端点时调大 `EM_MIN_INTERVAL`，避免东财风控。
