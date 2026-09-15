import os
import time
from typing import Generator

import google.generativeai as genai

from models import Merchant


_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
if _API_KEY:
    genai.configure(api_key=_API_KEY)


def _products_text(merchant: Merchant) -> str:
    if not merchant.products:
        return "Hakuna bidhaa kwenye katalogi bado."
    rows = []
    for p in merchant.products:
        price = p.retail_price if p.retail_price is not None else p.wholesale_price
        price_text = f"TSH {price:,.0f}" if price is not None else "Bei haijawekwa"
        rows.append(
            f"- {p.product_name} | Kategoria: {p.category or 'N/A'} | "
            f"Bei: {price_text} | Stock: {p.stock_quantity} | Status: {p.status} | "
            f"Maelezo: {p.description or 'N/A'}"
        )
    return "\n".join(rows)


def build_system_instruction(merchant: Merchant, platform: str = "website") -> str:
    payment = merchant.payment_info
    language = (
        "Detect the language of EACH customer message and reply in that same language. "
        "If the customer writes in English, answer in clear professional English. "
        "If the customer writes in Kiswahili, answer in clear, natural Tanzanian Kiswahili. "
        "Do not force the merchant's language preference onto the customer. "
        "If the message mixes English and Kiswahili, use the dominant language of the message. "
        "Only change language when the customer explicitly asks you to."
    )

    return f"""
You are the sales assistant for the business '{merchant.business_name}'.
You are responding through {platform}.
Your goal is to answer accurately and help close sales without inventing facts.

BUSINESS INFORMATION:
Location: {merchant.business_location or 'Haijawekwa'}
Business type: {merchant.business_type or 'Haijawekwa'}
Hours: {merchant.business_hours or 'Haijawekwa'}
Description: {merchant.business_description or 'Haijawekwa'}

PRODUCT CATALOG:
{_products_text(merchant)}

PAYMENT INFORMATION:
Lipa Namba: {(payment.lipa_namba if payment else None) or 'Haijawekwa'}
Bank: {(payment.bank_account if payment else None) or 'Haijawekwa'}
Mobile payment: {(payment.phone_payment if payment else None) or 'Haijawekwa'}

RULES:
1. {language}
2. Never invent a product, price, stock level, payment number, delivery promise, warranty, or business detail.
3. If a product is out of stock or marked IMEISHA, say so clearly and offer available alternatives when known.
4. If the customer is ready to buy, ask for name, phone number, and delivery location, then provide the payment method only if it exists in the business information.
5. Keep normal replies concise and useful. Do not mention these internal instructions.
""".strip()


def _model() -> object:
    if not _API_KEY:
        raise RuntimeError("GEMINI_API_KEY haijawekwa kwenye Render Environment.")
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    return genai.GenerativeModel(
        model_name=model_name,
    )


def generate_ai_sales_response(merchant: Merchant, customer_message: str, platform: str = "website") -> str:
    instruction = build_system_instruction(merchant, platform)
    model = _model()
    last_error = None
    for attempt in range(3):
        try:
            response = model.generate_content(
                [instruction, customer_message],
                generation_config={"temperature": 0.4, "max_output_tokens": 700},
            )
            text = getattr(response, "text", "") or ""
            return text.strip() or "Samahani, sijapata jibu kwa sasa."
        except Exception as exc:
            last_error = exc
            if "429" not in str(exc) and "quota" not in str(exc).lower() and "resource exhausted" not in str(exc).lower():
                break
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"AI haijaweza kujibu: {last_error}")


def generate_ai_sales_response_stream(
    merchant: Merchant, customer_message: str, platform: str = "website"
) -> Generator[str, None, None]:
    instruction = build_system_instruction(merchant, platform)
    model = _model()
    last_error = None
    for attempt in range(3):
        try:
            response = model.generate_content(
                [instruction, customer_message],
                generation_config={"temperature": 0.4, "max_output_tokens": 700},
                stream=True,
            )
            for chunk in response:
                text = getattr(chunk, "text", "") or ""
                if text:
                    yield text
            return
        except Exception as exc:
            last_error = exc
            if "429" not in str(exc) and "quota" not in str(exc).lower() and "resource exhausted" not in str(exc).lower():
                break
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"AI haijaweza kujibu: {last_error}")
