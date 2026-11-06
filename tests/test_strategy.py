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
    assert plan, "setup expected after a steady uptrend + tight base"
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

    # Positional Trading: same entry, 50% at +30%, the rest exits after 5 closes below EMA 50 in a row, no time stop
    pos = {"strategies": [{"id": "positional", "name": "Positional Trading", "type": "positional", "list": "SP",
                           "capital": 1000000, "pct": 10, "on": True}]}
    bp = {}
    stg.run(pos, bp, {"ABC": h}, sp, {})
    stg.run(pos, bp, {"ABC": h1}, sp, {})
    tp = bp["open"][0]
    assert tp["target"] == round(trig * 1.3, 2) and tp["type"] == "positional"
    stg.run(pos, bp, {"ABC": hist_from(c + [trig * 1.01] * 12, rng=0.002)}, sp, {})
    assert bp["open"] and not bp["open"][0]["exits"]                       # flat for 12 days: no time stop
    rally = c + [trig * 1.01] * 12 + [trig * (1 + 0.025 * k) for k in range(1, 15)]   # reaches +35%
    stg.run(pos, bp, {"ABC": hist_from(rally)}, sp, {})
    assert tp["booked"] and "Target +30%" in tp["exits"][0]["reason"]
    fall = rally + [rally[-1] * f for f in (0.97, 0.94, 0.90, 0.86, 0.82, 0.80, 0.78, 0.77, 0.76, 0.75, 0.74, 0.73)]
    df_f = stg._frame(hist_from(fall))
    stg.run(pos, bp, {"ABC": hist_from(fall)}, sp, {})
    assert tp["status"] == "closed" and "EMA 50" in tp["exits"][-1]["reason"], tp["exits"]
    k = df_f.index.index(tp["exits"][-1]["date"])
    assert all(df_f.c[k - x] < df_f.e50[k - x] for x in range(5)) and df_f.c[k - 5] >= df_f.e50[k - 5]   # sold on the 5th close below
    print("Positional OK:", [(x["reason"], x["price"]) for x in tp["exits"]], "P&L", tp["pnl"])

    # Smart Switch: Smallcap 100 above EMA 50 on the day before the buy -> Positional exits, below -> Swing exits
    import market
    sw = {"strategies": [{"id": "switch", "name": "Smart Switch", "type": "switch", "list": "SP", "capital": 1000000, "pct": 10, "on": True}]}
    for trend, want, tgt in ((1.003, "positional", 1.3), (0.997, "swing", 1.2)):
        idx = {"t": h1["t"], "c": [10000 * trend ** k for k in range(len(h1["t"]))]}
        mood = market.Mood(idx)
        bs = {}
        stg.run(sw, bs, {"ABC": h}, sp, {}, mood=mood)
        ev = stg.run(sw, bs, {"ABC": h1}, sp, {}, mood=mood)
        ts = bs["open"][0]
        assert ts["type"] == want and ts["target"] == round(trig * tgt, 2) and "Smallcap 100" in ts["regime"], (ts["type"], ts["regime"])
        assert bs["mood"]["switch"]["rules"] == ("Positional" if want == "positional" else "Swing")
        assert ev["log"][0]["reason"].endswith(("Positional exits", "Swing exits"))
    # daily switching: bought as Swing (index weak), index turns strong -> Positional (target +30%)
    n = len(h1["t"])
    weak_then_strong = {"t": h1["t"] + [f"2027-01-{k:02d}" for k in range(1, 29)],
                        "c": [10000 * 0.997 ** k for k in range(n)] + [10000 * 0.997 ** n * 1.02 ** k for k in range(1, 29)]}
    mood = market.Mood(weak_then_strong)
    bs = {}
    stg.run(sw, bs, {"ABC": h}, sp, {}, mood=mood)
    stg.run(sw, bs, {"ABC": h1}, sp, {}, mood=mood)
    ts = bs["open"][0]
    assert ts["type"] == "swing" and ts["switch"]
    hx = hist_from(c + [trig * 1.01] * 3, rng=0.002)
    hx["t"] = h1["t"] + ["2027-01-05", "2027-01-06", "2027-01-07"]
    ev = stg.run(sw, bs, {"ABC": hx}, sp, {}, mood=mood)
    assert ts["type"] == "positional" and ts["target"] == round(ts["entry"] * 1.3, 2), (ts["type"], ts.get("switches"))
    assert ev.get("switched") and ev["switched"][0]["to"] == "positional"
    print("Daily switch OK:", ts["switches"])
    # no index data -> Swing exits (the safer, faster rules)
    bs = {}
    stg.run(sw, bs, {"ABC": h}, sp, {}, mood=None)
    stg.run(sw, bs, {"ABC": h1}, sp, {}, mood=None)
    assert bs["open"][0]["type"] == "swing" and "unknown" in bs["open"][0]["regime"]
    # NSE daily index file
    nse = ("Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,Closing Index Value,Points Change,Change(%),Volume,Turnover (Rs. Cr.),P/E,P/B,Div Yield\n"
           "Nifty 50,03-11-2026,1,2,0.5,25000.10,1,1,1,1,1,1,1\nNifty Smallcap 100,03-11-2026,18000,18200,17900,18123.45,1,1,1,1,1,1,1\n")
    assert market.parse_nse(nse) == ("2026-11-03", 18123.45)
    print("Smart Switch OK")

    # climax exit: after the 50% booking, the rest is sold when price reaches 1.24x EMA 10 (Swing)
    bc = {}
    stg.run(settings, bc, {"ABC": h}, sp, {})
    stg.run(settings, bc, {"ABC": h1}, sp, {})
    tc = bc["open"][0]
    spike = c + [trig * 1.12 ** k for k in range(1, 8)]               # +12% a day: books +20%, then runs far above EMA 10
    hs = hist_from(spike)
    stg.run(settings, bc, {"ABC": hs}, sp, {})
    assert tc["status"] == "closed" and tc["exits"][-1]["reason"].startswith("Climax exit (1.2× EMA 10"), tc["exits"]   # no index: lower level
    dfs = stg._frame(hs); k = dfs.index.index(tc["exits"][-1]["date"])
    assert tc["exits"][-1]["price"] >= round(dfs.e10[k - 1] * 1.20, 2) - 0.01
    # Smallcap 100 above its EMA 50 -> the higher level (1.24x EMA 10) lets the winner run further
    import market
    strong = market.Mood({"t": hs["t"], "c": [10000 * 1.003 ** k for k in range(len(hs["t"]))]})
    bc2 = {}
    stg.run(settings, bc2, {"ABC": h}, sp, {}, mood=strong)
    stg.run(settings, bc2, {"ABC": h1}, sp, {}, mood=strong)
    stg.run(settings, bc2, {"ABC": hs}, sp, {}, mood=strong)
    t2 = bc2["closed"][0]
    assert t2["exits"][-1]["reason"].startswith("Climax exit (1.24× EMA 10"), t2["exits"]
    print("Climax exit OK:", tc["exits"][-1]["reason"], tc["exits"][-1]["price"])

    # OFF strategy does nothing; settings requests are validated
    off = {"strategies": [dict(settings["strategies"][0], on=False)]}
    assert stg.run(off, {}, {"ABC": h1}, sp, {})["entries"] == []
    data = stg.load_settings()
    assert data["strategies"][0]["id"] == "swing" and data["strategies"][0]["on"] is False
    assert [x["id"] for x in data["strategies"]] == ["swing", "positional", "switch", "growth_switch"]
    assert [x["pct"] for x in data["strategies"]] == [13, 12, 12, 8]
    # a strategies.json saved before Positional existed gets it added; a removed one stays removed
    storage.save_json("strategies.json", {"strategies": [dict(data["strategies"][0], on=True)]})
    assert [x["id"] for x in stg.load_settings()["strategies"]] == ["swing", "positional", "switch", "growth_switch"]
    d2 = stg.load_settings(); stg.apply_request(d2, {"action": "strategy_delete", "id": "positional"}); storage.save_json("strategies.json", d2)
    assert [x["id"] for x in stg.load_settings()["strategies"]] == ["swing", "switch", "growth_switch"]
    os.remove(os.path.join(storage.DATA, "strategies.json"))
    data = stg.load_settings()
    assert stg.apply_request(data, {"action": "strategy_save", "strategy": {"id": "swing", "name": "Swing Strategy", "on": True, "capital": "2000000", "pct": 5}}, "2026-11-05")
    assert data["strategies"][0]["on"] and data["strategies"][0]["capital"] == 2000000 and data["strategies"][0]["pct"] == 5 and data["strategies"][0]["on_since"] == "2026-11-05"
    assert stg.apply_request(data, {"action": "strategy_save", "strategy": {"id": "s1", "name": "<b>X</b>" * 20, "type": "evil", "list": "ALL"}})
    s1 = next(x for x in data["strategies"] if x["id"] == "s1")
    assert len(s1["name"]) == 40 and s1["type"] == "none" and s1["list"] == "SP"
    assert not stg.apply_request(data, {"action": "strategy_save", "strategy": {"id": "../x", "name": "a"}})
    assert stg.apply_request(data, {"action": "strategy_delete", "id": "s1"}) and len(data["strategies"]) == 4
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


