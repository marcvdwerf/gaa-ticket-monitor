from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from config import MAX_EVENTS_PER_SOURCE, MONITOR_PLATFORM_NAMES, REQUEST_TIMEOUT, TICKETS_IE_URLS
from utils.filters import extract_json_ld_candidates, normalize_text, normalize_url, stable_event_id, text_or_default


class TicketsIEMonitor:
    platform_slug = "tickets_ie"
    platform_name = MONITOR_PLATFORM_NAMES[platform_slug]

    def fetch_events(self, session, logger) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []

        for url in TICKETS_IE_URLS:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            if response.status_code in {401, 403, 405, 429}:
                logger.warning("Tickets.ie blocked %s with status %s", url, response.status_code)
                continue
            response.raise_for_status()
            html = response.text

            for block in extract_json_ld_candidates(html):
                if block.get("@type") != "Event":
                    continue
                name = text_or_default(block.get("name"))
                venue = text_or_default(block.get("location", {}).get("name"), "Unknown venue")
                date_text = text_or_default(block.get("startDate"))
                event_url = normalize_url(block.get("url") or url, base_url=url)
                event_id = stable_event_id(self.platform_slug, name, date_text, venue)
                collected.append(
                    {
                        "event_id": event_id,
                        "platform": self.platform_name,
                        "name": name,
                        "venue": venue,
                        "date": date_text,
                        "url": event_url,
                        "status": "onsale",
                        "competition": name,
                    }
                )

            soup = BeautifulSoup(html, "lxml")
            for link in soup.select("a[href]"):
                href = normalize_url(link.get("href", ""), base_url=url)
                text = normalize_text(link.get_text(" ", strip=True))
                if not href or len(text) < 10:
                    continue
                if not any(token in text.lower() for token in ["gaa", "final", "semi", "hurling", "football", "croke", " v "]):
                    continue
                parent_text = normalize_text(link.parent.get_text(" ", strip=True)) if link.parent else text
                date_match = re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b.*?\d{4}", parent_text)
                date_text = text_or_default(date_match.group(0) if date_match else "Unknown")
                event_id = stable_event_id(self.platform_slug, text, date_text, "Tickets.ie")
                collected.append(
                    {
                        "event_id": event_id,
                        "platform": self.platform_name,
                        "name": text,
                        "venue": "Tickets.ie",
                        "date": date_text,
                        "url": href,
                        "status": "detected",
                        "competition": text,
                    }
                )

            # Regex fallback for JavaScript-rendered data embedded in the HTML source.
            for match in re.finditer(r'"name"\s*:\s*"([^"]{8,180})"', html):
                name = normalize_text(match.group(1))
                if not any(token in name.lower() for token in ["gaa", "final", "semi", "hurling", "football", "croke", " v "]):
                    continue
                event_id = stable_event_id(self.platform_slug, name, "Unknown", "Tickets.ie")
                collected.append(
                    {
                        "event_id": event_id,
                        "platform": self.platform_name,
                        "name": name,
                        "venue": "Tickets.ie",
                        "date": "Unknown",
                        "url": normalize_url(url),
                        "status": "detected",
                        "competition": name,
                    }
                )

        deduped = {item["event_id"]: item for item in collected}
        logger.info("Tickets.ie monitor returned %s candidate events", len(deduped))
        return list(deduped.values())[:MAX_EVENTS_PER_SOURCE]
