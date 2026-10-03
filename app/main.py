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
main.py — Rawanga Trading Desk FastAPI service (port 3000).
E0-E1: health + datafeed with fallbacks + cache.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
import time

import httpx
from fastapi import FastAPI, HTTPException
from fastapi import Response
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import pandas as pd

from app import store
from app.datafeed import cache
from app.datafeed.sources import fetch_ohlcv, TFS as VALID_TFS
from app.engine import signals as eng
from app import exchange as ex
from app.engine import strategy as strat_mod
from app.engine import trades as tr_trades
from app.engine import runner as rn
from app.engine import trades as tr
from app.engine import webhooks as wh
from app.indicators import ta


def _lead_null(s):
    """Leading run of zeros -> NaN so it serializes as null.
    Needed for MACD: ema(adjust=False) yields 0.0 during warmup, while the chart
    (lightweight-charts) requires a gap, else it fails with 'Value is undefined'."""
    import numpy as np
    arr = np.asarray(s, dtype=float)
    i = 0
    n = len(arr)
    while i < n and arr[i] == 0.0:
        i += 1
    if i:
        arr = arr.copy()
        arr[:i] = np.nan
    import pandas as pd  # noqa
    return pd.Series(arr, index=getattr(s, 'index', None))
from app.instruments import INSTRUMENTS, all_instruments, resolve

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("tv")

from app import paths as _paths
ROOT = _paths.APP_ROOT
STATIC = _paths.STATIC_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    await cache.init()
    await wh.init()
    await store.init()
    await store.seed(INSTRUMENTS)
    app.state.client = httpx.AsyncClient(timeout=15.0)
    # Load user strategies into the engine (state/strategies.json)
    try:
        n = await strategy_load_saved()
        log.info("strategy scripts loaded: %s", n)
    except Exception as e:  # noqa: BLE001
        log.warning("strategy load failed: %s", e)
    # real-time scheduler: run on bar close
    app.state.sent = set()
    app.state.runner_task = asyncio.create_task(rn.loop(app.state.client, app.state.sent))
    log.info("Rawanga Trading Desk started")
    yield
    app.state.runner_task.cancel()
    try:
        await app.state.runner_task
    except asyncio.CancelledError:
        pass
    await app.state.client.aclose()


app = FastAPI(title="Rawanga Trading Desk", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "rawanga-trading-desk",
            "instruments": len(INSTRUMENTS), "bars_cached": await cache.count()}


async def _resolve(symbol: str) -> dict:
    """Instrument from the DB, with a fallback to the static registry."""
    row = await store.get(symbol)
    if row:
        return {"symbol": row["symbol"], "kind": row["kind"], "yahoo": row["yahoo"],
                "category": row["category"], "title": row["title"]}
    return resolve(symbol)


@app.get("/api/instruments")
async def list_instruments():
    rows = await store.list_instruments()
    return {"instruments": [{"symbol": r["symbol"], "kind": r["kind"], "yahoo": r["yahoo"],
                            "category": r["category"], "title": r["title"]} for r in rows]}


@app.post("/api/instruments")
async def add_instrument(payload: dict):
    sym = str(payload.get("symbol", "")).upper().strip()
    if not sym:
        raise HTTPException(400, "symbol required")
    ok = await store.add(sym, payload.get("kind", "crypto"),
                         payload.get("yahoo", f"{sym}-USD"),
                         payload.get("category", "crypto"),
                         payload.get("title", sym))
    if not ok:
        raise HTTPException(409, f"{sym} already exists")
    return {"added": sym}


@app.delete("/api/instruments/{symbol}")
async def del_instrument(symbol: str):
    return {"removed": await store.remove(symbol)}


@app.get("/api/bars/{symbol}")
async def bars(symbol: str, tf: str = "1h", limit: int = 500,
               refresh: bool = True):
    try:
        meta = await _resolve(symbol)
    except KeyError:
        raise HTTPException(404, f"unknown symbol {symbol}")
    if tf not in VALID_TFS:
        raise HTTPException(400, f"tf must be {'|'.join(VALID_TFS)}")
    source = "cache"
    if refresh:
        try:
            res = await fetch_ohlcv(meta["yahoo"] if meta["kind"] != "crypto" else meta["symbol"],
                                    tf, limit, client=app.state.client, kind=meta["kind"])
            await cache.upsert_bars(meta["symbol"], tf, res["bars"], res["source"])
            source = res["source"]
        except Exception as e:  # noqa: BLE001
            log.warning("live fetch failed for %s %s: %s -> cache", symbol, tf, e)
    rows = await cache.get_bars(meta["symbol"], tf, limit)
    return {"symbol": meta["symbol"], "title": meta["title"],
            "category": meta["category"], "tf": tf, "source": source,
            "count": len(rows),
            "bars": [{"t": r[0], "o": r[1], "h": r[2], "l": r[3],
                      "c": r[4], "v": r[5]} for r in rows]}


