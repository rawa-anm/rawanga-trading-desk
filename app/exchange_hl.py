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
exchange_hl.py — real trading driver for Hyperliquid (perp).

WHY A SEPARATE MODULE
=====================
Hyperliquid is fundamentally different from BingX, so "tweaking exchange.py"
is not possible — a second driver with the same function set is needed:

  ┌──────────────┬────────────────────────┬──────────────────────────┐
  │              │ BingX (exchange.py)    │ Hyperliquid (this file)  │
  ├──────────────┼────────────────────────┼──────────────────────────┤
  │ signature    │ HMAC-SHA256            │ EIP-712 + msgpack        │
  │ keys         │ api_key + secret_key   │ agent private key +      │
  │              │                        │ master account address   │
  │ positions    │ hedge LONG/SHORT       │ one-way only             │
  │ order        │ MARKET                 │ aggressive IOC limit     │
  │ min notional │ ~5 USDT                │ 10 USDT                  │
  │ identifier   │ "BTC-USDT"             │ "BTC" + asset index      │
  └──────────────┴────────────────────────┴──────────────────────────┘

Functions are named exactly as in exchange.py on purpose: trader.py can work
with either driver without knowing which one is selected.

SECURITY
========
- The agent wallet private key is stored ENCRYPTED (Fernet) in
  <data>/hl_secrets.enc; the master key is <data>/hl_secret.key (0600).
  Separate files from BingX: a leak of one does not expose the other.
- The key is never logged and never returned to the UI (mask only).
- Real trading is enabled by the shared switch trade_settings.live_enabled
  and additionally requires trade_settings.exchange == "hyperliquid".

IMPORTANT ABOUT KEYS (a common mistake)
=======================================
Trading is NOT done with the account's own private key, but with an
"API wallet" / agent wallet: at https://app.hyperliquid.xyz/API you create an
agent, receive its private key, and orders are signed with it ON BEHALF OF the
master account. Hence TWO values are needed: the master account address (0x...)
and the agent private key. If you paste the agent's address instead, account
data comes back empty (the classic trap).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import httpx

from app import paths as _paths

log = logging.getLogger("tv.hl")

STATE = _paths.DATA_DIR
SECRETS = _paths.HL_SECRETS_PATH
KEYFILE = _paths.HL_SECRET_KEY_PATH

MAINNET = "https://api.hyperliquid.xyz"
TESTNET = "https://api.hyperliquid-testnet.xyz"

MIN_NOTIONAL = 10.0      # Hyperliquid does not accept orders below 10 USDT
SLIPPAGE = 0.01          # 1% slippage for the IOC "market" order

# Our ticker -> coin on Hyperliquid.
# NOTE: PEPE is called kPEPE on HL (price ×1000, size ×1000).
# GOLD/XAUT is not in the HL perp listing — cannot be traded.
ALIASES = {
    "PEPE": "kPEPE",
    "GRAM": "GRAM",
}
# No rescaling needed: the size is always computed from the price of the HL
# coin itself (the kPEPE price already includes the ×1000 factor), and closing
# takes the position size as-is. Converting through a coefficient would only
# introduce a ×1000 error.


# ── Secrets (Fernet) ────────────────────────────────────────────────

# Last secrets-read error. Needed so that "no keys" and "keys failed to
# decrypt" do not look the same: a silent except would turn a lost key into
# "not configured".
SECRETS_ERROR: str | None = None


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
    global SECRETS_ERROR
    SECRETS.write_bytes(_fernet().encrypt(json.dumps(d).encode()))
    os.chmod(SECRETS, 0o600)
    SECRETS_ERROR = None


def load_secrets() -> dict:
    """Read the secrets. Empty dict = "not configured", but the reason goes to SECRETS_ERROR."""
    global SECRETS_ERROR
    if not SECRETS.exists():
        SECRETS_ERROR = None
        return {}
    try:
        data = json.loads(_fernet().decrypt(SECRETS.read_bytes()))
        SECRETS_ERROR = None
        return data if isinstance(data, dict) else {}
    except Exception as e:  # noqa: BLE001
        # Do NOT swallow silently: otherwise the file exists, keys "are not
        # there", and it is impossible to tell why.
        SECRETS_ERROR = f"{type(e).__name__}: {e}"
        log.warning("Hyperliquid: secrets failed to decrypt (%s)", SECRETS_ERROR)
        return {}


