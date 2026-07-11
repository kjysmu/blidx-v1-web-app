from copy import deepcopy

from app.repositories.workspace_repository import WorkspaceRepository


def sample_state() -> dict:
    return {
        "user": {"id": "user-1", "email": "jae@example.com", "user_name": "Jae"},
        "profile": {"first_name": "Jae", "company_name": "Blidx"},
        "onboarding_completed": True,
        "content_bank": [
            {"id": "memory-1", "raw_text": "A real founder moment."},
            {"id": "memory-2", "raw_text": "A second moment."},
        ],
        "posts": [
            {"id": "post-1", "content": "Draft text", "status": "pending"}
        ],
        "messages": [
            {"id": "message-1", "role": "user", "content": "Draft this."},
            {"id": "message-2", "role": "mira", "content": "Here is a draft."},
        ],
        "mira_workflow": {"stage": "review", "last_topic": "AI"},
        "conversation_signals": ["Prefers concise hooks"],
        "linkedin": {"connected": False, "access_token": None},
    }


def test_workspace_state_round_trip_is_lossless():
    original = sample_state()
    parts = WorkspaceRepository.partition_state(original)

    rebuilt = WorkspaceRepository.assemble_state(
        metadata=parts["metadata"],
        profile=parts["profile"],
        onboarding_completed=parts["onboarding_completed"],
        content_bank=parts["content_bank"],
        posts=parts["posts"],
        messages=parts["messages"],
    )

    assert rebuilt == original


def test_workspace_collections_are_not_duplicated_in_metadata():
    original = sample_state()
    parts = WorkspaceRepository.partition_state(original)

    assert "profile" not in parts["metadata"]
    assert "content_bank" not in parts["metadata"]
    assert "posts" not in parts["metadata"]
    assert "messages" not in parts["metadata"]
    assert parts["metadata"]["mira_workflow"]["stage"] == "review"


def test_workspace_partition_does_not_mutate_live_state():
    original = sample_state()
    before = deepcopy(original)
    parts = WorkspaceRepository.partition_state(original)
    parts["profile"]["first_name"] = "Changed"
    parts["content_bank"][0]["raw_text"] = "Changed"

    assert original == before
