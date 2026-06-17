import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.integrations.llm import ClaudeProvider


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

    def seed_test_scenario(self) -> dict:
        with self.lock:
            state = self._malia_test_state()
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
        return state

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
        return {
            "id": str(uuid.uuid4()),
            "title": hook[:70].capitalize(),
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
            "message": (
                f"{first_name}, I used Claude with your profile and Content Bank context."
                if provider != "template"
                else f"{first_name}, I used your profile and freshest context for this angle."
            ),
        }

    @staticmethod
    def _fallback_draft_text(state: dict, topic: str) -> str:
        profile = state["profile"]
        memory = state["content_bank"][0] if state["content_bank"] else None
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
        return (
            f"{hook.capitalize()} is not mainly a content problem.\n\n"
            f"It is a workflow problem.\n\n"
            f"At {company}, I keep returning to a simple principle: the system should "
            f"carry the work forward, while the founder provides judgment and context."
            f"{personal_block}\n\n"
            f"For {audience}, the useful question is not \"Can AI write this?\" "
            f"It is \"Can the system reliably turn real work into a clear point of view?\"\n\n"
            f"That is the standard I think founder-led content should meet.\n\n"
            f"What part of your content workflow creates the most friction today?"
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


demo_store = DemoStore()
