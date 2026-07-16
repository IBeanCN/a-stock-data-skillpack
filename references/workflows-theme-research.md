# 工作流：题材和产业链调研

1. `ths_hot_reason()` 拉当日强势股和题材归因。
2. 对题材标签做词频统计，识别主线。
3. `eastmoney_concept_blocks(code)` 验证个股概念归属。
4. `iwencai_search(query)` 检索主题研报，前提是已配置 key。
5. `eastmoney_reports(code)` / `eastmoney_industry_reports(industry_code)` 补研报证据。
6. `eastmoney_fund_flow_minute(code)` 或 `stock_fund_flow_120d(code)` 验证资金方向。

题材归因是市场叙事，不等于投资结论。
