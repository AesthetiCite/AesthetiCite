"""
AesthetiCite — Network Workspace Seed Data
app/api/seed_network.py

Seeds one organization, two clinics, sample users, 10 case logs,
1 saved protocol (vascular occlusion), and 1 safety report.
Safe to run multiple times (idempotent).
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import hash_password

log = logging.getLogger(__name__)


def seed_network_workspace(db: Session) -> None:
    """Idempotent seed for demo/dev environment."""
    try:
        # Skip if org already seeded
        exists = db.execute(text(
            "SELECT 1 FROM organizations WHERE slug = 'aestheticite-demo'"
        )).fetchone()
        if exists:
            log.info("[seed] Network workspace already seeded — skipping")
            return

        # ── Organization ──────────────────────────────────────────────────────
        org = db.execute(text("""
            INSERT INTO organizations (name, slug, plan)
            VALUES ('AesthetiCite Demo Network', 'aestheticite-demo', 'enterprise')
            RETURNING id::text
        """)).mappings().first()
        org_id = org["id"]

        # ── Clinics ───────────────────────────────────────────────────────────
        clinic_a = db.execute(text("""
            INSERT INTO clinics (org_id, name, address, timezone)
            VALUES (:oid, 'Mayfair Aesthetic Clinic', '14 Harley Street, London W1G 9PH', 'Europe/London')
            RETURNING id::text
        """), {"oid": org_id}).mappings().first()
        clinic_a_id = clinic_a["id"]

        clinic_b = db.execute(text("""
            INSERT INTO clinics (org_id, name, address, timezone)
            VALUES (:oid, 'Chelsea Skin & Laser Centre', '221 King''s Road, London SW3 5EL', 'Europe/London')
            RETURNING id::text
        """), {"oid": org_id}).mappings().first()
        clinic_b_id = clinic_b["id"]

        # ── Users ─────────────────────────────────────────────────────────────
        def upsert_user(email, full_name, role, pw="Demo1234!"):
            existing = db.execute(text(
                "SELECT id::text FROM users WHERE email = :e"
            ), {"e": email}).mappings().first()
            if existing:
                return existing["id"]
            row = db.execute(text("""
                INSERT INTO users (email, password_hash, full_name, role)
                VALUES (:e, :ph, :fn, :role)
                RETURNING id::text
            """), {"e": email, "ph": hash_password(pw), "fn": full_name, "role": role}).mappings().first()
            return row["id"]

        dr_mehta_id = upsert_user("mehta@aestheticite.demo", "Dr. Priya Mehta", "admin")
        dr_jones_id = upsert_user("jones@aestheticite.demo", "Dr. Sarah Jones", "clinician")
        dr_patel_id = upsert_user("patel@aestheticite.demo", "Dr. Ravi Patel", "clinician")
        admin_id    = upsert_user("admin@aestheticite.demo", "Clinic Admin", "clinic_admin")
        reviewer_id = upsert_user("reviewer@aestheticite.demo", "Dr. Alex Chen", "clinician")

        # ── Memberships ───────────────────────────────────────────────────────
        def add_membership(user_id, clinic_id, role):
            db.execute(text("""
                INSERT INTO memberships (user_id, clinic_id, org_id, role)
                VALUES (:uid, :cid, :oid, :role)
                ON CONFLICT (user_id, clinic_id) DO NOTHING
            """), {"uid": user_id, "cid": clinic_id, "oid": org_id, "role": role})

        add_membership(dr_mehta_id, clinic_a_id, "org_admin")
        add_membership(dr_mehta_id, clinic_b_id, "org_admin")
        add_membership(dr_jones_id, clinic_a_id, "clinician")
        add_membership(dr_patel_id, clinic_a_id, "clinician")
        add_membership(dr_patel_id, clinic_b_id, "clinician")
        add_membership(admin_id,    clinic_a_id, "clinic_admin")
        add_membership(reviewer_id, clinic_b_id, "reviewer")

        db.commit()

        # ── Sample Case Logs ──────────────────────────────────────────────────
        cases = [
            {
                "patient_reference": "PT-2026-001",
                "practitioner_name": "Dr. Sarah Jones",
                "procedure": "HA Filler — Nasolabial Folds",
                "region": "Mid-face",
                "product": "Juvederm Voluma 2ml",
                "complication_type": "Vascular Occlusion — HA Filler",
                "symptoms": "Immediate blanching, pain, livedo reticularis pattern post-injection",
                "suspected_diagnosis": "Arterial occlusion — facial artery branch",
                "treatment_given": "Hyaluronidase 1500 IU distributed across affected zone, warm compress, aspirin 300mg",
                "hyaluronidase_dose": "1500 IU in 3ml saline, repeated at 30min",
                "follow_up_plan": "Review at 24h and 72h. Ophthalmology referral arranged.",
                "outcome": "Resolved — skin perfusion restored within 2 hours",
                "notes": "No visual symptoms. Onset within 60 seconds of injection.",
                "clinic_id": clinic_a_id,
                "daysago": 2,
            },
            {
                "patient_reference": "PT-2026-002",
                "practitioner_name": "Dr. Ravi Patel",
                "procedure": "HA Filler — Tear Trough",
                "region": "Periorbital",
                "product": "Restylane Eyelight 0.5ml",
                "complication_type": "Vision Changes Post-Filler",
                "symptoms": "Sudden onset blurred vision right eye, amaurosis fugax immediately post-injection",
                "suspected_diagnosis": "Suspected retinal artery embolism",
                "treatment_given": "Emergency hyaluronidase periorbital 1500 IU, immediate ophthalmology transfer",
                "hyaluronidase_dose": "1500 IU periorbital and retrobulbar",
                "follow_up_plan": "Ophthalmology inpatient care. Retinal imaging arranged.",
                "outcome": "Partial recovery — follow-up ongoing",
                "notes": "High-risk zone. Aspiration performed pre-injection. Occurred despite precautions.",
                "clinic_id": clinic_a_id,
                "daysago": 14,
            },
            {
                "patient_reference": "PT-2026-003",
                "practitioner_name": "Dr. Sarah Jones",
                "procedure": "Botulinum Toxin Type A — Forehead",
                "region": "Upper Face",
                "product": "Botox 20u",
                "complication_type": "Ptosis Post-Botox",
                "symptoms": "Unilateral eyelid drooping appearing 4 days post-treatment",
                "suspected_diagnosis": "Levator palpebrae spread of toxin",
                "treatment_given": "Apraclonidine 0.5% drops TDS, reassurance",
                "hyaluronidase_dose": "N/A",
                "follow_up_plan": "Review at 2 weeks. Expected resolution in 4–8 weeks.",
                "outcome": "Resolving — partial improvement at 3 weeks",
                "notes": "Patient placed correctly, frontalis injection 2cm above brow.",
                "clinic_id": clinic_a_id,
                "daysago": 21,
            },
            {
                "patient_reference": "PT-2026-004",
                "practitioner_name": "Dr. Ravi Patel",
                "procedure": "Lip Filler — Vermilion Border",
                "region": "Lips",
                "product": "Juvederm Ultra 1ml",
                "complication_type": "Tyndall Effect",
                "symptoms": "Bluish discolouration visible along vermilion border in natural light",
                "suspected_diagnosis": "Superficial product placement — Tyndall effect",
                "treatment_given": "Hyaluronidase 150 IU targeted dissolution",
                "hyaluronidase_dose": "150 IU in 1ml saline, single session",
                "follow_up_plan": "Review 2 weeks post-dissolution. Re-treat at appropriate depth.",
                "outcome": "Resolved — repeat treatment at correct depth successful",
                "notes": "Tyndall present from previous practitioner's treatment.",
                "clinic_id": clinic_b_id,
                "daysago": 7,
            },
            {
                "patient_reference": "PT-2026-005",
                "practitioner_name": "Dr. Alex Chen",
                "procedure": "HA Filler — Cheeks",
                "region": "Mid-face / Zygoma",
                "product": "Sculptra 2ml bilateral",
                "complication_type": "Delayed Nodule Formation",
                "symptoms": "Bilateral palpable nodules 3 months post-treatment, non-tender",
                "suspected_diagnosis": "Biofilm-associated delayed inflammatory nodules",
                "treatment_given": "5-FU + triamcinolone intralesional, oral clarithromycin 500mg 3 weeks",
                "hyaluronidase_dose": "N/A (Sculptra)",
                "follow_up_plan": "Monthly injections x3. Ultrasound-guided if no response.",
                "outcome": "Ongoing — 40% reduction at 6 weeks",
                "notes": "Patient had dental procedure 3 weeks prior to onset.",
                "clinic_id": clinic_b_id,
                "daysago": 5,
            },
            {
                "patient_reference": "PT-2026-006",
                "practitioner_name": "Dr. Sarah Jones",
                "procedure": "Mesotherapy — Skin Booster",
                "region": "Cheeks",
                "product": "Profhilo 2ml",
                "complication_type": "Localised Bruising / Haematoma",
                "symptoms": "Extensive bruising right cheek, spreading over 48 hours",
                "suspected_diagnosis": "Vessel trauma — subcutaneous haematoma",
                "treatment_given": "Arnica topical, ice compress, patient reassured",
                "hyaluronidase_dose": "N/A",
                "follow_up_plan": "Review 7 days. Photograph documentation.",
                "outcome": "Resolved — complete resolution at 10 days",
                "notes": "Patient taking omega-3 supplements not disclosed pre-treatment.",
                "clinic_id": clinic_a_id,
                "daysago": 10,
            },
            {
                "patient_reference": "PT-2026-007",
                "practitioner_name": "Dr. Ravi Patel",
                "procedure": "Rhinoplasty Filler — Nasal Bridge",
                "region": "Nose",
                "product": "Restylane Lyft 1ml",
                "complication_type": "Vascular Occlusion — Nasal Tip",
                "symptoms": "Nasal tip blanching, progressive mottling, pain score 7/10",
                "suspected_diagnosis": "Angular artery / columellar artery occlusion",
                "treatment_given": "Hyaluronidase 900 IU, warm compress, GTN patch, aspirin 300mg",
                "hyaluronidase_dose": "900 IU titrated across columella and tip",
                "follow_up_plan": "Daily review for 5 days. Dermatology input if skin loss.",
                "outcome": "Resolved with minor superficial skin change at tip",
                "notes": "High-risk zone. Retrograde injection technique used.",
                "clinic_id": clinic_a_id,
                "daysago": 30,
            },
            {
                "patient_reference": "PT-2026-008",
                "practitioner_name": "Dr. Alex Chen",
                "procedure": "Thread Lift — Mid-face",
                "region": "Cheeks / SMAS",
                "product": "PDO Mono Threads x20",
                "complication_type": "Thread Migration / Palpable Threads",
                "symptoms": "Visible thread ends at entry point, mild tenderness",
                "suspected_diagnosis": "Superficial thread placement with migration",
                "treatment_given": "Thread removal under local anaesthetic",
                "hyaluronidase_dose": "N/A",
                "follow_up_plan": "Review 1 week post-removal. No re-treatment for 3 months.",
                "outcome": "Resolved — threads removed successfully",
                "notes": "Consent included thread migration risk.",
                "clinic_id": clinic_b_id,
                "daysago": 45,
            },
            {
                "patient_reference": "PT-2026-009",
                "practitioner_name": "Dr. Sarah Jones",
                "procedure": "Chemical Peel — TCA 20%",
                "region": "Full Face",
                "product": "TCA 20% Solution",
                "complication_type": "Post-Inflammatory Hyperpigmentation",
                "symptoms": "Persistent hyperpigmentation upper lip and forehead 6 weeks post-peel",
                "suspected_diagnosis": "PIH in Fitzpatrick IV skin type — inadequate pre-conditioning",
                "treatment_given": "Hydroquinone 4% + tretinoin 0.025% nightly, SPF50 strict",
                "hyaluronidase_dose": "N/A",
                "follow_up_plan": "Review monthly x3. Consider tranexamic acid oral.",
                "outcome": "Improving — 60% improvement at 12 weeks",
                "notes": "Pre-treatment Obagi conditioning not completed due to patient non-compliance.",
                "clinic_id": clinic_b_id,
                "daysago": 60,
            },
            {
                "patient_reference": "PT-2026-010",
                "practitioner_name": "Dr. Ravi Patel",
                "procedure": "Sculptra — Temples",
                "region": "Temples",
                "product": "Sculptra 2ml bilateral",
                "complication_type": "Delayed Inflammatory Reaction",
                "symptoms": "Bilateral swelling, warmth, erythema temples — 6 weeks post-treatment",
                "suspected_diagnosis": "Delayed immune-mediated inflammatory reaction to PLLA",
                "treatment_given": "Oral prednisolone 40mg reducing course over 2 weeks, topical clobetasol",
                "hyaluronidase_dose": "N/A",
                "follow_up_plan": "Weekly review. MRI if not resolving at 4 weeks.",
                "outcome": "Resolving — 70% improvement on steroids",
                "notes": "COVID-19 vaccine 3 weeks prior. Potential immune trigger.",
                "clinic_id": clinic_b_id,
                "daysago": 15,
            },
        ]

        for case_data in cases:
            days_ago = case_data.pop("daysago", 0)
            case_clinic = case_data.pop("clinic_id")
            incident_ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
            db.execute(text("""
                INSERT INTO network_case_logs
                    (org_id, clinic_id, created_by, patient_reference, incident_at,
                     practitioner_name, procedure, region, product, complication_type,
                     symptoms, suspected_diagnosis, treatment_given, hyaluronidase_dose,
                     follow_up_plan, outcome, notes)
                VALUES
                    (:oid, :cid, :uid, :pr, :ia,
                     :pn, :proc, :reg, :prod, :ct,
                     :sx, :sd, :tg, :hd, :fp, :out, :notes)
            """), {
                "oid": org_id, "cid": case_clinic, "uid": dr_mehta_id,
                "pr": case_data["patient_reference"], "ia": incident_ts,
                "pn": case_data["practitioner_name"], "proc": case_data["procedure"],
                "reg": case_data["region"], "prod": case_data["product"],
                "ct": case_data["complication_type"], "sx": case_data["symptoms"],
                "sd": case_data["suspected_diagnosis"], "tg": case_data["treatment_given"],
                "hd": case_data["hyaluronidase_dose"], "fp": case_data["follow_up_plan"],
                "out": case_data["outcome"], "notes": case_data["notes"],
            })

        db.commit()

        # ── Sample Saved Protocol — Vascular Occlusion ────────────────────────
        vascular_protocol = {
            "title": "Vascular Occlusion Protocol — HA Filler (BDSA/BCAM Guidelines)",
            "answer": "Management of suspected vascular occlusion following HA filler injection requires immediate recognition and action within the first 60 minutes to optimise outcomes.\n\n**IMMEDIATE STEPS:**\n1. Stop injection immediately\n2. Apply warm compress to affected area\n3. Begin hyaluronidase protocol — 1500 IU in 3ml saline, distributed across affected zone\n4. Reassess at 30 minutes; repeat hyaluronidase if incomplete resolution\n5. Administer aspirin 300mg orally (unless contraindicated)\n6. Apply GTN patch if available\n\n**ESCALATION CRITERIA:**\n- Any visual symptoms: immediate emergency transfer and ophthalmology consultation\n- Skin necrosis developing despite treatment: wound care and plastic surgery referral\n- No improvement after 3 hyaluronidase doses: hospital admission\n\n**FOLLOW-UP:**\n- Review at 24h, 72h, and 7 days\n- Document with clinical photography at each review\n- Dermatology referral if healing delayed beyond 14 days",
            "citations": [
                {"title": "BDSA Guidelines for Vascular Complications", "evidence_type": "Guideline", "badge_color": "green", "year": 2023},
                {"title": "BCAM Consensus on Hyaluronidase Use", "evidence_type": "Consensus Statement", "badge_color": "blue", "year": 2022},
                {"title": "Cohen & Dempsey — Vascular Complications Aesthetic Fillers", "evidence_type": "Review", "badge_color": "purple", "year": 2021},
            ],
            "tags": ["vascular-occlusion", "HA-filler", "emergency", "hyaluronidase", "guideline"],
        }

        db.execute(text("""
            INSERT INTO saved_protocols
                (org_id, clinic_id, created_by, title, source_query, answer_json, citations_json, tags, is_approved, is_pinned)
            VALUES
                (:oid, :cid, :uid, :title, :sq, :aj, :cj, :tags, TRUE, TRUE)
        """), {
            "oid": org_id, "cid": clinic_a_id, "uid": dr_mehta_id,
            "title": vascular_protocol["title"],
            "sq": "vascular occlusion hyaluronidase protocol aesthetic filler",
            "aj": json.dumps({"answer": vascular_protocol["answer"]}),
            "cj": json.dumps(vascular_protocol["citations"]),
            "tags": vascular_protocol["tags"],
        })

        # ── Sample Safety Report ───────────────────────────────────────────────
        db.execute(text("""
            INSERT INTO safety_reports (org_id, clinic_id, created_by, source_type, title, report_json)
            VALUES (:oid, :cid, :uid, 'guidance', :title, :rj)
        """), {
            "oid": org_id, "cid": clinic_a_id, "uid": dr_mehta_id,
            "title": "Safety Report — Vascular Occlusion Case PT-2026-001",
            "rj": json.dumps({
                "title": "Safety Report — Vascular Occlusion Case PT-2026-001",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "summary": "Patient presented with immediate blanching and livedo reticularis following HA filler injection to the nasolabial folds. Vascular occlusion was suspected and immediately treated with hyaluronidase 1500 IU.",
                "presenting_problem": "Immediate blanching, pain, livedo reticularis pattern post-injection to nasolabial folds.",
                "immediate_actions": ["Stop injection", "Apply warm compress", "Hyaluronidase 1500 IU administered within 5 minutes"],
                "treatment_used": "Hyaluronidase 1500 IU in 3ml saline, aspirin 300mg, warm compress, repeated hyaluronidase at 30min",
                "escalation_triggers": "Ophthalmology referral arranged. Visual symptom checklist completed — all negative.",
                "follow_up": "Review at 24h (resolved), 72h (clear), 7 days (no sequelae).",
                "evidence_references": [
                    {"title": "BDSA Guidelines for Vascular Complications", "evidence_type": "Guideline", "year": 2023}
                ],
                "clinician_notes": "Rapid response within 5 minutes from onset. Patient fully recovered. Technique review: retrograde injection technique used going forward.",
                "outcome": "Resolved — full recovery at 2 hours",
                "patient_readable": "You experienced a complication during your filler treatment where blood flow was briefly affected. We treated this immediately and your skin returned to normal. You were reviewed at follow-up appointments and have fully recovered.",
            }),
        })

        db.commit()
        log.info("[seed] Network workspace seeded: 1 org, 2 clinics, 5 users, 10 cases, 1 protocol, 1 report")

    except Exception as exc:
        log.error("[seed] Failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
