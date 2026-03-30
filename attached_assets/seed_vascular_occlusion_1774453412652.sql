-- =========================================
-- AesthetiCite: Vascular Occlusion Protocol Seed
-- Version 1 — Internal Draft
-- =========================================

INSERT INTO public.protocol_definitions (
  id,
  condition_code,
  title,
  applicable_when,
  contraindications,
  required_inputs,
  review_status,
  version,
  step_definitions
)
VALUES (
  'vascular-occlusion-v1',
  'VASCULAR_OCCLUSION',
  'Vascular Occlusion Emergency Protocol',

  -- applicable_when
  '{
    "any_of": [
      "skin_blanching",
      "livedo_reticularis",
      "pain_disproportionate",
      "capillary_refill_delayed",
      "dusky_discolouration",
      "post_filler_skin_change"
    ],
    "procedure_types": [
      "dermal_filler",
      "tear_trough",
      "nasolabial_fold",
      "lip_filler",
      "glabellar_filler",
      "nose_filler",
      "forehead_filler",
      "jawline_filler"
    ]
  }'::jsonb,

  -- contraindications
  '[
    {
      "condition": "known_hyaluronidase_allergy",
      "action": "do_not_administer_hyaluronidase",
      "escalate": true
    },
    {
      "condition": "non_ha_filler_used",
      "action": "hyaluronidase_will_not_dissolve_product",
      "note": "Escalate to vascular surgery or ophthalmology immediately. Supportive measures only."
    }
  ]'::jsonb,

  -- required_inputs
  ARRAY[
    'procedure_type',
    'anatomical_area',
    'product_used',
    'time_since_injection',
    'symptom_onset'
  ],

  -- review_status
  'internal_draft',

  -- version
  1,

  -- step_definitions
  '[
    {
      "step_code": "VO_STEP_01",
      "step_order": 1,
      "title": "STOP injection immediately",
      "action_type": "immediate_action",
      "criticality": "critical",
      "instruction": "Cease all injecting. Do not inject further product.",
      "time_target_seconds": 0
    },
    {
      "step_code": "VO_STEP_02",
      "step_order": 2,
      "title": "Assess skin changes",
      "action_type": "assessment",
      "criticality": "critical",
      "instruction": "Check for: blanching, livedo, dusky/mottled discolouration, delayed cap refill (>2s), pain disproportionate to procedure.",
      "checklist": [
        "Skin blanching present?",
        "Livedo reticularis pattern?",
        "Dusky or grey discolouration?",
        "Capillary refill >2 seconds?",
        "Pain disproportionate to procedure?"
      ],
      "time_target_seconds": 60
    },
    {
      "step_code": "VO_STEP_03",
      "step_order": 3,
      "title": "Assess for ocular symptoms",
      "action_type": "assessment",
      "criticality": "critical",
      "instruction": "Immediately ask patient: any visual changes, eye pain, vision loss, or double vision? Ocular involvement = ophthalmology emergency.",
      "red_flag_triggers": [
        "vision_loss",
        "visual_changes",
        "eye_pain",
        "diplopia",
        "ophthalmoplegia"
      ],
      "branch_logic": {
        "if_visual_symptoms": "ESCALATE_TO_OPHTHALMOLOGY_EMERGENCY",
        "if_no_visual_symptoms": "CONTINUE_TO_VO_STEP_04"
      },
      "time_target_seconds": 60
    },
    {
      "step_code": "VO_STEP_04",
      "step_order": 4,
      "title": "Administer hyaluronidase — immediate high-dose",
      "action_type": "drug_administration",
      "criticality": "critical",
      "instruction": "Administer hyaluronidase immediately. Do not delay for swab or skin prep in an emergency.",
      "dose_support": {
        "calculator_id": "hyaluronidase_vo_calculator",
        "standard_dose_units": 1500,
        "dose_range_units": [1500, 3000],
        "administration_route": "intradermal_and_subcutaneous",
        "injection_guidance": "Inject around and into the affected area. Use fanning technique. Cover full distribution of suspected occlusion zone.",
        "product_examples": ["Hyalase 1500IU", "Vitrase 200 USP units/mL"]
      },
      "time_target_seconds": 300
    },
    {
      "step_code": "VO_STEP_05",
      "step_order": 5,
      "title": "Apply warm compress and massage",
      "action_type": "intervention",
      "criticality": "high",
      "instruction": "Apply warm compress to affected area. Gently massage to promote vasodilation. Do not apply excessive pressure.",
      "duration_minutes": 10,
      "time_target_seconds": 600
    },
    {
      "step_code": "VO_STEP_06",
      "step_order": 6,
      "title": "Reassess at 20 minutes",
      "action_type": "reassessment",
      "criticality": "high",
      "instruction": "Assess skin colour, cap refill, and pain. Document findings with timestamp.",
      "reassessment_criteria": [
        "Skin returning to normal colour?",
        "Capillary refill <2s?",
        "Pain reducing?",
        "Livedo pattern fading?"
      ],
      "branch_logic": {
        "if_improving": "CONTINUE_MONITORING_VO_STEP_07",
        "if_not_improving": "REPEAT_HYALURONIDASE_VO_STEP_04_OR_ESCALATE"
      },
      "time_target_seconds": 1200
    },
    {
      "step_code": "VO_STEP_07",
      "step_order": 7,
      "title": "Consider repeat hyaluronidase if not improving",
      "action_type": "drug_administration",
      "criticality": "high",
      "instruction": "If skin changes persist or worsen at 20 minutes: repeat hyaluronidase 1500IU. May repeat every 30 minutes up to 3 doses.",
      "dose_support": {
        "calculator_id": "hyaluronidase_vo_calculator",
        "repeat_dose_units": 1500,
        "max_doses": 3,
        "interval_minutes": 30
      },
      "time_target_seconds": 300
    },
    {
      "step_code": "VO_STEP_08",
      "step_order": 8,
      "title": "Escalation decision",
      "action_type": "escalation",
      "criticality": "critical",
      "instruction": "If no improvement after 2 doses or any clinical deterioration: transfer to A&E or vascular surgery immediately. Call ahead.",
      "escalation_triggers": [
        "No improvement after 2 hyaluronidase doses",
        "Skin necrosis signs developing",
        "Any new ocular symptoms",
        "Patient haemodynamically unstable",
        "Non-HA filler suspected"
      ],
      "escalation_targets": [
        "accident_and_emergency",
        "vascular_surgery",
        "ophthalmology_if_ocular_symptoms"
      ]
    },
    {
      "step_code": "VO_STEP_09",
      "step_order": 9,
      "title": "Monitoring and follow-up plan",
      "action_type": "documentation",
      "criticality": "moderate",
      "instruction": "Arrange next-day review minimum. Document full timeline, doses, and clinical response. Complete MDO-standard incident form.",
      "followup_instructions": [
        "Review at 24 hours",
        "Review at 72 hours",
        "Photograph all areas at each review",
        "Prescribe aspirin 300mg if not contraindicated",
        "Consider topical GTN cream per local protocol",
        "Complete incident documentation before end of session"
      ]
    },
    {
      "step_code": "VO_STEP_10",
      "step_order": 10,
      "title": "Documentation and medico-legal record",
      "action_type": "documentation",
      "criticality": "high",
      "instruction": "Generate full AesthetiCite medico-legal PDF. Include: timestamp of onset, all interventions with doses and times, clinical direction, disposition, follow-up plan.",
      "documentation_fields": [
        "time_of_suspected_occlusion",
        "first_hyaluronidase_dose_time",
        "doses_administered",
        "clinical_response_timeline",
        "disposition",
        "followup_plan",
        "clinician_signature"
      ]
    }
  ]'::jsonb
)
ON CONFLICT (condition_code, version) DO NOTHING;


