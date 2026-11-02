from typing import Annotated

from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException, 
    Query, 
    Request, 
    status,
)
from sqlalchemy import select

from app.core.deps import SessionDep, require_perm
from app.core.permissions import Permissions
from app.core.rate_limiter import limiter
from app.models.general import ShopSettings
from app.models.identity import User
from app.schemas.shop_settings import (
    BulkUpdateShopSettingRequest,
    NewShopSettingRequest,
    ShopSettingResponse,
    UpdateShopSettingRequest,
)
import structlog

logger = structlog.get_logger()


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=list[ShopSettingResponse])
@limiter.limit("2/second")
async def get_all_settings(
    request: Request,
    db: SessionDep,
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
@limiter.limit("2/second")
async def get_setting_by_key(
    request: Request,
    key: str,
    db: SessionDep,
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
@limiter.limit("20/minute")
async def create_setting(
    request: Request,
    admin: Annotated[User, Depends(require_perm(Permissions.SETTINGS_WRITE))],
    new_setting: NewShopSettingRequest,
    db: SessionDep,
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

    logger.info("Shop setting created", setting_key=setting.key, admin_id=admin.id)
    return setting


@router.put("/bulk", response_model=list[ShopSettingResponse])
@limiter.limit("10/minute")
async def bulk_upsert_settings(
    request: Request,
    admin: Annotated[User, Depends(require_perm(Permissions.SETTINGS_WRITE))],
    payload: BulkUpdateShopSettingRequest,
    db: SessionDep,
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

    logger.info(
        "Shop settings bulk upserted",
        admin_id=admin.id,
        count=len(updated_settings),
        keys=[s.key for s in updated_settings],
    )

    return updated_settings


@router.patch("/{key}", response_model=ShopSettingResponse)
@limiter.limit("20/minute")
async def update_setting(
    request: Request,
    key: str,
    setting_update: UpdateShopSettingRequest,
    admin: Annotated[User, Depends(require_perm(Permissions.SETTINGS_WRITE))],
    db: SessionDep,
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

    logger.info("Shop setting updated", setting_key=key, admin_id=admin.id)
    return setting


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_setting(
    request: Request,
    key: str,
    admin: Annotated[User, Depends(require_perm(Permissions.SETTINGS_WRITE))],
    db: SessionDep,
):
    setting = await db.scalar(select(ShopSettings).where(ShopSettings.key == key))
    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting with key '{key}' not found",
        )

    await db.delete(setting)
    await db.commit()

    logger.info("Shop setting deleted", setting_key=key, admin_id=admin.id)
    return None