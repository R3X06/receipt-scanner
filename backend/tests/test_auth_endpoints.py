"""Tier 3 — auth endpoints (Gate 1 invariants), via TestClient + fake providers.

Covers signup's verification-gated flow (no account exists until the emailed
link is clicked), id-based tokens, /auth/me, rejection of tampered tokens, the
transparent bcrypt -> Argon2id rehash on login, and forgot/reset password
(including token_version session invalidation on reset) and account deletion.
"""
from jose import jwt

import auth
import email_utils
import models


def _signup(client, email, password="demo1234"):
    """Raw POST to /auth/signup — for tests that only care about the signup
    step itself (validation, rate limiting, the 'already registered' check).
    This does NOT create an account; use signup_and_verify for that."""
    return client.post("/auth/signup", json={"email": email, "password": password})


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------
# Signup — validation, and that it no longer creates an account by itself
# --------------------------------------------------------------------------

def test_signup_with_valid_credentials_returns_pending_detail(client):
    r = _signup(client, "demo@demo.com", "demo1234")
    assert r.status_code == 200, r.text
    assert "access_token" not in r.json()      # no account yet — verify-email creates it
    assert "detail" in r.json()


def test_signup_rejects_short_password(client):
    r = _signup(client, "a@b.com", "1234567")        # 7 chars
    assert r.status_code == 422


def test_signup_rejects_long_password(client):
    r = _signup(client, "a@b.com", "x" * 129)
    assert r.status_code == 422


def test_signup_rejects_malformed_email(client):
    r = _signup(client, "not-an-email", "12345678")
    assert r.status_code == 422


def test_signup_does_not_create_a_user_row(client, db):
    _signup(client, "pending@b.com")
    u = db.query(models.User).filter_by(email="pending@b.com").first()
    assert u is None                           # nothing written until verify-email


def test_signup_again_with_same_unverified_email_sends_a_fresh_token(client, monkeypatch):
    """No account exists yet, so there's nothing to conflict with — this is
    the 'resend' path: just resubmit signup with the same email."""
    tokens = []
    monkeypatch.setattr(
        email_utils, "send_verification_email",
        lambda to, token: tokens.append(token) or True,
    )
    r1 = _signup(client, "retry@b.com")
    r2 = _signup(client, "retry@b.com")
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(tokens) == 2
    assert tokens[0] != tokens[1]               # each signup mints its own token


def test_signup_rejects_email_already_registered_and_verified(client, signup_and_verify):
    signup_and_verify("taken@b.com")
    r = _signup(client, "taken@b.com")
    assert r.status_code == 400


# --------------------------------------------------------------------------
# Verify-email — this is the only place an account gets created
# --------------------------------------------------------------------------

def test_verify_email_creates_user_and_logs_in(client, db, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        email_utils, "send_verification_email",
        lambda to, token: captured.update(to=to, token=token) or True,
    )
    r = _signup(client, "verify@b.com")
    assert r.status_code == 200
    assert captured["to"] == "verify@b.com"
    assert captured["token"]

    r2 = client.post("/auth/verify-email", json={"token": captured["token"]})
    assert r2.status_code == 200, r2.text
    assert "access_token" in r2.json()          # verifying logs you straight in

    u = db.query(models.User).filter_by(email="verify@b.com").first()
    assert u is not None
    assert u.email_verified is True


def test_verify_email_creates_default_accounts_categories_and_goal(client, db, signup_and_verify):
    signup_and_verify("defaults@b.com")
    u = db.query(models.User).filter_by(email="defaults@b.com").first()
    assert db.query(models.Account).filter_by(user_id=u.id).count() == 2
    assert db.query(models.Category).filter_by(user_id=u.id).count() > 0
    assert db.query(models.Goal).filter_by(user_id=u.id, is_emergency=True).count() == 1


def test_verify_email_with_bogus_token_rejected(client):
    r = client.post("/auth/verify-email", json={"token": "not-a-real-token"})
    assert r.status_code == 400


def test_verify_email_rejects_a_login_token_used_as_a_signup_token(client, signup_and_verify):
    """A session token has no 'purpose': 'signup' claim, so it must not be
    accepted here even though it's validly signed with the same secret."""
    login_token = signup_and_verify("notasignuptoken@b.com")
    r = client.post("/auth/verify-email", json={"token": login_token})
    assert r.status_code == 400


def test_double_click_verify_is_idempotent(client, db, monkeypatch):
    """Clicking the same link twice (or an older resent link after a newer
    one already completed signup) must not error or create a second account —
    it just logs into the one that already exists."""
    captured = {}
    monkeypatch.setattr(
        email_utils, "send_verification_email",
        lambda to, token: captured.update(token=token) or True,
    )
    _signup(client, "twice@b.com")

    r1 = client.post("/auth/verify-email", json={"token": captured["token"]})
    r2 = client.post("/auth/verify-email", json={"token": captured["token"]})
    assert r1.status_code == 200 and r2.status_code == 200

    count = db.query(models.User).filter_by(email="twice@b.com").count()
    assert count == 1                           # not duplicated


def test_resend_verification_endpoint_no_longer_exists(client):
    """Removed: there's no account to be logged into pre-verification, so
    'resend' is just resubmitting /auth/signup with the same email."""
    r = client.post("/auth/resend-verification")
    assert r.status_code == 404


# --------------------------------------------------------------------------
# Tokens / session basics
# --------------------------------------------------------------------------

def test_token_sub_is_user_id_not_email(client, db, signup_and_verify):
    token = signup_and_verify("id@b.com")
    payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
    u = db.query(models.User).filter_by(email="id@b.com").first()
    assert payload["sub"] == u.id           # immutable id, not the email
    assert payload["sub"] != "id@b.com"


