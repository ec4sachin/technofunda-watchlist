"""Relative Strength (RS) Rating 1-99, IBD / MarketSmith style, for new SP / DT stocks.

Score of a stock = its price gain over the last 3, 6, 9 and 12 months, the last 3 months counted double:
    score = (2 x close/close_3m + close/close_6m + close/close_9m + close/close_12m) / 5
RS Rating = the % of all BSE-listed stocks whose score is lower (1 = weakest, 99 = strongest).

All BSE stocks: from BSE's daily price file (bhavcopy) of 5 days - today and about 3, 6, 9, 12 months back.
Those 5 files are downloaded only when a new stock passes its marks, and once per run.
The new stock itself is measured on its own split / bonus adjusted price history.
A stock listed less than 12 months ago is compared with the periods it has (at least 3 months),
against all stocks over those same periods. Under 3 months of prices: too new to rate.
"""
import bisect
from datetime import datetime, timedelta

import requests

import bhav
import prices

MONTHS = (3, 6, 9, 12)
WEIGHT = {3: 2, 6: 1, 9: 1, 12: 1}
_market = {}     # one download per run: {"dates": {0: "YYYY-MM-DD", 3: ...}, "close": {months: {code: close}}}
NOT_EQUITY = {"F", "G", "GS", "DB", "E", "IF", "MF", "TB"}   # debt, govt securities, ETFs, funds


def _equity(r):
    c = str(r.get("code", ""))
    return c.isdigit() and 500000 <= int(c) <= 599999 and r.get("series", "") not in NOT_EQUITY


def market(today=None, exchange=None):
    """Closing prices of all BSE stocks on the latest trading day and ~3 / 6 / 9 / 12 months before it.
    Returns the saved dict, or None if the latest day's file could not be downloaded."""
    if _market.get("ok"):
        return _market
    ex = exchange or bhav.Exchange("BSE", bhav.BSE_URLS, requests.Session())
    now = today or datetime.now(prices.IST).replace(tzinfo=None)
    dates, close = {}, {}

    def first_file(start, back=8, skip_today=False):
        for k in range(back):
            d = start - timedelta(days=k)
            if d.weekday() >= 5 or (skip_today and k == 0 and d.date() == now.date() and now.hour < 18):
                continue
            rows = ex.day(d)
            if rows:
                return d, {r["code"]: r["close"] for r in rows if _equity(r)}
        return None, None

    d0, c0 = first_file(now, back=10, skip_today=True)
    if not c0:
        return None
    dates[0], close[0] = d0.strftime("%Y-%m-%d"), {k: v for k, v in c0.items() if v >= 1}   # no sub-₹1 stocks today
    for mo in MONTHS:
        d, c = first_file(d0 - timedelta(days=round(mo * 30.44)))
        if c:
            dates[mo], close[mo] = d.strftime("%Y-%m-%d"), c
    if 3 not in close:
        return None
    _market.update(ok=True, dates=dates, close=close)
    return _market


def _score(now, then):
    """then: {months: close}. Weighted average of now / then over the periods given."""
    w = sum(WEIGHT[mo] for mo in then)
    return sum(WEIGHT[mo] * now / then[mo] for mo in then) / w


def rating(chart, mk):
    """RS Rating (1-99) of a stock with price history chart {"t": [...], "c": [...]} against market mk.
    Returns (rating or None, note)."""
    if not chart or not chart.get("t"):
        return None, "no price history"
    t, c = chart["t"], chart["c"]
    pts = [(d, v) for d, v in zip(t, c) if v]
    if not pts:
        return None, "no price history"
    ts = [d for d, _ in pts]

    def close_on(ds):     # last close on or before that day
        i = bisect.bisect_right(ts, ds) - 1
        return pts[i][1] if i >= 0 else None

    now = close_on(mk["dates"][0])
    then = {}
    for mo in MONTHS:
        ds = mk["dates"].get(mo)
        if ds and ts[0] <= ds:
            v = close_on(ds)
            if v:
                then[mo] = v
    if not now or 3 not in then:
        return None, "too new (under 3 months of prices)"
    # keep only periods without a gap: 3, then 6, then 9, then 12
    use = []
    for mo in MONTHS:
        if mo not in then:
            break
        use.append(mo)
    mine = _score(now, {mo: then[mo] for mo in use})
    base = mk["close"][0]
    others = []
    for code, cnow in base.items():
        th = {mo: mk["close"][mo].get(code) for mo in use}
        if all(th.values()):
            others.append(_score(cnow, th))
    if len(others) < 500:
        return None, "not enough market prices"
    others.sort()
    below = bisect.bisect_left(others, mine)
    r = max(1, min(99, round(100 * below / len(others))))
    span = f"{use[-1]} months" if len(use) < 4 else "12 months"
    return r, f"RS {r} ({span}, vs {len(others)} BSE stocks)"


def chart_for(code, m):
    """Split / bonus adjusted price history of a stock: Yahoo, else Screener's price chart."""
    t = prices.yahoo_ticker(code)
    res = None
    try:
        res = prices.close_and_ema([t], 200, span="2y").get(t)
    except Exception:
        res = None
    if not res and m.get("_company_id"):
        try:
            res = prices.screener_close_and_ema(m["_company_id"], 200)
        except Exception:
            res = None
    return res[3] if res and len(res) > 3 else None


def check(code, m, min_rs, today=None, chart=None):
    """Returns (status, rating, note): "pass" (RS above min_rs, or too new to rate),
    "fail" (RS min_rs or lower), "retry" (prices could not be read).
    chart: the stock's price history when already downloaded (else it is downloaded here)."""
    mk = market(today)
    if not mk:
        return "retry", None, "BSE price files could not be downloaded"
    r, note = rating(chart if chart and chart.get("t") else chart_for(code, m or {}), mk)
    if r is None:
        if note.startswith("too new"):
            return "pass", None, "RS: " + note
        return "retry", None, "RS: " + note
    return ("pass" if r > min_rs else "fail"), r, note
