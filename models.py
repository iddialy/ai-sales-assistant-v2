from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import List, Optional

# 1. Model ya Katalogi ya Bidhaa za Mfanyabiashara
class Product(BaseModel):
    product_id: str
    product_name: str
    price: float
    description: str

# 2. Model ya Njia za Kupokea Malipo za Mfanyabiashara (Za kumpa mteja)
class MerchantPaymentInfo(BaseModel):
    lipa_namba: Optional[str] = None
    bank_account: Optional[str] = None
    phone_payment: Optional[str] = None

# 3. Model Kuu ya Mfanyabiashara & Security/Subscription Control
class MerchantUser(BaseModel):
    user_id: str
    business_name: str
    email: EmailStr
    phone_number: str
    language_preference: str = "sw"  # 'sw' (Kiswahili) au 'en' (Kiingereza)
    subscription_status: str = "Pending"  # 'Active', 'Expired', au 'Pending'
    expiry_date: datetime
    payment_info: MerchantPaymentInfo
    products: List[Product] = []

# 4. Model ya Wateja Waliopatikana Mtandaoni (Leads Engine)
class CustomerLead(BaseModel):
    lead_id: str
    merchant_id: str
    platform: str  # Instagram, WhatsApp, Facebook, TikTok
    customer_name: str
    customer_phone: Optional[str] = None
    interest_product: str
    status: str = "New"  # 'New', 'In_Progress', 'Closed'
