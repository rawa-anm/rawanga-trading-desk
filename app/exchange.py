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
exchange.py — integration of real trading with the BingX exchange (USDT-M perpetual swap).

We trade ONLY futures (swap). What is actually available is what is present in /quote/contracts:
crypto + tokenized assets that the exchange lists (currently, of the "non-crypto", XAUT,
tokenized gold). Tokenized STOCKS and commodity futures are NOT in the BingX swap listing
as of the verification date — the module trades only what the exchange actually offers.

Security (mandatory):
- API keys are stored ENCRYPTED (Fernet) in state/bx_secrets.enc;
  master key — <data>/bx_secret.key (0600). We never log it or expose it externally.
- Real trading is DISABLED by default (trade_settings.live_enabled=0).
- We send orders only when: (a) live_enabled=1, (b) symbol is in the tradable list (enabled=1),
  (c) position size is derived from % of balance.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path

import httpx

BASE_LIVE = "https://open-api.bingx.com"
BASE_VST = "https://open-api-vst.bingx.com"
SRC = "BX-AI-SKILL"
RECV_WINDOW = 5000

from app import paths as _paths
STATE = _paths.DATA_DIR
SECRETS = _paths.SECRETS_PATH
KEYFILE = _paths.SECRET_KEY_PATH


# ── Secrets (Fernet) ────────────────────────────────────────────────

def _fernet():
    from cryptography.fernet import Fernet
    if not KEYFILE.exists():
        KEYFILE.write_bytes(Fernet.generate_key())
        os.chmod(KEYFILE, 0o600)
    key = KEYFILE.read_bytes().strip()
    if not key:
        KEYFILE.write_bytes(Fernet.generate_key())
        key = KEYFILE.read_bytes().strip()
    return Fernet(key)


def save_secrets(d: dict) -> None:
    SECRETS.write_bytes(_fernet().encrypt(json.dumps(d).encode()))
    os.chmod(SECRETS, 0o600)


def load_secrets() -> dict:
    if not SECRETS.exists():
        return {}
    try:
        return json.loads(_fernet().decrypt(SECRETS.read_bytes()))
    except Exception:  # noqa: BLE001
        return {}


def _mask(v: str) -> str:
    v = v or ""
    return (v[:6] + "…" + v[-4:]) if len(v) > 12 else ("—" if not v else "…")


def masked_keys() -> dict:
    """Safe summary for the UI — without the keys themselves."""
    s = load_secrets()
    return {
        "has_keys": bool(s.get("api_key") and s.get("secret_key")),
        "api_key_masked": _mask(s.get("api_key", "")),
        "has_fund_pw": bool(s.get("fund_password")),
        "env": s.get("env", "live"),
        "has_notify_token": bool(s.get("notify_bot_token")),
        "notify_token_masked": _mask(s.get("notify_bot_token", "")),
        "notify_chat_id": s.get("notify_chat_id", ""),
        "has_mail_pass": bool(s.get("smtp_pass")),
        "mail_pass_masked": _mask(s.get("smtp_pass", "")),
        "smtp_host": s.get("smtp_host", ""),
        "smtp_port": s.get("smtp_port", ""),
        "smtp_user": s.get("smtp_user", ""),
        "smtp_tls": s.get("smtp_tls", ""),
        "notify_email": s.get("notify_email", ""),
    }


def notify_cfg() -> dict:
    """Delivery settings for real-trade notifications (token/chat)."""
    s = load_secrets()
    return {"token": s.get("notify_bot_token", "") or "",
            "chat_id": s.get("notify_chat_id", "") or ""}


def mail_cfg() -> dict:
    """Settings for e-mail alerts (the user's own SMTP server). Empty host = off."""
    s = load_secrets()
    return {
        "host": s.get("smtp_host", "") or "",
        "port": s.get("smtp_port", "") or "",
        "user": s.get("smtp_user", "") or "",
        "password": s.get("smtp_pass", "") or "",
        "tls": str(s.get("smtp_tls", "1")) not in ("0", "false", "False", ""),
        "to": s.get("notify_email", "") or s.get("smtp_user", "") or "",
        "from": s.get("smtp_user", "") or "",
    }


# ── Signature and requests ───────────────────────────────────────────────

