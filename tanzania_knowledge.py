"""
Tanzania Geographic & Cultural Knowledge Layer

This module helps the AI understand Tanzanian locations,
administrative areas, common local names, addresses,
and everyday Tanzanian sales language.

The design intentionally keeps geographic knowledge outside
ai_engine.py so the dataset can grow without breaking the AI.
"""

import re
import unicodedata


# ============================================================
# TANZANIA COUNTRY CONTEXT
# ============================================================

COUNTRY_CONTEXT = """
COUNTRY:
United Republic of Tanzania

COMMON NAME:
Tanzania

COUNTRY CODE:
TZ

PHONE COUNTRY CODE:
+255

CURRENCY:
Tanzanian Shilling (TZS / TSH)

MAIN LANGUAGES USED IN BUSINESS:
Kiswahili and English

TIMEZONE:
Africa/Dar_es_Salaam

IMPORTANT:
Tanzania includes Mainland Tanzania and Zanzibar.
"""


# ============================================================
# REGIONS
# ============================================================

TANZANIA_REGIONS = {
    # Mainland
    "arusha": "Arusha",
    "dar es salaam": "Dar es Salaam",
    "dodoma": "Dodoma",
    "geita": "Geita",
    "iringa": "Iringa",
    "kagera": "Kagera",
    "katavi": "Katavi",
    "kigoma": "Kigoma",
    "kilimanjaro": "Kilimanjaro",
    "lindi": "Lindi",
    "manyara": "Manyara",
    "mara": "Mara",
    "mbeya": "Mbeya",
    "morogoro": "Morogoro",
    "mtwara": "Mtwara",
    "mwanza": "Mwanza",
    "njombe": "Njombe",
    "pwani": "Pwani",
    "rukwa": "Rukwa",
    "ruvuma": "Ruvuma",
    "shinyanga": "Shinyanga",
    "simiyu": "Simiyu",
    "singida": "Singida",
    "songwe": "Songwe",
    "tabora": "Tabora",
    "tanga": "Tanga",

    # Zanzibar
    "kaskazini unguja": "Kaskazini Unguja",
    "kusini unguja": "Kusini Unguja",
    "mjini magharibi": "Mjini Magharibi",
    "kaskazini pemba": "Kaskazini Pemba",
    "kusini pemba": "Kusini Pemba",
}


# ============================================================
# COMMON REGION ALIASES
# ============================================================

REGION_ALIASES = {
    "dar": "Dar es Salaam",
    "dar es salaam": "Dar es Salaam",
    "dsm": "Dar es Salaam",

    "arusha": "Arusha",
    "dodoma": "Dodoma",
    "mwanza": "Mwanza",
    "mbeya": "Mbeya",
    "morogoro": "Morogoro",
    "tanga": "Tanga",
    "tabora": "Tabora",
    "kigoma": "Kigoma",
    "iringa": "Iringa",
    "mtwara": "Mtwara",
    "lindi": "Lindi",
    "kagera": "Kagera",
    "manyara": "Manyara",
    "mara": "Mara",
    "geita": "Geita",
    "katavi": "Katavi",
    "kilimanjaro": "Kilimanjaro",
    "njombe": "Njombe",
    "pwani": "Pwani",
    "rukwa": "Rukwa",
    "ruvuma": "Ruvuma",
    "shinyanga": "Shinyanga",
    "simiyu": "Simiyu",
    "singida": "Singida",
    "songwe": "Songwe",
}


# ============================================================
# IMPORTANT TANZANIAN CITIES / URBAN CENTRES
# ============================================================

TANZANIAN_CITIES = {
    "Dar es Salaam": "Dar es Salaam",
    "Dodoma": "Dodoma",
    "Arusha": "Arusha",
    "Mwanza": "Mwanza",
    "Mbeya": "Mbeya",
    "Morogoro": "Morogoro",
    "Tanga": "Tanga",
    "Zanzibar City": "Mjini Magharibi",
    "Moshi": "Kilimanjaro",
    "Iringa": "Iringa",
    "Songea": "Ruvuma",
    "Mtwara": "Mtwara",
    "Lindi": "Lindi",
    "Tabora": "Tabora",
    "Kigoma": "Kigoma",
    "Shinyanga": "Shinyanga",
    "Bukoba": "Kagera",
    "Musoma": "Mara",
    "Singida": "Singida",
    "Sumbawanga": "Rukwa",
    "Njombe": "Njombe",
    "Geita": "Geita",
    "Babati": "Manyara",
    "Mpanda": "Katavi",
    "Tunduma": "Songwe",
}


# ============================================================
# DAR ES SALAAM COMMON LOCATIONS
# ============================================================

