"""Sector Rotation: SP + DT stocks grouped by sub-sector, each sub-sector's performance vs the Nifty Smallcap 100.

Sub-sector: Claude's own specific grouping in data/subsectors.json ({"CODE": ["Sector", "Sub-sector"]}, e.g.
["Pharma & Healthcare", "Injectables"]) - written on request 12 Nov 2026. Stocks not in that file use Screener's
finest level, "Industry" (4th of Broad Sector > Sector > Broad Industry > Industry), under its Sector. A sub-sector's line is an equal-weight index of its stocks: each day the average % move of
the stocks that traded, chained from 100 one year ago. Performance: 1 week = 5, 1 month = 21, 3 months = 63, 6 months = 126, 1 year = 252 trading days.
Phase (rotation, changed 14 Nov 2026 from 1 month + 1 week to the steadier 3 months + 1 month):
Leading = beating the index over 3 months and 1 month; Weakening = 3 months yes, 1 month no;
Improving = 3 months no, 1 month yes; Lagging = neither. Cycle: Improving -> Leading -> Weakening -> Lagging.
"""
import bisect

PERIODS = {"1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}
DAYS = 253


OVERRIDE_FILE = "subsectors.json"


def sub_sector(snap, override=None):
    """(sector, sub-sector) of a stock: the specific grouping in data/subsectors.json if it is there,
    else Screener's finest level (Industry) under its Sector; None when neither is known yet."""
    if isinstance(override, (list, tuple)) and len(override) >= 2 and override[1]:
        return (override[0] or "Other", override[1])
    p = (snap or {}).get("sector_path") or []
    p = [x for x in p] + [""] * (4 - len(p))
    sub = p[3] or p[2] or p[1]
    return (p[1] or p[0] or "Other", sub) if sub else None


def _aligned(hist, dates):
    """Closes of a stock on the index dates (last close carried forward; None before its first trade)."""
    t, c = hist.get("t") or [], hist.get("c") or []
    pts = [(d, v) for d, v in zip(t, c) if v]
    ts = [d for d, _ in pts]
    out = []
    for d in dates:
        i = bisect.bisect_right(ts, d) - 1
        out.append(pts[i][1] if i >= 0 else None)
    return out


def _perf(series, n):
    if len(series) <= n or series[-1] is None or series[-1 - n] in (None, 0):
        return None
    return round((series[-1] / series[-1 - n] - 1) * 100, 2)


def _phase(rel):
    m, w = rel.get("3M"), rel.get("1M")       # longer trend, latest move
    if m is None or w is None:
        return ""
    return "Leading" if m >= 0 and w >= 0 else "Weakening" if m >= 0 else "Improving" if w >= 0 else "Lagging"


def build(sp, dt, snaps, charts, index, override=None):
    """Data for the Sector Rotation tab (docs/sectors.json), or None without the index / prices."""
    if not index or not index.get("t") or not charts:
        return None
    dates = list(index["t"])[-DAYS:]
    ic = _aligned(index, dates)
    base = next((v for v in ic if v), None)
    if not base:
        return None
    groups, unclassified, listed = {}, [], {**{k: "DT" for k in dt}, **{k: "SP" for k in sp}}
    for sym, lst in listed.items():
        row = sp.get(sym) or dt.get(sym) or {}
        ss = sub_sector(snaps.get(sym), (override or {}).get(sym))
        if not ss:
            unclassified.append(sym)
            continue
        groups.setdefault(ss, []).append((sym, row.get("name") or sym, lst))
    subs = []
    for (sector, sub), members in groups.items():
        closes = {sym: _aligned(charts[sym], dates) for sym, _, _ in members if charts.get(sym)}
        series, v = [], 100.0
        for i in range(len(dates)):
            if i:
                moves = [cl[i] / cl[i - 1] - 1 for cl in closes.values() if cl[i] and cl[i - 1]]
                if moves:
                    v *= 1 + sum(moves) / len(moves)
            series.append(round(v, 2))
        perf = {k: _perf(series, n) for k, n in PERIODS.items()}
        iperf = {k: _perf(ic, n) for k, n in PERIODS.items()}
        rel = {k: (round(perf[k] - iperf[k], 2) if perf[k] is not None and iperf[k] is not None else None) for k in PERIODS}
        stocks = [{"s": sym, "n": name, "l": lst, **{k: _perf(closes[sym], n) if sym in closes else None for k, n in PERIODS.items()}}
                  for sym, name, lst in members]
        subs.append({"name": sub, "sector": sector, "n": len(members), "priced": len(closes), "series": series,
                     "perf": perf, "rel": rel, "phase": _phase(rel), "stocks": stocks})
    subs.sort(key=lambda x: -(x["perf"]["1M"] if x["perf"]["1M"] is not None else -999))
    return {"as_of": dates[-1], "dates": dates, "index": {"name": "Nifty Smallcap 100", "series": [round(v / base * 100, 2) if v else None for v in ic],
                                                          "perf": {k: _perf(ic, n) for k, n in PERIODS.items()}},
            "subs": subs, "total": len(listed), "unclassified": len(unclassified)}


def assign(listed, snaps, override):
    """New stocks (no specific sub-sector yet) get one automatically from their Screener classification (12 Nov 2026):
    - other stocks of the same Screener industry already grouped by hand -> the sub-sector most of them are in;
    - else a NEW sub-sector named after the Screener industry, under the sector most stocks of that Screener sector
      are in (or the Screener sector name).
    Saved as [sector, sub-sector, "auto"] so Claude can make it more specific later. Returns [(code, sector, sub, is_new)]."""
    hand = {k: v for k, v in override.items() if isinstance(v, (list, tuple)) and len(v) >= 2 and "auto" not in v[2:]}
    by_ind, by_sec = {}, {}
    for code, v in hand.items():
        p = ((snaps.get(code) or {}).get("sector_path") or []) + [""] * 4
        if p[3]:
            by_ind.setdefault(p[3], []).append((v[0], v[1]))
        if p[1]:
            by_sec.setdefault(p[1], []).append(v[0])
    known_subs = {tuple(v[:2]) for v in override.values() if isinstance(v, (list, tuple)) and len(v) >= 2}
    made = []
    for code in listed:
        if code in override:
            continue
        p = ((snaps.get(code) or {}).get("sector_path") or []) + [""] * 4
        ind = p[3] or p[2]
        if not ind:
            continue                          # Screener page not read yet: next run
        peers = by_ind.get(p[3]) or []
        if peers:
            sector, sub = max(set(peers), key=peers.count)
        else:
            secs = by_sec.get(p[1]) or []
            sector, sub = (max(set(secs), key=secs.count) if secs else (p[1] or p[0] or "Other")), ind
        override[code] = [sector, sub, "auto"]
        made.append((code, sector, sub, (sector, sub) not in known_subs))
        known_subs.add((sector, sub))
    return made
