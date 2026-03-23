"""
AesthetiCite Pre-Procedure Safety Engine — Enhancement Patch
=============================================================
Add this content to app/api/preprocedure_safety_engine.py

Changes
-------
1. PatientFactors — adds glp1_patient field
2. ProcedureInsight — adds ultrasound_recommended, ultrasound_note fields
3. adjust_score() — adds GLP-1 risk modifier (+6)
4. build_response() — computes ultrasound flag per region
5. New model: DifferentialRequest, DifferentialItem, DifferentialResponse
6. New endpoint: POST /api/safety/differential
7. PROCEDURE_RULES — biostimulator safety notes embedded in relevant rules

=== STEP 1: Replace PatientFactors model ===
"""

# ─── REPLACE PatientFactors with this ────────────────────────────────────────

class PatientFactors(BaseModel):
    prior_filler_in_same_area: Optional[bool] = None
    prior_vascular_event: Optional[bool] = None
    autoimmune_history: Optional[bool] = None
    allergy_history: Optional[bool] = None
    active_infection_near_site: Optional[bool] = None
    anticoagulation: Optional[bool] = None
    vascular_disease: Optional[bool] = None
    smoking: Optional[bool] = None
    # NEW — GLP-1 / semaglutide / tirzepatide patient
    glp1_patient: Optional[bool] = None


# ─── REPLACE ProcedureInsight with this ──────────────────────────────────────

class ProcedureInsight(BaseModel):
    procedure_name: str
    region: str
    likely_plane_or_target: Optional[str] = None
    danger_zones: List[str] = Field(default_factory=list)
    technical_notes: List[str] = Field(default_factory=list)
    # NEW — ultrasound guidance flags
    ultrasound_recommended: bool = False
    ultrasound_note: Optional[str] = None


# ─── ULTRASOUND FLAG LOGIC ────────────────────────────────────────────────────

# Regions where current congress evidence (RSNA 2025, CMAC 2025) recommends
# ultrasound guidance before injection.
ULTRASOUND_RECOMMENDED_REGIONS: set[str] = {
    "nose", "nasal", "nasal tip", "nasal bridge", "dorsum",
    "temple", "temporal",
    "forehead", "frontal",
    "tear trough", "infraorbital", "periorbital",
    "glabella",
}

ULTRASOUND_NOTES: dict[str, str] = {
    "nose": (
        "Nasal vasculature communicates with the ophthalmic territory via the dorsal nasal "
        "and angular arteries. RSNA 2025 data: 35% of nasal filler-related adverse events "
        "showed absent major vessel flow. Ultrasound with Doppler strongly advised before "
        "injection to confirm vessel positions in this high-risk zone."
    ),
    "temple": (
        "The superficial temporal artery is highly variable and palpable in most patients. "
        "Ultrasound with Doppler enables real-time vessel mapping and avoidance of direct "
        "arterial injection. Recommended before any filler in the temporal hollow."
    ),
    "forehead": (
        "Supratrochlear and supraorbital arteries carry intracranial connections. "
        "Ultrasound guidance for deep periosteal filler placement in the forehead significantly "
        "reduces risk of inadvertent arterial injection."
    ),
    "tear trough": (
        "The periorbital vasculature is delicate and patient-variable. "
        "Ultrasound can identify the infraorbital foramen and periorbital vascular structures "
        "to guide safe, deep filler placement and avoid superficial deposition (Tyndall risk)."
    ),
    "glabella": (
        "The glabellar region is among the highest-risk zones for filler-related vascular "
        "complications and vision loss. Ultrasound is advisable for any filler in this region "
        "to identify the supratrochlear and supraorbital vessels."
    ),
}


def get_ultrasound_flag(region: str) -> tuple[bool, Optional[str]]:
    """Return (recommended: bool, note: Optional[str]) for a given region string."""
    r = region.lower().strip()
    for key in ULTRASOUND_RECOMMENDED_REGIONS:
        if key in r:
            note = next((v for k, v in ULTRASOUND_NOTES.items() if k in r), None)
            return True, note
    return False, None


# ─── UPDATED adjust_score() — add GLP-1 modifier ─────────────────────────────

