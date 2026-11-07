"""Investor emails ("Screener Alert: Ashish Kacholia" / "Mukul Mahavir Agrawal"): stocks + what the investor did."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import emails  # noqa: E402

ROW = """<tr><td></td><td>{p1}</td><td>{p2}</td><td></td></tr>
<tr><td class="text"><a href="https://www.screener.in/company/{code}/{cons}?utm_source=email&utm_campaign=followed-people">
  {name}</a></td><td>{a}</td><td>{b}</td><td>{ch}</td></tr>"""

SHAREHOLDING = """<html><body><p>Updates for <strong>Mukul Mahavir Agrawal</strong>.</p>
<p><strong>Shareholding</strong></p><table>""" + "".join(ROW.format(**r) for r in (
    dict(p1="Sep 2026", p2="Oct 2026", code="APOLLOPIPE", cons="consolidated/", name="Apollo Pipes Ltd", a="3.41%", b="3.26%", ch="changed"),
    dict(p1="Jun 2026", p2="Sep 2026", code="526433", cons="consolidated/", name="ASM Technologies Ltd", a="10.28%", b="10.28%", ch=""),
    dict(p1="Jun 2026", p2="Sep 2026", code="KIRLFER", cons="", name="Kirloskar Ferrous Industries Ltd", a="1.21%", b="--%", ch="changed"),
    dict(p1="Jun 2026", p2="Sep 2026", code="STOVEKRAFT", cons="", name="Stove Kraft Ltd", a="1.74%", b="1.92%", ch="changed"),
    dict(p1="Aug 2026", p2="Sep 2026", code="ARDEE", cons="", name="Ardee Industries Ltd", a="--%", b="1.20%", ch="changed"),
)) + """</table><hr><a href="https://play.google.com/store/apps/details?id=com.screener.mobile">Review</a>
<p>You received this email because you are following "Mukul Mahavir Agrawal" on Screener.in.
You can <a href="https://www.screener.in/alerts/unsubscribe/x/y/p/?alert_id=1">disable</a>.</p></body></html>"""

DEALS = """<html><body><p>Updates for <strong>Mukul Mahavir Agrawal</strong>.</p>
<p><strong>Bulk Deals</strong></p><table><tr><td class="text">
<a href="https://www.screener.in/company/AJMERA/consolidated/?utm_content=deals">Ajmera Realty &amp; Infra India Ltd</a></td>
<td>Sell</td><td><strong>534493198.75</strong><br><small>3797465@140.75</small></td></tr></table>
<p><strong>Block Deals</strong></p><table><tr><td class="text">
<a href="https://www.screener.in/company/AJMERA/consolidated/?utm_content=deals">Ajmera Realty &amp; Infra India Ltd</a></td>
<td>Sell</td><td><strong>534493198.75</strong><br><small>3797465@140.75</small></td></tr></table></body></html>"""


def test():
    assert emails.subject_investor_name("Screener Alert: Ashish Kacholia") == "Ashish Kacholia"
    assert emails.subject_investor_name("Screener.in Updates: 52W High Alert") is None
    assert emails.subject_alert_name("Screener Alert: Ashish Kacholia") is None
    assert emails._norm_name("Mukul Mahavir Agarwal") == emails._norm_name("Mukul Mahavir Agrawal")

    got = {s["code"]: s for s in emails.parse_investor_html(SHAREHOLDING)}
    assert list(got) == ["APOLLOPIPE", "526433", "KIRLFER", "STOVEKRAFT", "ARDEE"], list(got)
    assert got["APOLLOPIPE"]["action"] == "cut stake 3.41% → 3.26%" and got["APOLLOPIPE"]["consolidated"]
    assert got["526433"]["action"] == "holds 10.28%"
    assert got["KIRLFER"]["action"] == "sold out (was 1.21%)" and not got["KIRLFER"]["consolidated"]
    assert got["STOVEKRAFT"]["action"] == "raised stake 1.74% → 1.92%"
    assert got["ARDEE"]["action"] == "new stake 1.2%"
    assert got["APOLLOPIPE"]["name"] == "Apollo Pipes Ltd"

    d = emails.parse_investor_html(DEALS)
    assert len(d) == 1 and d[0]["code"] == "AJMERA" and d[0]["name"] == "Ajmera Realty & Infra India Ltd"
    assert d[0]["action"] == "bulk deal Sell 3797465@140.75; block deal Sell 3797465@140.75", d[0]["action"]
    # the play-store / unsubscribe links are not stocks
    assert all("play" not in s["code"].lower() for s in got.values())
    print("Investor emails OK:", {k: v["action"] for k, v in got.items()}, d[0]["action"])


def test_fetch_mixes_both_kinds():
    """fetch_alert_stocks: a screen email and an investor email (any spelling of the name) are both read."""
    import email.message

    def msg(subject, html, mid):
        m = email.message.EmailMessage()
        m["Subject"], m["Message-ID"] = subject, mid
        m.set_content(html, subtype="html")
        return m.as_bytes()

    screen = '<a href="https://www.screener.in/company/SAHANA/">Sahana System</a>'
    box = {b"1": msg("Screener.in Updates: 52W High Alert", screen, "<a>"),
           b"2": msg("Screener Alert: Mukul Mahavir Agarwal", SHAREHOLDING, "<b>"),
           b"3": msg("Screener Alert: Somebody Else", DEALS, "<c>")}

    class Imap:
        def __init__(self, *a, **k): pass
        def login(self, *a): pass
        def select(self, *a, **k): pass
        def search(self, *a): return "OK", [b" ".join(box)]
        def fetch(self, n, what): return "OK", [(None, box[n])]
        def logout(self): pass
    real = emails.imaplib.IMAP4_SSL
    emails.imaplib.IMAP4_SSL = Imap
    try:
        stocks, ids, per = emails.fetch_alert_stocks("u", "p", ["52W High"], 3, set())
    finally:
        emails.imaplib.IMAP4_SSL = real
    assert "SAHANA" in stocks and "APOLLOPIPE" in stocks and "AJMERA" not in stocks, list(stocks)   # not a followed investor
    assert stocks["APOLLOPIPE"]["sources"] == ["Mukul Mahavir Agrawal"]
    assert stocks["APOLLOPIPE"]["notes"] == ["Mukul Mahavir Agrawal: cut stake 3.41% → 3.26%"]
    assert per["52W High"] == 1 and per["Mukul Mahavir Agrawal"] == 5 and per["Ashish Kacholia"] == 0
    assert set(ids) == {"<a>", "<b>"}
    # first run: investor emails 45 days back, but an old screen email is still skipped
    from email.utils import format_datetime
    from datetime import datetime, timedelta, timezone
    old = format_datetime(datetime.now(timezone.utc) - timedelta(days=20)).replace("+0000", "-0000")   # as Screener sends it

    def dated(subject, html, mid):
        m = email.message.EmailMessage()
        m["Subject"], m["Message-ID"], m["Date"] = subject, mid, old
        m.set_content(html, subtype="html")
        return m.as_bytes()
    box.clear()
    box.update({b"4": dated("Screener.in Updates: 52W High Alert", screen, "<d>"),
                b"5": dated("Screener Alert: Mukul Mahavir Agrawal", DEALS, "<e>")})
    emails.imaplib.IMAP4_SSL = Imap
    try:
        stocks, ids, per = emails.fetch_alert_stocks("u", "p", ["52W High"], 3, set(), investor_days_back=45)
    finally:
        emails.imaplib.IMAP4_SSL = real
    assert list(stocks) == ["AJMERA"] and "SAHANA" not in stocks, list(stocks)
    print("Screens + investors read together OK:", per)


if __name__ == "__main__":
    test()
    test_fetch_mixes_both_kinds()
