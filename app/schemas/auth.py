from datetime import datetime

from pydantic import BaseModel

from app.models.identity import Roles



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