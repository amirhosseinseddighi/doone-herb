from datetime import datetime
import re
from typing import Annotated

from pydantic import (
    BaseModel, 
    ConfigDict, 
    EmailStr, 
    Field, 
    StringConstraints, 
    field_validator, 
    model_validator
)

from app.models.identity import Roles

PASSWORD_SPECIAL_CHAR_REGEX = re.compile(r"[!@#$%^&*(),.?\":{}|<>]")
PasswordStr = Annotated[str, StringConstraints(strip_whitespace=False)]

class Token(BaseModel):
    access_token: str
    token_type: str


class UserBasicResponse(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(
            str_strip_whitespace=True,
            from_attributes=True
        )


class CurrentUserInfoResponse(BaseModel):
    email: str
    phone: str
    name: str
    tier: str
    sms_opt_in: bool
    last_seen_at: datetime
    role: str
    created_at: datetime
    telegram_opt_in: bool


class UpdateProfileRequest(BaseModel):
    """Partial profile update. Email is intentionally absent: it identifies the
    account and is used for password reset, so it is not user-editable."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid"
    )

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="User full name",
        examples=["Amir sed"]
    )

    phone: str | None = Field(
        default=None,
        min_length=11,
        max_length=11,
        pattern=r"^09\d{9}$",
        description="phone number format (09121231234)"
    )



class NewUserCreate(BaseModel):

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid"
    )

    email: EmailStr = Field(
        description="User email address",
        examples=["user@example.com"]
    )

    phone: str = Field(
        min_length=11,
        max_length=11,
        pattern=r"^09\d{9}$",
        description="phone number format (09121231234)"
    )

    name: str = Field(
        min_length=1, 
        max_length=50,
        description="User full name",
        examples=["Amir sed"]
    )
    

    password: PasswordStr = Field(
        min_length=8, 
        max_length=128,
        description="Must contain uppercase,lowercase,numbers and special chars"
    )
    password_repeat: PasswordStr = Field(min_length=8, max_length=128)


    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        if not PASSWORD_SPECIAL_CHAR_REGEX.search(v):
            raise ValueError("Password must contain at least one special character")
        return v


    @model_validator(mode="after")
    def validate_passwords_match(self) -> "NewUserCreate":
        if self.password != self.password_repeat:
            raise ValueError("Passwords do not match")
        return self










# ===== FORGET PASSWORD =======

class ForgetPasswordRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid"
    )

    email: EmailStr


# ====== RESET PASSWORD AND CHANGE PASSWORD ========
class PasswordMixin(BaseModel):
    """Reusable mixin for password complexity and strict config."""
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid"
    )

    new_password: PasswordStr = Field(
        min_length=8,
        max_length=128,
        description="Must contain uppercase, lowercase, numbers, and special chars"
    )
    password_repeat: PasswordStr = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        if not PASSWORD_SPECIAL_CHAR_REGEX.search(v):
            raise ValueError("Password must contain at least one special character")
        return v

    @model_validator(mode="after")
    def validate_passwords_match(self) -> "PasswordMixin":
        if self.new_password != self.password_repeat:
            raise ValueError("Passwords do not match")
        return self


class ResetPasswordRequest(PasswordMixin):
    token: str = Field(..., description="Password reset verification token")


class ChangePasswordRequest(PasswordMixin):
    current_password: PasswordStr = Field(..., description="User's existing password")

    @model_validator(mode="after")
    def validate_new_password_different(self) -> "ChangePasswordRequest":
        if self.current_password == self.new_password:
            raise ValueError("New password must be different from current password")
        return self