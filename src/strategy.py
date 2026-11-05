"""Trading strategies (paper trading until a broker is connected).

Settings (which strategies exist, ON/OFF, paper capital and % per trade) live in data/strategies.json and are changed
from the dashboard (through the Price Alerts robot). Trades live in data/strategy_trades.json and are
written only by the daily robot, so the two robots never edit the same file.

Swing Strategy rules (given by the user) - "version 5", chosen 4 Nov 2026 after comparing backtests:
  Entry (all must be true; checked on the candles before the entry day)
    1. Daily EMA 10 > EMA 20 > EMA 50 > EMA 200
    2. The last 5 daily candles (BASE_CANDLES; 4 until 5 Nov 2026) are in a tight range: highest high - lowest low
       <= 6% of the current price. Resistance = highest high of those candles. Buy when price goes 1% above it (a buy-stop order).
    3. The last candle's high is not more than 10% above EMA 10.
    (The old 42-candle "room to resistance" rule is switched off: ROOM_RULE = False.)
  Stop loss (whole quantity): 1% below the lowest low of the base, but never more than 6% below
    the actual buy price (the higher of the two is used).
  Time stop: if after 10 trading days the 50% target is not reached and the close is below +3%,
    sell everything at the close (frees the money for the next setup).
  Target: sell 50% at +20%.
  Trailing (remaining 50%): when a daily candle closes below EMA 10, its low becomes the exit line;
    if price later breaks below that low, sell the rest. A close back above EMA 10 clears the line.
"""
import math
import re

import pandas as pd

import storage

TYPES = {"swing": "Swing Strategy rules", "positional": "Positional Trading rules",
         "switch": "Smart Switch (Smallcap 100 decides the exits)", "none": "Rules not added yet"}
TRADING_TYPES = ("swing", "positional", "switch")
LISTS = ("SP", "DT", "BOTH")
DEFAULT = [{"id": "swing", "name": "Swing Strategy", "type": "swing", "list": "SP", "capital": 1000000, "pct": 13,
            "on": False, "note": "EMA stack + tight 5-candle base breakout", "added": ""},
           {"id": "positional", "name": "Positional Trading", "type": "positional", "list": "SP", "capital": 1000000, "pct": 12,
            "on": False, "note": "Same entry · 50% at +30% · rest exits on 2 closes below EMA 50", "added": ""},
           {"id": "switch", "name": "Smart Switch", "type": "switch", "list": "SP", "capital": 1000000, "pct": 12,
            "on": False, "note": "Same entry · exits follow Smallcap 100 daily: above EMA 50 → Positional, below → Swing", "added": ""}]
MAX_CATCHUP_DAYS = 10
BASE_CANDLES = 5           # rule 2: number of candles in the tight base (5 chosen 5 Nov 2026 after backtest; was 4)
BASE_RANGE = 0.06          # ... and the most their range may be (share of the current price)
BASE_MEASURE = "hl"        # "hl" = highest high / lowest low (wicks count), "close" = closing prices only
ROOM_RULE = False          # rule 4 / 6 (room to the 42-candle resistance) - off in version 5
STOP_BELOW_BASE = 0.01     # stop 1% below the base low
MAX_RISK = 0.06            # ... but never more than 6% below the buy price
TIME_STOP_DAYS, TIME_STOP_GAIN = 10, 0.03
TARGET, BOOK_FRACTION = 0.20, 0.5
# Exit rules of each strategy type (entry rules are the same for both)
RULES = {
    # climax: after the 50% booking, sell the rest when price runs far above its EMA (rule added 5 Nov 2026).
    # (ema, level when Smallcap 100 is above its EMA 50, level when below / unknown) - "middle path" chosen 5 Nov 2026
    "swing": {"target": 0.20, "trail": "ema10_low", "time_stop": (TIME_STOP_DAYS, TIME_STOP_GAIN), "climax": ("e10", 1.24, 1.20)},
    # Positional Trading (given 4 Nov 2026): 50% at +30%; the rest exits after 2 daily closes below EMA 50;
    # before the target the stop is 1% below the base low (and never more than 6% below the buy price)
    "positional": {"target": 0.30, "trail": "ema50_2close", "time_stop": None, "climax": ("e50", 1.48, 1.40)},
}
COST_PER_SIDE = 0.002      # brokerage + taxes + slippage, about 0.2% on each buy and each sell
DEF_CAPITAL, DEF_PCT = 1_000_000.0, 10.0   # paper capital, and % of the CURRENT capital per trade


