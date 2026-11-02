"""Offline test: python tests/test_robot.py  (no internet, no secrets needed)."""
import os
import shutil
import sys
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import emails  # noqa: E402
import fundamentals as fx  # noqa: E402
import main  # noqa: E402
import prices  # noqa: E402
import storage  # noqa: E402
import telegram as tg  # noqa: E402
import web  # noqa: E402

GOOD = fx.parse_company_page(open(os.path.join(HERE, "fixtures", "company_page.html")).read())
# 2.5/6 marks = 4.6/11: below the 5/11 bar (sales growth, EPS, FII/DII and shareholders fail)
WEAK = {**GOOD, "sales_growth_qtr_yoy": 10.0, "eps_latest_qtr": 5.0, "fii_dii_latest": 3.0, "shareholders_latest": 6000.0}
LOW = WEAK
# exactly 3/6 marks = 5.5/11: passes the 5/11 bar
MID = {**GOOD, "sales_growth_qtr_yoy": 10.0, "eps_latest_qtr": 5.0, "fii_dii_latest": 3.0}


def run(day, mode, metrics_by_code, price_by_ticker, email_stocks):
    main.datetime = type("D", (), {"now": staticmethod(lambda tz=None: datetime(2026, 11, day, 7, 0, tzinfo=tz))})
    emails.fetch_alert_stocks = lambda *a, **k: (email_stocks, ["<id>"], {"52W High": len(email_stocks)})
    fx.fetch_metrics = lambda code, *a, **k: metrics_by_code.get(code, GOOD)
    prices.close_and_ema = lambda tickers, period=200: {t: price_by_ticker.get(t, (110, 100, "01 Nov 2026")) for t in tickers}
    sent = []
    tg.send = lambda token, chat, text: sent.append(text)
    os.environ.update(GMAIL_ADDRESS="x", GMAIL_APP_PASSWORD="y")
    sys.argv = ["main.py", mode]
    main.main()
    return sent[0]


def test_real_stocks():
    """Marks on real Screener numbers (02 Nov 2026) for the 6 starting stocks."""
    import yaml
    import real_stocks
    cfg = yaml.safe_load(open(os.path.join(HERE, "..", "config", "rules.yaml")))
    expected = {"RATNAVEER": 4.5, "SHANTIGOLD": 4.5, "PATELRMART": 4.0,
                "SUPREMEPWR": 5.5, "EIMCOELECO": 4.0, "SAHANA": 4.0}
    for sym, d in real_stocks.STOCKS.items():
        m = fx.parse_company_page(real_stocks.to_html(d))
        got, out_of, _ = fx.score(m, cfg)
        assert (got, out_of) == (expected[sym], 6.0), (sym, got)
    # Supreme Power's table mixes quarters and half-years: Jun 2026 must be compared with Jun 2025
    m = fx.parse_company_page(real_stocks.to_html(real_stocks.STOCKS["SUPREMEPWR"]))
    assert m["sales_growth_qtr_yoy"] == round((51.06 - 38.23) / 38.23 * 100, 2)
    assert fx.on_full_scale(4.5, 6, cfg) == 8.3
    print("Real-stock marks OK:", expected)


def test():
    tmp = tempfile.mkdtemp()
    shutil.copytree(os.path.join(HERE, "..", "data"), os.path.join(tmp, "data"))
    storage.DATA = os.path.join(tmp, "data")
    web.OUT = os.path.join(tmp, "docs", "index.html")

    em = {
        "MEGAFLEX": {"code": "MEGAFLEX", "name": "Mega Flex Plast.", "consolidated": False, "sources": ["TTM Profit > 30%", "52W High"]},
        "544442": {"code": "544442", "name": "Chemkart India", "consolidated": True, "sources": ["Daily Volume Scan"]},
        "SAHANA": {"code": "SAHANA", "name": "Sahana System", "consolidated": True, "sources": ["52W High"]},
        "MIDCO": {"code": "MIDCO", "name": "Mid Score Co", "consolidated": True, "sources": ["Weekly Volume Scan"]},
        "LOWCO": {"code": "LOWCO", "name": "Low Score Co", "consolidated": True, "sources": ["Weekly Volume Scan"]},
    }
    # Day 2: Chemkart fails fundamentals, Megaflex passes; SAHANA already in SP.
    # RATNAVEER closes below EMA -> DT
    msg = run(2, "auto", {"544442": WEAK, "MIDCO": MID, "LOWCO": LOW}, {"RATNAVEER.NS": (480, 520, "01 Nov 2026")}, em)
    sp, dt = storage.load_list("SP"), storage.load_list("DT")
    assert "MEGAFLEX" in sp and "MIDCO" in sp and "544442" not in sp and "LOWCO" not in sp, sp.keys()
    assert "RATNAVEER" in dt and "RATNAVEER" not in sp
    assert "SAHANA" in sp
    print(msg, "\n" + "=" * 60)

    # Day 3: RATNAVEER back above EMA -> SP
    msg = run(3, "daily", {}, {"RATNAVEER.NS": (540, 521, "02 Nov 2026"), "SHANTIGOLD.NS": (90, 95, "02 Nov 2026")}, {})
    sp, dt = storage.load_list("SP"), storage.load_list("DT")
    assert "RATNAVEER" in sp and "SHANTIGOLD" in dt
    print(msg, "\n" + "=" * 60)

    # 1st of month: PATELRMART (4.6/11) removed from SP, SHANTIGOLD (4.6/11) removed from DT, SAHANA (5.5/11) stays
    msg = run(1, "auto", {"PATELRMART": WEAK, "SHANTIGOLD": LOW, "SAHANA": MID}, {"SHANTIGOLD.NS": (90, 95, "31 Oct 2026")}, {})
    sp, dt = storage.load_list("SP"), storage.load_list("DT")
    assert "PATELRMART" not in sp and "SHANTIGOLD" not in dt and "SAHANA" in sp
    print(msg)
    print("\nHistory log:\n" + open(os.path.join(storage.DATA, "history.csv")).read())
    assert os.path.exists(web.OUT)
    print("Web page:", web.OUT)
    print("\nALL TESTS PASSED")
    return tmp


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    test_real_stocks()
    test()