def _mask(v: str) -> str:
    v = v or ""
    if not v:
        return "—"
    return (v[:6] + "…" + v[-4:]) if len(v) > 12 else "…"


def masked_keys() -> dict:
    """Safe summary for the UI — without the keys themselves."""
    s = load_secrets()
    has_acct = bool(s.get("account_address"))
    has_pk = bool(s.get("api_private_key"))
    return {
        "has_keys": has_acct and has_pk,
        "account_address": s.get("account_address", ""),
        "account_masked": _mask(s.get("account_address", "")),
        "has_private_key": has_pk,
        "pk_masked": "…" + (s.get("api_private_key", "")[-4:] if has_pk else ""),
        "env": s.get("env", "mainnet"),
        "error": SECRETS_ERROR,
    }


def _base() -> str:
    return TESTNET if load_secrets().get("env") == "testnet" else MAINNET


# ── Read (public + info) ────────────────────────────────────────────

async def info(payload: dict, client: httpx.AsyncClient | None = None) -> dict | list:
    """POST /info — the single read entry point on Hyperliquid."""
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=20)
    try:
        r = await client.post(f"{_base()}/info", json=payload)
        r.raise_for_status()
        return r.json()
    finally:
        if own:
            await client.aclose()


async def meta(client=None) -> dict:
    """Perp metadata: universe (coin list + szDecimals + maxLeverage)."""
    d = await info({"type": "meta"}, client=client)
    return d if isinstance(d, dict) else {"universe": []}


async def asset_index(coin: str, client=None) -> int | None:
    """Coin index in the universe — also the asset id used in orders."""
    m = await meta(client=client)
    for i, u in enumerate(m.get("universe", [])):
        if u.get("name") == coin:
            return i
    return None


async def sz_decimals(coin: str, client=None) -> int:
    m = await meta(client=client)
    for u in m.get("universe", []):
        if u.get("name") == coin:
            return int(u.get("szDecimals", 0))
    return 0


async def max_leverage(coin: str, client=None) -> int:
    m = await meta(client=client)
    for u in m.get("universe", []):
        if u.get("name") == coin:
            return int(u.get("maxLeverage", 1))
    return 1


async def all_mids(client=None) -> dict:
    d = await info({"type": "allMids"}, client=client)
    return d if isinstance(d, dict) else {}


async def price(coin: str, client=None) -> float | None:
    try:
        m = await all_mids(client=client)
        v = m.get(coin)
        return float(v) if v else None
    except Exception:  # noqa: BLE001
        return None


async def contracts(client=None) -> list[dict]:
    """Tradable coin list — the analogue of BingX /quote/contracts for the UI."""
    m = await meta(client=client)
    return [{"symbol": f"{u['name']}-USDT", "coin": u["name"],
             "szDecimals": u.get("szDecimals"), "maxLeverage": u.get("maxLeverage")}
            for u in m.get("universe", []) if not u.get("isDelisted")]


# ── Private account data ────────────────────────────────────────────

def _acct() -> str:
    return load_secrets().get("account_address", "")


async def abstraction(client=None) -> str:
    """Account mode: "unifiedAccount" | "portfolioMargin" | "disabled" (standard).

    CRITICAL for the balance. Hyperliquid docs:
      "Under unified account or portfolio margin, the user's cross margin
       positions ... show all balances and holds in the SPOT clearinghouse state.
       Individual perp dex user states are NOT meaningful."
    That is, under unifiedAccount clearinghouseState.marginSummary.accountValue
    is empty NOT because there is no money, but because this scheme does not
    track it there. Spot + perp must NOT be added together — that would double
    count.
    """
    a = _acct()
    if not a:
        return "disabled"
    try:
        d = await info({"type": "userAbstraction", "user": a}, client=client)
    except Exception:  # noqa: BLE001
        return "disabled"
    if isinstance(d, str):
        return d
    # some API versions return an object
    if isinstance(d, dict):
        return str(d.get("abstraction") or "disabled")
    return "disabled"


async def spot_state(client=None) -> dict:
    """Spot balances. Under unifiedAccount — the source of truth for the account."""
    a = _acct()
    if not a:
        return {}
    d = await info({"type": "spotClearinghouseState", "user": a}, client=client)
    return d if isinstance(d, dict) else {}


