from fastapi import APIRouter
from app.schemas.posts import PostEditRequest, PostResponse

router = APIRouter()


@router.get("")
def list_posts():
    # TODO Day 13–14: return current user's posts
    return []


@router.post("/{post_id}/approve", response_model=PostResponse)
def approve_post(post_id: str):
    # TODO Day 13–14: mark post approved
    return {
        "id": post_id,
        "content": "placeholder content",
        "status": "approved",
        "source": "user_initiated",
        "scheduled_at": None,
        "published_url": None,
    }


@router.post("/{post_id}/edit", response_model=PostResponse)
def edit_post(post_id: str, payload: PostEditRequest):
    # TODO Day 13–14: create post version and update content
    return {
        "id": post_id,
        "content": payload.content,
        "status": "draft",
        "source": "user_initiated",
        "scheduled_at": None,
        "published_url": None,
    }


@router.post("/{post_id}/skip", response_model=PostResponse)
def skip_post(post_id: str):
    # TODO Day 13–14: mark skipped or archived
    return {
        "id": post_id,
        "content": "placeholder content",
        "status": "skipped",
        "source": "user_initiated",
        "scheduled_at": None,
        "published_url": None,
    }
