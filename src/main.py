"""TechnoFunda Watchlist robot.

  python src/main.py            -> daily run (Steps 1-4), plus monthly review (Step 5) on the 1st
  python src/main.py daily      -> only Steps 1-4
  python src/main.py monthly    -> only Step 5 (full fundamental review of SP and DT)
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from datetime import datetime as _DT  # used for parsing dates

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import emails  # noqa: E402
import fundamentals as fx  # noqa: E402
import prices  # noqa: E402
import storage  # noqa: E402
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
def daily(sp, dt, settings, rules_cfg, state, today, report, history):
    need = float(rules_cfg.get("new_stock_pass", 7))
    full = rules_cfg.get("full_marks", 11)

    # Step 1 - collect stocks from the 5 email alerts
    gmail, pwd = os.getenv("GMAIL_ADDRESS"), os.getenv("GMAIL_APP_PASSWORD")
    candidates, per_alert = {}, {}
    if gmail and pwd:
        try:
            candidates, new_ids, per_alert = emails.fetch_alert_stocks(
                gmail, pwd, settings["alerts"], settings.get("email_days_back", 3), set(state["seen_email_ids"]))
            state["seen_email_ids"].extend(new_ids)
        except Exception as e:  # keep going with the rest of the run
            report["warnings"].append(f"Could not read Gmail: {e}")
    else:
        report["warnings"].append("Gmail not set up (GMAIL_ADDRESS / GMAIL_APP_PASSWORD missing)")
    report["per_alert"] = per_alert
    report["email_total"] = len(candidates)

    # Step 2 + 3 - check fundamentals of stocks not already in SP/DT, add passers to SP
    fresh = {c: s for c, s in candidates.items() if c not in sp and c not in dt}
    report["already_listed"] = len(candidates) - len(fresh)
    for code, s in fresh.items():
        m = fx.fetch_metrics(code, s.get("consolidated", True))
        if not m:
            report["unchecked"].append((code, s["name"], "Screener page not found"))
            continue
        got, out_of, items = fx.score(m, rules_cfg)
        mk = f"{fx.on_full_scale(got, out_of, rules_cfg):g}/{full:g}"
        if fx.passes(got, out_of, need, rules_cfg):
            e = entry(code, s["name"] or m.get("_name", ""), ", ".join(s["sources"]), today)
            e.update(last_fund_check=today, fund_result=mk, marks_detail=detail_json(items),
                     consolidated="yes" if "consolidated" in m.get("_path", "") else "no",
                     screener_id=m.get("_company_id", ""))
            sp[code] = e
            report["added"].append((code, e["name"], f"marks {mk} · " + ", ".join(s["sources"])))
            history.append({"date": today, "symbol": code, "name": e["name"], "action": "ADDED to SP",
                            "reason": f"marks {mk}; from " + ", ".join(s["sources"])})
        else:
            report["rejected"].append((code, s["name"], mk))

    # Marks (not removal) for: stocks added by hand that were never marked, and stocks whose
    # last marks had 2+ checks without data (re-read, in case the other Screener page is complete)
    for list_name, items in (("SP", sp), ("DT", dt)):
        for sym, row in items.items():
            if row.get("last_fund_check") and missing_count(row) < 2:
                continue
            m = fx.fetch_metrics(sym, row.get("consolidated", "yes") != "no")
            if not m:
                continue
            got, out_of, marks = fx.score(m, rules_cfg)
            was = row.get("fund_result", "")
            row.update(last_fund_check=today, fund_result=f"{fx.on_full_scale(got, out_of, rules_cfg):g}/{full:g}",
                       marks_detail=detail_json(marks), name=row["name"] or m.get("_name", ""),
                       consolidated="yes" if "consolidated" in m.get("_path", "") else "no",
                       screener_id=m.get("_company_id", "") or row.get("screener_id", ""))
            note = row["fund_result"] + (f" (was {was})" if was and was != row["fund_result"] else "")
            report["first_marked"].append((sym, row["name"], note))

    # Step 4 - price vs 200 EMA
    period = int(settings.get("ema_period", 200))
    tick = {sym: prices.yahoo_ticker(sym, row.get("yahoo_override", ""))
            for sym, row in list(sp.items()) + list(dt.items())}
    try:
        px = prices.close_and_ema(sorted(set(tick.values())), period)
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
        res_by[sym] = prices.screener_close_and_ema(row.get("screener_id"), period)

    for sym in list(sp):
        res = res_by.get(sym)
        if not res:
            report["no_price"].append((sym, sp[sym]["name"]))
            continue
        close, ema, _ = res
        sp[sym].update(last_close=close, ema200=ema if ema is not None else "")
        if ema is None:
            report["new_listing"].append((sym, sp[sym]["name"], f"close {close:g}"))
            continue
        if close < ema:
            dt[sym] = sp.pop(sym)
            report["to_dt"].append((sym, dt[sym]["name"], f"close {close:g} < EMA {ema:g}"))
            history.append({"date": today, "symbol": sym, "name": dt[sym]["name"], "action": "SP -> DT",
                            "reason": f"close {close:g} below {period} EMA {ema:g}"})

    for sym in list(dt):
        if sym not in res_by:
            continue
        res = res_by.get(sym)
        if not res:
            report["no_price"].append((sym, dt[sym]["name"]))
            continue
        close, ema, _ = res
        dt[sym].update(last_close=close, ema200=ema if ema is not None else "")
        if ema is None:
            report["new_listing"].append((sym, dt[sym]["name"], f"close {close:g}"))
            continue
        if settings.get("move_dt_back_to_sp", True) and close > ema and not any(sym == x[0] for x in report["to_dt"]):
            sp[sym] = dt.pop(sym)
            report["to_sp"].append((sym, sp[sym]["name"], f"close {close:g} > EMA {ema:g}"))
            history.append({"date": today, "symbol": sym, "name": sp[sym]["name"], "action": "DT -> SP",
                            "reason": f"close {close:g} back above {period} EMA {ema:g}"})
    report["price_date"] = max((v[2] for v in res_by.values() if v),
                               key=lambda d: _DT.strptime(d, "%d %b %Y"), default="")


# ----------------------------------------------------------------- Step 5
def monthly(sp, dt, rules_cfg, today, report, history):
    need = float(rules_cfg.get("monthly_pass", 7))
    full = rules_cfg.get("full_marks", 11)
    drop_missing = str(rules_cfg.get("page_missing_monthly", "keep")).lower() == "remove"
    for list_name, items in (("SP", sp), ("DT", dt)):
        for sym in list(items):
            row = items[sym]
            m = fx.fetch_metrics(sym, row.get("consolidated", "yes") != "no")
            if not m:
                if drop_missing:
                    items.pop(sym)
                    report["removed"].append((sym, row["name"], f"{list_name}: Screener page not found"))
                else:
                    report["unchecked"].append((sym, row["name"], f"{list_name}: Screener page not found — kept"))
                continue
            if not row["name"] and m.get("_name"):
                row["name"] = m["_name"]
            got, out_of, marks = fx.score(m, rules_cfg)
            mk = f"{fx.on_full_scale(got, out_of, rules_cfg):g}/{full:g}"
            row.update(last_fund_check=today, fund_result=mk, marks_detail=detail_json(marks),
                       consolidated="yes" if "consolidated" in m.get("_path", "") else "no",
                       screener_id=m.get("_company_id", "") or row.get("screener_id", ""))
            if fx.passes(got, out_of, need, rules_cfg):
                report["monthly_pass"] += 1
            else:
                items.pop(sym)
                reason = f"marks {mk} — missed: " + fx.short_reason(marks)
                report["removed"].append((sym, row["name"], f"{list_name}: {reason}"))
                history.append({"date": today, "symbol": sym, "name": row["name"],
                                "action": f"REMOVED from {list_name}", "reason": reason})
    report["monthly_done"] = True


# ----------------------------------------------------------------- report
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
    block("🔻 <b>Moved SP → DT</b> (closed below 200 EMA)", r["to_dt"])
    block("🔼 <b>Moved DT → SP</b> (back above 200 EMA)", r["to_sp"])
    if r.get("monthly_done"):
        L += ["", f"🗓 <b>Monthly fundamental review</b>: {r['monthly_pass']} passed, {len(r['removed'])} removed"]
        block("❌ <b>Removed</b> (below monthly pass marks)", r["removed"])
    block("🆕 <b>Marks updated</b> (added by hand, or data was missing before)", r["first_marked"])
    block("⚠️ <b>Could not check</b>", r["unchecked"])
    if r["new_listing"]:
        L += ["", "🆕 New listings (under 200 trading days, 200 EMA not possible yet): " +
              ", ".join(n or s for s, n, _ in r["new_listing"])]
    if r["no_price"]:
        L += ["", "⚠️ No price data (EMA not checked): " + ", ".join(s for s, _ in r["no_price"])]
    if r["rejected"] and len(r["rejected"]) <= 15:
        L += ["", "🚫 Below pass marks (not added): " + ", ".join(f"{n or s} {why}" for s, n, why in r["rejected"])]
    for w in r["warnings"]:
        L.append(f"⚠️ {w}")
    if not any([r["added"], r["to_dt"], r["to_sp"], r["removed"]]):
        L += ["", "No changes today."]
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
    report = {k: [] for k in ("added", "rejected", "to_dt", "to_sp", "removed", "unchecked", "no_price",
                              "warnings", "first_marked", "new_listing")}
    report["monthly_pass"] = 0
    report["send_full_list"] = mode == "list"

    if mode in ("auto", "daily"):
        daily(sp, dt, settings, rules_cfg, state, today, report, history)
    is_review_day = now.day == int(settings.get("monthly_review_day", 1)) and state.get("last_monthly") != today
    if mode == "monthly" or (mode == "auto" and is_review_day):
        monthly(sp, dt, rules_cfg, today, report, history)
        state["last_monthly"] = today

    storage.save_list("SP", sp)
    storage.save_list("DT", dt)
    storage.log(history)
    state["last_run"] = now.isoformat(timespec="minutes")
    storage.save_state(state)
    summary = {k: report.get(k) for k in ("added", "rejected", "to_dt", "to_sp", "removed", "unchecked",
                                          "no_price", "warnings", "first_marked", "new_listing", "per_alert", "email_total",
                                          "already_listed", "price_date", "monthly_pass")}
    summary.update(mode=mode, monthly_done=bool(report.get("monthly_done")),
                   run_at=now.strftime("%d %b %Y, %I:%M %p IST"))
    storage.save_json("last_run.json", summary)
    web.build(sp, dt, summary, storage.load_history(), rules_cfg)

    msg = build_message(report, sp, dt, now.strftime("%d %b %Y"), str(settings.get("dashboard_url") or "").strip())
    tg.send(os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"), msg)


if __name__ == "__main__":
    main()
