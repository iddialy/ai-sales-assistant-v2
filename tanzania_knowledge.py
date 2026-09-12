"""
Tanzania Knowledge + Time Engine
--------------------------------
Designed for the AI Sales Assistant.

Authoritative references used when designing this module:
- Tanzania National Bureau of Statistics (NBS): geographic levels include
  region, district, ward/shehia, villages/mitaa and enumeration areas.
- TCRA: Tanzania postcode system and national postcode directory.

Important:
This module intentionally does NOT invent a complete village/street list.
For village/mtaa-level verification, the application should use an official
TCRA/NBS dataset or a connected lookup service. The module provides a strong
national geographic backbone and a safe context layer.
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

TZ_TANZANIA = ZoneInfo("Africa/Dar_es_Salaam")


# TCRA regional postcode bases. Tanzania has 26 regions in the published
# national postcode list.
REGIONS = {
    "Arusha": "23000",
    "Dar es Salaam": "11000",
    "Dodoma": "41000",
    "Geita": "30000",
    "Iringa": "51000",
    "Kagera": "35000",
    "Katavi": "50000",
    "Kigoma": "47000",
    "Kilimanjaro": "25000",
    "Lindi": "65000",
    "Manyara": "27000",
    "Mara": "31000",
    "Mbeya": "53000",
    "Morogoro": "67000",
    "Mtwara": "63000",
    "Mwanza": "33000",
    "Njombe": "59000",
    "Pwani": "61000",
    "Rukwa": "55000",
    "Ruvuma": "57000",
    "Shinyanga": "37000",
    "Simiyu": "39000",
    "Singida": "43000",
    "Songwe": "54100",
    "Tabora": "45000",
    "Tanga": "21000",
}

REGION_ALIASES = {
    "dar": "Dar es Salaam",
    "dsm": "Dar es Salaam",
    "dar es salam": "Dar es Salaam",
    "dar es salaam": "Dar es Salaam",
    "dodoma mjini": "Dodoma",
    "arusha mjini": "Arusha",
    "mwanza mjini": "Mwanza",
    "mbeya mjini": "Mbeya",
    "tanga mjini": "Tanga",
    "morogoro mjini": "Morogoro",
    "zanzibar": "Zanzibar",
    "ungunja": "Zanzibar",
    "pemba": "Pemba",
}

# High-value administrative/place vocabulary. This is intentionally not
# presented as an exhaustive lower-level gazetteer.
COMMON_DISTRICTS = {
    "Dar es Salaam": [
        "Ilala", "Kinondoni", "Temeke", "Ubungo", "Kigamboni",
    ],
    "Arusha": [
        "Arusha City", "Arusha District", "Longido", "Meru",
        "Monduli", "Ngorongoro",
    ],
    "Dodoma": [
        "Dodoma City", "Bahi", "Chamwino", "Chemba", "Kondoa",
        "Kongwa", "Mpwapwa",
    ],
    "Kilimanjaro": [
        "Moshi Municipal", "Moshi District", "Hai", "Rombo",
        "Same", "Siha",
    ],
    "Tanga": [
        "Tanga City", "Korogwe", "Lushoto", "Handeni", "Kilindi",
        "Muheza", "Mkinga", "Pangani",
    ],
    "Morogoro": [
        "Morogoro Municipal", "Morogoro District", "Kilosa",
        "Kilombero", "Ulanga", "Mvomero", "Gairo", "Malinyi",
    ],
    "Mwanza": [
        "Nyamagana", "Ilemela", "Sengerema", "Magu", "Misungwi",
        "Kwimba", "Ukerewe",
    ],
    "Mbeya": [
        "Mbeya City", "Mbeya District", "Rungwe", "Kyela",
        "Chunya", "Mbarali",
    ],
    "Pwani": [
        "Kibaha Town", "Kibaha District", "Bagamoyo", "Chalinze",
        "Mkuranga", "Rufiji", "Kibiti", "Mafia",
    ],
    "Lindi": [
        "Lindi Municipal", "Lindi District", "Kilwa", "Liwale",
        "Nachingwea", "Ruangwa",
    ],
    "Mtwara": [
        "Mtwara Municipal", "Mtwara District", "Masasi",
        "Nanyumbu", "Newala", "Tandahimba",
    ],
    "Ruvuma": [
        "Songea Municipal", "Songea District", "Mbinga",
        "Namtumbo", "Nyasa", "Tunduru",
    ],
    "Iringa": [
        "Iringa Municipal", "Iringa District", "Kilolo", "Mufindi",
    ],
    "Njombe": [
        "Njombe Town", "Njombe District", "Ludewa", "Makete",
        "Wanging'ombe",
    ],
    "Rukwa": [
        "Sumbawanga Municipal", "Sumbawanga District", "Kalambo",
        "Nkasi",
    ],
    "Katavi": [
        "Mpanda Municipal", "Mpanda District", "Mlele", "Nsimbo",
    ],
    "Kigoma": [
        "Kigoma-Ujiji", "Kigoma District", "Kasulu", "Uvinza",
        "Buhigwe", "Kakonko",
    ],
    "Tabora": [
        "Tabora Municipal", "Nzega", "Igunga", "Uyui", "Urambo",
        "Sikonge", "Kaliua",
    ],
    "Shinyanga": [
        "Shinyanga Municipal", "Shinyanga District", "Kahama",
        "Kishapu", "Bariadi",
    ],
    "Simiyu": [
        "Bariadi", "Busega", "Maswa", "Meatu", "Itilima",
    ],
    "Mara": [
        "Musoma Municipal", "Musoma District", "Bunda", "Butiama",
        "Rorya", "Serengeti", "Tarime",
    ],
    "Kagera": [
        "Bukoba Municipal", "Bukoba District", "Biharamulo",
        "Karagwe", "Kyerwa", "Missenyi", "Ngara",
    ],
    "Geita": [
        "Geita Town", "Geita District", "Bukombe", "Chato",
        "Mbogwe", "Nyang'hwale",
    ],
    "Manyara": [
        "Babati Town", "Babati District", "Hanang", "Kiteto",
        "Mbulu", "Simanjiro",
    ],
    "Singida": [
        "Singida Municipal", "Singida District", "Iramba",
        "Manyoni", "Ikungi", "Mkalama",
    ],
}

# Important Zanzibar regions for United Republic context.
ZANZIBAR_REGIONS = [
    "Kaskazini Unguja",
    "Kusini Unguja",
    "Mjini Magharibi",
    "Kaskazini Pemba",
    "Kusini Pemba",
]


def normalize_place(text: str) -> str:
    text = (text or "").lower().strip()
    text = text.replace("’", "'")
    text = re.sub(r"[^a-z0-9\s'\-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def resolve_region(text: str) -> Optional[str]:
    value = normalize_place(text)

    for region in REGIONS:
        if normalize_place(region) in value:
            return region

    for alias, region in REGION_ALIASES.items():
        if alias in value:
            return region

    return None


def find_known_districts(text: str) -> list[tuple[str, str]]:
    value = normalize_place(text)
    found: list[tuple[str, str]] = []

    for region, districts in COMMON_DISTRICTS.items():
        for district in districts:
            if normalize_place(district) in value:
                found.append((district, region))

    return found


def get_tanzania_time() -> datetime:
    """Always returns the actual current time in Tanzania timezone."""
    return datetime.now(TZ_TANZANIA)


def get_tanzania_time_context() -> str:
    now = get_tanzania_time()

    weekdays = [
        "Jumatatu", "Jumanne", "Jumatano", "Alhamisi",
        "Ijumaa", "Jumamosi", "Jumapili",
    ]

    months = [
        "Januari", "Februari", "Machi", "Aprili", "Mei", "Juni",
        "Julai", "Agosti", "Septemba", "Oktoba", "Novemba", "Desemba",
    ]

    return (
        "TANZANIA REAL-TIME CLOCK\n"
        f"- Tarehe: {now.day} {months[now.month - 1]} {now.year}\n"
        f"- Siku: {weekdays[now.weekday()]}\n"
        f"- Saa ya Tanzania: {now.strftime('%H:%M:%S')}\n"
        f"- Timezone: Africa/Dar_es_Salaam (UTC+03:00)\n"
        "- Tanzania mainland hutumia UTC+3 na haina daylight-saving time.\n"
    )


def _region_context() -> str:
    lines = ["TANZANIA ADMINISTRATIVE GEOGRAPHY"]

    for region, postcode in REGIONS.items():
        districts = COMMON_DISTRICTS.get(region, [])
        if districts:
            lines.append(
                f"- {region} (postcode base {postcode}): "
                + ", ".join(districts)
            )
        else:
            lines.append(f"- {region} (postcode base {postcode})")

    lines.append("")
    lines.append(
        "NBS geographic hierarchy: Region → District → Ward/Shehia "
        "→ Village/Mtaa → Enumeration Area."
    )
    lines.append(
        "Do not invent a ward, village, street or postcode. "
        "If a lower-level place is not verified, say that it needs confirmation."
    )

    return "\n".join(lines)


def get_tanzania_context(text: str = "") -> str:
    """
    Returns compact, relevant Tanzania context for the current customer
    message. It is deliberately much smaller than dumping a national
    gazetteer into every Gemini request.
    """
    parts = [
        get_tanzania_time_context(),
        _region_context(),
    ]

    region = resolve_region(text)
    if region:
        parts.append(f"CURRENTLY DETECTED REGION: {region}")

    districts = find_known_districts(text)
    if districts:
        parts.append(
            "DETECTED DISTRICT(S): "
            + ", ".join(f"{district} ({region})" for district, region in districts)
        )

    return "\n\n".join(parts)


def get_tanzania_place_hint(text: str) -> str:
    region = resolve_region(text)
    districts = find_known_districts(text)

    if not region and not districts:
        return ""

    lines = ["Verified Tanzania place hints:"]
    if region:
        lines.append(f"- Region: {region}")
    for district, district_region in districts:
        lines.append(f"- District: {district} (Region: {district_region})")

    return "\n".join(lines)