def _df(bars: list) -> pd.DataFrame:
    return pd.DataFrame(bars, columns=["ts", "o", "h", "l", "c", "v"])


# shared converter for the scheduler/engine
eng._df = _df  # noqa: SLF001


@app.get("/api/indicators/{symbol}")
async def indicators(symbol: str, tf: str = "1h", limit: int = 500):
    try:
        meta = await _resolve(symbol)
    except KeyError:
        raise HTTPException(404, f"unknown symbol {symbol}")
    rows = await cache.get_bars(meta["symbol"], tf, limit)
    if not rows:
        await bars(symbol, tf, limit)
        rows = await cache.get_bars(meta["symbol"], tf, limit)
    df = _df(rows)
    ind = ta.compute_all(df)

    def ser(s):
        return [None if pd.isna(v) else round(float(v), 6) for v in s]

    t = [int(x) for x in df["ts"]]
    return {
        "symbol": meta["symbol"], "tf": tf, "time": t,
        "ema200": ser(ind["ema200"]), "sma50": ser(ind["sma50"]),
        "sma200": ser(ind["sma200"]),
        "bb_upper": ser(ind["bb_upper"]), "bb_mid": ser(ind["bb_mid"]),
        "bb_lower": ser(ind["bb_lower"]),
        "supertrend": ser(ind["supertrend"]), "st_dir": ser(ind["st_dir"]),
        "donchian_hi": ser(ind["donchian_hi"]), "donchian_lo": ser(ind["donchian_lo"]),
        "rsi14": ser(ind["rsi14"]),
        # MACD: ema(adjust=False) yields 0.0 instead of NaN on warmup bars.
        # lightweight-charts requires a gap (null) at the start of the series, else
        # it throws "Value is undefined". We null leading zeros for MACD only.
        "macd": ser(_lead_null(ind["macd"])),
        "macd_signal": ser(_lead_null(ind["macd_signal"])),
        "macd_hist": ser(_lead_null(ind["macd_hist"])),
        "stoch_k": ser(ind["stoch_k"]), "stoch_d": ser(ind["stoch_d"]),
        "adx": ser(ind["adx"]), "atr14": ser(ind["atr14"]),
        "vol_ma20": ser(ind["vol_ma20"]),
    }


@app.get("/api/signals/{symbol}")
async def sig(symbol: str, strategy: str = "stv3", tf: str = "1h", limit: int = 500):
    try:
        meta = await _resolve(symbol)
    except KeyError:
        raise HTTPException(404, f"unknown symbol {symbol}")
    if strategy not in eng.STRATEGIES:
        raise HTTPException(400, f"unknown strategy {strategy}")
    rows = await cache.get_bars(meta["symbol"], tf, limit)
    if not rows:
        raise HTTPException(409, "no cached bars; call /api/bars first")
    params = await store.get_params(meta["symbol"], tf, strategy)
    d = eng.run(_df(rows), strategy, params)
    # return TRADES (entry→exit), not raw signals — so chart and journal match
    _sig = eng.signals_only(d, params)
    built = tr.build_trades(_sig)
    return {"symbol": meta["symbol"], "strategy": strategy, "tf": tf,
            "title": eng.STRATEGIES[strategy]["title"],
            "params_used": params,
            "signals": _sig,
            "trades": built["trades"], "open": built["open"]}


