from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from app.models.identity import Roles, User
from app.core.deps import CurrentUser, CurrentAdmin, OptionalUser, get_db
from app.db.database import AsyncSession
from app.core import security
from app.core.config import settings
from app.db.redis_cli import redis_client
from app.schemas.auth import CurrentUserInfoResponse, ForgetPasswordRequest, NewUserCreate, Token
from app.utils.email_utils import send_password_reset_email


router = APIRouter()



@router.post("/login", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], 
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: OptionalUser
):
    """ Login endpoint """


    # check user is not logged in
    if current_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already logged in.",
        )
    # check if user with this phone exists, then check if password is correct
    result = await db.execute(
        select(User).where(func.lower(User.email) == form_data.username.lower())
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
            "sub": str(user.id),
            "role": user.role
        }, 
        expires_delta= access_token_expires
    )

    return Token(access_token= access_token, token_type='bearer')



@router.get("/me", response_model=CurrentUserInfoResponse)
async def read_users_me(current_user: CurrentUser):
    return current_user



@router.post("/register", status_code=status.HTTP_201_CREATED)
async def create_new_user(
    new_user: NewUserCreate, 
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: OptionalUser
):
    # check user is not logged in
    if current_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already logged in.",
        )
    
    # check username and phone uniqueness
    normalized_email = new_user.email.lower()
    user_result = await db.execute(
        select(User.email, User.phone)
        .where(
            (func.lower(User.email) == normalized_email) |
            (User.phone == new_user.phone)
        )
    )

    existing_user = user_result.first()

    if existing_user:
        if existing_user.email.lower() == normalized_email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")
        if existing_user.phone == new_user.phone:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number already registered")


    # hash password
    password_hash = security.hash_password(new_user.password)

    user = User(
        email = normalized_email,
        phone = new_user.phone,
        name = new_user.name,
        role = Roles.CUSTOMER,
        password_hash = password_hash
    )


    db.add(user)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or phone number already registered",
        )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "Registration successful. Please login into your account."},
    )




@router.post("/forget-password", status_code=status.HTTP_200_OK)
async def forget_password(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: OptionalUser,
    background_task: BackgroundTasks,
    forget_password_request: ForgetPasswordRequest
):
    # check user is not logged in
    if current_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already logged in.",
        )

    # get email and check existance
    normalized_email = forget_password_request.email.lower()
    user_result = await db.execute(
        select(User)
        .where(
            (func.lower(User.email) == normalized_email)
        )
    )

    user = user_result.scalar_one_or_none()
    if user:
        # generate token
        reset_token = security.generate_reset_token()
        hash_reset_token = security.hash_reset_token(reset_token)

        # store token in redis
        redis_key = f"{settings.RESET_TOKEN_PREFIX}{reset_token}"
        redis_client.set(redis_key, str(user.id), ex=settings.RESET_TOKEN_TTL_SECONDS)


        # send email
        background_task.add_task(
            send_password_reset_email,
            user.name,
            user.email,
            reset_token
        )



    return {
            "message": "If an account exists with this email, you'll receive reset token soon."
        }




