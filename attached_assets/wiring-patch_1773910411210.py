"""
complication_protocol_engine.py — Wiring Patch
================================================
Two targeted additions to your existing complication_protocol_engine.py

─────────────────────────────────────────────────────────────────────────
FIX 4: Wire neuromodulator resistance into the protocol matcher
─────────────────────────────────────────────────────────────────────────
Find your PROTOCOL_KEYWORDS / matcher dict and ADD this entry.
Then add the full protocol data (from neuromodulator_and_prescan_additions.py)
into your PROTOCOLS dict.

─────────────────────────────────────────────────────────────────────────
FIX 5: Add prescan-briefing endpoint
─────────────────────────────────────────────────────────────────────────
Add the router endpoint at the bottom of the file.
"""

# ─────────────────────────────────────────────────────────────────────────────
# FIX 4 — Step 1: Add to your PROTOCOL_KEYWORDS dict (or equivalent matcher)
# ─────────────────────────────────────────────────────────────────────────────
# Find this pattern in your code (around the protocol matching logic):
#
#   "vascular_occlusion": ["vascular", "occlusion", "blanching", ...]
#   "anaphylaxis": ["anaphylaxis", "anaphylactic", ...]
#
# ADD this entry:

NEUROMODULATOR_RESISTANCE_KEYWORDS = [
    # Direct resistance terms
    "resistance", "resistant", "antibody resistance", "neutralising antibody",
    "neutralizing antibody", "immunological resistance",
    # Treatment failure
    "not working", "not effective", "no effect", "no response", "no result",
    "failed botox", "botox failure", "toxin failure", "toxin not working",
    "botox not working", "dysport not working",
    # Duration problems
    "wearing off", "wearing off faster", "shortened duration",
    "shorter duration", "duration reduced", "lasts less",
    "not lasting", "doesn't last",
    # Pseudo-resistance
    "pseudo-resistance", "pseudo resistance",
    # Specific products
    "botulinum resistance", "neuromodulator resistance",
    "neuromodulator failure", "neurotoxin resistance",
    "xeomin switch", "switch toxin",
]

# In your match_protocol() function, the entry should look like:
# "neuromodulator_resistance": NEUROMODULATOR_RESISTANCE_KEYWORDS

# ─────────────────────────────────────────────────────────────────────────────
# FIX 4 — Step 2: Add the protocol data to your PROTOCOLS dict
# ─────────────────────────────────────────────────────────────────────────────
# Copy the full NEUROMODULATOR_RESISTANCE_PROTOCOL dict from:
#   neuromodulator_and_prescan_additions.py
# And add it to your PROTOCOLS dict:
#
#   PROTOCOLS["neuromodulator_resistance"] = NEUROMODULATOR_RESISTANCE_PROTOCOL
#
# Or inline it directly into your existing PROTOCOLS dict if it's defined inline.


# ─────────────────────────────────────────────────────────────────────────────
# FIX 5 — Pre-Scan Briefing endpoint
# ─────────────────────────────────────────────────────────────────────────────
# Add these models and the endpoint to complication_protocol_engine.py.
# The PreScanBriefing data is already in neuromodulator_and_prescan_additions.py —
# copy PRESCAN_BRIEFINGS, PreScanBriefingRequest, PreScanBriefingResponse,
# _match_prescan_region(), and the prescan_briefing() function here,
# then register it with the router decorator:

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone

# (These are already at the top of complication_protocol_engine.py — no re-import needed)

# Copy PRESCAN_BRIEFINGS dict here (from neuromodulator_and_prescan_additions.py)
# Then add the endpoint:

# @router.post("/prescan-briefing", response_model=PreScanBriefingResponse)
# def prescan_briefing_endpoint(payload: PreScanBriefingRequest) -> PreScanBriefingResponse:
#     return prescan_briefing(payload)


# ─────────────────────────────────────────────────────────────────────────────
# FIX 5 — Also add to server/routes.ts (Express proxy)
# ─────────────────────────────────────────────────────────────────────────────
# Add this line alongside your other complication proxies (around line 503):
#
# app.post("/api/complications/prescan-briefing", (req, res) =>
#   proxyToFastAPI(req, res, "/api/complications/prescan-briefing"));


# ─────────────────────────────────────────────────────────────────────────────
# MATCH FUNCTION TEMPLATE
# ─────────────────────────────────────────────────────────────────────────────
# If your match_protocol() function iterates a keyword dict, it should look
# approximately like this (adapt to your existing pattern):

def match_protocol_patch_example(query: str) -> str:
    """
    Example showing how the matcher should work after adding
    neuromodulator_resistance keywords.
    """
    PROTOCOL_KEYWORDS: Dict[str, List[str]] = {
        "vascular_occlusion": [
            "vascular occlusion", "blanching", "pallor", "mottling", "livedo",
            "ischemia", "ischaemia", "necrosis risk", "pain after filler",
            "white patch", "vascular compromise",
        ],
        "anaphylaxis": [
            "anaphylaxis", "anaphylactic", "allergy reaction", "urticaria",
            "throat swelling", "hypotension", "wheeze", "epinephrine",
        ],
        "tyndall_effect": [
            "tyndall", "blue grey", "blue gray", "discolouration after filler",
            "superficial filler", "under eye blue",
        ],
        "ptosis": [
            "ptosis", "eyelid droop", "droopy eyelid", "brow ptosis",
            "botox ptosis", "toxin diffusion",
        ],
        "infection_biofilm": [
            "infection after filler", "biofilm", "abscess", "pus",
            "fever after filler", "warmth after filler", "erythema filler",
        ],
        "filler_nodules": [
            "nodule", "granuloma", "lump after filler", "hard lump",
            "firm swelling", "delayed nodule",
        ],
        # ── NEW ──────────────────────────────────────────────────────────────
        "neuromodulator_resistance": NEUROMODULATOR_RESISTANCE_KEYWORDS,
    }

    q = query.lower()
    scores: Dict[str, int] = {}

    for protocol_key, keywords in PROTOCOL_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in q)
        if score > 0:
            scores[protocol_key] = score

    if not scores:
        return "general"

    return max(scores, key=lambda k: scores[k])


# ─────────────────────────────────────────────────────────────────────────────
# EXPRESS ROUTE — add to server/routes.ts
# ─────────────────────────────────────────────────────────────────────────────
EXPRESS_ROUTE_ADDITIONS = """
// Complication protocols — add alongside existing complication routes (line ~503)
app.post("/api/complications/prescan-briefing", (req, res) =>
  proxyToFastAPI(req, res, "/api/complications/prescan-briefing"));

// Case log stats route (already exists as GET)
// Session report export PDF (already exists)
"""

print("Patch guide loaded. Apply the changes described in comments above.")
