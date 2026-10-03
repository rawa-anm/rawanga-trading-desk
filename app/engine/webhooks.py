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
webhooks.py — webhook registry and signal delivery to Telegram.

Portable build: the recipient is set by the user in the settings.
Later: threads by category.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import aiosqlite
import httpx

from app import paths as _paths
DB = str(_paths.DB_PATH)
# Portable build: the bot token is taken from the user's data, not from the host keys.
BOT_KEY_FILE = _paths.DATA_DIR / "bot.key"
# In the public build there is no "creator" — the default chat is empty, set in the settings.
CREATOR_ID = 0

SCHEMA = """
CREATE TABLE IF NOT EXISTS webhooks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy TEXT NOT NULL,
  symbol TEXT NOT NULL DEFAULT '*',
  tf TEXT NOT NULL DEFAULT '*',
  thread_id INTEGER,
  chat_id TEXT,
  enabled INTEGER DEFAULT 1,
  template TEXT DEFAULT '',
  created_ts INTEGER
);
CREATE TABLE IF NOT EXISTS signals_sent (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy TEXT, symbol TEXT, tf TEXT, side TEXT,
  price REAL, ts INTEGER, sent_ts INTEGER
);
-- Trend state per instrument (the last recorded flip)
CREATE TABLE IF NOT EXISTS trend_state (
  symbol TEXT NOT NULL,
  tf TEXT NOT NULL,
  last_side TEXT,
  last_flip_ts INTEGER,
  updated_ts INTEGER,
  PRIMARY KEY (symbol, tf)
);
"""


def _token() -> str:
    try:
        return BOT_KEY_FILE.read_text().strip()
    except FileNotFoundError:
        return ""


# Default recipient for test notifications. Empty in the public build — the user
# sets the chat id in the settings / webhook row.
DEFAULT_CHAT = ""

# ── Optional forum/channel routing by category ───────────────────────────────
# The portable build has no predefined recipient: each webhook stores its own
# chat id (set in the UI). If you deliver to a forum that has category topics,
# put its chat id here (or leave empty to skip threading entirely) and the
# category→thread map below is applied automatically.
PROD_CHAT = ""          # e.g. "-1001234567890" (empty = disabled, per-webhook chat is used)
TREND_THREAD = 2
THREAD_FUTURES = 3
THREAD_STOCKS = 4
THREAD_CRYPTO = 5


def thread_for_category(category: str | None) -> int:
    """Forum thread by instrument category.

    trend → 2 (trend indicator), crypto → 5, stocks → 4, futures → 3.
    Unknown — the crypto thread (5) as a safe default (production chat).
    """
    return {
        "trend": TREND_THREAD,
        "crypto": THREAD_CRYPTO,
        "stocks": THREAD_STOCKS,
        "futures": THREAD_FUTURES,
        # indices (NDX/DJI) — not stocks; there is no separate thread → the crypto thread
        "index": THREAD_CRYPTO,
    }.get((category or "").lower(), THREAD_CRYPTO)


async def init():
    async with aiosqlite.connect(DB) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def add_webhook(strategy: str, symbol: str = "*", chat_id: str = str(CREATOR_ID),
                      thread_id: int | None = None, template: str = "") -> int:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "INSERT INTO webhooks(strategy,symbol,chat_id,thread_id,template,created_ts) "
            "VALUES(?,?,?,?,?,?)",
            (strategy, symbol, chat_id, thread_id, template, int(time.time() * 1000)))
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


async def already_sent(strategy: str, symbol: str, tf: str, ts: int, side: str) -> bool:
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


async def get_trend_state(symbol: str, tf: str) -> dict | None:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM trend_state WHERE symbol=? AND tf=?", (symbol.upper(), tf))
        r = await cur.fetchone()
        return dict(r) if r else None


async def set_trend_state(symbol: str, tf: str, side: str, flip_ts: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO trend_state(symbol,tf,last_side,last_flip_ts,updated_ts) "
            "VALUES(?,?,?,?,?)",
            (symbol.upper(), tf, side, int(flip_ts), int(time.time() * 1000)))
        await db.commit()


