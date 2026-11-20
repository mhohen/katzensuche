"""Smart filtering for young female (or litter) Bauernhofkatzen near Linz, excluding shelters."""

from __future__ import annotations

import datetime as dt
import re
from typing import Optional

from .config import WatcherConfig
from .models import FilterDecision, Listing

# Shelter, rescue, foster, and pedigree-club exclusions.
# NOTE: Intentionally does NOT exclude "behördlich genehmigte/gemeldete Zucht"
# or "zur Zucht gemeldet", because Austrian farmers must include that phrase
# legally under § 8a Tierschutzgesetz when posting Bauernhofkatzen online.
SHELTER_OR_CLUB_KEYWORDS = [
    "tierheim",
    "tierschutz",
    "tierschutzverein",
    "tierschutzhaus",
    "tierschutzorganisation",
    "katzenhilfe",
    "tierhilfe",
    "katzenschutz",
    "streunerhilfe",
    "pflegestelle",
    "tierrettung",
    "gnadenhof",
    "arche noah",
    "vier pfoten",
    "menschen für tiere",
    "menschen fuer tiere",
    "tiere grenzenlos",
    "angsthund",
    "schutzvertrag",
    "vermittlungsgebühr",
    "vermittlungsgebuehr",
    "tötungsstation",
    "auslandstierschutz",
    "notfellchen",
    "sozialfellchen",
    "tiervermittlung",
    "animal care",
    # Purebred club / pedigree markers
    "stammbaum",
    "fife",
    "tcia",
    "wcf",
    "zuchtverein",
    "katzenfreunde österreich",
    "klub der katzenfreunde",
    "aus champions",
    "champions-eltern",
    "cattery",
    "verein:",
]

PUREBRED_KEYWORDS = [
    "bkh",
    "britisch kurzhaar",
    "britisch langhaar",
    "britisch-kurzhaar",
    "britisch-langhaar",
    "blh",
    "maine coon",
    "ragdoll",
    "bengal",
    "sphynx",
    "perser",
    "siam",
    "heilige birma",
    "scottish fold",
    "scottish straight",
    "norwegische waldkatze",
    "sibirische waldkatze",
    "neva masquerade",
    "russisch blau",
    "karthäuser",
    "karthaeuser",
    "savannah",
    "devon rex",
    "cornish rex",
    "abessinier",
    "highlander",
    "ragamuffin",
    "orientalisch kurzhaar",
    "türkisch angora",
    "burma",
]

FARM_OR_HOUSECAT_KEYWORDS = [
    "bauernhof",
    "hofkatze",
    "landkatze",
    "hauskatze",
    "hauskatzen",
    "hauskätzchen",
    "ekh",
    "europäisch kurzhaar",
    "europäische kurzhaar",
    "europaeisch kurzhaar",
]

KITTEN_CUES = [
    "kitten",
    "katzenbaby",
    "katzenbabys",
    "babykatze",
    "babykatzen",
    "babykätzchen",
    "kätzchen",
    "kaetzchen",
    "jungkatze",
    "jungkatzen",
    "jungtier",
    "wurf",
    "wochen alt",
    "wochen",
]

FEMALE_PATTERNS = [
    r"\bweiblich\w*\b",
    r"\bweibchen\b",
    r"\bmädchen\b",
    r"\bmaedchen\b",
    r"\bmädel\w*\b",
    r"\bmaedel\w*\b",
    r"\bkätzin\w*\b",
    r"\bkaetzin\w*\b",
    r"\bkatzendame\w*\b",
    r"\bkleine dame\b",
    r"\bdie kleine\b",
    r"\bsie ist\b",
    r"\bglückskatze\w*\b",
    r"\bglueckskatze\w*\b",
    r"\bdreifärbig\w*\b",
    r"\bdreifarbig\w*\b",
    r"\bschildpatt\w*\b",
    r"\btricolor\b",
]

MALE_PATTERNS = [
    r"\bmännlich\w*\b",
    r"\bmaennlich\w*\b",
    r"\bmännchen\b",
    r"\bmaennchen\b",
    r"\bkater\b",
    r"\bkaterchen\b",
    r"\bbub\b",
    r"\bbuben\b",
    r"\ber ist\b",
    r"\bder kleine\b",
    r"\bkleiner mann\b",
    r"\bkleiner bub\b",
    r"\bjung(?:-|\s+)kater\b",
]

UNAVAILABLE_OR_WANTED_PATTERNS = [
    r"\breserviert\b",
    r"(?<!zu\s)\bvergeben\b",
    r"\bverkauft\b",
    r"\bgesucht\b",
    r"\bvermisst\b",
    r"\bentlaufen\b",
    r"\bzugelaufen\b",
    r"\bdeckkater\b",
    r"^\s*suche\b",
    r"\bsuche\s+(?:ein|eine|junge|kleine|süße|baby|katze|kätzchen|kitten|bauernhof)",
]

