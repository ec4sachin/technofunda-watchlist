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
import bhav  # noqa: E402
bhav.enrich = lambda need, hists, **k: (0, [])  # no exchange downloads in tests
import market  # noqa: E402
market.history = lambda: None  # no index download in tests

GOOD = fx.parse_company_page(open(os.path.join(HERE, "fixtures", "company_page.html")).read())
GOOD["_company_id"] = "999"
# 2.5/6 marks = 4.6/11: below the 50% bar (sales growth, EPS, FII/DII and shareholders fail)
WEAK = {**GOOD, "sales_growth_qtr_yoy": 10.0, "eps_latest_qtr": 5.0, "fii_dii_latest": 3.0, "shareholders_latest": 6000.0}
LOW = WEAK
# exactly 3/6 marks = 5.5/11 = 50%: passes (pass mark 5.5/11 from 7 Nov 2026 = 5 of 10 with the new marks)
MID = {**GOOD, "sales_growth_qtr_yoy": 10.0, "eps_latest_qtr": 5.0, "fii_dii_latest": 3.0}


def run(day, mode, metrics_by_code, price_by_ticker, email_stocks):
    main.datetime = type("D", (), {"now": staticmethod(lambda tz=None: datetime(2026, 11, day, 7, 0, tzinfo=tz))})
    emails.fetch_alert_stocks = lambda *a, **k: (email_stocks, ["<id>"], {"52W High": len(email_stocks)})
    fx.fetch_metrics = lambda code, *a, **k: metrics_by_code.get(code, GOOD)
    prices.close_and_ema = lambda tickers, period=200, **k: {t: (None if t.endswith(".BO") else price_by_ticker.get(t, (110, 100, "01 Nov 2026"))) for t in tickers}
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
    # (7 Nov 2026: margin = latest quarter OPM at least 85% of the average of the 4 quarters before it,
    #  margin_tolerance_pct 15 -> SHANTIGOLD 4.5 -> 5.5, PATELRMART 4.0 -> 5.0, SAHANA 4.0 -> 5.0)
    assert cfg["margin_tolerance_pct"] == 15
    expected = {"RATNAVEER": 4.5, "SHANTIGOLD": 5.5, "PATELRMART": 5.0,
                "SUPREMEPWR": 5.5, "EIMCOELECO": 4.0, "SAHANA": 5.0}
    for sym, d in real_stocks.STOCKS.items():
        m = fx.parse_company_page(real_stocks.to_html(d))
        got, out_of, _ = fx.score(m, cfg)
        assert (got, out_of) == (expected[sym], 6.0), (sym, got)
    m = fx.parse_company_page(real_stocks.to_html(real_stocks.STOCKS["RATNAVEER"]))
    assert m["opm_latest_qtr"] == 9.0 and m["opm_avg_prev"] == 10.5   # (10 + 11 + 11 + 10) / 4
    # 15% tolerance: needs 8.925% (85% of 10.5%); 9.0% passes, 8.9% fails; the old 1-point rule still works if set
    for opm, ok in ((9.0, 1.0), (8.9, 0.0)):
        mm = dict(m, opm_latest_qtr=opm)
        assert [i[1] for i in fx.score(mm, cfg)[2] if i[0].startswith("Margin")] == [ok], opm
    pts = {k: v for k, v in cfg.items() if k != "margin_tolerance_pct"}
    assert [i[1] for i in fx.score(dict(m, opm_latest_qtr=9.5), dict(pts, margin_tolerance_points=1))[2] if i[0].startswith("Margin")] == [1.0]
    m = fx.parse_company_page(real_stocks.to_html(real_stocks.STOCKS["SAHANA"]))
    assert m["opm_avg_prev"] == 32.5 and m["opm_avg_periods"] == 2      # half-yearly: (32 + 33) / 2
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
    assert len(hist["t"]) == 250 and hist["c"][-1] == 299.5 and "o" not in hist  # Screener: closes only -> line chart
    assert close == 299.5 and ema is not None and ema < close and date == "30 Oct 2026", (close, ema, date)
    assert len(sess.calls) == 2
    # New listing: only 120 trading days -> price shown, EMA not possible
    short = {"datasets": [{"metric": "Price", "values": vals[-120:], "meta": {}}]}
    sess = FakeSession({base + "730": FakeResp(200, payload=short)})
    res = prices.screener_close_and_ema("1285561", 200, session=sess, pause=0)
    assert res[:3] == (299.5, None, "30 Oct 2026") and len(res[3]["c"]) == 120
    print("Page choice + Screener price fallback OK:", close, ema, date)


