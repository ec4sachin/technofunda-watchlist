"""TechnoFunda Watchlist robot.

  python src/main.py            -> daily run (Steps 1-4), plus monthly review (Step 5) on the 1st
  python src/main.py daily      -> only Steps 1-4
  python src/main.py monthly    -> only Step 5 (full fundamental review of SP and DT)
"""
import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from datetime import datetime as _DT  # used for parsing dates

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import emails  # noqa: E402
import fundamentals as fx  # noqa: E402
import bhav  # noqa: E402
import prices  # noqa: E402
import storage  # noqa: E402
import strategy  # noqa: E402
import market  # noqa: E402
import universe  # noqa: E402
import rs  # noqa: E402
import telegram as tg  # noqa: E402
import web  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
IST = timezone(timedelta(hours=5, minutes=30))


def cfg(name):
    with open(os.path.join(ROOT, "config", name), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def entry(symbol, name="", source="", today=""):
    return {"symbol": symbol, "name": name, "added_on": today, "source": source, "last_close": "",
            "ema200": "", "last_fund_check": "", "fund_result": "", "yahoo_override": "", "consolidated": "yes",
            "marks_detail": "", "screener_id": ""}


def missing_count(row):
    """How many marks checks had no data last time (n/a)."""
    try:
        return sum(1 for item in json.loads(row.get("marks_detail") or "[]") if item[3] == "n/a")
    except (ValueError, IndexError, TypeError):
        return 0


def detail_json(items):
    """Compact per-check marks for the dashboard: [[label, got, out_of, detail], ...]."""
    return json.dumps([[a, b, c, d] for a, b, c, d in items], ensure_ascii=False, separators=(",", ":"))


# ----------------------------------------------------------------- Steps 1-4
def daily(sp, dt, settings, rules_cfg, state, today, report, history, snaps, charts):
    need = float(rules_cfg.get("new_stock_pass", 7))
    full = rules_cfg.get("full_marks", 11)

    # Step 1 - collect stocks from the 5 email alerts + the investors you follow (Mukul Agrawal, Ashish Kacholia)
    gmail, pwd = os.getenv("GMAIL_ADDRESS"), os.getenv("GMAIL_APP_PASSWORD")
    candidates, per_alert = {}, {}
    if gmail and pwd:
        try:
            candidates, new_ids, per_alert = emails.fetch_alert_stocks(
                gmail, pwd, settings["alerts"], settings.get("email_days_back", 3), set(state["seen_email_ids"]),
                investors=settings.get("investors"),
                investor_days_back=None if state.get("investors_since") else 45)   # first time: their last 45 days
            state["seen_email_ids"].extend(new_ids)
            state.setdefault("investors_since", today)
        except Exception as e:  # keep going with the rest of the run
            report["warnings"].append(f"Could not read Gmail: {e}")
    else:
        report["warnings"].append("Gmail not set up (GMAIL_ADDRESS / GMAIL_APP_PASSWORD missing)")
    report["per_alert"] = per_alert
    report["email_total"] = len(candidates)
    # what the investors did in stocks that are already in your lists (a "holds" line is not news)
    report["investor_moves"] = [(c, (sp.get(c) or dt.get(c))["name"] or s["name"], f"{'SP' if c in sp else 'DT'} · " + "; ".join(
        n for n in s.get("notes", []) if ": holds" not in n)) for c, s in candidates.items()
        if (c in sp or c in dt) and any(": holds" not in n for n in s.get("notes", []))]

    # Step 2 + 3 - check fundamentals of stocks not already in SP/DT, add passers to SP
    fresh = {c: s for c, s in candidates.items() if c not in sp and c not in dt}
    report["already_listed"] = len(candidates) - len(fresh)
    # stocks whose Screener page could not be read on an earlier run are tried again (for up to 5 days)
    pending = state.setdefault("pending", {})
    for code, s in list(pending.items()):
        if code in sp or code in dt or _days_since(s.get("since", today), today) > 5:
            pending.pop(code)
        elif code not in fresh:
            fresh[code] = s
    for code, s in fresh.items():
        m = fx.fetch_metrics(code, s.get("consolidated", True))
        if m and fx.completeness(m) < 3:
            m = None
        if not m:
            pending.setdefault(code, {**s, "since": today})
            report["unchecked"].append((code, s["name"], "Screener page could not be read — will try again tomorrow"))
            continue
        pending.pop(code, None)
        got, out_of, items = fx.score(m, rules_cfg)
        snaps[code] = fx.snapshot(m, today)
        mk = f"{fx.on_full_scale(got, out_of, rules_cfg):g}/{full:g}"
        ok = fx.passes(got, out_of, need, rules_cfg)
        rs_note = ""
        min_rs, min_rs3 = float(rules_cfg.get("new_stock_min_rs") or 0), float(rules_cfg.get("new_stock_min_rs3") or 0)
        if ok and (min_rs or min_rs3):   # Relative Strength ratings (1-99): 12-month and 3-month must be above the levels
            try:
                status, _, rs_note = rs.check(code, m, min_rs, min_rs3=min_rs3)
            except Exception as e_:   # never stop the run for this
                status, rs_note = "retry", f"RS check failed: {e_}"
            if status == "retry":
                pending.setdefault(code, {**s, "since": today})
                report["unchecked"].append((code, s["name"], f"marks {mk} passed, but {rs_note} — will try again tomorrow"))
                continue
            if status == "fail":
                ok = False
        if ok:
            e = entry(code, s["name"] or m.get("_name", ""), ", ".join(s["sources"]), today)
            e.update(last_fund_check=today, fund_result=mk, marks_detail=detail_json(items),
                     consolidated="yes" if "consolidated" in m.get("_path", "") else "no",
                     screener_id=m.get("_company_id", ""))
            set_codes(e, m)
            sp[code] = e
            why = "; ".join(s.get("notes") or []) or ", ".join(s["sources"])
            if rs_note:
                e["rs"] = rs_note
            rs_txt = f" · {rs_note}" if rs_note else ""
            report["added"].append((code, e["name"], f"marks {mk}{rs_txt} · " + why))
            history.append({"date": today, "symbol": code, "name": e["name"], "action": "ADDED to SP",
                            "reason": f"marks {mk}{'; ' + rs_note if rs_note else ''}; from " + why})
        else:
            report["rejected"].append((code, s["name"], mk + (f" · {rs_note}" if rs_note else "") +
                                       (f" ({s['sources'][0]})" if s.get("notes") else "")))

    # Marks (not removal) for: stocks added by hand that were never marked, and stocks whose
    # last marks had 2+ checks without data (re-read, in case the other Screener page is complete)
    for list_name, items in (("SP", sp), ("DT", dt)):
        for sym, row in items.items():
            if row.get("last_fund_check") and missing_count(row) < 2 and sym in snaps:
                continue
            m = fx.fetch_metrics(sym, row.get("consolidated", "yes") != "no")
            if not m:
                continue
            got, out_of, marks = fx.score(m, rules_cfg)
            snaps[sym] = fx.snapshot(m, today)
            was, was_missing = row.get("fund_result", ""), missing_count(row) >= 2 or not row.get("last_fund_check")
            row.update(last_fund_check=today, fund_result=f"{fx.on_full_scale(got, out_of, rules_cfg):g}/{full:g}",
                       marks_detail=detail_json(marks), name=row["name"] or m.get("_name", ""),
                       consolidated="yes" if "consolidated" in m.get("_path", "") else "no",
                       screener_id=m.get("_company_id", "") or row.get("screener_id", ""))
            set_codes(row, m)
            if was != row["fund_result"] or (was_missing and missing_count(row) < 2):
                note = row["fund_result"] + (f" (was {was})" if was else "")
                report["first_marked"].append((sym, row["name"], note))

    # NSE / BSE codes for stocks that do not have them yet (one time per stock)
    for items in (sp, dt):
        for sym, row in items.items():
            if row.get("nse") or row.get("bse") or row.get("codes_checked"):
                continue
            m = fx.fetch_metrics(sym, row.get("consolidated", "yes") != "no")
            set_codes(row, m)
            if m and m.get("_company_id") and not row.get("screener_id"):
                row["screener_id"] = m["_company_id"]
            if m and not (row.get("nse") or row.get("bse")):
                row["codes_checked"] = today  # page has no exchange links: do not try every day

    # Newest results for the catalyst box (quarter numbers + price target) in results season - marks are not changed
    try:
        refresh_results(sp, dt, snaps, today)
    except Exception as e:   # never stop the run for this
        report["warnings"].append(f"Results refresh failed: {e}")

    # Step 4 - price vs 200 EMA
    period = int(settings.get("ema_period", 200))
    tick = {sym: prices.yahoo_ticker(sym, row.get("yahoo_override", ""))
            for sym, row in list(sp.items()) + list(dt.items())}
    # older BSE history for stocks that also have a BSE code (joined in front of the NSE prices)
    older = {tick[sym]: f"{row['bse']}.BO" for sym, row in list(sp.items()) + list(dt.items())
             if row.get("bse") and tick.get(sym, "").endswith(".NS")}
    try:
        px = prices.close_and_ema(sorted(set(tick.values())), period, older=older)
    except Exception as e:
        px = {}
        report["warnings"].append(f"Yahoo price download failed: {e}")
    res_by = {sym: px.get(t) for sym, t in tick.items()}

    # Not on Yahoo (common for BSE / SME stocks) -> use Screener.in's own price chart
    for sym, res in res_by.items():
        if res:
            continue
        row = sp.get(sym) or dt.get(sym)
        if not row.get("screener_id"):
            m = fx.fetch_metrics(sym, row.get("consolidated", "yes") != "no")
            if m and m.get("_company_id"):
                row["screener_id"] = m["_company_id"]
                set_codes(row, m)
        res_by[sym] = prices.screener_close_and_ema(row.get("screener_id"), period)

    # Real candles (open/high/low) for closes-only stocks, from the NSE / BSE daily price files
    need = {}
    for sym, res in res_by.items():
        if res and len(res) > 3 and res[3] and "o" not in res[3]:
            row = sp.get(sym) or dt.get(sym)
            need[sym] = {"nse": row.get("nse", ""), "bse": row.get("bse", "")}
    if need:
        try:
            days, warns = bhav.enrich(need, {s_: res_by[s_][3] for s_ in need})
            report["warnings"].extend(warns)
            print(f"Exchange price files: {days} day(s) downloaded for {len(need)} stock(s)")
        except Exception as e:  # never stop the run for this
            report["warnings"].append(f"Exchange price files failed: {e}")
    try:
        bhav.remove_unused(set(sp) | set(dt))
    except OSError:
        pass

    short = int(settings.get("new_listing_ema", 20))
    for sym in list(sp):
        res = res_by.get(sym)
        if not res:
            report["no_price"].append((sym, sp[sym]["name"]))
            continue
        if len(res) > 3 and res[3]:
            charts[sym] = res[3]
        close, ema, basis = judge(res, period, short)
        sp[sym].update(last_close=close, ema200=ema if ema is not None else "", ema_basis=basis or "")
        if basis != period:
            report["new_listing"].append((sym, sp[sym]["name"], f"close {close:g}" +
                                          (f" vs {short} EMA {ema:g} → SP" if ema is not None and close >= ema else
                                           f" vs {short} EMA {ema:g} → DT" if ema is not None else " (too new for any EMA)")))
        if ema is None:
            continue
        if close < ema:
            dt[sym] = sp.pop(sym)
            report["to_dt"].append((sym, dt[sym]["name"], f"close {close:g} < {basis} EMA {ema:g}"))
            history.append({"date": today, "symbol": sym, "name": dt[sym]["name"], "action": "SP -> DT",
                            "reason": f"close {close:g} below {basis} EMA {ema:g}" + (" (new listing)" if basis != period else "")})

    for sym in list(dt):
        if sym not in res_by:
            continue
        res = res_by.get(sym)
        if not res:
            report["no_price"].append((sym, dt[sym]["name"]))
            continue
        if len(res) > 3 and res[3]:
            charts[sym] = res[3]
        close, ema, basis = judge(res, period, short)
        dt[sym].update(last_close=close, ema200=ema if ema is not None else "", ema_basis=basis or "")
        if basis != period and not any(sym == x[0] for x in report["to_dt"]):
            report["new_listing"].append((sym, dt[sym]["name"], f"close {close:g}" +
                                          (f" vs {short} EMA {ema:g}" if ema is not None else " (too new for any EMA)")))
        if ema is None:
            continue
        if settings.get("move_dt_back_to_sp", True) and close > ema and not any(sym == x[0] for x in report["to_dt"]):
            sp[sym] = dt.pop(sym)
            report["to_sp"].append((sym, sp[sym]["name"], f"close {close:g} > {basis} EMA {ema:g}"))
            history.append({"date": today, "symbol": sym, "name": sp[sym]["name"], "action": "DT -> SP",
                            "reason": f"close {close:g} back above {basis} EMA {ema:g}" + (" (new listing)" if basis != period else "")})
    report["price_date"] = max((v[2] for v in res_by.values() if v),
                               key=lambda d: _DT.strptime(d, "%d %b %Y"), default="")


RESULTS_REFRESH_PER_RUN, RESULTS_REFRESH_DAYS = 40, 3


def _results_due(snap, today):
    """True when a newer quarter / half-year may be out: the latest saved one ended 4+ months ago
    (Jun results when it is Nov, Mar results when it is Nov, ...) and the page was last read 3+ days ago."""
    q = (snap.get("quarters") or {}).get("t") or []
    last = fx._month_index(q[-1]) if q else None
    now = _DT.strptime(today, "%Y-%m-%d")
    if last is None or now.year * 12 + now.month - last < 4:
        return False
    return _days_since(str(snap.get("as_of") or "2000-01-01"), today) >= RESULTS_REFRESH_DAYS


def refresh_results(sp, dt, snaps, today, limit=RESULTS_REFRESH_PER_RUN):
    """Results season: re-read the Screener page of stocks whose saved results are a period behind (max `limit` a run)
    so the catalyst box shows the latest quarter. Only the saved Screener numbers change - marks stay until the review."""
    n = 0
    for items in (sp, dt):
        for sym, row in items.items():
            snap = snaps.get(sym)
            if not snap or n >= limit or storage.screener_blocked() or not _results_due(snap, today):
                continue
            n += 1
            m = fx.fetch_metrics(sym, row.get("consolidated", "yes") != "no")
            if m and fx.completeness(m) >= 3:
                snaps[sym] = fx.snapshot(m, today)
            else:
                snap["as_of"] = today      # page not readable today: try again in 3 days
    return n


def _days_since(a, b):
    try:
        return (_DT.strptime(b, "%Y-%m-%d") - _DT.strptime(a, "%Y-%m-%d")).days
    except ValueError:
        return 99


def set_codes(row, m):
    """NSE symbol and BSE code shown on the dashboard (read from the Screener page)."""
    if m:
        row["nse"] = m.get("_nse") or row.get("nse", "")
        row["bse"] = m.get("_bse") or row.get("bse", "")


def judge(res, period, short=20):
    """(close, ema, basis). Normal stocks: the 200 EMA. New listings with under 200 trading days:
    the 20 EMA from their own price history. Too new even for that: (close, None, None)."""
    close, ema = res[0], res[1]
    if ema is not None:
        return close, ema, period
    hist = res[3] if len(res) > 3 and res[3] else {}
    closes = [c for c in hist.get("c", []) if c is not None]
    if len(closes) >= short:
        import pandas as pd
        e = pd.Series(closes, dtype=float).ewm(span=short, adjust=True).mean().iloc[-1]
        return close, round(float(e), 2), short
    return close, None, None


# ----------------------------------------------------------------- Step 5
def rs_lists(rules_cfg):
    """Monthly Relative Strength check: (min RS, lists checked) - min 0 = off."""
    lists = rules_cfg.get("monthly_rs_lists", ["SP", "DT"]) or []
    return (float(rules_cfg.get("monthly_min_rs", 0) or 0), float(rules_cfg.get("monthly_min_rs3", 0) or 0),
            {str(x).upper() for x in lists})


def monthly(sp, dt, rules_cfg, today, report, history, snaps, charts=None):
    need = float(rules_cfg.get("monthly_pass", 7))
    min_rs, min_rs3, rs_in = rs_lists(rules_cfg)
    rs_skip = 0
    full = rules_cfg.get("full_marks", 11)
    drop_missing = str(rules_cfg.get("page_missing_monthly", "keep")).lower() == "remove"
    for list_name, items in (("SP", sp), ("DT", dt)):
        for sym in list(items):
            row = items[sym]
            m = fx.fetch_metrics(sym, row.get("consolidated", "yes") != "no")
            if m and fx.completeness(m) < 3:
                m = None  # page opened but has (almost) no numbers: blocked/changed page, never judge on it
            if not m:
                if drop_missing and not storage.screener_blocked():  # never remove because Screener blocked us
                    items.pop(sym)
                    report["removed"].append((sym, row["name"], f"{list_name}: Screener page not found"))
                    history.append({"date": today, "symbol": sym, "name": row["name"],
                                    "action": f"REMOVED from {list_name}", "reason": "Screener page not found"})
                else:
                    report["unchecked"].append((sym, row["name"], f"{list_name}: Screener page not found — kept"))
                continue
            if not row["name"] and m.get("_name"):
                row["name"] = m["_name"]
            got, out_of, marks = fx.score(m, rules_cfg)
            snaps[sym] = fx.snapshot(m, today)
            mk = f"{fx.on_full_scale(got, out_of, rules_cfg):g}/{full:g}"
            row.update(last_fund_check=today, fund_result=mk, marks_detail=detail_json(marks),
                       consolidated="yes" if "consolidated" in m.get("_path", "") else "no",
                       screener_id=m.get("_company_id", "") or row.get("screener_id", ""))
            set_codes(row, m)
            reason = None
            if not fx.passes(got, out_of, need, rules_cfg):
                reason = f"marks {mk} — missed: " + fx.short_reason(marks)
            elif (min_rs or min_rs3) and list_name in rs_in:   # RS (12-month and 3-month) must be above the levels
                try:
                    status, _, note = rs.check(sym, m, min_rs, chart=(charts or {}).get(sym), min_rs3=min_rs3)
                except Exception as e_:
                    status, note = "retry", f"RS check failed: {e_}"
                if status == "fail":
                    reason = f"marks {mk} OK, but {note}"
                elif status == "retry":
                    rs_skip += 1   # RS not known today: never removed for that
                    report["unchecked"].append((sym, row["name"], f"{list_name}: {note} — kept"))
            if reason is None:
                report["monthly_pass"] += 1
            else:
                items.pop(sym)
                report["removed"].append((sym, row["name"], f"{list_name}: {reason}"))
                history.append({"date": today, "symbol": sym, "name": row["name"],
                                "action": f"REMOVED from {list_name}", "reason": reason})
    report["monthly_done"] = True


def rs_preview(sp, dt, rules_cfg, state, today, report, charts):
    """Once, after the monthly RS check was switched on: which SP / DT stocks have RS at or below the level
    (they would be removed at the next monthly review). Nothing is removed here."""
    min_rs, min_rs3, rs_in = rs_lists(rules_cfg)
    sig = f"{min_rs:g}/{min_rs3:g}/{','.join(sorted(rs_in))}"     # shown again once when the RS rules change
    if not (min_rs or min_rs3) or state.get("rs_preview_done") == sig or not charts:
        return
    rows, known, lose = [], 0, []
    for list_name, items in (("SP", sp), ("DT", dt)):
        if list_name not in rs_in:
            continue
        for sym, row in items.items():
            if not (charts.get(sym) or {}).get("t"):
                continue          # no prices today: not downloaded again just for the preview
            status, r, note = rs.check(sym, None, min_rs, chart=charts.get(sym), min_rs3=min_rs3)
            if status == "retry" and "BSE price files" in note:
                return            # market prices not available today: try again on the next run
            if r is not None:
                known += 1
                rows.append((list_name, status == "fail"))
                if status == "fail":
                    lose.append((r, sym, row["name"], f"{list_name} · {note}"))
    by = {ln: (sum(1 for l_, f in rows if l_ == ln and f), sum(1 for l_, _ in rows if l_ == ln)) for ln in ("SP", "DT")}
    report["rs_preview"] = {"min": min_rs, "min3": min_rs3, "by": by, "known": known,
                            "lose": [x[1:] for x in sorted(lose, key=lambda x: x[0])]}
    state["rs_preview_done"] = sig


# ----------------------------------------------------------------- report
def marks_preview(sp, dt, rules_cfg, state, today, report):
    """rules.yaml extra_marks: preview -> every SP / DT stock is checked once with the Business / Management / Future
    marks and the result is reported (nothing is removed). Unfinished stocks continue on the next run."""
    if fx.extra_mode(rules_cfg) != "preview":
        return
    sig = json.dumps([rules_cfg.get("extra_rules"), rules_cfg.get("auto_marks"), rules_cfg.get("monthly_pass")], sort_keys=True)
    old = storage.load_json("marks_preview.json", {})
    if old.get("signature") == sig and old.get("complete"):
        return   # already done for these rules
    rows = old.get("stocks", {}) if old.get("signature") == sig else {}
    need = float(rules_cfg.get("monthly_pass", 5))
    full = rules_cfg.get("full_marks", 11)
    for lst, items in (("SP", sp), ("DT", dt)):
        for sym, row in items.items():
            if sym in rows:
                continue
            if storage.screener_blocked():
                break
            m = fx.fetch_metrics(sym, row.get("consolidated", "yes") != "no")
            if not m or fx.completeness(m) < 3:
                continue
            g0, o0, items0 = fx.score(m, rules_cfg, extra=False)
            g1, o1, items1 = fx.score(m, rules_cfg, extra=True)
            new_items = items1[len(items0):]   # the Business / Management / Future checks
            rows[sym] = {"name": row.get("name") or sym, "list": lst,
                         "now": f"{fx.on_full_scale(g0, o0, rules_cfg):g}/{full:g}", "now_pass": fx.passes(g0, o0, need, rules_cfg),
                         "new": f"{fx.on_full_scale(g1, o1, rules_cfg):g}/{full:g}", "new_pass": fx.passes(g1, o1, need, rules_cfg),
                         "checks": {lab: [got, out, det] for lab, got, out, det in new_items}}
    total = len(sp) + len(dt)
    done = len(rows)
    storage.save_json("marks_preview.json", {"signature": sig, "as_of": today, "complete": done >= total,
                                             "stocks": rows, "total": total})
    if done < total:
        report["warnings"].append(f"New marks preview: {done} of {total} stocks checked so far — the rest on the next run")
        return
    now_ok = sum(1 for r in rows.values() if r["now_pass"])
    new_ok = sum(1 for r in rows.values() if r["new_pass"])
    lose = sorted([(s, r) for s, r in rows.items() if r["now_pass"] and not r["new_pass"]], key=lambda x: x[0])
    gain = sum(1 for r in rows.values() if r["new_pass"] and not r["now_pass"])
    per = {}
    for r in rows.values():
        for lab, (got, out, _) in r["checks"].items():
            if out:
                per.setdefault(lab, [0, 0])
                per[lab][0] += got >= out
                per[lab][1] += 1
    report["marks_preview"] = {"total": total, "now_ok": now_ok, "new_ok": new_ok, "gain": gain,
                               "lose": [(s, r["name"], f"{r['list']} · now {r['now']} → new {r['new']}") for s, r in lose],
                               "per_check": {k: f"{a} of {b}" for k, (a, b) in per.items()}}


def market_years(mood, this_year):
    """Nifty Smallcap 100 change per calendar year -> bull (>= +15%), bear (<= -10%) or sideways."""
    out = {}
    if not mood or not mood.t:
        return {"years": out}
    for y in range(this_year - 9, this_year + 1):
        pts = [(d, c) for d, c in zip(mood.t, mood.c) if d[:4] == str(y)]
        prev = [c for d, c in zip(mood.t, mood.c) if d < f"{y}-01-01"]
        if len(pts) < 20 or not prev:
            continue
        chg = (pts[-1][1] / prev[-1] - 1) * 100
        above = sum(1 for d, _ in pts if (mood.on(d) or (False,))[0]) / len(pts) * 100
        out[str(y)] = {"change": round(chg, 1), "above_ema50_days_pct": round(above),
                       "phase": "bull" if chg >= 15 else "bear" if chg <= -10 else "sideways", "partial": y == this_year}
    return {"years": out, "index_from": mood.t[0]}


def _per_year(final, capital, years):
    try:
        return ((final / capital) ** (1 / max(years, 0.5)) - 1) * 100
    except (TypeError, ZeroDivisionError, ValueError):
        return None


def strategy_check(strat_cfg, book, bt, ub, today):
    """Telegram lines: each ON strategy since it was switched on, next to what its backtest expected."""
    L = []
    for st in strat_cfg.get("strategies", []):
        sid = st.get("id")
        if not st.get("on") or st.get("type") not in strategy.TRADING_TYPES or not st.get("on_since"):
            continue
        days = _days_since(st["on_since"], today) or 0
        if days < 20:
            continue  # too early to say anything
        cap = (book.get("capital") or {}).get(sid) or {}
        start, eq = cap.get("start") or st.get("capital", strategy.DEF_CAPITAL), cap.get("equity")
        closed = [t for t in book.get("closed", []) if t.get("strategy") == sid]
        wins = sum(1 for t in closed if t.get("pnl", 0) > 0)
        n_open = sum(1 for t in book.get("open", []) if t.get("strategy") == sid)
        if st.get("list") == "GROWTH":
            x = (ub.get("strategies") or {}).get(sid) or {}
            p, since = x.get("period") or {}, x.get("since")
            yrs = (_days_since(since, ub.get("as_of", today)) or 365) / 365.25 if since else 1
            exp = _per_year(p.get("final"), p.get("capital"), yrs)
        else:
            p = (bt.get(sid) or {}).get("last2y") or {}
            exp = _per_year(p.get("final"), p.get("capital"), 2)
        months = days / 30.4
        live = (eq / start - 1) * 100 if eq and start else 0.0
        L.append(f"• <b>{html.escape(st.get('name', sid))}</b> — {months:.1f} months: <b>{live:+.1f}%</b> "
                 f"(₹{eq or start:,.0f}) · {len(closed)} closed, win {wins / len(closed) * 100:.0f}%" if closed else
                 f"• <b>{html.escape(st.get('name', sid))}</b> — {months:.1f} months: <b>{live:+.1f}%</b> (₹{eq or start:,.0f}) · no closed trade yet")
        L[-1] += f" · {n_open} open"
        if exp is not None:
            so_far = ((1 + exp / 100) ** (months / 12) - 1) * 100
            gap = live - so_far
            verdict = "✅ on track" if gap >= -5 else "⚠️ behind the backtest" if gap >= -12 else "🔴 well behind the backtest"
            L[-1] += f"\n   backtest: about {exp:+.0f}% a year → {so_far:+.1f}% expected so far · {verdict}"
    return L


def strategy_lines(st):
    """One block per strategy that is ON: capital, buys, sells, skipped breakouts, setups for today."""
    names = st.get("names") or {}
    sids = list(dict.fromkeys(list((st.get("capital") or {}).keys()) + [e.get("strategy") for e in st.get("entries", []) + st.get("exits", [])]))
    L = []
    h = st.get("health")
    if h:
        lab = strategy.HEALTH_LABEL.get(h["status"], h["status"])
        if h["status"] == "waiting":
            L += ["", f"🩺 <b>Smallcap market health</b>: {lab} — the Edge factor starts with your first closed paper trade "
                      f"(a verdict from {h['min']} trades)"]
        else:
            ed = "no losses yet" if h["edge"] is None else f"<b>{h['edge']:g}</b>"
            L += ["", f"🩺 <b>Smallcap market health</b>: {lab} · Edge factor {ed}",
                  f"Last {h['trades']} closed paper trades: won {h['win_pct']:g}% ({h['wins']} of {h['trades']}) · "
                  f"avg gain +{h['avg_gain']:g}% · avg loss −{h['avg_loss']:g}%  (Healthy above {h['good']:g}, Weak below {h['weak']:g})"]
    for sid in [x for x in sids if x]:
        L += ["", f"🎯 <b>{html.escape(str(names.get(sid, sid)))}</b> (paper trading)"]
        md = (st.get("mood") or {}).get(sid)
        if md:
            L.append(f"🧭 Smallcap 100 {md['close']:,.0f} {'above' if md['above'] else 'below'} EMA 50 {md['ema50']:,.0f} → "
                     f"open trades follow <b>{md['rules']}</b> exits today")
        c = (st.get("capital") or {}).get(sid)
        if c:
            gain = c["equity"] - c["start"]
            L.append(f"💰 Capital ₹{c['equity']:,.0f} ({gain / c['start'] * 100:+.1f}%) · in trades ₹{c['invested']:,.0f} · "
                     f"free ₹{c['cash']:,.0f} · next trade ₹{c['equity'] * c['pct'] / 100:,.0f} ({c['pct']:g}%)")
        n0 = len(L)
        for e in [x for x in st.get("entries", []) if x.get("strategy") == sid]:
            L.append(f"🟢 BUY {html.escape(e['name'])} ({e['symbol']}) {e['qty']} @ ₹{e['price']:g} · stop ₹{e['stop']:g} · target ₹{e['target']:g}"
                     + (f" · {html.escape(e['regime'].split(' → ')[-1])}" if e.get("regime") else ""))
        for e in [x for x in st.get("switched", []) if x.get("strategy") == sid]:
            L.append(f"🔁 {html.escape(e['name'])} ({e['symbol']}) now follows <b>{e['to'].capitalize()}</b> exits"
                     + (f" · new target ₹{e['target']:g}" if e.get("target") else ""))
        for e in [x for x in st.get("exits", []) if x.get("strategy") == sid]:
            L.append(f"{'✅' if e['pnl'] >= 0 else '🔴'} SELL {html.escape(e['name'])} ({e['symbol']}) {e['qty']} @ ₹{e['price']:g} — "
                     f"{html.escape(e['reason'])} · P&amp;L ₹{e['pnl']:+,.0f}")
        for x in [x for x in st.get("skipped", []) if x.get("strategy", sid) == sid]:
            L.append(f"⏭ Skipped {html.escape(x['name'])} ({x['symbol']}) — breakout, but no free capital")
        items = (st.get("setups") or {}).get(sid) or []
        if items:
            L.append("⏳ <b>Setups for today</b> (buy-stop orders):")
            L += [f"• {html.escape(x['name'])} ({x['symbol']}) — buy above ₹{x['buy_above']:g}, stop ₹{x['stop']:g}, "
                  f"qty {x['qty']} (risk {x['risk_pct']:g}%)" for x in items[:15]]
        if len(L) == n0:
            L.append("No entries, exits or setups today.")
    return L


def build_message(r, sp, dt, today_label, dashboard_url=""):
    L = [f"📊 <b>TechnoFunda Watchlist</b> — {today_label}"]
    if r.get("price_date"):
        L.append(f"<i>Prices as of {r['price_date']} close</i>")
    if "email_total" in r:
        L += ["", f"📥 Stocks in Screener emails: <b>{r['email_total']}</b> "
                  f"(already in SP/DT: {r['already_listed']})"]
        parts = [f"{k}: {v}" for k, v in r.get("per_alert", {}).items() if v]
        if parts:
            L.append("   " + " | ".join(parts))
        L.append(f"🔎 Fundamental marks checked: {len(r['added']) + len(r['rejected'])} → passed {len(r['added'])}")

    def block(title, items, show_reason=True):
        if items:
            L.extend(["", title] + [tg.stock_line(s, n, why if show_reason else "") for s, n, why in items])

    block("➕ <b>Added to SP</b>", r["added"])
    block("👤 <b>Investor moves in your SP / DT stocks</b>", r.get("investor_moves") or [])
    block("🔻 <b>Moved SP → DT</b> (closed below 200 EMA, or 20 EMA for new listings)", r["to_dt"])
    block("🔼 <b>Moved DT → SP</b> (back above 200 EMA / 20 EMA)", r["to_sp"])
    if r.get("monthly_done"):
        L += ["", f"🗓 <b>Monthly fundamental review</b>: {r['monthly_pass']} passed, {len(r['removed'])} removed"]
        block("❌ <b>Removed</b> (below monthly pass marks, or Relative Strength too low)", r["removed"])
    block("🆕 <b>Marks updated</b> (added by hand, or data was missing before)", r["first_marked"])
    block("⚠️ <b>Could not check</b>", r["unchecked"])
    if r["new_listing"]:
        L += ["", "🆕 <b>New listings</b> (under 200 trading days → judged on the 20 EMA instead)"] + \
             [tg.stock_line(s, n, why) for s, n, why in r["new_listing"]]
    if r["no_price"]:
        L += ["", "⚠️ No price data (EMA not checked): " + html.escape(", ".join(s for s, _ in r["no_price"]))]
    if r["rejected"] and len(r["rejected"]) <= 15:
        L += ["", "🚫 Below pass marks (not added): " + html.escape(", ".join(f"{n or s} {why}" for s, n, why in r["rejected"]))]
    for w in r["warnings"]:
        L.append(f"⚠️ {html.escape(str(w))}")
    if not any([r["added"], r["to_dt"], r["to_sp"], r["removed"]]):
        L += ["", "No changes today."]
    mp = r.get("marks_preview")
    if mp:
        L += ["", "🧪 <b>New marks preview</b> (Business / Management / Future — nothing changed yet)",
              f"Your {mp['total']} SP + DT stocks: pass now <b>{mp['now_ok']}</b> → with the new marks <b>{mp['new_ok']}</b>"
              f" ({len(mp['lose'])} would drop out, {mp['gain']} would newly pass)",
              "Stocks passing each new check: " + html.escape(" · ".join(f"{k}: {v}" for k, v in mp["per_check"].items()))]
        if mp["lose"]:
            L += ["Would be removed at the monthly review:"] + [tg.stock_line(s, n, why) for s, n, why in mp["lose"][:40]]
        L.append("To use them: set <code>extra_marks: on</code> in config/rules.yaml (or tell Claude).")
    rp = r.get("rs_preview")
    if rp:
        counts = " · ".join(f"{ln}: <b>{a}</b> of {b}" for ln, (a, b) in rp["by"].items() if b)
        lv = " and ".join(x for x in (f"RS above {rp['min']:g}" if rp.get("min") else "",
                                      f"3-month RS above {rp['min3']:g}" if rp.get("min3") else "") if x)
        L += ["", f"🧪 <b>Relative Strength preview</b> (nothing removed yet) — stocks failing {lv}:",
              f"{counts or 'none'} stocks (RS worked out for {rp['known']})",
              "These will be removed at the monthly review if their RS is still low then:"]
        L += [tg.stock_line(s_, n_, why) for s_, n_, why in rp["lose"][:40]]
        if len(rp["lose"]) > 40:
            L.append(f"… and {len(rp['lose']) - 40} more")
    if r.get("strategy_check"):
        L += ["", "📅 <b>Monthly paper-trading check</b> (live result vs backtest)"] + r["strategy_check"]
    st = r.get("strategy")
    if st:
        L += strategy_lines(st)
    L += ["", f"📋 <b>SP: {len(sp)}</b> stocks | <b>DT: {len(dt)}</b> stocks"]
    if r.get("monthly_done") or r.get("send_full_list"):
        for name, items in (("SP", sp), ("DT", dt)):
            if items:
                L += ["", f"<b>{name} list</b>"] + [tg.stock_line(s, items[s]["name"]) for s in sorted(items)]
    if dashboard_url:
        L += ["", f'🖥 <a href="{dashboard_url}">Open dashboard</a>']
    return "\n".join(L)


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "auto").lower()
    settings, rules_cfg = cfg("settings.yaml"), cfg("rules.yaml")
    now = datetime.now(IST)
    today = now.strftime("%Y-%m-%d")
    sp, dt = storage.load_list("SP"), storage.load_list("DT")
    state, history = storage.load_state(), []
    both = set(sp) & set(dt)
    snaps = storage.load_json("fundamentals.json", {})
    charts = {}
    report = {k: [] for k in ("added", "rejected", "to_dt", "to_sp", "removed", "unchecked", "no_price",
                              "warnings", "first_marked", "new_listing")}
    report["monthly_pass"] = 0
    report["send_full_list"] = mode == "list"
    for sym in sorted(both):  # a stock can be in only one list
        dt.pop(sym)
        report["warnings"].append(f"{sym} was in both SP and DT — kept it in SP only")

    if mode in ("auto", "daily"):
        daily(sp, dt, settings, rules_cfg, state, today, report, history, snaps, charts)
    # Strategies (paper trading until a broker is connected)
    strat_cfg, book = strategy.load_settings(), storage.load_json("strategy_trades.json", {})
    mood = None
    if mode in ("auto", "daily") and charts and any(x.get("type") in strategy.TRADING_TYPES for x in strat_cfg.get("strategies", [])):
        try:
            mood = market.Mood(market.history())  # Nifty Smallcap 100 vs EMA 50 (Smart Switch + climax exit levels)
            if not mood.t:
                report["warnings"].append("Nifty Smallcap 100 prices not available — Smart Switch uses Swing exits and climax exits use the lower levels today")
        except Exception as e:
            report["warnings"].append(f"Nifty Smallcap 100 check failed: {e}")
    # Your own growth stock list (data/universe): prices when a strategy trades it, or when its backtest is due
    growth, g_stocks, g_charts, g_missing = None, None, {}, []
    trade_growth = any(x.get("on") and x.get("list") == "GROWTH" and x.get("type") in strategy.TRADING_TYPES
                       for x in strat_cfg.get("strategies", []))
    u_due, g_failed = False, False
    if mode in ("auto", "daily") and charts:
        try:
            u_due = universe.due(today)
            if trade_growth or u_due:
                g_stocks = universe.load_list()
                g_charts, g_missing = universe.get_charts(g_stocks, span="max" if u_due else "2y")
                growth = {s_: n_ for s_, n_, _, _ in g_stocks} if g_charts else None
                print(f"Growth list: prices for {len(g_charts)} of {len(g_stocks)} stocks")
                if trade_growth and len(g_charts) < len(g_stocks) * 0.5:
                    report["warnings"].append(f"Growth list: prices for only {len(g_charts)} of {len(g_stocks)} stocks today")
        except Exception as e:
            g_failed = True   # do not download everything again for the backtest today
            report["warnings"].append(f"Growth list prices failed: {e}")
    if mode in ("auto", "daily") and charts:
        try:
            report["strategy"] = strategy.run(strat_cfg, book, {**g_charts, **charts}, sp, dt, mood=mood, growth=growth)
            report["strategy"]["health"] = strategy.edge(book.get("closed"))
            storage.save_json("strategy_trades.json", book)
            storage.append_trade_log(report["strategy"].get("log"))
        except Exception as e:  # never stop the watchlist for a strategy problem
            report["warnings"].append(f"Strategy check failed: {e}")
        # Backtest: the same rules on all past candles of the stocks each strategy scans
        try:
            names = {k: (sp.get(k) or dt.get(k) or {}).get("name") or k for k in charts}
            bt = {}
            for st_ in strat_cfg.get("strategies", []):
                if st_.get("type") not in strategy.TRADING_TYPES:
                    continue
                lst = st_.get("list", "SP")
                if lst == "GROWTH":
                    continue  # tested in the stock-list backtest below
                syms = sorted(sp) if lst == "SP" else sorted(dt) if lst == "DT" else sorted(set(sp) | set(dt))
                trades = strategy.backtest(st_, charts, names, syms, mood=mood)
                # only the last 2 years are shown: split into the 2nd last year and the last year
                d2 = (now - timedelta(days=730)).strftime("%Y-%m-%d")
                d1 = (now - timedelta(days=365)).strftime("%Y-%m-%d")
                cap, pct = float(st_.get("capital", strategy.DEF_CAPITAL)), float(st_.get("pct", strategy.DEF_PCT))
                recent = [t for t in trades if t["entry_date"] >= d2]
                rep = strategy.report(recent)
                closed = [t for t in recent if t["status"] == "closed"]
                if len(closed) > 1:  # honest view: result without the single best trade
                    best = max(closed, key=lambda t: t["pnl"])
                    rep["without_best"] = round(rep["total_pnl"] - best["pnl"], 2)
                    rep["best_trade"] = f"{best['name']} {best['entry_date']}"
                keep = sorted(recent, key=lambda t: t["entry_date"], reverse=True)[:300]
                bt[st_["id"]] = {"report": rep, "trades": [{k: t.get(k) for k in ("symbol", "name", "entry_date", "entry", "qty",
                                 "status", "pnl", "pnl_pct", "hold_days", "closed_on", "exits", "open_pnl", "type", "regime")} for t in keep],
                                 "as_of": today, "stocks": len(syms),
                                 "last2y": strategy.portfolio(trades, d2, capital=cap, pct=pct, rank=st_.get("rank")),
                                 "year2": strategy.portfolio(trades, d2, d1, capital=cap, pct=pct, rank=st_.get("rank")),
                                 "year1": strategy.portfolio(trades, d1, capital=cap, pct=pct, rank=st_.get("rank")),
                                 "index_from": mood.t[0] if mood and mood.t else None,
                                 # 10 years, calendar year by year (a fresh ₹10 lakh each year) - for bull / bear comparison
                                 "by_year": {str(y): {k: v for k, v in strategy.portfolio(trades, f"{y}-01-01", f"{y + 1}-01-01",
                                             capital=cap, pct=pct, rank=st_.get("rank")).items() if k in ("return_pct", "trades", "win_rate", "max_drawdown_pct",
                                             "open_trades", "final")} for y in range(now.year - 9, now.year + 1)},
                                 "stocks_with_history": {str(y): sum(1 for s_ in syms if charts.get(s_) and charts[s_]["t"]
                                                         and charts[s_]["t"][0] <= f"{y - 1}-02-01") for y in range(now.year - 9, now.year + 1)}}
            bt["_market"] = market_years(mood, now.year)
            storage.save_json("strategy_backtest.json", bt)
        except Exception as e:
            report["warnings"].append(f"Strategy backtest failed: {e}")
        # Backtest on your own stock list in data/universe/ (when it changed, or weekly)
        try:
            if u_due and g_stocks and len(g_charts) < 0.7 * len(g_stocks):
                report["warnings"].append(f"Stock-list backtest postponed: prices for only {len(g_charts)} of {len(g_stocks)} stocks today")
            elif u_due and not g_failed:
                u = universe.run(strat_cfg, mood, today, now.year, stocks=g_stocks, charts=g_charts or None, missing=g_missing)
                if u:
                    print(f"Stock-list backtest: {u['with_prices']} of {u['stocks']} stocks with prices")
        except Exception as e:
            report["warnings"].append(f"Stock-list backtest failed: {e}")
    # Monthly paper-trading check (first run of each month): live result vs what the backtest expected
    if mode in ("auto", "daily") and str(state.get("last_strategy_check", ""))[:7] != today[:7]:
        try:
            lines = strategy_check(strat_cfg, book, storage.load_json("strategy_backtest.json", {}),
                                   storage.load_json("universe_backtest.json", {}), today)
            if lines:
                report["strategy_check"] = lines
            state["last_strategy_check"] = today
        except Exception as e:
            report["warnings"].append(f"Monthly strategy check failed: {e}")
    # One-time check of all SP / DT stocks with the new Business / Management / Future marks (extra_marks: preview)
    if mode in ("auto", "daily"):
        try:
            marks_preview(sp, dt, rules_cfg, state, today, report)
        except Exception as e:
            report["warnings"].append(f"New marks preview failed: {e}")
        try:
            rs_preview(sp, dt, rules_cfg, state, today, report, charts)
        except Exception as e:
            report["warnings"].append(f"RS preview failed: {e}")
    # Runs on the review day, or on the next run if that day was missed (crash, skipped run)
    is_review_day = now.day >= int(settings.get("monthly_review_day", 1)) and str(state.get("last_monthly", ""))[:7] != today[:7]
    if not state.get("last_monthly"):
        state["last_monthly"] = today  # first run ever: the first review is on the next review day
        is_review_day = False
    if mode == "monthly" or (mode == "auto" and is_review_day):
        monthly(sp, dt, rules_cfg, today, report, history, snaps, charts=charts)
        if storage.screener_blocked():   # Screener blocked us (or out of time): the review runs again tomorrow
            report["warnings"].append("Screener blocked the monthly review part-way — it will run again on the next run")
        else:
            state["last_monthly"] = today

    storage.save_list("SP", sp)
    storage.save_list("DT", dt)
    listed = set(sp) | set(dt)
    snaps = {k: v for k, v in snaps.items() if k in listed}
    storage.save_json("fundamentals.json", snaps)
    storage.log(history)
    state["last_run"] = now.isoformat(timespec="minutes")
    storage.save_state(state)
    summary = {k: report.get(k) for k in ("added", "rejected", "to_dt", "to_sp", "removed", "unchecked", "investor_moves",
                                          "no_price", "warnings", "first_marked", "new_listing", "per_alert", "email_total",
                                          "already_listed", "price_date", "monthly_pass")}
    summary.update(mode=mode, monthly_done=bool(report.get("monthly_done")),
                   run_at=now.strftime("%d %b %Y, %I:%M %p IST"))
    storage.save_json("last_run.json", summary)
    alert_store = storage.load_json("alerts.json", {})
    alert_store["as_of"] = summary["run_at"]
    rules_cfg = {**rules_cfg, "_repo": os.getenv("GITHUB_REPOSITORY", "")}
    # the lists and data above are already saved: a problem in the page or the message must not lose them
    try:
        web.build(sp, dt, summary, storage.load_history(), rules_cfg, snaps=snaps, charts=charts or None, alerts=alert_store,
                  strategies={"settings": strat_cfg, "book": book, "backtest": storage.load_json("strategy_backtest.json", {}),
                              "universe": storage.load_json("universe_backtest.json", None),
                              "log": storage.load_trade_log()})
    except Exception as e:
        print("Dashboard build failed:", e)
        report["warnings"].append(f"Dashboard could not be updated today: {e}")
    try:
        msg = build_message(report, sp, dt, now.strftime("%d %b %Y"), str(settings.get("dashboard_url") or "").strip())
    except Exception as e:
        msg = f"📊 TechnoFunda Watchlist — {now.strftime('%d %b %Y')}\nThe daily message could not be built ({html.escape(str(e))}). Lists are saved; see the dashboard."
    tg.send(os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"), msg)


if __name__ == "__main__":
    main()