MONTH_MAP = {
    "jänner": 1,
    "jaenner": 1,
    "januar": 1,
    "jan": 1,
    "februar": 2,
    "feb": 2,
    "märz": 3,
    "maerz": 3,
    "april": 4,
    "apr": 4,
    "mai": 5,
    "juni": 6,
    "jun": 6,
    "juli": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "oktober": 10,
    "okt": 10,
    "november": 11,
    "nov": 11,
    "dezember": 12,
    "dez": 12,
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _parse_structured_age_months(age_field: str) -> Optional[float]:
    """Parse structured age strings like '1 Jahr und 8 Monate', '12 Wochen', '4 Monate'."""
    t = _norm(age_field)
    if not t:
        return None
    years = 0.0
    months = 0.0
    weeks = 0.0
    matched_any = False

    m = re.search(r"(\d+)\s*(?:jahr|jahre|jahren)", t)
    if m:
        years = float(m.group(1))
        matched_any = True
    m = re.search(r"(\d+)\s*(?:monat|monate|monaten)", t)
    if m:
        months = float(m.group(1))
        matched_any = True
    m = re.search(r"(\d+)\s*(?:woche|wochen)", t)
    if m:
        weeks = float(m.group(1))
        matched_any = True

    if not matched_any:
        return None
    return years * 12.0 + months + weeks / 4.33


def _estimate_birth_age_months(text: str, today: dt.date) -> Optional[float]:
    """Detect explicit birth dates like '27.09.2026', 'April 2024', 'im April geboren'."""
    t = _norm(text)

    # 1. Exact DD.MM.YYYY near birth words
    m = re.search(
        r"(?:geboren|geb\.?|am|zur welt)\s*(?:am\s*)?(\d{1,2})\.(\d{1,2})\.(20\d{2})",
        t,
    )
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            bdate = dt.date(year, month, day)
            days = (today - bdate).days
            if -30 <= days <= 365 * 25:
                return max(0.0, days / 30.44)
        except ValueError:
            pass

    # 2. Month + Year (e.g. 'Geburtsdatum: März 2024' or 'geboren Mai 2025')
    month_pat = "|".join(MONTH_MAP.keys())
    m = re.search(
        rf"(?:geboren|geburtsdatum|geb\.?)[^.\n]{{0,25}}\b({month_pat})\.?\s*(20\d{{2}})\b",
        t,
    )
    if m:
        month = MONTH_MAP[m.group(1)]
        year = int(m.group(2))
        diff = (today.year - year) * 12 + (today.month - month)
        if -1 <= diff <= 300:
            return float(max(0, diff))

    # 3. Month only ('im April geboren') -> assume most recent past occurrence
    m = re.search(rf"\bim\s+({month_pat})\s+geboren\b", t)
    if m:
        month = MONTH_MAP[m.group(1)]
        diff = today.month - month
        if diff < 0:
            diff += 12
        return float(diff)

    return None


def _check_age(listing: Listing, full_text: str, config: WatcherConfig, today: dt.date) -> Optional[str]:
    """Return rejection reason if clearly too old, else None."""
    # Structured age field (e.g. Tieranzeigen.at)
    if listing.age_field:
        months = _parse_structured_age_months(listing.age_field)
        if months is not None and months > config.max_age_months + 0.5:
            return f"Zu alt ({listing.age_field})"

    has_kitten_cue = any(k in full_text for k in KITTEN_CUES)

    # Explicit birth date
    birth_months = _estimate_birth_age_months(full_text, today)
    if birth_months is not None and birth_months > config.max_age_months + 0.5:
        return f"Zu alt (~{birth_months:.0f} Monate lt. Geburtsdatum)"

    # Explicit adult words when no kitten cues
    if not has_kitten_cue:
        if re.search(r"\b(?:erwachsen\w*|senior\w*|ausgewachsen\w*)\b", full_text):
            return "Ausgewachsene/ältere Katze"

        # Explicit age in years (ignore references to mother/father)
        for m in re.finditer(r"\b(\d+)\s*(?:jahr|jahre|jahren|jährig\w*|jaehrig\w*)\b", full_text):
            years = int(m.group(1))
            prefix = full_text[max(0, m.start() - 35): m.start()]
            if any(p in prefix for p in ("mutter", "mama", "vater", "papa", "eltern", "seit", "über")):
                continue
            if years >= 1:
                return f"Zu alt ({m.group(0)})"

        # Explicit age in months (only reject if all mentioned ages > max_age_months)
        month_matches = [
            int(m.group(1))
            for m in re.finditer(r"\b(\d+)\s*(?:monat|monate|monaten)\b", full_text)
        ]
        if month_matches and min(month_matches) > config.max_age_months:
            return f"Zu alt ({min(month_matches)} Monate)"

    return None


def _check_gender(listing: Listing, full_text: str) -> tuple[bool, str]:
    """Return (allowed, gender_label). Rejects only clearly male-only listings."""
    gf = _norm(listing.gender_field)
    if gf:
        has_f = any(w in gf for w in ("weiblich", "weibchen", "katze", "mädchen"))
        has_m = any(w in gf for w in ("männlich", "maennlich", "kater"))
        if has_f and has_m:
            return True, "Gemischter Wurf (inkl. weiblich)"
        if has_f:
            return True, "Weiblich"
        if has_m:
            return False, "Nur männlich / Kater"

    # Strip sentences about the father/sire so "Vater ist ein roter Kater" doesn't trigger male-only
    cleaned = re.sub(
        r"(?:vater|papa|deckkater)[^.!?\n]{0,60}",
        " ",
        full_text,
    )

    has_female = any(re.search(pat, cleaned) for pat in FEMALE_PATTERNS)
    has_male = any(re.search(pat, cleaned) for pat in MALE_PATTERNS)

    if has_female and has_male:
        return True, "Gemischter Wurf (inkl. weiblich)"
    if has_female:
        return True, "Weiblich"
    if has_male:
        return False, "Nur männlich / Kater"
    return True, "Geschlecht unklar / ganzer Wurf"


def evaluate_listing(
    listing: Listing,
    config: WatcherConfig,
    today: Optional[dt.date] = None,
) -> FilterDecision:
    """Evaluate a listing against all user criteria."""
    today = today or dt.date.today()
    title_l = _norm(listing.title)
    desc_l = _norm(listing.description)
    seller_l = _norm(listing.seller_name)
    cat_l = _norm(listing.category)
    tags_l = _norm(" ".join(listing.extra_tags))
    full_text = f"{title_l} {desc_l} {seller_l} {cat_l} {tags_l}".strip()

    # 1. Country check
    if listing.country and listing.country.upper() != "AT":
        return FilterDecision(False, f"Ausland ({listing.country})")

    # 2. Distance check
    if listing.distance_km is not None:
        if listing.distance_km > config.max_distance_km:
            return FilterDecision(
                False,
                f"Zu weit entfernt ({listing.distance_km:.0f} km > {config.max_distance_km:.0f} km)",
            )
    else:
        # Without coordinates, only allow OÖ (4xxx) or neighboring west-NÖ (33xx)
        if listing.postcode and not (listing.postcode.startswith("4") or listing.postcode.startswith("33")):
            return FilterDecision(False, f"PLZ außerhalb Region Linz ({listing.postcode})")

    # 3. Reserved / Sold / Wanted check
    if listing.reserved:
        return FilterDecision(False, "Bereits reserviert")
    for pat in UNAVAILABLE_OR_WANTED_PATTERNS:
        if re.search(pat, title_l):
            return FilterDecision(False, f"Nicht verfügbar / Suchanzeige ({pat})")

    # 4. Price check
    if listing.price_eur is not None and listing.price_eur > config.max_price_eur:
        return FilterDecision(
            False,
            f"Zu teuer (€ {listing.price_eur:.0f} > € {config.max_price_eur:.0f})",
        )

    # 5. No Tierheim / Tierschutz / Pedigree Club
    for kw in SHELTER_OR_CLUB_KEYWORDS:
        if kw in full_text:
            return FilterDecision(False, f"Tierheim/Tierschutz/Zuchtverein ({kw})")

    # 6. Exclude purebred cats unless explicitly Bauernhof
    has_farm_word = "bauernhof" in full_text or "hofkatze" in full_text
    if not has_farm_word:
        for breed in PUREBRED_KEYWORDS:
            if re.search(rf"\b{re.escape(breed)}\b", f"{title_l} {cat_l}"):
                return FilterDecision(False, f"Rassekatze ({breed})")

    # For Willhaben's "Rassekatzen / Mischlinge" category, require farm/housecat indicator
    if listing.require_farm_or_mix_keyword:
        if not any(kw in full_text for kw in FARM_OR_HOUSECAT_KEYWORDS):
            return FilterDecision(False, "Mischlinge-Kategorie ohne Bauernhof-/Hauskatzen-Bezug")

    # 7. Age check
    age_rejection = _check_age(listing, full_text, config, today)
    if age_rejection:
        return FilterDecision(False, age_rejection)

    # 8. Gender check (female OR unclear/litter allowed; male-only rejected)
    gender_ok, gender_label = _check_gender(listing, f"{title_l} {desc_l}")
    if not gender_ok:
        return FilterDecision(False, gender_label)

    # Build helpful highlights for the push notification
    highlights: list[str] = []
    if has_farm_word:
        highlights.append("Bauernhof")
    if any(k in full_text for k in ("kitten", "baby", "babys", "kätzchen", "wochen")):
        highlights.append("Jungtier/Kitten")
    if gender_label == "Weiblich":
        highlights.append("Weiblich")

    return FilterDecision(True, "Treffer", gender_label=gender_label, highlights=highlights)
