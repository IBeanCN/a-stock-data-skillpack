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
