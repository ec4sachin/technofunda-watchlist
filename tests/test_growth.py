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


def test_bse_bonus_and_screener_scaling():
    import datetime as D
    days, d = {}, D.date(2025, 6, 2)
    while len(days) < 200:
        if d.weekday() < 5:
            p = 300.0 if len(days) < 100 else 200.0      # 1:2 bonus (price / 1.5) on day 100, raw BSE prices
            days[d.isoformat()] = (p, p * 1.01, p * 0.99, p, 1000)
        d += D.timedelta(days=1)
    h = universe.bse_chart({}, days)
    assert max(h["c"]) == 200.0 and h["v"][0] == 1500, (max(h["c"]), h["v"][0])   # bonus 1.5 found, older prices / 1.5
    # Screener's (adjusted) closes for the last 50 days, 1% different: every BSE candle follows them
    sc = {t: 202.0 for t in sorted(days)[-50:]}
    h2 = universe.bse_chart(sc, days)
    assert abs(h2["c"][0] - 202.0) < 0.01 and abs(h2["c"][-1] - 202.0) < 0.01
    # a real 15% fall is NOT treated as a split
    days2 = {k: ((v[0] * 0.85,) * 4 + (1000,) if k > sorted(days)[150] else v) for k, v in days.items()}
    h3 = universe.bse_chart({}, days2)
    assert h3["c"][-1] == 170.0 and h3["c"][120] == 200.0
    print("BSE bonus correction + Screener scaling OK")


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
    # liquidity: ~₹28 lakh a day is below the ₹50 lakh minimum -> no buy; ~₹2.8 crore a day -> buy
    thin, book0 = dict(h1, v=[10000] * len(h1["t"])), {}
    strategy.run({"strategies": [gs]}, book0, {"THIN": dict(h, v=[10000] * len(h["t"]))}, {}, {}, growth={"THIN": "Thin"})
    assert not strategy.run({"strategies": [gs]}, book0, {"THIN": thin}, {}, {}, growth={"THIN": "Thin"})["entries"]
    h = dict(h, v=[100000] * len(h["t"])); h1 = dict(h1, v=[100000] * len(h1["t"]))
    cheap = strategy._frame(dict(h, c=[x / 20 for x in h["c"]], o=None, h=None, l=None))
    assert not strategy.liquid(gs, cheap, len(cheap.c) - 1)           # price under ₹20
    assert strategy.liquid({}, cheap, len(cheap.c) - 1)               # SP strategies have no filter
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


def test_positional_exit_after_20pct_gain():
    """Positional: +20% reached (target +30% not), then 2 closes below EMA 50 -> 100% sold."""
    from test_strategy import hist_from, uptrend_then_base
    closes = uptrend_then_base()
    plan = strategy.swing_setup(strategy._frame(hist_from(closes)), len(closes) - 1)
    trig = plan["trigger"]
    path = closes + [trig * 1.01] + [trig * (1 + 0.025 * k) for k in range(1, 10)]     # up to about +22%
    path += [path[-1]] * 30                                                            # sideways: EMA 50 catches up
    df0 = strategy._frame(hist_from(path))
    low = float(df0.e50[-1]) * 0.97                                                    # 5 closes 3% under EMA 50
    path += [low, low * 0.995, low * 0.99, low * 0.985, low * 0.98]
    df = strategy._frame(hist_from(path, rng=0.001))
    j0 = len(closes)
    st = dict(next(d for d in strategy.DEFAULT if d["id"] == "positional"))
    assert strategy.RULES["positional"]["ema50_after_gain"] is None   # rule is OFF; tested here switched on
    strategy.RULES["positional"]["ema50_after_gain"] = 0.20
    t, _ = strategy.try_entry(st, "ABC", "ABC", df, j0, mode="backtest", money=100000)
    assert t["stop"] < low, (t["stop"], low)
    for j in range(j0 + 1, len(df)):
        strategy.manage(t, df, j)
        if t["status"] == "closed":
            break
    assert not t["booked"] and t["status"] == "closed" and len(t["exits"]) == 1, t["exits"]
    assert "after +20% gain" in t["exits"][0]["reason"] and t["exits"][0]["qty"] == t["qty"], t["exits"]
    # rule now ON: before the +30% target, 5 closes below EMA 50 sell 100% (no +20% needed)
    assert strategy.RULES["positional"]["ema50_closes"] == 5
    strategy.RULES["positional"]["ema50_after_gain"] = None
    assert strategy.RULES["positional"]["ema50_before_target"] is True
    flat = closes + [trig * 1.01] + [trig * 1.05] * 40
    low2 = float(strategy._frame(hist_from(flat)).e50[-1]) * 0.99
    df2 = strategy._frame(hist_from(flat + [low2] * 5, rng=0.001))
    t2, _ = strategy.try_entry(st, "ABC", "ABC", df2, j0, mode="backtest", money=100000)
    assert t2["stop"] < low2
    for j in range(j0 + 1, len(df2)):
        strategy.manage(t2, df2, j)
    assert t2["status"] == "closed" and not t2["booked"] and t2["exits"][-1]["qty"] == t2["qty"], t2["exits"]
    assert "EMA 50 exit before target" in t2["exits"][-1]["reason"], t2["exits"]
    df3 = strategy._frame(hist_from(flat + [low2] * 4, rng=0.001))                     # only 4 closes: kept
    t3, _ = strategy.try_entry(st, "ABC", "ABC", df3, j0, mode="backtest", money=100000)
    for j in range(j0 + 1, len(df3)):
        strategy.manage(t3, df3, j)
    assert t3["status"] == "open", t3["exits"]
    strategy.RULES["positional"]["ema50_after_gain"] = None
    print("Positional exit after +20% gain (switched off) OK:", t["exits"][0]["reason"], t["exits"][0]["price"])


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
    test_bse_bonus_and_screener_scaling()
    test_no_trade_on_approximate_candles()
    test_growth_strategy_trades_its_list()
    test_positional_exit_after_20pct_gain()
    test_monthly_check()
