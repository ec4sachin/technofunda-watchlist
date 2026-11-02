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
GOOD["_company_id"] = "999"
# 2.5/6 marks = 4.6/11: below the 5/11 bar (sales growth, EPS, FII/DII and shareholders fail)
WEAK = {**GOOD, "sales_growth_qtr_yoy": 10.0, "eps_latest_qtr": 5.0, "fii_dii_latest": 3.0, "shareholders_latest": 6000.0}
LOW = WEAK
# exactly 3/6 marks = 5.5/11: passes the 5/11 bar
MID = {**GOOD, "sales_growth_qtr_yoy": 10.0, "eps_latest_qtr": 5.0, "fii_dii_latest": 3.0}


def run(day, mode, metrics_by_code, price_by_ticker, email_stocks):
    main.datetime = type("D", (), {"now": staticmethod(lambda tz=None: datetime(2026, 11, day, 7, 0, tzinfo=tz))})
    emails.fetch_alert_stocks = lambda *a, **k: (email_stocks, ["<id>"], {"52W High": len(email_stocks)})
    fx.fetch_metrics = lambda code, *a, **k: metrics_by_code.get(code, GOOD)
    prices.close_and_ema = lambda tickers, period=200: {t: (None if t.endswith(".BO") else price_by_ticker.get(t, (110, 100, "01 Nov 2026"))) for t in tickers}
    prices.screener_close_and_ema = lambda cid, period=200, **k: ((55.0, 60.0, "31 Oct 2026", {"t": ["2026-10-30", "2026-10-31"], "c": [56, 55], "e200": [60, 60], "e50": [57, 56]}) if cid == "999"
                                                                   else (77.0, None, "31 Oct 2026") if cid == "888" else None)
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


class FakeResp:
    def __init__(self, status, text="", payload=None):
        self.status_code, self.text, self._p = status, text, payload

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, **kw):
        self.calls.append(url)
        for key, resp in self.pages.items():
            if url.endswith(key):
                return resp
        return FakeResp(404)


