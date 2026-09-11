import os
import time
from typing import Generator

import google.generativeai as genai
from models import Merchant


# =========================================================
# GEMINI CONFIGURATION
# =========================================================

API_KEY = os.environ.get(
    "GEMINI_API_KEY",
    ""
)

if API_KEY:
    genai.configure(
        api_key=API_KEY
    )


# =========================================================
# BUSINESS INFORMATION
# =========================================================

def _get_business_information(
    merchant: Merchant
) -> dict:

    business_name = (
        merchant.business_name
        or "Haijawekwa"
    )

    business_phone = (
        merchant.phone_number
        or "Haijawekwa"
    )

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

    # =====================================================
    # PAYMENT INFORMATION
    # =====================================================

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

    # =====================================================
    # PRODUCT CATALOG
    # =====================================================

    product_lines = []

    for p in merchant.products:

        category = (
            p.category
            if p.category
            else "Haijawekwa"
        )

        wholesale_price = (
            f"TSH {p.wholesale_price:,.0f}"
            if p.wholesale_price is not None
            else "Haijawekwa"
        )

        retail_price = (
            f"TSH {p.retail_price:,.0f}"
            if p.retail_price is not None
            else "Haijawekwa"
        )

        stock_quantity = (
            p.stock_quantity
            if p.stock_quantity is not None
            else 0
        )

        status = (
            p.status
            if p.status
            else (
                "IPO"
                if stock_quantity > 0
                else "IMEISHA"
            )
        )

        image_available = (
            "NDIYO"
            if p.image_url
            else "HAPANA"
        )

        product_lines.append(
            f"""
- Jina: {p.product_name}
  Category: {category}
  Bei ya jumla: {wholesale_price}
  Bei ya rejareja: {retail_price}
  Stock: {stock_quantity}
  Status: {status}
  Picha ipo: {image_available}
  Maelezo: {p.description}
""".strip()
        )

    products_text = "\n".join(
        product_lines
    )

    if not products_text:

        products_text = (
            "Hakuna bidhaa zilizowekwa bado."
        )

    return {

        "business_name":
            business_name,

        "business_phone":
            business_phone,

        "business_location":
            business_location,

        "business_type":
            business_type,

        "business_hours":
            business_hours,

        "business_description":
            business_description,

        "lipa_namba":
            lipa_namba,

        "phone_payment":
            phone_payment,

        "bank_account":
            bank_account,

        "products_text":
            products_text,
    }


# =========================================================
# SYSTEM INSTRUCTION
# =========================================================

