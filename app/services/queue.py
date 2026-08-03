from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import Event, Participant, ParticipantStatus, generate_slug, utcnow
from app.services.auth import hash_pin


def get_event_by_slug(db: Session, slug: str) -> Event:
    event = db.scalar(select(Event).where(Event.slug == slug))
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


def create_event(db: Session, name: str, pin: str) -> Event:
    slug = generate_slug(name)
    while db.scalar(select(Event).where(Event.slug == slug)):
        slug = generate_slug(name)
    event = Event(name=name.strip(), slug=slug, pin_hash=hash_pin(pin))
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def set_event_active(db: Session, event: Event, is_active: bool) -> Event:
    event.is_active = is_active
    db.commit()
    db.refresh(event)
    return event


def count_by_status(db: Session, event_id: int) -> dict[str, int]:
    rows = db.execute(
        select(Participant.status, func.count())
        .where(Participant.event_id == event_id)
        .group_by(Participant.status)
    ).all()
    counts = {s.value: 0 for s in ParticipantStatus}
    for status_val, count in rows:
        key = status_val.value if isinstance(status_val, ParticipantStatus) else str(status_val)
        counts[key] = count
    counts["total"] = sum(counts[s.value] for s in ParticipantStatus)
    return counts


def next_queue_number(db: Session, event_id: int) -> int:
    current = db.scalar(
        select(func.max(Participant.queue_number)).where(Participant.event_id == event_id)
    )
    return (current or 0) + 1


def register_participant(
    db: Session, event: Event, name: str, email: str, team_name: str | None
) -> tuple[Participant, bool]:
    """Returns (participant, already_registered)."""
    email_norm = email.strip().lower()
    existing = db.scalar(
        select(Participant).where(
            Participant.event_id == event.id, Participant.email == email_norm
        )
    )
    if existing:
        return existing, True

    for _ in range(5):
        try:
            participant = Participant(
                event_id=event.id,
                name=name.strip(),
                email=email_norm,
                team_name=team_name.strip() if team_name else None,
                queue_number=next_queue_number(db, event.id),
                status=ParticipantStatus.waiting,
            )
            db.add(participant)
            db.commit()
            db.refresh(participant)
            return participant, False
        except IntegrityError:
            db.rollback()
            existing = db.scalar(
                select(Participant).where(
                    Participant.event_id == event.id, Participant.email == email_norm
                )
            )
            if existing:
                return existing, True
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Could not assign a queue number — try again",
    )


def get_participant_by_token(db: Session, event: Event, token: str) -> Participant:
    participant = db.scalar(
        select(Participant).where(
            Participant.event_id == event.id, Participant.checkin_token == token
        )
    )
    if not participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return participant


def get_called(db: Session, event_id: int) -> Participant | None:
    return db.scalar(
        select(Participant)
        .where(Participant.event_id == event_id, Participant.status == ParticipantStatus.called)
        .order_by(Participant.called_at.asc())
    )


def people_ahead(db: Session, participant: Participant) -> int:
    if participant.status != ParticipantStatus.waiting:
        return 0
    waiting_ahead = (
        db.scalar(
            select(func.count())
            .select_from(Participant)
            .where(
                Participant.event_id == participant.event_id,
                Participant.status == ParticipantStatus.waiting,
                Participant.queue_number < participant.queue_number,
            )
        )
        or 0
    )
    called = get_called(db, participant.event_id)
    return waiting_ahead + (1 if called else 0)


def list_participants(db: Session, event_id: int) -> list[Participant]:
    return list(
        db.scalars(
            select(Participant)
            .where(Participant.event_id == event_id)
            .order_by(Participant.queue_number.asc())
        ).all()
    )


def call_next(db: Session, event: Event) -> Participant:
    existing = get_called(db, event.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"#{existing.queue_number} is already being served. "
                "Check them in or skip first."
            ),
        )
    nxt = db.scalar(
        select(Participant)
        .where(
            Participant.event_id == event.id,
            Participant.status == ParticipantStatus.waiting,
        )
        .order_by(Participant.queue_number.asc())
    )
    if not nxt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No one waiting in queue"
        )
    nxt.status = ParticipantStatus.called
    nxt.called_at = utcnow()
    db.flush()
    called_count = (
        db.scalar(
            select(func.count())
            .select_from(Participant)
            .where(
                Participant.event_id == event.id,
                Participant.status == ParticipantStatus.called,
            )
        )
        or 0
    )
    if called_count > 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another guest is already being served. Refresh and try again.",
        )
    db.commit()
    db.refresh(nxt)
    return nxt


def skip_current(db: Session, event: Event, *, call_next_after: bool = False) -> Participant:
    current = get_called(db, event.id)
    if not current:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No one is currently called"
        )
    current.status = ParticipantStatus.skipped
    db.commit()
    db.refresh(current)
    if call_next_after:
        try:
            call_next(db, event)
        except HTTPException:
            pass
    return current


def requeue(db: Session, event: Event, queue_number: int) -> Participant:
    participant = db.scalar(
        select(Participant).where(
            Participant.event_id == event.id, Participant.queue_number == queue_number
        )
    )
    if not participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found")
    if participant.status not in (ParticipantStatus.skipped, ParticipantStatus.called):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot requeue from status {participant.status.value}",
        )
    participant.status = ParticipantStatus.waiting
    participant.called_at = None
    db.commit()
    db.refresh(participant)
    return participant


def checkin(
    db: Session,
    event: Event,
    token: str | None,
    queue_number: int | None,
) -> Participant:
    if not token and queue_number is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide token or queue_number",
        )
    participant: Participant | None = None
    if token:
        participant = db.scalar(
            select(Participant).where(
                Participant.event_id == event.id, Participant.checkin_token == token
            )
        )
    elif queue_number is not None:
        participant = db.scalar(
            select(Participant).where(
                Participant.event_id == event.id, Participant.queue_number == queue_number
            )
        )
    if not participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found")
    if participant.status == ParticipantStatus.checked_in:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already checked in")
    # Allow desk to check in waiting/called/skipped (walk-ups + QR)
    participant.status = ParticipantStatus.checked_in
    participant.checked_in_at = utcnow()
    if not participant.called_at:
        participant.called_at = utcnow()
    db.commit()
    db.refresh(participant)
    return participant


def up_next(db: Session, event_id: int, limit: int = 5) -> list[Participant]:
    return list(
        db.scalars(
            select(Participant)
            .where(Participant.event_id == event_id, Participant.status == ParticipantStatus.waiting)
            .order_by(Participant.queue_number.asc())
            .limit(limit)
        ).all()
    )
