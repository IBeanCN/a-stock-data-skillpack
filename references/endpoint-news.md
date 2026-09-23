# 新闻端点

| 端点 | 数据 | 数据源 |
|---|---|---|
| `eastmoney_stock_news(code)` | 个股相关新闻 | 东财 search-api |
| `cls_telegraph(page_size=20)` | 财联社电报，v1 API + 本地签名 | 财联社 |
| `eastmoney_global_news(page_size=20)` | 7x24 全球财经资讯 | 东财 np-weblist |
| `wallstreetcn_lives(channel="global-channel", limit=50, cursor=None)` | 7x24 快讯 | 华尔街见闻 |
| `cctv_news(date, with_content=True)` | 新闻联播条目与文字稿 | 央视网 |

新闻、快讯必须输出时间戳和来源。不能用旧知识补当前新闻。

## 华尔街见闻 7×24（上游 v3.9.0 §5.4，第三来源）

- `channel` 例：`global-channel`（要闻，默认）/ `a-stock-channel`（A 股）；`limit ≤ 100`。
- 翻页：把返回表 `attrs['next_cursor']` 传给下一次的 `cursor`。
- `importance` 取见闻的 `score`：实测只有 1 / 2，100 条里约 6 条为 2（头条级快讯）。时间为北京时间。
- `channels` 必须是字符串数组；来源改成字符串时会报错，不再被拆成单字。
- 与财联社、东财 7x24 互为独立备份（不同域名、不同风控面）。

## 央视《新闻联播》（上游 v3.9.0 §5.5）

- 当晚约 20:00 后更新当日条目；`with_content=True` 会逐条打开详情页取正文（约 15 次请求），只要标题和链接就传 `False`。
- 个别老视频已被下架，其 `content` 为 None（标题仍在）。
- 内容以时政为主，可用于政策信号研究；**做短视频文案时不要引用**。
