"""
AesthetiCite Mass Upload Engine — Five-Milestone Strategy
==========================================================

Milestone 1 → 100k   : Clean & rank existing corpus (run immediately)
Milestone 2 → 250k   : Guideline/review-first ingestion
Milestone 3 → 500k   : Multilingual retrieval — 25 languages
Milestone 4 → 1M     : Full breadth + deduplication + fast search
Milestone 5 → 1.5M   : Aesthetic medicine deep-dive + recency sweep + safety data

Each milestone triggers a quality operation before moving to the next.
"""
from __future__ import annotations

import os, sys, time, json, logging, threading, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import defusedxml.ElementTree as ET

PUBMED_LANG_MAP = {
    "english": "en", "french": "fr", "german": "de", "spanish": "es",
    "italian": "it", "portuguese": "pt", "chinese": "zh", "japanese": "ja",
    "korean": "ko", "dutch": "nl", "russian": "ru", "arabic": "ar",
    "turkish": "tr", "polish": "pl", "swedish": "sv", "norwegian": "no",
    "danish": "da", "finnish": "fi", "czech": "cs", "hungarian": "hu",
    "romanian": "ro", "greek": "el", "hebrew": "he", "persian": "fa",
    "thai": "th", "vietnamese": "vi", "ukrainian": "uk",
}
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from app.db.session import SessionLocal

logger = logging.getLogger("mass_upload")

# ─── Targets ────────────────────────────────────────────────────────────────
TARGET_DOCS = 1_500_000
MILESTONES = {1: 100_000, 2: 250_000, 3: 500_000, 4: 1_000_000, 5: 1_500_000}

BATCH_EMBED_SIZE = 64   # restored — memory is not the bottleneck
FETCH_BATCH_SIZE = 500
FETCH_WORKERS    = 4   # more parallel fetches now that DB insert overhead is gone
PROGRESS_FILE    = Path("mass_upload_progress.json")

# ─── Keepalive ───────────────────────────────────────────────────────────────
# Replit's idle-timeout kills the process if no inbound HTTP traffic arrives for
# ~5 minutes. The mass-upload agent only makes outbound calls (PubMed + DB), so
# we ping our own health endpoint every 60 s to keep the process alive.
def _keepalive_loop():
    """Ping /health every 60s indefinitely — keeps the process alive even when engine is idle/gated."""
    while True:
        try:
            requests.get("http://localhost:8000/health", timeout=5)
        except Exception:  # nosec B110
            pass
        time.sleep(60)

def _start_keepalive():
    t = threading.Thread(target=_keepalive_loop, daemon=True, name="keepalive")
    t.start()

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")
_DELAY = 0.12 if NCBI_API_KEY else 0.38


# ─── Shared state (exposed to API) ──────────────────────────────────────────
#
# Execution priority — QUALITY OVER VOLUME:
#   M1 = Clean corpus          (always runs, SQL cleanup only)
#   M2 = Authoritative corpus  (MANDATORY — evidence hierarchy & guideline density)
#   M3 = Globally usable corpus (BLOCKED until multilang retrieval strategy is fixed)
#   M4 = Broad & defensible corpus (runs after M3 is stable)
#   M5 = Aesthetic medicine deep-dive + recency sweep + patient safety data
#
# IMPORTANT: M2 is NEVER skipped because of corpus size.
#   M2 is about corpus SHAPE and evidence quality, not document count.
#
# IMPORTANT: M3 MUST NOT run until:
#   1. M1 is completed
#   2. M2 is completed
#   3. multilang_retrieval_fixed flag is set via the admin API
#      (multilingual success = language detection + translate-to-English retrieval
#       + answer translation — NOT pretending the corpus is natively multilingual)
#
# IMPORTANT: guideline and consensus documents must be explicitly prioritised
#   in ranking. M2 exists to guarantee minimum guideline density.
_state: dict = {
    # Runtime
    "running": False, "started_at": None, "stop_requested": False,
    "milestone": 0, "milestone_label": "Not started",
    "docs_start": 0, "docs_inserted": 0, "docs_skipped": 0, "docs_failed": 0,
    "queries_done": 0, "queries_total": 0,
    "current_db_count": 0, "last_query": "", "quality_op": "", "error": None,
    # ── Phase completion flags (persisted) ──────────────────────────────────
    "m1_completed": False,   # M1 = Clean corpus          (SQL cleanup)
    "m2_completed": False,   # M2 = Authoritative corpus  (guideline ingestion)
    "m3_completed": False,   # M3 = Globally usable       (multilingual ingestion)
    "m4_completed": False,   # M4 = Broad & defensible    (full sweep)
    "m5_completed": False,   # M5 = Aesthetic deep-dive   (specialty + recency + safety)
    # ── Operational policy flags (persisted) ─────────────────────────────────
    # These represent external readiness conditions that must be confirmed by
    # an admin before certain phases are allowed to proceed.
    #
    # multilang_retrieval_fixed:
    #   M3 is hard-BLOCKED until this is True.
    #   Must be set after confirming: language detection works, translate-to-English
    #   retrieval is live, and answer translation is live.
    "multilang_retrieval_fixed": False,
    #
    # guideline_priority_enabled:
    #   Controls whether the retrieval layer explicitly boosts guidelines/consensus
    #   documents in ranking. M4 emits a warning if this is False because running
    #   the broad sweep without ranking improvements risks burying high-quality docs.
    "guideline_priority_enabled": False,
    #
    # corpus_cleanup_verified:
    #   Confirms that M1 quality results have been reviewed (mislabeled docs fixed,
    #   evidence levels spot-checked). M2 strongly recommends this before starting.
    "corpus_cleanup_verified": False,
    # ── Resumability (persisted) ──────────────────────────────────────────────
    "current_phase": 0,
    "current_query_index": 0,
    "last_run_at": None,
    # ── Recommendation ────────────────────────────────────────────────────────
    "next_recommended_phase": 1,
    "next_recommended_action": "Run M1 corpus cleanup",
}
_lock = threading.Lock()

# Keys that survive a server restart (written to PROGRESS_FILE)
_PERSIST_KEYS = [
    "m1_completed", "m2_completed", "m3_completed", "m4_completed", "m5_completed",
    "multilang_retrieval_fixed", "guideline_priority_enabled", "corpus_cleanup_verified",
    "current_phase", "current_query_index", "last_run_at",
]


def _save_progress() -> None:
    """Persist completion flags and query index to disk."""
    try:
        data = {k: _state[k] for k in _PERSIST_KEYS}
        PROGRESS_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        logger.warning(f"[progress] Could not save: {e}")


def _load_progress() -> None:
    """Restore completion flags and policy flags from disk, then refresh recommendation."""
    try:
        if PROGRESS_FILE.exists():
            data = json.loads(PROGRESS_FILE.read_text())
            for k in _PERSIST_KEYS:
                if k in data:
                    _state[k] = data[k]
            logger.info(
                f"[progress] Loaded — "
                f"M1={_state['m1_completed']} M2={_state['m2_completed']} "
                f"M3={_state['m3_completed']} M4={_state['m4_completed']} "
                f"M5={_state['m5_completed']} | "
                f"policy: multilang_fixed={_state['multilang_retrieval_fixed']} "
                f"guideline_priority={_state['guideline_priority_enabled']} "
                f"cleanup_verified={_state['corpus_cleanup_verified']} | "
                f"resume: phase={_state['current_phase']} qi={_state['current_query_index']}"
            )
    except Exception as e:
        logger.warning(f"[progress] Could not load: {e}")
    # Refresh recommendation immediately based on loaded flags
    rec = _compute_next_recommended()
    _state["next_recommended_phase"] = rec.phase
    _state["next_recommended_action"] = rec.action


# ─── Recommendation engine ───────────────────────────────────────────────────

class PhaseRecommendation:
    """Structured output from _compute_next_recommended()."""
    def __init__(self, phase: int, action: str, blocked_by: str = ""):
        self.phase = phase          # 0=all done, 1-5=run that phase, 99=external action needed
        self.action = action        # human-readable instruction
        self.blocked_by = blocked_by  # what is preventing automatic progress


def _compute_next_recommended() -> PhaseRecommendation:
    """
    Determine what the engine should do next, taking into account both
    phase completion flags and operational policy flags.

    Decision tree (priority order):
      1. M1 not completed            → run M1 (corpus cleanup)
      2. M2 not completed            → run M2 (guideline ingestion)
         └─ warn if corpus_cleanup_verified is False
      3. guideline_priority not set  → external action: enable guideline ranking
         (do not proceed to M3/M4 until ranking is improved)
      4. multilang_retrieval not fixed → external action: fix retrieval strategy
         (M3 is hard-blocked here)
      5. M3 not completed            → run M3 (multilingual ingestion)
      6. M4 not completed            → run M4 (broad sweep)
         └─ warn if guideline_priority_enabled is False (should have been set by step 3)
      7. M5 not completed            → run M5 (aesthetic deep-dive + recency + safety)
      8. All done                    → no action needed
    """
    s = _state  # shorthand

    # Step 1 — M1 must run first
    if not s["m1_completed"]:
        return PhaseRecommendation(
            phase=1,
            action="Run M1 corpus cleanup (assigns evidence levels, audits doc types).",
        )

    # Step 2 — M2 is mandatory; never skip due to corpus size
    if not s["m2_completed"]:
        warning = ""
        if not s["corpus_cleanup_verified"]:
            warning = (
                " WARNING: corpus_cleanup_verified is False — it is strongly recommended "
                "to review M1 results (spot-check evidence levels, fix mislabeled docs) "
                "before running M2. Set corpus_cleanup_verified via the admin API when ready."
            )
        return PhaseRecommendation(
            phase=2,
            action=f"Run M2 guideline-first ingestion (MANDATORY for evidence hierarchy).{warning}",
        )

    # Step 3 — Retrieval must be improved before adding more docs
    if not s["guideline_priority_enabled"]:
        return PhaseRecommendation(
            phase=99,
            action=(
                "External action required: enable guideline priority in the retrieval layer. "
                "Guideline and consensus documents must be explicitly boosted in ranking "
                "before M3/M4 ingestion, otherwise high-quality docs get buried. "
                "Once done, call POST /api/mass-upload/set-policy with guideline_priority_enabled=true."
            ),
            blocked_by="guideline_priority_enabled=false",
        )

    # Step 4 — Multilingual retrieval must be fixed before M3
    if not s["multilang_retrieval_fixed"]:
        return PhaseRecommendation(
            phase=99,
            action=(
                "External action required: fix multilingual retrieval strategy. "
                "Correct approach: language detection + translate-to-English retrieval + "
                "answer translation back to user language. "
                "Do NOT run M3 against a ~99% English corpus with broken multilang retrieval. "
                "Once done, call POST /api/mass-upload/set-policy with multilang_retrieval_fixed=true."
            ),
            blocked_by="multilang_retrieval_fixed=false",
        )

    # Step 5 — M3 multilingual ingestion
    if not s["m3_completed"]:
        return PhaseRecommendation(
            phase=3,
            action="Run M3 multilingual ingestion (retrieval confirmed fixed, guideline priority enabled).",
        )

    # Step 6 — M4 broad sweep (warn if guideline priority wasn't set — belt-and-suspenders)
    if not s["m4_completed"]:
        warning = ""
        if not s["guideline_priority_enabled"]:
            warning = (
                " WARNING: guideline_priority_enabled is False — running M4 without "
                "retrieval ranking improvements risks burying high-quality guideline docs "
                "under the broad sweep volume."
            )
        return PhaseRecommendation(
            phase=4,
            action=f"Run M4 broad & defensible corpus sweep.{warning}",
        )

    # Step 7 — M5 aesthetic medicine deep-dive + recency + safety
    if not s["m5_completed"]:
        return PhaseRecommendation(
            phase=5,
            action=(
                "Run M5 — Aesthetic Medicine Deep-Dive: high-granularity subspecialty queries, "
                "2023–2025 recency sweep, patient safety & adverse event data, energy-based "
                "devices, biostimulators, anatomy for aesthetics, and psychosocial outcomes. "
                "Target: 1,500,000 documents."
            ),
        )

    # Step 8 — All phases done
    return PhaseRecommendation(
        phase=0,
        action="All phases complete. Corpus is at 1.5M target.",
    )


