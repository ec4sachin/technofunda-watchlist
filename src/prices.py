"""Step 4 - daily close vs 200-day EMA (data from Yahoo Finance)."""
import pandas as pd
import yfinance as yf


def yahoo_ticker(code, override=""):
    if override:
        return override
    return f"{code}.BO" if str(code).isdigit() else f"{code}.NS"


def close_and_ema(tickers, period=200):
    """tickers: list of Yahoo tickers. Returns {ticker: (close, ema, date) or None}."""
    out = {t: None for t in tickers}
    if not tickers:
        return out
    data = yf.download(tickers, period="2y", interval="1d", auto_adjust=False,
                       group_by="ticker", progress=False, threads=True)
    for t in tickers:
        try:
            df = data[t] if isinstance(data.columns, pd.MultiIndex) else data
            close = df["Close"].dropna()
        except (KeyError, TypeError):
            continue
        if len(close) < period:
            continue  # not enough history for a 200-day EMA
        ema = close.ewm(span=period, adjust=False).mean()
        out[t] = (round(float(close.iloc[-1]), 2), round(float(ema.iloc[-1]), 2),
                  close.index[-1].strftime("%d %b %Y"))
    return out
