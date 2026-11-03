"""Steps 2 & 5 - read fundamentals from Screener.in and score them with your marks system (rules.yaml)."""
import math
import re
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://www.screener.in"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}

TOP_RATIO_NAMES = {
    "market cap": "market_cap", "current price": "price", "stock p/e": "pe",
    "book value": "book_value", "dividend yield": "dividend_yield",
    "roce": "roce", "roe": "roe", "face value": "face_value",
}
RANGE_TITLES = {
    "compounded sales growth": "sales_growth", "compounded profit growth": "profit_growth",
    "stock price cagr": "stock_cagr", "return on equity": "roe",
}
RANGE_PERIODS = {"10 years": "10y", "5 years": "5y", "3 years": "3y", "1 year": "1y",
                 "ttm": "ttm", "last year": "last_year"}


# Screener's internal company id (used for its price chart), e.g. /company/source/quarter/1285561/6/2024/
COMPANY_ID_RE = re.compile(r'data-company-id="(\d+)"|/(?:company/source/quarter|ai/company|api/company)/(\d+)/')

# The numbers the marks system needs - used to pick the more complete page (consolidated / standalone)
SCORE_INPUTS = ("sales_growth_qtr_yoy", "sales_growth_ttm", "eps_latest_qtr", "eps_prev_qtr", "opm_latest_qtr",
                "opm_same_qtr_last_year", "fixed_assets_latest", "debtor_days", "fii_dii_latest", "shareholders_latest")


def completeness(m):
    return sum(1 for k in SCORE_INPUTS if m.get(k) is not None)


# ---------------------------------------------------------------- helpers
def _num(text):
    if text is None:
        return None
    t = text.replace(",", "").replace("\xa0", " ")
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    return float(m.group()) if m else None


def _label(text):
    t = (text or "").replace("\xa0", " ").replace("+", " ")
    return re.sub(r"\s+", " ", t).strip().lower()


def _table(soup, section_id):
    sec = soup.find(id=section_id)
    if not sec:
        return [], {}
    table = sec.select_one("table.data-table") or sec.find("table")
    if not table:
        return [], {}
    head = [th.get_text(" ", strip=True) for th in table.select("thead th")][1:]
    rows = {}
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        rows[_label(tds[0].get_text(" ", strip=True))] = [_num(td.get_text(" ", strip=True)) for td in tds[1:]]
    return head, rows


def _row(rows, *names):
    for n in names:
        if n in rows:
            return rows[n]
    for n in names:
        for k, v in rows.items():
            if k.startswith(n):
                return v
    return None


def _last(values, skip_from_end=0):
    if not values:
        return None
    vals = values[: len(values) - skip_from_end] if skip_from_end else values
    for v in reversed(vals):
        if v is not None:
            return v
    return None


def _pct(new, old):
    if new is None or old is None or old <= 0:
        return None
    return round((new - old) / old * 100, 2)


