from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

class Base(DeclarativeBase):
    pass

class Merchant(Base):
    __tablename__ = "merchants"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    language_preference: Mapped[str] = mapped_column(String(5), default="sw")
    subscription_status: Mapped[str] = mapped_column(String(20), default="Pending")
    plan_code: Mapped[str] = mapped_column(String(30), default="none")
    expiry_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    message_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    messages_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    payment_info: Mapped["MerchantPaymentInfo"] = relationship(back_populates="merchant", uselist=False, cascade="all, delete-orphan")
    products: Mapped[list["Product"]] = relationship(back_populates="merchant", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="merchant", cascade="all, delete-orphan")

class MerchantPaymentInfo(Base):
    __tablename__ = "merchant_payment_info"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.user_id"), unique=True)
    lipa_namba: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bank_account: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone_payment: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    merchant: Mapped[Merchant] = relationship(back_populates="payment_info")

class Product(Base):
    __tablename__ = "products"
    product_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.user_id"), index=True)
    product_name: Mapped[str] = mapped_column(String(200))
    price: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text)
    merchant: Mapped[Merchant] = relationship(back_populates="products")

class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.user_id"), index=True)
    reference: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    plan_code: Mapped[str] = mapped_column(String(30))
    amount: Mapped[int] = mapped_column(Integer)
    phone: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(40), default="PENDING")
    checkout_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    merchant: Mapped[Merchant] = relationship(back_populates="payments")

DATABASE_URL = __import__("os").environ.get("DATABASE_URL", "sqlite:///./salesai.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
