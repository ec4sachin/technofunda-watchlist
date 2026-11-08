"""Smallcap market health: Edge factor = (Win% / Loss%) x (Avg gain% / Avg loss%) from your closed paper trades."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import strategy  # noqa: E402


def trades(pcts, start=1):
    return [{"status": "closed", "pnl_pct": p, "closed_on": f"2026-11-{start + i:02d}", "strategy": "swing"} for i, p in enumerate(pcts)]


def test():
    # 6 wins avg +10%, 4 losses avg -5%: (60/40) x (10/5) = 3.0 -> Healthy
    h = strategy.edge(trades([10] * 6 + [-5] * 4))
    assert (h["edge"], h["status"], h["win_pct"], h["avg_gain"], h["avg_loss"]) == (3.0, "healthy", 60.0, 10.0, 5.0), h
    # 4 wins +6%, 6 losses -5%: (40/60) x (6/5) = 0.8 -> Weak
    h = strategy.edge(trades([6] * 4 + [-5] * 6))
    assert h["edge"] == 0.8 and h["status"] == "weak"
    # 5 / 5, +8 / -5: 1.6 -> Neutral; exactly 2 is Neutral too (Healthy is above 2), exactly 1 is Neutral (Weak is below 1)
    assert strategy.edge(trades([8] * 5 + [-5] * 5))["status"] == "neutral"
    assert strategy.edge(trades([10] * 5 + [-5] * 5))["edge"] == 2.0 and strategy.edge(trades([10] * 5 + [-5] * 5))["status"] == "neutral"
    assert strategy.edge(trades([5] * 5 + [-5] * 5))["status"] == "neutral"
    # under 10 trades: number shown, no verdict
    h = strategy.edge(trades([10, -5, 4]))
    assert h["status"] == "few" and h["trades"] == 3
    # no trades / no losses / no wins
    assert strategy.edge([])["status"] == "waiting" and strategy.edge(None)["edge"] is None
    h = strategy.edge(trades([5] * 12))
    assert h["edge"] is None and h["status"] == "healthy"
    assert strategy.edge(trades([-3] * 12))["edge"] == 0.0 and strategy.edge(trades([-3] * 12))["status"] == "weak"
    # only the latest 30 closed trades count (old bad trades drop out); open trades are left out
    old = trades([-5] * 20, start=1)
    new = [dict(t, closed_on="2026-12-%02d" % (i + 1)) for i, t in enumerate(trades([10] * 20 + [-5] * 10))]
    h = strategy.edge(old + new + [{"status": "open", "pnl_pct": None}])
    assert h["trades"] == 30 and h["wins"] == 20 and h["edge"] == 4.0, h
    print("Edge factor OK")


def test_message():
    import main
    st = {"health": strategy.edge(trades([10] * 6 + [-5] * 4)), "capital": {}, "entries": [], "exits": []}
    msg = "\n".join(main.strategy_lines(st))
    assert "Smallcap market health" in msg and "🟢 Healthy" in msg and "Edge factor <b>3</b>" in msg and "won 60%" in msg, msg
    msg = "\n".join(main.strategy_lines({"health": strategy.edge([])}))
    assert "No closed trades yet" in msg
    print("Health on Telegram OK")


if __name__ == "__main__":
    test()
    test_message()
