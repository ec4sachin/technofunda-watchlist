"""Growth list: BSE-only stocks from Screener closes + BSE daily files, live paper trading of the list, monthly check."""
import os
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import storage  # noqa: E402
import strategy  # noqa: E402
import universe  # noqa: E402


class FakeBSE:
    """Gives a BSE file for every weekday except one 'holiday'."""
    name, fails, ok = "BSE", 0, 0

    def __init__(self, holiday):
        self.holiday, self.asked = holiday, 0

    def day(self, d):
        self.asked += 1
        if d.strftime("%Y-%m-%d") == self.holiday:
            return None
        base = 100 + (d - datetime(2026, 1, 1)).days * 0.1
        return [{"code": "511764", "symbol": "X", "series": "", "open": base, "high": base * 1.02, "low": base * 0.99,
                 "close": base * 1.01, "volume": 500},
                {"code": "999999", "symbol": "OTHER", "series": "", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]


def test_bse_files_and_chart():
    storage.DATA = tempfile.mkdtemp()
    now = datetime(2026, 10, 20, 20, 0)
    hol = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    ex = FakeBSE(hol)
    days = universe._bse_days(["511764"], None, today=now, limit=30, exchange=ex)["511764"]
    assert len(days) == 29 and hol not in days, len(days)             # 30 asked, 1 holiday
    files = os.listdir(os.path.join(storage.DATA, universe.DAY_DIR))
    one = open(os.path.join(storage.DATA, universe.DAY_DIR, sorted(f for f in files if f[0] == "2")[-1])).read()
    assert "511764" in one and "999999" not in one                    # only the list's rows are kept
    ex2 = FakeBSE(hol)
    universe._bse_days(["511764"], None, today=now, limit=5, exchange=ex2)
    assert ex2.asked == 5                                             # saved days are not downloaded again
    # Screener closes (older) + BSE candles (newer, real): older part has no open/high/low
    first = min(days)
    old = {(datetime.strptime(first, "%Y-%m-%d") - timedelta(days=k)).strftime("%Y-%m-%d"): 95.0 + k * 0.01
           for k in range(1, 300) if (datetime.strptime(first, "%Y-%m-%d") - timedelta(days=k)).weekday() < 5}
    h = universe.bse_chart(old, days)
    assert h["t"][-1] == max(days) and h["o"][0] is None and h["o"][-1] is not None
    df = strategy._frame(h)
    assert not df.real[0] and df.real[-1]
    print("BSE daily files + Screener closes OK:", len(h["t"]), "days,", sum(df.real), "real candles")


def test_no_trade_on_approximate_candles():
    from test_strategy import hist_from, uptrend_then_base
    h = hist_from(uptrend_then_base() + [130.0] * 3)
    df = strategy._frame(h)
    i = len(df) - 4
    ok = strategy.swing_setup(df, i)
    h2 = dict(h, o=list(h["o"]), h=list(h["h"]), l=list(h["l"]))
    h2["h"][i - 1] = h2["l"][i - 1] = h2["o"][i - 1] = None           # one base candle is close-only
    assert strategy.swing_setup(strategy._frame(h2), i) is None
    print("No setup on approximate candles OK" + ("" if ok else " (base not found in sample)"))


def test_growth_strategy_trades_its_list():
    from test_strategy import hist_from, uptrend_then_base
    storage.DATA = tempfile.mkdtemp()
    closes = uptrend_then_base()
    h = hist_from(closes)
    plan = strategy.swing_setup(strategy._frame(h), len(closes) - 1)
    trig = plan["trigger"]
    h1 = hist_from(closes + [trig * 1.01]); h1["o"][-1] = closes[-1]; h1["h"][-1] = trig * 1.015
    gs = dict(next(d for d in strategy.DEFAULT if d["id"] == "growth_switch"), on=True)
    settings = {"strategies": [gs, dict(strategy.DEFAULT[0], on=True)]}
    book = {}
    strategy.run(settings, book, {"GROW1": h}, {}, {}, growth={"GROW1": "Growth One"})
    ev = strategy.run(settings, book, {"GROW1": h1}, {}, {}, growth={"GROW1": "Growth One"})
    assert [e["strategy"] for e in ev["entries"]] == ["growth_switch"], ev["entries"]  # the SP strategy never buys it
    t = book["open"][0]
    assert t["name"] == "Growth One" and t["ltp"] == round(h1["c"][-1], 2) and t["money"] == 80000.0   # 8% of ₹10 lakh
    assert "GROW1" not in book["last_day"]["swing"]
    # a day without growth prices: the open trade simply waits
    ev = strategy.run(settings, book, {}, {}, {}, growth=None)
    assert book["open"] and not ev["exits"]
    print("Growth list strategy OK:", t["symbol"], t["qty"], "@", t["entry"])


def test_monthly_check():
    import main
    cfg = {"strategies": [dict(strategy.DEFAULT[2], on=True, on_since="2026-08-01"),
                          dict(strategy.DEFAULT[3], on=True, on_since="2026-08-01"),
                          dict(strategy.DEFAULT[0], on=True, on_since="2026-10-30")]}
    book = {"capital": {"switch": {"start": 1e6, "equity": 1.06e6}, "growth_switch": {"start": 1e6, "equity": 0.9e6}},
            "closed": [{"strategy": "switch", "pnl": 5000}, {"strategy": "switch", "pnl": -2000}], "open": []}
    bt = {"switch": {"last2y": {"final": 1.44e6, "capital": 1e6}}}
    ub = {"as_of": "2026-11-05", "strategies": {"growth_switch": {"since": "2017-01-01", "period": {"final": 6e6, "capital": 1e6}}}}
    L = main.strategy_check(cfg, book, bt, ub, "2026-11-05")
    assert len(L) == 2 and "+6.0%" in L[0] and "win 50%" in L[0] and "on track" in L[0], L   # swing: only 6 days ON, skipped
    assert "-10.0%" in L[1] and "behind" in L[1], L
    print("Monthly check OK:\n" + "\n".join(L))


if __name__ == "__main__":
    test_bse_files_and_chart()
    test_no_trade_on_approximate_candles()
    test_growth_strategy_trades_its_list()
    test_monthly_check()
