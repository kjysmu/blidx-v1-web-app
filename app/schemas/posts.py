from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class PostStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    SKIPPED = "skipped"


class PostSource(str, Enum):
    USER_INITIATED = "user_initiated"
    MIRA_INITIATED = "mira_initiated"


class PostEditRequest(BaseModel):
    content: str


class PostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    content: str
    status: PostStatus
    source: PostSource
    created_at: datetime
    scheduled_at: datetime | None = None
    published_url: str | None = None
