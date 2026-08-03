from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError

from app.api.routes.events import router as events_router
from app.core.config import settings
from app.db import init_db, ping_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.secret_key in {"dev-secret-change-me", "change-me-to-a-long-random-string"}:
        print("WARNING: SECRET_KEY is a placeholder — set a strong secret before production.")
    init_db()
    yield


app = FastAPI(title="QueueAlign", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events_router)


@app.exception_handler(IntegrityError)
async def integrity_error(_request: Request, _exc: IntegrityError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": "Conflict — please retry"})


@app.exception_handler(OperationalError)
async def operational_error(_request: Request, _exc: OperationalError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Database busy — please retry"})


@app.get("/api/health")
def health() -> dict[str, str | bool]:
    db_ok = ping_db()
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "queuealign",
        "database": db_ok,
    }
