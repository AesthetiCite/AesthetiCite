from fastapi import Header, HTTPException
from app.core.config import settings

def require_admin(x_api_key: str = Header(default="")):
    if x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized (missing/invalid X-API-Key).")
    return True
