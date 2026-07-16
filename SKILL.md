---
name: a-stock-data
description: 当任务需要写代码实际获取A股数据时使用：行情/K线、研报、信号、资金面、新闻、财务/F10、公告、打板、ETF期权、舆情互动、备用源和估值等真实数据。渐进式披露 Skill 包：SKILL.md 只负责触发、路由和约束；端点实现统一在 scripts/a_stock_client.py；端点说明、字段口径、工作流、FAQ 按需读取 references/。
origin: custom
version: 3.4.0-progressive-client
---
# A股全栈数据工具包（渐进式披露）

项目主页：https://github.com/simonlin1212/a-stock-data  
作者：Simon 林 · 抖音「Simon林」· 公众号「硅基世纪」

## 何时使用

只在需要**实际获取 A 股数据或写数据抓取代码**时使用。不要用于纯概念解释、投资观点讨论、策略闲聊或不需要实时/历史数据的问答。

## 目录结构

| 路径 | 职责 |
|---|---|
| `SKILL.md` | 轻量路由器，只负责触发、路由和约束 |
| `scripts/a_stock_client.py` | 所有端点实现和命令行入口 |
| `scripts/validate_env.py` | 环境依赖和 iwencai key 检查 |
| `scripts/smoke_test_endpoints.py` | 端点迁移完整性 smoke test |
| `references/` | 按需读取的端点说明、字段口径、估值公式、工作流和故障处理；不放实现代码 |

## 使用原则

1. 先识别用户任务类型、股票代码、日期范围和输出要求。
2. 只读取最相关的 1-2 个 reference 文件，不要一次加载全部文档。
3. 优先执行 `scripts/a_stock_client.py` 中的函数，不要从 `references/` 复制实现代码。
4. 不要用记忆或训练数据补当前行情、新闻、公告、资金流、研报或估值输入。
5. 东财请求必须通过脚本内 `em_get()`，批量任务调大 `EM_MIN_INTERVAL`，不要并发打东财。
6. 主源 403/429/连接重置/空返回时，读取 `references/fallback-sources.md` 和 `references/troubleshooting.md`。

## 路由索引

| 用户意图 | 读取文件 |
|---|---|
| 依赖、ticker 归一化、数据源优先级、东财防封、输出要求 | `references/conventions.md` |
| 实时行情、K线、盘口、逐笔、PE/PB、市值、指数、ETF | `references/endpoint-market.md` |
| 研报列表、PDF、一致预期 EPS、iwencai 语义搜索 | `references/endpoint-research.md` |
| 热点题材、北向、概念、分钟资金流、龙虎榜、解禁、行业轮动 | `references/endpoint-signals.md` |
| 融资融券、大宗交易、股东户数、分红、120 日资金流 | `references/endpoint-capital-chip.md` |
| 个股新闻、财联社电报、全市场 7x24 快讯 | `references/endpoint-news.md` |
| 财务快照、F10、东财基本面、新浪财报三表 | `references/endpoint-fundamentals.md` |
| 巨潮公告、公告备用源 | `references/endpoint-announcements.md` |
| 涨停池、炸板池、跌停池、昨日涨停、打板情绪 | `references/endpoint-limit-up.md` |
| ETF 期权合约、T 型报价、希腊字母、IV | `references/endpoint-options.md` |
| 互动易、同花顺热榜、东财人气榜、概念命中 | `references/endpoint-sentiment.md` |
| 主源失败后的交易所/新浪/深交所备用源 | `references/fallback-sources.md` |
| 前向 PE、PE 消化时间、PEG | `references/valuation-formulas.md` |
| 单票完整估值、新标的估值判断 | `references/workflows-valuation.md` |
| 多股票批量估值、横向对比、筛选 | `references/workflows-screening.md` |
| 主题研报、产业链调研、题材归因 | `references/workflows-theme-research.md` |
| 依赖缺失、401、403、乱码、接口为空、mootdx 超时、smoke test | `references/troubleshooting.md` |

## 脚本入口

```bash
python3 scripts/a_stock_client.py list
python3 scripts/a_stock_client.py call tencent_quote --args '[["600519", "000001"]]'
python3 scripts/a_stock_client.py call forward_pe --args '[100, 5]'
python3 scripts/validate_env.py
python3 scripts/smoke_test_endpoints.py
```

CLI 输出 JSON；返回 DataFrame 的端点会自动转 records。

## 输出契约

回答中应包含：

1. 结论或数据表。
2. 数据源和日期。
3. 缺失字段、接口为空、非交易日、无 key、无机构覆盖等说明。
4. 如果包含估值或题材判断，必须区分事实和推断。

如果依赖缺失、网络不可达或接口下线，说明具体缺口，并只基于已取得或用户提供的数据继续。
