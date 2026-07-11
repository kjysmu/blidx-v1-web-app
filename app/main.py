from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import (
    security_configuration_status,
    settings,
    validate_runtime_configuration,
)
from app.api import admin, auth, chat, demo, generate, integrations, memory, posts, profile

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

def initialize_database() -> None:
    if not settings.USE_DATABASE_STORAGE:
        return

    from app.core.database import Base, engine
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_runtime_configuration()
    initialize_database()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
def root() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "security": security_configuration_status(),
    }

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(profile.router, prefix="/profile", tags=["Profile"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(memory.router, prefix="/memory", tags=["Memory"])
app.include_router(generate.router, prefix="/generate", tags=["Generate"])
app.include_router(posts.router, prefix="/posts", tags=["Posts"])
app.include_router(demo.router, prefix="/api", tags=["Web App"])
app.include_router(integrations.router, prefix="/api/integrations", tags=["Integrations"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")
