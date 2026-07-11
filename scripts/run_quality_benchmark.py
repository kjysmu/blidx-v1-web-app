"""Compare Mira with a plain-Claude baseline across the quality catalog.

This is intentionally manual because each scenario makes two Anthropic calls.

Usage:
    python scripts/run_quality_benchmark.py
    python scripts/run_quality_benchmark.py --limit 1
    python scripts/run_quality_benchmark.py --list
"""
import argparse
import json

from app.demo_store import DemoStore
from app.integrations.llm import ClaudeProvider
from app.quality_benchmarks import BENCHMARK_SCENARIOS
from app.services.draft_quality_service import DraftQualityService


def benchmark_state(scenario: dict) -> dict:
    store = DemoStore()
    state = store._initial_state()
    state["profile"].update(
        {
            "first_name": "Malia",
            "role": "Founder",
            "company_name": "Benchmark Co",
            "industry": "Technology and healthcare",
            "writing_style": "Specific, reflective, concise, and willing to leave tension unresolved.",
            "writing_samples": [
                "The most useful lesson from building this week was not a grand one.\n\nIt was noticing where the work kept losing context — and fixing that first."
            ],
            "audience": ["Founders", "Industry peers"],
            "avoided_phrases": ["game changer", "unlock", "the future of"],
        }
    )
    state["content_bank"] = [DemoStore._memory_entry(scenario["memory"])]
    return state


def baseline_draft(provider: ClaudeProvider, state: dict, scenario: dict) -> str:
    prompt = "\n\n".join(
        [
            "Write a LinkedIn post about: " + scenario["topic"],
            "Founder profile: " + json.dumps(state["profile"]),
            "Context: " + scenario["memory"],
        ]
    )
    return provider.generate(
        prompt,
        "You are a helpful AI writing assistant. Return only a polished LinkedIn post under 2,600 characters.",
    )


def score(state: dict, scenario: dict, content: str) -> dict:
    post = {
        "id": scenario["id"],
        "topic": scenario["topic"],
        "title": scenario["topic"],
        "content": content,
        "sources": [{"raw_text": scenario["memory"]}],
    }
    return DraftQualityService.evaluate(state, post, DemoStore._robotic_phrases())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=len(BENCHMARK_SCENARIOS))
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    scenarios = BENCHMARK_SCENARIOS[: max(0, args.limit)]
    if args.list:
        for scenario in scenarios:
            print(f"{scenario['id']}: {scenario['topic']}")
        return 0

    provider = ClaudeProvider()
    if not provider.configured:
        print("ANTHROPIC_API_KEY is required to run the quality benchmark.")
        return 2

    wins = 0
    results = []
    for scenario in scenarios:
        state = benchmark_state(scenario)
        mira_post = DemoStore._draft(state, scenario["topic"], "quality_benchmark")
        baseline_content = baseline_draft(provider, state, scenario)
        mira_review = score(state, scenario, mira_post["content"])
        baseline_review = score(state, scenario, baseline_content)
        winner = "Mira" if mira_review["dimension_score"] > baseline_review["dimension_score"] else "Baseline" if mira_review["dimension_score"] < baseline_review["dimension_score"] else "Tie"
        wins += winner == "Mira"
        result = {
            "scenario": scenario["id"],
            "mira": mira_review["readiness_percent"],
            "plain_claude": baseline_review["readiness_percent"],
            "winner": winner,
        }
        results.append(result)
        print(f"{scenario['id']}: Mira {result['mira']}% | plain Claude {result['plain_claude']}% | {winner}")

    print(f"\nMira wins: {wins}/{len(results)}")
    return 0 if results else 2


if __name__ == "__main__":
    raise SystemExit(main())
