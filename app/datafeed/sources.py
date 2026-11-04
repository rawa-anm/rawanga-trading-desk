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
from datetime import datetime, timedelta, timezone

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


# ── Hyperliquid (public info endpoint, NO keys, NO signing) ───────────
HL_INFO = "https://api.hyperliquid.xyz/info"
# HL intervals. 1w/1M are deliberately absent: their grid is not calendar
# based (a week starts on THURSDAY, a "month" is exactly 30 days). We take 1d
# and cut it ourselves, otherwise the grid drifts away from every other source.
HL_TF = {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

# Coins listed on HL under a x1000 lot ticker.
HL_ALIAS = {"PEPE": "kPEPE", "SHIB": "kSHIB", "BONK": "kBONK",
            "FLOKI": "kFLOKI", "LUNC": "kLUNC", "NEIRO": "kNEIRO",
            "DOGS": "kDOGS",
            # KPEPE is an instrument IN k-units already: on HL the coin is
            # called kPEPE, but no 1:1000 rescale applies — it IS the k-denominal.
            "KPEPE": "kPEPE"}
# (price factor, volume factor) for k-coins.
# kPEPE = 1000 PEPE: the price is 1000x BIGGER, so divide price and multiply
# volume. Without this vol_ma drifts by 1000x and vol_score starts lying.
HL_SCALE = {c: (1e-3, 1e3) for c in HL_ALIAS.values()}
# Instruments that are k-denominated by themselves: leave price/volume alone,
# otherwise KPEPE collapses into PEPE and the two rows become duplicates.
HL_KEEP_UNITS = {"KPEPE"}

# ── Tickers that exchanges call differently ───────────────────────────
# Verified against the APIs on 2026-11-03:
#   BingX:  PEPE -> 1000PEPE-USDT (x1000 lot; no plain PEPE pair)
#           GRAM -> GRAMTON-USDT   (same asset, different ticker name)
#   Bybit:  PEPE -> 1000PEPEUSDT
#   OKX:    PEPE -> PEPE-USDT      (plain PEPE, ordinary units)
#   Binance:PEPE -> PEPEUSDT       (ordinary units)
# Without renaming, BingX returns an EMPTY list and the instrument silently
# falls through to a foreign exchange — price and volume then come from a
# different venue than the one executing the trade.
SRC_ALIAS = {
    "bingx": {"PEPE": "1000PEPE", "GRAM": "GRAMTON", "KPEPE": "1000PEPE"},
    "bybit": {"PEPE": "1000PEPE"},
}

# Multipliers (price, volume) for lots quoted in other units.
# 1000PEPE = 1000 PEPE: price is 1000x bigger, volume 1000x smaller.
# GRAM (GRAMTON) is the same asset 1:1 — no multiplier.
SRC_SCALE = {
    ("bingx", "PEPE"): (1e-3, 1e3),
    ("bybit", "PEPE"): (1e-3, 1e3),
}

# Instruments whose PRIMARY source is pinned regardless of `prefer`:
# KPEPE only exists in k-units on Hyperliquid, so verification has to happen there.
PRIMARY_SOURCE = {"KPEPE": "hyperliquid"}


def _src_ticker(src_name: str, symbol: str) -> str:
    """Ticker of an instrument on a specific exchange (with renames applied)."""
    s = symbol.upper()
    return SRC_ALIAS.get(src_name, {}).get(s, s)


def _apply_src_scale(bars: list, src_name: str, symbol: str) -> list:
    """Convert x1000-lot bars (1000PEPE) back to ordinary units."""
    pmul, vmul = SRC_SCALE.get((src_name, symbol.upper()), (1.0, 1.0))
    if pmul == 1.0 and vmul == 1.0:
        return bars
    for b in bars:
        b[1] *= pmul; b[2] *= pmul; b[3] *= pmul; b[4] *= pmul
        b[5] *= vmul
    return bars


async def _hyperliquid(client, sym, tf, limit):
    """Hyperliquid candles via the PUBLIC info endpoint (no keys needed).

    Traps that had to be handled:
      - one endpoint (POST /info), payload {"type":"candleSnapshot"} — not a REST path;
      - bars arrive NEWEST FIRST and carry a `t` field instead of being arrays;
      - 1w/1M on HL are not calendar aligned (week starts THURSDAY, "month" = 30
        days), so those TFs are built from 1d and cut here — otherwise the grid
        disagrees with other sources and a bar slides by days;
      - k-coins (kPEPE and friends) quote x1000: divide price, multiply volume,
        otherwise vol_ma drifts by 1000x.
    """
    coin = HL_ALIAS.get(sym.upper(), sym.upper())
    if sym.upper() in HL_KEEP_UNITS:
        pmul, vmul = 1.0, 1.0          # already in k-units
    else:
        pmul, vmul = HL_SCALE.get(coin, (1.0, 1.0))

    if tf in HL_TF:
        iv, out_tf, agg_sec = HL_TF[tf], tf, 0
        want = limit
    elif tf == "1w":
        iv, out_tf, agg_sec = "1d", tf, TF_SECONDS["1w"]
        want = min(limit * 7 + 7, 5000)
    elif tf == "1M":
        iv, out_tf, agg_sec = "1d", tf, TF_SECONDS["1M"]
        want = min(limit * 31 + 31, 5000)
    else:
        raise SourceError(f"hyperliquid: unsupported tf {tf}")

    # Window is derived from the number of bars we need: without startTime HL
    # returns very few candles.
    span_ms = want * (TF_SECONDS[iv]) * 1000
    now = int(time.time() * 1000)
    r = await client.post(HL_INFO, json={"type": "candleSnapshot", "req": {
        "coin": coin, "interval": iv,
        "startTime": now - span_ms, "endTime": now}})
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list):
        raise SourceError(f"hyperliquid: unexpected payload {str(rows)[:120]}")

    out = [[int(c["t"]), float(c["o"]), float(c["h"]), float(c["l"]),
            float(c["c"]), float(c.get("v", 0))] for c in rows]
    if not out:
        raise SourceError("hyperliquid: empty")
    out.sort(key=lambda x: x[0])          # HL sends newest first

    if pmul != 1.0 or vmul != 1.0:
        # kPEPE price is 1000x the real one; volume is 1000x smaller.
        for b in out:
            b[1] *= pmul; b[2] *= pmul; b[3] *= pmul; b[4] *= pmul
            b[5] *= vmul

    if agg_sec:
        out = _hl_calendar_agg(out, out_tf)
    return out[-limit:]


