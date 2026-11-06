"""Errors found in the 3-reviewer check (6 Nov 2026): each test failed before its fix."""
import json
import math
import os
import sys
import tempfile
from datetime import datetime

import numpy as np

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import storage  # noqa: E402
import strategy as S  # noqa: E402


def _trade(sid, t, **k):
    base = {"id": "a", "strategy": sid, "strategy_name": sid, "symbol": "X", "name": "X", "entry_date": t, "entry": 100,
            "qty": 100, "remaining": 100, "stop": 90, "stop_reason": "SL", "target": 120, "booked": False, "type": "swing",
            "switch": False, "exits": [], "pnl": 0, "status": "open", "days": 0, "peak": 101, "mode": "paper"}
    base.update(k)
    return base


def test_no_stop_missed_after_long_gap():
    """More than 10 missed days: the stop loss inside the gap is still taken (on its own day)."""
    storage.DATA = tempfile.mkdtemp()
    n = 30
    t = [f"2026-02-{k + 1:02d}" if k < 28 else f"2026-03-{k - 27:02d}" for k in range(n)]
    c, low = [100.0] * n, [99.0] * n
    low[14] = 85.0
    ch = {"t": t, "o": c, "h": [x + 1 for x in c], "l": low, "c": c, "v": [1e6] * n}
    st = {"id": "swing", "name": "Swing", "type": "swing", "list": "SP", "capital": 1e6, "pct": 13, "on": True}
    book = {"open": [_trade("swing", t[4], days=5)], "closed": [], "last_day": {"swing": {"X": t[9]}}}
    ev = S.run({"strategies": [st]}, book, {"X": ch}, {"X": {"name": "X"}}, {})
    assert ev["exits"] and ev["exits"][0]["date"] == t[14] and ev["exits"][0]["price"] == 90, ev["exits"]
    # a strategy switched OFF still looks after its open trade (it is never frozen)
    book = {"open": [_trade("swing", t[4], days=5)], "closed": [], "last_day": {"swing": {"X": t[9]}}}
    ev = S.run({"strategies": [dict(st, on=False)]}, book, {"X": ch}, {"X": {"name": "X"}}, {})
    assert ev["exits"] and ev["exits"][0]["date"] == t[14] and not ev["setups"].get("swing"), ev
    print("Stop loss after a long gap OK")


def test_no_candle_twice():
    """A chart one day short (Yahoo lag) must not make a candle count twice."""
    storage.DATA = tempfile.mkdtemp()
    t = [f"2026-02-{k + 1:02d}" for k in range(12)]
    full = {"t": t, "o": [100.0] * 12, "h": [101.0] * 12, "l": [99.0] * 12, "c": [100.0] * 12, "v": [1e6] * 12}
    st = {"id": "s", "name": "S", "type": "swing", "list": "SP", "capital": 1e6, "pct": 13, "on": True}
    tr = _trade("s", t[1])
    book = {"open": [tr], "closed": [], "last_day": {"s": {"X": t[1]}}}
    for k in (6, 5, 6):
        S.run({"strategies": [st]}, book, {"X": {a: b[:k] for a, b in full.items()}}, {"X": {}}, {})
    assert tr["days"] == 4 and book["last_day"]["s"]["X"] == t[5], (tr["days"], book["last_day"])
    print("No candle counted twice OK")


def test_catch_up_in_date_order():
    """After missed days the buys happen in date order (not stock by stock)."""
    storage.DATA = tempfile.mkdtemp()
    n = 10
    t = [f"2026-02-{k + 1:02d}" for k in range(n)]
    charts = {s: {"t": t, "o": [100.0] * n, "h": [101.0] * n, "l": [99.0] * n, "c": [100.0] * n, "v": [1e6] * n} for s in ("AAA", "BBB")}
    sig = {"AAA": 8, "BBB": 5}
    real_setup, real_frame = S.swing_setup, S._frame

    def fake(df, i):
        if i + 1 == sig[df.tag]:
            return {"score": {"low_risk": 1.0}, "trigger": 100.5, "stop": 95.0, "base_low": 96, "resistance": 99.5, "r42": 0,
                    "room": None, "range_pct": 1, "base_from": "", "base_to": ""}
        return None

    def frame(h):
        d = real_frame(h)
        d.tag = next(k for k, v in charts.items() if v is h)
        return d

    S.swing_setup, S._frame = fake, frame
    try:
        st = {"id": "s", "name": "S", "type": "swing", "list": "SP", "capital": 1e6, "pct": 60, "on": True}
        book = {"open": [], "closed": [], "last_day": {"s": {"AAA": t[2], "BBB": t[2]}}}
        ev = S.run({"strategies": [st]}, book, charts, {"AAA": {}, "BBB": {}}, {})
    finally:
        S.swing_setup, S._frame = real_setup, real_frame
    assert [e["symbol"] for e in ev["entries"]] == ["BBB"] and [x["symbol"] for x in ev["skipped"]] == ["AAA"], ev
    print("Catch-up in date order OK")