# ------------------------------------------------------------------ settings
def load_settings():
    data = storage.load_json("strategies.json", None)
    if not isinstance(data, dict) or not isinstance(data.get("strategies"), list):
        data = {"strategies": [dict(s) for s in DEFAULT]}
    # a built-in strategy that is new (e.g. Positional Trading) appears automatically, unless it was removed
    ids, gone = {x.get("id") for x in data["strategies"]}, set(data.get("deleted", []))
    for d in DEFAULT:
        if d["id"] not in ids and d["id"] not in gone:
            data["strategies"].append(dict(d))
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
        cap = float(s.get("capital", old.get("capital", DEF_CAPITAL)))
    except (TypeError, ValueError):
        cap = DEF_CAPITAL
    try:
        pct = float(s.get("pct", old.get("pct", DEF_PCT)))
    except (TypeError, ValueError):
        pct = DEF_PCT
    out["capital"] = min(max(cap, 10_000.0), 1_000_000_000.0)
    out["pct"] = min(max(pct, 1.0), 100.0)
    out.pop("amount", None)
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
        if str(req.get("id")) in {d["id"] for d in DEFAULT}:
            data.setdefault("deleted", []).append(str(req.get("id")))  # do not bring a removed built-in back
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
    if i < 200 or i - 46 < 0:  # EMA 200 + 42 + base candles of history needed
        return None
    if not (df.e10[i] > df.e20[i] > df.e50[i] > df.e200[i]):                  # rule 1
        return None
    n, price = BASE_CANDLES, float(df.c[i])
    if BASE_MEASURE == "close":
        res, low = float(df.c[i - n + 1:i + 1].max()), float(df.c[i - n + 1:i + 1].min())
    else:
        res, low = float(df.h[i - n + 1:i + 1].max()), float(df.l[i - n + 1:i + 1].min())
    if (res - low) > BASE_RANGE * price:                                     # rule 2
        return None
    if df.h[i] > df.e10[i] * 1.10:                                           # rule 3
        return None
    entry = round(res * 1.01, 2)
    r42 = float(df.h[i - 41 - n:i - n + 1].max())                                    # rule 4
    room = (r42 - entry) / price * 100
    if ROOM_RULE and r42 > entry and 1 < room < 15:   # rule 4 + rule 6 (switched off in version 5)
        return None
    stop = max(low * (1 - STOP_BELOW_BASE), entry * (1 - MAX_RISK))
    return {"trigger": entry, "stop": round(stop, 2), "base_low": round(low, 2), "resistance": round(res, 2), "r42": round(r42, 2),
            "room": round(room, 1) if r42 > entry else None, "range_pct": round((res - low) / price * 100, 1),
            "base_from": df.index[i - n + 1], "base_to": df.index[i]}


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
    charges = round(COST_PER_SIDE * qty * (t["entry"] + price), 2)
    pnl = round(qty * (price - t["entry"]) - charges, 2)
    t["exits"].append({"date": day, "qty": qty, "price": round(price, 2), "reason": reason, "pnl": pnl, "charges": charges})
    t["pnl"] = round(sum(x["pnl"] for x in t["exits"]), 2)
    if t["remaining"] == 0:
        t["status"] = "closed"
        t["closed_on"] = day
        t["pnl_pct"] = round(t["pnl"] / (t["entry"] * t["qty"]) * 100, 2)
        t["hold_days"] = _days(t["entry_date"], day)
    return {"symbol": t["symbol"], "name": t["name"], "qty": qty, "price": round(price, 2), "reason": reason,
            "pnl": pnl, "strategy": t["strategy"], "date": day, "trade": t["id"], "closed": t["status"] == "closed",
            "trade_pnl": t["pnl"], "entry": t["entry"], "entry_date": t["entry_date"]}