async def clearinghouse(client=None) -> dict:
    a = _acct()
    if not a:
        return {}
    d = await info({"type": "clearinghouseState", "user": a}, client=client)
    return d if isinstance(d, dict) else {}


async def balance(client=None) -> dict | None:
    """Summary in UI format (equity/availableMargin/unrealizedProfit).

    TWO ACCOUNT MODES — and they must not be confused.

    ── unifiedAccount / portfolioMargin ──
    Hyperliquid docs:
      "For API users, unified account and portfolio margin show all balances
       and holds in the spot clearinghouse state. Individual perp dex user
       states are not meaningful."
      "Under unified account or portfolio margin, use spot balances endpoint
       instead for trading account balance across spot and perps."
    Therefore clearinghouseState.marginSummary.accountValue = 0 does NOT mean
    "no money" — this scheme simply does not track it there. The balance comes
    from spotClearinghouseState. Adding spot + perp is NOT allowed: it is the
    same balance in two representations, and the sum would double count.

    ── disabled (standard, separate accounts) ──
    Previous behaviour: equity from marginSummary.accountValue.

    Unrealized PnL in both modes comes from positions — they are always present
    in clearinghouseState.
    """
    a = _acct()
    if not a:
        return None

    st = await clearinghouse(client=client)
    if not st:
        return None

    unreal = 0.0
    for ap in st.get("assetPositions") or []:
        p = ap.get("position") or {}
        try:
            unreal += float(p.get("unrealizedPnl") or 0)
        except (TypeError, ValueError):
            pass

    mode = await abstraction(client=client)

    if mode in ("unifiedAccount", "portfolioMargin"):
        sp = await spot_state(client=client)
        if not sp:
            return None
        equity = 0.0
        for b in sp.get("balances") or []:
            try:
                equity += float(b.get("total") or 0)
            except (TypeError, ValueError):
                pass
        # Free = total - hold per asset (hold is in orders/margin).
        avail = 0.0
        for b in sp.get("balances") or []:
            try:
                avail += float(b.get("total") or 0) - float(b.get("hold") or 0)
            except (TypeError, ValueError):
                pass
        # Margin in use: maintenance from the perp state (still valid as a risk
        # source even when marginSummary is not maintained).
        try:
            used = float(st.get("crossMaintenanceMarginUsed") or 0)
        except (TypeError, ValueError):
            used = 0.0
        return {
            "equity": round(equity, 4),
            "availableMargin": round(avail, 4),
            "usedMargin": round(used, 4),
            "unrealizedProfit": round(unreal, 4),
            "balance": round(equity, 4),
            "mode": mode,
        }

    ms = st.get("marginSummary") or {}
    try:
        equity = float(ms.get("accountValue") or 0)
        avail = float(st.get("withdrawable") or 0)
        used = float(ms.get("totalMarginUsed") or 0)
    except (TypeError, ValueError):
        return None
    return {
        "equity": round(equity, 4),
        "availableMargin": round(avail, 4),
        "usedMargin": round(used, 4),
        "unrealizedProfit": round(unreal, 4),
        "balance": round(equity, 4),
        "mode": mode,
    }


async def positions(symbol: str | None = None, client=None) -> list[dict]:
    """Positions in BingX format (positionAmt/positionSide/avgPrice) — for the UI.

    Hyperliquid: szi > 0 = long, szi < 0 = short; it has no positionSide, so we
    fill in LONG/SHORT to keep the interface unchanged.
    """
    st = await clearinghouse(client=client)
    coin = hl_symbol(symbol) if symbol else None
    out = []
    for ap in st.get("assetPositions") or []:
        p = ap.get("position") or {}
        c = p.get("coin")
        if coin and c != coin:
            continue
        try:
            szi = float(p.get("szi") or 0)
        except (TypeError, ValueError):
            continue
        if szi == 0:
            continue
        out.append({
            "symbol": f"{c}-USDT",
            "positionAmt": szi,
            "positionSide": "LONG" if szi > 0 else "SHORT",
            "avgPrice": p.get("entryPx"),
            "markPrice": None,
            "unrealizedProfit": p.get("unrealizedPnl"),
            "leverage": (p.get("leverage") or {}).get("value"),
            "liquidationPrice": p.get("liquidationPx"),
            "positionValue": p.get("positionValue"),
        })
    return out