-- =========================================
-- Anaphylaxis Protocol — Seed v1
-- =========================================

INSERT INTO public.protocol_definitions (
  id,
  condition_code,
  title,
  applicable_when,
  contraindications,
  required_inputs,
  review_status,
  version,
  step_definitions
)
VALUES (
  'anaphylaxis-v1',
  'ANAPHYLAXIS',
  'Anaphylaxis Emergency Protocol',

  '{
    "any_of": [
      "urticaria_generalised",
      "angioedema",
      "bronchospasm",
      "hypotension",
      "tachycardia_unexplained",
      "loss_of_consciousness",
      "stridor",
      "rapid_symptom_onset_post_injection"
    ]
  }'::jsonb,

  '[]'::jsonb,

  ARRAY[
    'symptom_onset_minutes',
    'known_allergies',
    'weight_kg'
  ],

  'internal_draft',
  1,

  '[
    {
      "step_code": "ANA_STEP_01",
      "step_order": 1,
      "title": "Call 999 / emergency services immediately",
      "action_type": "immediate_action",
      "criticality": "critical",
      "instruction": "Call 999 (UK) or local emergency number. Do not delay. State: anaphylaxis following aesthetic injectable procedure.",
      "time_target_seconds": 30
    },
    {
      "step_code": "ANA_STEP_02",
      "step_order": 2,
      "title": "Lay patient flat — legs elevated",
      "action_type": "immediate_action",
      "criticality": "critical",
      "instruction": "Lie patient flat. Raise legs unless airway compromise or breathing difficulty. Do not allow them to sit or stand.",
      "time_target_seconds": 60
    },
    {
      "step_code": "ANA_STEP_03",
      "step_order": 3,
      "title": "Administer adrenaline (epinephrine) IM",
      "action_type": "drug_administration",
      "criticality": "critical",
      "instruction": "Administer adrenaline 1:1000 IM into outer mid-thigh. Use auto-injector if available.",
      "dose_support": {
        "calculator_id": "adrenaline_anaphylaxis_calculator",
        "adult_dose_mg": 0.5,
        "adult_dose_volume_ml": 0.5,
        "concentration": "1:1000",
        "route": "intramuscular_outer_thigh",
        "auto_injector": "EpiPen 0.3mg if available",
        "repeat_interval_minutes": 5,
        "max_doses": 3
      },
      "time_target_seconds": 120
    },
    {
      "step_code": "ANA_STEP_04",
      "step_order": 4,
      "title": "Monitor and reassess every 5 minutes",
      "action_type": "reassessment",
      "criticality": "critical",
      "instruction": "Monitor: HR, BP, SpO2, consciousness, breathing. Repeat adrenaline every 5 minutes if no improvement.",
      "time_target_seconds": 300
    },
    {
      "step_code": "ANA_STEP_05",
      "step_order": 5,
      "title": "Airway management",
      "action_type": "assessment",
      "criticality": "critical",
      "instruction": "If stridor or severe airway compromise: prepare for airway management. If trained: supplemental O2. Position: recovery if unconscious and breathing.",
      "time_target_seconds": 120
    },
    {
      "step_code": "ANA_STEP_06",
      "step_order": 6,
      "title": "Document and handover to paramedics",
      "action_type": "documentation",
      "criticality": "high",
      "instruction": "Record: time of reaction, product used, doses of adrenaline and timing, patient vitals. Hand over to paramedics on arrival.",
      "documentation_fields": [
        "time_of_onset",
        "product_used",
        "adrenaline_doses_and_times",
        "patient_vitals_on_handover",
        "known_allergies"
      ]
    }
  ]'::jsonb
)
ON CONFLICT (condition_code, version) DO NOTHING;