def test_page_choice_and_screener_prices():
    """Shanti Gold case: consolidated page incomplete -> standalone used. BSE/SME price from Screener chart."""
    import real_stocks
    full = real_stocks.to_html(real_stocks.STOCKS["SHANTIGOLD"]).replace(
        "</body>", "<a href='/company/source/quarter/1285561/6/2026/'>Raw PDF</a></body>")
    thin = "<html><body><h1>Shanti Gold</h1><section id='quarters'><table class='data-table'><thead><tr><th></th>" \
           "<th>Mar 2026</th><th>Jun 2026</th></tr></thead><tbody><tr><td>EPS in Rs</td><td>6.77</td><td>6.58</td></tr>" \
           "</tbody></table></section></body></html>"
    sess = FakeSession({"/company/SHANTIGOLD/consolidated/": FakeResp(200, thin),
                        "/company/SHANTIGOLD/": FakeResp(200, full)})
    m = fx.fetch_metrics("SHANTIGOLD", True, session=sess, pause=0)
    assert m["_path"] == "/company/SHANTIGOLD/" and m["_company_id"] == "1285561", m.get("_path")
    assert fx.completeness(m) == len(fx.SCORE_INPUTS)

    import pandas as pd
    base = "/api/company/1285561/chart/?q=Price-DMA50-DMA200-Volume&days="
    days = pd.bdate_range(end="2026-10-30", periods=400)
    vals = [[d.strftime("%Y-%m-%d"), str(100 + i * 0.5)] for i, d in enumerate(days)]
    weekly = {"datasets": [{"metric": "Price", "values": vals[::5], "meta": {"is_weekly": True}}]}
    daily = {"datasets": [{"metric": "Price", "label": "Price on BSE", "values": vals[-250:], "meta": {}},
                          {"metric": "DMA50", "values": []}]}
    # Old company: 730 days comes back weekly, 500 days comes back daily -> daily used
    sess = FakeSession({base + "730": FakeResp(200, payload=weekly), base + "500": FakeResp(200, payload=daily)})
    close, ema, date, hist = prices.screener_close_and_ema("1285561", 200, session=sess, pause=0)
    assert len(hist["t"]) == 250 and len(hist["e200"]) == 250 and hist["c"][-1] == 299.5
    assert close == 299.5 and ema is not None and ema < close and date == "30 Oct 2026", (close, ema, date)
    assert len(sess.calls) == 2
    # New listing: only 120 trading days -> price shown, EMA not possible
    short = {"datasets": [{"metric": "Price", "values": vals[-120:], "meta": {}}]}
    sess = FakeSession({base + "730": FakeResp(200, payload=short)})
    res = prices.screener_close_and_ema("1285561", 200, session=sess, pause=0)
    assert res[:3] == (299.5, None, "30 Oct 2026") and res[3]["e200"] == [] and len(res[3]["e50"]) == 120
    print("Page choice + Screener price fallback OK:", close, ema, date)


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
        "513472": {"code": "513472", "name": "Simplex Castings", "consolidated": False, "sources": ["Weekly Volume Scan"]},
        "544999": {"code": "544999", "name": "New IPO Co", "consolidated": False, "sources": ["52W High"]},
    }
    # Day 2: Chemkart fails fundamentals, Megaflex passes; SAHANA already in SP.
    # RATNAVEER closes below EMA -> DT
    msg = run(2, "auto", {"544442": WEAK, "MIDCO": MID, "LOWCO": LOW, "544999": {**GOOD, "_company_id": "888"}}, {"RATNAVEER.NS": (480, 520, "01 Nov 2026")}, em)
    sp, dt = storage.load_list("SP"), storage.load_list("DT")
    assert "MEGAFLEX" in sp and "MIDCO" in sp and "544442" not in sp and "LOWCO" not in sp, sp.keys()
    assert "RATNAVEER" in dt and "RATNAVEER" not in sp
    assert "SAHANA" in sp
    import json as _j
    # BSE stock: no Yahoo price -> Screener chart price used (55 < EMA 60) -> moved to DT
    assert "513472" in dt and dt["513472"]["last_close"] == "55.0" and dt["513472"]["screener_id"] == "999", dt.get("513472")
    print(msg, "\n" + "=" * 60)

    # Dashboard data: Screener snapshot saved per stock, chart history written to charts.json
    snaps = storage.load_json("fundamentals.json", {})
    assert "513472" in snaps and snaps["513472"]["roce"] == 41.3 and snaps["513472"]["quarters"]["t"][-1] == "Sep 2026"
    charts = _j.load(open(os.path.join(tmp, "docs", "charts.json")))
    assert charts["513472"]["c"] == [56, 55]
    page = open(web.OUT, encoding="utf-8").read()
    assert '"fund": {' in page and "Screener numbers" in page

    # New listing: price from Screener, no 200 EMA yet -> stays in SP, reported as new listing
    assert "544999" in sp and sp["544999"]["last_close"] == "77.0" and sp["544999"]["ema200"] == ""
    assert "New listings" in msg and "New IPO Co" in msg

    # A stock whose last marks had 3 checks without data is re-marked automatically the next day
    import json as _j
    sp["PATELRMART"].update(last_fund_check="2026-11-03",
                            marks_detail=_j.dumps([["a", 0, 1, "n/a"], ["b", 0, 1, "n/a"], ["c", 0, 1, "n/a"]]))
    storage.save_list("SP", sp)

    # Day 3: RATNAVEER back above EMA -> SP
    msg = run(3, "daily", {}, {"RATNAVEER.NS": (540, 521, "02 Nov 2026"), "SHANTIGOLD.NS": (90, 95, "02 Nov 2026")}, {})
    sp, dt = storage.load_list("SP"), storage.load_list("DT")
    assert "RATNAVEER" in sp and "SHANTIGOLD" in dt
    assert sp["PATELRMART"]["last_fund_check"] == "2026-11-03" and "n/a" not in sp["PATELRMART"]["marks_detail"]
    assert "Marks updated" in msg and "Patel Retail" in msg
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
    test_page_choice_and_screener_prices()
    test()