@app.get("/api/trend/{symbol}")
async def trend(symbol: str, tf: str = "1h", limit: int = 500,
               st_period: int = 10, st_mult: float = 3.0):
    """Trend indicator (Supertrend) — flips ONLY, no trades/PnL.

    VIX / USDTD — 15m; SPX / BTC — 1h. The frontend/webhook formats the text:
        VIX 🟢 Signs of a trend reversal to LONG
        VIX 🚨 Signs of a trend reversal to SHORT
    For VIX/USDTD the side is inverted (rise = short warning).
    """
    try:
        meta = await _resolve(symbol)
    except KeyError:
        raise HTTPException(404, f"unknown symbol {symbol}")
    rows = await cache.get_bars(meta["symbol"], tf, limit)
    if not rows:
        raise HTTPException(409, "no cached bars; call /api/bars first")
    d = eng.trend_watch(_df(rows), st_period, st_mult)
    flips = eng.trend_flips(d)
    return {"symbol": meta["symbol"], "title": meta["title"], "tf": tf,
            "st_period": st_period, "st_mult": st_mult,
            "flips": flips, "last": flips[-1] if flips else None}


@app.get("/api/trades/{symbol}")
async def trades_endpoint(symbol: str, strategy: str = "stv3", tf: str = "1h",
                         limit: int = 500, period: str = "all"):
    """Trade journal for an instrument + P/L statistics for the period."""
    try:
        meta = await _resolve(symbol)
    except KeyError:
        raise HTTPException(404, f"unknown symbol {symbol}")
    if strategy not in eng.STRATEGIES:
        raise HTTPException(400, f"unknown strategy {strategy}")
    rows = await cache.get_bars(meta["symbol"], tf, limit)
    if not rows:
        raise HTTPException(409, "no cached bars; call /api/bars first")
    params = await store.get_params(meta["symbol"], tf, strategy)
    d = eng.run(_df(rows), strategy, params)
    sigs = eng.signals_only(d, params, meta.get("category", "crypto"))
    built = tr.build_trades(sigs)
    all_trades = built["trades"]
    return {
        "symbol": meta["symbol"], "strategy": strategy, "tf": tf,
        "title": eng.STRATEGIES[strategy]["title"],
        "open": built["open"],
        "trades": list(reversed(all_trades)),   # newest on top
        "summary": {
            "all": tr.summarize(all_trades, "all"),
            "year": tr.summarize(all_trades, "year"),
            "month": tr.summarize(all_trades, "month"),
            "current_month": tr.summarize(all_trades, "current_month"),
        },
        "selected_period": tr.summarize(all_trades, period),
    }


@app.get("/api/strategies")
async def strategies():
    return {"strategies": [{"key": k, "title": v["title"]}
                           for k, v in eng.STRATEGIES.items()]}


@app.get("/api/strategy/samples")
async def strategy_samples():
    return {"samples": strat_mod.SAMPLES}


@app.get("/api/docs")
async def docs(lang: str = "en"):
    """Strategy-authoring documentation, per language (fallback to English)."""
    if lang not in ("en", "ru", "es"):
        lang = "en"
    docs_dir = _paths.DOCS_DIR
    path = docs_dir / f"strategies.{lang}.md"
    if not path.exists():
        path = docs_dir / "strategies.en.md"
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        text = "# Documentation\n\nNot found."
    return {"lang": lang, "markdown": text}


# ── Strategy editor (Python): validate → compile → register ──
STRAT_DYN = ROOT / "state" / "strategies.json"


