"""
Fix 5 — Rate limiting on vision endpoints
==========================================
gpt-4o with detail='high' is the most expensive call on the platform
(~$0.01–0.03 per image). Without rate limiting, a misconfigured client
or single user can generate hundreds of calls.

INTEGRATION:
1. This file shows the exact decorators to add to vision_analysis.py.
2. slowapi is already configured in main.py — no new dependencies needed.
3. Copy the limiter import and decorator lines into vision_analysis.py.

The rate limits applied:
  /api/vision/analyse        — 10 per minute per user (expensive gpt-4o call)
  /api/vision/serial-compare — 5 per minute per user (two images = 2x cost)
  /api/visual/differential   — 10 per minute per user
  All other vision endpoints — 30 per minute (cheap)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

# ─────────────────────────────────────────────────────────────────
# Limiter setup
# The limiter instance is already created in main.py.
# Import it here rather than creating a new one.
#
# In main.py you already have:
#   from slowapi import Limiter
#   from slowapi.util import get_remote_address
#   limiter = Limiter(key_func=get_remote_address)
#   app.state.limiter = limiter
#
# Import that same instance:
#   from app.main import limiter
# ─────────────────────────────────────────────────────────────────

# If you cannot import from main.py, create a shared limiter module:
# app/api/rate_limiter.py:
#   from slowapi import Limiter
#   from slowapi.util import get_remote_address
#   limiter = Limiter(key_func=get_remote_address)
# Then import it everywhere:
#   from app.api.rate_limiter import limiter

# ─────────────────────────────────────────────────────────────────
# PATCH for vision_analysis.py
# Add these decorators to the existing endpoint functions.
#
# BEFORE (in vision_analysis.py):
#
#   @router.post("/analyse", response_model=VisionAnalysisResponse)
#   def vision_analyse(req: VisionAnalysisRequest) -> VisionAnalysisResponse:
#       ...
#
# AFTER:
#
#   from app.main import limiter   # or from app.api.rate_limiter import limiter
#
#   @router.post("/analyse", response_model=VisionAnalysisResponse)
#   @limiter.limit("10/minute")
#   def vision_analyse(request: Request, req: VisionAnalysisRequest) -> VisionAnalysisResponse:
#       # Note: FastAPI requires 'request: Request' as first param when using slowapi
#       ...
#
# BEFORE (serial-compare):
#
#   @router.post("/serial-compare", response_model=SerialCompareResult)
#   def serial_compare(req: SerialCompareRequest) -> SerialCompareResult:
#       ...
#
# AFTER:
#
#   @router.post("/serial-compare", response_model=SerialCompareResult)
#   @limiter.limit("5/minute")
#   def serial_compare(request: Request, req: SerialCompareRequest) -> SerialCompareResult:
#       ...
# ─────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────
# PATCH for visual_differential.py
#
# BEFORE:
#   @router.post("/differential", response_model=DifferentialResponse)
#   def visual_differential(req: DifferentialRequest) -> DifferentialResponse:
#
# AFTER:
#   @router.post("/differential", response_model=DifferentialResponse)
#   @limiter.limit("10/minute")
#   def visual_differential(request: Request, req: DifferentialRequest) -> DifferentialResponse:
# ─────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────
# Per-user rate limiting (instead of per-IP)
# If you have JWT auth, use user_id instead of IP for fairer limits.
# ─────────────────────────────────────────────────────────────────

def get_user_id_or_ip(request: Request) -> str:
    """
    Rate limit key function — uses authenticated user ID if available,
    falls back to IP address.

    Usage:
        limiter = Limiter(key_func=get_user_id_or_ip)
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            import jwt
            secret = __import__("os").environ.get("JWT_SECRET", "")
            payload = jwt.decode(token, secret, algorithms=["HS256"])
            user_id = payload.get("sub") or payload.get("user_id")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass
    return get_remote_address(request)


# ─────────────────────────────────────────────────────────────────
# Cost tracking middleware
# Logs vision endpoint usage for cost monitoring.
# Add to main.py as a middleware.
# ─────────────────────────────────────────────────────────────────

import time
import logging

cost_logger = logging.getLogger("aestheticite.cost")

VISION_ENDPOINT_COSTS = {
    "/api/vision/analyse":        0.025,  # gpt-4o high detail, ~$0.025 avg
    "/api/vision/serial-compare": 0.040,  # two images
    "/api/visual/differential":   0.020,  # gpt-4o high detail
}


async def vision_cost_middleware(request: Request, call_next):
    """
    FastAPI middleware that logs estimated cost for vision endpoints.

    Add to main.py:
        from fix5_rate_limiting import vision_cost_middleware
        app.middleware("http")(vision_cost_middleware)

    Or using the decorator form:
        @app.middleware("http")
        async def cost_tracking(request: Request, call_next):
            return await vision_cost_middleware(request, call_next)
    """
    path = request.url.path
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start

    if path in VISION_ENDPOINT_COSTS and response.status_code == 200:
        est_cost = VISION_ENDPOINT_COSTS[path]
        client_ip = request.client.host if request.client else "unknown"
        cost_logger.info(
            f"VISION_CALL path={path} status={response.status_code} "
            f"elapsed={elapsed:.2f}s est_cost=${est_cost:.3f} client={client_ip}"
        )

    return response


# ─────────────────────────────────────────────────────────────────
# Rate limit exceeded handler
# Already configured in main.py via _rate_limit_exceeded_handler.
# Shown here for reference — no change needed.
# ─────────────────────────────────────────────────────────────────

from fastapi import Request as FastAPIRequest
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded


def vision_rate_limit_handler(request: FastAPIRequest, exc: RateLimitExceeded):
    """
    Custom 429 response for vision rate limit.
    The existing _rate_limit_exceeded_handler in main.py already handles this.
    This version adds a Retry-After header.
    """
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Vision analysis rate limit exceeded. "
                      "Maximum 10 analyses per minute. Please wait before retrying.",
            "retry_after_seconds": 60,
        },
        headers={"Retry-After": "60"},
    )


# ─────────────────────────────────────────────────────────────────
# Summary of all changes needed in vision_analysis.py
# ─────────────────────────────────────────────────────────────────

INTEGRATION_INSTRUCTIONS = """
Changes needed in app/api/vision_analysis.py:

1. Add import at top:
   from fastapi import Request
   from app.main import limiter  # reuse existing limiter

2. Add request: Request as first param + @limiter.limit decorator:

   @router.post("/analyse", response_model=VisionAnalysisResponse)
   @limiter.limit("10/minute")
   def vision_analyse(request: Request, req: VisionAnalysisRequest):
       ...

   @router.post("/serial-compare", response_model=SerialCompareResult)
   @limiter.limit("5/minute")
   def serial_compare(request: Request, req: SerialCompareRequest):
       ...

   @router.get("/feature-glossary")
   @limiter.limit("30/minute")
   def feature_glossary(request: Request):
       ...

Changes needed in app/api/visual_differential.py:

   @router.post("/differential", response_model=DifferentialResponse)
   @limiter.limit("10/minute")
   def visual_differential(request: Request, req: DifferentialRequest):
       ...

That's it. The existing slowapi setup in main.py handles everything else.
"""

if __name__ == "__main__":
    print(INTEGRATION_INSTRUCTIONS)
