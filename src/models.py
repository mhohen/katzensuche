"""Data models and geographic distance helper."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Listing:
    platform: str          # "willhaben", "landwirt", "tieranzeigen"
    ad_id: str             # Platform-specific unique ID
    title: str
    url: str
    description: str = ""
    price_eur: Optional[float] = None
    price_display: str = ""
    postcode: str = ""
    location: str = ""
    district: str = ""
    country: str = "AT"
    lat: Optional[float] = None
    lng: Optional[float] = None
    distance_km: Optional[float] = None
    seller_name: str = ""
    category: str = ""
    gender_field: str = ""   # Structured gender field if available (e.g. Tieranzeigen)
    age_field: str = ""      # Structured age field if available (e.g. Tieranzeigen)
    published_at: str = ""
    image_url: str = ""
    reserved: bool = False
    require_farm_or_mix_keyword: bool = False
    extra_tags: list[str] = field(default_factory=list)

    @property
    def unique_key(self) -> str:
        return f"{self.platform}:{self.ad_id}"


@dataclass
class FilterDecision:
    matched: bool
    reason: str
    gender_label: str = "Unklar / ganzer Wurf"
    highlights: list[str] = field(default_factory=list)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometers between two WGS84 coordinates."""
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
