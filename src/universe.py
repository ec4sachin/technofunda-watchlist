"""Backtest the strategies on your own stock list (for example a Screener.in export of
"Sales growth 5Years > 20 AND Profit growth 5Years > 25").

Put the file in data/universe/ (CSV or Excel). The robot reads the NSE code / BSE code columns
(or the company name links) and downloads the whole price history of every stock from Yahoo.
Results go to data/universe_backtest.json and the Strategy tab of the dashboard.
The backtest is run again when the file changes, and otherwise once a week.

Note: a list made with TODAY's 5-year growth numbers already "knows" which companies grew,
so a backtest on past years is more optimistic than real trading would have been.
"""
import csv
import hashlib
import io
import os
import re
from datetime import datetime

import pandas as pd

import prices
import storage
import strategy

FOLDER = "universe"
OUT = "universe_backtest.json"
CODE_COLS = {"nse": ("nse code", "nse symbol", "nse", "symbol", "nse_code"),
             "bse": ("bse code", "bse", "bse_code", "scrip code", "security code")}
NAME_COLS = ("name", "company", "company name", "stock")
VERSION = "2"             # change to run the backtest again with new rules
MAX_MCAP_CR = 25000        # only companies below ₹25,000 crore market cap (when the file has a market-cap column)


def _files():
    folder = os.path.join(storage.DATA, FOLDER)
    if not os.path.isdir(folder):
        return []
    return sorted(os.path.join(folder, f) for f in os.listdir(folder)
                  if f.lower().endswith((".csv", ".xlsx", ".xls")) and not f.startswith("~"))


def _frames(path):
    if path.lower().endswith(".csv"):
        raw = open(path, "rb").read().decode("utf-8-sig", "replace")
        # Screener exports sometimes have a few title lines before the table
        lines = raw.splitlines()
        start = next((k for k, ln in enumerate(lines[:30]) if re.search(r"(?i)\bname\b|nse|bse", ln)), 0)
        return [pd.read_csv(io.StringIO("\n".join(lines[start:])), dtype=str)]
    out = []
    links = _excel_links(path)
    for _, df in pd.read_excel(path, sheet_name=None, dtype=str, header=None).items():
        df = df.dropna(how="all")
        if df.empty:
            continue
        head = next((k for k in range(min(30, len(df)))
                     if any(re.search(r"(?i)^(s\.?no\.?|name|nse|bse)", str(v or "")) for v in df.iloc[k])), 0)
        df.columns = [str(c).strip() for c in df.iloc[head]]
        body = df.iloc[head + 1:].copy()
        # Screener puts a link to the company page on each name: /company/CODE/
        body["_link"] = [next((links[str(v).strip()] for v in row if str(v).strip() in links), "")
                         for row in body.itertuples(index=False)] if links else ""
        out.append(body)
    return out


def _excel_links(path):
    """{cell text: hyperlink} from an Excel file (Screener links each company name to its page)."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=False, data_only=True)
    except Exception:
        return {}
    found = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.hyperlink is not None and c.value:
                    found[str(c.value).strip()] = c.hyperlink.target or ""
    return found


def resolve_names(names, session=None, pause=1.0):
    """Company names -> Screener codes, using Screener's own search. {name: code}"""
    import time
    import requests
    s = session or requests.Session()
    out = {}
    for n in names:
        try:
            r = s.get("https://www.screener.in/api/company/search/", params={"q": n, "v": 3},
                      headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=20)
            hits = r.json() if r.status_code == 200 else []
        except Exception:
            hits = []
        time.sleep(pause)
        for h in hits or []:
            m = re.search(r"/company/([A-Za-z0-9&\-]+)/", str(h.get("url", "")))
            if m:
                out[n] = m.group(1).upper()
                break
    return out


def load_list(resolve=True):
    """[(symbol, name, nse, bse)] from the files in data/universe/ (duplicates removed).
    Rows with only a company name are looked up on Screener (resolve=True)."""
    seen, out, unknown = set(), [], []
    for path in _files():
        try:
            frames = _frames(path)
        except Exception as e:
            print(f"Could not read {path}: {e}")
            continue
        for df in frames:
            cols = {str(c).strip().lower(): c for c in df.columns}
            pick = lambda names: next((cols[n] for n in names if n in cols), None)
            c_nse, c_bse, c_name = pick(CODE_COLS["nse"]), pick(CODE_COLS["bse"]), pick(NAME_COLS)
            c_mcap = next((cols[k] for k in cols if re.search(r"mar(ket)?\.?\s*cap", k)), None)
            for _, r in df.iterrows():
                if c_mcap is not None and MAX_MCAP_CR:
                    try:
                        if float(str(r[c_mcap]).replace(",", "")) > MAX_MCAP_CR:
                            continue  # too big
                    except (TypeError, ValueError):
                        pass
                link = str(r.get("_link") or "") if "_link" in df else ""
                nse = str(r[c_nse]).strip().upper() if c_nse is not None and pd.notna(r[c_nse]) else ""
                bse = str(r[c_bse]).strip() if c_bse is not None and pd.notna(r[c_bse]) else ""
                bse = bse[:-2] if bse.endswith(".0") else bse
                name = str(r[c_name]).strip() if c_name is not None and pd.notna(r[c_name]) else ""
                nse = "" if nse in ("NAN", "NONE", "-") else nse
                bse = bse if re.fullmatch(r"\d{6}", bse) else ""
                if not nse and not bse and (link or name):
                    m = re.search(r"/company/([A-Za-z0-9&\-]+)/", link or name)  # a Screener link
                    if m:
                        code = m.group(1).upper()
                        nse, bse = ("", code) if code.isdigit() else (code, "")
                sym = nse or bse
                if not sym and name and name.lower() not in ("nan", "median", "total"):
                    unknown.append(name)
                    continue
                if not sym or sym in seen or not re.fullmatch(r"[A-Z0-9&\-]{1,20}", sym):
                    continue
                seen.add(sym)
                out.append((sym, name or sym, nse, bse))
    if unknown and resolve:
        cache = storage.load_json("universe_codes.json", {})
        todo = [n for n in dict.fromkeys(unknown) if n not in cache][:400]
        if todo:
            cache.update(resolve_names(todo))
            storage.save_json("universe_codes.json", cache)
        for n in dict.fromkeys(unknown):
            code = cache.get(n)
            if code and code not in seen:
                seen.add(code)
                out.append((code, n, "" if code.isdigit() else code, code if code.isdigit() else ""))
    return out


