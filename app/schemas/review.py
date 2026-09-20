from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ReviewBase(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="Review or reply text")


class ReviewCreate(ReviewBase):
    product_id: int
    stars: int = Field(..., ge=1, le=5, description="Rating from 1 to 5 stars")
    order_id: Optional[int] = None


class ReviewReplyCreate(ReviewBase):
    """Schema for adding a reply/comment to an existing review."""
    pass


class ReviewUpdate(BaseModel):
    stars: Optional[int] = Field(None, ge=1, le=5)
    text: Optional[str] = Field(None, min_length=1, max_length=2000)


class ReviewUserResponse(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class ReviewResponse(BaseModel):
    id: int
    product_id: int
    user_id: int
    order_id: Optional[int] = None
    parent_id: Optional[int] = None
    stars: Optional[int] = None
    text: str
    created_at: datetime
    user: Optional[ReviewUserResponse] = None
    replies: List["ReviewResponse"] = []

    model_config = ConfigDict(from_attributes=True)


class PaginatedReviewResponse(BaseModel):
    items: List[ReviewResponse]
    total: int
    offset: int
    limit: int