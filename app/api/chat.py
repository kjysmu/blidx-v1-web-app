from fastapi import APIRouter
from app.demo_store import demo_store
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest):
    result = demo_store.chat(payload.message)
    return {
        "reply": result["reply"],
        "actions": result["actions"],
        "post_id": result["post"]["id"] if result.get("post") else None,
    }
