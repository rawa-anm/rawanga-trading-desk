# Writing Trading Strategies — Rawanga Trading Desk

Welcome! This guide explains how to write, test and share your own strategies and
indicators in **Rawanga Trading Desk** — the portable charting & signals terminal.

A strategy is just **plain, vectorized Python code**. You do not install anything,
you do not import anything: you write a few lines in the built-in editor and the
engine runs them over the price data.

---

## 1. Introduction — what is a strategy?

A **strategy** is a small piece of **vectorized Python code** that the terminal's
engine executes on every bar of the chart.

- "Vectorized" means you work with **whole columns of data at once**, not with
  loops. Instead of *"for each candle, do…"* you write expressions that apply to
  the entire series in one line.
- The engine gives you ready-made **series**: `open`, `high`, `low`, `close`,
  `volume`. Each one is a `pandas.Series` aligned to the candles on the chart.
- You describe **when to enter** a trade (`entry(...)`) and **when to exit**
  (`exit(...)`), and/or **what to draw** on the chart (`plot(...)`, `shape(...)`,
  `hline(...)`).

Each strategy output is a set of bars where `long`, `short` and `exit` are `True`.
The backtest and the live scheduler use exactly those bars.

> There are two flavors of code you can run in the editor:
> - a **strategy** — declares entries/exits (Compile → registered in the engine);
> - an **indicator** — only draws things (To chart → overlay on the chart).
> The same code can do both.

---

## 2. The available names (full API)

These names are already defined for you. You never import them — just use them.

### Series (price data)

| Name | Type | Meaning |
|------|------|---------|
| `open`   | `pandas.Series` | Open price of each bar |
| `high`   | `pandas.Series` | High price |
| `low`    | `pandas.Series` | Low price |
| `close`  | `pandas.Series` | Close price |
| `volume` | `pandas.Series` | Volume |

All series share the same index (the candle timestamps), so you can compare and
combine them directly.

### Inputs (user parameters)

```python
value = inp(name, default, title='', type='float')
```

Declares a **user-adjustable parameter** that appears in the settings panel.
Returns the current value of the parameter.

- `name` — internal key (string), e.g. `'fast'`.
- `default` — default value.
- `title` — human-readable label shown in the UI (optional).
- `type` — one of `'int'`, `'float'`, `'bool'`, `'string'` (default `'float'`).

```python
fast  = inp('fast', 12, 'Fast EMA', 'int')
mult  = inp('mult', 1.5, 'Volume multiplier', 'float')
enabled = inp('enabled', True, 'Use filter', 'bool')
label = inp('label', 'MACD', 'Series label', 'string')
```

The editor scans your code and shows every `inp(...)` on one line as a separate
setting. Always assign the result to a variable:

```python
period = inp('period', 14, 'RSI length', 'int')   # ✅ good
inp('period', 14, 'RSI length', 'int')            # ❌ value is lost
```

### Indicators

All indicators return `pandas.Series` (or a tuple of them) aligned to the chart.

| Function | Returns | Notes |
|----------|---------|-------|
| `sma(a, n)` | Series | Simple moving average |
| `ema(a, n)` | Series | Exponential moving average |
| `rma(a, n)` | Series | Wilder's smoothing (used inside RSI/ATR) |
| `wma(a, n)` | Series | Weighted moving average |
| `stdev(a, n)` | Series | Rolling standard deviation |
| `highest(a, n)` | Series | Highest value over `n` bars |
| `lowest(a, n)` | Series | Lowest value over `n` bars |
| `change(a)` | Series | Difference vs. previous bar |
| `rsi(a, n=14)` | Series | Relative Strength Index |
| `macd(a, fast=12, slow=26, signal=9)` | `(macd, signal, hist)` | MACD line, signal line, histogram |
| `bb(a, n=20, k=2.0)` | `(upper, basis, lower)` | Bollinger Bands |
| `atr(n=14)` | Series | Average True Range (uses high/low/close) |
| `supertrend(period=7, mult=2.5)` | `(direction, line)` | `direction` is `+1` up / `-1` down |
| `adx(di_len=14, smooth=14)` | `(plus_di, minus_di, adx)` | Trend strength |
| `donchian(n=10)` | `(upper, lower)` | Donchian channel |

Examples:

