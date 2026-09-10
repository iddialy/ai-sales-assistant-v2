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
from models import Base, Merchant, Product, SessionLocal, engine


# Create database tables
Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="AI Sales Assistant Tanzania",
    version="6.0.0"
)


# CORS
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


# Security
password_hash = PasswordHash.recommended()

JWT_SECRET = os.getenv(
    "JWT_SECRET",
    "CHANGE_ME_IN_RENDER"
)

JWT_ALG = "HS256"


# -------------------------
# Request models
# -------------------------

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


class ProductIn(BaseModel):
    product_name: str = Field(
        min_length=1,
        max_length=200
    )
    price: float = Field(ge=0)
    description: str = ""


class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    platform: str = "web"


# -------------------------
# Database
# -------------------------

def db():
    session = SessionLocal()

    try:
        yield session

    finally:
        session.close()


# -------------------------
# Authentication
# -------------------------

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
        token = authorization.split(" ", 1)[1]

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
            detail="Account haipo kwenye database. Tafadhali fungua account tena."
        )

    return merchant


# -------------------------
# Helpers
# -------------------------

def normalize_phone(phone: str) -> str:

    digits = "".join(
        c for c in phone
        if c.isdigit()
    )

    if digits.startswith("0"):
        digits = "255" + digits[1:]

    if not digits.startswith("255") or len(digits) != 12:
        raise HTTPException(
            status_code=400,
            detail="Tafadhali tumia namba ya Tanzania, mfano 0712345678"
        )

    return digits


def public_merchant(merchant: Merchant):

    return {
        "user_id": merchant.user_id,
        "business_name": merchant.business_name,
        "email": merchant.email,
        "phone_number": merchant.phone_number,

        # Kept for database compatibility.
        # Payments are NOT required in v6.
        "plan_code": merchant.plan_code,
        "subscription_status": merchant.subscription_status,
        "expiry_date": (
            merchant.expiry_date.isoformat()
            if merchant.expiry_date
            else None
        ),

        "message_limit": None,
        "messages_used": merchant.messages_used,
    }


# -------------------------
# System
# -------------------------

@app.get("/")
def root():

    return {
        "system_status": "Online",
        "service": "AI Sales Assistant Tanzania",
        "version": "6.0.0",
        "payments": "disabled",
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


# -------------------------
# Signup
# -------------------------

@app.post("/auth/signup")
def signup(
    data: SignupIn,
    session: Session = Depends(db)
):

    email = str(data.email).lower().strip()

    existing = (
        session.query(Merchant)
        .filter(Merchant.email == email)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Email tayari imesajiliwa. Tumia Login."
        )

    merchant = Merchant(
        user_id="m_" + uuid.uuid4().hex[:16],
        business_name=data.business_name.strip(),
        email=email,
        phone_number=normalize_phone(
            data.phone_number
        ),
        password_hash=password_hash.hash(
            data.password
        ),
        language_preference=data.language_preference,
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
        "merchant": public_merchant(merchant),
    }


# -------------------------
# Login
# -------------------------

@app.post("/auth/login")
def login(
    data: LoginIn,
    session: Session = Depends(db)
):

    email = str(data.email).lower().strip()

    merchant = (
        session.query(Merchant)
        .filter(Merchant.email == email)
        .first()
    )

    if not merchant:
        raise HTTPException(
            status_code=401,
            detail="Account haipo. Hakikisha email au fungua Sign Up."
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
        "merchant": public_merchant(merchant),
    }


# -------------------------
# Current account
# -------------------------

@app.get("/auth/me")
def me(
    merchant: Merchant = Depends(current_merchant),
    session: Session = Depends(db)
):

    session.refresh(merchant)

    return public_merchant(merchant)


# -------------------------
# Products
# -------------------------

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
        }
        for p in merchant.products
    ]


# -------------------------
# AI Chat
# -------------------------

@app.post("/chat")
def chat(
    data: ChatIn,
    merchant: Merchant = Depends(current_merchant),
    session: Session = Depends(db),
):

    # Payments are disabled in v6.
    # Every logged-in merchant can test the AI.

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
                "Hakikisha GEMINI_API_KEY imewekwa kwenye Render."
            ),
        }

    merchant.messages_used += 1

    session.commit()

    return {
        "status": "success",
        "ai_reply": reply,
        "messages_used": merchant.messages_used,
        "message_limit": None,
    }


# -------------------------
# Incoming webhook
# -------------------------

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
            detail="Mfanyabiashara hajapatikana"
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
                "Hakikisha GEMINI_API_KEY imewekwa kwenye Render."
            ),
        }

    merchant.messages_used += 1

    session.commit()

    return {
        "status": "success",
        "merchant_id": merchant_id,
        "ai_reply": reply,
    }
