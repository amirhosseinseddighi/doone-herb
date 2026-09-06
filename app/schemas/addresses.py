from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AddressBase(BaseModel):
    label: str = Field(..., max_length=50, examples=["Home", "Work"])
    line: str = Field(..., max_length=255)
    unit: Optional[str] = Field(None, max_length=50)
    postal_code: str = Field(..., max_length=20)
    phone: str = Field(..., max_length=20)
    lat: float
    lng: float
    is_default: bool = False

    @field_validator("label", "line", "postal_code", "phone")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v


class AddressCreate(AddressBase):
    pass


class AddressUpdate(BaseModel):
    """All fields optional to support PATCH semantics."""
    label: Optional[str] = Field(None, max_length=50)
    line: Optional[str] = Field(None, max_length=255)
    unit: Optional[str] = Field(None, max_length=50)
    postal_code: Optional[str] = Field(None, max_length=20)
    phone: Optional[str] = Field(None, max_length=20)
    lat: Optional[float] = None
    lng: Optional[float] = None
    is_default: Optional[bool] = None

    @field_validator("label", "line", "postal_code", "phone")
    @classmethod
    def not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("must not be empty")
        return v


class AddressRead(AddressBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int