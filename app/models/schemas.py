from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.models import ParticipantStatus


class EventCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    pin: str = Field(min_length=4, max_length=32)


class EventPublic(BaseModel):
    slug: str
    name: str
    is_active: bool
    waiting_count: int
    called_count: int
    checked_in_count: int
    total_count: int


class EventCreated(BaseModel):
    slug: str
    name: str
    pin: str
    register_path: str
    desk_path: str
    display_path: str


class AuthRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=32)


class AuthResponse(BaseModel):
    token: str
    expires_in_hours: int


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    team_name: str | None = Field(default=None, max_length=120)


class ParticipantOut(BaseModel):
    id: int
    name: str
    email: str
    team_name: str | None
    queue_number: int
    checkin_token: str
    status: ParticipantStatus
    created_at: datetime
    called_at: datetime | None
    checked_in_at: datetime | None

    model_config = {"from_attributes": True}


class RegisterResponse(BaseModel):
    participant: ParticipantOut
    status_path: str
    qr_url: str


class ParticipantStatusOut(BaseModel):
    event_name: str
    event_slug: str
    participant: ParticipantOut
    people_ahead: int
    now_serving: int | None
    now_serving_name: str | None
    qr_url: str
    status_path: str


class DisplayParticipant(BaseModel):
    queue_number: int
    name: str
    team_name: str | None
    status: ParticipantStatus


class DisplayOut(BaseModel):
    event_name: str
    event_slug: str
    now_serving: DisplayParticipant | None
    up_next: list[DisplayParticipant]
    waiting_count: int
    checked_in_count: int
    total_count: int


class QueueOut(BaseModel):
    event_name: str
    event_slug: str
    now_serving: ParticipantOut | None
    participants: list[ParticipantOut]
    waiting_count: int
    called_count: int
    checked_in_count: int
    skipped_count: int
    total_count: int


class CheckinRequest(BaseModel):
    token: str | None = None
    queue_number: int | None = None


class MessageOut(BaseModel):
    ok: bool
    message: str
    participant: ParticipantOut | None = None