def adjust_score(base: int, request: "PreProcedureRequest") -> tuple[int, List[str]]:
    """
    Adjust base risk score with patient-factor and technique modifiers.
    Returns (adjusted_score: int, caution_flags: List[str])
    """
    score = base
    flags: List[str] = []

    pf = request.patient_factors
    if pf:
        if pf.prior_vascular_event:
            score += 12
            flags.append("Prior vascular event significantly increases ischemic risk in this region.")
        if pf.active_infection_near_site:
            score += 15
            flags.append("Active infection near the injection site is a contraindication to proceeding.")
        if pf.anticoagulation:
            score += 8
            flags.append("Anticoagulation increases bruising and haematoma risk.")
        if pf.autoimmune_history:
            score += 5
            flags.append("Autoimmune history may increase inflammatory and nodule risk.")
        if pf.allergy_history:
            score += 4
            flags.append("Allergy history — confirm no known reaction to the planned product or its components.")
        if pf.vascular_disease:
            score += 8
            flags.append("Vascular disease increases occlusion risk and reduces tissue tolerance of ischaemia.")
        if pf.smoking:
            score += 5
            flags.append("Smoking impairs wound healing and increases vascular complication risk.")
        if pf.prior_filler_in_same_area:
            score += 3
            flags.append("Prior filler in same area: assess for residual product and altered anatomy.")
        # NEW — GLP-1 modifier
        if pf.glp1_patient:
            score += 6
            flags.append(
                "GLP-1 medication (semaglutide/tirzepatide): rapid facial fat loss alters volume "
                "distribution and may change filler requirements. Standard quantities risk overcorrection. "
                "Facial anatomy may differ from prior assessments. Reassess treatment plan accordingly."
            )

    # Technique modifiers
    tech = (request.technique or "").lower()
    if "needle" in tech:
        score += 6
    elif "cannula" in tech:
        score -= 4

    # Experience modifier
    exp = request.injector_experience_level
    if exp == "junior":
        score += 8
        flags.append("Junior injector: strict supervision and emergency protocol preparedness is required.")
    elif exp == "senior":
        score -= 4

    return max(0, min(100, score)), flags


# ─── UPDATED build_response() — adds ultrasound flag ─────────────────────────

