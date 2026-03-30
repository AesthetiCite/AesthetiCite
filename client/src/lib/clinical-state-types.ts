/**
 * AesthetiCite — Clinical State Types (v2)
 * client/src/lib/clinical-state-types.ts
 *
 * Aligned with the Clinical Safety State Engine spec.
 */

export type UUID = string;
export type ISODateTime = string;

export type CaseStatus = "draft" | "active" | "paused" | "closed" | "open" | "escalated";
export type CaseMode =
  | "acute_complication"
  | "pre_procedure_safety"
  | "post_procedure_followup"
  | "emergency"
  | "standard"
  | "elective"
  | "training";

export type ClinicalPhase =
  | "intake"
  | "assessment"
  | "intervention"
  | "reassessment"
  | "disposition";

export type SeverityLevel = "low" | "moderate" | "high" | "critical";
export type ProtocolRunStatus = "in_progress" | "completed" | "aborted";
export type ProtocolStepStatus = "pending" | "ready" | "completed" | "skipped" | "blocked";

export type InterventionCategory =
  | "assessment"
  | "drug_administration"
  | "escalation"
  | "advice_given"
  | "referral"
  | "documentation"
  | "observation";

export type ClinicalDirection = "improving" | "unchanged" | "worsening" | "resolved";

export type DispositionType =
  | "managed_in_clinic_with_close_followup"
  | "urgent_hospital_referral"
  | "ophthalmology_emergency_referral"
  | "ambulance_transfer"
  | "resolved_and_discharged";

export type ReviewStatus = "internal_draft" | "clinical_review" | "approved" | "retired";

// ─── Nested value objects ───────────────────────────────────────────────────

export interface Allergy {
  substance: string;
  reaction?: string | null;
  severity?: string | null;
}

export interface ProductUsed {
  product_name: string;
  category?: string | null;
  lot_number?: string | null;
  volume_ml?: number | null;
}

export interface Technique {
  device?: "needle" | "cannula" | "mixed" | "unknown" | string;
  gauge?: string | null;
  plane?: string | null;
  bolus_or_linear?: string | null;
  [key: string]: unknown;
}

export interface SymptomEntry {
  name: string;
  present: boolean;
  severity?: number | null;
  onset?: string | null;
  distribution?: string | null;
}

export interface VitalSigns {
  heart_rate?: number | null;
  systolic_bp?: number | null;
  diastolic_bp?: number | null;
  spo2?: number | null;
  temperature_c?: number | null;
  [key: string]: unknown;
}

export interface VisualSymptoms {
  present?: boolean;
  symptoms?: string[];
  [key: string]: unknown;
}

export interface DiagnosisCandidate {
  code: string;
  label: string;
  confidence: number;
}

export interface ProtocolStepDefinition {
  step_code: string;
  step_order: number;
  title: string;
  action_type?: string;
  criticality?: string;
}

export interface DoseSupport {
  calculator_id?: string;
  suggested_range_units?: number[];
  [key: string]: unknown;
}

export interface RecommendedNextAction {
  action_code?: string;
  urgency?: string;
  rationale?: string;
  [key: string]: unknown;
}

// ─── Entity shapes ──────────────────────────────────────────────────────────

