"""Price alerts: you set them by messaging your Telegram bot, the robot checks prices
during market hours and sends a Telegram message plus a voice note (female voice).

Commands you can send to your bot:
  /alert SAHANA above 950     alert when Sahana trades at or above ₹950
  /alert ratnaveer below 340  alert when Ratnaveer trades at or below ₹340 (names work too)
  /alerts                     list your alerts
  /delete 3                   delete alert number 3   (or: /delete SAHANA  = all Sahana alerts)
  /price SAHANA               current price
  /help                       this list
"""
import html
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import yfinance as yf

import fundamentals as fx
import prices
import telegram as tg

IST = timezone(timedelta(hours=5, minutes=30))
HELP = (
    "🔔 <b>Price alerts</b>\n"
    "<code>/alert SAHANA above 950</code> — alert at or above ₹950\n"
    "<code>/alert SAHANA below 880</code> — alert at or below ₹880\n"
    "<code>/alerts</code> — list your alerts\n"
    "<code>/delete 3</code> — delete alert 3 (or <code>/delete SAHANA</code>)\n"
    "<code>/price SAHANA</code> — current price\n"
    "You can type the NSE symbol, BSE code, or part of the name of a stock in SP/DT.\n"
    "Alerts are checked every 15 minutes, Mon–Fri 9:15 AM–3:30 PM."
)
ALERT_RE = re.compile(r"^/alert(?:@\w+)?\s+(.+?)\s+(above|below|>|<|>=|<=)\s*₹?\s*([\d,]+(?:\.\d+)?)\s*$", re.I)


def empty_store():
    return {"offset": 0, "next_id": 1, "alerts": [], "bot_username": ""}


# ---------------------------------------------------------------- finding the stock
def resolve(text, sp, dt):
    """Turn what the user typed into (symbol, name). Watchlist stocks first, then any symbol."""
    q = text.strip().upper().replace("NSE:", "").replace("BSE:", "")
    rows = {**dt, **sp}
    if q in rows:
        return q, rows[q].get("name") or q
    word = re.compile(r"\b" + re.escape(q.lower()))
    hits = [(s, r.get("name") or s) for s, r in rows.items() if word.search((r.get("name") or "").lower())]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        return None, "Several stocks match: " + ", ".join(f"{n} ({s})" for s, n in hits[:6]) + ". Use the symbol."
    if re.fullmatch(r"[A-Z0-9&\-]{2,20}", q):
        return q, q
    return None, f"I could not find “{text.strip()}”. Use the NSE symbol or BSE code."


# ---------------------------------------------------------------- live prices
def market_open(now=None):
    now = now or datetime.now(IST)
    t = now.hour * 60 + now.minute
    return now.weekday() < 5 and 9 * 60 + 15 <= t <= 15 * 60 + 35


def live_prices(symbols, rows, tickers=None, now=None, budget_s=240):
    """{symbol: {"price": last, "bars": [(time, high, low), ...] today}}. Only fresh prices are returned:
    Yahoo 1-minute bars from today with the newest bar under 20 minutes old (so yesterday's close never
    triggers an alert), then the Screener page price for stocks Yahoo does not have (no high/low)."""
    import time as _t
    now = now or datetime.now(IST)
    out = {}
    if not symbols:
        return out
    tick = {s: (tickers or {}).get(s) or prices.yahoo_ticker(s, (rows.get(s) or {}).get("yahoo_override", "")) for s in symbols}
    try:
        data = yf.download(sorted(set(tick.values())), period="1d", interval="1m", auto_adjust=False,
                           group_by="ticker", progress=False, threads=True)
        for s, t in tick.items():
            try:
                df = data[t] if isinstance(data.columns, pd.MultiIndex) else data
                df = df.dropna(subset=["Close"])
                if df.empty:
                    continue
                idx = pd.DatetimeIndex(df.index)
                idx = idx.tz_localize("UTC") if idx.tz is None else idx
                idx = idx.tz_convert(IST)
                if idx[-1].date() != now.date() or now - idx[-1].to_pydatetime() > timedelta(minutes=20):
                    continue  # stale price (before the open, holiday, or stuck feed)
                out[s] = {"price": round(float(df["Close"].iloc[-1]), 2),
                          "bars": [(ts.to_pydatetime(), float(h), float(l)) for ts, h, l in zip(idx, df["High"], df["Low"])]}
            except (KeyError, TypeError, ValueError, AttributeError):
                pass
    except Exception as e:  # keep going with Screener
        print("Yahoo live price failed:", e)
    if now.hour * 60 + now.minute < 9 * 60 + 20:
        return out  # Screener still shows yesterday's price at the open
    sess, start = requests.Session(), _t.time()
    for s in symbols:
        if s in out:
            continue
        if _t.time() - start > budget_s:
            print("Screener price lookups stopped (time limit) — the rest are checked next run")
            break
        r = fx._get(sess, f"{fx.BASE}/company/{s}/")
        if r is not None and r.status_code == 200:
            p = fx.parse_company_page(r.text).get("price")
            if p:
                out[s] = {"price": p, "bars": []}
    return out


