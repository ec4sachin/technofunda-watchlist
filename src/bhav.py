"""Real daily candles (open / high / low / close / volume) for stocks Yahoo does not carry
(mostly BSE and NSE SME stocks), from the exchanges' own end-of-day "bhavcopy" files.

Each exchange publishes one file per trading day with the prices of every listed stock:
  BSE: https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_YYYYMMDD_F_0000.CSV
  NSE: https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv
       (or the new format .../content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip)

The robot keeps the candles it has found in data/ohlc/SYMBOL.csv, so each day is downloaded only once.
The first run fills in about a year (newest first); after that only the new day is downloaded.
A day on which an SME stock had no trades at all is not in that day's file: it is kept as a flat candle
(open = high = low = close = that day's price, volume 0), which is how charting sites show a no-trade day.
"""
import csv
import io
import os
import time
import zipfile
from datetime import datetime

import requests

import storage

MAX_DAYS_PER_RUN = 560   # enough to fill a whole year for both exchanges in one run (first time only)
KEEP_DAYS = 400          # candles kept per stock
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
      "Accept": "text/csv,application/zip,application/octet-stream,*/*"}
BSE_URLS = ["https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{ymd}_F_0000.CSV"]
NSE_URLS = ["https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{dmy}.csv",
            "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"]

# Column names in the different file formats
COLS = {
    "code": ("FinInstrmId", "SC_CODE", "SCRIP_CODE"),
    "symbol": ("TckrSymb", "SYMBOL", "SC_NAME"),
    "series": ("SctySrs", "SERIES", "SC_GROUP"),
    "open": ("OpnPric", "OPEN_PRICE", "OPEN"),
    "high": ("HghPric", "HIGH_PRICE", "HIGH"),
    "low": ("LwPric", "LOW_PRICE", "LOW"),
    "close": ("ClsPric", "CLOSE_PRICE", "CLOSE"),
    "volume": ("TtlTradgVol", "TTL_TRD_QNTY", "NO_OF_SHRS", "TOTTRDQTY"),
}
NSE_EQ_SERIES = {"EQ", "BE", "BZ", "SM", "ST", "SZ", "MT"}


def _f(v):
    try:
        x = float(str(v).replace(",", "").strip())
        return x if x > 0 else None
    except (TypeError, ValueError):
        return None


def parse(text):
    """Bhavcopy CSV text -> list of dicts with code, symbol, series, open, high, low, close, volume."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        head = [h.strip() for h in next(reader)]
    except StopIteration:
        return []
    idx = {}
    for key, names in COLS.items():
        for n in names:
            if n in head:
                idx[key] = head.index(n)
                break
    if not all(k in idx for k in ("open", "high", "low", "close")) or not ("code" in idx or "symbol" in idx):
        return []
    out = []
    for row in reader:
        if len(row) < len(head) - 2:
            continue
        g = lambda k: row[idx[k]].strip() if k in idx and idx[k] < len(row) else ""
        o, h, l, c = _f(g("open")), _f(g("high")), _f(g("low")), _f(g("close"))
        if None in (o, h, l, c):
            continue
        out.append({"code": g("code"), "symbol": g("symbol").upper(), "series": g("series").upper(),
                    "open": o, "high": h, "low": l, "close": c, "volume": int(_f(g("volume")) or 0)})
    return out


def _download(session, url):
    r = session.get(url, headers=UA, timeout=40)
    if r.status_code != 200 or len(r.content) < 200:
        return None
    if url.endswith(".zip") or r.content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            name = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
            return z.read(name).decode("utf-8", "replace") if name else None
    text = r.content.decode("utf-8", "replace")
    return None if text.lstrip().startswith("<") else text  # an HTML error page is not a price file


class Exchange:
    """Downloads one exchange's daily files; gives up for this run after 4 failed downloads in a row."""

    def __init__(self, name, urls, session):
        self.name, self.urls, self.s, self.fails, self.ok = name, urls, session, 0, 0

    def day(self, d):
        if self.fails >= 4:
            return None
        for u in self.urls:
            try:
                text = _download(self.s, u.format(ymd=d.strftime("%Y%m%d"), dmy=d.strftime("%d%m%Y")))
            except (requests.RequestException, zipfile.BadZipFile, OSError):
                text = None
            time.sleep(0.4)
            rows = parse(text) if text else []
            if rows:
                self.fails, self.ok = 0, self.ok + 1
                return rows
        self.fails += 1
        return None


# ------------------------------------------------------------------ cache
def _cache_path(sym):
    return os.path.join(storage.DATA, "ohlc", f"{sym}.csv")


