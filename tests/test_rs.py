"""Relative Strength rating (1-99) for new stocks: worked out against a made-up market of BSE stocks."""
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import rs  # noqa: E402

TODAY = datetime(2026, 11, 9, 9, 0)   # Monday morning: latest file is Friday 6 Nov


class FakeBSE:
    """1,000 stocks: stock i gained i/100 % per month (0 to 10%). Friday 6 Nov is the latest file."""
    def __init__(self, missing_days=()):
        self.asked, self.missing, self.fails, self.last = [], set(missing_days), 0, ""

    def day(self, d):
        self.asked.append(d.strftime("%Y-%m-%d"))
        if d.date() >= TODAY.date() or d.strftime("%Y-%m-%d") in self.missing:
            self.last = "missing"
            return None
        months = (datetime(2026, 11, 6) - d).days / 30.44
        rows = [{"code": str(500000 + i), "series": "A", "close": 100 / (1 + i / 10000) ** months} for i in range(1000)]
        rows.append({"code": "999001", "series": "F", "close": 1.0})          # a bond: not counted
        rows.append({"code": "590001", "series": "E", "close": 1.0})          # an ETF: not counted
        return rows


def chart(gain_per_month, months_listed=24):
    days = [datetime(2026, 11, 6) - timedelta(days=k) for k in range(int(months_listed * 30.44))][::-1]
    return {"t": [d.strftime("%Y-%m-%d") for d in days],
            "c": [100 / (1 + gain_per_month) ** ((datetime(2026, 11, 6) - d).days / 30.44) for d in days]}


