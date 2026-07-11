import uuid
from copy import deepcopy
from typing import Any

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models.user_workspace import UserWorkspace
from app.models.workspace_data import (
    WorkspaceMemory,
    WorkspaceMessage,
    WorkspaceMetadata,
    WorkspacePost,
    WorkspaceProfile,
)


COLLECTION_KEYS = ("content_bank", "posts", "messages")
SCHEMA_VERSION = 1


class WorkspaceRepository:
    """Persists the web-app state in user-owned relational collections.

    JSON payloads preserve the evolving MVP API shape, while rows provide
    account isolation and avoid one large, frequently rewritten state blob.
    """

    def load(self, user_id: str) -> dict[str, Any] | None:
        parsed_user_id = uuid.UUID(user_id)
        with SessionLocal.begin() as db:
            metadata = db.get(WorkspaceMetadata, parsed_user_id)
            if metadata is None:
                legacy = db.scalar(
                    select(UserWorkspace).where(UserWorkspace.user_id == parsed_user_id)
                )
                return deepcopy(legacy.state) if legacy else None

            profile = db.get(WorkspaceProfile, parsed_user_id)
            memories = self._ordered_payloads(db, WorkspaceMemory, parsed_user_id)
            posts = self._ordered_payloads(db, WorkspacePost, parsed_user_id)
            messages = self._ordered_payloads(db, WorkspaceMessage, parsed_user_id)
            return self.assemble_state(
                metadata=metadata.data,
                profile=profile.data if profile else {},
                onboarding_completed=bool(profile and profile.onboarding_completed),
                content_bank=memories,
                posts=posts,
                messages=messages,
            )

    def save(self, user_id: str, state: dict[str, Any]) -> None:
        parsed_user_id = uuid.UUID(user_id)
        parts = self.partition_state(state)
        with SessionLocal.begin() as db:
            metadata = db.get(WorkspaceMetadata, parsed_user_id)
            if metadata is None:
                metadata = WorkspaceMetadata(
                    user_id=parsed_user_id,
                    data=parts["metadata"],
                    schema_version=SCHEMA_VERSION,
                )
                db.add(metadata)
            else:
                metadata.data = parts["metadata"]
                metadata.schema_version = SCHEMA_VERSION

            profile = db.get(WorkspaceProfile, parsed_user_id)
            if profile is None:
                db.add(
                    WorkspaceProfile(
                        user_id=parsed_user_id,
                        data=parts["profile"],
                        onboarding_completed=parts["onboarding_completed"],
                    )
                )
            else:
                profile.data = parts["profile"]
                profile.onboarding_completed = parts["onboarding_completed"]

            self._replace_collection(
                db, WorkspaceMemory, parsed_user_id, parts["content_bank"]
            )
            self._replace_collection(db, WorkspacePost, parsed_user_id, parts["posts"])
            self._replace_collection(
                db, WorkspaceMessage, parsed_user_id, parts["messages"]
            )

    @staticmethod
    def partition_state(state: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(state)
        return {
            "metadata": {
                key: value
                for key, value in source.items()
                if key not in {*COLLECTION_KEYS, "profile", "onboarding_completed"}
            },
            "profile": source.get("profile") or {},
            "onboarding_completed": bool(source.get("onboarding_completed")),
            "content_bank": source.get("content_bank") or [],
            "posts": source.get("posts") or [],
            "messages": source.get("messages") or [],
        }

    @staticmethod
    def assemble_state(
        *,
        metadata: dict[str, Any],
        profile: dict[str, Any],
        onboarding_completed: bool,
        content_bank: list[dict[str, Any]],
        posts: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        state = deepcopy(metadata)
        state.update(
            {
                "profile": deepcopy(profile),
                "onboarding_completed": onboarding_completed,
                "content_bank": deepcopy(content_bank),
                "posts": deepcopy(posts),
                "messages": deepcopy(messages),
            }
        )
        return state

    @staticmethod
    def _ordered_payloads(db, model, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(model).where(model.user_id == user_id).order_by(model.position)
        ).all()
        return [deepcopy(row.data) for row in rows]

    @staticmethod
    def _replace_collection(db, model, user_id: uuid.UUID, items: list[dict]) -> None:
        db.execute(delete(model).where(model.user_id == user_id))
        db.add_all(
            model(user_id=user_id, position=position, data=deepcopy(item))
            for position, item in enumerate(items)
        )


workspace_repository = WorkspaceRepository()
