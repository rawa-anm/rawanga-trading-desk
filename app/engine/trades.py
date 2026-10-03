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
trades.py — turns strategy signals into trades (entry→exit) and computes P/L.

Trade: entry (long/short), entry price, exit price, stop, direction,
P/L in % and in price units, duration. Plus aggregates for the period.
"""
from __future__ import annotations

import time

import pandas as pd


def build_trades(signals: list[dict]) -> list[dict]:
    """Builds a list of completed trades from a stream of signals."""
    trades = []
    open_pos = None
    for s in signals:
        if s["side"] in ("long", "short"):
            # if a position was open — close it at the current price (reversal)
            if open_pos:
                trades.append(_close(open_pos, s["ts"], s["close"], reason="reversal"))
            open_pos = {
                "side": s["side"],
                "entry_ts": s["ts"],
                "entry": s.get("entry", s["close"]),
                "stop": s.get("stop"),
                "vol_score": s.get("vol_score"),
            }
        elif s["side"] == "exit" and open_pos:
            trades.append(_close(open_pos, s["ts"], s["close"],
                                 reason=s.get("reason") or "signal",
                                 trailing=bool(s.get("trailing"))))
            open_pos = None
    # unclosed position — returned as open
    open_trade = None
    if open_pos:
        open_trade = {
            "side": open_pos["side"],
            "entry_ts": open_pos["entry_ts"],
            "entry_dt": _iso(open_pos["entry_ts"]),
            "entry": open_pos["entry"],
            "stop": open_pos["stop"],
            "vol_score": open_pos.get("vol_score"),
            "exit_ts": None, "exit": None,
            "pl_pct": None, "pl_price": None,
            "duration_bars": None, "status": "open", "reason": None,
        }
    for t in trades:
        t["status"] = "closed"
    return {"trades": trades, "open": open_trade}


def _close(pos: dict, exit_ts: int, exit_price: float, reason: str,
           trailing: bool = False) -> dict:
    sign = 1 if pos["side"] == "long" else -1
    pl_price = sign * (exit_price - pos["entry"])
    pl_pct = sign * (exit_price / pos["entry"] - 1) * 100 if pos["entry"] else 0.0
    return {
        "side": pos["side"],
        "entry_ts": pos["entry_ts"], "entry": pos["entry"],
        "exit_ts": exit_ts, "exit": exit_price,
        "entry_dt": _iso(pos["entry_ts"]), "exit_dt": _iso(exit_ts),
        "stop": pos["stop"],
        "trailing": trailing,
        "pl_price": round(pl_price, 6),
        "pl_pct": round(pl_pct, 4),
        "duration_bars": None,
        "reason": reason,
    }


def _iso(ts_ms: int) -> str:
    return pd.Timestamp(ts_ms, unit="ms", tz="UTC").strftime("%Y-%m-%d %H:%M UTC")


def period_bounds(period: str, now_ms: int | None = None) -> tuple[int, int]:
    """Returns [from_ms, to_ms) for 'year' | 'month' | 'current_month' | 'all'."""
    now = pd.Timestamp((now_ms or int(time.time() * 1000)), unit="ms", tz="UTC")
    if period == "year":
        start = pd.Timestamp(year=now.year, month=1, day=1, tz="UTC")
    elif period == "month":            # previous calendar month
        first = pd.Timestamp(year=now.year, month=now.month, day=1, tz="UTC")
        start = (first - pd.Timedelta(days=1)).replace(day=1)
    elif period == "current_month":    # current calendar month
        start = pd.Timestamp(year=now.year, month=now.month, day=1, tz="UTC")
    else:                              # all
        return 0, int(now.timestamp() * 1000)
    return int(start.timestamp() * 1000), int(now.timestamp() * 1000)


def summarize(trades: list[dict], period: str = "all") -> dict:
    """Statistics on completed trades for the period."""
    lo, hi = period_bounds(period)
    sel = [t for t in trades if t.get("exit_ts") and lo <= t["exit_ts"] < hi]
    wins = [t for t in sel if (t["pl_pct"] or 0) > 0]
    losses = [t for t in sel if (t["pl_pct"] or 0) <= 0]
    gross_win = sum(t["pl_pct"] for t in wins)
    gross_loss = sum(t["pl_pct"] for t in losses)
    total = sum(t["pl_pct"] for t in sel)
    best = max(sel, key=lambda t: t["pl_pct"]) if sel else None
    worst = min(sel, key=lambda t: t["pl_pct"]) if sel else None
    return {
        "period": period,
        "from": lo, "to": hi,
        "count": len(sel),
        "wins": len(wins), "losses": len(losses),
        "win_rate": round(100 * len(wins) / len(sel), 1) if sel else None,
        "pl_pct_sum": round(total, 2),
        "gross_win": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "avg_pct": round(total / len(sel), 3) if sel else None,
        "best_pct": round(best["pl_pct"], 2) if best else None,
        "worst_pct": round(worst["pl_pct"], 2) if worst else None,
        "profit_factor": round(gross_win / abs(gross_loss), 2) if gross_loss else None,
    }
