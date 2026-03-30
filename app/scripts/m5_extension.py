"""
app/scripts/m5_extension.py

Phase D + E — aesthetic medicine corpus extension to 1,000,000 documents.

Phase D  Journal-level: core aesthetic / derm / plastic journals NOT in M5-Phase-A
Phase E  Topic-level  : emerging treatments, techniques, and patient-centred topics
         all scoped to aesthetic medicine

Strategy:
  • Stops automatically when documents table reaches TARGET_DOCS.
  • Fully idempotent — ON CONFLICT (source_id) DO NOTHING everywhere.
  • Shares ingest helpers from m5_ingest (fetch, parse, embed, insert).
  • Exposes run() for the FastAPI thread; also runnable as a CLI script.

Usage:
    python app/scripts/m5_extension.py
    python app/scripts/m5_extension.py --dry-run
    python app/scripts/m5_extension.py --target 1000000
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger("m5_ext")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

TARGET_DOCS = 1_000_000   # stop ingest once corpus reaches this count


# ─────────────────────────────────────────────────────────────────────────────
# Phase D — Journals not in M5 Phase A
# (ISSN, friendly_name, year_from, year_to)
# ─────────────────────────────────────────────────────────────────────────────

PHASE_D_JOURNALS: List[Tuple[str, str, int, int]] = [
    # High-yield aesthetic / cosmetic / dermatologic surgery journals
    ("1076-0512", "Dermatologic Surgery",                          2010, 2026),
    ("1473-2130", "Journal of Cosmetic Dermatology",               2012, 2026),
    ("0364-216X", "Aesthetic Plastic Surgery",                     2012, 2026),
    ("1748-6815", "Journal of Plastic Reconstructive Aesthetic Surgery", 2012, 2026),
    ("2689-3614", "Facial Plastic Surgery and Aesthetic Medicine", 2019, 2026),
    ("0736-6825", "Facial Plastic Surgery",                        2012, 2026),
    ("1545-9616", "Journal of Drugs in Dermatology",               2014, 2026),
    ("0190-9622", "Journal of the American Academy of Dermatology",2020, 2026),
    ("1525-1470", "Pediatric Dermatology",                         2018, 2026),  # scar/pigment
    ("1468-3083", "Journal of the European Academy of Dermatology",2022, 2026),  # recent gap

    # Plastic & reconstructive surgery — high aesthetic content
    ("0032-1052", "Plastic and Reconstructive Surgery",            2018, 2026),
    ("1049-2275", "Journal of Craniofacial Surgery",               2022, 2026),  # recent gap
    ("0148-7043", "Annals of Plastic Surgery",                     2022, 2026),  # recent gap

    # Clinical dermatology / general
    ("0738-081X", "Clinics in Dermatology",                        2015, 2026),
    ("1087-2108", "American Journal of Clinical Dermatology",      2015, 2026),
    ("1011-7571", "Medical Principles and Practice",               2018, 2026),

    # Regenerative / wound / laser
    ("1096-2395", "Wound Repair and Regeneration",                 2015, 2026),
    ("0196-8092", "Lasers in Surgery and Medicine",                2015, 2026),
    ("1083-3668", "Journal of Biomedical Optics",                  2018, 2026),

    # Open-access high-volume
    ("2352-6416", "JAAD Case Reports",                             2018, 2026),
    ("2050-0904", "Clinical Case Reports",                         2018, 2026),
]


# ─────────────────────────────────────────────────────────────────────────────
# Phase E — Topic queries (emerging treatments + patient-centred topics)
# (query, years_range)
# ─────────────────────────────────────────────────────────────────────────────

PHASE_E_QUERIES: List[Tuple[str, str]] = [

    # ── Biostimulators & next-gen injectables ────────────────────────────────
    ("polynucleotides PDRN skin rejuvenation clinical",           "2018:2026"),
    ("Profhilo biostimulator injectable skin laxity",             "2019:2026"),
    ("poly-L-lactic acid Sculptra volume restoration",            "2012:2026"),
    ("calcium hydroxylapatite Radiesse skin aging filler",        "2012:2026"),
    ("collagen stimulator aesthetic injectable clinical trial",   "2015:2026"),
    ("autologous conditioned serum growth factor skin",           "2016:2026"),
    ("exosome platelet lysate skin rejuvenation clinical",        "2020:2026"),
    ("microfat nanofat fat injection face rejuvenation",          "2015:2026"),
    ("skin booster hyaluronic acid intradermal injection quality","2015:2026"),

    # ── Thread lifts ─────────────────────────────────────────────────────────
    ("PDO thread lift face aesthetic outcome",                    "2016:2026"),
    ("PLLA thread suspension lift complication clinical",         "2017:2026"),
    ("barbed suture thread lift ptosis complication",             "2015:2026"),
    ("cog thread lift midface rejuvenation outcome",              "2017:2026"),

    # ── Energy-based devices ─────────────────────────────────────────────────
    ("RF microneedling Morpheus fractional radiofrequency skin",  "2018:2026"),
    ("microfocused ultrasound Ultherapy HIFU skin tightening RCT","2015:2026"),
    ("fractional CO2 laser skin resurfacing aging scar RCT",      "2012:2026"),
    ("erbium laser ablative resurfacing outcome",                  "2012:2026"),
    ("picosecond laser tattoo removal pigmentation clinical",      "2016:2026"),
    ("Q-switched Nd:YAG laser pigmentation melasma",              "2012:2026"),
    ("intense pulsed light IPL vascular rosacea clinical",        "2012:2026"),
    ("photobiomodulation LED red light skin clinical",            "2016:2026"),
    ("photodynamic therapy PDT acne aesthetic clinical trial",    "2012:2026"),
    ("low-level laser therapy LLLT hair loss clinical trial",     "2015:2026"),
    ("pulsed dye laser vascular lesion port wine stain",          "2012:2026"),
    ("non-ablative laser skin rejuvenation collagen clinical",    "2012:2026"),
    ("body contouring cryolipolysis RF ultrasound clinical",      "2014:2026"),

    # ── Specific anatomy and injection techniques ─────────────────────────────
    ("non-surgical rhinoplasty nose filler outcome complication", "2014:2026"),
    ("lip augmentation filler hyaluronic acid aesthetic outcome", "2012:2026"),
    ("tear trough periorbital filler dark circle treatment",      "2013:2026"),
    ("jawline chin filler definition aesthetic clinical",         "2015:2026"),
    ("temporal fossa filler aging volume rejuvenation",           "2016:2026"),
    ("cheek malar filler augmentation outcome study",             "2013:2026"),
    ("hand rejuvenation filler fat aesthetic treatment",          "2014:2026"),
    ("neck platysma décolletage aesthetic injectable treatment",  "2016:2026"),
    ("forehead glabella aesthetic botulinum injection technique", "2012:2026"),
    ("masseteric hypertrophy botulinum toxin jaw slimming",       "2013:2026"),
    ("hyperhidrosis botulinum toxin axilla palm treatment RCT",   "2010:2026"),
    ("platysmal band neck botulinum toxin clinical",              "2013:2026"),
    ("gummy smile botulinum toxin outcome",                       "2014:2026"),

    # ── Skin treatments / topicals ───────────────────────────────────────────
    ("glycolic acid chemical peel clinical outcome skin",         "2012:2026"),
    ("salicylic acid BHA peel acne treatment clinical",           "2012:2026"),
    ("trichloroacetic acid TCA peel skin aging outcome",          "2010:2026"),
    ("kojic acid tranexamic acid pigmentation clinical",          "2015:2026"),
    ("topical retinoid retinol tretinoin aging RCT",              "2015:2026"),
    ("azelaic acid skin brightening rosacea clinical",            "2015:2026"),
    ("bakuchiol retinol alternative aging skin clinical",         "2019:2026"),
    ("niacinamide skin aging pore acne pigment clinical",         "2016:2026"),
    ("peptide growth factor topical skin aging evidence",         "2016:2026"),

    # ── Hair & scalp ─────────────────────────────────────────────────────────
    ("PRP scalp hair loss androgenetic alopecia clinical trial",  "2014:2026"),
    ("mesotherapy hair loss scalp injection clinical",            "2015:2026"),
    ("hair transplant FUE FUT outcome patient satisfaction",      "2014:2026"),
    ("low-level laser therapy hairloss LLLT clinical RCT",        "2015:2026"),
    ("topical minoxidil female androgenetic alopecia clinical",   "2015:2026"),

    # ── Scar, pigmentation, and skin conditions ───────────────────────────────
    ("keloid hypertrophic scar intralesional steroid 5FU treatment","2010:2026"),
    ("post-inflammatory hyperpigmentation treatment laser peel",  "2014:2026"),
    ("acne scar treatment fractional laser clinical trial",       "2012:2026"),
    ("stretch mark striae treatment laser clinical",              "2013:2026"),
    ("vitiligo treatment laser phototherapy clinical",            "2012:2026"),
    ("rosacea treatment azelaic ivermectin laser clinical",       "2015:2026"),
    ("sebaceous hyperplasia treatment aesthetic clinical",        "2015:2026"),

    # ── Body contouring & procedures ─────────────────────────────────────────
    ("liposuction tumescent outcome aesthetic complication",      "2012:2026"),
    ("fat transfer breast augmentation safety outcome",           "2013:2026"),
    ("Brazilian butt lift gluteal fat grafting safety",           "2017:2026"),
    ("structural fat grafting face volume outcome",               "2012:2026"),
    ("deoxycholic acid Kybella Belkyra submental fat clinical",   "2013:2026"),
    ("body sculpting EMSculpt muscle aesthetic clinical",         "2019:2026"),

    # ── Patient experience & psychology ──────────────────────────────────────
    ("patient satisfaction aesthetic medicine outcome measure",   "2015:2026"),
    ("body dysmorphic disorder aesthetic patient screening",      "2015:2026"),
    ("social media influence aesthetic procedure demand",         "2018:2026"),
    ("aesthetic medicine motivation expectation patient",         "2015:2026"),
    ("male aesthetic medicine botulinum filler trend",            "2015:2026"),
    ("younger patient preventive aesthetic prejuvenation",        "2018:2026"),
    ("ethnic minority dark skin aesthetic treatment outcome",     "2015:2026"),
    ("quality of life aesthetic procedure patient reported",      "2015:2026"),
    ("gender-affirming aesthetic procedure clinical outcome",     "2018:2026"),

    # ── Safety, complications & medico-legal ─────────────────────────────────
    ("aesthetic procedure complication incidence epidemiology",   "2015:2026"),
    ("filler embolism vascular occlusion emergency treatment",    "2012:2026"),
    ("aesthetic medicine regulation practitioner safety UK EU",   "2016:2026"),
    ("adverse event reporting aesthetic medicine database",       "2016:2026"),
    ("hypersensitivity allergy filler injection treatment",       "2013:2026"),
    ("delayed inflammatory reaction filler COVID vaccine",        "2020:2026"),
    ("aesthetic complication litigation malpractice outcome",     "2015:2026"),

    # ── Very recent (2024-2026) gap-fill ─────────────────────────────────────
    ("aesthetic medicine 2024 clinical trial",                    "2024:2026"),
    ("dermal filler injectable 2024 outcome",                     "2024:2026"),
    ("botulinum toxin aesthetic 2024 clinical",                   "2024:2026"),
    ("laser energy device aesthetic 2024",                        "2024:2026"),
    ("cosmetic dermatology 2024 RCT review",                      "2024:2026"),
    ("injectable aesthetic medicine safety 2025",                 "2025:2026"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers — import from m5_ingest to avoid code duplication
# ─────────────────────────────────────────────────────────────────────────────

def _import_helpers():
    """Lazy-import from m5_ingest so CLI import is fast."""
    from app.scripts.m5_ingest import (
        get_conn, get_doc_count,
        search_pmids_by_journal, search_pmids_by_query,
        ingest_pmids,
    )
    return get_conn, get_doc_count, search_pmids_by_journal, search_pmids_by_query, ingest_pmids


# ─────────────────────────────────────────────────────────────────────────────
# Main run() — called by the FastAPI thread and by the CLI
# ─────────────────────────────────────────────────────────────────────────────

def run(
    target: int = TARGET_DOCS,
    dry_run: bool = False,
    stop_flag=None,
    progress_cb: Optional[Callable[[dict], None]] = None,
) -> dict:
    """
    Run Phase D (journals) then Phase E (topics) until the corpus hits `target`.

    stop_flag: threading.Event — set to cancel.
    progress_cb(snapshot): called after each journal / query batch.
    """
    (get_conn, get_doc_count, search_pmids_by_journal,
     search_pmids_by_query, ingest_pmids) = _import_helpers()

    stats = {
        "target":          target,
        "docs_at_start":   0,
        "docs_now":        0,
        "docs_needed":     0,
        "docs_inserted":   0,
        "chunks_inserted": 0,
        "phase":           "initialising",
        "current_item":    "",
        "items_done":      0,
        "items_total":     len(PHASE_D_JOURNALS) + len(PHASE_E_QUERIES),
        "started_at":      time.time(),
        "done":            False,
        "error":           None,
    }

    conn = get_conn()
    start_count = get_doc_count(conn)
    conn.close()

    stats["docs_at_start"] = start_count
    stats["docs_now"]      = start_count
    stats["docs_needed"]   = max(0, target - start_count)

    logger.info(f"═══ M5 Extension: Phase D + E ═══")
    logger.info(f"  Corpus now : {start_count:,}")
    logger.info(f"  Target     : {target:,}")
    logger.info(f"  Gap        : {stats['docs_needed']:,}")

    if start_count >= target:
        logger.info("Target already reached — nothing to do.")
        stats["done"] = True
        return stats

    if progress_cb:
        progress_cb({**stats})

    def _still_needed(conn) -> int:
        return max(0, target - get_doc_count(conn))

    def _should_stop(conn) -> bool:
        if stop_flag and stop_flag.is_set():
            return True
        if _still_needed(conn) <= 0:
            return True
        return False

    def _log_and_cb(label: str, d: int, c: int) -> None:
        conn2 = get_conn()
        stats["docs_now"]      = get_doc_count(conn2)
        conn2.close()
        stats["docs_inserted"]  += d
        stats["chunks_inserted"]+= c
        stats["docs_needed"]    = max(0, target - stats["docs_now"])
        stats["current_item"]   = label
        stats["items_done"]    += 1
        elapsed = time.time() - stats["started_at"]
        logger.info(
            f"  [{stats['items_done']}/{stats['items_total']}] {label[:55]} "
            f"→ +{d} docs | total={stats['docs_now']:,} | "
            f"gap={stats['docs_needed']:,}"
        )
        if progress_cb:
            progress_cb({**stats, "elapsed_s": elapsed})

    # ── Phase D — Journals ────────────────────────────────────────────────────
    stats["phase"] = "D_journals"
    logger.info("─── Phase D: journals ───")

    conn = get_conn()
    for issn, name, year_from, year_to in PHASE_D_JOURNALS:
        if _should_stop(conn):
            break

        label = f"{name} ({issn}) {year_from}-{year_to}"
        logger.info(f"\nJournal: {label}")
        pmids = search_pmids_by_journal(issn, year_from, year_to)
        logger.info(f"  PMIDs found: {len(pmids)}")
        if not pmids:
            _log_and_cb(label, 0, 0)
            continue

        specialty = "aesthetic_medicine" if any(
            kw in name.lower()
            for kw in ["aesthetic", "cosmetic", "dermatolog", "plastic", "laser", "facial"]
        ) else "dermatology"

        if not dry_run:
            # fetch_full_abstracts=False skips the per-PMID efetch call
            # (esummary already provides a usable abstract for chunking)
            d, c = ingest_pmids(pmids, specialty=specialty,
                                fetch_full_abstracts=False)
        else:
            d, c = 0, 0

        _log_and_cb(label, d, c)

    conn.close()

    # ── Phase E — Topic queries ───────────────────────────────────────────────
    stats["phase"] = "E_topics"
    logger.info("─── Phase E: topic queries ───")

    conn = get_conn()
    for query, years in PHASE_E_QUERIES:
        if _should_stop(conn):
            break

        label = f"{query[:55]} ({years})"
        logger.info(f"\nQuery: {label}")
        pmids = search_pmids_by_query(query, years=years)
        logger.info(f"  PMIDs found: {len(pmids)}")
        if not pmids:
            _log_and_cb(label, 0, 0)
            continue

        if not dry_run:
            d, c = ingest_pmids(pmids, specialty="aesthetic_medicine",
                                fetch_full_abstracts=False)
        else:
            d, c = 0, 0

        _log_and_cb(label, d, c)

    conn.close()

    # ── Final stats ───────────────────────────────────────────────────────────
    conn = get_conn()
    final_count = get_doc_count(conn)
    conn.close()

    stats.update({
        "docs_now":    final_count,
        "docs_needed": max(0, target - final_count),
        "done":        final_count >= target,
        "phase":       "complete",
        "elapsed_s":   time.time() - stats["started_at"],
    })

    if stop_flag and stop_flag.is_set():
        stats["phase"] = "stopped"

    logger.info(
        f"\n═══ Phase D+E complete ═══\n"
        f"  Corpus: {start_count:,} → {final_count:,} "
        f"(+{final_count - start_count:,})\n"
        f"  Inserted: {stats['docs_inserted']:,} docs, "
        f"{stats['chunks_inserted']:,} chunks\n"
        f"  Elapsed: {stats['elapsed_s']/60:.1f} min\n"
        f"  Target {'REACHED' if stats['done'] else 'NOT YET reached'}: "
        f"{final_count:,} / {target:,}"
    )

    if progress_cb:
        progress_cb({**stats})

    return stats


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="M5 Extension — Phase D+E ingest")
    ap.add_argument("--target",  type=int, default=TARGET_DOCS,
                    help=f"Stop when corpus reaches this count (default {TARGET_DOCS:,})")
    ap.add_argument("--dry-run", action="store_true",
                    help="Count PMIDs only — no inserts")
    args = ap.parse_args()
    result = run(target=args.target, dry_run=args.dry_run)
    sys.exit(0 if result.get("done") else 1)