def _finalise() -> None:
    """Mark engine as no longer running, compute recommendation, update label."""
    final = current_doc_count()
    rec = _compute_next_recommended()
    with _lock:
        _state["running"] = False
        _state["current_db_count"] = final
        _state["next_recommended_phase"] = rec.phase
        _state["next_recommended_action"] = rec.action
        if rec.phase == 0:
            _state["milestone_label"] = f"Complete — {final:,} documents"
        elif rec.phase == 99:
            _state["milestone_label"] = f"Waiting for external action — {rec.blocked_by}"
        elif rec.phase == 3 and not _state["multilang_retrieval_fixed"]:
            _state["milestone_label"] = "M3 BLOCKED — fix multilingual retrieval first"
    _save_progress()
    logger.info(
        f"[upload] Engine stopped. docs={final:,} | "
        f"next_phase={rec.phase} | action={rec.action[:80]}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1 QUERIES — Prioritised by evidence strength (guideline-first)
# ═══════════════════════════════════════════════════════════════════════════
PHASE2_QUERIES: List[Tuple[str, str, str]] = [
    # ── Clinical guidelines first ──────────────────────────────────────────
    ("aesthetic_medicine", "Guideline", '"practice guideline"[pt] AND (dermal filler OR botulinum toxin OR aesthetic)'),
    ("aesthetic_medicine", "Guideline", '"consensus"[Title/Abstract] AND (filler OR botulinum OR aesthetic) AND (injection OR treatment)'),
    ("aesthetic_medicine", "Guideline", '"guideline"[Title/Abstract] AND (aesthetic medicine OR cosmetic dermatology)'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND cardiology'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND oncology'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND (diabetes OR endocrinology)'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND psychiatry'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND (rheumatology OR rheumatoid)'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND neurology'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND dermatology'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND (gastroenterology OR liver)'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND (pulmonology OR asthma OR COPD)'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND nephrology'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND (orthopedics OR surgery)'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND (infectious disease OR sepsis)'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND (obstetrics OR gynecology)'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND pediatrics'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND hematology'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND ophthalmology'),
    ("medicine",           "Guideline", '"practice guideline"[pt] AND (pain OR analgesia)'),
    # ── Systematic reviews & meta-analyses ────────────────────────────────
    ("aesthetic_medicine", "Review", '"systematic review"[pt] AND (dermal filler OR botulinum OR hyaluronic acid OR aesthetic)'),
    ("aesthetic_medicine", "Review", '"meta-analysis"[pt] AND (dermal filler OR botulinum OR laser OR aesthetic medicine)'),
    ("medicine",           "Review", '"systematic review"[pt] AND (randomized controlled trial) AND 2020:2025[PDAT]'),
    ("medicine",           "Review", '"meta-analysis"[pt] AND (cardiovascular OR cardiac) AND 2020:2025[PDAT]'),
    ("medicine",           "Review", '"meta-analysis"[pt] AND (cancer OR tumor OR oncology) AND 2020:2025[PDAT]'),
    ("medicine",           "Review", '"meta-analysis"[pt] AND (diabetes OR insulin OR HbA1c) AND 2020:2025[PDAT]'),
    ("medicine",           "Review", '"meta-analysis"[pt] AND (depression OR anxiety OR mental health) AND 2020:2025[PDAT]'),
    ("medicine",           "Review", '"Cochrane Database Syst Rev"[Journal]'),
    ("medicine",           "Review", '"systematic review"[pt] AND (immunotherapy OR checkpoint inhibitor)'),
    ("medicine",           "Review", '"systematic review"[pt] AND (antibiotic resistance OR sepsis)'),
    ("medicine",           "Review", '"systematic review"[pt] AND (COVID-19 OR SARS-CoV-2)'),
    # ── High-impact RCTs ─────────────────────────────────────────────────
    ("aesthetic_medicine", "RCT", '"randomized controlled trial"[pt] AND (hyaluronic acid OR botulinum toxin OR filler)'),
    ("medicine",           "RCT", '"randomized controlled trial"[pt] AND (cancer OR tumor) AND 2022:2025[PDAT]'),
    ("medicine",           "RCT", '"randomized controlled trial"[pt] AND (heart failure OR atrial fibrillation) AND 2022:2025[PDAT]'),
    ("medicine",           "RCT", '"randomized controlled trial"[pt] AND (diabetes OR GLP-1 OR SGLT2) AND 2022:2025[PDAT]'),
    ("medicine",           "RCT", '"randomized controlled trial"[pt] AND (immunotherapy OR biologics) AND 2022:2025[PDAT]'),
    # ── Core aesthetic medicine ───────────────────────────────────────────
    ("aesthetic_medicine", "Injectables",    '"hyaluronic acid"[Title/Abstract] AND (filler OR injection OR dermal)'),
    ("aesthetic_medicine", "Injectables",    '"botulinum toxin"[Title/Abstract] AND (aesthetic OR cosmetic OR wrinkle)'),
    ("aesthetic_medicine", "Injectables",    '"dermal filler"[Title/Abstract]'),
    ("aesthetic_medicine", "Injectables",    '"vascular occlusion"[Title/Abstract] AND filler'),
    ("aesthetic_medicine", "Injectables",    '"hyaluronidase"[Title/Abstract]'),
    ("aesthetic_medicine", "Injectables",    '"lip augmentation"[Title/Abstract]'),
    ("aesthetic_medicine", "Injectables",    '"tear trough"[Title/Abstract]'),
    ("aesthetic_medicine", "Injectables",    '"nasolabial fold"[Title/Abstract] AND filler'),
    ("aesthetic_medicine", "Injectables",    '"collagen stimulator"[Title/Abstract]'),
    ("aesthetic_medicine", "Injectables",    '"poly-L-lactic acid"[Title/Abstract]'),
    ("aesthetic_medicine", "Injectables",    '"calcium hydroxylapatite"[Title/Abstract]'),
    ("aesthetic_medicine", "Energy Devices", '"laser skin"[Title/Abstract] OR "laser resurfacing"[Title/Abstract]'),
    ("aesthetic_medicine", "Energy Devices", '"radiofrequency"[Title/Abstract] AND (skin OR aesthetic OR tightening)'),
    ("aesthetic_medicine", "Energy Devices", '"intense pulsed light"[Title/Abstract] OR "IPL"[Title/Abstract]'),
    ("aesthetic_medicine", "Energy Devices", '"HIFU"[Title/Abstract] AND (skin OR body)'),
    ("aesthetic_medicine", "Energy Devices", '"picosecond laser"[Title/Abstract]'),
    ("aesthetic_medicine", "Body Contouring","\"cryolipolysis\"[Title/Abstract] OR \"CoolSculpting\"[Title/Abstract]"),
    ("aesthetic_medicine", "Body Contouring","\"deoxycholic acid\"[Title/Abstract] AND (submental OR chin)"),
    ("aesthetic_medicine", "Skin Procedures","\"microneedling\"[Title/Abstract] OR \"microneedle\"[Title/Abstract]"),
    ("aesthetic_medicine", "Skin Procedures","\"chemical peel\"[Title/Abstract]"),
    ("aesthetic_medicine", "Skin Procedures","\"platelet rich plasma\"[Title/Abstract] AND (skin OR aesthetic OR hair)"),
    ("aesthetic_medicine", "Skin Procedures","\"exosome\"[Title/Abstract] AND (skin OR hair OR aesthetic)"),
    ("aesthetic_medicine", "Skin Procedures","\"skin booster\"[Title/Abstract]"),
    ("aesthetic_medicine", "Skin Procedures","\"polynucleotide\"[Title/Abstract] AND skin"),
    ("aesthetic_medicine", "Skin Procedures","\"collagen induction therapy\"[Title/Abstract]"),
    # ── Dermatology deep ─────────────────────────────────────────────────
    ("medicine", "Dermatology", '"melasma"[Title/Abstract] AND treatment'),
    ("medicine", "Dermatology", '"acne"[Title/Abstract] AND (treatment OR therapy) AND (randomized OR review)'),
    ("medicine", "Dermatology", '"psoriasis"[Title/Abstract] AND (biologics OR treatment)'),
    ("medicine", "Dermatology", '"atopic dermatitis"[Title/Abstract] AND (dupilumab OR biologics OR treatment)'),
    ("medicine", "Dermatology", '"rosacea"[Title/Abstract] AND treatment'),
    ("medicine", "Dermatology", '"vitiligo"[Title/Abstract] AND treatment'),
    ("medicine", "Dermatology", '"melanoma"[Title/Abstract] AND (immunotherapy OR treatment)'),
    ("medicine", "Dermatology", '"alopecia"[Title/Abstract] AND (JAK inhibitor OR treatment)'),
    ("medicine", "Dermatology", '"wound healing"[Title/Abstract] AND (skin OR dermatology)'),
    ("medicine", "Dermatology", '"hidradenitis suppurativa"[Title/Abstract] AND treatment'),
    # ── Cardiology ───────────────────────────────────────────────────────
    ("medicine", "Cardiology", '"heart failure"[Title/Abstract] AND (treatment OR management)'),
    ("medicine", "Cardiology", '"atrial fibrillation"[Title/Abstract] AND (treatment OR ablation)'),
    ("medicine", "Cardiology", '"coronary artery disease"[Title/Abstract] AND (stent OR intervention)'),
    ("medicine", "Cardiology", '"hypertension"[Title/Abstract] AND (antihypertensive OR guidelines)'),
    ("medicine", "Cardiology", '"myocardial infarction"[Title/Abstract] AND (treatment OR outcome)'),
    ("medicine", "Cardiology", '"stroke"[Title/Abstract] AND (prevention OR thrombolysis OR thrombectomy)'),
    ("medicine", "Cardiology", '"SGLT2 inhibitor"[Title/Abstract] AND heart failure'),
    ("medicine", "Cardiology", '"GLP-1 receptor agonist"[Title/Abstract] AND cardiovascular'),
    # ── Oncology ─────────────────────────────────────────────────────────
    ("medicine", "Oncology", '"breast cancer"[Title/Abstract] AND (chemotherapy OR immunotherapy OR treatment)'),
    ("medicine", "Oncology", '"lung cancer"[Title/Abstract] AND (immunotherapy OR targeted therapy)'),
    ("medicine", "Oncology", '"colorectal cancer"[Title/Abstract] AND (chemotherapy OR treatment)'),
    ("medicine", "Oncology", '"prostate cancer"[Title/Abstract] AND (treatment OR hormonal)'),
    ("medicine", "Oncology", '"immunotherapy"[Title/Abstract] AND (cancer OR tumor) AND 2022:2025[PDAT]'),
    ("medicine", "Oncology", '"checkpoint inhibitor"[Title/Abstract] AND cancer AND 2022:2025[PDAT]'),
    ("medicine", "Oncology", '"CAR-T cell"[Title/Abstract] AND cancer'),
    ("medicine", "Oncology", '"cancer biomarker"[Title/Abstract] AND (diagnosis OR prognosis)'),
    # ── Remaining specialties ─────────────────────────────────────────────
    ("medicine", "Endocrinology",       '"type 2 diabetes"[Title/Abstract] AND (GLP-1 OR SGLT2 OR treatment)'),
    ("medicine", "Endocrinology",       '"obesity"[Title/Abstract] AND (semaglutide OR tirzepatide OR bariatric)'),
    ("medicine", "Endocrinology",       '"thyroid"[Title/Abstract] AND (hypothyroidism OR treatment)'),
    ("medicine", "Neurology",           '"multiple sclerosis"[Title/Abstract] AND (treatment OR disease modifying)'),
    ("medicine", "Neurology",           '"Parkinson disease"[Title/Abstract] AND (treatment OR management)'),
    ("medicine", "Neurology",           '"migraine"[Title/Abstract] AND (CGRP OR prevention)'),
    ("medicine", "Psychiatry",          '"depression"[Title/Abstract] AND (antidepressant OR treatment OR SSRI)'),
    ("medicine", "Psychiatry",          '"anxiety disorder"[Title/Abstract] AND (treatment OR CBT)'),
    ("medicine", "Rheumatology",        '"rheumatoid arthritis"[Title/Abstract] AND (biologic OR DMARD)'),
    ("medicine", "Rheumatology",        '"osteoarthritis"[Title/Abstract] AND (injection OR treatment)'),
    ("medicine", "Gastroenterology",    '"inflammatory bowel disease"[Title/Abstract] AND (biologics OR treatment)'),
    ("medicine", "Pulmonology",         '"COPD"[Title/Abstract] AND (treatment OR exacerbation)'),
    ("medicine", "Pulmonology",         '"asthma"[Title/Abstract] AND (biologics OR treatment)'),
    ("medicine", "Infectious Disease",  '"antibiotic resistance"[Title/Abstract] AND treatment'),
    ("medicine", "Infectious Disease",  '"sepsis"[Title/Abstract] AND (management OR outcome)'),
    ("medicine", "Infectious Disease",  '"COVID-19"[Title/Abstract] AND (treatment OR outcome) AND 2022:2025[PDAT]'),
    ("medicine", "Nephrology",          '"chronic kidney disease"[Title/Abstract] AND (treatment OR progression)'),
    ("medicine", "Orthopedics",         '"hip replacement"[Title/Abstract] AND (outcome OR complication)'),
    ("medicine", "Orthopedics",         '"knee replacement"[Title/Abstract] AND (outcome OR complication)'),
    ("medicine", "Gynecology",          '"endometriosis"[Title/Abstract] AND (treatment OR surgery)'),
    ("medicine", "Gynecology",          '"menopause"[Title/Abstract] AND (hormone therapy OR management)'),
    ("medicine", "Ophthalmology",       '"age-related macular degeneration"[Title/Abstract] AND (anti-VEGF OR treatment)'),
    ("medicine", "Pediatrics",          '"pediatric"[Title/Abstract] AND (infection OR antibiotic OR outcome)'),
    ("medicine", "Surgery",             '"laparoscopic"[Title/Abstract] AND (outcome OR complication)'),
    ("medicine", "Emergency Medicine",  '"septic shock"[Title/Abstract] AND (vasopressor OR outcome)'),
    ("medicine", "Pain Medicine",       '"chronic pain"[Title/Abstract] AND (treatment OR opioid)'),
    ("medicine", "Hematology",          '"thrombosis"[Title/Abstract] AND (anticoagulation OR treatment)'),
    ("dental_medicine", "Dentistry",    '"dental implant"[Title/Abstract] AND (outcome OR complication)'),
    ("dental_medicine", "Dentistry",    '"periodontal"[Title/Abstract] AND treatment'),
    ("general_medicine", "Internal Medicine", '"clinical guideline"[Title/Abstract] AND 2022:2025[PDAT]'),
    ("general_medicine", "Internal Medicine", '"artificial intelligence"[Title/Abstract] AND (diagnosis OR clinical)'),
]


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 3 QUERIES — Multilingual (25 languages)
# ═══════════════════════════════════════════════════════════════════════════
LANG_FILTERS = {
    "fr": "fre[la]", "es": "spa[la]", "de": "ger[la]", "it": "ita[la]",
    "pt": "por[la]", "ja": "jpn[la]", "zh": "chi[la]", "ar": "ara[la]",
    "ko": "kor[la]", "ru": "rus[la]", "nl": "dut[la]", "tr": "tur[la]",
    "pl": "pol[la]", "sv": "swe[la]", "da": "dan[la]", "fi": "fin[la]",
    "no": "nor[la]", "cs": "cze[la]", "hu": "hun[la]", "ro": "rum[la]",
}
MULTILANG_TOPICS = [
    ("aesthetic_medicine", "Injectables",    "hyaluronic acid filler injection"),
    ("aesthetic_medicine", "Injectables",    "botulinum toxin aesthetic"),
    ("aesthetic_medicine", "Energy Devices", "laser skin rejuvenation"),
    ("aesthetic_medicine", "Skin Procedures","platelet rich plasma"),
    ("medicine",           "Dermatology",    "acne treatment dermatology"),
    ("medicine",           "Cardiology",     "heart failure treatment"),
    ("medicine",           "Oncology",       "cancer chemotherapy immunotherapy"),
    ("medicine",           "Endocrinology",  "diabetes type 2 treatment"),
    ("medicine",           "Neurology",      "multiple sclerosis treatment"),
    ("medicine",           "Psychiatry",     "depression antidepressant"),
    ("medicine",           "Rheumatology",   "rheumatoid arthritis biologic"),
    ("medicine",           "Gastroenterology","inflammatory bowel disease"),
    ("medicine",           "Pulmonology",    "COPD asthma treatment"),
    ("medicine",           "Gynecology",     "breast cancer treatment"),
    ("medicine",           "Internal Medicine","clinical guidelines 2024"),
]

def _build_multilang_queries() -> List[Tuple[str, str, str]]:
    queries = []
    for lang_code, lang_filter in LANG_FILTERS.items():
        for domain, specialty, topic in MULTILANG_TOPICS:
            q = f'({topic}[Title/Abstract]) AND {lang_filter}'
            queries.append((domain, specialty, q))
    return queries

PHASE3_QUERIES = _build_multilang_queries()


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 4 QUERIES — Broad coverage sweep to reach 1M
# ═══════════════════════════════════════════════════════════════════════════
_year_ranges = [
    "2000:2004", "2005:2009", "2010:2014", "2015:2018", "2019:2021", "2022:2025",
]
_broad_topics = [
    ("medicine", "Internal Medicine",  '"clinical trial"[pt]', ),
    ("medicine", "Oncology",           "cancer treatment review"),
    ("medicine", "Cardiology",         "cardiovascular disease outcome"),
    ("medicine", "Neurology",          "neurological disorder treatment"),
    ("medicine", "Endocrinology",      "metabolic disease management"),
    ("medicine", "Psychiatry",         "mental health intervention"),
    ("medicine", "Gastroenterology",   "gastrointestinal disorder treatment"),
    ("medicine", "Pulmonology",        "respiratory disease treatment"),
    ("medicine", "Rheumatology",       "inflammatory disease biologic"),
    ("medicine", "Infectious Disease", "antimicrobial treatment outcome"),
    ("medicine", "Nephrology",         "kidney disease progression"),
    ("medicine", "Orthopedics",        "musculoskeletal treatment outcome"),
    ("medicine", "Gynecology",         "reproductive medicine treatment"),
    ("medicine", "Ophthalmology",      "retinal disease treatment"),
    ("medicine", "Pediatrics",         "child health intervention"),
    ("medicine", "Surgery",            "surgical outcome complication"),
    ("medicine", "Emergency Medicine", "critical care outcome"),
    ("medicine", "Pain Medicine",      "pain management intervention"),
    ("medicine", "Hematology",         "blood disorder treatment"),
    ("medicine", "Dermatology",        "skin disease treatment review"),
    ("aesthetic_medicine", "Aesthetic Medicine", "cosmetic procedure outcome safety"),
    ("dental_medicine",    "Dentistry",          "dental treatment outcome"),
    ("general_medicine",   "Internal Medicine",  "evidence-based medicine review"),
]
def _build_phase4_queries() -> List[Tuple[str, str, str]]:
    queries = []
    for yr in _year_ranges:
        for domain, specialty, topic in _broad_topics:
            if topic.startswith('"') and topic.endswith('[pt]'):
                q = f'{topic} AND {yr}[PDAT]'
            else:
                q = f'({topic}[Title/Abstract]) AND {yr}[PDAT]'
            queries.append((domain, specialty, q))
    return queries

PHASE4_QUERIES = _build_phase4_queries()


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 5 QUERIES — Aesthetic Medicine Deep-Dive, Recency & Safety (→1.5M)
# ═══════════════════════════════════════════════════════════════════════════
#
# Strategy:
#   A) High-granularity injectable subspecialty queries
#   B) Energy-based devices — laser, RF, HIFU, cryolipolysis, ultrasound
#   C) Biostimulators, collagen stimulators, regenerative aesthetics
#   D) Anatomy for aesthetics — danger zones, vascular territory, cadaveric studies
#   E) Patient safety — adverse events, complications, post-market surveillance
#   F) Hair restoration — FUE, FUT, PRP, scalp health
#   G) Body contouring — surgical and non-surgical fat reduction
#   H) Psychosocial outcomes — patient satisfaction, BDD, quality of life
#   I) 2023–2025 recency sweep — newest publications in all aesthetic domains
#   J) Skin science — collagen, fibroblasts, wound healing, photoageing
#   K) Clinical skills — injection technique, cannula vs needle, depth control

PHASE5_QUERIES: List[Tuple[str, str, str]] = [
    # ── A: Injectables — granular subspecialties ──────────────────────────
    ("aesthetic_medicine", "Injectables", '"hyaluronic acid"[Title/Abstract] AND (lip filler OR lip augmentation)'),
    ("aesthetic_medicine", "Injectables", '"hyaluronic acid"[Title/Abstract] AND (tear trough OR periorbital OR under-eye)'),
    ("aesthetic_medicine", "Injectables", '"hyaluronic acid"[Title/Abstract] AND (nasolabial OR marionette OR jawline)'),
    ("aesthetic_medicine", "Injectables", '"hyaluronic acid"[Title/Abstract] AND (rhinoplasty OR nose OR non-surgical rhinoplasty)'),
    ("aesthetic_medicine", "Injectables", '"hyaluronic acid"[Title/Abstract] AND (cheek OR malar OR midface)'),
    ("aesthetic_medicine", "Injectables", '"hyaluronic acid"[Title/Abstract] AND (temple OR temporal fossa)'),
    ("aesthetic_medicine", "Injectables", '"hyaluronic acid"[Title/Abstract] AND (chin OR prejowl OR mandible)'),
    ("aesthetic_medicine", "Injectables", '"dermal filler"[Title/Abstract] AND (complication OR adverse event OR safety)'),
    ("aesthetic_medicine", "Injectables", '"dermal filler"[Title/Abstract] AND (vascular occlusion OR embolism OR blindness)'),
    ("aesthetic_medicine", "Injectables", '"filler"[Title/Abstract] AND (granuloma OR nodule OR biofilm)'),
    ("aesthetic_medicine", "Injectables", '"botulinum toxin"[Title/Abstract] AND (glabellar OR frontalis OR forehead)'),
    ("aesthetic_medicine", "Injectables", '"botulinum toxin"[Title/Abstract] AND (masseter OR bruxism OR jaw slimming)'),
    ("aesthetic_medicine", "Injectables", '"botulinum toxin"[Title/Abstract] AND (crow\'s feet OR periorbital OR lateral canthus)'),
    ("aesthetic_medicine", "Injectables", '"botulinum toxin"[Title/Abstract] AND (neck OR platysma OR nefertiti)'),
    ("aesthetic_medicine", "Injectables", '"botulinum toxin"[Title/Abstract] AND (ptosis OR diplopia OR complication)'),
    ("aesthetic_medicine", "Injectables", '"botulinum toxin"[Title/Abstract] AND (dose OR unit OR dilution OR reconstitution)'),
    ("aesthetic_medicine", "Injectables", '"botulinum toxin"[Title/Abstract] AND (hyperhidrosis OR axillary OR sweating)'),
    ("aesthetic_medicine", "Injectables", '"cannula"[Title/Abstract] AND (filler OR injection OR aesthetic)'),
    ("aesthetic_medicine", "Injectables", '"microcannula"[Title/Abstract] AND (safety OR bruising OR technique)'),
    ("aesthetic_medicine", "Injectables", '"injection technique"[Title/Abstract] AND (aesthetic OR cosmetic OR filler)'),
    ("aesthetic_medicine", "Injectables", '"hyaluronidase"[Title/Abstract] AND (filler dissolution OR reversal OR vascular)'),
    ("aesthetic_medicine", "Injectables", '"calcium hydroxylapatite"[Title/Abstract] AND (aesthetic OR filler OR Radiesse)'),
    ("aesthetic_medicine", "Injectables", '"poly-L-lactic acid"[Title/Abstract] AND (aesthetic OR Sculptra OR collagen)'),
    ("aesthetic_medicine", "Injectables", '"polymethylmethacrylate"[Title/Abstract] AND (aesthetic OR permanent filler)'),
    ("aesthetic_medicine", "Injectables", '"fat grafting"[Title/Abstract] AND (facial OR lipofilling OR lipostructure)'),
    # ── B: Energy-based devices ───────────────────────────────────────────
    ("aesthetic_medicine", "Energy Devices", '"laser"[Title/Abstract] AND (skin resurfacing OR ablative OR fractional)'),
    ("aesthetic_medicine", "Energy Devices", '"fractional laser"[Title/Abstract] AND (CO2 OR erbium OR rejuvenation)'),
    ("aesthetic_medicine", "Energy Devices", '"non-ablative"[Title/Abstract] AND (laser OR skin rejuvenation OR collagen)'),
    ("aesthetic_medicine", "Energy Devices", '"radiofrequency"[Title/Abstract] AND (skin tightening OR aesthetic OR RF)'),
    ("aesthetic_medicine", "Energy Devices", '"radiofrequency microneedling"[Title/Abstract] AND (skin OR collagen)'),
    ("aesthetic_medicine", "Energy Devices", '"HIFU"[Title/Abstract] AND (skin laxity OR face lift OR ultrasound)'),
    ("aesthetic_medicine", "Energy Devices", '"high intensity focused ultrasound"[Title/Abstract] AND aesthetic'),
    ("aesthetic_medicine", "Energy Devices", '"cryolipolysis"[Title/Abstract] AND (fat reduction OR CoolSculpting OR outcome)'),
    ("aesthetic_medicine", "Energy Devices", '"intense pulsed light"[Title/Abstract] AND (IPL OR skin OR pigmentation)'),
    ("aesthetic_medicine", "Energy Devices", '"pulsed dye laser"[Title/Abstract] AND (vascular OR rosacea OR treatment)'),
    ("aesthetic_medicine", "Energy Devices", '"Nd:YAG"[Title/Abstract] AND (aesthetic OR laser OR skin)'),
    ("aesthetic_medicine", "Energy Devices", '"photobiomodulation"[Title/Abstract] AND (skin OR wound healing OR LED)'),
    ("aesthetic_medicine", "Energy Devices", '"low-level laser therapy"[Title/Abstract] AND (aesthetic OR hair OR skin)'),
    ("aesthetic_medicine", "Energy Devices", '"body contouring"[Title/Abstract] AND (energy based OR device OR non-surgical)'),
    ("aesthetic_medicine", "Energy Devices", '"skin tightening"[Title/Abstract] AND (technology OR device OR outcome)'),
    ("aesthetic_medicine", "Energy Devices", '"electromagnetic"[Title/Abstract] AND (muscle stimulation OR EMSCULPT OR aesthetic)'),
    ("aesthetic_medicine", "Energy Devices", '"laser hair removal"[Title/Abstract] AND (outcome OR complication OR technique)'),
    ("aesthetic_medicine", "Energy Devices", '"tattoo removal"[Title/Abstract] AND (laser OR Q-switched OR outcome)'),
    ("aesthetic_medicine", "Energy Devices", '"picosecond laser"[Title/Abstract] AND (aesthetic OR pigmentation OR tattoo)'),
    # ── C: Biostimulators & regenerative aesthetics ───────────────────────
    ("aesthetic_medicine", "Regenerative Aesthetics", '"platelet rich plasma"[Title/Abstract] AND (skin OR facial OR rejuvenation)'),
    ("aesthetic_medicine", "Regenerative Aesthetics", '"PRP"[Title/Abstract] AND (aesthetic OR face OR collagen OR outcome)'),
    ("aesthetic_medicine", "Regenerative Aesthetics", '"platelet rich fibrin"[Title/Abstract] AND (aesthetic OR PRF OR skin)'),
    ("aesthetic_medicine", "Regenerative Aesthetics", '"exosome"[Title/Abstract] AND (skin OR aesthetic OR regeneration) AND 2020:2025[PDAT]'),
    ("aesthetic_medicine", "Regenerative Aesthetics", '"stem cell"[Title/Abstract] AND (aesthetic OR skin OR rejuvenation)'),
    ("aesthetic_medicine", "Regenerative Aesthetics", '"growth factor"[Title/Abstract] AND (skin OR aesthetic OR wound healing)'),
    ("aesthetic_medicine", "Regenerative Aesthetics", '"collagen stimulator"[Title/Abstract] AND (aesthetic OR biostimulator)'),
    ("aesthetic_medicine", "Regenerative Aesthetics", '"PLLA"[Title/Abstract] AND (aesthetic OR collagen OR skin)'),
    ("aesthetic_medicine", "Regenerative Aesthetics", '"calcium hydroxylapatite"[Title/Abstract] AND (biostimulator OR collagen)'),
    ("aesthetic_medicine", "Regenerative Aesthetics", '"polynucleotide"[Title/Abstract] AND (skin OR aesthetic OR PDRN)'),
    ("aesthetic_medicine", "Regenerative Aesthetics", '"skin booster"[Title/Abstract] AND (hyaluronic acid OR injectable OR outcome)'),
    ("aesthetic_medicine", "Regenerative Aesthetics", '"mesotherapy"[Title/Abstract] AND (skin OR aesthetic OR outcome)'),
    # ── D: Anatomy for aesthetics ─────────────────────────────────────────
    ("aesthetic_medicine", "Anatomy", '"facial anatomy"[Title/Abstract] AND (injection OR aesthetic OR danger zone)'),
    ("aesthetic_medicine", "Anatomy", '"facial artery"[Title/Abstract] AND (anatomy OR aesthetic OR injection)'),
    ("aesthetic_medicine", "Anatomy", '"angular artery"[Title/Abstract] AND (anatomy OR aesthetic OR filler)'),
    ("aesthetic_medicine", "Anatomy", '"supratrochlear artery"[Title/Abstract] AND (anatomy OR aesthetic)'),
    ("aesthetic_medicine", "Anatomy", '"ophthalmic artery"[Title/Abstract] AND (anatomy OR aesthetic OR injection)'),
    ("aesthetic_medicine", "Anatomy", '"danger zone"[Title/Abstract] AND (facial OR injection OR aesthetic)'),
    ("aesthetic_medicine", "Anatomy", '"facial vein"[Title/Abstract] AND (anatomy OR aesthetic OR injection)'),
    ("aesthetic_medicine", "Anatomy", '"retaining ligament"[Title/Abstract] AND (facial OR anatomy OR aesthetic)'),
    ("aesthetic_medicine", "Anatomy", '"fat compartment"[Title/Abstract] AND (facial OR anatomy OR filler)'),
    ("aesthetic_medicine", "Anatomy", '"cadaver"[Title/Abstract] AND (facial anatomy OR injection OR aesthetic)'),
    ("aesthetic_medicine", "Anatomy", '"cadaveric study"[Title/Abstract] AND (aesthetic OR injection OR filler)'),
    ("aesthetic_medicine", "Anatomy", '"SMAS"[Title/Abstract] AND (anatomy OR aesthetic OR lift)'),
    ("aesthetic_medicine", "Anatomy", '"superficial musculoaponeurotic"[Title/Abstract] AND (anatomy OR aesthetic)'),
    ("aesthetic_medicine", "Anatomy", '"periorbital anatomy"[Title/Abstract] AND (aesthetic OR injection OR blepharoplasty)'),
    ("aesthetic_medicine", "Anatomy", '"lip anatomy"[Title/Abstract] AND (aesthetic OR injection OR filler)'),
    # ── E: Patient safety & adverse events ───────────────────────────────
    ("aesthetic_medicine", "Safety", '"vascular occlusion"[Title/Abstract] AND (filler OR injection OR aesthetic)'),
    ("aesthetic_medicine", "Safety", '"blindness"[Title/Abstract] AND (filler OR aesthetic OR injection)'),
    ("aesthetic_medicine", "Safety", '"skin necrosis"[Title/Abstract] AND (filler OR aesthetic OR injection)'),
    ("aesthetic_medicine", "Safety", '"adverse event"[Title/Abstract] AND (aesthetic OR cosmetic OR filler OR botulinum)'),
    ("aesthetic_medicine", "Safety", '"complication"[Title/Abstract] AND (aesthetic OR cosmetic procedure OR outcome)'),
    ("aesthetic_medicine", "Safety", '"infection"[Title/Abstract] AND (filler OR aesthetic injection OR cosmetic)'),
    ("aesthetic_medicine", "Safety", '"biofilm"[Title/Abstract] AND (filler OR aesthetic OR injection)'),
    ("aesthetic_medicine", "Safety", '"allergy"[Title/Abstract] AND (filler OR botulinum toxin OR aesthetic)'),
    ("aesthetic_medicine", "Safety", '"anaphylaxis"[Title/Abstract] AND (aesthetic OR cosmetic OR injectable)'),
    ("aesthetic_medicine", "Safety", '"tyndall effect"[Title/Abstract] AND (filler OR aesthetic)'),
    ("aesthetic_medicine", "Safety", '"foreign body reaction"[Title/Abstract] AND (filler OR aesthetic OR cosmetic)'),
    ("aesthetic_medicine", "Safety", '"post-market surveillance"[Title/Abstract] AND (medical device OR aesthetic OR filler)'),
    ("aesthetic_medicine", "Safety", '"patient safety"[Title/Abstract] AND (aesthetic OR cosmetic procedure)'),
    ("aesthetic_medicine", "Safety", '"informed consent"[Title/Abstract] AND (aesthetic OR cosmetic OR plastic surgery)'),
    ("aesthetic_medicine", "Safety", '"delayed hypersensitivity"[Title/Abstract] AND (filler OR aesthetic OR hyaluronic)'),
    # ── F: Hair restoration ───────────────────────────────────────────────
    ("aesthetic_medicine", "Hair Restoration", '"follicular unit extraction"[Title/Abstract] AND (hair OR FUE OR outcome)'),
    ("aesthetic_medicine", "Hair Restoration", '"hair transplantation"[Title/Abstract] AND (FUE OR FUT OR outcome)'),
    ("aesthetic_medicine", "Hair Restoration", '"androgenetic alopecia"[Title/Abstract] AND (treatment OR PRP OR finasteride)'),
    ("aesthetic_medicine", "Hair Restoration", '"platelet rich plasma"[Title/Abstract] AND (hair loss OR alopecia OR scalp)'),
    ("aesthetic_medicine", "Hair Restoration", '"minoxidil"[Title/Abstract] AND (alopecia OR hair loss OR treatment)'),
    ("aesthetic_medicine", "Hair Restoration", '"finasteride"[Title/Abstract] AND (alopecia OR hair loss OR androgenetic)'),
    ("aesthetic_medicine", "Hair Restoration", '"scalp"[Title/Abstract] AND (mesotherapy OR injection OR aesthetic)'),
    ("aesthetic_medicine", "Hair Restoration", '"alopecia areata"[Title/Abstract] AND (treatment OR injection OR outcome)'),
    ("aesthetic_medicine", "Hair Restoration", '"low level laser"[Title/Abstract] AND (hair loss OR alopecia OR hair growth)'),
    ("aesthetic_medicine", "Hair Restoration", '"hair growth"[Title/Abstract] AND (clinical trial OR treatment OR intervention)'),
    # ── G: Body contouring ────────────────────────────────────────────────
    ("aesthetic_medicine", "Body Contouring", '"liposuction"[Title/Abstract] AND (outcome OR complication OR technique)'),
    ("aesthetic_medicine", "Body Contouring", '"tumescent liposuction"[Title/Abstract] AND (technique OR outcome OR safety)'),
    ("aesthetic_medicine", "Body Contouring", '"body contouring"[Title/Abstract] AND (non-surgical OR outcome OR satisfaction)'),
    ("aesthetic_medicine", "Body Contouring", '"fat reduction"[Title/Abstract] AND (non-invasive OR device OR outcome)'),
    ("aesthetic_medicine", "Body Contouring", '"abdominoplasty"[Title/Abstract] AND (outcome OR complication OR tummy tuck)'),
    ("aesthetic_medicine", "Body Contouring", '"Brazilian butt lift"[Title/Abstract] AND (fat grafting OR outcome OR safety)'),
    ("aesthetic_medicine", "Body Contouring", '"deoxycholic acid"[Title/Abstract] AND (submental OR fat OR Kybella)'),
    ("aesthetic_medicine", "Body Contouring", '"cryolipolysis"[Title/Abstract] AND (fat OR outcome OR paradoxical)'),
    ("aesthetic_medicine", "Body Contouring", '"injection lipolysis"[Title/Abstract] AND (outcome OR safety OR technique)'),
    # ── H: Psychosocial outcomes & patient selection ─────────────────────
    ("aesthetic_medicine", "Psychosocial", '"body dysmorphic disorder"[Title/Abstract] AND (aesthetic OR cosmetic OR screening)'),
    ("aesthetic_medicine", "Psychosocial", '"patient satisfaction"[Title/Abstract] AND (aesthetic OR cosmetic OR filler)'),
    ("aesthetic_medicine", "Psychosocial", '"quality of life"[Title/Abstract] AND (aesthetic OR cosmetic procedure OR outcome)'),
    ("aesthetic_medicine", "Psychosocial", '"self-esteem"[Title/Abstract] AND (aesthetic OR cosmetic OR appearance)'),
    ("aesthetic_medicine", "Psychosocial", '"psychological"[Title/Abstract] AND (aesthetic procedure OR cosmetic surgery OR outcome)'),
    ("aesthetic_medicine", "Psychosocial", '"patient selection"[Title/Abstract] AND (aesthetic OR cosmetic surgery OR criteria)'),
    ("aesthetic_medicine", "Psychosocial", '"aesthetic outcome measure"[Title/Abstract] AND (scale OR questionnaire OR GAIS)'),
    ("aesthetic_medicine", "Psychosocial", '"GAiS"[Title/Abstract] AND (aesthetic OR cosmetic OR scale OR outcome)'),
    ("aesthetic_medicine", "Psychosocial", '"FACE-Q"[Title/Abstract] AND (aesthetic OR cosmetic OR outcome OR satisfaction)'),
    # ── I: 2023–2025 recency sweep ────────────────────────────────────────
    ("aesthetic_medicine", "Recency", '"aesthetic medicine"[Title/Abstract] AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"cosmetic procedure"[Title/Abstract] AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"dermal filler"[Title/Abstract] AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"botulinum toxin"[Title/Abstract] AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"laser"[Title/Abstract] AND (aesthetic OR cosmetic) AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"radiofrequency"[Title/Abstract] AND (aesthetic OR skin) AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"platelet rich plasma"[Title/Abstract] AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"skin aging"[Title/Abstract] AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"facial rejuvenation"[Title/Abstract] AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"thread lift"[Title/Abstract] AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"artificial intelligence"[Title/Abstract] AND aesthetic AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"machine learning"[Title/Abstract] AND (aesthetic OR cosmetic OR skin) AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"exosome"[Title/Abstract] AND (skin OR aesthetic) AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"biostimulator"[Title/Abstract] AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"collagen stimulator"[Title/Abstract] AND 2023:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"vascular complication"[Title/Abstract] AND filler AND 2022:2025[PDAT]'),
    ("aesthetic_medicine", "Recency", '"adverse event"[Title/Abstract] AND aesthetic AND 2022:2025[PDAT]'),
    ("medicine",           "Recency", '"randomized controlled trial"[pt] AND aesthetic AND 2022:2025[PDAT]'),
    ("medicine",           "Recency", '"systematic review"[pt] AND aesthetic AND 2022:2025[PDAT]'),
    ("medicine",           "Recency", '"meta-analysis"[pt] AND (aesthetic OR cosmetic) AND 2022:2025[PDAT]'),
    # ── J: Skin science ───────────────────────────────────────────────────
    ("aesthetic_medicine", "Skin Science", '"collagen synthesis"[Title/Abstract] AND (skin OR fibroblast OR wound)'),
    ("aesthetic_medicine", "Skin Science", '"fibroblast"[Title/Abstract] AND (skin aging OR collagen OR aesthetic)'),
    ("aesthetic_medicine", "Skin Science", '"photoageing"[Title/Abstract] AND (treatment OR skin OR UV)'),
    ("aesthetic_medicine", "Skin Science", '"photoaging"[Title/Abstract] AND (mechanism OR treatment OR skin care)'),
    ("aesthetic_medicine", "Skin Science", '"skin barrier"[Title/Abstract] AND (aesthetic OR treatment OR microbiome)'),
    ("aesthetic_medicine", "Skin Science", '"wound healing"[Title/Abstract] AND (aesthetic OR laser OR injection)'),
    ("aesthetic_medicine", "Skin Science", '"matrix metalloproteinase"[Title/Abstract] AND (skin aging OR collagen)'),
    ("aesthetic_medicine", "Skin Science", '"retinol"[Title/Abstract] AND (skin OR aging OR collagen)'),
    ("aesthetic_medicine", "Skin Science", '"retinoid"[Title/Abstract] AND (photoaging OR acne OR skin)'),
    ("aesthetic_medicine", "Skin Science", '"vitamin C"[Title/Abstract] AND (skin OR aesthetic OR antioxidant)'),
    ("aesthetic_medicine", "Skin Science", '"hyaluronic acid"[Title/Abstract] AND (skin hydration OR moisturisation OR dermis)'),
    ("aesthetic_medicine", "Skin Science", '"melanin"[Title/Abstract] AND (pigmentation OR melasma OR treatment)'),
    ("aesthetic_medicine", "Skin Science", '"melasma"[Title/Abstract] AND (treatment OR laser OR topical)'),
    ("aesthetic_medicine", "Skin Science", '"acne"[Title/Abstract] AND (scarring OR treatment OR aesthetic)'),
    ("aesthetic_medicine", "Skin Science", '"rosacea"[Title/Abstract] AND (treatment OR laser OR IPL OR outcome)'),
    ("aesthetic_medicine", "Skin Science", '"psoriasis"[Title/Abstract] AND (biologic OR treatment OR outcome) AND 2022:2025[PDAT]'),
    ("aesthetic_medicine", "Skin Science", '"eczema"[Title/Abstract] AND (biologic OR dupilumab OR outcome) AND 2022:2025[PDAT]'),
    # ── K: Thread lifts & tissue mechanics ───────────────────────────────
    ("aesthetic_medicine", "Thread Lift", '"thread lift"[Title/Abstract] AND (outcome OR complication OR technique)'),
    ("aesthetic_medicine", "Thread Lift", '"PDO thread"[Title/Abstract] AND (aesthetic OR face lift OR outcome)'),
    ("aesthetic_medicine", "Thread Lift", '"polydioxanone"[Title/Abstract] AND (thread OR aesthetic OR lift)'),
    ("aesthetic_medicine", "Thread Lift", '"PLLA thread"[Title/Abstract] AND (aesthetic OR facial OR outcome)'),
    ("aesthetic_medicine", "Thread Lift", '"cog thread"[Title/Abstract] AND (face lift OR aesthetic OR technique)'),
    ("aesthetic_medicine", "Thread Lift", '"aptos thread"[Title/Abstract] AND (aesthetic OR outcome OR lift)'),
    # ── L: Surgical aesthetics foundations ───────────────────────────────
    ("aesthetic_medicine", "Surgical Aesthetics", '"facelift"[Title/Abstract] AND (outcome OR complication OR technique)'),
    ("aesthetic_medicine", "Surgical Aesthetics", '"rhytidectomy"[Title/Abstract] AND (outcome OR SMAS OR technique)'),
    ("aesthetic_medicine", "Surgical Aesthetics", '"blepharoplasty"[Title/Abstract] AND (outcome OR complication OR technique)'),
    ("aesthetic_medicine", "Surgical Aesthetics", '"rhinoplasty"[Title/Abstract] AND (outcome OR complication OR technique)'),
    ("aesthetic_medicine", "Surgical Aesthetics", '"otoplasty"[Title/Abstract] AND (outcome OR technique)'),
    ("aesthetic_medicine", "Surgical Aesthetics", '"breast augmentation"[Title/Abstract] AND (outcome OR complication OR implant)'),
    ("aesthetic_medicine", "Surgical Aesthetics", '"breast implant"[Title/Abstract] AND (safety OR complication OR BIA-ALCL)'),
    ("aesthetic_medicine", "Surgical Aesthetics", '"BIA-ALCL"[Title/Abstract] AND (implant OR breast OR lymphoma)'),
    # ── M: Evidence infrastructure for aesthetics ─────────────────────────
    ("aesthetic_medicine", "Evidence", '"systematic review"[pt] AND (aesthetic medicine OR cosmetic dermatology)'),
    ("aesthetic_medicine", "Evidence", '"randomized controlled trial"[pt] AND (botulinum toxin OR filler OR aesthetic)'),
    ("aesthetic_medicine", "Evidence", '"meta-analysis"[pt] AND (botulinum toxin OR dermal filler OR aesthetic)'),
    ("aesthetic_medicine", "Evidence", '"Cochrane"[Title/Abstract] AND (aesthetic OR cosmetic OR dermatology)'),
    ("aesthetic_medicine", "Evidence", '"clinical guideline"[Title/Abstract] AND (aesthetic OR cosmetic OR injectable)'),
    ("aesthetic_medicine", "Evidence", '"consensus statement"[Title/Abstract] AND (aesthetic OR filler OR injectable)'),
    ("aesthetic_medicine", "Evidence", '"evidence based"[Title/Abstract] AND (aesthetic medicine OR cosmetic)'),
    ("aesthetic_medicine", "Evidence", '"level I evidence"[Title/Abstract] AND (aesthetic OR cosmetic)'),
]


# ═══════════════════════════════════════════════════════════════════════════
# PubMed helpers
# ═══════════════════════════════════════════════════════════════════════════
def search_pubmed_ids(query: str, retmax: int = 9999) -> List[str]:
    params = {
        "db": "pubmed", "term": query,
        "retmax": retmax, "retmode": "json",
    }
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    try:
        r = requests.get(ESEARCH_URL, params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        logger.warning(f"Search failed '{query[:50]}': {e}")
        return []


def fetch_pubmed_batch(pmids: List[str], retries: int = 2) -> List[Dict]:
    data = {"db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "xml"}
    if NCBI_API_KEY:
        data["api_key"] = NCBI_API_KEY
    for attempt in range(retries):
        try:
            r = requests.post(EFETCH_URL, data=data, timeout=90)
            r.raise_for_status()
            return _parse_xml(r.text)
        except Exception as e:
            if attempt < retries - 1:
                wait = 2 ** attempt  # 1s, then 2s
                logger.debug(f"Fetch retry {attempt+1}/{retries} for {len(pmids)} PMIDs (wait {wait}s): {e}")
                time.sleep(wait)
            else:
                logger.warning(f"Fetch failed {len(pmids)} PMIDs after {retries} attempts: {e}")
    return []


def _parse_xml(xml_text: str) -> List[Dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    papers = []
    for article in root.findall(".//PubmedArticle"):
        try:
            pmid_el = article.find(".//PMID")
            if pmid_el is None:
                continue
            pmid = pmid_el.text.strip()
            title_el = article.find(".//ArticleTitle")
            title = (title_el.text or "").strip() if title_el is not None else ""
            if not title or len(title) < 5:
                continue
            abstract_parts = article.findall(".//AbstractText")
            abstract = " ".join((el.text or "").strip() for el in abstract_parts if el.text).strip()
            if len(abstract) < 80:
                continue
            year_el = article.find(".//PubDate/Year")
            year = int(year_el.text) if year_el is not None and year_el.text and year_el.text.isdigit() else None
            journal_el = article.find(".//Journal/Title")
            journal = (journal_el.text or "").strip()[:200] if journal_el is not None else ""
            authors = []
            for au in article.findall(".//Author")[:4]:
                last = au.find("LastName")
                if last is not None and last.text:
                    authors.append(last.text.strip())
            authors_str = ", ".join(authors) + (" et al." if len(authors) >= 3 else "")
            doi = ""
            for eid in article.findall(".//ELocationID"):
                if eid.get("EIdType") == "doi":
                    doi = (eid.text or "").strip()
                    break
            lang_el = article.find(".//Language")
            _raw_lang = (lang_el.text or "en").strip().lower()
            lang = PUBMED_LANG_MAP.get(_raw_lang, _raw_lang[:2])
            pub_types = [pt.text or "" for pt in article.findall(".//PublicationType")]
            doc_type = _classify_doc_type(pub_types, abstract)
            url = f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            papers.append({
                "pmid": pmid, "title": title, "abstract": abstract,
                "year": year, "journal": journal, "authors": authors_str,
                "doi": doi, "url": url, "doc_type": doc_type, "lang": lang,
            })
        except Exception:  # nosec B112
            continue
    return papers


def _classify_doc_type(pub_types: List[str], abstract: str) -> str:
    pt = " ".join(pub_types).lower()
    ab = abstract.lower()
    if "practice guideline" in pt or "guideline" in pt:
        return "guideline"
    if "systematic review" in pt or "meta-analysis" in pt:
        return "review"
    if "randomized controlled trial" in pt or "clinical trial" in pt:
        return "journal_article"
    if "review" in pt:
        return "review"
    if "case report" in pt:
        return "case_report"
    if "case series" in pt:
        return "case_series"
    if "systematic review" in ab or "meta-analysis" in ab:
        return "review"
    return "journal_article"


def batch_ingest(papers: List[Dict], domain: str, specialty: str) -> Tuple[int, int, int]:
    if not papers:
        return 0, 0, 0
    import psycopg2, psycopg2.extras
    source_ids = [f"PMID_{p['pmid']}" for p in papers]
    raw = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=15)
    raw.autocommit = False
    try:
        cur = raw.cursor()
        cur.execute("SET synchronous_commit = off")

        # ── Find existing docs ──────────────────────────────────────────────
        cur.execute(
            "SELECT source_id FROM documents WHERE source_id = ANY(%s)",
            (source_ids,)
        )
        existing = {r[0] for r in cur.fetchall()}
        new_papers = [(p, f"{p['title']}\n\n{p['abstract']}"[:8000])
                      for p, sid in zip(papers, source_ids) if sid not in existing]
        if not new_papers:
            raw.commit()
            return 0, len(papers), 0

        logger.info(f"[ingest] {len(new_papers)} new / {len(papers)} total — embedding ...")
        # ── Embed ───────────────────────────────────────────────────────────
        try:
            from app.rag.embedder import embed_texts_batch
            embeddings = embed_texts_batch([t for _, t in new_papers], batch_size=BATCH_EMBED_SIZE)
            logger.info(f"[ingest] embed done ({len(embeddings)} vecs) — inserting ...")
        except Exception as e:
            logger.error(f"Embed failed: {e}")
            return 0, 0, len(new_papers)

        # ── Bulk INSERT documents via execute_values ────────────────────────
        doc_rows = [
            (f"PMID_{paper['pmid']}", paper["title"][:500], paper["authors"][:300],
             paper.get("year"), paper["journal"][:200], domain, paper["doc_type"],
             "active", paper["url"], specialty, paper.get("lang", "en"))
            for paper, _ in new_papers
        ]
        psycopg2.extras.execute_values(cur, """
            INSERT INTO documents
                (source_id, title, authors, year, organization_or_journal,
                 domain, document_type, status, url, specialty, language)
            VALUES %s
            ON CONFLICT (source_id) DO UPDATE SET
                title = EXCLUDED.title, authors = EXCLUDED.authors,
                year = EXCLUDED.year,
                organization_or_journal = EXCLUDED.organization_or_journal,
                domain = EXCLUDED.domain, document_type = EXCLUDED.document_type,
                url = EXCLUDED.url, updated_at = now()
        """, doc_rows, page_size=500)

        # ── Fetch IDs in one SELECT ─────────────────────────────────────────
        sids_new = [r[0] for r in doc_rows]
        cur.execute("SELECT id, source_id FROM documents WHERE source_id = ANY(%s)", (sids_new,))
        sid_to_id = {r[1]: r[0] for r in cur.fetchall()}

        # ── Bulk INSERT chunks via execute_values ───────────────────────────
        chunk_rows = []
        for (paper, text_content), emb in zip(new_papers, embeddings):
            sid = f"PMID_{paper['pmid']}"
            doc_id = sid_to_id.get(sid)
            if doc_id is None:
                continue
            emb_str = "[" + ",".join(f"{v:.6f}" for v in emb) + "]"
            chunk_rows.append((doc_id, 0, text_content, "abstract", emb_str))

        if chunk_rows:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO chunks
                    (document_id, chunk_index, text, page_or_section, embedding)
                VALUES %s
                ON CONFLICT (document_id, chunk_index) DO NOTHING
            """, chunk_rows, page_size=200)

        raw.commit()
        return len(chunk_rows), len(papers) - len(new_papers), len(new_papers) - len(chunk_rows)
    except Exception as e:
        logger.error(f"Batch error: {e}")
        raw.rollback()
        return 0, 0, len(papers)
    finally:
        raw.close()


def current_doc_count() -> int:
    db = SessionLocal()
    try:
        return db.execute(text("SELECT COUNT(*) FROM documents")).scalar_one()
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# Quality Operations — run at each milestone transition
# ═══════════════════════════════════════════════════════════════════════════
def quality_op_m1_clean_and_rank():
    """Milestone 1: Fix evidence levels, clean doc types, mark evidence-ranked."""
    logger.info("[QA] M1: Assigning evidence levels based on document type ...")
    db = SessionLocal()
    try:
        db.execute(text("""
            UPDATE chunks c
            SET evidence_level = CASE
                WHEN d.document_type = 'guideline'      THEN 'I'
                WHEN d.document_type = 'review'         THEN 'II'
                WHEN d.document_type = 'journal_article'THEN 'III'
                WHEN d.document_type = 'case_series'    THEN 'IV'
                WHEN d.document_type = 'case_report'    THEN 'IV'
                ELSE 'III'
            END
            FROM documents d
            WHERE c.document_id = d.id
              AND c.evidence_level IS NULL
        """))
        db.execute(text("""
            UPDATE documents SET document_type = 'journal_article'
            WHERE document_type = 'pubmed_pmc'
        """))
        db.execute(text("""
            UPDATE documents SET document_type = 'guideline'
            WHERE document_type = 'clinical_guideline'
        """))
        db.commit()
        logger.info("[QA] M1: Evidence levels assigned and doc types cleaned.")
    except Exception as e:
        logger.error(f"[QA] M1 error: {e}")
        db.rollback()
    finally:
        db.close()


def quality_op_m2_guideline_coverage():
    """Milestone 2: Log guideline/review counts, then rebuild the HNSW index."""
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT document_type, COUNT(*) FROM documents
            GROUP BY document_type ORDER BY COUNT(*) DESC
        """)).fetchall()
        logger.info("[QA] M2: Document type breakdown:")
        for doc_type, count in rows:
            logger.info(f"  {doc_type}: {count:,}")
    except Exception as e:
        logger.error(f"[QA] M2 error: {e}")
    finally:
        db.close()

    # Rebuild the vector similarity index after bulk inserts.
    # HNSW is unusable on Replit (requires >64MB /dev/shm).
    # IVFFlat (lists=100, non-concurrent) works reliably:
    #   - k-means training uses regular RAM (~7MB for 5K sample vectors)
    #   - single-pass build (no multi-phase TCP timeout risk)
    logger.info("[QA] M2: Rebuilding IVFFlat vector index on chunks (lists=100) ...")
    import psycopg2
    try:
        raw = psycopg2.connect(
            os.environ["DATABASE_URL"],
            keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
        )
        raw.autocommit = True
        cur = raw.cursor()
        # Terminate any zombie CREATE INDEX backends from previous failed attempts
        cur.execute("""
            SELECT pg_terminate_backend(pid) FROM pg_stat_activity
            WHERE pid != pg_backend_pid()
            AND query ILIKE '%CREATE INDEX%'
            AND state IS DISTINCT FROM 'disabled'
        """)
        # Drop any invalid leftover index
        cur.execute("DROP INDEX IF EXISTS idx_chunks_embedding_hnsw")
        cur.execute("SET max_parallel_maintenance_workers = 0")
        cur.execute("SET maintenance_work_mem = '32MB'")
        cur.execute("SET statement_timeout = '0'")
        cur.execute("""
            CREATE INDEX idx_chunks_embedding_hnsw
            ON chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """)
        raw.close()
        logger.info("[QA] M2: IVFFlat index rebuilt successfully (lists=100).")
    except Exception as e:
        logger.error(f"[QA] M2: Vector index rebuild failed: {e}")


def quality_op_m3_multilingual():
    """Milestone 3: Fix language field, re-tag multilingual docs."""
    logger.info("[QA] M3: Normalising language codes ...")
    db = SessionLocal()
    try:
        lang_fixes = [
            ("en", "english"), ("en", "eng"), ("en", "EN"),
            ("de", "ge"), ("de", "german"),
            ("es", "sp"), ("es", "spanish"),
            ("zh", "ch"), ("zh", "chi"), ("zh", "chinese"),
            ("pt", "po"), ("pt", "por"), ("pt", "portuguese"),
            ("fr", "fre"), ("fr", "french"),
            ("it", "ita"), ("it", "italian"),
            ("ja", "jpn"), ("ja", "japanese"),
            ("ko", "kor"), ("ko", "korean"),
            ("ru", "rus"), ("ru", "russian"),
            ("ar", "ara"), ("ar", "arabic"),
            ("nl", "du"),  ("nl", "dut"), ("nl", "dutch"),
        ]
        for iso, bad in lang_fixes:
            db.execute(text(
                "UPDATE documents SET language = :iso WHERE language = :bad"
            ), {"iso": iso, "bad": bad})
        db.execute(text(
            "UPDATE documents SET language = 'en' WHERE language IS NULL OR language = ''"
        ))
        db.commit()
        rows = db.execute(text("""
            SELECT language, COUNT(*) FROM documents
            GROUP BY language ORDER BY COUNT(*) DESC LIMIT 15
        """)).fetchall()
        logger.info("[QA] M3: Language distribution:")
        for lang, count in rows:
            logger.info(f"  {lang}: {count:,}")
    except Exception as e:
        logger.error(f"[QA] M3 error: {e}")
        db.rollback()
    finally:
        db.close()


def quality_op_m5_aesthetic_coverage():
    """Milestone 5: Log aesthetic medicine coverage and re-assign evidence levels for new docs."""
    logger.info("[QA] M5: Auditing aesthetic medicine corpus coverage ...")
    db = SessionLocal()
    try:
        # Evidence level refresh for any new docs from M5 that missed QA
        db.execute(text("""
            UPDATE chunks c
            SET evidence_level = CASE
                WHEN d.document_type = 'guideline'       THEN 'I'
                WHEN d.document_type = 'review'          THEN 'II'
                WHEN d.document_type = 'journal_article' THEN 'III'
                WHEN d.document_type = 'case_series'     THEN 'IV'
                WHEN d.document_type = 'case_report'     THEN 'IV'
                ELSE 'III'
            END
            FROM documents d
            WHERE c.document_id = d.id
              AND c.evidence_level IS NULL
        """))
        db.commit()

        # Coverage report — aesthetic domain breakdown
        rows = db.execute(text("""
            SELECT domain, COUNT(*) AS cnt
            FROM documents
            GROUP BY domain ORDER BY cnt DESC
        """)).fetchall()
        logger.info("[QA] M5: Domain distribution:")
        for row in rows:
            logger.info(f"  {row[0]}: {row[1]:,}")

        # Aesthetic subtype distribution
        aes_rows = db.execute(text("""
            SELECT document_type, COUNT(*) AS cnt
            FROM documents
            WHERE domain = 'aesthetic_medicine'
            GROUP BY document_type ORDER BY cnt DESC
        """)).fetchall()
        logger.info("[QA] M5: Aesthetic medicine doc types:")
        for row in aes_rows:
            logger.info(f"  {row[0]}: {row[1]:,}")

        total = db.execute(text("SELECT COUNT(*) FROM documents")).scalar_one()
        logger.info(f"[QA] M5: Total documents: {total:,}")
    except Exception as e:
        logger.error(f"[QA] M5 error: {e}")
        db.rollback()
    finally:
        db.close()


def quality_op_m4_dedup_and_index():
    """Milestone 4: Deduplication + evidence priority update."""
    logger.info("[QA] M4: Deduplication — removing exact title duplicates ...")
    db = SessionLocal()
    try:
        result = db.execute(text("""
            DELETE FROM documents
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY lower(trim(title))
                               ORDER BY
                                 CASE document_type
                                   WHEN 'guideline'      THEN 1
                                   WHEN 'review'         THEN 2
                                   WHEN 'journal_article'THEN 3
                                   ELSE 4
                                 END ASC,
                                 year DESC NULLS LAST, id ASC
                           ) AS rn
                    FROM documents
                    WHERE title IS NOT NULL AND trim(title) != ''
                ) ranked
                WHERE rn > 1
            )
        """))
        removed = result.rowcount
        db.commit()
        logger.info(f"[QA] M4: Removed {removed:,} duplicate documents.")
    except Exception as e:
        logger.error(f"[QA] M4 dedup error: {e}")
        db.rollback()
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# Core runner — processes queries, updates shared _state
# ═══════════════════════════════════════════════════════════════════════════
def _run_phase(phase_num: int, label: str, queries: List[Tuple[str, str, str]],
               quality_fn=None, resume_from: int = 0) -> bool:
    """
    Process all queries in a phase.
    Returns True if phase completed fully, False if interrupted.
    Saves progress to disk every 10 queries and on any stop/interrupt.
    Note: phases are NO LONGER stopped early based on doc count —
          every query runs to completion to ensure coverage quality.
    """
    with _lock:
        _state["milestone"] = phase_num
        _state["milestone_label"] = label
        _state["queries_total"] = len(queries)
        _state["queries_done"] = resume_from
        _state["current_phase"] = phase_num
        _state["quality_op"] = ""

    logger.info(
        f"=== PHASE {phase_num}: {label} | queries={len(queries)} "
        f"| resuming_from={resume_from} ==="
    )

    for i, (domain, specialty, query) in enumerate(queries):
        if i < resume_from:
            continue  # Already completed in a prior run

        if _state["stop_requested"]:
            with _lock:
                _state["current_query_index"] = i
            _save_progress()
            return False

        with _lock:
            _state["current_query_index"] = i
            _state["last_query"] = query[:80]
            _state["current_db_count"] = current_doc_count()

        try:
            pmids = search_pubmed_ids(query)
            if not pmids:
                with _lock:
                    _state["queries_done"] += 1
                continue

            logger.info(f"  [{i+1}/{len(queries)}] {specialty}: {len(pmids)} PMIDs | {query[:60]}")

            all_batches = [pmids[j:j + FETCH_BATCH_SIZE]
                           for j in range(0, len(pmids), FETCH_BATCH_SIZE)]
            with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
                futures = {pool.submit(fetch_pubmed_batch, b): b for b in all_batches}
                for future in as_completed(futures):
                    if _state["stop_requested"]:
                        with _lock:
                            _state["current_query_index"] = i
                        _save_progress()
                        return False
                    papers = future.result()
                    if papers:
                        ins, skip, fail = batch_ingest(papers, domain, specialty)
                        with _lock:
                            _state["docs_inserted"] += ins
                            _state["docs_skipped"]  += skip
                            _state["docs_failed"]   += fail
                            _state["current_db_count"] = _state["docs_start"] + _state["docs_inserted"]

            # Persist after every query so restarts lose at most one in-flight query
            with _lock:
                _state["queries_done"] += 1
                _state["current_query_index"] = i + 1
            _save_progress()

        except Exception as e:
            logger.error(f"Phase {phase_num} query error: {e}")
            with _lock:
                _state["queries_done"] += 1
            time.sleep(2)

    # Quality operation at phase end
    if quality_fn and not _state["stop_requested"]:
        with _lock:
            _state["quality_op"] = f"Running M{phase_num} quality check ..."
        quality_fn()
        with _lock:
            _state["quality_op"] = f"M{phase_num} quality check complete"

    # Mark phase complete and reset query index for next phase
    with _lock:
        _state[f"m{phase_num}_completed"] = True
        _state["current_query_index"] = 0
        _state["last_run_at"] = datetime.utcnow().isoformat()
    _save_progress()
    logger.info(f"[M{phase_num}] Phase complete.")
    return True


# ═══════════════════════════════════════════════════════════════════════════
# Main entrypoint
# ═══════════════════════════════════════════════════════════════════════════
def run_mass_upload():
    """
    AesthetiCite Corpus Engine — 4-Milestone Strategy
    ==================================================
    Roadmap (priority order):
      1. M1 — Clean corpus           (SQL cleanup, always runs unless already done)
      2. M2 — Authoritative corpus   (guideline-first ingestion, MANDATORY)
      3. SQL ranking improvements    (handled externally — guideline priority in retrieval)
      4. Multilingual retrieval fix  (handled externally — must be confirmed before M3)
      5. M3 — Globally usable corpus (multilingual ingestion, BLOCKED until above done)
      6. M4 — Broad & defensible     (full sweep, runs last)

    Skipping rules:
      M1: skipped only if m1_completed flag is already set.
      M2: skipped only if m2_completed flag is already set.
          NEVER skipped due to corpus size — M2 is about evidence shape, not count.
      M3: blocked (and engine halts with a warning) unless:
            - m1_completed = True
            - m2_completed = True
            - multilang_retrieval_fixed = True (set via admin API)
      M4: skipped only if m4_completed flag is already set.

    Resumability:
      current_phase + current_query_index are saved to PROGRESS_FILE every 10 queries.
      On restart, the engine resumes from where it stopped.
    """
    _load_progress()

    start_count = current_doc_count()
    with _lock:
        _state["running"] = True
        _state["stop_requested"] = False
        _state["docs_start"] = start_count
        _state["current_db_count"] = start_count
        _state["started_at"] = datetime.utcnow().isoformat()

    # Keep the process alive so Replit's idle-timeout doesn't kill us mid-upload
    _start_keepalive()

    logger.info("=" * 65)
    logger.info("  AesthetiCite Corpus Engine — 5-Milestone Strategy")
    logger.info(f"  Current: {start_count:,}  Target: {TARGET_DOCS:,}")
    logger.info("  Priority: M1=clean → M2=authoritative → M3=global → M4=broad → M5=aesthetic-deep-dive")
    logger.info(
        f"  Completion: M1={_state['m1_completed']} M2={_state['m2_completed']} "
        f"M3={_state['m3_completed']} M4={_state['m4_completed']} M5={_state['m5_completed']}"
    )
    logger.info(
        f"  Policy: multilang_fixed={_state['multilang_retrieval_fixed']} "
        f"guideline_priority={_state['guideline_priority_enabled']} "
        f"cleanup_verified={_state['corpus_cleanup_verified']}"
    )
    logger.info("=" * 65)

    # ── M1: Clean corpus ─────────────────────────────────────────────────────
    # SQL-only quality pass — assigns evidence levels, audits doc types.
    # Skipped only when m1_completed is already True (never skipped by count).
    if not _state["m1_completed"]:
        logger.info("[M1] Running corpus cleanup (evidence levels, doc type audit) ...")
        quality_op_m1_clean_and_rank()
        with _lock:
            _state["m1_completed"] = True
        _save_progress()
        logger.info("[M1] Complete.")
    else:
        logger.info("[M1] Already completed — skipping cleanup.")

    if _state["stop_requested"]:
        _finalise()
        return

    # ── M2: Authoritative corpus ──────────────────────────────────────────────
    # MANDATORY — ensures guideline density and evidence hierarchy.
    # NEVER skip based on corpus size. Skip ONLY if m2_completed = True.
    #
    # Policy: corpus_cleanup_verified should be True before M2 runs.
    # If False, a warning is logged but M2 still proceeds (soft requirement).
    if not _state["m2_completed"]:
        if not _state["corpus_cleanup_verified"]:
            logger.warning(
                "[M2] corpus_cleanup_verified is False — it is strongly recommended "
                "to review M1 quality results before ingesting guideline docs. "
                "Check evidence level assignments and fix any mislabeled documents. "
                "Then call POST /api/mass-upload/set-policy with corpus_cleanup_verified=true. "
                "Proceeding with M2 anyway (soft requirement)."
            )
        logger.info(
            "[M2] Running guideline-first ingestion (MANDATORY — evidence hierarchy). "
            "This phase runs regardless of current doc count."
        )
        resume_idx = (
            _state.get("current_query_index", 0)
            if _state.get("current_phase") == 2 else 0
        )
        ok = _run_phase(
            2, "Authoritative Corpus — Guideline & Review Priority",
            PHASE2_QUERIES, quality_op_m2_guideline_coverage, resume_from=resume_idx,
        )
        if not ok:
            _finalise()
            return
    else:
        logger.info("[M2] Already completed — skipping guideline ingestion.")

    if _state["stop_requested"]:
        _finalise()
        return

    # ── External gate: guideline priority ranking ─────────────────────────────
    # Before adding more docs (M3/M4), retrieval must be able to surface
    # guidelines correctly. If guideline_priority_enabled is False, the engine
    # halts here and waits for an admin to enable retrieval improvements.
    if not _state["guideline_priority_enabled"]:
        logger.warning(
            "[GATE] guideline_priority_enabled is False — engine is pausing before M3/M4. "
            "Action required: enable guideline priority in the retrieval layer "
            "(boost guideline and consensus documents in ranking). "
            "Without this, M3/M4 volume will bury high-quality docs. "
            "Once done, call POST /api/mass-upload/set-policy with guideline_priority_enabled=true."
        )
        _finalise()
        return

    # ── M3: Globally usable corpus ────────────────────────────────────────────
    # BLOCKED until:
    #   (a) guideline_priority_enabled = True  (checked above)
    #   (b) multilang_retrieval_fixed  = True  (checked here)
    #
    # Multilingual success = language detection + translate-to-English retrieval
    # + answer translation back to the user's language.
    # Running M3 against a ~99% English corpus with broken multilingual retrieval
    # only wastes PubMed quota and inflates corpus volume without quality gains.
    if not _state["m3_completed"]:
        if not _state["multilang_retrieval_fixed"]:
            logger.warning(
                "[M3] BLOCKED — multilang_retrieval_fixed is False. "
                "Fix the multilingual retrieval strategy before ingesting non-English docs: "
                "(1) language detection, "
                "(2) translate-to-English retrieval, "
                "(3) answer translation back to user language. "
                "Then call POST /api/mass-upload/set-policy with multilang_retrieval_fixed=true."
            )
            _finalise()
            return

        logger.info(
            "[M3] Starting multilingual ingestion "
            "(guideline priority enabled, retrieval confirmed fixed) ..."
        )
        resume_idx = (
            _state.get("current_query_index", 0)
            if _state.get("current_phase") == 3 else 0
        )
        ok = _run_phase(
            3, "Globally Usable Corpus — Multilingual Retrieval",
            PHASE3_QUERIES, quality_op_m3_multilingual, resume_from=resume_idx,
        )
        if not ok:
            _finalise()
            return
    else:
        logger.info("[M3] Already completed — skipping multilingual ingestion.")

    if _state["stop_requested"]:
        _finalise()
        return

    # ── M4: Broad & defensible corpus ─────────────────────────────────────────
    # Policy: warn if guideline_priority_enabled is False.
    # Should not be possible to reach here without it (gated above), but
    # belt-and-suspenders in case flags were manually edited.
    if not _state["m4_completed"]:
        if not _state["guideline_priority_enabled"]:
            logger.warning(
                "[M4] guideline_priority_enabled is False — running M4 without retrieval "
                "ranking improvements risks burying high-quality guideline docs under the "
                "broad sweep volume. Proceeding, but ranking should be fixed urgently."
            )
        resume_idx = (
            _state.get("current_query_index", 0)
            if _state.get("current_phase") == 4 else 0
        )
        ok = _run_phase(
            4, "Broad & Defensible Corpus — Full Coverage + Dedup",
            PHASE4_QUERIES, quality_op_m4_dedup_and_index, resume_from=resume_idx,
        )
        if not ok:
            _finalise()
            return
    else:
        logger.info("[M4] Already completed.")

    if _state["stop_requested"]:
        _finalise()
        return

    # ── M5: Aesthetic medicine deep-dive + recency + safety ──────────────────
    # Runs after M4. Targets the aesthetic medicine domain specifically with
    # granular subspecialty queries, the 2023-2025 recency sweep, patient safety
    # and adverse event data, anatomy for injectors, hair and body contouring.
    # Target: 1,500,000 total documents.
    if not _state["m5_completed"]:
        logger.info(
            "[M5] Starting aesthetic medicine deep-dive + recency sweep + safety data. "
            f"Queries: {len(PHASE5_QUERIES)}. Target: {MILESTONES[5]:,} docs."
        )
        resume_idx = (
            _state.get("current_query_index", 0)
            if _state.get("current_phase") == 5 else 0
        )
        ok = _run_phase(
            5, "Aesthetic Deep-Dive — Subspecialties + Recency + Safety",
            PHASE5_QUERIES, quality_op_m5_aesthetic_coverage, resume_from=resume_idx,
        )
        if not ok:
            _finalise()
            return
    else:
        logger.info("[M5] Already completed.")

    _finalise()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_mass_upload()
