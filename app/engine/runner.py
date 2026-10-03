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
runner.py — real-time scheduler: run on BAR CLOSE.

Every minute:
  1) for each enabled instrument (crypto/stocks/energy categories) on 15m/1h/4h/1d
     we take fresh bars and run both trading strategies (stv3, rawa_system);
  2) we send new signals (entry/reversal/stop/TP) via webhooks symbol×tf×strategy;
  3) for the 4 trend instruments we compute the Supertrend(10,3) flip and send a trend notification.
     The computation TF differs: VIX/USDTD — 15m (faster), SPX/BTC — 1h.
     VIX and USDTD are inverted: growth = short warning (risk-off).

Deduplication by (strategy, symbol, tf, ts, side) — we do not send the same bar again.
"""
from __future__ import annotations

import asyncio
import logging
import time

from app import store
from app.datafeed import cache
from app.datafeed.sources import fetch_ohlcv, TF_SECONDS, TFS
from app.engine import signals as eng
from app.engine import trader as trade_exec
from app.engine import trades as tr
from app.engine import webhooks as wh
from app.engine import mailer as mail
from app import exchange as ex

log = logging.getLogger("tv.runner")
STRATEGIES = eng.STRATEGIES  # dict with .title; trend is not traded here (run_trend handles it)
TRADE_STRATEGIES = list(eng.TRADE_STRATEGIES)  # stv3, rawa_system — for the loop iteration
# ── Trend notifications ────────────────────────────────────────────
# Supertrend parameters — exactly as in the standard implementation: Supertrend (10, hl2, 3).
TREND_ST_PERIOD = 10
TREND_ST_MULT = 3.0
# Symbol -> (computation TF, inversion).
#   VIX/USDTD — 15m, inverted (growth = short warning).
#   SPX/BTC   — 1h, without inversion.
TREND_CFG = {
    "VIX":   {"tf": "15m", "invert": True},
    "USDTD": {"tf": "15m", "invert": True},
    "SPX":   {"tf": "1h",  "invert": False},
    "BTC":   {"tf": "1h",  "invert": False},
}
TREND_SYMBOLS = wh.TREND_SYMBOLS  # VIX, SPX, BTC, USDTD


async def _email_alert(text: str, subject: str) -> bool:
    """Optional e-mail channel: send a copy of the alert to the user's mailbox.

    No-op (returns False) unless SMTP host + recipient are configured.
    """
    cfg = ex.mail_cfg()
    if not (cfg.get("host") and cfg.get("to")):
        return False
    try:
        r = await mail.send_email(cfg, subject, text)
        if not r.get("ok"):
            log.warning("e-mail alert not-ok: %s", r.get("error"))
        return bool(r.get("ok"))
    except Exception as e:  # noqa: BLE001
        log.warning("e-mail alert failed: %s", e)
        return False


async def _bars(client, meta, tf, limit=500):
    """Fetch fresh bars: live (via the cascade) → cache."""
    try:
        res = await fetch_ohlcv(meta["yahoo"] if meta["kind"] != "crypto" else meta["symbol"],
                                tf, limit, client=client, kind=meta["kind"])
        if res["bars"]:
            await cache.upsert_bars(meta["symbol"], tf, res["bars"], res["source"])
    except Exception as e:  # noqa: BLE001
        log.debug("live fetch failed %s %s: %s -> cache", meta["symbol"], tf, e)
    return await cache.get_bars(meta["symbol"], tf, limit)


async def run_trade_strategies(client, state, only_tfs=None, prime_only=False) -> int:
    """Runs the trading strategies. Returns the number of notifications sent.

    The source of notifications is the TRADE JOURNAL (tr.build_trades), not raw signals.
    This way the chat mirrors the real entries/exits that the chart shows
    (the same entry/exit/reason/P-L as in the right panel).

    only_tfs:   if set — we run only these TFs (bar close of those TFs).
    prime_only: initial warm-up — only records state in the DB, WITHOUT sending;
                this way a service restart does not re-broadcast the "history".
    """
    sent = 0
    rows = await store.list_instruments()
    trade_rows = [r for r in rows if r["category"] not in ("trend",)]
    tfs = [tf for tf in TFS if (only_tfs is None or tf in only_tfs)]
    for meta in trade_rows:
        for tf in tfs:
            bars = await _bars(client, meta, tf)
            if len(bars) < 30:
                continue
            d0 = eng._df(bars)  # noqa: SLF001 — shared converter
            # The list is taken dynamically: strategies compiled via the Strategy Editor
            # are picked up by the scheduler immediately, without a restart.
            for strat in list(eng.TRADE_STRATEGIES):
                params = await store.get_params(meta["symbol"], tf, strat)
                try:
                    d = eng.run(d0, strat, params)
                    sigs = eng.signals_only(d, params, meta.get("category", "crypto"))
                    bt = tr.build_trades(sigs)
                except Exception as e:  # noqa: BLE001
                    log.warning("strategy %s %s %s failed: %s", strat, meta["symbol"], tf, e)
                    continue

                hooks = await store.match_webhooks(meta["symbol"], tf, strat)
                if not hooks:
                    continue

                # ── Exactly the same trades as in the journal: closed + open ──
                deals = []
                for t in bt.get("trades", []):
                    deals.append({
                        "kind": "close", "side": t["side"], "ts": int(t["exit_ts"]),
                        "entry": t["entry"], "close": t["exit"], "reason": t.get("reason"),
                        "trailing": t.get("trailing"), "trade": t,
                    })
                o = bt.get("open")
                if o:
                    # We send the entry of an open trade only when it is fresh (not on every tick)
                    deals.append({
                        "kind": "open", "side": o["side"], "ts": int(o["entry_ts"]),
                        "entry": o["entry"], "close": o["entry"], "reason": None,
                        "trailing": False, "trade": o,
                    })

                for deal in deals:
                    now_ms = time.time() * 1000
                    # Freshness window for ANY trade (both open and close): we do not
                    # send old entries from the journal to the chat — otherwise backfill drags in history.
                    if now_ms - deal["ts"] > 2 * _tf_ms(tf):
                        continue
                    key = (strat, meta["symbol"], tf, deal["ts"], deal["kind"], deal["side"])
                    if key in state:
                        continue
                    dedup_side = deal["kind"] + ":" + deal["side"]
                    if await store.already_sent("deal", meta["symbol"], tf, deal["ts"],
                                                dedup_side):
                        state.add(key)
                        continue
                    if prime_only:
                        # start: only record, so as not to spam with "history"
                        await store.mark_sent("deal", meta["symbol"], tf, dedup_side,
                                              float(deal["close"]), deal["ts"])
                        state.add(key)
                        continue
                    # ── Real trading on the exchange (DISABLED by default).　──
                    # Persistent dedup (signals_sent strategy="exec"): a service
                    # restart must NOT duplicate a real order.
                    exec_side = "exec:" + deal["kind"] + ":" + str(deal["side"])
                    if not await store.already_sent("exec", meta["symbol"], tf,
                                                    deal["ts"], exec_side):
                        st = None
                        try:
                            st = await trade_exec.execute_deal(deal, meta, tf, client=client)
                        except Exception as e:  # noqa: BLE001
                            log.warning("trade exec failed %s: %s", meta["symbol"], e)
                            st = {"_status": "error"}
                        # We mark as executed ONLY on success. On error —
                        # we do not mark: we will retry on the next tick (the trade will not "hang",
                        # especially important for CLOSING).
                        if not (isinstance(st, dict) and st.get("_status") == "error"):
                            await store.mark_sent("exec", meta["symbol"], tf, exec_side,
                                                  float(deal["close"] or 0), deal["ts"])
                    # match the entry and exit for the exit signal (the same trade!)
                    sig = _deal_sig(deal)
                    text = wh.format_signal(sig, meta["symbol"], tf,
                                            STRATEGIES[strat]["title"], trade=deal["trade"])
                    ok = False
                    # ── Route from the webhook registry. A webhook is the GATE
                    # of delivery: no enabled hook for symbol×TF×strategy →
                    # the signal is not sent. Each hook carries its own chat_id;
                    # hooks pointing at PROD_CHAT are routed to the category thread.
                    for h in hooks:
                        dest = str(h["chat_id"])
                        if dest == wh.PROD_CHAT:
                            tid = h.get("thread_id") or wh.thread_for_category(
                                meta.get("category"))
                        else:
                            tid = h.get("thread_id")
                        try:
                            res = await wh.send_telegram(dest, text, tid, client=client)
                            # send_telegram returns {'ok': False, 'error': ...}
                            # without an exception (e.g. 'no bot token') — we check ok.
                            if res is not None and res.get("ok"):
                                ok = True
                            else:
                                err = (res or {}).get("error", "unknown")
                                log.warning("send not-ok %s %s: %s", meta["symbol"], tf, err)
                        except Exception as e:  # noqa: BLE001
                            log.warning("send failed: %s", e)
                    # E-mail channel (optional) — independent of Telegram.
                    try:
                        if await _email_alert(text, f"RTD {meta['symbol']} {tf}"):
                            ok = True
                    except Exception as e:  # noqa: BLE001
                        log.warning("e-mail send failed: %s", e)
                    if not ok:
                        # Delivery failed — we do NOT mark as sent,
                        # so that the signal is not lost forever.
                        continue
                    await store.mark_sent("deal", meta["symbol"], tf,
                                          dedup_side, float(deal["close"]), deal["ts"])
                    state.add(key)
                    sent += 1
    return sent


def _deal_sig(deal):
    """Builds a signal exactly from the journal trade (not from raw signals)."""
    if deal["kind"] == "close":
        return {"side": "exit", "exit_of": deal["side"], "close": deal["close"],
                "ts": deal["ts"], "reason": deal["reason"], "trailing": deal["trailing"]}
    return {"side": deal["side"], "close": deal["close"], "ts": deal["ts"],
            "stop": (deal["trade"] or {}).get("stop"),
            "vol_score": (deal["trade"] or {}).get("vol_score")}


async def run_trend(client, state, only_tfs=None, prime_only=False) -> int:
    """Supertrend trend notifications for the 4 instruments (only on bar close of their TF).

    VIX/USDTD — 15m (inversion), SPX/BTC — 1h. One notification per phase entry.
    """
    sent = 0
    for sym in TREND_SYMBOLS:
        cfg = TREND_CFG.get(sym)
        if not cfg:
            continue
        tf = cfg["tf"]
        if only_tfs is not None and tf not in only_tfs:
            continue
        meta = await store.get(sym)
        if not meta:
            continue
        bars = await _bars(client, meta, tf)
        if len(bars) < 30:
            continue
        # Parameters — the same as in the standard implementation: Supertrend (10, hl2, 3)
        d = eng._df(bars)  # noqa: SLF001
        dw = eng.trend_watch(d, TREND_ST_PERIOD, TREND_ST_MULT)
        flips = eng.trend_flips(dw)
        if not flips:
            continue
        last = flips[-1]
        # phase entry: only the last bar. If the flip happened earlier
        # (in the middle of the window) — that is already history, we do not send.
        #
        # We do NOT apply a freshness window for trend instruments: stocks/indices
        # (SPX) close the bar at 22:00 CEST and Yahoo serves it with a delay,
        # and the 1h run does not happen every hour at the same minute. A hard 2×TF window
        # was eating SPX/BTC. Dedup by trend_state protects against re-sending
        # (prev["last_side"] == side) — more reliable than a time window.
        now_ms = int(time.time() * 1000)
        flip_ts = int(last["ts"])
        age_ms = now_ms - flip_ts
        # Inversion: for VIX/USDTD, growth = a short warning (risk-off).
        side = last["side"]
        if cfg["invert"]:
            side = "short" if side == "long" else "long"
        key = ("trend", sym, tf, flip_ts, side)
        if key in state:
            continue
        prev = await wh.get_trend_state(sym, tf)
        fresh = age_ms <= 3 * _tf_ms(tf)
        already = prev is not None and int(prev.get("last_flip_ts") or 0) == flip_ts
        # We do not send and just record the state: start (warm-up) / old flip
        # (we do not drag in history) / this same flip already sent (dedup by the FACT of the flip).
        # IMPORTANT: we also write the state for an OLD flip — otherwise for SPX the record
        # was not created (its flip is always older than 3 bars) → prev=None → the very first
        # fresh flip was silently swallowed by the `prev is None` check.
        if prime_only or not fresh or already:
            await wh.set_trend_state(sym, tf, side, flip_ts)
            state.add(key)
            continue
        text = wh.format_trend(sym, side)
        # Route from the webhook registry (strategy="trend"): the hook is the GATE and the address.
        # No enabled hook → we do not send (same as for trades).
        hooks = await store.match_webhooks(sym, tf, "trend")
        if not hooks:
            await wh.set_trend_state(sym, tf, side, flip_ts)
            state.add(key)
            continue
        ok = False
        for h in hooks:
            dest = str(h["chat_id"])
            tid = h.get("thread_id")
            if tid is None and dest == wh.PROD_CHAT:
                tid = wh.TREND_THREAD
            try:
                res = await wh.send_telegram(dest, text, tid, client=client)
                if res is not None and res.get("ok"):
                    ok = True
                else:
                    log.warning("trend send not-ok %s: %s", sym, (res or {}).get("error"))
            except Exception as e:  # noqa: BLE001
                log.warning("trend send failed %s: %s", sym, e)
        # E-mail channel (optional) — independent of Telegram.
        try:
            if await _email_alert(text, f"RTD trend {sym}"):
                ok = True
        except Exception as e:  # noqa: BLE001
            log.warning("trend e-mail failed %s: %s", sym, e)
        if ok:
            # State — only AFTER successful delivery: on failure we do not record,
            # so that a retry works on the next tick (within the freshness window).
            await wh.set_trend_state(sym, tf, side, flip_ts)
            state.add(key)
            sent += 1
    return sent


async def tick(client, state, only_tfs=None, prime_only=False) -> dict:
    """One run. `state` — a set of keys already sent (in process memory).

    only_tfs=None — run all TFs (initial warm-up);
    only_tfs={tf} — only the TFs whose bar has closed.
    prime_only=True — we send nothing, only mark in the DB (warm-up on start).
    """
    t0 = time.time()
    t = await run_trade_strategies(client, state, only_tfs, prime_only=prime_only)
    r = await run_trend(client, state, only_tfs, prime_only=prime_only)
    log.info("tick: trade=%d trend=%d (%.1fs)", t, r, time.time() - t0)
    return {"trade": t, "trend": r, "elapsed": round(time.time() - t0, 2)}


def _tf_ms(tf: str) -> int:
    return TF_SECONDS.get(tf, 900) * 1000


async def loop(client, state, interval: int = 20):
    """Infinite loop, run — strictly on the BAR-CLOSE SCHEDULE.

    Instead of frequently polling the provider, we compute the time UNTIL the next bar boundary
    and sleep exactly until it (+ a small buffer). We wake up → one run of the TF
    whose bar has just closed. No cache snapshots every 20s and no extra requests.
    """
    log.info("runner loop started (bar-close schedule)", )
    # the first run — ONLY warm-up: we record the state, send nothing
    # (otherwise a restart re-broadcasts the "history" over the last bars)
    try:
        await tick(client, state, prime_only=True)
    except Exception as e:  # noqa: BLE001
        log.warning("prime tick failed: %s", e)
    last_closed: dict[str, int] = {tf: 0 for tf in TFS}
    # ── Catch-up RETRIES ─────────────────────────────────────────
    # The bar closed at the boundary, but the exchange serves the closed candle with a lag
    # (BingX ~1-3 min). Previously in this case the signal waited for the next 15m boundary
    # (+15 min) — unacceptable. Now after each boundary there is a short cycle of
    # retries: every RETRY_EVERY s up to RETRY_MAX_WINDOW s we check whether the bar
    # has matured, and as soon as it is — we run and send immediately.
    RETRY_EVERY = 20.0
    RETRY_MAX_WINDOW = 300.0  # 5 min — the limit of the acceptable gap
    buf = 8.0  # buffer after the boundary: let the provider mature
    while True:
        try:
            now = time.time()
            # Wake up at the nearest boundary of any TF, not just 15m.
            _, wait = _next_bar_close(now)
            await asyncio.sleep(wait)
            now = time.time()
            # All TFs whose boundary has closed since the last time (usually one).
            due = [tf for tf in TFS
                   if _closed_boundary(tf, now) > last_closed.get(tf, 0)]
            if not due:
                continue
            # The main run.
            sent_now = 0
            for tf in due:
                r = await tick(client, state, only_tfs={tf})
                sent_now += (r or {}).get("trade", 0) + (r or {}).get("trend", 0)
                last_closed[tf] = _closed_boundary(tf, now)
            # Catch-up RETRIES.
            # The provider may serve the bar with a delay (BingX ~1-3 min), and on
            # the first run close has not matured yet → the signal is not formed.
            # Therefore within a 5 min window we repeat the run of the same TF every 20 s —
            # tick is idempotent (dedup prevents duplicates), and as soon as the data
            # matures, the new signal goes out immediately.
            # Previously we checked only the new bar's boundary — that is not enough: a bar with
            # an incomplete close already has the right boundary, but there is no signal yet.
            started = time.time()
            while time.time() - started < RETRY_MAX_WINDOW:
                await asyncio.sleep(RETRY_EVERY)
                for tf in due:
                    r = await tick(client, state, only_tfs={tf})
                    sent_now += (r or {}).get("trade", 0) + (r or {}).get("trend", 0)
                if sent_now:
                    break   # the signal went out — retries are no longer needed
        except Exception as e:  # noqa: BLE001
            log.warning("tick failed: %s", e)
            await asyncio.sleep(interval)


def _next_bar_close(now: float | None = None) -> tuple[str, float]:
    """The nearest close boundary among TFS → (tf, seconds until it + buffer).

    Boundaries are multiples of the TF duration in UTC (for 1d — UTC midnight).
    """
    now = now if now is not None else time.time()
    buf = 8.0  # buffer: let the provider/cache mature after close
    best_tf, best_wait = None, None
    for tf in TFS:
        step = _tf_sec(tf)
        nxt = (int(now // step) + 1) * step
        wait = nxt - now + buf
        if best_wait is None or wait < best_wait:
            best_tf, best_wait = tf, wait
    return best_tf, max(best_wait, 1.0)


def _closed_boundary(tf: str, now: float | None = None) -> int:
    """The last CLOSED bar boundary for a TF (in seconds, UTC)."""
    now = now if now is not None else time.time()
    step = _tf_sec(tf)
    return int(now // step) * step


def _tf_sec(tf: str) -> int:
    return TF_SECONDS.get(tf, 900)


async def current_bar_boundary(client, tf: str):
    """The freshest CLOSED bar at the provider → its boundary (sec) or None.

    Used by the catch-up retries: it reveals whether the bar has matured on the exchange,
    without resorting to a full run of all strategies.
    """
    try:
        rows = await store.list_instruments()
    except Exception:  # noqa: BLE001
        return None
    # one crypto instrument from the most liquid family is enough
    probe = None
    for r in rows:
        if r.get("kind") == "crypto" and r["symbol"] == "BTC":
            probe = r
            break
    if probe is None:
        for r in rows:
            if r.get("kind") == "crypto":
                probe = r
                break
    if probe is None:
        return None
    try:
        res = await fetch_ohlcv(probe["symbol"], tf, 3, client=client, kind="crypto")
    except Exception:  # noqa: BLE001
        return None
    bars = res.get("bars") or []
    if not bars:
        return None
    # the last bar from the provider: if it is ALREADY CLOSED (not current),
    # its ts+step <= now. We compute from the ts of the last bar.
    last_ts = int(bars[-1][0]) // 1000
    step = _tf_sec(tf)
    # if the last bar is still current (boundary in the future), we take the previous one
    boundary = last_ts
    if boundary + step > time.time():
        boundary = last_ts - step
    return boundary