```python
ma = sma(close, 50)
er = ema(close, 21)

# MACD -> (macd, signal, hist)
m = macd(close)
macd_line   = m[0]
macd_signal = m[1]
macd_hist   = m[2]

# Bollinger -> (upper, basis, lower)
b = bb(close, 20, 2.0)
bb_upper = b[0]
bb_basis = b[1]
bb_lower = b[2]

# Supertrend -> (direction, line)
st = supertrend(7, 2.5)
st_dir  = st[0]
st_line = st[1]

# ADX -> (plus_di, minus_di, adx)
a = adx(14, 14)
plus_di  = a[0]
minus_di = a[1]
adx_val  = a[2]

# Donchian -> (upper, lower)
d = donchian(10)
don_hi = d[0]
don_lo = d[1]
```

> `atr`, `supertrend`, `adx` and `donchian` read `high`/`low`/`close` internally —
> you just pass the length parameters.

> ℹ️ **Multi-value indicators return a tuple.** Access the parts by **index** —
> `m[0]`, `m[1]`, … — or inline, e.g. `macd(close)[2]`. **Tuple unpacking**
> (`a, b = f(...)`) is **not allowed** by the sandbox and will be rejected during
> **Check** (see “Common mistakes” §10).

### Comparisons (crosses)

```python
crossover(a, b)   # True on the bar where a crosses ABOVE b
crossunder(a, b)  # True on the bar where a crosses BELOW b
```

`a` and `b` can be a series or a number. Returns a boolean series.

```python
entry('long',  crossover(ema_fast, ema_slow))
entry('short', crossunder(ema_fast, ema_slow))
```

### Utility

| Function | Returns | Meaning |
|----------|---------|---------|
| `nz(x, repl=0)` | Series/scalar | Replace `NaN` with `repl` |
| `na(x)` | bool / bool-series | `True` where the value is `NaN` |
| `series(x)` | Series | Turn a scalar/array into a Series aligned to the chart |

```python
r_clean = nz(rsi(close, 14), 50)   # NaNs at the start → 50
is_missing = na(close)
```

### Signals

```python
entry(side, cond)   # side: 'long' or 'short'
exit(cond)
```

- `entry('long', cond)` — open/reverse to a **long** when `cond` is `True`.
- `entry('short', cond)` — open/reverse to a **short** when `cond` is `True`.
- `exit(cond)` — **close** the current position when `cond` is `True`.

`cond` must be a boolean series (a comparison result). Nothing is sent unless a
condition fires.

```python
entry('long',  crossover(ema_fast, ema_slow))
entry('short', crossunder(ema_fast, ema_slow))
exit(crossunder(close, ema_slow))
```

### Drawing (indicator output)

```python
plot(title, series, color='#2962ff', width=1, style='line')
shape(title, cond, color, location='abovebar', shape='circle')
hline(title, value, color)
```

| Function | Purpose |
|----------|---------|
| `plot(...)` | Draw a line (or histogram) of a series |
| `shape(...)` | Draw a marker on bars where `cond` is `True` |
| `hline(...)` | Draw a horizontal level (e.g. 30 / 70 for RSI) |

- `plot`: `style` can be `'line'` (default) or `'histogram'`; `width` is the line
  thickness (1–4).
- `shape`: `location` is `'abovebar'` or `'belowbar'` (also `'top'`/`'bottom'`);
  `shape` is `'circle'`, `'triangleup'`, `'triangledown'`, or `'square'`.
- `hline`: `value` is the price/level of the horizontal line.

```python
plot('SMA 50', sma(close, 50), '#ff9800', 2, 'line')
plot('MACD hist', macd(close)[2], '#26a69a', 1, 'histogram')
hline('Zero', 0, '#787b86')
shape('Buy',  crossover(close, sma(close, 50)), '#26a69a', 'belowbar', 'triangleup')
shape('Sell', crossunder(close, sma(close, 50)), '#ef5350', 'abovebar', 'triangledown')
```

---

## 3. How to write conditions

A comparison between series produces a **boolean series** — one `True`/`False`
value per bar:

```python
bull = ema_fast > ema_slow
oversold = rsi(close, 14) < 30
strong = atr(14) > 1.5
```

To combine conditions, use the **bitwise operators** — they work element-by-element
across the whole series:

| You want | Use | Example |
|----------|-----|---------|
| AND | `&` | `(ema_fast > ema_slow) & (volume > vol_ma)` |
| OR  | `\|` | `(r < 30) \| (r > 70)` |
| NOT | `~` | `~(ema_fast > ema_slow)` |

> ⚠️ **Do NOT use `and`, `or`, `not` on series.** Python's `and`/`or`/`not` are
> meant for single truth values and will raise an error
> (*"The truth value of a Series is ambiguous"*). Always wrap each comparison in
> parentheses and join them with `&`, `|`, `~`:

