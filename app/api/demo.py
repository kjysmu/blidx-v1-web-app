from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import use_request_user
from app.demo_store import DuplicateSourceError, current_user_id, demo_store
from app.quality_benchmarks import BENCHMARK_SCENARIOS
from app.services.source_ingestion_service import (
    MAX_SOURCE_BYTES,
    SourceIngestionError,
    source_ingestion_service,
)

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


class MemoryUpdatePayload(BaseModel):
    raw_text: str | None = Field(default=None, min_length=3)
    category: str | None = None
    freshness: str | None = None
    content_potential: str | None = None


class DraftPayload(BaseModel):
    topic: str = Field(min_length=3)
    source: str = "user_initiated"
    source_ids: list[str] = Field(default_factory=list, max_length=5)


class EditPayload(BaseModel):
    instructions: str = Field(min_length=2)


class VariantPayload(BaseModel):
    variant_id: str = Field(min_length=1)


class ApprovePayload(BaseModel):
    schedule_type: str = "best_time"
    scheduled_at: str | None = None


class ChatPayload(BaseModel):
    message: str = Field(min_length=2)
    # Optional short human label shown in the chat transcript while `message`
    # (e.g. a full angle prompt) drives the actual processing.
    display: str | None = Field(default=None, max_length=200)
    source_ids: list[str] = Field(default_factory=list, max_length=5)


class SourceUrlPayload(BaseModel):
    url: str = Field(min_length=8, max_length=2_000)
    category: str | None = None


class LinkedInTrackPayload(BaseModel):
    url: str | None = None


class DraftFeedbackPayload(BaseModel):
    sentiment: Literal["sounds_like_me", "needs_work"]
    reason: str | None = Field(default=None, max_length=500)
    tags: list[
        Literal[
            "too_formal",
            "too_generic",
            "too_polished",
            "wrong_emphasis",
            "too_long",
            "too_salesy",
        ]
    ] = Field(default_factory=list, max_length=6)


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


def source_error(error: SourceIngestionError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": error.code, "message": str(error)},
    )


def save_ingested_source(
    source,
    category: str | None,
    user: dict | None,
) -> dict[str, Any]:
    previous_user_id = current_user_id.set(user["id"] if user else None)
    try:
        return demo_store.add_source(source.text, category, source.metadata())
    except DuplicateSourceError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "source_duplicate",
                "message": "This source is already in your Content Bank.",
                "entry_id": error.entry_id,
            },
        ) from error
    finally:
        current_user_id.reset(previous_user_id)


@router.post("/content-bank/upload")
async def upload_content_bank_source(
    file: UploadFile = File(...),
    category: str | None = Form(default=None),
    user: dict | None = Depends(use_request_user),
) -> dict[str, Any]:
    data = await file.read(MAX_SOURCE_BYTES + 1)
    await file.close()
    try:
        source = source_ingestion_service.extract_upload(
            filename=file.filename or "source",
            content_type=file.content_type,
            data=data,
        )
    except SourceIngestionError as error:
        raise source_error(error) from error
    return save_ingested_source(source, category, user)


@router.post("/content-bank/import-url")
async def import_content_bank_url(
    payload: SourceUrlPayload,
    user: dict | None = Depends(use_request_user),
) -> dict[str, Any]:
    try:
        source = await source_ingestion_service.import_url(payload.url)
    except SourceIngestionError as error:
        raise source_error(error) from error
    return save_ingested_source(source, payload.category, user)


@router.put("/content-bank/{memory_id}")
def update_content_bank_entry(
    memory_id: str, payload: MemoryUpdatePayload
) -> dict[str, Any]:
    entry = demo_store.update_memory(memory_id, payload.model_dump(exclude_none=True))
    if entry is None:
        raise HTTPException(status_code=404, detail="Content Bank entry not found")
    return entry


@router.delete("/content-bank/{memory_id}")
def delete_content_bank_entry(memory_id: str) -> dict[str, Any]:
    entry = demo_store.delete_memory(memory_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Content Bank entry not found")
    return {"deleted": True, "entry": entry}


@router.post("/onboarding/complete")
def complete_onboarding(payload: OnboardingPayload) -> dict[str, Any]:
    profile = payload.model_dump(exclude={"first_memory"})
    return demo_store.complete_onboarding(profile, payload.first_memory)


@router.post("/drafts")
def create_draft(payload: DraftPayload) -> dict[str, Any]:
    return demo_store.create_post(payload.topic, payload.source, payload.source_ids)


@router.post("/chat/message")
def chat_message(payload: ChatPayload) -> dict[str, Any]:
    return demo_store.chat(
        payload.message,
        display=payload.display,
        source_ids=payload.source_ids,
    )


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


@router.post("/drafts/{draft_id}/feedback")
def record_draft_feedback(draft_id: str, payload: DraftFeedbackPayload) -> dict[str, Any]:
    feedback = demo_store.record_draft_feedback(
        draft_id,
        payload.sentiment,
        payload.reason,
        payload.tags,
    )
    if feedback is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return feedback


@router.get("/quality/report")
def quality_report() -> dict[str, Any]:
    return demo_store.snapshot()["quality_report"]


@router.get("/quality/benchmarks")
def quality_benchmarks() -> dict[str, Any]:
    return {"scenarios": BENCHMARK_SCENARIOS, "count": len(BENCHMARK_SCENARIOS)}


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


@router.post("/drafts/{draft_id}/restore")
def restore_draft(draft_id: str) -> dict[str, Any]:
    post = demo_store.restore_post(draft_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Draft not found or not skipped")
    return post


@router.post("/reset")
def reset_demo() -> dict[str, Any]:
    return demo_store.reset()


@router.post("/seed-test-scenario")
def seed_test_scenario() -> dict[str, Any]:
    return demo_store.seed_test_scenario()
