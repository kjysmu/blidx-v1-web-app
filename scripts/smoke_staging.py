"""Post-deploy smoke test for a Blidx deployment.

Runs an isolated end-to-end flow against a live base URL using a throwaway
registered user, so it never touches the shared public demo state.

Usage:
    python scripts/smoke_staging.py https://blidx-v1-web-app.onrender.com
    python scripts/smoke_staging.py http://localhost:8000
"""
import json
import sys
import urllib.error
import urllib.request
import uuid

RESULTS: list[tuple[bool, str]] = []


def check(passed: bool, label: str, detail: str = "") -> bool:
    RESULTS.append((passed, label))
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))
    return passed


def request(base: str, path: str, data=None, token: str | None = None, method: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        base + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers=headers,
        method=method or ("POST" if data is not None else "GET"),
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read().decode()
        return response.status, json.loads(body) if body.strip().startswith(("{", "[")) else body


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    base = sys.argv[1].rstrip("/")
    print(f"Smoke testing {base}\n")

    # 1. Service is up and serving the app
    status, _ = request(base, "/health")
    check(status == 200, "health endpoint responds 200")
    status, body = request(base, "/")
    check(status == 200 and "Blidx" in str(body), "root serves the web app")

    # 2. Integration wiring — the go/no-go signals for staging
    status, integrations = request(base, "/api/integrations/status")
    anthropic_ok = integrations.get("anthropic", {}).get("configured", False)
    check(status == 200, "integrations status responds")
    check(
        anthropic_ok,
        "ANTHROPIC_API_KEY configured (Claude-powered Mira)",
        "" if anthropic_ok else "Mira will use the deterministic fallback",
    )
    linkedin = integrations.get("linkedin", {})
    check(
        bool(linkedin.get("configured")),
        "LinkedIn OAuth credentials configured",
        "" if linkedin.get("configured") else "manual copy/open fallback only",
    )
    print(f"       database storage: {integrations.get('database', {}).get('storage')}")

    # 3. Isolated user flow: register → onboard → chat → draft → approve
    email = f"smoke-{uuid.uuid4().hex[:10]}@example.com"
    status, auth = request(base, "/auth/register", {
        "email": email,
        "password": "smoke-test-password-1",
        "user_name": "Smoke Test",
    })
    token = auth.get("access_token")
    if not check(status == 200 and bool(token), "register throwaway user", email):
        return finish()

    status, _ = request(base, "/api/onboarding/complete", {
        "first_name": "Smoke",
        "company_name": "Smoke Test Co",
        "industry": "SaaS",
        "company_description": "Deployment smoke test workspace.",
        "audience": ["Founders"],
        "expertise": ["Testing"],
        "posting_frequency": "3-4x_per_week",
        "first_memory": "Ran the staging smoke test and everything held together.",
    }, token=token)
    check(status == 200, "complete onboarding")

    status, chat = request(base, "/api/chat/message", {
        "message": "What should I post about today?",
    }, token=token)
    check(status == 200 and bool(chat.get("reply")), "chat message gets a Mira reply")

    status, draft = request(base, "/api/drafts", {"topic": "smoke test founder lessons"}, token=token)
    post = draft.get("post") or draft
    provider = post.get("generation_provider", "unknown")
    check(status == 200 and post.get("status") == "pending", "draft generation", f"provider: {provider}")
    if anthropic_ok:
        check(provider != "template", "draft used Claude, not the template fallback", provider)

    status, approved = request(
        base, f"/api/drafts/{post['id']}/approve",
        {"schedule_type": "best_time"}, token=token,
    )
    check(status == 200 and approved.get("status") == "scheduled", "approve draft to calendar")

    status, state = request(base, "/api/state", token=token)
    posts = state.get("posts", [])
    check(
        status == 200 and len(posts) >= 1 and "proactive_brief" in state,
        "user state consistent after flow",
        f"{len(posts)} post(s), {len(state.get('content_bank', []))} memories",
    )
    return finish()


def finish() -> int:
    failed = [label for passed, label in RESULTS if not passed]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("Failed: " + "; ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as exc:
        print(f"[FAIL] could not reach the service: {exc}")
        sys.exit(1)
