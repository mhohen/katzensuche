"""Landwirt.com scraper reading __NUXT_DATA__ (devalue format) + detail JSON-LD."""

from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, Optional

from ..config import LANDWIRT_SEARCH_URL, WatcherConfig
from ..geo import extract_plz, resolve_plz
from ..models import Listing, haversine_km
from .http_client import fetch_text

NUXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)
JSONLD_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL
)
WRAPPER_TAGS = {"ShallowReactive", "Reactive", "Ref", "ShallowRef"}


def resolve_nuxt_devalue(raw: list[Any], idx: int, depth: int = 0) -> Any:
    """Safely resolve a single index inside Nuxt 3's devalue payload.

    Crucial detail: in devalue, only container entries (dict values and list
    elements) are integer references into `raw`. Primitives (including bools
    and numeric fields like `price` or `id`) must NOT be dereferenced again.
    """
    if depth > 10 or idx < 0 or idx >= len(raw):
        return None
    node = raw[idx]
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            if isinstance(v, int) and not isinstance(v, bool):
                out[k] = resolve_nuxt_devalue(raw, v, depth + 1)
            else:
                out[k] = v
        return out
    if isinstance(node, list):
        if len(node) == 2 and isinstance(node[0], str) and node[0] in WRAPPER_TAGS:
            ref = node[1]
            if isinstance(ref, int) and not isinstance(ref, bool):
                return resolve_nuxt_devalue(raw, ref, depth + 1)
            return ref
        if len(node) >= 1 and node[0] in ("Set", "EmptyShallowRef", "EmptyRef"):
            return []
        res = []
        for elem in node:
            if isinstance(elem, int) and not isinstance(elem, bool):
                res.append(resolve_nuxt_devalue(raw, elem, depth + 1))
            else:
                res.append(elem)
        return res
    return node


def _extract_price(prices_obj: Any) -> Optional[float]:
    if not isinstance(prices_obj, dict):
        return None
    for branch in ("inclusive", "exclusive"):
        sub = prices_obj.get(branch)
        if isinstance(sub, dict):
            p = sub.get("price")
            if isinstance(p, (int, float)) and not isinstance(p, bool) and p >= 0:
                return float(p)
    return None


def parse_search_html(
    page_html: str,
    config: WatcherConfig,
    plz_cache: dict[str, list[float]],
) -> list[Listing]:
    """Parse Landwirt.com Katzen page HTML into Listing objects."""
    m = NUXT_DATA_RE.search(page_html)
    if not m:
        raise RuntimeError("Landwirt.com __NUXT_DATA__ nicht gefunden")

    raw = json.loads(m.group(1))
    if not isinstance(raw, list):
        raise RuntimeError("Landwirt.com __NUXT_DATA__ hat unerwartetes Format")

    listings: list[Listing] = []
    seen_ids: set[str] = set()

    for idx, node in enumerate(raw):
        if not (
            isinstance(node, dict)
            and "title_slug" in node
            and "supplier" in node
            and "short_description" in node
            and "id" in node
        ):
            continue

        ad = resolve_nuxt_devalue(raw, idx)
        if not isinstance(ad, dict):
            continue

        ad_id = str(ad.get("id") or "").strip()
        if not ad_id or ad_id in seen_ids:
            continue
        seen_ids.add(ad_id)

        title = html_lib.unescape(str(ad.get("title") or "").strip())
        slug = str(ad.get("title_slug") or "").strip()
        url = (
            f"https://www.landwirt.com/kleinanzeigen/detail/{slug}-{ad_id}"
            if slug
            else f"https://www.landwirt.com/kleinanzeigen/detail/{ad_id}"
        )

        supplier = ad.get("supplier") if isinstance(ad.get("supplier"), dict) else {}
        country_code = str(supplier.get("country_code") or "AT").strip().upper()
        country_zip = str(supplier.get("country_zip") or "").strip()
        postcode = extract_plz(country_zip)
        location = re.sub(r"^\d{4,5}\s*", "", country_zip).strip() or country_zip

        loc = supplier.get("location") if isinstance(supplier.get("location"), dict) else {}
        lat = loc.get("lat") if isinstance(loc.get("lat"), (int, float)) else None
        lng = loc.get("lng") if isinstance(loc.get("lng"), (int, float)) else None
        if (lat is None or lng is None) and country_code == "AT" and postcode:
            coords = resolve_plz(postcode, plz_cache, timeout_sec=config.http_timeout_sec)
            if coords:
                lat, lng = coords

        dist = (
            haversine_km(config.center_lat, config.center_lng, float(lat), float(lng))
            if lat is not None and lng is not None
            else None
        )

        price_eur = _extract_price(ad.get("prices"))
        price_display = (
            f"€ {price_eur:.0f}"
            if price_eur is not None and price_eur > 0
            else ("zu verschenken" if price_eur == 0 else "Preis a. A.")
        )

        reserved = bool(ad.get("reserved"))
        img_url = str(ad.get("image_url_big") or ad.get("image_url") or "").strip()

        listings.append(
            Listing(
                platform="landwirt",
                ad_id=ad_id,
                title=title,
                url=url,
                description=html_lib.unescape(str(ad.get("short_description") or "").strip()),
                price_eur=price_eur,
                price_display=price_display,
                postcode=postcode,
                location=location,
                country=country_code,
                lat=float(lat) if lat is not None else None,
                lng=float(lng) if lng is not None else None,
                distance_km=dist,
                seller_name=str(supplier.get("name") or "").strip(),
                category="Katzen (Landwirt.com)",
                published_at=str(ad.get("created") or "").strip(),
                image_url=img_url,
                reserved=reserved,
            )
        )

    return listings


def enrich_detail(listing: Listing, config: WatcherConfig) -> None:
    """Fetch full Landwirt.com detail JSON-LD description for a newly seen ad."""
    try:
        page_html = fetch_text(listing.url, timeout_sec=config.http_timeout_sec, retries=1)
        for block in JSONLD_RE.findall(page_html):
            try:
                obj = json.loads(block)
            except ValueError:
                continue
            if isinstance(obj, dict) and obj.get("description"):
                desc = html_lib.unescape(str(obj["description"]).strip())
                if len(desc) > len(listing.description):
                    listing.description = desc
                break
    except Exception:
        return


def scrape_landwirt(config: WatcherConfig, plz_cache: dict[str, list[float]]) -> list[Listing]:
    """Fetch Landwirt.com Katzen listings."""
    page_html = fetch_text(LANDWIRT_SEARCH_URL, timeout_sec=config.http_timeout_sec)
    return parse_search_html(page_html, config, plz_cache)
