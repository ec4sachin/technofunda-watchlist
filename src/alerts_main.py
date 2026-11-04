"""Runs every 15 minutes (see .github/workflows/alerts.yml):
answers your Telegram commands, and during market hours checks your price alerts."""
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import alerts  # noqa: E402
import storage  # noqa: E402
import telegram as tg  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def main():
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("Telegram is not set up (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")
        return
    with open(os.path.join(ROOT, "config", "settings.yaml"), encoding="utf-8") as f:
        settings = yaml.safe_load(f) or {}
    lang = str(settings.get("alert_voice_language", "hi")).lower()
    store = storage.load_json("alerts.json", alerts.empty_store())
    sp, dt = storage.load_list("SP"), storage.load_list("DT")
    before = repr(store)
    if not store.get("bot_username"):
        store["bot_username"] = tg.bot_username(token)
        tg.set_commands(token)
    import strategy
    strat = strategy.load_settings()
    strat_before = repr(strat)
    applied = alerts.ingest_requests(store, os.path.join(storage.DATA, "alert_requests"), token, chat, sp, dt,
                                     strategies=strat)
    if repr(strat) != strat_before:
        storage.save_json("strategies.json", strat)
    if applied:
        print(f"Applied {applied} request(s) from the dashboard.")
    alerts.process_commands(store, token, chat, sp, dt)
    if alerts.market_open() or "--force" in sys.argv:
        fired = alerts.check_alerts(store, token, chat, sp, dt, lang,
                                    save=lambda: storage.save_json("alerts.json", store))
        print(f"Checked alerts, {len(fired)} fired.")
    else:
        print("Market closed: commands answered, prices not checked.")
    if repr(store) != before:
        storage.save_json("alerts.json", store)


if __name__ == "__main__":
    main()
