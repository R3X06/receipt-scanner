"""/docs, /redoc, /openapi.json — gated off in production, on everywhere else.

The decision itself is a pure function (main._docs_urls_for), tested directly
rather than by reimporting the app module with a different ENVIRONMENT value —
main.app is a module-level singleton the whole test suite shares, so swapping
its config mid-session would be fragile. The live check below instead confirms
the default (non-production) test environment leaves docs reachable, which is
the actual wiring that matters day to day.
"""
import main


def test_docs_disabled_in_production():
    assert main._docs_urls_for("production") == {
        "docs_url": None, "redoc_url": None, "openapi_url": None,
    }


def test_docs_enabled_outside_production():
    assert main._docs_urls_for("development") == {}
    assert main._docs_urls_for("staging") == {}
    assert main._docs_urls_for("") == {}


def test_docs_reachable_in_default_test_environment(client):
    # ENVIRONMENT isn't set to "production" anywhere in the test setup, so this
    # confirms the wiring — not just the decision function — leaves docs on.
    r = client.get("/docs")
    assert r.status_code == 200