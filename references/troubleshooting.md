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

## iwencai 401

配置 `IWENCAI_API_KEY`。无 key 时不要使用 iwencai 端点。

## 接口返回空

先确认：交易日、日期格式、股票代码、是否有机构覆盖、是否停牌、是否源站改版。

## smoke test

```bash
python3 scripts/smoke_test_endpoints.py
python3 scripts/smoke_test_endpoints.py --network
```

## v3.7 数据源边界

- 东财市场路由正确不代表 ETF 具有个股资金流；部分 ETF 仍会返回空。
- baostock 不支持北交所；新浪北交所复权因子可能 404。
- 申万 XLS 出现 SSL 错误时更新 CA/certifi 并检查代理。
- 社融仅支持 2021 年起新表格式；PMI 主字段或页面措辞变更时会抛错而非静默返回空。