def load_cache(sym):
    p = _cache_path(sym)
    out = {}
    if os.path.exists(p):
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    out[r["date"]] = (float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), int(float(r["volume"] or 0)))
                except (KeyError, ValueError):
                    continue
    return out


def save_cache(sym, rows):
    os.makedirs(os.path.dirname(_cache_path(sym)), exist_ok=True)
    keep = sorted(rows)[-KEEP_DAYS:]
    with open(_cache_path(sym), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close", "volume"])
        for d in keep:
            w.writerow([d, *rows[d]])


def remove_unused(keep_symbols):
    folder = os.path.join(storage.DATA, "ohlc")
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if name.endswith(".csv") and name[:-4] not in keep_symbols:
                os.remove(os.path.join(folder, name))


# ------------------------------------------------------------------ main step
def enrich(need, hists, session=None, max_days=MAX_DAYS_PER_RUN, exchanges=None):
    """need: {symbol: {"nse": "...", "bse": "..."}} for stocks whose chart has closes only.
    hists: {symbol: chart history dict with "t" and "c"} (changed in place: adds "o", "h", "l", "v").
    Returns (number of days downloaded, list of warnings)."""
    s = session or requests.Session()
    ex = exchanges or {"bse": Exchange("BSE", BSE_URLS, s), "nse": Exchange("NSE", NSE_URLS, s)}
    caches = {sym: load_cache(sym) for sym in need}
    # which exchange file has each stock: NSE symbol when there is one, otherwise the BSE code
    where = {}
    for sym, c in need.items():
        if c.get("nse"):
            where[sym] = ("nse", c["nse"].upper())
        elif c.get("bse") or str(sym).isdigit():
            where[sym] = ("bse", str(c.get("bse") or sym))
    # trading days we still miss (taken from the stock's own price dates), newest first
    missing = {}
    for sym, (exch, _) in where.items():
        h = hists.get(sym) or {}
        for d in (h.get("t") or [])[-KEEP_DAYS:]:
            if d not in caches[sym]:
                missing.setdefault((exch, d), set()).add(sym)
    days = sorted(missing, key=lambda k: k[1], reverse=True)[:max_days]
    no_trade = {}
    fetched = 0
    for exch, d in days:
        rows = ex[exch].day(datetime.strptime(d, "%Y-%m-%d"))
        if rows is None:
            continue
        fetched += 1
        found = set()
        if exch == "bse":
            by = {r["code"]: r for r in rows if r["code"]}
        else:
            by = {}
            for r in rows:
                if r["series"] in NSE_EQ_SERIES or not r["series"]:
                    by.setdefault(r["symbol"], r)
        for sym in missing[(exch, d)]:
            r = by.get(where[sym][1])
            if r:
                caches[sym][d] = (r["open"], r["high"], r["low"], r["close"], r["volume"])
                found.add(sym)
        for sym in missing[(exch, d)] - found:
            no_trade.setdefault(sym, []).append(d)
    # no-trade days: only for stocks the files do contain on other days (so a wrong code never makes flat candles)
    for sym, ds in no_trade.items():
        if not caches[sym]:
            continue
        h = hists.get(sym) or {}
        pos = {t: i for i, t in enumerate(h.get("t") or [])}
        for d in ds:
            c = (h.get("c") or [None] * len(pos))[pos[d]] if d in pos else None
            if c:
                caches[sym][d] = (c, c, c, c, 0)
    for sym in where:
        if caches[sym]:
            save_cache(sym, caches[sym])
        merge(hists.get(sym), caches[sym])
    warnings = [f"{e.name} daily price files could not be downloaded today — those SME charts stay approximate (≈)."
                for e in ex.values() if e.fails >= 4 and e.ok == 0]
    return fetched, warnings


def merge(hist, cache):
    """Put real open/high/low (and volume) into a closes-only chart history, day by day."""
    if not hist or not cache or not hist.get("t"):
        return
    n = len(hist["t"])
    o, h, l = [None] * n, [None] * n, [None] * n
    v = list(hist.get("v") or [None] * n)
    for i, d in enumerate(hist["t"]):
        row = cache.get(d)
        if row:
            # the exchange file has the price of that day; the chart's close may be adjusted for a later
            # split / bonus, so open/high/low are scaled to the chart's close
            c = hist["c"][i]
            f = c / row[3] if c and row[3] else 1.0
            o[i], h[i], l[i] = round(row[0] * f, 2), round(row[1] * f, 2), round(row[2] * f, 2)
            if row[4] is not None:
                v[i] = round(row[4] / f) if f else row[4]
    if any(x is not None for x in o):
        hist.update(o=o, h=h, l=l, v=v)
