# 公告端点

| 端点 | 数据 | 数据源 |
|---|---|---|
| `cninfo_announcements(code, page_size=30)` | 沪深北公告全文检索 | 巨潮 cninfo |
| `announcements_backup(code)` | 公告备用源，深市深交所官方，沪市东财 | 深交所/东财 |

巨潮公告会动态解析真实 `orgId`。若公告为空，先确认股票代码、市场、日期范围和是否非交易日。
