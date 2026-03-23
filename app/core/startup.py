from sqlalchemy import text
from app.db.session import engine

DDL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  role TEXT NOT NULL DEFAULT 'clinician',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  full_name TEXT,
  practitioner_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS auth_access_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL,
  token TEXT UNIQUE NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_access_requests_email ON auth_access_requests(email);

-- Evidence-locked dosing rules (admin-managed, sourced)
CREATE TABLE IF NOT EXISTS dosing_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  rule_json JSONB NOT NULL,
  source_id TEXT,
  source_excerpt TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dosing_rules_category ON dosing_rules(category);

-- User interests for personalized research alerts (Phase 4)
CREATE TABLE IF NOT EXISTS user_interests (
  user_id TEXT NOT NULL,
  topic TEXT NOT NULL,
  email TEXT,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, topic)
);

CREATE INDEX IF NOT EXISTS idx_user_interests_user ON user_interests(user_id);
"""

def ensure_users_table():
    import logging
    log = logging.getLogger(__name__)

    # Execute each statement individually so a single failure (e.g. pgcrypto
    # extension permission) does not abort all subsequent table creation.
    statements = [s.strip() for s in DDL.split(";") if s.strip()]
    with engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception as e:
                log.warning(f"[startup] Non-fatal DDL warning: {e}")

    # Idempotent column additions
    with engine.begin() as conn:
        for alter in [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS practitioner_id TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS clinic_id TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ",
        ]:
            try:
                conn.execute(text(alter))
            except Exception as e:
                log.warning(f"[startup] Non-fatal ALTER warning: {e}")
