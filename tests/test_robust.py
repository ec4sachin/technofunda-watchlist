"""Robust test of Smart Switch (24 Nov 2026): structure of the result and the 'strong on the buy day' filter."""
import os
import sys
import tempfile

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import pandas as pd  # noqa: E402
import storage  # noqa: E402
import robust  # noqa: E402
import strategy  # noqa: E402


def _hist(start, step, n=900, rng=0.004):
    t = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2019-01-01", periods=n)]
    c = []
    for i in range(n):           # rises, with a flat 6-day pause every 40 days (bases to break out of)
        c.append((c[-1] if c else start) * (1 if i % 40 > 33 else 1.02 if i % 40 == 0 else step))
    o = [c[i - 1] if i else c[0] for i in range(n)]
    return {"t": t, "o": o, "h": [max(o[i], c[i]) * (1 + rng) for i in range(n)],
            "l": [min(o[i], c[i]) * (1 - rng) for i in range(n)], "c": c, "v": [100000] * n}


def test_strong_on_day():
    charts = {"FAST": _hist(100, 1.004), "SLOW": _hist(100, 1.0005), "MID": _hist(100, 1.001), "FLAT": _hist(100, 1.0),
              "UP2": _hist(100, 1.002)}
    strong = robust.strong_on_day(charts)
    d = charts["FAST"]["t"][400]
    assert d in strong["FAST"] and d not in strong["SLOW"] and d not in strong["FLAT"]   # top 20% of 5 = the fastest only
    trades = [{"symbol": "FAST", "entry_date": d}, {"symbol": "SLOW", "entry_date": d}]
    assert robust.only_strong(trades, strong) == [trades[0]]


def test_run_structure():
    storage.DATA = tempfile.mkdtemp()
    charts = {f"S{i}": _hist(100 + i, 1.003 + i * 0.0003) for i in range(6)}
    names = {k: k for k in charts}
    cfg = {"strategies": [dict(x, on=True) for x in strategy.DEFAULT]}
    out = robust.run(cfg, charts, names, sorted(charts), charts, names, None, "2026-11-24", 2026)
    assert out and storage.load_json("robust_test.json", {})["version"] == robust.TEST_VERSION
    for k in ("sp_list", "stock_list", "stock_list_strong_only"):
        r = out[k]
        assert len(r["grid"]) == len(robust.TRIGGERS) * len(robust.GAPS)
        assert sum(g["live"] for g in r["grid"]) == 1
        live = next(g for g in r["grid"] if g["live"])
        assert live["trigger_pct"] == 1.0 and live["gap_pct"] == 5.0
        assert set(r["walk_forward"]) >= {"chosen_on_2017_2022", "chosen_out", "live_out"}
        assert set(r["costs"]) == {"normal", "double"}
    sl = out["sp_list"]
    assert sl["costs"]["normal"]["trades"] > 0
    assert sl["costs"]["double"]["return_pct"] <= sl["costs"]["normal"]["return_pct"]   # more costs never help
    assert not robust.due("2026-11-25") and robust.due("2026-12-02")
    assert strategy.COST_PER_SIDE == 0.002 and strategy.MAX_GAP == "list"               # settings put back
