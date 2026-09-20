from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ShopSettingResponse(BaseModel):
    id: int
    key: str = Field(min_length=1, max_length=50)
    value: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NewShopSettingRequest(BaseModel):
    key: str = Field(min_length=1, max_length=50)
    value: str = Field(min_length=0)


class UpdateShopSettingRequest(BaseModel):
    value: str = Field(min_length=0)


class BulkUpdateShopSettingRequest(BaseModel):
    settings: list[NewShopSettingRequest]