```python
# ✅ correct
cond = (ema_fast > ema_slow) & (rsi(close, 14) < 55)

# ❌ wrong — raises an error
cond = (ema_fast > ema_slow) and (rsi(close, 14) < 55)
```

Always parenthesize the individual comparisons, because in Python `&` binds
tighter than `>`:

```python
# ✅
bull = (ema_fast > ema_slow) & (close > ema_fast)

# ❌ parsed as ema_fast > (ema_slow & close) > ema_fast
bull = ema_fast > ema_slow & close > ema_fast
```

You can compare a series with a number, or two series with each other, freely.

---

## 4. Sandbox rules (safety)

Your code runs in a **restricted sandbox**. Before anything is executed, the code
is inspected (AST-whitelist): it must be safe and purely vectorized.

**Forbidden — will be rejected before running:**

- `import` / `from ... import ...`
- `eval`, `exec`, `open`
- any file or network access
- loops: `for`, `while`
- generators and list/set/dict comprehensions (`[... for ...]`, `(... for ...)`)
- function/class/lambda definitions (`def`, `class`, `lambda`)
- `with`, `try`/`except`, `raise`, `yield`, `await`
- `global`, `nonlocal`, `del`
- **dunder attributes** — anything starting with `__` (e.g. `__class__`,
  `__globals__`)

**Allowed — safe, vectorized building blocks:**

- All the API names above (`sma`, `ema`, `rsi`, `entry`, `plot`, …).
- Safe **Series/DataFrame methods**, including (not exhaustive):
  `shift`, `fillna`, `ffill`, `bfill`, `dropna`, `interpolate`,
  `rolling`, `ewm`, `expanding`, `mean`, `sum`, `std`, `var`, `min`, `max`,
  `median`, `abs`, `clip`, `where`, `diff`, `cumsum`, `cummax`, `cummin`,
  `cumprod`, `pct_change`, `astype`, `isna`, `notna`, `rank`, `round`,
  `pow`, `replace`, `any`, `all`, `count`, `first`, `last`, `head`, `tail`,
  `idxmin`, `idxmax`, and the operator-methods `le`, `ge`, `lt`, `gt`, `eq`, `ne`,
  `add`, `sub`, `mul`, `div`, `mod`.
- **numpy** helpers via `np.`: `np.maximum`, `np.minimum`, `np.where`, `np.abs`,
  `np.log`, `np.log10`, `np.sqrt`, `np.exp`, `np.clip`, `np.sign`,
  `np.nan_to_num`, `np.isnan`, `np.isfinite`, `np.arange`.
- Built-ins: `bool`, `float`, `int`, `abs`, `round`, `min`, `max`, `len`.
- `df` (the full OHLCV DataFrame), `pd`, `np`.

**Good to know:**

- Because values are vectorized, `if` on a series does not work. Use `np.where` /
  `.where(...)` instead of branching:

```python
# ❌ if on a series — ambiguous
# if close > open: ...

# ✅ vectorized choice
direction = np.where(close > open, 1, -1)
stop = np.minimum(close, ema(close, 20))   # element-wise minimum
```

- Read-only access to data only. No side effects, no I/O, no persistence.

---

## 5. Step-by-step example #1 — EMA crossover

Idea: go **long** when the fast EMA crosses above the slow EMA, go **short** when it
crosses below.

```python
# ── Inputs ────────────────────────────────────────────────
fast = inp('fast', 12, 'Fast EMA', 'int')
slow = inp('slow', 26, 'Slow EMA', 'int')

# ── Indicators ───────────────────────────────────────────
ema_fast = ema(close, fast)
ema_slow = ema(close, slow)

# ── Signals ──────────────────────────────────────────────
entry('long',  crossover(ema_fast, ema_slow))
entry('short', crossunder(ema_fast, ema_slow))
```

Line by line:

1. `fast` / `slow` — two parameters you can tweak in the settings panel.
2. `ema(...)` — compute the two averages over the whole chart at once.
3. `entry('long', ...)` — a long is fired on the exact bar where the fast line
   crosses from below to above the slow line.
4. `entry('short', ...)` — symmetrical: a short on the downward cross.

Optional additions:

```python
# Only trade when volatility is meaningful
filter_ok = atr(14) > sma(atr(14), 20)

entry('long',  crossover(ema_fast, ema_slow) & filter_ok)
entry('short', crossunder(ema_fast, ema_slow) & filter_ok)

# Flat exit when the trend flips back
exit(crossunder(ema_fast, ema_slow))
```

