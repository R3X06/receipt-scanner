"""Tier 3 — auth endpoints (Gate 1 invariants), via TestClient + fake providers.

Covers the signup password/email policy, id-based tokens, /auth/me, rejection of
tampered tokens, the transparent bcrypt -> Argon2id rehash on login, email
verification, and forgot/reset password (including token_version session
invalidation on reset).
"""
from jose import jwt

import auth
import email_utils
import models


def _signup(client, email, password="demo1234"):
    return client.post("/auth/signup", json={"email": email, "password": password})


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def test_signup_accepts_demo_credentials(client):
    r = _signup(client, "demo@demo.com", "demo1234")
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()


def test_signup_rejects_short_password(client):
    r = _signup(client, "a@b.com", "1234567")        # 7 chars
    assert r.status_code == 422


def test_signup_rejects_long_password(client):
    r = _signup(client, "a@b.com", "x" * 129)
    assert r.status_code == 422


def test_signup_rejects_malformed_email(client):
    r = _signup(client, "not-an-email", "12345678")
    assert r.status_code == 422


def test_token_sub_is_user_id_not_email(client, db):
    token = _signup(client, "id@b.com").json()["access_token"]
    payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
    u = db.query(models.User).filter_by(email="id@b.com").first()
    assert payload["sub"] == u.id           # immutable id, not the email
    assert payload["sub"] != "id@b.com"


def test_me_returns_authenticated_user(client):
    token = _signup(client, "me@b.com").json()["access_token"]
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
# Email verification
# --------------------------------------------------------------------------

def test_signup_creates_unverified_user_and_sends_a_token(client, db, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        email_utils, "send_verification_email",
        lambda to, token: captured.update(to=to, token=token) or True,
    )
    r = _signup(client, "verify@b.com")
    assert r.status_code == 200

    u = db.query(models.User).filter_by(email="verify@b.com").first()
    assert u.email_verified is False
    assert captured["to"] == "verify@b.com"
    assert captured["token"]                              # a token was generated
    assert u.verification_token_hash == auth.hash_token(captured["token"])


def test_verify_email_with_valid_token_marks_verified(client, db, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        email_utils, "send_verification_email",
        lambda to, token: captured.update(token=token) or True,
    )
    _signup(client, "verify2@b.com")

    r = client.post("/auth/verify-email", json={"token": captured["token"]})
    assert r.status_code == 200

    u = db.query(models.User).filter_by(email="verify2@b.com").first()
    assert u.email_verified is True
    assert u.verification_token_hash is None              # single-use: cleared after success


def test_verify_email_with_bogus_token_rejected(client):
    r = client.post("/auth/verify-email", json={"token": "not-a-real-token"})
    assert r.status_code == 400


def test_resend_verification_requires_auth(client):
    r = client.post("/auth/resend-verification")
    assert r.status_code == 401


# --------------------------------------------------------------------------
# Forgot / reset password
# --------------------------------------------------------------------------

def test_forgot_password_returns_generic_response_for_unknown_email(client):
    r = client.post("/auth/forgot-password", json={"email": "nobody@b.com"})
    assert r.status_code == 200
    assert "if that email" in r.json()["detail"].lower()   # same message either way — no enumeration


def test_forgot_password_returns_same_generic_response_for_known_email(client, monkeypatch):
    monkeypatch.setattr(email_utils, "send_password_reset_email", lambda to, token: True)
    _signup(client, "forgot@b.com")
    r = client.post("/auth/forgot-password", json={"email": "forgot@b.com"})
    assert r.status_code == 200
    assert "if that email" in r.json()["detail"].lower()


def test_reset_password_with_valid_token_changes_password(client, db, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        email_utils, "send_password_reset_email",
        lambda to, token: captured.update(token=token) or True,
    )
    _signup(client, "reset@b.com", "oldpassword1")
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


def test_reset_password_invalidates_prior_tokens(client, monkeypatch):
    """A JWT minted before the reset must stop working immediately, even
    though it hasn't expired — otherwise a stolen token survives the reset
    the user took specifically to lock the attacker out."""
    old_token = _signup(client, "invalidate@b.com", "oldpassword1").json()["access_token"]

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