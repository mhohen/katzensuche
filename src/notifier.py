"""ntfy.sh JSON push notifier (UTF-8 safe, supports photo preview & direct click URL).

Both spouses/family members simply subscribe to the exact same topic name
in the free ntfy mobile app (iOS / Android) to receive every alert simultaneously.
Multiple comma-separated topics in NTFY_TOPIC are also supported if needed.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from .config import WatcherConfig
from .models import FilterDecision, Listing

PLATFORM_LABELS = {
    "willhaben": "Willhaben",
    "landwirt": "Landwirt.com",
    "tieranzeigen": "Tieranzeigen.at",
}


def get_topics(config: WatcherConfig) -> list[str]:
    return [t.strip() for t in config.ntfy_topic.split(",") if t.strip()]


def build_listing_payload(
    topic: str,
    listing: Listing,
    decision: FilterDecision,
    priority: int = 4,
) -> dict:
    """Build an ntfy JSON API payload for a matched cat listing."""
    platform_name = PLATFORM_LABELS.get(listing.platform, listing.platform)
    dist_str = f"{listing.distance_km:.0f} km" if listing.distance_km is not None else "Nähe Linz"
    loc_parts = [p for p in (listing.postcode, listing.location) if p]
    loc_str = " ".join(loc_parts) or listing.district or "Oberösterreich"

    title = f"🐱 {listing.price_display} · {dist_str} · {platform_name}"

    lines = [
        listing.title,
        f"📍 {loc_str} ({dist_str} von Linz)",
        f"💶 {listing.price_display} · 🐾 {decision.gender_label}",
    ]
    if listing.description:
        snippet = listing.description.replace("\n", " ").strip()
        if len(snippet) > 220:
            snippet = snippet[:217].rstrip() + "..."
        lines.append("")
        lines.append(snippet)

    payload: dict = {
        "topic": topic,
        "title": title,
        "message": "\n".join(lines),
        "priority": priority,
        "tags": ["cat"],
        "click": listing.url,
        "actions": [
            {
                "action": "view",
                "label": f"Auf {platform_name} öffnen",
                "url": listing.url,
                "clear": True,
            }
        ],
    }
    if listing.image_url and listing.image_url.startswith("http"):
        payload["attach"] = listing.image_url

    return payload


def send_ntfy_payload(payload: dict, config: WatcherConfig) -> None:
    """Send a JSON payload to the configured ntfy server."""
    url = config.ntfy_server
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "katzen-watcher/1.0",
    }
    if config.ntfy_token:
        headers["Authorization"] = f"Bearer {config.ntfy_token}"

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=config.http_timeout_sec) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")[:300]
        raise RuntimeError(f"ntfy HTTP {e.code}: {detail}") from e


def notify_listing(
    listing: Listing,
    decision: FilterDecision,
    config: WatcherConfig,
    dry_run: bool = False,
) -> bool:
    """Send a push notification for a matched listing to all configured ntfy topics."""
    topics = get_topics(config)
    if not topics:
        if not dry_run:
            print("[WARN] NTFY_TOPIC ist nicht gesetzt – überspringe Push-Benachrichtigung.")
        return False

    for topic in topics:
        payload = build_listing_payload(topic, listing, decision, priority=config.ntfy_priority)
        if dry_run:
            print(f"[DRY-RUN ntfy -> {topic}] {payload['title']}\n{payload['message']}\n{payload['click']}\n")
        else:
            send_ntfy_payload(payload, config)
    return True


def notify_status(
    title: str,
    message: str,
    config: WatcherConfig,
    priority: int = 3,
    tags: Optional[list[str]] = None,
    click_url: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    """Send a status, startup, or health-warning message via ntfy."""
    topics = get_topics(config)
    if not topics:
        return False

    for topic in topics:
        payload: dict = {
            "topic": topic,
            "title": title,
            "message": message,
            "priority": priority,
            "tags": tags or ["information_source"],
        }
        if click_url:
            payload["click"] = click_url
        if dry_run:
            print(f"[DRY-RUN ntfy status -> {topic}] {title}: {message}")
        else:
            send_ntfy_payload(payload, config)
    return True