def _sign(qs: str, secret: str) -> str:
    return hmac.new(secret.encode(), qs.encode(), hashlib.sha256).hexdigest()


def _base() -> str:
    return BASE_VST if load_secrets().get("env") == "vst" else BASE_LIVE


# ── Time synchronization with the server ────────────────────────────
# The host clock may lag/run ahead → BingX rejects requests with 100421
# ("timestamp mismatch"). We compute offset = serverTime - localTime and
# apply it to the timestamp in signed requests. We do not touch the system clock.
_OFFSET_MS = 0
_OFFSET_AT = 0.0


async def _sync_time(client, force: bool = False) -> int:
    global _OFFSET_MS, _OFFSET_AT
    now = time.time()
    if not force and _OFFSET_AT and (now - _OFFSET_AT) < 300:
        return _OFFSET_MS
    try:
        r = await client.get(f"{_base()}/openApi/swap/v2/server/time",
                             headers={"X-SOURCE-KEY": SRC})
        st = int(r.json()["data"]["serverTime"])
        _OFFSET_MS = st - int(now * 1000)
        _OFFSET_AT = now
    except Exception:  # noqa: BLE001
        pass
    return _OFFSET_MS


def _now_ms() -> int:
    return int(time.time() * 1000) + _OFFSET_MS


async def request(method: str, path: str, params: dict | None = None, *,
                  signed: bool = False, client: httpx.AsyncClient | None = None) -> dict:
    params = dict(params or {})
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=15)
    headers = {"X-SOURCE-KEY": SRC}
    try:
        if not signed:
            r = await client.request(method, f"{_base()}{path}", params=params, headers=headers)
            r.raise_for_status()
            return r.json()
        s = load_secrets()
        if not (s.get("api_key") and s.get("secret_key")):
            raise RuntimeError("BingX API keys are not set")
        await _sync_time(client)
        # One retry on a timestamp error (100421):
        # force a clock resync and retry — the clock may have drifted.
        for attempt in (1, 2):
            p = dict(params)
            p["timestamp"] = _now_ms()
            p.setdefault("recvWindow", RECV_WINDOW)
            qs = "&".join(f"{k}={p[k]}" for k in sorted(p))
            sig = _sign(qs, s["secret_key"])
            headers["X-BX-APIKEY"] = s["api_key"]
            r = await client.request(method, f"{_base()}{path}?{qs}&signature={sig}", headers=headers)
            r.raise_for_status()
            j = r.json()
            if j.get("code") == 100421 and attempt == 1:
                await _sync_time(client, force=True)
                continue
            return j
    finally:
        if own:
            await client.aclose()


# ── Public data ────────────────────────────────────────────────

async def contracts(client=None) -> list[dict]:
    d = await request("GET", "/openApi/swap/v2/quote/contracts", client=client)
    return d.get("data") or []


async def server_time_sync(client=None) -> int:
    """Forced clock resync; returns the current offset (ms)."""
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=10)
    try:
        return await _sync_time(client, force=True)
    finally:
        if own:
            await client.aclose()


async def price(symbol: str, client=None) -> float | None:
    try:
        d = await request("GET", "/openApi/swap/v2/quote/price",
                          {"symbol": symbol}, client=client)
        return float(d["data"]["price"])
    except Exception:  # noqa: BLE001
        return None


# ── Private data ────────────────────────────────────────────────

async def balance(client=None) -> dict | None:
    d = await request("GET", "/openApi/swap/v3/user/balance", signed=True, client=client)
    arr = d.get("data") or []
    return arr[0] if arr else None


async def positions(symbol: str | None = None, client=None) -> list[dict]:
    p = {"symbol": symbol} if symbol else {}
    d = await request("GET", "/openApi/swap/v2/user/positions", p, signed=True, client=client)
    return d.get("data") or []


async def income(income_type: str = "REALIZED_PNL", limit: int = 200, client=None) -> list[dict]:
    d = await request("GET", "/openApi/swap/v2/user/income",
                      {"incomeType": income_type, "limit": limit}, signed=True, client=client)
    return d.get("data") or []


def realised_pnl_total(records: list[dict]) -> float:
    tot = 0.0
    for r in records:
        try:
            tot += float(r.get("income", 0))
        except Exception:  # noqa: BLE001
            pass
    return round(tot, 4)


