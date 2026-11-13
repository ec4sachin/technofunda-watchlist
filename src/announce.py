"""Business announcements of SP / DT stocks from the exchanges (rule of 13 Nov 2026).

Every run reads the corporate announcements filed since the last run:
  BSE  - api.bseindia.com (all companies, one day at a time, page by page) for stocks with a BSE code
  NSE  - www.nseindia.com/api/corporate-announcements (main board + SME) only for stocks without a BSE code
Only BUSINESS news is kept (orders, contracts, capacity / new plant, acquisition / JV / MoU, new product,
approvals, business updates) - board-meeting notices, trading window, newspaper ads, ESOPs, certificates etc. are dropped.
Saved in data/announcements.json: {"last": "YYYY-MM-DD", "items": {code: [{d, t, k, url, ex}, ...]}} (last 45 days).
The dashboard shows them in the Catalyst window; Claude reads them next day and adds the ones that are a real
catalyst to data/catalysts.json. A download failure never stops the run.
"""
import re
import time
from datetime import datetime, timedelta

import requests

import storage

FILE = "announcements.json"
KEEP_DAYS = 45
MAX_BACK = 4              # days read on the first run / after a gap
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
BSE_API = ("https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno={page}&strCat=-1"
           "&strPrevDate={ymd}&strScrip=&strSearch=P&strToDate={ymd}&strType=C&subcategory=-1")
BSE_PDF = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/{}"
NSE_HOME = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
NSE_API = "https://www.nseindia.com/api/corporate-announcements?index={index}&from_date={dmy}&to_date={dmy}"

# kind of business news: (label, words) - first match wins
KINDS = [
    ("Order", r"\border|work order|purchase order|contract|letter of (?:award|intent|acceptance)|\bloa\b|\bloi\b|"
              r"\bbag(?:s|ged)\b|secures?|secured|\bwins?\b|\bwon\b|lowest bidder|\bl-?1\b|empanel"),
    ("Capacity", r"capacity|expansion|commission|commercial production|new plant|new unit|greenfield|brownfield|"
                 r"capex|production (?:start|commence)|commences? production|trial production"),
    ("Acquisition / JV", r"acqui|joint venture|\bjv\b|memorandum of understanding|\bmou\b|strategic (?:partnership|alliance)|"
                         r"collaborat|tie-?up|technology (?:transfer|licen)"),
    ("Product / approval", r"launch|new product|approval|usfda|\bfda\b|\brdso\b|\bbis\b|certif(?:ied|ication)|patent|"
                           r"registration|prototype|type test"),
    ("Business update", r"business update|operational update|guidance|press release|media release|outlook"),
]
DROP = (r"trading window|board meeting|newspaper|publication|\besop|\besos|employee stock|postal ballot|"
        r"annual general|\bagm\b|\begm\b|record date|dividend|loss of share|duplicate share|share certificate|"
        r"regulation 74|reg\.? 74|credit rating|compliance certificate|secretarial|closure of|scrutini[sz]er|"
        r"voting result|investor meet|analyst meet|earnings call|conference call|con-?call|audio recording|transcript|"
        r"change in (?:director|auditor|kmp|company secretary)|resignation|appointment of|book closure|"
        r"financial results|integrated filing|statement of deviation|monitoring agency|insider trading|"
        r"sast|pledge|encumbrance|allotment|warrant")
_KIND = [(k, re.compile(p, re.I)) for k, p in KINDS]
_DROP = re.compile(DROP, re.I)


def kind_of(text, sub=""):
    """Business label for an announcement, or None when it is routine paperwork."""
    txt = f"{sub} {text}"
    if "award of order" in sub.lower() or "receipt of order" in sub.lower():
        return "Order"
    if _DROP.search(txt) and not re.search(r"\border\b|contract|capacity|acqui|joint venture", text, re.I):
        return None
    for k, rx in _KIND:
        if rx.search(txt):
            return k
    return None


def _clean(t, n=280):
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def bse_day(day, session=None, max_pages=60):
    """All BSE announcements of one day: [{code, d, title, sub, url}] (empty list if it cannot be read)."""
    s = session or requests.Session()
    h = {"User-Agent": UA, "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com",
         "Accept": "application/json, text/plain, */*"}
    out, ymd = [], day.strftime("%Y%m%d")
    for page in range(1, max_pages + 1):
        if storage.out_of_time():
            break
        try:
            r = s.get(BSE_API.format(page=page, ymd=ymd), headers=h, timeout=20)
            rows = ((r.json() or {}).get("Table") or []) if r.ok else []
        except Exception:
            rows = []
        if not rows:
            break
        for x in rows:
            sub = str(x.get("SUBCATNAME") or x.get("CATEGORYNAME") or "")
            title = x.get("HEADLINE") or x.get("NEWSSUB") or ""
            att = x.get("ATTACHMENTNAME") or ""
            out.append({"code": str(x.get("SCRIP_CD") or "").strip(), "d": str(x.get("NEWS_DT") or x.get("DT_TM") or "")[:10] or day.strftime("%Y-%m-%d"),
                        "title": _clean(f"{x.get('NEWSSUB') or ''} — {title}" if x.get("NEWSSUB") and title and title not in str(x.get("NEWSSUB")) else title or x.get("NEWSSUB")),
                        "sub": sub, "url": BSE_PDF.format(att) if att else "https://www.bseindia.com/corporates/ann.html"})
        try:
            total = int(rows[0].get("TotalPageCnt") or 0)
        except (TypeError, ValueError):
            total = 0
        if total and page >= total:
            break
        time.sleep(0.4)
    return out


