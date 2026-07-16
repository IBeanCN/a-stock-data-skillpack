# 研报端点

| 端点 | 数据 | 数据源 |
|---|---|---|
| `eastmoney_reports(code, max_pages=5)` | 个股研报、评级、EPS 预测 | 东财 reportapi |
| `eastmoney_industry_reports(industry_code="*")` | 行业研报 | 东财 reportapi |
| `download_pdf(record)` | 研报 PDF | 东财 PDF |
| `ths_eps_forecast(code)` | 机构一致预期 EPS | 同花顺 |
| `iwencai_search(query)` | NL 语义搜索研报 | iwencai，需 key |
| `iwencai_query(query)` | NL 结构化查询 | iwencai，需 key |
| `dedup_articles(items)` | 文章去重 | 本地处理 |

## 注意

- 东财研报和 PDF 请求走 `em_get()` 或脚本封装，不要裸请求。
- 同花顺一致预期可能没有机构覆盖；无覆盖时不要推断 EPS。
- iwencai 只从 `IWENCAI_API_KEY` 读取 key。
