from app.core.config import settings

def validate_env():
    """Validate critical environment variables. Strict in production."""
    if settings.ENV.lower() in ("prod", "production"):
        if not settings.JWT_SECRET or len(settings.JWT_SECRET) < 16:
            raise RuntimeError("JWT_SECRET is missing or too short. Set a strong secret in environment variables.")
        if not settings.ADMIN_API_KEY or len(settings.ADMIN_API_KEY) < 8:
            raise RuntimeError("ADMIN_API_KEY is missing or too short. Set it in environment variables.")
