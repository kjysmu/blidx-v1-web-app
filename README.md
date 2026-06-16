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
local MVP endpoints and a JSON demo store so the product flow can be tested
without PostgreSQL, LinkedIn, Stripe, or paid LLM credentials.

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