async def income(client=None, start_ms: int | None = None) -> list[dict]:
    """PnL history: closed trades (closedPnl) + funding.

    The analogue of BingX /user/income. Returned in the same shape
    (income/time) so the total calculation can be reused.
    """
    a = _acct()
    if not a:
        return []
    since = int(start_ms or 0)
    out: list[dict] = []
    try:
        payload = {"type": "userFillsByTime", "user": a}
        if since:
            payload["startTime"] = since
        fills = await info(payload, client=client)
        for f in fills or []:
            try:
                pnl = float(f.get("closedPnl") or 0)
                fee = float(f.get("fee") or 0)
            except (TypeError, ValueError):
                continue
            if pnl == 0 and fee == 0:
                continue
            out.append({"income": round(pnl - fee, 8), "time": f.get("time"),
                        "incomeType": "REALIZED_PNL", "tranId": f.get("tid")})
    except Exception:  # noqa: BLE001
        pass
    try:
        payload = {"type": "userFunding", "user": a}
        if since:
            payload["startTime"] = since
        fund = await info(payload, client=client)
        for f in fund or []:
            d = f.get("delta") or {}
            try:
                out.append({"income": float(d.get("usdc") or 0),
                            "time": f.get("time"),
                            "incomeType": "FUNDING_FEE", "tranId": f.get("hash")})
            except (TypeError, ValueError):
                pass
    except Exception:  # noqa: BLE001
        pass
    return out


async def pnl_history(client=None, start_ms: int | None = None) -> dict:
    """Realized + funding totals in the unified UI format."""
    import datetime as _dt

    rows = await income(client=client, start_ms=start_ms)
    realized = round(sum(r["income"] for r in rows if r.get("incomeType") == "REALIZED_PNL"), 6)
    funding = round(sum(r["income"] for r in rows if r.get("incomeType") == "FUNDING_FEE"), 6)
    times = [int(r["time"]) for r in rows if r.get("time")]
    since = until = None
    if times:
        since = _dt.datetime.fromtimestamp(min(times) / 1000).strftime("%Y-%m-%d")
        until = _dt.datetime.fromtimestamp(max(times) / 1000).strftime("%Y-%m-%d")
    return {"realized": realized, "funding": funding,
            "total": round(realized + funding, 6),
            "records": len([r for r in rows if r.get("incomeType") == "REALIZED_PNL"]),
            "since": since, "until": until}


# ── Write (orders) ──────────────────────────────────────────────────

def _sdk():
    """Lazy SDK init. Used ONLY for signing and sending orders.

    Requires the optional extra: pip install -r requirements-hl.txt
    """
    try:
        import eth_account
        from hyperliquid.exchange import Exchange
        from hyperliquid.utils import constants
    except ImportError as e:  # noqa: BLE001
        raise RuntimeError(
            "Hyperliquid SDK is not installed. Run: pip install -r requirements-hl.txt"
        ) from e

    s = load_secrets()
    pk = s.get("api_private_key", "")
    acct = s.get("account_address", "")
    if not pk or not acct:
        raise RuntimeError("Hyperliquid: account address and/or agent private key are not set")
    wallet = eth_account.Account.from_key(pk)
    base = constants.TESTNET_API_URL if s.get("env") == "testnet" else constants.MAINNET_API_URL
    # account_address — the MASTER account (NOT the agent address!), otherwise
    # account data comes back empty.
    return Exchange(wallet, base_url=base, account_address=acct)


_ex = None


def _exchange():
    global _ex
    if _ex is None:
        _ex = _sdk()
    return _ex


def reset_client() -> None:
    """Reset the SDK cache — call after keys or environment change."""
    global _ex
    _ex = None
    _LEV_SET.clear()


def _round_sz(coin_sz: float, dec: int) -> float:
    return float(f"{coin_sz:.{dec}f}")


async def _run(fn, *a, **kw):
    """The SDK is synchronous — run it in a thread so the event loop is not blocked."""
    return await asyncio.to_thread(fn, *a, **kw)


async def is_hedge_mode(client=None) -> bool:
    """Hyperliquid has no hedge mode — always one-way (positionSide=BOTH)."""
    return False


