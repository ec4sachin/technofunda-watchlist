"""Business announcements (13 Nov 2026): only business news of SP / DT stocks is kept; BSE for stocks with a BSE code,
NSE only for NSE-only stocks; duplicates are not added twice; downloads are faked here (no network)."""
import os, sys, tempfile
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
tmp = tempfile.mkdtemp()
import storage
storage.DATA_DIR = tmp if hasattr(storage, "DATA_DIR") else tmp
_save, _load = {}, {}
storage.save_json = lambda name, obj: _save.__setitem__(name, obj)
storage.load_json = lambda name, default: _save.get(name, default)
storage.out_of_time = lambda: False
import announce as A

k = A.kind_of
assert k("Receipt of order worth Rs 27.85 crore from Mazagon Dock") == "Order"
assert k("Bagging of work order from NHAI") == "Order"
assert k("x", "Award of Order / Receipt of Order") == "Order"
assert k("Commencement of commercial production at new plant") == "Capacity"
assert k("Acquisition of 51% stake in XYZ Ltd") == "Acquisition / JV"
assert k("Signing of MoU with Government of Karnataka") == "Acquisition / JV"
assert k("Launch of new product range") == "Product / approval"
assert k("Closure of Trading Window") is None
assert k("Intimation of Board Meeting to consider financial results") is None
assert k("Copy of Newspaper Publication") is None
assert k("Allotment of ESOP") is None
assert k("Board meeting outcome - approved capacity expansion of 20,000 TPA") == "Capacity"

def bse(day, s=None):
    return [{"code": "513472", "d": day.strftime("%Y-%m-%d"), "title": "Receipt of order worth Rs 40 crore from SAIL", "sub": "", "url": "u1"},
            {"code": "513472", "d": day.strftime("%Y-%m-%d"), "title": "Closure of Trading Window", "sub": "", "url": "u2"},
            {"code": "999999", "d": day.strftime("%Y-%m-%d"), "title": "Receipt of order", "sub": "", "url": "u3"}]
def nse(day, s=None):
    return [{"symbol": "PRIMECAB", "d": day.strftime("%Y-%m-%d"), "title": "Commercial production started at Giloth MV line", "sub": "", "url": "u4"},
            {"symbol": "DANISH", "d": day.strftime("%Y-%m-%d"), "title": "Receipt of order for transformers", "sub": "", "url": "u5"}]
sp = {"513472": {"name": "Simplex Castings", "bse": "513472"}, "PRIMECAB": {"name": "Prime Cable", "nse": "PRIMECAB"},
      "DANISH": {"name": "Danish Power", "nse": "DANISH", "bse": "544222"}}
day = datetime(2026, 11, 12)
new, ok = A.update(sp, {}, "2026-11-13", days=[day], bse=bse, nse=nse)
codes = sorted(c for c, *_ in new)
assert ok and codes == ["513472", "PRIMECAB"], new          # DANISH has a BSE code: its NSE copy is not used
items = _save[A.FILE]["items"]
assert items["513472"][0]["k"] == "Order" and items["PRIMECAB"][0]["k"] == "Capacity"
new2, _ = A.update(sp, {}, "2026-11-13", days=[day], bse=bse, nse=nse)
assert new2 == [], new2                                     # same announcement is not added again
assert set(A.recent(sp, {}, today="2026-11-13")) == {"513472", "PRIMECAB"}
# nothing could be read: "last" date is not moved on
_save.clear()
new3, ok3 = A.update(sp, {}, "2026-11-13", days=[day], bse=lambda d, s=None: [], nse=lambda d, s=None: [])
assert not ok3 and _save[A.FILE]["last"] == ""
print("announcements: all checks passed")
