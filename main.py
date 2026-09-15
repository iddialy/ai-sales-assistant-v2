import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from urllib.parse import urlencode, quote
from datetime import datetime, timedelta
from typing import Generator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    StreamingResponse,
    RedirectResponse,
    PlainTextResponse,
)

from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, joinedload
from cryptography.fernet import Fernet, InvalidToken

from ai_engine import (
    generate_ai_sales_response,
    generate_ai_sales_response_stream,
)

from models import (
    Base,
    ChatRequest,
    Conversation,
    Customer,
    LoginRequest,
    Merchant,
    MerchantPaymentInfo,
    Product,
    ProductCreate,
    ProductUpdate,
    ProfileUpdate,
    SessionLocal,
    SignupRequest,
    SubscriptionPayment,
    SocialConnection,
    engine,
)


app = FastAPI(
    title="AI Sales Assistant Tanzania",
    version="2.0.0",
)


# =========================================================
# CORS
# =========================================================

cors_raw = os.getenv("CORS_ORIGINS", "*")
origins = [x.strip() for x in cors_raw.split(",") if x.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# GLOBAL CONFIG
# =========================================================

TOKEN_SECRET = os.getenv(
    "TOKEN_SECRET",
    "dev-change-this-secret",
)

TOKEN_TTL = 60 * 60 * 24 * 30

SOCIAL_FRONTEND_URL = os.getenv(
    "SOCIAL_FRONTEND_URL",
    "https://iddialy.github.io/ai-sales-assistant-v2/",
)

SOCIAL_STATE_TTL = 10 * 60

WHATSAPP_GRAPH_VERSION = os.getenv(
    "WHATSAPP_GRAPH_VERSION",
    "v23.0",
)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


# =========================================================
# PASSWORD
# =========================================================

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)

    rounds = 210_000

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt,
        rounds,
    )

    return (
        f"pbkdf2_sha256$"
        f"{rounds}$"
        f"{base64.urlsafe_b64encode(salt).decode()}$"
        f"{base64.urlsafe_b64encode(digest).decode()}"
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_b64, digest_b64 = stored.split("$", 3)

        if algo != "pbkdf2_sha256":
            return False

        salt = base64.urlsafe_b64decode(
            salt_b64.encode()
        )

        expected = base64.urlsafe_b64decode(
            digest_b64.encode()
        )

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt,
            int(rounds),
        )

        return hmac.compare_digest(
            actual,
            expected,
        )

    except Exception:
        return False


# =========================================================
# LOGIN TOKEN
# =========================================================

def make_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": int(time.time()) + TOKEN_TTL,
    }

    raw = base64.urlsafe_b64encode(
        json.dumps(
            payload,
            separators=(",", ":"),
        ).encode()
    ).decode().rstrip("=")

    sig = hmac.new(
        TOKEN_SECRET.encode(),
        raw.encode(),
        hashlib.sha256,
    ).digest()

    signature = base64.urlsafe_b64encode(
        sig
    ).decode().rstrip("=")

    return f"{raw}.{signature}"


def decode_token(token: str) -> str:
    try:
        raw, signature = token.split(".", 1)

        expected = hmac.new(
            TOKEN_SECRET.encode(),
            raw.encode(),
            hashlib.sha256,
        ).digest()

        supplied = base64.urlsafe_b64decode(
            signature
            + "=" * (-len(signature) % 4)
        )

        if not hmac.compare_digest(
            expected,
            supplied,
        ):
            raise ValueError

        payload = json.loads(
            base64.urlsafe_b64decode(
                raw + "=" * (-len(raw) % 4)
            ).decode()
        )

        if int(payload["exp"]) < int(time.time()):
            raise ValueError

        return str(payload["sub"])

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Session imekwisha au si sahihi. Tafadhali login tena.",
        )


# =========================================================
# PRODUCTS
# =========================================================

def public_product(p: Product):
    return {
        "product_id": p.product_id,
        "product_name": p.product_name,
        "category": p.category,
        "description": p.description or "",
        "wholesale_price": p.wholesale_price,
        "retail_price": p.retail_price,
        "price": p.retail_price,
        "stock_quantity": p.stock_quantity,
        "status": p.status,
        "image_url": p.image_url,
    }


# =========================================================
# SOCIAL CONNECTIONS
# =========================================================

def _social_cipher():
    raw = os.getenv(
        "SOCIAL_TOKEN_ENCRYPTION_KEY",
        "",
    ).strip()

    if raw:
        try:
            return Fernet(raw.encode())

        except Exception:
            pass

    key = base64.urlsafe_b64encode(
        hashlib.sha256(
            TOKEN_SECRET.encode("utf-8")
        ).digest()
    )

    return Fernet(key)


