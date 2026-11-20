"""Austrian postal code -> coordinates resolver with built-in Linz-area seed table
and cached api.zippopotam.us fallback (zero external dependencies).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Optional

# Seed table of major PLZs around Linz so common lookups never need an API call.
# Any unlisted AT postal code is resolved via api.zippopotam.us and persisted in state.json.
BUILTIN_AT_PLZ: dict[str, tuple[float, float]] = {
    # Linz & Linz-Land
    "4020": (48.3064, 14.2861),
    "4030": (48.2489, 14.3189),
    "4040": (48.3289, 14.2858),
    "4050": (48.2219, 14.2397),  # Traun
    "4052": (48.2089, 14.2903),  # Ansfelden
    "4053": (48.2036, 14.2606),  # Haid
    "4055": (48.1878, 14.2225),  # Pucking
    "4060": (48.2764, 14.2533),  # Leonding
    "4061": (48.2583, 14.2053),  # Pasching
    "4062": (48.2572, 14.1619),  # Thening
    "4063": (48.2275, 14.1819),  # Hörsching
    "4064": (48.2256, 14.1558),  # Oftering
    "4070": (48.3089, 14.0225),  # Eferding
    "4072": (48.2825, 14.1061),  # Alkoven
    "4073": (48.3236, 14.1917),  # Wilhering
    "4074": (48.3358, 13.9497),  # Stroheim
    "4075": (48.2683, 14.0044),  # Breitenaich
    "4076": (48.2650, 13.9722),  # St. Marienkirchen
    "4081": (48.3622, 14.0067),  # Hartkirchen
    "4082": (48.3747, 14.0281),  # Aschach
    "4083": (48.4142, 13.9144),  # Haibach
    "4100": (48.3328, 14.1725),  # Ottensheim
    "4101": (48.3422, 14.0519),  # Feldkirchen an der Donau
    "4102": (48.3636, 14.1131),  # Goldwörth
    "4111": (48.3497, 14.1553),  # Walding
    "4112": (48.3764, 14.1539),  # Rottenegg
    "4113": (48.4161, 14.0933),  # St. Martin im Mühlkreis
    "4114": (48.4581, 14.0189),  # Neuhaus
    "4115": (48.4453, 14.0358),  # Kleinzell
    "4120": (48.4811, 14.0022),  # Neufelden
    "4150": (48.5722, 13.9908),  # Rohrbach-Berg
    "4170": (48.5786, 14.0372),  # Haslach
    "4180": (48.4594, 14.2286),  # Zwettl an der Rodl
    "4181": (48.4733, 14.2058),  # Oberneukirchen
    "4190": (48.5675, 14.2875),  # Bad Leonfelden
    "4201": (48.3811, 14.1917),  # Gramastetten
    "4202": (48.4317, 14.2944),  # Hellmonsödt
    "4203": (48.3717, 14.3494),  # Altenberg bei Linz
    "4204": (48.4547, 14.3775),  # Reichenau im Mühlkreis
    "4209": (48.3469, 14.4150),  # Engerwitzdorf
    "4210": (48.3536, 14.4153),  # Gallneukirchen
    "4211": (48.3978, 14.4050),  # Alberndorf
    "4212": (48.4294, 14.4822),  # Neumarkt im Mühlkreis
    "4221": (48.2856, 14.3653),  # Steyregg
    "4222": (48.2683, 14.4322),  # St. Georgen an der Gusen
    "4223": (48.3189, 14.4775),  # Katsdorf
    "4224": (48.3494, 14.5094),  # Wartberg ob der Aist
    "4225": (48.2739, 14.4150),  # Luftenberg
    "4230": (48.3578, 14.5311),  # Pregarten
    "4232": (48.3661, 14.5161),  # Hagenberg
    "4240": (48.5117, 14.5044),  # Freistadt
    "4273": (48.4517, 14.7736),  # Kaltenberg
    "4280": (48.4044, 14.7367),  # Königswiesen
    "4291": (48.4686, 14.5419),  # Lasberg
    "4300": (48.1742, 14.5333),  # St. Valentin (NÖ)
    "4303": (48.1989, 14.5653),  # St. Pantaleon
    "4310": (48.2414, 14.5186),  # Mauthausen
    "4311": (48.2764, 14.5819),  # Schwertberg
    "4312": (48.2636, 14.5236),  # Ried in der Riedmark
    "4320": (48.2508, 14.6331),  # Perg
    "4331": (48.2275, 14.6078),  # Naarn im Machlande
    "4341": (48.2469, 14.7481),  # Arbing
    "4360": (48.2278, 14.8508),  # Grein
    "4400": (48.0428, 14.4214),  # Steyr
    "4407": (48.0600, 14.4272),  # Dietach
    "4421": (48.0372, 14.3311),  # Aschach an der Steyr
    "4431": (48.1056, 14.5672),  # Haidershofen
    "4441": (48.0369, 14.4969),  # Behamberg
    "4451": (48.0219, 14.4075),  # Garsten
    "4470": (48.2139, 14.4792),  # Enns
    "4481": (48.2194, 14.4178),  # Asten
    "4482": (48.2111, 14.4939),  # Ennsdorf (NÖ)
    "4483": (48.1656, 14.4600),  # Hargelsberg
    "4484": (48.1469, 14.4658),  # Kronstorf
    "4490": (48.2072, 14.3775),  # St. Florian
    "4491": (48.1678, 14.3711),  # Niederneukirchen
    "4492": (48.1400, 14.3958),  # Hofkirchen im Traunkreis
    "4493": (48.1039, 14.3939),  # Wolfern
    "4501": (48.1319, 14.2347),  # Neuhofen an der Krems
    "4502": (48.1489, 14.2811),  # St. Marien
    "4511": (48.1517, 14.1592),  # Allhaming
    "4521": (48.0933, 14.3164),  # Schiedlberg
    "4522": (48.0469, 14.3075),  # Sierning
    "4523": (48.0467, 14.3469),  # Neuzeug
    "4531": (48.1117, 14.1914),  # Kematen an der Krems
    "4532": (48.0811, 14.2122),  # Rohr im Kremstal
    "4540": (48.0342, 14.2089),  # Bad Hall
    "4550": (48.0558, 14.1306),  # Kremsmünster
    "4560": (47.9061, 14.1200),  # Kirchdorf an der Krems
    "4600": (48.1575, 14.0289),  # Wels
    "4611": (48.2211, 14.0989),  # Buchkirchen
    "4612": (48.2611, 14.0511),  # Scharten
    "4614": (48.1914, 14.1119),  # Marchtrenk
    "4615": (48.2233, 14.1325),  # Holzhausen
    "4616": (48.1656, 14.1258),  # Weißkirchen an der Traun
    "4621": (48.1083, 14.1206),  # Sipbachzell
    "4622": (48.1253, 14.1422),  # Eggendorf
    "4623": (48.1333, 13.9433),  # Gunskirchen
    "4624": (48.0869, 13.9422),  # Pennewang
    "4625": (48.1628, 13.8414),  # Offenhausen
    "4631": (48.1872, 13.9633),  # Krenglbach
    "4632": (48.1875, 13.9136),  # Pichl bei Wels
    "4641": (48.0750, 14.0222),  # Steinhaus
    "4642": (48.0706, 14.0581),  # Sattledt
    "4650": (48.0933, 13.8764),  # Lambach
    "4655": (48.0044, 13.9247),  # Vorchdorf
    "4701": (48.2283, 13.9033),  # Bad Schallerbach
    "4702": (48.2342, 13.9475),  # Wallern
    "4710": (48.2356, 13.8314),  # Grieskirchen
    "4713": (48.2067, 13.8161),  # Gallspach
    "4722": (48.3472, 13.7711),  # Peuerbach
    "4810": (47.9183, 13.7994),  # Gmunden
    "4840": (48.0086, 13.6556),  # Vöcklabruck
    "4910": (48.2100, 13.4894),  # Ried im Innkreis
    "3300": (48.1219, 14.8722),  # Amstetten (NÖ)
    "3350": (48.1103, 14.5633),  # Stadt Haag (NÖ)
    "3352": (48.0469, 14.6231),  # St. Peter in der Au (NÖ)
    "3353": (48.0056, 14.6611),  # Seitenstetten (NÖ)
    "3355": (47.9775, 14.6306),  # Ertl (NÖ)
    "3361": (48.0731, 14.7564),  # Aschbach-Markt (NÖ)
    "3363": (48.0886, 14.8194),  # Ulmerfeld-Hausmening (NÖ)
    "3311": (48.1333, 14.8031),  # Zeillern (NÖ)
    "3313": (48.1656, 14.7772),  # Wallsee (NÖ)
    "3314": (48.1444, 14.6514),  # Strengberg (NÖ)
}


def extract_plz(text: str) -> str:
    """Extract a 4-digit Austrian postal code from a string like '4073 Wilhering'."""
    if not text:
        return ""
    m = re.search(r"\b([1-9]\d{3})\b", text)
    return m.group(1) if m else ""


def resolve_plz(
    plz: str,
    plz_cache: dict[str, list[float]],
    timeout_sec: int = 10,
) -> Optional[tuple[float, float]]:
    """Resolve an Austrian 4-digit postal code to (lat, lng).

    Checks built-in table -> persistent cache -> free api.zippopotam.us/AT/<plz>.
    """
    code = extract_plz(plz)
    if not code:
        return None
    if code in BUILTIN_AT_PLZ:
        return BUILTIN_AT_PLZ[code]
    if code in plz_cache:
        val = plz_cache[code]
        if isinstance(val, list) and len(val) == 2:
            return (float(val[0]), float(val[1]))
        return None

    url = f"https://api.zippopotam.us/AT/{code}"
    req = urllib.request.Request(url, headers={"User-Agent": "katzen-watcher/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            places = data.get("places") or []
            if places:
                lat = float(places[0]["latitude"])
                lng = float(places[0]["longitude"])
                plz_cache[code] = [round(lat, 5), round(lng, 5)]
                return (lat, lng)
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
        pass
    return None
