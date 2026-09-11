import os
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Merchant(Base):
    __tablename__ = "merchants"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(255))
    language_preference: Mapped[str] = mapped_column(String(5), default="sw")
    subscription_status: Mapped[str] = mapped_column(String(20), default="Active")
    plan_code: Mapped[str] = mapped_column(String(30), default="test")
    expiry_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    message_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    messages_used: Mapped[int] = mapped_column(Integer, default=0)
    business_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    business_hours: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    payment_info: Mapped[Optional["MerchantPaymentInfo"]] = relationship(
        back_populates="merchant",
        uselist=False,
        cascade="all, delete-orphan",
    )
    products: Mapped[List["Product"]] = relationship(
        back_populates="merchant",
        cascade="all, delete-orphan",
    )


class MerchantPaymentInfo(Base):
    __tablename__ = "merchant_payment_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.user_id"),
        unique=True,
        index=True,
    )
    lipa_namba: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bank_account: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone_payment: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    merchant: Mapped[Merchant] = relationship(back_populates="payment_info")


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.user_id"),
        index=True,
    )
    product_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    wholesale_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    retail_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="IPO")
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Compatibility with an older database that may still contain a required
    # `price` column. New code uses retail_price; this field is never exposed.
    legacy_price: Mapped[Optional[float]] = mapped_column(
        "price",
        Float,
        nullable=True,
    )

    merchant: Mapped[Merchant] = relationship(back_populates="products")


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./salesai.db").strip()

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgresql://"):]

connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


class SignupRequest(BaseModel):
    business_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone_number: str = Field(min_length=5, max_length=30)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ProductCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    category: Optional[str] = None
    description: str = ""
    wholesale_price: Optional[float] = Field(default=None, ge=0)
    retail_price: Optional[float] = Field(default=None, ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    status: str = "IPO"
    image_url: Optional[str] = None


class ProductUpdate(ProductCreate):
    pass


class ProfileUpdate(BaseModel):
    business_name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    phone_number: Optional[str] = Field(default=None, min_length=5, max_length=30)
    business_location: Optional[str] = Field(default=None, max_length=255)
    business_type: Optional[str] = Field(default=None, max_length=100)
    business_hours: Optional[str] = Field(default=None, max_length=255)
    business_description: Optional[str] = None
    language_preference: Optional[str] = None
    lipa_namba: Optional[str] = Field(default=None, max_length=100)
    bank_account: Optional[str] = Field(default=None, max_length=200)
    phone_payment: Optional[str] = Field(default=None, max_length=30)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
