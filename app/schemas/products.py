from __future__ import annotations
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from app.schemas.categories import CategoryResponse



class OfferResponse(BaseModel):

    id: int
    badge_label: str
    starts_at: datetime
    ends_at: datetime



   
class ProductResponse(BaseModel):

    id: int
    name: str
    slug: str
    category: CategoryResponse
    description: str
    keyword_tags: Optional[str]
    is_featured: bool
    variants: list[ProductVariantResponse]

    model_config = ConfigDict(from_attributes=True)


class NewProductRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category_id: int
    variants: list[NewProductVariantRequest]
    description: Optional[str] = Field(max_length=400)
    is_in_stock: bool
    is_featured: bool


class UpdateProductRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    category_id: Optional[int] = Field(default=None)
    description: Optional[str] = Field(default=None, max_length=400)
    keyword_tags: Optional[str] = Field(default=None)
    is_featured: Optional[bool] = Field(default=None)
    is_hidden: Optional[bool] = Field(default=None)





# =========== PRODUCT VARIANTS ============

class ProductVariantResponse(BaseModel):
    id: int
    label: str
    price: int
    compare_at_price: Optional[int]
    stock_qty: int
    sku: str
    offers: list[OfferResponse]

    model_config = ConfigDict(from_attributes=True)


class NewProductVariantRequest(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    price: int
    compare_at_price: Optional[int]
    stock_qty: int



class UpdateProductVariantRequest(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=100)
    price: Optional[int] = Field(default=None, ge=0)
    compare_at_price: Optional[int] = Field(default=None, ge=0)
    stock_qty: Optional[int] = Field(default=None, ge=0)