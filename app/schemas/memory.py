from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MemoryCreate(BaseModel):
    raw_text: str
    url: str | None = None
    topic: str | None = None
    tags: list[str] = Field(default_factory=list)
    importance_score: int = Field(default=1, ge=1)


class MemoryResponse(MemoryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    created_at: datetime
