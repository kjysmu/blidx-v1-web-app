from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import use_request_user
from app.demo_store import demo_store

router = APIRouter(dependencies=[Depends(use_request_user)])


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
    preferred_structure: str | None = None
    avoided_phrases: list[str] | None = None
    cta_style: str | None = None
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


class VariantPayload(BaseModel):
    variant_id: str = Field(min_length=1)


class ApprovePayload(BaseModel):
    schedule_type: str = "best_time"
    scheduled_at: str | None = None


class ChatPayload(BaseModel):
    message: str = Field(min_length=2)


class LinkedInTrackPayload(BaseModel):
    url: str | None = None


class OnboardingPayload(BaseModel):
    first_name: str = Field(min_length=1)
    role: str | None = None
    company_name: str = Field(min_length=1)
    company_website: str | None = None
    industry: str = Field(min_length=1)
    company_description: str = Field(min_length=3)
    audience: list[str] = Field(default_factory=list)
    expertise: list[str] = Field(default_factory=list)
    content_types: list[str] = Field(default_factory=list)
    posting_frequency: str = "3-4x_per_week"
    tone: str = "Insightful & measured"
    writing_style: str | None = None
    writing_samples: list[str] = Field(default_factory=list)
    preferred_structure: str | None = None
    avoided_phrases: list[str] = Field(default_factory=list)
    cta_style: str | None = None
    first_memory: str | None = None


@router.get("/state")
def get_state() -> dict[str, Any]:
    return demo_store.snapshot()


@router.put("/profile")
def update_profile(payload: ProfilePayload) -> dict[str, Any]:
    return demo_store.update_profile(payload.model_dump(exclude_none=True))


@router.post("/content-bank")
def create_content_bank_entry(payload: MemoryPayload) -> dict[str, Any]:
    return demo_store.add_memory(payload.raw_text, payload.category)


@router.post("/onboarding/complete")
def complete_onboarding(payload: OnboardingPayload) -> dict[str, Any]:
    profile = payload.model_dump(exclude={"first_memory"})
    return demo_store.complete_onboarding(profile, payload.first_memory)


@router.post("/drafts")
def create_draft(payload: DraftPayload) -> dict[str, Any]:
    return demo_store.create_post(payload.topic, payload.source)


@router.post("/chat/message")
def chat_message(payload: ChatPayload) -> dict[str, Any]:
    return demo_store.chat(payload.message)


@router.post("/drafts/{draft_id}/edit")
def edit_draft(draft_id: str, payload: EditPayload) -> dict[str, Any]:
    post = demo_store.edit_post(draft_id, payload.instructions)
    if post is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return post


@router.post("/drafts/{draft_id}/use-variant")
def use_draft_variant(draft_id: str, payload: VariantPayload) -> dict[str, Any]:
    post = demo_store.use_variant(draft_id, payload.variant_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Draft variant not found")
    return post


@router.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: str, payload: ApprovePayload) -> dict[str, Any]:
    post = demo_store.approve_post(
        draft_id, payload.schedule_type, payload.scheduled_at
    )
    if post is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return post


@router.post("/drafts/{draft_id}/publish")
def publish_draft(draft_id: str) -> dict[str, Any]:
    result = demo_store.publish_post(draft_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return result


@router.post("/drafts/{draft_id}/track-linkedin-url")
def track_linkedin_url(draft_id: str, payload: LinkedInTrackPayload) -> dict[str, Any]:
    post = demo_store.track_linkedin_url(draft_id, payload.url)
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
