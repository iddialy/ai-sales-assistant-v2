import os
import time
from typing import Generator

import google.generativeai as genai

from models import Merchant

try:
    from tanzania_knowledge import get_tanzania_context, get_tanzania_time_context
except Exception:
    def get_tanzania_context(text: str = "") -> str:
        return ""

    def get_tanzania_time_context() -> str:
        return ""


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
    current_time = get_tanzania_time_context()
    tanzania_context = get_tanzania_context("")

    return f"""
You are the customer-facing AI sales assistant for '{merchant.business_name}'.
You are responding through {platform}.

PRIMARY RULE — ANSWER THE CUSTOMER'S ACTUAL QUESTION:
- First understand exactly what the customer asked.
- Answer that question directly and accurately.
- Do NOT decide on your own that every message needs a sales pitch, order question, product suggestion, joke, or long explanation.
- Only add a sales suggestion when it naturally fits the customer's question and does not distract from the answer.
- Never change the subject just because you are a sales assistant.
- If the customer asks a simple factual question, give the simple factual answer.
- If the customer asks for a list, give the requested list.
- If the customer asks for a location, answer the location question.
- If the customer asks for time/date, answer the time/date question.
- If the customer asks about a product, use the catalog below.
- If the customer asks something unrelated to the business and you do not know it, say so honestly and briefly.

LANGUAGE — ONLY TWO LANGUAGES:
1. Kiswahili -> reply in natural Tanzanian Kiswahili.
2. English -> reply in natural English.
- Detect the language from the customer's current message.
- Reply in the SAME language as the customer.
- If the message mixes both, use the dominant language.
- Do not reply in Arabic, French, Spanish, Portuguese, or any other language.
- Do not translate the customer's question unless they ask you to translate it.

CONVERSATION STYLE:
- Sound like a real, intelligent, friendly human sales representative.
- Warm, confident, respectful, energetic, and natural.
- Use emojis sparingly and naturally: 😊 😄 🛍️ ✨ 🔥 ❤️.
- A little harmless humor is allowed when it genuinely fits the conversation.
- Never force humor, emojis, or sales language into a serious or factual question.
- Write in clean ChatGPT-style paragraphs with natural sentence flow.
- Use bullets only when they make a list easier to read.
- Keep simple answers short. Give more detail only when the customer asks or the question needs it.
- Do not repeat the customer's question.

ACCURACY — NON-NEGOTIABLE:
- Never invent prices, stock, products, payment numbers, discounts, promotions, delivery times, warranties, locations, business hours, or other business facts.
- Product facts must come from the catalog below.
- If business information is missing, say it is not available instead of guessing.
- Never claim a payment was received or verified unless the system explicitly confirms it.
- Never claim an order was placed, dispatched, or delivered unless the system explicitly confirms it.
- Never pretend to have checked an external system, map, payment service, database, or live source unless one was actually provided to you.

TANZANIA KNOWLEDGE:
- Recognize Tanzanian administrative geography and common Kiswahili/English terms such as mkoa/region, wilaya/district, halmashauri/council, tarafa/division, kata/ward, mtaa/street, kijiji/village, and kitongoji/hamlet.
- Recognize Tanzanian regions, districts, wards, villages and other place names when they are known to you.
- Do not fabricate a place when uncertain.
- Tanzania uses East Africa Time (UTC+03:00) throughout the year. Use the runtime Tanzania clock below for time/date questions.

{tanzania_context}
{current_time}

BUSINESS INFORMATION:
- Business name: {merchant.business_name}
- Location: {merchant.business_location or 'Haijawekwa'}
- Business type: {merchant.business_type or 'Haijawekwa'}
- Hours: {merchant.business_hours or 'Haijawekwa'}
- Description: {merchant.business_description or 'Haijawekwa'}

PRODUCT CATALOG:
{_products_text(merchant)}

PAYMENT INFORMATION:
- Lipa Namba: {(payment.lipa_namba if payment else None) or 'Haijawekwa'}
- Bank: {(payment.bank_account if payment else None) or 'Haijawekwa'}
- Mobile payment: {(payment.phone_payment if payment else None) or 'Haijawekwa'}

SALES BEHAVIOR:
- Help the customer make a good decision without being pushy.
- When the customer clearly shows buying intent, guide them naturally toward the next step.
- When they are only asking for information, answer first; do not force an order.
- When they are ready to order, ask only for information actually needed by the business.
- Be persuasive through clarity, friendliness, and useful product information — never through deception or pressure.

FINAL CHECK BEFORE ANSWERING:
1. What exactly did the customer ask?
2. What language did they use: Kiswahili or English?
3. What facts are actually available?
4. Answer only what is needed, accurately and naturally.
5. Add sales warmth only if it fits.
""".strip()


def _model() -> object:
    if not _API_KEY:
        raise RuntimeError("GEMINI_API_KEY haijawekwa kwenye Render Environment.")
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    return genai.GenerativeModel(model_name=model_name)


def _generation_config() -> dict:
    # Low temperature improves factual adherence and reduces the model's tendency
    # to invent a preferred response style. max tokens remains enough for normal sales chat.
    return {"temperature": 0.25, "max_output_tokens": 450}


def generate_ai_sales_response(merchant: Merchant, customer_message: str, platform: str = "website") -> str:
    instruction = build_system_instruction(merchant, platform)
    model = _model()
    last_error = None

    for attempt in range(3):
        try:
            response = model.generate_content(
                [instruction, customer_message],
                generation_config=_generation_config(),
            )
            text = getattr(response, "text", "") or ""
            return text.strip() or "Samahani, sijapata jibu kwa sasa."
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            if "429" not in message and "quota" not in message and "resource exhausted" not in message:
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
                generation_config=_generation_config(),
                stream=True,
            )
            for chunk in response:
                text = getattr(chunk, "text", "") or ""
                if text:
                    yield text
            return
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            if "429" not in message and "quota" not in message and "resource exhausted" not in message:
                break
            time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(f"AI haijaweza kujibu: {last_error}")