# ---------------------------------------------------------------- voice
def voice_text(a, price, lang):
    name, target = a["name"] or a["symbol"], f"{a['price']:g}"
    if lang == "hi":
        way = "ऊपर" if a["op"] == "above" else "नीचे"
        return f"प्राइस अलर्ट। {name} {target} रुपये के {way} पहुँच गया है। अभी का भाव {price:g} रुपये है।"
    way = "risen above" if a["op"] == "above" else "fallen below"
    return f"Price alert. {name} has {way} {target} rupees. The price now is {price:g} rupees."


def make_voice(text, lang="hi"):
    """Female voice (Google text-to-speech). Returns an .ogg voice note path (or .mp3 if conversion fails)."""
    try:
        from gtts import gTTS
    except ImportError:
        return None
    folder = tempfile.mkdtemp()
    mp3 = os.path.join(folder, "alert.mp3")
    try:
        if lang == "hi":
            gTTS(text, lang="hi").save(mp3)
        else:
            gTTS(text, lang="en", tld="co.in").save(mp3)  # Indian English
    except Exception as e:
        print("Voice could not be made:", e)
        return None
    ogg = os.path.join(folder, "alert.ogg")
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-c:a", "libopus", "-b:a", "48k", ogg],
                       check=True, timeout=60)
        return ogg
    except (OSError, subprocess.SubprocessError):
        return mp3


# ---------------------------------------------------------------- commands
def _list_text(store):
    active = [a for a in store["alerts"] if a["status"] == "active"]
    done = [a for a in store["alerts"] if a["status"] == "triggered"][-5:]
    if not active and not done:
        return "You have no alerts. Example: <code>/alert SAHANA above 950</code>"
    lines = ["🔔 <b>Active alerts</b>" if active else "No active alerts."]
    lines += [f"{a['id']}. {html.escape(a['name'])} ({a['symbol']}) {a['op']} ₹{a['price']:g}" for a in active]
    if done:
        lines += ["", "✅ <b>Recently triggered</b>"]
        lines += [f"{a['id']}. {html.escape(a['name'])} {a['op']} ₹{a['price']:g} — hit ₹{a.get('hit_price', 0):g} on {a.get('hit_at', '')}"
                  for a in done]
    return "\n".join(lines)


def process_commands(store, token, chat_id, sp, dt, now=None):
    """Read new messages to the bot and act on them. Returns True if alerts changed."""
    now = now or datetime.now(IST)
    changed = False
    for upd in tg.get_updates(token, store.get("offset", 0)):
        store["offset"] = upd["update_id"] + 1
        changed = True  # offset moved
        msg = upd.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != str(chat_id):
            continue  # only you can control the robot
        text = (msg.get("text") or "").strip()
        low = text.lower()
        if low.startswith("/alerts"):
            tg.send(token, chat_id, _list_text(store))
        elif low.startswith("/alert"):
            m = ALERT_RE.match(text)
            if not m:
                tg.send(token, chat_id, "Please write it like: <code>/alert SAHANA above 950</code>")
                continue
            sym, name = resolve(m.group(1), sp, dt)
            if not sym:
                tg.send(token, chat_id, html.escape(name))
                continue
            op = "above" if m.group(2).lower() in ("above", ">", ">=") else "below"
            if float(m.group(3).replace(",", "")) <= 0:
                tg.send(token, chat_id, "The price must be more than 0.")
                continue
            a = {"id": store["next_id"], "symbol": sym, "name": name, "op": op,
                 "price": float(m.group(3).replace(",", "")), "status": "active",
                 "created": now.strftime("%d %b %Y %I:%M %p"), "created_ts": now.isoformat(timespec="seconds"),
                 "ticker": _ticker(sym, sp, dt)}
            store["next_id"] += 1
            store["alerts"].append(a)
            tg.send(token, chat_id, f"✅ Alert {a['id']} set: <b>{html.escape(name)}</b> ({sym}) {op} ₹{a['price']:g}\n"
                                    "I check every 15 minutes during market hours (Mon–Fri 9:15–3:30).")
        elif low.startswith("/delete"):
            arg = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else ""
            before = len(store["alerts"])
            if arg.isdigit():
                store["alerts"] = [a for a in store["alerts"] if a["id"] != int(arg)]
            elif arg:
                sym, _ = resolve(arg, sp, dt)
                store["alerts"] = [a for a in store["alerts"] if a["symbol"] != sym]
            gone = before - len(store["alerts"])
            tg.send(token, chat_id, f"🗑 Deleted {gone} alert(s)." if gone else "No matching alert. Send /alerts to see the numbers.")
        elif low.startswith("/price"):
            arg = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
            sym, name = resolve(arg, sp, dt) if arg else (None, "Write it like: <code>/price SAHANA</code>")
            if not sym:
                tg.send(token, chat_id, name if not arg else html.escape(name))
                continue
            p = (live_prices([sym], {**dt, **sp}).get(sym) or {}).get("price")
            tg.send(token, chat_id, f"💹 <b>{html.escape(name)}</b> ({sym}): " + (f"₹{p:g}" if p else "price not available right now (market closed?)"))
        elif low.startswith("/help") or low.startswith("/start"):
            tg.send(token, chat_id, HELP)
    return changed


