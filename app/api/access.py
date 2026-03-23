from __future__ import annotations
import os
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import get_db
from app.schemas.access import RequestAccess, SetPassword
from app.core.emailer import send_email
from app.core.auth import hash_password

router = APIRouter(prefix="/auth", tags=["auth-access"])

def _public_url() -> str:
    url = os.getenv("APP_PUBLIC_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("APP_PUBLIC_URL is not set.")
    return url

def _looks_institutional(email: str) -> bool:
    """Simple OpenEvidence-like gate: avoid gmail/yahoo/hotmail, require org domain for students."""
    email = email.lower()
    bad = ("@gmail.", "@yahoo.", "@outlook.", "@hotmail.", "@live.", "@aol.")
    return not any(b in email for b in bad) and "." in email.split("@")[-1]

@router.post("/request-access")
def request_access(payload: RequestAccess, db: Session = Depends(get_db)):
    """
    Public:
    - Creates/updates a user with role clinician/student
    - Sends set-password link by email (valid 60 min)
    Conditions:
    - clinician: any professional email OK
    - student: MUST be institutional-like email (simple heuristic)
    """
    email = payload.email.lower().strip()
    full_name = payload.full_name.strip()
    pid = payload.practitioner_id.strip()
    role = payload.role

    if role == "student" and not _looks_institutional(email):
        raise HTTPException(
            status_code=400,
            detail="Students must use an institutional email address (university/hospital)."
        )

    temp_hash = hash_password("TEMP-" + secrets.token_urlsafe(16))

    db.execute(text("""
      INSERT INTO users (email, password_hash, role, is_active, full_name, practitioner_id)
      VALUES (:email, :ph, :role, true, :full_name, :pid)
      ON CONFLICT (email) DO UPDATE SET
        full_name=EXCLUDED.full_name,
        practitioner_id=EXCLUDED.practitioner_id,
        role=EXCLUDED.role,
        is_active=true;
    """), {
        "email": email,
        "ph": temp_hash,
        "role": role,
        "full_name": full_name,
        "pid": pid,
    })

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=60)

    db.execute(text("""
      INSERT INTO auth_access_requests (email, token, expires_at)
      VALUES (:email, :token, :exp);
    """), {"email": email, "token": token, "exp": expires_at})

    db.commit()

    link = f"{_public_url()}/set-password?token={token}"

    prefix = "Dr." if role == "clinician" else "Student"
    id_label = "Practitioner number" if role == "clinician" else "Student/registration number"
    subject = "AesthetiCite — Set your password"
    body = (
        f"Hello {prefix} {full_name},\n\n"
        f"Your AesthetiCite access request has been received.\n"
        f"{id_label}: {pid}\n\n"
        f"Set your password using this secure link (valid for 60 minutes):\n{link}\n\n"
        f"If you did not request access, you can ignore this email.\n\n"
        f"— AesthetiCite"
    )

    try:
        send_email(email, subject, body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email delivery failed: {e}")

    return {"ok": True, "message": "Check your email to set your password."}

@router.post("/set-password")
def set_password(payload: SetPassword, db: Session = Depends(get_db)):
    token = payload.token.strip()
    row = db.execute(text("""
      SELECT email, expires_at
      FROM auth_access_requests
      WHERE token = :token
    """), {"token": token}).mappings().first()

    if not row:
        raise HTTPException(status_code=400, detail="Invalid token.")
    if row["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token expired.")

    email = row["email"]
    pw_hash = hash_password(payload.password)

    db.execute(text("""
      UPDATE users
      SET password_hash = :ph, is_active = true
      WHERE email = :email;
    """), {"ph": pw_hash, "email": email})

    db.execute(text("DELETE FROM auth_access_requests WHERE token = :token;"), {"token": token})
    db.commit()

    return {"ok": True, "message": "Password set. You can now log in."}
