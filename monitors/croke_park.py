from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from config import CROKE_PARK_URLS, MAX_EVENTS_PER_SOURCE, MONITOR_PLATFORM_NAMES, REQUEST_TIMEOUT
from utils.filters import normalize_text, normalize_url, stable_event_id


class CrokeParkMonitor:
    platform_slug = "croke_park"
    platform_name = MONITOR_PLATFORM_NAMES[platform_slug]

    def fetch_events(self, session, logger) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        for url in CROKE_PARK_URLS:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")

            headings = soup.select("h1, h2, h3, h4, a[href]")
            for node in headings:
                text = normalize_text(node.get_text(" ", strip=True))
                if len(text) < 8:
                    continue
                if not any(token in text.lower() for token in ["croke park", "gaa", "fixture", "match", "ticket", "final", "semi", "hurling", "football"]):
                    continue
                href = normalize_url(node.get("href", "") if getattr(node, 'attrs', None) else url, base_url=url) or normalize_url(url)
                surrounding = normalize_text(node.parent.get_text(" ", strip=True)) if node.parent else text
                status = "coming soon" if "soon" in surrounding.lower() else "detected"
                date_match = re.search(r"\b\d{1,2}\s+[A-Z][a-z]{2,8}\b|\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun).{0,80}?\d{4}\b", surrounding)
                date_text = date_match.group(0) if date_match else "Unknown"
                event_id = stable_event_id(self.platform_slug, text, date_text, "Croke Park")
                collected.append(
                    {
                        "event_id": event_id,
                        "platform": self.platform_name,
                        "name": text,
                        "venue": "Croke Park",
                        "date": date_text,
                        "url": href,
                        "status": status,
                        "competition": text,
                    }
                )

        deduped = {item["event_id"]: item for item in collected}
        logger.info("Croke Park monitor returned %s candidate events", len(deduped))
        return list(deduped.values())[:MAX_EVENTS_PER_SOURCE]
