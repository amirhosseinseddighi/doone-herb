from __future__ import annotations
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update

from app.core.deps import CurrentUser, get_db
from app.db.database import AsyncSession
from app.models.identity import Address
from app.schemas.addresses import AddressCreate, AddressRead, AddressUpdate
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/addresses", tags=["addresses"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _get_owned_address(db: AsyncSession, user_id: int, address_id: int) -> Address:
    result = await db.execute(
        select(Address).where(
            Address.id == address_id,
            Address.user_id == user_id,
        )
    )
    address = result.scalars().first()
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found",
        )
    return address


async def _unset_other_defaults(db: AsyncSession, user_id: int, exclude_id: int | None = None) -> None:
    stmt = (
        update(Address)
        .where(Address.user_id == user_id, Address.is_default.is_(True))
        .values(is_default=False)
    )
    if exclude_id is not None:
        stmt = stmt.where(Address.id != exclude_id)
    await db.execute(stmt)


@router.get("", response_model=list[AddressRead])
async def list_addresses(current_user: CurrentUser, db: DbDep):
    result = await db.execute(
        select(Address)
        .where(Address.user_id == current_user.id)
        .order_by(Address.is_default.desc(), Address.id.desc())
    )
    return result.scalars().all()


@router.get("/{address_id}", response_model=AddressRead)
async def get_address(address_id: int, current_user: CurrentUser, db: DbDep):
    return await _get_owned_address(db, current_user.id, address_id)


@router.post("", response_model=AddressRead, status_code=status.HTTP_201_CREATED)
async def create_address(
    payload: AddressCreate,
    current_user: CurrentUser,
    db: DbDep,
):
    # first address for a user is always the default,regardless of input
    result = await db.execute(
        select(Address.id).where(Address.user_id == current_user.id).limit(1)
    )
    has_existing = result.scalars().first() is not None
    make_default = payload.is_default or not has_existing

    if make_default:
        await _unset_other_defaults(db, current_user.id)

    address = Address(
        **payload.model_dump(exclude={"is_default"}),
        is_default=make_default,
        user_id=current_user.id,
    )
    db.add(address)
    await db.commit()
    await db.refresh(address)

    logger.info(
        "Address created",
        address_id=address.id,
        user_id=current_user.id,
        is_default=address.is_default,
    )
    return address


@router.patch("/{address_id}", response_model=AddressRead)
async def update_address(
    address_id: int,
    payload: AddressUpdate,
    current_user: CurrentUser,
    db: DbDep,
):
    address = await _get_owned_address(db, current_user.id, address_id)

    data = payload.model_dump(exclude_unset=True)
    making_default = data.pop("is_default", None)

    for field, value in data.items():
        setattr(address, field, value)

    if making_default is True and not address.is_default:
        await _unset_other_defaults(db, current_user.id, exclude_id=address.id)
        address.is_default = True
    elif making_default is False:
        # don't allow removing default without replacement; ignore/ or raise
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot unset default directly; set another address as default instead",
        )

    await db.commit()
    await db.refresh(address)

    logger.info(
        "Address updated",
        address_id=address_id,
        user_id=current_user.id,
        fields=sorted(data.keys()),
        made_default=making_default is True,
    )
    return address


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(address_id: int, current_user: CurrentUser, db: DbDep):
    address = await _get_owned_address(db, current_user.id, address_id)
    was_default = address.is_default

    await db.delete(address)
    await db.flush()

    if was_default:
        result = await db.execute(
            select(Address)
            .where(Address.user_id == current_user.id)
            .order_by(Address.id.asc())
            .limit(1)
        )
        fallback = result.scalars().first()
        if fallback:
            fallback.is_default = True

    await db.commit()

    logger.info(
        "Address deleted",
        address_id=address_id,
        user_id=current_user.id,
        was_default=was_default,
    )


@router.post("/{address_id}/set-default", response_model=AddressRead)
async def set_default_address(address_id: int, current_user: CurrentUser, db: DbDep):
    address = await _get_owned_address(db, current_user.id, address_id)
    if not address.is_default:
        await _unset_other_defaults(db, current_user.id, exclude_id=address.id)
        address.is_default = True
        await db.commit()
        await db.refresh(address)
        logger.info("Address set as default", address_id=address_id, user_id=current_user.id)
    return address