---

## 6. Step-by-step example #2 — RSI reversal

Idea: buy when RSI is oversold, sell when it is overbought.

```python
# ── Inputs ────────────────────────────────────────────────
n  = inp('n', 14, 'RSI length', 'int')
lo = inp('lo', 30, 'Oversold', 'float')
hi = inp('hi', 70, 'Overbought', 'float')

# ── Indicator ────────────────────────────────────────────
r = rsi(close, n)

# ── Signals ──────────────────────────────────────────────
entry('long',  r < lo)
entry('short', r > hi)
```

Explanation:

1. `rsi(close, n)` gives the RSI series.
2. `r < lo` is `True` on every bar where RSI is below 30 → long.
3. `r > hi` is `True` on every bar where RSI is above 70 → short.

> `r < 30` stays `True` for many consecutive bars while RSI remains oversold. The
> engine's signal layer collapses a run of equal signals, so you do not get a new
> trade on every candle. If you only want the *first* dip below 30, combine it
> with a cross:

```python
entry('long',  crossover(r, lo) )
entry('short', crossunder(r, hi))
```

Add a trend filter to avoid buying knives:

```python
uptrend = close > sma(close, 200)
entry('long',  (r < lo) & uptrend)
entry('short', (r > hi) & ~uptrend)
```

---

## 7. Indicator example (drawing only)

An indicator does not trade — it only draws. Use it with **To chart**.

```python
# ── Inputs ────────────────────────────────────────────────
n = inp('n', 50, 'SMA length', 'int')

# ── Computation ──────────────────────────────────────────
ma = sma(close, n)

# ── Drawing ──────────────────────────────────────────────
plot('SMA', ma, '#ff9800', 2, 'line')
hline('Zero', 0, '#787b86')
shape('Buy',  crossover(close, ma), '#26a69a', 'belowbar', 'triangleup')
shape('Sell', crossunder(close, ma), '#ef5350', 'abovebar', 'triangledown')
```

What appears on the chart:

- an orange **line** with the SMA(50);
- a grey dashed **horizontal line** at 0;
- green **triangle-up** markers below the bars on upward crosses of the close over
  the SMA;
- red **triangle-down** markers above the bars on downward crosses.

An RSI panel looks like this:

```python
n = inp('n', 14, 'RSI length', 'int')

r = rsi(close, n)

plot('RSI', r, '#9c27b0', 2, 'line')
hline('Overbought', 70, '#ef5350')
hline('Oversold', 30, '#26a69a')
```

---

## 8. Export / import — sharing strategies

Every compiled strategy can be downloaded as a single **`.rwd.json`** file and
shared with anyone; they import it in one click.

- **Export** button → downloads `<Title>.rwd.json` for the selected strategy.
- **Import** button → pick a `.rwd.json` file → the strategy is validated and
  registered immediately.

The file is plain JSON with this structure:

```json
{
  "kind": "rawanga-trading-desk-strategy",
  "version": 1,
  "key": "my_strategy",
  "title": "My Strategy",
  "source": "fast = inp('fast', 12, 'Fast EMA', 'int')\n...",
  "inputs": [
    { "var": "fast", "kind": "int", "name": "Fast EMA", "default": "12", "_val": 12 }
  ],
  "author": "Andrei Maltsev (Rawanga)",
  "license": "Apache-2.0",
  "homepage": "https://rawanga.es"
}
```

| Field | Meaning |
|-------|---------|
| `kind` | File type marker (always `rawanga-trading-desk-strategy`) |
| `version` | Format version (currently `1`) |
| `key` | Internal id (derived from the title) |
| `title` | Display name |
| `source` | **The full strategy code** (the important part) |
| `inputs` | Auto-detected parameters |
| `author` | Author line |
| `license` | License of the shared code |
| `homepage` | Project link |

**How to share:**

1. Write and **Check** your strategy.
2. Click **Export** → save `MyStrategy.rwd.json`.
3. Send the file (chat, e-mail, repository, gist).
4. The recipient clicks **Import**, selects the file — done. The strategy appears
   in their list, ready to run.

> The recipient's machine re-validates the code through the same sandbox, so a
> shared file can never execute anything unsafe. Only the `source` field matters
> for the logic — the other fields are metadata.

---

## 9. Compiling

Three buttons drive the workflow in the editor:

