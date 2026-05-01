from __future__ import annotations

import re
import time
from typing import Any

from bs4 import BeautifulSoup

from config import MAX_EVENTS_PER_SOURCE, MONITOR_PLATFORM_NAMES, REQUEST_TIMEOUT, TICKETMASTER_DISCOVERY_URL, TICKETMASTER_FALLBACK_URLS, TM_API_KEY
from utils.filters import extract_json_ld_candidates, normalize_text, normalize_url, stable_event_id, text_or_default


class TicketmasterMonitor:
    platform_slug = "ticketmaster"
    platform_name = MONITOR_PLATFORM_NAMES[platform_slug]

    def fetch_events(self, session, logger) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        if TM_API_KEY:
            try:
                events.extend(self._fetch_from_api(session, logger))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ticketmaster API failed, falling back to HTML: %s", exc)

        if not events:
            try:
                events.extend(self._fetch_from_html(session, logger))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Ticketmaster HTML fallback failed: %s", exc)

        deduped: dict[str, dict[str, Any]] = {}
        for event in events:
            deduped[event["event_id"]] = event
        return list(deduped.values())[:MAX_EVENTS_PER_SOURCE]

    def _fetch_from_api(self, session, logger) -> list[dict[str, Any]]:
        queries = ["gaa", "croke park", "all-ireland"]
        collected: list[dict[str, Any]] = []

        for query in queries:
            response = session.get(
                TICKETMASTER_DISCOVERY_URL,
                params={
                    "apikey": TM_API_KEY,
                    "countryCode": "IE",
                    "keyword": query,
                    "size": 100,
                    "sort": "date,asc",
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            for item in payload.get("_embedded", {}).get("events", []):
                venue_block = (item.get("_embedded", {}).get("venues") or [{}])[0]
                date_block = item.get("dates", {}).get("start", {})
                status_block = item.get("dates", {}).get("status", {})
                name = text_or_default(item.get("name"))
                venue = text_or_default(venue_block.get("name") or venue_block.get("city", {}).get("name"))
                date_text = text_or_default(date_block.get("localDate") or date_block.get("dateTime"))
                url = normalize_url(item.get("url", ""))
                event_id = item.get("id") or stable_event_id(self.platform_slug, name, date_text, venue)
                collected.append(
                    {
                        "event_id": f"{self.platform_slug}:{event_id}",
                        "platform": self.platform_name,
                        "name": name,
                        "venue": venue,
                        "date": date_text,
                        "url": url,
                        "status": text_or_default(status_block.get("code") or status_block.get("description"), "onsale"),
                        "competition": text_or_default(item.get("classifications", [{}])[0].get("segment", {}).get("name", "GAA"), "GAA"),
                    }
                )
            time.sleep(0.35)

        logger.info("Ticketmaster API returned %s candidate events", len(collected))
        return collected

    def _fetch_from_html(self, session, logger) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for url in TICKETMASTER_FALLBACK_URLS:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            if response.status_code in {401, 403, 405, 429}:
                logger.warning("Ticketmaster HTML blocked for %s with status %s", url, response.status_code)
                continue
            response.raise_for_status()
            html = response.text

            # First try structured data.
            for block in extract_json_ld_candidates(html):
                if block.get("@type") != "Event":
                    continue
                name = text_or_default(block.get("name"))
                venue = text_or_default(block.get("location", {}).get("name"), "Unknown venue")
                date_text = text_or_default(block.get("startDate"))
                event_url = normalize_url(block.get("url") or url, base_url=url)
                event_id = stable_event_id(self.platform_slug, name, date_text, venue)
                if event_url in seen_urls:
                    continue
                seen_urls.add(event_url)
                collected.append(
                    {
                        "event_id": event_id,
                        "platform": self.platform_name,
                        "name": name,
                        "venue": venue,
                        "date": date_text,
                        "url": event_url,
                        "status": "onsale",
                        "competition": "GAA",
                    }
                )

            # Heuristic fallback: scrape event links and surrounding text.
            soup = BeautifulSoup(html, "lxml")
            for link in soup.select("a[href]"):
                href = normalize_url(link.get("href", ""), base_url=url)
                text = normalize_text(link.get_text(" ", strip=True))
                if not href or href in seen_urls or len(text) < 8:
                    continue
                if "/artist/" in href:
                    continue
                if not any(token in text.lower() for token in ["gaa", "final", "semi", "hurling", "football", "croke", "v ", " v "]):
                    continue
                parent_text = normalize_text(link.parent.get_text(" ", strip=True)) if link.parent else text
                date_match = re.search(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b.*?(?=(?:[A-Z][a-z]+,?\s*[A-Z]{1,3}|$))", parent_text)
                date_text = text_or_default(date_match.group(0) if date_match else "Unknown")
                venue_guess = "Unknown venue"
                venue_match = re.search(r"(?:Dublin|Cork|Galway|Kerry|Limerick|Kilkenny|Wexford|Armagh|Monaghan|Roscommon|Offaly|Tipperary|Laois|Kildare|Waterford|Clare).*", parent_text)
                if venue_match:
                    venue_guess = venue_match.group(0)[:120]
                event_id = stable_event_id(self.platform_slug, text, date_text, venue_guess)
                seen_urls.add(href)
                collected.append(
                    {
                        "event_id": event_id,
                        "platform": self.platform_name,
                        "name": text,
                        "venue": venue_guess,
                        "date": date_text,
                        "url": href,
                        "status": "onsale",
                        "competition": "GAA",
                    }
                )

            # Sometimes Ticketmaster exposes JSON blobs with event names.
            json_hits = re.findall(r'"name":"([^"]{8,160})"', html)
            for hit in json_hits[:30]:
                text = normalize_text(hit)
                if not any(token in text.lower() for token in ["gaa", "final", "semi", "hurling", "football", "croke", " v "]):
                    continue
                event_id = stable_event_id(self.platform_slug, text, "Unknown", "Unknown venue")
                collected.append(
                    {
                        "event_id": event_id,
                        "platform": self.platform_name,
                        "name": text,
                        "venue": "Unknown venue",
                        "date": "Unknown",
                        "url": url,
                        "status": "detected",
                        "competition": "GAA",
                    }
                )

            time.sleep(0.35)

        logger.info("Ticketmaster HTML fallback returned %s candidate events", len(collected))
        return collected
