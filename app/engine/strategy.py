# Copyright 2026 Andrei Maltsev (Rawanga)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
strategy.py — strategy editor and engine in Python (sandbox).

The user writes a strategy in Python (vectorised, pandas). Before running,
the code is SAFETY-CHECKED (AST whitelist: no import/eval/exec/open/dunder,
only allowed functions and methods), then executed in a restricted environment
and dry-run on real bars. Registered only after success.

Public editor API (available names):
  open series:         open, high, low, close, volume
  user inputs:         inp(name, default, title='', type='float')   # int|float|bool|string
  indicators:          sma, ema, rma, wma, stdev, highest, lowest, change,
                       rsi, macd, bb, atr, supertrend, adx, donchian
  comparison:          crossover(a, b), crossunder(a, b)
  misc:                nz(x, repl=0), na(x), series(x)
  signals:             entry(side, cond), exit(cond)     # side: 'long'|'short'
  drawing:             plot(title, series, color, width, style),
                       shape(title, cond, color, location, shape),
                       hline(title, value, color)
"""
from __future__ import annotations

import ast
import re

import numpy as np
import pandas as pd

from app.indicators import ta
from app import paths as _paths

STRAT_DIR = _paths.PINE_DIR  # user strategies directory (kept for compatibility)

_INPUT_RE = re.compile(
    r"""^\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*inp\s*\(\s*
        (?P<name>['"][^'"]*['"])\s*,\s*
        (?P<default>-?[\d.]|true|false|['"][^'"]*['"]|[^\s,)]+)\s*
        (?:,\s*(?P<title>['"][^'"]*['"]))?\s*
        (?:,\s*(?P<kind>['"][^'"]*['"]))?\s*\)""",
    re.VERBOSE | re.MULTILINE,
)

# ── Whitelists ──────────────────────────────────────────────────────
_HELPER_CALLS = {
    "inp", "sma", "ema", "rma", "wma", "stdev", "highest", "lowest", "change",
    "rsi", "macd", "bb", "atr", "supertrend", "adx", "donchian",
    "crossover", "crossunder", "nz", "na", "series",
    "entry", "exit", "plot", "shape", "hline",
    "bool", "float", "int", "abs", "round", "min", "max", "len",
}
# Series/DataFrame methods allowed to call (safe, no I/O)
_ALLOWED_METHODS = {
    "shift", "fillna", "ffill", "bfill", "dropna", "interpolate",
    "rolling", "ewm", "expanding",
    "mean", "sum", "std", "var", "min", "max", "median", "abs", "clip",
    "where", "diff", "cumsum", "cummax", "cummin", "cumprod", "pct_change",
    "astype", "isna", "notna", "rank", "round", "pow", "replace",
    "le", "ge", "lt", "gt", "eq", "ne", "add", "sub", "mul", "div", "mod",
    "any", "all", "count", "first", "last", "head", "tail", "idxmin", "idxmax",
}
_ALLOWED_NP = {
    "absolute", "maximum", "minimum", "where", "isnan", "isfinite",
    "log", "log10", "sqrt", "exp", "clip", "sign", "nan_to_num", "arange",
}
_ALLOWED_NAMES = {
    "df", "pd", "np", "True", "False", "None",
    "open", "high", "low", "close", "volume",
} | _HELPER_CALLS
_FORBIDDEN_NODES = (
    ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef,
    ast.ClassDef, ast.Lambda, ast.For, ast.AsyncFor, ast.While, ast.With,
    ast.AsyncWith, ast.Try, ast.Global, ast.Nonlocal, ast.Delete, ast.Raise,
    ast.Yield, ast.YieldFrom, ast.Await,
)


class StrategyError(Exception):
    pass


def _collect_inputs(src: str) -> tuple[dict, list[dict]]:
    inputs, meta = {}, []
    for m in _INPUT_RE.finditer(src):
        var = m.group("var")
        name = m.group("name").strip('"\'')
        default = m.group("default")
        title = (m.group("title") or f'"{var}"').strip('"\'')
        kind = (m.group("kind") or '"float"').strip('"\'') or "float"
        d = default
        if kind == "int":
            try: d = int(float(default))
            except Exception: d = 0
        elif kind == "float":
            try: d = float(default)
            except Exception: d = 0.0
        elif kind == "bool":
            d = str(default).lower() == "true"
        else:
            d = str(default).strip('"\'')
        inputs[var] = kind
        meta.append({"var": var, "kind": kind, "name": title, "default": default, "_val": d})
    return inputs, meta


def validate(src: str) -> dict:
    """AST safety check + input collection. Returns {'ok','errors','inputs'}."""
    errors: list[dict] = []
    if not src or not src.strip():
        return {"ok": False, "errors": [{"line": 0, "level": "error", "msg": "empty code"}],
                "inputs": []}
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return {"ok": False, "errors": [{"line": e.lineno or 0, "level": "error",
                "msg": f"syntax: {e.msg}"}], "inputs": []}

    _inputs, inputs_meta = _collect_inputs(src)
    assigned: set[str] = set()
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        for tgt in targets:
            for sub in ast.walk(tgt):
                if isinstance(sub, ast.Name):
                    assigned.add(sub.id)
    allowed_names = set(_ALLOWED_NAMES) | set(_inputs.keys()) | assigned

    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_NODES):
            errors.append({"line": getattr(node, "lineno", 0), "level": "error",
                           "msg": f"{type(node).__name__} is not allowed"})
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            errors.append({"line": getattr(node, "lineno", 0), "level": "error",
                           "msg": "generators/list comprehensions are not allowed"})
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                errors.append({"line": getattr(node, "lineno", 0), "level": "error",
                               "msg": "forbidden attribute"})
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in allowed_names:
                errors.append({"line": node.lineno, "level": "error",
                               "msg": f"unknown name '{node.id}'"})
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id not in _HELPER_CALLS:
                errors.append({"line": node.lineno, "level": "error",
                               "msg": f"function '{f.id}' is not allowed"})
            if isinstance(f, ast.Attribute):
                # allow only Series/DataFrame methods and np.*
                base = f.value
                base_name = base.id if isinstance(base, ast.Name) else None
                if base_name == "np":
                    ok = f.attr in _ALLOWED_NP
                elif base_name == "pd":
                    ok = f.attr in {"Series", "DataFrame"}
                else:
                    ok = f.attr in _ALLOWED_METHODS
                if not ok:
                    errors.append({"line": node.lineno, "level": "error",
                                   "msg": f"method/function '{f.attr}' is not allowed"})
    # note: `if <series>:` would error at runtime — the docs suggest the right form
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            t = node.test
            if not isinstance(t, (ast.Compare,)) or True:
                pass
    return {"ok": not errors, "errors": errors, "inputs": inputs_meta}


# ── Helpers available to strategy code ───────────────────────────────
def _S(a, index=None):
    if isinstance(a, pd.Series):
        return a
    return pd.Series(a, index=index)


def _mk_helpers(df: pd.DataFrame) -> dict:
    def sma(a, n): return ta.sma(_S(a, df.index), int(n))
    def ema(a, n): return ta.ema(_S(a, df.index), int(n))
    def rma(a, n): return ta.rma(_S(a, df.index), int(n))
    def wma(a, n): return _S(a, df.index).rolling(int(n)).apply(
        lambda x: np.average(x, weights=np.arange(1, len(x) + 1)), raw=True)
    def stdev(a, n): return _S(a, df.index).rolling(int(n)).std(ddof=0)
    def highest(a, n): return _S(a, df.index).rolling(int(n)).max()
    def lowest(a, n): return _S(a, df.index).rolling(int(n)).min()
    def change(a): return _S(a, df.index).diff()
    def rsi(a, n=14): return ta.rsi(_S(a, df.index), int(n))
    def macd(a, f=12, s=26, sig=9): return ta.macd(_S(a, df.index), int(f), int(s), int(sig))
    def bb(a, n=20, k=2.0): return ta.bollinger(_S(a, df.index), int(n), float(k))
    def atr(n=14): return ta.atr(df, int(n))
    def supertrend(period=7, mult=2.5): return ta.supertrend(df, int(period), float(mult))
    def adx(di=14, smooth=14): return ta.adx(df, int(di), int(smooth))
    def donchian(n=10): return ta.donchian(df, int(n))
    def crossover(a, b):
        A, B = _S(a, df.index), _S(b, df.index)
        return (A > B) & (A.shift(1) <= B.shift(1))
    def crossunder(a, b):
        A, B = _S(a, df.index), _S(b, df.index)
        return (A < B) & (A.shift(1) >= B.shift(1))
    def nz(x, repl=0):
        return _S(x, df.index).fillna(repl) if isinstance(x, pd.Series) else (
            repl if x is None or (isinstance(x, float) and np.isnan(x)) else x)
    def na(x):
        return pd.isna(x) if not isinstance(x, pd.Series) else x.isna()
    def series(x):
        return _S(x, df.index)
    return {
        "sma": sma, "ema": ema, "rma": rma, "wma": wma, "stdev": stdev,
        "highest": highest, "lowest": lowest, "change": change, "rsi": rsi,
        "macd": macd, "bb": bb, "atr": atr, "supertrend": supertrend, "adx": adx,
        "donchian": donchian, "crossover": crossover, "crossunder": crossunder,
        "nz": nz, "na": na, "series": series,
        "abs": abs, "round": round, "min": np.minimum, "max": np.maximum,
        "len": len, "pd": pd, "np": np,
    }


def build_strategy(src: str):
    """Compile the source into a strategy(df, **inputs) function. Returns (fn, meta)."""
    tr = validate(src)
    if not tr["ok"]:
        return None, tr
    input_meta = tr["inputs"]
    defaults = {im["var"]: im["_val"] for im in input_meta}

    def strategy(df, **inputs):
        params = {**defaults, **{k: v for k, v in inputs.items() if k in defaults}}
        false = pd.Series(False, index=df.index).fillna(False)
        acc = {"long": false.copy(), "short": false.copy(), "exit": false.copy()}
        plots: list = []

        def _cond_series(cond):
            if cond is None:
                return pd.Series(True, index=df.index)
            c = cond if isinstance(cond, pd.Series) else pd.Series(bool(cond), index=df.index)
            return c.fillna(False)

        def inp(name, default=None, title="", type="float"):  # noqa: A002
            if name in params:
                v = params[name]
            else:
                v = default
            if type == "int":
                try: return int(float(v))
                except Exception: return 0
            if type == "float":
                try: return float(v)
                except Exception: return 0.0
            if type == "bool":
                return v if isinstance(v, bool) else str(v).lower() == "true"
            return v

        def entry(side, cond=None):
            key = side if side in ("long", "short") else "long"
            acc[key] = acc[key] | _cond_series(cond)

        def exit(cond=None):  # noqa: A001
            acc["exit"] = acc["exit"] | _cond_series(cond)

        def plot(title, srs, color="#2962ff", width=1, style="line"):
            s = srs if isinstance(srs, pd.Series) else pd.Series(srs, index=df.index)
            plots.append({"kind": "line", "title": str(title), "color": str(color),
                          "width": int(float(width or 1)), "style": str(style),
                          "data": [None if pd.isna(v) else round(float(v), 8) for v in s]})

        def shape(title, cond, color="#26a69a", location="abovebar", shape="circle"):  # noqa: A002
            s = cond.fillna(False) if isinstance(cond, pd.Series) else pd.Series(
                bool(cond), index=df.index)
            plots.append({"kind": "shape", "title": str(title), "color": str(color),
                          "location": str(location), "shape": str(shape),
                          "data": [bool(v) for v in s]})

        def hline(title, value, color="#787b86"):
            try:
                v = float(value)
            except Exception:  # noqa: BLE001
                return
            plots.append({"kind": "hline", "title": str(title), "color": str(color), "value": v})

        env = _mk_helpers(df)
        env.update({
            "df": df,
            "open": df["o"], "high": df["h"], "low": df["l"],
            "close": df["c"], "volume": df["v"],
            "inp": inp, "entry": entry, "exit": exit,
            "plot": plot, "shape": shape, "hline": hline,
            "__builtins__": {},
        })
        exec(compile(src, "<strategy>", "exec"), env)  # noqa: S102 (AST-verified)
        strategy.last_plots = plots
        return df.assign(long=acc["long"].fillna(False), short=acc["short"].fillna(False),
                         exit=acc["exit"].fillna(False))

    strategy.last_plots = []
    return strategy, {"ok": True, "errors": [], "inputs": input_meta, "defaults": defaults}


# ── Strategy samples (for the editor) ───────────────────────────────
SAMPLES: dict[str, str] = {
    "EMA + volume (strategy)": """\
