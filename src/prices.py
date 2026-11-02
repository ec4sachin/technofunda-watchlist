"""Step 4 - daily close vs 200-day EMA.

Prices come from Yahoo Finance first. Many BSE and SME stocks are missing on Yahoo,
so for those the price history is taken from Screener.in's own price chart instead,
and the 200-day EMA is calculated from it.
"""
import time

import pandas as pd
import requests
import yfinance as yf

SCREENER_CHART = "https://www.screener.in/api/company/{cid}/chart/?q=Price-DMA50-DMA200-Volume&days={days}"
# Screener sends weekly prices for long periods, so shorter periods are tried until daily prices come back
SCREENER_DAYS = (730, 500, 365)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
}


def yahoo_ticker(code, override=""):
    if override:
        return override
    return f"{code}.BO" if str(code).isdigit() else f"{code}.NS"


def _ema_result(close, period):
    """(last close, EMA, date). EMA is None when there are fewer than `period` trading days (new listing)."""
    close = close.dropna()
    if close.empty:
        return None
    last = (round(float(close.iloc[-1]), 2), pd.Timestamp(close.index[-1]).strftime("%d %b %Y"))
    if len(close) < period:
        return (last[0], None, last[1])
    ema = close.ewm(span=period, adjust=True).mean()
    return (last[0], round(float(ema.iloc[-1]), 2), last[1])


def close_and_ema(tickers, period=200):
    """Yahoo Finance. tickers: list of Yahoo tickers. Returns {ticker: (close, ema, date) or None}."""
    out = {t: None for t in tickers}
    if not tickers:
        return out
    data = yf.download(tickers, period="2y", interval="1d", auto_adjust=False,
                       group_by="ticker", progress=False, threads=True)
    for t in tickers:
        try:
            df = data[t] if isinstance(data.columns, pd.MultiIndex) else data
            out[t] = _ema_result(df["Close"], period)
        except (KeyError, TypeError):
            continue
    return out


def parse_screener_chart(payload):
    """Screener chart JSON -> (pandas Series of closing prices, is_weekly) or (None, False)."""
    for ds in (payload or {}).get("datasets", []):
        if str(ds.get("metric", "")).lower() != "price":
            continue
        weekly = bool((ds.get("meta") or {}).get("is_weekly"))
        dates, vals = [], []
        for point in ds.get("values", []):
            try:
                dates.append(pd.Timestamp(point[0]))
                vals.append(float(point[1]))
            except (TypeError, ValueError, IndexError):
                continue
        if vals:
            return pd.Series(vals, index=dates).sort_index(), weekly
    return None, False


def screener_close_and_ema(company_id, period=200, session=None, pause=1.5):
    """Price from Screener.in's chart for one company. Returns (close, ema or None, date) or None."""
    if not company_id:
        return None
    s = session or requests.Session()
    for days in SCREENER_DAYS:
        try:
            r = s.get(SCREENER_CHART.format(cid=company_id, days=days), headers=HEADERS, timeout=30)
            time.sleep(pause)
            if r.status_code == 429:
                time.sleep(15)
                continue
            if r.status_code != 200:
                print(f"Screener chart {company_id} ({days}d): HTTP {r.status_code}")
                continue
            series, weekly = parse_screener_chart(r.json())
        except (requests.RequestException, ValueError) as e:
            print(f"Screener chart {company_id} ({days}d): {e}")
            continue
        if series is None:
            continue
        if weekly:
            continue  # ask again for a shorter period, which comes back daily
        return _ema_result(series, period)
    return None
