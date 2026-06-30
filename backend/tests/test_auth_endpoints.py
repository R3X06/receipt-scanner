"""Tier 3 — auth endpoints (Gate 1 invariants), via TestClient + fake providers.

Covers the signup password/email policy, id-based tokens, /auth/me, rejection of
tampered tokens, and the transparent bcrypt -> Argon2id rehash on login.
"""
from jose import jwt

import auth
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