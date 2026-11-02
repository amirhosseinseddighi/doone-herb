from __future__ import annotations
from dataclasses import dataclass
from typing import Annotated, Optional
from fastapi import Cookie, status
from fastapi import Depends, HTTPException
from sqlalchemy import select
import structlog
from app.core.permissions import Permissions, has_perm
from app.core.security import oauth2_scheme, verify_access_token, oauth2_scheme_optional
from app.db.database import AsyncSession
from app.db.database import Base, AsyncSessionLocal
from app.models.identity import Roles, User

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session



async def get_optional_current_user(
    token: Annotated[Optional[str], Depends(oauth2_scheme_optional)],
    db: SessionDep,
) -> Optional[User]:
    """return authenticated User if a valid token is provided, otherwise None."""
    if not token:
        return None
    
    user_id = verify_access_token(token=token)
    if not user_id:
        return None

    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        return None

    result = await db.execute(
        select(User).where(User.id == user_id_int)
    )
    user = result.scalars().first()
    if user is not None:
        structlog.contextvars.bind_contextvars(user_id=user.id, role=user.role.value)
    return user




async def get_current_user(
        token: Annotated[str, Depends(oauth2_scheme)],
        db: SessionDep
):
    user_id = verify_access_token(token=token)
    if not user_id:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Unauthorized User", 
            headers = {"WWW-Authenticate": "Bearer"}
        )
    
    try:
        user_id_int = int(user_id)

    except (TypeError, ValueError):
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Invalid or expired access token", 
            headers = {"WWW-Authenticate": "Bearer"}
        )
    
    
    result = await db.execute(
        select(User).where(User.id == user_id_int)
    )

    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Unauthorized User",
            headers = {"WWW-Authenticate": "Bearer"}
        )

    structlog.contextvars.bind_contextvars(user_id=user.id, role=user.role.value)
    return user



async def get_optional_admin(
    current_user: OptionalUser,
) -> Optional[User]:
    """Return the current user if they're an OWNER/MANAGER, else None.
 
    Mirrors CurrentManagerOrOwner's role set, but never raises -- so it's
    safe to use alongside a required CurrentUser dependency for "author OR
    admin" checks.
    """
    if current_user is not None and current_user.role in (Roles.OWNER, Roles.MANAGER):
        return current_user
    return None
 


def require_perm(*perms: Permissions):
    async def checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not all(has_perm(user, p) for p in perms):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user
    return checker
 


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdminOptional = Annotated[Optional[User], Depends(get_optional_admin)]
OptionalUser = Annotated[Optional[User], Depends(get_optional_current_user)]



# ===== CART =====
@dataclass
class CartIdentity:
    """Resolved owner of a cart request: either a logged-in user or a guest token."""
    user_id: Optional[int]
    guest_token: Optional[str]


async def get_cart_identity(
    current_user: OptionalUser,
    guest_token: Optional[str] = Cookie(None, alias="guest_cart_token"),
) -> CartIdentity:
    return CartIdentity(
        user_id=current_user.id if current_user else None,
        guest_token=guest_token,
    )


async def require_cart_identity(
    identity: Annotated[CartIdentity, Depends(get_cart_identity)],
) -> CartIdentity:
    """Same as get_cart_identity, but 404s when there's no cart to act on at all."""
    if not identity.user_id and not identity.guest_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart not found",
        )
    return identity


CartIdentityDep = Annotated[CartIdentity, Depends(get_cart_identity)]
RequiredCartIdentityDep = Annotated[CartIdentity, Depends(require_cart_identity)]

SessionDep = Annotated[AsyncSession, Depends(get_db)]
