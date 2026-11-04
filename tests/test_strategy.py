"""Swing Strategy rules on made-up prices: setup, buy-stop entry, stop loss, 50% at +20%, EMA-10 trailing exit."""
import os
import sys
import tempfile

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import pandas as pd  # noqa: E402
import storage  # noqa: E402
import strategy as stg  # noqa: E402


def hist_from(closes, rng=0.004):
    t = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2025-01-01", periods=len(closes))]
    o = [closes[i - 1] if i else closes[0] for i in range(len(closes))]
    h = [max(o[i], closes[i]) * (1 + rng) for i in range(len(closes))]
    l = [min(o[i], closes[i]) * (1 - rng) for i in range(len(closes))]
    return {"t": t, "o": o, "h": h, "l": l, "c": list(closes)}


def uptrend_then_base(n_up=260, base=4):
    # steady rise (EMAs stack 10>20>50>200), then a short pullback-free flat base near the high
    closes = [100 * (1.004 ** i) for i in range(n_up)]
    top = closes[-1]
    closes += [top * x for x in (0.995, 1.0, 0.998, 1.001)][:base]
    return closes


def test():
    storage.DATA = tempfile.mkdtemp()
    closes = uptrend_then_base()
    h = hist_from(closes)
    df = stg._frame(h)
    plan = stg.swing_setup(df, len(df) - 1)
    assert plan, "setup expected after a steady uptrend + tight 4-candle base"
    assert plan["range_pct"] <= 6 and plan["trigger"] == round(max(h["h"][-4:]) * 1.01, 2)
    # rule 3: stretched far above EMA 10 -> no setup
    hs = hist_from(closes[:-1] + [closes[-1] * 1.2])
    assert stg.swing_setup(stg._frame(hs), len(hs["t"]) - 1) is None
    # version 5: the 42-candle room rule is off -> an old high 5% above entry no longer blocks the trade
    c4 = list(closes); c4[len(c4) - 20] = plan["trigger"] * 1.05 / 1.004
    assert stg.swing_setup(stg._frame(hist_from(c4)), len(c4) - 1) is not None
    # stop = 1% below the base low, but never more than 6% below the buy price
    assert plan["stop"] == round(max(min(h["l"][-4:]) * 0.99, plan["trigger"] * 0.94), 2), plan
    wide = list(closes[:-4]) + [closes[-5] * x for x in (0.95, 1.0, 0.96, 1.0)]   # ~5.5% deep base
    pw = stg.swing_setup(stg._frame(hist_from(wide)), len(wide) - 1)
    if pw:
        assert (pw["trigger"] - pw["stop"]) / pw["trigger"] <= 0.0601, pw

    settings = {"strategies": [{"id": "swing", "name": "Swing Strategy", "type": "swing", "list": "SP", "capital": 1000000, "pct": 10, "on": True}]}
    sp = {"ABC": {"name": "ABC Ltd"}}
    book = {}
    # day 0: strategy switched ON -> no backfill, just today's setups
    ev = stg.run(settings, book, {"ABC": h}, sp, {})
    assert not ev["entries"] and ev["setups"]["swing"][0]["buy_above"] == plan["trigger"]
    trig, stop = plan["trigger"], plan["stop"]
    # day 1: breakout above the trigger -> paper BUY at the trigger
    c = closes + [trig * 1.01]
    h1 = hist_from(c); h1["o"][-1] = closes[-1]; h1["h"][-1] = trig * 1.015
    ev = stg.run(settings, book, {"ABC": h1}, sp, {})
    assert len(ev["entries"]) == 1 and ev["entries"][0]["price"] == trig, ev
    t = book["open"][0]
    assert t["qty"] == int(100000 // trig) and t["stop"] == stop and t["target"] == round(trig * 1.2, 2)  # 10% of ₹10 lakh
    # days 2..: rally to +20% -> 50% booked; then a close below EMA 10 and a break of that low -> rest sold
    up = [trig * (1 + 0.02 * k) for k in range(1, 12)]       # reaches +22%
    c2 = c + up
    h2 = hist_from(c2)
    ev = stg.run(settings, book, {"ABC": h2}, sp, {})
    assert t["booked"] and any("Target" in x["reason"] for x in ev["exits"]) and t["remaining"] == t["qty"] - t["qty"] // 2
    down = [up[-1] * 0.93, up[-1] * 0.90]                     # close below EMA 10, then break its low
    h3 = hist_from(c2 + down, rng=0.002)
    ev = stg.run(settings, book, {"ABC": h3}, sp, {})
    assert t["status"] == "closed" and any("Trailing" in x["reason"] for x in ev["exits"]), (t, ev)
    assert book["closed"][0]["pnl"] > 0 and not book["open"]
    cap = book["capital"]["swing"]
    assert cap["equity"] == round(1000000 + book["closed"][0]["pnl"], 2) and cap["cash"] == cap["equity"]  # capital grew
    assert book["realized"]["swing"] == book["closed"][0]["pnl"]
    assert all("charges" in x and x["charges"] > 0 for x in t["exits"])   # costs are taken off
    print("Swing: entry", trig, "| exits", [(x["reason"], x["price"]) for x in t["exits"]], "| P&L", t["pnl"])

    # stop loss: breakout then fall below the base low
    book2 = {}
    stg.run(settings, book2, {"ABC": h}, sp, {})
    stg.run(settings, book2, {"ABC": h1}, sp, {})
    hl = hist_from(c + [stop * 0.97]); hl["l"][-1] = stop * 0.96; hl["o"][-1] = c[-1]
    ev = stg.run(settings, book2, {"ABC": hl}, sp, {})
    tr = book2["closed"][0]
    assert tr["exits"][0]["reason"].startswith("Stop") and tr["exits"][0]["price"] == stop and tr["pnl"] < 0
    print("Stop loss OK:", tr["exits"][0])

    # time stop: breakout, then 10 flat days under +3% -> sold at the close
    book3 = {}
    stg.run(settings, book3, {"ABC": h}, sp, {})
    stg.run(settings, book3, {"ABC": h1}, sp, {})
    flat = c + [trig * 1.01] * 10
    stg.run(settings, book3, {"ABC": hist_from(flat, rng=0.002)}, sp, {})
    t3 = book3["closed"][0]
    assert t3["exits"][0]["reason"].startswith("Time stop") and t3["hold_days"] is not None, t3["exits"]
    print("Time stop OK:", t3["exits"][0]["reason"], t3["exits"][0]["price"])

    # OFF strategy does nothing; settings requests are validated
    off = {"strategies": [dict(settings["strategies"][0], on=False)]}
    assert stg.run(off, {}, {"ABC": h1}, sp, {})["entries"] == []
    data = stg.load_settings()
    assert data["strategies"][0]["id"] == "swing" and data["strategies"][0]["on"] is False
    assert stg.apply_request(data, {"action": "strategy_save", "strategy": {"id": "swing", "name": "Swing Strategy", "on": True, "capital": "2000000", "pct": 5}}, "2026-11-05")
    assert data["strategies"][0]["on"] and data["strategies"][0]["capital"] == 2000000 and data["strategies"][0]["pct"] == 5 and data["strategies"][0]["on_since"] == "2026-11-05"
    assert stg.apply_request(data, {"action": "strategy_save", "strategy": {"id": "s1", "name": "<b>X</b>" * 20, "type": "evil", "list": "ALL"}})
    s1 = data["strategies"][1]
    assert len(s1["name"]) == 40 and s1["type"] == "none" and s1["list"] == "SP"
    assert not stg.apply_request(data, {"action": "strategy_save", "strategy": {"id": "../x", "name": "a"}})
    assert stg.apply_request(data, {"action": "strategy_delete", "id": "s1"}) and len(data["strategies"]) == 1
    # portfolio: one money pot, 10% of current capital per trade, skip when no free cash
    tr = [{"status": "closed", "symbol": f"S{i}", "name": f"S{i}", "entry_date": f"2026-01-{i + 1:02d}", "closed_on": "2026-03-01",
           "entry": 100.0, "qty": 10, "pnl": 100.0} for i in range(12)]                       # 12 trades of +10% at once
    pf = stg.portfolio(tr, "2025-01-01")
    assert pf["trades"] == 10 and pf["skipped"] == 2 and pf["final"] == 1100000.0, pf             # only 10 fit in the money
    tr2 = [dict(tr[0], entry_date="2026-01-01", closed_on="2026-01-10"), dict(tr[1], entry_date="2026-02-01", closed_on="2026-02-10")]
    pf2 = stg.portfolio(tr2, "2025-01-01")
    assert pf2["final"] == round(1000000 + 10000 + 101000 * 0.1, 2), pf2                          # 2nd trade uses the grown capital
    print("Strategy settings + capital OK")


if __name__ == "__main__":
    test()


def test_split_adjust():
    """Unadjusted split / bonus (V-Marc 1:6, Simplex 1:5) and a single bad price day are fixed."""
    import prices
    idx = pd.bdate_range("2026-01-01", periods=8)
    df = pd.DataFrame({"Open": [100, 101, 102, 103, 17.3, 17.5, 17.6, 17.7], "High": [101, 102, 103, 104, 17.6, 17.8, 17.9, 18],
                       "Low": [99, 100, 101, 102, 17.0, 17.2, 17.3, 17.4], "Close": [100, 101, 102, 103.8, 17.4, 17.6, 17.7, 17.8]}, index=idx)
    adj, notes = prices.adjust_corporate_actions(df)
    assert "1:6" in notes[0] and abs(adj["Close"].iloc[3] - 103.8 / 6) < 0.01 and adj["Close"].iloc[-1] == 17.8, notes
    # Simplex Castings case: opened 4.2x lower and closed 5.07x lower -> 1:5
    df2 = pd.DataFrame({"Open": [534.7, 124.6, 102.0], "High": [534.7, 124.6, 103.95], "Low": [510.05, 102.0, 95.95],
                        "Close": [519.25, 102.45, 100.25]}, index=idx[:3])
    assert "1:5 " in prices.adjust_corporate_actions(df2)[1][0] + " "
    # one bad day that comes straight back is ignored
    df3 = pd.DataFrame({"Close": [10.0, 10.2, 2.0, 10.3, 10.4]}, index=idx[:5])
    a3, n3 = prices.adjust_corporate_actions(df3)
    assert "bad price day" in n3[0] and a3["Close"].iloc[2] == 10.2 and a3["Close"].iloc[0] == 10.0
    # a normal 20% move is left alone
    assert prices.adjust_corporate_actions(pd.DataFrame({"Close": [10.0, 12.0, 12.5]}, index=idx[:3]))[1] == []
    print("Split / bonus adjustment OK")


if __name__ == "__main__":
    test_split_adjust()
