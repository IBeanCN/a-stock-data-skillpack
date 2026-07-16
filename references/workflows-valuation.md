# 工作流：单票估值

1. `normalize_code(code)` 归一化代码。
2. `tencent_quote([code])` 获取价格、PE/PB、市值。
3. `eastmoney_stock_info(code)` 获取行业、股本、上市日期。
4. `ths_eps_forecast(code)` 获取一致预期 EPS。
5. `full_valuation(code)` 生成估值全景。
6. `eastmoney_stock_news(code)` 和 `cninfo_announcements(code)` 检查近期事件。

输出时区分事实数据和估值推断。
