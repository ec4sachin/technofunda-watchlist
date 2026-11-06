"""Backtest the strategies on your own stock list (for example a Screener.in export of
"Sales growth 5Years > 20 AND Profit growth 5Years > 25").

Put the file in data/universe/ (CSV or Excel). The robot reads the NSE code / BSE code columns
(or the company name links) and downloads the whole price history of every stock from Yahoo.
Stocks Yahoo does not have (mostly BSE-only companies) get about 2 years of closing prices from Screener
(saved once in data/universe_px/) and real daily candles from BSE's daily price file (one small file per day
in data/bse_days/, only the rows of your list). The same list can be paper-traded live ("Growth list").
Results go to data/universe_backtest.json and the Strategy tab of the dashboard.
The backtest is run again when the file changes, and otherwise once a week.

Note: a list made with TODAY's 5-year growth numbers already "knows" which companies grew,
so a backtest on past years is more optimistic than real trading would have been.
"""
import csv
import glob
import hashlib
import io
import os
import re
import time
from datetime import datetime, timedelta

import pandas as pd

import bhav
import prices
import storage
import strategy

FOLDER = "universe"
OUT = "universe_backtest.json"
CODE_COLS = {"nse": ("nse code", "nse symbol", "nse", "symbol", "nse_code"),
             "bse": ("bse code", "bse", "bse_code", "scrip code", "security code")}
NAME_COLS = ("name", "company", "company name", "stock")
VERSION = "7"             # change to run the backtest again with new rules
PCT_TEST = (6, 7, 8, 9, 10, 11, 12, 13, 14, 15)
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


# ------------------------------------------------------------------ prices
PX_DIR, DAY_DIR = "universe_px", "bse_days"
BSE_DAYS_BACK = 600          # calendar days of BSE daily files kept (about 400 trading days)
MAX_BSE_FILES_PER_RUN = 200  # the first fill takes about 2-3 runs, then 1 file a day
MAX_SCREENER_PER_RUN = 120   # the first fill takes about 4 runs (each stock once)


def symbols():
    """Symbols of the list (no Screener lookups) - cheap."""
    try:
        return {s for s, _, _, _ in load_list(resolve=False)}
    except Exception:
        return set()


def _yahoo(stocks, span):
    """{symbol: chart} from Yahoo: batches of 80, then the misses again in batches of 20 (Yahoo often drops some)."""
    tick = {s: (f"{nse}.NS" if nse else f"{bse}.BO") for s, _, nse, bse in stocks}
    older = {f"{nse}.NS": f"{bse}.BO" for s, _, nse, bse in stocks if nse and bse} if span == "max" else {}
    charts = {}
    todo = sorted(set(tick.values()))
    for size in (80, 20):
        got = set()
        for k in range(0, len(todo), size):
            part = todo[k:k + size]
            try:
                px = prices.close_and_ema(part, 200, older={t: older[t] for t in part if t in older}, span=span)
            except Exception as e:
                print("Yahoo batch failed:", e)
                px = {}
            for t in part:
                res = px.get(t)
                if res and len(res) > 3 and res[3] and res[3].get("t"):
                    got.add(t)
                    for s_ in [s_ for s_, tt in tick.items() if tt == t]:
                        charts[s_] = res[3]
        todo = [t for t in todo if t not in got]
        if not todo:
            break
    return charts


def _company_id(code, session):
    import fundamentals as fx
    if storage.screener_blocked():
        return None
    try:
        r = session.get(f"https://www.screener.in/company/{code}/", headers={"User-Agent": prices.HEADERS["User-Agent"]}, timeout=30)
        storage.screener_answer(r.status_code)
        if r.status_code == 404:
            return ""             # Screener has no page for this code
        if r.status_code != 200:
            if r.status_code == 429:
                time.sleep(20)
            return None           # blocked / server problem: ask again on a later run
        m = fx.COMPANY_ID_RE.search(r.text)
        return (m.group(1) or m.group(2)) if m else None
    except Exception:
        return None


