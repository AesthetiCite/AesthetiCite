# AesthetiCite Security Patches
## Apply in this order — estimated 90 minutes total

---

## IMMEDIATE (30 min) — Before showing any clinic

### Step 1 — Rotate JWT_SECRET RIGHT NOW (0 code, 2 minutes)
Check what JWT_SECRET is in your Railway / Replit env vars.
If it is any word, phrase, or fewer than 32 characters, generate a new one:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Paste the output as your new JWT_SECRET. All existing sessions will be
invalidated — this is intentional and correct.

---

### Step 2 — Apply security_patch_main.py (10 min)
File: `app/main.py`
- CHANGE 1: CORS lock-down (fail-closed, not fail-open)
- CHANGE 2: Security headers middleware
- CHANGE 3: Lock metrics-lite endpoint
- CHANGE 4: Audit log table SQL in startup migration

---

### Step 3 — Apply security_patch_inputs.py (15 min)
Files: `app/api/vision_analysis.py`, `app/api/clinical_tools_engine.py`,
       `app/api/visual_counseling.py`, `app/api/complication_protocol_engine.py`,
       `app/api/preprocedure_safety_engine.py`
- Rate limits on vision and AI tool endpoints
- sanitize_input() on all free-text user fields
- File upload: MIME type + size validation

Install dependency:
```bash
pip install python-magic
echo "python-magic>=0.4.27" >> requirements.txt
```

---

## BEFORE FIRST ENTERPRISE CONTRACT (60 min)

### Step 4 — Apply security_patch_auth.py (20 min)
Files: `app/core/auth.py`, `app/api/auth.py` (or wherever login lives)
- JWT refresh tokens (30-day, rotating)
- Brute-force lockout on /auth/login
- Update login endpoint to return refresh_token

---

### Step 5 — Apply security_patch_audit.py (20 min)
New file: `app/core/audit.py`
- Postgres-backed durable audit log
- Replace safe_write_jsonl() calls in governance.py
- Add audit events to ask_stream.py, auth.py, and protocol engine

---

### Step 6 — Apply security_patch_frontend.py (20 min)
Files: `client/src/lib/auth.ts`, `client/src/main.tsx`, `index.html`,
       `server/routes.ts`
- Refresh token storage + authedFetch() with auto-retry
- Sentry frontend integration
- Security meta tags in HTML

Install dependency:
```bash
npm install @sentry/react
```

---

## ENV VARS CHECKLIST

Set all of these in Railway (and update Replit for dev):

| Variable | Required | What it should be |
|---|---|---|
| JWT_SECRET | CRITICAL | 64-char random hex from `secrets.token_hex(32)` |
| CORS_ORIGINS | CRITICAL | `https://aestheticite.com,https://www.aestheticite.com` |
| ENV | Required | `production` on Railway, `dev` on Replit |
| VITE_SENTRY_DSN | Optional | Get from Sentry dashboard after creating project |
| DATABASE_URL | Already set | Pooled Neon URL (with -pooler in hostname) |
| DATABASE_URL_DIRECT | Migrations only | Direct Neon URL (without -pooler) |

---

## WHAT EACH PATCH FIXES

| Patch | Vulnerability | Severity |
|---|---|---|
| Step 1 (JWT_SECRET) | Token forgery — admin access with no password | CRITICAL |
| Step 2 CORS | Any website can call your API using a clinician's session | CRITICAL |
| Step 2 Headers | XSS, clickjacking, MIME sniffing | CRITICAL |
| Step 2 metrics-lite | Leaks user count and DB stats to anyone | Medium |
| Step 3 rate limits | GPT-4o vision abuse — unlimited $0.025 calls | CRITICAL |
| Step 3 sanitize | Prompt injection into LLM via user fields | High |
| Step 3 file upload | Memory exhaustion, malicious file crashes | High |
| Step 4 refresh tokens | Clinicians silently logged out mid-procedure | High |
| Step 4 brute-force | Unlimited password attempts on any account | High |
| Step 5 audit log | Audit log wiped on every deploy (GDPR, SaMD) | Critical |
| Step 6 authedFetch | 401 errors break mid-session without recovery | Medium |
| Step 6 Sentry frontend | React errors invisible — no debugging data | Medium |

---

## WHAT THIS DOES NOT COVER

These require external action (not code):
- SOC 2 Type II: engage Vanta, 6-month audit process
- HIPAA BAAs: sign with Neon, Railway, OpenAI (1 day, no cost)
- UK GDPR Data Processing Agreement: review with legal
- Penetration test: recommended before first enterprise contract
