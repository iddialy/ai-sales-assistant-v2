import os
from datetime import datetime
import google.generativeai as genai
from models import Merchant

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

def verify_subscription(merchant: Merchant) -> bool:
    if merchant.subscription_status != "Active" or not merchant.expiry_date:
        return False
    if datetime.utcnow() > merchant.expiry_date:
        merchant.subscription_status = "Expired"
        return False
    if merchant.message_limit is not None and merchant.messages_used >= merchant.message_limit:
        return False
    return True

def generate_ai_sales_response(merchant: Merchant, customer_message: str, platform: str) -> str:
    if not verify_subscription(merchant):
        return "SERVICE_INACTIVE"
    products_text = "\n".join([f"- {p.product_name}: TSH {p.price:,.0f}. Maelezo: {p.description}" for p in merchant.products]) or "Hakuna bidhaa zilizowekwa bado."
    if merchant.language_preference == "sw":
        system_instruction = f"""
Wewe ni Msaidizi wa Mauzo wa duka la '{merchant.business_name}'. Unajibu wateja kwenye {platform} na unalenga kufunga mauzo.
ORODHA YA BIDHAA NA BEI:\n{products_text}
MAELEZO YA MALIPO YA DUKA:\nLipa Namba: {merchant.payment_info.lipa_namba if merchant.payment_info else 'Haipo'}\nAkaunti ya Bank: {merchant.payment_info.bank_account if merchant.payment_info else 'Haipo'}\nSimu ya Malipo: {merchant.payment_info.phone_payment if merchant.payment_info else 'Haipo'}
SHERIA: Tumia bei halisi za katalogi pekee; usizue taarifa. Ukipewa oda, omba jina, simu na eneo la delivery. Kama taarifa haipo, mwambie mteja utaunganisha na mmiliki.
"""
    else:
        system_instruction = f"""
You are the AI Sales Assistant for '{merchant.business_name}' on {platform}. Close sales professionally.
PRODUCTS:\n{products_text}
PAYMENT DETAILS: {merchant.payment_info.phone_payment if merchant.payment_info else 'N/A'}
Always use exact catalog prices. Ask for customer name, phone and delivery location when ordering. Never invent missing information.
"""
    model = genai.GenerativeModel(model_name=os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"), system_instruction=system_instruction)
    return model.generate_content(customer_message).text