# ---------------------------------------------------------------- parsing
def parse_company_page(html):
    soup = BeautifulSoup(html, "lxml")
    m = {}
    h1 = soup.find("h1")
    m["_name"] = h1.get_text(" ", strip=True) if h1 else None
    # Exchange codes from the BSE / NSE links at the top of the page
    bse = re.search(r"bseindia\.com/stock-share-price/[^\"']*?/(\d{6})/?[\"']", html)
    nse = re.search(r"nseindia\.com/get-quotes/equity\?symbol=([A-Za-z0-9&%\-_.]+)", html)
    m["_bse"] = bse.group(1) if bse else ""
    m["_nse"] = nse.group(1).replace("%26", "&").upper() if nse else ""
    cid = COMPANY_ID_RE.search(html)
    if cid:
        m["_company_id"] = cid.group(1) or cid.group(2)

    # Top ratios box
    for li in soup.select("#top-ratios li"):
        name_el = li.select_one(".name")
        if not name_el:
            continue
        label = _label(name_el.get_text(" ", strip=True))
        numbers = [_num(s.get_text()) for s in li.select(".number")]
        if label.startswith("high / low") and len(numbers) >= 2:
            m["high_52w"], m["low_52w"] = numbers[0], numbers[1]
            continue
        key = TOP_RATIO_NAMES.get(label) or re.sub(r"[^a-z0-9]+", "_", label).strip("_")
        if numbers:
            m[key] = numbers[0]
    if m.get("price") and m.get("high_52w"):
        m["away_from_52w_high"] = round((m["high_52w"] - m["price"]) / m["high_52w"] * 100, 2)

    # Growth / return range tables (under Profit & Loss)
    for t in soup.select("table.ranges-table"):
        th = t.find("th")
        title = _label(th.get_text(" ", strip=True)) if th else ""
        prefix = RANGE_TITLES.get(title)
        if not prefix:
            continue
        for tr in t.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) == 2:
                period = RANGE_PERIODS.get(_label(tds[0].get_text()).rstrip(":"))
                if period:
                    m[f"{prefix}_{period}"] = _num(tds[1].get_text())

    # Quarterly results. "Same period last year" is found by DATE (Sep 2026 -> Sep 2025),
    # so half-yearly SME tables and mixed quarter/half-year tables are handled correctly.
    q_head, q = _table(soup, "quarters")
    m["result_period_months"] = _period_months(q_head)
    ly = _same_period_last_year(q_head)  # column index, or None
    q_sales = _row(q, "sales", "revenue")
    q_profit = _row(q, "net profit")
    q_opm = _row(q, "opm %", "financing margin %")
    q_eps = _row(q, "eps in rs", "eps")
    if ly is not None:
        if q_sales and len(q_sales) == len(q_head):
            m["sales_growth_qtr_yoy"] = _pct(q_sales[-1], q_sales[ly])
        if q_profit and len(q_profit) == len(q_head):
            m["profit_growth_qtr_yoy"] = _pct(q_profit[-1], q_profit[ly])
        if q_opm and len(q_opm) == len(q_head):
            m["opm_same_qtr_last_year"] = q_opm[ly]
    if q_opm:
        m["opm_latest_qtr"] = q_opm[-1]
    if q_eps and len(q_eps) >= 2:
        m["eps_latest_qtr"], m["eps_prev_qtr"] = q_eps[-1], q_eps[-2]
    if q_head and q_sales and len(q_sales) == len(q_head):
        n = min(8, len(q_head))
        cut = lambda r: list(r[-n:]) if r and len(r) == len(q_head) else []  # noqa: E731
        m["_quarters"] = {"t": q_head[-n:], "sales": cut(q_sales), "profit": cut(q_profit),
                          "opm": cut(q_opm), "eps": cut(q_eps)}

    # Annual P&L
    pl_head, pl = _table(soup, "profit-loss")
    has_ttm = bool(pl_head) and pl_head[-1].upper() == "TTM"
    np_row = _row(pl, "net profit")
    m["net_profit_ttm"] = _last(np_row)
    m["opm_last_year"] = _last(_row(pl, "opm %", "financing margin %"), 1 if has_ttm else 0)
    pbt, interest = _row(pl, "profit before tax"), _row(pl, "interest")
    skip = 1 if has_ttm else 0
    pbt_ly, int_ly = _last(pbt, skip), _last(interest, skip)
    if pbt_ly is not None and int_ly is not None:
        m["interest_coverage"] = 999.0 if int_ly == 0 else round((pbt_ly + int_ly) / int_ly, 2)

    # Balance sheet -> debt to equity
    _, bs = _table(soup, "balance-sheet")
    eq, res, borrow = _last(_row(bs, "equity capital")), _last(_row(bs, "reserves")), _last(_row(bs, "borrowings"))
    if eq is not None and res is not None and (eq + res) > 0:
        m["debt_to_equity"] = round((borrow or 0) / (eq + res), 2)
    fa, cwip = _row(bs, "fixed assets", "net block"), _row(bs, "cwip")
    if fa and len(fa) >= 2 and fa[-1] is not None and fa[-2] is not None:
        c_now = (cwip[-1] or 0) if cwip else 0
        c_prev = (cwip[-2] or 0) if cwip and len(cwip) >= 2 else 0
        m["fixed_assets_latest"], m["fixed_assets_prev"] = fa[-1] + c_now, fa[-2] + c_prev

    # Cash flow -> CFO / Net profit
    cf_head, cf = _table(soup, "cash-flow")
    cfo = _row(cf, "cash from operating activity")
    if cfo and np_row and pl_head:
        annual_np = dict(zip(pl_head, np_row))
        pairs = [(c, annual_np.get(h)) for h, c in zip(cf_head, cfo)
                 if c is not None and annual_np.get(h) is not None]
        if pairs:
            c, p = pairs[-1]
            m["cfo_to_profit_latest"] = round(c / p, 2) if p > 0 else None
            last5 = pairs[-5:]
            sp = sum(p for _, p in last5)
            m["cfo_to_profit_5y"] = round(sum(c for c, _ in last5) / sp, 2) if sp > 0 else None

    # Ratios
    _, r = _table(soup, "ratios")
    m["debtor_days"] = _last(_row(r, "debtor days"))
    m["working_capital_days"] = _last(_row(r, "working capital days"))

    # Shareholding
    _, sh = _table(soup, "quarterly-shp")
    if not sh:
        _, sh = _table(soup, "shareholding")
    prom = _row(sh, "promoters")
    if prom:
        vals = [v for v in prom if v is not None]
        if vals:
            m["promoter_holding"] = vals[-1]
            if len(vals) >= 5:
                m["promoter_change_1y"] = round(vals[-1] - vals[-5], 2)
    elif sh:
        m["promoter_holding"] = 0.0  # company with no promoters listed
    if sh:
        fii, dii = _row(sh, "fiis"), _row(sh, "diis")
        if fii or dii:
            n = max(len(fii or []), len(dii or []))

            def inst(i):
                return sum((r[i] or 0) for r in (fii, dii) if r and len(r) == n)
            if n >= 2:
                m["fii_dii_latest"], m["fii_dii_prev"] = round(inst(-1), 2), round(inst(-2), 2)
        else:
            m["fii_dii_latest"] = m["fii_dii_prev"] = 0.0
        holders = _row(sh, "no. of shareholders", "no of shareholders")
        if holders and len(holders) >= 2 and holders[-1] is not None and holders[-2] is not None:
            m["shareholders_latest"], m["shareholders_prev"] = holders[-1], holders[-2]

    return {k: v for k, v in m.items() if v is not None}


