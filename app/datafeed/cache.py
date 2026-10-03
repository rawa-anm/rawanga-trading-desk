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
cache.py — candle cache in SQLite.
Table bars(symbol, tf, ts, o,h,l,c,v, source) with PK(symbol,tf,ts).
"""
from __future__ import annotations

import aiosqlite
from app import paths as _paths

DB = str(_paths.DB_PATH)

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
  symbol TEXT NOT NULL, tf TEXT NOT NULL, ts INTEGER NOT NULL,
  o REAL, h REAL, l REAL, c REAL, v REAL, source TEXT,
  PRIMARY KEY (symbol, tf, ts)
);
CREATE INDEX IF NOT EXISTS idx_bars_sym_tf ON bars(symbol, tf, ts DESC);
"""


async def init():
    async with aiosqlite.connect(DB) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def upsert_bars(symbol: str, tf: str, bars: list, source: str) -> int:
    rows = [(symbol, tf, int(b[0]), b[1], b[2], b[3], b[4], b[5], source) for b in bars]
    async with aiosqlite.connect(DB) as db:
        await db.executemany(
            "INSERT OR REPLACE INTO bars(symbol,tf,ts,o,h,l,c,v,source) "
            "VALUES(?,?,?,?,?,?,?,?,?)", rows)
        await db.commit()
    return len(rows)


async def get_bars(symbol: str, tf: str, limit: int = 500) -> list:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT ts,o,h,l,c,v FROM bars WHERE symbol=? AND tf=? "
            "ORDER BY ts DESC LIMIT ?", (symbol, tf, limit))
        rows = await cur.fetchall()
    return [list(r) for r in reversed(rows)]


async def last_ts(symbol: str, tf: str):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT MAX(ts) FROM bars WHERE symbol=? AND tf=?", (symbol, tf))
        (ts,) = await cur.fetchone()
    return ts


async def count(symbol: str = None, tf: str = None) -> int:
    q = "SELECT COUNT(*) FROM bars"
    args = ()
    if symbol and tf:
        q += " WHERE symbol=? AND tf=?"
        args = (symbol, tf)
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(q, args)
        (n,) = await cur.fetchone()
    return n
