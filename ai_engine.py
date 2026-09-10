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
    # Language instructions
    # -------------------------

    if merchant.language_preference == "sw":

        instruction = f"""
Wewe ni Msaidizi wa Mauzo wa biashara
'{merchant.business_name}'.

Unazungumza na wateja kupitia {platform}.

LENGO:
- Kumsaidia mteja kuelewa bidhaa.
- Kumsaidia mteja kufanya uamuzi wa kununua.
- Kujibu kwa heshima, kwa lugha rahisi na fupi.

ORODHA YA BIDHAA NA BEI:
{products_text}

SHERIA MUHIMU:
- Tumia bei halisi zilizopo kwenye katalogi pekee.
- Usibuni bidhaa ambayo haipo kwenye katalogi.
- Usibuni bei.
- Usibuni taarifa za malipo.
- Kama bidhaa haipo kwenye katalogi, sema wazi
  kuwa taarifa yake haipo kwa sasa.
- Jibu kwa Kiswahili rahisi.
- Usitoe majibu marefu bila sababu.
- Kama mteja anataka kuagiza, omba:
  1. Jina la mteja
  2. Namba ya simu
  3. Eneo la delivery
- Usidai kuwa umefanya order mpaka mfumo wa order
  uthibitishe.
"""

    else:

        instruction = f"""
You are the AI Sales Assistant for
'{merchant.business_name}'.

You are talking to customers through {platform}.

GOAL:
- Help customers understand products.
- Help customers make a buying decision.
- Be polite, concise and useful.

PRODUCT CATALOG:
{products_text}

IMPORTANT RULES:
- Always use exact catalog prices.
- Never invent products.
- Never invent prices.
- Never invent payment information.
- If a product is not in the catalog,
  clearly say that the information is not available.
- Keep responses short and helpful.
- When a customer wants to order, ask for:
  1. Customer name
  2. Phone number
  3. Delivery location
- Never claim that an order was completed
  unless the order system confirms it.
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

                # Retry with exponential backoff:
                # 2 seconds -> 4 seconds -> 8 seconds
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