# ---------------------------------------------------------------- requests from the dashboard
def ingest_requests(store, folder, token, chat_id, sp, dt, now=None, strategies=None):
    """The dashboard saves one small file per click in data/alert_requests/. Apply them, then remove them.

    File content: {"action": "add", "symbol": "SAHANA", "name": "...", "op": "above", "price": 950}
               or {"action": "delete", "id": 3}
    Returns the number of requests applied.
    """
    import json
    now = now or datetime.now(IST)
    if not os.path.isdir(folder):
        return 0
    done = 0
    for fname in sorted(os.listdir(folder)):
        path = os.path.join(folder, fname)
        if not fname.endswith(".json"):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                req = json.load(f)
        except (OSError, ValueError):
            os.remove(path)
            continue
        if not isinstance(req, dict):
            os.remove(path)  # not a request: ignore it so it cannot block the alerts
            continue
        action = str(req.get("action", "")).lower()
        if action.startswith("strategy_"):
            if strategies is not None:
                import strategy
                strategy.apply_request(strategies, req, now.strftime("%Y-%m-%d"))
            os.remove(path)
            done += 1
            continue
        if action == "add":
            sym, name = resolve(str(req.get("symbol", "")), sp, dt)
            op = "below" if str(req.get("op", "")).lower() == "below" else "above"
            try:
                price = float(req.get("price"))
            except (TypeError, ValueError):
                price = 0.0
            if sym and price > 0:
                name = str(req.get("name") or name)[:80]
                a = {"id": store["next_id"], "symbol": sym, "name": name, "op": op, "price": round(price, 2),
                     "status": "active", "created": now.strftime("%d %b %Y %I:%M %p"), "source": "dashboard",
                     "created_ts": now.isoformat(timespec="seconds"), "ticker": _ticker(sym, sp, dt)}
                store["next_id"] += 1
                store["alerts"].append(a)
        elif action == "delete":
            try:
                aid = int(req.get("id"))
            except (TypeError, ValueError):
                aid = None
            store["alerts"] = [a for a in store["alerts"] if a["id"] != aid]
        os.remove(path)
        done += 1
    return done


# ---------------------------------------------------------------- checking
def _ticker(sym, sp, dt):
    row = sp.get(sym) or dt.get(sym) or {}
    return prices.yahoo_ticker(sym, row.get("yahoo_override", ""))


def _since(a):
    """Price bars after the alert was created count (an active alert has never been hit since then)."""
    try:
        return datetime.fromisoformat(a.get("created_ts"))
    except (TypeError, ValueError):
        return None


def check_alerts(store, token, chat_id, sp, dt, lang="hi", now=None, save=None):
    """Check active alerts against live prices (including the high/low since the last check, so a quick
    touch between two checks is not missed). Returns the alerts that fired.
    An alert is marked done only when the Telegram message was delivered; `save` is called after each one."""
    now = now or datetime.now(IST)
    active = [a for a in store["alerts"] if a["status"] == "active"]
    if not active:
        return []
    syms = sorted({a["symbol"] for a in active})
    px = live_prices(syms, {**dt, **sp}, tickers={a["symbol"]: a.get("ticker") for a in active if a.get("ticker")}, now=now)
    fired = []
    for a in active:
        info = px.get(a["symbol"])
        if not info:
            continue
        p, since = info["price"], _since(a)
        bars = [b for b in info["bars"] if b[0] > since] if since else info["bars"][-1:]
        hi = max([b[1] for b in bars] + [p])
        lo = min([b[2] for b in bars] + [p])
        touched = hi if a["op"] == "above" else lo
        if not ((a["op"] == "above" and touched >= a["price"]) or (a["op"] == "below" and touched <= a["price"])):
            continue
        arrow = "🔺" if a["op"] == "above" else "🔻"
        extra = f" (touched ₹{touched:g})" if abs(touched - p) > 1e-9 else ""
        ok = tg.send(token, chat_id,
                     f"🔔 <b>PRICE ALERT</b> {arrow}\n<b>{html.escape(str(a['name']))}</b> ({a['symbol']}) is {a['op']} ₹{a['price']:g}{extra}\n"
                     f"Price now: <b>₹{p:g}</b>  ·  <a href=\"{tg.chart_url(a['symbol'])}\">📈 Chart</a>")
        if not ok:
            continue  # Telegram did not get it: try again next run
        a.update(status="triggered", hit_price=p, hit_at=now.strftime("%d %b %Y %I:%M %p"))
        fired.append(a)
        tg.send_voice(token, chat_id, make_voice(voice_text(a, p, lang), lang), caption=f"Alert: {a['name']}")
        if save:
            save()  # saved at once, so a later problem in this run cannot make it fire again
    return fired
