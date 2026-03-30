from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None


class UserOut(BaseModel):
    id: str
    email: EmailStr
    is_active: bool
    role: str
    created_at: Optional[str] = None
    full_name: Optional[str] = None
    practitioner_id: Optional[str] = None


class AdminCreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=200)
    role: str = "clinician"
