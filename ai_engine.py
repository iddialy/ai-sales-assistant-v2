import os
from datetime import datetime

import google.generativeai as genai

from models import Merchant


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

API_KEY = os.environ.get("GEMINI_API_KEY", "")

if API_KEY:
    genai.configure(api_key=API_KEY)

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-1.5-flash"
)


# ============================================================
# SUBSCRIPTION CHECK
# ============================================================

def verify_subscription(merchant: Merchant) -> bool:
    """
    Check whether the merchant is allowed to use the AI.
    """

    # If the project does not have subscription fields yet,
    # allow the AI to continue.
    subscription_status = getattr(
        merchant,
        "subscription_status",
        None
    )

    expiry_date = getattr(
        merchant,
        "expiry_date",
        None
    )

    message_limit = getattr(
        merchant,
        "message_limit",
        None
    )

    messages_used = getattr(
        merchant,
        "messages_used",
        0
    )

    # If subscription information exists, validate it.
    if subscription_status is not None:

        if subscription_status != "Active":
            return False

        if expiry_date:
            if datetime.utcnow() > expiry_date:
                return False

        if (
            message_limit is not None
            and messages_used >= message_limit
        ):
            return False

    return True


# ============================================================
# PRODUCT CATALOG
# ============================================================

def _product_catalog(merchant: Merchant) -> str:
    """
    Build a clean product catalog for the AI.
    """

    products = getattr(
        merchant,
        "products",
        []
    ) or []

    if not products:
        return "Hakuna bidhaa zilizowekwa bado."

    lines = []

    for product in products:

        name = getattr(
            product,
            "product_name",
            "Bidhaa"
        )

        description = getattr(
            product,
            "description",
            ""
        ) or ""

        category = getattr(
            product,
            "category",
            ""
        ) or ""

        # New system uses retail_price.
        # Fallback to old price field for compatibility.
        retail_price = getattr(
            product,
            "retail_price",
            None
        )

        if retail_price is None:
            retail_price = getattr(
                product,
                "price",
                None
            )

        wholesale_price = getattr(
            product,
            "wholesale_price",
            None
        )

        stock_quantity = getattr(
            product,
            "stock_quantity",
            None
        )

        status = getattr(
            product,
            "status",
            None
        )

        line = f"- {name}"

        if category:
            line += f" | Category: {category}"

        if retail_price is not None:
            try:
                line += f" | Bei ya rejareja: TSH {float(retail_price):,.0f}"
            except Exception:
                line += f" | Bei ya rejareja: TSH {retail_price}"

        if wholesale_price is not None:
            try:
                line += f" | Bei ya jumla: TSH {float(wholesale_price):,.0f}"
            except Exception:
                line += f" | Bei ya jumla: TSH {wholesale_price}"

        if stock_quantity is not None:
            line += f" | Stock: {stock_quantity}"

        if status:
            line += f" | Status: {status}"

        if description:
            line += f" | Maelezo: {description}"

        lines.append(line)

    return "\n".join(lines)


# ============================================================
# PAYMENT DETAILS
# ============================================================

def _payment_details(merchant: Merchant) -> str:
    """
    Get merchant payment information.
    """

    payment_number = getattr(
        merchant,
        "payment_number",
        None
    )

    if not payment_number:
        payment_number = getattr(
            merchant,
            "lipa_number",
            None
        )

    if not payment_number:
        payment_number = getattr(
            merchant,
            "payment_phone",
            None
        )

    if not payment_number:
        return "Namba ya malipo haijawekwa bado."

    return str(payment_number)


# ============================================================
# BUSINESS CONTEXT
# ============================================================

def _business_context(merchant: Merchant) -> str:
    """
    Prepare all merchant information for the AI.
    """

    business_name = getattr(
        merchant,
        "business_name",
        None
    ) or getattr(
        merchant,
        "name",
        None
    ) or "Biashara"

    phone = getattr(
        merchant,
        "phone",
        None
    ) or getattr(
        merchant,
        "phone_number",
        None
    ) or ""

    location = getattr(
        merchant,
        "location",
        None
    ) or ""

    business_type = getattr(
        merchant,
        "business_type",
        None
    ) or ""

    working_hours = getattr(
        merchant,
        "working_hours",
        None
    ) or ""

    description = getattr(
        merchant,
        "business_description",
        None
    ) or getattr(
        merchant,
        "description",
        None
    ) or ""

    payment_number = _payment_details(merchant)

    products = _product_catalog(merchant)

    return f"""
JINA LA BIASHARA:
{business_name}

NAMBA YA SIMU:
{phone}

LOCATION:
{location}

AINA YA BIASHARA:
{business_type}

SAHA ZA KAZI:
{working_hours}

MAELEZO YA BIASHARA:
{description}

NAMBA YA MALIPO:
{payment_number}

BIDHAA ZINAZOPATIKANA:
{products}
""".strip()


# ============================================================
# AI SYSTEM INSTRUCTION
# ============================================================