def test_me_returns_authenticated_user(client, signup_and_verify):
    token = signup_and_verify("me@b.com")
    r = client.get("/auth/me", headers=_hdr(token))
    assert r.status_code == 200
    assert r.json()["email"] == "me@b.com"


def test_tampered_token_is_rejected(client):
    r = client.get("/auth/me", headers=_hdr("not.a.valid.token"))
    assert r.status_code == 401


def test_legacy_bcrypt_hash_is_rehashed_to_argon2_on_login(client, db):
    from passlib.context import CryptContext
    legacy = CryptContext(schemes=["bcrypt"]).hash("demo1234")
    u = models.User(email="legacy@b.com", hashed_password=legacy, primary_currency="SGD")
    db.add(u)
    db.commit()
    assert u.hashed_password.startswith("$2")          # bcrypt before login

    r = client.post("/auth/login", json={"email": "legacy@b.com", "password": "demo1234"})
    assert r.status_code == 200, r.text

    db.refresh(u)
    assert u.hashed_password.startswith("$argon2id$")   # upgraded silently


# --------------------------------------------------------------------------
# Forgot / reset password
# --------------------------------------------------------------------------

def test_forgot_password_returns_generic_response_for_unknown_email(client):
    r = client.post("/auth/forgot-password", json={"email": "nobody@b.com"})
    assert r.status_code == 200
    assert "if that email" in r.json()["detail"].lower()   # same message either way — no enumeration


def test_forgot_password_returns_same_generic_response_for_known_email(client, signup_and_verify, monkeypatch):
    monkeypatch.setattr(email_utils, "send_password_reset_email", lambda to, token: True)
    signup_and_verify("forgot@b.com")
    r = client.post("/auth/forgot-password", json={"email": "forgot@b.com"})
    assert r.status_code == 200
    assert "if that email" in r.json()["detail"].lower()


def test_reset_password_with_valid_token_changes_password(client, db, signup_and_verify, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        email_utils, "send_password_reset_email",
        lambda to, token: captured.update(token=token) or True,
    )
    signup_and_verify("reset@b.com", "oldpassword1")
    client.post("/auth/forgot-password", json={"email": "reset@b.com"})

    r = client.post("/auth/reset-password",
                    json={"token": captured["token"], "new_password": "newpassword1"})
    assert r.status_code == 200

    r2 = client.post("/auth/login", json={"email": "reset@b.com", "password": "newpassword1"})
    assert r2.status_code == 200
    r3 = client.post("/auth/login", json={"email": "reset@b.com", "password": "oldpassword1"})
    assert r3.status_code == 401


def test_reset_password_with_bogus_token_rejected(client):
    r = client.post("/auth/reset-password",
                    json={"token": "not-a-real-token", "new_password": "whatever123"})
    assert r.status_code == 400


def test_reset_password_invalidates_prior_tokens(client, signup_and_verify, monkeypatch):
    """A JWT minted before the reset must stop working immediately, even
    though it hasn't expired — otherwise a stolen token survives the reset
    the user took specifically to lock the attacker out."""
    old_token = signup_and_verify("invalidate@b.com", "oldpassword1")

    captured = {}
    monkeypatch.setattr(
        email_utils, "send_password_reset_email",
        lambda to, token: captured.update(token=token) or True,
    )
    client.post("/auth/forgot-password", json={"email": "invalidate@b.com"})
    client.post("/auth/reset-password",
               json={"token": captured["token"], "new_password": "newpassword1"})

    r = client.get("/auth/me", headers=_hdr(old_token))
    assert r.status_code == 401                            # old session is dead


# --------------------------------------------------------------------------
# Account deletion
# --------------------------------------------------------------------------

def test_delete_account_requires_auth(client):
    r = client.request("DELETE", "/auth/me", json={"password": "whatever1"})
    assert r.status_code == 401


def test_delete_account_rejects_wrong_password(client, signup_and_verify):
    token = signup_and_verify("delwrong@b.com", "correctpassword1")
    r = client.request("DELETE", "/auth/me", json={"password": "wrongpassword"}, headers=_hdr(token))
    assert r.status_code == 401


def test_delete_account_removes_user_and_all_owned_data(client, db, signup_and_verify):
    token = signup_and_verify("delme@b.com", "correctpassword1")
    u = db.query(models.User).filter_by(email="delme@b.com").first()
    uid = u.id

    r = client.request("DELETE", "/auth/me", json={"password": "correctpassword1"}, headers=_hdr(token))
    assert r.status_code == 200, r.text

    assert db.query(models.User).filter_by(id=uid).first() is None
    assert db.query(models.Account).filter_by(user_id=uid).count() == 0
    assert db.query(models.Category).filter_by(user_id=uid).count() == 0
    assert db.query(models.Goal).filter_by(user_id=uid).count() == 0


def test_deleted_account_token_no_longer_works(client, signup_and_verify):
    token = signup_and_verify("delgone@b.com", "correctpassword1")
    client.request("DELETE", "/auth/me", json={"password": "correctpassword1"}, headers=_hdr(token))
    r = client.get("/auth/me", headers=_hdr(token))
    assert r.status_code == 401


def test_deleted_account_email_can_sign_up_again(client, db, signup_and_verify):
    """Confirms the delete actually freed the unique-email constraint, not
    just hid the row somehow."""
    token = signup_and_verify("reuse@b.com", "correctpassword1")
    client.request("DELETE", "/auth/me", json={"password": "correctpassword1"}, headers=_hdr(token))

    r = _signup(client, "reuse@b.com", "differentpassword1")
    assert r.status_code == 200, r.text
