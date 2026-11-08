"""Business / Management / Future marks (rules given 7 Nov 2026), worked out by hand on a test page."""
import os
import sys

import yaml

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)
import fundamentals as fx  # noqa: E402
from real_stocks import _tbl  # noqa: E402

CFG = yaml.safe_load(open(os.path.join(HERE, "..", "config", "rules.yaml")))


def page(q_np=(10, 10, 12, 12, 13), q_pbt=(13, 13, 15, 15, 17), q_int=(1, 1, 1, 1, 1), promoter=50.0,
         cfo=(8, 9, 10), np_y=(15, 18, 20), pe=20, growth_ttm=30):
    q_head = ["Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"]
    top = ("<ul id='top-ratios'><li><span class='name'>Stock P/E</span><span><span class='number'>"
           f"{pe}</span></span></li></ul>")
    rng = ("<table class='ranges-table'><tr><th colspan='2'>Compounded Profit Growth</th></tr>"
           f"<tr><td>TTM:</td><td>{growth_ttm}%</td></tr></table>")
    return ("<html><body><h1>Test Co</h1>" + top +
            _tbl("quarters", q_head, [("Sales", [100] * 5, ""), ("Interest", list(q_int), ""), ("Profit before tax", list(q_pbt), ""),
                                      ("Net Profit", list(q_np), ""), ("OPM %", [10] * 5, "%"), ("EPS in Rs", [1] * 5, "")]) +
            "<section id='profit-loss'>" + rng[:-8] + "</table>" +
            _tbl("x", ["Mar 2024", "Mar 2025", "Mar 2026", "TTM"], [("Net Profit", list(np_y) + [50], "")]).replace(
                "<section id='x'>", "").replace("</section>", "") + "</section>" +
            _tbl("balance-sheet", ["Mar 2025", "Mar 2026"], [("Equity Capital", [10, 10], ""), ("Reserves", [190, 190], ""),
                                                               ("Borrowings", [50, 50], ""), ("Fixed Assets", [100, 100], "")]) +
            _tbl("cash-flow", ["Mar 2024", "Mar 2025", "Mar 2026"], [("Cash from Operating Activity", list(cfo), "")]) +
            _tbl("shareholding", ["Jun 2026", "Sep 2026"], [("Promoters", [promoter, promoter], "%")],
                 inner="<div id='quarterly-shp'>{T}</div>") + "</body></html>")


def marks(html):
    m = fx.parse_company_page(html)
    items = {i[0].split(" ")[0] + (" " + i[0].split(" ")[1] if i[0].startswith(("TTM", "Cash", "Management")) else ""): i
             for i in fx.score(m, dict(CFG, auto_marks=dict(CFG["auto_marks"], outlook=1)), extra=True)[2]}
    return m, items


def test_numbers():
    m, it = marks(page())
    # ROE of a quarter = profit x 4 / equity (10 + 190 = 200): Sep 2026 = 13 x 4 / 200 = 26%;
    # previous 4 quarters 10, 10, 12, 12 -> 20, 20, 24, 24 -> avg 22%
    assert m["roe_q_latest"] == 26.0 and m["roe_q_avg"] == 22.0, m
    # ROCE = (PBT + interest) x 4 / (equity + borrowings = 250): latest (17 + 1) x 4 / 250 = 28.8%; prev 22.4, 22.4, 25.6, 25.6 -> 24
    assert m["roce_q_latest"] == 28.8 and m["roce_q_avg"] == 24.0, m
    assert m["cfo_to_profit_3y"] == round(27 / 53, 2)     # (8 + 9 + 10) / (15 + 18 + 20), TTM column not used
    assert m["peg_ttm"] == round(20 / 30, 2)
    assert it["ROE"][1] == 2.0 and it["Promoter"][1] == 0.5 and it["Cash from"][1] == 0.5
    assert it["TTM profit"][1] == 0.5 and it["TTM PEG"][1] == 0.5
    assert "Management outlook" not in it    # not checked yet: left out, not marked down
    print("Extra marks numbers OK:", {k: v[1] for k, v in it.items()})


def test_rules():
    # ROE falls to 18% (9 x 4 / 200) = 82% of 22%: below 85% -> both needed -> 0 of 2
    _, it = marks(page(q_np=(10, 10, 12, 12, 9)))
    assert it["ROE"][1] == 0.0, it["ROE"]
    # ROE 19% = 86% of 22%: passes (ROCE also fine)
    _, it = marks(page(q_np=(10, 10, 12, 12, 9.5)))
    assert it["ROE"][1] == 2.0, it["ROE"]
    # ROCE falls below 85% while ROE is fine -> 0
    _, it = marks(page(q_pbt=(13, 13, 15, 15, 10)))   # ROCE (10 + 1) x 4 / 250 = 17.6% = 73% of 24%
    assert it["ROE"][1] == 0.0
    # promoter 44.9% < 45%; cash 40% of profit < 50%; growth 24% < 25%; PEG 20/24 = 0.83 still <= 1
    _, it = marks(page(promoter=44.9, cfo=(6, 7, 8), growth_ttm=24))
    assert it["Promoter"][1] == 0 and it["Cash from"][1] == 0 and it["TTM profit"][1] == 0 and it["TTM PEG"][1] == 0.5
    # PEG: P/E 40 / growth 30 = 1.33 > 1 -> 0; falling profit -> no PEG mark
    _, it = marks(page(pe=40))
    assert it["TTM PEG"][1] == 0
    _, it = marks(page(growth_ttm=-5))
    assert it["TTM PEG"][1] == 0 and "no TTM profit growth" in it["TTM PEG"][3]
    # loss years: cash check fails, not a crash
    _, it = marks(page(np_y=(-5, -2, 1)))
    assert it["Cash from"][1] == 0
    print("Extra marks rules OK")


