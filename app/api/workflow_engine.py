"""
AesthetiCite — Workflow Engine  (The Secret Weapon)
====================================================
Provides structured, action-first clinical workflows for
aesthetic complications. Pure in-memory — zero database calls.

GET /api/workflow?complication=vascular_occlusion  — full workflow
GET /api/workflow/list                             — all workflows with metadata
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/workflow", tags=["Workflow Engine"])

StepType = Literal["action", "assess", "monitor", "escalate", "document", "wait"]
Priority = Literal["critical", "high", "normal"]


class WorkflowStep(BaseModel):
    step: int
    type: StepType
    priority: Priority
    action: str
    detail: str
    timer_seconds: Optional[int] = None
    drug: Optional[str] = None
    dose: Optional[str] = None
    branch: Optional[Dict[str, Any]] = None
    checkpoint: Optional[str] = None


class Workflow(BaseModel):
    complication: str
    display_name: str
    urgency: Literal["immediate", "urgent", "same_day", "routine"]
    risk_level: Literal["critical", "high", "moderate", "low"]
    time_critical: Optional[str] = None
    total_steps: int
    steps: List[WorkflowStep]
    completion_criteria: str
    escalation_trigger: str
    evidence_basis: str


WORKFLOWS: Dict[str, Workflow] = {

    "vascular_occlusion": Workflow(
        complication="vascular_occlusion",
        display_name="Vascular Occlusion",
        urgency="immediate",
        risk_level="critical",
        time_critical="60-minute treatment window. Tissue damage is irreversible after 4–6 hours.",
        completion_criteria="Blanching fully resolved, normal skin colour, capillary refill < 2 seconds.",
        escalation_trigger="Visual symptoms at any point → abandon this workflow, call 999 immediately.",
        evidence_basis="BAFPS/RAFT Consensus 2023; Aesthet Surg J 2021.",
        total_steps=9,
        steps=[
            WorkflowStep(
                step=1, type="action", priority="critical",
                action="STOP injection immediately",
                detail="Withdraw needle/cannula. Do not apply pressure. Do not massage — this may extend the occlusion.",
                checkpoint="Injection is stopped and patient is lying flat.",
            ),
            WorkflowStep(
                step=2, type="assess", priority="critical",
                action="Check for visual symptoms",
                detail="Ask: any blurred vision, double vision, or visual loss? Examine for ptosis or ophthalmoplegia.",
                branch={
                    "condition": "Any visual symptom present",
                    "action": "STOP this protocol. Call 999 immediately. Ophthalmology referral now.",
                    "severity": "critical",
                },
                checkpoint="No visual symptoms confirmed. Continue.",
            ),
            WorkflowStep(
                step=3, type="action", priority="critical",
                action="Inject hyaluronidase 1500 IU NOW",
                detail="Flood the entire compromised vascular territory generously. Use 150 IU/ml concentration. Fan technique.",
                drug="Hyaluronidase",
                dose="1500 IU minimum — can repeat. Maximum 10,000 IU total in severe cases.",
            ),
            WorkflowStep(
                step=4, type="action", priority="critical",
                action="Give aspirin 300 mg orally",
                detail="Antiplatelet agent. Give immediately unless contraindicated (active GI bleed, allergy). Ask about contraindications first.",
                drug="Aspirin",
                dose="300 mg stat. 75 mg daily thereafter.",
            ),
            WorkflowStep(
                step=5, type="action", priority="high",
                action="Apply warm compress",
                detail="Promotes vasodilation. Do not use ice — this causes vasoconstriction.",
            ),
            WorkflowStep(
                step=6, type="action", priority="high",
                action="Apply nitroglycerin paste 2% topically",
                detail="Thin layer over blanched area. Promotes vasodilation. Avoid mucous membranes.",
                drug="Nitroglycerin paste",
                dose="2% paste, thin layer topically.",
            ),
            WorkflowStep(
                step=7, type="monitor", priority="critical",
                action="Monitor capillary refill every 5 min",
                detail="Press and release skin. Normal refill < 2 seconds. Document colour, warmth, and refill at each check.",
                timer_seconds=300,
                checkpoint="Is blanching improving? Skin warming? Capillary refill < 2s?",
            ),
            WorkflowStep(
                step=8, type="escalate", priority="critical",
                action="No improvement at 60 min? Repeat hyaluronidase",
                detail="Repeat 1500 IU every 60 minutes. Up to 3000–10,000 IU total. If no improvement → emergency department.",
                timer_seconds=3600,
                branch={
                    "condition": "No improvement at 60 minutes",
                    "action": "Emergency department transfer. Call ahead.",
                    "severity": "critical",
                },
            ),
            WorkflowStep(
                step=9, type="document", priority="high",
                action="Document everything with timestamps",
                detail="Product + batch number, time of injection, time blanching noticed, time hyaluronidase given, dose, response. Photograph at baseline and every 15–30 min.",
            ),
        ],
    ),

    "anaphylaxis": Workflow(
        complication="anaphylaxis",
        display_name="Anaphylaxis",
        urgency="immediate",
        risk_level="critical",
        time_critical="Minutes. Adrenaline must be given within 5 minutes of recognition.",
        completion_criteria="Patient stable, emergency services on site, biphasic monitoring in place.",
        escalation_trigger="Call 999 at step 1. Do not wait for any other steps before calling.",
        evidence_basis="Resuscitation Council UK 2023; NICE CG134.",
        total_steps=7,
        steps=[
            WorkflowStep(
                step=1, type="action", priority="critical",
                action="Call 999 NOW",
                detail="Do not wait. This is life-threatening. Call while initiating treatment.",
            ),
            WorkflowStep(
                step=2, type="action", priority="critical",
                action="Adrenaline 0.5 mg IM — lateral thigh",
                detail="1:1000 adrenaline, 0.5 ml IM into the anterolateral thigh. Use auto-injector if available.",
                drug="Adrenaline (Epinephrine)",
                dose="0.5 mg IM (0.5 ml of 1:1000). Repeat every 5 min if no improvement.",
                timer_seconds=300,
            ),
            WorkflowStep(
                step=3, type="action", priority="critical",
                action="Lay patient flat — legs elevated",
                detail="Helps maintain blood pressure. If airway compromise: semi-recumbent. Do NOT sit up if hypotensive.",
            ),
            WorkflowStep(
                step=4, type="action", priority="critical",
                action="High-flow oxygen 15 L/min",
                detail="Non-rebreather mask. Maintain SpO2 > 94%.",
                drug="Oxygen",
                dose="15 L/min via non-rebreather mask.",
            ),
            WorkflowStep(
                step=5, type="monitor", priority="critical",
                action="Monitor airway, breathing, pulse continuously",
                detail="Be ready to perform CPR. Document vital signs every 2 minutes.",
                timer_seconds=120,
            ),
            WorkflowStep(
                step=6, type="action", priority="high",
                action="Chlorphenamine 10 mg IM (adjunct only)",
                detail="Antihistamine — secondary to adrenaline. Does NOT replace adrenaline.",
                drug="Chlorphenamine",
                dose="10 mg IM.",
            ),
            WorkflowStep(
                step=7, type="document", priority="high",
                action="Record all times and doses",
                detail="Time of symptom onset, each medication given with dose and time, vital signs, patient response.",
            ),
        ],
    ),

    "ptosis": Workflow(
        complication="ptosis",
        display_name="Botox-Induced Ptosis",
        urgency="same_day",
        risk_level="low",
        time_critical="Not immediately time-critical. Resolves 4–8 weeks typically.",
        completion_criteria="Lid elevation to normal position or patient referred to ophthalmology.",
        escalation_trigger="Diplopia or ophthalmoplegia → urgent ophthalmology.",
        evidence_basis="Clin Ophthalmol 2021; Ophthal Plast Reconstr Surg 2019.",
        total_steps=6,
        steps=[
            WorkflowStep(
                step=1, type="assess", priority="high",
                action="Measure ptosis degree (MRD1)",
                detail="Measure margin-reflex distance 1 (MRD1): distance from corneal reflex to upper lid margin. Normal > 3 mm. Document with photograph.",
                checkpoint="MRD1 measured and documented.",
            ),
            WorkflowStep(
                step=2, type="assess", priority="critical",
                action="Check for diplopia or ophthalmoplegia",
                detail="Ask about double vision. Check extraocular movements. Any abnormality → urgent ophthalmology today.",
                branch={
                    "condition": "Diplopia or restricted eye movement",
                    "action": "Urgent ophthalmology referral today.",
                    "severity": "high",
                },
            ),
            WorkflowStep(
                step=3, type="action", priority="high",
                action="Reassure patient — usually temporary",
                detail="Botulinum toxin ptosis is almost always reversible. Typical duration 4–8 weeks. Very rarely up to 12 weeks.",
            ),
            WorkflowStep(
                step=4, type="action", priority="normal",
                action="Prescribe apraclonidine 0.5% eye drops",
                detail="Alpha-agonist stimulates Müller's muscle → lifts lid 1–2 mm. Use 1–2 drops 3 times daily affected eye only.",
                drug="Apraclonidine 0.5%",
                dose="1–2 drops to affected eye, 3x daily. Continue until resolution.",
            ),
            WorkflowStep(
                step=5, type="monitor", priority="normal",
                action="Review at 2 weeks",
                detail="Measure MRD1 again. Photograph. Adjust apraclonidine if needed.",
            ),
            WorkflowStep(
                step=6, type="document", priority="normal",
                action="Document baseline and plan",
                detail="Photograph, MRD1 measurement, treatment given, follow-up date. Patient counselled regarding expected timeline.",
            ),
        ],
    ),

    "nodule": Workflow(
        complication="nodule",
        display_name="Filler Nodule / Granuloma",
        urgency="same_day",
        risk_level="moderate",
        time_critical="Not immediately time-critical. Assess within days.",
        completion_criteria="Nodule resolved or treatment plan established with follow-up.",
        escalation_trigger="Fluctuance, fever, or spreading erythema → infection protocol.",
        evidence_basis="J Am Acad Dermatol 2022; Dermatol Surg 2021.",
        total_steps=6,
        steps=[
            WorkflowStep(
                step=1, type="assess", priority="high",
                action="Assess: inflammatory vs non-inflammatory",
                detail="Inflammatory: tender, erythematous, warm. Non-inflammatory: firm, painless, mobile. Late nodule: may be hard, immobile.",
                checkpoint="Assessed and classified.",
            ),
            WorkflowStep(
                step=2, type="assess", priority="high",
                action="Check timing and filler type",
                detail="Early (<4 wks): likely inflammatory. Late (>4 wks): possible granuloma or biofilm. HA filler: dissolvable. Non-HA: not dissolvable.",
                branch={
                    "condition": "Fluctuance, fever, or spreading erythema",
                    "action": "Switch to Infection protocol. This may be an abscess or biofilm.",
                    "severity": "high",
                },
            ),
            WorkflowStep(
                step=3, type="action", priority="high",
                action="Hyaluronidase 75–150 IU intralesional (if HA filler)",
                detail="Small volume, intradermal. Start conservatively. Assess at 2 weeks before repeat.",
                drug="Hyaluronidase",
                dose="75–150 IU per nodule. 32g needle, intradermal.",
            ),
            WorkflowStep(
                step=4, type="action", priority="normal",
                action="5-FU + triamcinolone for inflammatory nodule",
                detail="5-FU 50 mg/ml + triamcinolone 40 mg/ml, 1:1 ratio. 0.1–0.2 ml per nodule intralesional. Assess at 4 weeks.",
                drug="5-FU + Triamcinolone",
                dose="0.1–0.2 ml intralesional. Max 3 sessions.",
            ),
            WorkflowStep(
                step=5, type="monitor", priority="normal",
                action="Review at 4 weeks",
                detail="Photograph at each visit. Assess size, consistency, tenderness. Repeat treatment if partial improvement.",
            ),
            WorkflowStep(
                step=6, type="document", priority="normal",
                action="Document and plan follow-up",
                detail="Photograph baseline. Treatment given. Review date. Patient counselled about expected timeline (weeks to months).",
            ),
        ],
    ),

    "infection": Workflow(
        complication="infection",
        display_name="Post-Filler Infection / Biofilm",
        urgency="urgent",
        risk_level="high",
        time_critical="Start antibiotics within hours. Delay risks sepsis.",
        completion_criteria="Infection resolving, antibiotics commenced, follow-up arranged.",
        escalation_trigger="Systemic signs (fever >38°C, spreading erythema, unwell) → A&E same day.",
        evidence_basis="Aesthet Surg J 2022; J Clin Aesthet Dermatol 2021.",
        total_steps=6,
        steps=[
            WorkflowStep(
                step=1, type="assess", priority="critical",
                action="Assess: cellulitis vs abscess vs biofilm",
                detail="Cellulitis: spreading redness, no fluid. Abscess: fluctuant swelling with pus. Biofilm: recurrent, late-onset, firm.",
                checkpoint="Classified. If abscess: step 2 first.",
                branch={
                    "condition": "Fever + spreading erythema + unwell",
                    "action": "A&E referral today. Call ahead.",
                    "severity": "critical",
                },
            ),
            WorkflowStep(
                step=2, type="action", priority="critical",
                action="Drain abscess + swab for MC&S",
                detail="Incise and drain. Send pus for culture including atypical organisms. Document volume and appearance.",
            ),
            WorkflowStep(
                step=3, type="action", priority="critical",
                action="Start antibiotics immediately",
                detail="Co-amoxiclav 625 mg TDS × 7 days. If biofilm suspected: clarithromycin 500 mg BD + ciprofloxacin 500 mg BD × 4–6 weeks.",
                drug="Co-amoxiclav or Dual biofilm therapy",
                dose="Co-amoxiclav 625 mg TDS × 7d. OR clarithromycin 500 mg BD + ciprofloxacin 500 mg BD × 4–6 weeks.",
            ),
            WorkflowStep(
                step=4, type="action", priority="high",
                action="Dissolve HA filler with hyaluronidase",
                detail="If HA filler in infected area: hyaluronidase 1500 IU removes substrate for biofilm.",
                drug="Hyaluronidase",
                dose="1500 IU if HA filler confirmed.",
            ),
            WorkflowStep(
                step=5, type="monitor", priority="critical",
                action="Review at 48 hours",
                detail="If no improvement at 48 hours on antibiotics → refer. Document wound appearance and response.",
                branch={
                    "condition": "No improvement at 48 hours",
                    "action": "Refer to GP or A&E. Consider IV antibiotics.",
                    "severity": "high",
                },
            ),
            WorkflowStep(
                step=6, type="document", priority="high",
                action="Document and report",
                detail="Photograph. Swab results. Antibiotics prescribed with dates. Next review. Adverse event form completed.",
            ),
        ],
    ),

    "tyndall": Workflow(
        complication="tyndall",
        display_name="Tyndall Effect",
        urgency="routine",
        risk_level="low",
        time_critical="Not time-critical. Treat electively.",
        completion_criteria="Blue/grey discolouration resolved.",
        escalation_trigger="If bruising is the cause: do not treat with hyaluronidase — wait for resolution.",
        evidence_basis="Dermatol Surg 2020.",
        total_steps=4,
        steps=[
            WorkflowStep(
                step=1, type="assess", priority="normal",
                action="Confirm Tyndall effect",
                detail="Blue-grey translucent discolouration through thin skin. No erythema, no warmth. Most common: tear trough, lips, nasolabial.",
                checkpoint="Confirmed Tyndall. Not bruising (bruising resolves spontaneously).",
            ),
            WorkflowStep(
                step=2, type="action", priority="normal",
                action="Hyaluronidase 15–75 IU intradermal",
                detail="Conservative starting dose. 32g needle, intradermal injection targeting the superficial filler depot. Assess at 2 weeks.",
                drug="Hyaluronidase",
                dose="15–75 IU intradermal. Very conservative — thin skin area.",
            ),
            WorkflowStep(
                step=3, type="monitor", priority="normal",
                action="Review at 2 weeks",
                detail="Reassess with natural lighting. Repeat if partial improvement. Usually 1–3 sessions required.",
            ),
            WorkflowStep(
                step=4, type="document", priority="normal",
                action="Photograph before and after",
                detail="Standardised lighting and angle. Document dose used at each session.",
            ),
        ],
    ),

    "dir": Workflow(
        complication="dir",
        display_name="Delayed Inflammatory Reaction",
        urgency="same_day",
        risk_level="moderate",
        time_critical="Not immediately time-critical. Treat within 24–48 hours.",
        completion_criteria="Swelling resolving, patient comfortable, follow-up plan in place.",
        escalation_trigger="Airway involvement or features of anaphylaxis → emergency services.",
        evidence_basis="Dermatol Ther 2022; J Dermatol 2021.",
        total_steps=6,
        steps=[
            WorkflowStep(
                step=1, type="assess", priority="high",
                action="Confirm timing and bilateral pattern",
                detail="DIR onset: 2+ weeks post-treatment. Typically bilateral, symmetric swelling. No fever, no systemic illness in most cases.",
                branch={
                    "condition": "Airway involvement or anaphylaxis features",
                    "action": "Anaphylaxis protocol. 999 now.",
                    "severity": "critical",
                },
            ),
            WorkflowStep(
                step=2, type="assess", priority="normal",
                action="Identify systemic trigger",
                detail="Ask: recent viral illness, vaccination, dental work, COVID-19? Common triggers. Helps predict recurrence.",
            ),
            WorkflowStep(
                step=3, type="action", priority="high",
                action="Cetirizine 10 mg daily",
                detail="First-line antihistamine. Reduces histamine-mediated inflammation. Start immediately.",
                drug="Cetirizine",
                dose="10 mg once daily. Continue until swelling resolves.",
            ),
            WorkflowStep(
                step=4, type="action", priority="normal",
                action="Prednisolone 30 mg reducing course (if severe)",
                detail="5-day reducing course for significant swelling. Taper: 30/20/10/5/5 mg.",
                drug="Prednisolone",
                dose="30 mg reducing over 5–7 days.",
            ),
            WorkflowStep(
                step=5, type="action", priority="normal",
                action="Consider dissolving filler if recurrent",
                detail="For 2+ DIR episodes: hyaluronidase 1500 IU to remove trigger. Discuss with patient.",
                drug="Hyaluronidase",
                dose="1500 IU if recurrent DIR.",
            ),
            WorkflowStep(
                step=6, type="document", priority="normal",
                action="Document and counsel patient",
                detail="Photograph. Treatment given. Trigger identified. Review date. Counsel: may recur with future triggers.",
            ),
        ],
    ),

    "necrosis": Workflow(
        complication="necrosis",
        display_name="Skin Necrosis",
        urgency="immediate",
        risk_level="critical",
        time_critical="Urgent. Tissue loss is progressive. Plastic surgery referral within 24–48 hours.",
        completion_criteria="Wound care established. Plastic surgery or wound care specialist involved.",
        escalation_trigger="Any spreading necrosis → same-day plastic surgery referral.",
        evidence_basis="Aesthet Surg J 2021; Plast Reconstr Surg 2020.",
        total_steps=6,
        steps=[
            WorkflowStep(
                step=1, type="action", priority="critical",
                action="Start vascular occlusion treatment NOW",
                detail="Necrosis follows unresolved vascular occlusion. Give hyaluronidase 1500 IU + aspirin 300 mg + warm compress + nitroglycerin paste even if late.",
                drug="Hyaluronidase",
                dose="1500 IU minimum.",
            ),
            WorkflowStep(
                step=2, type="document", priority="critical",
                action="Photograph immediately",
                detail="Essential for medico-legal documentation and surgical planning. Take now and at every review.",
            ),
            WorkflowStep(
                step=3, type="action", priority="critical",
                action="Do NOT debride early",
                detail="Early debridement can extend the zone of damage. Allow natural demarcation. Consult specialist before any debridement.",
            ),
            WorkflowStep(
                step=4, type="action", priority="critical",
                action="Refer to plastic surgery — same day",
                detail="Urgent referral. Call directly, do not just send a letter. Explain timeline, cause, and current state.",
            ),
            WorkflowStep(
                step=5, type="action", priority="high",
                action="Start prophylactic antibiotics",
                detail="Co-amoxiclav 625 mg TDS × 7 days. Reduces infection risk in compromised tissue.",
                drug="Co-amoxiclav",
                dose="625 mg TDS × 7 days.",
            ),
            WorkflowStep(
                step=6, type="document", priority="critical",
                action="Complete adverse event report",
                detail="Document for medical defence. Notify MDO. Retain product batch number. Inform patient and document consent for ongoing care.",
            ),
        ],
    ),
}

# Ensure total_steps matches
for _key, _wf in WORKFLOWS.items():
    _wf.total_steps = len(_wf.steps)


@router.get("/list")
def list_workflows() -> List[Dict[str, Any]]:
    """List all available workflows with metadata."""
    return [
        {
            "key":           key,
            "display_name":  wf.display_name,
            "urgency":       wf.urgency,
            "risk_level":    wf.risk_level,
            "total_steps":   wf.total_steps,
            "time_critical": wf.time_critical,
        }
        for key, wf in WORKFLOWS.items()
    ]


@router.get("")
def get_workflow(
    complication: str = Query(..., min_length=2),
) -> Workflow:
    """
    GET /api/workflow?complication=vascular_occlusion
    Zero latency — pure in-memory.
    """
    if complication in WORKFLOWS:
        return WORKFLOWS[complication]

    norm = complication.lower().replace(" ", "_").replace("-", "_")
    if norm in WORKFLOWS:
        return WORKFLOWS[norm]

    for key, wf in WORKFLOWS.items():
        if (norm in key or key in norm or
                norm in wf.display_name.lower() or
                wf.display_name.lower() in norm):
            return wf

    keywords = norm.split("_")
    for key, wf in WORKFLOWS.items():
        if any(kw in key for kw in keywords if len(kw) > 3):
            return wf

    raise HTTPException(
        status_code=404,
        detail=f"No workflow found for '{complication}'. Available: {list(WORKFLOWS.keys())}",
    )
