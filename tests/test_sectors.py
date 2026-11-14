"""Sector Rotation: sub-sectors from Screener's classification, equal-weight sub-sector line vs the Smallcap 100."""
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import fundamentals as fx  # noqa: E402
import sectors  # noqa: E402


def days(n):
    d, out = date(2025, 1, 1), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test():
    T = days(300)
    index = {"t": T, "c": [1000 * (1.001 ** i) for i in range(300)]}             # +0.1% a day
    up2 = {"t": T, "c": [100 * (1.002 ** i) for i in range(300)]}                 # +0.2% a day
    flat = {"t": T, "c": [50.0] * 300}
    new = {"t": T[-10:], "c": [10 * (1.01 ** i) for i in range(10)]}             # listed 10 days ago, +1% a day
    path = lambda sub: ["Industrials", "Capital Goods", sub, sub + " parts"]     # noqa: E731
    snaps = {"A": {"sector_path": path("Aerospace")}, "B": {"sector_path": path("Aerospace")},
             "C": {"sector_path": ["Healthcare", "Pharma", "Pharmaceuticals", "Drugs"]}, "N": {"sector_path": path("Aerospace")},
             "U": {}}
    sp = {"A": {"name": "Aaa"}, "C": {"name": "Ccc"}, "N": {"name": "Newco"}}
    dt = {"B": {"name": "Bbb"}, "U": {"name": "Unknown"}}
    out = sectors.build(sp, dt, snaps, {"A": up2, "B": flat, "C": up2, "N": new, "U": flat}, index)
    assert out["total"] == 5 and out["unclassified"] == 1 and out["as_of"] == T[-1]
    subs = {x["name"]: x for x in out["subs"]}
    assert set(subs) == {"Aerospace parts", "Drugs"} and subs["Aerospace parts"]["sector"] == "Capital Goods"   # Screener's finest level
    ph = subs["Drugs"]
    assert abs(ph["perf"]["1W"] - (1.002 ** 5 - 1) * 100) < 0.01 and ph["n"] == 1
    assert abs(out["index"]["perf"]["1M"] - (1.001 ** 21 - 1) * 100) < 0.01
    assert ph["rel"]["3M"] > 0 and ph["rel"]["1M"] > 0 and ph["phase"] == "Leading"   # 3 months + 1 month (14 Nov 2026)
    assert sectors._phase({"3M": 2, "1M": -1}) == "Weakening" and sectors._phase({"3M": -2, "1M": 1}) == "Improving"
    assert sectors._phase({"3M": -2, "1M": -1}) == "Lagging" and sectors._phase({"3M": 1, "1M": None}) == ""
    ae = subs["Aerospace parts"]
    # equal weight: early on only A (+0.2%) and B (0%) -> +0.1% a day; the last 9 days N (+1%) joins: (0.2 + 0 + 1) / 3 = +0.4%
    assert abs(ae["series"][-1] / ae["series"][-2] - 1.004) < 1e-4 and abs(ae["series"][100] / ae["series"][99] - 1.001) < 1e-4
    st = {s["s"]: s for s in ae["stocks"]}
    assert st["B"]["l"] == "DT" and st["B"]["1M"] == 0 and st["N"]["1M"] is None and st["N"]["1W"] is not None
    assert len(ae["series"]) == len(out["dates"]) == sectors.DAYS and set(ae["perf"]) == {"1W", "1M", "3M", "6M", "1Y"}
    assert abs(ph["perf"]["3M"] - (1.002 ** 63 - 1) * 100) < 0.01 and abs(ph["perf"]["6M"] - (1.002 ** 126 - 1) * 100) < 0.01
    assert sectors.build(sp, dt, snaps, {}, index) is None and sectors.build(sp, dt, snaps, {"A": up2}, None) is None
    # Screener page: the 4 classification links
    html = ("<h1>X</h1><a href='/market/IN07/' title='Broad Sector'>Industrials</a><a href='/market/IN07/IN0702/' title='Sector'>Capital Goods</a>"
            "<a href='/market/IN07/IN0702/IN070201/' title='Broad Industry'>Aerospace &amp; Defense</a>"
            "<a href='/market/IN07/IN0702/IN070201/IN070201001/' title='Industry'>Aerospace &amp; Defense</a>")
    m = fx.parse_company_page(html)
    assert m["sector_path"] == ["Industrials", "Capital Goods", "Aerospace & Defense", "Aerospace & Defense"]
    assert fx.snapshot(m)["sector_path"] == m["sector_path"]
    assert sectors.sub_sector({"sector_path": m["sector_path"]}) == ("Capital Goods", "Aerospace & Defense")
    # specific grouping (data/subsectors.json) comes first; it also works before the Screener page is read
    assert sectors.sub_sector({"sector_path": m["sector_path"]}, ["Defence & Aerospace", "Naval systems"]) == ("Defence & Aerospace", "Naval systems")
    assert sectors.sub_sector({}, ["Pharma & Healthcare", "Injectables"]) == ("Pharma & Healthcare", "Injectables")
    out2 = sectors.build(sp, dt, snaps, {"A": up2, "B": flat, "C": up2, "N": new, "U": flat}, index,
                         override={"C": ["Pharma & Healthcare", "Injectables"], "U": ["Pharma & Healthcare", "Injectables"]})
    s2 = {x["name"]: x for x in out2["subs"]}
    assert out2["unclassified"] == 0 and s2["Injectables"]["n"] == 2 and "Drugs" not in s2 and s2["Injectables"]["sector"] == "Pharma & Healthcare"
    assert sectors.sub_sector({"sector_path": ["", "", "", ""]}) is None
    print("Sector Rotation OK:", {k: v["phase"] for k, v in subs.items()})


