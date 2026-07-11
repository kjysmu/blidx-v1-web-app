import os
import re
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.request import urlopen

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api")

sync_playwright = playwright_sync.sync_playwright
PlaywrightError = playwright_sync.Error

ROOT_DIR = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_health(base_url: str) -> None:
    deadline = time.time() + 20
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as error:  # pragma: no cover - only used for diagnostics
            last_error = error
        time.sleep(0.25)
    raise RuntimeError(f"Blidx server did not become healthy: {last_error}")


@pytest.fixture(scope="module")
def live_server():
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(
        {
            "ANTHROPIC_API_KEY": "",
            "USE_DATABASE_STORAGE": "false",
            "PYTHONPATH": str(ROOT_DIR),
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_health(base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture(scope="module")
def browser():
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            yield browser
            browser.close()
    except PlaywrightError as error:
        pytest.skip(f"Playwright Chromium is not installed or cannot launch: {error}")


def fill_onboarding(page) -> None:
    page.locator('[data-testid="onboarding-form"]').wait_for()
    page.locator('input[name="first_name"]').fill("Jae")
    page.locator('input[name="company_name"]').fill("Blidx QA")
    page.locator('input[name="industry"]').fill("AI SaaS")
    page.locator('input[name="expertise"]').fill("AI, founder content, product strategy")
    page.locator('textarea[name="company_description"]').fill(
        "Blidx helps founders turn real work moments into credible LinkedIn content."
    )
    page.locator('textarea[name="writing_style"]').fill(
        "Specific, human, concise, reflective, and practical."
    )
    page.locator('textarea[name="writing_samples"]').fill(
        "The best founder content usually starts inside the work, not inside a prompt."
    )
    page.locator('textarea[name="first_memory"]').fill(
        "This week I tested a founder workflow and noticed the hard part is choosing what is worth saying."
    )
    page.locator('[data-testid="complete-onboarding"]').click()
    page.locator("h1").filter(has_text=re.compile(r"^Good ")).wait_for()


def test_authenticated_golden_path_in_browser(live_server, browser):
    context = browser.new_context()
    page = context.new_page()
    page.add_init_script("window.open = () => ({ closed: false });")

    email = f"browser-{uuid.uuid4().hex}@example.com"
    page.goto(live_server)

    page.locator('[data-testid="auth-toggle"]').click()
    page.locator('input[name="user_name"]').fill("Jae Browser")
    page.locator('input[name="email"]').fill(email)
    page.locator('input[name="password"]').fill("strong-password-123")
    page.locator('[data-testid="auth-submit"]').click()

    fill_onboarding(page)

    page.locator('[data-tab="bank"]').first.click()
    page.locator('[data-testid="bank-text"]').fill(
        "A founder told me they do not need another AI writing tool; they need help deciding which real work moment deserves a post."
    )
    page.locator('[data-testid="bank-save"]').click()
    page.get_by_text("Saved to Content Bank").wait_for()

    page.locator('[data-tab="chat"]').first.click()
    page.locator('[data-testid="chat-message"]').fill("Give me 3 angles from my Content Bank")
    page.locator('[data-testid="chat-send"]').click()
    page.locator('[data-testid="angle-action"]').first.wait_for(timeout=10000)

    page.locator('[data-testid="angle-action"]').first.click()
    page.locator('[data-testid="draft-card"]').first.wait_for(timeout=10000)
    page.get_by_text("Draft ready:").first.wait_for()

    page.locator('[data-testid="open-draft-workspace"]').first.click()
    draft_modal = page.locator('[data-testid="draft-review-modal"]')
    draft_modal.wait_for()
    draft_modal.get_by_text("Draft workspace").wait_for()
    page.locator('[data-testid="voice-match"]').click()
    page.get_by_text("Mira saved this voice match").wait_for()
    page.locator("#close-draft-review").click()

    page.locator('[data-testid="linkedin-handoff"]').first.click()
    page.locator('[data-testid="linkedin-modal"]').wait_for()
    page.locator('[data-testid="linkedin-not-yet"]').click()
    page.get_by_text("Draft kept in Blidx for later.").wait_for()

    # Save now lives in the draft workspace, not on the chat card.
    page.locator('[data-testid="review-draft"]').first.click()
    page.locator('[data-testid="draft-review-modal"]').wait_for()
    page.locator('[data-testid="save-draft"]').first.click()
    page.get_by_text("Saved to Library").wait_for()

    page.locator('[data-tab="library"]').first.click()
    page.locator('[data-testid="library-page"]').wait_for()
    page.get_by_text("Open draft workspace").first.wait_for()
    page.get_by_text("Approve").first.click()

    page.locator('[data-testid="schedule-modal"]').wait_for()
    page.locator('[data-schedule="best_time"]').click()
    page.get_by_text("Scheduled and added to Calendar").wait_for()

    page.locator('[data-tab="calendar"]').first.click()
    calendar_page = page.locator('[data-testid="calendar-page"]')
    calendar_page.wait_for()
    calendar_page.get_by_text("Best time this week").first.wait_for()

    page.locator('[data-tab="settings"]').first.click()
    settings_page = page.locator('[data-testid="settings-page"]')
    settings_page.wait_for()
    settings_page.get_by_text("Your Profile", exact=True).wait_for()
    settings_page.get_by_text("LinkedIn", exact=True).first.wait_for()
    settings_page.get_by_text("Notifications", exact=True).wait_for()
    settings_page.get_by_text("Account", exact=True).wait_for()
    settings_page.get_by_text("Mira profile details").wait_for()
    settings_page.get_by_text("Help & feedback", exact=True).wait_for()
    assert settings_page.get_by_text("System / staging", exact=True).count() == 0
    assert settings_page.get_by_text("PayloadCMS review", exact=True).count() == 0
    settings_page.locator('input[name="first_name"]').wait_for()

    # The tester checklist now lives at the bottom of Settings, not the quick menu.
    page.locator('[data-action="qa-status"]').click()
    qa_page = page.locator('[data-testid="qa-page"]')
    qa_page.wait_for()
    qa_page.get_by_text("Recommended QA script").wait_for()
    qa_page.get_by_text("Mockup alignment").wait_for()
    qa_page.get_by_text("Known limitations").wait_for()
    qa_page.get_by_text("How to send feedback").wait_for()

    context.close()


def test_mobile_settings_uses_full_viewport_and_real_profile_editor(live_server, browser):
    context = browser.new_context(
        viewport={"width": 430, "height": 932},
        is_mobile=True,
        has_touch=True,
        device_scale_factor=3,
    )
    page = context.new_page()

    email = f"mobile-{uuid.uuid4().hex}@example.com"
    page.goto(live_server)

    page.locator('[data-testid="auth-toggle"]').click()
    page.locator('input[name="user_name"]').fill("Jae Mobile")
    page.locator('input[name="email"]').fill(email)
    page.locator('input[name="password"]').fill("strong-password-123")
    page.locator('[data-testid="auth-submit"]').click()

    fill_onboarding(page)

    page.locator('.mobile-nav [data-tab="settings"]').click()
    page.locator('[data-testid="settings-page"]').wait_for()

    metrics = page.evaluate(
        """() => {
            const rect = (selector) => {
                const element = document.querySelector(selector);
                const box = element.getBoundingClientRect();
                return { left: Math.round(box.left), width: Math.round(box.width) };
            };
            return {
                innerWidth: window.innerWidth,
                shell: rect(".shell"),
                mobileNav: rect(".mobile-nav"),
                settingsActions: [...document.querySelectorAll(".settings-row-action")].map((el) => el.textContent.trim()),
                hasProfileForm: Boolean(document.querySelector('#profile-form input[name="first_name"]')),
            };
        }"""
    )

    assert metrics["shell"] == {"left": 0, "width": metrics["innerWidth"]}
    assert metrics["mobileNav"] == {"left": 0, "width": metrics["innerWidth"]}
    assert "Edit" not in metrics["settingsActions"]
    assert metrics["hasProfileForm"]

    context.close()
