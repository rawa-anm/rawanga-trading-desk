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
signals.py — built-in strategy signals (Python).

STv3 (Supertrend v3):
  LONG:  flip DOWN->UP with 2-candle confirmation
  SHORT: flip UP->DOWN with confirmation   OR breach: red candle below ST under EMA200
  EXIT:  reverse flip

Rawa Trade System (Vol+ADX):
  LONG:  close > don_hi[-1] and vol > vol_ma20*1.5 and adx > 25
  SHORT: close < don_lo[-1] and vol > vol_ma20*1.5 and adx > 25
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.indicators import ta


def stv3(df: pd.DataFrame, st_period=7, st_mult=2.5, ema_len=200, sl_pct=1.0,
         use_ema_breach=True) -> pd.DataFrame:
    d = df.copy()
    st_dir, st_line = ta.supertrend(d, st_period, st_mult)
    ema = ta.ema(d["c"], ema_len)
    d["st_dir"], d["st_line"], d["ema"] = st_dir, st_line, ema

    flip_raw = st_dir.diff() != 0
    # 2-candle confirmation: dir[-2]==dir[0] and dir[-3]!=dir[0]
    flip_c = pd.Series(False, index=d.index)
    for i in range(len(d)):
        if i >= 2 and d["st_dir"].iloc[i - 2] != d["st_dir"].iloc[i] \
                and d["st_dir"].iloc[i - 1] == d["st_dir"].iloc[i]:
            flip_c.iloc[i] = True
    up = st_dir > 0
    dn = st_dir < 0

    enter_long = flip_c & ~flip_c.shift(1).fillna(False) & up
    breach = up & (d["c"] < st_line) & (d["c"].shift(1) < ema) & (d["c"] < d["o"])
    enter_short = (flip_c & ~flip_c.shift(1).fillna(False) & dn) | (use_ema_breach & breach)

    d["long"] = enter_long.fillna(False)
    d["short"] = enter_short.fillna(False)
    d["exit"] = (flip_raw.fillna(False) & (up | dn))
    d["stop_pct"] = sl_pct / 100.0
    # volume base for estimating the volume factor (stv3 has no volume filter — we take 20)
    d["vol_ma"] = ta.sma(d["v"], 20)
    return d


def rawa_system(df: pd.DataFrame, donch_entry=10, donch_exit=5, atr_len=14,
                atr_mult=2.0, vol_len=20, vol_mult=1.5, adx_on=True,
                adx_di_len=14, adx_smooth=14, adx_thresh=25.0,
                permit_long=True, permit_short=True) -> pd.DataFrame:
    d = df.copy()
    don_hi = ta.donchian(d, donch_entry)[0]
    don_lo = ta.donchian(d, donch_entry)[1]
    a = ta.atr(d, atr_len)
    vol_ma = ta.sma(d["v"], vol_len)
    _, _, adx = ta.adx(d, adx_di_len, adx_smooth)
    adx_pass = (~adx_on) | (adx > adx_thresh)

    long_sig = permit_long & (d["c"] > don_hi.shift(1)) & (d["v"] > vol_ma * vol_mult) & adx_pass
    short_sig = permit_short & (d["c"] < don_lo.shift(1)) & (d["v"] > vol_ma * vol_mult) & adx_pass

    d["don_hi"], d["don_lo"], d["atr"], d["adx"], d["vol_ma"] = don_hi, don_lo, a, adx, vol_ma
    d["long"] = long_sig.fillna(False)
    d["short"] = short_sig.fillna(False)
    d["stop_abs"] = a * atr_mult
    return d


def trend_watch(df: pd.DataFrame, st_period=10, st_mult=3.0) -> pd.DataFrame:
    """TREND INDICATOR (not an entries/exits strategy).

    Pure Supertrend(10, 3) — the same parameters as in the standard implementation
    (BTCUSD · Supertrend (10, 3) · SuperTrend Sell).

    Events:
        long  = the FIRST bar that entered the up phase  (DOWN -> UP)
        short = the FIRST bar that entered the down phase (UP -> DOWN)
    Notification mode — once per phase entry, silence until the change (see runner).
    Used for VIX / SPX / BTC / USDT.D on 15m.
    """
    d = df.copy()
    st_dir, st_line = ta.supertrend(d, st_period, st_mult)
    d["st_dir"], d["st_line"] = st_dir, st_line
    change = st_dir.diff()
    d["long"] = ((change > 0) & (st_dir > 0)).fillna(False)
    d["short"] = ((change < 0) & (st_dir < 0)).fillna(False)
    return d


