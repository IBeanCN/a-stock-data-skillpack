# 基础数据 / 财报端点

| 端点 | 数据 | 数据源 |
|---|---|---|
| `tdx_client()` | 财务快照、F10 底层 client | mootdx |
| `eastmoney_stock_info(code)` | 行业、股本、市值、上市日期 | 东财 push2 |
| `sina_financial_report(code, report_type, num=5)` | 利润表/资产负债表/现金流量表 | 新浪 |
| `st_stock_list()` | 全市场 ST / *ST 名单（当日快照） | 东财（baostock 兜底） |

`report_type` 常用值：

- `lrb`：利润表。
- `fzb`：资产负债表。
- `llb`：现金流量表。

财报字段来自公开接口，报告期和单位要随结果一起说明。

## mootdx 财务 / F10 的正确入口（上游 #52）

- 2026-09 起通达信公开服务器的 K 线 / 盘口 / 逐笔命令普遍返回 0 行，财务快照与 F10 仍正常，但**必须用财务口径验活**：
  `tdx_client(check='finance')` 会同时核对财务快照、F10 类别表里有「最新提示」、并实际读出非空正文。
- 用默认 `check='bars'` 的客户端调财务 / F10 会被误判成「全部不可达」，反之亦然。
- 服务端变化后 F10 只剩「最新提示」一类：请求不存在的类别时 mootdx 返回 dict，直接切片会 `TypeError`；
  先用 `client.F10C(symbol=...)` 列出实际类别，其余类别请改用对应端点（公司概况 / 股东研究 / 资本运作等见公开接口）。

## ST / *ST 名单（上游 v3.9.0 §6.8）

- 沪深：东财「风险警示板」过滤（含 B 股）；北交所：东财不纳入该过滤，改为拉北交所全表按名称筛。
- 逐行校验代码、市场号和名称（实测两张表 562 行：代码全 6 位、市场号只有 0/1、名称无空值）；
  市场号缺失原来一律当深市，名称为空会让北交所那半边被静默筛掉却仍标「沪深京」。
- 只有东财两个域名都连不上才退到 baostock 证券列表按名称筛：**只有沪深、没有价格**，`attrs` 里注明；返回错误页直接报错。
- `price` / `pct_change` 在走 `push2delay` 时约有 15 分钟延迟（`source_url` 可看出走的是哪个域）。

## 历史估值、上市状态与行业历史（v3.7）

- `baostock_valuation_history(code, start_date, end_date)`：`peTTM/pbMRQ/psTTM/pcfNcfTTM/turn/tradestatus/isST`。
- `baostock_stock_basic(code)`：上市日 `ipoDate`、退市日 `outDate`、类型与状态。baostock 不支持北交所，脚本会在登录前拒绝。
- `sw_industry_history()`：申万官方行业变迁 XLS；规范化 `industry_code/l1_code/l2_code` 为 6 位。官方文件不含中文行业名，不可套用东财或通达信名称。
- `sw_industry_as_of(data, code, as_of)`：取指定历史时点所属行业，避免前视偏差。