SWITCH_MODE = "daily"   # chosen 4 Nov 2026 (best in both backtest years). Smart Switch: "entry" = rules fixed on the buy day, "up" = upgrade to Positional
                        # when small caps turn strong, "daily" = follow the index every day


def _apply_switch(t, df, j, mood):
    """Smart Switch during the trade: change the exit rules when the Nifty Smallcap 100 crosses its EMA 50."""
    if not t.get("switch") or mood is None or j < 1 or SWITCH_MODE == "entry":
        return
    m = mood.on(df.index[j - 1])   # the index as known before this day's trading
    if m is None:
        return
    want = "positional" if m[0] else "swing"
    if SWITCH_MODE == "up" and (want != "positional" or t["type"] == "positional" or t["booked"]):
        return
    if want != t["type"]:
        t["type"] = want
        if not t["booked"]:
            t["target"] = round(t["entry"] * (1 + RULES[want]["target"]), 2)
        t.setdefault("switches", []).append(f"{df.index[j]}: → {want}")


def manage(t, df, j, mood=None):
    """Apply the exit rules to an open trade on candle j. Returns the sells made."""
    _apply_switch(t, df, j, mood)
    day = df.index[j]
    o, h, l, c, e10 = float(df.o[j]), float(df.h[j]), float(df.l[j]), float(df.c[j]), float(df.e10[j])
    rules = RULES.get(t.get("type", "swing"), RULES["swing"])
    tgt_txt = f"Target +{rules['target'] * 100:g}% (50% booked)"
    done = []
    t["days"] = t.get("days", 0) + 1
    # stop loss (whole remaining quantity). Gap down: sold at the open.
    if l <= t["stop"]:
        s = _sell(t, day, t["remaining"], min(o, t["stop"]), t.get("stop_reason", "Stop loss"))
        return [s] if s else []
    # 50% at +20%
    if not t["booked"] and h >= t["target"]:
        half = int(t["qty"] * BOOK_FRACTION) or t["qty"]
        s = _sell(t, day, half, max(o, t["target"]), tgt_txt)
        t["booked"] = True
        if s:
            done.append(s)
        if t["status"] == "closed":
            return done
    # time stop: not moving -> free the money (Swing only)
    ts = rules["time_stop"]
    if ts and not t["booked"] and t["days"] >= ts[0] and c < t["entry"] * (1 + ts[1]):
        s = _sell(t, day, t["remaining"], c, f"Time stop ({ts[0]} days, under +{ts[1] * 100:g}%)")
        return done + ([s] if s else [])
    # climax exit for the rest: price far above its EMA (level from the day before = a waiting sell order)
    cx = rules.get("climax")
    if cx and t["booked"] and t["remaining"] and j > 0:
        ema_name, strong, weak = cx
        m = mood.on(df.index[j - 1]) if mood else None
        mult = strong if (m and m[0]) else weak
        level = float(getattr(df, ema_name)[j - 1]) * mult
        if h >= level:
            s = _sell(t, day, t["remaining"], max(o, level),
                      f"Climax exit ({mult:g}× EMA {ema_name[1:]} = ₹{level:,.2f})")
            if s:
                done.append(s)
            return done
    # Positional: the rest exits at the close of the 2nd daily close below EMA 50 in a row
    if rules["trail"] == "ema50_2close":
        if t["booked"]:
            t["below50"] = t.get("below50", 0) + 1 if c < float(df.e50[j]) else 0
            if t["below50"] >= 2:
                s = _sell(t, day, t["remaining"], c, "Trailing EMA 50 exit (2 closes below)")
                if s:
                    done.append(s)
        return done
    # Swing: trailing EMA 10 for the rest
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


