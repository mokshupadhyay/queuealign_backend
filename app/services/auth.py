from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"

_pin_failures: dict[str, list[float]] = {}
_pin_lock = Lock()
MAX_PIN_ATTEMPTS = 8
PIN_WINDOW_SECONDS = 300


def hash_pin(pin: str) -> str:
    return pwd_context.hash(pin)


def verify_pin(pin: str, pin_hash: str) -> bool:
    return pwd_context.verify(pin, pin_hash)


def create_desk_token(event_slug: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.desk_token_hours)
    payload = {"sub": event_slug, "typ": "desk", "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_desk_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get("typ") != "desk":
            return None
        slug = payload.get("sub")
        return str(slug) if slug else None
    except JWTError:
        return None


def pin_rate_limited(key: str) -> bool:
    now = datetime.now(timezone.utc).timestamp()
    with _pin_lock:
        attempts = [t for t in _pin_failures.get(key, []) if now - t < PIN_WINDOW_SECONDS]
        _pin_failures[key] = attempts
        return len(attempts) >= MAX_PIN_ATTEMPTS


def record_pin_failure(key: str) -> None:
    now = datetime.now(timezone.utc).timestamp()
    with _pin_lock:
        attempts = [t for t in _pin_failures.get(key, []) if now - t < PIN_WINDOW_SECONDS]
        attempts.append(now)
        _pin_failures[key] = attempts


def clear_pin_failures(key: str) -> None:
    with _pin_lock:
        _pin_failures.pop(key, None)
