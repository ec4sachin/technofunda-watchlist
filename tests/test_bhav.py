"""Exchange price files -> real candles for closes-only (SME) stocks."""
import os
import sys
import tempfile

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import bhav  # noqa: E402
import storage  # noqa: E402

BSE = ("TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,"
       "OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n"
       "2026-11-03,2026-11-03,CM,BSE,STK,530477,INE00,VIKRAMTH,X,,,,,VIKRAM THERMO,385.00,395.50,378.20,383.00,383,387.35,,,,,12345,0,0,F1,1,,,,,\n"
       "2026-11-03,2026-11-03,CM,BSE,STK,500325,INE01,RELIANCE,A,,,,,RELIANCE,1,2,0.5,1.5,1,1,,,,,1,0,0,F1,1,,,,,\n")
NSE = (" SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"
       "ACETEC, SM, 03-Nov-2026, 100.00, 101.00, 108.00, 99.50, 106, 106.50, 104, 24000, 25, 30, 24000, 100\n"
       "ACETEC, BL, 03-Nov-2026, 100.00, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1\n")


class FakeEx:
    def __init__(self, name, text):
        self.name, self.text, self.fails, self.ok, self.asked = name, text, 0, 0, []

    def day(self, d):
        self.asked.append(d.strftime("%Y-%m-%d"))
        if d.strftime("%Y-%m-%d") == "2026-11-03":
            self.ok += 1
            return bhav.parse(self.text)
        self.fails += 1
        return None


def test():
    storage.DATA = tempfile.mkdtemp()
    rows = bhav.parse(BSE)
    assert rows[0]["code"] == "530477" and rows[0]["high"] == 395.5 and rows[0]["volume"] == 12345
    rows = bhav.parse(NSE)
    assert rows[0]["symbol"] == "ACETEC" and rows[0]["series"] == "SM" and rows[0]["low"] == 99.5
    assert bhav.parse("<html>error</html>") == []

    hists = {"530477": {"t": ["2026-10-31", "2026-11-03"], "c": [387.35, 383.0]},
             "ACETEC": {"t": ["2026-10-31", "2026-11-03"], "c": [100.0, 106.5], "v": [5, 6]}}
    ex = {"bse": FakeEx("BSE", BSE), "nse": FakeEx("NSE", NSE)}
    days, warns = bhav.enrich({"530477": {"bse": "530477"}, "ACETEC": {"nse": "ACETEC"}}, hists, exchanges=ex)
    assert days == 2 and not warns, (days, warns)
    h = hists["530477"]
    assert h["o"] == [None, 385.0] and h["h"] == [None, 395.5] and h["l"] == [None, 378.2] and h["v"][1] == 12345, h
    a = hists["ACETEC"]
    assert a["h"] == [None, 108.0] and a["c"][1] == 106.5  # SM series used, BL (block deal) row ignored
    # second run: 3 Nov comes from the cache, only the missing day is asked again
    ex2 = {"bse": FakeEx("BSE", BSE), "nse": FakeEx("NSE", NSE)}
    hists2 = {"530477": {"t": ["2026-10-31", "2026-11-03"], "c": [387.35, 383.0]}}
    bhav.enrich({"530477": {"bse": "530477"}}, hists2, exchanges=ex2)
    assert ex2["bse"].asked == ["2026-10-31"] and hists2["530477"]["h"][1] == 395.5, ex2["bse"].asked
    # exchange not reachable at all -> a clear warning, no crash
    ex3 = {"bse": FakeEx("BSE", ""), "nse": FakeEx("NSE", "")}
    ex3["bse"].fails = 4
    _, warns = bhav.enrich({"544442": {"bse": "544442"}}, {"544442": {"t": ["2026-10-30"], "c": [10.0]}}, exchanges=ex3)
    assert warns and "BSE" in warns[0]
    bhav.remove_unused({"530477"})
    assert os.listdir(os.path.join(storage.DATA, "ohlc")) == ["530477.csv"]
    print("Exchange price files OK")


if __name__ == "__main__":
    test()


def test_no_trade_day():
    """A stock missing from a downloaded day's file (no trades) gets a flat candle, if the file has it on other days."""
    storage.DATA = tempfile.mkdtemp()

    class Ex(FakeEx):
        def day(self, d):
            self.asked.append(d.strftime("%Y-%m-%d"))
            self.ok += 1
            return bhav.parse(BSE if d.strftime("%Y-%m-%d") == "2026-11-03" else BSE.replace("530477", "999999"))
    hists = {"530477": {"t": ["2026-10-30", "2026-11-03"], "c": [387.35, 383.0]},
             "111111": {"t": ["2026-10-30", "2026-11-03"], "c": [5.0, 6.0]}}   # code never in any file
    ex = {"bse": Ex("BSE", ""), "nse": Ex("NSE", "")}
    bhav.enrich({"530477": {"bse": "530477"}, "111111": {"bse": "111111"}}, hists, exchanges=ex)
    h = hists["530477"]
    assert h["o"] == [387.35, 385.0] and h["h"][0] == h["l"][0] == 387.35 and h["v"][0] == 0, h
    assert "o" not in hists["111111"]  # wrong / unknown code: no made-up candles
    # next run asks nothing again
    ex2 = {"bse": Ex("BSE", ""), "nse": Ex("NSE", "")}
    bhav.enrich({"530477": {"bse": "530477"}}, {"530477": {"t": ["2026-10-30", "2026-11-03"], "c": [387.35, 383.0]}}, exchanges=ex2)
    assert ex2["bse"].asked == [], ex2["bse"].asked
    print("No-trade days OK")


if __name__ == "__main__":
    test_no_trade_day()
