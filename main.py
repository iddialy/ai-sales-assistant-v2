import os
import uuid
import hmac
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from ai_engine import generate_ai_sales_response
from models import (
    Base,
    Merchant,
    MerchantPaymentInfo,
    Product,
    SessionLocal,
    engine,
)


# -------------------------
# Create database tables
# -------------------------

Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="AI Sales Assistant Tanzania",
    version="7.0.0"
)


# -------------------------
# CORS
# -------------------------

cors_raw = os.getenv(
    "CORS_ORIGINS",
    "https://iddialy.github.io"
)

origins = [
    x.strip()
    for x in cors_raw.split(",")
    if x.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------
# Security
# -------------------------

password_hash = PasswordHash.recommended()

JWT_SECRET = os.getenv(
    "JWT_SECRET",
    "CHANGE_ME_IN_RENDER"
)

JWT_ALG = "HS256"


# =========================================================
# REQUEST MODELS
# =========================================================

class SignupIn(BaseModel):
    business_name: str = Field(
        min_length=2,
        max_length=200
    )
    email: EmailStr
    phone_number: str
    password: str = Field(
        min_length=8,
        max_length=128
    )
    language_preference: str = "sw"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class BusinessProfileIn(BaseModel):
    business_name: str = Field(
        min_length=2,
        max_length=200
    )

    phone_number: str = Field(
        min_length=9,
        max_length=20
    )

    business_location: Optional[str] = Field(
        default=None,
        max_length=300
    )

    business_type: Optional[str] = Field(
        default=None,
        max_length=150
    )

    business_hours: Optional[str] = Field(
        default=None,
        max_length=300
    )

    business_description: Optional[str] = Field(
        default=None,
        max_length=5000
    )

    lipa_namba: Optional[str] = Field(
        default=None,
        max_length=100
    )

    phone_payment: Optional[str] = Field(
        default=None,
        max_length=20
    )

    bank_account: Optional[str] = Field(
        default=None,
        max_length=200
    )


class ProductIn(BaseModel):
    product_name: str = Field(
        min_length=1,
        max_length=200
    )

    price: float = Field(
        ge=0
    )

    description: str = ""

    image_url: Optional[str] = Field(
        default=None,
        max_length=2000
    )


class ChatIn(BaseModel):
    message: str = Field(
        min_length=1
    )

    platform: str = "web"


# =========================================================
# DATABASE
# =========================================================

def db():
    session = SessionLocal()

    try:
        yield session

    finally:
        session.close()


# =========================================================
# AUTHENTICATION
# =========================================================

def token_for(merchant: Merchant) -> str:

    return jwt.encode(
        {
            "sub": merchant.user_id,
            "exp": datetime.utcnow() + timedelta(days=7),
        },
        JWT_SECRET,
        algorithm=JWT_ALG,
    )


def current_merchant(
    authorization: Optional[str] = Header(None),
    session: Session = Depends(db),
) -> Merchant:

    if not authorization or not authorization.startswith("Bearer "):

        raise HTTPException(
            status_code=401,
            detail="Login required"
        )

    try:

        token = authorization.split(
            " ",
            1
        )[1]

        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALG]
        )

    except jwt.PyJWTError:

        raise HTTPException(
            status_code=401,
            detail="Session ime-expire. Ingia tena."
        )

    merchant_id = payload.get("sub")

    merchant = session.get(
        Merchant,
        merchant_id
    )

    if not merchant:

        raise HTTPException(
            status_code=401,
            detail=(
                "Account haipo kwenye database. "
                "Tafadhali fungua account tena."
            )
        )

    return merchant


# =========================================================
# HELPERS
# =========================================================

def normalize_phone(phone: str) -> str:

    digits = "".join(
        c for c in phone
        if c.isdigit()
    )

    if digits.startswith("0"):

        digits = "255" + digits[1:]

    if (
        not digits.startswith("255")
        or len(digits) != 12
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Tafadhali tumia namba ya Tanzania, "
                "mfano 0712345678"
            )
        )

    return digits


