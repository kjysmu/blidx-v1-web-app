from fastapi import APIRouter
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest):
    # TODO Day 10–12:
    # user message -> Mira -> memory -> research -> content -> draft
    return {
        "reply": "Mira placeholder response. Backend skeleton is working.",
        "actions": [],
        "post_id": None,
    }
