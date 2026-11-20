"""Tieranzeigen.at scraper for Oberösterreich and Niederösterreich."""

from __future__ import annotations

import html as html_lib
import re
from typing import Optional

from ..config import TIERANZEIGEN_SEARCH_URLS, WatcherConfig
from ..geo import extract_plz, resolve_plz
from ..models import Listing, haversine_km
from .http_client import fetch_text


def _strip_tags(text: str) -> str:
    cleaned = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html_lib.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_price(text: str) -> Optional[float]:
    t = text.lower()
    if "verschenken" in t or "gratis" in t:
        return 0.0
    if "preis a. a" in t or "auf anfrage" in t or not any(ch.isdigit() for ch in t):
        return None
    s = text.replace(".", "").replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def parse_search_html(
    page_html: str,
    config: WatcherConfig,
    plz_cache: dict[str, list[float]],
) -> list[Listing]:
    """Parse Tieranzeigen.at list page into Listing objects."""
    boxes = page_html.split('<div class="content_container_box">')[1:]
    listings: list[Listing] = []

    for box in boxes:
        url_m = re.search(
            r'href="(https://www\.tieranzeigen\.at/katzen/(\d+)[^"]*)"',
            box,
        )
        if not url_m:
            continue
        url = url_m.group(1)
        ad_id = url_m.group(2)

        title_m = re.search(
            r'<span class="fs16 linkcolor bold"[^>]*>(.*?)</span>',
            box,
            re.DOTALL,
        )
        title = _strip_tags(title_m.group(1)) if title_m else ""

        date_m = re.search(r"fa-clock[^>]*></i>\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})", box)
        published_at = date_m.group(1) if date_m else ""

        img_m = re.search(r'<img\s+src="([^"]+)"', box)
        img_url = img_m.group(1) if img_m else ""

        price_m = re.search(
            r'<div class="content_preis[^"]*">(.*?)</div>',
            box,
            re.DOTALL,
        )
        price_display = _strip_tags(price_m.group(1)) if price_m else "Preis a. A."
        price_eur = _parse_price(price_display)

        cat_m = re.search(r'<div class="content_t3[^"]*">\s*<b>(.*?)</b>', box, re.DOTALL)
        category = _strip_tags(cat_m.group(1)) if cat_m else ""

        loc_m = re.search(r"fa-map-marker-alt[^>]*></i>\s*([^<]+)", box)
        loc_raw = _strip_tags(loc_m.group(1)) if loc_m else ""
        postcode = extract_plz(loc_raw)
        location = re.sub(r"^\d{4}\s*", "", loc_raw).strip() or loc_raw

        extra_tags: list[str] = []
        if "<b>Verein:</b>" in box or "Verein:" in box:
            extra_tags.append("Verein:")

        lat: Optional[float] = None
        lng: Optional[float] = None
        dist: Optional[float] = None
        if postcode:
            coords = resolve_plz(postcode, plz_cache, timeout_sec=config.http_timeout_sec)
            if coords:
                lat, lng = coords
                dist = haversine_km(config.center_lat, config.center_lng, lat, lng)

        listings.append(
            Listing(
                platform="tieranzeigen",
                ad_id=ad_id,
                title=title,
                url=url,
                price_eur=price_eur,
                price_display=price_display,
                postcode=postcode,
                location=location,
                country="AT",
                lat=lat,
                lng=lng,
                distance_km=dist,
                category=category,
                published_at=published_at,
                image_url=img_url,
                extra_tags=extra_tags,
            )
        )

    return listings


def enrich_detail(listing: Listing, config: WatcherConfig) -> None:
    """Fetch Tieranzeigen.at detail page for full description, gender, age, and seller."""
    try:
        page_html = fetch_text(listing.url, timeout_sec=config.http_timeout_sec, retries=1)

        # Structured attributes table
        g_m = re.search(
            r"<b>Geschlecht:</b></div><div[^>]*>(.*?)</div>",
            page_html,
            re.DOTALL | re.IGNORECASE,
        )
        if g_m:
            listing.gender_field = _strip_tags(g_m.group(1))

        a_m = re.search(
            r"<b>Alter:</b></div><div[^>]*>(.*?)</div>",
            page_html,
            re.DOTALL | re.IGNORECASE,
        )
        if a_m:
            listing.age_field = _strip_tags(a_m.group(1))

        # Meta description (clean summary) + og:image (higher res)
        meta_m = re.search(
            r'<meta\s+name="description"\s+content="([^"]+)"',
            page_html,
            re.IGNORECASE,
        )
        if meta_m:
            listing.description = html_lib.unescape(meta_m.group(1)).strip()

        og_m = re.search(
            r'<meta\s+property="og:image"\s+content="([^"]+)"',
            page_html,
            re.IGNORECASE,
        )
        if og_m:
            listing.image_url = og_m.group(1).strip()

        # Seller name just above the location marker
        s_m = re.search(
            r"<strong>\s*(?:<i[^>]*></i>\s*)?([^<]{2,80})</strong>\s*<div class=\"mt5\">\s*<i class=\"fas fa-map-marker-alt",
            page_html,
            re.DOTALL,
        )
        if s_m:
            listing.seller_name = _strip_tags(s_m.group(1))

        # Capture Verein / Tierschutz mentions in body if present
        if "tierschutz" in page_html.lower() and "tierschutz" not in listing.description.lower():
            # Avoid false positives from site footer: check only near main detail section
            detail_idx = page_html.find("detail-eigenschaften")
            if detail_idx > 0:
                window = page_html[max(0, detail_idx - 3000): detail_idx + 4000].lower()
                for marker in ("tierheim", "tierschutzverein", "katzenhilfe", "pflegestelle"):
                    if marker in window:
                        listing.extra_tags.append(marker)
    except Exception:
        return


def scrape_tieranzeigen(
    config: WatcherConfig, plz_cache: dict[str, list[float]]
) -> list[Listing]:
    """Fetch and deduplicate Tieranzeigen.at listings for OÖ and NÖ."""
    seen: dict[str, Listing] = {}
    for _label, url in TIERANZEIGEN_SEARCH_URLS:
        page_html = fetch_text(url, timeout_sec=config.http_timeout_sec)
        for item in parse_search_html(page_html, config, plz_cache):
            seen.setdefault(item.ad_id, item)
    return list(seen.values())