def _hl_calendar_agg(bars: list[list], tf: str) -> list[list]:
    """Fold daily HL bars into WEEKLY/MONTHLY buckets by CALENDAR.

    _aggregate_bars cuts at whole intervals since the epoch — correct for
    15m/1h/4h, but for 1w/1M that yields a 1970-based grid: weeks start on
    THURSDAY, "months" on the 6th. BingX/Binance cut by calendar: week starts
    Monday 00:00 UTC, month on the 1st.
    """
    buckets: dict[int, list] = {}
    for b in sorted(bars, key=lambda x: x[0]):
        dt = datetime.fromtimestamp(b[0] / 1000, timezone.utc)
        if tf == "1w":
            k = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            k = k - timedelta(days=k.weekday())
        else:  # 1M
            k = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ts = int(k.timestamp() * 1000)
        if ts not in buckets:
            buckets[ts] = [ts, b[1], b[2], b[3], b[4], b[5]]
        else:
            a = buckets[ts]
            a[2] = max(a[2], b[2])
            a[3] = min(a[3], b[3])
            a[4] = b[4]
            a[5] = (a[5] or 0) + (b[5] or 0)
    return [buckets[k] for k in sorted(buckets)]


CRYPTO_SOURCES = [("bingx", _bingx), ("hyperliquid", _hyperliquid),
                  ("binance", _binance), ("bybit", _bybit), ("okx", _okx)]


def ordered_crypto_sources(prefer: str | None = None) -> list:
    """Cascade where `prefer` (the executing exchange) comes FIRST.

    The rest stay as a safety net in their original order.
    """
    if not prefer:
        return list(CRYPTO_SOURCES)
    pref = str(prefer).strip().lower()
    head = [(n, f) for n, f in CRYPTO_SOURCES if n == pref]
    tail = [(n, f) for n, f in CRYPTO_SOURCES if n != pref]
    return head + tail


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