DAR_ES_SALAAM_LOCATIONS = {
    "kariakoo": {
        "name": "Kariakoo",
        "city": "Dar es Salaam",
        "type": "commercial area / market area",
    },

    "tandale": {
        "name": "Tandale",
        "city": "Dar es Salaam",
        "type": "locality / ward area",
    },

    "manzese": {
        "name": "Manzese",
        "city": "Dar es Salaam",
        "type": "locality / ward area",
    },

    "tairi tatu": {
        "name": "Tairi Tatu",
        "city": "Dar es Salaam",
        "type": "local area",
    },

    "magomeni": {
        "name": "Magomeni",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "sinza": {
        "name": "Sinza",
        "city": "Dar es Salaam",
        "type": "locality / ward area",
    },

    "mikocheni": {
        "name": "Mikocheni",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "msasani": {
        "name": "Msasani",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "masaki": {
        "name": "Masaki",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "kinondoni": {
        "name": "Kinondoni",
        "city": "Dar es Salaam",
        "type": "municipality / area",
    },

    "ilala": {
        "name": "Ilala",
        "city": "Dar es Salaam",
        "type": "municipality / district area",
    },

    "temeke": {
        "name": "Temeke",
        "city": "Dar es Salaam",
        "type": "municipality / district area",
    },

    "ubungo": {
        "name": "Ubungo",
        "city": "Dar es Salaam",
        "type": "municipality / district area",
    },

    "kigamboni": {
        "name": "Kigamboni",
        "city": "Dar es Salaam",
        "type": "municipality / district area",
    },

    "posta": {
        "name": "Posta",
        "city": "Dar es Salaam",
        "type": "central business area",
    },

    "upanga": {
        "name": "Upanga",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "kariakoo market": {
        "name": "Kariakoo Market",
        "city": "Dar es Salaam",
        "type": "market",
    },

    "buguruni": {
        "name": "Buguruni",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "tabata": {
        "name": "Tabata",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "kimara": {
        "name": "Kimara",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "mbezi": {
        "name": "Mbezi",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "gongolamboto": {
        "name": "Gongolamboto",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "chanika": {
        "name": "Chanika",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "mbagala": {
        "name": "Mbagala",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "kurasini": {
        "name": "Kurasini",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "changombe": {
        "name": "Chang'ombe",
        "city": "Dar es Salaam",
        "type": "locality",
    },

    "ilala": {
        "name": "Ilala",
        "city": "Dar es Salaam",
        "type": "district area",
    },
}


# ============================================================
# COMMON TANZANIAN ADDRESS TERMS
# ============================================================

ADDRESS_TERMS = {
    "mtaa": "street/locality",
    "mtaa wa": "street/locality",
    "barabara": "road/street",
    "barabara ya": "road/street",
    "road": "road/street",
    "street": "street",
    "kijiji": "village",
    "kijijini": "village/rural area",
    "kitongoji": "hamlet/sub-village",
    "kata": "ward",
    "wilaya": "district",
    "mkoa": "region",
    "shehia": "shehia",
    "eneo": "area/locality",
    "soko": "market",
    "stendi": "bus/transport stand",
    "terminal": "transport terminal",
    "posta": "post office / central area",
    "jengo": "building",
    "ghorofa": "floor",
    "nyumba": "house",
    "namba ya nyumba": "house number",
    "postcode": "postcode",
    "postikodi": "postcode",
}


# ============================================================
# COMMON TANZANIAN SALES / CHAT EXPRESSIONS
# ============================================================

TANZANIAN_SALES_LANGUAGE = {
    "sh ngapi": "asking for price",
    "sh ngapi?": "asking for price",
    "bei yake": "asking for price",
    "bei ni ngapi": "asking for price",
    "bei gani": "asking for price",
    "mna hii": "asking whether product is available",
    "ipo": "asking whether product is available",
    "ipo bado": "asking whether product is still available",
    "mna stock": "asking about stock",
    "stock ipo": "asking about stock",
    "na delivery": "asking about delivery",
    "delivery je": "asking about delivery",
    "mnafika": "asking whether delivery/service reaches location",
    "mko wapi": "asking business location",
    "upo wapi": "asking business location",
    "nitumie namba": "asking for payment/contact number",
    "lipa vipi": "asking payment method",
    "bei ya jumla": "asking wholesale price",
    "nipunguzie": "asking for discount",
    "last price": "asking for final/best price",
    "nataka mbili": "customer wants quantity two",
    "nataka tatu": "customer wants quantity three",
}


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(text: str) -> str:
    """
    Normalize customer text for location matching.
    """

    if not text:
        return ""

    text = str(text).lower().strip()

    text = unicodedata.normalize(
        "NFKD",
        text
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


# ============================================================
# LOCATION MATCHING
# ============================================================

def find_known_locations(
    customer_message: str
) -> list[dict]:
    """
    Detect known Tanzanian regions, cities and common
    Dar es Salaam locations.

    This does not claim that an unknown location does not exist.
    It only returns locations confidently recognized by this layer.
    """

    normalized = normalize_text(
        customer_message
    )

    results = []

    # Regions
    for alias, official_name in REGION_ALIASES.items():

        pattern = rf"\b{re.escape(alias)}\b"

        if re.search(pattern, normalized):

            results.append({
                "name": official_name,
                "type": "region",
                "confidence": "high",
            })

    # Cities
    for city, region in TANZANIAN_CITIES.items():

        city_normalized = normalize_text(
            city
        )

        if city_normalized in normalized:

            results.append({
                "name": city,
                "region": region,
                "type": "city",
                "confidence": "high",
            })

    # Dar locations
    for key, info in DAR_ES_SALAAM_LOCATIONS.items():

        key_normalized = normalize_text(
            key
        )

        if key_normalized in normalized:

            result = dict(info)

            result["type"] = (
                result.get(
                    "type",
                    "locality"
                )
            )

            result["confidence"] = "high"

            results.append(result)

    return _remove_duplicate_locations(
        results
    )


# ============================================================
# ADDRESS SIGNALS
# ============================================================

def detect_address_signals(
    customer_message: str
) -> list[str]:
    """
    Detect whether customer message contains
    address/location language.
    """

    normalized = normalize_text(
        customer_message
    )

    found = []

    for term, meaning in ADDRESS_TERMS.items():

        if term in normalized:

            found.append(
                f"{term} = {meaning}"
            )

    return found


# ============================================================
# SALES LANGUAGE SIGNALS
# ============================================================

def detect_sales_signals(
    customer_message: str
) -> list[str]:
    """
    Detect common Tanzanian sales expressions.
    """

    normalized = normalize_text(
        customer_message
    )

    found = []

    for phrase, meaning in TANZANIAN_SALES_LANGUAGE.items():

        if normalize_text(phrase) in normalized:

            found.append(
                f"{phrase} = {meaning}"
            )

    return found


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def _remove_duplicate_locations(
    locations: list[dict]
) -> list[dict]:

    unique = []

    seen = set()

    for location in locations:

        key = (
            location.get("name"),
            location.get("type"),
            location.get("region"),
        )

        if key not in seen:

            seen.add(key)

            unique.append(
                location
            )

    return unique


# ============================================================
# TANZANIA CONTEXT FOR AI
# ============================================================

def get_tanzania_context(
    customer_message: str
) -> str:
    """
    Generate only the relevant Tanzania knowledge
    for the current customer message.

    This keeps the AI prompt small and efficient.
    """

    locations = find_known_locations(
        customer_message
    )

    address_signals = detect_address_signals(
        customer_message
    )

    sales_signals = detect_sales_signals(
        customer_message
    )

    lines = []

    lines.append(
        COUNTRY_CONTEXT.strip()
    )

    # Known locations
    if locations:

        lines.append(
            "\nRECOGNIZED TANZANIAN LOCATIONS:"
        )

        for location in locations:

            name = location.get(
                "name",
                ""
            )

            location_type = location.get(
                "type",
                ""
            )

            region = location.get(
                "region",
                ""
            )

            line = (
                f"- {name}"
                f" | Type: {location_type}"
            )

            if region:
                line += (
                    f" | Region/area: {region}"
                )

            lines.append(line)

    # Address signals
    if address_signals:

        lines.append(
            "\nADDRESS SIGNALS:"
        )

        for signal in address_signals:

            lines.append(
                f"- {signal}"
            )

    # Sales language
    if sales_signals:

        lines.append(
            "\nTANZANIAN SALES LANGUAGE:"
        )

        for signal in sales_signals:

            lines.append(
                f"- {signal}"
            )

    lines.append(
        """
GEOGRAPHIC SAFETY RULES:

- Recognizing a place name does not mean the AI knows
  the exact distance, route, delivery price or travel time.

- Never invent delivery fees.

- Never invent travel time.

- Never claim a specific road route unless route data
  is actually available.

- If the customer gives an incomplete location,
  ask for the missing information when necessary.

- If a place is not recognized by this local knowledge
  layer, do not automatically say the place does not exist.

- The merchant's own delivery coverage and business
  information always take priority for sales decisions.

- A customer can mention a region, district, ward,
  village, street, landmark, building or informal/local
  place name.

- Treat location words as possible geographic context,
  not automatically as a request for navigation.
"""
    )

    return "\n".join(lines)
