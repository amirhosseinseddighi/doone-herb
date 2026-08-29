from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict
from app.schemas.categories import CategoryResponse



class OfferResponse(BaseModel):

    id: int
    badge_label: str
    starts_at: datetime
    ends_at: datetime

class ProductVariantResponse(BaseModel):
    id: int
    label: str
    price: int
    compare_at_price: Optional[int]
    stock_qty: int
    sku: str
    offers: list[OfferResponse]

    model_config = ConfigDict(from_attributes=True)




   
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