def test():
    rs._market.clear()
    ex = FakeBSE(missing_days={"2026-08-07"})        # a holiday 3 months back: the day before is used
    mk = rs.market(TODAY, exchange=ex)
    assert mk["dates"][0] == "2026-11-06" and mk["dates"][3] == "2026-08-06", mk["dates"]
    assert len(mk["close"][0]) == 1000                 # bond + ETF left out
    assert not any(a in ("2026-11-07", "2026-11-08") for a in ex.asked)   # weekend not asked
    n = len(ex.asked)
    assert rs.market(TODAY, exchange=ex) is mk and len(ex.asked) == n     # once per run

    # gaining 5% a month beats 500 of the 1,000 (stock i gains i/10 %): RS 50
    r, note = rs.rating(chart(0.05), mk)
    assert r == 50, (r, note)
    assert "12 months" in note
    r, _ = rs.rating(chart(0.09), mk)
    assert r == 90
    assert rs.rating(chart(0.5), mk)[0] == 99 and rs.rating(chart(-0.2), mk)[0] == 1
    # listed 5 months ago: compared over 3 months only, against the same 3 months of everyone
    r, note = rs.rating(chart(0.085, months_listed=5), mk)
    assert r == 85 and "3 months" in note, (r, note)
    # 2 months of prices: too new to rate
    assert rs.rating(chart(0.3, months_listed=2), mk)[0] is None

    # 3-month RS: only the last 3 months count. Strong for a year, weak lately: 12-month RS 85, 3-month RS low
    def two_speed(fast, slow, recent_days=92):
        days = [datetime(2026, 11, 6) - timedelta(days=k) for k in range(730)][::-1]
        c, v = [], 100.0
        for i, d in enumerate(days):
            age = (datetime(2026, 11, 6) - d).days
            g = slow if age < recent_days else fast
            if i:
                v *= (1 + g) ** ((d - days[i - 1]).days / 30.44)
            c.append(v)
        return {"t": [d.strftime("%Y-%m-%d") for d in days], "c": c}
    ch = two_speed(0.16, 0.02)
    r12, _ = rs.rating(ch, mk)
    r3, note3 = rs.rating(ch, mk, upto=3)
    assert r3 == 20 and note3 == "3-month RS 20" and r12 > 80, (r12, r3)
    assert rs.rating(chart(0.09), mk, upto=3)[0] == 90       # steady stock: same both ways

    real = rs.chart_for
    try:
        for g, want in ((0.09, "pass"), (0.08, "fail"), (0.081, "pass")):   # 80 is not "above 80"
            rs.chart_for = lambda code, m, g=g: chart(g)
            assert rs.check("X", {}, 80)[0] == want, (g, rs.check("X", {}, 80))
        rs.chart_for = lambda code, m: ch                     # 12-month fine, 3-month weak
        st, worst, why = rs.check("X", {}, 80, min_rs3=80)
        assert st == "fail" and worst == 20 and why == "3-month RS 20 (need above 80)", (st, worst, why)
        assert rs.check("X", {}, 80)[0] == "pass"             # 3-month check off
        assert rs.check("X", {}, 0, min_rs3=80)[0] == "fail"   # only the 3-month check (your setting)
        rs.chart_for = lambda code, m: chart(0.09)
        assert rs.check("X", {}, 0, min_rs3=80) == ("pass", 90, "3-month RS 90 (vs 1000 BSE stocks)"), rs.check("X", {}, 0, min_rs3=80)
        rs.chart_for = lambda code, m: two_speed(0.0, 0.10)        # flat for a year, strong lately: 3-month RS passes alone
        assert rs.check("X", {}, 0, min_rs3=80)[0] == "pass" and rs.check("X", {}, 80, min_rs3=80)[0] == "fail"
        rs.chart_for = lambda code, m: chart(0.09)
        st, worst, why = rs.check("X", {}, 80, min_rs3=80)
        assert st == "pass" and why.endswith("3-month RS 90"), why
        rs.chart_for = lambda code, m: chart(0.05)
        assert rs.check("X", {}, 80, min_rs3=80)[2] == "RS 50 (need above 80) and 3-month RS 50 (need above 80)"
        rs.chart_for = lambda code, m: chart(0.3, months_listed=1)
        assert rs.check("X", {}, 80)[0] == "pass"           # too new: let in, noted
        rs.chart_for = lambda code, m: None
        assert rs.check("X", {}, 80)[0] == "retry"          # no prices today: try again tomorrow
        rs._market.clear()
        rs._market["ok"] = False
        real_market = rs.market
        rs.market = lambda today=None: None
        assert rs.check("X", {}, 80)[0] == "retry"          # BSE files not downloaded
        rs.market = real_market
    finally:
        rs.chart_for = real
        rs._market.clear()
    print("RS rating OK")


