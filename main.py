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
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session, joinedload

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
    Order,
    OrderItem,
    Product,
    ProductCreate,
    ProductUpdate,
    ProfileUpdate,
    SessionLocal,
    SignupRequest,
    engine,
)


APP_VERSION = "11.0.0"


app = FastAPI(
    title="AI Sales Assistant Tanzania",
    version=APP_VERSION,
)


cors_raw = os.getenv(
    "CORS_ORIGINS",
    "https://iddialy.github.io",
)

origins = [
    item.strip()
    for item in cors_raw.split(",")
    if item.strip()
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=86400,
)


TOKEN_SECRET = os.getenv("TOKEN_SECRET", "").strip()

if not TOKEN_SECRET:
    TOKEN_SECRET = "dev-only-change-this-token-secret"


TOKEN_TTL = 60 * 60 * 24 * 30


# ============================================================
# DATABASE
# ============================================================

def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


# ============================================================
# PASSWORD SECURITY
# ============================================================

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    rounds = 210_000

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        rounds,
    )

    salt_text = base64.urlsafe_b64encode(
        salt
    ).decode("ascii")

    digest_text = base64.urlsafe_b64encode(
        digest
    ).decode("ascii")

    return (
        f"pbkdf2_sha256"
        f"${rounds}"
        f"${salt_text}"
        f"${digest_text}"
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_text, digest_text = stored.split(
            "$",
            3,
        )

        if algorithm != "pbkdf2_sha256":
            return False

        salt = base64.urlsafe_b64decode(
            salt_text.encode("ascii")
        )

        expected = base64.urlsafe_b64decode(
            digest_text.encode("ascii")
        )

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(rounds),
        )

        return hmac.compare_digest(
            actual,
            expected,
        )

    except Exception:
        return False


# ============================================================
# TOKEN AUTHENTICATION
# ============================================================

def make_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": int(time.time()) + TOKEN_TTL,
    }

    raw = base64.urlsafe_b64encode(
        json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")
    ).decode("ascii").rstrip("=")

    signature = hmac.new(
        TOKEN_SECRET.encode("utf-8"),
        raw.encode("ascii"),
        hashlib.sha256,
    ).digest()

    signature_text = base64.urlsafe_b64encode(
        signature
    ).decode("ascii").rstrip("=")

    return f"{raw}.{signature_text}"


def decode_token(token: str) -> str:
    try:
        raw, signature_text = token.split(
            ".",
            1,
        )

        expected = hmac.new(
            TOKEN_SECRET.encode("utf-8"),
            raw.encode("ascii"),
            hashlib.sha256,
        ).digest()

        supplied = base64.urlsafe_b64decode(
            signature_text
            + "=" * (-len(signature_text) % 4)
        )

        if not hmac.compare_digest(
            expected,
            supplied,
        ):
            raise ValueError("bad signature")

        payload = json.loads(
            base64.urlsafe_b64decode(
                raw
                + "=" * (-len(raw) % 4)
            ).decode("utf-8")
        )

        if int(payload["exp"]) < int(time.time()):
            raise ValueError("expired")

        return str(payload["sub"])

    except Exception:
        raise HTTPException(
            status_code=401,
            detail=(
                "Session imekwisha au si sahihi. "
                "Tafadhali login tena."
            ),
        )


# ============================================================
# PUBLIC SERIALIZERS
# ============================================================

def public_product(product: Product):
    return {
        "product_id": product.product_id,
        "product_name": product.product_name,
        "category": product.category,
        "description": product.description or "",
        "wholesale_price": product.wholesale_price,
        "retail_price": product.retail_price,
        "price": product.retail_price,
        "stock_quantity": product.stock_quantity,
        "status": product.status,
        "image_url": product.image_url,
    }


def public_customer(customer: Customer):
    return {
        "customer_id": customer.customer_id,
        "merchant_id": customer.merchant_id,
        "name": customer.name,
        "phone_number": customer.phone_number,
        "email": customer.email,
        "location": customer.location,
        "platform": customer.platform,
        "created_at": (
            customer.created_at.isoformat()
            if customer.created_at
            else None
        ),
        "last_seen_at": (
            customer.last_seen_at.isoformat()
            if customer.last_seen_at
            else None
        ),
    }


