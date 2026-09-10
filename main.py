import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from ai_engine import generate_ai_sales_response
from models import Base, Merchant, MerchantPaymentInfo, Product, SessionLocal, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Sales Assistant Tanzania", version="5.1.0")

cors_raw = os.getenv("CORS_ORIGINS", "https://iddialy.github.io")
origins = [x.strip() for x in cors_raw.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

password_hash = PasswordHash.recommended()
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_RENDER")
JWT_ALG = "HS256"



class SignupIn(BaseModel):
    business_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone_number: str
    password: str = Field(min_length=8, max_length=128)
    language_preference: str = "sw"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProductIn(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    price: float = Field(ge=0)
    description: str = ""



class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    platform: str = "web"


def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def token_for(merchant: Merchant) -> str:
    return jwt.encode(
        {"sub": merchant.user_id, "exp": datetime.utcnow() + timedelta(days=7)},
        JWT_SECRET,
        algorithm=JWT_ALG,
    )


def current_merchant(
    authorization: Optional[str] = Header(None),
    session: Session = Depends(db),
) -> Merchant:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Login required")
    try:
        payload = jwt.decode(authorization.split(" ", 1)[1], JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session ime-expire. Ingia tena.")
    merchant_id = payload.get("sub")
    merchant = session.get(Merchant, merchant_id)
    if not merchant:
        raise HTTPException(401, "Account haipo kwenye database. Tafadhali fungua account tena.")
    return merchant


def normalize_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("0"):
        digits = "255" + digits[1:]
    if not digits.startswith("255") or len(digits) != 12:
        raise HTTPException(400, "Tafadhali tumia namba ya Tanzania, mfano 0712345678")
    return digits


def public_merchant(merchant: Merchant):
    return {
        "user_id": merchant.user_id,
        "business_name": merchant.business_name,
        "email": merchant.email,
        "phone_number": merchant.phone_number,
        "plan_code": merchant.plan_code,
        "subscription_status": merchant.subscription_status,
        "expiry_date": merchant.expiry_date.isoformat() if merchant.expiry_date else None,
        "message_limit": merchant.message_limit,
        "messages_used": merchant.messages_used,
    }


def activate_subscription(payment: Payment, merchant: Merchant, now: datetime):
    plan = PLANS[payment.plan_code]
    base = (
        merchant.expiry_date
        if merchant.subscription_status == "Active"
        and merchant.expiry_date
        and merchant.expiry_date > now
        else now
    )
    merchant.subscription_status = "Active"
    merchant.plan_code = payment.plan_code
    merchant.message_limit = plan["limit"]
    merchant.messages_used = 0
    merchant.expiry_date = base + timedelta(days=30)


def verify_webhook_signature(raw_body: bytes, signature_header: Optional[str]) -> bool:
    if not MALIPO_WEBHOOK_SECRET:
        return False
    provided = (signature_header or "").strip()
    if provided.startswith("sha256="):
        provided = provided[len("sha256="):]
    expected = hmac.new(
        MALIPO_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(provided, expected)


@app.get("/")
def root():
    return {
        "system_status": "Online",
        "service": "AI Sales Assistant Tanzania",
        "version": "5.1.0",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "database": "configured" if os.getenv("DATABASE_URL") else "sqlite-fallback",
    }


@app.post("/auth/signup")
def signup(data: SignupIn, session: Session = Depends(db)):
    email = str(data.email).lower().strip()
    if session.query(Merchant).filter(Merchant.email == email).first():
        raise HTTPException(409, "Email tayari imesajiliwa. Tumia Login.")

    merchant = Merchant(
        user_id="m_" + uuid.uuid4().hex[:16],
        business_name=data.business_name.strip(),
        email=email,
        phone_number=normalize_phone(data.phone_number),
        password_hash=password_hash.hash(data.password),
        language_preference=data.language_preference,
    )
    merchant.payment_info = MerchantPaymentInfo(phone_payment=merchant.phone_number)
    session.add(merchant)
    session.commit()
    session.refresh(merchant)
    return {"token": token_for(merchant), "merchant": public_merchant(merchant)}


@app.post("/auth/login")
def login(data: LoginIn, session: Session = Depends(db)):
    email = str(data.email).lower().strip()
    merchant = session.query(Merchant).filter(Merchant.email == email).first()
    if not merchant:
        raise HTTPException(401, "Account haipo. Hakikisha email au fungua Sign Up.")
    try:
        valid = password_hash.verify(data.password, merchant.password_hash)
    except Exception:
        valid = False
    if not valid:
        raise HTTPException(401, "Password si sahihi.")
    return {"token": token_for(merchant), "merchant": public_merchant(merchant)}


@app.get("/auth/me")
def me(merchant: Merchant = Depends(current_merchant), session: Session = Depends(db)):
    session.refresh(merchant)
    if (
        merchant.subscription_status == "Active"
        and merchant.expiry_date
        and datetime.utcnow() >= merchant.expiry_date
    ):
        merchant.subscription_status = "Expired"
        session.commit()
    return public_merchant(merchant)


@app.post("/products")
def add_product(
    data: ProductIn,
    merchant: Merchant = Depends(current_merchant),
    session: Session = Depends(db),
):
    product = Product(
        product_id="p_" + uuid.uuid4().hex[:16],
        merchant_id=merchant.user_id,
        product_name=data.product_name.strip(),
        price=data.price,
        description=data.description.strip(),
    )
    session.add(product)
    session.commit()
    return {"status": "success", "product_id": product.product_id}


@app.get("/products")
def products(merchant: Merchant = Depends(current_merchant)):
    return [
        {
            "product_id": p.product_id,
            "product_name": p.product_name,
            "price": p.price,
            "description": p.description,
        }
        for p in merchant.products
    ]


@app.post("/chat")
def chat(
    data: ChatIn,
    merchant: Merchant = Depends(current_merchant),
    session: Session = Depends(db),
):
    # Payments are temporarily disabled. Every authenticated merchant can test the AI.
    reply = generate_ai_sales_response(merchant, data.message, data.platform)
    if reply == "SERVICE_INACTIVE":
        return {
            "status": "blocked",
            "message": "AI haijaweza kuanza. Hakikisha GEMINI_API_KEY imewekwa kwenye Render.",
        }
    merchant.messages_used += 1
    session.commit()
    return {
        "status": "success",
        "ai_reply": reply,
        "messages_used": merchant.messages_used,
        "message_limit": None,
    }


@app.post("/webhook/message")
def incoming(
    merchant_id: str,
    platform: str,
    customer_message: str,
    x_webhook_secret: Optional[str] = Header(None),
    session: Session = Depends(db),
):
    secret = os.getenv("WEBHOOK_SECRET", "")
    if secret and not hmac.compare_digest(x_webhook_secret or "", secret):
        raise HTTPException(401, "Invalid webhook secret")
    merchant = session.get(Merchant, merchant_id)
    if not merchant:
        raise HTTPException(404, "Mfanyabiashara hajapatikana")
    reply = generate_ai_sales_response(merchant, customer_message, platform)
    if reply == "SERVICE_INACTIVE":
        return {"status": "blocked", "message": "AI haijaweza kuanza. Hakikisha GEMINI_API_KEY imewekwa."}
    merchant.messages_used += 1
    session.commit()
    return {"status": "success", "merchant_id": merchant_id, "ai_reply": reply}
