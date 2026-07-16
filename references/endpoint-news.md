# 新闻端点

| 端点 | 数据 | 数据源 |
|---|---|---|
| `eastmoney_stock_news(code)` | 个股相关新闻 | 东财 search-api |
| `cls_telegraph(page_size=20)` | 财联社电报，v1 API + 本地签名 | 财联社 |
| `eastmoney_global_news(page_size=20)` | 7x24 全球财经资讯 | 东财 np-weblist |

新闻、快讯必须输出时间戳和来源。不能用旧知识补当前新闻。