def _strat_load_json() -> dict:
    try:
        return json.loads(STRAT_DYN.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _strat_save_json(d: dict) -> None:
    STRAT_DYN.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


async def strategy_load_saved() -> int:
    """Register the saved user strategies in the engine on startup."""
    d = _strat_load_json()
    n = 0
    for key, rec in d.items():
        fn, meta = strat_mod.build_strategy(rec.get("source", ""))
        if fn is None:
            log.warning("strategy %s does not compile on startup: %s", key, meta.get("errors"))
            continue
        eng.register_strategy(key, rec.get("title") or key, fn, meta.get("inputs"))
        n += 1
    return n


@app.post("/api/strategy/validate")
async def strategy_validate(payload: dict):
    """Code check BEFORE compilation: AST safety + dry run."""
    src = payload.get("source") or ""
    if not src.strip():
        raise HTTPException(400, "empty source")
    v = strat_mod.validate(src)
    result = {"ok": v["ok"], "errors": v["errors"], "inputs": v.get("inputs", [])}
    if not v["ok"]:
        return result
    symbol = payload.get("symbol") or "BTC"
    tf = payload.get("tf") or "1h"
    try:
        meta_i = await _resolve(symbol)
        bars = await cache.get_bars(meta_i["symbol"], tf, 500)
        if not bars:
            result["warn"] = "no bars for dry run"
            return result
        d0 = _df(bars)
        fn, meta = strat_mod.build_strategy(src)
        out = fn(d0)
        sigs = eng.signals_only(out, {}, meta_i.get("category", "crypto"))
        bt = tr_trades.build_trades(sigs)
        result["dryrun"] = {
            "symbol": meta_i["symbol"], "tf": tf, "bars": len(bars),
            "longs": int(out["long"].sum()), "shorts": int(out["short"].sum()),
            "exits": int(out["exit"].sum()),
            "trades": len(bt["trades"]), "has_open": bool(bt["open"]),
        }
    except Exception as e:  # noqa: BLE001
        result["ok"] = False
        result["errors"] = result.get("errors", []) + [
            {"line": 0, "level": "error", "msg": f"dry run: {e}"}]
    return result


@app.post("/api/strategy/compile")
async def strategy_compile(payload: dict):
    """Compile and register a strategy (after a successful check)."""
    src = payload.get("source") or ""
    name = str(payload.get("name") or "strategy").strip()
    if not src.strip():
        raise HTTPException(400, "empty source")
    v = strat_mod.validate(src)
    if not v["ok"]:
        return JSONResponse(status_code=400, content={"ok": False, "errors": v["errors"]})
    fn, meta = strat_mod.build_strategy(src)
    if fn is None:
        return JSONResponse(status_code=400, content={"ok": False, "errors": meta.get("errors")})
    try:
        bars = await cache.get_bars("BTC", "1h", 500)
        if bars:
            fn(_df(bars))
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=400,
                            content={"ok": False, "errors": [{"line": 0, "level": "error",
                                     "msg": f"dry run failed: {e}"}]})
    key = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_") or "strategy"
    if key in ("stv3", "rawa_system", "trend"):
        raise HTTPException(409, "name is taken by a built-in strategy")
    eng.register_strategy(key, name, fn, meta.get("inputs"))
    d = _strat_load_json()
    d[key] = {"title": name, "source": src, "inputs": meta.get("inputs")}
    _strat_save_json(d)
    return {"ok": True, "key": key, "title": name, "inputs": meta.get("inputs")}


@app.delete("/api/strategy/compiled/{key}")
async def strategy_unregister(key: str):
    eng.unregister_strategy(key)
    d = _strat_load_json()
    if key in d:
        del d[key]
        _strat_save_json(d)
    return {"ok": True, "removed": key}


@app.get("/api/strategy/compiled")
async def strategy_compiled():
    d = _strat_load_json()
    return {"compiled": [{"key": k, "title": v.get("title"),
                          "inputs": v.get("inputs", [])} for k, v in d.items()]}


@app.post("/api/strategy/indicator")
async def strategy_indicator(payload: dict):
    """Compile the code as an INDICATOR and return series for drawing."""
    src = payload.get("source") or ""
    if not src.strip():
        raise HTTPException(400, "empty source")
    symbol = payload.get("symbol") or "BTC"
    tf = payload.get("tf") or "1h"
    v = strat_mod.validate(src)
    if not v["ok"]:
        return JSONResponse(status_code=400, content={"ok": False, "errors": v["errors"]})
    fn, meta = strat_mod.build_strategy(src)
    if fn is None:
        return JSONResponse(status_code=400, content={"ok": False, "errors": meta.get("errors")})
    try:
        m = await _resolve(symbol)
        bars = await cache.get_bars(m["symbol"], tf, 500)
        d0 = _df(bars)
        params = payload.get("params") or {}
        fn(d0, **{k: v2 for k, v2 in params.items() if k in (meta.get("defaults") or {})})
        plots = getattr(fn, "last_plots", [])
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=400,
                            content={"ok": False, "errors": [{"line": 0, "level": "error",
                                     "msg": f"run: {e}"}]})
    times = [int(x) for x in d0["ts"]]
    return {"ok": True, "inputs": meta.get("inputs", []), "time": times, "plots": plots}


