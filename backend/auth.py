from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
import models
import os

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


def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


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
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user