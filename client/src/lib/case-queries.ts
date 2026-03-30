/**
 * AesthetiCite — Clinical Case Query Helpers (v2)
 * client/src/lib/case-queries.ts
 *
 * Typed fetch helpers for all case lifecycle operations.
 * Uses the project's own FastAPI backend at /api/clinical-cases.
 * All requests are authenticated via the Bearer token from localStorage.
 */

import type {
  CaseSession,
  CaseSessionCreate,
  CaseSessionUpdate,
  PatientContext,
  ProcedureContext,
  ClinicalStateSnapshot,
  ClinicalImpression,
  ProtocolRun,
  ProtocolRunStep,
  InterventionEvent,
  ReassessmentEvent,
  DispositionPlan,
  CaseLiveView,
  CaseMode,
  CaseStatus,
  ProtocolDefinition,
} from "./clinical-state-types";

// ─────────────────────────────────────────────────────────────────
// UTILITY
// ─────────────────────────────────────────────────────────────────

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem("access_token") || sessionStorage.getItem("access_token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...options,
    headers: { ...getAuthHeaders(), ...(options.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

const BASE = "/clinical-cases";

// ─────────────────────────────────────────────────────────────────
// CASES
// ─────────────────────────────────────────────────────────────────

export async function createCase(payload: CaseSessionCreate): Promise<CaseSession> {
  return apiFetch<CaseSession>(BASE, { method: "POST", body: JSON.stringify(payload) });
}

export async function getCase(caseId: string): Promise<CaseSession> {
  return apiFetch<CaseSession>(`${BASE}/${caseId}`);
}

export async function updateCase(caseId: string, payload: CaseSessionUpdate): Promise<CaseSession> {
  return apiFetch<CaseSession>(`${BASE}/${caseId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function listCases(options?: {
  status?: CaseStatus;
  mode?: CaseMode;
  limit?: number;
  offset?: number;
}): Promise<CaseSession[]> {
  const params = new URLSearchParams();
  if (options?.status) params.set("status", options.status);
  if (options?.mode) params.set("mode", options.mode);
  if (options?.limit != null) params.set("limit", String(options.limit));
  if (options?.offset != null) params.set("offset", String(options.offset));
  const qs = params.toString();
  return apiFetch<CaseSession[]>(`${BASE}${qs ? `?${qs}` : ""}`);
}

// ─────────────────────────────────────────────────────────────────
// PATIENT CONTEXT
// ─────────────────────────────────────────────────────────────────

export async function upsertPatientContext(
  caseId: string,
  payload: Omit<PatientContext, "id" | "case_id" | "created_at" | "updated_at">
): Promise<PatientContext> {
  return apiFetch<PatientContext>(`${BASE}/${caseId}/patient-context`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

// ─────────────────────────────────────────────────────────────────
// PROCEDURE CONTEXT
// ─────────────────────────────────────────────────────────────────

export async function upsertProcedureContext(
  caseId: string,
  payload: Omit<ProcedureContext, "id" | "case_id" | "created_at" | "updated_at">
): Promise<ProcedureContext> {
  return apiFetch<ProcedureContext>(`${BASE}/${caseId}/procedure-context`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

// ─────────────────────────────────────────────────────────────────
// CLINICAL STATE SNAPSHOTS
// ─────────────────────────────────────────────────────────────────

export async function appendClinicalState(
  caseId: string,
  payload: Omit<ClinicalStateSnapshot, "id" | "case_id" | "state_version" | "created_at" | "recorded_at">
): Promise<ClinicalStateSnapshot> {
  return apiFetch<ClinicalStateSnapshot>(`${BASE}/${caseId}/states`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ─────────────────────────────────────────────────────────────────
// CLINICAL IMPRESSIONS
// ─────────────────────────────────────────────────────────────────

export async function createImpression(
  caseId: string,
  payload: Omit<ClinicalImpression, "id" | "case_id" | "generated_at" | "created_at">
): Promise<ClinicalImpression> {
  return apiFetch<ClinicalImpression>(`${BASE}/${caseId}/impressions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ─────────────────────────────────────────────────────────────────
// PROTOCOL RUNS
// ─────────────────────────────────────────────────────────────────

export async function startProtocolRun(caseId: string, protocolId: string): Promise<ProtocolRun> {
  return apiFetch<ProtocolRun>(`${BASE}/${caseId}/protocol-runs`, {
    method: "POST",
    body: JSON.stringify({ protocol_id: protocolId }),
  });
}

/**
 * Auto-selects and starts the best-matched protocol based on the case's
 * current procedure context and latest clinical state snapshot.
 * Throws an API error if no protocol matches.
 */
export async function autoStartProtocol(caseId: string): Promise<ProtocolRun> {
  return apiFetch<ProtocolRun>(`${BASE}/${caseId}/auto-start-protocol`, {
    method: "POST",
  });
}

export async function updateProtocolRun(
  runId: string,
  payload: Partial<Pick<ProtocolRun, "status" | "current_step_order" | "outcome_notes" | "completed_at">>
): Promise<ProtocolRun> {
  return apiFetch<ProtocolRun>(`/protocol-runs/${runId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function completeProtocolStep(
  stepId: string,
  opts?: { performed_by?: string; notes?: string }
): Promise<ProtocolRunStep> {
  return apiFetch<ProtocolRunStep>(`/protocol-run-steps/${stepId}`, {
    method: "PATCH",
    body: JSON.stringify({
      status: "completed",
      completed_at: new Date().toISOString(),
      performed_by: opts?.performed_by ?? null,
      notes: opts?.notes ?? null,
    }),
  });
}

export async function abortProtocolRun(runId: string): Promise<ProtocolRun> {
  return apiFetch<ProtocolRun>(`/protocol-runs/${runId}`, {
    method: "PATCH",
    body: JSON.stringify({ status: "aborted", completed_at: new Date().toISOString() }),
  });
}

// ─────────────────────────────────────────────────────────────────
// INTERVENTIONS
// ─────────────────────────────────────────────────────────────────

export async function logIntervention(
  caseId: string,
  payload: Omit<InterventionEvent, "id" | "case_id" | "performed_at" | "created_at">
): Promise<InterventionEvent> {
  return apiFetch<InterventionEvent>(`${BASE}/${caseId}/interventions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ─────────────────────────────────────────────────────────────────
// REASSESSMENTS
// ─────────────────────────────────────────────────────────────────

export async function logReassessment(
  caseId: string,
  payload: Omit<ReassessmentEvent, "id" | "case_id" | "performed_at" | "created_at">
): Promise<ReassessmentEvent> {
  return apiFetch<ReassessmentEvent>(`${BASE}/${caseId}/reassessments`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ─────────────────────────────────────────────────────────────────
// DISPOSITION
// ─────────────────────────────────────────────────────────────────

export async function setDisposition(
  caseId: string,
  payload: Omit<DispositionPlan, "id" | "case_id" | "decision_time" | "created_at">
): Promise<DispositionPlan> {
  return apiFetch<DispositionPlan>(`${BASE}/${caseId}/disposition`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ─────────────────────────────────────────────────────────────────
// LIVE VIEW
// ─────────────────────────────────────────────────────────────────

export async function getCaseLiveView(caseId: string): Promise<CaseLiveView> {
  return apiFetch<CaseLiveView>(`${BASE}/${caseId}/live-view`);
}

// ─────────────────────────────────────────────────────────────────
// PROTOCOL DEFINITIONS (read-only)
// ─────────────────────────────────────────────────────────────────

export async function listProtocols(): Promise<
  Array<Pick<ProtocolDefinition, "id" | "condition_code" | "title" | "review_status" | "version">>
> {
  return apiFetch("/protocols");
}

export async function getProtocol(protocolId: string): Promise<ProtocolDefinition> {
  return apiFetch(`/protocols/${protocolId}`);
}
