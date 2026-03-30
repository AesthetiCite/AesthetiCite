"""
security_patch_main.py
======================
Apply to: app/main.py

THREE changes in this file:
  CHANGE 1 — CORS fails-closed instead of fails-open
  CHANGE 2 — Security headers middleware (HSTS, CSP, X-Frame, etc.)
  CHANGE 3 — Lock metrics-lite endpoint behind admin auth
  CHANGE 4 — Create audit_log table on startup

═══════════════════════════════════════════════════════════════════
CHANGE 1 — CORS
Find this block (exact text):

    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

Replace with:

    _origins_raw = os.environ.get("CORS_ORIGINS", "").strip()
    if not _origins_raw:
        if os.environ.get("ENV", "dev").lower() == "production":
            raise RuntimeError(
                "CORS_ORIGINS must be set in production. "
                "Set it to your frontend domain e.g. https://aestheticite.com"
            )
        _origins = ["http://localhost:3000", "http://localhost:5173"]
    else:
        _origins = [o.strip() for o in _origins_raw.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key",
                       "X-Admin-Api-Key", "X-Partner-Session"],
    )

Also add at the top of main.py with the other imports:
    import os

(it may already be there — check first)

═══════════════════════════════════════════════════════════════════
CHANGE 2 — Security headers middleware

Add this ENTIRE block immediately after the CORS middleware block
and before the rate limiting lines:

    from fastapi import Request as _Request
    from starlette.middleware.base import BaseHTTPMiddleware

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: _Request, call_next):
            response = await call_next(request)
            # Prevent browsers caching clinical data
            if request.url.path.startswith("/api/"):
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
                response.headers["Pragma"]        = "no-cache"
            # Core security headers
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"]        = "DENY"
            response.headers["X-XSS-Protection"]       = "1; mode=block"
            response.headers["Referrer-Policy"]        = (
                "strict-origin-when-cross-origin"
            )
            response.headers["Permissions-Policy"]     = (
                "camera=(), microphone=(), geolocation=(), payment=()"
            )
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob: https:; "
                "font-src 'self' data:; "
                "connect-src 'self' https://api.openai.com "
                "https://*.neon.tech wss:; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self';"
            )
            return response

    app.add_middleware(SecurityHeadersMiddleware)

═══════════════════════════════════════════════════════════════════
CHANGE 3 — Lock metrics-lite behind admin auth

Find:
    @app.get("/metrics-lite")
    def metrics_lite():

Replace with:
    from app.core.auth import require_admin_user as _require_admin

    @app.get("/metrics-lite")
    def metrics_lite(_user=Depends(_require_admin)):

═══════════════════════════════════════════════════════════════════
CHANGE 4 — Create audit_log table on startup

Add this SQL to the DOC_META_MIGRATION_SQL string (paste at the end,
before the closing triple-quote):

    CREATE TABLE IF NOT EXISTS audit_log (
        id          BIGSERIAL PRIMARY KEY,
        logged_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        event_type  TEXT        NOT NULL,
        request_id  TEXT,
        user_id     TEXT,
        email       TEXT,
        ip_address  TEXT,
        path        TEXT,
        event_data  JSONB
    );
    CREATE INDEX IF NOT EXISTS idx_audit_user
        ON audit_log(user_id, logged_at DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_event
        ON audit_log(event_type, logged_at DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_time
        ON audit_log(logged_at DESC);

That's all four changes in main.py.
"""
