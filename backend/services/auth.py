import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

import jwt
from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models.models import Business, User

# Ensure .env is loaded
env_path = Path(__file__).resolve().parents[1] / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")

# Allow test secret only during automated pytest runs if unset
if not JWT_SECRET:
    if "PYTEST_CURRENT_TEST" in os.environ or os.getenv("TESTING") == "True":
        JWT_SECRET = "automated-test-secret-key-32-chars-long"
    else:
        raise ValueError("JWT_SECRET is missing from backend/.env. Please configure JWT_SECRET.")

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

security_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 100,000 iterations and random salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    return f"pbkdf2:sha256:100000${salt}${key.hex()}"


def verify_password(plain_password: str, stored_password: str) -> Tuple[bool, bool]:
    """
    Verify password. Returns (is_valid, needs_rehash).
    Handles both modern PBKDF2-SHA256 hashes and legacy plain-text accounts.
    """
    if not stored_password or not plain_password:
        return False, False

    if stored_password.startswith("pbkdf2:sha256:100000$"):
        parts = stored_password.split("$")
        if len(parts) == 3:
            salt = parts[1]
            expected_hash = parts[2]
            computed_key = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt.encode("utf-8"),
                100_000,
            )
            is_valid = hmac.compare_digest(computed_key.hex(), expected_hash)
            return is_valid, False

    # Legacy plain-text fallback (e.g. initial demo seed data)
    is_valid = hmac.compare_digest(plain_password, stored_password)
    # If legacy match, signal that caller should re-hash and save
    return is_valid, True


def create_access_token(user_id: int, email: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency to extract and verify the authenticated User."""
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(auth.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.scalar(select(User).where(User.id == int(user_id)))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_business(
    x_business_id: Optional[str] = Header(None, alias="X-Business-ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Business:
    """
    FastAPI dependency ensuring:
    1. An active business is identified.
    2. The business strictly belongs to current_user.
    3. Cross-tenant access is rejected with 403 Forbidden.
    """
    user_businesses = db.scalars(
        select(Business).where(Business.user_id == current_user.id)
    ).all()

    if not user_businesses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No businesses are associated with your account.",
        )

    if x_business_id:
        try:
            target_id = int(x_business_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Business-ID header.",
            )

        business = db.scalar(
            select(Business).where(
                Business.id == target_id,
                Business.user_id == current_user.id,
            )
        )
        if not business:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have access to this business.",
            )
        return business

    # Default to first business if not explicitly provided
    return user_businesses[0]