def build_response(request: "PreProcedureRequest") -> "PreProcedureResponse":
    """Build a full PreProcedureResponse for the given request."""
    rule = match_rule(request)
    score, flags = adjust_score(rule["base_risk"], request)

    if score < 35:
        level: "RiskLevel" = "low"
        decision: "DecisionLevel" = "go"
        rationale = (
            "Risk factors are within acceptable parameters for a competent injector with "
            "standard precautions and an emergency protocol in place."
        )
    elif score < 55:
        level = "moderate"
        decision = "caution"
        rationale = (
            "Moderate overall risk identified. Proceed with enhanced vigilance, conservative "
            "volume strategy, and active complication monitoring throughout the procedure."
        )
    elif score < 72:
        level = "high"
        decision = "high_risk"
        rationale = (
            "High risk profile. Ensure full emergency preparedness, confirm hyaluronidase "
            "availability, consider technique modification, and reassess whether to proceed today."
        )
    else:
        level = "very_high"
        decision = "high_risk"
        rationale = (
            "Very high risk. Strongly consider deferring or referring this procedure. "
            "If proceeding, maximum precaution, senior supervision, and immediate emergency "
            "access are essential."
        )

    top_risks = []
    for comp_name, comp_score, comp_why in rule["complications"]:
        adjusted_comp = min(100, comp_score + max(0, score - rule["base_risk"]))
        if adjusted_comp < 25:
            risk_level: "RiskLevel" = "low"
        elif adjusted_comp < 50:
            risk_level = "moderate"
        elif adjusted_comp < 70:
            risk_level = "high"
        else:
            risk_level = "very_high"
        top_risks.append(
            RiskItem(
                complication=comp_name,
                risk_score=adjusted_comp,
                risk_level=risk_level,
                why_it_matters=comp_why,
            )
        )
    top_risks.sort(key=lambda r: r.risk_score, reverse=True)

    # Ultrasound flag — NEW
    us_recommended, us_note = get_ultrasound_flag(request.region)

    evidence = EvidenceRetriever().retrieve(request, rule)

    return PreProcedureResponse(
        request_id=str(uuid.uuid4()),
        generated_at_utc=now_utc_iso(),
        engine_version=ENGINE_VERSION,
        knowledge_revision=KNOWLEDGE_REVISION,
        safety_assessment=SafetyAssessment(
            overall_risk_score=score,
            overall_risk_level=level,
            decision=decision,
            rationale=rationale,
        ),
        top_risks=top_risks,
        procedure_insight=ProcedureInsight(
            procedure_name=rule.get("procedure_aliases", [request.procedure])[0],
            region=request.region,
            likely_plane_or_target=rule.get("plane"),
            danger_zones=rule.get("danger_zones", []),
            technical_notes=rule.get("tech_notes", []),
            ultrasound_recommended=us_recommended,   # NEW
            ultrasound_note=us_note,                  # NEW
        ),
        mitigation_steps=rule["mitigation"],
        caution_flags=flags,
        evidence=evidence,
        disclaimer=(
            "This output is pre-procedure safety decision support, not a substitute for "
            "clinician judgment, anatomical expertise, product knowledge, or local emergency "
            "preparedness."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  NEW: Complication Differential Endpoint
#  POST /api/safety/differential
# ═══════════════════════════════════════════════════════════════════════════════

class DifferentialSymptoms(BaseModel):
    """Structured symptom input for complication differential."""
    onset: str = Field(..., description="e.g. 'immediate', 'hours after', 'weeks after'")
    appearance: str = Field(..., description="e.g. 'pale/blanching', 'lump/nodule', 'erythema'")
    pain: str = Field(..., description="e.g. 'severe burning', 'mild tender', 'none'")
    location: str = Field(..., description="e.g. 'nose tip', 'tear trough', 'lip'")
    product_used: Optional[str] = None
    time_since_injection: Optional[str] = None


class DifferentialItem(BaseModel):
    rank: int
    diagnosis: str
    probability: Literal["high", "moderate", "low"]
    key_clues: List[str]
    immediate_actions: List[str]
    rule_out: List[str]
    escalation_note: Optional[str] = None


class DifferentialResponse(BaseModel):
    request_id: str
    generated_at_utc: str
    differentials: List[DifferentialItem]
    clinical_reminder: str


def _score_differential(symptoms: DifferentialSymptoms) -> List[DifferentialItem]:
    """
    Score differential diagnoses from symptom input.
    Based on the structured complication framework from CMAC 2025.
    """
    results: List[DifferentialItem] = []
    a = symptoms.appearance.lower()
    p = symptoms.pain.lower()
    o = symptoms.onset.lower()
    t = (symptoms.time_since_injection or "").lower()

    # ── Vascular Occlusion ─────────────────────────────────────────────────
    vo_score = (
        (3 if any(x in a for x in ["pale", "blanch", "white", "mottl", "livedo"]) else 0) +
        (2 if any(x in p for x in ["severe", "intense", "burning"]) else 0) +
        (2 if any(x in o for x in ["immediate", "during", "minutes"]) else 0)
    )
    if vo_score >= 2:
        results.append(DifferentialItem(
            rank=0,
            diagnosis="Vascular Occlusion (VO)",
            probability="high" if vo_score >= 5 else "moderate",
            key_clues=[
                "Blanching, pallor, or mottled/livedo pattern",
                "Severe or burning pain at/near injection site",
                "Immediate or rapid onset (during or minutes after injection)",
                "Well-demarcated ischaemic zone",
            ],
            immediate_actions=[
                "STOP injection immediately — do not inject further",
                "Apply warm compress to affected area",
                "Inject hyaluronidase NOW if HA filler — do not wait for confirmation",
                "Initiate vascular occlusion protocol (high-dose, repeated hyaluronidase)",
                "Escalate if blanching, pain, or mottling does not resolve within 30–60 min",
                "Have emergency ophthalmology contact if periorbital or nasal region",
            ],
            rule_out=[
                "Bruising (purplish, non-demarcated, resolves over days)",
                "Normal post-procedure erythema (diffuse, warm, resolves in hours)",
                "Delayed-onset nodule (palpable, weeks later, no blanching)",
            ],
            escalation_note=(
                "If visual symptoms develop (blurred vision, loss of visual field) — "
                "immediate ophthalmology emergency referral. This is a sight-threatening emergency."
            ),
        ))

    # ── Delayed-Onset Nodule ───────────────────────────────────────────────
    don_score = (
        (3 if any(x in a for x in ["lump", "nodule", "hard", "firm"]) else 0) +
        (2 if any(x in t for x in ["week", "month"]) else 0) +
        (1 if any(x in p for x in ["mild", "tender"]) else 0)
    )
    if don_score >= 2:
        results.append(DifferentialItem(
            rank=0,
            diagnosis="Delayed-Onset Nodule (DON)",
            probability="high" if don_score >= 4 else "moderate",
            key_clues=[
                "Palpable firm nodule (days to months post-procedure)",
                "May be tender or asymptomatic",
                "Non-blanching",
                "Delayed onset (not immediate)",
            ],
            immediate_actions=[
                "Assess if filler-related nodule vs inflammatory vs infected",
                "Use ultrasound if available to differentiate filler mass from abscess",
                "If HA filler: trial hyaluronidase injection",
                "If signs of infection: culture, antibiotics, do not inject further",
                "Photograph and document for follow-up tracking",
            ],
            rule_out=[
                "Vascular occlusion (no blanching, no acute onset in DON)",
                "Granuloma (typically late onset, inflammatory, firm — may need biopsy)",
                "Infection (warm, erythematous, fever possible)",
            ],
            escalation_note=None,
        ))

    # ── Infection / Biofilm ────────────────────────────────────────────────
    inf_score = (
        (2 if any(x in a for x in ["red", "erythema", "warm"]) else 0) +
        (3 if any(x in a for x in ["pus", "discharge"]) else 0) +
        (1 if any(x in t for x in ["week", "month"]) else 0) +
        (1 if "throb" in p else 0)
    )
    if inf_score >= 2:
        results.append(DifferentialItem(
            rank=0,
            diagnosis="Infection / Biofilm",
            probability="high" if inf_score >= 4 else "moderate",
            key_clues=[
                "Erythema, warmth, swelling, tenderness",
                "Possible pus or discharge",
                "Onset typically days to weeks post-procedure",
                "Throbbing pain may suggest abscess",
            ],
            immediate_actions=[
                "Do NOT inject more filler into or near the area",
                "Swab for culture if discharge present",
                "Start broad-spectrum antibiotics empirically",
                "Consider hyaluronidase if firm HA nodule with signs of infection",
                "Refer to appropriate specialist if no improvement in 48 hours",
                "Consider imaging (ultrasound) to assess for abscess",
            ],
            rule_out=[
                "Hypersensitivity (more urticarial, no pus, rapid onset)",
                "Normal post-procedure swelling (resolves within 24–48h, no erythema or warmth)",
                "Delayed-onset inflammatory nodule (no systemic signs, no fever)",
            ],
            escalation_note=(
                "Biofilm infections may require prolonged antibiotic courses and product dissolution. "
                "Multidrug resistance is possible with delayed-presentation biofilm."
            ),
        ))

    # ── Hypersensitivity / Anaphylaxis ─────────────────────────────────────
    hs_score = (
        (3 if any(x in a for x in ["itch", "urtic", "hive", "rash"]) else 0) +
        (2 if any(x in o for x in ["immediate", "minutes"]) else 0) +
        (1 if "widespread" in symptoms.location.lower() else 0)
    )
    if hs_score >= 2:
        results.append(DifferentialItem(
            rank=0,
            diagnosis="Hypersensitivity / Anaphylaxis",
            probability="high" if hs_score >= 4 else "moderate",
            key_clues=[
                "Urticaria, pruritus, or generalised erythema",
                "Rapid onset (typically within minutes)",
                "May be widespread or involve distant sites",
                "Throat tightness, wheeze, or hypotension suggest anaphylaxis",
            ],
            immediate_actions=[
                "ASSESS airway, breathing, circulation FIRST",
                "If anaphylaxis: adrenaline (epinephrine) 0.5mg IM (lateral thigh) IMMEDIATELY",
                "Call emergency services if systemic signs present",
                "Antihistamine and corticosteroid as adjunct (not primary treatment)",
                "Position patient supine with legs raised",
                "Do not leave patient unattended",
            ],
            rule_out=[
                "Normal post-procedure localised erythema (limited to injection site, not urticarial)",
                "Vascular occlusion (ischaemic pattern, not urticarial or widespread)",
            ],
            escalation_note=(
                "Anaphylaxis is an emergency — do not delay epinephrine. "
                "Have adrenaline auto-injector (EpiPen) in clinic at all times."
            ),
        ))

    # ── Tyndall Effect ─────────────────────────────────────────────────────
    tyndall_score = (
        (3 if any(x in a for x in ["blue", "grey", "gray", "discolour", "discolor"]) else 0) +
        (2 if any(x in symptoms.location.lower() for x in ["tear", "eye", "periorbital", "under"]) else 0) +
        (1 if any(x in t for x in ["week", "month"]) else 0)
    )
    if tyndall_score >= 2:
        results.append(DifferentialItem(
            rank=0,
            diagnosis="Tyndall Effect",
            probability="high" if tyndall_score >= 4 else "moderate",
            key_clues=[
                "Blue-grey discolouration under the skin",
                "Periorbital or superficial injection site",
                "Gradual onset (not immediate)",
                "Typically painless",
            ],
            immediate_actions=[
                "Confirm clinically — Wood's lamp may help",
                "Plan hyaluronidase treatment for HA filler dissolution",
                "Counsel patient: may require multiple treatment sessions",
                "Photograph and document",
                "Reassess depth and product selection for future treatments",
            ],
            rule_out=[
                "Bruising (purple, resolves over days, not persistent blue-grey)",
                "Infection (warm, erythematous, painful)",
            ],
            escalation_note=None,
        ))

    # ── Fallback ───────────────────────────────────────────────────────────
    if not results:
        results.append(DifferentialItem(
            rank=1,
            diagnosis="Insufficient symptom data — further assessment required",
            probability="low",
            key_clues=["Symptom pattern does not clearly match standard complication profiles"],
            immediate_actions=[
                "Perform a full clinical assessment",
                "Use ultrasound if available to assess local anatomy and filler position",
                "Consult an experienced colleague",
                "Treat as vascular occlusion until proven otherwise if any blanching is present",
            ],
            rule_out=["Consider vascular occlusion in any post-filler concern with colour change or pain"],
            escalation_note=None,
        ))
        return results

    # Sort by probability then assign ranks
    order = {"high": 0, "moderate": 1, "low": 2}
    results.sort(key=lambda r: order[r.probability])
    for i, r in enumerate(results):
        r.rank = i + 1

    return results


@router.post("/differential", response_model=DifferentialResponse)
def complication_differential(payload: DifferentialSymptoms) -> DifferentialResponse:
    """
    POST /api/safety/differential
    Accepts a structured symptom description and returns a ranked
    complication differential with immediate action steps.

    Based on the structured complication framework presented at CMAC 2025
    (onset × appearance × pain × timing layering approach).
    """
    diffs = _score_differential(payload)
    return DifferentialResponse(
        request_id=str(uuid.uuid4()),
        generated_at_utc=now_utc_iso(),
        differentials=diffs,
        clinical_reminder=(
            "This differential is clinical decision support only. "
            "In any post-filler concern with blanching, pain, or colour change, "
            "treat as vascular occlusion until proven otherwise. "
            "Use ultrasound where available to differentiate. "
            "Do not delay emergency intervention while awaiting a definitive diagnosis."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  BIOSTIMULATOR SAFETY NOTES — Add to relevant PROCEDURE_RULES entries
# ═══════════════════════════════════════════════════════════════════════════════
# For jawline/chin/cheek rule, add this to tech_notes:
#
#   "CaHA (Radiesse): cannot be dissolved with hyaluronidase — vascular occlusion "
#   "management differs from HA fillers. Ensure your protocol accounts for non-dissoluble product.",
#
# For general note on PLLA, add to mitigation where applicable:
#
#   "PLLA (Sculptra): although lower-risk profile, region-specific vascular risk applies. "
#   "Recent evidence shows PLLA can cause unexpected vascular adverse events. "
#   "Do not assume lower-risk product = lower-risk procedure in high-risk zones.",
#
# ═══════════════════════════════════════════════════════════════════════════════
