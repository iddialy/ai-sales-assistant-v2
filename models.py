import os
from datetime import datetime
from typing import Optional, List

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from pydantic import BaseModel, EmailStr, Field


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
        back_populates="merchant", uselist=False, cascade="all, delete-orphan"
    )
    products: Mapped[List["Product"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )
    customers: Mapped[List["Customer"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )
    social_connections: Mapped[List["SocialConnection"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )


class MerchantPaymentInfo(Base):
    __tablename__ = "merchant_payment_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.user_id"), unique=True)
    lipa_namba: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bank_account: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone_payment: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    merchant: Mapped[Merchant] = relationship(back_populates="payment_info")


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.user_id"), index=True)
    product_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    wholesale_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    retail_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="IPO")
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    merchant: Mapped[Merchant] = relationship(back_populates="products")


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.user_id"), index=True)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    platform: Mapped[str] = mapped_column(String(50), default="website")
    external_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    merchant: Mapped[Merchant] = relationship(back_populates="customers")
    conversations: Mapped[List["Conversation"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )


class Conversation(Base):
    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.user_id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    platform: Mapped[str] = mapped_column(String(50), default="website")
    customer_message: Mapped[str] = mapped_column(Text)
    ai_reply: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    customer: Mapped[Customer] = relationship(back_populates="conversations")



class SocialConnection(Base):
    __tablename__ = "social_connections"
    __table_args__ = (UniqueConstraint("merchant_id", "provider", name="uq_social_connection_merchant_provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.user_id"), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    account_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    account_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="CONNECTED")
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    merchant: Mapped[Merchant] = relationship(back_populates="social_connections")


class SubscriptionPayment(Base):
    __tablename__ = "subscription_payments"
    __table_args__ = (UniqueConstraint("payment_reference", name="uq_subscription_payment_reference"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.user_id"), index=True)
    order_reference: Mapped[str] = mapped_column(String(120), index=True)
    payment_reference: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    plan_code: Mapped[str] = mapped_column(String(30))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="TZS")
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    customer_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)



DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./salesai.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgresql://"):]

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


# API schemas
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
    wholesale_price: Optional[float] = None
    retail_price: Optional[float] = None
    stock_quantity: int = Field(default=0, ge=0)
    status: str = "IPO"
    image_url: Optional[str] = None


class ProductUpdate(ProductCreate):
    pass


class ProfileUpdate(BaseModel):
    business_name: Optional[str] = None
    phone_number: Optional[str] = None
    business_location: Optional[str] = None
    business_type: Optional[str] = None
    business_hours: Optional[str] = None
    business_description: Optional[str] = None
    language_preference: Optional[str] = None
    lipa_namba: Optional[str] = None
    bank_account: Optional[str] = None
    phone_payment: Optional[str] = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    customer_key: Optional[str] = Field(default=None, max_length=255)
