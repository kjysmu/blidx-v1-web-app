import json
import re
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.core.config import settings
from app.core.database import SessionLocal
from app.integrations.llm import ClaudeProvider
from app.models.user import User
from app.models.user_workspace import UserWorkspace


class CurrentUserContext:
    def __init__(self) -> None:
        self.local = threading.local()

    def get(self) -> str | None:
        return getattr(self.local, "user_id", None)

    def set(self, user_id: str | None) -> str | None:
        previous = self.get()
        self.local.user_id = user_id
        return previous

    def reset(self, token: str | None) -> None:
        self.local.user_id = token


current_user_id = CurrentUserContext()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DemoStore:
    def __init__(self) -> None:
        self.path = Path(__file__).resolve().parent.parent / "data" / "demo_state.json"
        self.users_dir = self.path.parent / "users"
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.users_dir.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(self._initial_state())

    def _initial_state(self, user: dict | None = None) -> dict:
        now = utc_now().isoformat()
        user_block = user or {
            "id": str(uuid.uuid4()),
            "email": "jae@blidx.local",
            "user_name": "Jae",
        }
        first_name = (user_block.get("user_name") or "Jae").split()[0]
        return {
            "user": user_block,
            "profile": {
                "first_name": first_name,
                "role": "Founder / CEO",
                "company_name": "Blidx",
                "company_website": "https://blidx.com",
                "industry": "SaaS / Software",
                "company_description": (
                    "Blidx helps founders turn their work and insights into "
                    "consistent LinkedIn content."
                ),
                "expertise": ["AI / Machine Learning", "Product Strategy"],
                "writing_style": "",
                "writing_samples": [],
                "preferred_structure": "Hook, context, lesson, reflective question",
                "avoided_phrases": ["game changer", "unlock", "10x"],
                "cta_style": "Reflective question",
                "audience": ["Founders", "Industry Peers"],
                "content_types": ["Industry insights", "Lessons learned"],
                "posting_frequency": "3-4x_per_week",
                "tone": "Insightful & measured",
                "timezone": "Asia/Singapore",
            },
            "content_bank": [],
            "posts": [],
            "onboarding_completed": user is None,
            "messages": [
                {
                    "id": str(uuid.uuid4()),
                    "role": "mira",
                    "content": "Your pipeline is clear. What should we turn into your next post?",
                    "created_at": now,
                    "kind": "message",
                }
            ],
            "mira_workflow": {
                "stage": "capture",
                "last_topic": None,
                "last_angles": [],
                "last_memory_id": None,
                "updated_at": now,
            },
            "linkedin": {
                "connected": False,
                "access_token": None,
                "profile": None,
                "connected_at": None,
            },
        }

    def _state_path(self) -> Path:
        user_id = current_user_id.get()
        if not user_id:
            return self.path
        return self.users_dir / f"{user_id}.json"

    def _read(self) -> dict:
        if self._database_storage_enabled():
            return self._read_db_state()

        path = self._state_path()
        if not path.exists():
            self._write(self._initial_state({"id": current_user_id.get(), "email": "", "user_name": "User"}))
        return self._normalize_state(json.loads(path.read_text()))

    def _write(self, state: dict) -> None:
        if self._database_storage_enabled():
            self._write_db_state(state)
            return

        self._state_path().write_text(json.dumps(state, indent=2))

    def ensure_user_state(self, user: dict) -> dict:
        with self.lock:
            token = current_user_id.set(user["id"])
            try:
                if settings.USE_DATABASE_STORAGE:
                    state = self._read()
                    state["user"] = self._user_block(user)
                    self._write(state)
                    return self._public_state(state)

                path = self._state_path()
                if path.exists():
                    state = self._read()
                    state["user"] = self._user_block(user)
                    self._write(state)
                else:
                    state = self._initial_state(self._user_block(user))
                    self._write(state)
                return self._public_state(state)
            finally:
                current_user_id.reset(token)

    @staticmethod
    def _database_storage_enabled() -> bool:
        return bool(settings.USE_DATABASE_STORAGE and current_user_id.get())

    @staticmethod
    def _user_block(user: dict) -> dict:
        return {
            "id": user["id"],
            "email": user["email"],
            "user_name": user.get("user_name") or user["email"].split("@")[0],
        }

    def _read_db_state(self) -> dict:
        user_id = current_user_id.get()
        parsed_user_id = uuid.UUID(user_id)
        with SessionLocal() as db:
            workspace = (
                db.query(UserWorkspace)
                .filter(UserWorkspace.user_id == parsed_user_id)
                .first()
            )
            if workspace is None:
                workspace = UserWorkspace(
                    user_id=parsed_user_id,
                    state=self._initial_state(self._db_user_block(db, parsed_user_id)),
                )
                db.add(workspace)
                db.commit()
                db.refresh(workspace)
            return self._normalize_state(deepcopy(workspace.state))

    def _write_db_state(self, state: dict) -> None:
        user_id = current_user_id.get()
        parsed_user_id = uuid.UUID(user_id)
        with SessionLocal() as db:
            workspace = (
                db.query(UserWorkspace)
                .filter(UserWorkspace.user_id == parsed_user_id)
                .first()
            )
            if workspace is None:
                workspace = UserWorkspace(
                    user_id=parsed_user_id,
                    state=deepcopy(state),
                )
                db.add(workspace)
            else:
                workspace.state = deepcopy(state)
            db.commit()

    @staticmethod
    def _db_user_block(db, user_id: uuid.UUID) -> dict:
        user = db.get(User, user_id)
        if not user:
            return {"id": str(user_id), "email": "", "user_name": "User"}
        return {
            "id": str(user.id),
            "email": user.email,
            "user_name": user.user_name or user.email.split("@")[0],
        }

    def snapshot(self) -> dict:
        with self.lock:
            return self._public_state(self._read())

    def update_profile(self, profile: dict) -> dict:
        with self.lock:
            state = self._read()
            state["profile"].update(profile)
            self._write(state)
            return deepcopy(state["profile"])

    def complete_onboarding(self, profile: dict, first_memory: str | None = None) -> dict:
        with self.lock:
            state = self._read()
            state["profile"].update(profile)
            state["onboarding_completed"] = True
            if first_memory and first_memory.strip():
                state["content_bank"].insert(0, self._memory_entry(first_memory))
            first_name = state["profile"].get("first_name") or "there"
            state["messages"] = [
                {
                    "id": str(uuid.uuid4()),
                    "role": "mira",
                    "content": (
                        f"Welcome, {first_name}. I set up your Blidx workspace. "
                        "Tell me what happened this week, ask for content angles, or ask me to draft your first LinkedIn post."
                    ),
                    "created_at": utc_now().isoformat(),
                    "kind": "message",
                }
            ]
            self._write(state)
            return self._public_state(state)

    def add_memory(self, raw_text: str, category: str | None = None) -> dict:
        category = category or self._categorize(raw_text)
        entry = {
            "id": str(uuid.uuid4()),
            "raw_text": raw_text.strip(),
            "category": category,
            "tags": [category.title()],
            "freshness": "fresh",
            "content_potential": self._potential(raw_text),
            "created_at": utc_now().isoformat(),
        }
        with self.lock:
            state = self._read()
            state["content_bank"].insert(0, entry)
            self._write(state)
        return deepcopy(entry)

    def update_memory(self, memory_id: str, updates: dict) -> dict | None:
        allowed_freshness = {"fresh", "used", "archived"}
        allowed_potential = {"low", "medium", "high"}
        with self.lock:
            state = self._read()
            for entry in state.get("content_bank", []):
                if entry.get("id") != memory_id:
                    continue
                if updates.get("raw_text") is not None:
                    entry["raw_text"] = updates["raw_text"].strip()
                if updates.get("category") is not None:
                    category = updates["category"].strip() or self._categorize(entry["raw_text"])
                    entry["category"] = category
                    entry["tags"] = [category.title()]
                if updates.get("freshness") in allowed_freshness:
                    entry["freshness"] = updates["freshness"]
                if updates.get("content_potential") in allowed_potential:
                    entry["content_potential"] = updates["content_potential"]
                entry["updated_at"] = utc_now().isoformat()
                self._write(state)
                return deepcopy(entry)
        return None

    def delete_memory(self, memory_id: str) -> dict | None:
        with self.lock:
            state = self._read()
            entries = state.get("content_bank", [])
            for index, entry in enumerate(entries):
                if entry.get("id") == memory_id:
                    removed = entries.pop(index)
                    self._write(state)
                    return deepcopy(removed)
        return None

    def create_post(self, topic: str, source: str = "user_initiated") -> dict:
        with self.lock:
            state = self._read()
            post = self._draft(state, topic, source)
            state["posts"].insert(0, post)
            self._append_message(
                state,
                "mira",
                f"I created a review-ready draft for “{topic.strip()}”. You can edit it, save it, approve it, or send it to LinkedIn.",
                kind="draft_created",
                post_id=post["id"],
            )
            self._write(state)
            return deepcopy(post)

    def chat(self, content: str) -> dict:
        content = content.strip()
        with self.lock:
            state = self._read()
            intent = self._detect_chat_intent(content)
            self._set_workflow(state, last_intent=intent)
            self._append_message(state, "user", content)

            if self._is_off_topic(content):
                reply = (
                    "I’m going to keep us inside Blidx for now: your LinkedIn content, "
                    "Content Bank, drafts, publishing, and founder voice. What should we turn "
                    "into a post?"
                )
                self._append_message(state, "mira", reply, kind="redirect")
                self._write(state)
                return {"reply": reply, "actions": ["redirect"], "post": None, "state": self._public_state(state)}

            selected_angle_topic = self._topic_from_selected_angle(state, content)
            memory = None
            if (
                not selected_angle_topic
                and self._looks_like_memory(content)
                and not self._wants_draft(content)
            ):
                memory = self._memory_entry(content)
                state["content_bank"].insert(0, memory)

            post = None
            wants_draft = self._wants_draft(content)
            followup_draft = self._is_affirmative_draft_request(state, content)
            if selected_angle_topic or wants_draft or followup_draft:
                topic = (
                    selected_angle_topic
                    if selected_angle_topic
                    else self._topic_from_context(state, content if followup_draft else None)
                    if followup_draft or self._wants_latest_context(content)
                    else self._extract_topic(content)
                )
                if not selected_angle_topic and not followup_draft and self._needs_context_before_drafting(state, topic):
                    reply = self._context_request_reply(state, topic)
                    actions = ["context_requested"]
                    kind = "context_request"
                    post_id = None
                else:
                    post = self._draft(state, topic, "chat")
                    state["posts"].insert(0, post)
                    reply = (
                        "I drafted it and kept it in the review workspace. "
                        "Read it once for truth, then choose the next move: revise the voice, save it, schedule it, or use the LinkedIn fallback."
                    )
                    actions = ["draft_created"]
                    kind = "draft_created"
                    post_id = post["id"]
                    self._set_workflow(
                        state,
                        stage="review",
                        last_topic=topic,
                        selected_angle=selected_angle_topic,
                    )
            elif memory:
                reply = self._memory_saved_strategy_reply(state, memory)
                actions = ["memory_saved", "angles_suggested"]
                kind = "message"
                post_id = None
            else:
                reply = (
                    self._content_strategy_reply(state, content)
                    or self._generate_chat_reply(state, content)
                    or self._fallback_chat_reply(state, content)
                )
                actions = ["reply"]
                kind = "message"
                post_id = None

            self._append_message(state, "mira", reply, kind=kind, post_id=post_id)
            self._write(state)
            return {
                "reply": reply,
                "actions": actions,
                "post": deepcopy(post),
                "state": self._public_state(state),
            }

    def edit_post(self, post_id: str, instructions: str) -> dict | None:
        with self.lock:
            state = self._read()
            post = self._find_post(state, post_id)
            if post is None:
                return None

            content = self._generate_ai_revision(state, post, instructions)
            if not content:
                content = post["content"]
                lowered = instructions.lower()
                if "short" in lowered:
                    paragraphs = [item for item in content.split("\n\n") if item]
                    content = "\n\n".join(paragraphs[:4])
                if "bold" in lowered or "stronger hook" in lowered:
                    lines = content.splitlines()
                    lines[0] = f"Most founders are getting this wrong: {lines[0]}"
                    content = "\n".join(lines)
                if "personal" in lowered:
                    content += (
                        "\n\nThis is the operating lesson I am carrying into "
                        "the next stage of building Blidx."
                    )
                if "cta" in lowered or "call to action" in lowered:
                    content += "\n\nWhat part of this workflow feels most broken in your own content process?"
                if "voice" in lowered:
                    content += (
                        "\n\nThe way I would say it simply: the system should carry the workflow, "
                        "but the founder should keep the judgment."
                    )
                if content == post["content"]:
                    content += f"\n\nEdit note applied: {instructions.strip()}"

            post["content"] = content[:3000]
            post["char_count"] = len(post["content"])
            post["quality_review"] = self._quality_review(state, post)
            post["version"] += 1
            post["status"] = "pending"
            post["updated_at"] = utc_now().isoformat()
            self._write(state)
            return deepcopy(post)

    def use_variant(self, post_id: str, variant_id: str) -> dict | None:
        with self.lock:
            state = self._read()
            post = self._find_post(state, post_id)
            if post is None:
                return None

            variant = next(
                (
                    item
                    for item in post.get("variants", [])
                    if item.get("id") == variant_id
                ),
                None,
            )
            if variant is None:
                return None

            post["content"] = variant["content"][:3000]
            post["title"] = variant.get("label") or post["title"]
            post["char_count"] = len(post["content"])
            post["quality_review"] = self._quality_review(state, post)
            post["version"] += 1
            post["status"] = "pending"
            post["selected_variant_id"] = variant_id
            post["updated_at"] = utc_now().isoformat()
            self._append_message(
                state,
                "mira",
                f"I switched the active draft to the “{variant.get('label', 'selected')}” variant.",
                kind="draft_updated",
                post_id=post["id"],
            )
            self._write(state)
            return deepcopy(post)

    def approve_post(
        self, post_id: str, schedule_type: str, scheduled_at: str | None
    ) -> dict | None:
        with self.lock:
            state = self._read()
            post = self._find_post(state, post_id)
            if post is None:
                return None

            now = utc_now()
            if schedule_type == "now":
                post["status"] = "published"
                post["published_at"] = now.isoformat()
                post["published_url"] = None
                post["scheduled_at"] = None
                post["schedule_type"] = "now"
                post["schedule_label"] = "Posted now"
            else:
                post["status"] = "scheduled"
                schedule = self._resolve_schedule(
                    state, schedule_type, scheduled_at, now
                )
                post["scheduled_at"] = schedule["scheduled_at"]
                post["schedule_type"] = schedule["schedule_type"]
                post["schedule_label"] = schedule["schedule_label"]
            post["updated_at"] = now.isoformat()
            self._write(state)
            return deepcopy(post)

    @staticmethod
    def _resolve_schedule(
        state: dict, schedule_type: str, scheduled_at: str | None, now: datetime
    ) -> dict:
        schedule_type = schedule_type or "best_time"
        timezone_name = state.get("profile", {}).get("timezone") or "UTC"
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            tz = timezone.utc
        local_now = now.astimezone(tz)

        if scheduled_at:
            return {
                "scheduled_at": scheduled_at,
                "schedule_type": "custom",
                "schedule_label": "Custom time",
            }

        if schedule_type == "tomorrow_morning":
            target = (local_now + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            return {
                "scheduled_at": target.astimezone(timezone.utc).isoformat(),
                "schedule_type": schedule_type,
                "schedule_label": "Tomorrow morning",
            }

        if schedule_type == "later_today":
            target = local_now.replace(hour=17, minute=30, second=0, microsecond=0)
            if target <= local_now:
                target = (local_now + timedelta(days=1)).replace(
                    hour=9, minute=0, second=0, microsecond=0
                )
            return {
                "scheduled_at": target.astimezone(timezone.utc).isoformat(),
                "schedule_type": schedule_type,
                "schedule_label": "Later today",
            }

        target = DemoStore._next_best_week_slot(local_now)
        return {
            "scheduled_at": target.astimezone(timezone.utc).isoformat(),
            "schedule_type": "best_time",
            "schedule_label": "Best time this week",
        }

    @staticmethod
    def _next_best_week_slot(local_now: datetime) -> datetime:
        # Tue/Thu mornings are a reasonable MVP default for B2B LinkedIn testing.
        preferred_weekdays = (1, 3)
        for days_ahead in range(0, 8):
            candidate_day = local_now + timedelta(days=days_ahead)
            if candidate_day.weekday() not in preferred_weekdays:
                continue
            candidate = candidate_day.replace(hour=10, minute=30, second=0, microsecond=0)
            if candidate > local_now:
                return candidate
        return (local_now + timedelta(days=1)).replace(
            hour=10, minute=30, second=0, microsecond=0
        )

    def publish_post(self, post_id: str) -> dict | None:
        with self.lock:
            state = self._read()
            post = self._find_post(state, post_id)
            if post is None:
                return None

            linkedin = state.get("linkedin") or {}
            access_token = linkedin.get("access_token")
            if not access_token:
                return {
                    "published": False,
                    "mode": "manual_fallback",
                    "fallback_url": "https://www.linkedin.com/feed/",
                    "message": (
                        "LinkedIn is not connected yet. The draft can be copied and posted "
                        "manually, then tracked here with the LinkedIn URL."
                    ),
                    "post": deepcopy(post),
                }

            from app.integrations.linkedin import LinkedInClient

            try:
                published = LinkedInClient().publish_post(access_token, post["content"])
            except Exception as exc:
                return {
                    "published": False,
                    "mode": "manual_fallback",
                    "fallback_url": "https://www.linkedin.com/feed/",
                    "message": "LinkedIn auto-post failed, so use the manual fallback.",
                    "error": str(exc)[:240],
                    "post": deepcopy(post),
                }

            now = utc_now()
            post["status"] = "published"
            post["published_at"] = now.isoformat()
            post["published_url"] = published.get("url")
            post["linkedin_post_id"] = published.get("id") or published.get("status")
            post["updated_at"] = now.isoformat()
            self._append_message(
                state,
                "mira",
                "Published to LinkedIn and saved it in your Library.",
                kind="published",
                post_id=post["id"],
            )
            self._write(state)
            return {"published": True, "mode": "oauth", "post": deepcopy(post)}

    def track_linkedin_url(self, post_id: str, url: str | None) -> dict | None:
        with self.lock:
            state = self._read()
            post = self._find_post(state, post_id)
            if post is None:
                return None

            now = utc_now()
            post["status"] = "published"
            post["published_at"] = now.isoformat()
            post["published_url"] = (url or "").strip() or None
            post["updated_at"] = now.isoformat()
            self._append_message(
                state,
                "mira",
                "Great, I marked this as posted and kept the LinkedIn link in your Library.",
                kind="published",
                post_id=post["id"],
            )
            self._write(state)
            return deepcopy(post)

    def store_linkedin_connection(self, token: dict, profile: dict | None = None) -> dict:
        with self.lock:
            state = self._read()
            state["linkedin"] = {
                "connected": True,
                "access_token": token.get("access_token"),
                "profile": profile or {},
                "connected_at": utc_now().isoformat(),
                "expires_in": token.get("expires_in"),
            }
            self._append_message(
                state,
                "mira",
                "LinkedIn is connected. Future approved drafts can be published directly.",
                kind="integration",
            )
            self._write(state)
            return self._public_state(state)["linkedin"]

    def save_post(self, post_id: str) -> dict | None:
        return self._set_status(post_id, "saved")

    def delete_post(self, post_id: str) -> dict | None:
        return self._set_status(post_id, "deleted")

    def reset(self) -> dict:
        with self.lock:
            user = self._read().get("user") if current_user_id.get() else None
            state = self._initial_state(user)
            self._write(state)
            return self._public_state(state)

    def seed_test_scenario(self) -> dict:
        with self.lock:
            state = self._malia_test_state()
            self._write(state)
            return self._public_state(state)

    def _set_status(self, post_id: str, status: str) -> dict | None:
        with self.lock:
            state = self._read()
            post = self._find_post(state, post_id)
            if post is None:
                return None
            post["status"] = status
            post["updated_at"] = utc_now().isoformat()
            self._write(state)
            return deepcopy(post)

    def _malia_test_state(self) -> dict:
        state = self._initial_state()
        state["user"] = {
            "id": str(uuid.uuid4()),
            "email": "malia@blidx.demo",
            "user_name": "Malia",
        }
        state["profile"] = {
            "first_name": "Malia",
            "role": "Founder",
            "company_name": "HeyJuni",
            "company_website": "https://www.heyjuni.com",
            "industry": "Healthcare - Mental Health",
            "company_description": (
                "HeyJuni is a mental health platform combining community, "
                "workshops, and therapy around real human connection."
            ),
            "expertise": ["Startup", "Mental Health", "Medicine"],
            "writing_style": (
                "Data-driven yet personal. Uses reflective questions, measured "
                "conviction, numbered structures like 1/, 2/, 3/, and ends with "
                "an invitation to connect or reflect."
            ),
            "writing_samples": [
                (
                    "What if healing did not have to start in a clinic? "
                    "For many people, the first step is not treatment. It is feeling "
                    "seen, safe, and connected."
                ),
                (
                    "Coexistence with AI is the strategy, but we cannot ignore what "
                    "changes when technology starts reshaping how people work, learn, "
                    "and care for one another."
                ),
            ],
            "audience": ["Industry Peers", "Founders", "Investors / VCs"],
            "content_types": ["Industry insights", "Personal stories", "Case studies"],
            "posting_frequency": "3-4x_per_week",
            "tone": "Insightful & measured",
            "timezone": "Asia/Singapore",
        }
        for raw_text, category in [
            (
                "I attended an event about the evolution of AI. Many founders were curious, but I could also sense anxiety about what AI will replace.",
                "events",
            ),
            (
                "I keep thinking about the value of human connection in mental health care as more AI products launch.",
                "insights",
            ),
            (
                "I rebuilt the new HeyJuni website mostly by myself with AI support. It felt empowering and scary at the same time.",
                "milestones",
            ),
        ]:
            state["content_bank"].insert(
                0,
                {
                    "id": str(uuid.uuid4()),
                    "raw_text": raw_text,
                    "category": category,
                    "tags": [category.title()],
                    "freshness": "fresh",
                    "content_potential": self._potential(raw_text),
                    "created_at": utc_now().isoformat(),
                },
            )
        state["test_scenario"] = {
            "loaded": True,
            "name": "Malia founder-test scenario",
            "next_prompt": "human connection versus AI in mental health",
        }
        state["onboarding_completed"] = True
        state["messages"] = [
            {
                "id": str(uuid.uuid4()),
                "role": "mira",
                "content": (
                    "Hi Malia, I loaded your HeyJuni profile and three Content Bank moments. "
                    "You can chat with me naturally, or ask me to draft a post from one of them."
                ),
                "created_at": utc_now().isoformat(),
                "kind": "message",
            }
        ]
        return state

    @staticmethod
    def _normalize_state(state: dict) -> dict:
        state.setdefault("content_bank", [])
        state.setdefault("posts", [])
        profile = state.setdefault("profile", {})
        profile.setdefault("writing_style", "")
        profile.setdefault("writing_samples", [])
        profile.setdefault(
            "preferred_structure",
            "Hook, context, lesson, reflective question",
        )
        profile.setdefault("avoided_phrases", ["game changer", "unlock", "10x"])
        profile.setdefault("cta_style", "Reflective question")
        state.setdefault("onboarding_completed", True if state.get("test_scenario") else False)
        state.setdefault(
            "messages",
            [
                {
                    "id": str(uuid.uuid4()),
                    "role": "mira",
                    "content": "Your pipeline is clear. What should we turn into your next post?",
                    "created_at": utc_now().isoformat(),
                    "kind": "message",
                }
            ],
        )
        workflow = state.setdefault("mira_workflow", {})
        workflow.setdefault("stage", "capture")
        workflow.setdefault("last_topic", None)
        workflow.setdefault("last_angles", [])
        workflow.setdefault("last_memory_id", None)
        workflow.setdefault("updated_at", utc_now().isoformat())
        state.setdefault(
            "linkedin",
            {
                "connected": False,
                "access_token": None,
                "profile": None,
                "connected_at": None,
            },
        )
        return state

    @staticmethod
    def _public_state(state: dict) -> dict:
        public = deepcopy(state)
        linkedin = public.setdefault("linkedin", {})
        linkedin.pop("access_token", None)
        linkedin["connected"] = bool(state.get("linkedin", {}).get("access_token")) or bool(
            linkedin.get("connected")
        )
        public["auth"] = {
            "authenticated": bool(current_user_id.get()),
            "user_id": current_user_id.get(),
        }
        return public

    @staticmethod
    def _find_post(state: dict, post_id: str) -> dict | None:
        return next((post for post in state["posts"] if post["id"] == post_id), None)

    @staticmethod
    def _categorize(text: str) -> str:
        lowered = text.lower()
        keywords = {
            "people": ["met", "meeting", "spoke", "conversation"],
            "events": ["event", "conference", "summit", "workshop"],
            "insights": ["realized", "insight", "noticed", "believe"],
            "milestones": ["closed", "launched", "milestone", "achieved"],
            "reading": ["read", "article", "book", "report"],
            "solutions": ["fixed", "solved", "problem", "challenge"],
        }
        for category, values in keywords.items():
            if any(value in lowered for value in values):
                return category
        return "general"

    @staticmethod
    def _potential(text: str) -> str:
        high_signals = ("first", "learned", "failed", "closed", "realized", "why")
        return "high" if any(signal in text.lower() for signal in high_signals) else "medium"

    @staticmethod
    def _append_message(
        state: dict,
        role: str,
        content: str,
        *,
        kind: str = "message",
        post_id: str | None = None,
    ) -> dict:
        message = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "created_at": utc_now().isoformat(),
            "kind": kind,
        }
        if post_id:
            message["post_id"] = post_id
        state.setdefault("messages", []).append(message)
        state["messages"] = state["messages"][-40:]
        return message

    @staticmethod
    def _memory_entry(raw_text: str, category: str | None = None) -> dict:
        category = category or DemoStore._categorize(raw_text)
        return {
            "id": str(uuid.uuid4()),
            "raw_text": raw_text.strip(),
            "category": category,
            "tags": [category.title()],
            "freshness": "fresh",
            "content_potential": DemoStore._potential(raw_text),
            "created_at": utc_now().isoformat(),
        }

    @staticmethod
    def _set_workflow(state: dict, **updates: object) -> dict:
        workflow = state.setdefault("mira_workflow", {})
        workflow.update(updates)
        workflow["updated_at"] = utc_now().isoformat()
        return workflow

    @staticmethod
    def _angle_options(topic: str, latest: str, audience_label: str) -> list[dict]:
        short_topic = DemoStore._short_topic(topic)
        moment = latest or short_topic
        return [
            {
                "id": "angle_1",
                "title": "Specific moment",
                "framework": "field_note",
                "detail": f"Lead with the real scene behind “{short_topic}” and show what changed in your thinking.",
                "prompt": f"Specific moment around {moment}: what changed in my thinking and why it matters for {audience_label}.",
            },
            {
                "id": "angle_2",
                "title": "Founder POV",
                "framework": "sharp_pov",
                "detail": f"Turn it into a sharper opinion about what {audience_label} usually misunderstand.",
                "prompt": f"Founder POV on {short_topic}: what most people misunderstand and what I now believe.",
            },
            {
                "id": "angle_3",
                "title": "Useful question",
                "framework": "practical_note",
                "detail": "Make the post practical by ending with where the workflow, trust, or judgment breaks for the reader.",
                "prompt": f"Useful question about {short_topic}: where the workflow, trust, or judgment breaks for the reader.",
            },
        ]

    @staticmethod
    def _detect_chat_intent(content: str) -> str:
        lowered = content.lower().strip()
        if DemoStore._wants_draft(content):
            return "draft"
        if any(phrase in lowered for phrase in ("shorter", "revise", "edit", "improve", "change", "make it")):
            return "revise"
        if any(phrase in lowered for phrase in ("angle", "angles", "idea", "ideas", "topic", "what should")):
            return "strategy"
        if DemoStore._looks_like_memory(content):
            return "capture"
        if any(phrase in lowered for phrase in ("how does this work", "what can you do", "help me")):
            return "product_help"
        return "chat"

    @staticmethod
    def _framework_label(framework: str | None) -> str:
        labels = {
            "field_note": "field note",
            "sharp_pov": "sharp founder POV",
            "practical_note": "practical framework",
            "story_observation": "story-led observation",
            "contrarian_take": "contrarian take",
        }
        return labels.get(framework or "", "field note")

    @staticmethod
    def _remember_angle_options(
        state: dict,
        topic: str,
        latest: str = "",
        memory_id: str | None = None,
    ) -> list[dict]:
        profile = state.get("profile", {})
        audience_label = ", ".join((profile.get("audience") or ["your audience"])[:3])
        angles = DemoStore._angle_options(topic, latest, audience_label)
        DemoStore._set_workflow(
            state,
            stage="angle_choice",
            last_topic=topic,
            last_angles=angles,
            last_memory_id=memory_id,
            selected_angle=None,
        )
        return angles

    @staticmethod
    def _memory_saved_strategy_reply(state: dict, memory: dict) -> str:
        raw_text = memory.get("raw_text", "")
        profile = state.get("profile", {})
        audience_label = ", ".join((profile.get("audience") or ["your audience"])[:3])
        angles = DemoStore._remember_angle_options(
            state,
            raw_text,
            raw_text,
            memory.get("id"),
        )
        angle_lines = "\n\n".join(
            f"{index}/ {angle['title']}: {angle['detail']} Framework: {DemoStore._framework_label(angle.get('framework'))}."
            for index, angle in enumerate(angles, start=1)
        )
        return (
            "Step 1/4 captured: I saved this to your Content Bank.\n\n"
            f"Why it matters for {audience_label}: it has a real scene, so the post can sound owned instead of AI-generated.\n\n"
            "Step 2/4 choose the angle before drafting:\n\n"
            f"{angle_lines}\n\n"
            "Reply with “angle 1”, “angle 2”, or “angle 3”. I’ll draft from that choice next."
        )

    @staticmethod
    def _topic_from_selected_angle(state: dict, content: str) -> str | None:
        workflow = state.get("mira_workflow") or {}
        angles = workflow.get("last_angles") or []
        if not angles:
            return None

        lowered = content.lower().strip()
        match = re.search(r"\b(?:angle|option|direction)\s*([123])\b", lowered)
        if not match:
            ordinal_map = {
                "first": 1,
                "second": 2,
                "third": 3,
            }
            for word, number in ordinal_map.items():
                if re.search(rf"\b{word}\b", lowered) and any(
                    signal in lowered for signal in ("angle", "option", "direction", "draft")
                ):
                    match_index = number
                    break
            else:
                return None
        else:
            match_index = int(match.group(1))

        index = match_index - 1
        if index < 0 or index >= len(angles):
            return None
        selected = angles[index]
        DemoStore._set_workflow(
            state,
            stage="draft",
            selected_angle=selected,
            last_topic=selected.get("prompt") or selected.get("title"),
            draft_framework=selected.get("framework"),
        )
        return selected.get("prompt") or selected.get("title")

    @staticmethod
    def _wants_draft(content: str) -> bool:
        lowered = content.lower()
        draft_action_signals = (
            "draft",
            "write",
            "create",
            "make",
            "turn this into",
            "post about",
        )
        if "linkedin post" in lowered and not any(signal in lowered for signal in draft_action_signals):
            return False
        conversational_question_signals = (
            "what should",
            "what can",
            "any ideas",
            "give me ideas",
            "suggest",
            "angle",
            "topic",
        )
        if lowered.strip().endswith("?") and any(
            signal in lowered for signal in conversational_question_signals
        ):
            return False
        draft_signals = (
            "draft",
            "write a post",
            "create a post",
            "turn this into",
            "linkedin post",
            "make a post",
        )
        return any(signal in lowered for signal in draft_signals) or lowered.startswith(
            "post about "
        )

    @staticmethod
    def _looks_like_memory(content: str) -> bool:
        lowered = content.lower()
        if "?" in content or lowered.startswith(
            ("what should", "what can", "how should", "can you", "give me", "suggest")
        ):
            return False
        signals = (
            "i attended",
            "i met",
            "i spoke",
            "i realized",
            "i learned",
            "we launched",
            "we rebuilt",
            "today",
            "this week",
        )
        return any(signal in lowered for signal in signals)

    @staticmethod
    def _is_off_topic(content: str) -> bool:
        lowered = content.lower()
        off_topic = (
            "weather",
            "recipe",
            "sports score",
            "movie recommendation",
            "homework",
            "dating advice",
            "stock tip",
            "crypto",
        )
        content_terms = (
            "post",
            "linkedin",
            "content",
            "draft",
            "audience",
            "founder",
            "malia",
            "heyjuni",
            "blidx",
            "mental health",
            "ai",
            "work",
            "startup",
        )
        return any(term in lowered for term in off_topic) and not any(
            term in lowered for term in content_terms
        )

    @staticmethod
    def _extract_topic(content: str) -> str:
        topic = content.strip()
        lowered = topic.lower()
        prefixes = (
            "draft a post about",
            "draft about",
            "draft a linkedin post about",
            "draft linkedin post about",
            "write a draft about",
            "write a post about",
            "create a post about",
            "make a post about",
            "draft a linkedin post from this angle:",
            "draft a post from this angle:",
            "turn this into a linkedin post:",
            "turn this into a post:",
            "linkedin post about",
            "post about",
        )
        for prefix in prefixes:
            if lowered.startswith(prefix):
                topic = topic[len(prefix) :].strip(" :.-")
                break
        return topic or content.strip()

    @staticmethod
    def _wants_latest_context(content: str) -> bool:
        lowered = content.lower()
        return any(
            phrase in lowered
            for phrase in (
                "latest memory",
                "latest content bank",
                "from my memory",
                "from my content bank",
                "from the content bank",
                "from this angle",
                "from that angle",
            )
        )

    @staticmethod
    def _is_affirmative_draft_request(state: dict, content: str) -> bool:
        if not DemoStore._is_affirmative_text(content):
            return False
        recent_mira = [
            message
            for message in state.get("messages", [])[-4:]
            if message.get("role") == "mira"
        ]
        return any(
            "draft" in (message.get("content") or "").lower()
            for message in recent_mira
        )

    @staticmethod
    def _topic_from_context(state: dict, current_content: str | None = None) -> str:
        workflow = state.get("mira_workflow") or {}
        selected_angle = workflow.get("selected_angle") or {}
        if selected_angle.get("prompt"):
            return selected_angle["prompt"]
        last_angles = workflow.get("last_angles") or []
        if last_angles and workflow.get("stage") == "angle_choice":
            first_angle = last_angles[0]
            if first_angle.get("prompt"):
                return first_angle["prompt"]
        if state.get("content_bank"):
            latest = state["content_bank"][0]["raw_text"]
            if "ai" in latest.lower() and "mental" in json.dumps(state.get("profile", {})).lower():
                return "human connection versus AI in mental health"
            return latest[:140]
        recent_topic = DemoStore._topic_from_recent_draft_request(state, current_content)
        if recent_topic:
            return recent_topic
        messages = [
            message.get("content", "")
            for message in state.get("messages", [])
            if message.get("role") == "user"
        ]
        return messages[-1] if messages else "a founder insight from this week"

    @staticmethod
    def _topic_from_recent_draft_request(state: dict, current_content: str | None = None) -> str | None:
        current = (current_content or "").strip()
        for message in reversed(state.get("messages", [])[-8:]):
            content = (message.get("content") or "").strip()
            if message.get("role") != "user" or not content:
                continue
            if current and content == current:
                continue
            if DemoStore._is_affirmative_text(content):
                continue
            if DemoStore._wants_draft(content):
                return DemoStore._extract_topic(content)
        return None

    @staticmethod
    def _is_affirmative_text(content: str) -> bool:
        lowered = content.lower().strip(" .!?,")
        affirmative = (
            "yes",
            "yes please",
            "go ahead",
            "do it",
            "draft it",
            "please draft",
            "make it",
            "just draft it",
            "turn it into a post",
            "sounds good",
        )
        return lowered in affirmative

    @staticmethod
    def _provider_label(post: dict) -> str:
        provider = post.get("generation_provider") or "template"
        return "Claude" if provider.startswith("Anthropic") else "your profile and Content Bank context"

    @staticmethod
    def _polish_title(title: str) -> str:
        for source, replacement in {
            "Ai": "AI",
            "Saas": "SaaS",
            "Gtm": "GTM",
            "Api": "API",
        }.items():
            title = title.replace(source, replacement)
        return title

    @staticmethod
    def _draft(state: dict, topic: str, source: str) -> dict:
        profile = state["profile"]
        topic = DemoStore._clean_topic(topic)
        memory = DemoStore._relevant_memory(state, topic)
        first_name = profile.get("first_name") or "there"
        hook = topic.strip().rstrip(".")
        content, provider, error = DemoStore._generate_ai_draft(state, topic)
        if not content:
            content = DemoStore._fallback_draft_text(state, topic)
            provider = "template"

        sources = []
        if memory:
            sources.append(
                {
                    "type": "personal",
                    "title": f"Content Bank · {memory['category'].title()}",
                }
            )
        if provider != "template":
            sources.append({"type": "ai", "title": f"Generated with {provider}"})

        now = utc_now()
        title = hook[:70].strip()
        if title:
            title = title[0].upper() + title[1:]
            title = DemoStore._polish_title(title)
        post = {
            "id": str(uuid.uuid4()),
            "title": title,
            "content": content[:3000],
            "status": "pending",
            "source": source,
            "sources": sources,
            "char_count": len(content[:3000]),
            "version": 1,
            "scheduled_at": None,
            "published_at": None,
            "published_url": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "generation_provider": provider,
            "generation_error": error,
            "variants": DemoStore._draft_variants(state, topic, content[:3000]),
            "selected_variant_id": "main",
            "message": (
                f"{first_name}, I used Claude with your profile, Content Bank context, and the {DemoStore._framework_label(DemoStore._fallback_style(state, topic))} framework."
                if provider != "template"
                else f"{first_name}, I used your profile, freshest context, and the {DemoStore._framework_label(DemoStore._fallback_style(state, topic))} framework for this angle."
            ),
        }
        post["quality_review"] = DemoStore._quality_review(state, post)
        return post

    @staticmethod
    def _robotic_phrases() -> tuple[str, ...]:
        return (
            "in today's fast-paced",
            "game changer",
            "unlock",
            "10x",
            "not just",
            "delve into",
            "revolutionize",
            "transform the way",
            "leverage ai",
            "cutting-edge",
            "seamlessly",
        )

    @staticmethod
    def _quality_review(state: dict, post: dict) -> dict:
        content = post.get("content", "")
        plain = content.lower()
        profile = state.get("profile", {})
        sources = post.get("sources", [])
        has_question = "?" in content
        has_numbered_structure = any(marker in content for marker in ("1/", "2/", "3/"))
        audience_hits = [
            audience
            for audience in profile.get("audience", [])
            if audience and audience.lower() in plain
        ]
        memory_text = ""
        if state.get("content_bank"):
            memory_text = state["content_bank"][0].get("raw_text", "")
        memory_terms = [
            term.strip(".,:;!?").lower()
            for term in memory_text.split()
            if len(term.strip(".,:;!?")) > 5
        ][:8]
        memory_overlap = sum(1 for term in memory_terms if term in plain)
        robotic_hits = [phrase for phrase in DemoStore._robotic_phrases() if phrase in plain]

        checks = [
            {
                "id": "real_moment",
                "label": "Real moment",
                "passed": bool(sources or memory_overlap >= 2),
                "detail": (
                    "Uses a Content Bank memory or specific source."
                    if sources or memory_overlap >= 2
                    else "Needs a specific moment from the Content Bank."
                ),
            },
            {
                "id": "clear_pov",
                "label": "Clear POV",
                "passed": any(
                    phrase in plain
                    for phrase in (
                        "i think",
                        "i believe",
                        "my working principle",
                        "the question is",
                        "that tension matters",
                        "the opportunity is",
                    )
                )
                or has_numbered_structure,
                "detail": (
                    "Has a point of view or useful structure."
                    if has_numbered_structure
                    or any(
                        phrase in plain
                        for phrase in (
                            "i think",
                            "i believe",
                            "my working principle",
                            "the question is",
                            "that tension matters",
                            "the opportunity is",
                        )
                    )
                    else "Needs a sharper founder opinion."
                ),
            },
            {
                "id": "founder_voice",
                "label": "Founder voice",
                "passed": bool(audience_hits)
                or any(
                    phrase in plain
                    for phrase in ("at ", "building", "founder", "i keep", "i rebuilt", "my")
                ),
                "detail": (
                    "Connects to the founder, company, or intended audience."
                    if audience_hits
                    or any(
                        phrase in plain
                        for phrase in ("at ", "building", "founder", "i keep", "i rebuilt", "my")
                    )
                    else "Could sound more like the founder's own perspective."
                ),
            },
            {
                "id": "good_cta",
                "label": "Good CTA",
                "passed": has_question
                or any(phrase in plain for phrase in ("comment", "connect", "share")),
                "detail": (
                    "Ends with a question or invitation."
                    if has_question or any(phrase in plain for phrase in ("comment", "connect", "share"))
                    else "Needs a stronger closing question or invitation."
                ),
            },
            {
                "id": "linkedin_length",
                "label": "LinkedIn length",
                "passed": 300 <= len(content) <= 2200,
                "detail": (
                    "Readable LinkedIn length."
                    if 300 <= len(content) <= 2200
                    else "Length may be too short or too long for review."
                ),
            },
            {
                "id": "human_voice",
                "label": "Human voice",
                "passed": not robotic_hits and "I keep thinking about" not in content[:80],
                "detail": (
                    "Avoids common AI phrasing and overused openings."
                    if not robotic_hits and "I keep thinking about" not in content[:80]
                    else "Still has robotic or repeated AI-style phrasing."
                ),
            },
        ]
        score = sum(1 for check in checks if check["passed"])
        needs = [check["label"] for check in checks if not check["passed"]]
        return {
            "score": score,
            "max_score": len(checks),
            "label": f"Draft readiness: {score}/{len(checks)}",
            "needs": needs,
            "checks": checks,
        }

    @staticmethod
    def _draft_variants(state: dict, topic: str, main_content: str) -> list[dict]:
        profile = state["profile"]
        topic = DemoStore._clean_topic(topic)
        memory_entry = DemoStore._relevant_memory(state, topic)
        use_company = DemoStore._should_use_company_anchor(state, topic, memory_entry)
        company = profile.get("company_name") or "my company"
        company_context = f"At {company}," if use_company else "In founder-led work,"
        building_context = (
            f"while building {company}"
            if use_company
            else "when turning real work into a point of view"
        )
        workflow_sentence = (
            f"That is the workflow I want {company} to make feel natural."
            if use_company
            else "That is the kind of workflow I want to make feel natural."
        )
        audience = ", ".join(profile.get("audience") or ["founders"])
        memory = memory_entry["raw_text"] if memory_entry else ""
        hook = DemoStore._variant_theme(topic)
        context = (
            memory
            or f"I keep noticing this tension around {hook}: speed is useful, but judgment is still the scarce part."
        )
        variants = [
            {
                "id": "personal_story",
                "label": "Personal founder story",
                "positioning": "Lead with the real moment, then turn it into a lesson.",
                "content": (
                    f"I keep thinking about {hook}.\n\n"
                    f"{context}\n\n"
                    f"{company_context} I keep seeing that the useful insight is rarely sitting in a polished document. "
                    "It is usually hidden inside the messy middle of building: the call, the decision, the constraint, the thing that almost got missed.\n\n"
                    "That is why I think founder-led content should start closer to the work.\n\n"
                    "Not with a blank page.\n"
                    "Not with a generic prompt.\n"
                    "But with a real moment that reveals what the founder is learning.\n\n"
                    f"For {audience}, that is where the point of view becomes believable.\n\n"
                    "What moment from your work this week would make a stronger post than another broad opinion?"
                ),
            },
            {
                "id": "industry_pov",
                "label": "Sharp industry POV",
                "positioning": "Make the bigger market point first, then support it with context.",
                "content": (
                    f"{hook} is not mainly a writing problem.\n\n"
                    "It is an operating problem.\n\n"
                    f"Most teams do not lack ideas. They lack a reliable way to turn real work into a clear point of view for {audience}.\n\n"
                    f"That is the pattern I keep coming back to {building_context}: the best content is already happening inside the business. "
                    "It is just scattered across notes, calls, product decisions, customer conversations, and founder instincts.\n\n"
                    "The opportunity is not to make AI write louder.\n\n"
                    "It is to make the system carry the workflow, while the founder keeps the judgment.\n\n"
                    "That distinction matters more than most content tools admit."
                ),
            },
            {
                "id": "practical_lesson",
                "label": "Practical lesson",
                "positioning": "Turn the idea into a useful framework readers can apply.",
                "content": (
                    f"A practical way to think about {hook}:\n\n"
                    "1/ Capture the real moment while it is still fresh.\n"
                    "2/ Ask what changed in your thinking.\n"
                    "3/ Choose the audience that needs the lesson most.\n"
                    "4/ Draft from the tension, not from a generic topic.\n"
                    "5/ Let the founder approve the judgment before anything gets published.\n\n"
                    f"{workflow_sentence}\n\n"
                    f"The goal is not more content for {audience}.\n"
                    "The goal is more signal from the work that is already happening.\n\n"
                    "What step in that workflow usually breaks first for you?"
                ),
            },
        ]
        return [
            {**variant, "char_count": len(variant["content"])}
            for variant in variants
            if variant["content"].strip() != main_content.strip()
        ]

    @staticmethod
    def _variant_theme(topic: str) -> str:
        topic = DemoStore._clean_topic(topic)
        lowered = topic.lower()
        if "scattered" in lowered and "content" in lowered:
            return "turning scattered founder context into content"
        if "human connection" in lowered and "ai" in lowered:
            return "human connection versus AI"
        cleaned = topic.strip().rstrip(".")
        if len(cleaned) > 90:
            return "turning a real founder moment into a clear point of view"
        return cleaned or "a founder insight from this week"

    @staticmethod
    def _fallback_draft_text(state: dict, topic: str) -> str:
        profile = state["profile"]
        topic = DemoStore._clean_topic(topic)
        memory = DemoStore._relevant_memory(state, topic)
        use_company = DemoStore._should_use_company_anchor(state, topic, memory)
        company = profile.get("company_name") or "my company"
        audience = ", ".join(profile.get("audience") or ["founders"])
        memory_text = memory["raw_text"] if memory else ""
        hook = topic.strip().rstrip(".")
        industry = profile.get("industry") or ""
        topic_terms = DemoStore._topic_terms(topic)
        industry_terms = DemoStore._topic_terms(industry)
        closing = DemoStore._closing_question(profile)
        style = DemoStore._fallback_style(state, topic)
        use_mental_health_frame = (
            "mental health" in industry.lower()
            and ("mental health" in topic.lower() or bool(topic_terms & industry_terms))
        )
        if use_mental_health_frame:
            anchor = (
                f"At {company}, this question keeps coming back to one thing"
                if use_company
                else "In mental health, this question keeps coming back to one thing"
            )
            return (
                f"What does {hook} ask from us, beyond the technology?\n\n"
                f"{anchor}: people do not only need access. "
                "They need to feel seen, safe, and connected.\n\n"
                f"A recent moment made this more concrete for me: {memory_text or 'I saw how quickly AI can make hard work feel more possible, and also how easily it can make human care feel abstract.'}\n\n"
                "That tension matters.\n\n"
                "1/ AI can reduce friction.\n"
                "2/ It can help founders move faster.\n"
                "3/ But in mental health, the human layer cannot become an afterthought.\n\n"
                f"For {audience}, I think the question is not whether AI belongs in the future of care. "
                "It is where it should support the relationship, and where the relationship must stay central.\n\n"
                f"{closing}"
            )

        personal_block = memory_text or (
            f"The interesting part is what {hook} changes about taste, judgment, and the way people decide what feels meaningful."
        )
        if style == "field_note":
            company_line = (
                f"At {company}, that is the part of the work I want to make easier to carry."
                if use_company
                else "That is the part of the work I think founders often lose too quickly."
            )
            return (
                f"A small note from this week:\n\n"
                f"{personal_block}\n\n"
                "The obvious takeaway would be to write faster.\n\n"
                "I think the better takeaway is quieter: protect the moment before it gets flattened into a generic opinion.\n\n"
                f"{company_line}\n\n"
                f"For {audience}, the useful signal is rarely the polished conclusion. "
                "It is the decision, doubt, conversation, or constraint that produced the conclusion.\n\n"
                f"{closing}"
            )

        if style == "sharp_pov":
            anchor = (
                f"Building {company} has made this feel less theoretical."
                if use_company
                else "This feels less theoretical when you look at how founders actually work."
            )
            return (
                f"{DemoStore._sentence_case(hook)} is mostly treated as a writing problem.\n\n"
                "I do not think that is quite right.\n\n"
                f"{anchor}\n\n"
                f"The real issue is deciding what is worth saying before the draft exists. {personal_block}\n\n"
                "Once that decision is clear, the writing gets easier.\n\n"
                "Before that, even a good AI draft can feel strangely empty.\n\n"
                f"For {audience}, I would rather see fewer posts with more evidence of judgment.\n\n"
                f"{closing}"
            )

        if style == "story_observation":
            company_line = (
                f"It is the kind of moment I want {company} to help founders preserve."
                if use_company
                else "It is the kind of moment founders often forget to preserve."
            )
            return (
                f"I would not start a post about {hook} with a big claim.\n\n"
                "I would start smaller.\n\n"
                f"{personal_block}\n\n"
                "That is the useful part: not the topic itself, but the moment that made the topic feel real.\n\n"
                f"{company_line}\n\n"
                f"For {audience}, this is usually where the stronger post begins: with the observation before the conclusion.\n\n"
                f"{closing}"
            )

        if style == "contrarian_take":
            return (
                f"The obvious post about {hook} is probably not the best one.\n\n"
                "The obvious post explains why the topic matters.\n\n"
                "The better post shows what most people are missing.\n\n"
                f"{personal_block}\n\n"
                "That is the tension I would write from: the gap between the broad conversation and the real decision happening inside the work.\n\n"
                f"For {audience}, the value is not another polished opinion. It is a sharper reason to reconsider the default answer.\n\n"
                f"{closing}"
            )

        return (
            f"One thing I would not outsource too quickly: the judgment behind {hook}.\n\n"
            f"{personal_block}\n\n"
            "AI can help shape the page. It can make a messy thought easier to work with.\n\n"
            "But the reason a post feels believable is usually smaller and more human than the final wording:\n\n"
            "1/ what actually happened\n"
            "2/ what it made you reconsider\n"
            "3/ why your audience should care now\n\n"
            f"That is the piece I want {company if use_company else 'the workflow'} to protect.\n\n"
            f"{closing}"
        )

    @staticmethod
    def _fallback_style(state: dict, topic: str) -> str:
        workflow = state.get("mira_workflow") or {}
        selected_angle = workflow.get("selected_angle") or {}
        if selected_angle.get("framework"):
            return selected_angle["framework"]
        if workflow.get("draft_framework"):
            return workflow["draft_framework"]
        recommended = DemoStore._recommended_framework(
            topic,
            state.get("content_bank", [{}])[0].get("raw_text", "") if state.get("content_bank") else "",
        )
        if recommended:
            return recommended
        seed = len(topic) + len(state.get("posts", [])) + len(state.get("messages", []))
        styles = ("field_note", "sharp_pov", "practical_note", "story_observation", "contrarian_take")
        return styles[seed % len(styles)]

    @staticmethod
    def _sentence_case(text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return "This"
        return cleaned[0].upper() + cleaned[1:]

    @staticmethod
    def _clean_topic(topic: str) -> str:
        cleaned = topic.strip().strip('"“”').rstrip(".")
        lowered = cleaned.lower()
        prefixes = (
            "draft a post about",
            "draft about",
            "draft a linkedin post about",
            "draft linkedin post about",
            "write a draft about",
            "write a post about",
            "create a post about",
            "make a post about",
            "draft a linkedin post from this angle:",
            "draft a post from this angle:",
            "linkedin post about",
            "post about",
        )
        for prefix in prefixes:
            if lowered.startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip(" :.-")
                break
        return cleaned or topic.strip()

    @staticmethod
    def _topic_terms(text: str) -> set[str]:
        stopwords = {
            "about",
            "draft",
            "post",
            "linkedin",
            "this",
            "that",
            "with",
            "from",
            "into",
            "your",
            "what",
            "when",
            "where",
            "should",
            "would",
            "could",
            "make",
            "write",
            "create",
        }
        return {
            word.strip(".,:;!?()[]{}\"'“”‘’").lower()
            for word in text.split()
            if len(word.strip(".,:;!?()[]{}\"'“”‘’")) > 2
            and word.strip(".,:;!?()[]{}\"'“”‘’").lower() not in stopwords
        }

    @staticmethod
    def _relevant_memory(state: dict, topic: str) -> dict | None:
        topic_terms = DemoStore._topic_terms(topic)
        if not topic_terms:
            return None
        best_entry = None
        best_score = 0
        for entry in state.get("content_bank", [])[:8]:
            memory_terms = DemoStore._topic_terms(
                " ".join(
                    [
                        entry.get("raw_text", ""),
                        entry.get("category", ""),
                        " ".join(entry.get("tags", [])),
                    ]
                )
            )
            score = len(topic_terms & memory_terms)
            if score > best_score:
                best_score = score
                best_entry = entry
        workflow_terms = {"content", "workflow", "founder", "founders", "audience"}
        if best_score >= 2 or (best_score >= 1 and topic_terms & workflow_terms):
            return best_entry
        return None

    @staticmethod
    def _should_use_company_anchor(state: dict, topic: str, memory: dict | None = None) -> bool:
        if memory:
            return True
        profile = state.get("profile", {})
        company = (profile.get("company_name") or "").lower()
        if company and company in topic.lower():
            return True
        topic_terms = DemoStore._topic_terms(topic)
        profile_terms = DemoStore._topic_terms(
            " ".join(
                [
                    profile.get("company_description", ""),
                    profile.get("industry", ""),
                    " ".join(profile.get("expertise", [])),
                ]
            )
        )
        return len(topic_terms & profile_terms) >= 2

    @staticmethod
    def _needs_context_before_drafting(state: dict, topic: str) -> bool:
        topic = DemoStore._clean_topic(topic)
        lowered = topic.lower()
        if DemoStore._relevant_memory(state, topic):
            return False
        padded = f" {lowered} "
        if any(pronoun in padded for pronoun in (" i ", " we ", " my ", " our ")):
            return False
        if any(
            signal in lowered
            for signal in (
                "today",
                "this week",
                "because",
                "after",
                "when",
                "learned",
                "realized",
                "spoke",
                "met",
                "launched",
                "rebuilt",
            )
        ):
            return False
        if ":" in topic or len(topic.split()) >= 7:
            return False
        topic_terms = DemoStore._topic_terms(topic)
        return len(topic_terms) <= 4

    @staticmethod
    def _context_request_reply(state: dict, topic: str) -> str:
        topic = DemoStore._clean_topic(topic)
        profile = state.get("profile", {})
        company = profile.get("company_name") or "your work"
        if "latest memory" in topic.lower() or "content bank" in topic.lower():
            return (
                "I can draft from the Content Bank, but there is not a strong matching memory yet. "
                "Give me one real moment first: what happened, why it mattered, and what it changed in your thinking?"
            )
        return (
            f"I can draft about {topic}, but I do not want to give you a generic AI-looking post.\n\n"
            f"Give me one concrete detail from {company}: a moment, conversation, decision, event, or tension behind this topic. "
            "One sentence is enough. If you want me to draft without that context anyway, say “just draft it.”"
        )

    @staticmethod
    def _closing_question(profile: dict) -> str:
        cta_style = (profile.get("cta_style") or "").lower()
        if "comment" in cta_style:
            return "What would you add from your own experience?"
        if "connect" in cta_style:
            return "If you are thinking about this too, I would be glad to compare notes."
        if "question" in cta_style or "reflect" in cta_style:
            return "What part of this workflow creates the most friction for you right now?"
        return profile.get("cta_style") or "What part of this workflow creates the most friction for you right now?"

    @staticmethod
    def _generate_ai_draft(state: dict, topic: str) -> tuple[str | None, str, str | None]:
        provider = ClaudeProvider()
        if not provider.configured:
            return None, "template", None

        system_prompt = (
            "You are Mira, the content operating partner inside Blidx. "
            "Write only the LinkedIn post draft, with no preamble. "
            "The draft must sound like the user, not like a generic AI assistant. "
            "Use first person when appropriate. Keep it publishable, specific, and under 2,600 characters. "
            "Use the user's writing samples and voice controls as the highest-priority style guide. "
            "Prefer concrete founder moments over broad claims. Avoid hype, cliches, and any phrases listed as avoided. "
            "Vary the structure. Do not use the same hook-context-lesson-question sequence every time. "
            "Choose the format that fits the topic: field note, sharp observation, practical list, founder memo, or reflective essay. "
            "Use plain, slightly imperfect human language. It is okay to be concise, unresolved, or specific rather than polished. "
            "Do not over-frame the topic as a grand universal lesson unless the user gave evidence for it. "
            "Avoid obvious AI patterns: 'not just X, but Y', 'in today's fast-paced world', 'game changer', 'unlock', "
            "'the future of', 'delve into', 'revolutionize', 'transform the way', 'leverage AI', and generic inspirational endings. "
            "Avoid over-explaining. Leave some texture and human imperfection if it fits the user's style. "
            "Use short paragraphs. If listing multiple points, use the user's preferred numbered style like 1/, 2/, 3/. "
            "End with the user's preferred CTA style. "
            "Do not repeat command phrases such as 'draft about' in the draft. "
            "Use Content Bank context only when it is clearly relevant to the requested topic. "
            "Do not mention Blidx or the user's company unless the user explicitly asks, the topic is about that company, "
            "or the relevant Content Bank context is about that company. "
            "Do not invent concrete facts, names, statistics, events, or credentials that are not in the context."
        )
        try:
            return (
                provider.generate(DemoStore._context_package(state, topic), system_prompt),
                f"Anthropic {provider.model}",
                None,
            )
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            return None, "template", str(exc)[:300]

    @staticmethod
    def _generate_ai_revision(state: dict, post: dict, instructions: str) -> str | None:
        provider = ClaudeProvider()
        if not provider.configured:
            return None

        system_prompt = (
            "You are Mira, the content operating partner inside Blidx. "
            "Revise the LinkedIn draft according to the user's instructions. "
            "Return only the revised post text, with no preamble or markdown fence. "
            "Keep the user's facts intact, do not invent specifics, and stay under 2,600 characters."
        )
        prompt = "\n\n".join(
            [
                "USER PROFILE\n" + json.dumps(state.get("profile", {}), indent=2),
                "CONTENT BANK\n" + json.dumps(state.get("content_bank", [])[:5], indent=2),
                "CURRENT DRAFT\n" + post.get("content", ""),
                "REVISION INSTRUCTIONS\n" + instructions.strip(),
            ]
        )
        try:
            return provider.generate(prompt, system_prompt)
        except (httpx.HTTPError, RuntimeError, ValueError):
            return None

    @staticmethod
    def _context_package(state: dict, topic: str) -> str:
        profile = state["profile"]
        topic = DemoStore._clean_topic(topic)
        memory = DemoStore._relevant_memory(state, topic)
        memories = [memory] if memory else []
        writing_samples = profile.get("writing_samples") or []
        avoided = profile.get("avoided_phrases") or []
        framework = DemoStore._fallback_style(state, topic)

        return "\n\n".join(
            [
                "TASK\n" f"Draft a LinkedIn post about: {topic.strip()}",
                "DRAFT STRATEGY\n"
                f"Use this framework: {DemoStore._framework_label(framework)}.\n"
                "If the framework is field note, lead with a concrete scene or observation.\n"
                "If it is sharp founder POV, name what the audience misunderstands.\n"
                "If it is practical framework, make the steps useful without sounding like a generic listicle.\n"
                "If it is story-led observation, keep the post smaller and more human.\n"
                "If it is contrarian take, show the better disagreement without being performative.",
                "USER PROFILE\n" + json.dumps(profile, indent=2),
                "VOICE CONTROLS\n"
                f"Preferred structure: {profile.get('preferred_structure') or 'Not specified'}\n"
                f"CTA style: {profile.get('cta_style') or 'Not specified'}\n"
                f"Phrases to avoid: {', '.join(avoided) if avoided else 'None specified'}\n"
                "Use writing samples as the strongest style signal when present.",
                "LINKEDIN ABOUT / WRITING STYLE\n"
                + (profile.get("writing_style") or "No writing style provided yet."),
                "VOICE BENCHMARK\n"
                + (
                    "\n\n---\n\n".join(writing_samples)
                    if writing_samples
                    else "No writing samples provided yet."
                ),
                "CONTENT BANK CONTEXT\n"
                + (
                    json.dumps(memories, indent=2)
                    if memories
                    else "No matching Content Bank entry. Do not invent personal context; make the post more observational and less specific."
                ),
                "QUALITY BAR\n"
                "1. Data plus emotion: connect facts to lived experience.\n"
                "2. Rhetorical questions: pull readers into reflection.\n"
                "3. Numbered structure when useful: 1/, 2/, 3/.\n"
                "4. Vulnerability with strength: honest, resilient, never performative.\n"
                "5. Call to connection: invite readers into the conversation.\n"
                "6. Measured but passionate: conviction with humility.\n"
                "7. Human specificity: avoid generic AI cadence, tidy fake certainty, and recycled thought-leadership phrases.",
            ]
        )

    @staticmethod
    def _generate_chat_reply(state: dict, content: str) -> str | None:
        provider = ClaudeProvider()
        if not provider.configured:
            return None

        system_prompt = (
            "You are Mira, Blidx's content operating partner. You are not a generic assistant. "
            "Your job is to help a founder turn real work into LinkedIn content. "
            "Be calm, specific, and editorial. Avoid robotic phrases, hype, and repeated templates. "
            "Do not always use the same structure. Sometimes ask one sharp question; sometimes offer options; "
            "sometimes name the strongest angle directly. Keep replies short enough for a chat screen. "
            "When the user asks for ideas, angles, or what to post, act like a content strategist first: "
            "give a strategic read, name why the idea works or does not work, identify audience fit, "
            "and ask for the missing concrete detail before drafting. "
            "When suggesting angles, format them exactly as '1/ Angle title: one-sentence explanation.' "
            "so the product can offer draft actions. If the user's topic is broad and lacks a real moment, "
            "ask for one concrete detail before drafting. Respect the user's voice controls."
        )
        messages = state.get("messages", [])[-8:]
        workflow = state.get("mira_workflow", {})
        prompt = "\n\n".join(
            [
                "USER PROFILE\n" + json.dumps(state.get("profile", {}), indent=2),
                "CONTENT BANK\n" + json.dumps(state.get("content_bank", [])[:5], indent=2),
                "MIRA WORKFLOW STATE\n" + json.dumps(workflow, indent=2),
                "RECENT CHAT\n" + json.dumps(messages, indent=2),
                "LATEST USER MESSAGE\n" + content,
            ]
        )
        try:
            return provider.generate(prompt, system_prompt)
        except (httpx.HTTPError, RuntimeError, ValueError):
            return None

    @staticmethod
    def _content_strategy_reply(state: dict, content: str) -> str | None:
        if not DemoStore._wants_content_strategy(content):
            return None

        profile = state.get("profile", {})
        memories = state.get("content_bank", [])
        audience = profile.get("audience") or ["your audience"]
        audience_label = ", ".join(audience[:3])
        latest = memories[0].get("raw_text", "") if memories else ""
        topic = DemoStore._strategy_topic(content, latest)
        score, label, strengths, risks = DemoStore._strategy_score(topic, latest, audience)
        best_angle = DemoStore._best_strategy_angle(topic, latest)
        missing_detail = DemoStore._missing_strategy_detail(topic, latest)
        angles = DemoStore._remember_angle_options(state, topic, latest)
        recommended_framework = DemoStore._recommended_framework(topic, latest, score)
        angle_lines = "\n\n".join(
            f"{index}/ {angle['title']}: {angle['detail']} Framework: {DemoStore._framework_label(angle.get('framework'))}."
            for index, angle in enumerate(angles, start=1)
        )

        return (
            f"Step 2/4: choose the angle before drafting.\n\n"
            f"Strategic read: {label} ({score}/5).\n\n"
            f"Why it can work: {strengths}\n\n"
            f"Risk: {risks}\n\n"
            f"Best angle for {audience_label}: {best_angle}\n\n"
            f"Recommended draft framework: {DemoStore._framework_label(recommended_framework)}.\n\n"
            "Mira judgment: I would not draft this as a generic thought-leadership post. I would keep one concrete moment visible and let the opinion come from that.\n\n"
            "Three draftable directions:\n\n"
            f"{angle_lines}\n\n"
            f"Missing detail before I draft: {missing_detail}\n\n"
            "Choose “angle 1”, “angle 2”, or “angle 3”, or send the missing detail first."
        )

    @staticmethod
    def _wants_content_strategy(content: str) -> bool:
        lowered = content.lower()
        if DemoStore._wants_draft(content):
            return False
        strategy_signals = (
            "what should",
            "angle",
            "angles",
            "idea",
            "ideas",
            "suggest",
            "topic",
            "topics",
            "linkedin",
            "post",
            "content",
            "is this good",
            "should i write",
        )
        if any(signal in lowered for signal in strategy_signals):
            return True
        return len(content.split()) >= 12 and not content.strip().endswith("?")

    @staticmethod
    def _strategy_topic(content: str, latest: str = "") -> str:
        lowered = content.lower()
        if latest and any(
            phrase in lowered
            for phrase in ("what should", "from my content bank", "from the content bank", "latest memory")
        ):
            return latest
        topic = DemoStore._extract_topic(content)
        for phrase in (
            "give me angles from",
            "give me angles about",
            "suggest angles from",
            "suggest angles about",
            "what should i post about",
            "what should i post",
            "post about",
            "content about",
        ):
            if topic.lower().startswith(phrase):
                topic = topic[len(phrase) :].strip(" :.-")
                break
        return topic or latest or content

    @staticmethod
    def _strategy_score(topic: str, latest: str, audience: list[str]) -> tuple[int, str, str, str]:
        text = f"{topic} {latest}".lower()
        score = 1
        if latest:
            score += 1
        if any(word in text for word in ("i ", "we ", "my ", "our ", "founder", "customer", "event", "spoke", "learned", "realized")):
            score += 1
        if any(word in text for word in ("but", "versus", "tension", "problem", "hard", "missed", "changed")):
            score += 1
        audience_terms = " ".join(audience).lower()
        if any(term in text for term in audience_terms.split() if len(term) > 4):
            score += 1
        score = min(score, 5)
        if score >= 4:
            label = "strong"
            strengths = "it has enough specificity and tension to become more than a generic opinion."
            risks = "do not over-polish it; keep the real moment visible."
        elif score >= 3:
            label = "promising"
            strengths = "there is a useful angle here, but it needs one concrete detail to feel owned."
            risks = "without the moment, it may sound like a standard LinkedIn take."
        else:
            label = "not ready yet"
            strengths = "the theme may be relevant, but the content signal is still too abstract."
            risks = "drafting now would likely produce generic AI-style content."
        return score, label, strengths, risks

    @staticmethod
    def _best_strategy_angle(topic: str, latest: str = "") -> str:
        text = f"{topic} {latest}".lower()
        if "ai" in text and any(word in text for word in ("health", "mental", "care")):
            return "focus on where AI reduces friction, and where trust still needs a human relationship."
        if "ai" in text:
            return "make the post about judgment, taste, and workflow instead of simply saying AI is useful."
        if "content" in text or "linkedin" in text:
            return "show that the real bottleneck is not writing, but capturing founder context at the right moment."
        if latest:
            return "open with the lived moment, then name the lesson it revealed."
        return "turn the broad topic into one specific founder decision, mistake, or observation."

    @staticmethod
    def _recommended_framework(topic: str, latest: str = "", score: int = 3) -> str:
        text = f"{topic} {latest}".lower()
        if latest and any(word in text for word in ("spoke", "met", "event", "this week", "noticed", "learned")):
            return "field_note"
        if any(word in text for word in ("wrong", "misunderstand", "myth", "problem", "versus", "not")):
            return "sharp_pov"
        if any(word in text for word in ("how", "workflow", "steps", "framework", "process")):
            return "practical_note"
        if score <= 2:
            return "story_observation"
        return "field_note"

    @staticmethod
    def _missing_strategy_detail(topic: str, latest: str = "") -> str:
        text = f"{topic} {latest}".lower()
        if latest:
            return "what exactly changed in your thinking after this happened?"
        if "event" in text:
            return "what was one moment from the event that surprised you?"
        if "ai" in text:
            return "what did you personally see, build, test, or question around AI?"
        return "what happened in real life that made this topic feel relevant today?"

    @staticmethod
    def _short_topic(topic: str) -> str:
        cleaned = DemoStore._clean_topic(topic).strip()
        return cleaned[:90] + ("..." if len(cleaned) > 90 else "")

    @staticmethod
    def _fallback_chat_reply(state: dict, content: str) -> str:
        profile = state.get("profile", {})
        company = profile.get("company_name") or "your company"
        memories = state.get("content_bank", [])
        bank_count = len(memories)
        lowered = content.lower()
        latest = memories[0]["raw_text"] if memories else ""
        audience = ", ".join(profile.get("audience") or ["your audience"])

        if any(word in lowered for word in ("hi", "hello", "hey")) and len(content.split()) <= 4:
            return (
                "Hi. Tell me one real thing that happened this week, or ask me for angles from the Content Bank. "
                f"I’ll keep the {company} context in the background and help you turn the strongest bit into a post."
            )

        if any(phrase in lowered for phrase in ("what can you do", "how does this work", "help me")):
            return (
                "I can help in four practical ways:\n\n"
                "1/ Capture a real moment into the Content Bank.\n"
                "2/ Turn it into 2-3 LinkedIn angles.\n"
                "3/ Draft a post in your voice.\n"
                "4/ Move the approved draft toward LinkedIn posting.\n\n"
                "A good next message is: “Give me angles from the AI event.”"
            )

        if "what should" in lowered:
            if latest:
                return (
                    f"The strongest starting point is already in your Content Bank:\n\n“{latest}”\n\n"
                    "I’d turn that into a post because it has a real moment, not just an opinion. "
                    "The angle I’d test: what this moment changed in your thinking.\n\n"
                    "Want three angles, or should I draft the strongest one?"
                )
            return (
                "I’d start with one real moment from this week. A post becomes much stronger when it begins with something you actually saw, built, learned, or questioned."
            )

        if any(phrase in lowered for phrase in ("angle", "idea", "suggest", "topic")):
            if latest:
                return (
                    f"Here are three directions I’d consider:\n\n"
                    f"1/ Personal founder moment: open with “{latest}” and name what it made you reconsider.\n\n"
                    "2/ Industry point of view: show where technology helps, and where human judgment still matters.\n\n"
                    f"3/ Reader question: ask {audience} where they think the workflow breaks today.\n\n"
                    "I’d draft angle 1 first because it is the hardest for a generic AI tool to copy."
                )
            return (
                "I can suggest angles, but I need one real moment first. Tell me something that happened this week: an event, customer conversation, launch, lesson, or tension you noticed."
            )

        if "linkedin" in lowered or "post" in lowered or "content" in lowered:
            if latest:
                return (
                    f"For {company}, I would not start with a generic thought. I would start with the freshest real moment:\n\n"
                    f"“{latest}”\n\n"
                    "Then I’d build the post around one tension, one lesson, and one question for the reader. "
                    "If you want the fastest path, say “draft it” and I’ll create the draft card."
                )
            return (
                f"Yes. For {company}, I’d turn this into a post by choosing one concrete moment, "
                "one clear point of view, and one question for the audience. Share the moment first, then I can draft from it."
            )

        if any(phrase in lowered for phrase in ("too long", "shorter", "better", "improve", "change")):
            pending = next((post for post in state.get("posts", []) if post.get("status") == "pending"), None)
            if pending:
                return (
                    "I can revise the active draft. Use the Edit button on the draft card and tell me the direction, for example: "
                    "“shorter and more personal” or “make the opening stronger.”"
                )

        if bank_count:
            variants = [
                (
                    f"I’d connect your message back to the latest Content Bank moment: “{latest}”. "
                    "There is a useful founder insight hiding there. Do you want an angle, or should I draft it?"
                ),
                (
                    f"The strongest thread I see is the tension between speed and trust. For {company}, that can become a post about "
                    "where AI helps the work move faster, and where human connection still has to lead. Want me to turn that into a draft?"
                ),
                (
                    "I would make this more specific before drafting. One good framing is:\n\n"
                    "“AI made the work feel more possible, but it also made me think harder about what should stay human.”\n\n"
                    "That gives the post a clear emotional and strategic center."
                ),
            ]
            index = (len(content) + len(state.get("messages", []))) % len(variants)
            return variants[index]

        if "?" in content:
            return (
                "My short answer: yes, but we should anchor it in a real moment so it does not sound generic. "
                "Give me one detail from the week, and I’ll help shape it into a LinkedIn-ready point of view."
            )

        return (
            "That can become useful content if we make it concrete. What is the real moment behind it: something you saw, built, learned, questioned, or changed your mind about?"
        )


demo_store = DemoStore()