def format_signal(sig: dict, symbol: str, tf: str, strategy_title: str,
                  trade: dict | None = None) -> str:
    """Trade notification.

    Entry: side, entry price, stop (or a trailing marker), TP if present.
    Exit: reason (stop/take/reversal/signal) AND MANDATORY P/L.
    """
    dt = time.strftime("%Y-%m-%d %H:%M", time.gmtime(sig["ts"] / 1000))
    # Send time: that is the "event in chat". The bar time (dt) — as a separate
    # marker, so that bar close is not confused with the delivery moment.
    sent_dt = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
    side = sig["side"]
    price = round(float(sig["close"]), 6)

    # ── EXIT / CLOSE ──
    if side == "exit":
        of = sig.get("exit_of", "?")
        head = "🔵 CLOSE LONG" if of == "long" else "🔵 CLOSE SHORT"
        reason = sig.get("reason", "signal")
        rmap = {
            "stop": "🛑 stop-loss" + (" (trailing)" if sig.get("trailing") else ""),
            "tp": "🎯 take-profit",
            "reversal": "🔄 reversal",
            "signal": "📈 strategy signal",
        }
        lines = [f"{head}  {symbol}  ·  {tf}",
                 f"strategy: {strategy_title}",
                 f"reason: {rmap.get(reason, reason)}",
                 f"exit: {price}"]
        # P/L IS MANDATORY on close
        pl_pct = None
        if trade is not None:
            pl_pct = trade.get("pl_pct")
            entry = trade.get("entry")
            if entry is not None:
                lines.append(f"entry: {entry}")
        if pl_pct is None and sig.get("exit_of") and sig.get("entry"):
            sign = 1 if of == "long" else -1
            pl_pct = sign * (float(sig["close"]) / float(sig["entry"]) - 1) * 100
        if pl_pct is not None:
            emo = "🟢" if pl_pct >= 0 else "🔴"
            lines.append(f"P/L: {emo} {pl_pct:+.2f}%")
        lines.append(f"time: {sent_dt} UTC")
        lines.append(f"bar: {dt} UTC")
        return "\n".join(lines)

    # ── ENTRY ──
    head = "🟢 LONG" if side == "long" else "🔴 SHORT"
    lines = [f"{head}  {symbol}  ·  {tf}",
             f"strategy: {strategy_title}",
             f"entry: {price}"]
    stop = sig.get("stop")
    if stop is not None:
        lines.append(f"stop: {round(float(stop), 6)}")
    tp = sig.get("tp_price")
    if tp is not None:
        lines.append(f"take: {round(float(tp), 6)}")
    # candle volume factor on a 5-point scale
    vs = sig.get("vol_score")
    if vs is not None:
        lines.append(f"volume: {vs}/5 {'▮' * int(vs)}{'▯' * (5 - int(vs))}")
    lines.append(f"time: {sent_dt} UTC")
    lines.append(f"bar: {dt} UTC")
    return "\n".join(lines)


# ── Trend notifications (Supertrend 15m: VIX / SPX / BTC / USDTD) ────────────
# Trend symbol -> (label in the message, phrase for LONG, phrase for SHORT)
TREND_MSG = {
    "VIX":   ("VIX",    "Signs of a trend reversal to LONG", "Signs of a trend reversal to SHORT"),
    "USDTD": ("USDT.D", "Stablecoin dominance is falling!",    "Stablecoin dominance is rising!"),
    "BTC":   ("CRYPTO", "Signs of a trend reversal to LONG, it is recommended to close shorts",
                          "Signs of a trend reversal to SHORT, it is recommended to close longs"),
    "SPX":   ("SP500",  "Signs of a trend reversal to LONG, it is recommended to close shorts",
                          "Signs of a trend reversal to SHORT, it is recommended to close longs"),
}
# Bold emoji variants for BTC (CRYPTO) and SPX (SP500)
TREND_EMOJI = {
    "VIX":   ("🟢", "🚨"),
    "USDTD": ("🟢", "🚨"),
    "BTC":   ("🟢🟢🟢", "🚨🚨🚨"),
    "SPX":   ("🟢🟢🟢", "🚨🚨🚨"),
}
# Symbol -> key in TREND_MSG (the BTC trend is taken from the trading symbol BTC)
TREND_LABEL = {"VIX": "VIX", "SPX": "SPX", "BTC": "BTC", "USDTD": "USDTD"}
TREND_SYMBOLS = ["VIX", "SPX", "BTC", "USDTD"]


def format_trend(symbol: str, side: str) -> str:
    """Format of a trend notification. Example:
    <b>CRYPTO</b>🟢🟢🟢<b> Signs of a trend reversal to LONG, it is recommended to close shorts</b>
    """
    key = TREND_LABEL.get(symbol.upper(), symbol.upper())
    label, long_msg, short_msg = TREND_MSG.get(key, (key, "Reversal to LONG", "Reversal to SHORT"))
    up, dn = TREND_EMOJI.get(key, ("🟢", "🚨"))
    emoji, msg = (up, long_msg) if side == "long" else (dn, short_msg)
    return f"<b>{label}</b>{emoji}<b> {msg}</b>"

async def send_alert(text: str, chat_id: str | None = None,
                     thread_id: int | None = None,
                     client: httpx.AsyncClient | None = None) -> dict:
    """Sends a single notification to Telegram to the given chat_id (or the default)."""
    return await send_telegram(chat_id or DEFAULT_CHAT, text,
                               thread_id=thread_id, client=client)


async def send_telegram(chat_id: str, text: str,
                        thread_id: int | None = None,
                        client: httpx.AsyncClient | None = None,
                        token: str | None = None):
    # token: explicit (e.g. from the trading settings) → otherwise the default bot.
    token = token or _token()
    if not token:
        return {"ok": False, "error": "no bot token"}
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": True}
    if thread_id:
        payload["message_thread_id"] = thread_id
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=12)
    try:
        r = await client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json=payload)
        return r.json()
    finally:
        if own:
            await client.aclose()
