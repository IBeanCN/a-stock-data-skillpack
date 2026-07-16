# 通用约定

## 依赖

```bash
pip install -r requirements.txt
```

- `requests`：HTTP 数据源。
- `pandas`：DataFrame 输出和表格解析。
- `lxml`：`pandas.read_html()` 解析 HTML 表格。
- `mootdx`：通达信 TCP 行情、财务快照、F10。
- `stockstats`：技术指标扩展，当前端点不强制使用。

环境检查：

```bash
python3 scripts/validate_env.py
```

## iwencai key

仅 iwencai 语义搜索需要 key：

```bash
export IWENCAI_API_KEY="your_key_here"
export IWENCAI_BASE_URL="https://openapi.iwencai.com"
```

只从环境变量读取 key。不要把 key 写进 README、SKILL.md、references、脚本或验证目录。

## Ticker 归一化

`normalize_code()` 支持：

| 输入 | 输出 |
|---|---|
| `688017` | `688017` |
| `SH688017` / `sh688017` | `688017` |
| `688017.SH` / `688017.sh` | `688017` |
| `SZ000001` | `000001` |
| `BJ832000` | `832000` |

`get_prefix()` 规则：

| 代码开头 | 前缀 |
|---|---|
| `6` / `9` | `sh` |
| `8` | `bj` |
| 其他 | `sz` |

## 数据源优先级

行情、K线、实时价、市值、财务快照能从通达信或腾讯拿到的，优先不用东财。东财只用于独有数据，并且必须经 `em_get()` 串行限流。

| 优先级 | 数据源 | 用途 | 风险 |
|---|---|---|---|
| 1 | mootdx 通达信 | K线、五档、逐笔、财务快照、F10 | 不封 IP，但 TCP 7709 可能受网络限制 |
| 2 | 腾讯财经 | 实时价、PE/PB、市值、换手率、涨跌停、指数、ETF | 低 |
| 3 | 同花顺 | 热点、题材归因、北向、热榜、一致预期 | 低，部分接口需 UA |
| 4 | 百度股市通 | K线带均线 | 低 |
| 5 | 新浪财经 | 财报三表、ETF 期权、备用资金流 | 低 |
| 6 | 巨潮 cninfo | 公告、互动易 | 低 |
| 7 | iwencai | NL 语义搜索 | 需 key |
| 末位 | 东财 | 研报、资金流、龙虎榜、解禁、两融、大宗、股东户数、分红、新闻、打板、人气 | 有风控 |

## 东财防封

`em_get()` 内置：

- session 复用。
- 默认 `trust_env=False`，不继承系统代理。
- 直连失败后可 fallback 到环境代理。
- `EM_MIN_INTERVAL=1.0` 秒最小间隔。
- 0.1-0.5 秒随机抖动。
- 三次直连重试。

批量筛选时把 `EM_MIN_INTERVAL` 调大到 1.5-2 秒。不要并发请求东财接口。

## 输出要求

回答中必须说明：

- 数据源。
- 观察日期、公告日期或报告日期。
- 缺失字段。
- 接口为空、无 key、无机构覆盖、非交易日、源被风控等 caveat。
- 如果包含估值或题材判断，必须区分事实和推断。

不要用训练数据补当前市场价格、资金流、公告、新闻、研报。
