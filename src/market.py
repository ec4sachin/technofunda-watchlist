"""Market mood from the Nifty Smallcap 100 index: is it above or below its daily EMA 50?

Used by the "Smart Switch" strategy: when a trade is bought,
  index close > EMA 50  -> the trade uses the Positional Trading exit rules
  index close < EMA 50  -> the trade uses the Swing Strategy exit rules

Prices: Yahoo Finance (^CNXSC, whole history in one download). If Yahoo fails, NSE's official daily
index file (ind_close_all_DDMMYYYY.csv) is used, kept in data/index_smallcap100.csv.
"""
import csv
import io
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

import storage

YAHOO = "^CNXSC"
NAME = "Nifty Smallcap 100"
NSE_URL = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{dmy}.csv"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
CACHE = "index_smallcap100.csv"


def _from_yahoo():
    import yfinance as yf
    df = yf.download(YAHOO, period="max", interval="1d", auto_adjust=False, progress=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df[df["Close"].notna()]
    return {"t": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in df.index], "c": [round(float(x), 2) for x in df["Close"]]}


def parse_nse(text):
    """NSE ind_close_all CSV -> (date 'YYYY-MM-DD', close) of the Smallcap 100 row, or None."""
    rows = csv.reader(io.StringIO(text.lstrip("﻿")))
    head = [h.strip().lower() for h in next(rows, [])]
    try:
        i_name, i_date = head.index("index name"), head.index("index date")
        i_close = next(k for k, h in enumerate(head) if h.startswith("closing index value"))
    except (ValueError, StopIteration):
        return None
    for r in rows:
        if len(r) > i_close and r[i_name].strip().lower() == NAME.lower():
            try:
                d = datetime.strptime(r[i_date].strip(), "%d-%m-%Y").strftime("%Y-%m-%d")
                return d, round(float(r[i_close]), 2)
            except ValueError:
                return None
    return None


def _from_nse(days=120, session=None):
    """Fill the local cache with NSE daily index files (newest first, `days` calendar days back)."""
    s = session or requests.Session()
    p = os.path.join(storage.DATA, CACHE)
    have = {}
    if os.path.exists(p):
        with open(p, newline="", encoding="utf-8") as f:
            have = {r["date"]: float(r["close"]) for r in csv.DictReader(f)}
    today, fails = datetime.now(), 0
    for k in range(days):
        d = today - timedelta(days=k)
        if d.weekday() >= 5 or d.strftime("%Y-%m-%d") in have:
            continue
        try:
            r = s.get(NSE_URL.format(dmy=d.strftime("%d%m%Y")), headers=UA, timeout=30)
            got = parse_nse(r.text) if r.status_code == 200 else None
        except requests.RequestException:
            got = None
        time.sleep(0.3)
        if got:
            have[got[0]] = got[1]
            fails = 0
        else:
            fails += 1
            if fails >= 15 and not have:
                break
    if have:
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "close"])
            for d in sorted(have):
                w.writerow([d, have[d]])
    ks = sorted(have)
    return {"t": ks, "c": [have[d] for d in ks]} if ks else None


def history():
    """{'t': dates, 'c': closes} of the Nifty Smallcap 100 (Yahoo, else NSE files), or None."""
    try:
        h = _from_yahoo()
        if h and len(h["t"]) > 60:
            return h
    except Exception as e:
        print("Smallcap 100 from Yahoo failed:", e)
    try:
        return _from_nse()
    except Exception as e:
        print("Smallcap 100 from NSE failed:", e)
        return None


class Mood:
    """For any date: is the index above its EMA 50 on the last index close on or before that date?"""

    def __init__(self, hist):
        self.t = list((hist or {}).get("t") or [])
        c = pd.Series((hist or {}).get("c") or [], dtype=float)
        self.c = c.tolist()
        self.e50 = c.ewm(span=50, adjust=True).mean().tolist() if len(c) else []

    def on(self, day):
        """(above: True/False, close, ema50, index date) or None when unknown (no data, or under 50 days)."""
        import bisect
        k = bisect.bisect_right(self.t, day) - 1
        if k < 49:
            return None
        return self.c[k] > self.e50[k], round(self.c[k], 2), round(self.e50[k], 2), self.t[k]

    def now(self):
        return self.on(self.t[-1]) if self.t else None
