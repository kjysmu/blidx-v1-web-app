from fastapi import APIRouter
from app.schemas.generate import GenerateRequest, GenerateResponse

router = APIRouter()


@router.post("", response_model=GenerateResponse)
def generate_post(payload: GenerateRequest):
    # TODO Day 7–9:
    # profile + memory + topic -> draft
    return {
        "post_id": "placeholder_post_id",
        "post": f"Placeholder LinkedIn draft about: {payload.topic}",
    }
