import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from ai_engine import generate_ai_sales_response
from models import Base, Merchant, MerchantPaymentInfo, Payment, Product, SessionLocal, engine

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
MALIPO_BASE = os.getenv("MALIPO_BASE_URL", "https://core-prod.malipopay.co.tz").rstrip("/")
MALIPO_TOKEN = os.getenv("MALIPOPAY_API_TOKEN", "")
MALIPO_WEBHOOK_SECRET = os.getenv("MALIPOPAY_WEBHOOK_SECRET", "")

PLANS = {
    "starter": {"name": "Starter", "amount": 35000, "limit": 1000},
    "business": {"name": "Business", "amount": 75000, "limit": None},
}


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


class PaymentIn(BaseModel):
    plan_code: str
    phone: str


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
        "malipopay_api_key": bool(MALIPO_TOKEN),
        "webhook_secret": bool(MALIPO_WEBHOOK_SECRET),
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


@app.get("/plans")
def plans():
    return {"plans": PLANS}


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


@app.post("/payments/create")
async def create_payment(
    data: PaymentIn,
    merchant: Merchant = Depends(current_merchant),
    session: Session = Depends(db),
):
    if data.plan_code not in PLANS:
        raise HTTPException(400, "Kifurushi hakipo")
    if not MALIPO_TOKEN:
        raise HTTPException(503, "MalipoPay API key haijawekwa kwenye Render")

    phone = normalize_phone(data.phone)
    plan = PLANS[data.plan_code]
    customer_reference = "SAI-" + uuid.uuid4().hex[:18].upper()

    payment = Payment(
        merchant_id=merchant.user_id,
        reference=customer_reference,
        plan_code=data.plan_code,
        amount=plan["amount"],
        phone=phone,
        status="PENDING",
    )
    session.add(payment)
    session.commit()
    session.refresh(payment)

    # MalipoPay v2 direct collection. The MNO is detected from the phone number.
    payload = {
        "reference": customer_reference,
        "description": f"AI Sales Assistant - {plan['name']}",
        "amount": plan["amount"],
        "service": "mobile",
        "account": phone,
        "amountType": "FULL",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{MALIPO_BASE}/api/v2/payment/collection",
                headers={"apiToken": MALIPO_TOKEN, "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        payment.status = "FAILED"
        session.commit()
        raise HTTPException(502, f"MalipoPay haijapatikana: {exc}")

    try:
        gateway = response.json()
    except ValueError:
        gateway = {"success": False, "message": response.text[:500]}

    if response.status_code >= 400 or gateway.get("success") is False:
        payment.status = "FAILED"
        session.commit()
        message = gateway.get("message") or "MalipoPay imekataa ombi la malipo."
        raise HTTPException(502, message)

    data_out = gateway.get("data") or {}
    payment.status = str(data_out.get("status") or "PROCESSING").upper()
    payment.external_reference = data_out.get("reference")
    payment.checkout_url = data_out.get("link")
    session.commit()

    return {
        "status": payment.status,
        "reference": payment.reference,
        "external_reference": payment.external_reference,
        "amount": plan["amount"],
        "plan": plan["name"],
        "message": "Ombi la malipo limetumwa. Angalia simu yako na thibitisha kwa PIN kwenye mobile money.",
    }


@app.post("/webhook/malipopay")
async def malipo_webhook(
    request: Request,
    x_malipopay_signature: Optional[str] = Header(None),
    session: Session = Depends(db),
):
    raw_body = await request.body()
    if not verify_webhook_signature(raw_body, x_malipopay_signature):
        raise HTTPException(401, "Invalid MalipoPay webhook signature")

    try:
        body = json.loads(raw_body)
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    event = str(body.get("event") or "").lower()
    status = str(body.get("status") or "").upper()
    reference = body.get("customerReference") or body.get("reference")
    payment = session.query(Payment).filter(Payment.reference == reference).first()
    if not payment:
        return {"ok": True, "ignored": True}

    if event == "payment.confirmed":
        paid_amount = float(body.get("amount") or 0)
        payment.external_reference = body.get("reference") or body.get("transactionId")
        if paid_amount < float(payment.amount) or status == "PARTIAL":
            payment.status = "PARTIAL"
            session.commit()
            return {"ok": True, "status": "partial"}

        if payment.status != "PAID":
            payment.status = "PAID"
            payment.paid_at = datetime.utcnow()
            payment.external_reference = body.get("transactionId") or body.get("reference")
            merchant = session.get(Merchant, payment.merchant_id)
            if merchant:
                activate_subscription(payment, merchant, datetime.utcnow())
            session.commit()

    elif event == "payment.failed":
        payment.status = status or "FAILED"
        session.commit()

    elif event == "payment.refunded":
        payment.status = "REFUNDED"
        session.commit()

    return {"ok": True}


@app.get("/payments/{reference}")
def payment_status(
    reference: str,
    merchant: Merchant = Depends(current_merchant),
    session: Session = Depends(db),
):
    payment = (
        session.query(Payment)
        .filter(Payment.reference == reference, Payment.merchant_id == merchant.user_id)
        .first()
    )
    if not payment:
        raise HTTPException(404, "Malipo hayapo")
    return {
        "reference": payment.reference,
        "status": payment.status,
        "plan": payment.plan_code,
        "amount": payment.amount,
        "external_reference": payment.external_reference,
    }


@app.post("/chat")
def chat(
    data: ChatIn,
    merchant: Merchant = Depends(current_merchant),
    session: Session = Depends(db),
):
    reply = generate_ai_sales_response(merchant, data.message, data.platform)
    if reply == "SERVICE_INACTIVE":
        if merchant.expiry_date and datetime.utcnow() >= merchant.expiry_date:
            merchant.subscription_status = "Expired"
            session.commit()
        return {
            "status": "blocked",
            "message": "Huduma haipo active. Tafadhali lipia au renew kifurushi.",
        }
    if merchant.message_limit is not None:
        merchant.messages_used += 1
        session.commit()
    return {
        "status": "success",
        "ai_reply": reply,
        "messages_used": merchant.messages_used,
        "message_limit": merchant.message_limit,
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
        return {"status": "blocked", "message": "Huduma haipo active"}
    if merchant.message_limit is not None:
        merchant.messages_used += 1
        session.commit()
    return {"status": "success", "merchant_id": merchant_id, "ai_reply": reply}
