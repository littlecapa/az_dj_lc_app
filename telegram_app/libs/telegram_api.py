"""Zentrale API-Funktion zum Versenden von Telegram-Nachrichten.

Nutzt den Telegram-Bot (Konfiguration via TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
in .env bzw. Azure App Settings). Jede erfolgreich versendete Nachricht wird
in TelegramMessage protokolliert.
"""
import logging

import requests
from django.conf import settings

from ..models import TelegramMessage

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
REQUEST_TIMEOUT_SECONDS = 10


def send_telegram_message(text: str, trigger: str = "") -> bool:
    """Sendet `text` per Telegram Bot API an den konfigurierten Chat.

    Bei Erfolg wird die Nachricht in TelegramMessage protokolliert (inkl.
    Zeitstempel und optionalem `trigger`, aktuell nur als Vorbereitung für
    zukünftige automatische Auslöser gedacht).

    Gibt True bei Erfolg zurück, False bei fehlender Konfiguration oder
    einem Fehler beim Versand. Wirft keine Exception nach außen.
    """
    text = (text or "").strip()
    if not text:
        return False

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", None)

    if not token or not chat_id:
        logger.error("Telegram: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID nicht konfiguriert.")
        return False

    try:
        response = requests.post(
            TELEGRAM_API_URL.format(token=token),
            data={"chat_id": chat_id, "text": text},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        success = response.ok and response.json().get("ok", False)
        if not success:
            logger.error("Telegram-Versand fehlgeschlagen: %s", response.text[:500])
    except requests.RequestException as exc:
        logger.error("Telegram-Versand fehlgeschlagen (Exception): %s", exc)
        success = False

    if success:
        TelegramMessage.objects.create(message=text, trigger=trigger or "")

    return success
