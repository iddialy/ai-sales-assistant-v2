import os

import google.generativeai as genai
from models import Merchant

API_KEY = os.environ.get("GEMINI_API_KEY", "")

if API_KEY:
    genai.configure(api_key=API_KEY)


def generate_ai_sales_response(
    merchant: Merchant,
    customer_message: str,
    platform: str
) -> str:

    if not API_KEY:
        return "Samahani, AI bado haijaunganishwa kwenye server."

    products_text = "\n".join(
        [
            f"- {p.product_name}: TSH {p.price:,.0f}. Maelezo: {p.description}"
            for p in merchant.products
        ]
    ) or "Hakuna bidhaa zilizowekwa bado."

    if merchant.language_preference == "sw":

        instruction = f"""
Wewe ni Msaidizi wa Mauzo wa duka la
'{merchant.business_name}'.

Unajibu wateja kwenye {platform} na unalenga
kusaidia kufunga mauzo.

ORODHA YA BIDHAA NA BEI:
{products_text}

SHERIA:
- Tumia bei halisi za katalogi pekee.
- Usizue bidhaa au bei ambazo hazipo.
- Jibu kwa Kiswahili rahisi na kifupi.
- Kama mteja anauliza kuhusu bidhaa, tumia taarifa
  kutoka kwenye katalogi.
- Kama bidhaa haipo kwenye katalogi, sema
  kuwa taarifa hiyo haipo kwa sasa.
- Ukipewa oda, omba jina, simu na eneo la delivery.
- Usizue taarifa za malipo.
"""

    else:

        instruction = f"""
You are the AI Sales Assistant for
'{merchant.business_name}' on {platform}.

PRODUCTS:
{products_text}

RULES:
- Always use exact catalog prices.
- Never invent products, prices or missing information.
- Keep answers short and helpful.
- When a customer wants to order, ask for
  customer name, phone number and delivery location.
"""


    model_name = os.environ.get(
        "GEMINI_MODEL",
        "gemini-2.5-flash"
    )

    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=instruction,
    )

    try:

        response = model.generate_content(
            customer_message
        )

        if not response or not response.text:
            return "Samahani, AI haikupata jibu kwa sasa."

        return response.text.strip()

    except Exception as e:

        print("Gemini error:", str(e))

        return (
            "Samahani, AI imepata tatizo kwa sasa. "
            "Tafadhali jaribu tena."
        )
