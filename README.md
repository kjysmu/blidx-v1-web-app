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

For browser-level QA of the full signup/onboarding/Content Bank/Mira/draft
workflow:

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
pytest tests/test_e2e_browser.py
```

For a paid, manual quality comparison between Mira and a plain-Claude baseline:

```bash
python scripts/run_quality_benchmark.py --list
python scripts/run_quality_benchmark.py --limit 1
```

The full catalog contains five founder-content scenarios. Each executed scenario
makes two Anthropic calls, so it is never run automatically during tests or deploys.

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

The web app uses the `/api` endpoints. In staging, authenticated users and their
profiles, Content Bank entries, drafts, and messages are persisted in separate
Postgres workspace tables. Local development can still use JSON files by setting
`USE_DATABASE_STORAGE=false`.

## Current integration status

- Claude / Anthropic: supported through `ANTHROPIC_API_KEY`. When the key is
  missing or the API call fails, Mira falls back to the deterministic demo
  generator so the app stays usable.
- LinkedIn: signed one-time OAuth state binds each connection to the Blidx user
  who started it. Tokens are encrypted at rest, disconnect/expiry states are
  supported, and text publishing uses LinkedIn's versioned Posts API. The
  tester-safe copy/open fallback remains available when OAuth or publishing fails.
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
LINKEDIN_TOKEN_ENCRYPTION_KEY
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

The Render blueprint enables Postgres persistence with
`USE_DATABASE_STORAGE=true`. The persistent disk remains available for local
fallback data, but authenticated staging workspaces no longer depend on it.
