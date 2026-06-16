from fastapi import APIRouter
from app.schemas.profile import UserProfileCreate, UserProfileResponse

router = APIRouter()


@router.get("", response_model=UserProfileResponse)
def get_profile():
    # TODO Day 5–6: return authenticated user's profile
    return {
        "id": "placeholder_profile_id",
        "user_id": "placeholder_user_id",
        "role": None,
        "company": None,
        "industry": None,
        "expertise": [],
        "audience": [],
        "content_types": [],
        "posting_frequency": None,
        "tone": None,
        "raw_source": None,
        "writing_samples": [],
    }


@router.post("", response_model=UserProfileResponse)
def create_profile(payload: UserProfileCreate):
    # TODO Day 5–6: create profile
    return {
        "id": "placeholder_profile_id",
        "user_id": "placeholder_user_id",
        **payload.model_dump(),
    }


@router.put("", response_model=UserProfileResponse)
def update_profile(payload: UserProfileCreate):
    # TODO Day 5–6: update profile
    return {
        "id": "placeholder_profile_id",
        "user_id": "placeholder_user_id",
        **payload.model_dump(),
    }
