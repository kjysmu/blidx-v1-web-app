import re
from collections import Counter
from copy import deepcopy
from typing import Any


STOP_WORDS = {
    "about", "after", "again", "also", "because", "before", "being", "between",
    "could", "draft", "from", "have", "into", "just", "more", "post", "should",
    "that", "their", "there", "these", "they", "this", "those", "through", "today",
    "with", "would", "write", "your",
}


class DraftQualityService:
    DIMENSION_MAX = 5

    @classmethod
    def evaluate(
        cls,
        state: dict[str, Any],
        post: dict[str, Any],
        robotic_phrases: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        content = (post.get("content") or "").strip()
        profile = state.get("profile") or {}
        topic = post.get("topic") or post.get("title") or ""
        sources = post.get("sources") or []
        context = " ".join(
            [topic, str(profile), *(item.get("raw_text") or item.get("excerpt") or "" for item in sources)]
        )

        dimensions = [
            cls._topic_fidelity(topic, content),
            cls._voice_fidelity(profile.get("writing_samples") or [], content),
            cls._specificity(sources, content),
            cls._factual_safety(context, content),
            cls._structure_variety(state, post, content),
            cls._publish_readiness(content, robotic_phrases),
        ]
        score = sum(item["score"] for item in dimensions)
        maximum = len(dimensions) * cls.DIMENSION_MAX
        blockers = [item["label"] for item in dimensions if item["score"] <= 2]
        return {
            "dimension_score": score,
            "dimension_max": maximum,
            "readiness_percent": round(score / maximum * 100) if maximum else 0,
            "dimensions": dimensions,
            "blockers": blockers,
        }

    @classmethod
    def summarize(cls, state: dict[str, Any]) -> dict[str, Any]:
        posts = [post for post in state.get("posts", []) if post.get("status") != "deleted"]
        feedback = state.get("draft_feedback") or []
        scored = [post.get("quality_review") or {} for post in posts]
        percentages = [item.get("readiness_percent") for item in scored if item.get("readiness_percent") is not None]
        explicit = [item for item in feedback if item.get("event") == "voice_rating"]
        positive = sum(1 for item in explicit if item.get("sentiment") == "sounds_like_me")
        revisions = [item for item in feedback if item.get("event") == "edit"]
        return {
            "drafts_evaluated": len(percentages),
            "average_readiness": round(sum(percentages) / len(percentages)) if percentages else None,
            "voice_ratings": len(explicit),
            "positive_voice_ratings": positive,
            "voice_match_percent": round(positive / len(explicit) * 100) if explicit else None,
            "revision_count": len(revisions),
            "approval_count": sum(1 for item in feedback if item.get("event") == "approved"),
            "rejection_count": sum(1 for item in feedback if item.get("event") == "rejected"),
            "common_revision_requests": cls._common_revision_requests(revisions),
        }

    @staticmethod
    def feedback_context(state: dict[str, Any], limit: int = 8) -> str:
        feedback = state.get("draft_feedback") or []
        useful = []
        for item in reversed(feedback):
            if item.get("event") == "edit" and item.get("reason"):
                useful.append(f"Revision requested: {item['reason'][:180]}")
            elif item.get("event") == "voice_rating":
                label = "matched voice" if item.get("sentiment") == "sounds_like_me" else "missed voice"
                detail = f": {item['reason'][:180]}" if item.get("reason") else ""
                useful.append(f"User said draft {label}{detail}")
            elif item.get("event") == "rejected":
                useful.append(f"User rejected draft: {(item.get('reason') or 'no reason supplied')[:180]}")
            if len(useful) >= limit:
                break
        return "\n".join(useful) or "No draft feedback yet."

    @classmethod
    def _topic_fidelity(cls, topic: str, content: str) -> dict[str, Any]:
        terms = cls._terms(topic)
        if not terms:
            return cls._dimension("topic_fidelity", "Topic fidelity", 3, "No explicit topic was stored for comparison.")
        overlap = len(terms & cls._terms(content)) / len(terms)
        score = 5 if overlap >= 0.7 else 4 if overlap >= 0.45 else 3 if overlap >= 0.25 else 1
        return cls._dimension(
            "topic_fidelity", "Topic fidelity", score,
            "The requested subject remains central." if score >= 4 else "The draft may have drifted away from the requested subject.",
        )

    @classmethod
    def _voice_fidelity(cls, samples: list[str], content: str) -> dict[str, Any]:
        if not samples:
            return cls._dimension("voice_fidelity", "Voice fidelity", 2, "Add writing samples to measure founder voice reliably.")
        sample = "\n\n".join(samples)
        matches = 0
        matches += cls._has_first_person(sample) == cls._has_first_person(content)
        matches += ("?" in sample) == ("?" in content)
        matches += cls._has_numbered_list(sample) == cls._has_numbered_list(content)
        matches += cls._sentence_length_band(sample) == cls._sentence_length_band(content)
        matches += cls._paragraph_length_band(sample) == cls._paragraph_length_band(content)
        return cls._dimension(
            "voice_fidelity", "Voice fidelity", int(matches),
            "Structure and rhythm resemble the supplied writing samples." if matches >= 4 else "The rhythm or structure differs from the founder's writing samples.",
        )

    @classmethod
    def _specificity(cls, sources: list[dict], content: str) -> dict[str, Any]:
        source_text = " ".join(item.get("raw_text") or "" for item in sources)
        overlap = len(cls._terms(source_text) & cls._terms(content))
        concrete = bool(re.search(r"\b\d+(?:[.,]\d+)?%?(?![\d/])", content))
        score = min(5, (3 if sources else 1) + (1 if overlap >= 3 else 0) + (1 if concrete else 0))
        return cls._dimension(
            "specificity", "Specificity", score,
            "Uses grounded details from the Content Bank." if score >= 4 else "Needs a concrete, sourced moment or detail.",
        )

    @classmethod
    def _factual_safety(cls, context: str, content: str) -> dict[str, Any]:
        claims = set(re.findall(r"\b\d+(?:[.,]\d+)?%?(?![\d/])", content))
        supported = set(re.findall(r"\b\d+(?:[.,]\d+)?%?(?![\d/])", context))
        unsupported = sorted(claims - supported)
        score = 5 if not unsupported else 2 if len(unsupported) == 1 else 1
        detail = "No unsupported numeric claims detected."
        if unsupported:
            detail = "Verify unsupported numeric claims: " + ", ".join(unsupported[:3])
        return cls._dimension("factual_safety", "Factual safety", score, detail)

    @classmethod
    def _structure_variety(cls, state: dict[str, Any], post: dict, content: str) -> dict[str, Any]:
        opening = cls._opening(content)
        prior = [
            cls._opening(item.get("content") or "")
            for item in state.get("posts", [])
            if item.get("id") != post.get("id") and item.get("status") != "deleted"
        ][:5]
        duplicate = any(opening and opening == candidate for candidate in prior)
        score = 2 if duplicate else 5
        return cls._dimension(
            "structure_variety", "Structural variety", score,
            "Opening differs from recent drafts." if not duplicate else "Opening repeats a recent draft too closely.",
        )

    @classmethod
    def _publish_readiness(cls, content: str, robotic_phrases: tuple[str, ...]) -> dict[str, Any]:
        lowered = content.lower()
        robotic = [phrase for phrase in robotic_phrases if phrase in lowered]
        length_ok = 300 <= len(content) <= 2600
        paragraphs = [item for item in content.split("\n\n") if item.strip()]
        score = 5
        if not length_ok:
            score -= 2
        if robotic:
            score -= min(2, len(robotic))
        if len(paragraphs) < 2:
            score -= 1
        score = max(1, score)
        return cls._dimension(
            "publish_readiness", "Publish readiness", score,
            "Readable length and no common AI tells detected." if score >= 4 else "Review length, paragraphing, or robotic phrasing before publishing.",
        )

    @staticmethod
    def _dimension(identifier: str, label: str, score: int, detail: str) -> dict[str, Any]:
        return {"id": identifier, "label": label, "score": score, "max_score": 5, "detail": detail}

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {
            token for token in re.findall(r"[a-z0-9]+", text.lower())
            if len(token) > 3 and token not in STOP_WORDS
        }

    @staticmethod
    def _has_first_person(text: str) -> bool:
        return bool(re.search(r"\b(i|i'm|i've|my|we|our)\b", text.lower()))

    @staticmethod
    def _has_numbered_list(text: str) -> bool:
        return bool(re.search(r"(?m)^\s*[1-3]/", text))

    @staticmethod
    def _sentence_length_band(text: str) -> str:
        sentences = [item for item in re.split(r"[.!?]+", text) if item.strip()]
        average = sum(len(item.split()) for item in sentences) / max(1, len(sentences))
        return "short" if average < 10 else "medium" if average < 20 else "long"

    @staticmethod
    def _paragraph_length_band(text: str) -> str:
        paragraphs = [item for item in text.split("\n\n") if item.strip()]
        average = sum(len(item.split()) for item in paragraphs) / max(1, len(paragraphs))
        return "short" if average < 18 else "medium" if average < 40 else "long"

    @staticmethod
    def _opening(text: str) -> str:
        return re.sub(r"\W+", " ", text.lower().split("\n", 1)[0]).strip()[:100]

    @staticmethod
    def _common_revision_requests(revisions: list[dict]) -> list[dict[str, Any]]:
        labels = ("shorter", "longer", "hook", "personal", "voice", "cta", "formal", "data", "salesy")
        counts = Counter(
            label
            for item in revisions
            for label in labels
            if label in (item.get("reason") or "").lower()
        )
        return [{"request": label, "count": count} for label, count in counts.most_common(5)]
