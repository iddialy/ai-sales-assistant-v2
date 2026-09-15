"""Tanzania context helpers for the AI Sales Assistant.

Keeps Tanzania-specific time and administrative vocabulary in one place.
The LLM remains responsible for natural-language recognition of place names;
this module supplies the current Tanzania clock and authoritative geography
levels used by NBS/administrative terminology.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

TANZANIA_TZ = ZoneInfo("Africa/Dar_es_Salaam")

# Tanzania has 31 regions in the United Republic: 26 Mainland + 5 Zanzibar.
# Names are provided as a recognition aid; lower-level units are intentionally
# not hard-coded here because NBS administrative boundaries/data can change.
TANZANIA_REGIONS = [
    "Arusha", "Dar es Salaam", "Dodoma", "Geita", "Iringa", "Kagera",
    "Katavi", "Kigoma", "Kilimanjaro", "Lindi", "Manyara", "Mara",
    "Mbeya", "Morogoro", "Mtwara", "Mwanza", "Njombe", "Pwani",
    "Rukwa", "Ruvuma", "Shinyanga", "Simiyu", "Singida", "Songwe",
    "Tabora", "Tanga",
    "Mjini Magharibi", "Kaskazini Unguja", "Kusini Unguja",
    "Kaskazini Pemba", "Kusini Pemba",
]

ADMIN_LEVELS = (
    "mkoa/region",
    "wilaya/district",
    "halmashauri/council",
    "tarafa/division",
    "kata/ward",
    "mtaa/street",
    "kijiji/village",
    "kitongoji/hamlet",
)


def get_tanzania_time_context() -> str:
    now = datetime.now(TANZANIA_TZ)
    return (
        "CURRENT TANZANIA TIME (authoritative runtime clock)\n"
        f"- Date: {now.strftime('%Y-%m-%d')}\n"
        f"- Time: {now.strftime('%H:%M:%S')}\n"
        f"- Day: {now.strftime('%A')}\n"
        "- Timezone: Africa/Dar_es_Salaam\n"
        "- UTC offset: +03:00 (EAT)\n"
    )


def get_tanzania_context(text: str = "") -> str:
    regions = ", ".join(TANZANIA_REGIONS)
    levels = ", ".join(ADMIN_LEVELS)
    return (
        "TANZANIA GEOGRAPHY RECOGNITION\n"
        f"- Regions: {regions}\n"
        f"- Administrative levels/terms: {levels}\n"
        "- Recognize Tanzanian place names in both Kiswahili and English spelling.\n"
        "- Do not invent a district, ward, village, street, or other place.\n"
        "- If a place is uncertain, say that you are not certain instead of guessing.\n"
        "- For current official administrative boundaries, prefer the latest NBS/official administrative data when available.\n"
    )