def test_classify_once():
    import main
    snaps = {"A": {"pe": 1}, "B": {"sector_path": ["a", "b", "c", "d"]}, "C": {"pe": 2}}
    real = fx.fetch_metrics
    asked = []
    fx.fetch_metrics = lambda code, *a, **k: (asked.append(code), {"sector_path": ["x", "y", "z", "w"]} if code == "A" else {"pe": 3})[1]
    try:
        main.classify({"A": {}, "B": {}}, {"C": {}}, snaps, override={})
        assert asked == ["A", "C"] and snaps["A"]["sector_path"][2] == "z" and snaps["C"]["sector_path"] == ["", "", "", ""]
        main.classify({"A": {}, "B": {}}, {"C": {}}, snaps, override={})
        assert asked == ["A", "C"]                                   # read once
        snaps.update(D={"pe": 1}, E={"pe": 1})
        main.classify({"D": {}, "E": {}}, {}, snaps, limit=1, override={"D": ["X", "Y"]})
        assert asked == ["A", "C", "E"]                              # not grouped yet: read first
        many = {f"S{i}": {} for i in range(80)}
        asked.clear()
        main.classify(many, {}, {k: {} for k in many}, override={})
        assert len(asked) == main.CLASSIFY_PER_RUN
    finally:
        fx.fetch_metrics = real
    print("Sub-sector reading OK")


def test_new_stock_groups():
    """New stocks: join the hand-made sub-sector of the same Screener industry, or a new sub-sector is made."""
    P = lambda sec, ind: ["Healthcare", sec, "Pharmaceuticals & Biotechnology", ind]          # noqa: E731
    snaps = {"INJ1": {"sector_path": P("Healthcare", "Pharmaceuticals")}, "INJ2": {"sector_path": P("Healthcare", "Pharmaceuticals")},
             "API1": {"sector_path": P("Healthcare", "Pharmaceuticals")}, "HOSP": {"sector_path": ["Healthcare", "Healthcare", "Healthcare Services", "Hospital"]},
             "NEW1": {"sector_path": P("Healthcare", "Pharmaceuticals")},
             "NEW2": {"sector_path": ["Healthcare", "Healthcare", "Healthcare Equipment", "Medical Equipment & Supplies"]},
             "NEW3": {"sector_path": ["Industrials", "Capital Goods", "Industrial Products", "Bearings"]},
             "WAIT": {}}
    override = {"INJ1": ["Pharma & Healthcare", "Injectables"], "INJ2": ["Pharma & Healthcare", "Injectables"],
                "API1": ["Pharma & Healthcare", "APIs & intermediates"], "HOSP": ["Pharma & Healthcare", "Hospitals"]}
    made = sectors.assign(["INJ1", "NEW1", "NEW2", "NEW3", "WAIT"], snaps, override)
    got = {c: (sec, sub, new) for c, sec, sub, new in made}
    assert got["NEW1"] == ("Pharma & Healthcare", "Injectables", False)        # most stocks of that industry are Injectables
    assert got["NEW2"] == ("Pharma & Healthcare", "Medical Equipment & Supplies", True)   # new sub-sector, sector learnt
    assert got["NEW3"] == ("Capital Goods", "Bearings", True)                  # nothing to learn from: Screener names
    assert "WAIT" not in got and override["NEW1"] == ["Pharma & Healthcare", "Injectables", "auto"]
    assert sectors.sub_sector({}, override["NEW3"]) == ("Capital Goods", "Bearings")
    assert sectors.assign(["NEW1"], snaps, override) == []                      # done once
    # robot step: waits until the hand-grouped stocks' Screener industries are known, then saves and reports
    import tempfile
    import main
    import storage
    storage.DATA = tempfile.mkdtemp()
    storage.save_json("subsectors.json", {k: v for k, v in override.items() if "auto" not in v})
    rep = {}
    early = {**snaps, "INJ1": {}, "INJ2": {}}                                     # 2 of 4 known: wait
    assert main.sub_new({"INJ1": {}, "INJ2": {}, "API1": {}, "HOSP": {}, "NEW3": {"name": "Bearco"}}, {}, early, rep) == [] and not rep
    main.sub_new({"INJ1": {}, "INJ2": {}, "API1": {}, "HOSP": {}, "NEW3": {"name": "Bearco"}}, {}, snaps, rep)
    assert rep["sub_sectors"] == [("NEW3", "Bearco", "Bearings (Capital Goods) · new sub-sector")], rep
    assert storage.load_json("subsectors.json", {})["NEW3"] == ["Capital Goods", "Bearings", "auto"]
    msg = main.build_message({**{k: [] for k in ("added", "rejected", "to_dt", "to_sp", "removed", "unchecked", "no_price", "warnings",
                                                  "first_marked", "new_listing")}, "sub_sectors": rep["sub_sectors"]}, {}, {}, "x")
    assert "Sub-sector given" in msg and "Bearings" in msg
    print("New stock sub-sectors OK")


if __name__ == "__main__":
    test()
    test_classify_once()
    test_new_stock_groups()