# Leverage successfully applied during the process lifetime (coin -> int).
# Hyperliquid does NOT report per-instrument leverage before a position exists:
# in clearinghouseState leverage only appears inside an open position. So
# remembering the applied value is the only way to let trader.py verify it with
# the same code path as for BingX.
_LEV_SET: dict[str, int] = {}


async def set_leverage(symbol: str, leverage: int, client=None) -> dict:
    coin = hl_symbol(symbol)
    ex = await _run(_exchange)
    r = await _run(ex.update_leverage, int(leverage), coin, True)
    if isinstance(r, dict) and r.get("status") == "ok":
        _LEV_SET[coin] = int(leverage)
    return r


async def get_leverage(symbol: str, client=None) -> dict:
    """Instrument leverage in BingX format (longLeverage/shortLeverage).

    Source priority:
      1) an actually open position (the most honest source);
      2) the value successfully applied in this process;
      3) empty — then trader.py refuses to send the order (safe behaviour).
    """
    coin = hl_symbol(symbol)
    pos = await positions(symbol, client=client)
    if pos:
        lev = pos[0].get("leverage")
        try:
            iv = int(lev)
            if iv > 0:
                return {"longLeverage": iv, "shortLeverage": iv}
        except (TypeError, ValueError):
            pass
    if coin in _LEV_SET:
        iv = _LEV_SET[coin]
        return {"longLeverage": iv, "shortLeverage": iv}
    return {}


async def place_market(symbol: str, side: str, position_side: str,
                       quote_usdt: float | None = None, quantity: float | None = None,
                       reduce_only: bool = False, client=None) -> dict:
    """Market order = aggressive IOC limit (HL has no type=MARKET).

    side: BUY / SELL. position_side is ignored (one-way).
    Exactly one of quote_usdt / quantity.
    """
    coin = hl_symbol(symbol)
    dec = await sz_decimals(coin, client=client)
    px = await price(coin, client=client)
    if px is None or px <= 0:
        return {"status": "err", "response": "no price to compute the size"}

    if quantity is not None:
        sz = _round_sz(abs(float(quantity)), dec)
    elif quote_usdt is not None:
        q = float(quote_usdt)
        if q < MIN_NOTIONAL:
            return {"status": "err",
                    "response": f"notional {q:.2f} USDT is below the minimum {MIN_NOTIONAL} USDT"}
        sz = _round_sz(q / px, dec)
    else:
        raise ValueError("quote_usdt or quantity is required")

    if sz <= 0:
        return {"status": "err", "response": "size after rounding is 0"}

    ex = await _run(_exchange)
    is_buy = side.upper() == "BUY"
    try:
        r = await _run(ex.market_open, coin, is_buy, sz, None, SLIPPAGE)
    except Exception as e:  # noqa: BLE001
        return {"status": "err", "response": str(e)}

    ok = isinstance(r, dict) and r.get("status") == "ok"
    return {
        "code": 0 if ok else 1,
        "msg": "" if ok else str((r or {}).get("response")),
        "data": {"coin": coin, "sz": sz, "side": side, "raw": r},
    }


async def close_position(symbol: str, position_side: str | None = None, client=None) -> dict:
    """Close the position with an opposite IOC order for the full size.

    We do not use market_close from the SDK: it looks the position up itself
    and in some versions silently does nothing. Computing the size explicitly
    is more predictable.
    """
    coin = hl_symbol(symbol)
    pos = [p for p in await positions(symbol, client=client)
           if float(p.get("positionAmt") or 0) != 0]
    if not pos:
        return {"code": 0, "msg": "no position", "data": {}}
    p = pos[0]
    szi = float(p["positionAmt"])
    sz = abs(szi)
    ex = await _run(_exchange)
    is_buy = szi < 0          # close a short by buying
    try:
        r = await _run(ex.market_open, coin, is_buy, sz, None, SLIPPAGE)
    except Exception as e:  # noqa: BLE001
        return {"code": 1, "msg": str(e), "data": {}}
    ok = isinstance(r, dict) and r.get("status") == "ok"
    return {"code": 0 if ok else 1, "msg": "" if ok else str((r or {}).get("response")),
            "data": {"coin": coin, "sz": sz, "raw": r}}


# ── Symbol mapping ──────────────────────────────────────────────────

def hl_symbol(sym: str) -> str:
    s = (sym or "").upper().replace("-USDT", "").replace("USDT", "")
    return ALIASES.get(s, s)
