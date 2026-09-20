from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.core.deps import CurrentManagerOrOwner, get_db
from app.db.database import AsyncSession
from app.models.general import ShopSettings
from app.schemas.shop_settings import (
    BulkUpdateShopSettingRequest,
    NewShopSettingRequest,
    ShopSettingResponse,
    UpdateShopSettingRequest,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=list[ShopSettingResponse])
async def get_all_settings(
    db: Annotated[AsyncSession, Depends(get_db)],
    search: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=50,
            description="Search settings by key name",
        ),
    ] = None,
):
    stmt = select(ShopSettings)

    if search is not None:
        term = search.strip()
        if term:
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            stmt = stmt.where(ShopSettings.key.ilike(pattern, escape="\\"))

    result = await db.execute(stmt.order_by(ShopSettings.key.asc()))
    return result.scalars().all()


@router.get("/{key}", response_model=ShopSettingResponse)
async def get_setting_by_key(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    setting = await db.scalar(select(ShopSettings).where(ShopSettings.key == key))
    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting with key '{key}' not found",
        )
    return setting


# ================= ADMIN OPERATIONS ===================

@router.post("", response_model=ShopSettingResponse, status_code=status.HTTP_201_CREATED)
async def create_setting(
    admin: CurrentManagerOrOwner,
    new_setting: NewShopSettingRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    existing = await db.scalar(
        select(ShopSettings).where(ShopSettings.key == new_setting.key)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Setting key '{new_setting.key}' already exists",
        )

    setting = ShopSettings(key=new_setting.key, value=new_setting.value)
    db.add(setting)
    await db.commit()
    await db.refresh(setting)
    return setting


@router.put("/bulk", response_model=list[ShopSettingResponse])
async def bulk_upsert_settings(
    admin: CurrentManagerOrOwner,
    payload: BulkUpdateShopSettingRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    updated_settings: list[ShopSettings] = []

    for item in payload.settings:
        setting = await db.scalar(
            select(ShopSettings).where(ShopSettings.key == item.key)
        )
        if setting:
            setting.value = item.value
        else:
            setting = ShopSettings(key=item.key, value=item.value)
            db.add(setting)
        updated_settings.append(setting)

    await db.commit()
    for s in updated_settings:
        await db.refresh(s)

    return updated_settings


@router.patch("/{key}", response_model=ShopSettingResponse)
async def update_setting(
    key: str,
    setting_update: UpdateShopSettingRequest,
    admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    setting = await db.scalar(select(ShopSettings).where(ShopSettings.key == key))
    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting with key '{key}' not found",
        )

    setting.value = setting_update.value
    await db.commit()
    await db.refresh(setting)
    return setting


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_setting(
    key: str,
    admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    setting = await db.scalar(select(ShopSettings).where(ShopSettings.key == key))
    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting with key '{key}' not found",
        )

    await db.delete(setting)
    await db.commit()
    return None