def public_conversation(conversation: Conversation):
    return {
        "conversation_id": conversation.conversation_id,
        "merchant_id": conversation.merchant_id,
        "customer_id": conversation.customer_id,
        "product_id": conversation.product_id,
        "platform": conversation.platform,
        "customer_message": conversation.customer_message,
        "ai_reply": conversation.ai_reply,
        "created_at": (
            conversation.created_at.isoformat()
            if conversation.created_at
            else None
        ),
    }


def public_order(order: Order):
    return {
        "order_id": order.order_id,
        "merchant_id": order.merchant_id,
        "customer_id": order.customer_id,
        "status": order.status,
        "total_amount": order.total_amount,
        "payment_status": order.payment_status,
        "platform": order.platform,
        "created_at": (
            order.created_at.isoformat()
            if order.created_at
            else None
        ),
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "subtotal": item.subtotal,
            }
            for item in order.items
        ],
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

        "products": [
            public_product(product)
            for product in merchant.products
        ],
    }


# ============================================================
# CURRENT MERCHANT
# ============================================================

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

    token = authorization.split(
        " ",
        1,
    )[1].strip()

    user_id = decode_token(token)

    merchant = (
        db.query(Merchant)
        .options(
            joinedload(Merchant.payment_info),
            joinedload(Merchant.products),
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


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

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
            "price": "FLOAT",
        },

        "merchant_payment_info": {
            "merchant_id": "VARCHAR(64)",
            "lipa_namba": "VARCHAR(100)",
            "bank_account": "VARCHAR(200)",
            "phone_payment": "VARCHAR(30)",
        },
    }

    with engine.begin() as connection:

        for table_name, columns in additions.items():

            inspector = inspect(connection)

            if not inspector.has_table(
                table_name
            ):
                continue

            existing = {
                column["name"]
                for column in inspector.get_columns(
                    table_name
                )
            }

            for column_name, definition in columns.items():

                if column_name in existing:
                    continue

                try:

                    connection.execute(
                        text(
                            f'ALTER TABLE "{table_name}" '
                            f'ADD COLUMN "{column_name}" {definition}'
                        )
                    )

                except Exception:
                    pass

        inspector = inspect(connection)

        if inspector.has_table("products"):

            columns = {
                column["name"]
                for column in inspector.get_columns(
                    "products"
                )
            }

            if (
                "price" in columns
                and "retail_price" in columns
            ):

                try:

                    connection.execute(
                        text(
                            "UPDATE products "
                            "SET retail_price = price "
                            "WHERE retail_price IS NULL "
                            "AND price IS NOT NULL"
                        )
                    )

                except Exception:
                    pass


@app.on_event("startup")
def startup():
    init_database()


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "system_status": "Online",
        "service": "AI Sales Assistant Tanzania",
        "version": APP_VERSION,
        "authentication": "enabled",
        "product_management": "enabled",
        "customer_management": "enabled",
        "conversation_tracking": "enabled",
        "orders": "enabled",
        "streaming": "enabled",
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    try:

        with engine.connect() as connection:
            connection.execute(
                text("SELECT 1")
            )

        return {
            "status": "ok",
            "database": "connected",
            "version": APP_VERSION,
        }

    except Exception as exc:

        raise HTTPException(
            status_code=503,
            detail=f"Database error: {exc}",
        )


# ============================================================
# SIGNUP
# ============================================================

@app.post("/auth/signup")
def signup(
    payload: SignupRequest,
    db: Session = Depends(get_db),
):

    email = str(
        payload.email
    ).lower().strip()

    existing = (
        db.query(Merchant)
        .filter(
            Merchant.email == email
        )
        .first()
    )

    if existing:

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

    merchant.payment_info = (
        MerchantPaymentInfo()
    )

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


