from __future__ import annotations
import enum
from typing import Optional

from pydantic import EmailStr, Field

from app.db.database import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    Boolean,
    Integer, 
    String, 
    ForeignKey, 
    DateTime,
    Enum as SQLEnum,
    Text
)
from datetime import UTC, datetime

from app.models.category import Review
from app.models.order import Cart


class UserTier(str, enum.Enum):
    NEW = 'new'
    SILVER = 'silver'
    GOLD = 'gold'
    RISK = 'risk'


class AdminRole(str, enum.Enum):
    OWNER = 'owner'
    MANAGER = 'manager'
    PACKER = 'packer'


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True,unique=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    tier: Mapped[UserTier] = mapped_column(
        SQLEnum(
            UserTier,
            name="user_tier_enum",
            values_callable=lambda x:[e.value for e in x]
        ),
        default=UserTier.NEW,
        nullable=False
    )

    telegram_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    addresses: Mapped[list["Address"]] = relationship("Address", back_populates="user")
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="user")
    cart: Mapped["Cart"] = relationship("Cart", back_populates="user")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="user")



class OTPCode(Base):
    __tablename__="otp_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True,unique=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(5), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Address(Base):
    __tablename__ = "addresses"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    line: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    lat: Mapped[float] = mapped_column(nullable=False)
    lng: Mapped[float] = mapped_column(nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="addresses")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="address")


class AdminUser(Base):
    __tablename__ = "admin_users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[EmailStr] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AdminRole] = mapped_column(
        SQLEnum(
            AdminRole,
            name="admin_role_enum",
            values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
