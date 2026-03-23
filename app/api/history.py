from __future__ import annotations
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from pydantic import BaseModel
from datetime import datetime

from app.core.config import settings
from app.db.session import get_db

router = APIRouter(prefix="/history", tags=["history"])


class HistoryItem(BaseModel):
    id: str
    question: str
    domain: str
    mode: str
    created_at: datetime
    citations_count: int
    refusal: bool


class HistoryResponse(BaseModel):
    items: List[HistoryItem]
    total: int


def get_current_user(request: Request, db: Session) -> dict:
    """Get current user from JWT token."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization bearer token")
    token = auth_header[7:]
    from app.core.auth import decode_token
    user_id = decode_token(token)
    row = db.execute(text("""
        SELECT id::text, email, is_active, role
        FROM users
        WHERE id = :id
    """), {"id": user_id}).mappings().first()
    if not row or not row["is_active"]:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return dict(row)


@router.get("", response_model=HistoryResponse)
def get_history(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    """Get query history for the current user."""
    user = get_current_user(request, db)
    user_id = user["id"]
    
    # Get total count
    total = db.execute(text("""
        SELECT COUNT(*) FROM queries WHERE user_id = :user_id
    """), {"user_id": user_id}).scalar_one()
    
    # Get paginated items
    rows = db.execute(text("""
        SELECT 
            id::text,
            question,
            domain,
            mode,
            created_at,
            citations_count,
            refusal
        FROM queries
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """), {"user_id": user_id, "limit": limit, "offset": offset}).mappings().all()
    
    items = [
        HistoryItem(
            id=row["id"],
            question=row["question"],
            domain=row["domain"] or "medicine",
            mode=row["mode"] or "clinic",
            created_at=row["created_at"],
            citations_count=row["citations_count"] or 0,
            refusal=row["refusal"] or False,
        )
        for row in rows
    ]
    
    return HistoryResponse(items=items, total=total)


@router.delete("/{query_id}")
def delete_history_item(
    query_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete a query from history."""
    user = get_current_user(request, db)
    user_id = user["id"]
    
    # Verify ownership
    row = db.execute(text("""
        SELECT user_id FROM queries WHERE id = :id
    """), {"id": query_id}).mappings().first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Query not found")
    if row["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Delete answer first (foreign key)
    db.execute(text("DELETE FROM answers WHERE query_id = :id"), {"id": query_id})
    db.execute(text("DELETE FROM queries WHERE id = :id"), {"id": query_id})
    db.commit()
    
    return {"ok": True}
