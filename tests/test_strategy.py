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
    # rule 4: an old high only 5% above entry -> skip
    c4 = list(closes); c4[len(c4) - 20] = plan["trigger"] * 1.05 / 1.004
    assert stg.swing_setup(stg._frame(hist_from(c4)), len(c4) - 1) is None
    # rule 6: an old high within 1% of the entry -> take it (breakout through the old resistance)
    c6 = list(closes); c6[len(c6) - 20] = plan["trigger"] * 1.005 / 1.004
    assert stg.swing_setup(stg._frame(hist_from(c6)), len(c6) - 1) is not None

    settings = {"strategies": [{"id": "swing", "name": "Swing Strategy", "type": "swing", "list": "SP", "amount": 25000, "on": True}]}
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
    assert t["qty"] == int(25000 // trig) and t["stop"] == stop and t["target"] == round(trig * 1.2, 2)
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

    # OFF strategy does nothing; settings requests are validated
    off = {"strategies": [dict(settings["strategies"][0], on=False)]}
    assert stg.run(off, {}, {"ABC": h1}, sp, {})["entries"] == []
    data = stg.load_settings()
    assert data["strategies"][0]["id"] == "swing" and data["strategies"][0]["on"] is False
    assert stg.apply_request(data, {"action": "strategy_save", "strategy": {"id": "swing", "name": "Swing Strategy", "on": True, "amount": "50000"}}, "2026-11-05")
    assert data["strategies"][0]["on"] and data["strategies"][0]["amount"] == 50000 and data["strategies"][0]["on_since"] == "2026-11-05"
    assert stg.apply_request(data, {"action": "strategy_save", "strategy": {"id": "s1", "name": "<b>X</b>" * 20, "type": "evil", "list": "ALL"}})
    s1 = data["strategies"][1]
    assert len(s1["name"]) == 40 and s1["type"] == "none" and s1["list"] == "SP"
    assert not stg.apply_request(data, {"action": "strategy_save", "strategy": {"id": "../x", "name": "a"}})
    assert stg.apply_request(data, {"action": "strategy_delete", "id": "s1"}) and len(data["strategies"]) == 1
    print("Strategy settings OK")


if __name__ == "__main__":
    test()