SNAPSHOT_KEYS = ("market_cap", "price", "high_52w", "low_52w", "pe", "book_value", "dividend_yield",
                 "roce", "roe", "roe_3y", "sales_growth_ttm", "sales_growth_3y", "sales_growth_5y",
                 "profit_growth_ttm", "profit_growth_3y", "profit_growth_5y", "sales_growth_qtr_yoy",
                 "profit_growth_qtr_yoy", "opm_latest_qtr", "opm_last_year", "net_profit_ttm",
                 "debt_to_equity", "interest_coverage", "cfo_to_profit_5y", "debtor_days",
                 "working_capital_days", "promoter_holding", "promoter_change_1y", "fii_dii_latest",
                 "shareholders_latest", "result_period_months")


def snapshot(m, today=""):
    """The Screener numbers shown on the dashboard's Fundamentals tab."""
    snap = {k: m[k] for k in SNAPSHOT_KEYS if m.get(k) is not None}
    if m.get("_quarters"):
        snap["quarters"] = m["_quarters"]
    snap["basis"] = "Consolidated" if "consolidated" in m.get("_path", "") else "Standalone"
    snap["as_of"] = today
    return snap


def _get(s, url):
    for attempt in range(3):
        try:
            r = s.get(url, headers=HEADERS, timeout=30)
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 429:
            time.sleep(20 * (attempt + 1))
            continue
        return r
    return None


def fetch_metrics(code, consolidated=True, session=None, pause=2.0):
    """Download the Screener page for one company and return its metrics (or None).

    Some companies have a consolidated page that is missing most numbers (e.g. Shanti Gold),
    so when the first page is incomplete the other one is read too, and the more complete one is used.
    """
    s = session or requests.Session()
    paths = [f"/company/{code}/consolidated/", f"/company/{code}/"] if consolidated else \
            [f"/company/{code}/", f"/company/{code}/consolidated/"]
    best = None
    for path in paths:
        r = _get(s, BASE + path)
        time.sleep(pause)
        if r is None or r.status_code != 200:
            continue
        metrics = parse_company_page(r.text)
        metrics["_path"] = path
        if best is None or completeness(metrics) > completeness(best):
            best = metrics
        if completeness(best) == len(SCORE_INPUTS):
            break
    return best


# ---------------------------------------------------------------- scoring (your marks system)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun",
                                       "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _month_index(h):
    mm = re.match(r"([A-Za-z]{3})\w*\s+(\d{4})", (h or "").strip())
    if mm and mm.group(1).lower() in MONTHS:
        return int(mm.group(2)) * 12 + MONTHS[mm.group(1).lower()]
    return None


def _same_period_last_year(head):
    """Index of the column exactly 12 months before the latest column, or None."""
    idx = [_month_index(h) for h in head or []]
    if not idx or idx[-1] is None:
        return None
    target = idx[-1] - 12
    return idx.index(target) if target in idx else None


