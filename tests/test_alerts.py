"""Offline test for price alerts: python tests/test_alerts.py"""
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import alerts  # noqa: E402
import telegram as tg  # noqa: E402

CHAT = "12345"
SP = {"SAHANA": {"name": "Sahana System"}, "RATNAVEER": {"name": "Ratnaveer Precision Engineering"},
      "SHANTIGOLD": {"name": "Shanti Gold International"}}
DT = {"SUPREMEPWR": {"name": "Supreme Power Equipment"}}


def fake_updates(texts, chat=CHAT, start=100):
    return [{"update_id": start + i, "message": {"chat": {"id": int(chat)}, "text": t}} for i, t in enumerate(texts)]


def test():
    sent, voices = [], []
    tg.send = lambda token, chat, text: sent.append(text) or True
    tg.send_voice = lambda token, chat, path, caption="": voices.append((path, caption)) or True
    now = datetime(2026, 11, 3, 10, 0, tzinfo=alerts.IST)

    store = alerts.empty_store()
    tg.get_updates = lambda token, offset: fake_updates([
        "/alert SAHANA above 950", "/alert ratnaveer below 340", "/alert gold above 1,000.50",
        "/alert TATAELXSI above 7000", "/alert SAHANA 950", "/alerts"]) + fake_updates(["/alert SAHANA above 1"], chat="999", start=200)
    alerts.process_commands(store, "t", CHAT, SP, DT, now)
    act = [(a["symbol"], a["op"], a["price"]) for a in store["alerts"]]
    assert act == [("SAHANA", "above", 950.0), ("RATNAVEER", "below", 340.0), ("SHANTIGOLD", "above", 1000.5),
                   ("TATAELXSI", "above", 7000.0)], act
    assert store["offset"] == 201                                   # all updates read, other chat ignored
    assert any("Please write it like" in m for m in sent)           # bad format explained
    assert "Active alerts" in sent[-1] and "4. TATAELXSI" in sent[-1]

    # delete by number and by name
    tg.get_updates = lambda token, offset: fake_updates(["/delete 4", "/delete gold"], start=300)
    alerts.process_commands(store, "t", CHAT, SP, DT, now)
    assert [a["id"] for a in store["alerts"]] == [1, 2]

    # prices: Sahana crosses 950, Ratnaveer still above 340 -> only alert 1 fires, with voice note
    alerts.live_prices = lambda syms, rows, **k: {"SAHANA": {"price": 952.4, "bars": []}, "RATNAVEER": {"price": 371.0, "bars": []}}
    alerts.make_voice = lambda text, lang="hi": voices.append(("text", text)) or "/tmp/x.ogg"
    sent.clear()
    fired = alerts.check_alerts(store, "t", CHAT, SP, DT, "hi", now)
    assert [a["id"] for a in fired] == [1] and store["alerts"][0]["status"] == "triggered"
    assert "PRICE ALERT" in sent[0] and "₹952.4" in sent[0]
    assert ("text", "प्राइस अलर्ट। Sahana System 950 रुपये के ऊपर पहुँच गया है। अभी का भाव 952.4 रुपये है।") in voices
    # a triggered alert does not fire again
    assert alerts.check_alerts(store, "t", CHAT, SP, DT, "hi", now) == []

    # English voice text
    a = {"name": "Ratnaveer", "symbol": "RATNAVEER", "op": "below", "price": 340.0}
    assert alerts.voice_text(a, 338.5, "en") == "Price alert. Ratnaveer has fallen below 340 rupees. The price now is 338.5 rupees."

    # market hours (India time)
    assert alerts.market_open(datetime(2026, 11, 3, 9, 15, tzinfo=alerts.IST))
    assert not alerts.market_open(datetime(2026, 11, 3, 9, 0, tzinfo=alerts.IST))
    assert not alerts.market_open(datetime(2026, 11, 7, 11, 0, tzinfo=alerts.IST))  # Saturday
    print("Alerts OK")


def test_dashboard_requests():
    """Files saved by the dashboard (one per click) become alerts / deletions, then are removed."""
    import json
    import tempfile
    sent = []
    tg.send = lambda token, chat, text: sent.append(text) or True
    folder = tempfile.mkdtemp()
    def put(name, obj):
        with open(os.path.join(folder, name), "w") as f:
            json.dump(obj, f)
    store = alerts.empty_store()
    put("1-a.json", {"action": "add", "symbol": "SAHANA", "name": "Sahana System", "op": "above", "price": 950})
    put("2-b.json", {"action": "add", "symbol": "SUPREMEPWR", "op": "below", "price": "230.5"})
    put("3-c.json", {"action": "add", "symbol": "SAHANA", "op": "above", "price": "oops"})   # bad price -> ignored
    open(os.path.join(folder, ".keep"), "w").close()
    n = alerts.ingest_requests(store, folder, "t", CHAT, SP, DT)
    assert n == 3 and [(a["id"], a["symbol"], a["op"], a["price"], a["source"]) for a in store["alerts"]] == \
        [(1, "SAHANA", "above", 950.0, "dashboard"), (2, "SUPREMEPWR", "below", 230.5, "dashboard")]
    assert sorted(os.listdir(folder)) == [".keep"]  # saved quietly, no Telegram message
    put("4-d.json", {"action": "delete", "id": 1})
    alerts.ingest_requests(store, folder, "t", CHAT, SP, DT)
    assert [a["id"] for a in store["alerts"]] == [2] and sent == []
    print("Dashboard requests OK")