class _Mood:
    def __init__(self, m):
        self.m = m

    def on(self, d):
        return (self.m[d], 1, 1, d) if d in self.m else None


def test_switch_forgets_other_mode():
    """Smart Switch: the EMA 50 count of the Positional days is not carried over the Swing days."""
    n = 9
    idx = [f"2026-01-{k + 1:02d}" for k in range(n)]
    c = np.array([140, 139, 150, 150, 150, 150, 150, 140, 140], float)
    df = S.Candles(idx, c, c + 1, c - 1, c)
    df.e50, df.e10 = np.array([145.0] * n), np.array([100.0] * n)
    regime = {idx[0]: True, idx[1]: False, idx[2]: False, idx[3]: False, idx[4]: False, idx[5]: False, idx[6]: True, idx[7]: True}
    t = _trade("s", "2025-12-31", type="positional", switch=True, booked=True, remaining=50, target=130, stop=50, days=20, peak=150)
    keep = S.RULES["swing"]["climax"], S.RULES["positional"]["climax"]
    S.RULES["swing"]["climax"] = S.RULES["positional"]["climax"] = None
    try:
        out = []
        for j in range(1, n):
            out.append((idx[j], [x["reason"] for x in S.manage(t, df, j, _Mood(regime))]))
            if t["status"] == "closed":
                break
    finally:
        S.RULES["swing"]["climax"], S.RULES["positional"]["climax"] = keep
    assert out[-1][0] == idx[8], out   # exit on the 2nd real close below EMA 50 (not the 1st)
    print("Smart Switch exit memory OK")


def test_climax_never_below_target_on_booking_day():
    idx = [f"2026-01-{k + 1:02d}" for k in range(3)]
    o = np.array([100, 100, 110.0]); h = np.array([101, 101, 125.0]); low = np.array([99, 99, 109.0]); c = np.array([100, 100, 122.0])
    df = S.Candles(idx, o, h, low, c)
    df.e10 = np.array([90.0, 90.0, 95.0])              # climax level 1.20 x 90 = 108 < target 120
    t = _trade("s", idx[0], target=120, stop=50)
    S.manage(t, df, 1)
    S.manage(t, df, 2)
    assert t["status"] == "closed" and all(x["price"] >= 120 for x in t["exits"]), t["exits"]
    print("Climax on booking day OK:", [(x["price"], x["reason"][:14]) for x in t["exits"]])


def test_portfolio_frees_booked_half():
    """The money of the 50% booking comes back on the booking day (as in paper trading)."""
    a = {"status": "closed", "symbol": "A", "name": "A", "entry_date": "2026-01-01", "closed_on": "2026-03-01", "entry": 100, "qty": 10,
         "pnl": 150, "exits": [{"date": "2026-01-10", "qty": 5, "pnl": 100}, {"date": "2026-03-01", "qty": 5, "pnl": 50}]}
    b = {"status": "closed", "symbol": "B", "name": "B", "entry_date": "2026-01-15", "closed_on": "2026-02-01", "entry": 100, "qty": 10,
         "pnl": 0, "exits": [{"date": "2026-02-01", "qty": 10, "pnl": 0}]}
    p = S.portfolio([a, b], "2026-01-01", capital=1000, pct=60)
    assert p["trades"] == 2 and p["skipped"] == 0 and abs(p["final"] - 1090) < 0.01, p   # 600 x 15% = +90
    print("Portfolio frees the booked half OK")


def test_bad_numbers_rejected():
    st = S._clean({"id": "x", "name": "X", "capital": "nan", "pct": "inf"}, {"capital": 500000, "pct": 9})
    assert st["capital"] == 500000 and st["pct"] == 9 and json.dumps(st).find("NaN") < 0
    import alerts
    d = tempfile.mkdtemp()
    store = {"next_id": 1, "alerts": []}
    for k, price in enumerate(("950", "950", "inf", "nan")):
        json.dump({"action": "add", "symbol": "ABC", "op": "above", "price": price}, open(os.path.join(d, f"r{k}.json"), "w"))
    alerts.ingest_requests(store, d, "", "", {"ABC": {"name": "ABC Ltd"}}, {})
    assert len(store["alerts"]) == 1 and store["alerts"][0]["price"] == 950, store   # one alert, no duplicates, no inf/nan
    print("Bad numbers + duplicate alerts OK")