export interface CaseSession {
  id: UUID;
  clinic_id?: UUID | null;
  chief_concern?: string | null;
  status: CaseStatus;
  mode: CaseMode;
  language: string;
  country?: string | null;
  tags: string[];
  created_by_user_id?: UUID | null;
  notes?: string | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface CaseSessionCreate {
  clinic_id?: UUID | null;
  status?: CaseStatus;
  mode?: CaseMode;
  chief_concern?: string | null;
  language?: string;
  country?: string | null;
  tags?: string[];
  created_by_user_id?: UUID | null;
  notes?: string | null;
}

export interface CaseSessionUpdate {
  clinic_id?: UUID | null;
  status?: CaseStatus;
  mode?: CaseMode;
  chief_concern?: string | null;
  language?: string;
  country?: string | null;
  tags?: string[];
  notes?: string | null;
}

export interface PatientContext {
  id: UUID;
  case_id: UUID;
  patient_ref?: string | null;
  age?: number | null;
  sex?: string | null;
  pregnancy_status?: string | null;
  weight_kg?: number | null;
  consent_status?: string | null;
  known_allergies: Allergy[];
  relevant_history: string[];
  current_medications: string[];
  risk_flags: string[];
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface ProcedureContext {
  id: UUID;
  case_id: UUID;
  procedure_type?: string | null;
  subtype?: string | null;
  treatment_date_time?: ISODateTime | null;
  operator_role?: string | null;
  anatomical_areas: string[];
  products_used: ProductUsed[];
  technique?: Technique | null;
  procedure_notes?: string | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface ClinicalStateSnapshot {
  id: UUID;
  case_id: UUID;
  state_version: number;
  phase?: ClinicalPhase | null;
  time_since_procedure_minutes?: number | null;
  symptoms: SymptomEntry[];
  vital_signs?: VitalSigns | null;
  red_flags: string[];
  airway_risk: boolean;
  visual_symptoms?: VisualSymptoms | null;
  photos_attached: boolean;
  free_text_observations?: string | null;
  recorded_at: ISODateTime;
  created_at: ISODateTime;
}

export interface ClinicalImpression {
  id: UUID;
  case_id: UUID;
  derived_from_state_id?: UUID | null;
  primary_diagnosis: DiagnosisCandidate;
  differentials: DiagnosisCandidate[];
  severity_level?: SeverityLevel | null;
  severity_rationale: string[];
  vision_emergency: boolean;
  anaphylaxis_probability?: number | null;
  needs_immediate_action: boolean;
  generated_by: string;
  reasoning?: string | null;
  generated_at: ISODateTime;
  created_at: ISODateTime;
}

export interface ProtocolDefinition {
  id: string;
  condition_code: string;
  title: string;
  applicable_when: Record<string, unknown>;
  contraindications: unknown[];
  required_inputs: string[];
  review_status: ReviewStatus;
  version: number;
  step_definitions: ProtocolStepDefinition[];
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface ProtocolRun {
  id: UUID;
  case_id: UUID;
  protocol_id: string;
  status: ProtocolRunStatus;
  current_step_order?: number | null;
  outcome_notes?: string | null;
  started_at: ISODateTime;
  completed_at?: ISODateTime | null;
  created_at?: ISODateTime;
  updated_at?: ISODateTime;
}

export interface ProtocolRunStep {
  id: UUID;
  protocol_run_id: UUID;
  step_code: string;
  step_order: number;
  title: string;
  status: ProtocolStepStatus;
  performed_by?: string | null;
  notes?: string | null;
  dose_support?: DoseSupport | null;
  completed_at?: ISODateTime | null;
  created_at: ISODateTime;
  updated_at?: ISODateTime;
}

export interface InterventionEvent {
  id: UUID;
  case_id: UUID;
  linked_run_step_id?: UUID | null;
  category: InterventionCategory;
  action: string;
  details: Record<string, unknown>;
  performed_by?: string | null;
  immediate_response?: string | null;
  performed_at: ISODateTime;
  created_at: ISODateTime;
}

export interface ReassessmentEvent {
  id: UUID;
  case_id: UUID;
  findings: Record<string, unknown>;
  clinical_direction: ClinicalDirection;
  recommended_next_action?: RecommendedNextAction | null;
  next_reassessment_due_in_minutes?: number | null;
  time_since_last_intervention_minutes?: number | null;
  performed_by?: string | null;
  performed_at: ISODateTime;
  created_at: ISODateTime;
}

export interface DispositionPlan {
  id: UUID;
  case_id: UUID;
  disposition: DispositionType;
  escalation_required: boolean;
  escalation_reason?: string | null;
  followup_plan: string[];
  patient_advice: string[];
  owner?: string | null;
  decided_by?: string | null;
  decision_time: ISODateTime;
  created_at: ISODateTime;
}

// ─── Live view ──────────────────────────────────────────────────────────────

export interface AlertItemLive {
  type: "critical" | "high" | "warning" | "info" | "urgent";
  message: string;
}

export interface CaseLiveView {
  case_header: {
    case_id: UUID;
    chief_concern?: string | null;
    status: string;
    severity?: SeverityLevel | null;
  };
  patient_summary?: {
    age?: number | null;
    risk_flags: string[];
  } | null;
  procedure_summary?: {
    procedure_type?: string | null;
    area: string[];
    product: string[];
  } | null;
  current_impression?: {
    primary_diagnosis?: string | null;
    confidence?: number | null;
    needs_immediate_action?: boolean | null;
  } | null;
  current_protocol?: {
    title?: string | null;
    current_step_order?: number | null;
    next_step?: string | null;
  } | null;
  timers: {
    minutes_since_procedure?: number | null;
    next_reassessment_due_in_minutes?: number | null;
  };
  alerts: AlertItemLive[];
  evidence_summary?: {
    aci_score?: number | null;
    confidence_label?: string | null;
    top_sources: string[];
  } | null;
}
