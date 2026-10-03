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
sources.py — OHLCV sources with a fallback cascade.

Crypto:  BingX -> Binance -> Bybit -> OKX
Stocks/energy: Yahoo Finance (with UA + retry on 429)

All sources return a list of candles [ts_ms, open, high, low, close, volume] (UTC, ms).
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import time

import httpx

from app import paths as _paths

log = logging.getLogger("tv.datafeed")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Timeframes: SINGLE registry (source of truth for API/UI/scheduler).
# Normalized name -> (bingx, binance, bybit, okx, yahoo)
TF_MAP = {
    "15m": ("15m", "15m", "15",  "15m", "15m"),
    "1h":  ("1h",  "1h",  "60",  "1H",  "60m"),
    "4h":  ("4h",  "4h",  "240", "4H",  None),   # Yahoo has no 4h — we aggregate from 1h
    "1d":  ("1d",  "1d",  "D",   "1D",  "1d"),
    "1w":  ("1w",  "1w",  "W",   "1W",  "1wk"),
    "1M":  ("1M",  "1M",  "M",   "1M",  "1mo"),
}
# Canonical TF order (UI/scheduler).
TFS = ["15m", "1h", "4h", "1d", "1w", "1M"]
YAHOO_RANGE = {"15m": "60d", "1h": "730d", "4h": "730d", "1d": "5y",
               "1w": "10y", "1M": "max"}
# Seconds per bar (for the synthetic dominance candle grid)
TF_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400,
              "1w": 604800, "1M": 2592000}


class SourceError(Exception):
    pass


# ── Crypto ──────────────────────────────────────────────────────────

async def _bingx(client, sym, tf, limit):
    iv = TF_MAP[tf][0]
    r = await client.get(
        "https://open-api.bingx.com/openApi/swap/v3/quote/klines",
        params={"symbol": f"{sym}-USDT", "interval": iv, "limit": limit},
    )
    r.raise_for_status()
    data = r.json().get("data", [])
    out = [[int(c["time"]), float(c["open"]), float(c["high"]),
            float(c["low"]), float(c["close"]), float(c.get("volume", 0))] for c in data]
    return sorted(out, key=lambda x: x[0])


async def _binance(client, sym, tf, limit):
    iv = TF_MAP[tf][1]
    r = await client.get(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": f"{sym}USDT", "interval": iv, "limit": limit},
    )
    r.raise_for_status()
    return [[int(k[0]), float(k[1]), float(k[2]), float(k[3]),
             float(k[4]), float(k[5])] for k in r.json()]


async def _bybit(client, sym, tf, limit):
    iv = TF_MAP[tf][2]
    r = await client.get(
        "https://api.bybit.com/v5/market/kline",
        params={"category": "linear", "symbol": f"{sym}USDT", "interval": iv, "limit": limit},
    )
    r.raise_for_status()
    rows = r.json()["result"]["list"]
    out = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]),
            float(x[4]), float(x[5])] for x in rows]
    return sorted(out, key=lambda x: x[0])


async def _okx(client, sym, tf, limit):
    iv = TF_MAP[tf][3]
    r = await client.get(
        "https://www.okx.com/api/v5/market/candles",
        params={"instId": f"{sym}-USDT", "bar": iv, "limit": min(limit, 300)},
    )
    r.raise_for_status()
    rows = r.json()["data"]
    out = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]),
            float(x[4]), float(x[5])] for x in rows]
    return sorted(out, key=lambda x: x[0])


CRYPTO_SOURCES = [("bingx", _bingx), ("binance", _binance),
                  ("bybit", _bybit), ("okx", _okx)]


# ── USDT Dominance (synthetic candles from CoinGecko) ───────────────

