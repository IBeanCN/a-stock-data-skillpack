# 估值公式

实现位置：`scripts/a_stock_client.py`。

## `forward_pe(price, eps_forward)`

```text
forward_pe = price / eps_forward
```

`eps_forward <= 0` 时没有可解释 PE。

## `pe_digestion(current_pe, target_pe, growth_rate)`

```text
years = log(current_pe / target_pe) / log(1 + growth_rate)
```

适合粗略估算，不是预测模型。

## `calc_peg(pe, cagr)`

```text
PEG = PE / (CAGR * 100)
```

`cagr` 用小数，例如 20% 写 `0.20`。

## `full_valuation(code)`

组合行情、一致预期 EPS 和估值公式。使用前确认一致预期数据非空。
