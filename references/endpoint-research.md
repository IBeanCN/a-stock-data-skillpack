# 研报端点

| 端点 | 数据 | 数据源 |
|---|---|---|
| `eastmoney_reports(code, max_pages=5)` | 个股研报、评级、EPS 预测 | 东财 reportapi |
| `eastmoney_industry_reports(industry_code="*")` | 行业研报 | 东财 reportapi |
| `download_pdf(record)` | 研报 PDF | 东财 PDF |
| `ths_eps_forecast(code)` | 机构一致预期 EPS | 同花顺 |
| `iwencai_search(query)` | NL 语义搜索研报 | iwencai，需 key |
| `iwencai_query(query)` | NL 结构化查询 | iwencai，需 key |
| `sina_research_reports(code=None, page=1)` | 研报列表第二来源 | 新浪（无评级与目标价） |
| `dedup_articles(items)` | 文章去重 | 本地处理 |

## 注意

- 东财研报和 PDF 请求走 `em_get()` 或脚本封装，不要裸请求。
- 个股研报和同花顺一致预期会先严格归一化 ticker；格式错误、市场矛盾、显式沪市指数会抛错，避免把错误输入误读为“无研报覆盖”。
- 北交所 `43/83/87` 老号段多数已迁至 `920xxx`；老码研报为空时会抛 `ValueError`，请按名称反查现行代码。
- 行业研报 `begin` 留空时默认取相对今天近两年，不再使用固定起始日。
- 同花顺一致预期可能没有机构覆盖；无覆盖时不要推断 EPS。
- iwencai 只从 `IWENCAI_API_KEY` 读取 key。

## 新浪研报列表（上游 v3.9.0 §2.4，研报第二来源）

- `code=None` 返回全市场最新（每页约 40 条，`page` 从 1 开始）；给代码只看该股。
- 只给列表与详情页链接，**没有评级和目标价**，需要这些用东财研报。
- 北交所必须写 `bj920982`；只给数字时新浪返回「没有找到」，看起来像该股没有研报，函数会自动加 `bj` 前缀。
- 新浪对连续请求会返回**假的空页**（HTTP 200，与真的没有研报长得一样，实测间隔 1 秒触发、≥5 秒恢复）：
  函数内置 6 秒最小间隔，并对空页等待后重试一次，批量翻页会比较慢。
- 带序号的行必须全部解析出来；0 行只认页面上的「没有找到相关内容」。