def nse_day(day, session=None):
    """NSE announcements (main board + SME) of one day: [{symbol, d, title, sub, url}]."""
    s = session or requests.Session()
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Referer": NSE_HOME}
    try:
        s.get(NSE_HOME, headers={"User-Agent": UA}, timeout=20)     # cookies first
    except Exception:
        return []
    out, dmy = [], day.strftime("%d-%m-%Y")
    for index in ("equities", "sme"):
        try:
            r = s.get(NSE_API.format(index=index, dmy=dmy), headers=h, timeout=20)
            rows = r.json() if r.ok else []
        except Exception:
            rows = []
        if isinstance(rows, dict):
            rows = rows.get("data") or []
        for x in rows or []:
            dt = str(x.get("an_dt") or x.get("sort_date") or "")
            try:
                d = datetime.strptime(dt[:11], "%d-%b-%Y").strftime("%Y-%m-%d")
            except ValueError:
                d = dt[:10] or day.strftime("%Y-%m-%d")
            out.append({"symbol": str(x.get("symbol") or "").upper(), "d": d,
                        "title": _clean(x.get("attchmntText") or x.get("desc")), "sub": str(x.get("desc") or ""),
                        "url": x.get("attchmntFile") or NSE_HOME})
    return out


def update(sp, dt, today, days=None, bse=bse_day, nse=nse_day):
    """Read the announcements filed since the last run and keep the business ones of SP / DT stocks.
    Returns the NEW ones as [(code, name, "Kind: title", url)] for the Telegram message."""
    saved = storage.load_json(FILE, {}) or {}
    items = saved.get("items") or {}
    now = datetime.strptime(today, "%Y-%m-%d")
    last = saved.get("last")
    start = max(now - timedelta(days=MAX_BACK), datetime.strptime(last, "%Y-%m-%d")) if last else now - timedelta(days=MAX_BACK)
    days = days or [start + timedelta(days=i) for i in range((now - start).days + 1)]
    rows = {**sp, **dt}
    by_bse = {str(r.get("bse") or (c if str(c).isdigit() else "")): c for c, r in rows.items()}
    by_bse.pop("", None)
    by_nse = {str(r.get("nse") or (c if not str(c).isdigit() else "")).upper(): c for c, r in rows.items()
              if not (r.get("bse") or str(c).isdigit())}
    by_nse.pop("", None)
    new, s_b, s_n, read_any = [], requests.Session(), requests.Session(), False

    def add(code, a, ex):
        k = kind_of(a["title"], a.get("sub", ""))
        if not k or not a["title"]:
            return
        lst = items.setdefault(code, [])
        key = (a["d"], a["title"][:80].lower())
        if any((x["d"], x["t"][:80].lower()) == key for x in lst):
            return
        lst.append({"d": a["d"], "t": a["title"], "k": k, "url": a["url"], "ex": ex, "seen": today})
        new.append((code, rows[code].get("name") or code, f"{k}: {a['title']}", a["url"]))

    for d in days:
        if d.weekday() >= 5 and d.date() != now.date():
            continue
        if by_bse:
            got = bse(d, s_b)
            read_any = read_any or bool(got)
            for a in got:
                if a["code"] in by_bse:
                    add(by_bse[a["code"]], a, "BSE")
        if by_nse:
            got = nse(d, s_n)
            read_any = read_any or bool(got)
            for a in got:
                if a["symbol"] in by_nse:
                    add(by_nse[a["symbol"]], a, "NSE")
    cut = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    items = {c: sorted([x for x in lst if x["d"] >= cut], key=lambda x: x["d"], reverse=True)[:12]
             for c, lst in items.items()}
    items = {c: v for c, v in items.items() if v}
    # move "last" on only when something could be read (a blocked day is tried again next run)
    storage.save_json(FILE, {"last": today if read_any else (last or ""), "items": items})
    return new, read_any


def recent(sp, dt, days=30, today=None):
    """{code: [...]} of SP / DT stocks for the dashboard (last 30 days)."""
    saved = storage.load_json(FILE, {}) or {}
    now = datetime.strptime(today, "%Y-%m-%d") if today else datetime.now()
    cut = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    return {c: [x for x in v if x.get("d", "") >= cut] for c, v in (saved.get("items") or {}).items()
            if (c in sp or c in dt) and any(x.get("d", "") >= cut for x in v)}
