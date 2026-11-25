"""Fairer test of ONE strategy (Smart Switch on the SP list) before real money - added 24 Nov 2026.

The normal backtest has two weak points:
  * hindsight: it trades TODAY's SP / stock list on past years (those stocks are in the list because they did well);
  * tuning: rules were picked by looking at the same years they are judged on.
This test answers four questions and saves the answers in data/robust_test.json:
  1. Walk-forward: choose the best buy-stop / gap limit using 2017-2022 only, then see how that choice and the live rule
     did on 2023-today (years the choice did not look at).
  2. Stability: the result for every buy-stop / gap-limit pair next to each other (similar numbers = a real edge,
     one spike = luck).
  3. Costs: the live rule with double trading costs (0.4% per side instead of 0.2%).
  4. Hindsight filter: on the bigger stock list, only trades where the stock was in the top 20% by 3-month price
     strength ON THE BUY DAY (something you could have known then), instead of "in today's list".
It runs on the weekly stock-list backtest day (when both price sets are downloaded) and when TEST_VERSION changes.
"""
import storage
import strategy

OUT = "robust_test.json"
TEST_VERSION = "3"             # 3 = with tight-base rule 2b (bodies <= 5%), 25 Nov 2026; 2 = with the 15% pause rule (24 Nov 2026)
STRATEGY_ID = "switch"                     # Smart Switch (SP list)
TRIGGERS = (0.005, 0.01, 0.015)            # buy-stop above the resistance
GAPS = (0.03, 0.05, None)                  # gap-up limit (None = no limit)
IN_SAMPLE, OUT_SAMPLE = ("2017-01-01", "2023-01-01"), ("2023-01-01", "9999")
RS_DAYS, RS_TOP = 63, 0.80                 # 3-month return, top 20% of the stock list on the buy day


def due(today):
    old = storage.load_json(OUT, {})
    return old.get("version") != TEST_VERSION or old.get("as_of", "")[:10] < _week_ago(today)


def _week_ago(today):
    from datetime import date, timedelta
    return (date.fromisoformat(today) - timedelta(days=7)).isoformat()


def _row(trades, st, a, b, pause=None, mood=None):
    cap, pct = float(st.get("capital", strategy.DEF_CAPITAL)), float(st.get("pct", strategy.DEF_PCT))
    p = strategy.portfolio(trades, a, b, capital=cap, pct=pct, rank=st.get("rank"), pause_dd=pause, mood=mood)
    return {k: p.get(k) for k in ("return_pct", "max_drawdown_pct", "trades", "win_rate") + (("pauses",) if pause else ())}


def _years(trades, st, first, last):
    cap, pct = float(st.get("capital", strategy.DEF_CAPITAL)), float(st.get("pct", strategy.DEF_PCT))
    return {str(y): strategy.portfolio(trades, f"{y}-01-01", f"{y + 1}-01-01", capital=cap, pct=pct,
                                       rank=st.get("rank"))["return_pct"] for y in range(first, last + 1)}


def _cagr(ret_pct, a, b, today):
    """Yearly growth rate from a total return over a period (so 6 years and 4 years can be compared)."""
    from datetime import date
    end = today if b == "9999" else b
    yrs = max((date.fromisoformat(end) - date.fromisoformat(a)).days / 365.25, 0.1)
    return round(((1 + ret_pct / 100) ** (1 / yrs) - 1) * 100, 1) if ret_pct is not None and ret_pct > -100 else None


def strong_on_day(charts):
    """{symbol: set of dates on which the stock's 3-month return was in the top 20% of all stocks with prices}."""
    import pandas as pd
    cols = {}
    for sym, h in charts.items():
        if h and h.get("t") and h.get("c"):
            s = pd.Series(h["c"], index=h["t"], dtype="float64")
            cols[sym] = s[~s.index.duplicated()]
    if not cols:
        return {}
    df = pd.DataFrame(cols).sort_index().ffill(limit=5)
    rank = df.pct_change(RS_DAYS, fill_method=None).rank(axis=1, pct=True)
    out = {}
    for sym in rank.columns:
        col = rank[sym]
        out[sym] = set(col.index[col.shift(1) >= RS_TOP])   # strength known at the close BEFORE the buy day
    return out


def only_strong(trades, strong):
    return [t for t in trades if t["entry_date"] in strong.get(t["symbol"], ())]