def test_voice_file():
    """The mp3 from text-to-speech is turned into a Telegram voice note (.ogg)."""
    import importlib
    import types
    importlib.reload(alerts)

    class FakeTTS:
        def __init__(self, text, lang="en", tld=None):
            self.lang, self.tld = lang, tld

        def save(self, path):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", path], check=True)
    sys.modules["gtts"] = types.SimpleNamespace(gTTS=FakeTTS)
    path = alerts.make_voice("Price alert", "hi")
    assert path.endswith(".ogg") and os.path.getsize(path) > 0, path
    print("Voice note OK:", path)


if __name__ == "__main__":
    test()
    test_dashboard_requests()
    test_voice_file()
    print("ALL ALERT TESTS PASSED")


def test_alert_safety():
    """Stale prices never fire, a quick touch between checks fires, failed Telegram retries, bad files ignored."""
    import json as _j
    import tempfile as _tf
    from datetime import datetime as _d
    import pandas as pd
    now = _d(2026, 11, 3, 11, 0, tzinfo=alerts.IST)
    # 1. Yahoo returns yesterday's bars before the open -> no price at all
    idx_old = pd.date_range("2026-11-02 15:00", periods=3, freq="1min", tz="Asia/Kolkata")
    idx_new = pd.date_range("2026-11-03 10:30", periods=25, freq="1min", tz="Asia/Kolkata")
    import yfinance as _yf
    def fake_dl(tickers, **k):
        idx = idx_new if "SAHANA.NS" in tickers else idx_old
        hi = [950.0] * len(idx)
        if len(idx) > 3:
            hi[3] = 1001.0  # a quick spike at 10:33
        return pd.DataFrame({"High": hi, "Low": [940.0] * len(idx), "Close": [945.0] * len(idx)}, index=idx)
    alerts.yf.download = fake_dl
    alerts.fx._get = lambda *a, **k: None
    px = alerts.live_prices(["RATNAVEER"], {}, now=now)
    assert px == {}, px
    px = alerts.live_prices(["SAHANA"], {}, now=now)
    assert px["SAHANA"]["price"] == 945.0 and len(px["SAHANA"]["bars"]) == 25
    # 2. the spike at 10:33 (between two checks) fires an alert created at 10:00; not one created at 10:40
    real_live = alerts.live_prices
    store = {"next_id": 3, "offset": 0, "alerts": [
        {"id": 1, "symbol": "SAHANA", "name": "Sahana", "op": "above", "price": 1000, "status": "active", "created_ts": "2026-11-03T10:00:00+05:30"},
        {"id": 2, "symbol": "SAHANA", "name": "Sahana", "op": "above", "price": 1000, "status": "active", "created_ts": "2026-11-03T10:40:00+05:30"}]}
    sent, saves = [], []
    alerts.tg.send = lambda token, chat, text: sent.append(text) or True
    alerts.tg.send_voice = lambda *a, **k: True
    alerts.live_prices = real_live
    fired = alerts.check_alerts(store, "t", "1", {}, {}, "en", now=now, save=lambda: saves.append(1))
    assert [a["id"] for a in fired] == [1] and saves == [1] and "touched ₹1001" in sent[0], (fired, sent)
    # 3. Telegram down -> alert stays active, fires next time
    store["alerts"][1]["price"] = 944
    store["alerts"][1]["op"] = "below"
    store["alerts"][1]["created_ts"] = "2026-11-03T10:00:00+05:30"
    alerts.tg.send = lambda token, chat, text: False
    assert alerts.check_alerts(store, "t", "1", {}, {}, "en", now=now) == [] and store["alerts"][1]["status"] == "active"
    # 4. a request file that is valid JSON but not a request is removed and does not crash
    folder = _tf.mkdtemp()
    open(os.path.join(folder, "a.json"), "w").write("[1]")
    open(os.path.join(folder, "b.json"), "w").write(_j.dumps({"action": "add", "symbol": "SAHANA", "name": {"x": 1}, "op": "above", "price": 5}))
    n = alerts.ingest_requests(store, folder, "t", "1", {"SAHANA": {"name": "Sahana"}}, {})
    assert n == 1 and os.listdir(folder) == [] and isinstance(store["alerts"][-1]["name"], str)
    # 5. typing ITC must not pick "Pitcher Ltd"
    assert alerts.resolve("ITC", {"ABC": {"name": "Pitcher Ltd"}}, {}) == ("ITC", "ITC")
    print("Alert safety OK")


if __name__ == "__main__":
    test_alert_safety()
