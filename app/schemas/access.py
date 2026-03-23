from pydantic import BaseModel, EmailStr, Field
from typing import Literal

Role = Literal["clinician", "student"]

class RequestAccess(BaseModel):
    full_name: str = Field(..., min_length=3, max_length=120)
    email: EmailStr
    practitioner_id: str = Field(..., min_length=3, max_length=60)  # for students: student/registration number
    role: Role = "clinician"

class SetPassword(BaseModel):
    token: str = Field(..., min_length=20, max_length=300)
    password: str = Field(..., min_length=8, max_length=200)
