"""Main orchestrator for the Linz Bauernhofkatze watcher."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from .config import WatcherConfig
from .filters import evaluate_listing
from .models import FilterDecision, Listing
from .notifier import PLATFORM_LABELS, notify_listing, notify_status
from .scrapers import landwirt, tieranzeigen, willhaben
from .scrapers.http_client import FetchBlockedError

ALL_PLATFORMS = ("willhaben", "landwirt", "tieranzeigen")


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load_state(path: Path) -> tuple[dict[str, Any], bool]:
    """Load persistent state JSON. Returns (state_dict, existed)."""
    if not path.exists():
        return {"seen": {}, "plz_cache": {}, "health": {}}, False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("State root is not a JSON object")
        data.setdefault("seen", {})
        data.setdefault("plz_cache", {})
        data.setdefault("health", {})
        return data, True
    except Exception as exc:
        print(f"[WARN] Konnte State-Datei {path} nicht lesen ({exc}), starte neu.")
        return {"seen": {}, "plz_cache": {}, "health": {}}, False


def prune_old_seen(state: dict[str, Any], retention_days: int) -> int:
    """Remove seen entries older than `retention_days` so state stays compact."""
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=retention_days)
    seen = state.get("seen", {})
    to_delete: list[str] = []
    for key, meta in seen.items():
        ts = meta.get("first_seen") if isinstance(meta, dict) else None
        if not ts:
            continue
        try:
            parsed = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if parsed < cutoff:
                to_delete.append(key)
        except ValueError:
            continue
    for key in to_delete:
        del seen[key]
    return len(to_delete)


def save_state_if_changed(path: Path, state: dict[str, Any], original_dump: str) -> bool:
    """Persist state only if content changed (avoids noisy git commits every 5 min)."""
    new_dump = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if new_dump == original_dump:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_dump, encoding="utf-8")
    return True


def _passes_pre_detail_checks(listing: Listing, config: WatcherConfig) -> bool:
    """Quick cheap check before fetching an individual listing's detail page."""
    if listing.country and listing.country.upper() != "AT":
        return False
    if listing.distance_km is not None and listing.distance_km > config.max_distance_km:
        return False
    if listing.price_eur is not None and listing.price_eur > config.max_price_eur:
        return False
    if listing.reserved:
        return False
    return True


def _enrich_listing(listing: Listing, config: WatcherConfig) -> None:
    if listing.platform == "willhaben":
        willhaben.enrich_detail(listing, config)
    elif listing.platform == "landwirt":
        landwirt.enrich_detail(listing, config)
    elif listing.platform == "tieranzeigen":
        tieranzeigen.enrich_detail(listing, config)


def _scrape_platform(
    platform: str, config: WatcherConfig, plz_cache: dict[str, list[float]]
) -> list[Listing]:
    if platform == "willhaben":
        return willhaben.scrape_willhaben(config)
    if platform == "landwirt":
        return landwirt.scrape_landwirt(config, plz_cache)
    if platform == "tieranzeigen":
        return tieranzeigen.scrape_tieranzeigen(config, plz_cache)
    raise ValueError(f"Unbekannte Plattform: {platform}")


