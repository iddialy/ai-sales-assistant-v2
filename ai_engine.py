import os
from datetime import datetime
import google.generativeai as genai
from models import MerchantUser

# Kuweka API Key ya AI kutoka kwenye Environment Variables
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

def verify_subscription(merchant: MerchantUser) -> bool:
    """
    Kipengele cha ulinzi: Kinahakikisha mfanyabiashara 
    amelipia ada ya mwezi kabla AI haijafanya kazi.
    """
    if merchant.subscription_status != "Active":
        return False
    if datetime.now() > merchant.expiry_date:
        merchant.subscription_status = "Expired"
        return False
    return True

def generate_ai_sales_response(merchant: MerchantUser, customer_message: str, platform: str) -> str:
    # 1. Ukaguzi wa Ulinzi wa Malipo ya Mfanyabiashara
    if not verify_subscription(merchant):
        return "SERVICE_INACTIVE"

    # 2. Kupanga Orodha ya Bidhaa zote za Duka hili
    products_text = "\n".join([
        f"- {p.product_name}: TSH {p.price:,.0f}. Maelezo: {p.description}" 
        for p in merchant.products
    ])
    
    # 3. Kusanifu Akili ya AI kulingana na Lugha (Kiswahili / Kiingereza)
    if merchant.language_preference == "sw":
        system_instruction = f"""
        Wewe ni Msaidizi wa Mauzo (Sales Assistant) wa duka la '{merchant.business_name}'.
        Lengo yako kuu ni kujibu maswali ya wateja kwenye mtandao wa {platform} na KUFUNGA MAUZO (Close Sales).
        
        ORODHA YA BIDHAA NA BEI ZETU:
        {products_text}
        
        MAELEZO YA MALIPO YA DUKA HILI:
        Lipa Namba: {merchant.payment_info.lipa_namba or 'Haipo'}
        Akaunti ya Bank: {merchant.payment_info.bank_account or 'Haipo'}
        Simu ya Malipo: {merchant.payment_info.phone_payment or 'Haipo'}
        
        SHERIA ZA KUJIBU MTEJA:
        1. Salimia kwa heshima, changamko na Kiswahili safi cha biashara za Kitanzania.
        2. Tumia bei na sifa halisi zilizopo kwenye katalogi pekee. Usizue au kubadili bei.
        3. Mteja akionyesha nia ya kununua au kutoa oda, mpe njia za malipo hapo juu na mwombe jina lake pamoja na namba ya simu ili kumwandikia oda.
        4. Kama taarifa haipo kwenye katalogi, mjibu kwa heshima kuwa unamuunganisha na mmiliki wa duka mara moja.
        """
    else:
        system_instruction = f"""
        You are an AI Sales Assistant for '{merchant.business_name}' responding on {platform}.
        Your primary goal is to answer customer questions politely and CLOSE SALES.
        
        PRODUCT CATALOG:
        {products_text}
        
        PAYMENT DETAILS:
        Merchant Lipa Namba: {merchant.payment_info.lipa_namba or 'N/A'}
        Bank Account: {merchant.payment_info.bank_account or 'N/A'}
        Mobile Payment: {merchant.payment_info.phone_payment or 'N/A'}
        
        RULES:
        1. Respond politely, professionally, and persuasively.
        2. Always use the exact prices listed in the catalog.
        3. Request the customer's name, phone number, and delivery location when they are ready to order.
        4. If info is missing, inform the customer that you are connecting them to the store owner.
        """

    # 4. Kuita Gemini AI Model
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=system_instruction
    )
    
    response = model.generate_content(customer_message)
    return response.text