def trend_flips(d: pd.DataFrame) -> list[dict]:
    """List of Supertrend flips: [{ts, close, side, st_line}]."""
    out = []
    for _, row in d.iterrows():
        if bool(row.get("long")) or bool(row.get("short")):
            out.append({"ts": int(row["ts"]), "close": float(row["c"]),
                        "side": "long" if bool(row.get("long")) else "short",
                        "st_line": float(row["st_line"]) if not pd.isna(row.get("st_line")) else None})
    return out


STRATEGIES = {
    "stv3": {"fn": stv3, "title": "Supertrend v3"},
    "rawa_system": {"fn": rawa_system, "title": "Rawa Trade System Vol+ADX"},
    "trend": {"fn": trend_watch, "title": "Supertrend (trend indicator)"},
}

# Actual STRATEGIES (entries/exits). "trend" — only an indicator, does not go into trades.
TRADE_STRATEGIES = ["stv3", "rawa_system"]


def register_strategy(key: str, title: str, fn, inputs: list | None = None,
                      trade: bool = True) -> None:
    """Registers a user (compiled) strategy in the engine."""
    STRATEGIES[key] = {"fn": fn, "title": title, "custom": True,
                       "inputs": inputs or []}
    if trade and key not in TRADE_STRATEGIES:
        TRADE_STRATEGIES.append(key)


def unregister_strategy(key: str) -> None:
    STRATEGIES.pop(key, None)
    if key in TRADE_STRATEGIES:
        TRADE_STRATEGIES.remove(key)


def run(df: pd.DataFrame, name: str, params: dict | None = None) -> pd.DataFrame:
    if name not in STRATEGIES:
        raise KeyError(f"unknown strategy {name}")
    entry = STRATEGIES[name]
    fn = entry["fn"]
    # A user strategy accepts **inputs — we pass only
    # the input params declared in it (we ignore the rest).
    if entry.get("custom"):
        names = {i["var"] for i in entry.get("inputs", [])}
        clean = {k: v for k, v in (params or {}).items() if k in names}
        return fn(df, **clean)
    # Keep only the parameters that the function actually accepts.
    # Extra ones (risk_pct and any junk from inputs / TP/trail) — we ignore,
    # otherwise strategy() raises TypeError and the whole endpoint returns 500.
    import inspect
    allowed = set(inspect.signature(fn).parameters) - {"df"}
    clean = {k: v for k, v in (params or {}).items() if k in allowed}
    return fn(df, **clean)