def test_index_download():
    """NSE daily index files: 3 years asked once, holidays remembered, nothing asked again next time."""
    import tempfile as _t
    from datetime import datetime as _d, timedelta as _td
    import market
    storage.DATA = _t.mkdtemp()

    class R:
        def __init__(s, code, text=""): s.status_code, s.text = code, text

    class Sess:
        def __init__(s): s.n = 0
        def get(s, url, **k):
            s.n += 1
            dmy = url.split("_")[-1][:8]
            d = _d.strptime(dmy, "%d%m%Y")
            if d.day == 15:  # pretend the 15th is always a holiday
                return R(404)
            return R(200, "Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,Closing Index Value\n"
                          f"Nifty Smallcap 100,{d.strftime('%d-%m-%Y')},1,1,1,{10000 + d.toordinal() % 1000}\n")
    market.time.sleep = lambda s: None
    s1 = Sess()
    h = market._from_nse(days=60, session=s1)
    assert len(h["t"]) > 30 and s1.n >= len(h["t"])
    s2 = Sess()
    market._from_nse(days=60, session=s2)
    assert s2.n <= 7, s2.n          # only the last week is asked again (in case a file was late)
    m = market.Mood(h)
    assert m.now() is None or len(m.now()) == 4
    print("Index download OK:", len(h["t"]), "days, second run asked", s2.n)


