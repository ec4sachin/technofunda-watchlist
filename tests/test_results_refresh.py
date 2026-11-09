"""Results season: stocks whose saved results are a period behind are re-read (40 a run, every 3 days)."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import fundamentals as fx  # noqa: E402
import main  # noqa: E402


def snap(last, as_of):
    return {"quarters": {"t": ["Mar 2026", last]}, "as_of": as_of, "pe": 10}


def test():
    d = main._results_due
    assert d(snap("Jun 2026", "2026-11-05"), "2026-11-09")          # Sep results may be out
    assert not d(snap("Sep 2026", "2026-11-01"), "2026-11-09")      # already the latest
    assert not d(snap("Jun 2026", "2026-11-07"), "2026-11-09")      # read 2 days ago: wait
    assert d(snap("Mar 2026", "2026-11-01"), "2026-11-09")          # half-yearly, Sep half due
    assert d(snap("Sep 2026", "2026-12-20"), "2027-01-25")          # Dec quarter results season
    assert not d({"as_of": "2026-01-01"}, "2026-11-09")             # no results saved: nothing to compare

    snaps = {f"S{i}": snap("Jun 2026", "2026-11-01") for i in range(45)}
    snaps["NEW"] = snap("Sep 2026", "2026-11-01")
    snaps["BAD"] = snap("Jun 2026", "2026-11-01")
    sp = {k: {} for k in snaps}
    real = (fx.fetch_metrics, fx.completeness)
    asked = []
    fx.fetch_metrics = lambda code, *a, **k: (asked.append(code), None if code == "BAD" else
                                              {"_quarters": {"t": ["Jun 2026", "Sep 2026"]}, "pe": 12, "_path": "/company/x/"})[1]
    fx.completeness = lambda m: 10
    try:
        n = main.refresh_results(sp, {}, snaps, "2026-11-09")
        assert n == 40 and "NEW" not in asked and len(asked) == 40
        assert snaps["S0"]["quarters"]["t"][-1] == "Sep 2026" and snaps["S0"]["as_of"] == "2026-11-09" and snaps["S0"]["pe"] == 12
        asked.clear()
        main.refresh_results(sp, {}, snaps, "2026-11-10")              # the rest the next day
        assert sorted(asked) == sorted([f"S{i}" for i in range(40, 45)] + ["BAD"]), asked
        assert snaps["BAD"]["quarters"]["t"][-1] == "Jun 2026" and snaps["BAD"]["as_of"] == "2026-11-10"
        asked.clear()
        main.refresh_results(sp, {}, snaps, "2026-11-11")
        assert asked == []                                              # BAD waits 3 days, the others are up to date
    finally:
        fx.fetch_metrics, fx.completeness = real
    print("Results refresh OK")


if __name__ == "__main__":
    test()
