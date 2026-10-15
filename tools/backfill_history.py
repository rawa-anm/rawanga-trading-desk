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
backfill_history.py — one-off deep backfill of candle history into the cache (tv.db).

Why: the cache is only filled with the "last N" (runner limit=500), so the
history "floor" is frozen at the date of the first run. The exchange returns at
most 1000 candles per request — no deeper. Here we take history by PAGINATION
(endTime backwards) until we reach FLOOR_DATE or the exchange stops returning
data, and write via upsert (INSERT OR REPLACE in cache.upsert_bars).

Source: BingX (the trading venue) — crypto only. Non-crypto (Yahoo) is already deep.

Run:  python tools/backfill_history.py
Idempotent: a repeated run only fills in older stretches.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Resolve the project root (the directory above this tools/ dir) so that the
# portable build works from any location — no absolute production paths.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import paths as _paths  # noqa: E402
from app.datafeed import cache  # noqa: E402

BINGX = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"

# Do not go deeper than this date (UTC). If the exchange offers older — cut here.
FLOOR_DATE = datetime(2026, 4, 1, tzinfo=timezone.utc)
FLOOR_MS = int(FLOOR_DATE.timestamp() * 1000)

# TF -> BingX interval. 15m/1h/4h/1d; (1w/1M are already deep since 2020 — untouched).
TF_INTERVAL = {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

PAGE_LIMIT = 1000          # BingX maximum per request
MAX_PAGES = 60             # safety cap
SLEEP = 0.35              # pause between requests (rate-limit politeness)
RETRIES = 3

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout),
                              logging.FileHandler(ROOT / "tools" / f"backfill_{datetime.now():%Y%m%d_%H%M}.log")])
log = logging.getLogger("backfill")


async def bingx_page(client, sym, iv, end_ms):
    """One BingX page. end_ms=None — the freshest. Returns a list of bars."""
    params = {"symbol": f"{sym}-USDT", "interval": iv, "limit": PAGE_LIMIT}
    if end_ms is not None:
        params["endTime"] = end_ms
    for a in range(RETRIES):
        try:
            r = await client.get(BINGX, params=params, timeout=25)
            j = r.json()
            if j.get("code") not in (0, None):
                # 109400 — invalid params; empty/error — stop for this symbol
                raise RuntimeError(f"code={j.get('code')} msg={j.get('msg')}")
            d = j.get("data", []) or []
            out = [[int(c["time"]), float(c["open"]), float(c["high"]),
                    float(c["low"]), float(c["close"]), float(c.get("volume", 0))]
                   for c in d]
            out.sort(key=lambda x: x[0])
            return out
        except Exception as e:  # noqa: BLE001
            if a == RETRIES - 1:
                log.warning("  %s %s: request error: %s", sym, iv, e)
                return []
            await asyncio.sleep(1.0 + a)
    return []


async def cache_min(sym, tf):
    import aiosqlite
    async with aiosqlite.connect(cache.DB) as db:
        cur = await db.execute("SELECT MIN(ts) FROM bars WHERE symbol=? AND tf=?", (sym, tf))
        (ts,) = await cur.fetchone()
        return ts


async def backfill_symbol_tf(client, sym, tf):
    iv = TF_INTERVAL[tf]
    mm = await cache_min(sym, tf)   # we need the MINIMUM, not the maximum
    end = (mm - 1) if mm else None
    added = 0
    pages = 0
    while pages < MAX_PAGES:
        bars = await bingx_page(client, sym, iv, end)
        if not bars:
            break
        await cache.upsert_bars(sym, tf, bars, "bingx")
        added += len(bars)
        oldest = bars[0][0]
        pages += 1
        if len(bars) < PAGE_LIMIT:
            break
        if oldest <= FLOOR_MS:
            break
        end = oldest - 1
        await asyncio.sleep(SLEEP)
    return pages, added


async def main():
    await cache.init()
    import aiosqlite
    async with aiosqlite.connect(cache.DB) as db:
        cur = await db.execute("SELECT symbol FROM instruments WHERE category='crypto' AND enabled=1 ORDER BY symbol")
        syms = [r[0] for r in await cur.fetchall()]
    log.info("backfill: %d symbols × TF %s; floor=%s", len(syms), list(TF_INTERVAL), FLOOR_DATE.date())

    total_added = 0
    async with httpx.AsyncClient(timeout=25) as client:
        for i, sym in enumerate(syms, 1):
            line = []
            for tf in TF_INTERVAL:
                before = await cache_min(sym, tf)
                pages, added = await backfill_symbol_tf(client, sym, tf)
                after = await cache_min(sym, tf)
                total_added += added
                old = datetime.utcfromtimestamp(before / 1000).strftime("%m-%d") if before else "-"
                new = datetime.utcfromtimestamp(after / 1000).strftime("%m-%d") if after else "-"
                line.append(f"{tf}:+{added}({old}->{new})")
                await asyncio.sleep(SLEEP)
            log.info("[%2d/%d] %-6s %s", i, len(syms), sym, "  ".join(line))
    log.info("backfill done. total added/updated: %d bars", total_added)


if __name__ == "__main__":
    asyncio.run(main())
