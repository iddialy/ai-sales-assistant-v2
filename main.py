import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from datetime import datetime
from typing import Generator

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, joinedload

from ai_engine import generate_ai_sales_response, generate_ai_sales_response_stream
from models import (
    Base, ChatRequest, Conversation, Customer, LoginRequest, Merchant, MerchantPaymentInfo, Product,
    ProductCreate, ProductUpdate, ProfileUpdate, SessionLocal, SignupRequest, engine,
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
        "products": [public_product(p) for p in merchant.products],
    }


def get_current_merchant(authorization: str | None, db: Session) -> Merchant:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization token inahitajika.")
    user_id = decode_token(authorization.split(" ", 1)[1].strip())
    merchant = (
        db.query(Merchant)
        .options(joinedload(Merchant.payment_info), joinedload(Merchant.products))
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
        )
        db.add(customer)
    else:
        customer.last_message_at = datetime.utcnow()
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
            "last_message_at": "TIMESTAMP", "created_at": "TIMESTAMP",
        },
        "conversations": {
            "platform": "VARCHAR(50)", "customer_message": "TEXT", "ai_reply": "TEXT", "created_at": "TIMESTAMP",
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
        .options(joinedload(Merchant.payment_info), joinedload(Merchant.products))
        .filter(Merchant.email == email)
        .first()
    )
    if not merchant or not verify_password(payload.password, merchant.password_hash):
        raise HTTPException(status_code=401, detail="Email au password si sahihi.")
    return {"token": make_token(merchant.user_id), "merchant": public_merchant(merchant)}


@app.get("/me")
def me(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    return public_merchant(get_current_merchant(authorization, db))


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
        customer.last_message_at = datetime.utcnow()
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
                .options(joinedload(Merchant.payment_info), joinedload(Merchant.products))
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
                c.last_message_at = datetime.utcnow()
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

