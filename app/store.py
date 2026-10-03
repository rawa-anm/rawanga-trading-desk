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
store.py — registry of instruments, PER-TF strategy params and PER-TF webhooks.
Settings key: symbol × tf × strategy. Everything in SQLite.
"""
from __future__ import annotations

import json
import time

import aiosqlite
from app import paths as _paths

DB = str(_paths.DB_PATH)

SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments (
  symbol TEXT PRIMARY KEY,
  kind TEXT, yahoo TEXT, category TEXT, title TEXT,
  enabled INTEGER DEFAULT 1, created_ts INTEGER
);
-- Strategy params for a specific instrument+TF (override the global ones)
CREATE TABLE IF NOT EXISTS strategy_params (
  symbol TEXT NOT NULL DEFAULT '*',
  tf TEXT NOT NULL DEFAULT '*',
  strategy TEXT NOT NULL,
  params TEXT,
  updated_ts INTEGER,
  PRIMARY KEY (symbol, tf, strategy)
);
-- Webhooks: a row = one route symbol × tf × strategy
CREATE TABLE IF NOT EXISTS webhooks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL DEFAULT '*',
  tf TEXT NOT NULL DEFAULT '*',
  strategy TEXT NOT NULL DEFAULT '*',
  chat_id TEXT,
  thread_id INTEGER,
  enabled INTEGER DEFAULT 1,
  template TEXT DEFAULT '',
  created_ts INTEGER
);
CREATE TABLE IF NOT EXISTS signals_sent (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy TEXT, symbol TEXT, tf TEXT, side TEXT,
  price REAL, ts INTEGER, sent_ts INTEGER
);
-- ── Real trading (BingX) ───────────────────────────────────
-- Settings (key/value): live_enabled, leverage, entry_pct
CREATE TABLE IF NOT EXISTS trade_settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
-- Traded tickers (trading only for the ones enabled here)
CREATE TABLE IF NOT EXISTS trade_tickers (
  symbol TEXT PRIMARY KEY,
  category TEXT,
  bingx_symbol TEXT,
  enabled INTEGER DEFAULT 1,
  added_ts INTEGER
);
-- Order execution log
CREATE TABLE IF NOT EXISTS trade_exec (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER, symbol TEXT, bingx_symbol TEXT,
  action TEXT, side TEXT, qty REAL, price REAL,
  ok INTEGER, error TEXT, raw TEXT
);
"""


async def init():
    async with aiosqlite.connect(DB) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def seed(defaults: dict):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT COUNT(*) FROM instruments")
        (n,) = await cur.fetchone()
        if n:
            return
        rows = [(s, k, y, c, t, 1, int(time.time() * 1000))
                for s, (k, y, c, t) in defaults.items()]
        await db.executemany(
            "INSERT OR IGNORE INTO instruments(symbol,kind,yahoo,category,title,enabled,created_ts) "
            "VALUES(?,?,?,?,?,?,?)", rows)
        await db.commit()


# ── instruments ────────────────────────────────────────────────
async def list_instruments() -> list[dict]:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM instruments ORDER BY category, symbol")
        return [dict(r) for r in await cur.fetchall()]


async def get(symbol: str) -> dict | None:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM instruments WHERE symbol=?", (symbol.upper(),))
        r = await cur.fetchone()
        return dict(r) if r else None


async def add(symbol, kind, yahoo, category, title) -> bool:
    async with aiosqlite.connect(DB) as db:
        try:
            await db.execute(
                "INSERT INTO instruments(symbol,kind,yahoo,category,title,created_ts) "
                "VALUES(?,?,?,?,?,?)",
                (symbol.upper(), kind, yahoo, category, title, int(time.time() * 1000)))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove(symbol: str) -> bool:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("DELETE FROM instruments WHERE symbol=?", (symbol.upper(),))
        await db.commit()
        return cur.rowcount > 0


