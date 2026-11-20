"""Unit tests for filters, parsers, distance calculation, and ntfy payloads."""

from __future__ import annotations

import datetime as dt
import os
import unittest
from unittest import mock

from src.config import WatcherConfig
from src.filters import evaluate_listing
from src.models import Listing, haversine_km
from src.notifier import build_listing_payload, get_topics
from src.scrapers.landwirt import resolve_nuxt_devalue


class FilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = WatcherConfig(
            center_lat=48.3069,
            center_lng=14.2858,
            max_distance_km=50.0,
            max_price_eur=300.0,
            max_age_months=7,
            ntfy_topic="test-topic-1, test-topic-2",
        )
        self.today = dt.date(2026, 11, 20)

    def test_example_willhaben_bauernhofkatze_matches(self) -> None:
        listing = Listing(
            platform="willhaben",
            ad_id="842158736",
            title="Süße und verspielte Bauernhofkatze zu verkaufen",
            url="https://www.willhaben.at/iad/kaufen-und-verkaufen/d/suesse-und-verspielte-bauernhofkatze-zu-verkaufen-842158736/",
            description=(
                "Wir suchen ein neues Zuhause für unser süßes und verspieltes Babykätzchen. "
                "Die Kleine ist weiblich und jetzt ungefähr 15 Wochen alt und somit jederzeit zu verkaufen. "
                "Der Preis liegt bei 200€. Das Kätzchen kommen aus einer behördlich genehmigten Katzenzucht."
            ),
            price_eur=200.0,
            price_display="€ 200",
            postcode="4331",
            location="Naarn im Machlande",
            distance_km=haversine_km(48.3069, 14.2858, 48.23036, 14.62424),
            seller_name="Wahl",
        )
        res = evaluate_listing(listing, self.cfg, today=self.today)
        self.assertTrue(res.matched, res.reason)
        self.assertEqual(res.gender_label, "Weiblich")

    def test_landwirt_litter_kittens_matches(self) -> None:
        listing = Listing(
            platform="landwirt",
            ad_id="29920906",
            title="Katzenbabys abzugeben",
            url="https://www.landwirt.com/kleinanzeigen/detail/katzenbabys-abzugeben-29920906",
            description=(
                "Unsere zur Zucht gemeldete Europäisch Kurzhaar Katze hat am 27.09.2026 fünf wunderschöne, "
                "gesunde Kitten zur Welt gebracht. Die Kleinen wachsen auf unserem Bauernhof auf."
            ),
            price_eur=180.0,
            price_display="€ 180",
            postcode="4273",
            location="Kaltenberg",
            distance_km=haversine_km(48.3069, 14.2858, 48.48708, 14.79253),
            seller_name="Raimund Himmelbauer",
        )
        res = evaluate_listing(listing, self.cfg, today=self.today)
        self.assertTrue(res.matched, res.reason)
        self.assertEqual(res.gender_label, "Geschlecht unklar / ganzer Wurf")

    def test_rejects_male_only(self) -> None:
        listing = Listing(
            platform="landwirt",
            ad_id="29923502",
            title="Kätzchen abzugeben",
            url="https://www.landwirt.com/kleinanzeigen/detail/kaetzchen-abzugeben-29923502",
            description="Kätzchen abzugeben (EKH). Er ist männlich, am 15. August 2026 geboren.",
            price_eur=150.0,
            postcode="3355",
            location="Ertl",
            distance_km=45.0,
        )
        res = evaluate_listing(listing, self.cfg, today=self.today)
        self.assertFalse(res.matched)
        self.assertIn("männlich", res.reason.lower())

    def test_rejects_shelter_and_tierschutz(self) -> None:
        listing = Listing(
            platform="willhaben",
            ad_id="1027793244",
            title="Emma & Timmy",
            url="https://www.willhaben.at/iad/kaufen-und-verkaufen/d/x-1027793244/",
            description="Emma & Timmy suchen ein Zuhause. Sie sind ca 4 Monate alt.",
            price_eur=200.0,
            postcode="4551",
            location="Penzendorf",
            distance_km=34.0,
            seller_name="Tierschutzverein Angsthund",
        )
        res = evaluate_listing(listing, self.cfg, today=self.today)
        self.assertFalse(res.matched)
        self.assertIn("tierheim", res.reason.lower())

    def test_rejects_reserved_and_wanted(self) -> None:
        for title in [
            "RESERVIERT! 2 Kitten weiblich",
            "VERGEBEN! Bauernhofkatze",
            "Alle bereits vergeben",
            "Babykatze gesucht",
            "Suche kleine Bauernhofkatze",
        ]:
            listing = Listing(
                platform="willhaben",
                ad_id="1",
                title=title,
                url="https://example.com/1",
                description="Bauernhofkatze weiblich 12 Wochen",
                price_eur=100.0,
                distance_km=10.0,
            )
            res = evaluate_listing(listing, self.cfg, today=self.today)
            self.assertFalse(res.matched, f"Expected rejection for: {title}")

    def test_allows_austrian_zu_vergeben(self) -> None:
        listing = Listing(
            platform="willhaben",
            ad_id="10",
            title="Süße Bauernhofkatze ab sofort zu vergeben",
            url="https://example.com/10",
            description="Weibliches Kätzchen, 14 Wochen alt, vom Bauernhof.",
            price_eur=80.0,
            distance_km=15.0,
        )
        res = evaluate_listing(listing, self.cfg, today=self.today)
        self.assertTrue(res.matched, res.reason)

    def test_rejects_purebred_and_expensive(self) -> None:
        listing = Listing(
            platform="landwirt",
            ad_id="29909103",
            title="Britisch-Langhaar-Mädchen in Blue Point sucht Zuhause",
            url="https://example.com/2",
            description="Unser hübsches Britisch-Langhaar-Kätzchen",
            price_eur=250.0,
            distance_km=15.0,
        )
        res = evaluate_listing(listing, self.cfg, today=self.today)
        self.assertFalse(res.matched)

    def test_rejects_adult_cat_structured_and_text(self) -> None:
        l1 = Listing(
            platform="tieranzeigen",
            ad_id="1912264",
            title="Liebes Katzenmädchen",
            url="https://example.com/3",
            description="Suche bestes Katzenzuhause für liebes Katzenmädchen.",
            age_field="1 Jahr und 8 Monate",
            gender_field="weiblich",
            distance_km=8.0,
        )
        self.assertFalse(evaluate_listing(l1, self.cfg, today=self.today).matched)

        l2 = Listing(
            platform="willhaben",
            ad_id="1363949922",
            title="Schmusekatze sucht Zuhause",
            url="https://example.com/4",
            description="Geschlecht: weiblich Geburtsdatum: Jänner 2024",
            price_eur=130.0,
            distance_km=20.0,
        )
        self.assertFalse(evaluate_listing(l2, self.cfg, today=self.today).matched)

    def test_allows_kitten_when_parent_age_or_father_mentioned(self) -> None:
        listing = Listing(
            platform="landwirt",
            ad_id="999",
            title="Bauernhof-Kitten abzugeben",
            url="https://example.com/5",
            description=(
                "Unsere Mutter ist 2 Jahre alt und der Vater ist ein roter Kater. "
                "Die 4 kleinen Kitten sind 12 Wochen alt und wachsen am Bauernhof auf."
            ),
            price_eur=100.0,
            distance_km=18.0,
        )
        res = evaluate_listing(listing, self.cfg, today=self.today)
        self.assertTrue(res.matched, res.reason)

    def test_rejects_too_far_and_foreign(self) -> None:
        l_far = Listing(
            platform="willhaben",
            ad_id="2",
            title="Bauernhofkatze weiblich",
            url="https://example.com/far",
            description="12 Wochen alt, weiblich",
            price_eur=100.0,
            distance_km=88.0,
        )
        self.assertFalse(evaluate_listing(l_far, self.cfg, today=self.today).matched)

        l_de = Listing(
            platform="landwirt",
            ad_id="3",
            title="Bauernhofkatze weiblich",
            url="https://example.com/de",
            description="12 Wochen alt, weiblich",
            price_eur=100.0,
            country="DE",
            distance_km=40.0,
        )
        self.assertFalse(evaluate_listing(l_de, self.cfg, today=self.today).matched)

    def test_nuxt_devalue_does_not_deref_bools_or_primitives(self) -> None:
        # Index 0 is a dict referencing: id=1 (12345), reserved=2 (False), active=3 (True), price=4 (180)
        raw = [
            {"id": 1, "reserved": 2, "active": 3, "price": 4, "title": 5},
            12345,
            False,
            True,
            180,
            "Katzenbabys",
        ]
        resolved = resolve_nuxt_devalue(raw, 0)
        self.assertEqual(resolved["id"], 12345)
        self.assertIs(resolved["reserved"], False)
        self.assertIs(resolved["active"], True)
        self.assertEqual(resolved["price"], 180)
        self.assertEqual(resolved["title"], "Katzenbabys")

    def test_ntfy_payload_and_multi_topics(self) -> None:
        self.assertEqual(get_topics(self.cfg), ["test-topic-1", "test-topic-2"])
        listing = Listing(
            platform="landwirt",
            ad_id="29920906",
            title="Katzenbabys abzugeben",
            url="https://www.landwirt.com/kleinanzeigen/detail/katzenbabys-abzugeben-29920906",
            description="Fünf gesunde Kitten vom Bauernhof",
            price_eur=180.0,
            price_display="€ 180",
            postcode="4273",
            location="Kaltenberg",
            distance_km=42.3,
            image_url="https://bilder.landwirt.com/example.jpg",
        )
        decision = evaluate_listing(listing, self.cfg, today=self.today)
        payload = build_listing_payload("test-topic-1", listing, decision, priority=4)
        self.assertEqual(payload["topic"], "test-topic-1")
        self.assertIn("€ 180", payload["title"])
        self.assertIn("42 km", payload["title"])
        self.assertEqual(payload["click"], listing.url)
        self.assertEqual(payload["attach"], listing.image_url)

    def test_empty_github_env_vars_fall_back_to_defaults(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "NTFY_SERVER": "",
                "MAX_DISTANCE_KM": "",
                "MAX_PRICE_EUR": "",
                "MAX_AGE_MONTHS": "",
            },
        ):
            cfg = WatcherConfig()
            self.assertEqual(cfg.ntfy_server, "https://ntfy.sh")
            self.assertEqual(cfg.max_distance_km, 50.0)
            self.assertEqual(cfg.max_price_eur, 300.0)
            self.assertEqual(cfg.max_age_months, 7)


if __name__ == "__main__":
    unittest.main()