async def _dominance(client, ysym, tf, limit):
    """USDT.D: USDT dominance from CoinGecko /global.

    CoinGecko free does not provide history, so we build only the current point
    and accumulate it in a JSON file on every poll (at bar close).
    The dominance value in % is treated as the price.
    """
    r = await client.get("https://api.coingecko.com/api/v3/global",
                         headers={"User-Agent": UA, "Accept": "application/json"})
    if r.status_code == 429:
        raise SourceError("coingecko 429 rate-limit")
    r.raise_for_status()
    mcp = r.json()["data"]["market_cap_percentage"]
    val = float(mcp["usdt"])
    now_ms = int(time.time() // (TF_SECONDS.get(tf, 900)) * TF_SECONDS.get(tf, 900) * 1000)
    path = _paths.USDTD_HISTORY_PATH
    hist = []
    if path.exists():
        try:
            hist = json.loads(path.read_text())
        except Exception:
            hist = []
    if not hist or hist[-1][0] != now_ms:
        hist.append([now_ms, val, val, val, val, 0.0])
    hist = hist[-limit:]
    path.write_text(json.dumps(hist))
    return [[int(a), float(b), float(c), float(d), float(e), float(f)] for a, b, c, d, e, f in hist]


# ── Yahoo (stocks / metals / energy) ───────────────────────────────

def _aggregate_bars(bars: list[list], tf_sec: int) -> list[list]:
    """Folds raw bars into candles of tf_sec seconds (valid 15m/1h from minute snapshots).

    Yahoo sometimes returns a stream misaligned to the grid (VIX — minute snapshots),
    then Supertrend/ATR are computed on noise. Here we collect OHLCV over windows
    [k*tf_sec, (k+1)*tf_sec) — open=first, close=last, high/low=extremes.
    """
    step = tf_sec * 1000
    buckets: dict[int, list] = {}
    for b in sorted(bars, key=lambda x: x[0]):
        t = int(b[0])
        k = t // step * step
        if k not in buckets:
            buckets[k] = [k, b[1], b[2], b[3], b[4], b[5]]
        else:
            agg = buckets[k]
            agg[2] = max(agg[2], b[2])
            agg[3] = min(agg[3], b[3])
            agg[4] = b[4]          # close — the last by time
            agg[5] = (agg[5] or 0) + (b[5] or 0)   # volume — the sum
    return [buckets[k] for k in sorted(buckets)]


async def _yahoo(client, ysym, tf, limit):
    iv = TF_MAP[tf][4]
    rng = YAHOO_RANGE[tf]
    # Yahoo does not serve 4h directly (TF_MAP[…][4]=None) — we take 1h and aggregate below.
    yiv = iv or "1h"
    r = await client.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ysym}",
        params={"interval": yiv, "range": rng},
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    if r.status_code == 429:
        raise SourceError("yahoo 429 rate-limit")
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(ts):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], (q.get("volume") or [None])[i]
        if None in (o, h, l, c):
            continue
        out.append([int(t) * 1000, float(o), float(h), float(l), float(c), float(v or 0)])
    # Yahoo may return a non-15m grid (e.g. VIX — minute snapshots).
    # We aggregate to the target TF if the bars are not aligned to 900s.
    tf_sec = TF_SECONDS[tf]
    if len(out) >= 2:
        sorted_out = sorted(out, key=lambda x: x[0])
        aligned = all((sorted_out[i + 1][0] - sorted_out[i][0]) % (tf_sec * 1000) == 0
                      for i in range(min(len(sorted_out) - 1, 20))) \
            and sorted_out[0][0] % (tf_sec * 1000) == 0
        if not aligned:
            log.info("yahoo %s tf=%s: off-grid → aggregating into %ds", ysym, tf, tf_sec)
            out = _aggregate_bars(out, tf_sec)
    return out[-limit:]


# ── Core: fetch with cascade ──────────────────────────────────────────

async def fetch_ohlcv(symbol: str, tf: str, limit: int = 500,
                      client: httpx.AsyncClient | None = None,
                      kind: str = "crypto") -> dict:
    """Returns {'symbol','tf','source','bars':[[ts,o,h,l,c,v],...]}."""
    if tf not in TF_MAP:
        raise SourceError(f"unsupported tf {tf}")
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=12.0)
    errors = []
    try:
        if kind == "dominance":
            sources = [("dominance", _dominance)]
        elif kind == "crypto":
            sources = CRYPTO_SOURCES + [("yahoo", _yahoo)]
        else:
            sources = [("yahoo", _yahoo)]
        for name, fn in sources:
            arg = symbol if name == "yahoo" else symbol.upper()
            for attempt in range(2):
                try:
                    bars = await fn(client, arg, tf, limit)
                    if bars:
                        log.info("fetch %s %s <- %s (%d bars)", symbol, tf, name, len(bars))
                        return {"symbol": symbol, "tf": tf, "source": name, "bars": bars}
                    raise SourceError("empty")
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{name}: {e}")
                    if "429" in str(e):
                        await asyncio.sleep(1.5)
                        continue
                    break
        raise SourceError("all sources failed: " + " | ".join(errors[-4:]))
    finally:
        if own:
            await client.aclose()
