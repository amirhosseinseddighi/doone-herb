from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.identity import Roles


USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")
PASSWORD_SPECIAL_CHAR_REGEX = re.compile(r"[!@#$%^&*(),.?\":{}|<>]")


class Token(BaseModel):
    access_token: str
    token_type: str



class CurrentUserInfoResponse(BaseModel):
    phone: str
    name: str
    tier: str
    sms_opt_in: bool
    last_seen_at: datetime
    role: str
    created_at: datetime
    telegram_opt_in: bool 


class NewUserCreate(BaseModel):

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid"
    )

    username: str = Field(
        min_length=3, 
        max_length=20,
        pattern=r"^[a-zA-Z1-9_-]+$",
        description="alphanumeric characters, underscores and hyphens only",
        examples=["09120000000"]
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
    

    password: str = Field(
        min_length=8, 
        max_length=128,
        description="Must contain uppercase,lowercase,numbers and special chars"
    )
    password_repeat: str = Field(min_length=8, max_length=128)


    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str):
        username = v.lower()
        if not USERNAME_REGEX.match(username):
            raise ValueError("Username can only contain alphanumeric characters, underscores, and hyphens")

        return v


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