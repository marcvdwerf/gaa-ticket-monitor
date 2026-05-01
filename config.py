from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

load_dotenv()

BASE_DIR: Final[Path] = Path(__file__).resolve().parent
SEEN_EVENTS_FILE: Final[Path] = BASE_DIR / "seen_events.json"
LOG_LEVEL: Final[str] = os.getenv("LOG_LEVEL", "INFO").upper()
REQUEST_TIMEOUT: Final[int] = int(os.getenv("REQUEST_TIMEOUT", "20"))
MAX_WORKERS: Final[int] = int(os.getenv("MAX_WORKERS", "5"))
MAX_EVENTS_PER_SOURCE: Final[int] = int(os.getenv("MAX_EVENTS_PER_SOURCE", "100"))
DEFAULT_RATE_LIMIT_SECONDS: Final[float] = float(os.getenv("DEFAULT_RATE_LIMIT_SECONDS", "1.0"))
HTTP_RETRY_TOTAL: Final[int] = int(os.getenv("HTTP_RETRY_TOTAL", "3"))
HTTP_RETRY_BACKOFF: Final[float] = float(os.getenv("HTTP_RETRY_BACKOFF", "1.0"))
HEALTHCHECK_VERBOSE: Final[bool] = os.getenv("HEALTHCHECK_VERBOSE", "true").lower() == "true"

TELEGRAM_BOT_TOKEN: Final[str] = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: Final[str] = os.getenv("TELEGRAM_CHAT_ID", "")

# Optional tokens / API keys. The monitor works without them, but coverage improves if added.
TM_API_KEY: Final[str] = os.getenv("TM_API_KEY", "")
EVENTBRITE_TOKEN: Final[str] = os.getenv("EVENTBRITE_TOKEN", "")

TRACKED_KEYWORDS: Final[list[str]] = [
    item.strip()
    for item in os.getenv(
        "TRACKED_KEYWORDS",
        "Dublin,Kerry,Mayo,Cork,Galway,All-Ireland,Semi Final,Final,Hurling,Football,Croke Park,Leinster,Munster,Ulster",
    ).split(",")
    if item.strip()
]

REQUIRE_MATCHING_KEYWORDS: Final[bool] = os.getenv("REQUIRE_MATCHING_KEYWORDS", "true").lower() == "true"
FUZZY_MATCH_ENABLED: Final[bool] = os.getenv("FUZZY_MATCH_ENABLED", "true").lower() == "true"
FUZZY_MATCH_THRESHOLD: Final[float] = float(os.getenv("FUZZY_MATCH_THRESHOLD", "0.86"))

USER_AGENT: Final[str] = os.getenv(
    "USER_AGENT",
    "TravelBeyondThePitch-GAA-Ticket-Monitor/1.0 (+https://github.com/)",
)

REQUEST_HEADERS: Final[dict[str, str]] = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
    "Accept-Language": "en-IE,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

TICKETMASTER_DISCOVERY_URL: Final[str] = "https://app.ticketmaster.com/discovery/v2/events.json"
TICKETMASTER_FALLBACK_URLS: Final[list[str]] = [
    "https://www.ticketmaster.ie/search?q=gaa",
    "https://www.ticketmaster.ie/browse/gaa-catid-729/sport-rid-10004/all-of-ireland-dma-608",
    "https://www.ticketmaster.ie/search?q=croke+park",
]
GAA_URLS: Final[list[str]] = [
    "https://www.gaa.ie/tickets",
]
TICKETS_IE_URLS: Final[list[str]] = [
    "https://www.tickets.ie/gaa-3/",
    "https://www.tickets.ie/",
]
UNIVERSE_URLS: Final[list[str]] = [
    "https://www.universe.com/explore?query=gaa&loc=Ireland",
]
EVENTBRITE_SEARCH_URL: Final[str] = "https://www.eventbriteapi.com/v3/events/search/"
EVENTBRITE_URLS: Final[list[str]] = [
    "https://www.eventbrite.ie/d/ireland/gaa/",
    "https://www.eventbrite.com/d/ireland/gaelic/",
]
CROKE_PARK_URLS: Final[list[str]] = [
    "https://crokepark.ie/",
    "https://crokepark.ie/matchday",
    "https://crokepark.ie/events",
    "https://crokepark.ie/concerts",
]

MONITOR_PLATFORM_NAMES: Final[dict[str, str]] = {
    "ticketmaster": "Ticketmaster Ireland",
    "gaa": "GAA Official",
    "tickets_ie": "Tickets.ie",
    "universe": "Universe",
    "eventbrite": "Eventbrite",
    "croke_park": "Croke Park",
}