def _encrypt_social_token(
    value: str | None,
) -> str | None:

    if not value:
        return None

    return _social_cipher().encrypt(
        value.encode("utf-8")
    ).decode("utf-8")


def _decrypt_social_token(
    value: str | None,
) -> str | None:

    if not value:
        return None

    try:
        return _social_cipher().decrypt(
            value.encode("utf-8")
        ).decode("utf-8")

    except InvalidToken:
        return None


def _make_social_state(
    merchant_id: str,
    provider: str,
) -> str:

    payload = {
        "merchant_id": merchant_id,
        "provider": provider,
        "exp": int(time.time()) + SOCIAL_STATE_TTL,
        "nonce": secrets.token_urlsafe(12),
    }

    raw = base64.urlsafe_b64encode(
        json.dumps(
            payload,
            separators=(",", ":"),
        ).encode()
    ).decode().rstrip("=")

    sig = hmac.new(
        TOKEN_SECRET.encode(),
        raw.encode(),
        hashlib.sha256,
    ).hexdigest()

    return f"{raw}.{sig}"


def _read_social_state(
    state: str,
) -> dict:

    try:
        raw, sig = state.split(".", 1)

        expected = hmac.new(
            TOKEN_SECRET.encode(),
            raw.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(
            expected,
            sig,
        ):
            raise ValueError

        payload = json.loads(
            base64.urlsafe_b64decode(
                raw + "=" * (-len(raw) % 4)
            ).decode()
        )

        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError

        if payload.get("provider") not in {
            "whatsapp",
            "facebook",
            "instagram",
            "tiktok",
        }:
            raise ValueError

        return payload

    except Exception:
        raise HTTPException(
            400,
            "Social connection request si sahihi au ime-expire.",
        )


def _social_public(c: SocialConnection):
    return {
        "provider": c.provider,
        "account_name": c.account_name,
        "account_id": c.account_id,
        "status": c.status,
        "connected": c.status == "CONNECTED",
        "token_expires_at": (
            c.token_expires_at.isoformat()
            if c.token_expires_at
            else None
        ),
        "updated_at": (
            c.updated_at.isoformat()
            if c.updated_at
            else None
        ),
    }


def _social_config_error(
    provider: str,
):

    if provider in {
        "whatsapp",
        "facebook",
        "instagram",
    }:

        if (
            not os.getenv("META_APP_ID")
            or not os.getenv("META_APP_SECRET")
        ):
            return (
                "Meta App ID/Secret "
                "hazijawekwa kwenye Render."
            )

    if provider == "tiktok":

        if (
            not os.getenv("TIKTOK_CLIENT_KEY")
            or not os.getenv("TIKTOK_CLIENT_SECRET")
        ):
            return (
                "TikTok Client Key/Secret "
                "hazijawekwa kwenye Render."
            )

    return None


# =========================================================
# MERCHANT
# =========================================================

def public_merchant(
    merchant: Merchant,
):

    payment = merchant.payment_info

    return {
        "user_id": merchant.user_id,
        "business_name": merchant.business_name,
        "email": merchant.email,
        "phone_number": merchant.phone_number,
        "language_preference": merchant.language_preference,
        "subscription_status": merchant.subscription_status,
        "plan_code": merchant.plan_code,
        "expiry_date": (
            merchant.expiry_date.isoformat()
            if merchant.expiry_date
            else None
        ),
        "message_limit": merchant.message_limit,
        "messages_used": merchant.messages_used,
        "business_location": merchant.business_location,
        "business_type": merchant.business_type,
        "business_hours": merchant.business_hours,
        "business_description": merchant.business_description,
        "payment_info": {
            "lipa_namba": (
                payment.lipa_namba
                if payment
                else None
            ),
            "bank_account": (
                payment.bank_account
                if payment
                else None
            ),
            "phone_payment": (
                payment.phone_payment
                if payment
                else None
            ),
        },
        "social_connections": [
            _social_public(c)
            for c in merchant.social_connections
        ],
        "products": [
            public_product(p)
            for p in merchant.products
        ],
    }


def get_current_merchant(
    authorization: str | None,
    db: Session,
) -> Merchant:

    if (
        not authorization
        or not authorization.lower().startswith("bearer ")
    ):
        raise HTTPException(
            status_code=401,
            detail="Authorization token inahitajika.",
        )

    user_id = decode_token(
        authorization.split(" ", 1)[1].strip()
    )

    merchant = (
        db.query(Merchant)
        .options(
            joinedload(Merchant.payment_info),
            joinedload(Merchant.products),
            joinedload(Merchant.social_connections),
        )
        .filter(
            Merchant.user_id == user_id
        )
        .first()
    )

    if not merchant:
        raise HTTPException(
            status_code=401,
            detail="Akaunti haijapatikana.",
        )

    return merchant


# =========================================================
# CUSTOMERS
# =========================================================

def public_customer(
    c: Customer,
):

    return {
        "customer_id": c.customer_id,
        "name": c.name,
        "phone": c.phone,
        "email": c.email,
        "platform": c.platform,
        "last_message_at": (
            c.last_message_at.isoformat()
            if c.last_message_at
            else None
        ),
        "last_seen_at": (
            c.last_seen_at.isoformat()
            if c.last_seen_at
            else None
        ),
        "created_at": (
            c.created_at.isoformat()
            if c.created_at
            else None
        ),
    }


def public_conversation(
    c: Conversation,
):

    return {
        "conversation_id": c.conversation_id,
        "customer_id": c.customer_id,
        "platform": c.platform,
        "customer_message": c.customer_message,
        "ai_reply": c.ai_reply,
        "created_at": (
            c.created_at.isoformat()
            if c.created_at
            else None
        ),
    }


def get_or_create_customer(
    db: Session,
    merchant_id: str,
    customer_key: str | None,
    platform: str = "website",
) -> Customer:

    key = (customer_key or "").strip()

    customer = None

    if key:

        customer = (
            db.query(Customer)
            .filter(
                Customer.merchant_id == merchant_id,
                Customer.platform == platform,
                Customer.external_key == key,
            )
            .first()
        )

    if not customer:

        customer = Customer(
            customer_id="c_" + uuid.uuid4().hex,
            merchant_id=merchant_id,
            name=(
                "Website Customer"
                if platform == "website"
                else f"{platform} Customer"
            ),
            platform=platform,
            external_key=key or None,
            last_message_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )

        db.add(customer)

    else:

        now = datetime.utcnow()

        customer.last_message_at = now
        customer.last_seen_at = now

    return customer


# =========================================================
# DATABASE MIGRATION
# =========================================================

def init_database():

    Base.metadata.create_all(
        bind=engine
    )

    additions = {

        "merchants": {
            "password_hash": "VARCHAR(255)",
            "language_preference": "VARCHAR(5)",
            "subscription_status": "VARCHAR(20)",
            "plan_code": "VARCHAR(30)",
            "expiry_date": "TIMESTAMP",
            "message_limit": "INTEGER",
            "messages_used": "INTEGER DEFAULT 0",
            "business_location": "VARCHAR(255)",
            "business_type": "VARCHAR(100)",
            "business_hours": "VARCHAR(255)",
            "business_description": "TEXT",
            "created_at": "TIMESTAMP",
        },

        "products": {
            "category": "VARCHAR(100)",
            "wholesale_price": "FLOAT",
            "retail_price": "FLOAT",
            "stock_quantity": "INTEGER DEFAULT 0",
            "status": "VARCHAR(20)",
            "image_url": "TEXT",
        },

        "customers": {
            "name": "VARCHAR(200)",
            "phone": "VARCHAR(50)",
            "email": "VARCHAR(320)",
            "platform": "VARCHAR(50)",
            "external_key": "VARCHAR(255)",
            "last_message_at": "TIMESTAMP",
            "last_seen_at": "TIMESTAMP",
            "created_at": "TIMESTAMP",
        },

        "conversations": {
            "platform": "VARCHAR(50)",
            "customer_message": "TEXT",
            "ai_reply": "TEXT",
            "created_at": "TIMESTAMP",
        },

        "social_connections": {
            "merchant_id": "VARCHAR(64)",
            "provider": "VARCHAR(30)",
            "account_name": "VARCHAR(255)",
            "account_id": "VARCHAR(255)",
            "status": "VARCHAR(30)",
            "access_token_encrypted": "TEXT",
            "refresh_token_encrypted": "TEXT",
            "token_expires_at": "TIMESTAMP",
            "created_at": "TIMESTAMP",
            "updated_at": "TIMESTAMP",
        },
    }

    with engine.begin() as conn:

        inspector = inspect(conn)

        for table, cols in additions.items():

            if not inspector.has_table(table):
                continue

            existing = {
                c["name"]
                for c in inspector.get_columns(table)
            }

            for name, definition in cols.items():

                if name not in existing:

                    try:

                        conn.execute(
                            text(
                                f'ALTER TABLE {table} '
                                f'ADD COLUMN {name} {definition}'
                            )
                        )

                    except Exception:
                        pass

        if inspector.has_table("products"):

            try:

                conn.execute(
                    text(
                        "UPDATE products "
                        "SET retail_price = price "
                        "WHERE retail_price IS NULL "
                        "AND price IS NOT NULL"
                    )
                )

            except Exception:
                pass

        if inspector.has_table("customers"):

            try:

                fresh_inspector = inspect(conn)

                customer_cols = {
                    c["name"]
                    for c in fresh_inspector.get_columns(
                        "customers"
                    )
                }

                if (
                    "last_message_at" in customer_cols
                    and "last_contact_at" in customer_cols
                ):

                    conn.execute(
                        text(
                            "UPDATE customers "
                            "SET last_message_at = "
                            "COALESCE("
                            "last_message_at, "
                            "last_contact_at)"
                        )
                    )

                fresh_inspector = inspect(conn)

                customer_cols = {
                    c["name"]
                    for c in fresh_inspector.get_columns(
                        "customers"
                    )
                }

                if "last_seen_at" not in customer_cols:

                    conn.execute(
                        text(
                            "ALTER TABLE customers "
                            "ADD COLUMN last_seen_at TIMESTAMP"
                        )
                    )

                    fresh_inspector = inspect(conn)

                    customer_cols = {
                        c["name"]
                        for c in fresh_inspector.get_columns(
                            "customers"
                        )
                    }

                if "last_seen_at" in customer_cols:

                    if "last_contact_at" in customer_cols:

                        conn.execute(
                            text(
                                "UPDATE customers "
                                "SET last_seen_at = "
                                "COALESCE("
                                "last_seen_at, "
                                "last_message_at, "
                                "last_contact_at, "
                                "created_at, "
                                "CURRENT_TIMESTAMP)"
                            )
                        )

                    else:

                        conn.execute(
                            text(
                                "UPDATE customers "
                                "SET last_seen_at = "
                                "COALESCE("
                                "last_seen_at, "
                                "last_message_at, "
                                "created_at, "
                                "CURRENT_TIMESTAMP)"
                            )
                        )

                    if conn.dialect.name == "postgresql":

                        conn.execute(
                            text(
                                "ALTER TABLE customers "
                                "ALTER COLUMN last_seen_at "
                                "SET NOT NULL"
                            )
                        )

            except Exception:
                pass


@app.on_event("startup")
def startup():
    init_database()


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():

    return {
        "system_status": "Online",
        "service": "AI Sales Assistant Tanzania",
        "version": "2.0.0",
    }


@app.get("/health")
def health():

    try:

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "database": "connected",
        }

    except Exception as exc:

        raise HTTPException(
            status_code=503,
            detail=f"Database error: {exc}",
        )


