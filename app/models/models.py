from __future__ import annotations

import enum
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ParticipantStatus(str, enum.Enum):
    waiting = "waiting"
    called = "called"
    checked_in = "checked_in"
    skipped = "skipped"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    participants: Mapped[list[Participant]] = relationship(
        "Participant", back_populates="event", cascade="all, delete-orphan"
    )


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("event_id", "queue_number", name="uq_event_queue_number"),
        UniqueConstraint("event_id", "email", name="uq_event_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    team_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    queue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    checkin_token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=lambda: uuid.uuid4().hex
    )
    status: Mapped[ParticipantStatus] = mapped_column(
        Enum(ParticipantStatus), default=ParticipantStatus.waiting, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped[Event] = relationship("Event", back_populates="participants")


def generate_slug(name: str) -> str:
    base = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
    while "--" in base:
        base = base.replace("--", "-")
    base = (base[:40] or "event").strip("-")
    suffix = secrets.token_hex(3)
    return f"{base}-{suffix}"
