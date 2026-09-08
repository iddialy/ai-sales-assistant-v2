import os
from datetime import datetime

import google.generativeai as genai
from models import Merchant

API_KEY = os.environ.get("GEMINI_API_KEY", "")
if API_KEY:
    genai.configure(api_key=API_KEY)


def verify_subscription(merchant: Merchant) -> bool:
    if merchant.subscription_status != "Active" or not merchant.expiry_date:
        return False
    if datetime.utcnow() > merchant.expiry_date:
        return False
    if merchant.message_limit is not None and merchant.messages_used >= merchant.message_limit:
        return False
    return True


def generate_ai_sales_response(merchant: Merchant, customer_message: str, platform: str) -> str:
    if not API_KEY:
        return "Samahani, AI bado haijaunganishwa kwenye server."
    if not verify_subscription(merchant):
        return "SERVICE_INACTIVE"

    products_text = "\n".join(
        [
            f"- {p.product_name}: TSH {p.price:,.0f}. Maelezo: {p.description}"
            for p in merchant.products
        ]
    ) or "Hakuna bidhaa zilizowekwa bado."

    payment_info = merchant.payment_info
    payment_text = (
        f"Lipa Namba: {payment_info.lipa_namba if payment_info else 'Haipo'}\n"
        f"Akaunti ya Bank: {payment_info.bank_account if payment_info else 'Haipo'}\n"
        f"Simu ya Malipo: {payment_info.phone_payment if payment_info else 'Haipo'}"
    )

    if merchant.language_preference == "sw":
        instruction = f"""
Wewe ni Msaidizi wa Mauzo wa duka la '{merchant.business_name}'. Unajibu wateja kwenye {platform} na unalenga kufunga mauzo.

ORODHA YA BIDHAA NA BEI:
{products_text}

MAELEZO YA MALIPO YA DUKA:
{payment_text}

SHERIA:
- Tumia bei halisi za katalogi pekee; usizue taarifa.
- Jibu kwa Kiswahili rahisi na kifupi isipokuwa mteja aombe lugha nyingine.
- Ukipewa oda, omba jina, simu na eneo la delivery.
- Kama taarifa haipo, mwambie mteja utaunganisha na mmiliki.
"""
    else:
        instruction = f"""
You are the AI Sales Assistant for '{merchant.business_name}' on {platform}.
PRODUCTS:
{products_text}
PAYMENT DETAILS:
{payment_text}
Always use exact catalog prices. Ask for customer name, phone and delivery location when ordering. Never invent missing information.
"""

    model = genai.GenerativeModel(
        model_name=os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"),
        system_instruction=instruction,
    )
    return model.generate_content(customer_message).text