def _screener_closes(codes, session, limit=MAX_SCREENER_PER_RUN):
    """Closing prices from Screener for BSE-only stocks, saved once in data/universe_px/CODE.csv."""
    folder = os.path.join(storage.DATA, PX_DIR)
    os.makedirs(folder, exist_ok=True)
    ids = storage.load_json("universe_ids.json", {})
    got = storage.load_json("universe_px_dates.json", {})
    old = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    path = lambda c: os.path.join(folder, f"{c}.csv")

    def saved(code):
        if not os.path.exists(path(code)):
            return None
        with open(path(code), newline="", encoding="utf-8") as f:
            return {r["date"]: float(r["close"]) for r in csv.DictReader(f) if r.get("close")}

    for code in codes:  # saved before the dates were kept
        if os.path.exists(path(code)) and code not in got:
            got[code] = today
    # stocks never fetched first, then the oldest (refreshed monthly, so a new split / bonus is picked up)
    order = sorted(codes, key=lambda c: (os.path.exists(path(c)), got.get(c, "")))
    out, asked = {}, 0
    for code in order:
        p = path(code)
        if os.path.exists(p) and (got.get(code, "") >= old or asked >= limit):
            out[code] = saved(code)
            continue
        if asked >= limit or ids.get(code) == "" or storage.screener_blocked():
            continue  # later run / not on Screener / Screener blocking us today
        asked += 1
        cid = ids.get(code) or _company_id(code, session)
        time.sleep(1.0)
        res = None
        if cid:
            ids[code] = cid
            res = prices.screener_close_and_ema(cid, 200, session=session)
        elif cid == "":
            ids[code] = ""
        hist = res[3] if res and len(res) > 3 else None
        if not hist or not hist.get("t"):
            if os.path.exists(p):  # keep the saved prices
                out[code] = saved(code)
            continue
        rows = {d: c for d, c in zip(hist["t"], hist["c"]) if c}
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "close"])
            for d in sorted(rows):
                w.writerow([d, rows[d]])
        out[code] = rows
        got[code] = datetime.now().strftime("%Y-%m-%d")
    storage.save_json("universe_ids.json", ids)
    storage.save_json("universe_px_dates.json", got)
    return out


def _save_day(folder, ds, rows, want, keep=None):
    """Write one day file with the rows of `want` (plus rows already saved for other codes in `keep`)."""
    with open(os.path.join(folder, f"{ds}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code", "open", "high", "low", "close", "volume"])
        done = set()
        for r in rows:
            if r["code"] in want and r["code"] not in done:
                done.add(r["code"])
                w.writerow([r["code"], round(r["open"], 2), round(r["high"], 2), round(r["low"], 2), round(r["close"], 2), r["volume"]])
        for code, row in (keep or {}).items():
            if code not in done:
                w.writerow([code, *row])


