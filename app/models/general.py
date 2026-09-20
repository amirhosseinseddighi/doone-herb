from __future__ import annotations
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.order import _utcnow
from app.db.database import Base


class ShopSettings(Base):
    __tablename__="shop_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
        )