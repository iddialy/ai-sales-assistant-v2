import os
import time

import google.generativeai as genai
from models import Merchant


# -------------------------
# Gemini configuration
# -------------------------

API_KEY = os.environ.get("GEMINI_API_KEY", "")

if API_KEY:
    genai.configure(api_key=API_KEY)


# -------------------------
# AI response
# -------------------------

def generate_ai_sales_response(
    merchant: Merchant,
    customer_message: str,
    platform: str
) -> str:

    # -------------------------
    # Check API key
    # -------------------------

    if not API_KEY:
        return (
            "Samahani, AI bado haijaunganishwa kwenye server. "
            "Tafadhali wasiliana na support."
        )

    # -------------------------
    # Business Profile
    # -------------------------

    business_name = merchant.business_name or "Haijawekwa"
    business_phone = merchant.phone_number or "Haijawekwa"

    business_location = (
        merchant.business_location
        if merchant.business_location
        else "Haijawekwa"
    )

    business_type = (
        merchant.business_type
        if merchant.business_type
        else "Haijawekwa"
    )

    business_hours = (
        merchant.business_hours
        if merchant.business_hours
        else "Haijawekwa"
    )

    business_description = (
        merchant.business_description
        if merchant.business_description
        else "Haijawekwa"
    )

    # -------------------------
    # Payment information
    # -------------------------

    payment_info = merchant.payment_info

    if payment_info:

        lipa_namba = (
            payment_info.lipa_namba
            if payment_info.lipa_namba
            else "Haijawekwa"
        )

        phone_payment = (
            payment_info.phone_payment
            if payment_info.phone_payment
            else "Haijawekwa"
        )

        bank_account = (
            payment_info.bank_account
            if payment_info.bank_account
            else "Haijawekwa"
        )

    else:

        lipa_namba = "Haijawekwa"
        phone_payment = "Haijawekwa"
        bank_account = "Haijawekwa"

    # -------------------------
    # Product catalog
    # -------------------------

    products_text = "\n".join(
        [
            (
                f"- {p.product_name}: "
                f"TSH {p.price:,.0f}. "
                f"Maelezo: {p.description}"
            )
            for p in merchant.products
        ]
    )

    if not products_text:
        products_text = "Hakuna bidhaa zilizowekwa bado."

    # -------------------------
    # Business information
    # -------------------------

    business_info_text = f"""
TAARIFA ZA BIASHARA:

Jina la biashara:
{business_name}

Namba ya simu ya biashara:
{business_phone}

Location ya biashara:
{business_location}

Aina ya biashara:
{business_type}

Saa za kazi:
{business_hours}

Maelezo ya biashara:
{business_description}


TAARIFA ZA MALIPO:

Lipa Namba:
{lipa_namba}

Namba ya simu ya malipo:
{phone_payment}

Bank Account:
{bank_account}


ORODHA YA BIDHAA NA BEI:

{products_text}
"""

    # -------------------------
    # Language instructions
    # -------------------------

    if merchant.language_preference == "sw":

        instruction = f"""
Wewe ni Msaidizi wa Mauzo wa biashara
'{business_name}'.

Unazungumza na wateja kupitia {platform}.

LENGO:
- Kumsaidia mteja kuelewa biashara na bidhaa.
- Kumsaidia mteja kufanya uamuzi wa kununua.
- Kujibu kwa heshima, kwa lugha rahisi na fupi.
- Kutumia taarifa halisi za biashara zilizotolewa
  kwenye mfumo.

{business_info_text}

SHERIA MUHIMU:

1. TUMIA TAARIFA ZA BIASHARA
- Ukulizwa location ya biashara, tumia
  location iliyo kwenye taarifa hapo juu.
- Ukulizwa saa za kazi, tumia saa zilizo hapo juu.
- Ukulizwa aina ya biashara, tumia taarifa hapo juu.
- Ukulizwa kuhusu biashara kwa ujumla, tumia
  maelezo ya biashara hapo juu.

2. TAARIFA ZA MALIPO
- Ukulizwa "nalipaje?", "lipa namba ni ipi?",
  "namba ya malipo ni ipi?" au swali kama hilo,
  tumia taarifa za malipo zilizo hapo juu.
- Toa Lipa Namba ikiwa ipo.
- Toa namba ya simu ya malipo ikiwa ipo.
- Toa bank account ikiwa mteja ameuliza kuhusu
  malipo ya benki.
- USIBUNI namba ya malipo.
- Kama taarifa ya malipo haijawekwa, sema:
  "Tafadhali wasiliana na biashara kwa taarifa
  sahihi za malipo."

3. BIDHAA NA BEI
- Tumia bei halisi zilizopo kwenye katalogi pekee.
- Usibuni bidhaa ambayo haipo kwenye katalogi.
- Usibuni bei.
- Kama bidhaa haipo kwenye katalogi, sema wazi
  kuwa taarifa yake haipo kwa sasa.

4. MAAGIZO
- Kama mteja anataka kuagiza, omba:
  1. Jina la mteja
  2. Namba ya simu
  3. Eneo la delivery
- Usidai kuwa order imekamilika mpaka mfumo
  wa order uthibitishe.

5. MAJIBU
- Jibu kwa Kiswahili rahisi.
- Kuwa friendly na mwenye kusaidia.
- Usitoe majibu marefu bila sababu.
- Usibuni taarifa ambazo hazipo kwenye mfumo.
"""

    else:

        instruction = f"""
You are the AI Sales Assistant for
'{business_name}'.

You are talking to customers through {platform}.

GOAL:
- Help customers understand the business and products.
- Help customers make a buying decision.
- Be polite, concise and useful.
- Always use the real business information
  provided by the system.

{business_info_text}

IMPORTANT RULES:

1. BUSINESS INFORMATION
- If asked for the business location, use the
  location provided above.
- If asked about business hours, use the hours
  provided above.
- If asked about the business type, use the
  information provided above.
- If asked about the business generally, use
  the business description above.

2. PAYMENT INFORMATION
- If asked how to pay or for payment details,
  use the payment information above.
- Never invent payment numbers.
- If payment information is unavailable,
  tell the customer to contact the business.

3. PRODUCTS AND PRICES
- Always use exact catalog prices.
- Never invent products.
- Never invent prices.
- If a product is not in the catalog,
  clearly say that the information is not available.

4. ORDERS
- When a customer wants to order, ask for:
  1. Customer name
  2. Phone number
  3. Delivery location
- Never claim an order was completed unless
  the order system confirms it.

5. RESPONSES
- Keep responses short and helpful.
- Never invent information that is not in the system.
"""

    # -------------------------
    # Gemini model
    # -------------------------

    model_name = os.environ.get(
        "GEMINI_MODEL",
        "gemini-3.5-flash-lite"
    )

    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=instruction,
    )

    # -------------------------
    # Generate response
    # -------------------------

    max_retries = 3

    for attempt in range(max_retries):

        try:

            response = model.generate_content(
                customer_message
            )

            if (
                not response
                or not getattr(response, "text", None)
            ):
                return (
                    "Samahani, AI haikupata jibu kwa sasa. "
                    "Tafadhali jaribu tena."
                )

            return response.text.strip()

        except Exception as e:

            error_text = str(e).lower()

            print(
                f"Gemini error "
                f"(attempt {attempt + 1}/{max_retries}): "
                f"{str(e)}"
            )

            # -------------------------
            # Rate limit / quota
            # -------------------------

            is_rate_limit = any(
                keyword in error_text
                for keyword in [
                    "429",
                    "resource_exhausted",
                    "quota",
                    "rate limit",
                    "too many requests",
                ]
            )

            if is_rate_limit:

                if attempt < max_retries - 1:

                    wait_seconds = 2 ** (attempt + 1)

                    print(
                        f"Gemini rate limit detected. "
                        f"Retrying in {wait_seconds} seconds..."
                    )

                    time.sleep(wait_seconds)

                    continue

                return (
                    "Samahani, AI imefikia kikomo cha matumizi "
                    "kwa sasa. Tafadhali jaribu tena baada ya "
                    "muda mfupi."
                )

            # -------------------------
            # Other Gemini errors
            # -------------------------

            return (
                "Samahani, AI imepata tatizo kwa sasa. "
                "Tafadhali jaribu tena."
            )

    # -------------------------
    # Final fallback
    # -------------------------

    return (
        "Samahani, AI haijaweza kujibu kwa sasa. "
        "Tafadhali jaribu tena."
    )
