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
    tg.send = lambda token, chat, text: sent.append(text)
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
    alerts.live_prices = lambda syms, rows: {"SAHANA": 952.4, "RATNAVEER": 371.0}
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
    test_voice_file()
    print("ALL ALERT TESTS PASSED")
