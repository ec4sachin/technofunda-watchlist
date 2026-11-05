"""Your own stock list: Screener Excel (names with links), CSV with codes, names looked up; backtest runs."""
import os
import sys
import tempfile

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import storage  # noqa: E402
import strategy  # noqa: E402
import universe  # noqa: E402
import prices  # noqa: E402


def test():
    storage.DATA = tempfile.mkdtemp()
    folder = os.path.join(storage.DATA, "universe")
    os.makedirs(folder)
    # 1. Screener-style Excel: title rows, S.No./Name/CMP, names linked to /company/CODE/
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Growth stocks"]); ws.append([])
    ws.append(["S.No.", "Name", "CMP Rs.", "Sales growth 5Years %"])
    for i, (n, code) in enumerate((("Ratnaveer Precision", "RATNAVEER"), ("Vikram Thermo", "530477"))):
        ws.append([i + 1, n, 100, 25])
        ws.cell(row=ws.max_row, column=2).hyperlink = f"https://www.screener.in/company/{code}/consolidated/"
    ws.append(["", "Median: 2 Co.", "", ""])
    wb.save(os.path.join(folder, "screen.xlsx"))
    # 2. CSV with codes + a name-only row
    open(os.path.join(folder, "extra.csv"), "w").write("Name,NSE Code,BSE Code,Mar Cap Rs.Cr.\nSahana System,SAHANA,,1200\nOld Co,,500001,800\n"
                                                      "Mystery Ltd,,,\nRatnaveer Precision,RATNAVEER,543978,900\nGiant Corp,GIANT,,\"1,20,000\"\n")
    universe.resolve_names = lambda names, **k: {"Mystery Ltd": "MYSTERY"} if "Mystery Ltd" in names else {}
    lst = universe.load_list()
    syms = [x[0] for x in lst]
    assert {"RATNAVEER", "530477"} <= set(syms) and "SAHANA" in syms and "500001" in syms and "MYSTERY" in syms, lst
    assert syms.count("RATNAVEER") == 1
    assert "GIANT" not in syms   # above ₹25,000 crore market cap: left out
    assert universe.due("2026-11-05")
    # 3. backtest runs on downloaded prices (faked here)
    sys.path.insert(0, HERE)
    from test_strategy import hist_from, uptrend_then_base
    h = hist_from(uptrend_then_base() + [130.0] * 3)
    prices.close_and_ema = lambda tickers, period=200, **k: {t: (1, 1, "d", h) for t in tickers}
    out = universe.run({"strategies": [dict(s, on=False) for s in strategy.DEFAULT]}, None, "2026-11-05", 2026)
    assert out["stocks"] == 5 and out["with_prices"] == 5 and set(out["strategies"]) == {"swing", "positional", "switch", "growth_switch"}
    assert "by_year" in out["strategies"]["swing"] and not universe.due("2026-11-05")
    print("Stock-list backtest OK:", syms)


if __name__ == "__main__":
    test()
