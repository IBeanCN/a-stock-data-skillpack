# 工作流：批量筛选

1. 准备股票代码列表，先用 `normalize_code()` 清洗。
2. `tencent_quote(codes)` 批量拉行情和估值。
3. 需要行业对比时调用 `industry_comparison()`。
4. 需要资金验证时抽样调用 `stock_fund_flow_120d(code)`，不要对大量代码并发打东财。
5. 输出排序规则、过滤条件、缺失字段和数据日期。