def public_merchant(
    merchant: Merchant,
    session: Optional[Session] = None
):

    payment_info = merchant.payment_info

    return {
        "user_id": merchant.user_id,

        "business_name": merchant.business_name,

        "email": merchant.email,

        "phone_number": merchant.phone_number,

        # -------------------------
        # Business Profile
        # -------------------------

        "business_location": (
            merchant.business_location
        ),

        "business_type": (
            merchant.business_type
        ),

        "business_hours": (
            merchant.business_hours
        ),

        "business_description": (
            merchant.business_description
        ),

        # -------------------------
        # Merchant Payment Details
        # -------------------------

        "payment_info": {

            "lipa_namba": (
                payment_info.lipa_namba
                if payment_info
                else None
            ),

            "phone_payment": (
                payment_info.phone_payment
                if payment_info
                else None
            ),

            "bank_account": (
                payment_info.bank_account
                if payment_info
                else None
            ),
        },

        # -------------------------
        # Subscription
        # -------------------------

        "plan_code": merchant.plan_code,

        "subscription_status": (
            merchant.subscription_status
        ),

        "expiry_date": (
            merchant.expiry_date.isoformat()
            if merchant.expiry_date
            else None
        ),

        "message_limit": None,

        "messages_used": merchant.messages_used,
    }


# =========================================================
# SYSTEM
# =========================================================

@app.get("/")
def root():

    return {
        "system_status": "Online",
        "service": "AI Sales Assistant Tanzania",
        "version": "7.0.0",
        "payments": "disabled",
        "business_profile": "enabled",
    }


@app.get("/health")
def health():

    return {
        "status": "ok",

        "database": (
            "configured"
            if os.getenv("DATABASE_URL")
            else "sqlite-fallback"
        ),
    }


# =========================================================
# SIGNUP
# =========================================================

@app.post("/auth/signup")
def signup(
    data: SignupIn,
    session: Session = Depends(db)
):

    email = str(
        data.email
    ).lower().strip()

    existing = (
        session.query(Merchant)
        .filter(
            Merchant.email == email
        )
        .first()
    )

    if existing:

        raise HTTPException(
            status_code=409,
            detail=(
                "Email tayari imesajiliwa. "
                "Tumia Login."
            )
        )

    merchant = Merchant(

        user_id=(
            "m_" +
            uuid.uuid4().hex[:16]
        ),

        business_name=(
            data.business_name.strip()
        ),

        email=email,

        phone_number=normalize_phone(
            data.phone_number
        ),

        password_hash=password_hash.hash(
            data.password
        ),

        language_preference=(
            data.language_preference
        ),

        subscription_status="Active",

        plan_code="test",

        message_limit=None,

        messages_used=0,
    )

    session.add(merchant)

    session.commit()

    session.refresh(merchant)

    return {
        "token": token_for(merchant),

        "merchant": public_merchant(
            merchant,
            session
        ),
    }


# =========================================================
# LOGIN
# =========================================================

@app.post("/auth/login")
def login(
    data: LoginIn,
    session: Session = Depends(db)
):

    email = str(
        data.email
    ).lower().strip()

    merchant = (
        session.query(Merchant)
        .filter(
            Merchant.email == email
        )
        .first()
    )

    if not merchant:

        raise HTTPException(
            status_code=401,
            detail=(
                "Account haipo. "
                "Hakikisha email au fungua Sign Up."
            )
        )

    try:

        valid = password_hash.verify(
            data.password,
            merchant.password_hash
        )

    except Exception:

        valid = False

    if not valid:

        raise HTTPException(
            status_code=401,
            detail="Password si sahihi."
        )

    return {
        "token": token_for(merchant),

        "merchant": public_merchant(
            merchant,
            session
        ),
    }


# =========================================================
# CURRENT ACCOUNT
# =========================================================

@app.get("/auth/me")
def me(
    merchant: Merchant = Depends(current_merchant),
    session: Session = Depends(db)
):

    session.refresh(merchant)

    return public_merchant(
        merchant,
        session
    )


# =========================================================
# BUSINESS PROFILE
# =========================================================

@app.get("/business-profile")
def get_business_profile(
    merchant: Merchant = Depends(current_merchant),
    session: Session = Depends(db)
):

    session.refresh(merchant)

    return public_merchant(
        merchant,
        session
    )


