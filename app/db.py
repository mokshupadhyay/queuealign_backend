from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _resolve_database_url(url: str) -> str:
    # SQLAlchemy + psycopg3
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")

    if url.startswith("sqlite:///./"):
        root = Path(__file__).resolve().parent.parent
        db_path = root / url.removeprefix("sqlite:///./")
        return f"sqlite:///{db_path}"
    return url


DATABASE_URL = _resolve_database_url(settings.database_url)
IS_SQLITE = DATABASE_URL.startswith("sqlite")

connect_args: dict = {"check_same_thread": False} if IS_SQLITE else {}
# Serverless (Vercel) + Neon: no persistent connections between invocations
engine_kwargs: dict = {"connect_args": connect_args, "pool_pre_ping": True}
if not IS_SQLITE:
    engine_kwargs["poolclass"] = NullPool

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ARG001
    if not IS_SQLITE:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from app.models import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def ping_db() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
