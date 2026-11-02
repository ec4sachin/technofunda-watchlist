"""Real Screener.in numbers for the 6 starting SP stocks (taken 02 Nov 2026).

Used to test the marks calculation on real data, including:
- half-yearly SME results (Sahana)
- a mixed quarter / half-year results table (Supreme Power)
- a result table whose latest column is Jun 2026 (Shanti Gold, Patel Retail)
"""

STOCKS = {
    "RATNAVEER": {
        "name": "Ratnaveer Precision Engineering Ltd", "price": 360, "mcap": 3023, "hl": (366, 129),
        "q_head": ["Mar 2025", "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"],
        "sales": [203, 265, 286, 269, 249, 315, 387], "opm": [8, 10, 10, 11, 11, 10, 9],
        "np": [11, 15, 15, 17, 17, 18, 24], "eps": [1.72, 2.40, 2.48, 2.12, 2.13, 2.17, 2.87],
        "sales_ttm": 20, "sales_3y": None,
        "bs_head": ["Mar 2025", "Mar 2026", "Sep 2026"], "fa": [186, 242, 249], "cwip": [54, 82, 148],
        "r_head": ["Mar 2025", "Mar 2026"], "debtor": [27, 60],
        "sh_head": ["Jun 2026", "Sep 2026"], "prom": [45.49, 38.71], "fii": [3.53, 3.25], "dii": [2.00, 1.15],
        "holders": [55925, 62461],
    },
    "SHANTIGOLD": {
        "name": "Shanti Gold International Ltd", "price": 286, "mcap": 2192, "hl": (438, 155),
        "q_head": ["Jun 2024", "Sep 2024", "Dec 2024", "Mar 2025", "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026"],
        "sales": [240, 266, 303, 297, 293, 430, 637, 659, 716], "opm": [6, 6, 9, 7, 13, 14, 9, 10, 10],
        "np": [9, 9, 18, 9, 25, 44, 40, 52, 50], "eps": [1.56, 1.61, 3.07, 1.60, 4.29, 5.71, 5.23, 6.77, 6.58],
        "sales_ttm": 111, "sales_3y": 44,
        "bs_head": ["Mar 2025", "Mar 2026"], "fa": [57, 59], "cwip": [9, 10],
        "r_head": ["Mar 2025", "Mar 2026"], "debtor": [60, 66],
        "sh_head": ["Jun 2026", "Sep 2026"], "prom": [74.89, 70.35], "fii": [1.92, 2.22], "dii": [1.58, 1.64],
        "holders": [30274, 45737],
    },
    "PATELRMART": {
        "name": "Patel Retail Ltd", "price": 240, "mcap": 801, "hl": (266, 149),
        "q_head": ["Jun 2024", "Sep 2024", "Dec 2024", "Mar 2025", "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026"],
        "sales": [177.38, 195.33, 228.31, 219.67, 182.45, 222.44, 309.27, 334.16, 309.54],
        "opm": [7.59, 7.24, 6.11, 7.09, 8.30, 7.44, 7.46, 5.19, 6.13],
        "np": [6.12, 5.85, 6.13, 7.18, 6.92, 10.14, 12.00, 9.98, 9.52],
        "eps": [2.51, 2.40, 2.46, 2.89, 2.78, 3.04, 3.59, 2.99, 2.85],
        "sales_ttm": 42, "sales_3y": 1,
        "bs_head": ["Mar 2025", "Mar 2026"], "fa": [65, 108], "cwip": [0, 1],
        "r_head": ["Mar 2025", "Mar 2026"], "debtor": [52, 56],
        "sh_head": ["Jun 2026", "Sep 2026"], "prom": [70.0, 70.0], "fii": [1.48, 0.87], "dii": [2.99, 2.97],
        "holders": [37293, 34848],
    },
    "SUPREMEPWR": {
        "name": "Supreme Power Equipment Ltd", "price": 243, "mcap": 606, "hl": (304, 131),
        "q_head": ["Jun 2023", "Dec 2023", "Jun 2024", "Sep 2024", "Dec 2024", "Jun 2025", "Sep 2025", "Dec 2025", "Jun 2026"],
        "sales": [22.90, 21.63, 25.45, 29.38, 27.52, 38.23, 42.44, 37.78, 51.06],
        "opm": [10.74, 17.89, 16.70, 14.60, 7.45, 14.44, 16.49, 10.11, 15.47],
        "np": [2.71, 2.92, 3.40, 3.73, 3.17, 4.45, 4.96, 3.38, 4.90],
        "eps": [15.06, 1.17, 1.36, 1.49, 1.27, 1.78, 1.98, 1.35, 1.96],
        "sales_ttm": 39, "sales_3y": 36,
        "bs_head": ["Mar 2025", "Mar 2026", "Sep 2026"], "fa": [11, 87, 91], "cwip": [49, 29, 32],
        "r_head": ["Mar 2025", "Mar 2026"], "debtor": [110, 87],
        "sh_head": ["Mar 2026", "Sep 2026"], "prom": [57.16, 57.16], "fii": [0.58, 0.75], "dii": [0.04, 0.23],
        "holders": [4785, 4954],
    },
    "EIMCOELECO": {
        "name": "Eimco Elecon (India) Ltd", "price": 2134, "mcap": 1231, "hl": (2475, 1406),
        "q_head": ["Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"],
        "sales": [33.24, 63.06, 66.88, 77.52, 56.80], "opm": [15.70, 19.84, 19.33, 18.38, 18.91],
        "np": [5.35, 12.52, 6.36, 15.38, 7.83], "eps": [9.27, 21.70, 11.03, 26.66, 13.57],
        "sales_ttm": 25, "sales_3y": 10,
        "bs_head": ["Mar 2025", "Mar 2026", "Sep 2026"], "fa": [70, 75, 121], "cwip": [1, 2, 0],
        "r_head": ["Mar 2025", "Mar 2026"], "debtor": [101, 115],
        "sh_head": ["Jun 2026", "Sep 2026"], "prom": [48.96, 48.96], "fii": [3.25, 1.30], "dii": [0.98, 1.07],
        "holders": [17825, 17139],
    },
    "SAHANA": {
        "name": "Sahana Systems Ltd", "price": 915, "mcap": 971, "hl": (1016, 571),
        "q_head": ["Sep 2022", "Mar 2023", "Sep 2023", "Mar 2024", "Sep 2024", "Mar 2025", "Sep 2025", "Mar 2026"],
        "sales": [7, 17, 24, 45, 53, 115, 114, 217], "opm": [30, 44, 26, 38, 38, 32, 33, 29],
        "np": [2, 4, 5, 14, 14, 25, 28, 47], "eps": [2.62, 6.13, 4.43, 13.42, 13.48, 33.46, 26.10, 40.69],
        "sales_ttm": 98, "sales_3y": 139,
        "bs_head": ["Mar 2025", "Mar 2026"], "fa": [37, 58], "cwip": [17, 36],
        "r_head": ["Mar 2025", "Mar 2026"], "debtor": [193, 107],
        "sh_head": ["Jun 2026", "Sep 2026"], "prom": [57.31, 57.31], "fii": [0.96, 0.50], "dii": [0.60, 0.88],
        "holders": [3382, 3355],
    },
}


