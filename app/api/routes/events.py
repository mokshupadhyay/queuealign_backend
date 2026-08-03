from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models.models import Event, Participant
from app.models.schemas import (
    AuthRequest,
    AuthResponse,
    CheckinRequest,
    DeskParticipant,
    DisplayOut,
    DisplayParticipant,
    EventCreate,
    EventCreated,
    EventPublic,
    EventUpdate,
    MessageOut,
    ParticipantOut,
    ParticipantPublic,
    ParticipantStatusOut,
    QueueOut,
    RegisterRequest,
    RegisterResponse,
    RequeueRequest,
    SkipRequest,
)
from app.services import auth as auth_service
from app.services import queue as queue_service
from app.services import qr as qr_service

router = APIRouter(prefix="/api")


def require_desk(slug: str, authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Desk auth required")
    token = authorization.removeprefix("Bearer ").strip()
    token_slug = auth_service.decode_desk_token(token)
    if not token_slug or token_slug != slug:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired desk token"
        )
    return token_slug


def _client_key(request: Request, slug: str) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    ip = (forwarded.split(",")[0].strip() if forwarded else None) or (
        request.client.host if request.client else "unknown"
    )
    return f"{slug}:{ip}"


@router.post("/events", response_model=EventCreated)
def create_event(body: EventCreate, db: Session = Depends(get_db)) -> EventCreated:
    event = queue_service.create_event(db, body.name, body.pin)
    return EventCreated(
        slug=event.slug,
        name=event.name,
        pin=body.pin,
        register_path=f"/e/{event.slug}",
        desk_path=f"/e/{event.slug}/desk",
        display_path=f"/e/{event.slug}/display",
    )


@router.get("/events/{slug}", response_model=EventPublic)
def get_event(slug: str, db: Session = Depends(get_db)) -> EventPublic:
    event = queue_service.get_event_by_slug(db, slug)
    counts = queue_service.count_by_status(db, event.id)
    return EventPublic(
        slug=event.slug,
        name=event.name,
        is_active=event.is_active,
        waiting_count=counts["waiting"],
        called_count=counts["called"],
        checked_in_count=counts["checked_in"],
        total_count=counts["total"],
    )


@router.patch("/events/{slug}", response_model=EventPublic)
def update_event(
    slug: str,
    body: EventUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(require_desk),
) -> EventPublic:
    event = queue_service.get_event_by_slug(db, slug)
    event = queue_service.set_event_active(db, event, body.is_active)
    counts = queue_service.count_by_status(db, event.id)
    return EventPublic(
        slug=event.slug,
        name=event.name,
        is_active=event.is_active,
        waiting_count=counts["waiting"],
        called_count=counts["called"],
        checked_in_count=counts["checked_in"],
        total_count=counts["total"],
    )