def test_off_and_preview_do_not_change_marks():
    m = fx.parse_company_page(page())
    for mode in ("off", "preview"):
        got, out_of, items = fx.score(m, dict(CFG, extra_marks=mode))
        assert out_of == 6.0, (mode, out_of)
    for v in (True, "on", "ON", "true"):   # YAML turns a bare  on  into True
        assert fx.score(m, dict(CFG, extra_marks=v))[1] == 10.0, v
    for v in (False, "off", "preview", None):
        assert fx.score(m, dict(CFG, extra_marks=v))[1] == 6.0, v
    # pass mark 5: the shown score counts (4.5 of 10 shows 5.0/11 -> passes; 4.4 of 10 shows 4.8 -> fails)
    assert fx.passes(4.5, 10, 5, CFG) and not fx.passes(4.4, 10, 5, CFG) and fx.passes(3, 6, 5, CFG) and not fx.passes(2.5, 6, 5, CFG)
    got, out_of, items = fx.score(m, dict(CFG, extra_marks="on"))
    assert out_of == 10.0     # 6 + 2 + 1 + 1 (no outlook check for this stock: that mark is left out)
    print("Off / preview / on OK")


def test_outlook_file():
    """data/outlook.json (written by Claude): 1 mark while valid, left out when missing or expired."""
    import tempfile
    import storage
    storage.DATA = tempfile.mkdtemp()
    storage.save_json("outlook.json", {"ABC": {"ok": True, "note": "guides 25% growth FY27", "date": "2026-11-07", "until": "2027-02-05"},
                                       "OLD": {"ok": True, "note": "x", "date": "2026-01-01", "until": "2026-04-01"},
                                       "BAD": {"ok": False, "note": "orders slowing", "date": "2026-11-07", "until": "2027-02-05"}})
    on = dict(CFG, extra_marks="on")
    base = fx.parse_company_page(page())

    def outlook(code):
        m = fx.add_outlook(dict(base), code, today="2026-11-08")
        got, out_of, items = fx.score(m, on)
        return out_of, [i for i in items if i[0].startswith("Management outlook")]
    o, it = outlook("ABC")
    assert o == 11.0 and it[0][1] == 1.0 and "25% growth" in it[0][3], it
    o, it = outlook("BAD")
    assert o == 11.0 and it[0][1] == 0.0
    for code in ("OLD", "NEW"):     # expired / never checked: left out
        o, it = outlook(code)
        assert o == 10.0 and not it
    print("Outlook file OK")


def test_preview_run():
    """extra_marks: preview -> all SP / DT stocks checked once, reported, nothing removed; continues after a block."""
    import tempfile
    import main
    import storage
    storage.DATA = tempfile.mkdtemp()
    good, weak = fx.parse_company_page(page()), fx.parse_company_page(page(q_np=(10, 10, 12, 12, 5), promoter=30, growth_ttm=5))
    good.update(sales_growth_qtr_yoy=30, sales_growth_ttm=20, receivables=1, debtor_days=50, fii_dii_latest=2, fii_dii_prev=1,
                shareholders_latest=90, shareholders_prev=100, fixed_assets_latest=100, fixed_assets_prev=90)
    weak.update({k: good[k] for k in ("sales_growth_qtr_yoy", "sales_growth_ttm", "debtor_days", "fii_dii_latest", "fii_dii_prev",
                                      "shareholders_latest", "shareholders_prev", "fixed_assets_latest", "fixed_assets_prev")})
    weak.update(fii_dii_latest=1, fii_dii_prev=2, shareholders_latest=120, fixed_assets_latest=80)   # just passes today (3 of 6)
    pages = {"AAA": good, "BBB": weak, "CCC": good}
    asked = []
    real = fx.fetch_metrics
    fx.fetch_metrics = lambda code, *a, **k: (asked.append(code), pages[code])[1]
    try:
        sp, dt = {"AAA": {"name": "A"}, "BBB": {"name": "B"}}, {"CCC": {"name": "C"}}
        cfg = dict(CFG, extra_marks="preview")
        rep = {"warnings": []}
        storage.SCREENER["blocked_in_a_row"] = 3          # Screener blocks part-way: nothing checked, try again next run
        main.marks_preview(sp, dt, cfg, {}, "2026-11-07", rep)
        storage.SCREENER["blocked_in_a_row"] = 0
        assert "0 of 3" in rep["warnings"][0] and "marks_preview" not in rep
        rep = {"warnings": []}
        main.marks_preview(sp, dt, cfg, {}, "2026-11-08", rep)
        mp = rep["marks_preview"]
        assert mp["total"] == 3 and mp["now_ok"] == 3 and mp["new_ok"] == 2 and [x[0] for x in mp["lose"]] == ["BBB"], mp
        assert mp["per_check"]["Promoter ≥ 45%"] == "2 of 3"
        assert set(sp) == {"AAA", "BBB"} and set(dt) == {"CCC"}               # nothing removed
        n = len(asked)
        main.marks_preview(sp, dt, cfg, {}, "2026-11-09", {"warnings": []})   # done once: not again
        assert len(asked) == n
        msg = main.build_message({**{k: [] for k in ("added", "rejected", "to_dt", "to_sp", "removed", "unchecked", "no_price",
                                                     "warnings", "first_marked", "new_listing")}, "marks_preview": mp}, sp, dt, "x")
        assert "New marks preview" in msg and "BBB" in msg
    finally:
        fx.fetch_metrics = real
    print("Preview run OK:", mp["now_ok"], "->", mp["new_ok"], mp["lose"])


if __name__ == "__main__":
    test_outlook_file()
    test_preview_run()
    test_numbers()
    test_rules()
    test_off_and_preview_do_not_change_marks()
