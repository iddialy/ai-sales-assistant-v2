import os, uuid, hmac, hashlib
from datetime import datetime, timedelta
from typing import Optional

import httpx
import jwt
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from models import Base, engine, SessionLocal, Merchant, MerchantPaymentInfo, Product, Payment
from ai_engine import generate_ai_sales_response

Base.metadata.create_all(bind=engine)
app = FastAPI(title="AI Sales Assistant Tanzania", version="3.0.1")

origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()]
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
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://iddialy.github.io/ai-sales-assistant-v2/")
MALIPO_BASE = os.getenv("MALIPO_BASE_URL", "https://core-prod.malipopay.co.tz").rstrip("/")
MALIPO_TOKEN = os.getenv("MALIPOPAY_API_TOKEN", "")
MALIPO_WEBHOOK_SECRET = os.getenv("MALIPOPAY_WEBHOOK_SECRET", "")

PLANS = {
    "starter": {"name": "Starter", "amount": 35000, "limit": 1000},
    "business": {"name": "Business", "amount": 75000, "limit": None},
}

class SignupIn(BaseModel):
    business_name: str
    email: EmailStr
    phone_number: str
    password: str
    language_preference: str = "sw"

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class ProductIn(BaseModel):
    product_name: str
    price: float
    description: str

class PaymentIn(BaseModel):
    plan_code: str
    phone: str

class ChatIn(BaseModel):
    message: str
    platform: str = "web"


def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def token_for(m: Merchant):
    return jwt.encode(
        {"sub": m.user_id, "exp": datetime.utcnow() + timedelta(days=7)},
        JWT_SECRET,
        algorithm=JWT_ALG,
    )


