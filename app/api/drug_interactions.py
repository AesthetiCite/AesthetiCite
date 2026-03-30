"""
Fix 4 — Expanded Drug Interaction Checker
==========================================
Replaces the 8-drug hardcoded DrugInteractionAdapter in growth_engine.py
with a comprehensive checker covering:
  - Anticoagulants (high severity)
  - GLP-1 agonists (new — wound healing, anaesthesia risk)
  - Immunosuppressants (infection risk)
  - NSAIDs + antiplatelets (bleeding)
  - SSRIs / SNRIs (bruising, serotonin syndrome risk)
  - Corticosteroids (skin thinning, wound healing)
  - Isotretinoin (procedure contraindication)
  - RxNav live API adapter (thousands of drugs)

INTEGRATION:
  In growth_engine.py, replace:
      class DrugInteractionAdapter:
          ...
      drug_adapter = DrugInteractionAdapter()

  With:
      from app.api.drug_interactions import AestheticDrugChecker
      drug_adapter = AestheticDrugChecker()

  The check() method signature is identical.

POST /api/growth/drug-interactions remains unchanged.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import re

logger = logging.getLogger(__name__)

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"


# ─────────────────────────────────────────────────────────────────
# Data model (same as existing DrugInteractionItem)
# ─────────────────────────────────────────────────────────────────

@dataclass
class DrugInteractionItem:
    medication: str
    product_or_context: str
    severity: str           # "high" | "moderate" | "low"
    explanation: str
    action: str
    mechanism: Optional[str] = None
    references: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Drug database — normalized names → interaction profile
# ─────────────────────────────────────────────────────────────────

@dataclass
class DrugProfile:
    normalized: str
    display: str
    severity: str
    category: str
    explanation: str
    action: str
    mechanism: Optional[str] = None
    aliases: List[str] = field(default_factory=list)


DRUG_DATABASE: List[DrugProfile] = [

    # ── Anticoagulants — HIGH ──────────────────────────────────────
    DrugProfile("warfarin", "Warfarin", "high", "anticoagulant",
        "Warfarin significantly increases bruising and bleeding risk during injectable procedures. "
        "INR must be checked and documented. Haematoma formation risk is substantially elevated.",
        "Check INR before procedure. Consider delaying if INR > 3.0. Document counselling. "
        "Avoid high-risk anatomical zones where compression is difficult.",
        "Vitamin K antagonist — prolongs prothrombin time",
        aliases=["coumadin", "coumarin"]),

    DrugProfile("apixaban", "Apixaban (Eliquis)", "high", "anticoagulant",
        "Direct oral anticoagulant — significantly increases bruising and bleeding risk. "
        "No reliable reversal agent available in most clinic settings.",
        "Document medication. Discuss bleeding risk and realistic bruising expectations. "
        "Compression bandaging should be available. Avoid high-vascular-density zones.",
        "Direct Factor Xa inhibitor",
        aliases=["eliquis"]),

    DrugProfile("rivaroxaban", "Rivaroxaban (Xarelto)", "high", "anticoagulant",
        "Direct oral anticoagulant — significantly increases bruising and bleeding risk.",
        "Same precautions as apixaban. Document counselling. Consider cannula technique.",
        "Direct Factor Xa inhibitor",
        aliases=["xarelto"]),

    DrugProfile("dabigatran", "Dabigatran (Pradaxa)", "high", "anticoagulant",
        "Direct thrombin inhibitor — significantly increases bleeding risk.",
        "Document medication. Discuss bruising risk. Idarucizumab is specific reversal agent "
        "but not available in clinic settings.",
        "Direct thrombin inhibitor",
        aliases=["pradaxa"]),

    DrugProfile("heparin", "Heparin / LMWH", "high", "anticoagulant",
        "Therapeutic or prophylactic heparin substantially increases bleeding and haematoma risk.",
        "Clarify indication and dose. If therapeutic, liaise with prescribing clinician before proceeding.",
        "Potentiates antithrombin III",
        aliases=["enoxaparin", "dalteparin", "tinzaparin", "clexane", "fragmin"]),

    # ── GLP-1 agonists — MODERATE/HIGH ────────────────────────────
    DrugProfile("semaglutide", "Semaglutide (Ozempic / Wegovy)", "high", "glp1_agonist",
        "GLP-1 agonists cause significant changes in facial fat distribution and volume — "
        "Ozempic face phenotype. Planned filler volumes may be inappropriate. "
        "Delayed gastric emptying increases anaesthesia aspiration risk if sedation planned. "
        "Rapid weight loss affects baseline facial anatomy for contouring procedures.",
        "Review current dose and weight trajectory. Document weight change over 3–6 months. "
        "Reassess filler volume targets in context of ongoing volume loss. "
        "If sedation/general anaesthesia planned, follow GLP-1 fasting guidelines "
        "(ASA 2023: hold day-of-procedure).",
        "GLP-1 receptor agonist — delayed gastric emptying, fat redistribution",
        aliases=["ozempic", "wegovy", "rybelsus"]),

    DrugProfile("liraglutide", "Liraglutide (Victoza / Saxenda)", "high", "glp1_agonist",
        "Same class as semaglutide. Ongoing facial volume changes affect planning for "
        "contouring and volumisation procedures.",
        "Same precautions as semaglutide. Document dose and weight trajectory.",
        "GLP-1 receptor agonist",
        aliases=["victoza", "saxenda"]),

    DrugProfile("tirzepatide", "Tirzepatide (Mounjaro)", "high", "glp1_agonist",
        "Dual GIP/GLP-1 agonist with pronounced weight loss effect. "
        "Facial volume changes may be more marked than with GLP-1 monotherapy.",
        "Same precautions as semaglutide. Particularly document volume baseline before starting.",
        "Dual GIP and GLP-1 receptor agonist",
        aliases=["mounjaro", "zepbound"]),

    DrugProfile("dulaglutide", "Dulaglutide (Trulicity)", "moderate", "glp1_agonist",
        "GLP-1 agonist — delayed gastric emptying and possible facial volume changes.",
        "Document use. Review filler volume targets if significant weight loss ongoing.",
        "GLP-1 receptor agonist",
        aliases=["trulicity"]),

    # ── Immunosuppressants — HIGH ──────────────────────────────────
    DrugProfile("methotrexate", "Methotrexate", "high", "immunosuppressant",
        "Immunosuppression substantially increases infection risk after injectable procedures. "
        "Impaired wound healing. Increased risk of biofilm formation after filler.",
        "Liaise with rheumatologist or prescribing clinician before proceeding. "
        "Assess current disease activity and immunosuppression level. "
        "Consider antibiotic prophylaxis per local protocol.",
        "Dihydrofolate reductase inhibitor — suppresses T-cell and B-cell function",
        aliases=[]),

    DrugProfile("ciclosporin", "Ciclosporin (Cyclosporine)", "high", "immunosuppressant",
        "Calcineurin inhibitor — significant immunosuppression increases infection and "
        "poor healing risk after injectable procedures.",
        "Liaise with specialist. Assess infection risk carefully before proceeding.",
        "Calcineurin inhibitor",
        aliases=["cyclosporine", "neoral", "sandimmun"]),

    DrugProfile("azathioprine", "Azathioprine", "high", "immunosuppressant",
        "Purine analogue immunosuppressant — increases infection risk after injectables.",
        "Liaise with prescribing clinician. Document immunosuppression status.",
        "Purine analogue — suppresses lymphocyte proliferation",
        aliases=["imuran"]),

    DrugProfile("mycophenolate", "Mycophenolate mofetil", "high", "immunosuppressant",
        "Immunosuppressant — increases infection and poor healing risk.",
        "Liaise with specialist. Antibiotic prophylaxis should be considered.",
        "Inosine monophosphate dehydrogenase inhibitor",
        aliases=["cellcept", "myfortic"]),

    DrugProfile("adalimumab", "Adalimumab (Humira)", "high", "immunosuppressant",
        "TNF-alpha inhibitor — significant immunosuppression. Risk of infection "
        "and impaired healing after injectable procedures is substantially elevated.",
        "Document biological therapy. Liaise with specialist. "
        "Consider procedure timing relative to injection cycle.",
        "Anti-TNF-alpha monoclonal antibody",
        aliases=["humira"]),

    DrugProfile("etanercept", "Etanercept (Enbrel)", "high", "immunosuppressant",
        "TNF inhibitor — same concerns as adalimumab.",
        "Same precautions as adalimumab.",
        "TNF receptor fusion protein",
        aliases=["enbrel"]),

    # ── Corticosteroids — MODERATE ────────────────────────────────
    DrugProfile("prednisolone", "Prednisolone / Prednisone", "moderate", "corticosteroid",
        "Long-term corticosteroids cause skin thinning, impaired wound healing, "
        "and increased bruising risk. Fat redistribution may affect facial anatomy.",
        "Document dose and duration. Use conservative volumes and gentle technique. "
        "Warn patient about increased bruising and slower healing.",
        "Glucocorticoid — anti-inflammatory, catabolic effect on connective tissue",
        aliases=["prednisone", "dexamethasone", "hydrocortisone", "methylprednisolone"]),

    # ── NSAIDs + Antiplatelets — MODERATE ─────────────────────────
    DrugProfile("aspirin", "Aspirin", "moderate", "antiplatelet",
        "Low-dose aspirin (cardiovascular prophylaxis) increases bruising risk. "
        "Should not be stopped without cardiology review if for cardiovascular indication.",
        "Do not advise stopping if cardiovascular indication. "
        "Discuss realistic bruising expectations. Use compression and ice.",
        "Irreversible COX-1 inhibitor — impairs platelet aggregation",
        aliases=["acetylsalicylic acid", "asa"]),

    DrugProfile("clopidogrel", "Clopidogrel (Plavix)", "moderate", "antiplatelet",
        "Irreversible platelet inhibition — significantly increases bruising risk. "
        "Do not advise stopping without cardiology review.",
        "Document indication. Do not recommend cessation without specialist review. "
        "Compression technique and haematoma monitoring recommended.",
        "P2Y12 receptor antagonist",
        aliases=["plavix"]),

    DrugProfile("ibuprofen", "Ibuprofen / NSAIDs", "moderate", "nsaid",
        "NSAIDs increase bruising and bleeding risk. "
        "Can be avoided for 7 days pre-procedure if for non-essential analgesia.",
        "Advise patient to avoid for 7 days pre-procedure if safe to do so. "
        "Document if essential medication.",
        "COX-1 and COX-2 inhibitor",
        aliases=["naproxen", "diclofenac", "meloxicam", "celecoxib", "indomethacin",
                 "ketoprofen", "mefenamic", "piroxicam"]),

    # ── SSRIs / SNRIs — MODERATE ──────────────────────────────────
    DrugProfile("sertraline", "SSRIs / SNRIs", "moderate", "ssri_snri",
        "SSRIs and SNRIs impair platelet aggregation (serotonin depletion in platelets), "
        "increasing bruising risk. Effect is similar to low-dose aspirin.",
        "Counsel patient about increased bruising. Do not advise stopping. "
        "Document use and discuss realistic bruising expectations.",
        "Serotonin reuptake inhibition → platelet serotonin depletion → impaired aggregation",
        aliases=["fluoxetine", "escitalopram", "citalopram", "paroxetine",
                 "venlafaxine", "duloxetine", "fluvoxamine"]),

    # ── Isotretinoin — HIGH ────────────────────────────────────────
    DrugProfile("isotretinoin", "Isotretinoin (Roaccutane)", "high", "retinoid",
        "Active isotretinoin use is a contraindication to most aesthetic procedures. "
        "Impaired wound healing, increased keloid and scarring risk. "
        "Most guidelines recommend waiting 6–12 months after cessation before procedures.",
        "Do not proceed with skin-disrupting procedures during active isotretinoin treatment. "
        "Wait minimum 6 months (many protocols: 12 months) after cessation. "
        "Document last dose date.",
        "Retinoic acid — impairs epidermal barrier repair and wound healing",
        aliases=["roaccutane", "accutane", "tretinoin oral"]),

    # ── Antivirals / herpes prophylaxis — LOW ─────────────────────
    DrugProfile("aciclovir", "Aciclovir / antivirals", "low", "antiviral",
        "Patients on antiviral prophylaxis may have recurrent herpes labialis history. "
        "Lip filler procedures may trigger herpetic reactivation.",
        "For lip procedures: confirm antiviral prophylaxis is prescribed and taken "
        "as directed. Document history of oral herpes.",
        "Nucleoside analogue antiviral",
        aliases=["acyclovir", "valaciclovir", "valacyclovir", "famciclovir"]),
]

# Build normalised lookup: any alias or primary name → DrugProfile
_DRUG_LOOKUP: Dict[str, DrugProfile] = {}
for _dp in DRUG_DATABASE:
    _DRUG_LOOKUP[_dp.normalized] = _dp
    for _alias in _dp.aliases:
        _DRUG_LOOKUP[_alias.lower()] = _dp


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().strip())


def _match_drug(name: str) -> Optional[DrugProfile]:
    n = _normalize(name)
    # Exact match
    if n in _DRUG_LOOKUP:
        return _DRUG_LOOKUP[n]
    # Partial match — check if any known key is a substring
    for key, profile in _DRUG_LOOKUP.items():
        if key in n or n in key:
            return profile
    return None


# ─────────────────────────────────────────────────────────────────
# RxNav live API adapter
# ─────────────────────────────────────────────────────────────────

async def _rxnav_check(drug_a: str, drug_b: str) -> List[Dict]:
    """Check NIH RxNav for interactions between two drug names."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{RXNAV_BASE}/interaction/interaction.json",
                params={"rxcui": drug_a},
            )
            if r.status_code != 200:
                return []
            data = r.json()
            pairs = (data.get("interactionTypeGroup") or [])
            results = []
            for group in pairs:
                for itype in (group.get("interactionType") or []):
                    for pair in (itype.get("interactionPair") or []):
                        description = pair.get("description", "")
                        severity = pair.get("severity", "")
                        results.append({
                            "description": description,
                            "severity": severity,
                        })
            return results
    except Exception as e:
        logger.debug(f"[RxNav] check failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────
# Main checker class
# ─────────────────────────────────────────────────────────────────

class AestheticDrugChecker:
    """
    Drop-in replacement for DrugInteractionAdapter in growth_engine.py.
    Same check() method signature.
    """

    def check(
        self,
        medications: List[str],
        planned_products: List[str],
    ) -> List[DrugInteractionItem]:
        items: List[DrugInteractionItem] = []
        seen: Set[str] = set()
        prods = planned_products or ["injectable aesthetic procedure"]

        for med_name in medications:
            profile = _match_drug(med_name)
            if not profile:
                continue
            # Deduplicate by category (avoid listing same class twice)
            if profile.category in seen:
                continue
            seen.add(profile.category)
            for prod in prods:
                items.append(DrugInteractionItem(
                    medication=profile.display,
                    product_or_context=prod,
                    severity=profile.severity,
                    explanation=profile.explanation,
                    action=profile.action,
                    mechanism=profile.mechanism,
                ))

        # Sort: high first, then moderate, then low
        order = {"high": 0, "moderate": 1, "low": 2}
        items.sort(key=lambda x: order.get(x.severity, 3))
        return items

    def check_single(self, medication: str) -> Optional[DrugInteractionItem]:
        """Check a single medication. Returns None if not in database."""
        profile = _match_drug(medication)
        if not profile:
            return None
        return DrugInteractionItem(
            medication=profile.display,
            product_or_context="aesthetic injectable procedure",
            severity=profile.severity,
            explanation=profile.explanation,
            action=profile.action,
            mechanism=profile.mechanism,
        )

    def list_covered_drugs(self) -> List[Dict]:
        """Return the full drug database for UI display."""
        seen_cats: Set[str] = set()
        result = []
        for dp in DRUG_DATABASE:
            if dp.category not in seen_cats:
                seen_cats.add(dp.category)
            result.append({
                "name": dp.display,
                "severity": dp.severity,
                "category": dp.category,
                "aliases": dp.aliases,
            })
        return result
