from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from config import EVENTBRITE_SEARCH_URL, EVENTBRITE_TOKEN, EVENTBRITE_URLS, MAX_EVENTS_PER_SOURCE, MONITOR_PLATFORM_NAMES, REQUEST_TIMEOUT
from utils.filters import extract_json_ld_candidates, normalize_text, normalize_url, stable_event_id, text_or_default


class EventbriteMonitor:
    platform_slug = "eventbrite"
    platform_name = MONITOR_PLATFORM_NAMES[platform_slug]

    def fetch_events(self, session, logger) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        if EVENTBRITE_TOKEN:
            try:
                events.extend(self._fetch_from_api(session, logger))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Eventbrite API failed, falling back to HTML: %s", exc)

        if not events:
            try:
                events.extend(self._fetch_from_html(session, logger))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Eventbrite HTML fallback failed: %s", exc)

        deduped = {item["event_id"]: item for item in events}
        return list(deduped.values())[:MAX_EVENTS_PER_SOURCE]

    def _fetch_from_api(self, session, logger) -> list[dict[str, Any]]:
        headers = {"Authorization": f"Bearer {EVENTBRITE_TOKEN}"}
        queries = ["gaa", "gaelic", "croke park"]
        collected: list[dict[str, Any]] = []
        for query in queries:
            response = session.get(
                EVENTBRITE_SEARCH_URL,
                headers=headers,
                params={
                    "q": query,
                    "location.address": "Ireland",
                    "expand": "venue",
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            for item in payload.get("events", []):
                name = text_or_default(item.get("name", {}).get("text"))
                venue = text_or_default((item.get("venue") or {}).get("name"), "Unknown venue")
                date_text = text_or_default(item.get("start", {}).get("utc") or item.get("start", {}).get("local"))
                event_url = normalize_url(item.get("url", ""))
                status = text_or_default(item.get("status"), "live")
                event_id = item.get("id") or stable_event_id(self.platform_slug, name, date_text, venue)
                collected.append(
                    {
                        "event_id": f"{self.platform_slug}:{event_id}",
                        "platform": self.platform_name,
                        "name": name,
                        "venue": venue,
                        "date": date_text,
                        "url": event_url,
                        "status": status,
                        "competition": name,
                    }
                )
        logger.info("Eventbrite API returned %s candidate events", len(collected))
        return collected

    def _fetch_from_html(self, session, logger) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        for url in EVENTBRITE_URLS:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            if response.status_code in {401, 403, 405, 429}:
                logger.warning("Eventbrite blocked %s with status %s", url, response.status_code)
                continue
            response.raise_for_status()
            html = response.text
            if "captcha" in html.lower() or "human verification" in html.lower():
                logger.warning("Eventbrite returned a human verification page for %s", url)
                continue

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
                if not any(token in text.lower() for token in ["gaa", "gaelic", "final", "semi", "hurling", "football", "croke"]):
                    continue
                parent_text = normalize_text(link.parent.get_text(" ", strip=True)) if link.parent else text
                date_match = re.search(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun).{0,90}?\d{4}\b", parent_text)
                date_text = text_or_default(date_match.group(0) if date_match else "Unknown")
                event_id = stable_event_id(self.platform_slug, text, date_text, "Eventbrite")
                collected.append(
                    {
                        "event_id": event_id,
                        "platform": self.platform_name,
                        "name": text,
                        "venue": "Eventbrite",
                        "date": date_text,
                        "url": href,
                        "status": "detected",
                        "competition": text,
                    }
                )

            for match in re.finditer(r'"name":"([^"]{8,180})"', html):
                name = normalize_text(match.group(1))
                if not any(token in name.lower() for token in ["gaa", "gaelic", "final", "semi", "hurling", "football", "croke"]):
                    continue
                event_id = stable_event_id(self.platform_slug, name, "Unknown", "Eventbrite")
                collected.append(
                    {
                        "event_id": event_id,
                        "platform": self.platform_name,
                        "name": name,
                        "venue": "Eventbrite",
                        "date": "Unknown",
                        "url": normalize_url(url),
                        "status": "detected",
                        "competition": name,
                    }
                )

        logger.info("Eventbrite HTML fallback returned %s candidate events", len(collected))
        return collected
