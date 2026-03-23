from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.core.auth import hash_password, verify_password, create_access_token, get_current_user
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenResponse, UserOut, AdminCreateUserRequest

router = APIRouter(prefix="/auth", tags=["auth"])

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
    row = db.execute(text("""
        SELECT id::text AS id, email, password_hash, is_active
        FROM users
        WHERE email = :email
    """), {"email": payload.email.lower()}).mappings().first()

    if not row or not row["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(sub=row["id"])
    return TokenResponse(access_token=token)

@router.get("/me", response_model=UserOut)
def me(user=Depends(get_current_user)):
    return user
