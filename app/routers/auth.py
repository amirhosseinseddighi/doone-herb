from datetime import UTC, datetime, timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select, delete as sql_delete
from sqlalchemy.exc import IntegrityError
from app.models.identity import ResetPasswordToken, Roles, User
from app.core.deps import CurrentUser, CurrentAdmin, OptionalUser, get_db
from app.db.database import AsyncSession
from app.core import security
from app.core.config import settings
from app.core.rate_limiter import limiter
from app.routers.cart import merge_guest_cart_to_user
from app.schemas.auth import ChangePasswordRequest, CurrentUserInfoResponse, ForgetPasswordRequest, NewUserCreate, PaginatedUserResponse, ResetPasswordRequest, Token, UpdateProfileRequest, UserInfoForAdmin
from app.utils.email_utils import send_password_reset_email
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])



@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: OptionalUser,
    guest_cart_token: Optional[str] = Cookie(None, alias="guest_cart_token"),
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
        logger.warning("Login failed", email=form_data.username)
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail="Wrong Username or Password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # merge guest cart
    if guest_cart_token:
        await merge_guest_cart_to_user(
            guest_token=guest_cart_token,
            current_user=user,
            db=db
        )

    # delete guest cart cookie
    response.delete_cookie(
        key="guest_cart_token",
        httponly=True,
        samesite="lax",
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

    logger.info("Login successful", user_id=user.id, email=user.email, role=user.role.value)

    return Token(access_token= access_token, token_type='bearer')



@router.get("/me", response_model=CurrentUserInfoResponse)
@limiter.limit("2/second")
async def read_users_me(request: Request, current_user: CurrentUser):
    return current_user


@router.patch("/me", response_model=CurrentUserInfoResponse)
@limiter.limit("5/minute")
async def update_users_me(
    request: Request,
    profile_update: UpdateProfileRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Partial profile update. Email is not editable (see UpdateProfileRequest)."""
    update_data = profile_update.model_dump(exclude_unset=True)

    # check phone uniqueness against every other account
    new_phone = update_data.get("phone")
    if new_phone and new_phone != current_user.phone:
        existing_phone = await db.execute(
            select(User.id).where(
                (User.phone == new_phone) & (User.id != current_user.id)
            )
        )
        if existing_phone.first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number already registered",
            )

    for field, value in update_data.items():
        setattr(current_user, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered",
        )

    await db.refresh(current_user)
    logger.info("Profile updated", user_id=current_user.id, fields=sorted(update_data.keys()))
    return current_user


@router.get("/admin/users", response_model=PaginatedUserResponse)
@limiter.limit("10/minute")
async def read_admin_users(
    request: Request,
    _admin: CurrentAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=150)] = 150,
):
    result = await db.execute(
        select(User)
        .offset(offset).limit(limit)
        .where(User.role == Roles.CUSTOMER)
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    total_users_req = await db.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == Roles.CUSTOMER)
    )

    total_users = total_users_req.scalar() or 0

    has_more = offset + limit < total_users

    return PaginatedUserResponse(
        users = [UserInfoForAdmin.model_validate(user) for user in users],
        offset=offset,
        limit=limit,
        has_more=has_more
    )



@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
async def create_new_user(
    request: Request,
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
        logger.warning("Registration failed", email=normalized_email, reason="duplicate")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or phone number already registered",
        )

    await db.refresh(user)
    logger.info("User registered", user_id=user.id, email=user.email)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "Registration successful. Please login into your account."},
    )




@router.post("/forget-password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/hour")
async def forget_password(
    request: Request,
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


        # remove old tokens
        await db.execute(sql_delete(ResetPasswordToken).where(ResetPasswordToken.user_id == user.id))

        # generate token
        reset_token = security.generate_reset_token()
        hash_reset_token = security.hash_reset_token(reset_token)

        # store token in db
        reset_token_entry = ResetPasswordToken(
            user_id=user.id,
            token_hash=hash_reset_token,
        )


        reset_token_entry.expire_at = datetime.now(UTC) + timedelta(
            seconds=settings.RESET_TOKEN_TTL_SECONDS
        )

        db.add(reset_token_entry)
        await db.commit()
        await db.refresh(reset_token_entry)

        logger.info("Password reset requested", user_id=user.id, email=user.email)

        # send email
        background_task.add_task(
            send_password_reset_email,
            name=user.name,
            to_email=user.email,
            token=reset_token
        )



    return {
            "message": "If an account exists with this email, you'll receive reset token soon."
        }





@router.post("/reset-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/hour")
async def reset_password(
    request: Request,
    reset_password_request: ResetPasswordRequest,
    current_user: OptionalUser,
    db: Annotated[AsyncSession, Depends(get_db)]
):

    # check user is not logged in
    if current_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already logged in.",
        )
        
    # check if token exists
    reset_token = reset_password_request.token
    hash_reset_token = security.hash_reset_token(reset_token)
    reset_token_res = await db.execute(
        select(ResetPasswordToken)
        .where(ResetPasswordToken.token_hash == hash_reset_token)
    )

    reset_password_token = reset_token_res.scalar_one_or_none()

    if not reset_password_token or (reset_password_token.expire_at < datetime.now(UTC)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    # remove all reset tokens
    await db.execute(sql_delete(ResetPasswordToken).where(ResetPasswordToken.user_id == reset_password_token.user_id))

    

    # get the user
    user_result = await db.execute(
            select(User)
            .where(
                (User.id == reset_password_token.user_id)
            )
        )
    
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Something bad happend. Try again!",
        )

    # hash new_password
    new_password_hash = security.hash_password(reset_password_request.new_password)

    # change the user's password
    user.password_hash = new_password_hash

    # commit changes
    await db.commit()

    logger.info("Password reset completed", user_id=user.id, email=user.email)

    # return response
    return {
        "message": "Password reset successfully. You can now log in with your new password.",
    }



@router.post("/change-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    change_password_request: ChangePasswordRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Authenticated user password update endpoint."""
    
    # Verify existing password
    if not security.verify_password(
        change_password_request.current_password, current_user.password_hash
    ):
        logger.warning("Password change failed", user_id=current_user.id, reason="incorrect current password")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password.",
        )

    # Hash new password and apply change
    current_user.password_hash = security.hash_password(
        change_password_request.new_password
    )

    db.add(current_user)
    await db.commit()

    logger.info("Password changed", user_id=current_user.id)

    return {"message": "Password changed successfully."}