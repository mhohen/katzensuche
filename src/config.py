"""Configuration for the Linz Bauernhofkatze watcher.

All core thresholds can also be overridden via environment variables so you
can tweak them in GitHub Actions or locally without editing code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class WatcherConfig:
    # Center point: Linz Hauptplatz (Oberösterreich)
    center_lat: float = field(default_factory=lambda: _env_float("CENTER_LAT", 48.3069))
    center_lng: float = field(default_factory=lambda: _env_float("CENTER_LNG", 14.2858))
    max_distance_km: float = field(default_factory=lambda: _env_float("MAX_DISTANCE_KM", 50.0))

    # Price limit in EUR (None / "zu verschenken" / "Preis auf Anfrage" are allowed)
    max_price_eur: float = field(default_factory=lambda: _env_float("MAX_PRICE_EUR", 300.0))

    # Age limit in months (rejects clearly older/adult cats)
    max_age_months: int = field(default_factory=lambda: _env_int("MAX_AGE_MONTHS", 7))

    # ntfy notification settings
    ntfy_server: str = field(
        default_factory=lambda: (
            os.environ.get("NTFY_SERVER", "").strip() or "https://ntfy.sh"
        ).rstrip("/")
    )
    ntfy_topic: str = field(default_factory=lambda: os.environ.get("NTFY_TOPIC", "").strip())
    ntfy_token: str = field(default_factory=lambda: os.environ.get("NTFY_TOKEN", "").strip())
    ntfy_priority: int = field(default_factory=lambda: _env_int("NTFY_PRIORITY", 4))

    # Alerting threshold for consecutive platform failures (e.g. 6 * 5 min = 30 min)
    error_alert_threshold: int = field(
        default_factory=lambda: _env_int("ERROR_ALERT_THRESHOLD", 6)
    )

    # Prune seen entries older than N days to keep state file small forever
    state_retention_days: int = field(
        default_factory=lambda: _env_int("STATE_RETENTION_DAYS", 90)
    )

    # HTTP timeout per request in seconds
    http_timeout_sec: int = field(default_factory=lambda: _env_int("HTTP_TIMEOUT_SEC", 20))


# Platforms and their search URLs
WILLHABEN_SEARCH_URLS = [
    # Hauskatzen - Oberösterreich (areaId=4), neueste zuerst
    (
        "willhaben_ooe_hauskatzen",
        "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz/katzen/hauskatzen-4969?areaId=4&sort=1&rows=30",
        False,  # require_farm_or_mix_keyword
    ),
    # Hauskatzen - Niederösterreich (areaId=3, für St. Valentin, Ennsdorf, Haag, Amstetten nahe Linz)
    (
        "willhaben_noe_hauskatzen",
        "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz/katzen/hauskatzen-4969?areaId=3&sort=1&rows=30",
        False,
    ),
    # Rassekatzen/Mischlinge - Oberösterreich (nur wenn Bauernhof/Hauskatze/EKH/Mix erwähnt)
    (
        "willhaben_ooe_mischlinge",
        "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz/katzen/rassekatzen-mischlinge-4970?areaId=4&sort=1&rows=30",
        True,
    ),
]

LANDWIRT_SEARCH_URL = "https://www.landwirt.com/kleinanzeigen/katzen"

TIERANZEIGEN_SEARCH_URLS = [
    ("tieranzeigen_ooe", "https://www.tieranzeigen.at/oberoesterreich/katzen/"),
    ("tieranzeigen_noe", "https://www.tieranzeigen.at/niederoesterreich/katzen/"),
]
