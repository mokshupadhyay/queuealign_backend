from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.models import ParticipantStatus


class EventCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    pin: str = Field(min_length=4, max_length=32, pattern=r"^\d+$")


class EventPublic(BaseModel):
    slug: str
    name: str
    is_active: bool
    waiting_count: int
    called_count: int
    checked_in_count: int
    total_count: int
    created_at: datetime | None = None
    event_qr_url: str | None = None


class EventListItem(BaseModel):
    slug: str
    name: str
    waiting_count: int
    checked_in_count: int
    total_count: int
    created_at: datetime


class EventCreated(BaseModel):
    slug: str
    name: str
    pin: str
    register_path: str
    register_url: str
    desk_path: str
    display_path: str
    event_qr_url: str


class EventUpdate(BaseModel):
    is_active: bool


class AuthRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=32)


class AuthResponse(BaseModel):
    token: str
    expires_in_hours: int


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    team_name: str | None = Field(default=None, max_length=120)


class ParticipantPublic(BaseModel):
    id: int
    name: str
    team_name: str | None
    queue_number: int
    status: ParticipantStatus
    created_at: datetime
    called_at: datetime | None
    checked_in_at: datetime | None

    model_config = {"from_attributes": True}


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


class DeskParticipant(BaseModel):
    id: int
    name: str
    email: str
    team_name: str | None
    queue_number: int
    status: ParticipantStatus
    created_at: datetime
    called_at: datetime | None
    checked_in_at: datetime | None

    model_config = {"from_attributes": True}


class RegisterResponse(BaseModel):
    participant: ParticipantOut
    status_path: str
    qr_url: str
    already_registered: bool = False


class ParticipantStatusOut(BaseModel):
    event_name: str
    event_slug: str
    participant: ParticipantPublic
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
    is_active: bool
    now_serving: DeskParticipant | None
    participants: list[DeskParticipant]
    waiting_count: int
    called_count: int
    checked_in_count: int
    skipped_count: int
    total_count: int


class CheckinRequest(BaseModel):
    token: str | None = None
    queue_number: int | None = None


class RequeueRequest(BaseModel):
    queue_number: int = Field(ge=1)


class SkipRequest(BaseModel):
    call_next: bool = False


class MessageOut(BaseModel):
    ok: bool
    message: str
    participant: ParticipantOut | DeskParticipant | None = None