def test_daily_gate():
    """New stock that passes its marks: added only with RS above 80; RS not readable -> tried again tomorrow."""
    import tempfile
    import main
    import storage
    import fundamentals as fx
    import emails
    storage.DATA = tempfile.mkdtemp()
    real = (fx.fetch_metrics, fx.score, fx.passes, emails.fetch_alert_stocks, rs.check, fx.completeness,
            main.prices.close_and_ema, main.prices.screener_close_and_ema)
    cands = {c: {"code": c, "name": c + " Ltd", "consolidated": True, "sources": ["52W High"], "notes": []}
             for c in ("STRONG", "WEAK", "NODATA")}
    fx.fetch_metrics = lambda code, *a, **k: {"_name": code, "_path": "/company/x/consolidated/"}
    fx.completeness = lambda m: 10
    fx.score = lambda m, cfg, **k: (6, 10, [])
    fx.passes = lambda *a: True
    emails.fetch_alert_stocks = lambda *a, **k: (dict(cands), [], {"52W High": 3})
    rs.check = lambda code, m, mn, min_rs3=0: {"STRONG": ("pass", 92, "RS 92 (12 months, vs 4000 BSE stocks), 3-month RS 88"),
                                    "WEAK": ("fail", 61, "3-month RS 61 (need above 80)"),
                                    "NODATA": ("retry", None, "BSE price files could not be downloaded")}[code]
    os.environ.update(GMAIL_ADDRESS="x", GMAIL_APP_PASSWORD="y")
    main.prices.close_and_ema = lambda *a, **k: {}
    main.prices.screener_close_and_ema = lambda *a, **k: None
    try:
        import yaml
        cfg = dict(yaml.safe_load(open(os.path.join(HERE, "..", "config", "rules.yaml"))))
        assert cfg["new_stock_min_rs"] == 0 and cfg["new_stock_min_rs3"] == 80
        sp, dt, state, rep = {}, {}, {"seen_email_ids": []}, {k: [] for k in ("added", "rejected", "to_dt", "to_sp", "removed",
                                                                              "unchecked", "no_price", "warnings", "first_marked", "new_listing")}
        main.daily(sp, dt, {"alerts": ["52W High"]}, cfg, state, "2026-11-09", rep, [], {}, {})
        assert "STRONG" in sp and "WEAK" not in sp and "NODATA" not in sp, sp.keys()
        assert "RS 92" in rep["added"][0][2]
        assert rep["rejected"][0][0] == "WEAK" and "3-month RS 61 (need above 80)" in rep["rejected"][0][2], rep["rejected"]
        assert rep["unchecked"][0][0] == "NODATA" and "NODATA" in state["pending"]
        # RS gate off (0): weak stock gets in
        sp, rep2 = {}, {k: [] for k in rep}
        state = {"seen_email_ids": []}
        main.daily(sp, dt, {"alerts": ["52W High"]}, dict(cfg, new_stock_min_rs=0, new_stock_min_rs3=0), state, "2026-11-09", rep2, [], {}, {})
        assert {"STRONG", "WEAK", "NODATA"} <= set(sp)
    finally:
        (fx.fetch_metrics, fx.score, fx.passes, emails.fetch_alert_stocks, rs.check, fx.completeness,
         main.prices.close_and_ema, main.prices.screener_close_and_ema) = real
        for k in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
            os.environ.pop(k, None)
    print("Daily RS gate OK")