| Button | What it does |
|--------|--------------|
| 🔎 **Check** | Validates the code (safety + syntax) **and runs a trial backtest** on real bars. Reports errors and a summary: bars, `long`/`short`/`exit` counts, number of trades. |
| ⚙ **Compile** | Same validation, then **registers the strategy in the engine** under a key. It becomes available to the scheduler and the backtester immediately (no restart). |
| 🧷 **To chart** | Runs the code as an **indicator** and overlays its `plot`/`shape`/`hline` output on the current chart. Trades are not registered. |

Recommended flow:

1. Paste your code.
2. Click **Check** → fix any errors until it says *“check passed”* and the trial
   backtest looks sane.
3. Click **Compile** → the strategy is saved (name it in the *Strategy name*
   field first). The key is derived from the name, e.g. `My Strategy` → `my_strategy`.
4. To visualize an indicator, click **To chart** instead.

Notes:

- The name must be unique; the reserved keys `stv3`, `rawa_system` and `trend`
  are taken by built-in strategies.
- Compiled strategies are persisted and re-registered automatically on startup.
- You can delete a compiled strategy from the list of saved strategies.

---

## 10. Common mistakes and tips

**1. Using `and` / `or` / `not` on series**

```python
# ❌ "The truth value of a Series is ambiguous"
cond = (r < 30) and (close > ma)

# ✅
cond = (r < 30) & (close > ma)
```

**2. Forgetting parentheses around comparisons**

```python
# ❌ operator precedence bug
cond = close > ema_fast & volume > vol_ma

# ✅
cond = (close > ema_fast) & (volume > vol_ma)
```

**3. Using loops**

```python
# ❌ for ... is not allowed
for i in range(len(close)):
    ...

# ✅ express it vectorized
mom = close / close.shift(10) - 1
```

**4. Forgetting to assign `inp(...)`**

```python
# ❌ the input is declared but never used
inp('len', 14, 'Length', 'int')

# ✅
length = inp('len', 14, 'Length', 'int')
```

**5. `if` on a series**

```python
# ❌ ambiguous
# if close > open: side = 1

# ✅
side = np.where(close > open, 1, -1)
```

**6. Comparing an empty / early region**

Indicators like `sma(close, 200)` are `NaN` for the first bars. Comparisons with
`NaN` are `False`, which is what you want — but if you must substitute, use `nz`:

```python
ma = nz(sma(close, 200), close)
```

**7. Tuning inputs**

Prefer `inp(...)` over hard-coded numbers, so you can optimize without editing the
code. The parameters appear in the settings panel after compilation.

**8. Keeping entries and exits consistent**

`entry('long', …)` also **reverses** a short. If you want a flat exit instead, use
`exit(...)`. Decide consciously which one you need.

**9. Plotting only when you mean an indicator**

`plot`/`shape`/`hline` are harmless in a strategy, but they only affect the chart
when you press **To chart**. Signals come from `entry`/`exit`.

**10. Test on several symbols and timeframes**

A strategy that looks great on one symbol can be noise elsewhere. Use **Check**
(and the backtester) on several markets and timeframes before trusting it.

**11. Tuple unpacking (`a, b = f(...)`) is not allowed**

The sandbox rejects tuple-unpacking assignments during **Check**. Multi-value
indicators return a tuple — index it instead:

```python
# ❌ 'unknown name' error during Check
macd_line, macd_signal, macd_hist = macd(close)

# ✅
m = macd(close)
macd_line   = m[0]
macd_signal = m[1]
macd_hist   = m[2]

# inline also works:
hist = macd(close)[2]
```

**Handy building blocks**

```python
# ATR-based stop distance as a series
stop_dist = atr(14) * 2

# Normalized momentum
roc = close / close.shift(20) - 1

# Volatility filter
calm = stdev(close, 20) < sma(stdev(close, 20), 50)

# Supertrend direction
st = supertrend(10, 3.0)
st_dir = st[0]
entry('long',  (st_dir == 1) & (st_dir.shift(1) == -1))
entry('short', (st_dir == -1) & (st_dir.shift(1) == 1))

# Bollinger breakout
b = bb(close, 20, 2.0)
upper = b[0]
lower = b[2]
entry('long',  crossover(close, upper))
entry('short', crossunder(close, lower))
```

---

## Disclaimer

**Not investment advice. Trading is at your own risk.**

The software is provided “as is”, without warranty of any kind. Past performance
does not guarantee future results. Always test your strategies and never risk more
than you can afford to lose.

---

© 2026 Andrei Maltsev · Rawanga AI · https://rawanga.es