def _tbl(section, head, rows, inner=""):
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join(f"<tr><td class='text'><button>{lab}&nbsp;<span>+</span></button></td>" +
                   "".join(f"<td>{'' if v is None else v}{suffix}</td>" for v in vals) + "</tr>"
                   for lab, vals, suffix in rows)
    table = f"<table class='data-table'><thead><tr><th></th>{th}</tr></thead><tbody>{body}</tbody></table>"
    return f"<section id='{section}'>{inner.replace('{T}', table) if inner else table}</section>"


def to_html(d):
    """Build a page with the same structure as a Screener.in company page."""
    hi, lo = d["hl"]
    top = (f"<ul id='top-ratios'><li><span class='name'>Market Cap</span><span>₹ <span class='number'>{d['mcap']:,}</span> Cr.</span></li>"
           f"<li><span class='name'>Current Price</span><span>₹ <span class='number'>{d['price']:,}</span></span></li>"
           f"<li><span class='name'>High / Low</span><span>₹ <span class='number'>{hi:,}</span> / <span class='number'>{lo:,}</span></span></li></ul>")
    rng = ("<table class='ranges-table'><tr><th colspan='2'>Compounded Sales Growth</th></tr>"
           f"<tr><td>3 Years:</td><td>{'' if d['sales_3y'] is None else d['sales_3y']}%</td></tr>"
           f"<tr><td>TTM:</td><td>{d['sales_ttm']}%</td></tr></table>")
    return "<html><body><h1>" + d["name"] + "</h1>" + top + \
        _tbl("quarters", d["q_head"], [("Sales", d["sales"], ""), ("OPM %", d["opm"], "%"),
                                       ("Net Profit", d["np"], ""), ("EPS in Rs", d["eps"], "")]) + \
        "<section id='profit-loss'>" + rng + "</section>" + \
        _tbl("balance-sheet", d["bs_head"], [("Fixed Assets", d["fa"], ""), ("CWIP", d["cwip"], "")]) + \
        _tbl("ratios", d["r_head"], [("Debtor Days", d["debtor"], "")]) + \
        _tbl("shareholding", d["sh_head"], [("Promoters", d["prom"], "%"), ("FIIs", d["fii"], "%"),
                                            ("DIIs", d["dii"], "%"), ("No. of Shareholders", [f"{x:,}" for x in d["holders"]], "")],
             inner="<div id='quarterly-shp'>{T}</div>") + "</body></html>"