def test_monthly_and_preview():
    """Stocks already in SP / DT: removed at the monthly review when RS is 80 or lower; kept when RS is unknown.
    The one-time preview only reports."""
    import tempfile
    import main
    import storage
    import fundamentals as fx
    import yaml
    storage.DATA = tempfile.mkdtemp()
    cfg = dict(yaml.safe_load(open(os.path.join(HERE, "..", "config", "rules.yaml"))))
    # 8 Nov 2026: only the 3-month RS is used
    assert cfg["monthly_min_rs"] == 0 and cfg["monthly_min_rs3"] == 80 and cfg["new_stock_min_rs"] == 0 and cfg["new_stock_min_rs3"] == 80
    cfg.update(monthly_min_rs=80)          # both checks tested below
    assert cfg["monthly_rs_lists"] == ["SP"]   # DT not checked (8 Nov 2026)
    cfg["monthly_rs_lists"] = ["SP", "DT"]     # both lists tested here
    real = (fx.fetch_metrics, fx.score, fx.passes, fx.completeness, rs.check)
    ratings = {"S_STRONG": ("pass", 90, "RS 90 (12 months, vs 4000 BSE stocks)"),
               "S_WEAK": ("fail", 80, "RS 80 (need above 80)"),
               "D_WEAK": ("fail", 35, "RS 35 (need above 80) and 3-month RS 40 (need above 80)"),
               "D_NEW": ("pass", None, "RS: too new (under 3 months of prices)"),
               "S_NODATA": ("retry", None, "RS: no price history"),
               "S_LOWMARKS": ("pass", 95, "RS 95")}
    used_chart = {}

    def fake_check(code, m, mn, today=None, chart=None, min_rs3=0):
        used_chart[code] = chart
        return ratings[code]
    fx.fetch_metrics = lambda code, *a, **k: {"_name": code, "_path": "/x/consolidated/"}
    fx.completeness = lambda m: 10
    fx.score = lambda m, c, **k: (6, 10, [])
    fx.passes = lambda got, out_of, need, c: True
    rs.check = fake_check
    try:
        def lists():
            sp = {c: {"symbol": c, "name": c, "consolidated": "yes"} for c in ("S_STRONG", "S_WEAK", "S_NODATA", "S_LOWMARKS")}
            dt = {c: {"symbol": c, "name": c, "consolidated": "yes"} for c in ("D_WEAK", "D_NEW")}
            return sp, dt
        # preview first (nothing removed, shown once)
        sp, dt = lists()
        state, rep = {}, {"warnings": []}
        charts = {c: {"t": ["2026-11-06"], "c": [1]} for c in list(sp) + list(dt)}
        main.rs_preview(sp, dt, cfg, state, "2026-11-09", rep, charts)
        p = rep["rs_preview"]
        assert len(sp) == 4 and len(dt) == 2
        assert p["by"] == {"SP": (1, 3), "DT": (1, 1)}, p["by"]          # S_WEAK at exactly 80 counts as low
        assert [x[0] for x in p["lose"]] == ["D_WEAK", "S_WEAK"]
        rep2 = {"warnings": []}
        main.rs_preview(sp, dt, cfg, state, "2026-11-10", rep2, charts)
        assert "rs_preview" not in rep2                                    # once only
        rep3 = {"warnings": []}
        main.rs_preview(sp, dt, dict(cfg, monthly_min_rs3=70), state, "2026-11-11", rep3, charts)
        assert "rs_preview" in rep3                                        # rules changed: shown once more
        msg = main.build_message({**{k: [] for k in ("added", "rejected", "to_dt", "to_sp", "removed", "unchecked", "no_price",
                                                     "warnings", "first_marked", "new_listing")}, "rs_preview": p}, sp, dt, "x")
        assert "Relative Strength preview" in msg and "D_WEAK" in msg

        # monthly review: marks first, then RS
        sp, dt = lists()
        fx.score = lambda m, c, **k: (6, 10, []) if m["_name"] != "S_LOWMARKS" else (2, 10, [])
        fx.passes = lambda got, out_of, need, c: got >= 4.5
        rep = {"removed": [], "unchecked": [], "monthly_pass": 0}
        hist = []
        main.monthly(sp, dt, cfg, "2026-12-01", rep, hist, {}, charts=charts)
        assert set(sp) == {"S_STRONG", "S_NODATA"} and set(dt) == {"D_NEW"}, (sp.keys(), dt.keys())
        why = {s_: w for s_, _, w in rep["removed"]}
        assert "need above 80" in why["S_WEAK"] and "3-month RS 40" in why["D_WEAK"] and "marks" in why["S_LOWMARKS"]
        assert used_chart["S_STRONG"] is charts["S_STRONG"]                # today's prices reused, not downloaded again
        assert rep["unchecked"][0][0] == "S_NODATA" and rep["monthly_pass"] == 3
        # DT left out of the RS check
        sp, dt = lists()
        rep = {"removed": [], "unchecked": [], "monthly_pass": 0}
        main.monthly(sp, dt, dict(cfg, monthly_rs_lists=["SP"]), "2026-12-01", rep, [], {}, charts=charts)
        assert "D_WEAK" in dt
        # RS check off
        sp, dt = lists()
        rep = {"removed": [], "unchecked": [], "monthly_pass": 0}
        main.monthly(sp, dt, dict(cfg, monthly_min_rs=0, monthly_min_rs3=0), "2026-12-01", rep, [], {}, charts=charts)
        assert set(sp) == {"S_STRONG", "S_WEAK", "S_NODATA"} and len(dt) == 2
    finally:
        fx.fetch_metrics, fx.score, fx.passes, fx.completeness, rs.check = real
    print("Monthly RS check + preview OK")


if __name__ == "__main__":
    test()
    test_daily_gate()
    test_monthly_and_preview()
