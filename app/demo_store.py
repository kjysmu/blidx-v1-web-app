import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

            memory = None
            if self._looks_like_memory(content) and not self._wants_draft(content):
                memory = self._memory_entry(content)
                state["content_bank"].insert(0, memory)

            post = None
            wants_draft = self._wants_draft(content)
            followup_draft = self._is_affirmative_draft_request(state, content)
            if wants_draft or followup_draft:
                topic = (
                    self._topic_from_context(state)
                    if followup_draft or self._wants_latest_context(content)
                    else self._extract_topic(content)
                )
                post = self._draft(state, topic, "chat")
                state["posts"].insert(0, post)
                reply = (
                    f"Done. I turned that into a draft using {self._provider_label(post)} "
                    "and placed it below for review."
                )
                actions = ["draft_created"]
                kind = "draft_created"
                post_id = post["id"]
            elif memory:
                reply = (
                    "Saved that to your Content Bank. It has the shape of a personal insight, "
                    "so I can use it as context for the next post. Want me to draft from this angle?"
                )
                actions = ["memory_saved"]
                kind = "message"
                post_id = None
            else:
                reply = self._generate_chat_reply(state, content) or self._fallback_chat_reply(state, content)
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
            else:
                post["status"] = "scheduled"
                if scheduled_at:
                    post["scheduled_at"] = scheduled_at
                else:
                    tomorrow = now + timedelta(days=1)
                    post["scheduled_at"] = tomorrow.replace(
                        hour=0, minute=30, second=0, microsecond=0
                    ).isoformat()
            post["updated_at"] = now.isoformat()
            self._write(state)
            return deepcopy(post)

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
        return self._set_status(post_id, "draft")

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
    def _wants_draft(content: str) -> bool:
        lowered = content.lower()
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
            "write a post about",
            "create a post about",
            "make a post about",
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
        lowered = content.lower().strip(" .!?,")
        affirmative = (
            "yes",
            "yes please",
            "go ahead",
            "do it",
            "draft it",
            "please draft",
            "make it",
            "turn it into a post",
            "sounds good",
        )
        if lowered not in affirmative:
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
    def _topic_from_context(state: dict) -> str:
        if state.get("content_bank"):
            latest = state["content_bank"][0]["raw_text"]
            if "ai" in latest.lower() and "mental" in json.dumps(state.get("profile", {})).lower():
                return "human connection versus AI in mental health"
            return latest[:140]
        messages = [
            message.get("content", "")
            for message in state.get("messages", [])
            if message.get("role") == "user"
        ]
        return messages[-1] if messages else "a founder insight from this week"

    @staticmethod
    def _provider_label(post: dict) -> str:
        provider = post.get("generation_provider") or "template"
        return "Claude" if provider.startswith("Anthropic") else "your profile and Content Bank context"

    @staticmethod
    def _draft(state: dict, topic: str, source: str) -> dict:
        profile = state["profile"]
        memory = state["content_bank"][0] if state["content_bank"] else None
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
        return {
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
                f"{first_name}, I used Claude with your profile and Content Bank context."
                if provider != "template"
                else f"{first_name}, I used your profile and freshest context for this angle."
            ),
        }

    @staticmethod
    def _draft_variants(state: dict, topic: str, main_content: str) -> list[dict]:
        profile = state["profile"]
        company = profile.get("company_name") or "my company"
        audience = ", ".join(profile.get("audience") or ["founders"])
        memory = state["content_bank"][0]["raw_text"] if state.get("content_bank") else ""
        hook = DemoStore._variant_theme(topic)
        context = memory or hook
        variants = [
            {
                "id": "personal_story",
                "label": "Personal founder story",
                "positioning": "Lead with the real moment, then turn it into a lesson.",
                "content": (
                    f"I had a moment this week that made {hook} feel much less abstract.\n\n"
                    f"{context}\n\n"
                    f"At {company}, I keep seeing that the useful insight is rarely sitting in a polished document. "
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
                    f"That is the pattern I keep coming back to while building {company}: the best content is already happening inside the business. "
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
                    f"That is the workflow I want {company} to make feel natural.\n\n"
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
        memories = state["content_bank"][:3]
        memory = memories[0] if memories else None
        company = profile.get("company_name") or "my company"
        audience = ", ".join(profile.get("audience") or ["founders"])
        memory_text = memory["raw_text"] if memory else ""
        hook = topic.strip().rstrip(".")
        expertise = ", ".join(profile.get("expertise") or [])
        if "mental health" in (profile.get("industry") or "").lower():
            return (
                f"What does {hook} ask from us, beyond the technology?\n\n"
                f"At {company}, this question keeps coming back to one thing: people do not only need access. "
                "They need to feel seen, safe, and connected.\n\n"
                f"A recent moment made this more concrete for me: {memory_text or 'I saw how quickly AI can make hard work feel more possible, and also how easily it can make human care feel abstract.'}\n\n"
                "That tension matters.\n\n"
                "1/ AI can reduce friction.\n"
                "2/ It can help founders move faster.\n"
                "3/ But in mental health, the human layer cannot become an afterthought.\n\n"
                f"For {audience}, I think the question is not whether AI belongs in the future of care. "
                "It is where it should support the relationship, and where the relationship must stay central.\n\n"
                "What part of care do you believe should never be automated?"
            )

        personal_block = memory_text or (
            "A recent building moment reminded me that consistent content comes from noticing the work while it is happening."
        )
        return (
            f"I keep thinking about {hook}.\n\n"
            f"At {company}, the best content does not start as content. It starts as a real moment from the work.\n\n"
            f"For example: {personal_block}\n\n"
            "That is the part I want to protect as AI becomes more present in how founders communicate.\n\n"
            "The value is not only speed. It is helping a founder notice what they already learned, sharpen it, "
            f"and share it with {audience} in a way that feels specific.\n\n"
            f"My working principle: use the system for structure, but keep the judgment, context, and point of view human.\n\n"
            f"Curious how others in {expertise or 'this space'} think about this."
        )

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
            "Blend data, emotional truth, and practical insight. Use rhetorical questions when natural. "
            "If listing multiple points, use the user's preferred numbered style like 1/, 2/, 3/. "
            "End with a thoughtful invitation to reflect, connect, or respond. "
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
        memories = state["content_bank"][:8]
        writing_samples = profile.get("writing_samples") or []

        return "\n\n".join(
            [
                "TASK\n" f"Draft a LinkedIn post about: {topic.strip()}",
                "USER PROFILE\n" + json.dumps(profile, indent=2),
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
                    else "No Content Bank entries yet. Ask a reflective question rather than inventing personal context."
                ),
                "QUALITY BAR\n"
                "1. Data plus emotion: connect facts to lived experience.\n"
                "2. Rhetorical questions: pull readers into reflection.\n"
                "3. Numbered structure when useful: 1/, 2/, 3/.\n"
                "4. Vulnerability with strength: honest, resilient, never performative.\n"
                "5. Call to connection: invite readers into the conversation.\n"
                "6. Measured but passionate: conviction with humility.",
            ]
        )

    @staticmethod
    def _generate_chat_reply(state: dict, content: str) -> str | None:
        provider = ClaudeProvider()
        if not provider.configured:
            return None

        system_prompt = (
            "You are Mira, Blidx's content operating partner. You are a focused chatbot, "
            "not a generic assistant. Help the user clarify LinkedIn angles, Content Bank "
            "entries, draft direction, and publishing workflow. Keep replies warm, concise, "
            "and practical. If the user asks for a draft, say you can draft it and ask for "
            "one missing detail only if essential."
        )
        messages = state.get("messages", [])[-8:]
        prompt = "\n\n".join(
            [
                "USER PROFILE\n" + json.dumps(state.get("profile", {}), indent=2),
                "CONTENT BANK\n" + json.dumps(state.get("content_bank", [])[:5], indent=2),
                "RECENT CHAT\n" + json.dumps(messages, indent=2),
                "LATEST USER MESSAGE\n" + content,
            ]
        )
        try:
            return provider.generate(prompt, system_prompt)
        except (httpx.HTTPError, RuntimeError, ValueError):
            return None

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
                f"Hi. I’m here with the {company} context. You can tell me what happened this week, "
                "ask for angles, or ask me to draft a LinkedIn post when you are ready."
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
                    "I’d post about the tension you already have in the Content Bank: "
                    "AI is making the work feel more possible, but mental health still depends on trust, safety, and human connection.\n\n"
                    f"The best starting point is this moment: “{latest}”\n\n"
                    "That gives the post a real founder anchor instead of a generic AI opinion. If you want, ask me for angles or say “draft it.”"
                )
            return (
                "I’d start with one real moment from this week. A post becomes much stronger when it begins with something you actually saw, built, learned, or questioned."
            )

        if any(phrase in lowered for phrase in ("angle", "idea", "suggest", "topic")):
            if latest:
                return (
                    f"I see three possible angles for {company}:\n\n"
                    f"1/ Personal founder moment: use “{latest}” as the opening, then reflect on what it changed in your thinking.\n\n"
                    "2/ Industry point of view: talk about why AI can increase access, but mental health still needs trust and human connection.\n\n"
                    f"3/ Audience question: ask {audience} where they believe technology should support care, and where it should stay in the background.\n\n"
                    "The strongest one for LinkedIn is angle 2, because it connects product, care, and founder judgment. Want me to draft that?"
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
