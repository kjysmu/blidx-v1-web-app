from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserProfileCreate(BaseModel):
    role: str | None = None
    company: str | None = None
    industry: str | None = None
    expertise: list[str] = Field(default_factory=list)
    audience: list[str] = Field(default_factory=list)
    content_types: list[str] = Field(default_factory=list)
    posting_frequency: int | None = Field(default=None, ge=0)
    tone: str | None = None
    raw_source: str | None = None
    writing_samples: list[str] = Field(default_factory=list)


class UserProfileResponse(UserProfileCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    created_at: datetime
