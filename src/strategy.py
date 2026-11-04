"""Trading strategies (paper trading until a broker is connected).

Settings (which strategies exist, ON/OFF, amount per trade) live in data/strategies.json and are changed
from the dashboard (through the Price Alerts robot). Trades live in data/strategy_trades.json and are
written only by the daily robot, so the two robots never edit the same file.

Swing Strategy rules (given by the user):
  Entry (all must be true; checked on the candles before the entry day)
    1. Daily EMA 10 > EMA 20 > EMA 50 > EMA 200
    2. The last 4 daily candles are in a tight range: highest high - lowest low <= 6% of the current price.
       Resistance = highest high of those 4 candles. Buy when price goes 1% above it (a buy-stop order).
    3. The last candle's high is not more than 10% above EMA 10.
    4. Resistance of the 42 candles before the base: if it is above the entry price but less than 15%
       (of the current price) away, skip. No resistance above the entry = OK.
    6. Exception to rule 4: if that resistance is within 1% of the entry price, take the trade
       (buying there is a breakout through the old resistance too).
  Stop loss: below the lowest low of the 4-candle base (whole quantity).
  Target: sell 50% at +20%.
  Trailing (remaining 50%): when a daily candle closes below EMA 10, its low becomes the exit line;
    if price later breaks below that low, sell the rest. A close back above EMA 10 clears the line.
"""
import math
import re

import pandas as pd

import storage

TYPES = {"swing": "Swing Strategy rules", "none": "Rules not added yet"}
LISTS = ("SP", "DT", "BOTH")
DEFAULT = [{"id": "swing", "name": "Swing Strategy", "type": "swing", "list": "SP", "amount": 25000,
            "on": False, "note": "EMA stack + tight 4-candle base breakout", "added": ""}]
MAX_CATCHUP_DAYS = 10


# ------------------------------------------------------------------ settings
def load_settings():
    data = storage.load_json("strategies.json", None)
    if not isinstance(data, dict) or not isinstance(data.get("strategies"), list):
        data = {"strategies": [dict(s) for s in DEFAULT]}
    return data


