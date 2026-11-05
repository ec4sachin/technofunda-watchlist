"""Step 4 - daily close vs 200-day EMA.

Prices come from Yahoo Finance first. Many BSE and SME stocks are missing on Yahoo,
so for those the price history is taken from Screener.in's own price chart instead,
and the 200-day EMA is calculated from it.
"""
import time
from datetime import datetime, timedelta, timezone

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


IST = timezone(timedelta(hours=5, minutes=30))


def _now():
    return datetime.now(IST)


def _drop_unfinished_day(df):
    """During market hours the newest row is today's unfinished candle: SP/DT must use real closes only."""
    if df.empty:
        return df
    now = _now()
    last = pd.Timestamp(df.index[-1])
    if last.date() == now.date() and now.hour * 60 + now.minute < 15 * 60 + 45:
        return df.iloc[:-1]
    return df


# Split / bonus ratios (old price / new price): 2 = 1:1 bonus or 1:2 split, 5 = 1:5 split, 2.5 = 3:2 bonus ...
_FACTORS = sorted({round(p / q, 4) for q in range(1, 6) for p in range(q + 1, 101) if p / q >= 1.6})


def _snap(r1, r2=None, tol=0.03):
    """The simplest split ratio between the open-based and close-based jump (whole numbers first, then halves ...)."""
    lo, hi = min(r1, r2 or r1) * (1 - tol), max(r1, r2 or r1) * (1 + tol)
    mid = (lo * hi) ** 0.5
    for q in range(1, 6):
        hits = [p / q for p in range(q + 1, 101 * q) if lo <= p / q <= hi and p / q >= 1.6]
        if hits:
            return round(min(hits, key=lambda f: abs(f - mid)), 4)
    return None


def adjust_corporate_actions(df):
    """Fix prices that were not adjusted for a split / bonus (one big overnight jump that matches a split ratio:
    all older prices are divided by that ratio) and single bad price days (a jump that comes straight back).
    Returns (df, notes)."""
    df = df.copy()
    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col in df:
            df[col] = df[col].astype(float)   # whole-number volumes would break the split correction
    has_o = "Open" in df and df["Open"].notna().any()
    notes = []
    c = df["Close"].to_numpy(dtype=float).copy()
    i = 1
    while i < len(df):
        prev, cur = c[i - 1], c[i]
        if not (prev > 0 and cur > 0) or 1 / 1.6 < cur / prev < 1.6:
            i += 1
            continue
        # one bad day: the next close is back near the old price
        if i + 1 < len(df) and c[i + 1] > 0 and abs(c[i + 1] / prev - 1) < 0.25:
            for col in ("Open", "High", "Low", "Close"):
                if col in df:
                    df.iloc[i, df.columns.get_loc(col)] = prev
            c[i] = prev
            notes.append(f"{df.index[i]}: bad price day ignored")
            i += 1
            continue
        o = float(df["Open"].iloc[i]) if has_o and pd.notna(df["Open"].iloc[i]) and df["Open"].iloc[i] > 0 else cur
        f = _snap(prev / o, prev / cur) if prev > o and prev > cur else None
        g = _snap(o / prev, cur / prev) if o > prev and cur > prev else None
        if f:      # split / bonus: older prices divided by f
            for col in ("Open", "High", "Low", "Close"):
                if col in df:
                    df.iloc[:i, df.columns.get_loc(col)] = df.iloc[:i, df.columns.get_loc(col)] / f
            if "Volume" in df:
                df.iloc[:i, df.columns.get_loc("Volume")] = df.iloc[:i, df.columns.get_loc("Volume")] * f
            c[:i] = c[:i] / f
            notes.append(f"{df.index[i]}: split/bonus 1:{f:g} adjusted")
        elif g:    # share consolidation (reverse split): older prices multiplied
            for col in ("Open", "High", "Low", "Close"):
                if col in df:
                    df.iloc[:i, df.columns.get_loc(col)] = df.iloc[:i, df.columns.get_loc(col)] * g
            if "Volume" in df:
                df.iloc[:i, df.columns.get_loc("Volume")] = df.iloc[:i, df.columns.get_loc("Volume")] / g
            c[:i] = c[:i] * g
            notes.append(f"{df.index[i]}: consolidation {g:g}:1 adjusted")
        i += 1
    return df, notes


def _ema_result(df, period):
    """(last close, EMA, date, chart history). df has a Close column (Open/High/Low/Volume optional).

    EMA is None with fewer than `period` trading days (new listing).
    """
    if isinstance(df, pd.Series):
        df = df.to_frame("Close")
    df = df[df["Close"].notna()]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = _drop_unfinished_day(df)
    if df.empty:
        return None
    df, _ = adjust_corporate_actions(df)
    if df.empty:
        return None
    close = df["Close"].astype(float)
    last = (round(float(close.iloc[-1]), 2), pd.Timestamp(close.index[-1]).strftime("%d %b %Y"))
    hist = _payload(df)
    if len(close) < period:
        return (last[0], None, last[1], hist)
    ema = close.ewm(span=period, adjust=True).mean()
    return (last[0], round(float(ema.iloc[-1]), 2), last[1], hist)


def join_older(df_new, df_old):
    """Put the older part of a second price history (e.g. BSE, before the stock moved to NSE) in front of df_new.
    The older prices are scaled so both join smoothly on the first common day."""
    if df_old is None or df_old.empty or df_new is None or df_new.empty:
        return df_new
    first = df_new.index[0]
    older = df_old[df_old.index < first]
    if len(older) < 20:
        return df_new
    common = df_old.index.intersection(df_new.index)
    f = 1.0
    if len(common):
        a, b = float(df_new.loc[common[0], "Close"]), float(df_old.loc[common[0], "Close"])
        if a > 0 and b > 0:
            f = a / b
    older = older.copy()
    for col in ("Open", "High", "Low", "Close"):
        if col in older:
            older[col] = older[col] * f
    return pd.concat([older[[c for c in df_new.columns if c in older]], df_new])


def close_and_ema(tickers, period=200, older=None, span="max"):
    """Yahoo Finance, whole history. Returns {ticker: (close, ema, date, history) or None}.
    older: {nse_ticker: bse_ticker} - the BSE history is joined in front when it goes back further
    (stocks that moved from BSE to NSE, or SME stocks that moved to the main board)."""
    out = {t: None for t in tickers}
    if not tickers:
        return out
    extra = sorted({b for t, b in (older or {}).items() if t in tickers and b not in tickers})
    data = yf.download(sorted(set(tickers) | set(extra)), period=span, interval="1d", auto_adjust=False,
                       group_by="ticker", progress=False, threads=True)
    cols = ("Open", "High", "Low", "Close", "Volume")

    def frame(t):
        df = data[t] if isinstance(data.columns, pd.MultiIndex) else data
        df = df[[c for c in cols if c in df]]
        return df[df["Close"].notna()] if "Close" in df else None

    for t in tickers:
        try:
            df = frame(t)
            if df is None or df.empty:
                continue
            b = (older or {}).get(t)
            if b:
                try:
                    df = join_older(df, frame(b))
                except (KeyError, TypeError):
                    pass
            out[t] = _ema_result(df, period)
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