if __name__ == "__main__":
    test_index_download()


def test_join_bse_history():
    """BSE prices before the NSE listing are joined in front (scaled to meet on the first common day)."""
    import prices
    bse_idx = pd.bdate_range("2020-01-01", periods=400)
    bse = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": [100.0 + i * 0.1 for i in range(400)]}, index=bse_idx)
    nse = bse.iloc[300:].copy() * 1.002               # NSE starts later, tiny price difference
    joined = prices.join_older(nse, bse)
    assert len(joined) == 400 and joined.index[0] == bse_idx[0] and joined.index.is_monotonic_increasing
    assert abs(joined["Close"].iloc[299] / joined["Close"].iloc[300] - bse["Close"].iloc[299] / bse["Close"].iloc[300]) < 1e-9
    assert prices.join_older(nse, None) is nse and len(prices.join_older(nse, bse.iloc[290:])) == 100  # under 20 older days: not joined
    print("BSE history join OK:", len(joined), "days")


def test_rank_same_day():
    """When money is short, the chosen rank decides which same-day signal is bought."""
    def tr(sym, tight, ret):
        return {"symbol": sym, "name": sym, "entry_date": "2024-01-02", "status": "closed", "closed_on": "2024-02-01",
                "pnl": ret * 1000, "entry": 100.0, "qty": 10, "plan": {"score": {"tight": tight, "strength": 5.0}}}
    trades = [tr("AAA", 5.5, -0.1), tr("ZZZ", 2.0, 0.3)]
    a = stg.portfolio(trades, "2024-01-01", capital=1000, pct=100, rank="alpha")
    t = stg.portfolio(trades, "2024-01-01", capital=1000, pct=100, rank="tight")
    assert a["trades"] == 1 and a["final"] < 1000 and t["final"] > 1000, (a["final"], t["final"])
    assert stg.rank_value({"score": {"strength": 9}}, "strength") < stg.rank_value({"score": {"strength": 2}}, "strength")
    assert stg.rank_value({"score": {}}, "tight") == 1e9
    print("Rank of same-day signals OK")


if __name__ == "__main__":
    test_rank_same_day()
    test_join_bse_history()
