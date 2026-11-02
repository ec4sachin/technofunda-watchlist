# TechnoFunda Watchlist Robot 🤖

Every morning at **7:00 AM** this robot:

1. Reads your 5 Screener.in alert emails and makes one stock list
2. Gives each stock **fundamental marks** (your TechnoFunda marks system in `config/rules.yaml`)
3. Adds stocks scoring **5 or more out of 11** to watchlist **SP** (if not already there)
4. Moves SP stocks that closed **below the 200-day EMA** to watchlist **DT**
   (and moves DT stocks back to SP when they close above it again)
5. On the **1st of every month**, re-marks all SP and DT stocks and removes those **below 5 out of 11**
6. Sends you a **Telegram** message with every change and a **📈 Chart** link for each stock

Your lists are in the `data` folder: `SP.csv`, `DT.csv`, and `history.csv` (log of every change).

---

## One-time setup (about 30 minutes, no coding)

### Part A — Put the files on GitHub
1. Go to **github.com** and sign in (or create a free account).
2. Top-right **+** → **New repository**.
   - Name: `technofunda-watchlist`
   - Select **Public** (needed for the free dashboard in Part F — see "Is Public safe?" below)
   - Click **Create repository**
3. On the new page click **uploading an existing file**.
4. Unzip the file you got from Claude. Open the folder, select **everything inside it**, and drag it into the GitHub page.
   - ⚠️ The folder `.github` is hidden on some computers. On Windows: File Explorer → View → tick **Hidden items**. On Mac: press `Cmd + Shift + .`
5. Click **Commit changes**.

### Part B — Gmail "App Password" (lets the robot read your Screener emails)
1. Open **myaccount.google.com** → **Security**.
2. Make sure **2-Step Verification** is ON.
3. Search for **App passwords** at the top of that page.
4. App name: `watchlist` → **Create**. Google shows a 16-letter password. Copy it.
   (This password can only read mail — it can't change your Google password.)

### Part C — Telegram bot
1. In Telegram, open **@BotFather** → send `/newbot` → choose a name (e.g. `TechnoFunda Watchlist`) and a username ending in `bot`.
2. BotFather gives a **token** like `7012345678:AAH...`. Copy it.
3. Open your new bot and send it any message, e.g. `hi`.
4. Open **@userinfobot** in Telegram → it replies with your **Id** (a number). Copy it.

### Part D — Save the 4 secrets in GitHub
In your repository: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**. Add these 4, one by one:

| Name (type exactly) | Value |
|---|---|
| `GMAIL_ADDRESS` | your Gmail address |
| `GMAIL_APP_PASSWORD` | the 16-letter password from Part B (no spaces) |
| `TELEGRAM_BOT_TOKEN` | the token from BotFather |
| `TELEGRAM_CHAT_ID` | your Id number from @userinfobot |

### Part E — First test run
1. Click the **Actions** tab → if asked, click **I understand my workflows, go ahead and enable them**.
2. Click **Watchlist Robot** on the left → **Run workflow** → mode `daily` → **Run workflow**.
3. Wait 2–5 minutes. You should get a Telegram message. ✅

After this, it runs by itself every day at 7 AM.

### Part F — Your one-page dashboard on GitHub (free, 2 minutes)
The robot rebuilds the dashboard (`docs/index.html`) after every run, and GitHub Pages shows it as a website. It updates by itself every morning.

1. In your repository: **Settings** → **Pages** (left menu).
2. Under **Build and deployment** → Source: **Deploy from a branch**.
3. Branch: **main**, folder: **/docs** → **Save**.
4. Wait 1–2 minutes and refresh the page. GitHub shows **"Your site is live at"** a link like
   `https://YOUR-GITHUB-NAME.github.io/technofunda-watchlist/` — open it and bookmark it on your phone.
5. In `config/settings.yaml`, paste that link after `dashboard_url:` → **Commit changes**.
   Now every Telegram message ends with an **Open dashboard** link.

**Optional — use your own address `watchlist.dhanyaatra.com`:**
1. **GoDaddy** → `dhanyaatra.com` → **DNS** → **Add New Record**:
   Type **CNAME** · Name `watchlist` · Value `YOUR-GITHUB-NAME.github.io` · Save.
2. Back in GitHub **Settings** → **Pages** → **Custom domain**: type `watchlist.dhanyaatra.com` → **Save**.
3. When the check turns green (can take up to an hour), tick **Enforce HTTPS**.
4. Update `dashboard_url` in `config/settings.yaml` to `https://watchlist.dhanyaatra.com`.

**Is Public safe?** Yes for passwords: your Gmail app password and Telegram token are stored in GitHub **Secrets**, which nobody else can see, even in a public repository. What becomes visible to anyone who finds it: the program files, your SP/DT watchlists and their history. The dashboard page itself is always public on GitHub Pages (even with a paid plan and a private repository), and it tells search engines not to list it. If you want the program files hidden, GitHub Pro (paid) allows Pages from a Private repository with the same steps.

---

## Daily use

| I want to… | Do this |
|---|---|
| Change marks or pass marks | Open `config/rules.yaml` → ✏️ pencil icon → edit the numbers → **Commit changes** |
| Add a stock to SP by hand | Open `data/SP.csv` → ✏️ → add a line like `TATAELXSI,Tata Elxsi,2026-11-05,Manual,,,,,,yes` → Commit |
| Remove a stock by hand | Open `data/SP.csv` or `data/DT.csv` → ✏️ → delete its line → Commit |
| See the full SP and DT list now | Actions → Watchlist Robot → Run workflow → mode `list` |
| Run the monthly check now | Actions → Watchlist Robot → Run workflow → mode `monthly` |
| See everything on one page | Open your dashboard link (Part F) — tabs SP, DT, Today, History |
| See why a stock moved | Dashboard → **History** tab (or `data/history.csv`) |
| Change alert names, EMA, or the review day | Open `config/settings.yaml` |

You can do all of this from the **GitHub app** on your phone too.

---

## Good to know
- **Marks:** the robot calculates the 6 automatic marks of your 11-mark system (P&L 3, Balance sheet 1.5, Holding 1.5). Business, Management and Future (5 marks) need your judgement and are not included yet, so the 5/11 bar is applied as the same percentage (45%) — in practice **3 out of 6 automatic marks**. Telegram shows the score on your 11-mark scale.
- **SME stocks** that report half-yearly are compared with the same half of last year automatically.
- **Charts:** NSE stocks open in TradingView; BSE-only stocks (number codes like `544442`) open on Screener.
- **Price data** comes from Yahoo Finance. If a stock shows "No price data", type its Yahoo code (e.g. `SYMBOL.NS` for NSE or `544442.BO` for BSE) in the `yahoo_override` column of that stock in the CSV.
- **New listings** with less than 200 trading days can't have a 200 EMA yet, so they stay in SP until enough history exists.
- **Dashboard:** `docs/index.html` is your one-page dashboard: SP and DT lists with marks, 200 EMA position, Chart and Screener buttons, today's changes and full history. Part F puts it online with GitHub Pages.
- GitHub's 7:00 AM schedule can sometimes start 10–30 minutes late. That's normal.
- **Never** put passwords or tokens inside the files — only in GitHub Secrets.

## Files (you don't need to touch these)
`src/` program files · `.github/workflows/watchlist.yml` the 7 AM schedule · `tests/` offline test
