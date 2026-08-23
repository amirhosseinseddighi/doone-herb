from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CategoryResponse(BaseModel):
    """ Public category response schema """
    id: int
    slug: str = Field(min_length=0)
    name: str = Field(min_length=0)
    tint_color: Optional[str] = Field(min_length=7, max_length=7)
    dot_color: Optional[str] = Field(min_length=7, max_length=7)

    model_config = ConfigDict(from_attributes=True)