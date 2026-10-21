# a-stock-data-skillpack

面向 AI 编程助手的 A 股全栈数据 Skill 包。

本项目基于 [simonlin1212/a-stock-data](https://github.com/simonlin1212/a-stock-data) 改造而来，将原始单文件 `SKILL.md` 重构为渐进式披露结构：轻量入口、集中脚本实现、按需读取文档。目标是让 Claude Code、Codex、Hermes Agent 等工具在需要 A 股真实数据时，只加载当前任务需要的上下文，而不是一次性吞下完整端点代码。

## 项目结构

```text
SKILL.md                         # 轻量路由器：触发、路由和约束
scripts/a_stock_client.py         # 端点实现和 CLI 入口
scripts/validate_env.py           # 环境依赖检查
scripts/smoke_test_endpoints.py   # 端点迁移 smoke test
references/                       # 按需读取的说明文档
requirements.txt                  # Python 依赖
```

## 这个 fork 做了什么

- 将原项目的大型单文件 Skill 改为渐进式披露 Skill 包。
- 把端点实现集中到 `scripts/a_stock_client.py`。
- 将端点说明、字段口径、估值公式、工作流和故障处理拆进 `references/`。
- 新增 `validate_env.py`，检查运行依赖和 `IWENCAI_API_KEY`。
- 新增 `smoke_test_endpoints.py`，用于无网络函数完整性校验和可选网络探测。
- 保留并整理原项目的 A 股数据端点能力，包括行情、研报、信号、资金面、新闻、基础数据、公告、打板、ETF 期权、舆情互动、期货与大宗商品、事件驱动、可转债和备用源。
- 当前同步至上游 `v3.10.2`：十五层、87 个入口（82 主入口 + 5 备胎）、34 个来源；v3.10.1 / v3.10.2 未增删入口。
  历史上吸收的上游能力：v3.9.0 / v3.10.0 的 25 + 2 个入口（腾讯 K 线与当日逐笔、通达信官网盘后包、新浪研报列表、
  ETF 份额、华尔街见闻快讯、新闻联播、ST 名单、上证e互动、中债收益率曲线、回购定盘利率、LPR、全球宏观日历、
  期货与大宗商品、事件驱动、可转债），以及通达信行情命令失效（#52）与聚宽代码支持（#55）的处理。
- v3.10.1 / v3.10.2 同步的是修复：腾讯 K 线成交量单位（科创板是股）与对账口径、腾讯逐笔重试会话 +
  `frame.attrs["complete"]` 盘后核对、新浪期货日 K 自动重试、`full_valuation()` 的 PE 消化年数在盈利不增长时返回 `null`。

## 快速开始

安装依赖：

```bash
pip install -r requirements.txt
```

检查环境：

```bash
python3 scripts/validate_env.py
```

查看可用端点：

```bash
python3 scripts/a_stock_client.py list
```

调用端点：

```bash
python3 scripts/a_stock_client.py call tencent_quote --args '[["600519", "000001"]]'
python3 scripts/a_stock_client.py call forward_pe --args '[100, 5]'
python3 scripts/a_stock_client.py call normalize_code --args '["688017.SH"]'
python3 scripts/a_stock_client.py call to_joinquant --args '["sh000001"]'
```

运行 smoke test：

```bash
python3 scripts/smoke_test_endpoints.py
python3 scripts/smoke_test_endpoints.py --network
```

## Skill 使用方式

将整个目录安装到 AI 编程助手可读取的 Skill 目录，而不是只复制 `SKILL.md`。

Hermes Agent 示例：

```bash
mkdir -p ~/.hermes/skills/a-stock-data
cp -R SKILL.md scripts references requirements.txt ~/.hermes/skills/a-stock-data/
```

Claude Code 示例：

```bash
mkdir -p ~/.claude/skills/a-stock-data
cp -R SKILL.md scripts references requirements.txt ~/.claude/skills/a-stock-data/
```

## 渐进式披露设计

`SKILL.md` 只保留触发条件、路由表和执行约束。实际使用时，Agent 应按任务读取最相关的 1-2 个 reference 文件，并调用 `scripts/a_stock_client.py` 中的端点。

主要文档：

| 文件 | 内容 |
|---|---|
| `references/conventions.md` | 依赖、代码归一化、数据源优先级、东财防封、输出要求 |
| `references/endpoint-market.md` | 行情、K 线、复权因子、盘口、指数、ETF |
| `references/endpoint-research.md` | 研报、PDF、一致预期、iwencai |
| `references/endpoint-signals.md` | 热点、北向、概念、资金流、龙虎榜、解禁、行业 |
| `references/endpoint-capital-chip.md` | 两融、大宗、股东户数、分红、120 日资金流、筹码分布 |
| `references/endpoint-news.md` | 个股新闻、财联社电报、7x24 快讯 |
| `references/endpoint-fundamentals.md` | 基础面、估值历史、上市状态、申万行业历史、财报、F10 |
| `references/endpoint-macro.md` | 人民银行社融、国家统计局 PMI |
| `references/endpoint-announcements.md` | 公告 |
| `references/endpoint-limit-up.md` | 涨停池、炸板池、跌停池、打板情绪 |
| `references/endpoint-options.md` | ETF 期权 |
| `references/endpoint-sentiment.md` | 互动易、热榜、人气、概念命中 |
| `references/fallback-sources.md` | 备用源和降级策略 |
| `references/valuation-formulas.md` | 前向 PE、PE 消化、PEG |
| `references/workflows-*.md` | 估值、筛选、题材研究工作流 |
| `references/troubleshooting.md` | 常见故障处理 |

## 数据源原则

- 行情、K 线、实时价、市值等优先使用通达信、腾讯、百度。
- 东财仅用于其独有数据，并且必须通过 `em_get()` 串行限流。
- 批量调用东财接口时调大 `EM_MIN_INTERVAL`，不要并发请求。
- 主源失败时优先查看 `references/fallback-sources.md`。

## iwencai Key

只有 iwencai 语义搜索需要 key：

```bash
export IWENCAI_API_KEY="your_key_here"
export IWENCAI_BASE_URL="https://openapi.iwencai.com"
```

不要把 key 写入 README、SKILL.md、references 或脚本文件。

## 输出约束

使用本 Skill 生成分析结果时，应说明：

- 数据源。
- 数据日期、公告日期或报告日期。
- 缺失字段、接口为空、非交易日、无 key、无机构覆盖等 caveat。
- 估值和题材判断必须区分事实与推断。

本项目只提供数据访问工具，不构成投资建议。

## 致谢

本项目 fork 并改造自 [simonlin1212/a-stock-data](https://github.com/simonlin1212/a-stock-data)。感谢原作者 Simon Lin 对 A 股数据端点、接口修复、数据源优先级和防封策略的整理与开源。

## License

本项目遵守原项目的开源协议，使用 [Apache License 2.0](./LICENSE)。