def capital_of(st, book):
    """Paper capital now = starting capital + all profits/losses so far; free cash = capital - money in open trades."""
    sid = st.get("id")
    start = float(st.get("capital", DEF_CAPITAL))
    done = (book.get("realized") or {}).get(sid)
    if done is None:  # older trade files: add up the closed trades once
        done = sum(t["pnl"] for t in book.get("closed", []) if t["strategy"] == sid)
    part = sum(t["pnl"] for t in book.get("open", []) if t["strategy"] == sid)
    invested = sum(t["entry"] * t["remaining"] for t in book.get("open", []) if t["strategy"] == sid)
    equity = start + done + part
    return {"start": start, "equity": round(equity, 2), "invested": round(invested, 2), "cash": round(equity - invested, 2),
            "pct": float(st.get("pct", DEF_PCT))}


def trade_size(st, cap):
    """Money for one new trade: pct% of the current capital (needs that much free cash)."""
    size = cap["equity"] * cap["pct"] / 100
    return size if cap["cash"] >= size * 0.999 and size > 0 else 0.0


def exit_type(st, day, mood):
    """Which exit rules a new trade gets. Smart Switch: Smallcap 100 above its EMA 50 -> positional, else swing."""
    if st.get("type") != "switch":
        return st.get("type", "swing"), ""
    m = mood.on(day) if mood else None
    if m is None:
        return "swing", "Smallcap 100 unknown → Swing exits"
    return ("positional", f"Smallcap 100 {m[1]:,.0f} above EMA 50 {m[2]:,.0f} → Positional exits") if m[0] else \
           ("swing", f"Smallcap 100 {m[1]:,.0f} below EMA 50 {m[2]:,.0f} → Swing exits")


def try_entry(st, sym, name, df, j, mode="paper", money=None, mood=None):
    """Entry on candle j if the setup on the candle before is triggered. Returns (trade, sells on the same day) or (None, [])."""
    plan = swing_setup(df, j - 1)
    if not plan or df.h[j] < plan["trigger"]:
        return None, []
    sid = st.get("id")
    entry = max(plan["trigger"], float(df.o[j]))  # gap up above the trigger: filled at the open
    money = float(money if money is not None else st.get("capital", DEF_CAPITAL) * st.get("pct", DEF_PCT) / 100)
    ttype, regime = exit_type(st, df.index[j - 1], mood)
    qty = math.floor(money / entry)
    if qty < 1:
        return None, []
    stop = round(max(plan["base_low"] * (1 - STOP_BELOW_BASE), entry * (1 - MAX_RISK)), 2)
    why = f"Stop loss (1% below {BASE_CANDLES}-candle base)" if stop == round(plan["base_low"] * (1 - STOP_BELOW_BASE), 2) else "Stop loss (6% max risk)"
    t = {"id": f"{sid}-{sym}-{df.index[j]}", "strategy": sid, "strategy_name": st.get("name", sid),
         "symbol": sym, "name": name, "entry_date": df.index[j], "entry": round(entry, 2),
         "type": ttype, "regime": regime, "switch": st.get("type") == "switch",
         "qty": qty, "remaining": qty, "stop": stop, "stop_reason": why, "days": 0,
         "target": round(entry * (1 + RULES[ttype]["target"]), 2),
         "booked": False, "signal_low": None, "signal_date": None, "exits": [], "pnl": 0.0,
         "status": "open", "mode": mode, "money": round(money, 2), "plan": {k: plan[k] for k in ("resistance", "range_pct", "r42", "room")}}
    sells = []
    if df.l[j] <= t["stop"]:  # fell back to the stop on the same day
        s = _sell(t, df.index[j], t["remaining"], t["stop"], why + " — same day")
        if s:
            sells.append(s)
    return t, sells


def _log_buy(t):
    return {"date": t["entry_date"], "strategy": t["strategy_name"], "mode": t["mode"], "action": "BUY", "symbol": t["symbol"],
            "name": t["name"], "qty": t["qty"], "price": t["entry"], "value": round(t["qty"] * t["entry"], 2),
            "reason": f"Breakout above ₹{t['plan']['resistance']:g} + 1% (stop ₹{t['stop']:g}, target ₹{t['target']:g})"
                      + (f" · {t['regime']}" if t.get("regime") else ""),
            "pnl": "", "pnl_pct": "", "hold_days": "", "trade_id": t["id"]}


