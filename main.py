from __future__ import annotations

import concurrent.futures
import sys
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import DEFAULT_RATE_LIMIT_SECONDS, HEALTHCHECK_VERBOSE, HTTP_RETRY_BACKOFF, HTTP_RETRY_TOTAL, MAX_WORKERS, REQUEST_HEADERS
from monitors.croke_park import CrokeParkMonitor
from monitors.eventbrite import EventbriteMonitor
from monitors.gaa import GAAMonitor
from monitors.ticketmaster import TicketmasterMonitor
from monitors.tickets_ie import TicketsIEMonitor
from monitors.universe import UniverseMonitor
from utils.filters import event_fingerprint, matches_keywords, utc_now_iso
from utils.logger import setup_logger
from utils.storage import load_seen_events, prune_seen_events, save_seen_events, update_seen_event
from utils.telegram import build_alert_message, send_telegram_message

logger = setup_logger()


def build_session() -> requests.Session:
    retry = Retry(
        total=HTTP_RETRY_TOTAL,
        read=HTTP_RETRY_TOTAL,
        connect=HTTP_RETRY_TOTAL,
        backoff_factor=HTTP_RETRY_BACKOFF,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def run_monitor(monitor: Any) -> list[dict[str, Any]]:
    session = build_session()
    try:
        start = time.perf_counter()
        events = monitor.fetch_events(session, logger)
        elapsed = time.perf_counter() - start
        logger.info("%s finished in %.2fs with %s raw events", monitor.platform_name, elapsed, len(events))
        time.sleep(DEFAULT_RATE_LIMIT_SECONDS)
        return events
    finally:
        session.close()


def main() -> int:
    started_utc = utc_now_iso()
    logger.info("Starting GAA ticket monitor run at %s", started_utc)
    seen_events = load_seen_events()
    telegram_session = build_session()
    monitors = [
        TicketmasterMonitor(),
        GAAMonitor(),
        TicketsIEMonitor(),
        UniverseMonitor(),
        EventbriteMonitor(),
        CrokeParkMonitor(),
    ]

    all_events: list[dict[str, Any]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(monitors))) as executor:
        future_map = {executor.submit(run_monitor, monitor): monitor.platform_name for monitor in monitors}
        for future in concurrent.futures.as_completed(future_map):
            platform_name = future_map[future]
            try:
                all_events.extend(future.result())
            except Exception as exc:  # noqa: BLE001
                logger.exception("Monitor %s failed: %s", platform_name, exc)

    deduped_candidates: dict[str, dict[str, Any]] = {}
    for event in all_events:
        deduped_candidates[event["event_id"]] = event
    candidate_events = list(deduped_candidates.values())

    logger.info("Collected %s unique candidate events before keyword filtering", len(candidate_events))

    filtered_events = [event for event in candidate_events if matches_keywords(event)]
    logger.info("%s events remained after keyword filtering", len(filtered_events))

    new_or_changed: list[dict[str, Any]] = []
    now_utc = utc_now_iso()

    for event in filtered_events:
        fingerprint = event_fingerprint(event)
        previous = seen_events.get(event["event_id"])
        is_new = previous is None
        has_changed = bool(previous and previous.get("fingerprint") != fingerprint)

        if is_new or has_changed:
            new_or_changed.append(event)
            update_seen_event(seen_events, event, fingerprint, now_utc)
        else:
            seen_events[event["event_id"]]["last_seen_utc"] = now_utc

    alerts_sent = 0
    for event in sorted(new_or_changed, key=lambda item: (item.get("platform", ""), item.get("date", ""), item.get("name", ""))):
        message = build_alert_message(event, now_utc)
        try:
            sent = send_telegram_message(telegram_session, message)
            if sent:
                alerts_sent += 1
                logger.info("Alert sent for %s", event.get("name", "Unknown event"))
            else:
                logger.warning("Telegram not configured or rejected message for %s", event.get("name", "Unknown event"))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send Telegram alert for %s: %s", event.get("name", "Unknown event"), exc)

    seen_events = prune_seen_events(seen_events)
    save_seen_events(seen_events)

    if HEALTHCHECK_VERBOSE:
        logger.info(
            "Healthcheck | total_raw=%s | unique=%s | filtered=%s | alerts=%s | seen_store=%s",
            len(all_events),
            len(candidate_events),
            len(filtered_events),
            alerts_sent,
            len(seen_events),
        )

    logger.info("Completed monitor run at %s", utc_now_iso())
    telegram_session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
