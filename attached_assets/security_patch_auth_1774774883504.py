"""
security_patch_auth.py
======================
Apply to: app/core/auth.py  AND  app/api/auth.py (or wherever the login
endpoint and token creation live)

TWO changes:
  CHANGE 1 — Add create_refresh_token() and decode_refresh_token()
              to app/core/auth.py
  CHANGE 2 — Add /auth/refresh endpoint + update login to return both tokens
  CHANGE 3 — Brute-force protection on login

═══════════════════════════════════════════════════════════════════
CHANGE 1 — app/core/auth.py

Add these two functions immediately after create_access_token():

    def create_refresh_token(sub: str) -> str:
        \"\"\"Long-lived refresh token (30 days). Used only to mint new access tokens.\"\"\"
        now = datetime.now(timezone.utc)
        exp = now + timedelta(days=30)
        payload = {
            "sub":  sub,
            "type": "refresh",
            "iat":  int(now.timestamp()),
            "exp":  int(exp.timestamp()),
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


    def decode_refresh_token(token: str) -> str:
        \"\"\"Validates a refresh token and returns the user sub (id).\"\"\"
        try:
            payload = jwt.decode(
                token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG]
            )
            if payload.get("type") != "refresh":
                raise HTTPException(
                    status_code=401, detail="Token is not a refresh token"
                )
            sub = payload.get("sub")
            if not sub:
                raise HTTPException(status_code=401, detail="Missing sub in token")
            return sub
        except JWTError:
            raise HTTPException(
                status_code=401, detail="Invalid or expired refresh token"
            )


═══════════════════════════════════════════════════════════════════
CHANGE 2 — app/api/auth.py (or wherever the login endpoint lives)

Step A: Add this import at the top of the file:
    from app.core.auth import (
        create_access_token, create_refresh_token,
        decode_refresh_token, verify_password,
        require_admin_user,
    )
    from pydantic import BaseModel as _BaseModel

Step B: Find the login endpoint's return statement. It currently returns
        something like:
    return {"access_token": token, "token_type": "bearer"}

Replace with:
    return {
        "access_token":  create_access_token(str(row["id"])),
        "refresh_token": create_refresh_token(str(row["id"])),
        "token_type":    "bearer",
        "expires_in":    settings.JWT_EXPIRES_MIN * 60,
    }

Step C: Add this new endpoint anywhere in the auth router:

    class _RefreshRequest(_BaseModel):
        refresh_token: str

    @router.post("/auth/refresh", summary="Exchange refresh token for new access token")
    def refresh_access_token(payload: _RefreshRequest, db: Session = Depends(get_db)):
        sub = decode_refresh_token(payload.refresh_token)
        # Verify user still exists and is active
        row = db.execute(
            text("SELECT id, is_active FROM users WHERE id = :id"),
            {"id": sub},
        ).mappings().first()
        if not row or not row["is_active"]:
            raise HTTPException(
                status_code=401, detail="User not found or deactivated"
            )
        return {
            "access_token":  create_access_token(sub),
            "refresh_token": create_refresh_token(sub),  # rotate refresh token too
            "token_type":    "bearer",
            "expires_in":    settings.JWT_EXPIRES_MIN * 60,
        }


═══════════════════════════════════════════════════════════════════
CHANGE 3 — Brute-force protection on login

Add this import at the top of auth.py:
    import time as _time

Add this in-memory lockout tracker (replace with Redis for production):
    _FAILED_LOGINS: dict = {}  # {email: {"count": N, "locked_until": float}}
    _MAX_ATTEMPTS  = 5
    _LOCKOUT_BASE  = 30  # seconds — doubles each failure after max

    def _check_lockout(email: str) -> None:
        record = _FAILED_LOGINS.get(email.lower())
        if record and _time.time() < record.get("locked_until", 0):
            wait = int(record["locked_until"] - _time.time())
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed attempts. Try again in {wait} seconds.",
            )

    def _record_failure(email: str) -> None:
        key = email.lower()
        record = _FAILED_LOGINS.get(key, {"count": 0, "locked_until": 0})
        record["count"] += 1
        if record["count"] >= _MAX_ATTEMPTS:
            # Progressive lockout: 30s, 60s, 120s, 240s...
            extra = record["count"] - _MAX_ATTEMPTS
            record["locked_until"] = _time.time() + _LOCKOUT_BASE * (2 ** extra)
        _FAILED_LOGINS[key] = record

    def _clear_failures(email: str) -> None:
        _FAILED_LOGINS.pop(email.lower(), None)

Then inside the login endpoint, add calls in the right places:

    @router.post("/auth/login")
    def login(payload: LoginRequest, db: Session = Depends(get_db)):
        _check_lockout(payload.email)           # ← ADD: check before anything

        row = db.execute(...).mappings().first()
        if not row:
            _record_failure(payload.email)      # ← ADD: record miss
            raise HTTPException(401, "Invalid credentials")

        if not verify_password(payload.password, row["password_hash"]):
            _record_failure(payload.email)      # ← ADD: record bad password
            raise HTTPException(401, "Invalid credentials")

        _clear_failures(payload.email)          # ← ADD: clear on success
        # ... rest of login ...

═══════════════════════════════════════════════════════════════════
Also add the /auth/refresh proxy route in server/routes.ts:

    app.post("/api/auth/refresh", (req, res) =>
        proxyToFastAPI(req, res, "/auth/refresh"));

And update the frontend (lib/auth.ts) to call /api/auth/refresh
when a 401 is received — add this function:

    export async function refreshAccessToken(refreshToken: string): Promise<string | null> {
      try {
        const res = await fetch("/api/auth/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) return null;
        const data = await res.json();
        setToken(data.access_token);
        localStorage.setItem("aestheticite_refresh", data.refresh_token);
        return data.access_token;
      } catch {
        return null;
      }
    }

    export function getRefreshToken(): string | null {
      return localStorage.getItem("aestheticite_refresh");
    }
"""