def _log_sell(s, t):
    return {"date": s["date"], "strategy": t["strategy_name"], "mode": t["mode"], "action": "SELL", "symbol": s["symbol"],
            "name": s["name"], "qty": s["qty"], "price": s["price"], "value": round(s["qty"] * s["price"], 2),
            "reason": s["reason"], "pnl": s["pnl"], "pnl_pct": round((s["price"] - t["entry"]) / t["entry"] * 100, 2),
            "hold_days": _days(t["entry_date"], s["date"]), "trade_id": t["id"]}


def run(settings, book, charts, sp, dt, today="", mood=None):
    """Process new daily candles for every ON strategy. Changes `book` (trades file) in place.
    Returns events for the Telegram message and the dashboard; events["log"] = rows for the trade log."""
    book.setdefault("open", [])
    book.setdefault("closed", [])
    book.setdefault("last_day", {})
    book["setups"] = {}
    events = {"entries": [], "exits": [], "setups": {}, "log": [],
              "names": {x.get("id"): x.get("name") for x in settings.get("strategies", [])}}
    frames = {s: _frame(h) for s, h in charts.items()}
    frames = {s: f for s, f in frames.items() if f is not None}
    names = {s: (sp.get(s) or dt.get(s) or {}).get("name") or s for s in frames}
    for st in settings.get("strategies", []):
        sid = st.get("id")
        if not st.get("on") or st.get("type") not in TRADING_TYPES:
            continue
        scan = set(sp) if st.get("list", "SP") == "SP" else set(dt) if st.get("list") == "DT" else set(sp) | set(dt)
        seen = book["last_day"].get(sid)
        if not isinstance(seen, dict):
            seen = book["last_day"][sid] = {}
        mine = {t["symbol"]: t for t in book["open"] if t["strategy"] == sid}

        def close(t):
            real = book.setdefault("realized", {})
            if sid not in real:
                real[sid] = sum(x["pnl"] for x in book["closed"] if x["strategy"] == sid)
            real[sid] = round(real[sid] + t["pnl"], 2)
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
                    before = t["type"]
                    sells = manage(t, df, j, mood)
                    if t["type"] != before:
                        events.setdefault("switched", []).append({"symbol": sym, "name": t["name"], "strategy": sid, "to": t["type"],
                                                                  "target": None if t["booked"] else t["target"], "date": df.index[j]})
                    for s in sells:
                        events["exits"].append(s)
                        events["log"].append(_log_sell(s, t))
                    if t["status"] == "closed":
                        close(t)
                    continue
                if t or sym not in scan:
                    continue
                if not swing_setup(df, j - 1) or df.h[j] < swing_setup(df, j - 1)["trigger"]:
                    continue
                money = trade_size(st, capital_of(st, book))
                if not money:
                    events.setdefault("skipped", []).append({"symbol": sym, "name": names.get(sym, sym), "date": df.index[j], "strategy": sid})
                    continue  # no free capital (all money in open trades)
                t, sells = try_entry(st, sym, names.get(sym, sym), df, j, money=money, mood=mood)
                if not t:
                    continue
                book["open"].append(t)
                mine[sym] = t
                events["entries"].append({"symbol": sym, "name": t["name"], "qty": t["qty"], "price": t["entry"],
                                          "stop": t["stop"], "target": t["target"], "strategy": sid, "regime": t.get("regime", "")})
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
                cap = capital_of(st, book)
                qty = max(1, math.floor(cap["equity"] * cap["pct"] / 100 / plan["trigger"]))
                ready.append({"symbol": sym, "name": names.get(sym, sym), "buy_above": plan["trigger"], "stop": plan["stop"],
                              "qty": qty, "amount": round(qty * plan["trigger"], 2), "range_pct": plan["range_pct"],
                              "risk_pct": round((plan["trigger"] - plan["stop"]) / plan["trigger"] * 100, 1),
                              "as_of": df.index[-1]})
        book["setups"][sid] = ready
        events["setups"][sid] = ready
        if st.get("type") == "switch":
            m = mood.now() if mood else None
            book.setdefault("mood", {})[sid] = events.setdefault("mood", {})[sid] = (
                {"above": m[0], "close": m[1], "ema50": m[2], "date": m[3], "rules": "Positional" if m[0] else "Swing"} if m else None)
        book.setdefault("capital", {})[sid] = capital_of(st, book)
        events.setdefault("capital", {})[sid] = book["capital"][sid]
    book["closed"] = book["closed"][-500:]
    return events