fast = inp('fast', 20, 'Fast EMA', 'int')
slow = inp('slow', 50, 'Slow EMA', 'int')
mult = inp('mult', 1.5, 'Volume multiplier', 'float')

ema_fast = ema(close, fast)
ema_slow = ema(close, slow)
vol_ma   = sma(volume, fast)

bull = (ema_fast > ema_slow) & (volume > vol_ma * mult)
bear = (ema_fast < ema_slow) & (volume > vol_ma * mult)

entry('long',  bull & crossover(ema_fast, ema_slow))
entry('short', bear & crossunder(ema_fast, ema_slow))
exit(crossunder(ema_fast, ema_slow))
""",
    "EMA crossover (strategy)": """\
fast = inp('fast', 12, 'Fast EMA', 'int')
slow = inp('slow', 26, 'Slow EMA', 'int')

ema_fast = ema(close, fast)
ema_slow = ema(close, slow)

entry('long',  crossover(ema_fast, ema_slow))
entry('short', crossunder(ema_fast, ema_slow))
""",
    "RSI reversal (strategy)": """\
n  = inp('n', 14, 'RSI period', 'int')
lo = inp('lo', 30, 'Oversold', 'float')
hi = inp('hi', 70, 'Overbought', 'float')

r = rsi(close, n)

entry('long',  r < lo)
entry('short', r > hi)
""",
    "Indicator: SMA + bands (to chart)": """\
n = inp('n', 50, 'SMA period', 'int')

ma = sma(close, n)

plot('SMA', ma, '#ff9800', 2, 'line')
hline('zero', 0, '#787b86')
shape('BUY',  crossover(close, ma), '#26a69a', 'belowbar', 'triangleup')
shape('SELL', crossunder(close, ma), '#ef5350', 'abovebar', 'triangledown')
""",
    "Indicator: RSI panel": """\
n = inp('n', 14, 'RSI period', 'int')

r = rsi(close, n)

plot('RSI', r, '#9c27b0', 2, 'line')
hline('OB', 70, '#ef5350')
hline('OS', 30, '#26a69a')
""",
}