# ── Retries and source guard (Creator's requirement, 2026-10-15) ──
# How many times we hit a SINGLE exchange before falling back: 3 tries × 5 s.
RETRY_TRIES = 3
RETRY_DELAY = 5.0
# Exchange cooldown: after a FULL failure (transport/5xx/429) we do not hammer it
# 3×5 s for every ticker — otherwise a global outage stretches one tick (≈85
# instruments) into minutes. While cooling down — one quick attempt per ticker.
_SRC_COOLDOWN: dict[str, float] = {}
_COOLDOWN_SEC = 60.0


def _retry_after(e) -> float | None:
    """Retry-After from the response (429), if present (≤10 s)."""
    resp = getattr(e, "response", None)
    if resp is not None:
        ra = resp.headers.get("Retry-After")
        if ra:
            try:
                return min(float(ra), 10.0)
            except Exception:  # noqa: BLE001
                return None
    return None


def _is_global_err(e) -> bool:
    """Does it look like a WHOLE-exchange failure (network/5xx/429)?"""
    if isinstance(e, (httpx.TransportError, httpx.TimeoutException)):
        return True
    resp = getattr(e, "response", None)
    if resp is not None and (resp.status_code == 429 or resp.status_code >= 500):
        return True
    return False


async def _retry_fetch(fn, client, arg, tf, limit, name,
                       tries: int = RETRY_TRIES, delay: float = RETRY_DELAY):
    """Repeated requests to a SINGLE exchange. Returns bars or None.

    During a global outage (cooldown) — a single quick attempt, no delays.
    """
    now = time.time()
    cooling = _SRC_COOLDOWN.get(name, 0) > now
    attempts = 1 if cooling else tries
    last_err = None
    for i in range(1, attempts + 1):
        try:
            bars = await fn(client, arg, tf, limit)
            if bars:
                _SRC_COOLDOWN.pop(name, None)
                return bars
            last_err = "empty"
        except Exception as e:  # noqa: BLE001
            last_err = e
            ra = _retry_after(e)
            if ra:
                await asyncio.sleep(ra)
                continue
        if i < attempts:
            await asyncio.sleep(delay)
    if not cooling:
        _SRC_COOLDOWN[name] = now + _COOLDOWN_SEC
        log.warning("fetch %s %s <- %s: %d attempts failed (%s); cooldown %.0fs",
                    arg, tf, name, attempts, last_err, _COOLDOWN_SEC)
    return None


async def fetch_ohlcv(symbol: str, tf: str, limit: int = 500,
                      client: httpx.AsyncClient | None = None,
                      kind: str = "crypto",
                      prefer: str | None = None) -> dict:
    """Returns {'symbol','tf','source','bars':[[ts,o,h,l,c,v],...]}.

    Cascade: (prefer) → BingX → Hyperliquid → Binance → Bybit → OKX (crypto).
    `prefer` is the executing exchange and is queried first. EACH source is
    tried with retries 3×5 s (_retry_fetch). The `source` in the reply shows
    which venue the bar actually came from (used for the webhook marker).

    PRIMARY_SOURCE pins the main source rigidly, ignoring `prefer`: some tickers
    do not exist on the executing exchange under that name (KPEPE only exists in
    k-units on Hyperliquid).

    Taking the bar from one venue while executing on another is exactly how
    false arbitrage signals appeared (STRK case): prices differ in tenths of a
    percent between exchanges and the strategy reads that as a move.
    """
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
            # prefer — the executing exchange goes first.
            # PRIMARY_SOURCE — a hard pin, it comes first regardless of prefer.
            pinned = PRIMARY_SOURCE.get(symbol.upper())
            sources = ordered_crypto_sources(pinned or prefer) + [("yahoo", _yahoo)]
        else:
            sources = [("yahoo", _yahoo)]
        for name, fn in sources:
            if name == "yahoo":
                arg = symbol
            else:
                # The ticker may be named differently on this venue (1000PEPE).
                arg = _src_ticker(name, symbol)
            bars = await _retry_fetch(fn, client, arg, tf, limit, name)
            if bars:
                bars = _apply_src_scale(bars, name, symbol)
                log.info("fetch %s %s <- %s (%d bars)", symbol, tf, name, len(bars))
                return {"symbol": symbol, "tf": tf, "source": name, "bars": bars}
            errors.append(f"{name}: failed")
        raise SourceError("all sources failed: " + " | ".join(errors[-4:]))
    finally:
        if own:
            await client.aclose()