def signals_only(d: pd.DataFrame, opt: dict | None = None,
                 category: str = "crypto") -> list[dict]:
    """Returns signals with entry AND exit points + stop size.

    IMPORTANT: an entry is opened only on a TRANSITION (no position → there is a signal).
    While a position of the same direction is open, repeated long/short are ignored.
    A contrary signal closes the position and opens the opposite one.

    Exits checked ON EVERY BAR (intra-bar, by low/high), in priority order:
      1) HARD STOP (like strategy.exit(stop=...)) — always enabled.
      2) TAKE-PROFIT (opt.use_tp) — optional, not needed by reversal strategies.
      3) TRAILING STOP (opt.use_trail) — optional; trails the stop after the price.
    Plus exit by the strategy's own signal (exit / reversal).
    """
    o = opt or {}
    use_tp = bool(o.get("use_tp", False))
    tp_pct = float(o.get("tp_pct", 0) or 0)          # % of the entry price
    use_trail = bool(o.get("use_trail", False))
    trail_pct = float(o.get("trail_pct", 0) or 0)    # % of the max/min since entry

    out = []
    in_pos = None  # the currently open position
    for i, row in d.iterrows():
        ts = int(row["ts"])
        close = float(row["c"])
        hi = float(row["h"])
        lo = float(row["l"])
        want_long = bool(row.get("long"))
        want_short = bool(row.get("short"))
        want_exit = bool(row.get("exit"))

        # ── 1. HARD STOP / TP / TRAILING BY INTRA-BAR MOVEMENT ──
        stopped = False
        if in_pos:
            side = in_pos["side"]
            entry = in_pos["entry"]
            # update the extreme for trailing
            trail_active = False
            if use_trail and trail_pct > 0:
                if side == "long":
                    in_pos["peak"] = max(in_pos.get("peak", entry), hi)
                    trail_stop = in_pos["peak"] * (1 - trail_pct / 100.0)
                    new_stop = max(in_pos["stop"] or 0, trail_stop)
                else:
                    in_pos["peak"] = min(in_pos.get("peak", entry), lo)
                    trail_stop = in_pos["peak"] * (1 + trail_pct / 100.0)
                    new_stop = min(in_pos["stop"] or 1e18, trail_stop)
                if new_stop != in_pos["stop"]:
                    trail_active = True
                    in_pos["trailing"] = True
                in_pos["stop"] = new_stop
            stop = in_pos.get("stop")
            tp = None
            if use_tp and tp_pct > 0:
                tp = entry * (1 + tp_pct / 100.0) if side == "long" else entry * (1 - tp_pct / 100.0)
            # intra-bar touch check: stop first (risk priority), then TP
            if stop is not None and ((side == "long" and lo <= stop) or (side == "short" and hi >= stop)):
                out.append({"ts": ts, "close": stop, "side": "exit",
                            "exit_of": side, "atr": in_pos.get("atr"), "reason": "stop",
                            "trailing": bool(in_pos.get("trailing"))})
                in_pos = None
                stopped = True
            elif tp is not None and ((side == "long" and hi >= tp) or (side == "short" and lo <= tp)):
                out.append({"ts": ts, "close": tp, "side": "exit",
                            "exit_of": side, "atr": in_pos.get("atr"), "reason": "tp",
                            "tp_price": tp})
                in_pos = None
                stopped = True
            elif want_exit:
                # exit by the strategy's own signal
                out.append({"ts": ts, "close": close, "side": "exit",
                            "exit_of": side, "atr": in_pos.get("atr"), "reason": "signal"})
                in_pos = None

        if stopped:
            pass  # position closed — below we can open a new one on this bar's signal

        new_side = None
        if want_long and want_short:
            new_side = None                      # contradiction - skip
        elif want_long:
            new_side = "long"
        elif want_short:
            new_side = "short"

        if in_pos:
            if new_side and new_side != in_pos["side"]:
                # reversal: close and open the opposite
                out.append({"ts": ts, "close": close, "side": "exit",
                            "exit_of": in_pos["side"], "atr": in_pos.get("atr"),
                            "reason": "reversal"})
                in_pos = None
            else:
                continue                          # same signal - ignore, no re-entry

        if new_side and in_pos is None:
            atr_v = row.get("atr")
            atr_v = float(atr_v) if atr_v is not None and not pd.isna(atr_v) else None
            stop = _stop_for(row, close, new_side, category)
            vol_score = _vol_score(row)
            in_pos = {"side": new_side, "entry": close, "stop": stop,
                      "atr": atr_v, "peak": close, "trailing": False}
            out.append({"ts": ts, "close": close, "side": new_side,
                        "entry": close, "stop": stop, "atr": atr_v,
                        "vol_score": vol_score})
    return out


def _vol_score(row) -> int | None:
    """Score of the candle VOLUME FACTOR on a five-point scale.

    We compare the bar volume with its average (vol_ma, 20):
        < 0.5×  →  1
       0.5–0.8×  →  2
       0.8–1.2×  →  3 (normal)
       1.2–2.0×  →  4
        > 2.0×   →  5 (spike)
    """
    v = row.get("v")
    ma = row.get("vol_ma")
    if v is None or ma is None or pd.isna(v) or pd.isna(ma) or float(ma) <= 0:
        return None
    ratio = float(v) / float(ma)
    if ratio < 0.5:
        return 1
    if ratio < 0.8:
        return 2
    if ratio < 1.2:
        return 3
    if ratio < 2.0:
        return 4
    return 5


def _stop_for(row, close, side, category="crypto"):
    """STOP PRICE. In strategies stop_abs is the ABSOLUTE volatility magnitude
    (atr*mult), not a price. Therefore for the stop it must be ADDED/SUBTRACTED from close.

    The stop step is normalized by instrument class: commodities/currency ≥0.5%, stocks ≥1%,
    crypto ≥2% of the price. Otherwise with a flattened ATR (flat bars in the cache) the stop drops
    to tick noise and is hit instantly.
    """
    min_pct = _min_stop_pct(category)          # fraction (0.005 / 0.01 / 0.02)
    floor_abs = close * min_pct
    stop_abs = row.get("stop_abs")
    has_abs = stop_abs is not None and not pd.isna(stop_abs) and float(stop_abs) > 0
    dist = float(stop_abs) if has_abs else close * float(row.get("stop_pct", 0) or 0)
    dist = max(dist, floor_abs)                # minimum by instrument class
    return close - dist if side == "long" else close + dist


def _min_stop_pct(category: str) -> float:
    """Minimum stop step from the price by instrument class."""
    return {
        "crypto": 0.02,     # 2%
        "stocks": 0.01,     # 1% (stocks)
        "energy": 0.005,    # 0.5% (commodities/futures)
        "metals": 0.005,    # 0.5% (metals)
        "indices": 0.005,   # 0.5% (indices)
        "fx": 0.005,        # 0.5% (currencies)
    }.get((category or "").lower(), 0.02)
