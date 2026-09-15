import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from urllib.parse import urlencode, quote
from datetime import datetime
from typing import Generator

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse, HTMLResponse
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, joinedload
from cryptography.fernet import Fernet, InvalidToken

from ai_engine import generate_ai_sales_response, generate_ai_sales_response_stream
from models import (
    Base, ChatRequest, Conversation, Customer, LoginRequest, Merchant, MerchantPaymentInfo, Product,
    ProductCreate, ProductUpdate, ProfileUpdate, SessionLocal, SignupRequest, SubscriptionPayment, SocialConnection, engine,
)

app = FastAPI(title="AI Sales Assistant Tanzania", version="2.0.0")

cors_raw = os.getenv("CORS_ORIGINS", "*")
origins = [x.strip() for x in cors_raw.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOKEN_SECRET = os.getenv("TOKEN_SECRET", "dev-change-this-secret")
TOKEN_TTL = 60 * 60 * 24 * 30


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    rounds = 210_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return f"pbkdf2_sha256${rounds}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_b64, digest_b64 = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def make_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + TOKEN_TTL}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(TOKEN_SECRET.encode(), raw.encode(), hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{raw}.{signature}"


def decode_token(token: str) -> str:
    try:
        raw, signature = token.split(".", 1)
        expected = hmac.new(TOKEN_SECRET.encode(), raw.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode())
        if int(payload["exp"]) < int(time.time()):
            raise ValueError
        return str(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Session imekwisha au si sahihi. Tafadhali login tena.")


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


SOCIAL_FRONTEND_URL = os.getenv("SOCIAL_FRONTEND_URL", "https://iddialy.github.io/ai-sales-assistant-v2/")
SOCIAL_STATE_TTL = 10 * 60


def _social_cipher():
    raw = os.getenv("SOCIAL_TOKEN_ENCRYPTION_KEY", "").strip()
    if raw:
        try:
            return Fernet(raw.encode())
        except Exception:
            pass
    key = base64.urlsafe_b64encode(hashlib.sha256(TOKEN_SECRET.encode("utf-8")).digest())
    return Fernet(key)


def _encrypt_social_token(value: str | None) -> str | None:
    if not value:
        return None
    return _social_cipher().encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt_social_token(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _social_cipher().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def _make_social_state(merchant_id: str, provider: str) -> str:
    payload = {"merchant_id": merchant_id, "provider": provider, "exp": int(time.time()) + SOCIAL_STATE_TTL, "nonce": secrets.token_urlsafe(12)}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(TOKEN_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def _read_social_state(state: str) -> dict:
    try:
        raw, sig = state.split(".", 1)
        expected = hmac.new(TOKEN_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode())
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError
        if payload.get("provider") not in {"whatsapp", "facebook", "instagram", "tiktok"}:
            raise ValueError
        return payload
    except Exception:
        raise HTTPException(400, "Social connection request si sahihi au ime-expire.")


def _social_public(c: SocialConnection):
    return {
        "provider": c.provider,
        "account_name": c.account_name,
        "account_id": c.account_id,
        "status": c.status,
        "connected": c.status == "CONNECTED",
        "token_expires_at": c.token_expires_at.isoformat() if c.token_expires_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _social_config_error(provider: str):
    if provider in {"whatsapp", "facebook", "instagram"}:
        if not os.getenv("META_APP_ID") or not os.getenv("META_APP_SECRET"):
            return "Meta App ID/Secret hazijawekwa kwenye Render."
    if provider == "tiktok":
        if not os.getenv("TIKTOK_CLIENT_KEY") or not os.getenv("TIKTOK_CLIENT_SECRET"):
            return "TikTok Client Key/Secret hazijawekwa kwenye Render."
    return None

def public_merchant(merchant: Merchant):
    payment = merchant.payment_info
    return {
        "user_id": merchant.user_id,
        "business_name": merchant.business_name,
        "email": merchant.email,
        "phone_number": merchant.phone_number,
        "language_preference": merchant.language_preference,
        "subscription_status": merchant.subscription_status,
        "plan_code": merchant.plan_code,
        "expiry_date": merchant.expiry_date.isoformat() if merchant.expiry_date else None,
        "message_limit": merchant.message_limit,
        "messages_used": merchant.messages_used,
        "business_location": merchant.business_location,
        "business_type": merchant.business_type,
        "business_hours": merchant.business_hours,
        "business_description": merchant.business_description,
        "payment_info": {
            "lipa_namba": payment.lipa_namba if payment else None,
            "bank_account": payment.bank_account if payment else None,
            "phone_payment": payment.phone_payment if payment else None,
        },
        "social_connections": [_social_public(c) for c in merchant.social_connections],
        "products": [public_product(p) for p in merchant.products],
    }


def get_current_merchant(authorization: str | None, db: Session) -> Merchant:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization token inahitajika.")
    user_id = decode_token(authorization.split(" ", 1)[1].strip())
    merchant = (
        db.query(Merchant)
        .options(joinedload(Merchant.payment_info), joinedload(Merchant.products), joinedload(Merchant.social_connections))
        .filter(Merchant.user_id == user_id)
        .first()
    )
    if not merchant:
        raise HTTPException(status_code=401, detail="Akaunti haijapatikana.")
    return merchant


def public_customer(c: Customer):
    return {
        "customer_id": c.customer_id,
        "name": c.name,
        "phone": c.phone,
        "email": c.email,
        "platform": c.platform,
        "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
        "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }

def public_conversation(c: Conversation):
    return {
        "conversation_id": c.conversation_id,
        "customer_id": c.customer_id,
        "platform": c.platform,
        "customer_message": c.customer_message,
        "ai_reply": c.ai_reply,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }

def get_or_create_customer(db: Session, merchant_id: str, customer_key: str | None, platform: str = "website") -> Customer:
    key = (customer_key or "").strip()
    customer = None
    if key:
        customer = (db.query(Customer)
            .filter(Customer.merchant_id == merchant_id, Customer.platform == platform, Customer.external_key == key)
            .first())
    if not customer:
        customer = Customer(
            customer_id="c_" + uuid.uuid4().hex,
            merchant_id=merchant_id,
            name="Website Customer" if platform == "website" else f"{platform} Customer",
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

def init_database():
    Base.metadata.create_all(bind=engine)
    # Add columns needed by this version when an older table already exists.
    additions = {
        "merchants": {
            "password_hash": "VARCHAR(255)", "language_preference": "VARCHAR(5)",
            "subscription_status": "VARCHAR(20)", "plan_code": "VARCHAR(30)",
            "expiry_date": "TIMESTAMP", "message_limit": "INTEGER", "messages_used": "INTEGER DEFAULT 0",
            "business_location": "VARCHAR(255)", "business_type": "VARCHAR(100)",
            "business_hours": "VARCHAR(255)", "business_description": "TEXT", "created_at": "TIMESTAMP",
        },
        "products": {
            "category": "VARCHAR(100)", "wholesale_price": "FLOAT", "retail_price": "FLOAT",
            "stock_quantity": "INTEGER DEFAULT 0", "status": "VARCHAR(20)", "image_url": "TEXT",
        },
        "customers": {
            "name": "VARCHAR(200)", "phone": "VARCHAR(50)", "email": "VARCHAR(320)",
            "platform": "VARCHAR(50)", "external_key": "VARCHAR(255)",
            "last_message_at": "TIMESTAMP", "last_seen_at": "TIMESTAMP", "created_at": "TIMESTAMP",
        },
        "conversations": {
            "platform": "VARCHAR(50)", "customer_message": "TEXT", "ai_reply": "TEXT", "created_at": "TIMESTAMP",
        },
        "social_connections": {
            "merchant_id": "VARCHAR(64)", "provider": "VARCHAR(30)", "account_name": "VARCHAR(255)",
            "account_id": "VARCHAR(255)", "status": "VARCHAR(30)", "access_token_encrypted": "TEXT",
            "refresh_token_encrypted": "TEXT", "token_expires_at": "TIMESTAMP", "created_at": "TIMESTAMP",
            "updated_at": "TIMESTAMP",
        },
    }
    with engine.begin() as conn:
        inspector = inspect(conn)
        for table, cols in additions.items():
            if not inspector.has_table(table):
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, definition in cols.items():
                if name not in existing:
                    try:
                        conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {definition}'))
                    except Exception:
                        pass
        if inspector.has_table("products"):
            try:
                conn.execute(text("UPDATE products SET retail_price = price WHERE retail_price IS NULL AND price IS NOT NULL"))
            except Exception:
                pass

        # Customer schema compatibility: older deployments used last_contact_at,
        # while the current model uses last_message_at. Keep the database usable
        # across upgrades and preserve existing timestamps when possible.
        if inspector.has_table("customers"):
            try:
                fresh_inspector = inspect(conn)
                customer_cols = {c["name"] for c in fresh_inspector.get_columns("customers")}
                if "last_message_at" in customer_cols and "last_contact_at" in customer_cols:
                    conn.execute(text(
                        "UPDATE customers SET last_message_at = COALESCE(last_message_at, last_contact_at)"
                    ))

                # The production customers table already has last_seen_at as a
                # NOT NULL column. Make sure older rows and newly-created rows
                # always receive a value before Customer is queried/inserted.
                fresh_inspector = inspect(conn)
                customer_cols = {c["name"] for c in fresh_inspector.get_columns("customers")}
                if "last_seen_at" not in customer_cols:
                    conn.execute(text("ALTER TABLE customers ADD COLUMN last_seen_at TIMESTAMP"))
                    fresh_inspector = inspect(conn)
                    customer_cols = {c["name"] for c in fresh_inspector.get_columns("customers")}
                if "last_seen_at" in customer_cols:
                    conn.execute(text(
                        "UPDATE customers SET last_seen_at = COALESCE(last_seen_at, last_message_at, last_contact_at, created_at, CURRENT_TIMESTAMP)"
                    ))
                    # PostgreSQL is the production database. Enforce NOT NULL
                    # only after all existing rows have been backfilled.
                    if conn.dialect.name == "postgresql":
                        conn.execute(text("ALTER TABLE customers ALTER COLUMN last_seen_at SET NOT NULL"))
            except Exception:
                pass


@app.on_event("startup")
def startup():
    init_database()


@app.get("/")
def root():
    return {"system_status": "Online", "service": "AI Sales Assistant Tanzania", "version": "2.0.0"}


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {exc}")


@app.post("/auth/signup")
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    email = str(payload.email).lower().strip()
    if db.query(Merchant).filter(Merchant.email == email).first():
        raise HTTPException(status_code=409, detail="Email hii tayari imesajiliwa. Tumia Login.")
    merchant = Merchant(
        user_id="m_" + uuid.uuid4().hex,
        business_name=payload.business_name.strip(),
        email=email,
        phone_number=payload.phone_number.strip(),
        password_hash=hash_password(payload.password),
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
    token = make_token(merchant.user_id)
    return {"token": token, "merchant": public_merchant(merchant)}


@app.post("/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = str(payload.email).lower().strip()
    merchant = (
        db.query(Merchant)
        .options(joinedload(Merchant.payment_info), joinedload(Merchant.products), joinedload(Merchant.social_connections))
        .filter(Merchant.email == email)
        .first()
    )
    if not merchant or not verify_password(payload.password, merchant.password_hash):
        raise HTTPException(status_code=401, detail="Email au password si sahihi.")
    return {"token": make_token(merchant.user_id), "merchant": public_merchant(merchant)}


@app.get("/me")
def me(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    return public_merchant(get_current_merchant(authorization, db))


def _create_clickpesa_checkout(merchant: Merchant, plan_code: str, db: Session):
    api_token = os.getenv("CLICKPESA_API_TOKEN", "").strip()
    if not api_token:
        raise HTTPException(503, detail="ClickPesa API token haijawekwa kwenye Render Environment Variables.")

    checksum_key = os.getenv("CLICKPESA_CHECKSUM_KEY", "").strip()
    if not checksum_key:
        raise HTTPException(503, detail="CLICKPESA_CHECKSUM_KEY haijawekwa kwenye Render Environment Variables.")

    plans = {"daily": (2000, "1-day Sales Assistant subscription"), "monthly": (50000, "30-day Sales Assistant subscription")}
    if plan_code not in plans:
        raise HTTPException(422, detail="Kifurushi hakitambuliki.")

    amount, description = plans[plan_code]
    order_reference = f"SUB|{merchant.user_id}|{plan_code}"
    # Make every attempt unique while keeping the plan/merchant reference parseable.
    order_reference = f"{order_reference}|{uuid.uuid4().hex[:10]}"

    payload = {
        "totalPrice": str(amount),
        "orderReference": order_reference,
        "orderCurrency": "TZS",
        "customerName": merchant.business_name,
        "customerEmail": merchant.email,
        "customerPhone": merchant.phone_number.replace("+", "").replace(" ", ""),
        "description": description,
    }
    canonical = _canonicalize_payload(payload)
    serialized = json.dumps(canonical, separators=(",", ":"), ensure_ascii=False)
    payload["checksum"] = hmac.new(checksum_key.encode("utf-8"), serialized.encode("utf-8"), hashlib.sha256).hexdigest()

    # Keep a local pending record so the webhook can reconcile the real payment reference.
    db.add(SubscriptionPayment(
        merchant_id=merchant.user_id,
        order_reference=order_reference,
        payment_reference="PENDING:" + uuid.uuid4().hex,
        plan_code=plan_code,
        amount=amount,
        currency="TZS",
        status="PENDING",
        customer_phone=merchant.phone_number,
    ))
    db.commit()

    req = UrlRequest(
        "https://api.clickpesa.com/third-parties/checkout-link/generate-checkout-url",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(502, detail=f"ClickPesa checkout error: {detail[:500]}")
    except URLError as exc:
        raise HTTPException(502, detail=f"ClickPesa haijafikika: {exc.reason}")

    checkout_link = result.get("checkoutLink")
    if not checkout_link:
        raise HTTPException(502, detail="ClickPesa haikurudisha checkoutLink.")
    return {"checkoutLink": checkout_link, "orderReference": order_reference, "planCode": plan_code, "amount": amount}


@app.post("/payments/clickpesa/checkout")
def create_clickpesa_checkout(payload: dict, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    merchant = get_current_merchant(authorization, db)
    plan_code = str(payload.get("plan_code") or "").strip().lower()
    return _create_clickpesa_checkout(merchant, plan_code, db)


@app.get("/social/connections")
def list_social_connections(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    merchant = get_current_merchant(authorization, db)
    rows = db.query(SocialConnection).filter(SocialConnection.merchant_id == merchant.user_id).all()
    return {"connections": [_social_public(c) for c in rows]}


@app.get("/social/connect/{provider}")
def social_connect(provider: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    merchant = get_current_merchant(authorization, db)
    provider = provider.lower().strip()
    if provider not in {"whatsapp", "facebook", "instagram", "tiktok"}:
        raise HTTPException(422, "Social network haijatambuliwa.")
    config_error = _social_config_error(provider)
    if config_error:
        raise HTTPException(503, config_error)
    state = _make_social_state(merchant.user_id, provider)
    if provider in {"whatsapp", "facebook", "instagram"}:
        redirect_uri = os.getenv("META_REDIRECT_URI", "").strip()
        if not redirect_uri:
            raise HTTPException(503, "META_REDIRECT_URI haijawekwa kwenye Render.")
        scope = "pages_show_list,pages_read_engagement,pages_manage_metadata,pages_messaging,instagram_basic,instagram_manage_messages,business_management,whatsapp_business_management,whatsapp_business_messaging"
        params = {"client_id": os.getenv("META_APP_ID"), "redirect_uri": redirect_uri, "state": state, "response_type": "code", "scope": scope}
        return {"authUrl": "https://www.facebook.com/dialog/oauth?" + urlencode(params)}
    redirect_uri = os.getenv("TIKTOK_REDIRECT_URI", "").strip()
    if not redirect_uri:
        raise HTTPException(503, "TIKTOK_REDIRECT_URI haijawekwa kwenye Render.")
    params = {"client_key": os.getenv("TIKTOK_CLIENT_KEY"), "redirect_uri": redirect_uri, "state": state, "response_type": "code", "scope": "user.info.basic"}
    return {"authUrl": "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(params)}


@app.get("/social/callback/meta")
def social_callback_meta(code: str | None = None, state: str | None = None, error: str | None = None, error_description: str | None = None, db: Session = Depends(get_db)):
    if error:
        return RedirectResponse(f"{SOCIAL_FRONTEND_URL}?social_error={quote(str(error_description or error))}")
    if not code or not state:
        return RedirectResponse(f"{SOCIAL_FRONTEND_URL}?social_error=Meta%20callback%20haijakamilika")
    try:
        st = _read_social_state(state)
        if st["provider"] not in {"whatsapp", "facebook", "instagram"}:
            raise ValueError
        redirect_uri = os.getenv("META_REDIRECT_URI", "").strip()
        token_url = "https://graph.facebook.com/oauth/access_token?" + urlencode({"client_id": os.getenv("META_APP_ID"), "client_secret": os.getenv("META_APP_SECRET"), "redirect_uri": redirect_uri, "code": code})
        with urlopen(UrlRequest(token_url, method="GET"), timeout=25) as response:
            token_data = json.loads(response.read().decode("utf-8"))
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("Meta haikutoa access token.")
        me_url = "https://graph.facebook.com/me?fields=id,name&access_token=" + urlencode({"x":access_token})[2:]
        with urlopen(UrlRequest(me_url, method="GET"), timeout=25) as response:
            me = json.loads(response.read().decode("utf-8"))
        row = db.query(SocialConnection).filter(SocialConnection.merchant_id == st["merchant_id"], SocialConnection.provider == st["provider"]).first()
        if not row:
            row = SocialConnection(merchant_id=st["merchant_id"], provider=st["provider"])
            db.add(row)
        row.account_name = me.get("name") or f"{st['provider'].title()} account"
        row.account_id = str(me.get("id") or "")
        row.status = "CONNECTED"
        row.access_token_encrypted = _encrypt_social_token(access_token)
        row.token_expires_at = None
        row.updated_at = datetime.utcnow()
        db.commit()
        return RedirectResponse(f"{SOCIAL_FRONTEND_URL}?social_connected={st['provider']}")
    except Exception as exc:
        return RedirectResponse(f"{SOCIAL_FRONTEND_URL}?social_error={quote(str(exc)[:180])}")


@app.get("/social/callback/tiktok")
def social_callback_tiktok(code: str | None = None, state: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    if error:
        return RedirectResponse(f"{SOCIAL_FRONTEND_URL}?social_error={quote(str(error))}")
    if not code or not state:
        return RedirectResponse(f"{SOCIAL_FRONTEND_URL}?social_error=TikTok%20callback%20haijakamilika")
    try:
        st = _read_social_state(state)
        if st["provider"] != "tiktok":
            raise ValueError
        redirect_uri = os.getenv("TIKTOK_REDIRECT_URI", "").strip()
        body = urlencode({"client_key": os.getenv("TIKTOK_CLIENT_KEY"), "client_secret": os.getenv("TIKTOK_CLIENT_SECRET"), "code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri}).encode()
        req = UrlRequest("https://open.tiktokapis.com/v2/oauth/token/", data=body, headers={"Content-Type":"application/x-www-form-urlencoded"}, method="POST")
        with urlopen(req, timeout=25) as response:
            token_data = json.loads(response.read().decode("utf-8"))
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError(token_data.get("error_description") or "TikTok haikutoa access token.")
        display_name = None
        open_id = token_data.get("open_id")
        try:
            profile_req = UrlRequest("https://open.tiktokapis.com/v2/user/info/?fields=display_name,open_id", headers={"Authorization": f"Bearer {access_token}"}, method="GET")
            with urlopen(profile_req, timeout=25) as response:
                profile = json.loads(response.read().decode("utf-8"))
            data = profile.get("data", {}).get("user", {})
            display_name = data.get("display_name")
            open_id = data.get("open_id") or open_id
        except Exception:
            pass
        row = db.query(SocialConnection).filter(SocialConnection.merchant_id == st["merchant_id"], SocialConnection.provider == "tiktok").first()
        if not row:
            row = SocialConnection(merchant_id=st["merchant_id"], provider="tiktok")
            db.add(row)
        row.account_name = display_name or "TikTok account"
        row.account_id = str(open_id or "")
        row.status = "CONNECTED"
        row.access_token_encrypted = _encrypt_social_token(access_token)
        refresh_token = token_data.get("refresh_token")
        row.refresh_token_encrypted = _encrypt_social_token(refresh_token)
        expires_in = token_data.get("expires_in")
        row.token_expires_at = datetime.utcnow() if not expires_in else datetime.utcnow() + __import__("datetime").timedelta(seconds=int(expires_in))
        row.updated_at = datetime.utcnow()
        db.commit()
        return RedirectResponse(f"{SOCIAL_FRONTEND_URL}?social_connected=tiktok")
    except Exception as exc:
        return RedirectResponse(f"{SOCIAL_FRONTEND_URL}?social_error={quote(str(exc)[:180])}")


@app.delete("/social/connections/{provider}")
def disconnect_social(provider: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    merchant = get_current_merchant(authorization, db)
    row = db.query(SocialConnection).filter(SocialConnection.merchant_id == merchant.user_id, SocialConnection.provider == provider.lower().strip()).first()
    if not row:
        raise HTTPException(404, "Account haija-connectiwa.")
    db.delete(row)
    db.commit()
    return {"ok": True, "provider": provider}


@app.put("/profile")
def update_profile(payload: ProfileUpdate, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    merchant = get_current_merchant(authorization, db)
    data = payload.model_dump(exclude_unset=True)
    payment_fields = {"lipa_namba", "bank_account", "phone_payment"}
    for key, value in data.items():
        if key in payment_fields:
            continue
        if value is not None and hasattr(merchant, key):
            setattr(merchant, key, value)
    payment = merchant.payment_info or MerchantPaymentInfo(merchant_id=merchant.user_id)
    for key in payment_fields:
        if key in data:
            setattr(payment, key, data[key])
    merchant.payment_info = payment
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    return public_merchant(merchant)


@app.get("/products")
def list_products(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    merchant = get_current_merchant(authorization, db)
    return {"products": [public_product(p) for p in merchant.products]}


@app.post("/products")
def create_product(payload: ProductCreate, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    merchant = get_current_merchant(authorization, db)
    if payload.retail_price is None and payload.wholesale_price is None:
        raise HTTPException(status_code=422, detail="Weka angalau bei ya rejareja au jumla.")
    if payload.status not in {"IPO", "IMEISHA"}:
        raise HTTPException(status_code=422, detail="Status lazima iwe IPO au IMEISHA.")
    product = Product(product_id="p_" + uuid.uuid4().hex, merchant_id=merchant.user_id, **payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return public_product(product)


@app.put("/products/{product_id}")
def update_product(product_id: str, payload: ProductUpdate, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    merchant = get_current_merchant(authorization, db)
    product = db.query(Product).filter(Product.product_id == product_id, Product.merchant_id == merchant.user_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Bidhaa haijapatikana.")
    if payload.status not in {"IPO", "IMEISHA"}:
        raise HTTPException(status_code=422, detail="Status lazima iwe IPO au IMEISHA.")
    for key, value in payload.model_dump().items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return public_product(product)


@app.delete("/products/{product_id}")
def delete_product(product_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    merchant = get_current_merchant(authorization, db)
    product = db.query(Product).filter(Product.product_id == product_id, Product.merchant_id == merchant.user_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Bidhaa haijapatikana.")
    db.delete(product)
    db.commit()
    return {"status": "success", "message": "Bidhaa imefutwa."}


@app.get("/customers")
def list_customers(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    merchant = get_current_merchant(authorization, db)
    customers = (db.query(Customer)
        .filter(Customer.merchant_id == merchant.user_id)
        .order_by(Customer.last_message_at.desc())
        .all())
    return {"customers": [public_customer(c) for c in customers]}

@app.get("/customers/{customer_id}/conversations")
def customer_conversations(customer_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    merchant = get_current_merchant(authorization, db)
    customer = (db.query(Customer)
        .filter(Customer.customer_id == customer_id, Customer.merchant_id == merchant.user_id)
        .first())
    if not customer:
        raise HTTPException(status_code=404, detail="Customer hajapatikana.")
    conversations = (db.query(Conversation)
        .filter(Conversation.customer_id == customer_id, Conversation.merchant_id == merchant.user_id)
        .order_by(Conversation.created_at.asc())
        .all())
    return {"customer": public_customer(customer), "conversations": [public_conversation(c) for c in conversations]}

@app.post("/chat")
def chat(payload: ChatRequest, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    merchant = get_current_merchant(authorization, db)
    customer = get_or_create_customer(db, merchant.user_id, payload.customer_key, "website")
    try:
        reply = generate_ai_sales_response(merchant, payload.message, "website")
        now = datetime.utcnow()
        customer.last_message_at = now
        customer.last_seen_at = now
        db.add(Conversation(
            conversation_id="cv_" + uuid.uuid4().hex,
            merchant_id=merchant.user_id,
            customer_id=customer.customer_id,
            platform="website",
            customer_message=payload.message,
            ai_reply=reply,
        ))
        merchant.messages_used = (merchant.messages_used or 0) + 1
        db.commit()
        return {"status": "success", "reply": reply, "customer_id": customer.customer_id}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/chat/stream")
def chat_stream(payload: ChatRequest, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    merchant = get_current_merchant(authorization, db)
    customer = get_or_create_customer(db, merchant.user_id, payload.customer_key, "website")
    customer_id = customer.customer_id
    merchant_id = merchant.user_id
    message = payload.message
    db.commit()

    def generator():
        result_parts = []
        local_db = SessionLocal()
        try:
            fresh = (local_db.query(Merchant)
                .options(joinedload(Merchant.payment_info), joinedload(Merchant.products), joinedload(Merchant.social_connections))
                .filter(Merchant.user_id == merchant_id).first())
            if not fresh:
                yield "Samahani, akaunti haijapatikana."
                return
            for chunk in generate_ai_sales_response_stream(fresh, message, "website"):
                result_parts.append(chunk)
                yield chunk
            reply = "".join(result_parts)
            c = local_db.query(Customer).filter(Customer.customer_id == customer_id).first()
            if c:
                now = datetime.utcnow()
                c.last_message_at = now
                c.last_seen_at = now
            local_db.add(Conversation(
                conversation_id="cv_" + uuid.uuid4().hex,
                merchant_id=merchant_id,
                customer_id=customer_id,
                platform="website",
                customer_message=message,
                ai_reply=reply,
            ))
            m = local_db.query(Merchant).filter(Merchant.user_id == merchant_id).first()
            if m:
                m.messages_used = (m.messages_used or 0) + 1
            local_db.commit()
        except Exception as exc:
            local_db.rollback()
            yield f"\n[ERROR] {exc}"
        finally:
            local_db.close()
    return StreamingResponse(generator(), media_type="text/plain; charset=utf-8", headers={"Cache-Control": "no-cache"})


def _canonicalize_payload(value):
    if isinstance(value, dict):
        return {key: _canonicalize_payload(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonicalize_payload(item) for item in value]
    return value


def _validate_clickpesa_checksum(payload: dict) -> bool:
    checksum_key = os.getenv("CLICKPESA_CHECKSUM_KEY", "").strip()
    if not checksum_key:
        return True
    received = str(payload.get("checksum") or "").strip()
    if not received:
        return False
    body = {k: v for k, v in payload.items() if k not in {"checksum", "checksumMethod"}}
    canonical = _canonicalize_payload(body)
    serialized = json.dumps(canonical, separators=(",", ":"), ensure_ascii=False)
    computed = hmac.new(checksum_key.encode("utf-8"), serialized.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, received)


def _plan_from_payment(amount: float):
    if abs(amount - 2000) < 0.01:
        return "daily", 1
    if abs(amount - 50000) < 0.01:
        return "monthly", 30
    return None, None


@app.post("/webhook/clickpesa/payment-received")
async def clickpesa_payment_received(payload: dict, db: Session = Depends(get_db)):
    if not _validate_clickpesa_checksum(payload):
        raise HTTPException(status_code=401, detail="Invalid ClickPesa checksum.")

    event = str(payload.get("event") or "").strip().upper()
    data = payload.get("data") or {}
    status = str(data.get("status") or "").strip().upper()
    if event != "PAYMENT RECEIVED" or status != "SUCCESS":
        return {"status": "ignored"}

    order_reference = str(data.get("orderReference") or "").strip()
    payment_reference = str(data.get("paymentReference") or data.get("id") or "").strip()
    currency = str(data.get("collectedCurrency") or "TZS").strip().upper()
    try:
        amount = float(data.get("collectedAmount") or 0)
    except (TypeError, ValueError):
        amount = 0

    if not order_reference or not payment_reference or currency != "TZS":
        raise HTTPException(status_code=400, detail="Incomplete ClickPesa payment payload.")

    parts = order_reference.split("|")
    if len(parts) < 3 or parts[0] != "SUB":
        raise HTTPException(status_code=400, detail="Invalid subscription order reference.")

    merchant_id, requested_plan = parts[1], parts[2].lower()
    plan_code, days = _plan_from_payment(amount)
    if not plan_code or requested_plan != plan_code:
        raise HTTPException(status_code=400, detail="Payment amount does not match subscription plan.")

    merchant = db.query(Merchant).filter(Merchant.user_id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found.")

    existing = db.query(SubscriptionPayment).filter(SubscriptionPayment.payment_reference == payment_reference).first()
    if existing:
        return {"status": "already_processed", "payment_reference": payment_reference}

    pending = (db.query(SubscriptionPayment)
               .filter(SubscriptionPayment.order_reference == order_reference, SubscriptionPayment.merchant_id == merchant.user_id, SubscriptionPayment.status == "PENDING")
               .order_by(SubscriptionPayment.id.desc()).first())

    from datetime import timedelta
    now = datetime.utcnow()
    current_expiry = merchant.expiry_date
    expiry = (current_expiry + timedelta(days=days)) if current_expiry and current_expiry > now else (now + timedelta(days=days))

    merchant.subscription_status = "Active"
    merchant.plan_code = plan_code
    merchant.expiry_date = expiry
    merchant.message_limit = None

    customer = data.get("customer") or {}
    if pending:
        pending.payment_reference = payment_reference
        pending.plan_code = plan_code
        pending.amount = amount
        pending.currency = currency
        pending.status = "SUCCESS"
        pending.customer_phone = str(customer.get("customerPhoneNumber") or "").strip() or pending.customer_phone
        pending.paid_at = now
    else:
        db.add(SubscriptionPayment(
            merchant_id=merchant.user_id,
            order_reference=order_reference,
            payment_reference=payment_reference,
            plan_code=plan_code,
            amount=amount,
            currency=currency,
            status="SUCCESS",
            customer_phone=str(customer.get("customerPhoneNumber") or "").strip() or None,
            paid_at=now,
        ))
    db.commit()

    return {
        "status": "success",
        "payment_reference": payment_reference,
        "merchant_id": merchant.user_id,
        "plan_code": plan_code,
        "expiry_date": merchant.expiry_date.isoformat() if merchant.expiry_date else None,
    }

@app.post("/webhook/message")
def webhook_message(merchant_id: str, platform: str, customer_message: str, customer_key: str | None = None, db: Session = Depends(get_db)):
    merchant = db.query(Merchant).options(joinedload(Merchant.payment_info), joinedload(Merchant.products)).filter(Merchant.user_id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Mfanyabiashara hajapatikana.")
    try:
        reply = generate_ai_sales_response(merchant, customer_message, platform)
        customer = get_or_create_customer(db, merchant_id, customer_key, platform)
        db.add(Conversation(
            conversation_id="cv_" + uuid.uuid4().hex,
            merchant_id=merchant_id,
            customer_id=customer.customer_id,
            platform=platform,
            customer_message=customer_message,
            ai_reply=reply,
        ))
        merchant.messages_used = (merchant.messages_used or 0) + 1
        db.commit()
        return {"status": "success", "merchant_id": merchant_id, "platform": platform, "customer_message": customer_message, "ai_reply": reply, "customer_id": customer.customer_id}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc))

