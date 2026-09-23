# 故障处理

## 依赖缺失

运行：

```bash
python3 scripts/validate_env.py
```

在 PEP 668 环境里使用 venv 或 uv 安装依赖，不要污染系统 Python。

## 东财 403 / 429 / 连接重置

1. 降低频率，调大 `EM_MIN_INTERVAL`。
2. 串行调用，不要并发。
3. 等待风控解除或换网络。
4. 切换 `fallback-sources.md` 中的备用端点。

## mootdx 连接失败

海外网络常见 TCP 7709 超时。使用国内网络/代理，或更新 `_TDX_SERVERS`。

## mootdx 拿到空表（2026-09 起，上游 #52）

内置 10 台服务器逐台实测：TCP 都可达、财务与除权除息正常、F10 只剩「最新提示」一类，但 K 线 / 五档 / 逐笔返回 0 行。

| 需求 | 改用 |
|---|---|
| 日 / 周 / 月 K 线（沪深） | `tencent_kline(code, period="day", adjust="qfq")` |
| 1~60 分钟 K 线 | `tencent_kline(code, period="m5")` |
| 某交易日全市场日线（含成交额） | `tdx_daily_package(date)` |
| 当日逐笔 | `tencent_ticks(code)` |
| 财务快照 / F10 | `tdx_client(check="finance")` |

行情类调用若仍用默认 K 线验活，会误报「全部服务器不可达」；财务类调用若用行情口径验活同样误判。

## F10 只剩「最新提示」

请求不存在的类别时 mootdx 返回 dict，切片直接 `TypeError`。先用 `client.F10C(symbol=...)` 列出实际类别；
其余类别（公司概况 / 股东研究 / 资本运作等）改用公开端点，不要写死旧类别名。

## 新浪研报返回假空页

两次请求间隔 1 秒时，第二次起返回「没有找到相关内容」空页（HTTP 200，与真的没有研报长得一样），间隔 ≥5 秒恢复正常。
`sina_research_reports()` 内置 6 秒最小间隔，并对空页等待后重试一次；批量翻页慢是设计如此。

## 期货 / 交易所官方端点的常见坑

- 中金所、广期所只能走 HTTP（实测中金所 443 握手即断、广期所 443 证书是 `*.unionpayintl.com`）。
- 大商所官网 JS 反爬（纯 HTTP 412），官方日行情未接入，大商所品种用 `futures_kline` / `futures_realtime`。
- 非交易日（含周六）官方文件返回空表或 404，函数抛 `ValueError`，不会回退到最近交易日。
- 上期能源首个交易日之前也会发文件但里面没有合约，函数按「当时还没有」抛 `ValueError`。
- 中债单次查询超过 1 年会静默返回 0 行，函数按 360 天切片；整段 7 天以上 0 行才报错。
- 盘后包老日期：2021-08-16 之前 404，2022-05-06 之前没有北交所文件（只返回沪深）。

## iwencai 401

配置 `IWENCAI_API_KEY`。无 key 时不要使用 iwencai 端点。

## 接口返回空

先确认：交易日、日期格式、股票代码、是否有机构覆盖、是否停牌、是否源站改版。

## smoke test

```bash
python3 scripts/smoke_test_endpoints.py
python3 scripts/smoke_test_endpoints.py --network
```

无网络模式校验 97 个必需函数、ticker 与聚宽代码归一化、复权换算、筹码分布，以及新端点的参数校验（区间上限、布尔值、市场边界）。
`--network` 只做 best-effort 探测：抛异常记 WARN，返回空但无异常记 OK，单个源波动不会阻断整体验证。

## v3.7 数据源边界

- 东财市场路由正确不代表 ETF 具有个股资金流；部分 ETF 仍会返回空。
- baostock 不支持北交所；新浪北交所复权因子可能 404。
- 申万 XLS 出现 SSL 错误时更新 CA/certifi 并检查代理。
- 社融仅支持 2021 年起新表格式；PMI 主字段或页面措辞变更时会抛错而非静默返回空。
