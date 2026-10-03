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
trader.py — execution of signals on BingX (real trading).

Safety rules (all mandatory):
  1) live_enabled = 1 (the main switch, default 0);
  2) the symbol is in trade_tickers and enabled=1;
  3) API keys are present; position size = entry_pct% of free margin × leverage.
We send nothing if even one condition is not met.

Position mode: one-way (positionSide=BOTH) — BingX default. Entry: BUY=LONG,
SELL=SHORT; close — via closePosition.
"""
from __future__ import annotations

import json
import logging
import time

from app import exchange as ex
from app import store
from app.engine import webhooks as wh
from app.engine import mailer as mail

log = logging.getLogger("tv.trader")

# Notifications about REAL trades go to the chat configured in the trading settings.
# The bot token and chat_id are taken from the trading settings (if set).
PRIVATE_CHAT = ""


def _fmt(sym: str, kind: str, side: str | None, price, notional, extra: str = "") -> str:
    """Format of the notification about the execution of a real trade."""
    if kind == "open":
        sd = "LONG" if side == "BUY" else "SHORT"
        emoji = "🟢" if side == "BUY" else "🔴"
        head = f"{emoji} <b>LIVE · OPEN {sd}</b> {sym}"
        body = (f"notional: {notional} USDT\nprice: {price}" if price else f"notional: {notional} USDT")
        return f"{head}\n{body}" + (f"\n{extra}" if extra else "")
    if kind == "close":
        return f"🔵 <b>LIVE · CLOSE</b> {sym}" + (f"\nprice: {price}" if price else "") + (f"\n{extra}" if extra else "")
    return f"⚠️ <b>LIVE · {kind}</b> {sym}" + (f"\n{extra}" if extra else "")


async def _notify(text: str, client=None) -> None:
    """Sends a notification about a real trade to the configured channels.

    Telegram (bot token + chat_id) and/or e-mail (SMTP) — whichever is set.
    """
    cfg = ex.notify_cfg()
    token = cfg.get("token") or None
    chat = str(cfg.get("chat_id") or PRIVATE_CHAT)
    sent_any = False
    if chat:
        try:
            res = await wh.send_telegram(chat, text, None, client=client, token=token)
            if res is not None and res.get("ok"):
                sent_any = True
            elif res is not None:
                log.warning("trade notify not-ok: %s", res.get("description") or res.get("error"))
        except Exception as e:  # noqa: BLE001
            log.warning("trade notify failed: %s", e)
    # E-mail channel (optional, the user's own SMTP server).
    mcfg = ex.mail_cfg()
    if mcfg.get("host") and mcfg.get("to"):
        try:
            r = await mail.send_email(mcfg, "Rawanga Trading Desk — trade alert", text)
            if r.get("ok"):
                sent_any = True
            else:
                log.warning("trade e-mail not-ok: %s", r.get("error"))
        except Exception as e:  # noqa: BLE001
            log.warning("trade e-mail failed: %s", e)
    if not sent_any:
        log.debug("trade notify: no channel configured")


async def _notional_usdt(client) -> float | None:
    """Order notional in USDT: entry_pct% of free margin × leverage."""
    s = await store.get_trade_settings()
    if not s.get("live_enabled"):
        return None
    bal = await ex.balance(client=client)
    if not bal:
        return None
    try:
        avail = float(bal.get("availableMargin") or bal.get("equity") or 0)
    except Exception:  # noqa: BLE001
        return None
    if avail <= 0:
        return None
    lev = int(s.get("leverage", 1)) or 1
    pct = float(s.get("entry_pct", 0)) / 100.0
    notional = avail * pct * lev
    return round(notional, 2)


async def execute_deal(deal: dict, meta: dict, tf: str, client=None) -> dict | None:
    """Execute a journal trade on the exchange. Returns the result or None (not trading)."""
    sym = meta["symbol"]
    # 1) trading is enabled and the symbol is tradable
    s = await store.get_trade_settings()
    if not s.get("live_enabled"):
        return None
    if not await store.is_trade_enabled(sym):
        return None
    if not ex.masked_keys()["has_keys"]:
        return None

    bx = ex.bingx_symbol(sym)
    kind = deal["kind"]
    hedge = await ex.is_hedge_mode(client)
    try:
        if kind == "open":
            lev = int(s.get("leverage", 1)) or 1
            # Explicitly set leverage (without an explicit one BingX may apply the maximum),
            # then CHECK that it was actually applied,
            # otherwise we do NOT send the order.
            await ex.set_leverage(bx, lev, client=client)
            chk = await ex.get_leverage(bx, client=client)
            cur_long = int(chk.get("longLeverage", 0) or 0)
            cur_short = int(chk.get("shortLeverage", 0) or 0)
            want = cur_long if deal["side"] == "long" else cur_short
            if want != lev:
                log.error("leverage not applied %s: want=%s got L=%s S=%s", bx, lev, cur_long, cur_short)
                await store.log_exec(sym, bx, "open", deal.get("side"), None, deal.get("close"),
                                     0, f"leverage mismatch want={lev} L={cur_long} S={cur_short}", "")
                await _notify(f"⚠️ <b>LIVE · order NOT sent</b> {sym}\nleverage not applied: expected {lev}, L={cur_long} S={cur_short}", client=client)
                return None
            pos_side = ("LONG" if deal["side"] == "long" else "SHORT") if hedge else "BOTH"
            opp = "SHORT" if pos_side == "LONG" else "LONG"
            # ── Protection against a double position (especially in hedge mode!) ──
            # In hedge mode LONG and SHORT can coexist: if a position remains
            # on entry, or on the opposite side (leftover from a reversal) —
            # we do NOT open a new one until it is clean. First close the opposite.
            try:
                _pos = await ex.positions(bx, client=client)
                mine = [p for p in _pos if float(p.get("positionAmt") or 0) != 0
                        and (p.get("positionSide") == pos_side or not hedge)]
                if mine:
                    log.info("trade skip %s: position already open (%s)", sym, pos_side)
                    return None
                opp_pos = [p for p in _pos if float(p.get("positionAmt") or 0) != 0
                           and p.get("positionSide") == opp]
                if opp_pos:
                    log.info("trade %s: closing opposite %s before open %s", sym, opp, pos_side)
                    await ex.close_position(bx, opp, client=client)
                    _pos2 = await ex.positions(bx, client=client)
                    still = [p for p in _pos2 if float(p.get("positionAmt") or 0) != 0
                             and p.get("positionSide") == opp]
                    if still:
                        log.error("trade abort %s: opposite %s still open", sym, opp)
                        await _notify(f"⚠️ <b>LIVE · order cancelled</b> {sym}\nfailed to close the opposite {opp}", client=client)
                        return None
            except Exception as e:  # noqa: BLE001
                log.warning("position check failed %s: %s", sym, e)
            notional = await _notional_usdt(client)
            if not notional or notional <= 0:
                log.warning("trade skip %s: notional<=0", sym)
                return None
            side = "BUY" if deal["side"] == "long" else "SELL"
            r = await ex.place_market(bx, side, pos_side, quote_usdt=notional, client=client)
            ok = r.get("code") == 0
            await store.log_exec(sym, bx, "open", side, notional, deal.get("close"),
                                 ok, r.get("msg"), json.dumps(r)[:2000])
            log.info("trade OPEN %s %s %s notional=%.2f ok=%s", sym, side, bx, notional, ok)
            # Notification about the live trade
            await _notify(_fmt(sym, "open", side, deal.get("close"), notional,
                               extra=f"leverage: {lev}× · {bx}"), client=client)
            return r if ok else {"_status": "error"}
        elif kind == "close":
            pos_side = ("LONG" if deal.get("side") == "long" else "SHORT") if hedge else "BOTH"
            r = await ex.close_position(bx, pos_side, client=client)
            ok = r.get("code") == 0
            await store.log_exec(sym, bx, "close", deal.get("side"), None, deal.get("close"),
                                 ok, r.get("msg"), json.dumps(r)[:2000])
            log.info("trade CLOSE %s %s ok=%s", sym, bx, ok)
            reason = deal.get("reason")
            extra = f"reason: {reason}" if reason else ""
            pl = deal.get("trade", {}).get("pl_pct") if deal.get("trade") else None
            if pl is not None:
                extra += (f" · P/L: {pl:+.2f}%" if pl >= 0 else f" · P/L: {pl:.2f}%")
            await _notify(_fmt(sym, "close", deal.get("side"), deal.get("close"), None,
                               extra=extra), client=client)
            return r if ok else {"_status": "error"}
    except Exception as e:  # noqa: BLE001
        await store.log_exec(sym, bx, kind, deal.get("side"), None, deal.get("close"),
                             0, str(e), "")
        log.warning("trade %s %s failed: %s", kind, sym, e)
        await _notify(f"⚠️ <b>LIVE · error {kind}</b> {sym}\n{e}", client=client)
        # _status=error → the caller does NOT mark the trade as executed → it will retry
        # the close (the position will not "hang").
        return {"_status": "error"}
    return None
