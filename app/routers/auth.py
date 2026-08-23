from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from app.models.identity import User
from app.core.deps import CurrentUser, CurrentAdminUser, get_db
from app.db.database import AsyncSession
from app.core import security
from app.core.config import settings
from app.schemas.auth import Token

router = APIRouter()



@router.post("/login", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], 
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """ Login endpoint """
    # check if user with this phone exists, then check if password is correct
    result = await db.execute(
        select(User).where(func.lower(User.phone) == form_data.username.lower())
    )

    user = result.scalars().first()

    if not user or not security.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail="Wrong Username or Password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # if both are correct then generate a JWT token (access token + refresh token) and return it with Token model
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.generate_access_token(
        data = {
            "sub": str(user.id)
        }, 
        expires_delta= access_token_expires
    )

    return Token(access_token= access_token, token_type='bearer')