def _signature():
    h = hashlib.sha1(VERSION.encode())
    for p in _files():
        h.update(open(p, "rb").read())
    return h.hexdigest()[:16]


def due(today):
    """Run when the list changed, or the last run is a week old."""
    if not _files():
        return False
    old = storage.load_json(OUT, {})
    if old.get("signature") != _signature():
        return True
    try:
        return (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(old.get("as_of", "2000-01-01"), "%Y-%m-%d")).days >= 7
    except ValueError:
        return True


def _rank_row(trades, since, d2, cap, pct, rk, first_year, now_year):
    p = strategy.portfolio(trades, since, capital=cap, pct=pct, rank=rk)
    l2 = strategy.portfolio(trades, d2, capital=cap, pct=pct, rank=rk)
    yrs = [strategy.portfolio(trades, f"{y}-01-01", f"{y + 1}-01-01", capital=cap, pct=pct, rank=rk)["return_pct"]
           for y in range(first_year, now_year + 1)]
    return {"return_pct": p["return_pct"], "final": p["final"], "capital": cap, "max_drawdown_pct": p["max_drawdown_pct"],
            "trades": p["trades"], "skipped": p["skipped"], "win_rate": p["win_rate"],
            "last2y": l2["return_pct"], "last2y_dd": l2["max_drawdown_pct"],
            "loss_years": sum(1 for r in yrs if r < 0), "worst_year": min(yrs) if yrs else None}


def run(settings, mood, today, now_year):
    """Download prices for the list and backtest every trading strategy on it."""
    stocks = load_list()
    if not stocks:
        return None
    tick = {s: (f"{nse}.NS" if nse else f"{bse}.BO") for s, _, nse, bse in stocks}
    older = {f"{nse}.NS": f"{bse}.BO" for s, _, nse, bse in stocks if nse and bse}
    charts, missing = {}, []
    tickers = sorted(set(tick.values()))
    for k in range(0, len(tickers), 80):  # Yahoo in batches
        part = tickers[k:k + 80]
        try:
            px = prices.close_and_ema(part, 200, older={t: older[t] for t in part if t in older})
        except Exception as e:
            print("Yahoo batch failed:", e)
            px = {}
        for s, t in tick.items():
            if t in part:
                res = px.get(t)
                if res and len(res) > 3 and res[3]:
                    charts[s] = res[3]
                elif t in part:
                    missing.append(s)
    names = {s: n for s, n, _, _ in stocks}
    syms = sorted(charts)
    d2 = f"{int(today[:4]) - 2}{today[4:]}"
    out = {"as_of": today, "signature": _signature(), "stocks": len(stocks), "with_prices": len(syms),
           "missing": missing[:300], "strategies": {}, "rank_names": strategy.RANKS}
    for st in settings.get("strategies", []):
        if st.get("type") not in strategy.TRADING_TYPES:
            continue
        cap, pct = float(st.get("capital", strategy.DEF_CAPITAL)), float(st.get("pct", strategy.DEF_PCT))
        trades = strategy.backtest(st, charts, names, syms, mood=mood)
        start = min((h["t"][0] for h in charts.values() if h.get("t")), default=today)
        first_year = max(int(start[:4]) + 1, now_year - 9)
        out["strategies"][st["id"]] = {
            "name": st.get("name"), "pct": pct,
            "last2y": {k: v for k, v in strategy.portfolio(trades, d2, capital=cap, pct=pct).items() if k != "trades_list"},
            "since": f"{first_year}-01-01",
            "period": {k: v for k, v in strategy.portfolio(trades, f"{first_year}-01-01", capital=cap, pct=pct).items()
                       if k != "trades_list"},
            "by_year": {str(y): {k: v for k, v in strategy.portfolio(trades, f"{y}-01-01", f"{y + 1}-01-01", capital=cap, pct=pct).items()
                                 if k in ("return_pct", "trades", "win_rate", "max_drawdown_pct", "skipped")}
                        for y in range(first_year, now_year + 1)},
            "report": {k: v for k, v in strategy.report(trades).items() if k not in ("curve", "months")},
            "rank": st.get("rank") or strategy.RANK,
            # when money is short: which of the same-day buy signals to take first
            "rank_test": {rk: _rank_row(trades, f"{first_year}-01-01", d2, cap, pct, rk, first_year, now_year)
                          for rk in strategy.RANKS},
        }
    out["stocks_with_history"] = {str(y): sum(1 for h in charts.values() if h.get("t") and h["t"][0] <= f"{y - 1}-02-01")
                                  for y in range(now_year - 9, now_year + 1)}
    storage.save_json(OUT, out)
    return out
