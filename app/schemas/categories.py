from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from pydantic import BaseModel, ConfigDict, Field


if TYPE_CHECKING:
    from app.schemas.products import BaseProductResponse


class CategoryResponse(BaseModel):
    id: int
    slug: str = Field(min_length=0)
    name: str = Field(min_length=0)
    tint_color: Optional[str] = Field(min_length=7, max_length=7)
    dot_color: Optional[str] = Field(min_length=7, max_length=7)
    sort_order: int
    is_active: bool

    image_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)



class CategoryDetails(CategoryResponse):
    products: list[BaseProductResponse] = Field(default_factory=list)
    total_products: int
    model_config = ConfigDict(from_attributes=True)


class PaginatedCategoryResponse(BaseModel):
    categories: list[CategoryResponse]
    offset: int
    limit: int
    has_more: bool


class NewCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    tint_color: str = Field(min_length=7, max_length=7, pattern=r"^#[0-9a-fA-F]{6}$")
    dot_color: str = Field(min_length=7, max_length=7, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int = Field(default=0)
    is_active: bool = Field(default=True)


class UpdateCategoryRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    tint_color: Optional[str] = Field(default=None, min_length=7, max_length=7, pattern=r"^#[0-9a-fA-F]{6}$")
    dot_color: Optional[str] = Field(default=None, min_length=7, max_length=7, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: Optional[int] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)

class CategoryImageUploadResponse(BaseModel):
    id: int
    url: str

    model_config = ConfigDict(from_attributes=True)





from app.schemas.products import BaseProductResponse  # noqa: E402
CategoryDetails.model_rebuild()