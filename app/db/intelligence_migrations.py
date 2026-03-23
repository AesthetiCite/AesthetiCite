"""
AesthetiCite — Unicorn Intelligence Migrations
Adds tables for:
  - practitioner_risk_scores   (Shift-inspired)
  - complication_alerts        (Shift-inspired pattern detection)
  - complication_monitors      (DentalMonitoring-inspired async photo)
  - llm_provider_config        (Mistral/OpenAI abstraction)
  - clinician_events           (Contentsquare-inspired session analytics)

Run: python -m app.db.intelligence_migrations
"""
from __future__ import annotations
from sqlalchemy import text
from app.db.session import SessionLocal

MIGRATION_SQL = """
-- ============================================================
-- PRACTITIONER RISK SCORES
-- ============================================================
CREATE TABLE IF NOT EXISTS practitioner_risk_scores (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    clinic_id           UUID NOT NULL,
    practitioner_name   TEXT NOT NULL,
    period_start        DATE NOT NULL,
    period_end          DATE NOT NULL,
    total_cases         INTEGER NOT NULL DEFAULT 0,
    high_risk_cases     INTEGER NOT NULL DEFAULT 0,
    vascular_cases      INTEGER NOT NULL DEFAULT 0,
    necrosis_cases      INTEGER NOT NULL DEFAULT 0,
    visual_cases        INTEGER NOT NULL DEFAULT 0,
    unresolved_cases    INTEGER NOT NULL DEFAULT 0,
    risk_score          NUMERIC(5,2) NOT NULL DEFAULT 0,
    risk_level          TEXT NOT NULL DEFAULT 'normal'
                        CHECK(risk_level IN ('normal','elevated','high','critical')),
    top_complications   JSONB NOT NULL DEFAULT '[]',
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(clinic_id, practitioner_name, period_start, period_end)
);
CREATE INDEX IF NOT EXISTS idx_prs_clinic      ON practitioner_risk_scores(clinic_id);
CREATE INDEX IF NOT EXISTS idx_prs_level       ON practitioner_risk_scores(risk_level);
CREATE INDEX IF NOT EXISTS idx_prs_generated   ON practitioner_risk_scores(generated_at DESC);

-- ============================================================
-- COMPLICATION ALERTS  (pattern-triggered)
-- ============================================================
CREATE TABLE IF NOT EXISTS complication_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    clinic_id       UUID NOT NULL,
    alert_type      TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK(severity IN ('info','warning','critical')),
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    evidence_json   JSONB NOT NULL DEFAULT '{}',
    is_dismissed    BOOLEAN NOT NULL DEFAULT FALSE,
    dismissed_by    UUID,
    dismissed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alerts_clinic     ON complication_alerts(clinic_id);
CREATE INDEX IF NOT EXISTS idx_alerts_dismissed  ON complication_alerts(is_dismissed);
CREATE INDEX IF NOT EXISTS idx_alerts_created    ON complication_alerts(created_at DESC);

-- ============================================================
-- COMPLICATION MONITORS  (DentalMonitoring-inspired)
-- ============================================================
CREATE TABLE IF NOT EXISTS complication_monitors (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    clinic_id           UUID NOT NULL,
    case_log_id         UUID,
    created_by          UUID NOT NULL,
    patient_reference   TEXT NOT NULL,
    procedure           TEXT,
    region              TEXT,
    monitor_status      TEXT NOT NULL DEFAULT 'active'
                        CHECK(monitor_status IN ('active','resolved','escalated','closed')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_monitors_clinic  ON complication_monitors(clinic_id);
CREATE INDEX IF NOT EXISTS idx_monitors_status  ON complication_monitors(monitor_status);

CREATE TABLE IF NOT EXISTS monitor_submissions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    monitor_id      UUID NOT NULL REFERENCES complication_monitors(id) ON DELETE CASCADE,
    submitted_by    UUID,
    image_url       TEXT,
    image_b64       TEXT,
    notes           TEXT,
    ai_assessment   JSONB NOT NULL DEFAULT '{}',
    alert_triggered BOOLEAN NOT NULL DEFAULT FALSE,
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_submissions_monitor ON monitor_submissions(monitor_id);
CREATE INDEX IF NOT EXISTS idx_submissions_alert   ON monitor_submissions(alert_triggered);

-- ============================================================
-- LLM PROVIDER CONFIG  (per-org Mistral / OpenAI)
-- ============================================================
CREATE TABLE IF NOT EXISTS llm_provider_configs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL UNIQUE,
    provider        TEXT NOT NULL DEFAULT 'openai'
                    CHECK(provider IN ('openai','mistral','azure_openai','local')),
    model           TEXT NOT NULL DEFAULT 'gpt-4o',
    api_key_enc     TEXT,
    base_url        TEXT,
    on_premise      BOOLEAN NOT NULL DEFAULT FALSE,
    extra_params    JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- CLINICIAN EVENTS  (Contentsquare-inspired)
-- ============================================================
CREATE TABLE IF NOT EXISTS clinician_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID,
    clinic_id       UUID,
    user_id         UUID,
    session_id      TEXT,
    event_type      TEXT NOT NULL,
    target_element  TEXT,
    answer_section  TEXT,
    query_id        TEXT,
    duration_ms     INTEGER,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cevents_clinic   ON clinician_events(clinic_id);
CREATE INDEX IF NOT EXISTS idx_cevents_type     ON clinician_events(event_type);
CREATE INDEX IF NOT EXISTS idx_cevents_created  ON clinician_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cevents_section  ON clinician_events(answer_section)
"""


def run_intelligence_migrations() -> None:
    with SessionLocal() as db:
        for stmt in MIGRATION_SQL.strip().split(";"):
            s = stmt.strip()
            if s:
                try:
                    db.execute(text(s))
                except Exception as e:
                    print(f"[intelligence_migrations] warning: {e}")
        db.commit()
    print("[intelligence_migrations] OK")


if __name__ == "__main__":
    run_intelligence_migrations()