# ── Strategy export / import (sharing between users) ──────────
@app.get("/api/strategy/export/{key}")
async def strategy_export(key: str):
    d = _strat_load_json()
    rec = d.get(key)
    if not rec:
        raise HTTPException(404, "strategy not found")
    payload = {
        "kind": "rawanga-trading-desk-strategy",
        "version": 1,
        "key": key,
        "title": rec.get("title") or key,
        "source": rec.get("source", ""),
        "inputs": rec.get("inputs", []),
        "author": "Andrei Maltsev (Rawanga)",
        "license": "Apache-2.0",
        "homepage": "https://rawanga.es",
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    fname = re.sub(r"[^A-Za-z0-9_.-]", "_", rec.get("title") or key) + ".rwd.json"
    return Response(content=body, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.post("/api/strategy/import")
async def strategy_import(payload: dict):
    """Import a strategy: native format (.rwd.json) or {name, source}."""
    src = payload.get("source") or ""
    name = str(payload.get("title") or payload.get("name") or "imported").strip()
    if not src.strip():
        raise HTTPException(400, "empty source")
    v = strat_mod.validate(src)
    if not v["ok"]:
        return JSONResponse(status_code=400, content={"ok": False, "errors": v["errors"]})
    fn, meta = strat_mod.build_strategy(src)
    if fn is None:
        return JSONResponse(status_code=400, content={"ok": False, "errors": meta.get("errors")})
    key = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_") or "imported"
    if key in ("stv3", "rawa_system", "trend"):
        key += "_user"
    eng.register_strategy(key, name, fn, meta.get("inputs"))
    d = _strat_load_json()
    d[key] = {"title": name, "source": src, "inputs": meta.get("inputs")}
    _strat_save_json(d)
    return {"ok": True, "key": key, "title": name, "inputs": meta.get("inputs")}


@app.get("/api/params-matrix")
async def params_matrix():
    """All saved parameters (symbol×tf×strategy) for the UI."""
    return {"params": await store.all_params()}


# Risk add-ons (TP/trailing) — optional, off by default.
# Apply to any strategy; saved via the star (★) per symbol×tf×strategy.
RISK_EXTRAS = {
    "use_tp":    {"value": False, "name": "Take-profit on", "kind": "bool"},
    "tp_pct":    {"value": 2.0,   "name": "TP, % from entry",   "kind": "float"},
    "use_trail": {"value": False, "name": "Trailing stop on", "kind": "bool"},
    "trail_pct": {"value": 1.5,   "name": "Trailing, % from extreme", "kind": "float"},
}


@app.get("/api/strategy-params/{strategy}")
async def strategy_params(strategy: str, symbol: str = "*", tf: str = "*"):
    saved = await store.get_params(symbol, tf, strategy)
    defaults = {}
    entry = eng.STRATEGIES.get(strategy)
    if entry and not entry.get("custom"):
        import inspect
        for p in inspect.signature(entry["fn"]).parameters.values():
            if p.name == "df":
                continue
            dv = None if p.default is inspect.Parameter.empty else p.default
            kind = ("bool" if isinstance(dv, bool) else
                    "int" if isinstance(dv, int) else
                    "float" if isinstance(dv, float) else "string")
            defaults[p.name] = {"value": dv, "name": p.name, "kind": kind}
    return {"strategy": strategy, "symbol": symbol, "tf": tf,
            "params": {**defaults, **RISK_EXTRAS},
            "saved": saved}


@app.post("/api/strategy-params/{strategy}")
async def set_strategy_params(strategy: str, payload: dict):
    await store.set_params(payload.get("symbol", "*"), payload.get("tf", "*"),
                           strategy, payload.get("params", {}))
    return {"ok": True}


@app.get("/")
async def index():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    import hashlib, time as _t
    js = STATIC / "js" / "app.js"
    ver = hashlib.md5((js.read_bytes() if js.exists() else b"")).hexdigest()[:8]
    html = html.replace("/static/js/app.js", f"/static/js/app.js?v={ver}")
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    })


# ── Webhooks (E5) ─────────────────────────────────────────────

@app.get("/api/webhooks")
async def webhooks_list():
    return {"webhooks": await store.list_webhooks(),
            "matrix": await store.matrix()}


@app.post("/api/webhooks")
async def webhooks_add(payload: dict):
    hid = await store.add_webhook(
        symbol=payload.get("symbol", "*"),
        tf=payload.get("tf", "*"),
        strategy=payload.get("strategy", "*"),
        chat_id=str(payload.get("chat_id", wh.CREATOR_ID)),
        thread_id=payload.get("thread_id"),
        template=payload.get("template", ""))
    return {"id": hid}


@app.put("/api/webhooks/{hid}")
async def webhooks_update(hid: int, payload: dict):
    ok = await store.update_webhook(hid, payload)
    return {"ok": ok, "webhooks": await store.list_webhooks()}


