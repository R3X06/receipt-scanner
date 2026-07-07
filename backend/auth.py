import hashlib
import secrets
import sys
from datetime import timedelta
from clock import utcnow
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from database import get_db
import models
import os

# ---------------------------------------------------------------------------
# Rate limiting — in-memory (single Railway instance; no Redis needed at this
# scale). Disabled under pytest: the endpoint test suite calls /auth/login and
# /auth/signup dozens of times per run and would otherwise start failing on
# 429s partway through, unrelated to what each test is actually checking.
# ---------------------------------------------------------------------------
TESTING = "pytest" in sys.modules
limiter = Limiter(key_func=get_remote_address, enabled=not TESTING)

# ---------------------------------------------------------------------------
# JWT signing secret — environment-aware hard-fail (Gate 1, Decision 1.3)
#   * production: refuse to start if the secret is missing or left at default
#   * development: fall back to a clearly-labelled insecure secret, warn loudly
# ---------------------------------------------------------------------------
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
_DEFAULT_SECRET = "changethisinproduction"
_DEV_FALLBACK_SECRET = "dev-only-insecure-secret-do-not-use-in-prod"

SECRET_KEY = os.getenv("JWT_SECRET")

if ENVIRONMENT == "production":
    if not SECRET_KEY or SECRET_KEY == _DEFAULT_SECRET:
        raise RuntimeError(
            "JWT_SECRET is missing or set to the insecure default while "
            "ENVIRONMENT=production. Refusing to start. Set a strong, unique "
            "JWT_SECRET in the production environment."
        )
else:
    if not SECRET_KEY or SECRET_KEY == _DEFAULT_SECRET:
        SECRET_KEY = _DEV_FALLBACK_SECRET
        print(
            "[auth] WARNING: JWT_SECRET not set (or left at default) — using an "
            "insecure development fallback. Fine locally; NEVER in production."
        )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week
SIGNUP_TOKEN_EXPIRE_MINUTES = 60 * 24      # 24h — matches the old verification-link expiry

# ---------------------------------------------------------------------------
# Password hashing — Argon2id primary; bcrypt retained only to verify legacy
# hashes and trigger transparent rehash-on-login (Gate 1, Decision 1.1).
# Argon2id params follow the OWASP baseline: 19 MiB memory, 2 iterations, p=1.
# ---------------------------------------------------------------------------
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",
    argon2__memory_cost=19456,   # 19 MiB
    argon2__time_cost=2,
    argon2__parallelism=1,
)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str):
    return pwd_context.verify(plain, hashed)


def needs_rehash(hashed: str) -> bool:
    """True when the stored hash uses a deprecated scheme/params (e.g. legacy
    bcrypt), signalling it should be re-hashed with Argon2id on next login."""
    return pwd_context.needs_update(hashed)


def generate_token() -> str:
    """A single-use, unguessable token for email verification / password reset
    links. 32 bytes of URL-safe randomness — not a password, no need for a
    slow hash, but never stored raw (see hash_token)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 of a verification/reset token, for at-rest storage. A fast hash
    is correct here (unlike passwords): the token already has 256 bits of
    entropy, so there's nothing for an attacker to brute-force even against a
    stolen DB row — the threat model is DB leakage, not offline guessing."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_token(data: dict, expire_minutes: int | None = None):
    to_encode = data.copy()
    minutes = expire_minutes if expire_minutes is not None else ACCESS_TOKEN_EXPIRE_MINUTES
    expire = utcnow() + timedelta(minutes=minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


class InvalidSignupToken(Exception):
    """Raised for a signup-verification token that's malformed, expired, or
    not actually a signup token (e.g. someone passing a session or
    password-reset token to /auth/verify-email)."""


def decode_signup_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise InvalidSignupToken("invalid or expired")
    if payload.get("purpose") != "signup" or not payload.get("email") or not payload.get("pwd_hash"):
        raise InvalidSignupToken("wrong token type")
    return payload


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # Gate 1, Decision 1.4: identity is keyed on the immutable user.id
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_version = payload.get("ver", 0)
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_exception
    # A password reset bumps token_version, so a JWT minted before the reset
    # stops verifying immediately instead of staying valid until it expires
    # (up to a week away) — closes the "stolen token survives a reset" gap.
    if (user.token_version or 0) != token_version:
        raise credentials_exception
    return user


def get_owned(db: Session, model, obj_id: str, user: models.User):
    """The single ownership accessor (design lock §3.5, Property K).

    Every lookup is filtered by user_id, so this structurally cannot return
    another user's row — there is no code path that returns a record the caller
    doesn't own. Raises 404 (not 403) so the existence of another user's record
    is never revealed. Use this for every per-user fetch (import batches /
    candidates, and anything else) instead of re-deriving the filter at each
    call site, which is how the original mutation-ownership gap arose.
    """
    obj = (
        db.query(model)
        .filter(model.id == obj_id, model.user_id == user.id)
        .first()
    )
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{model.__name__} not found",
        )
    return obj