def _build_instruction(
    merchant: Merchant,
    platform: str
) -> str:

    info = _get_business_information(
        merchant
    )

    business_name = (
        info["business_name"]
    )

    business_info_text = f"""
TAARIFA ZA BIASHARA:

Jina la biashara:
{business_name}

Namba ya simu ya biashara:
{info["business_phone"]}

Location ya biashara:
{info["business_location"]}

Aina ya biashara:
{info["business_type"]}

Saa za kazi:
{info["business_hours"]}

Maelezo ya biashara:
{info["business_description"]}


TAARIFA ZA MALIPO:

Lipa Namba:
{info["lipa_namba"]}

Namba ya simu ya malipo:
{info["phone_payment"]}

Bank Account:
{info["bank_account"]}


ORODHA YA BIDHAA:

{info["products_text"]}
"""

    # =====================================================
    # KISWAHILI
    # =====================================================

    if merchant.language_preference == "sw":

        return f"""
Wewe ni Msaidizi wa Mauzo wa biashara
'{business_name}'.

Unazungumza na wateja kupitia {platform}.

LENGO:

- Kumsaidia mteja kuelewa biashara na bidhaa.
- Kumsaidia mteja kufanya uamuzi wa kununua.
- Kujibu kwa heshima.
- Kujibu kwa Kiswahili rahisi.
- Kujibu kwa ufupi na moja kwa moja.
- Kutumia taarifa halisi zilizopo kwenye mfumo.

{business_info_text}


=====================================================
SHERIA ZA BIDHAA
=====================================================

1. PRODUCT NAME

Tumia jina halisi la bidhaa lililopo
kwenye katalogi.

Usibuni bidhaa ambayo haipo.


2. CATEGORY

Kama mteja akiuliza bidhaa za category
fulani, tumia category iliyowekwa kwenye
katalogi.

Mfano:

"Mna viatu?"

Tafuta bidhaa ambazo category yake ni
Viatu.


3. BEI YA REJAREJA

Kama mteja akiuliza:

- "Bei gani?"
- "Inauzwa sh ngapi?"
- "Bei yake ni kiasi gani?"
- "How much?"

Kwa kawaida tumia:

BEI YA REJAREJA.


4. BEI YA JUMLA

Kama mteja akiuliza:

- "Bei ya jumla?"
- "Wholesale price?"
- "Nikichukua nyingi ni bei gani?"

Tumia:

BEI YA JUMLA.


5. STOCK

Kama mteja akiuliza:

- "Ipo?"
- "Mna stock?"
- "Bado ipo?"
- "Zipo ngapi?"

Tumia STOCK QUANTITY na STATUS.

Mfano:

Stock 10 + Status IPO:

"Ndiyo, ipo. Kwa sasa tuna stock ya 10."

Stock 0 + Status IMEISHA:

"Samahani, bidhaa hii imeisha kwa sasa."


6. PRODUCT STATUS

Status zinazotumika ni:

IPO
IMEISHA

Usibuni status nyingine.

Kama status ni IMEISHA,
usiambie mteja kuwa bidhaa ipo.

Kama stock ni 0,
ichukulie bidhaa kama IMEISHA.


7. USIBUNI TAARIFA

Usibuni:

- Bei
- Stock
- Category
- Product
- Payment number
- Location
- Business hours

Tumia taarifa zilizo kwenye mfumo pekee.


=====================================================
BUSINESS INFORMATION
=====================================================

Kama mteja akiuliza location,
tumia location ya biashara hapo juu.

Kama mteja akiuliza saa za kazi,
tumia saa za kazi hapo juu.

Kama mteja akiuliza aina ya biashara,
tumia business type hapo juu.

Kama mteja akiuliza kuhusu biashara kwa ujumla,
tumia business description.


=====================================================
PAYMENT INFORMATION
=====================================================

Kama mteja akiuliza:

- "Nalipaje?"
- "Lipa namba ni ipi?"
- "Namba ya malipo ni ipi?"

Tumia taarifa halisi za malipo.

Usibuni namba ya malipo.

Kama hakuna taarifa ya malipo:

"Tafadhali wasiliana na biashara kwa taarifa
sahihi za malipo."


=====================================================
ORDERS
=====================================================

Kama mteja anataka kuagiza,
omba:

1. Jina la mteja
2. Namba ya simu
3. Eneo la delivery

Usidai kuwa order imekamilika mpaka
mfumo wa order uthibitishe.


=====================================================
STYLE
=====================================================

- Kuwa friendly.
- Kuwa professional.
- Jibu swali moja kwa moja.
- Usirudie taarifa zisizoombwa.
- Usitoe majibu marefu bila sababu.
- Usibuni taarifa.
"""


    # =====================================================
    # ENGLISH
    # =====================================================

    return f"""
You are the AI Sales Assistant for
'{business_name}'.

You are talking to customers through {platform}.

GOAL:

- Help customers understand the business.
- Help customers understand products.
- Help customers make buying decisions.
- Be polite and concise.
- Always use real information from the system.

{business_info_text}


=====================================================
PRODUCT RULES
=====================================================

PRODUCT NAME:

Use only products in the catalog.

Never invent products.


CATEGORY:

Use the product category stored in the catalog.

If the customer asks for products in a category,
return matching products from the catalog.


RETAIL PRICE:

When a customer asks for the normal product price,
use the RETAIL PRICE.


WHOLESALE PRICE:

When a customer specifically asks for wholesale,
bulk pricing or wholesale price,
use the WHOLESALE PRICE.


STOCK:

When the customer asks whether a product is available,
use STOCK QUANTITY and STATUS.

If stock is 0,
the product should be treated as unavailable.


STATUS:

Valid statuses are:

IPO
IMEISHA

Never invent other statuses.


NEVER INVENT:

- Products
- Prices
- Stock
- Categories
- Payment numbers
- Business information


=====================================================
PAYMENTS
=====================================================

Use only the payment information provided.

Never invent payment numbers.

If payment information is unavailable,
tell the customer to contact the business.


=====================================================
ORDERS
=====================================================

When the customer wants to order,
ask for:

1. Customer name
2. Phone number
3. Delivery location

Never claim an order was completed unless
the order system confirms it.


=====================================================
STYLE
=====================================================

- Be friendly.
- Be professional.
- Keep responses concise.
- Answer the current question directly.
- Do not repeat unnecessary information.
- Never invent information.
"""


# =========================================================
# GEMINI MODEL
# =========================================================

