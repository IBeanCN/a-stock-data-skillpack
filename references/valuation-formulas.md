# 估值公式

实现位置：`scripts/a_stock_client.py`。

## `forward_pe(price, eps_forward)`

```text
forward_pe = price / eps_forward
```

`eps_forward <= 0` 时没有可解释 PE。

## `pe_digestion(current_pe, cagr, target_pe=30)`

```text
years = log(current_pe / target_pe) / log(1 + cagr)
```

- `current_pe <= target_pe` → `0.0`（已经消化到目标估值）。
- `cagr <= 0`（盈利持平或下降）→ `inf`（永远消化不到，不是 0）。
- 适合粗略估算，不是预测模型。

## `calc_peg(pe, cagr)`

```text
PEG = PE / (CAGR * 100)
```

`cagr` 用小数，例如 20% 写 `0.20`。

## `full_valuation(code)` 的 `digest_years`

组合行情、一致预期 EPS 和估值公式。使用前确认一致预期数据非空。
`digest_years` 直接复用 `pe_digestion()`，四种分支：

| 情形 | `digest_years` |
|---|---|
| 当年 EPS 为正、前向 PE ≤ 30x | `0.0` |
| 当年 EPS 为正、前向 PE > 30x、预期增长为正 | 消化年数 |
| 前向 PE > 30x，但下一年预测缺失或盈利不增长 | `None`（JSON `null`） |
| 当年 EPS 缺失或不为正 | `None`（JSON `null`） |

`None` **不是 0**：不要读成「已经消化到 30x」，它表示得不出有限年数。上游 v3.10.2（#58）修的就是这一点。

`mcap_yi` 是**总市值**（腾讯行情下标 45，与 `tencent_quote()` 同名口径一致）；需要流通市值用 `tencent_quote()` 的
`float_mcap_yi`（下标 44）。v3.10.2 之前本端点误取了下标 44。
