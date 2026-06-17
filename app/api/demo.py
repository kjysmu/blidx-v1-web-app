from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.demo_store import demo_store

router = APIRouter()


class ProfilePayload(BaseModel):
    first_name: str | None = None
    role: str | None = None
    company_name: str | None = None
    company_website: str | None = None
    industry: str | None = None
    company_description: str | None = None
    expertise: list[str] | None = None
    writing_style: str | None = None
    writing_samples: list[str] | None = None
    audience: list[str] | None = None
    content_types: list[str] | None = None
    posting_frequency: str | None = None
    tone: str | None = None
    timezone: str | None = None


class MemoryPayload(BaseModel):
    raw_text: str = Field(min_length=3)
    category: str | None = None


class DraftPayload(BaseModel):
    topic: str = Field(min_length=3)
    source: str = "user_initiated"


class EditPayload(BaseModel):
    instructions: str = Field(min_length=2)


class ApprovePayload(BaseModel):
    schedule_type: str = "best_time"
    scheduled_at: str | None = None


@router.get("/state")
def get_state() -> dict[str, Any]:
    return demo_store.snapshot()


@router.put("/profile")
def update_profile(payload: ProfilePayload) -> dict[str, Any]:
    return demo_store.update_profile(payload.model_dump(exclude_none=True))


@router.post("/content-bank")
def create_content_bank_entry(payload: MemoryPayload) -> dict[str, Any]:
    return demo_store.add_memory(payload.raw_text, payload.category)


@router.post("/drafts")
def create_draft(payload: DraftPayload) -> dict[str, Any]:
    return demo_store.create_post(payload.topic, payload.source)


@router.post("/drafts/{draft_id}/edit")
def edit_draft(draft_id: str, payload: EditPayload) -> dict[str, Any]:
    post = demo_store.edit_post(draft_id, payload.instructions)
    if post is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return post


@router.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: str, payload: ApprovePayload) -> dict[str, Any]:
    post = demo_store.approve_post(
        draft_id, payload.schedule_type, payload.scheduled_at
    )
    if post is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return post


@router.post("/drafts/{draft_id}/save")
def save_draft(draft_id: str) -> dict[str, Any]:
    post = demo_store.save_post(draft_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return post


@router.post("/drafts/{draft_id}/delete")
def delete_draft(draft_id: str) -> dict[str, Any]:
    post = demo_store.delete_post(draft_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return post


@router.post("/reset")
def reset_demo() -> dict[str, Any]:
    return demo_store.reset()


@router.post("/seed-test-scenario")
def seed_test_scenario() -> dict[str, Any]:
    return demo_store.seed_test_scenario()