def current_merchant(authorization: Optional[str] = Header(None), db: Session = Depends(db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Login required")
    try:
        payload = jwt.decode(authorization.split(" ", 1)[1], JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    m = db.get(Merchant, payload.get("sub"))
    if not m:
        raise HTTPException(401, "Account not found")
    return m


def normalize_phone(phone: str) -> str:
    p = "".join(c for c in phone if c.isdigit())
    if p.startswith("0"):
        p = "255" + p[1:]
    if not p.startswith("255") or len(p) != 12:
        raise HTTPException(400, "Tafadhali tumia namba ya Tanzania, mfano 0712345678")
    return p


def public_merchant(m):
    return {
        "user_id": m.user_id,
        "business_name": m.business_name,
        "email": m.email,
        "phone_number": m.phone_number,
        "plan_code": m.plan_code,
        "subscription_status": m.subscription_status,
        "expiry_date": m.expiry_date,
        "message_limit": m.message_limit,
        "messages_used": m.messages_used,
    }


def activate_subscription(payment: Payment, merchant: Merchant, now: datetime):
    plan = PLANS[payment.plan_code]
    # If the merchant is already active, extend from the current expiry.
    base = merchant.expiry_date if merchant.subscription_status == "Active" and merchant.expiry_date and merchant.expiry_date > now else now
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
    expected = hmac.new(MALIPO_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


@app.get("/")
def root():
    return {"system_status": "Online", "service": "AI Sales Assistant Tanzania", "version": "3.0.1"}


@app.post("/auth/signup")
def signup(data: SignupIn, db: Session = Depends(db)):
    if len(data.password) < 8:
        raise HTTPException(400, "Password iwe na angalau herufi 8")
    email = data.email.lower()
    if db.query(Merchant).filter(Merchant.email == email).first():
        raise HTTPException(409, "Email tayari imesajiliwa")
    m = Merchant(
        user_id="m_" + uuid.uuid4().hex[:16],
        business_name=data.business_name.strip(),
        email=email,
        phone_number=normalize_phone(data.phone_number),
        password_hash=password_hash.hash(data.password),
        language_preference=data.language_preference,
    )
    m.payment_info = MerchantPaymentInfo(phone_payment=m.phone_number)
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"token": token_for(m), "merchant": public_merchant(m)}


@app.post("/auth/login")
def login(data: LoginIn, db: Session = Depends(db)):
    m = db.query(Merchant).filter(Merchant.email == data.email.lower()).first()
    if not m or not password_hash.verify(data.password, m.password_hash):
        raise HTTPException(401, "Email au password si sahihi")
    return {"token": token_for(m), "merchant": public_merchant(m)}


@app.get("/auth/me")
def me(m: Merchant = Depends(current_merchant), db: Session = Depends(db)):
    db.refresh(m)
    # Keep status consistent if the subscription has expired.
    if m.subscription_status == "Active" and m.expiry_date and datetime.utcnow() >= m.expiry_date:
        m.subscription_status = "Expired"
        db.commit()
    return public_merchant(m)


@app.get("/plans")
def plans():
    return {"plans": PLANS}


@app.post("/products")
def add_product(data: ProductIn, m: Merchant = Depends(current_merchant), db: Session = Depends(db)):
    if data.price < 0:
        raise HTTPException(400, "Bei haiwezi kuwa chini ya sifuri")
    p = Product(
        product_id="p_" + uuid.uuid4().hex[:16],
        merchant_id=m.user_id,
        product_name=data.product_name.strip(),
        price=data.price,
        description=data.description.strip(),
    )
    db.add(p)
    db.commit()
    return {"status": "success", "product_id": p.product_id}


@app.get("/products")
def products(m: Merchant = Depends(current_merchant)):
    return [
        {"product_id": p.product_id, "product_name": p.product_name, "price": p.price, "description": p.description}
        for p in m.products
    ]


@app.post("/payments/create")
async def create_payment(data: PaymentIn, m: Merchant = Depends(current_merchant), db: Session = Depends(db)):
    if data.plan_code not in PLANS:
        raise HTTPException(400, "Kifurushi hakipo")
    if not MALIPO_TOKEN:
        raise HTTPException(503, "MalipoPay API token haijawekwa kwenye Render")

    phone = normalize_phone(data.phone)
    plan = PLANS[data.plan_code]
    reference = "SAI-" + uuid.uuid4().hex[:18].upper()
    payment = Payment(
        merchant_id=m.user_id,
        reference=reference,
        plan_code=data.plan_code,
        amount=plan["amount"],
        phone=phone,
        status="PENDING",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    # MalipoPay hosted checkout: it handles the payment UI and redirects the customer back.
    payload = {
        "amount": plan["amount"],
        "currency": "TZS",
        "description": f"AI Sales Assistant - {plan['name']}",
        "callbackUrl": f"{FRONTEND_URL}?payment=complete&reference={reference}",
        "reference": reference,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{MALIPO_BASE}/api/v1/payment/link",
                headers={"apiToken": MALIPO_TOKEN, "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        payment.status = "FAILED"
        db.commit()
        raise HTTPException(502, f"MalipoPay haijapatikana: {exc}")

    try:
        out = r.json()
    except ValueError:
        out = {"message": r.text[:500]}

    if r.status_code >= 400 or out.get("success") is False:
        payment.status = "FAILED"
        db.commit()
        gateway_message = out.get("message") or "Payment gateway imekataa ombi"
        raise HTTPException(502, gateway_message)

    data_out = out.get("data") or {}
    payment.checkout_url = (
        data_out.get("paymentUrl")
        or data_out.get("url")
        or data_out.get("checkoutUrl")
        or out.get("paymentUrl")
        or out.get("url")
        or out.get("checkoutUrl")
    )
    db.commit()

    if not payment.checkout_url:
        raise HTTPException(502, "MalipoPay haikurudisha checkout URL")

    return {
        "status": "pending",
        "reference": reference,
        "amount": plan["amount"],
        "plan": plan["name"],
        "checkout_url": payment.checkout_url,
    }


@app.post("/webhook/malipopay")
async def malipo_webhook(
    request: Request,
    x_malipopay_signature: Optional[str] = Header(None),
    db: Session = Depends(db),
):
    raw_body = await request.body()
    if not verify_webhook_signature(raw_body, x_malipopay_signature):
        raise HTTPException(401, "Invalid MalipoPay webhook signature")

    try:
        body = __import__("json").loads(raw_body)
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    event = str(body.get("event") or "").lower()
    status = str(body.get("status") or "").upper()
    reference = body.get("customerReference") or body.get("reference")
    payment = db.query(Payment).filter(Payment.reference == reference).first()
    if not payment:
        return {"ok": True, "ignored": True}

    if event == "payment.confirmed" and status in {"SUCCESSFUL", "PAID"}:
        paid_amount = body.get("amount")
        if paid_amount is not None and float(paid_amount) < float(payment.amount):
            payment.status = "PARTIAL"
            db.commit()
            return {"ok": True, "status": "partial"}
        if payment.status != "PAID":
            payment.status = "PAID"
            payment.paid_at = datetime.utcnow()
            payment.external_reference = body.get("transactionId")
            merchant = db.get(Merchant, payment.merchant_id)
            if merchant:
                activate_subscription(payment, merchant, datetime.utcnow())
            db.commit()

    elif event == "payment.failed" or status in {"FAILED", "REJECTED", "CANCELLED", "CUSTOMER_REJECTED"}:
        payment.status = status or "FAILED"
        db.commit()

    elif event == "payment.refunded":
        payment.status = "REFUNDED"
        db.commit()

    return {"ok": True}


@app.get("/payments/{reference}")
def payment_status(reference: str, m: Merchant = Depends(current_merchant), db: Session = Depends(db)):
    p = db.query(Payment).filter(Payment.reference == reference, Payment.merchant_id == m.user_id).first()
    if not p:
        raise HTTPException(404, "Malipo hayapo")
    return {
        "reference": p.reference,
        "status": p.status,
        "plan": p.plan_code,
        "amount": p.amount,
        "checkout_url": p.checkout_url,
    }


@app.post("/chat")
def chat(data: ChatIn, m: Merchant = Depends(current_merchant), db: Session = Depends(db)):
    reply = generate_ai_sales_response(m, data.message, data.platform)
    if reply == "SERVICE_INACTIVE":
        return {"status": "blocked", "message": "Huduma haipo active. Tafadhali lipia au renew kifurushi."}
    if m.message_limit is not None:
        m.messages_used += 1
        db.commit()
    return {"status": "success", "ai_reply": reply, "messages_used": m.messages_used, "message_limit": m.message_limit}


@app.post("/webhook/message")
def incoming(
    merchant_id: str,
    platform: str,
    customer_message: str,
    x_webhook_secret: Optional[str] = Header(None),
    db: Session = Depends(db),
):
    secret = os.getenv("WEBHOOK_SECRET", "")
    if secret and not hmac.compare_digest(x_webhook_secret or "", secret):
        raise HTTPException(401, "Invalid webhook secret")
    m = db.get(Merchant, merchant_id)
    if not m:
        raise HTTPException(404, "Mfanyabiashara hajapatikana")
    reply = generate_ai_sales_response(m, customer_message, platform)
    if reply == "SERVICE_INACTIVE":
        return {"status": "blocked", "message": "Huduma haipo active"}
    if m.message_limit is not None:
        m.messages_used += 1
        db.commit()
    return {"status": "success", "merchant_id": merchant_id, "ai_reply": reply}
