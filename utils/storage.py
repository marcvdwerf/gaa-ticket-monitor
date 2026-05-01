from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import SEEN_EVENTS_FILE


def ensure_storage_file(path: Path = SEEN_EVENTS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("{}\n", encoding="utf-8")


def load_seen_events(path: Path = SEEN_EVENTS_FILE) -> dict[str, dict[str, Any]]:
    ensure_storage_file(path)
    try:
        raw = path.read_text(encoding="utf-8").strip() or "{}"
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_seen_events(seen_events: dict[str, dict[str, Any]], path: Path = SEEN_EVENTS_FILE) -> None:
    ensure_storage_file(path)
    ordered = dict(sorted(seen_events.items(), key=lambda item: item[0]))
    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def update_seen_event(seen_events: dict[str, dict[str, Any]], event: dict[str, Any], fingerprint: str, now_utc: str) -> None:
    event_id = event["event_id"]
    previous = seen_events.get(event_id, {})
    seen_events[event_id] = {
        "event_id": event_id,
        "platform": event.get("platform", "Unknown"),
        "name": event.get("name", "Unknown"),
        "venue": event.get("venue", "Unknown"),
        "date": event.get("date", "Unknown"),
        "url": event.get("url", ""),
        "status": event.get("status", "unknown"),
        "fingerprint": fingerprint,
        "first_seen_utc": previous.get("first_seen_utc", now_utc),
        "last_seen_utc": now_utc,
        "last_alerted_utc": now_utc,
    }


def prune_seen_events(seen_events: dict[str, dict[str, Any]], max_items: int = 5000) -> dict[str, dict[str, Any]]:
    if len(seen_events) <= max_items:
        return seen_events

    sorted_items = sorted(
        seen_events.items(),
        key=lambda item: item[1].get("last_seen_utc", ""),
        reverse=True,
    )
    return dict(sorted_items[:max_items])