def run_watcher(
    config: WatcherConfig,
    state_path: Path,
    platforms: tuple[str, ...],
    dry_run: bool = False,
    seed_only: bool = False,
    verbose: bool = False,
) -> int:
    state, existed = load_state(state_path)
    original_dump = (
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if existed
        else ""
    )

    seen: dict[str, Any] = state["seen"]
    plz_cache: dict[str, list[float]] = state["plz_cache"]
    health: dict[str, Any] = state["health"]

    all_new_matches: list[tuple[Listing, FilterDecision]] = []
    platform_summaries: list[str] = []
    any_platform_ok = False
    now_iso = _utc_now_iso()

    for platform in platforms:
        label = PLATFORM_LABELS.get(platform, platform)
        p_health = health.setdefault(platform, {"errors": 0, "alerted_down": False})

        try:
            listings = _scrape_platform(platform, config, plz_cache)
            any_platform_ok = True
            # Handle recovery alert
            if p_health.get("alerted_down"):
                notify_status(
                    title=f"✅ {label} läuft wieder",
                    message=f"{label} ist wieder erreichbar und liefert aktuell {len(listings)} Inserate.",
                    config=config,
                    priority=3,
                    tags=["white_check_mark"],
                    dry_run=dry_run,
                )
            p_health["errors"] = 0
            p_health["alerted_down"] = False
            p_health.pop("last_error", None)
        except Exception as exc:
            err_msg = str(exc)
            p_health["errors"] = int(p_health.get("errors", 0)) + 1
            p_health["last_error"] = err_msg[:200]
            print(f"[ERROR] {label}: {err_msg}")
            platform_summaries.append(f"{label}: FEHLER ({err_msg[:80]})")

            if (
                p_health["errors"] >= config.error_alert_threshold
                and not p_health.get("alerted_down")
            ):
                hint = (
                    "\nHinweis: Falls Cloud-IP blockiert wird, lokal am Mac via launchd starten oder Willhaben-Suchagent nutzen."
                    if isinstance(exc, FetchBlockedError)
                    else ""
                )
                notify_status(
                    title=f"⚠️ {label} seit {p_health['errors']} Durchläufen gestört",
                    message=f"Letzter Fehler: {err_msg[:200]}{hint}",
                    config=config,
                    priority=4,
                    tags=["warning"],
                    dry_run=dry_run,
                )
                p_health["alerted_down"] = True
            continue

        new_count = 0
        matched_count = 0

        for listing in listings:
            key = listing.unique_key
            if key in seen:
                continue

            new_count += 1
            # Fetch full detail text only for promising new listings
            if _passes_pre_detail_checks(listing, config):
                _enrich_listing(listing, config)

            decision = evaluate_listing(listing, config)
            seen[key] = {
                "first_seen": now_iso,
                "title": listing.title[:100],
                "matched": decision.matched,
            }

            if decision.matched:
                matched_count += 1
                all_new_matches.append((listing, decision))
                dist = f"{listing.distance_km:.0f} km" if listing.distance_km is not None else "? km"
                print(
                    f"[TREFFER] {label} | {listing.price_display} | {dist} | "
                    f"{listing.postcode} {listing.location} | {decision.gender_label} | "
                    f"{listing.title} -> {listing.url}"
                )
            elif verbose:
                dist = f"{listing.distance_km:.0f} km" if listing.distance_km is not None else "? km"
                print(
                    f"[SKIP] {label} | {dist} | {listing.price_display} | "
                    f"{listing.title[:50]} -> {decision.reason}"
                )

        platform_summaries.append(
            f"{label}: {len(listings)} geprüft, {new_count} neu, {matched_count} Treffer"
        )

    print("Zusammenfassung: " + " | ".join(platform_summaries))

    # Send notifications
    if not seed_only:
        is_first_run = not existed
        if is_first_run:
            # First run: notify up to 3 current matches (closest first) + startup confirmation
            sorted_matches = sorted(
                all_new_matches,
                key=lambda pair: (
                    pair[0].distance_km if pair[0].distance_km is not None else 999.0
                ),
            )
            notify_status(
                title="🐱 Katzen-Wächter Linz gestartet!",
                message=(
                    f"Überwache ab sofort alle 5 Min. Willhaben, Landwirt.com & Tieranzeigen.at "
                    f"(Umkreis {config.max_distance_km:.0f} km, max. € {config.max_price_eur:.0f}, kein Tierheim).\n"
                    f"Aktuell gefundene Treffer: {len(sorted_matches)}"
                ),
                config=config,
                priority=3,
                tags=["cat", "rocket"],
                dry_run=dry_run,
            )
            for listing, decision in sorted_matches[:3]:
                notify_listing(listing, decision, config, dry_run=dry_run)
        else:
            for listing, decision in all_new_matches:
                notify_listing(listing, decision, config, dry_run=dry_run)

    pruned = prune_old_seen(state, config.state_retention_days)
    if pruned and verbose:
        print(f"[INFO] {pruned} alte Einträge aus State entfernt.")

    if not dry_run:
        changed = save_state_if_changed(state_path, state, original_dump)
        print(f"[STATE] {'Aktualisiert' if changed else 'Unverändert'}: {state_path}")
    else:
        print("[DRY-RUN] State wurde nicht gespeichert, keine echten Push-Nachrichten gesendet.")

    return 0 if any_platform_ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Überwacht Willhaben, Landwirt.com & Tieranzeigen.at auf junge weibliche Bauernhofkatzen nahe Linz."
    )
    parser.add_argument(
        "--state-file",
        default="state/seen.json",
        help="Pfad zur State-Datei (Standard: state/seen.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prüft live ohne Push-Nachricht und ohne State zu speichern.",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Speichert aktuelle Inserate als gesehen ohne Push-Benachrichtigungen.",
    )
    parser.add_argument(
        "--test-notify",
        action="store_true",
        help="Sendet sofort eine Test-Benachrichtigung an NTFY_TOPIC.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Zeigt auch aussortierte Inserate mit Begründung an.",
    )
    parser.add_argument(
        "--only",
        default="",
        help="Nur bestimmte Plattformen prüfen (Komma-getrennt: willhaben,landwirt,tieranzeigen).",
    )
    args = parser.parse_args(argv)
    config = WatcherConfig()

    if args.test_notify:
        if not config.ntfy_topic:
            print("[ERROR] Bitte zuerst Umgebungsvariable NTFY_TOPIC setzen!")
            return 2
        notify_status(
            title="🐱 Test vom Katzen-Wächter Linz",
            message=(
                "Perfekt! Wenn du und deine Frau diese Nachricht am Handy seht, "
                "bekommt ihr ab sofort alle neuen Bauernhofkatzen im Umkreis von Linz sofort als Push."
            ),
            config=config,
            priority=4,
            tags=["cat", "tada"],
            click_url="https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz/katzen/hauskatzen-4969?areaId=4&sort=1",
            dry_run=False,
        )
        print(f"[OK] Test-Benachrichtigung an Topic '{config.ntfy_topic}' gesendet.")
        return 0

    if args.only.strip():
        platforms = tuple(
            p.strip().lower() for p in args.only.split(",") if p.strip().lower() in ALL_PLATFORMS
        )
        if not platforms:
            print(f"[ERROR] Ungültige Plattform-Auswahl: {args.only}")
            return 2
    else:
        platforms = ALL_PLATFORMS

    return run_watcher(
        config=config,
        state_path=Path(args.state_file),
        platforms=platforms,
        dry_run=args.dry_run,
        seed_only=args.seed,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