def _period_months(head):
    """Months between the last two result columns: 3 = quarterly, 6 = half-yearly."""
    idx = []
    for h in head or []:
        mm = re.match(r"([A-Za-z]{3})\w*\s+(\d{4})", h.strip())
        if mm and mm.group(1).lower() in MONTHS:
            idx.append(int(mm.group(2)) * 12 + MONTHS[mm.group(1).lower()])
    if len(idx) >= 2 and idx[-1] > idx[-2]:
        return idx[-1] - idx[-2]
    return 3


def score(m, cfg):
    """Automatic part of your fundamental marks.

    Returns (marks, max_marks, items). Each item: (label, got, out_of, detail).
    A check with missing data gets 0 marks and detail 'n/a'.
    """
    w = cfg.get("auto_marks", {})
    tol = float(cfg.get("stable_tolerance_pct", 2)) / 100
    mtol = float(cfg.get("margin_tolerance_points", 1))
    items = []

    def add(key, label, ok, detail):
        out_of = float(w.get(key, 0))
        if out_of:
            items.append((label, out_of if ok else 0.0, out_of, detail if ok is not None else "n/a"))

    g = m.get
    # P&L 1 - quarter sales growth >= 0.8 x TTM sales growth
    qs, ts = g("sales_growth_qtr_yoy"), g("sales_growth_ttm")
    add("q_sales_growth", "Q-Sales growth", None if qs is None or ts is None else qs >= 0.8 * ts,
        f"{qs:g}% vs needed {0.8 * ts:.1f}%" if qs is not None and ts is not None else "")
    # P&L 2 - latest quarter EPS >= 0.8 x previous quarter EPS
    e1, e0 = g("eps_latest_qtr"), g("eps_prev_qtr")
    add("q_eps", "Q-EPS", None if e1 is None or e0 is None else e1 >= 0.8 * e0,
        f"EPS {e1:g} vs prev {e0:g}" if e1 is not None and e0 is not None else "")
    # P&L 3 - margin expansion or stable (vs same quarter last year)
    o1, o0 = g("opm_latest_qtr"), g("opm_same_qtr_last_year")
    add("margin", "Margin stable/up", None if o1 is None or o0 is None else o1 >= o0 - mtol,
        f"OPM {o1:g}% vs {o0:g}% last year" if o1 is not None and o0 is not None else "")
    # Balance sheet 1 - fixed assets increased or stable
    f1, f0 = g("fixed_assets_latest"), g("fixed_assets_prev")
    add("fixed_assets", "Fixed assets stable/up", None if f1 is None or f0 is None else f1 >= f0 * (1 - tol),
        f"{f1:g} vs {f0:g} Cr" if f1 is not None and f0 is not None else "")
    # Balance sheet 2 - receivables < 0.5 x revenue  (= debtor days below 182.5)
    dd = g("debtor_days")
    add("receivables", "Receivables < 0.5×Revenue", None if dd is None else dd < 182.5,
        f"debtor days {dd:g}" if dd is not None else "")
    # Holding 1 - FII + DII holding increased
    i1, i0 = g("fii_dii_latest"), g("fii_dii_prev")
    add("fii_dii", "FII/DII buying", None if i1 is None or i0 is None else i1 > i0,
        f"{i1:g}% vs {i0:g}%" if i1 is not None and i0 is not None else "")
    # Holding 2 - number of shareholders decreased or stable
    h1, h0 = g("shareholders_latest"), g("shareholders_prev")
    add("shareholders", "Shareholders stable/down", None if h1 is None or h0 is None else h1 <= h0 * (1 + tol),
        f"{h1:,.0f} vs {h0:,.0f}" if h1 is not None and h0 is not None else "")

    got = sum(i[1] for i in items)
    out_of = sum(i[2] for i in items)
    return round(got, 2), round(out_of, 2), items


def on_full_scale(got, out_of, cfg):
    """Convert automatic marks to your 11-mark scale, e.g. 4/6 -> 7.3/11."""
    full = float(cfg.get("full_marks", 11))
    return math.floor(got / out_of * full * 10 + 0.5 + 1e-9) / 10 if out_of else 0.0  # 8.25 -> 8.3


def passes(got, out_of, pass_marks, cfg):
    """Same percentage bar: 7/11 needed  ->  got/out_of must be >= 7/11."""
    full = float(cfg.get("full_marks", 11))
    return out_of > 0 and got / out_of >= float(pass_marks) / full - 1e-9


def short_reason(items, limit=3):
    """Text of the checks that did not get marks."""
    missed = [f"{label} ({detail})" if detail else label for label, got, _, detail in items if got == 0]
    return "; ".join(missed[:limit]) + (" …" if len(missed) > limit else "")
