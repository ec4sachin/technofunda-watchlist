"""Revenue guidance rule (13 Nov 2026): guidance below 15% a year -> removed at the monthly review / new stock not added.
Range = middle; rupee guidance vs last full year from the saved quarters (later year -> yearly rate); none = no effect."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import main

Q = {"quarters": {"t": ["Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"],
                  "sales": [25, 25, 25, 25, 30, 30], "profit": [1] * 6, "opm": [10] * 6, "eps": [1] * 6}}
H = {"result_period_months": 6, "quarters": {"t": ["Mar 2025", "Sep 2025", "Mar 2026", "Sep 2026"],
                                              "sales": [40, 50, 50, 60], "profit": [1] * 4, "opm": [10] * 4, "eps": [1] * 4}}
cats = {"A": {"guide": {"rev": {"fy": "FY27", "pct": [10, 15]}}},       # middle 12.5 -> fails
        "B": {"guide": {"rev": {"fy": "FY27", "pct": [15]}}},           # exactly 15 -> passes
        "C": {"guide": {"rev": {"fy": "FY27", "cr": [110]}}},           # 110 vs FY26 100 = +10% -> fails
        "D": {"guide": {"rev": {"fy": "FY28", "cr": [144]}}},           # 144 vs 100 over 2 years = +20% a year -> passes
        "E": {"guide": {}},                                              # no guidance -> never fails
        "F": {"guide": {"rev": {"fy": "FY27", "cr": [120]}}}}           # half-yearly: FY26 = 50 + 50 = 100 -> +20%
cfg = {"monthly_min_revenue_guidance": 15}
low = lambda c, s=Q: main._low_guidance(c, s, cfg, "monthly_min_revenue_guidance", cats)  # noqa: E731

assert main._fy_base(Q) == (2026, 100.0), main._fy_base(Q)
assert main._fy_base(H) == (2026, 100.0), main._fy_base(H)
assert main.guided_growth("A", Q, cats) == 12.5 and low("A")
assert main.guided_growth("B", Q, cats) == 15 and low("B") is None
assert abs(main.guided_growth("C", Q, cats) - 10) < 0.01 and low("C")
assert abs(main.guided_growth("D", Q, cats) - 20) < 0.01 and low("D") is None
assert main.guided_growth("E", Q, cats) is None and low("E") is None
assert main.guided_growth("Z", Q, cats) is None and low("Z") is None
assert abs(main.guided_growth("F", H, cats) - 20) < 0.01 and low("F", H) is None
assert low("C", {}) is None                                           # no quarters saved: not comparable -> kept
assert main._low_guidance("A", Q, {"monthly_min_revenue_guidance": 0}, "monthly_min_revenue_guidance", cats) is None  # rule off
print("guidance rule: all checks passed")