@app.put("/business-profile")
def update_business_profile(
    data: BusinessProfileIn,
    merchant: Merchant = Depends(current_merchant),
    session: Session = Depends(db),
):

    # -------------------------
    # Basic business information
    # -------------------------

    merchant.business_name = (
        data.business_name.strip()
    )

    merchant.phone_number = normalize_phone(
        data.phone_number
    )

    merchant.business_location = (
        data.business_location.strip()
        if data.business_location
        else None
    )

    merchant.business_type = (
        data.business_type.strip()
        if data.business_type
        else None
    )

    merchant.business_hours = (
        data.business_hours.strip()
        if data.business_hours
        else None
    )

    merchant.business_description = (
        data.business_description.strip()
        if data.business_description
        else None
    )

    # -------------------------
    # Merchant payment details
    # -------------------------

    payment_info = merchant.payment_info

    if not payment_info:

        payment_info = MerchantPaymentInfo(
            merchant_id=merchant.user_id
        )

        session.add(payment_info)

    payment_info.lipa_namba = (
        data.lipa_namba.strip()
        if data.lipa_namba
        else None
    )

    payment_info.phone_payment = (
        normalize_phone(data.phone_payment)
        if data.phone_payment
        else None
    )

    payment_info.bank_account = (
        data.bank_account.strip()
        if data.bank_account
        else None
    )

    session.commit()

    session.refresh(merchant)

    return {
        "status": "success",

        "message": (
            "Business Profile imehifadhiwa."
        ),

        "merchant": public_merchant(
            merchant,
            session
        ),
    }


# =========================================================
# PRODUCTS
# =========================================================

@app.post("/products")
def add_product(
    data: ProductIn,
    merchant: Merchant = Depends(current_merchant),
    session: Session = Depends(db),
):

    product = Product(

        product_id=(
            "p_" +
            uuid.uuid4().hex[:16]
        ),

        merchant_id=merchant.user_id,

        product_name=(
            data.product_name.strip()
        ),

        price=data.price,

        description=(
            data.description.strip()
        ),

        image_url=(
            data.image_url.strip()
            if data.image_url
            else None
        ),
    )

    session.add(product)

    session.commit()

    session.refresh(product)

    return {
        "status": "success",

        "product_id": product.product_id,
    }


@app.get("/products")
def products(
    merchant: Merchant = Depends(current_merchant)
):

    return [

        {
            "product_id": p.product_id,

            "product_name": p.product_name,

            "price": p.price,

            "description": p.description,

            "image_url": p.image_url,
        }

        for p in merchant.products
    ]


# =========================================================
# AI CHAT
# =========================================================

@app.post("/chat")
def chat(
    data: ChatIn,
    merchant: Merchant = Depends(current_merchant),
    session: Session = Depends(db),
):

    # Payments are disabled.
    # Every logged-in merchant can test AI.

    reply = generate_ai_sales_response(
        merchant,
        data.message,
        data.platform
    )

    if reply == "SERVICE_INACTIVE":

        return {
            "status": "blocked",

            "message": (
                "AI haijaweza kuanza. "
                "Hakikisha GEMINI_API_KEY "
                "imewekwa kwenye Render."
            ),
        }

    merchant.messages_used += 1

    session.commit()

    return {

        "status": "success",

        "ai_reply": reply,

        "messages_used": (
            merchant.messages_used
        ),

        "message_limit": None,
    }


# =========================================================
# INCOMING WEBHOOK
# =========================================================

@app.post("/webhook/message")
def incoming(
    merchant_id: str,
    platform: str,
    customer_message: str,
    x_webhook_secret: Optional[str] = Header(None),
    session: Session = Depends(db),
):

    secret = os.getenv(
        "WEBHOOK_SECRET",
        ""
    )

    if secret and not hmac.compare_digest(
        x_webhook_secret or "",
        secret
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid webhook secret"
        )

    merchant = session.get(
        Merchant,
        merchant_id
    )

    if not merchant:

        raise HTTPException(
            status_code=404,
            detail=(
                "Mfanyabiashara hajapatikana"
            )
        )

    reply = generate_ai_sales_response(
        merchant,
        customer_message,
        platform
    )

    if reply == "SERVICE_INACTIVE":

        return {

            "status": "blocked",

            "message": (
                "AI haijaweza kuanza. "
                "Hakikisha GEMINI_API_KEY "
                "imewekwa kwenye Render."
            ),
        }

    merchant.messages_used += 1

    session.commit()

    return {

        "status": "success",

        "merchant_id": merchant_id,

        "ai_reply": reply,
    }