# ── strategy params (per symbol × tf × strategy) ───────────
async def set_params(symbol: str, tf: str, strategy: str, params: dict):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO strategy_params(symbol,tf,strategy,params,updated_ts) "
            "VALUES(?,?,?,?,?)",
            (symbol.upper(), tf, strategy, json.dumps(params), int(time.time() * 1000)))
        await db.commit()


async def get_params(symbol: str, tf: str, strategy: str) -> dict:
    """Cascade: exact match → (symbol,*,*) → (*,tf,*) → (*,*,strategy) → {}."""
    async with aiosqlite.connect(DB) as db:
        for key in ((symbol.upper(), tf, strategy), (symbol.upper(), "*", strategy),
                    ("*", tf, strategy), ("*", "*", strategy)):
            cur = await db.execute(
                "SELECT params FROM strategy_params WHERE symbol=? AND tf=? AND strategy=?",
                key)
            r = await cur.fetchone()
            if r and r[0]:
                return json.loads(r[0])
    return {}


async def all_params() -> list[dict]:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM strategy_params ORDER BY symbol, tf, strategy")
        return [dict(r) for r in await cur.fetchall()]


# ── webhooks (per symbol × tf × strategy) ───────────────────────
async def add_webhook(symbol, tf, strategy, chat_id, thread_id=None, template="") -> int:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "INSERT INTO webhooks(symbol,tf,strategy,chat_id,thread_id,template,created_ts) "
            "VALUES(?,?,?,?,?,?,?)",
            (symbol.upper(), tf, strategy, chat_id, thread_id, template,
             int(time.time() * 1000)))
        await db.commit()
        return cur.lastrowid


async def list_webhooks() -> list[dict]:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM webhooks ORDER BY id")
        return [dict(r) for r in await cur.fetchall()]


async def remove_webhook(hid: int) -> bool:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("DELETE FROM webhooks WHERE id=?", (hid,))
        await db.commit()
        return cur.rowcount > 0


async def toggle_webhook(hid: int, enabled: bool) -> bool:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("UPDATE webhooks SET enabled=? WHERE id=?",
                               (1 if enabled else 0, hid))
        await db.commit()
        return cur.rowcount > 0


async def update_webhook(hid: int, fields: dict) -> bool:
    """Spot update of a webhook (only the fields passed in)."""
    allowed = ("symbol", "tf", "strategy", "chat_id", "thread_id", "template", "enabled")
    sets, args = [], []
    for k in allowed:
        if k in fields and fields[k] is not None:
            v = fields[k]
            if k == "symbol":
                v = str(v).upper()
            if k == "enabled":
                v = 1 if v else 0
            sets.append(f"{k}=?")
            args.append(v)
    if not sets:
        return False
    args.append(hid)
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            f"UPDATE webhooks SET {', '.join(sets)} WHERE id=?", args)
        await db.commit()
        return cur.rowcount > 0


async def toggle_cell(symbol: str, tf: str, strategy: str, enabled: bool) -> int:
    """Enable/disable a webhook for the exact symbol×tf×strategy cell. Creates a row if absent."""
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT id FROM webhooks WHERE symbol=? AND tf=? AND strategy=?",
            (symbol.upper(), tf, strategy))
        r = await cur.fetchone()
        if r:
            await db.execute("UPDATE webhooks SET enabled=? WHERE id=?",
                             (1 if enabled else 0, r[0]))
        else:
            await db.execute(
                "INSERT INTO webhooks(symbol,tf,strategy,chat_id,enabled,created_ts) "
                "VALUES(?,?,?,?,?,?)",
                (symbol.upper(), tf, strategy, None, 1 if enabled else 0,
                 int(time.time() * 1000)))
        await db.commit()
    return 1


async def matrix() -> dict:
    """Webhook state for the symbol×tf×strategy matrix: {'BTC|15m|stv3': true, ...}."""
    out = {}
    for w in await list_webhooks():
        out[f"{w['symbol']}|{w['tf']}|{w['strategy']}"] = bool(w["enabled"])
    return out


