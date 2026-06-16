from fastapi import APIRouter
from app.schemas.memory import MemoryCreate, MemoryResponse

router = APIRouter()


@router.post("", response_model=MemoryResponse)
def create_memory(payload: MemoryCreate):
    # TODO Day 7–9: save content bank entry
    return {
        "id": "placeholder_memory_id",
        "user_id": "placeholder_user_id",
        **payload.model_dump(),
    }


@router.get("")
def list_memory():
    # TODO Day 7–9: list current user's content bank entries
    return []
