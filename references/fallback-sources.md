# 备用源和降级策略

| 主源问题 | 备用端点 | 备用源 |
|---|---|---|
| 东财龙虎榜被封或为空 | `dragon_tiger_backup(date)` | 上交所/深交所官方 |
| 东财资金流被封或为空 | `fund_flow_backup(code)` | 新浪日度资金流 |
| 巨潮公告被封或为空 | `announcements_backup(code)` | 深交所官方/东财沪市公告 |
| mootdx 行情命令返回空（#52） | `tencent_kline(code)` / `tdx_daily_package(date)` | 腾讯 / 通达信官网盘后包 |
| mootdx `transaction()` 返回空 | `tencent_ticks(code)` | 腾讯（当日分笔） |
| 东财研报不可达 | `sina_research_reports(code)` | 新浪（无评级与目标价） |
| 财联社 / 东财 7x24 不可达 | `wallstreetcn_lives(channel)` | 华尔街见闻 |
| 巨潮互动易对沪市返回 0 条 | `sse_e_interaction(code)` | 上证e互动（上交所官方） |
| 大商所官方日行情（412 反爬，未接入） | `futures_kline("M0")` / `futures_realtime(["M0"])` | 新浪 |

降级后必须说明口径变化。例如新浪日度资金流不能和东财分钟资金流直接相加。
K 线备用源的量纲也不一致：新浪 `getKLineData` 的量是**股**；腾讯 `tencent_kline()` 科创板是股、其余是手（详见 `endpoint-market.md`），降级前后不要直接比较 `volume`。

## mootdx 行情失效后的分层（2026-09 起）

通达信公开服务器的 K 线 / 盘口 / 逐笔命令普遍返回 0 行（10 台服务器逐台实测，TCP 都可达）。
财务快照与 F10 仍正常，用 `tdx_client(check='finance')`；行情改用腾讯 K 线 / 逐笔与通达信官网盘后包。

## v3.7 无自动备用的能力

复权因子（新浪北交所）、baostock 北交所历史估值、申万行业历史、人民银行社融和国家统计局 PMI 当前没有等价的零鉴权自动备用端点。失败时应明确报告来源/市场/格式边界，不要用训练数据补值。
