from pydantic import BaseModel


class GenerateRequest(BaseModel):
    topic: str


class GenerateResponse(BaseModel):
    post_id: str
    post: str
