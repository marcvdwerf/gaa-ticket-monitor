from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from config import MAX_EVENTS_PER_SOURCE, MONITOR_PLATFORM_NAMES, REQUEST_TIMEOUT, UNIVERSE_URLS
from utils.filters import extract_json_ld_candidates, normalize_text, normalize_url, stable_event_id, text_or_default


class UniverseMonitor:
    platform_slug = "universe"
    platform_name = MONITOR_PLATFORM_NAMES[platform_slug]

    def fetch_events(self, session, logger) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []

        for url in UNIVERSE_URLS:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            if response.status_code in {401, 403, 405, 429}:
                logger.warning("Universe blocked %s with status %s", url, response.status_code)
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
                if not href or "/events/" not in href or len(text) < 10:
                    continue
                if not any(token in text.lower() for token in ["gaa", "final", "semi", "hurling", "football", "croke", " v "]):
                    continue
                parent_text = normalize_text(link.parent.get_text(" ", strip=True)) if link.parent else text
                date_match = re.search(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun).{0,80}?\d{4}\b", parent_text)
                date_text = text_or_default(date_match.group(0) if date_match else "Unknown")
                event_id = stable_event_id(self.platform_slug, text, date_text, "Universe")
                collected.append(
                    {
                        "event_id": event_id,
                        "platform": self.platform_name,
                        "name": text,
                        "venue": "Universe",
                        "date": date_text,
                        "url": href,
                        "status": "detected",
                        "competition": text,
                    }
                )

            for match in re.finditer(r'/events/([a-z0-9\-]+-tickets-[A-Z0-9]+)', html, flags=re.IGNORECASE):
                slug = match.group(1)
                event_url = f"https://www.universe.com/events/{slug}"
                name = normalize_text(slug.replace("-tickets", "").replace("-", " ").title())
                if not any(token in name.lower() for token in ["gaa", "final", "semi", "hurling", "football", "croke", " v "]):
                    continue
                event_id = stable_event_id(self.platform_slug, name, "Unknown", "Universe")
                collected.append(
                    {
                        "event_id": event_id,
                        "platform": self.platform_name,
                        "name": name,
                        "venue": "Universe",
                        "date": "Unknown",
                        "url": normalize_url(event_url),
                        "status": "detected",
                        "competition": name,
                    }
                )

        deduped = {item["event_id"]: item for item in collected}
        logger.info("Universe monitor returned %s candidate events", len(deduped))
        return list(deduped.values())[:MAX_EVENTS_PER_SOURCE]
