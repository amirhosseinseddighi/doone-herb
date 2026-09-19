from datetime import UTC, datetime, timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select, delete as sql_delete
from sqlalchemy.exc import IntegrityError
from app.models.identity import ResetPasswordToken, Roles, User
from app.core.deps import CurrentUser, CurrentAdmin, OptionalUser, get_db
from app.db.database import AsyncSession
from app.core import security
from app.core.config import settings
from app.routers.cart import merge_guest_cart_to_user
from app.schemas.auth import ChangePasswordRequest, CurrentUserInfoResponse, ForgetPasswordRequest, NewUserCreate, ResetPasswordRequest, Token
from app.utils.email_utils import send_password_reset_email


router = APIRouter(prefix="/auth", tags=["auth"])



@router.post("/login", response_model=Token)
async def login(
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

    return Token(access_token= access_token, token_type='bearer')



@router.get("/me", response_model=CurrentUserInfoResponse)
async def read_users_me(current_user: CurrentUser):
    return current_user


@router.get("/admin/users")
async def read_admin_users(
    _admin: CurrentAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [
        {
            "id": user.id,
            "name": user.name,
            "phone": user.phone,
            "city": "",
            "orders": 0,
            "spend": 0,
            "last": "-",
            "tg": user.telegram_opt_in,
            "sms": user.sms_opt_in,
            "tier": user.tier.value,
            "note": user.note or "",
        }
        for user in users
        if user.role == Roles.CUSTOMER
    ]



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




@router.post("/forget-password", status_code=status.HTTP_202_ACCEPTED)
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
async def reset_password(
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

    # return response
    return {
        "message": "Password reset successfully. You can now log in with your new password.",
    }



@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    change_password_request: ChangePasswordRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Authenticated user password update endpoint."""
    
    # Verify existing password
    if not security.verify_password(
        change_password_request.current_password, current_user.password_hash
    ):
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

    return {"message": "Password changed successfully."}