async def match_webhooks(symbol: str, tf: str, strategy: str) -> list[dict]:
    """Webhooks matching a signal: exact match or '*' for any field."""
    out = []
    for w in await list_webhooks():
        if not w["enabled"]:
            continue
        if w["symbol"] not in ("*", symbol.upper()):
            continue
        if w["tf"] not in ("*", tf):
            continue
        if w["strategy"] not in ("*", strategy):
            continue
        out.append(w)
    return out


# ── deduplication of sent signals ─────────────────────────
async def already_sent(strategy, symbol, tf, ts, side) -> bool:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT 1 FROM signals_sent WHERE strategy=? AND symbol=? AND tf=? "
            "AND ts=? AND side=? LIMIT 1", (strategy, symbol, tf, ts, side))
        return await cur.fetchone() is not None


async def mark_sent(strategy, symbol, tf, side, price, ts):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO signals_sent(strategy,symbol,tf,side,price,ts,sent_ts) "
            "VALUES(?,?,?,?,?,?,?)",
            (strategy, symbol, tf, side, price, ts, int(time.time() * 1000)))
        await db.commit()


# ── Real trading: settings / tickers / log ─────────────
DEFAULT_TRADE_SETTINGS = {
    "live_enabled": "0",   # 0/1 — the main real-trading switch
    "leverage": "5",       # leverage for swap positions
    "entry_pct": "10",     # % of free balance per position
}


async def get_trade_settings() -> dict:
    out = dict(DEFAULT_TRADE_SETTINGS)
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT key,value FROM trade_settings")
        for k, v in await cur.fetchall():
            out[k] = v
    out["live_enabled"] = str(out.get("live_enabled", "0")) in ("1", "true", "True")
    try:
        out["leverage"] = int(out.get("leverage", 5))
    except Exception:  # noqa: BLE001
        out["leverage"] = 5
    try:
        out["entry_pct"] = float(out.get("entry_pct", 10))
    except Exception:  # noqa: BLE001
        out["entry_pct"] = 10.0
    return out


async def set_trade_settings(fields: dict):
    async with aiosqlite.connect(DB) as db:
        for k in ("live_enabled", "leverage", "entry_pct"):
            if k not in fields or fields[k] is None:
                continue
            v = fields[k]
            if k == "live_enabled":
                v = "1" if (v is True or str(v) in ("1", "true", "True", "on")) else "0"
            await db.execute(
                "INSERT OR REPLACE INTO trade_settings(key,value) VALUES(?,?)", (k, str(v)))
        await db.commit()


async def list_trade_tickers() -> list[dict]:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM trade_tickers ORDER BY symbol")
        return [dict(r) for r in await cur.fetchall()]


async def add_trade_ticker(symbol: str, category: str, bingx_symbol: str) -> bool:
    async with aiosqlite.connect(DB) as db:
        try:
            await db.execute(
                "INSERT INTO trade_tickers(symbol,category,bingx_symbol,enabled,added_ts) "
                "VALUES(?,?,?,1,?)",
                (symbol.upper(), category, bingx_symbol, int(time.time() * 1000)))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove_trade_ticker(symbol: str) -> bool:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("DELETE FROM trade_tickers WHERE symbol=?", (symbol.upper(),))
        await db.commit()
        return cur.rowcount > 0


async def set_trade_ticker(symbol: str, enabled: bool) -> bool:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("UPDATE trade_tickers SET enabled=? WHERE symbol=?",
                               (1 if enabled else 0, symbol.upper()))
        await db.commit()
        return cur.rowcount > 0


async def is_trade_enabled(symbol: str) -> bool:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT enabled FROM trade_tickers WHERE symbol=? AND enabled=1", (symbol.upper(),))
        return await cur.fetchone() is not None


async def log_exec(symbol, bingx_symbol, action, side, qty, price, ok, error, raw):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO trade_exec(ts,symbol,bingx_symbol,action,side,qty,price,ok,error,raw) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (int(time.time() * 1000), symbol, bingx_symbol, action, side, qty, price,
             1 if ok else 0, error, raw))
        await db.commit()


async def list_exec(limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM trade_exec ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]
