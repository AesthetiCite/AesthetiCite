from __future__ import annotations
import os
import time as _time
import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from app.core.config import settings
from app.core.auth import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_refresh_token, get_current_user,
)
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenResponse, UserOut, AdminCreateUserRequest

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Brute-force lockout (in-memory; replace with Redis for multi-instance prod) ──
_FAILED_LOGINS: dict = {}
_MAX_ATTEMPTS  = 5
_LOCKOUT_BASE  = 30  # seconds — doubles each failure above max

def _check_lockout(email: str) -> None:
    record = _FAILED_LOGINS.get(email.lower())
    if record and _time.time() < record.get("locked_until", 0):
        wait = int(record["locked_until"] - _time.time())
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {wait} seconds.",
        )

def _record_failure(email: str) -> None:
    key = email.lower()
    record = _FAILED_LOGINS.get(key, {"count": 0, "locked_until": 0})
    record["count"] += 1
    if record["count"] >= _MAX_ATTEMPTS:
        extra = record["count"] - _MAX_ATTEMPTS
        record["locked_until"] = _time.time() + _LOCKOUT_BASE * (2 ** extra)
    _FAILED_LOGINS[key] = record

def _clear_failures(email: str) -> None:
    _FAILED_LOGINS.pop(email.lower(), None)

def require_admin_api_key(x_api_key: str = Header(default="")):
    if x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized (missing/invalid X-API-Key).")
    return True

@router.post("/register", response_model=UserOut)
def admin_register_user(
    payload: AdminCreateUserRequest,
    _: bool = Depends(require_admin_api_key),
    db: Session = Depends(get_db),
):
    pw_hash = hash_password(payload.password)
    try:
        row = db.execute(text("""
            INSERT INTO users (email, password_hash, role)
            VALUES (:email, :ph, :role)
            RETURNING id::text, email, is_active, role, created_at::text;
        """), {"email": payload.email.lower(), "ph": pw_hash, "role": payload.role}).mappings().first()
        db.commit()
        return dict(row)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="User already exists or invalid data")

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    _check_lockout(payload.email)

    row = db.execute(text("""
        SELECT id::text AS id, email, password_hash, is_active
        FROM users
        WHERE email = :email
    """), {"email": payload.email.lower()}).mappings().first()

    if not row or not row["is_active"]:
        _record_failure(payload.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(payload.password, row["password_hash"]):
        _record_failure(payload.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _clear_failures(payload.email)
    token = create_access_token(sub=row["id"])
    refresh = create_refresh_token(sub=row["id"])
    try:
        from app.api.session_tracker import record_session_start
        record_session_start(user_id=str(row["id"]), email=row["email"], session_token=token)
    except Exception:
        pass
    return {
        "access_token":  token,
        "refresh_token": refresh,
        "token_type":    "bearer",
        "expires_in":    settings.JWT_EXPIRES_MIN * 60,
    }


class _RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", summary="Exchange refresh token for new access token")
def refresh_access_token(payload: _RefreshRequest, db: Session = Depends(get_db)):
    sub = decode_refresh_token(payload.refresh_token)
    row = db.execute(
        text("SELECT id::text AS id, is_active FROM users WHERE id = :id"),
        {"id": sub},
    ).mappings().first()
    if not row or not row["is_active"]:
        raise HTTPException(status_code=401, detail="User not found or deactivated")
    return {
        "access_token":  create_access_token(sub),
        "refresh_token": create_refresh_token(sub),
        "token_type":    "bearer",
        "expires_in":    settings.JWT_EXPIRES_MIN * 60,
    }

@router.get("/me", response_model=UserOut)
def me(user=Depends(get_current_user)):
    return user


class AdminSetPasswordPayload(BaseModel):
    email: str
    new_password: str

def _effective_db_url() -> str:
    return (
        os.environ.get("NEON_DATABASE_URL")
        or os.environ.get("DATABASE_URL", "")
    )

@router.post("/admin/set-password")
def admin_set_password(
    payload: AdminSetPasswordPayload,
    _: bool = Depends(require_admin_api_key),
    db: Session = Depends(get_db),
):
    """Admin-only: reset any user's password. Updates in both auth DB and operational DB."""
    email = payload.email.lower().strip()
    pw_hash = hash_password(payload.new_password)
    updated_dbs = []

    row = db.execute(text("""
        UPDATE users SET password_hash = :ph
        WHERE email = :email
        RETURNING id::text, email, role, is_active
    """), {"ph": pw_hash, "email": email}).mappings().first()
    db.commit()

    if row:
        updated_dbs.append("auth_db")
    else:
        raise HTTPException(status_code=404, detail=f"User {email} not found in auth database")

    raw_url = os.environ.get("DATABASE_URL", "")
    if raw_url and raw_url != _effective_db_url():
        try:
            conn = psycopg2.connect(raw_url, connect_timeout=10)
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE email = %s RETURNING email",
                (pw_hash, email)
            )
            if cur.rowcount > 0:
                updated_dbs.append("operational_db")
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            pass

    return {
        "status": "ok",
        "email": row["email"],
        "role": row["role"],
        "updated_in": updated_dbs,
    }
