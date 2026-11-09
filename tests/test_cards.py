"""Stock card: price next to the name, no EMA % line, catalyst summary box (data/catalysts.json)."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import storage  # noqa: E402
import web  # noqa: E402


def test():
    storage.DATA = tempfile.mkdtemp()
    storage.save_json("catalysts.json", {"AAA": {"text": "Order book up 40%.", "date": "2026-11-09", "sources": [["Results", "https://x.in"]]},
                                         "OLD": {"text": "gone from the lists", "date": "2026-11-09"},
                                         "BBB": {"text": "", "date": "2026-11-09"}})
    sp = {"AAA": {"name": "Aaa Ltd", "last_close": "100", "ema200": "80"}, "BBB": {"name": "Bbb", "last_close": "50", "ema200": "60"}}
    data = web.page_data(sp, {}, {}, [], {"full_marks": 11})
    assert list(data["catalysts"]) == ["AAA"], data["catalysts"]          # only listed stocks with a summary
    html = web.FULL_PAGE.replace("{fragment}", web.render_fragment(data))
    assert "Order book up 40%." in html
    js = web.FRAGMENT
    assert "% \" + (gap >= 0 ? \"above\"" not in js                       # the "▲ 33.1% above 200 EMA" line is gone
    assert 'class="nmline"' in js and "catBox(r)" in js and "openCat(" in js
    storage.save_json("catalysts.json", [])                                 # a broken file never breaks the page
    assert web.page_data(sp, {}, {}, [], {"full_marks": 11})["catalysts"] == {}
    real = os.path.join(HERE, "..", "data", "catalysts.json")      # the catalyst notes written so far
    for k, v in (json.load(open(real, encoding="utf-8")) if os.path.exists(real) else {}).items():
        assert 25 <= len(v["text"].replace("==", "").split()) <= 130, (k, len(v["text"].split()))
    print("Stock card OK")


if __name__ == "__main__":
    test()
