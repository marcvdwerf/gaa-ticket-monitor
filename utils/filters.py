from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from config import FUZZY_MATCH_ENABLED, FUZZY_MATCH_THRESHOLD, REQUIRE_MATCHING_KEYWORDS, TRACKED_KEYWORDS

_DROP_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
}

_WHITESPACE_RE = re.compile(r"\s+")

# GAA sport termen - event MOET minstens één van deze bevatten
_GAA_SPORT_TERMS = [
    "hurling",
    "gaelic football",
    "gaa",
    "all-ireland",
    "all ireland",
    "leinster championship",
    "munster championship",
    "ulster championship",
    "connacht championship",
    "leinster final",
    "munster final",
    "ulster final",
    "connacht final",
    "allianz league",
    "national league",
    "gaa ticket",
    "county championship",
    "provincial final",
    "croke park",
    "páirc uí chaoimh",
    "semple stadium",
    "machale park",
    "fitzgerald stadium",
    "casement park",
    "gaelic",
    "intercounty",
    "inter-county",
]

# Woorden die bijna zeker GEEN GAA wedstrijd zijn
_NON_GAA_EXCLUSIONS = [
    "concert",
    "comedy",
    "festival",
    "exhibition",
    "conference",
    "wedding",
    "graduation",
    "cinema",
    "theatre",
    "theater",
    "museum",
    "tour guide",
    "sightseeing",
    "pub crawl",
    "night out",
    "dj",
    "stand-up",
    "stand up",
    "open mic",
    "craft beer",
    "wine tasting",
    "yoga",
    "pilates",
    "fitness class",
    "art exhibition",
    "networking",
    "business event",
    "charity gala",
]

# Platforms die altijd GAA-specifiek zijn - geen extra check nodig
_TRUSTED_GAA_PLATFORMS = {
    "gaa official",
    "gaa",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def slugify(value: str) -> str:
    cleaned = normalize_text(value).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    return cleaned.strip("-") or "unknown"


def normalize_url(url: str, base_url: str | None = None) -> str:
    if not url:
        return base_url or ""
    absolute = urljoin(base_url or "", url)
    parsed = urlparse(absolute)
    kept_query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in _DROP_QUERY_PARAMS]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", urlencode(kept_query), ""))


def fuzzy_contains_keyword(text: str, keywords: list[str] | None = None) -> bool:
    haystack = normalize_text(text).lower()
    if not haystack:
        return False

    for keyword in keywords or TRACKED_KEYWORDS:
        needle = normalize_text(keyword).lower()
        if not needle:
            continue
        if needle in haystack:
            return True
        if not FUZZY_MATCH_ENABLED:
            continue
        haystack_tokens = haystack.split()
        needle_tokens = needle.split()
        window_size = max(1, len(needle_tokens))
        for index in range(len(haystack_tokens)):
            candidate = " ".join(haystack_tokens[index : index + window_size + 1])
            if not candidate:
                continue
            if SequenceMatcher(None, candidate, needle).ratio() >= FUZZY_MATCH_THRESHOLD:
                return True
    return False


def is_gaa_sport_event(event: dict[str, Any]) -> bool:
    """
    Controleert of een event echt een GAA hurling of Gaelic football wedstrijd is.
    Events van het officiële GAA platform worden altijd vertrouwd.
    Voor andere platforms wordt gecheckt of er een GAA sport term in staat
    en of er geen duidelijke uitsluitingswoorden in staan.
    """
    platform = normalize_text(str(event.get("platform", ""))).lower()

    # Officieel GAA platform altijd vertrouwen
    if any(trusted in platform for trusted in _TRUSTED_GAA_PLATFORMS):
        return True

    searchable = normalize_text(" ".join([
        str(event.get("name", "")),
        str(event.get("venue", "")),
        str(event.get("competition", "")),
        str(event.get("status", "")),
    ])).lower()

    # Check op uitsluitingswoorden
    for exclusion in _NON_GAA_EXCLUSIONS:
        if exclusion in searchable:
            return False

    # Check of er minstens één GAA sport term in staat
    for term in _GAA_SPORT_TERMS:
        if term in searchable:
            return True

    return False


def matches_keywords(event: dict[str, Any], keywords: list[str] | None = None) -> bool:
    if not REQUIRE_MATCHING_KEYWORDS:
        return True

    searchable = " ".join(
        [
            str(event.get("name", "")),
            str(event.get("venue", "")),
            str(event.get("competition", "")),
            str(event.get("status", "")),
            str(event.get("platform", "")),
        ]
    )

    # Eerst keyword check
    if not fuzzy_contains_keyword(searchable, keywords=keywords):
        return False

    # Dan GAA sport check
    return is_gaa_sport_event(event)


def stable_event_id(platform_slug: str, name: str, date_text: str, venue: str) -> str:
    raw = "|".join([platform_slug, normalize_text(name).lower(), normalize_text(date_text).lower(), normalize_text(venue).lower()])
    return f"{platform_slug}:{slugify(name)}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def event_fingerprint(event: dict[str, Any]) -> str:
    payload = {
        "name": normalize_text(str(event.get("name", ""))),
        "venue": normalize_text(str(event.get("venue", ""))),
        "platform": normalize_text(str(event.get("platform", ""))),
        "date": normalize_text(str(event.get("date", ""))),
        "status": normalize_text(str(event.get("status", ""))),
        "url": normalize_url(str(event.get("url", ""))),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def extract_json_ld_candidates(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    items: list[dict[str, Any]] = []
    for script in soup.select("script[type='application/ld+json']"):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            items.extend([item for item in data if isinstance(item, dict)])
        elif isinstance(data, dict):
            items.append(data)
    return items


def text_or_default(value: Any, default: str = "Unknown") -> str:
    text = normalize_text(str(value))
    return text if text else default