@app.delete("/api/webhooks/{hid}")
async def webhooks_del(hid: int):
    return {"removed": await store.remove_webhook(hid)}


@app.post("/api/webhooks/{hid}/toggle")
async def webhooks_toggle(hid: int, payload: dict):
    return {"ok": await store.toggle_webhook(hid, bool(payload.get("enabled", True)))}


@app.post("/api/webhooks/cell")
async def webhook_cell(payload: dict):
    """Enable/disable a specific symbol×tf×strategy cell from the instruments panel."""
    await store.toggle_cell(payload.get("symbol", "*"), payload.get("tf", "*"),
                            payload.get("strategy", "*"),
                            bool(payload.get("enabled", True)))
    return {"ok": True, "matrix": await store.matrix()}


@app.post("/api/test-signal")
async def test_signal(payload: dict):
    """Test signal. By default — the chat set by the user (payload.chat).

    To test forum routing: pass a forum chat id + thread (or an auto-topic by
    instrument category).
    """
    symbol = payload.get("symbol", "BTC")
    strategy = payload.get("strategy", "stv3")
    tf = payload.get("tf", "1h")
    meta = await _resolve(symbol)
    params = await store.get_params(meta["symbol"], tf, strategy)
    d = eng.run(_df(await cache.get_bars(meta["symbol"], tf, 500)), strategy, params)
    sigs = eng.signals_only(d, params, meta.get("category", "crypto"))
    if not sigs:
        raise HTTPException(404, "no signals on current data")
    last = sigs[-1]
    text = wh.format_signal(last, meta["symbol"], tf, eng.STRATEGIES[strategy]["title"])
    chat = str(payload.get("chat", wh.DEFAULT_CHAT))
    if chat in ("prod", "channel") and wh.PROD_CHAT:
        chat = wh.PROD_CHAT
        thread = payload.get("thread")
        if thread is None:
            thread = wh.thread_for_category(meta.get("category"))
    else:
        thread = payload.get("thread")
    res = await wh.send_telegram(chat, text, thread, client=app.state.client)
    return {"sent": res.get("ok", False), "chat": chat, "thread": thread,
            "signal": last, "text": text}


# ── Real trading (BingX swap) ──────────────────────────

@app.get("/api/trade/settings")
async def trade_settings_get():
    return {"settings": await store.get_trade_settings(), "keys": ex.masked_keys()}


@app.post("/api/trade/settings")
async def trade_settings_set(payload: dict):
    # Save keys only when explicitly provided (empty ones do NOT wipe existing).
    keys = {k: payload[k] for k in ("api_key", "secret_key", "fund_password", "env",
                                     "notify_bot_token", "notify_chat_id",
                                     "smtp_host", "smtp_port", "smtp_user", "smtp_pass",
                                     "smtp_tls", "notify_email")
            if k in payload and payload.get(k) not in (None, "")}
    if keys:
        cur = ex.load_secrets()
        cur.update(keys)
        ex.save_secrets(cur)
    # Protection: real trading cannot be enabled without the fund password.
    live_req = payload.get("live_enabled") in (True, "1", "true", "True", "on")
    if live_req:
        s = ex.load_secrets()
        if not (s.get("api_key") and s.get("secret_key")):
            raise HTTPException(400, "Save the API keys first")
        if not s.get("fund_password"):
            raise HTTPException(400, "Set the fund password — real trading cannot be enabled without it")
        if not (payload.get("fund_password") or payload.get("confirm")):
            raise HTTPException(400, "Confirm enabling real trading with the fund password")
    await store.set_trade_settings(payload)
    return {"ok": True, "settings": await store.get_trade_settings(),
            "keys": ex.masked_keys()}


@app.post("/api/trade/keys/clear")
async def trade_keys_clear():
    ex.save_secrets({})
    return {"ok": True, "keys": ex.masked_keys()}


