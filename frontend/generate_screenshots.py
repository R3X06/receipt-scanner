"""
Generates KALLA's README screenshots by driving a headless browser
against a running local instance. Mirrors generate_icon.py's spirit:
one script, run on demand, deterministic output.

Requires: pip install playwright --break-system-packages
Then once: playwright install chromium

Usage:
    python generate_screenshots.py

Assumes:
- Frontend dev server running at FRONTEND_URL (default localhost:5173)
- A demo/test account exists with DEMO_EMAIL / DEMO_PASSWORD
- That account has at least one savings goal with an allocation
  already made, so "View distribution" has real data to show
"""

import os
import time
from playwright.sync_api import sync_playwright

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
DEMO_EMAIL = os.environ.get("DEMO_EMAIL", "demo@demo.com")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "screenshots")

DESKTOP_VIEWPORT = {"width": 1440, "height": 900}
MOBILE_VIEWPORT = {"width": 390, "height": 844}


def login(page):
    page.goto(FRONTEND_URL)
    page.get_by_role("button", name="Get Started").click()
    page.get_by_placeholder("you@example.com").fill(DEMO_EMAIL)
    page.get_by_placeholder("••••••••").fill(DEMO_PASSWORD)
    page.get_by_role("button", name="Sign in", exact=True).click()
    page.wait_for_selector("text=Spending by category", timeout=10000)


def shot(page, filename, delay=0.3):
    time.sleep(delay)
    path = os.path.join(OUT_DIR, filename)
    page.screenshot(path=path)
    print(f"saved {filename}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    if not DEMO_PASSWORD:
        raise SystemExit("Set DEMO_PASSWORD env var before running.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # --- Desktop dashboard ---
        page = browser.new_page(viewport=DESKTOP_VIEWPORT)
        login(page)
        shot(page, "dashboard.png", delay=1.0)

        # --- Allocation / distribution ---
        page.get_by_label("Savings").click()
        page.wait_for_selector("text=View distribution", timeout=5000)
        page.get_by_text("View distribution").click()
        page.wait_for_timeout(500)
        shot(page, "allocation.png")
        page.keyboard.press("Escape")
        page.keyboard.press("Escape")

        # --- Statement (receipt print animation) ---
        page.get_by_text("[ print statement ]").click()
        page.wait_for_timeout(1500)  # let the line-by-line print finish
        shot(page, "statement.png")
        page.keyboard.press("Escape")

        page.close()

        # --- Mobile ---
        mobile_page = browser.new_page(viewport=MOBILE_VIEWPORT)
        login(mobile_page)
        shot(mobile_page, "mobile.png", delay=1.0)
        mobile_page.close()

        browser.close()

    print(f"\nAll screenshots saved to {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()