def test_bse_not_found_and_refill():
    import bhav
    import universe
    storage.DATA = tempfile.mkdtemp()
    import pandas as pd
    dates = pd.bdate_range("2025-06-01", "2026-11-05").strftime("%Y-%m-%d").tolist()

    class Ex:
        def __init__(self):
            self.calls, self.fails, self.ok, self.name, self.last = 0, 0, 0, "NSE", "ok"

        def day(self, d):
            self.calls += 1
            return [{"code": "1", "symbol": "OTHER", "series": "EQ", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
    calls = []
    for _ in range(2):
        ex = Ex()
        bhav.enrich({"NEW": {"nse": "OLDNAME", "bse": ""}}, {"NEW": {"t": dates, "c": [10.0] * len(dates)}}, exchanges={"nse": ex, "bse": Ex()})
        calls.append(ex.calls)
    assert calls[0] > 100 and calls[1] == 0, calls      # a code in none of the files is not asked again for a month

    class Ex2:
        def __init__(self, down=()):
            self.fails, self.ok, self.calls, self.down, self.last = 0, 0, 0, set(down), ""

        def day(self, d):
            self.calls += 1
            if d.strftime("%Y-%m-%d") in self.down:
                self.fails += 1
                self.last = "error"
                return None
            self.fails, self.last = 0, "ok"
            return [{"code": c, "open": 10, "high": 10, "low": 10, "close": 10, "volume": 5} for c in ("500001", "500002")]
    storage.DATA = tempfile.mkdtemp()
    universe._bse_days(["500001"], None, today=datetime(2026, 11, 5, 20), limit=40, exchange=Ex2(down={"2026-10-01"}))
    assert not os.path.exists(os.path.join(storage.DATA, "bse_days", "no_file.txt"))   # a network error is not a holiday
    out = {}
    for k in range(25):   # 40 files a run: first the new days, then the old days get the new code
        out = universe._bse_days(["500001", "500002"], None, today=datetime(2026, 11, 6, 20), limit=40, exchange=Ex2())
        if len(out.get("500002", {})) == len(out["500001"]):
            break
    assert len(out["500002"]) == len(out["500001"]) and os.path.exists(os.path.join(storage.DATA, "bse_days", "2026-10-01.csv")), \
        {k: len(v) for k, v in out.items()}
    print("BSE: not-found codes + new codes filled in OK")


def test_bse_split_after_screener_and_real_fall():
    import universe
    import pandas as pd
    dates = pd.bdate_range("2025-06-01", "2026-11-05").strftime("%Y-%m-%d").tolist()
    closes = {d: 100.0 for d in dates if d <= "2026-10-20"}
    days = {d: ((p := 100.0 if d < "2026-10-26" else 50.0), p * 1.01, p * 0.99, p, 1000) for d in dates[-200:]}
    h = universe.bse_chart(closes, days)
    assert h["c"][-1] == 50.0 and abs(h["c"][0] - 50.0) < 0.01, (h["c"][0], h["c"][-1])   # 1:2 split after Screener's days
    # a real 24% fall on a day Screener also shows is NOT a split
    closes2 = {d: (100.0 if d < "2026-04-10" else 76.0) for d in dates}
    days2 = {d: ((p := 100.0 if d < "2026-04-10" else 76.0), p, p, p, 1000) for d in dates[-300:]}
    h2 = universe.bse_chart(closes2, days2)
    assert h2["c"][0] == 100.0 and h2["c"][-1] == 76.0
    # a 20% lower-circuit fall outside Screener's days is NOT a split either (ratio 1.25)
    days3 = {d: ((p := 100.0 if d < "2026-10-26" else 80.0), p, p, p, 1000) for d in dates[-200:]}
    h3 = universe.bse_chart({}, days3)
    assert h3["c"][0] == 100.0 and h3["c"][-1] == 80.0
    print("BSE split / real fall OK")


def test_screener_block_stops_waiting():
    import time
    import fundamentals as fx
    storage.SCREENER["blocked_in_a_row"] = 0
    slept, real = [0], time.sleep
    time.sleep = lambda s: slept.__setitem__(0, slept[0] + s)

    class R:
        status_code, text = 429, ""

    class Sess:
        def get(self, *a, **k):
            return R()
    try:
        for k in range(5):
            assert fx.fetch_metrics(f"X{k}", True, session=Sess()) is None
    finally:
        time.sleep = real
        storage.SCREENER["blocked_in_a_row"] = 0
    assert slept[0] < 200, slept[0]
    print("Screener block: stops waiting OK")


def test_telegram_long_line_cut_at_comma():
    import telegram
    line = ", ".join(f"<b>STOCK{k}</b> &amp; co" for k in range(400))
    parts = telegram._chunks(line)
    assert len(parts) > 1 and all(p.count("<b>") == p.count("</b>") for p in parts)
    print("Telegram long line OK")


if __name__ == "__main__":
    test_no_stop_missed_after_long_gap()
    test_no_candle_twice()
    test_catch_up_in_date_order()
    test_switch_forgets_other_mode()
    test_climax_never_below_target_on_booking_day()
    test_portfolio_frees_booked_half()
    test_bad_numbers_rejected()
    test_bse_not_found_and_refill()
    test_bse_split_after_screener_and_real_fall()
    test_screener_block_stops_waiting()
    test_telegram_long_line_cut_at_comma()
    print("ALL REVIEW TESTS PASSED")
