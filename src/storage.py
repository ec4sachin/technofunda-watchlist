"""Watchlists are plain CSV files in the data/ folder (you can open them in Excel)."""
import csv
import json
import os

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
FIELDS = ["symbol", "name", "added_on", "source", "last_close", "ema200",
          "last_fund_check", "fund_result", "yahoo_override", "consolidated", "marks_detail",
          "screener_id", "ema_basis"]
HISTORY_FIELDS = ["date", "symbol", "name", "action", "reason"]


def _path(name):
    return os.path.join(DATA, name)


def load_list(name):
    p = _path(f"{name}.csv")
    if not os.path.exists(p):
        return {}
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {r["symbol"].strip().upper(): {k: (r.get(k) or "").strip() for k in FIELDS}
            for r in rows if r.get("symbol", "").strip()}


def save_list(name, items):
    with open(_path(f"{name}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for sym in sorted(items):
            w.writerow({k: items[sym].get(k, "") for k in FIELDS})


def log(entries):
    p = _path("history.csv")
    new = not os.path.exists(p)
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        if new:
            w.writeheader()
        for e in entries:
            w.writerow({k: e.get(k, "") for k in HISTORY_FIELDS})


def save_json(name, obj):
    with open(_path(name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)


def load_json(name, default):
    p = _path(name)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except ValueError:
            pass
    return default


def load_history(limit=300):
    p = _path("history.csv")
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[-limit:][::-1]


def load_state():
    p = _path("state.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"seen_email_ids": [], "last_run": "", "last_monthly": ""}


def save_state(state):
    state["seen_email_ids"] = state["seen_email_ids"][-1000:]
    with open(_path("state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