# ============================================================
# LOGIN
# ============================================================

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
            status_code=401,
            detail="Email au password si sahihi.",
        )

    return {
        "token": make_token(
            merchant.user_id
        ),
        "merchant": public_merchant(
            merchant
        ),
    }


# ============================================================
# ME
# ============================================================

@app.get("/me")
def me(
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    return public_merchant(
        get_current_merchant(
            authorization,
            db,
        )
    )


# ============================================================
# PROFILE
# ============================================================

@app.put("/profile")
def update_profile(
    payload: ProfileUpdate,
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    data = payload.model_dump(
        exclude_unset=True
    )

    payment_fields = {
        "lipa_namba",
        "bank_account",
        "phone_payment",
    }

    for key, value in data.items():

        if key in payment_fields:
            continue

        if hasattr(
            merchant,
            key,
        ):
            setattr(
                merchant,
                key,
                value,
            )

    payment = merchant.payment_info

    if payment is None:

        payment = MerchantPaymentInfo(
            merchant_id=merchant.user_id
        )

        merchant.payment_info = payment

    for key in payment_fields:

        if key in data:

            setattr(
                payment,
                key,
                data[key],
            )

    db.add(merchant)
    db.add(payment)
    db.commit()

    refreshed = (
        db.query(Merchant)
        .options(
            joinedload(Merchant.payment_info),
            joinedload(Merchant.products),
        )
        .filter(
            Merchant.user_id
            == merchant.user_id
        )
        .first()
    )

    return public_merchant(
        refreshed
    )


# ============================================================
# PRODUCTS
# ============================================================

@app.get("/products")
def list_products(
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    return {
        "products": [
            public_product(product)
            for product in merchant.products
        ]
    }


def validate_product_payload(payload):

    if (
        payload.retail_price is None
        and payload.wholesale_price is None
    ):

        raise HTTPException(
            status_code=422,
            detail=(
                "Weka angalau bei ya "
                "rejareja au jumla."
            ),
        )

    if payload.status not in {
        "IPO",
        "IMEISHA",
    }:

        raise HTTPException(
            status_code=422,
            detail=(
                "Status lazima iwe "
                "IPO au IMEISHA."
            ),
        )


@app.post("/products")
def create_product(
    payload: ProductCreate,
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    validate_product_payload(
        payload
    )

    data = payload.model_dump()

    data["legacy_price"] = (
        payload.retail_price
        if payload.retail_price is not None
        else payload.wholesale_price
    )

    product = Product(
        product_id="p_" + uuid.uuid4().hex,
        merchant_id=merchant.user_id,
        **data,
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    return public_product(
        product
    )


@app.put("/products/{product_id}")
def update_product(
    product_id: str,
    payload: ProductUpdate,
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    product = (
        db.query(Product)
        .filter(
            Product.product_id
            == product_id,
            Product.merchant_id
            == merchant.user_id,
        )
        .first()
    )

    if not product:

        raise HTTPException(
            status_code=404,
            detail="Bidhaa haijapatikana.",
        )

    validate_product_payload(
        payload
    )

    data = payload.model_dump()

    data["legacy_price"] = (
        payload.retail_price
        if payload.retail_price is not None
        else payload.wholesale_price
    )

    for key, value in data.items():

        setattr(
            product,
            key,
            value,
        )

    db.commit()
    db.refresh(product)

    return public_product(
        product
    )


@app.delete("/products/{product_id}")
def delete_product(
    product_id: str,
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    product = (
        db.query(Product)
        .filter(
            Product.product_id
            == product_id,
            Product.merchant_id
            == merchant.user_id,
        )
        .first()
    )

    if not product:

        raise HTTPException(
            status_code=404,
            detail="Bidhaa haijapatikana.",
        )

    db.delete(product)
    db.commit()

    return {
        "status": "success",
        "message": "Bidhaa imefutwa.",
    }


# ============================================================
# CUSTOMER HELPERS
# ============================================================

def get_or_create_customer(
    db: Session,
    merchant_id: str,
    platform: str,
    phone_number: str | None = None,
    name: str | None = None,
    email: str | None = None,
    location: str | None = None,
):

    customer = None

    if phone_number:

        customer = (
            db.query(Customer)
            .filter(
                Customer.merchant_id
                == merchant_id,
                Customer.phone_number
                == phone_number,
            )
            .first()
        )

    if customer is None and email:

        customer = (
            db.query(Customer)
            .filter(
                Customer.merchant_id
                == merchant_id,
                Customer.email
                == email,
            )
            .first()
        )

    if customer is None:

        customer = Customer(
            customer_id="c_" + uuid.uuid4().hex,
            merchant_id=merchant_id,
            name=name,
            phone_number=phone_number,
            email=email,
            location=location,
            platform=platform or "website",
            created_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )

        db.add(customer)

    else:

        customer.last_seen_at = datetime.utcnow()

        if name:
            customer.name = name

        if email:
            customer.email = email

        if location:
            customer.location = location

        if platform:
            customer.platform = platform

    return customer


# ============================================================
# CUSTOMERS
# ============================================================

@app.get("/customers")
def list_customers(
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    customers = (
        db.query(Customer)
        .filter(
            Customer.merchant_id
            == merchant.user_id
        )
        .order_by(
            Customer.last_seen_at.desc()
        )
        .all()
    )

    return {
        "customers": [
            public_customer(customer)
            for customer in customers
        ]
    }


@app.get("/customers/{customer_id}")
def get_customer(
    customer_id: str,
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    customer = (
        db.query(Customer)
        .filter(
            Customer.customer_id
            == customer_id,
            Customer.merchant_id
            == merchant.user_id,
        )
        .first()
    )

    if not customer:

        raise HTTPException(
            status_code=404,
            detail="Customer hajapatikana.",
        )

    return public_customer(
        customer
    )


# ============================================================
# CONVERSATIONS
# ============================================================

@app.get("/conversations")
def list_conversations(
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    conversations = (
        db.query(Conversation)
        .filter(
            Conversation.merchant_id
            == merchant.user_id
        )
        .order_by(
            Conversation.created_at.desc()
        )
        .limit(100)
        .all()
    )

    return {
        "conversations": [
            public_conversation(
                conversation
            )
            for conversation in conversations
        ]
    }


@app.get(
    "/customers/{customer_id}/conversations"
)
def customer_conversations(
    customer_id: str,
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    customer = (
        db.query(Customer)
        .filter(
            Customer.customer_id
            == customer_id,
            Customer.merchant_id
            == merchant.user_id,
        )
        .first()
    )

    if not customer:

        raise HTTPException(
            status_code=404,
            detail="Customer hajapatikana.",
        )

    conversations = (
        db.query(Conversation)
        .filter(
            Conversation.merchant_id
            == merchant.user_id,
            Conversation.customer_id
            == customer_id,
        )
        .order_by(
            Conversation.created_at.asc()
        )
        .all()
    )

    return {
        "customer": public_customer(
            customer
        ),
        "conversations": [
            public_conversation(
                conversation
            )
            for conversation in conversations
        ],
    }


# ============================================================
# DASHBOARD METRICS
# ============================================================

@app.get("/dashboard")
def dashboard(
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    merchant_id = merchant.user_id

    total_products = (
        db.query(func.count(Product.product_id))
        .filter(
            Product.merchant_id
            == merchant_id
        )
        .scalar()
        or 0
    )

    total_customers = (
        db.query(func.count(Customer.customer_id))
        .filter(
            Customer.merchant_id
            == merchant_id
        )
        .scalar()
        or 0
    )

    total_conversations = (
        db.query(
            func.count(
                Conversation.conversation_id
            )
        )
        .filter(
            Conversation.merchant_id
            == merchant_id
        )
        .scalar()
        or 0
    )

    total_orders = (
        db.query(
            func.count(Order.order_id)
        )
        .filter(
            Order.merchant_id
            == merchant_id
        )
        .scalar()
        or 0
    )

    pending_orders = (
        db.query(
            func.count(Order.order_id)
        )
        .filter(
            Order.merchant_id
            == merchant_id,
            Order.status == "PENDING",
        )
        .scalar()
        or 0
    )

    paid_orders = (
        db.query(
            func.count(Order.order_id)
        )
        .filter(
            Order.merchant_id
            == merchant_id,
            Order.payment_status == "PAID",
        )
        .scalar()
        or 0
    )

    total_sales = (
        db.query(
            func.coalesce(
                func.sum(Order.total_amount),
                0,
            )
        )
        .filter(
            Order.merchant_id
            == merchant_id,
            Order.payment_status == "PAID",
        )
        .scalar()
        or 0
    )

    low_stock_products = (
        db.query(Product)
        .filter(
            Product.merchant_id
            == merchant_id,
            Product.stock_quantity <= 5,
            Product.status == "IPO",
        )
        .order_by(
            Product.stock_quantity.asc()
        )
        .limit(10)
        .all()
    )

    return {
        "merchant": {
            "user_id": merchant.user_id,
            "business_name": merchant.business_name,
        },

        "metrics": {
            "total_products": total_products,
            "total_customers": total_customers,
            "total_conversations": total_conversations,
            "total_orders": total_orders,
            "pending_orders": pending_orders,
            "paid_orders": paid_orders,
            "total_sales": float(total_sales),
        },

        "low_stock_products": [
            public_product(product)
            for product in low_stock_products
        ],
    }


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
def chat(
    payload: ChatRequest,
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    try:

        reply = generate_ai_sales_response(
            merchant,
            payload.message,
            "website",
        )

        customer = get_or_create_customer(
            db=db,
            merchant_id=merchant.user_id,
            platform="website",
        )

        db.flush()

        conversation = Conversation(
            conversation_id="conv_"
            + uuid.uuid4().hex,

            merchant_id=merchant.user_id,

            customer_id=(
                customer.customer_id
                if customer
                else None
            ),

            platform="website",

            customer_message=payload.message,

            ai_reply=reply,

            created_at=datetime.utcnow(),
        )

        db.add(conversation)

        merchant.messages_used = (
            (merchant.messages_used or 0)
            + 1
        )

        db.commit()

        return {
            "status": "success",
            "reply": reply,
            "conversation_id": (
                conversation.conversation_id
            ),
        }

    except Exception as exc:

        db.rollback()

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )


# ============================================================
# STREAMING CHAT
# ============================================================

@app.post("/chat/stream")
def chat_stream(
    payload: ChatRequest,
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    merchant_id = merchant.user_id

    def generator() -> Generator[
        str,
        None,
        None,
    ]:

        local_db = SessionLocal()

        full_reply = ""

        try:

            fresh = (
                local_db.query(Merchant)
                .options(
                    joinedload(
                        Merchant.payment_info
                    ),
                    joinedload(
                        Merchant.products
                    ),
                )
                .filter(
                    Merchant.user_id
                    == merchant_id
                )
                .first()
            )

            if not fresh:

                yield (
                    "Samahani, "
                    "akaunti haijapatikana."
                )

                return

            for chunk in generate_ai_sales_response_stream(
                fresh,
                payload.message,
                "website",
            ):

                full_reply += chunk

                yield chunk

            customer = get_or_create_customer(
                db=local_db,
                merchant_id=merchant_id,
                platform="website",
            )

            local_db.flush()

            conversation = Conversation(
                conversation_id="conv_"
                + uuid.uuid4().hex,

                merchant_id=merchant_id,

                customer_id=(
                    customer.customer_id
                    if customer
                    else None
                ),

                platform="website",

                customer_message=payload.message,

                ai_reply=full_reply,

                created_at=datetime.utcnow(),
            )

            local_db.add(
                conversation
            )

            fresh.messages_used = (
                (fresh.messages_used or 0)
                + 1
            )

            local_db.commit()

        except Exception as exc:

            local_db.rollback()

            yield (
                "Samahani, AI imepata "
                f"tatizo: {exc}"
            )

        finally:

            local_db.close()

    return StreamingResponse(
        generator(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": (
                "no-cache, no-transform"
            ),
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
# WEBHOOK MESSAGE
# ============================================================

@app.post("/webhook/message")
def webhook_message(
    merchant_id: str,
    platform: str,
    customer_message: str,
    customer_phone: str | None = None,
    customer_name: str | None = None,
    customer_email: str | None = None,
    customer_location: str | None = None,
    db: Session = Depends(get_db),
):

    merchant = (
        db.query(Merchant)
        .options(
            joinedload(
                Merchant.payment_info
            ),
            joinedload(
                Merchant.products
            ),
        )
        .filter(
            Merchant.user_id
            == merchant_id
        )
        .first()
    )

    if not merchant:

        raise HTTPException(
            status_code=404,
            detail=(
                "Mfanyabiashara "
                "hajapatikana."
            ),
        )

    try:

        reply = generate_ai_sales_response(
            merchant,
            customer_message,
            platform,
        )

        customer = get_or_create_customer(
            db=db,
            merchant_id=merchant_id,
            platform=platform,
            phone_number=customer_phone,
            name=customer_name,
            email=customer_email,
            location=customer_location,
        )

        db.flush()

        conversation = Conversation(
            conversation_id="conv_"
            + uuid.uuid4().hex,

            merchant_id=merchant_id,

            customer_id=(
                customer.customer_id
                if customer
                else None
            ),

            platform=platform,

            customer_message=customer_message,

            ai_reply=reply,

            created_at=datetime.utcnow(),
        )

        db.add(conversation)

        merchant.messages_used = (
            (merchant.messages_used or 0)
            + 1
        )

        db.commit()

        return {
            "status": "success",
            "merchant_id": merchant_id,
            "platform": platform,
            "customer_id": (
                customer.customer_id
                if customer
                else None
            ),
            "conversation_id": (
                conversation.conversation_id
            ),
            "customer_message": customer_message,
            "ai_reply": reply,
        }

    except Exception as exc:

        db.rollback()

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )


# ============================================================
# ORDERS
# ============================================================

@app.get("/orders")
def list_orders(
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    orders = (
        db.query(Order)
        .options(
            joinedload(Order.items)
        )
        .filter(
            Order.merchant_id
            == merchant.user_id
        )
        .order_by(
            Order.created_at.desc()
        )
        .limit(100)
        .all()
    )

    return {
        "orders": [
            public_order(order)
            for order in orders
        ]
    }


@app.get("/orders/{order_id}")
def get_order(
    order_id: str,
    authorization: str | None = Header(
        default=None
    ),
    db: Session = Depends(get_db),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    order = (
        db.query(Order)
        .options(
            joinedload(Order.items)
        )
        .filter(
            Order.order_id
            == order_id,
            Order.merchant_id
            == merchant.user_id,
        )
        .first()
    )

    if not order:

        raise HTTPException(
            status_code=404,
            detail="Order haijapatikana.",
        )

    return public_order(
        order
    )


# ============================================================
# CREATE ORDER
# ============================================================

@app.post("/orders")
def create_order(
    customer_id: str | None = None,
    platform: str = "website",
    db: Session = Depends(get_db),
    authorization: str | None = Header(
        default=None
    ),
):

    merchant = get_current_merchant(
        authorization,
        db,
    )

    if customer_id:

        customer = (
            db.query(Customer)
            .filter(
                Customer.customer_id
                == customer_id,
                Customer.merchant_id
                == merchant.user_id,
            )
            .first()
        )

        if not customer:

            raise HTTPException(
                status_code=404,
                detail=(
                    "Customer "
                    "hajapatikana."
                ),
            )

    order = Order(
        order_id="ord_"
        + uuid.uuid4().hex,

        merchant_id=merchant.user_id,

        customer_id=customer_id,

        status="PENDING",

        total_amount=0,

        payment_status="UNPAID",

        platform=platform,

        created_at=datetime.utcnow(),
    )

    db.add(order)
    db.commit()
    db.refresh(order)

    return public_order(
        order
    )
