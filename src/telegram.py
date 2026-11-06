"""Telegram: send messages and voice notes, and read the commands you send to the bot."""
import html
import os

import requests

API = "https://api.telegram.org/bot{token}/{method}"


def chart_url(symbol):
    """Chart link: TradingView for NSE symbols, Screener chart for BSE codes."""
    if str(symbol).isdigit():
        return f"https://www.screener.in/company/{symbol}/#chart"
    return f"https://www.tradingview.com/chart/?symbol=NSE%3A{symbol}"


def stock_line(symbol, name, extra=""):
    nm = html.escape(name or symbol)
    tail = f" — {html.escape(extra)}" if extra else ""
    return f"• <b>{nm}</b> ({symbol}){tail} — <a href=\"{chart_url(symbol)}\">📈 Chart</a>"


def _call(token, method, timeout=30, **kw):
    try:
        r = requests.post(API.format(token=token, method=method), timeout=timeout, **kw)
        data = r.json()
        if not data.get("ok"):
            print(f"Telegram {method} error:", str(data)[:300])
        return data
    except (requests.RequestException, ValueError) as e:
        print(f"Telegram {method} failed:", str(e).replace(str(token), "***"))  # never print the bot token
        return {"ok": False}


def _chunks(text, size=3800):
    out, cur = [], ""
    for line in text.split("\n"):
        while len(line) > size:  # a single very long line is cut into pieces, at a ", " so no tag or &amp; is split
            if cur:
                out.append(cur)
                cur = ""
            cut = line.rfind(", ", 0, size)
            cut = cut + 2 if cut > size // 2 else size
            out.append(line[:cut])
            line = line[cut:]
        if len(cur) + len(line) + 1 > size and cur:
            out.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return [c for c in out if c.strip()]


def send(token, chat_id, text):
    """Send a message (split into parts if long). Returns True when every part was delivered."""
    if not token or not chat_id:
        print("Telegram not configured — message below:\n" + text)
        return False
    ok = True
    for c in _chunks(text):
        res = _call(token, "sendMessage", data={"chat_id": chat_id, "text": c, "parse_mode": "HTML",
                                                "disable_web_page_preview": "true"})
        if not res.get("ok") and "parse" in str(res.get("description", "")).lower():
            # formatting problem: send the same text without formatting rather than lose it
            import re
            plain = re.sub(r"<[^>]+>", "", c).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
            res = _call(token, "sendMessage", data={"chat_id": chat_id, "text": plain, "disable_web_page_preview": "true"})
        ok = ok and bool(res.get("ok"))
    return ok


def send_voice(token, chat_id, path, caption=""):
    """Send an audio file as a voice note (.ogg) or as audio (.mp3)."""
    if not token or not chat_id or not path or not os.path.exists(path):
        return False
    method, field = ("sendVoice", "voice") if path.endswith(".ogg") else ("sendAudio", "audio")
    with open(path, "rb") as f:
        res = _call(token, method, timeout=60, data={"chat_id": chat_id, "caption": caption},
                    files={field: (os.path.basename(path), f)})
    return bool(res.get("ok"))


def get_updates(token, offset):
    """New messages sent to the bot since `offset`."""
    if not token:
        return []
    res = _call(token, "getUpdates", data={"offset": offset, "timeout": 0, "allowed_updates": '["message"]'})
    return res.get("result", []) if res.get("ok") else []


def bot_username(token):
    if not token:
        return ""
    res = _call(token, "getMe")
    return (res.get("result") or {}).get("username", "") if res.get("ok") else ""


def set_commands(token):
    """Show the command menu when you type "/" in the bot chat."""
    import json
    cmds = [{"command": "alert", "description": "Set price alert, e.g. /alert SAHANA above 950"},
            {"command": "alerts", "description": "List my alerts"},
            {"command": "delete", "description": "Delete an alert, e.g. /delete 3"},
            {"command": "price", "description": "Current price, e.g. /price SAHANA"},
            {"command": "help", "description": "How to use the alerts"}]
    return _call(token, "setMyCommands", data={"commands": json.dumps(cmds)}).get("ok", False)
