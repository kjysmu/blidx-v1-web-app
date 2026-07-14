import re
from collections import Counter
from typing import Any


VOICE_STOP_WORDS = {
    "about", "after", "again", "also", "because", "before", "being", "could",
    "from", "have", "into", "just", "more", "should", "that", "their", "there",
    "these", "they", "this", "those", "through", "very", "what", "when", "where",
    "which", "with", "would", "your",
}


class VoiceProfileService:
    VERSION = 1

    @classmethod
    def analyze(cls, samples: list[str] | None) -> dict[str, Any]:
        cleaned = [sample.strip() for sample in (samples or []) if sample and sample.strip()]
        combined = "\n\n".join(cleaned)
        words = cls._words(combined)
        sentences = cls._sentences(combined)
        paragraphs = cls._paragraphs(combined)
        openings = [cls._opening_style(sample) for sample in cleaned]

        sample_count = len(cleaned)
        total_words = len(words)
        readiness = (
            "calibrated"
            if sample_count >= 3 and total_words >= 150
            else "learning"
            if sample_count
            else "untrained"
        )
        avg_sentence_words = cls._average_words(sentences)
        avg_paragraph_words = cls._average_words(paragraphs)
        first_person_rate = cls._rate(sentences, cls._has_first_person)
        question_rate = cls._rate(sentences, lambda value: "?" in value)
        numbered_list_rate = cls._rate(cleaned, cls._has_numbered_list)
        opening_counts = Counter(openings)
        preferred_opening = opening_counts.most_common(1)[0][0] if opening_counts else "unknown"
        vocabulary = Counter(
            word
            for word in words
            if len(word) > 3 and word not in VOICE_STOP_WORDS
        )
        common_vocabulary = [word for word, count in vocabulary.most_common(12) if count >= 2][:8]

        profile = {
            "version": cls.VERSION,
            "readiness": readiness,
            "sample_count": sample_count,
            "total_words": total_words,
            "avg_sentence_words": avg_sentence_words,
            "sentence_length": cls._length_band(avg_sentence_words, 10, 20),
            "avg_paragraph_words": avg_paragraph_words,
            "paragraph_length": cls._length_band(avg_paragraph_words, 18, 40),
            "first_person_rate": first_person_rate,
            "question_rate": question_rate,
            "numbered_list_rate": numbered_list_rate,
            "preferred_opening": preferred_opening,
            "opening_styles": dict(opening_counts),
            "common_vocabulary": common_vocabulary,
        }
        profile["summary"] = cls._summary(profile)
        return profile

    @classmethod
    def prompt_context(cls, profile: dict[str, Any]) -> str:
        voice = profile.get("voice_profile") or cls.analyze(profile.get("writing_samples"))
        if not voice.get("sample_count"):
            return "Voice is not calibrated yet. Follow the explicit style notes and avoid inventing a personal style."

        first_person = (
            "Use first person regularly."
            if voice.get("first_person_rate", 0) >= 35
            else "Use first person sparingly."
        )
        questions = (
            "Questions are part of the founder's natural rhythm."
            if voice.get("question_rate", 0) >= 15
            else "Do not force a closing question."
        )
        lists = (
            "Numbered lists are a recurring pattern."
            if voice.get("numbered_list_rate", 0) >= 40
            else "Avoid numbered lists unless the idea is genuinely procedural."
        )
        vocabulary = ", ".join(voice.get("common_vocabulary") or []) or "no repeated vocabulary signal yet"
        return "\n".join(
            [
                f"Calibration: {voice.get('readiness')} from {voice.get('sample_count')} sample(s) and {voice.get('total_words')} words.",
                f"Rhythm: {voice.get('sentence_length')} sentences (about {voice.get('avg_sentence_words')} words) and {voice.get('paragraph_length')} paragraphs (about {voice.get('avg_paragraph_words')} words).",
                f"Opening tendency: {voice.get('preferred_opening', 'unknown').replace('_', ' ')}.",
                first_person,
                questions,
                lists,
                f"Recurring vocabulary: {vocabulary}. Use this only as a signal; never copy a sample sentence.",
            ]
        )

    @classmethod
    def match(cls, profile: dict[str, Any], content: str) -> tuple[int, str]:
        voice = profile.get("voice_profile") or cls.analyze(profile.get("writing_samples"))
        if not voice.get("sample_count"):
            return 2, "Add writing samples to measure founder voice reliably."

        features = cls._content_features(content)
        matches = 0
        matches += features["sentence_length"] == voice.get("sentence_length")
        matches += features["paragraph_length"] == voice.get("paragraph_length")
        matches += features["first_person"] == (voice.get("first_person_rate", 0) >= 35)
        matches += features["question"] == (voice.get("question_rate", 0) >= 15)
        matches += features["numbered_list"] == (voice.get("numbered_list_rate", 0) >= 40)
        detail = (
            "Rhythm and structure match the founder's calibrated voice."
            if matches >= 4
            else "Sentence rhythm, paragraphing, or recurring voice patterns differ from the founder's samples."
        )
        return int(matches), detail

    @classmethod
    def _content_features(cls, text: str) -> dict[str, Any]:
        sentences = cls._sentences(text)
        paragraphs = cls._paragraphs(text)
        return {
            "sentence_length": cls._length_band(cls._average_words(sentences), 10, 20),
            "paragraph_length": cls._length_band(cls._average_words(paragraphs), 18, 40),
            "first_person": cls._has_first_person(text),
            "question": "?" in text,
            "numbered_list": cls._has_numbered_list(text),
        }

    @staticmethod
    def _words(text: str) -> list[str]:
        return re.findall(r"[a-z][a-z'-]*", text.lower())

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [item.strip() for item in re.split(r"(?<=[.!?])\s+|\n+", text) if item.strip()]

    @staticmethod
    def _paragraphs(text: str) -> list[str]:
        return [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]

    @classmethod
    def _average_words(cls, values: list[str]) -> int:
        if not values:
            return 0
        return round(sum(len(cls._words(value)) for value in values) / len(values))

    @staticmethod
    def _rate(values: list[str], predicate) -> int:
        if not values:
            return 0
        return round(sum(1 for value in values if predicate(value)) / len(values) * 100)

    @staticmethod
    def _length_band(value: int, short_limit: int, medium_limit: int) -> str:
        if value < short_limit:
            return "short"
        if value < medium_limit:
            return "medium"
        return "long"

    @staticmethod
    def _has_first_person(text: str) -> bool:
        return bool(re.search(r"\b(i|i'm|i've|i'd|my|mine|we|we're|we've|our|ours)\b", text.lower()))

    @staticmethod
    def _has_numbered_list(text: str) -> bool:
        return bool(re.search(r"(?m)^\s*(?:[1-9][.)/]|[-*])\s+", text))

    @classmethod
    def _opening_style(cls, text: str) -> str:
        first = re.split(r"(?<=[.!?])\s+|\n+", text.strip(), maxsplit=1)[0].strip()
        if "?" in first:
            return "question"
        if re.search(r"\b\d+(?:[.,]\d+)?%?\b", first):
            return "number_or_fact"
        if cls._has_first_person(first):
            return "first_person"
        return "statement"

    @staticmethod
    def _summary(profile: dict[str, Any]) -> str:
        count = profile["sample_count"]
        if not count:
            return "Add three real posts so Mira can learn your rhythm instead of guessing."
        if profile["readiness"] != "calibrated":
            return f"Learning from {count} sample(s). Add more real posts until Mira has at least 150 words across three samples."
        return (
            f"Calibrated from {count} samples: {profile['sentence_length']} sentences, "
            f"{profile['paragraph_length']} paragraphs, and a {profile['preferred_opening'].replace('_', ' ')} opening tendency."
        )
