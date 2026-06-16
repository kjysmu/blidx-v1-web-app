from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api import auth, chat, demo, generate, memory, posts, profile

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    version="0.1.0",
)


@app.get("/")
def root() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": settings.APP_NAME}

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(profile.router, prefix="/profile", tags=["Profile"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(memory.router, prefix="/memory", tags=["Memory"])
app.include_router(generate.router, prefix="/generate", tags=["Generate"])
app.include_router(posts.router, prefix="/posts", tags=["Posts"])
app.include_router(demo.router, prefix="/api", tags=["Web App"])
app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")