# =========================================================
# AUTH
# =========================================================

@app.post("/auth/signup")
def signup(
    payload: SignupRequest,
    db: Session = Depends(get_db),
):

    email = str(
        payload.email
    ).lower().strip()

    if db.query(Merchant).filter(
        Merchant.email == email
    ).first():

        raise HTTPException(
            status_code=409,
            detail=(
                "Email hii tayari imesajiliwa. "
                "Tumia Login."
            ),
        )

    merchant = Merchant(
        user_id="m_" + uuid.uuid4().hex,
        business_name=payload.business_name.strip(),
        email=email,
        phone_number=payload.phone_number.strip(),
        password_hash=hash_password(
            payload.password
        ),
        language_preference="sw",
        subscription_status="Active",
        plan_code="test",
        messages_used=0,
        created_at=datetime.utcnow(),
    )

    merchant.payment_info = MerchantPaymentInfo()

    db.add(merchant)

    db.commit()

    db.refresh(merchant)

    token = make_token(
        merchant.user_id
    )

    return {
        "token": token,
        "merchant": public_merchant(
            merchant
        ),
    }


@app.post("/auth/login")
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
):

    email = str(
        payload.email
    ).lower().strip()

    merchant = (
        db.query(Merchant)
        .options(
            joinedload(Merchant.payment_info),
            joinedload(Merchant.products),
            joinedload(Merchant.social_connections),
        )
        .filter(
            Merchant.email == email
        )
        .first()
    )

    if (
        not merchant
        or not verify_password(
            payload.password,
            merchant.password_hash,
        )
    ):

        raise HTTPException(
            status_code=401
