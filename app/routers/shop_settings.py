from typing import Annotated

from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException, 
    Query, 
    Request, 
    status,
    BackgroundTasks
)
from sqlalchemy import select

from app.core.deps import CurrentManagerOrOwner, get_db
from app.core.rate_limiter import limiter
from app.db.database import AsyncSession
from app.models.general import ShopSettings
from app.schemas.shop_settings import (
    BulkUpdateShopSettingRequest,
    NewShopSettingRequest,
    ShopSettingResponse,
    UpdateShopSettingRequest,
)
import structlog

from app.utils.general_utils import export_database

logger = structlog.get_logger()


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=list[ShopSettingResponse])
@limiter.limit("2/second")
async def get_all_settings(
    request: Request,
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
@limiter.limit("2/second")
async def get_setting_by_key(
    request: Request,
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
@limiter.limit("20/minute")
async def create_setting(
    request: Request,
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

    logger.info("Shop setting created", setting_key=setting.key, admin_id=admin.id)
    return setting


@router.put("/bulk", response_model=list[ShopSettingResponse])
@limiter.limit("10/minute")
async def bulk_upsert_settings(
    request: Request,
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

    logger.info("Shop setting updated", setting_key=key, admin_id=admin.id)
    return setting


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_setting(
    request: Request,
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

    logger.info("Shop setting deleted", setting_key=key, admin_id=admin.id)
    return None



# =============== IMPORT/EXPORT SHOP SETTINGS ===============

"""
an endpoint to request database export:
    - it will create a background task to retrieve database chunk by chunk and then strem it?
    - or will it add job to background task and upload it chunk by chunk and then there is another
    endpoint like /download/{export_id} to download the exported db

an endpoint to request database import:
    - the client will send chunk by chunk(large data)
    - we will restore and save data in one big file.
    - then we will import it chunk by chunk into dataset in background task.
"""

@router.post("/export", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/hour")
async def export_request(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_admin: CurrentManagerOrOwner,
    background_task: BackgroundTasks
):
    background_task.add_task(export_database, db)
    return {"message": "Export request is processing"}

@router.get("/export/download/{export_id}")
@limiter.limit("5/hour")
async def download_exported_db(
    request: Request,
    current_admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)],
    export_id: int
):
    ...
