"""
Telegram 推播
從環境變數讀 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
"""

import os
import requests


def send(text):
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # Telegram 訊息上限 4096 字元,超過就截斷
    if len(text) > 4000:
        text = text[:4000] + "\n\n...(已截斷)"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }

    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()