def _bse_days(codes, session, today=None, limit=MAX_BSE_FILES_PER_RUN, exchange=None):
    """BSE daily price files -> data/bse_days/YYYY-MM-DD.csv with only the rows of `codes`.
    Codes added to the list later get the days already saved filled in too (a few hundred files per run).
    Returns {code: {date: (o, h, l, c, v)}}."""
    folder = os.path.join(storage.DATA, DAY_DIR)
    os.makedirs(folder, exist_ok=True)
    pt = os.path.join(folder, "no_file.txt")
    no_file = set(open(pt).read().split()) if os.path.exists(pt) else set()
    files = {os.path.basename(f)[:10] for f in glob.glob(os.path.join(folder, "????-??-??.csv"))}
    ex = exchange or bhav.Exchange("BSE", bhav.BSE_URLS, session)
    now = today or datetime.now(prices.IST).replace(tzinfo=None)
    want = set(codes)
    # which codes the saved day files cover. Files saved before this note existed: the codes found in them.
    cov_name = os.path.join(DAY_DIR, "covered.json")
    cov = storage.load_json(cov_name, None)
    if not isinstance(cov, dict):
        found = set()
        for f in glob.glob(os.path.join(folder, "????-??-??.csv")):
            with open(f, newline="", encoding="utf-8") as fh:
                found |= {r["code"] for r in csv.DictReader(fh)}
        cov = {"codes": sorted(found), "refill": {}}
    covered = set(cov.get("codes", []))
    refill = cov.get("refill") or {}
    if not files:
        covered, refill = set(want), {}          # nothing saved yet: every new file has all codes
    new_codes = want - covered - set(refill.get("codes", []))
    if new_codes:   # codes that joined the list: the days already saved get their rows too
        refill = {"codes": sorted(set(refill.get("codes", [])) | new_codes), "done": []}
    tried, new_missing = 0, []
    for k in range(BSE_DAYS_BACK):
        d = now - timedelta(days=k)
        ds = d.strftime("%Y-%m-%d")
        if d.weekday() >= 5 or ds in files or (ds in no_file and k > 5):
            continue
        if tried >= limit or ex.fails >= 4 or storage.out_of_time():
            break
        if k == 0 and (now.hour * 60 + now.minute) < 18 * 60:
            continue  # today's file comes out in the evening (India time)
        tried += 1
        rows = ex.day(d)
        if not rows:
            if getattr(ex, "last", "missing") == "missing":
                new_missing.append(ds)   # the exchange says there is no file: holiday
            continue
        _save_day(folder, ds, rows, want)
        files.add(ds)
        if refill:
            refill.setdefault("done", []).append(ds)   # a new file already has every code
    # fill in older saved days for codes that joined the list later
    if refill.get("codes"):
        add, done = set(refill["codes"]), set(refill.get("done", []))
        for ds in sorted(files - done, reverse=True):
            if tried >= limit or ex.fails >= 4 or storage.out_of_time():
                break
            tried += 1
            rows = ex.day(datetime.strptime(ds, "%Y-%m-%d"))
            if rows is None and getattr(ex, "last", "") == "error":
                continue
            keep = {}
            with open(os.path.join(folder, f"{ds}.csv"), newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    keep[r["code"]] = [r["open"], r["high"], r["low"], r["close"], r["volume"]]
            _save_day(folder, ds, rows or [], add, keep)
            done.add(ds)
        if files <= done:
            covered |= add
            refill = {}
        else:
            refill["done"] = sorted(done)
    if new_missing:
        with open(pt, "w") as f:
            f.write("\n".join(sorted(no_file | set(new_missing))))
    cut = (now - timedelta(days=BSE_DAYS_BACK + 30)).strftime("%Y-%m-%d")
    out = {}
    for f in sorted(glob.glob(os.path.join(folder, "????-??-??.csv"))):
        ds = os.path.basename(f)[:10]
        if ds < cut:
            os.remove(f)  # older than needed
            continue
        with open(f, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["code"] in want:
                    try:
                        out.setdefault(r["code"], {})[ds] = (float(r["open"]), float(r["high"]), float(r["low"]),
                                                             float(r["close"]), int(float(r["volume"] or 0)))
                    except ValueError:
                        continue
    storage.save_json(cov_name, {"codes": sorted(covered), "refill": refill})
    return out


def _ratio(r, tol=0.03):
    """Nearest simple ratio p/q (q up to 5) to r, e.g. 1.5 for a 1:2 bonus, else r itself."""
    best = min(((p / q, abs(p / q - r) / r) for q in range(1, 6) for p in range(q + 1, 100 * q + 1)), key=lambda x: x[1])
    return best[0] if best[1] <= tol else r


def _raw_adjust(rows, known=None):
    """rows: list of [o, h, l, c, v] in date order (o is NaN for close-only days). Small BSE stocks have price
    bands of 20% or less: a 20% fall is a ratio of 1.25 (100 -> 80), a 20% rise 1.20. So an overnight gap
    beyond the band - a fall of more than 22% (ratio over 1.28) or a rise of more than 24% - at the open AND
    the close of a real candle is a split / bonus: all older rows (close-only ones too) are divided by that
    ratio. Changes rows in place.
    known[k] True = Screener's adjusted close exists for that day: a gap between two such days is real (Screener
    already shows any split there), so it is never treated as a split."""
    for k in range(1, len(rows)):
        if known and known[k] and known[k - 1]:
            continue
        prev, cur = rows[k - 1], rows[k]
        if not (prev[3] > 0) or not (cur[0] > 0) or not (cur[3] > 0):
            continue   # (NaN compares False: close-only day)
        ro, rc = prev[3] / cur[0], prev[3] / cur[3]
        for up in (False, True):
            a, b = (1 / ro, 1 / rc) if up else (ro, rc)
            lim = 1.24 if up else 1.28
            if a > lim and b > lim and abs(a / b - 1) < 0.08:
                f = _ratio((a * b) ** 0.5)
                f = 1 / f if up else f
                for r in rows[:k]:
                    r[0], r[1], r[2], r[3] = r[0] / f, r[1] / f, r[2] / f, r[3] / f
                    r[4] = r[4] * f
                break
    return rows


def bse_chart(closes, days):
    """Screener closes (older part, close only) + BSE daily candles (real) -> chart history like Yahoo's.
    1) BSE files have raw prices, Screener's closes are adjusted for splits / bonuses: on days with both, the
       raw candle is scaled to Screener's close (before Screener's first day its first factor is used, after
       its last day the last factor).
    2) Then a split / bonus that Screener does not cover yet (before or after its days) is found from the
       overnight gap and all older prices are divided by it."""
    dates = sorted(set(closes) | set(days))
    if not dates:
        return None
    nan = float("nan")
    both = [d for d in dates if d in days and d in closes and days[d][3] > 0 and closes[d] > 0]
    f = closes[both[0]] / days[both[0]][3] if both else 1.0
    rows = []
    for d in dates:
        if d in days:
            o, h, l, c, v = days[d]
            if d in closes and c > 0 and closes[d] > 0:
                f = closes[d] / c
            rows.append([o * f, h * f, l * f, c * f, v / f if f else v])
        else:
            rows.append([nan, nan, nan, closes[d], nan])
    _raw_adjust(rows, [d in closes for d in dates])
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=pd.to_datetime(dates), dtype=float)
    res = prices._ema_result(df, 200)
    return res[3] if res else None


def get_charts(stocks, span="max", session=None, today=None):
    """{symbol: chart history} for the list: Yahoo first, then Screener + BSE files for the rest. Returns (charts, missing)."""
    import requests
    s = session or requests.Session()
    # stocks Yahoo does not have: asked again only on the full (weekly backtest) run
    no_yahoo = set(storage.load_json("universe_no_yahoo.json", []))
    ask = stocks if span == "max" else [x for x in stocks if x[0] not in no_yahoo]
    charts = _yahoo(ask, span)
    if span == "max":
        storage.save_json("universe_no_yahoo.json", sorted(x[0] for x in stocks if x[0] not in charts and not x[2]))  # BSE-only codes
    rest = [(sym, bse) for sym, _, nse, bse in stocks if sym not in charts and bse]
    if rest:
        codes = [b for _, b in rest]
        try:
            days = _bse_days(codes, s, today=today)
        except Exception as e:
            print("BSE daily files failed:", e)
            days = {}
        by_day = {}
        for code, rows in days.items():
            by_day[code] = rows
        closes = _screener_closes(codes, s)
        for sym, code in rest:
            h = bse_chart(closes.get(code, {}), by_day.get(code, {}))
            if h and len(h["t"]) > 30:
                charts[sym] = h
    missing = [sym for sym, _, _, _ in stocks if sym not in charts]
    return charts, missing


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


def run(settings, mood, today, now_year, stocks=None, charts=None, missing=None):
    """Download prices for the list (unless given) and backtest every trading strategy on it."""
    stocks = stocks if stocks is not None else load_list()
    if not stocks:
        return None
    if charts is None:
        charts, missing = get_charts(stocks)
    missing = missing or []
    names = {s: n for s, n, _, _ in stocks}
    syms = sorted(charts)
    d2 = f"{int(today[:4]) - 2}{today[4:]}"
    out = {"as_of": today, "signature": _signature(), "stocks": len(stocks), "with_prices": len(syms),
           "from_bse_files": sum(1 for s, _, nse, bse in stocks if s in charts and not nse and bse and "o" in charts[s]
                                 and charts[s]["o"] and charts[s]["o"][0] is None),
           "missing": missing[:300], "strategies": {}, "rank_names": strategy.RANKS}
    for st in settings.get("strategies", []):
        if st.get("type") not in strategy.TRADING_TYPES:
            continue
        cap, pct = float(st.get("capital", strategy.DEF_CAPITAL)), float(st.get("pct", strategy.DEF_PCT))
        trades = strategy.backtest(st, charts, names, syms, mood=mood)
        start = min((h["t"][0] for h in charts.values() if h.get("t")), default=today)
        first_year = max(int(start[:4]) + 1, now_year - 9)
        # the same strategy without its liquidity filter, to see what the filter changes
        nofilter = None
        if st.get("min_turnover") or st.get("min_price"):
            raw = strategy.backtest(dict(st, min_turnover=0, min_price=0), charts, names, syms, mood=mood)
            nofilter = _rank_row(raw, f"{first_year}-01-01", d2, cap, pct, st.get("rank") or strategy.RANK, first_year, now_year)
        out["strategies"][st["id"]] = {
            "name": st.get("name"), "pct": pct,
            "last2y": {k: v for k, v in strategy.portfolio(trades, d2, capital=cap, pct=pct, rank=st.get("rank")).items() if k != "trades_list"},
            "since": f"{first_year}-01-01",
            "period": {k: v for k, v in strategy.portfolio(trades, f"{first_year}-01-01", capital=cap, pct=pct, rank=st.get("rank")).items()
                       if k != "trades_list"},
            "by_year": {str(y): {k: v for k, v in strategy.portfolio(trades, f"{y}-01-01", f"{y + 1}-01-01", capital=cap, pct=pct, rank=st.get("rank")).items()
                                 if k in ("return_pct", "trades", "win_rate", "max_drawdown_pct", "skipped")}
                        for y in range(first_year, now_year + 1)},
            "report": {k: v for k, v in strategy.report(trades).items() if k not in ("curve", "months")},
            "rank": st.get("rank") or strategy.RANK,
            "nofilter": nofilter,
            "filter": {"min_turnover": st.get("min_turnover"), "min_price": st.get("min_price")} if nofilter else None,
            # when money is short: which of the same-day buy signals to take first
            "rank_test": {rk: _rank_row(trades, f"{first_year}-01-01", d2, cap, pct, rk, first_year, now_year)
                          for rk in strategy.RANKS},
            # smaller or bigger % per trade (with the strategy's own choice of which signal first)
            "pct_test": {str(pc): _rank_row(trades, f"{first_year}-01-01", d2, cap, pc, st.get("rank") or strategy.RANK, first_year, now_year)
                         for pc in PCT_TEST},
        }
    out["stocks_with_history"] = {str(y): sum(1 for h in charts.values() if h.get("t") and h["t"][0] <= f"{y - 1}-02-01")
                                  for y in range(now_year - 9, now_year + 1)}
    storage.save_json(OUT, out)
    return out
