# ETF 期权端点

| 端点 | 数据 | 数据源 |
|---|---|---|
| `sina_option_codes(underlying="510050", call=True)` | ETF 期权合约清单 | 新浪 |
| `sina_option_tquote(option_code)` | T 型报价、买卖档、持仓量 | 新浪 |
| `sina_option_greeks(option_code)` | Delta/Gamma/Theta/Vega/IV | 新浪 |

支持标的包括 `510050`、`510300`、`588000`、`510500`。期权数据需注明合约、到期月份和观察时间。
