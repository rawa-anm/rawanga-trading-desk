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
broker.py — trading backend switch: BingX <-> Hyperliquid.

WHY
===
Two drivers with the same function set:
  app/exchange.py    — BingX   (proven in production, NOT TOUCHED)
  app/exchange_hl.py — Hyperliquid

This module decides which one a call goes to. Exactly ONE is active at any
time, but the keys of both exchanges are stored simultaneously — in separate
encrypted files — and you can switch at any moment.

WHY THIS WAY, INSTEAD OF EDITING exchange.py
============================================
The BingX branch stays byte-for-byte as it was: with active() == "bingx" every
call goes to exchange.py exactly as before, without intermediate conversions.
Zero regression risk in what is already battle-tested.

IMPORTANT WHEN SWITCHING
========================
Open positions on the INACTIVE exchange are NOT closed and NOT tracked: to the
app they become invisible. Close positions on the current exchange before
switching (the UI warns about this).
"""
from __future__ import annotations

from app import exchange as bx
from app import exchange_hl as hl

VALID = ("bingx", "hyperliquid")

# Active backend. Kept in memory; the value is restored from the DB at startup
# (main.py) and changed when settings are saved.
_active = "bingx"


def set_active(name: str) -> str:
    global _active
    n = (name or "").strip().lower()
    if n not in VALID:
        n = "bingx"
    if n != _active:
        _active = n
        reset_clients()
    return _active


def active() -> str:
    return _active


def reset_clients() -> None:
    """Drop the Hyperliquid SDK cache (after a key/environment change)."""
    try:
        hl.reset_client()
    except Exception:  # noqa: BLE001
        pass


def _m():
    return hl if _active == "hyperliquid" else bx


# ── Synchronous ─────────────────────────────────────────────────────

def masked_keys() -> dict:
    """Key summary for BOTH exchanges + which one is active.

    The UI reads has_keys/env/api_key_masked at the top level — those refer to
    the active exchange, so existing code keeps working.
    """
    b = bx.masked_keys()
    h = hl.masked_keys()
    cur = h if _active == "hyperliquid" else b
    return {
        "exchange": _active,
        "has_keys": cur.get("has_keys", False),
        "api_key_masked": cur.get("api_key_masked", cur.get("account_masked", "—")),
        "has_fund_pw": b.get("has_fund_pw", False),
        "env": cur.get("env", "live"),
        # Notifications are shared by both exchanges (stored in the BingX file)
        "has_notify_token": b.get("has_notify_token", False),
        "notify_token_masked": b.get("notify_token_masked", "—"),
        "notify_chat_id": b.get("notify_chat_id", ""),
        "has_mail_pass": b.get("has_mail_pass", False),
        "mail_pass_masked": b.get("mail_pass_masked", "—"),
        "smtp_host": b.get("smtp_host", ""),
        "smtp_port": b.get("smtp_port", ""),
        "smtp_user": b.get("smtp_user", ""),
        "smtp_tls": b.get("smtp_tls", ""),
        "notify_email": b.get("notify_email", ""),
        # Full per-exchange summaries — for the settings form
        "bingx": b,
        "hyperliquid": h,
    }


def notify_cfg() -> dict:
    """Telegram trade notifications — shared, independent of the exchange."""
    return bx.notify_cfg()


def mail_cfg() -> dict:
    """E-mail alert settings — shared, independent of the exchange."""
    return bx.mail_cfg()


def exchange_symbol(sym: str) -> str:
    """Our ticker -> symbol in the active exchange's format (BTC -> BTC-USDT / BTC)."""
    if _active == "hyperliquid":
        return f"{hl.hl_symbol(sym)}-USDT"
    return bx.bingx_symbol(sym)


# Compatibility: older code calls bingx_symbol but means "the exchange symbol"
def bingx_symbol(sym: str) -> str:
    return exchange_symbol(sym)


def has_keys() -> bool:
    return bool(masked_keys().get("has_keys"))


# ── Async: proxying ─────────────────────────────────────────────────

async def balance(client=None):
    return await _m().balance(client=client)


async def positions(symbol: str | None = None, client=None):
    return await _m().positions(symbol, client=client)


async def contracts(client=None):
    return await _m().contracts(client=client)


async def price(symbol: str, client=None):
    return await _m().price(symbol, client=client)


async def is_hedge_mode(client=None) -> bool:
    return await _m().is_hedge_mode(client=client)


async def set_leverage(symbol: str, leverage: int, client=None):
    return await _m().set_leverage(symbol, leverage, client=client)


async def get_leverage(symbol: str, client=None):
    return await _m().get_leverage(symbol, client=client)


async def place_market(symbol: str, side: str, position_side: str,
                       quote_usdt=None, quantity=None, reduce_only: bool = False,
                       client=None):
    return await _m().place_market(symbol, side, position_side,
                                   quote_usdt=quote_usdt, quantity=quantity,
                                   reduce_only=reduce_only, client=client)


async def close_position(symbol: str, position_side: str | None = None, client=None):
    return await _m().close_position(symbol, position_side, client=client)


async def pnl_history(client=None, start_ms: int | None = None) -> dict:
    """PnL total over the whole history — one format for the UI.

    Both drivers expose the same pnl_history() shape
    (realized / funding / total / records / since / until).
    """
    return await _m().pnl_history(client=client, start_ms=start_ms)
