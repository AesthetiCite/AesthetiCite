"""
AesthetiCite — Clinic Network Safety Workspace
Database migration + seed data for PostgreSQL (pgvector stack)

Run standalone:  python -m app.db.network_migrations
Or imported on startup via app.main.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app.db.session import SessionLocal

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

MIGRATION_SQL = """
-- ============================================================
-- ORGANIZATIONS
-- ============================================================
CREATE TABLE IF NOT EXISTS organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    slug        TEXT UNIQUE NOT NULL,
    logo_url    TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- CLINICS
-- ============================================================
CREATE TABLE IF NOT EXISTS clinics (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    location    TEXT,
    timezone    TEXT NOT NULL DEFAULT 'UTC',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_clinics_org ON clinics(org_id);

-- ============================================================
-- MEMBERSHIPS  (user ↔ clinic)
-- ============================================================
CREATE TABLE IF NOT EXISTS memberships (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    clinic_id   UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK(role IN ('super_admin','org_admin','clinic_admin','clinician','reviewer')),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, clinic_id)
);
CREATE INDEX IF NOT EXISTS idx_memberships_user  ON memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_memberships_clinic ON memberships(clinic_id);

-- ============================================================
-- CASE LOGS
-- ============================================================
CREATE TABLE IF NOT EXISTS case_logs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    clinic_id            UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    created_by           UUID NOT NULL,
    patient_reference    TEXT NOT NULL,
    event_date           TIMESTAMPTZ,
    practitioner_name    TEXT,
    procedure            TEXT,
    region               TEXT,
    product_used         TEXT,
    complication_type    TEXT,
    symptoms             TEXT,
    suspected_diagnosis  TEXT,
    treatment_given      TEXT,
    hyaluronidase_dose   TEXT,
    follow_up_plan       TEXT,
    outcome              TEXT,
    notes                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_caselogs_clinic    ON case_logs(clinic_id);
CREATE INDEX IF NOT EXISTS idx_caselogs_org       ON case_logs(org_id);
CREATE INDEX IF NOT EXISTS idx_caselogs_date      ON case_logs(event_date DESC);
CREATE INDEX IF NOT EXISTS idx_caselogs_comptype  ON case_logs(complication_type);

