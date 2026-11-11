"""TTM profit growth below 20%: removed from SP / DT at the monthly review, and new stocks are not added (11 Nov 2026)."""
import os
import sys
import tempfile

import yaml

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import emails  # noqa: E402
import fundamentals as fx  # noqa: E402
import main  # noqa: E402
import storage  # noqa: E402

CFG = yaml.safe_load(open(os.path.join(HERE, "..", "config", "rules.yaml")))
GROWTH = {"FAST": 45.0, "EDGE": 20.0, "SLOW": 12.0, "FALL": -30.0, "NONE": None}


def fake(code, *a, **k):
    return {"_name": code, "_path": "/company/x/consolidated/", "profit_growth_ttm": GROWTH[code]}


def test():
    assert CFG["monthly_min_profit_growth"] == 20 and CFG["new_stock_min_profit_growth"] == 20
    storage.DATA = tempfile.mkdtemp()
    real = (fx.fetch_metrics, fx.score, fx.passes, fx.completeness, emails.fetch_alert_stocks)
    fx.fetch_metrics, fx.completeness = fake, (lambda m: 10)
    fx.score = lambda m, c, **k: (6, 10, [])
    fx.passes = lambda *a: True
    try:
        cfg = dict(CFG, monthly_min_rs=0, monthly_min_rs3=0, new_stock_min_rs=0, new_stock_min_rs3=0)
        sp = {c: {"symbol": c, "name": c, "consolidated": "yes"} for c in ("FAST", "SLOW", "NONE")}
        dt = {c: {"symbol": c, "name": c, "consolidated": "yes"} for c in ("EDGE", "FALL")}
        rep = {"removed": [], "unchecked": [], "monthly_pass": 0}
        hist = []
        main.monthly(sp, dt, cfg, "2026-12-01", rep, hist, {})
        assert set(sp) == {"FAST", "NONE"} and set(dt) == {"EDGE"}, (sp.keys(), dt.keys())   # 20% exactly stays; unknown stays
        why = {s: w for s, _, w in rep["removed"]}
        assert why["SLOW"] == "SP: marks 6.6/11 OK, but TTM profit growth 12% (need 20% or more)", why
        assert "TTM profit growth -30%" in why["FALL"] and rep["monthly_pass"] == 3
        assert any(h["action"] == "REMOVED from DT" and h["symbol"] == "FALL" for h in hist)
        # off
        sp = {c: {"symbol": c, "name": c, "consolidated": "yes"} for c in ("SLOW",)}
        rep = {"removed": [], "unchecked": [], "monthly_pass": 0}
        main.monthly(sp, {}, dict(cfg, monthly_min_profit_growth=0), "2026-12-01", rep, [], {})
        assert "SLOW" in sp
        # new stocks from the emails
        cands = {c: {"code": c, "name": c, "consolidated": True, "sources": ["52W High"], "notes": []} for c in ("FAST", "SLOW", "NONE")}
        emails.fetch_alert_stocks = lambda *a, **k: (dict(cands), [], {"52W High": 3})
        os.environ.update(GMAIL_ADDRESS="x", GMAIL_APP_PASSWORD="y")
        main.prices.close_and_ema = lambda *a, **k: {}
        main.prices.screener_close_and_ema = lambda *a, **k: None
        sp, dt, state = {}, {}, {"seen_email_ids": []}
        rep = {k: [] for k in ("added", "rejected", "to_dt", "to_sp", "removed", "unchecked", "no_price", "warnings",
                               "first_marked", "new_listing")}
        main.daily(sp, dt, {"alerts": ["52W High"]}, cfg, state, "2026-11-11", rep, [], {}, {})
        assert set(sp) == {"FAST", "NONE"}, sp.keys()
        assert rep["rejected"][0][0] == "SLOW" and "TTM profit growth 12% (need 20% or more)" in rep["rejected"][0][2], rep["rejected"]
    finally:
        fx.fetch_metrics, fx.score, fx.passes, fx.completeness, emails.fetch_alert_stocks = real
        for k in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
            os.environ.pop(k, None)
    print("TTM profit growth rule OK")


if __name__ == "__main__":
    test()
