"""Required local release gate for Blidx.

The regular pytest suite intentionally allows browser tests to skip when
Playwright is unavailable. This command does not: it verifies that Chromium can
launch, then runs the complete test suite, including the real browser journeys.
"""

import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def verify_browser() -> bool:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FAIL] Playwright is not installed.")
        print("       Install it with: pip install -r requirements-dev.txt")
        return False

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.set_content("<title>Blidx release gate</title>")
            ready = page.title() == "Blidx release gate"
            browser.close()
    except PlaywrightError as error:
        print(f"[FAIL] Playwright Chromium could not launch: {error}")
        print("       Install it with: python -m playwright install chromium")
        return False

    if not ready:
        print("[FAIL] Chromium launched but did not complete the preflight page check.")
        return False
    print("[PASS] Playwright Chromium preflight", flush=True)
    return True


def main() -> int:
    print("Blidx release gate\n", flush=True)
    if not verify_browser():
        return 1

    print(
        "\nRunning API, security, integration, quality, and browser tests...\n",
        flush=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT_DIR,
        check=False,
    )
    if result.returncode:
        print("\n[FAIL] Release blocked because one or more tests failed.")
        return result.returncode

    print("\n[PASS] Release gate complete. This commit is ready for staging.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
