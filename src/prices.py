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


def _r(v):
    return None if v is None or pd.isna(v) else round(float(v), 2)


def _payload(df):
    """Full daily history for the dashboard chart: dates + open/high/low/close/volume (o/h/l only when known)."""
    out = {"t": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in df.index], "c": [_r(v) for v in df["Close"]]}
    if all(k in df for k in ("Open", "High", "Low")):
        out.update(o=[_r(v) for v in df["Open"]], h=[_r(v) for v in df["High"]], l=[_r(v) for v in df["Low"]])
    if "Volume" in df:
        out["v"] = [None if pd.isna(v) else int(v) for v in df["Volume"]]
    return out


def _ema_result(df, period):
    """(last close, EMA, date, chart history). df has a Close column (Open/High/Low/Volume optional).

    EMA is None with fewer than `period` trading days (new listing).
    """
    if isinstance(df, pd.Series):
        df = df.to_frame("Close")
    df = df[df["Close"].notna()]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if df.empty:
        return None
    close = df["Close"].astype(float)
    last = (round(float(close.iloc[-1]), 2), pd.Timestamp(close.index[-1]).strftime("%d %b %Y"))
    hist = _payload(df)
    if len(close) < period:
        return (last[0], None, last[1], hist)
    ema = close.ewm(span=period, adjust=True).mean()
    return (last[0], round(float(ema.iloc[-1]), 2), last[1], hist)


def close_and_ema(tickers, period=200):
    """Yahoo Finance, whole history. Returns {ticker: (close, ema, date, history) or None}."""
    out = {t: None for t in tickers}
    if not tickers:
        return out
    data = yf.download(tickers, period="max", interval="1d", auto_adjust=False,
                       group_by="ticker", progress=False, threads=True)
    for t in tickers:
        try:
            df = data[t] if isinstance(data.columns, pd.MultiIndex) else data
            out[t] = _ema_result(df[[c for c in ("Open", "High", "Low", "Close", "Volume") if c in df]], period)
        except (KeyError, TypeError):
            continue
    return out


def parse_screener_chart(payload):
    """Screener chart JSON -> (DataFrame with Close and Volume, is_weekly) or (None, False)."""
    price, vol, weekly = None, {}, False
    for ds in (payload or {}).get("datasets", []):
        metric = str(ds.get("metric", "")).lower()
        if metric == "price":
            weekly = bool((ds.get("meta") or {}).get("is_weekly"))
            dates, vals = [], []
            for point in ds.get("values", []):
                try:
                    dates.append(pd.Timestamp(point[0]))
                    vals.append(float(point[1]))
                except (TypeError, ValueError, IndexError):
                    continue
            if vals:
                price = pd.Series(vals, index=dates)
        elif metric == "volume":
            for point in ds.get("values", []):
                try:
                    vol[pd.Timestamp(point[0])] = float(point[1])
                except (TypeError, ValueError, IndexError):
                    continue
    if price is None:
        return None, False
    df = price.to_frame("Close").sort_index()
    if vol:
        df["Volume"] = pd.Series(vol).reindex(df.index)
    return df, weekly


def screener_close_and_ema(company_id, period=200, session=None, pause=1.5):
    """Price from Screener.in's chart for one company. Returns (close, ema or None, date, history) or None."""
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
