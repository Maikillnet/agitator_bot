from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, Boolean, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base
import enum

class RepeatTouch(str, enum.Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"

class TalkStatus(str, enum.Enum):
    NO_ONE = "NO_ONE"
    REFUSAL = "REFUSAL"
    CONSENT = "CONSENT"

class FlyerMethod(str, enum.Enum):
    HAND = "HAND"
    MAILBOX = "MAILBOX"
    NONE = "NONE"

class Agent(Base):
    __tablename__ = "agent"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)  # NEW
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    admin_logged_in: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    visits: Mapped[list['Visit']] = relationship(back_populates="agent")
    contacts: Mapped[list['Contact']] = relationship(back_populates="agent")

class Visit(Base):
    __tablename__ = "visit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agent.id", ondelete="CASCADE"))
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    agent: Mapped['Agent'] = relationship(back_populates="visits")
    contacts: Mapped[list['Contact']] = relationship(back_populates="visit")

class Contact(Base):
    __tablename__ = "contact"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visit.id", ondelete="CASCADE"))
    agent_id: Mapped[int] = mapped_column(ForeignKey("agent.id", ondelete="SET NULL"))
    full_name: Mapped[str] = mapped_column(String(255))
    phone_e164: Mapped[str] = mapped_column(String(32))
    phone_hash: Mapped[str] = mapped_column(String(64))

    repeat_touch: Mapped[RepeatTouch | None] = mapped_column(SAEnum(RepeatTouch), nullable=True)
    talk_status: Mapped[TalkStatus | None] = mapped_column(SAEnum(TalkStatus), nullable=True)

    door_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    mailbox_photo: Mapped[bool] = mapped_column(Boolean, default=False)

    flyer_method: Mapped[FlyerMethod | None] = mapped_column(SAEnum(FlyerMethod), nullable=True)
    flyer_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    home_voting: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    visit: Mapped['Visit'] = relationship(back_populates="contacts")
    agent: Mapped['Agent'] = relationship(back_populates="contacts")
