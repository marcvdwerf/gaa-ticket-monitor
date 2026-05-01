from __future__ import annotations

from typing import Any

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


MD_V2_SPECIALS = r"_*[]()~`>#+-=|{}.!"


def escape_markdown_v2(text: str) -> str:
    safe = text or ""
    for char in MD_V2_SPECIALS:
        safe = safe.replace(char, f"\\{char}")
    return safe


def build_alert_message(event: dict[str, Any], detected_utc: str) -> str:
    return "\n".join(
        [
            "🚨 *NEW GAA TICKETS LIVE*",
            "",
            f"*Event:* {escape_markdown_v2(event.get('name', 'Unknown'))}",
            f"*Venue:* {escape_markdown_v2(event.get('venue', 'Unknown'))}",
            f"*Platform:* {escape_markdown_v2(event.get('platform', 'Unknown'))}",
            f"*Date:* {escape_markdown_v2(event.get('date', 'Unknown'))}",
            f"*Status:* {escape_markdown_v2(event.get('status', 'unknown'))}",
            "",
            "*Tickets:*",
            escape_markdown_v2(event.get('url', '')),
            "",
            f"*Detected:* {escape_markdown_v2(detected_utc)}",
        ]
    )


def send_telegram_message(session: requests.Session, message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    response = session.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": False,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return bool(payload.get("ok"))
