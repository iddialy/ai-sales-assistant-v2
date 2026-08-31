from fastapi import FastAPI, HTTPException
from models import MerchantUser, MerchantPaymentInfo, Product
from ai_engine import generate_ai_sales_response
from datetime import datetime, timedelta

# Kutengeneza Server App
app = FastAPI(
    title="AI Sales Assistant SaaS Engine",
    description="Backend API inayosimamia majibu ya AI na ulinzi wa Subscriptions",
    version="1.0.0"
)

# Mfano wa Data ya Mfanyabiashara aliyesajiliwa kwenye Database
# (Kwenye mfumo halisi, data hii itasomwa kutoka PostgreSQL/MongoDB)
sample_merchant = MerchantUser(
    user_id="m_101",
    business_name="Kijiji Cha Magodoro",
    email="info@magodoro.com",
    phone_number="0678156170",
    language_preference="sw", # 'sw' kwa Kiswahili au 'en' kwa Kiingereza
    subscription_status="Active", # Status: Active, Expired, au Pending
    expiry_date=datetime.now() + timedelta(days=30), # Ana siku 30 za huduma
    payment_info=MerchantPaymentInfo(
        lipa_namba="554433", 
        bank_account="CRDB: 0152XXXXX",
        phone_payment="0678156170"
    ),
    products=[
        Product(
            product_id="p1", 
            product_name="Godoro la Afya 6x6", 
            price=250000, 
            description="Zuri kwa afya ya mgongo, shingo na kiuno. Waranti miaka 5."
        ),
        Product(
            product_id="p2", 
            product_name="Godoro Standard 5x6", 
            price=180000, 
            description="Imara, halibonyeki haraka na linadumu sana."
        )
    ]
)

@app.get("/")
async def root():
    """Ukurasa wa kuangalia kama Seva ipo hewani"""
    return {
        "system_status": "Online",
        "message": "AI Sales Assistant SaaS Server is Running!"
    }

@app.post("/webhook/message")
async def handle_incoming_message(merchant_id: str, platform: str, customer_message: str):
    """
    Endpoint inayopokea messages kutoka Instagram, WhatsApp, Facebook na TikTok
    """
    # 1. Hakiki kama mfanyabiashara yupo kwenye mfumo
    if merchant_id != sample_merchant.user_id:
        raise HTTPException(status_code=404, detail="Mfanyabiashara hajapatikana")
        
    # 2. Pata jibu kutoka kwenye AI Engine
    ai_response = generate_ai_sales_response(sample_merchant, customer_message, platform)
    
    # 3. Ukaguzi wa Ulinzi: Kama mfanyabiashara hajalipia ada ya mwezi
    if ai_response == "SERVICE_INACTIVE":
        return {
            "status": "blocked",
            "message": "Huduma imesimama. Tafadhali lipia kifurushi cha mwezi kuendelea kutumia AI."
        }
        
    # 4. Kurudisha jibu lililotengenezwa na AI
    return {
        "status": "success",
        "merchant_id": merchant_id,
        "platform": platform,
        "customer_message": customer_message,
        "ai_reply": ai_response
    }
