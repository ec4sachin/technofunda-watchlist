"""Send the report to Telegram."""
import html
import requests


def chart_url(symbol):
    """Step 6 - Chart link: TradingView for NSE symbols, Screener chart for BSE codes."""
    if str(symbol).isdigit():
        return f"https://www.screener.in/company/{symbol}/#chart"
    return f"https://www.tradingview.com/chart/?symbol=NSE%3A{symbol}"


def stock_line(symbol, name, extra=""):
    nm = html.escape(name or symbol)
    tail = f" — {html.escape(extra)}" if extra else ""
    return f"• <b>{nm}</b> ({symbol}){tail} — <a href=\"{chart_url(symbol)}\">📈 Chart</a>"


def send(token, chat_id, text):
    if not token or not chat_id:
        print("Telegram not configured — message below:\n" + text)
        return
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > 3800:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur)
    for c in chunks:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat_id, "text": c, "parse_mode": "HTML",
                                "disable_web_page_preview": "true"}, timeout=30)
        if not r.ok:
            print("Telegram error:", r.status_code, r.text[:300])