-- ============================================================
-- SAVED PROTOCOLS
-- ============================================================
CREATE TABLE IF NOT EXISTS saved_protocols (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    clinic_id       UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    created_by      UUID NOT NULL,
    title           TEXT NOT NULL,
    source_query    TEXT NOT NULL,
    answer_json     JSONB NOT NULL DEFAULT '{}',
    citations_json  JSONB NOT NULL DEFAULT '[]',
    tags            TEXT[] NOT NULL DEFAULT '{}',
    is_pinned       BOOLEAN NOT NULL DEFAULT FALSE,
    is_archived     BOOLEAN NOT NULL DEFAULT FALSE,
    clinic_approved BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by     UUID,
    approved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_protocols_clinic   ON saved_protocols(clinic_id);
CREATE INDEX IF NOT EXISTS idx_protocols_archived ON saved_protocols(is_archived);

-- ============================================================
-- SAFETY REPORTS
-- ============================================================
CREATE TABLE IF NOT EXISTS safety_reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    clinic_id           UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    created_by          UUID NOT NULL,
    source_type         TEXT NOT NULL CHECK(source_type IN ('case_log','guidance')),
    source_id           UUID,
    title               TEXT NOT NULL,
    summary             TEXT,
    presenting_problem  TEXT,
    immediate_actions   TEXT,
    treatment_used      TEXT,
    escalation_triggers TEXT,
    follow_up           TEXT,
    evidence_refs       JSONB NOT NULL DEFAULT '[]',
    clinician_notes     TEXT,
    patient_summary     TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reports_clinic ON safety_reports(clinic_id);

-- ============================================================
-- ANALYTICS EVENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS analytics_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID,
    clinic_id   UUID,
    user_id     UUID,
    event_type  TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_events_clinic     ON analytics_events(clinic_id);
CREATE INDEX IF NOT EXISTS idx_events_type       ON analytics_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created    ON analytics_events(created_at DESC);
"""


# ---------------------------------------------------------------------------
# SEED DATA
# ---------------------------------------------------------------------------

SEED_ORG_ID     = "a1000000-0000-0000-0000-000000000001"
SEED_CLINIC_A   = "b1000000-0000-0000-0000-000000000001"
SEED_CLINIC_B   = "b2000000-0000-0000-0000-000000000002"

SEED_USER_ADMIN    = "c1000000-0000-0000-0000-000000000001"
SEED_USER_CLINICIAN = "c2000000-0000-0000-0000-000000000002"
SEED_USER_REVIEWER = "c3000000-0000-0000-0000-000000000003"

SAMPLE_CASE_LOGS = [
    {
        "id": str(uuid.UUID(int=i+1)),
        "org_id": SEED_ORG_ID,
        "clinic_id": SEED_CLINIC_A,
        "created_by": SEED_USER_CLINICIAN,
        "patient_reference": f"REF-2024-{100+i:03d}",
        "event_date": f"2024-0{(i%9)+1}-{(i%28)+1:02d}T10:00:00Z",
        "practitioner_name": ["Dr. Sarah Chen", "Dr. James Porter", "Dr. Emma Walsh"][i % 3],
        "procedure": ["Lip filler", "Tear trough filler", "Cheek filler", "Glabellar toxin",
                      "Nasolabial fold filler", "Jawline filler", "Lip filler",
                      "Periorbital filler", "Chin filler", "Temple filler"][i],
        "region": ["Lips", "Periorbital", "Midface", "Glabella", "Nasolabial", "Jawline",
                   "Lips", "Periorbital", "Chin", "Temple"][i],
        "product_used": ["Juvederm Ultra", "Restylane", "Sculptra", "Botox",
                         "Radiesse", "Juvederm Voluma", "Belotero", "Teosyal",
                         "Juvederm Volux", "Juvederm Voluma"][i],
        "complication_type": ["Vascular occlusion", "Bruising", "Vascular occlusion",
                               "Ptosis", "Nodule", "Asymmetry", "Tyndall effect",
                               "Oedema", "Delayed inflammatory reaction", "Vascular occlusion"][i],
        "symptoms": [
            "Immediate blanching, pain, skin discolouration at injection site",
            "Significant bruising lower lip, patient anxious",
            "Livedo reticularis pattern 2 minutes post-injection, blanching",
            "Left eyelid drooping 3 days post-treatment, patient distressed",
            "Firm palpable nodule 3 weeks post nasolabial treatment",
            "Mild asymmetry noted on review at 2 weeks",
            "Bluish discolouration visible under thin skin",
            "Significant swelling 48h post treatment, non-tender",
            "Firm redness and swelling at 4 weeks post treatment",
            "Blanching and pain immediately post temple injection",
        ][i],
        "suspected_diagnosis": [
            "Vascular occlusion — HA filler",
            "Ecchymosis",
            "Vascular occlusion — superficial",
            "Botulinum toxin-induced ptosis",
            "Inflammatory nodule / granuloma",
            "Post-filler asymmetry",
            "Tyndall effect",
            "Angioedema / delayed hypersensitivity",
            "Delayed inflammatory reaction (DIR)",
            "Vascular occlusion — branch ophthalmic artery risk",
        ][i],
        "treatment_given": [
            "Immediate hyaluronidase 1500IU, warm compress, aspirin 300mg",
            "Topical arnica, reassurance, monitoring",
            "Hyaluronidase 600IU, aspirin, nitroglycerin paste",
            "Observation, reassurance, planned review at 6 weeks",
            "Intralesional 5FU + steroid injection, massage",
            "Review booked, patient reassured, touch-up planned",
            "Hyaluronidase 150IU to dissolve superficial filler",
            "Antihistamine, cold compress, review at 72h",
            "Oral prednisolone 30mg reducing course, hydroxychloroquine",
            "Hyaluronidase 1500IU + 300IU repeated x3, urgent ophthalmology referral",
        ][i],
        "hyaluronidase_dose": [
            "1500IU", None, "600IU", None, None, None, "150IU", None, None, "1500IU initial"
        ][i],
        "follow_up_plan": "Review at 48h and 1 week. Photo documentation.",
        "outcome": ["Resolved", "Resolved", "Partial resolution", "Resolved",
                    "Ongoing", "Resolved", "Resolved", "Resolved", "Ongoing", "Urgent referral"][i],
        "notes": "Documented per clinic protocol. Incident form completed.",
    }
    for i in range(10)
]

SAMPLE_PROTOCOL = {
    "id": "d1000000-0000-0000-0000-000000000001",
    "org_id": SEED_ORG_ID,
    "clinic_id": SEED_CLINIC_A,
    "created_by": SEED_USER_ADMIN,
    "title": "Vascular Occlusion Emergency Protocol — HA Filler",
    "source_query": "vascular occlusion hyaluronic acid filler management",
    "answer_json": {
        "clinical_summary": "Vascular occlusion (VO) is the most serious acute complication of dermal filler injection. It occurs when filler is injected intravascularly or compresses a vessel, leading to ischaemia. Immediate recognition and treatment within 60 minutes is critical to prevent tissue necrosis.",
        "immediate_actions": [
            "STOP injection immediately",
            "Do not apply pressure — this may extend the occlusion",
            "Administer hyaluronidase 1500 IU immediately if HA filler used",
            "Apply warm compress to aid vasodilation",
            "Administer aspirin 300 mg orally (unless contraindicated)",
            "Apply topical nitroglycerin paste 2% to affected area",
        ],
        "dose_guidance": {
            "hyaluronidase": "1500–3000 IU per treatment session; repeat every 60 min if no improvement; can use up to 10,000 IU in severe cases",
            "aspirin": "300 mg stat, 75 mg daily thereafter",
            "nitroglycerin_paste": "Thin layer topically over affected area, avoid mucous membranes"
        },
        "red_flags": [
            "Visual changes — any visual disturbance requires IMMEDIATE ophthalmology referral",
            "Skin necrosis (dark purple/black discolouration)",
            "Spreading livedo beyond injection site",
            "Patient reports severe pain disproportionate to procedure",
        ],
        "escalation": "If no improvement within 60 minutes, or if any visual symptoms: call 999 / emergency services, arrange urgent ophthalmology. Do not wait.",
    },
    "citations_json": [
        {"id": 1, "title": "Management of vascular complications of facial fillers", "source": "J Clin Aesthet Dermatol", "year": 2021},
        {"id": 2, "title": "BAFPS/RAFT consensus on vascular occlusion", "source": "BAFPS Guidelines", "year": 2023},
        {"id": 3, "title": "Hyaluronidase dosing in vascular compromise", "source": "Aesthet Surg J", "year": 2020},
    ],
    "tags": ["vascular-occlusion", "emergency", "hyaluronidase", "HA-filler"],
    "is_pinned": True,
    "clinic_approved": True,
}

SAMPLE_SAFETY_REPORT = {
    "id": "e1000000-0000-0000-0000-000000000001",
    "org_id": SEED_ORG_ID,
    "clinic_id": SEED_CLINIC_A,
    "created_by": SEED_USER_ADMIN,
    "source_type": "case_log",
    "source_id": str(uuid.UUID(int=1)),
    "title": "Safety Report — Lip Filler Vascular Occlusion (REF-2024-101)",
    "summary": "Vascular occlusion identified immediately post lip filler injection. Treated promptly with hyaluronidase 1500 IU and adjunct medications. Full resolution achieved within 48 hours.",
    "presenting_problem": "Patient presented for lip augmentation with 1ml Juvederm Ultra. Two minutes post-injection, blanching was noted across the upper lip with patient reporting significant pain. Skin discolouration (mottled pattern) observed immediately.",
    "immediate_actions": "Injection stopped immediately. Hyaluronidase 1500 IU administered at four injection sites. Warm compress applied. Aspirin 300 mg given orally. Nitroglycerin paste applied to upper lip. Patient monitored for 90 minutes.",
    "treatment_used": "Hyaluronidase 1500 IU total; aspirin 300 mg stat; topical nitroglycerin 2%; warm compress therapy.",
    "escalation_triggers": "Visual symptoms were assessed — patient confirmed no visual changes. No escalation to emergency services required. Ophthalmology on standby.",
    "follow_up": "Patient reviewed at 24h and 48h. Full skin reperfusion confirmed at 48h review. No residual ischaemia. Patient counselled regarding future treatment risks.",
    "evidence_refs": [
        {"title": "BAFPS/RAFT consensus on vascular occlusion", "year": 2023, "level": "Guideline"},
        {"title": "Hyaluronidase dosing in aesthetic complications", "year": 2021, "level": "Review"},
    ],
    "clinician_notes": "Retrospective review: Needle technique used. Consider cannula for future lip treatments in this patient. Vascular mapping at baseline would be advisable.",
    "patient_summary": "A complication occurred during your lip treatment where a blood vessel was temporarily affected. This was treated immediately and successfully. All tests confirmed normal healing. Your clinician will discuss future treatment options with you.",
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_migrations() -> None:
    with SessionLocal() as db:
        for stmt in MIGRATION_SQL.strip().split(";"):
            s = stmt.strip()
            if s:
                try:
                    db.execute(text(s))
                except Exception as e:
                    print(f"[network_migrations] warning: {e}")
        db.commit()
    print("[network_migrations] schema OK")


def run_seed() -> None:
    with SessionLocal() as db:
        # Org
        db.execute(text("""
            INSERT INTO organizations (id, name, slug)
            VALUES (:id, :name, :slug)
            ON CONFLICT (id) DO NOTHING
        """), {"id": SEED_ORG_ID, "name": "Aesthetic Clinic Group", "slug": "acg"})

        # Clinics
        db.execute(text("""
            INSERT INTO clinics (id, org_id, name, location)
            VALUES (:id, :org_id, :name, :location)
            ON CONFLICT (id) DO NOTHING
        """), {"id": SEED_CLINIC_A, "org_id": SEED_ORG_ID, "name": "London Clinic", "location": "London, UK"})

        db.execute(text("""
            INSERT INTO clinics (id, org_id, name, location)
            VALUES (:id, :org_id, :name, :location)
            ON CONFLICT (id) DO NOTHING
        """), {"id": SEED_CLINIC_B, "org_id": SEED_ORG_ID, "name": "Manchester Clinic", "location": "Manchester, UK"})

        # Memberships (assumes users already exist in `users` table)
        for user_id, role, clinic_id in [
            (SEED_USER_ADMIN, "org_admin", SEED_CLINIC_A),
            (SEED_USER_ADMIN, "org_admin", SEED_CLINIC_B),
            (SEED_USER_CLINICIAN, "clinician", SEED_CLINIC_A),
            (SEED_USER_REVIEWER, "reviewer", SEED_CLINIC_A),
        ]:
            db.execute(text("""
                INSERT INTO memberships (user_id, org_id, clinic_id, role)
                VALUES (:user_id, :org_id, :clinic_id, :role)
                ON CONFLICT (user_id, clinic_id) DO NOTHING
            """), {"user_id": user_id, "org_id": SEED_ORG_ID,
                   "clinic_id": clinic_id, "role": role})

        # Case logs
        for log in SAMPLE_CASE_LOGS:
            db.execute(text("""
                INSERT INTO case_logs (
                    id, org_id, clinic_id, created_by, patient_reference, event_date,
                    practitioner_name, procedure, region, product_used, complication_type,
                    symptoms, suspected_diagnosis, treatment_given, hyaluronidase_dose,
                    follow_up_plan, outcome, notes
                ) VALUES (
                    :id, :org_id, :clinic_id, :created_by, :patient_reference, :event_date,
                    :practitioner_name, :procedure, :region, :product_used, :complication_type,
                    :symptoms, :suspected_diagnosis, :treatment_given, :hyaluronidase_dose,
                    :follow_up_plan, :outcome, :notes
                ) ON CONFLICT (id) DO NOTHING
            """), log)

        # Saved protocol
        p = SAMPLE_PROTOCOL
        db.execute(text("""
            INSERT INTO saved_protocols (
                id, org_id, clinic_id, created_by, title, source_query,
                answer_json, citations_json, tags, is_pinned, clinic_approved
            ) VALUES (
                :id, :org_id, :clinic_id, :created_by, :title, :source_query,
                :answer_json, :citations_json, :tags, :is_pinned, :clinic_approved
            ) ON CONFLICT (id) DO NOTHING
        """), {
            **p,
            "answer_json": json.dumps(p["answer_json"]),
            "citations_json": json.dumps(p["citations_json"]),
        })

        # Safety report
        r = SAMPLE_SAFETY_REPORT
        db.execute(text("""
            INSERT INTO safety_reports (
                id, org_id, clinic_id, created_by, source_type, source_id, title,
                summary, presenting_problem, immediate_actions, treatment_used,
                escalation_triggers, follow_up, evidence_refs, clinician_notes, patient_summary
            ) VALUES (
                :id, :org_id, :clinic_id, :created_by, :source_type, :source_id, :title,
                :summary, :presenting_problem, :immediate_actions, :treatment_used,
                :escalation_triggers, :follow_up, :evidence_refs, :clinician_notes, :patient_summary
            ) ON CONFLICT (id) DO NOTHING
        """), {**r, "evidence_refs": json.dumps(r["evidence_refs"])})

        db.commit()
    print("[network_migrations] seed OK")


if __name__ == "__main__":
    run_migrations()
    run_seed()
