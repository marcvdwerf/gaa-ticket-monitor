from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from config import GAA_URLS, MAX_EVENTS_PER_SOURCE, MONITOR_PLATFORM_NAMES, REQUEST_TIMEOUT
from utils.filters import normalize_text, normalize_url, stable_event_id, text_or_default


class GAAMonitor:
    platform_slug = "gaa"
    platform_name = MONITOR_PLATFORM_NAMES[platform_slug]

    def fetch_events(self, session, logger) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []

        for url in GAA_URLS:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            html = response.text
            soup = BeautifulSoup(html, "lxml")
            page_text = normalize_text(soup.get_text("\n", strip=True))

            section_patterns = [
                ("Now On Sale", "onsale"),
                ("On Sale Soon", "coming soon"),
            ]

            for heading, status in section_patterns:
                if heading not in page_text:
                    continue
                section_text = page_text.split(heading, 1)[1]
                lines = [normalize_text(line) for line in section_text.split("\n") if normalize_text(line)]
                lines = lines[:60]
                for index, line in enumerate(lines):
                    if len(line) < 10:
                        continue
                    if not any(keyword in line.lower() for keyword in ["gaa", "championship", "cup", "final", "hurling", "football"]):
                        continue
                    date_text = "Unknown"
                    if index >= 1:
                        possible_date = normalize_text(" ".join(lines[max(0, index - 2):index]))
                        if re.search(r"\b\d{1,2}\s+[A-Z][a-z]{2}\b|\bto\b", possible_date):
                            date_text = possible_date
                    event_id = stable_event_id(self.platform_slug, line, date_text, "Official GAA Tickets")
                    collected.append(
                        {
                            "event_id": event_id,
                            "platform": self.platform_name,
                            "name": line,
                            "venue": "Official GAA Tickets",
                            "date": date_text,
                            "url": normalize_url(url),
                            "status": status,
                            "competition": line,
                        }
                    )

            # Additional generic link discovery in case the page gains event-specific links later.
            for link in soup.select("a[href]"):
                text = normalize_text(link.get_text(" ", strip=True))
                if len(text) < 10:
                    continue
                if not any(token in text.lower() for token in ["gaa", "championship", "cup", "final", "hurling", "football"]):
                    continue
                href = normalize_url(link.get("href", ""), base_url=url)
                event_id = stable_event_id(self.platform_slug, text, "Unknown", "Official GAA Tickets")
                collected.append(
                    {
                        "event_id": event_id,
                        "platform": self.platform_name,
                        "name": text_or_default(text),
                        "venue": "Official GAA Tickets",
                        "date": "Unknown",
                        "url": href,
                        "status": "detected",
                        "competition": text,
                    }
                )

        deduped = {item["event_id"]: item for item in collected}
        logger.info("GAA monitor returned %s candidate events", len(deduped))
        return list(deduped.values())[:MAX_EVENTS_PER_SOURCE]
