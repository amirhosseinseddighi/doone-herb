from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.order import Order
from app.db.database import Base


class Category(Base):
    __tablename__ = "categories"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tint_color: Mapped[str] = mapped_column(String(7), nullable=False)
    dot_color: Mapped[str] = mapped_column(String(7), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    is_deleted: Mapped[bool] = mapped_column(
            Boolean, 
            default=False, 
            nullable=False, 
            server_default="false", 
            index=True
        )

    products: Mapped[list["Product"]] = relationship("Product", back_populates="category")



class Product(Base):
    __tablename__ = "products"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, unique=True)
    slug: Mapped[str] = mapped_column(String(300), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    keyword_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(UTC), 
        onupdate=lambda: datetime.now(UTC)
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        nullable=False, 
        server_default="false", 
        index=True
    )

    category: Mapped["Category"] = relationship("Category", back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship("ProductVariant", back_populates="product")

    images: Mapped[list["ProductImage"]] = relationship(
        "ProductImage", 
        back_populates="product",
        cascade="all, delete-orphan"
    )
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="product")
    order_items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="product")



class ProductVariant(Base):
    __tablename__ = "product_variants"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    compare_at_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stock_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    product: Mapped["Product"] = relationship("Product", back_populates="variants")
    offers: Mapped[list["Offer"]] = relationship("Offer", back_populates="product_variant")
    order_items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="product_variant")
    

class ProductImage(Base):
    __tablename__ = "product_images"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


    product: Mapped["Product"] = relationship("Product", back_populates="images")


class Offer(Base):
    __tablename__ = "offers"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_variant_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("product_variants.id"), 
        nullable=False, 
        index=True
    )
    badge_label: Mapped[str] = mapped_column(String(100), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product_variant: Mapped["ProductVariant"] = relationship(
        "ProductVariant",
        back_populates="offers"
    )


class Review(Base):
    __tablename__ = "reviews"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    order_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    admin_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(UTC), 
        nullable=False, 
        index=True
    )


    product: Mapped["Product"] = relationship("Product", back_populates="reviews")
    user: Mapped["User"] = relationship("User", back_populates="reviews")
    order: Mapped[Optional["Order"]] = relationship("Order", back_populates="reviews")