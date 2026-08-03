# QueueAlign API

Fair-queue check-in for hackathons. FastAPI + SQLite (local) / Neon Postgres (production).

## Setup

```bash
cd queuealign_backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8001
```

API docs: http://127.0.0.1:8001/docs

Health: `GET /api/health`

## Database

- **Local:** SQLite (`DATABASE_URL=sqlite:///./queuealign.db`)
- **Vercel / production:** Neon Postgres — set `DATABASE_URL` in the Vercel project env  
  (SQLAlchemy uses `psycopg`; `postgresql://…` is rewritten automatically)

Also set `SECRET_KEY`, `CORS_ORIGINS`, and `FRONTEND_URL` on Vercel.

## Notable endpoints

- `POST /api/events` — create
- `PATCH /api/events/{slug}` — open/close registration (desk auth)
- `POST /api/events/{slug}/register` — register (returns existing ticket if email already used)
- `POST /api/events/{slug}/call-next` | `checkin` | `skip` | `requeue`
- `GET /api/events/{slug}/display` — public board
- `GET /api/qr/{token}.png` — ticket QR
