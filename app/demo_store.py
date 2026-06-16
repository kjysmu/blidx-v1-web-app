import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DemoStore:
    def __init__(self) -> None:
        self.path = Path(__file__).resolve().parent.parent / "data" / "demo_state.json"
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(self._initial_state())

    def _initial_state(self) -> dict:
        return {
            "user": {
                "id": str(uuid.uuid4()),
                "email": "jae@blidx.local",
                "user_name": "Jae",
            },
            "profile": {
                "first_name": "Jae",
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
        }

    def _read(self) -> dict:
        return json.loads(self.path.read_text())

    def _write(self, state: dict) -> None:
        self.path.write_text(json.dumps(state, indent=2))

    def snapshot(self) -> dict:
        with self.lock:
            return deepcopy(self._read())

    def update_profile(self, profile: dict) -> dict:
        with self.lock:
            state = self._read()
            state["profile"].update(profile)
            self._write(state)
            return deepcopy(state["profile"])

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
            self._write(state)
            return deepcopy(post)

    def edit_post(self, post_id: str, instructions: str) -> dict | None:
        with self.lock:
            state = self._read()
            post = self._find_post(state, post_id)
            if post is None:
                return None

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
            if content == post["content"]:
                content += f"\n\nEdit note applied: {instructions.strip()}"

            post["content"] = content[:3000]
            post["char_count"] = len(post["content"])
            post["version"] += 1
            post["status"] = "pending"
            post["updated_at"] = utc_now().isoformat()
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

    def save_post(self, post_id: str) -> dict | None:
        return self._set_status(post_id, "draft")

    def delete_post(self, post_id: str) -> dict | None:
        return self._set_status(post_id, "deleted")

    def reset(self) -> dict:
        with self.lock:
            state = self._initial_state()
            self._write(state)
            return deepcopy(state)

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
    def _draft(state: dict, topic: str, source: str) -> dict:
        profile = state["profile"]
        memory = state["content_bank"][0] if state["content_bank"] else None
        first_name = profile.get("first_name") or "there"
        company = profile.get("company_name") or "my company"
        audience = ", ".join(profile.get("audience") or ["founders"])
        memory_text = memory["raw_text"] if memory else ""

        hook = topic.strip().rstrip(".")
        personal_block = (
            f"\n\nA recent moment made this concrete for me: {memory_text}"
            if memory_text
            else (
                "\n\nBuilding this in practice has made one thing clear: "
                "consistency comes from owning the workflow, not waiting for inspiration."
            )
        )
        content = (
            f"{hook.capitalize()} is not mainly a content problem.\n\n"
            f"It is a workflow problem.\n\n"
            f"At {company}, I keep returning to a simple principle: the system should "
            f"carry the work forward, while the founder provides judgment and context."
            f"{personal_block}\n\n"
            f"For {audience}, the useful question is not “Can AI write this?” "
            f"It is “Can the system reliably turn real work into a clear point of view?”\n\n"
            f"That is the standard I think founder-led content should meet.\n\n"
            f"What part of your content workflow creates the most friction today?"
        )
        now = utc_now()
        return {
            "id": str(uuid.uuid4()),
            "title": hook[:70].capitalize(),
            "content": content[:3000],
            "status": "pending",
            "source": source,
            "sources": (
                [
                    {
                        "type": "personal",
                        "title": f"Content Bank · {memory['category'].title()}",
                    }
                ]
                if memory
                else []
            ),
            "char_count": len(content[:3000]),
            "version": 1,
            "scheduled_at": None,
            "published_at": None,
            "published_url": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "message": f"{first_name}, I used your profile and freshest context for this angle.",
        }


demo_store = DemoStore()
