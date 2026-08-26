# 基础数据 / 财报端点

| 端点 | 数据 | 数据源 |
|---|---|---|
| `tdx_client()` | 财务快照、F10 底层 client | mootdx |
| `eastmoney_stock_info(code)` | 行业、股本、市值、上市日期 | 东财 push2 |
| `sina_financial_report(code, report_type, num=5)` | 利润表/资产负债表/现金流量表 | 新浪 |

`report_type` 常用值：

- `lrb`：利润表。
- `fzb`：资产负债表。
- `llb`：现金流量表。

财报字段来自公开接口，报告期和单位要随结果一起说明。

## 历史估值、上市状态与行业历史（v3.7）

- `baostock_valuation_history(code, start_date, end_date)`：`peTTM/pbMRQ/psTTM/pcfNcfTTM/turn/tradestatus/isST`。
- `baostock_stock_basic(code)`：上市日 `ipoDate`、退市日 `outDate`、类型与状态。baostock 不支持北交所，脚本会在登录前拒绝。
- `sw_industry_history()`：申万官方行业变迁 XLS；规范化 `industry_code/l1_code/l2_code` 为 6 位。官方文件不含中文行业名，不可套用东财或通达信名称。
- `sw_industry_as_of(data, code, as_of)`：取指定历史时点所属行业，避免前视偏差。