def _trades(st, charts, names, syms, mood):
    """All trade sets the test needs (each a full backtest): every buy-stop / gap pair, and the live rule with double costs."""
    live_key = (strategy.trigger_of(st), strategy.gap_of(st))
    sets = {live_key: strategy.backtest(st, charts, names, syms, mood=mood)}
    for tr in TRIGGERS:
        for gp in GAPS:
            if (tr, gp) not in sets:
                sets[(tr, gp)] = strategy.backtest_with({"TRIGGER_ABOVE": tr, "MAX_GAP": gp}, st, charts, names, syms, mood=mood)
    double = strategy.backtest_with({"COST_PER_SIDE": strategy.COST_PER_SIDE * 2}, st, charts, names, syms, mood=mood)
    return {"live_key": live_key, "sets": sets, "double": double, "stocks": len(syms)}


def _summary(st, tr_sets, today, now_year, strong=None, mood=None):
    f = (lambda tt: only_strong(tt, strong)) if strong is not None else (lambda tt: tt)
    grid = []
    for (tr, gp), tt in tr_sets["sets"].items():
        tt = f(tt)
        r_in, r_out = _row(tt, st, *IN_SAMPLE), _row(tt, st, *OUT_SAMPLE)
        grid.append({"trigger_pct": round(tr * 100, 2), "gap_pct": None if gp is None else round(gp * 100, 2),
                     "live": (tr, gp) == tr_sets["live_key"],
                     "in": dict(r_in, cagr=_cagr(r_in["return_pct"], *IN_SAMPLE, today)),
                     "out": dict(r_out, cagr=_cagr(r_out["return_pct"], *OUT_SAMPLE, today))})
    grid.sort(key=lambda g: (g["trigger_pct"], 999 if g["gap_pct"] is None else g["gap_pct"]))
    # choice made with 2017-2022 only: best return per unit of drawdown
    best = max(grid, key=lambda g: (g["in"]["return_pct"] or -1e9) / max(g["in"]["max_drawdown_pct"] or 1, 1))
    live = next(g for g in grid if g["live"])
    lv = f(tr_sets["sets"][tr_sets["live_key"]])
    return {"stocks": tr_sets["stocks"], "grid": grid,
            "walk_forward": {"chosen_on_2017_2022": {"trigger_pct": best["trigger_pct"], "gap_pct": best["gap_pct"]},
                             "chosen_in": best["in"], "chosen_out": best["out"], "live_in": live["in"], "live_out": live["out"]},
            "costs": {"normal": _row(lv, st, IN_SAMPLE[0], "9999"), "double": _row(f(tr_sets["double"]), st, IN_SAMPLE[0], "9999")},
            # safety rule (24 Nov 2026): pause new buys after a 15% fall, until the Smallcap 100 is above its EMA 50
            "pause_rule": {"without": _row(lv, st, IN_SAMPLE[0], "9999"),
                           "with_15pct_pause": _row(lv, st, IN_SAMPLE[0], "9999", pause=0.15, mood=mood),
                           "with_10pct_pause": _row(lv, st, IN_SAMPLE[0], "9999", pause=0.10, mood=mood)},
            "by_year": _years(lv, st, int(IN_SAMPLE[0][:4]), now_year)}


def run(strat_cfg, sp_charts, sp_names, sp_syms, list_charts, list_names, mood, today, now_year):
    st = next((s for s in strat_cfg.get("strategies", []) if s.get("id") == STRATEGY_ID), None)
    if not st:
        return None
    out = {"version": TEST_VERSION, "as_of": today, "strategy": st.get("name"),
           "rules": {"trigger_pct": strategy.trigger_of(st) * 100, "gap_pct": (strategy.gap_of(st) or 0) * 100 or None,
                     "max_risk_pct": strategy.MAX_RISK * 100, "cost_per_side_pct": strategy.COST_PER_SIDE * 100},
           "periods": {"in_sample": IN_SAMPLE, "out_of_sample": OUT_SAMPLE}}
    out["sp_list"] = _summary(st, _trades(st, sp_charts, sp_names, sp_syms, mood), today, now_year, mood=mood)
    if list_charts:
        tl = _trades(st, list_charts, list_names, sorted(list_charts), mood)
        out["stock_list"] = _summary(st, tl, today, now_year, mood=mood)
        out["stock_list_strong_only"] = _summary(st, tl, today, now_year, strong=strong_on_day(list_charts), mood=mood)
    storage.save_json(OUT, out)
    return out