@router.post("/events/{slug}/auth", response_model=AuthResponse)
def auth_desk(
    slug: str,
    body: AuthRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthResponse:
    key = _client_key(request, slug)
    if auth_service.pin_rate_limited(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many PIN attempts. Wait a few minutes and try again.",
        )
    event = queue_service.get_event_by_slug(db, slug)
    if not auth_service.verify_pin(body.pin, event.pin_hash):
        auth_service.record_pin_failure(key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect PIN")
    auth_service.clear_pin_failures(key)
    token = auth_service.create_desk_token(event.slug)
    return AuthResponse(token=token, expires_in_hours=settings.desk_token_hours)


@router.post("/events/{slug}/register", response_model=RegisterResponse)
def register(slug: str, body: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    event = queue_service.get_event_by_slug(db, slug)
    if not event.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Event is not accepting registrations",
        )
    participant, already = queue_service.register_participant(
        db, event, body.name, str(body.email), body.team_name
    )
    return RegisterResponse(
        participant=ParticipantOut.model_validate(participant),
        status_path=qr_service.status_path(event.slug, participant.checkin_token),
        qr_url=qr_service.qr_api_path(participant.checkin_token),
        already_registered=already,
    )


@router.get("/events/{slug}/participants/{token}", response_model=ParticipantStatusOut)
def participant_status(
    slug: str, token: str, db: Session = Depends(get_db)
) -> ParticipantStatusOut:
    event = queue_service.get_event_by_slug(db, slug)
    participant = queue_service.get_participant_by_token(db, event, token)
    called = queue_service.get_called(db, event.id)
    return ParticipantStatusOut(
        event_name=event.name,
        event_slug=event.slug,
        participant=ParticipantPublic.model_validate(participant),
        people_ahead=queue_service.people_ahead(db, participant),
        now_serving=called.queue_number if called else None,
        now_serving_name=called.name if called else None,
        qr_url=qr_service.qr_api_path(participant.checkin_token),
        status_path=qr_service.status_path(event.slug, participant.checkin_token),
    )


@router.get("/events/{slug}/display", response_model=DisplayOut)
def display_feed(slug: str, db: Session = Depends(get_db)) -> DisplayOut:
    event = queue_service.get_event_by_slug(db, slug)
    called = queue_service.get_called(db, event.id)
    waiting = queue_service.up_next(db, event.id, limit=5)
    counts = queue_service.count_by_status(db, event.id)

    def to_display(p: Participant) -> DisplayParticipant:
        return DisplayParticipant(
            queue_number=p.queue_number,
            name=p.name,
            team_name=p.team_name,
            status=p.status,
        )

    return DisplayOut(
        event_name=event.name,
        event_slug=event.slug,
        now_serving=to_display(called) if called else None,
        up_next=[to_display(p) for p in waiting],
        waiting_count=counts["waiting"],
        checked_in_count=counts["checked_in"],
        total_count=counts["total"],
    )


@router.get("/events/{slug}/queue", response_model=QueueOut)
def desk_queue(
    slug: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_desk),
) -> QueueOut:
    event = queue_service.get_event_by_slug(db, slug)
    participants = queue_service.list_participants(db, event.id)
    called = queue_service.get_called(db, event.id)
    counts = queue_service.count_by_status(db, event.id)
    return QueueOut(
        event_name=event.name,
        event_slug=event.slug,
        is_active=event.is_active,
        now_serving=DeskParticipant.model_validate(called) if called else None,
        participants=[DeskParticipant.model_validate(p) for p in participants],
        waiting_count=counts["waiting"],
        called_count=counts["called"],
        checked_in_count=counts["checked_in"],
        skipped_count=counts["skipped"],
        total_count=counts["total"],
    )


@router.post("/events/{slug}/call-next", response_model=MessageOut)
def call_next(
    slug: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_desk),
) -> MessageOut:
    event = queue_service.get_event_by_slug(db, slug)
    participant = queue_service.call_next(db, event)
    return MessageOut(
        ok=True,
        message=f"Now serving #{participant.queue_number} — {participant.name}",
        participant=ParticipantOut.model_validate(participant),
    )


@router.post("/events/{slug}/checkin", response_model=MessageOut)
def checkin(
    slug: str,
    body: CheckinRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_desk),
) -> MessageOut:
    event = queue_service.get_event_by_slug(db, slug)
    participant = queue_service.checkin(db, event, body.token, body.queue_number)
    return MessageOut(
        ok=True,
        message=f"Checked in #{participant.queue_number} — {participant.name}",
        participant=ParticipantOut.model_validate(participant),
    )


@router.post("/events/{slug}/skip", response_model=MessageOut)
def skip(
    slug: str,
    body: SkipRequest | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_desk),
) -> MessageOut:
    event = queue_service.get_event_by_slug(db, slug)
    call_next_after = body.call_next if body else False
    participant = queue_service.skip_current(db, event, call_next_after=call_next_after)
    return MessageOut(
        ok=True,
        message=f"Skipped #{participant.queue_number} — {participant.name}",
        participant=ParticipantOut.model_validate(participant),
    )


@router.post("/events/{slug}/requeue", response_model=MessageOut)
def requeue(
    slug: str,
    body: RequeueRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_desk),
) -> MessageOut:
    event = queue_service.get_event_by_slug(db, slug)
    participant = queue_service.requeue(db, event, body.queue_number)
    return MessageOut(
        ok=True,
        message=f"Returned #{participant.queue_number} — {participant.name} to waiting",
        participant=ParticipantOut.model_validate(participant),
    )


@router.get("/qr/{token}.png")
def qr_image(token: str, db: Session = Depends(get_db)) -> Response:
    participant = db.scalar(select(Participant).where(Participant.checkin_token == token))
    if not participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown token")
    event = db.get(Event, participant.event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    png = qr_service.make_qr_png(qr_service.status_url(event.slug, token))
    return Response(content=png, media_type="image/png")