def _system_instruction(
    merchant: Merchant,
    customer_message: str
) -> str:
    """
    Strict AI instructions, especially language behavior.
    """

    business_context = _business_context(merchant)

    return f"""
WEWE NI AI SALES ASSISTANT WA BIASHARA HII.

Tumia taarifa za biashara hapa chini kujibu wateja:

---------------- BUSINESS INFORMATION ----------------

{business_context}

--------------------------------------------------------

MUHIMU SANA - SHERIA YA LUGHA:

1. Mteja akiandika kwa KISWAHILI, jibu kwa KISWAHILI.

2. Mteja akiandika kwa ENGLISH, jibu kwa ENGLISH.

3. USIJIBU KWA KISWAHILI wakati mteja ameuliza kwa ENGLISH.

4. USITAFSIRI swali la English kwenda Kiswahili katika jibu.

5. USITAFSIRI swali la Kiswahili kwenda English katika jibu.

6. Lugha ambayo mteja ametumia ndiyo lugha ya jibu.

7. Kama mteja ametumia lugha zote mbili, tumia lugha iliyo dominant
   kwenye ujumbe wake.

8. Kama ujumbe hauko wazi kuhusu lugha, tumia KISWAHILI.

9. Merchant language preference HAIPASWI kushinda lugha ambayo mteja
   ametumia.

10. Mteja akiendelea na conversation kwa English, endelea English.
    Mteja akibadilisha kwenda Kiswahili, badilisha kwenda Kiswahili.

MFANO:

Customer:
"Hello, do you have shoes?"

Jibu:
"Yes, we have shoes available. Which type or size are you looking for?"

Customer:
"Habari, mna viatu?"

Jibu:
"Habari! Ndiyo, tuna viatu vinavyopatikana. Unatafuta aina au size gani?"

Customer:
"How much is this?"

Jibu:
"That product costs TSH ..."

Customer:
"Hii ni shilingi ngapi?"

Jibu:
"Hii bidhaa ni TSH ..."

--------------------------------------------------------

SHERIA ZA MAUZO:

- Kuwa friendly, professional na helpful.
- Jibu kwa ufupi lakini kwa taarifa muhimu.
- Usitoe taarifa ambayo haipo kwenye business information.
- Usibuni bei.
- Usibuni stock.
- Usibuni bidhaa ambazo hazipo kwenye catalog.
- Kama bidhaa haipo, sema haipo na unaweza kusaidia bidhaa nyingine.
- Kama customer anauliza bei, tumia bei iliyopo kwenye catalog.
- Kama customer anauliza stock, tumia stock iliyopo.
- Kama stock ni 0 au status ni IMEISHA, usiseme bidhaa ipo.
- Kama bidhaa iko available, unaweza kumshawishi customer kufanya order.
- Usimdanganye customer kuhusu delivery, warranty, location au huduma
  ambazo hazijaelezwa kwenye taarifa za biashara.
- Kama payment number ipo na customer anauliza namna ya kulipa,
  mpe payment number hiyo.
- Usibuni payment number.
- Usibuni discount.
- Usibuni wholesale price.
- Usibuni retail price.

--------------------------------------------------------

STYLE:

- Usitumie majibu marefu bila sababu.
- Jibu kama sales assistant halisi.
- Kuwa natural.
- Usianze kila jibu kwa "Karibu".
- Usirudie taarifa ambazo customer tayari anajua.
- Uliza swali la follow-up pale linaposaidia kuuza bidhaa.

--------------------------------------------------------

CUSTOMER MESSAGE:

{customer_message}

Kumbuka:
LUGHA YA CUSTOMER MESSAGE NDIO LUGHA YA JIBU.
"""


# ============================================================
# NORMAL AI RESPONSE
# ============================================================

def generate_ai_sales_response(
    merchant: Merchant,
    customer_message: str
) -> str:
    """
    Generate a normal AI sales response.
    """

    if not API_KEY:
        return (
            "Samahani, AI bado haijaunganishwa kwenye server."
        )

    if not verify_subscription(merchant):
        return "SERVICE_INACTIVE"

    try:
        instruction = _system_instruction(
            merchant,
            customer_message
        )

        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=instruction
        )

        response = model.generate_content(
            customer_message
        )

        text = getattr(
            response,
            "text",
            None
        )

        if text:
            return text.strip()

        return (
            "Samahani, sijapata jibu kwa sasa. "
            "Tafadhali jaribu tena."
        )

    except Exception as exc:
        print(
            f"AI generation error: {exc}"
        )

        return (
            "Samahani, kuna tatizo la muda kwenye AI. "
            "Tafadhali jaribu tena."
        )


# ============================================================
# STREAMING AI RESPONSE
# ============================================================

def generate_ai_sales_response_stream(
    merchant: Merchant,
    customer_message: str
):
    """
    Generate AI response as a stream.
    """

    if not API_KEY:
        yield (
            "Samahani, AI bado haijaunganishwa "
            "kwenye server."
        )
        return

    if not verify_subscription(merchant):
        yield "SERVICE_INACTIVE"
        return

    try:
        instruction = _system_instruction(
            merchant,
            customer_message
        )

        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=instruction
        )

        response = model.generate_content(
            customer_message,
            stream=True
        )

        for chunk in response:

            text = getattr(
                chunk,
                "text",
                None
            )

            if text:
                yield text

    except Exception as exc:
        print(
            f"AI streaming error: {exc}"
        )

        yield (
            "Samahani, kuna tatizo la muda kwenye AI. "
            "Tafadhali jaribu tena."
        )
