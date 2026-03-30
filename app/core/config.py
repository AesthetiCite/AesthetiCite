import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "AesthetiCite"
    ENV: str = "dev"

    DATABASE_URL: str = (
        os.getenv("NEON_DATABASE_URL")
        or os.getenv("DATABASE_URL", "postgresql+psycopg://localhost/evidentia")
    )

    # On Replit: set by the AI integration (AI_INTEGRATIONS_OPENAI_API_KEY).
    # On Railway / any other host: set OPENAI_API_KEY instead.
    OPENAI_API_KEY: str = (
        os.getenv("AI_INTEGRATIONS_OPENAI_API_KEY")
        or os.getenv("OPENAI_API_KEY", "")
    )
    OPENAI_BASE_URL: str = (
        os.getenv("AI_INTEGRATIONS_OPENAI_BASE_URL")
        or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )

    # Operational limits
    MAX_CONTEXT_CHARS: int = 12000
    MIN_CITATIONS_REQUIRED: int = 2  # Require at least 2 sources to reduce hallucination risk

    # Admin
    ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "")
    UPLOAD_DIR: str = "data/uploads"

    # Rate limiting (slowapi syntax)
    RATE_LIMIT_ASK: str = "60/minute"
    RATE_LIMIT_INGEST: str = "10/hour"

    # LLM synthesis (OpenEvidence-like RAG)
    LLM_PROVIDER: str = "openai"  # "openai" | "mistral" | "none"
    OPENAI_MODEL: str = "gpt-4o-mini"
    MISTRAL_MODEL: str = "mistral-small-latest"

    # Answer quality
    MAX_SOURCES_IN_PROMPT: int = 8
    MAX_CHARS_PER_SOURCE: int = 900
    LLM_TEMPERATURE: float = 0.1  # Low temperature for deterministic, less hallucinatory responses

    # RAG
    EMBEDDING_DIM: int = 384
    CHUNK_SIZE_CHARS: int = 1200
    CHUNK_OVERLAP_CHARS: int = 200

    # Retrieval tuning (hybrid)
    RETRIEVE_K_VECTOR: int = 24
    RETRIEVE_K_KEYWORD: int = 24
    RERANK_TOP_N: int = 18

    # Prefer recent evidence when available
    MIN_YEAR_PREFERRED: int = 2014

    # Evidence-type preference (buyer-grade)
    PREFERRED_DOC_TYPES: str = "guideline,consensus,ifu,review,prescribing_information"

    # Auth
    REQUIRE_AUTH_FOR_ASK: bool = True
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALG: str = "HS256"
    JWT_EXPIRES_MIN: int = 60 * 24 * 7  # 7 days

    # CORS (set to your frontend URL(s))
    # Falls back to APP_PUBLIC_URL when CORS_ORIGINS is not explicitly set,
    # always adds localhost for development convenience.
    APP_PUBLIC_URL: str = os.getenv("APP_PUBLIC_URL", "")

    @property
    def cors_origins_list(self) -> list[str]:
        base = os.getenv("CORS_ORIGINS", "")
        origins: list[str] = [o.strip() for o in base.split(",") if o.strip()]
        if not origins:
            if self.APP_PUBLIC_URL:
                origins.append(self.APP_PUBLIC_URL.rstrip("/"))
            origins.append("http://localhost:5000")
            origins.append("http://localhost:3000")
        return origins

    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "")


settings = Settings()