# ── Trading operations ───────────────────────────────────────────────

async def is_hedge_mode(client=None) -> bool:
    """true = hedge mode (dual side); false = one-way."""
    try:
        r = await request("GET", "/openApi/swap/v1/positionSide/dual", signed=True, client=client)
        return str(r.get("data", {}).get("dualSidePosition", "")).lower() == "true"
    except Exception:  # noqa: BLE001
        return True  # safer to assume hedge (explicit positionSide)


async def set_leverage(symbol: str, leverage: int, client=None) -> dict:
    """Explicitly sets leverage. In hedge mode — separately for LONG and SHORT.

    Without explicit leverage BingX may apply/keep the maximum —
    so we set it explicitly before every entry.
    """
    lev = int(leverage)
    if await is_hedge_mode(client):
        rl = await request("POST", "/openApi/swap/v2/trade/leverage",
                           {"symbol": symbol, "side": "LONG", "leverage": lev},
                           signed=True, client=client)
        rs = await request("POST", "/openApi/swap/v2/trade/leverage",
                           {"symbol": symbol, "side": "SHORT", "leverage": lev},
                           signed=True, client=client)
        return {"long": rl, "short": rs}
    return await request("POST", "/openApi/swap/v2/trade/leverage",
                         {"symbol": symbol, "side": "BOTH", "leverage": lev},
                         signed=True, client=client)


async def place_market(symbol: str, side: str, position_side: str,
                       quote_usdt: float | None = None, quantity: float | None = None,
                       reduce_only: bool = False, client=None) -> dict:
    """Market order on BingX swap.

    side: BUY (open long / close short), SELL (open short / close long).
    position_side: LONG / SHORT / BOTH.
    Exactly one of: quote_usdt (notional in USDT) or quantity (in the base coin).
    """
    p = {"symbol": symbol, "side": side, "positionSide": position_side, "type": "MARKET"}
    if quote_usdt is not None:
        p["quoteOrderQty"] = round(float(quote_usdt), 4)
    elif quantity is not None:
        p["quantity"] = float(quantity)
    else:
        raise ValueError("quote_usdt or quantity is required")
    if reduce_only:
        p["reduceOnly"] = "true"
    return await request("POST", "/openApi/swap/v2/trade/order", p, signed=True, client=client)


async def close_position(symbol: str, position_side: str | None = None, client=None) -> dict:
    """Close a position WITHOUT the risk of opening the opposite one.

    BingX `closePosition` accepts ONLY `positionId` (not symbol+positionSide!).
    Therefore we find the REAL open position and close it by positionId.
    If there is no positionId — fallback: reduce-only market order.
    """
    pos = await positions(symbol, client=client)
    target = None
    for p in pos:
        amt = float(p.get("positionAmt") or 0)
        if amt == 0:
            continue
        if position_side in (None, "BOTH", p.get("positionSide")):
            target = p
            break
    if not target:
        return {"code": 0, "msg": "no position", "data": {}}
    pid = target.get("positionId")
    side = target.get("positionSide")
    if pid:
        return await request("POST", "/openApi/swap/v1/trade/closePosition",
                             {"positionId": str(pid)}, signed=True, client=client)
    # fallback (no positionId): an opposite market order with the same positionSide
    # reduces the position in hedge mode; reduceOnly must not be sent in BingX hedge mode.
    amt = abs(float(target.get("positionAmt") or 0))
    mk = "SELL" if side == "LONG" else "BUY"
    return await place_market(symbol, mk, side, quantity=amt, client=client)


async def get_leverage(symbol: str, client=None) -> dict:
    r = await request("GET", "/openApi/swap/v2/trade/leverage", {"symbol": symbol},
                      signed=True, client=client)
    return r.get("data", {})


# ── Mapping of our symbols → BingX pairs ─────────────────────────────
# Aliases: our ticker -> base asset on BingX.
ALIASES = {
    "PEPE": "1000PEPE",
    "GRAM": "GRAMTON",
    "GOLD": "XAUT",   # tokenized gold (if we trade "gold")
}


def bingx_symbol(sym: str) -> str:
    s = ALIASES.get(sym.upper(), sym.upper())
    return f"{s}-USDT"
