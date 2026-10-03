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
indicators.py — technical indicators (vectorized, without TA-Lib).
Pure functions over pandas.Series/DataFrame (vectorized, no external dependencies).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder's smoothing (ta.rma)."""
    return s.ewm(alpha=1 / n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = rma(d.clip(lower=0), n)
    dn = rma(-d.clip(upper=0), n)
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd(close: pd.Series, fast=12, slow=26, sig=9):
    line = ema(close, fast) - ema(close, slow)
    signal = ema(line, sig)
    return line, signal, line - signal


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["c"].shift(1)
    return pd.concat([df["h"] - df["l"], (df["h"] - pc).abs(),
                      (df["l"] - pc).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return rma(true_range(df), n)


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    m = sma(close, n)
    sd = close.rolling(n).std(ddof=0)
    return m - k * sd, m, m + k * sd


def stoch(df: pd.DataFrame, n: int = 14, smooth_k: int = 3, smooth_d: int = 3):
    ll = df["l"].rolling(n).min()
    hh = df["h"].rolling(n).max()
    k = 100 * (df["c"] - ll) / (hh - ll).replace(0, np.nan)
    k = sma(k, smooth_k)
    return k, sma(k, smooth_d)


def cci(df: pd.DataFrame, n: int = 20) -> pd.Series:
    tp = (df["h"] + df["l"] + df["c"]) / 3
    m = tp.rolling(n).mean()
    md = (tp - m).abs().rolling(n).mean()
    return (tp - m) / (0.015 * md.replace(0, np.nan))


def roc(close: pd.Series, n: int = 10) -> pd.Series:
    return 100 * (close - close.shift(n)) / close.shift(n)


def williams_r(df: pd.DataFrame, n: int = 14) -> pd.Series:
    hh = df["h"].rolling(n).max()
    ll = df["l"].rolling(n).min()
    return -100 * (hh - df["c"]) / (hh - ll).replace(0, np.nan)


def adx(df: pd.DataFrame, di_len: int = 14, smooth: int = 14):
    up = df["h"].diff()
    dn = -df["l"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = rma(true_range(df), di_len)
    pdi = 100 * rma(pd.Series(plus_dm, index=df.index), di_len) / tr
    mdi = 100 * rma(pd.Series(minus_dm, index=df.index), di_len) / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return pdi, mdi, rma(dx, smooth)


def supertrend(df: pd.DataFrame, period: int = 7, mult: float = 2.5):
    """Returns (direction, line). direction: +1 up, -1 down."""
    a = atr(df, period)
    hl2 = (df["h"] + df["l"]) / 2
    upper = (hl2 + mult * a).to_numpy()
    lower = (hl2 - mult * a).to_numpy()
    close = df["c"].to_numpy()
    n = len(df)
    fu = np.full(n, np.nan)
    fl = np.full(n, np.nan)
    dir_ = np.ones(n, dtype=int)
    for i in range(n):
        if i == 0 or np.isnan(upper[i]):
            fu[i], fl[i], dir_[i] = upper[i], lower[i], 1
            continue
        fu[i] = upper[i] if (upper[i] < fu[i - 1]) or (close[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lower[i] if (lower[i] > fl[i - 1]) or (close[i - 1] < fl[i - 1]) else fl[i - 1]
        if dir_[i - 1] == 1:
            dir_[i] = -1 if close[i] < fl[i] else 1
        else:
            dir_[i] = 1 if close[i] > fu[i] else -1
    line = np.where(dir_ == 1, fl, fu)
    return pd.Series(dir_, index=df.index), pd.Series(line, index=df.index)


def donchian(df: pd.DataFrame, n: int = 10):
    return df["h"].rolling(n).max(), df["l"].rolling(n).min()


def compute_all(df: pd.DataFrame) -> dict:
    """Computes the full set of indicators for the chart."""
    c = df["c"]
    st_dir, st_line = supertrend(df, 7, 2.5)
    bb_u, bb_m, bb_l = bollinger(c, 20, 2.0)
    don_h, don_l = donchian(df, 10)
    ml, ms, mh = macd(c)
    sk, sd = stoch(df)
    pdi, mdi, adxv = adx(df)
    return {
        "ema200": ema(c, 200),
        "sma50": sma(c, 50),
        "sma200": sma(c, 200),
        "bb_upper": bb_u, "bb_mid": bb_m, "bb_lower": bb_l,
        "supertrend": st_line, "st_dir": st_dir,
        "donchian_hi": don_h, "donchian_lo": don_l,
        "rsi14": rsi(c, 14),
        "macd": ml, "macd_signal": ms, "macd_hist": mh,
        "stoch_k": sk, "stoch_d": sd,
        "adx": adxv, "di_plus": pdi, "di_minus": mdi,
        "cci20": cci(df), "roc10": roc(c, 10),
        "williams_r": williams_r(df), "atr14": atr(df, 14),
        "vol_ma20": sma(df["v"], 20),
    }
