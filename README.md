# Blidx Backend

FastAPI backend for the Blidx V1 content workflow.

## Stack

- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Pydantic
- JWT Auth
- Service / Repository architecture

## Setup

```bash
cd blidx-backend-skeleton
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
cp .env.example .env
```

## Run locally

```bash
uvicorn app.main:app --reload
```

Then open:

```txt
http://localhost:8000/
```

The root URL serves the local mobile-first Blidx web app. It includes a
functional test workflow for profile personalization, Content Bank capture,
draft generation, editing, scheduling, Library, and Calendar.

API documentation remains available at:

```txt
http://localhost:8000/docs
```

## Database

Create the configured PostgreSQL database, then apply migrations:

```bash
alembic upgrade head
```

The initial schema includes:

- users and authentication identity fields
- onboarding and personalization profiles
- Content Bank entries
- posts with approval, scheduling, publishing, and source state

## Tests

```bash
pytest
```

## API routes

```txt
GET /health
POST /auth/register
POST /auth/login
GET /profile
POST /profile
PUT /profile
POST /chat
POST /memory
GET /memory
POST /generate
GET /posts
POST /posts/{post_id}/approve
POST /posts/{post_id}/edit
POST /posts/{post_id}/skip
```

The original route handlers remain placeholders. The web app uses the `/api`
MVP endpoints and a JSON demo store so the product flow can be tested while the
production database/auth layers are still being connected.

## Current integration status

- Claude / Anthropic: supported through `ANTHROPIC_API_KEY`. When the key is
  missing or the API call fails, Mira falls back to the deterministic demo
  generator so the app stays usable.
- LinkedIn: OAuth URL generation and token exchange helpers are implemented.
  The tester-safe fallback is also available in the UI: copy the draft and open
  LinkedIn for manual posting.
- Admin: `/admin` is available behind HTTP Basic auth. Set `ADMIN_USERNAME` and
  `ADMIN_PASSWORD` in the environment before enabling it on staging.
- PayloadCMS: reviewed for V1. It is a strong Next.js-native CMS/admin option,
  but it adds a second backend stack while the MVP is still FastAPI-first. The
  current recommendation is to defer PayloadCMS and use the lightweight `/admin`
  route until the product needs a marketer-managed CMS or a full Next.js app.

### Required secrets

Never commit `.env` or real keys. Configure these in Render's Environment tab:

```txt
ANTHROPIC_API_KEY
LINKEDIN_CLIENT_ID
LINKEDIN_CLIENT_SECRET
LINKEDIN_REDIRECT_URI
ADMIN_USERNAME
ADMIN_PASSWORD
```

The current LinkedIn app redirect URLs provided by Malia are for
`localhost:3000` and `app.blidx.com`. The Render staging URL will not complete
OAuth until it is added to LinkedIn or routed behind `app.blidx.com`.

## Deploy to Render

This repository includes a `render.yaml` blueprint for the current local MVP.
It deploys the FastAPI app and serves the web interface from `/`.

Render settings:

```txt
Runtime: Python
Build command: pip install -r requirements.txt
Start command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health check path: /health
```

The local MVP uses `data/demo_state.json` for demo persistence. The Render
blueprint mounts a small persistent disk at `data/` so demo data survives
service restarts.
