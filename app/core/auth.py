from __future__ import annotations
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.db.session import get_db

bearer = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    password_bytes = password.encode('utf-8')
    hash_bytes = password_hash.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hash_bytes)

def create_access_token(sub: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.JWT_EXPIRES_MIN)
    payload = {"sub": sub, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

def create_refresh_token(sub: str) -> str:
    """Long-lived refresh token (30 days). Used only to mint new access tokens."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=30)
    payload = {
        "sub":  sub,
        "type": "refresh",
        "iat":  int(now.timestamp()),
        "exp":  int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

def decode_refresh_token(token: str) -> str:
    """Validates a refresh token and returns the user sub (id)."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token is not a refresh token")
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Missing sub in token")
        return sub
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        sub = payload.get("sub")
        if not sub:
            raise InvalidTokenError("Missing sub")
        return sub
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
):
    if creds is None:
        raise HTTPException(status_code=401, detail="Missing Authorization bearer token")
    user_id = decode_token(creds.credentials)
    row = db.execute(text("""
        SELECT id::text, email, is_active, role, created_at::text, full_name, practitioner_id
        FROM users
        WHERE id = :id
    """), {"id": user_id}).mappings().first()
    if not row or not row["is_active"]:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return dict(row)

def require_admin_user(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
