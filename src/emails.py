"""Step 1 - read Screener.in alert emails from Gmail and collect one stock list."""
import email
import imaplib
import re
from email.header import decode_header, make_header

from bs4 import BeautifulSoup

SCREENER_SENDER = "no-reply@screener.in"
COMPANY_LINK = re.compile(r"screener\.in/company/([^/?#]+)/(consolidated/)?", re.I)


def subject_alert_name(subject):
    """'Screener.in Updates: 52W High Alert' -> '52W High'."""
    m = re.match(r"\s*Screener\.in Updates:\s*(.+?)\s+Alert\s*$", subject or "", re.I)
    return m.group(1).strip() if m else None


def parse_alert_html(html):
    """Return list of stocks found in one alert email body.

    Each stock: {code, name, consolidated, screener_path}
    code is the NSE symbol (e.g. SAHANA) or BSE code (e.g. 544442).
    """
    soup = BeautifulSoup(html, "lxml")
    stocks, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = COMPANY_LINK.search(a["href"])
        if not m:
            continue
        code = m.group(1).upper()
        if code in seen:
            continue
        seen.add(code)
        consolidated = bool(m.group(2))
        stocks.append({
            "code": code,
            "name": a.get_text(" ", strip=True),
            "consolidated": consolidated,
            "screener_path": f"/company/{code}/" + ("consolidated/" if consolidated else ""),
        })
    return stocks


def _html_of(msg):
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True) or b""
            return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    return ""


def fetch_alert_stocks(gmail_user, app_password, alert_names, days_back, already_seen_ids):
    """Read recent alert emails. Returns (stocks_by_code, new_message_ids, per_alert_counts)."""
    wanted = {a.lower(): a for a in alert_names}
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(gmail_user, app_password)
    imap.select('"[Gmail]/All Mail"', readonly=True)

    query = f"from:{SCREENER_SENDER} newer_than:{int(days_back)}d"  # subjects filtered below
    typ, data = imap.search(None, "X-GM-RAW", f'"{query}"')
    ids = data[0].split() if typ == "OK" and data and data[0] else []

    stocks, new_ids = {}, []
    per_alert = {a: 0 for a in alert_names}
    for num in ids:
        typ, msg_data = imap.fetch(num, "(RFC822)")
        if typ != "OK":
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        msg_id = (msg.get("Message-ID") or "").strip()
        if msg_id and msg_id in already_seen_ids:
            continue
        subject = str(make_header(decode_header(msg.get("Subject", ""))))
        alert = subject_alert_name(subject)
        if not alert or alert.lower() not in wanted:
            continue
        alert = wanted[alert.lower()]
        found = parse_alert_html(_html_of(msg))
        per_alert[alert] += len(found)
        for s in found:
            entry = stocks.setdefault(s["code"], {**s, "sources": []})
            if alert not in entry["sources"]:
                entry["sources"].append(alert)
        if msg_id:
            new_ids.append(msg_id)
    imap.logout()
    return stocks, new_ids, per_alert