# ------------------------------------------------------------------ backtest
def backtest(st, charts, names, symbols, money=100000.0, mood=None):
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
                manage(t, df, j, mood)
                if t["status"] == "closed":
                    trades.append(t)
                    t = None
                continue
            t, _ = try_entry(st, sym, names.get(sym, sym), df, j, mode="backtest", money=money, mood=mood)
            if t and t["status"] == "closed":
                trades.append(t)
                t = None
        if t:
            last = float(df.c[-1])
            t["ltp"] = last
            t["last_date"] = df.index[-1]
            t["open_pnl"] = round((last - t["entry"]) * t["remaining"] - COST_PER_SIDE * t["remaining"] * (t["entry"] + last), 2)
            trades.append(t)
    return trades


def portfolio(trades, start, end="9999", capital=DEF_CAPITAL, pct=DEF_PCT):
    """The backtest trades taken in date order with one money pot: each trade gets pct% of the capital at that
    moment (profits grow the size), a trade is skipped when there is not enough free cash.
    Trade results already include costs."""
    # open trades count at today's price (their booked part + the rest at the last close)
    todo = sorted([t for t in trades if start <= t["entry_date"] < end and (t["status"] == "closed" or "open_pnl" in t)],
                  key=lambda t: (t["entry_date"], t["symbol"]))
    cash, opn, taken, skipped, wins, months, rows = float(capital), [], 0, 0, 0, {}, []

    def settle(upto):
        nonlocal cash, opn, wins
        keep = []
        for x in sorted(opn, key=lambda x: x["end"]):
            if x["end"] <= upto:
                gain = x["money"] * x["ret"]
                cash += x["money"] + gain
                months[x["end"][:7]] = round(months.get(x["end"][:7], 0) + gain, 2)
                wins += gain > 0
                rows.append({"name": x["name"], "symbol": x["symbol"], "entry_date": x["d"], "closed_on": x["end"], "open": x["open"],
                             "money": round(x["money"]), "pnl": round(gain, 2), "pnl_pct": round(x["ret"] * 100, 2)})
            else:
                keep.append(x)
        opn = keep

    for t in todo:
        settle(t["entry_date"])
        equity = cash + sum(x["money"] for x in opn)
        size = equity * pct / 100
        if cash < size * 0.999:
            skipped += 1
            continue
        cash -= size
        still = t["status"] != "closed"
        total = t["pnl"] + (t.get("open_pnl", 0) if still else 0)
        opn.append({"end": t.get("last_date", "9999-12") if still else t["closed_on"], "money": size, "ret": total / (t["entry"] * t["qty"]),
                    "name": t["name"], "symbol": t["symbol"], "d": t["entry_date"], "open": still})
        taken += 1
    settle("9999")
    eq, peak, dd, curve = float(capital), float(capital), 0.0, []
    for m in sorted(months):
        eq += months[m]
        peak = max(peak, eq)
        dd = max(dd, (peak - eq) / peak)
        curve.append([m, round(eq, 2)])
    first = todo[0]["entry_date"] if todo else start
    n_open = sum(1 for r in rows if r.get("open"))
    return {"start": start, "capital": capital, "pct": pct, "final": round(cash, 2), "profit": round(cash - capital, 2), "open_trades": n_open,
            "return_pct": round((cash / capital - 1) * 100, 1), "trades": taken, "skipped": skipped, "wins": wins,
            "win_rate": round(wins / taken * 100, 1) if taken else None, "max_drawdown_pct": round(dd * 100, 1),
            "months": months, "curve": curve, "first_trade": first, "trades_list": rows[-200:][::-1]}


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