def _get_model(
    instruction: str
):

    model_name = os.environ.get(
        "GEMINI_MODEL",
        "gemini-3.5-flash-lite"
    )

    return genai.GenerativeModel(
        model_name=model_name,
        system_instruction=instruction,
    )


# =========================================================
# RATE LIMIT CHECK
# =========================================================

def _is_rate_limit_error(
    error_text: str
) -> bool:

    error_text = (
        error_text.lower()
    )

    return any(
        keyword in error_text
        for keyword in [
            "429",
            "resource_exhausted",
            "quota",
            "rate limit",
            "too many requests",
        ]
    )


# =========================================================
# NORMAL AI RESPONSE
# =========================================================

def generate_ai_sales_response(
    merchant: Merchant,
    customer_message: str,
    platform: str
) -> str:

    if not API_KEY:

        return (
            "Samahani, AI bado haijaunganishwa kwenye server. "
            "Tafadhali wasiliana na support."
        )

    instruction = _build_instruction(
        merchant,
        platform
    )

    model = _get_model(
        instruction
    )

    max_retries = 3

    for attempt in range(
        max_retries
    ):

        try:

            response = (
                model.generate_content(
                    customer_message
                )
            )

            if (
                not response
                or not getattr(
                    response,
                    "text",
                    None
                )
            ):

                return (
                    "Samahani, AI haikupata jibu kwa sasa. "
                    "Tafadhali jaribu tena."
                )

            return (
                response.text.strip()
            )

        except Exception as e:

            error_text = str(e)

            print(
                f"Gemini error "
                f"(attempt {attempt + 1}/{max_retries}): "
                f"{error_text}"
            )

            if _is_rate_limit_error(
                error_text
            ):

                if attempt < max_retries - 1:

                    wait_seconds = (
                        2 ** (attempt + 1)
                    )

                    print(
                        "Gemini rate limit detected. "
                        f"Retrying in {wait_seconds} seconds..."
                    )

                    time.sleep(
                        wait_seconds
                    )

                    continue

                return (
                    "Samahani, AI imefikia kikomo cha matumizi "
                    "kwa sasa. Tafadhali jaribu tena baada ya "
                    "muda mfupi."
                )

            return (
                "Samahani, AI imepata tatizo kwa sasa. "
                "Tafadhali jaribu tena."
            )

    return (
        "Samahani, AI haijaweza kujibu kwa sasa. "
        "Tafadhali jaribu tena."
    )


# =========================================================
# REAL STREAMING AI RESPONSE
# =========================================================

def generate_ai_sales_response_stream(
    merchant: Merchant,
    customer_message: str,
    platform: str
) -> Generator[str, None, None]:

    if not API_KEY:

        yield (
            "Samahani, AI bado haijaunganishwa kwenye server. "
            "Tafadhali wasiliana na support."
        )

        return

    instruction = _build_instruction(
        merchant,
        platform
    )

    model = _get_model(
        instruction
    )

    max_retries = 3

    for attempt in range(
        max_retries
    ):

        try:

            print(
                "Starting Gemini streaming response..."
            )

            response = (
                model.generate_content(
                    customer_message,
                    stream=True
                )
            )

            got_text = False

            for chunk in response:

                try:

                    text = getattr(
                        chunk,
                        "text",
                        ""
                    )

                except Exception:

                    text = ""

                if text:

                    got_text = True

                    yield text

            if got_text:

                print(
                    "Gemini streaming completed."
                )

                return

            yield (
                "Samahani, AI haikupata jibu kwa sasa. "
                "Tafadhali jaribu tena."
            )

            return

        except Exception as e:

            error_text = str(e)

            print(
                f"Gemini streaming error "
                f"(attempt {attempt + 1}/{max_retries}): "
                f"{error_text}"
            )

            if _is_rate_limit_error(
                error_text
            ):

                if attempt < max_retries - 1:

                    wait_seconds = (
                        2 ** (attempt + 1)
                    )

                    print(
                        "Gemini rate limit detected. "
                        f"Retrying in {wait_seconds} seconds..."
                    )

                    time.sleep(
                        wait_seconds
                    )

                    continue

                yield (
                    "Samahani, AI imefikia kikomo cha matumizi "
                    "kwa sasa. Tafadhali jaribu tena baada ya "
                    "muda mfupi."
                )

                return

            yield (
                "Samahani, AI imepata tatizo kwa sasa. "
                "Tafadhali jaribu tena."
            )

            return

    yield (
        "Samahani, AI haijaweza kujibu kwa sasa. "
        "Tafadhali jaribu tena."
    )