@app.post("/api/trade/test-notify")
async def trade_test_notify():
    """Test trade alert to the configured channels (Telegram and/or e-mail)."""
    cfg = ex.notify_cfg()
    chat = str(cfg.get("chat_id") or wh.DEFAULT_CHAT)
    text = "🔧 <b>Rawanga Trading Desk</b> — trade alert test"
    out = {"telegram": None, "email": None}
    if chat:
        res = await wh.send_telegram(chat, text, None, client=app.state.client,
                                     token=(cfg.get("token") or None))
        out["telegram"] = {"sent": bool(res and res.get("ok")), "chat": chat,
                           "error": None if (res and res.get("ok")) else ((res or {}).get("error") or (res or {}).get("description"))}
    mcfg = ex.mail_cfg()
    if mcfg.get("host") and mcfg.get("to"):
        from app.engine import mailer as _mail
        r = await _mail.send_email(mcfg, "Rawanga Trading Desk — test alert", text)
        out["email"] = {"sent": bool(r.get("ok")), "to": mcfg.get("to"), "error": r.get("error")}
    sent = bool((out["telegram"] or {}).get("sent") or (out["email"] or {}).get("sent"))
    return {"sent": sent, "chat": chat, "channels": out,
            "error": None if sent else "no channel configured or delivery failed"}


@app.get("/api/trade/tickers")
async def trade_tickers_get():
    return {"tickers": await store.list_trade_tickers()}


@app.post("/api/trade/tickers")
async def trade_tickers_add(payload: dict):
    sym = str(payload.get("symbol", "")).upper().strip()
    if not sym:
        raise HTTPException(400, "symbol required")
    # The symbol may be outside our research registry (e.g. XAUT) —
    # acceptable for real trading: category/pair from payload or default.
    try:
        meta = await _resolve(sym)
        cat = meta.get("category", "crypto")
    except Exception:  # noqa: BLE001
        cat = payload.get("category", "crypto")
    bx = payload.get("bingx_symbol") or ex.bingx_symbol(sym)
    ok = await store.add_trade_ticker(sym, cat, bx)
    if not ok:
        raise HTTPException(409, f"{sym} is already in the list")
    return {"added": sym, "bingx_symbol": bx}


@app.post("/api/trade/tickers/{symbol}/toggle")
async def trade_tickers_toggle(symbol: str, payload: dict):
    return {"ok": await store.set_trade_ticker(symbol, bool(payload.get("enabled", True)))}


@app.delete("/api/trade/tickers/{symbol}")
async def trade_tickers_del(symbol: str):
    return {"removed": await store.remove_trade_ticker(symbol)}


@app.get("/api/trade/available")
async def trade_available():
    """Which of our instruments exist as a BingX swap contract (UI hint)."""
    try:
        cs = await ex.contracts(client=app.state.client)
        have = {c.get("symbol") for c in cs}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"BingX contracts: {e}")
    rows = await store.list_instruments()
    out = []
    for r in rows:
        if r["category"] == "trend":
            continue
        bx = ex.bingx_symbol(r["symbol"])
        out.append({"symbol": r["symbol"], "category": r["category"],
                    "bingx_symbol": bx, "available": bx in have})
    return {"available": out}


@app.get("/api/trade/account")
async def trade_account():
    """Balance + PnL from real closed trades (REALIZED_PNL) + positions."""
    if not ex.masked_keys()["has_keys"]:
        return {"connected": False, "error": "API keys are not set"}
    try:
        bal = await ex.balance(client=app.state.client)
        pos = await ex.positions(client=app.state.client)
        inc = await ex.income("REALIZED_PNL", 500, client=app.state.client)
    except Exception as e:  # noqa: BLE001
        return {"connected": False, "error": str(e)}
    return {
        "connected": True,
        "balance": bal,
        "pnl_realized_total": ex.realised_pnl_total(inc),
        "pnl_records": len(inc),
        "positions": pos,
    }


@app.get("/api/trade/exec")
async def trade_exec_list(limit: int = 100):
    return {"exec": await store.list_exec(limit)}


@app.post("/api/trade/close/{symbol}")
async def trade_close(symbol: str):
    """Manual position close at market price (traded tickers only)."""
    if not await store.is_trade_enabled(symbol):
        raise HTTPException(403, f"{symbol} is not in the traded list")
    bx = ex.bingx_symbol(symbol)
    pos = await ex.positions(bx, client=app.state.client)
    closed = []
    for p in pos:
        if float(p.get("positionAmt", 0) or 0) == 0:
            continue
        r = await ex.close_position(bx, p.get("positionSide", "BOTH"), client=app.state.client)
        await store.log_exec(symbol, bx, "close", p.get("positionSide"), None, None,
                             r.get("code") == 0, r.get("msg"), json.dumps(r))
        closed.append(r)
    return {"ok": True, "closed": closed}
