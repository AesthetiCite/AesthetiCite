import os
from typing import Optional

# ── Canonical DB URL resolution ─────────────────────────────────────────────
_CANONICAL_URL: str = (
    os.environ.get("NEON_DATABASE_URL")
    or os.environ.get("DATABASE_URL", "postgresql://localhost/evidentia")
)

_sync_url = _CANONICAL_URL
if _sync_url.startswith("postgresql://"):
    _sync_url = _sync_url.replace("postgresql://", "postgresql+psycopg://", 1)

_async_url = _CANONICAL_URL
if _async_url.startswith("postgresql://"):
    _async_url = _async_url.replace("postgresql://", "postgresql+psycopg://", 1)

# ── Lazy singletons — engines created on first access, not at import time ───
# This prevents import-time deadlocks caused by SQLAlchemy's asyncio engine
# spawning background threads (which can hold Python's import lock) during the
# FastAPI startup event, when the main thread is still importing other modules.

_engine = None
_SessionLocal = None
_async_engine = None
_AsyncSessionLocal = None


def _get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        _engine = create_engine(
            _sync_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10},
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def _get_async_engine():
    global _async_engine, _AsyncSessionLocal
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        _async_engine = create_async_engine(
            _async_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _AsyncSessionLocal = async_sessionmaker(
            bind=_async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_engine


# ── Public accessors — backward-compatible with all existing callers ─────────

class _LazyEngine:
    """Proxy that initialises the sync SQLAlchemy engine on first attribute access."""
    def __getattr__(self, name):
        return getattr(_get_engine(), name)

    def __repr__(self):
        return repr(_get_engine())


class _LazySessionFactory:
    """Proxy that initialises SessionLocal on first call / attribute access."""
    def __call__(self, *a, **kw):
        _get_engine()
        return _SessionLocal(*a, **kw)

    def __getattr__(self, name):
        _get_engine()
        return getattr(_SessionLocal, name)


class _LazyAsyncEngine:
    def __getattr__(self, name):
        return getattr(_get_async_engine(), name)

    def __repr__(self):
        return repr(_get_async_engine())


class _LazyAsyncSessionFactory:
    def __call__(self, *a, **kw):
        _get_async_engine()
        return _AsyncSessionLocal(*a, **kw)

    def __getattr__(self, name):
        _get_async_engine()
        return getattr(_AsyncSessionLocal, name)


engine = _LazyEngine()
SessionLocal = _LazySessionFactory()
async_engine = _LazyAsyncEngine()
AsyncSessionLocal = _LazyAsyncSessionFactory()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db():
    _get_async_engine()
    async with _AsyncSessionLocal() as session:
        yield session
