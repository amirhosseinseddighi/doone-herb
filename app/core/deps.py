from __future__ import annotations
from typing import Annotated
from fastapi import status
from fastapi import Depends, HTTPException
from sqlalchemy import select
from app.core.security import oauth2_scheme, verify_access_token
from app.db.database import AsyncSession
from app.db.database import Base, AsyncSessionLocal
from app.models.identity import Roles, User

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session



async def get_current_user(
        token: Annotated[str, Depends(oauth2_scheme)],
        db: Annotated[AsyncSession, Depends(get_db)]
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
    
    return user



def require_role(*allowed_roles: Roles):
    """Dependency factory for role-based access control."""
    async def check_role(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Insufficient permissions", 
                headers={"WWW-Authenticate": "Bearer"}
            )
        return user
    return check_role


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(require_role(Roles.OWNER, Roles.PACKER, Roles.MANAGER))]
CurrentOwner = Annotated[User, Depends(require_role(Roles.OWNER))]