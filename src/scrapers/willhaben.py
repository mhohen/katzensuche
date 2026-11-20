"""Willhaben.at scraper reading __NEXT_DATA__ JSON (OÖ + adjacent NÖ)."""

from __future__ import annotations

import html as html_lib
import json
import re
from typing import Optional

from ..config import WILLHABEN_SEARCH_URLS, WatcherConfig
from ..models import Listing, haversine_km
from .http_client import fetch_text

NEXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


def _strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html_lib.unescape(cleaned)
    return re.sub(r"[ \t]+", " ", cleaned).strip()


def _parse_float(val: str) -> Optional[float]:
    if not val:
        return None
    s = val.strip().replace(".", "").replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def _parse_coords(val: str) -> tuple[Optional[float], Optional[float]]:
    if not val or "," not in val:
        return None, None
    parts = val.split(",", 1)
    try:
        return float(parts[0].strip()), float(parts[1].strip())
    except ValueError:
        return None, None


def _attrs_map(ad: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for item in ad.get("attributes", {}).get("attribute", []):
        name = item.get("name")
        if name:
            out[name] = item.get("values") or []
    return out


def _first(attrs: dict[str, list[str]], key: str) -> str:
    vals = attrs.get(key)
    return str(vals[0]) if vals else ""


def parse_search_html(
    page_html: str,
    config: WatcherConfig,
    require_farm_or_mix_keyword: bool = False,
) -> list[Listing]:
    """Parse Willhaben search results HTML into Listing objects."""
    m = NEXT_DATA_RE.search(page_html)
    if not m:
        raise RuntimeError("Willhaben __NEXT_DATA__ nicht gefunden (Seitenstruktur geändert?)")

    data = json.loads(m.group(1))
    sr = data.get("props", {}).get("pageProps", {}).get("searchResult", {})
    summaries = sr.get("advertSummaryList", {}).get("advertSummary", [])
    listings: list[Listing] = []

    for ad in summaries:
        ad_id = str(ad.get("id") or "").strip()
        if not ad_id:
            continue
        attrs = _attrs_map(ad)
        seo_url = _first(attrs, "SEO_URL")
        if seo_url:
            url = (
                seo_url
                if seo_url.startswith("http")
                else f"https://www.willhaben.at/iad/{seo_url.lstrip('/')}"
            )
        else:
            url = f"https://www.willhaben.at/iad/kaufen-und-verkaufen/d/-{ad_id}/"

        price_raw = _first(attrs, "PRICE")
        price_display = _first(attrs, "PRICE_FOR_DISPLAY")
        price_eur: Optional[float] = None
        if price_raw:
            try:
                price_eur = float(price_raw.replace(",", "."))
            except ValueError:
                price_eur = _parse_float(price_display)
        elif "verschenken" in price_display.lower():
            price_eur = 0.0

        lat, lng = _parse_coords(_first(attrs, "COORDINATES"))
        dist = (
            haversine_km(config.center_lat, config.center_lng, lat, lng)
            if lat is not None and lng is not None
            else None
        )

        imgs = ad.get("advertImageList", {}).get("advertImage", [])
        img_url = imgs[0].get("mainImageUrl", "") if imgs else ""

        listings.append(
            Listing(
                platform="willhaben",
                ad_id=ad_id,
                title=html_lib.unescape(str(ad.get("description") or "").strip()),
                url=url,
                description=_strip_html(_first(attrs, "BODY_DYN")),
                price_eur=price_eur,
                price_display=price_display or (f"€ {price_eur:.0f}" if price_eur is not None else "Preis k. A."),
                postcode=_first(attrs, "POSTCODE"),
                location=_first(attrs, "LOCATION"),
                district=_first(attrs, "DISTRICT"),
                country="AT",
                lat=lat,
                lng=lng,
                distance_km=dist,
                seller_name=_first(attrs, "ORGNAME"),
                category="Hauskatzen" if not require_farm_or_mix_keyword else "Rassekatzen / Mischlinge",
                published_at=_first(attrs, "PUBLISHED_String"),
                image_url=img_url,
                require_farm_or_mix_keyword=require_farm_or_mix_keyword,
            )
        )
    return listings


def enrich_detail(listing: Listing, config: WatcherConfig) -> None:
    """Fetch full Willhaben detail description & seller company name for a newly seen ad."""
    try:
        page_html = fetch_text(listing.url, timeout_sec=config.http_timeout_sec, retries=1)
        m = NEXT_DATA_RE.search(page_html)
        if not m:
            return
        data = json.loads(m.group(1))
        ad = data.get("props", {}).get("pageProps", {}).get("advertDetails", {})
        attrs = _attrs_map(ad)
        full_desc = _strip_html(_first(attrs, "DESCRIPTION"))
        if full_desc:
            listing.description = full_desc
        company = _first(attrs, "COMPANY/COMPANY_NAME")
        if company and not listing.seller_name:
            listing.seller_name = company
    except Exception:
        # Detail enrichment is best-effort; summary card already has key data.
        return


def scrape_willhaben(config: WatcherConfig) -> list[Listing]:
    """Fetch and deduplicate Willhaben listings across configured search URLs."""
    seen: dict[str, Listing] = {}
    for _label, url, require_farm in WILLHABEN_SEARCH_URLS:
        page_html = fetch_text(url, timeout_sec=config.http_timeout_sec)
        for item in parse_search_html(page_html, config, require_farm_or_mix_keyword=require_farm):
            # Prefer Hauskatzen entry over Mischlinge entry if same ad appears in both
            if item.ad_id not in seen or (seen[item.ad_id].require_farm_or_mix_keyword and not item.require_farm_or_mix_keyword):
                seen[item.ad_id] = item
    return list(seen.values())