def _clean(s, old=None):
    """Only safe, known fields from the dashboard."""
    old = old or {}
    out = dict(old)
    sid = str(s.get("id") or old.get("id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,30}", sid):
        return None
    out["id"] = sid
    name = str(s.get("name", old.get("name", ""))).strip()[:40]
    if not name:
        return None
    out["name"] = name
    out["type"] = s.get("type", old.get("type", "none")) if s.get("type", old.get("type", "none")) in TYPES else "none"
    out["list"] = s.get("list", old.get("list", "SP")) if s.get("list", old.get("list", "SP")) in LISTS else "SP"
    out["note"] = str(s.get("note", old.get("note", "")))[:120]
    try:
        amt = float(s.get("amount", old.get("amount", 25000)))
    except (TypeError, ValueError):
        amt = 25000.0
    out["amount"] = min(max(amt, 1000.0), 10_000_000.0)
    out["on"] = bool(s.get("on", old.get("on", False)))
    out["added"] = str(old.get("added") or s.get("added") or "")[:10]
    return out


def apply_request(data, req, today=""):
    """{"action": "strategy_save", "strategy": {...}} or {"action": "strategy_delete", "id": "..."}.
    Returns True when the settings changed."""
    action = str(req.get("action", ""))
    items = data.setdefault("strategies", [])
    if action == "strategy_save" and isinstance(req.get("strategy"), dict):
        s = req["strategy"]
        old = next((x for x in items if x.get("id") == s.get("id")), None)
        new = _clean(s, old)
        if not new:
            return False
        if not new["added"]:
            new["added"] = today
        if old:
            if new["on"] and not old.get("on"):
                new["on_since"] = today
            items[items.index(old)] = new
        else:
            if new["on"]:
                new["on_since"] = today
            items.append(new)
        return True
    if action == "strategy_delete":
        before = len(items)
        data["strategies"] = [x for x in items if x.get("id") != str(req.get("id"))]
        return len(data["strategies"]) != before
    return False


# ------------------------------------------------------------------ candles
class Candles:
    """Daily candles as plain number arrays (fast for a candle-by-candle simulation)."""

    def __init__(self, idx, o, h, l, c):
        import numpy as np
        self.index = idx
        self.o, self.h, self.l, self.c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
        cs = pd.Series(self.c)
        for p in (10, 20, 50, 200):
            setattr(self, f"e{p}", cs.ewm(span=p, adjust=True).mean().to_numpy())

    def __len__(self):
        return len(self.index)


def _frame(hist):
    """Chart history -> Candles. Missing open/high/low (approximate candles) use the close."""
    if not hist or not hist.get("t"):
        return None
    t, c = hist["t"], hist["c"]
    n = len(t)
    get = lambda k: hist.get(k) or [None] * n
    o, h, l = get("o"), get("h"), get("l")
    keep = [i for i in range(n) if c[i] is not None]
    if not keep:
        return None
    pick = lambda arr: [arr[i] if arr[i] is not None else c[i] for i in keep]
    return Candles([t[i] for i in keep], pick(o), pick(h), pick(l), [c[i] for i in keep])


def swing_setup(df, i):
    """Setup using candles up to row i (the last base candle). Returns the buy-stop plan or None."""
    if i < 200 or i - 46 < 0:  # EMA 200 + 42 + 4 candles of history needed
        return None
    if not (df.e10[i] > df.e20[i] > df.e50[i] > df.e200[i]):                  # rule 1
        return None
    res, low, price = float(df.h[i - 3:i + 1].max()), float(df.l[i - 3:i + 1].min()), float(df.c[i])
    if (res - low) > 0.06 * price:                                           # rule 2
        return None
    if df.h[i] > df.e10[i] * 1.10:                                           # rule 3
        return None
    entry = round(res * 1.01, 2)
    r42 = float(df.h[i - 45:i - 3].max())                                    # rule 4
    room = (r42 - entry) / price * 100
    if r42 > entry and 1 < room < 15:   # rule 4 + rule 6 (within 1% = breakout through the old resistance)
        return None
    return {"trigger": entry, "stop": round(low, 2), "resistance": round(res, 2), "r42": round(r42, 2),
            "room": round(room, 1) if r42 > entry else None, "range_pct": round((res - low) / price * 100, 1),
            "base_from": df.index[i - 3], "base_to": df.index[i]}


# ------------------------------------------------------------------ trades
def _days(a, b):
    from datetime import date
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except ValueError:
        return None


def _sell(t, day, qty, price, reason):
    qty = min(qty, t["remaining"])
    if qty <= 0:
        return None
    t["remaining"] -= qty
    pnl = round(qty * (price - t["entry"]), 2)
    t["exits"].append({"date": day, "qty": qty, "price": round(price, 2), "reason": reason, "pnl": pnl})
    t["pnl"] = round(sum(x["pnl"] for x in t["exits"]), 2)
    if t["remaining"] == 0:
        t["status"] = "closed"
        t["closed_on"] = day
        t["pnl_pct"] = round(t["pnl"] / (t["entry"] * t["qty"]) * 100, 2)
        t["hold_days"] = _days(t["entry_date"], day)
    return {"symbol": t["symbol"], "name": t["name"], "qty": qty, "price": round(price, 2), "reason": reason,
            "pnl": pnl, "strategy": t["strategy"], "date": day, "trade": t["id"], "closed": t["status"] == "closed",
            "trade_pnl": t["pnl"], "entry": t["entry"], "entry_date": t["entry_date"]}


def manage(t, df, j):
    """Apply the exit rules to an open trade on candle j. Returns the sells made."""
    day = df.index[j]
    o, h, l, c, e10 = float(df.o[j]), float(df.h[j]), float(df.l[j]), float(df.c[j]), float(df.e10[j])
    done = []
    # stop loss below the base (whole remaining quantity). Gap down: sold at the open.
    if l <= t["stop"]:
        s = _sell(t, day, t["remaining"], min(o, t["stop"]), "Stop loss (below 4-candle base)")
        return [s] if s else []
    # 50% at +20%
    if not t["booked"] and h >= t["target"]:
        half = t["qty"] // 2 or t["qty"]
        s = _sell(t, day, half, max(o, t["target"]), "Target +20% (50% booked)")
        t["booked"] = True
        if s:
            done.append(s)
        if t["status"] == "closed":
            return done
    # trailing EMA 10 for the rest
    if t["booked"]:
        if t.get("signal_low") is not None and t.get("signal_date") != day and l < t["signal_low"]:
            s = _sell(t, day, t["remaining"], min(o, t["signal_low"]), "Trailing EMA 10 exit")
            if s:
                done.append(s)
            return done
        if c < e10:
            t["signal_low"], t["signal_date"] = round(l, 2), day
        elif c > e10:
            t["signal_low"], t["signal_date"] = None, None
    return done


def try_entry(st, sym, name, df, j, mode="paper"):
    """Entry on candle j if the setup on the candle before is triggered. Returns (trade, sells on the same day) or (None, [])."""
    plan = swing_setup(df, j - 1)
    if not plan or df.h[j] < plan["trigger"]:
        return None, []
    sid = st.get("id")
    entry = max(plan["trigger"], float(df.o[j]))  # gap up above the trigger: filled at the open
    qty = max(1, math.floor(float(st.get("amount", 25000)) / entry))
    t = {"id": f"{sid}-{sym}-{df.index[j]}", "strategy": sid, "strategy_name": st.get("name", sid),
         "symbol": sym, "name": name, "entry_date": df.index[j], "entry": round(entry, 2),
         "qty": qty, "remaining": qty, "stop": plan["stop"], "target": round(entry * 1.20, 2),
         "booked": False, "signal_low": None, "signal_date": None, "exits": [], "pnl": 0.0,
         "status": "open", "mode": mode, "plan": {k: plan[k] for k in ("resistance", "range_pct", "r42", "room")}}
    sells = []
    if df.l[j] <= t["stop"]:  # fell back to the stop on the same day
        s = _sell(t, df.index[j], t["remaining"], t["stop"], "Stop loss (same day)")
        if s:
            sells.append(s)
    return t, sells


def _log_buy(t):
    return {"date": t["entry_date"], "strategy": t["strategy_name"], "mode": t["mode"], "action": "BUY", "symbol": t["symbol"],
            "name": t["name"], "qty": t["qty"], "price": t["entry"], "value": round(t["qty"] * t["entry"], 2),
            "reason": f"Breakout above ₹{t['plan']['resistance']:g} + 1% (stop ₹{t['stop']:g}, target ₹{t['target']:g})",
            "pnl": "", "pnl_pct": "", "hold_days": "", "trade_id": t["id"]}


def _log_sell(s, t):
    return {"date": s["date"], "strategy": t["strategy_name"], "mode": t["mode"], "action": "SELL", "symbol": s["symbol"],
            "name": s["name"], "qty": s["qty"], "price": s["price"], "value": round(s["qty"] * s["price"], 2),
            "reason": s["reason"], "pnl": s["pnl"], "pnl_pct": round((s["price"] - t["entry"]) / t["entry"] * 100, 2),
            "hold_days": _days(t["entry_date"], s["date"]), "trade_id": t["id"]}


def run(settings, book, charts, sp, dt, today=""):
    """Process new daily candles for every ON strategy. Changes `book` (trades file) in place.
    Returns events for the Telegram message and the dashboard; events["log"] = rows for the trade log."""
    book.setdefault("open", [])
    book.setdefault("closed", [])
    book.setdefault("last_day", {})
    book["setups"] = {}
    events = {"entries": [], "exits": [], "setups": {}, "log": []}
    frames = {s: _frame(h) for s, h in charts.items()}
    frames = {s: f for s, f in frames.items() if f is not None}
    names = {s: (sp.get(s) or dt.get(s) or {}).get("name") or s for s in frames}
    for st in settings.get("strategies", []):
        sid = st.get("id")
        if not st.get("on") or st.get("type") != "swing":
            continue
        scan = set(sp) if st.get("list", "SP") == "SP" else set(dt) if st.get("list") == "DT" else set(sp) | set(dt)
        seen = book["last_day"].get(sid)
        if not isinstance(seen, dict):
            seen = book["last_day"][sid] = {}
        mine = {t["symbol"]: t for t in book["open"] if t["strategy"] == sid}

        def close(t):
            book["open"].remove(t)
            book["closed"].append(t)
            mine.pop(t["symbol"], None)

        for sym, df in frames.items():
            # each stock remembers its own last checked candle; a stock seen for the first time
            # (strategy just switched ON, or newly added to the list) starts from its next new candle
            since = seen.get(sym) or df.index[-1]
            seen[sym] = df.index[-1]
            idx = [k for k, d in enumerate(df.index) if d > since][-MAX_CATCHUP_DAYS:]
            for j in idx:
                t = mine.get(sym)
                if t and t["entry_date"] < df.index[j]:
                    for s in manage(t, df, j):
                        events["exits"].append(s)
                        events["log"].append(_log_sell(s, t))
                    if t["status"] == "closed":
                        close(t)
                    continue
                if t or sym not in scan:
                    continue
                t, sells = try_entry(st, sym, names.get(sym, sym), df, j)
                if not t:
                    continue
                book["open"].append(t)
                mine[sym] = t
                events["entries"].append({"symbol": sym, "name": t["name"], "qty": t["qty"], "price": t["entry"],
                                          "stop": t["stop"], "target": t["target"], "strategy": sid})
                events["log"].append(_log_buy(t))
                for s in sells:
                    events["exits"].append(s)
                    events["log"].append(_log_sell(s, t))
                if t["status"] == "closed":
                    close(t)
        for sym in [x for x in seen if x not in frames and x not in mine]:
            seen.pop(sym)  # stock left the lists
        # setups for the next session: a buy-stop to place today
        ready = []
        for sym in sorted(scan):
            df = frames.get(sym)
            if df is None or sym in mine:
                continue
            plan = swing_setup(df, len(df) - 1)
            if plan:
                qty = max(1, math.floor(float(st.get("amount", 25000)) / plan["trigger"]))
                ready.append({"symbol": sym, "name": names.get(sym, sym), "buy_above": plan["trigger"], "stop": plan["stop"],
                              "qty": qty, "amount": round(qty * plan["trigger"], 2), "range_pct": plan["range_pct"],
                              "risk_pct": round((plan["trigger"] - plan["stop"]) / plan["trigger"] * 100, 1),
                              "as_of": df.index[-1]})
        book["setups"][sid] = ready
        events["setups"][sid] = ready
    book["closed"] = book["closed"][-500:]
    return events


# ------------------------------------------------------------------ backtest
def backtest(st, charts, names, symbols):
    """The same rules on all past candles of `symbols` (one trade per stock at a time).
    Note: these are stocks in the list TODAY, so the result is more optimistic than real life."""
    trades = []
    for sym in symbols:
        df = _frame(charts.get(sym))
        if df is None or len(df) < 248:
            continue
        t = None
        for j in range(247, len(df)):
            if t:
                manage(t, df, j)
                if t["status"] == "closed":
                    trades.append(t)
                    t = None
                continue
            t, _ = try_entry(st, sym, names.get(sym, sym), df, j, mode="backtest")
            if t and t["status"] == "closed":
                trades.append(t)
                t = None
        if t:
            last = float(df.c[-1])
            t["ltp"] = last
            t["open_pnl"] = round((last - t["entry"]) * t["remaining"], 2)
            trades.append(t)
    return trades


# ------------------------------------------------------------------ performance
def report(trades):
    """How good is the strategy? Works on closed trades (open ones are listed separately)."""
    closed = sorted([t for t in trades if t["status"] == "closed"], key=lambda t: t.get("closed_on", ""))
    opn = [t for t in trades if t["status"] != "closed"]
    wins = [t for t in closed if t["pnl"] > 0]
    loss = [t for t in closed if t["pnl"] <= 0]
    gw, gl = sum(t["pnl"] for t in wins), -sum(t["pnl"] for t in loss)
    eq, peak, dd, curve, months = 0.0, 0.0, 0.0, [], {}
    for t in closed:
        eq += t["pnl"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        curve.append([t["closed_on"], round(eq, 2)])
        m = t["closed_on"][:7]
        months[m] = round(months.get(m, 0) + t["pnl"], 2)
    pct = [t.get("pnl_pct") or 0 for t in closed]
    holds = [t.get("hold_days") for t in closed if t.get("hold_days") is not None]
    n = len(closed)
    return {
        "trades": n, "open": len(opn), "wins": len(wins), "losses": len(loss),
        "win_rate": round(len(wins) / n * 100, 1) if n else None,
        "total_pnl": round(eq, 2),
        "open_pnl": round(sum(t.get("open_pnl", 0) for t in opn), 2),
        "avg_win": round(gw / len(wins), 2) if wins else None,
        "avg_loss": round(-gl / len(loss), 2) if loss else None,
        "profit_factor": round(gw / gl, 2) if gl > 0 else None,
        "expectancy": round(eq / n, 2) if n else None,
        "avg_return_pct": round(sum(pct) / n, 2) if n else None,
        "best": max((t["pnl"] for t in closed), default=None),
        "worst": min((t["pnl"] for t in closed), default=None),
        "max_drawdown": round(dd, 2),
        "avg_hold_days": round(sum(holds) / len(holds), 1) if holds else None,
        "first": closed[0]["entry_date"] if closed else None, "last": closed[-1]["closed_on"] if closed else None,
        "curve": curve, "months": months,
    }


def stats(book, sid=None):
    closed = [t for t in book.get("closed", []) if sid is None or t["strategy"] == sid]
    wins = [t for t in closed if t["pnl"] > 0]
    return {"trades": len(closed), "wins": len(wins), "win_rate": round(len(wins) / len(closed) * 100) if closed else None,
            "pnl": round(sum(t["pnl"] for t in closed), 2)}
