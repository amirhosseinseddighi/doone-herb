from typing import Optional

from pydantic import BaseModel, ConfigDict
from app.schemas.categories import CategoryResponse



class ProductVariantResponse(BaseModel):
    id: int
    label: str
    price: int
    compare_at_price: Optional[int]
    stock_qty: int
    sku: str

    model_config = ConfigDict(from_attributes=True)




   
class ProductResponse(BaseModel):

    id: int
    name: str
    category: CategoryResponse
    description: str
    keyword_tags: Optional[str]
    is_featured: bool
    variants: list[ProductVariantResponse]

    model_config = ConfigDict(from_attributes=True)