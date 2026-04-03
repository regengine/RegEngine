from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from passlib.context import CryptContext
import os
import secrets
import logging

_logger = logging.getLogger("auth_utils")

# ──────────────────────────────────────────────────────────────
# JWT Secret Key — MUST be set in production.
# In development, falls back to a random key (sessions won't
# survive restarts, which is acceptable for local dev).
# ──────────────────────────────────────────────────────────────
_env_secret = os.getenv("AUTH_SECRET_KEY")
if not _env_secret:
    _is_production = os.getenv("REGENGINE_ENV", "").lower() == "production"
    if _is_production:
        raise RuntimeError(
            "AUTH_SECRET_KEY must be set in production. "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
        )
    _env_secret = secrets.token_urlsafe(32)
    _logger.warning(
        "AUTH_SECRET_KEY not set — using ephemeral key. "
        "Sessions will NOT survive restarts. Set AUTH_SECRET_KEY for persistence."
    )

SECRET_KEY = _env_secret
ALGORITHM = "HS256"

# Session timeout configuration (configurable via env vars)
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
SESSION_IDLE_TIMEOUT_MINUTES = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "60"))

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token() -> str:
    # Opaque token for database storage
    return secrets.token_urlsafe(64)

def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

def hash_token(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()

