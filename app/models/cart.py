from datetime import UTC, datetime
import enum
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from sqlalchemy import Enum as SQLEnum, Time


class Cart(Base):
    __tablename__="carts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    guest_token: Mapped[str] = mapped_column(String(100),nullable=False, unique=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), 
            default=lambda: datetime.now(UTC), 
            onupdate=lambda: datetime.now(UTC)
        )


    user: Mapped["User"] = relationship("User", back_populates="cart")
    items: Mapped[list["CartItem"]] = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")



class CartItem(Base):
    __tablename__ = "cart_items"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cart_id: Mapped[int] = mapped_column(Integer, ForeignKey("carts.id"), index=True)
    product_variant_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("product_variants.id"), 
        index=True, 
        nullable=False
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False)

    product_variant: Mapped["ProductVariant"] = relationship("ProductVariant")
    cart: Mapped[Optional["Cart"]] = relationship("Cart")