def test_full_history_ohlc():
    """Yahoo data -> full-history candles (open/high/low/close/volume) with EMA from all of it."""
    import pandas as pd
    idx = pd.bdate_range(end="2026-10-30", periods=3000)
    df = pd.DataFrame({"Open": range(3000), "High": [x + 2 for x in range(3000)], "Low": [x - 1 for x in range(3000)],
                       "Close": [x + 1.0 for x in range(3000)], "Volume": [1000] * 3000}, index=idx)
    close, ema, date, hist = prices._ema_result(df, 200)
    assert close == 3000.0 and len(hist["t"]) == 3000 and hist["o"][0] == 0 and hist["h"][-1] == 3001 and hist["v"][-1] == 1000
    assert abs(ema - df["Close"].ewm(span=200, adjust=True).mean().iloc[-1]) < 0.01
    print("Full-history candles OK:", len(hist["t"]), "days")


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
    chart = _j.load(open(os.path.join(tmp, "docs", "charts", "513472.json")))
    assert chart["c"] == [56, 55]
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

    st = storage.load_state(); st["last_monthly"] = "2026-10-01"; storage.save_state(st)  # last review was in October
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
    test_full_history_ohlc()
    test()


def test_new_listing_ema20():
    """New listing (under 200 days): above 20 EMA -> SP, below 20 EMA -> DT. Too new for 20 EMA -> stays."""
    up = list(range(100, 160))                 # 60 days rising -> close above 20 EMA
    down = list(range(160, 100, -1))           # 60 days falling -> close below 20 EMA
    assert main.judge((159.0, None, "d", {"c": up}), 200)[2] == 20
    c, e, b = main.judge((101.0, None, "d", {"c": down}), 200)
    assert b == 20 and c < e
    assert main.judge((50.0, None, "d", {"c": [50] * 10}), 200) == (50.0, None, None)
    assert main.judge((300.0, 250.0, "d", {"c": up}), 200) == (300.0, 250.0, 200)

    def row(sym):
        return {**main.entry(sym, sym, "test", "01 Nov 2026"), "last_fund_check": "01 Nov 2026", "fund_result": "6/11"}
    sp = {"UPIPO": row("UPIPO"), "DOWNIPO": row("DOWNIPO")}
    dt = {"BACKIPO": row("BACKIPO")}
    hist = {"UPIPO.NS": (159.0, None, "02 Nov 2026", {"t": [], "c": up}),
            "DOWNIPO.NS": (101.0, None, "02 Nov 2026", {"t": [], "c": down}),
            "BACKIPO.NS": (159.0, None, "02 Nov 2026", {"t": [], "c": up})}
    prices.close_and_ema = lambda tickers, period=200, **k: {t: hist.get(t) for t in tickers}
    os.environ.pop("GMAIL_ADDRESS", None)
    report = {k: [] for k in ("added", "rejected", "to_dt", "to_sp", "removed", "unchecked", "no_price",
                              "warnings", "first_marked", "new_listing")}
    snaps = {s: {} for s in ("UPIPO", "DOWNIPO", "BACKIPO")}
    history = []
    main.daily(sp, dt, {"alerts": [], "ema_period": 200}, {"new_stock_pass": 5}, {"seen_email_ids": []},
               "02 Nov 2026", report, history, snaps, {})
    assert set(sp) == {"UPIPO", "BACKIPO"} and set(dt) == {"DOWNIPO"}, (sp.keys(), dt.keys())
    assert sp["UPIPO"]["ema_basis"] == 20 and "20 EMA" in history[0]["reason"]
    print("New listing 20 EMA rule OK:", [h["action"] + " " + h["symbol"] for h in history])


if __name__ == "__main__":
    test_new_listing_ema20()


def test_exchange_codes():
    html = ("<h1>Ratnaveer</h1><a href='https://www.bseindia.com/stock-share-price/ratnaveer-precision-engineering-ltd/RATNAVEER/543978/'>"
            "BSE: 543978</a><a href='https://www.nseindia.com/get-quotes/equity?symbol=RATNAVEER'>NSE: RATNAVEER</a>")
    m = fx.parse_company_page(html)
    row = {}
    main.set_codes(row, m)
    assert row == {"nse": "RATNAVEER", "bse": "543978"}, row
    print("NSE/BSE codes OK:", row)


if __name__ == "__main__":
    test_exchange_codes()
