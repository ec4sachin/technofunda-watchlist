"""Step 1 - read Screener.in alert emails from Gmail and collect one stock list."""
import email
import imaplib
import re
from email.header import decode_header, make_header

from bs4 import BeautifulSoup

SCREENER_SENDER = "no-reply@screener.in"
# Investors you follow on Screener: emails "Screener Alert: <NAME>" (holdings changes, bulk / block deals)
DEFAULT_INVESTORS = ["Mukul Mahavir Agrawal", "Ashish Kacholia"]
COMPANY_LINK = re.compile(r"screener\.in/company/([^/?#]+)/(consolidated/)?", re.I)


def subject_alert_name(subject):
    """'Screener.in Updates: 52W High Alert' -> '52W High'."""
    m = re.match(r"\s*Screener\.in Updates:\s*(.+?)\s+Alert\s*$", subject or "", re.I)
    return m.group(1).strip() if m else None


def subject_investor_name(subject):
    """'Screener Alert: Ashish Kacholia' -> 'Ashish Kacholia'."""
    m = re.match(r"\s*Screener Alert:\s*(.+?)\s*$", subject or "", re.I)
    return m.group(1).strip() if m else None


def _norm_name(n):
    """Spelling-proof name key: 'Mukul Mahavir Agarwal' and '... Agrawal' are the same investor."""
    n = re.sub(r"[^a-z]", "", (n or "").lower())
    return n.replace("agarwal", "agrawal").replace("aggarwal", "agrawal")


def _pct(t):
    try:
        return float(str(t).replace("%", "").strip())
    except ValueError:
        return None   # "--%" = not holding (any more)


def parse_investor_html(html):
    """Stocks in an investor email, each with what the investor did:
    {code, name, consolidated, screener_path, action}  e.g. action "raised stake 2.27% → 2.36%",
    "cut stake 3.41% → 3.26%", "new stake 1.20%", "sold out (was 1.21%)", "holds 1.57%", "bulk deal Sell 3797465@140.75"."""
    soup = BeautifulSoup(html, "lxml")
    out = {}
    for strong in soup.find_all("strong"):
        section = strong.get_text(" ", strip=True).lower()
        p = strong.find_parent("p")
        table = p.find_next_sibling("table") if p else None
        if table is None or not any(k in section for k in ("shareholding", "deal")):
            continue
        for tr in table.find_all("tr"):
            a = tr.find("a", href=True)
            m = COMPANY_LINK.search(a["href"]) if a else None
            if not m:
                continue
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if "deal" in section:
                side = tds[1].capitalize() if len(tds) > 1 else ""
                qty = re.search(r"([\d,]+)\s*@\s*([\d.,]+)", tds[2]) if len(tds) > 2 else None
                action = f"{section.replace(' deals', '').replace(' deal', '')} deal {side}" + (f" {qty.group(1)}@{qty.group(2)}" if qty else "")
            else:
                old, new = (_pct(tds[1]), _pct(tds[2])) if len(tds) > 2 else (None, None)
                if old is None and new is not None:
                    action = f"new stake {new:g}%"
                elif new is None and old is not None:
                    action = f"sold out (was {old:g}%)"
                elif old is not None and new > old:
                    action = f"raised stake {old:g}% → {new:g}%"
                elif old is not None and new < old:
                    action = f"cut stake {old:g}% → {new:g}%"
                else:
                    action = f"holds {new:g}%" if new is not None else "holding"
            code = m.group(1).upper()
            consolidated = bool(m.group(2))
            e = out.setdefault(code, {"code": code, "name": a.get_text(" ", strip=True), "consolidated": consolidated,
                                      "screener_path": f"/company/{code}/" + ("consolidated/" if consolidated else ""), "actions": []})
            if action not in e["actions"]:
                e["actions"].append(action)
    for e in out.values():
        e["action"] = "; ".join(e.pop("actions"))
    return list(out.values())


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


def fetch_alert_stocks(gmail_user, app_password, alert_names, days_back, already_seen_ids, investors=None, investor_days_back=None):
    """Read recent alert emails (screens + followed investors). Returns (stocks_by_code, new_message_ids, per_alert_counts).
    A stock from an investor email has "notes": ["Ashish Kacholia: raised stake 2.27% → 2.36%", ...]."""
    wanted = {a.lower(): a for a in alert_names}
    investors = DEFAULT_INVESTORS if investors is None else investors
    people = {_norm_name(n): n for n in investors}
    imap = imaplib.IMAP4_SSL("imap.gmail.com", timeout=60)
    imap.login(gmail_user, app_password)
    imap.select('"[Gmail]/All Mail"', readonly=True)

    # investor emails can be read further back (first run: their holdings of the last weeks), screens days_back only
    look = max(int(days_back), int(investor_days_back or 0))
    query = f"from:{SCREENER_SENDER} newer_than:{look}d"  # subjects filtered below
    from datetime import datetime, timedelta, timezone
    from email.utils import parsedate_to_datetime
    screen_from = datetime.now(timezone.utc) - timedelta(days=int(days_back))
    typ, data = imap.search(None, "X-GM-RAW", f'"{query}"')
    ids = data[0].split() if typ == "OK" and data and data[0] else []

    stocks, new_ids = {}, []
    per_alert = {a: 0 for a in list(alert_names) + list(investors)}
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
        person = people.get(_norm_name(subject_investor_name(subject)))
        if person:
            alert = person
            found = parse_investor_html(_html_of(msg))
        elif alert and alert.lower() in wanted:
            try:
                if look > int(days_back) and parsedate_to_datetime(msg.get("Date")) < screen_from:
                    continue   # an older screen email: only investor emails are read that far back
            except (TypeError, ValueError):
                pass
            alert = wanted[alert.lower()]
            found = parse_alert_html(_html_of(msg))
        else:
            continue
        per_alert[alert] += len(found)
        for s in found:
            entry = stocks.setdefault(s["code"], {**{k: v for k, v in s.items() if k != "action"}, "sources": [], "notes": []})
            if alert not in entry["sources"]:
                entry["sources"].append(alert)
            if s.get("action") and f"{alert}: {s['action']}" not in entry["notes"]:
                entry["notes"].append(f"{alert}: {s['action']}")
        if msg_id:
            new_ids.append(msg_id)
    imap.logout()
    return stocks, new_ids, per_alert
