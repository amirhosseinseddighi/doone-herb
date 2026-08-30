from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CategoryResponse(BaseModel):
    """ Public category response schema """
    id: int
    slug: str = Field(min_length=0)
    name: str = Field(min_length=0)
    tint_color: Optional[str] = Field(default=None, min_length=7, max_length=7, pattern=r"^#[0-9a-fA-F]{6}$")
    dot_color: Optional[str] = Field(default=None, min_length=7, max_length=7, pattern=r"^#[0-9a-fA-F]{6}$")

    model_config = ConfigDict(from_attributes=True)


class NewCategoryRequest(BaseModel):
    """ Admin category creation schema """
    name: str = Field(min_length=1, max_length=100)
    tint_color: str = Field(min_length=7, max_length=7, pattern=r"^#[0-9a-fA-F]{6}$")
    dot_color: str = Field(min_length=7, max_length=7, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int = Field(default=0)
    is_active: bool = Field(default=True)


class UpdateCategoryRequest(BaseModel):
    """ Admin category update schema """
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    tint_color: Optional[str] = Field(default=None, min_length=7, max_length=7, pattern=r"^#[0-9a-fA-F]{6}$")
    dot_color: Optional[str] = Field(default=None, min_length=7, max_length=7, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: Optional[int] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)