/**
 * AesthetiCite — Supabase Typed Query Helpers
 * src/lib/supabase-queries.ts
 *
 * Covers all case lifecycle operations needed by the frontend:
 *   - createCase
 *   - getCase
 *   - upsertPatientContext
 *   - upsertProcedureContext
 *   - appendClinicalState
 *   - createImpression
 *   - startProtocolRun
 *   - completeProtocolStep
 *   - logIntervention
 *   - logReassessment
 *   - setDisposition
 *   - getCaseLiveView (via FastAPI — not Supabase direct)
 *   - listCases
 *
 * Usage:
 *   All functions accept a SupabaseClient instance so they work with
 *   both the browser client and the server-side admin client.
 */

import type { SupabaseClient } from "@supabase/supabase-js";
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
} from "./clinical-state-types";

// ─────────────────────────────────────────────────────────────────
// UTILITY
// ─────────────────────────────────────────────────────────────────

function throwOnError<T>(data: T | null, error: unknown): T {
  if (error) throw error;
  if (data === null) throw new Error("No data returned");
  return data;
}

// ─────────────────────────────────────────────────────────────────
// CASES
// ─────────────────────────────────────────────────────────────────

export async function createCase(
  supabase: SupabaseClient,
  payload: Omit<CaseSessionCreate, "created_by_user_id">
): Promise<CaseSession> {
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("Not authenticated");

  const { data, error } = await supabase
    .from("case_sessions")
    .insert({ ...payload, created_by_user_id: user.id })
    .select()
    .single();

  return throwOnError(data, error) as CaseSession;
}

export async function getCase(
  supabase: SupabaseClient,
  caseId: string
): Promise<CaseSession> {
  const { data, error } = await supabase
    .from("case_sessions")
    .select("*")
    .eq("id", caseId)
    .single();

  return throwOnError(data, error) as CaseSession;
}

export async function updateCase(
  supabase: SupabaseClient,
  caseId: string,
  payload: CaseSessionUpdate
): Promise<CaseSession> {
  const { data, error } = await supabase
    .from("case_sessions")
    .update(payload)
    .eq("id", caseId)
    .select()
    .single();

  return throwOnError(data, error) as CaseSession;
}

export async function listCases(
  supabase: SupabaseClient,
  options?: {
    status?: CaseStatus;
    mode?: CaseMode;
    limit?: number;
    offset?: number;
  }
): Promise<CaseSession[]> {
  let query = supabase
    .from("case_sessions")
    .select("*")
    .order("created_at", { ascending: false });

  if (options?.status) query = query.eq("status", options.status);
  if (options?.mode) query = query.eq("mode", options.mode);
  if (options?.limit) query = query.limit(options.limit);
  if (options?.offset) query = query.range(
    options.offset,
    options.offset + (options.limit ?? 20) - 1
  );

  const { data, error } = await query;
  return throwOnError(data, error) as CaseSession[];
}

// ─────────────────────────────────────────────────────────────────
// PATIENT CONTEXT
// ─────────────────────────────────────────────────────────────────

export async function upsertPatientContext(
  supabase: SupabaseClient,
  caseId: string,
  payload: Omit<PatientContext, "id" | "case_id" | "created_at" | "updated_at">
): Promise<PatientContext> {
  const { data, error } = await supabase
    .from("patient_contexts")
    .upsert(
      { ...payload, case_id: caseId },
      { onConflict: "case_id" }
    )
    .select()
    .single();

  return throwOnError(data, error) as PatientContext;
}

export async function getPatientContext(
  supabase: SupabaseClient,
  caseId: string
): Promise<PatientContext | null> {
  const { data, error } = await supabase
    .from("patient_contexts")
    .select("*")
    .eq("case_id", caseId)
    .maybeSingle();

  if (error) throw error;
  return data as PatientContext | null;
}

// ─────────────────────────────────────────────────────────────────
// PROCEDURE CONTEXT
// ─────────────────────────────────────────────────────────────────

export async function upsertProcedureContext(
  supabase: SupabaseClient,
  caseId: string,
  payload: Omit<ProcedureContext, "id" | "case_id" | "created_at" | "updated_at">
): Promise<ProcedureContext> {
  const { data, error } = await supabase
    .from("procedure_contexts")
    .upsert(
      { ...payload, case_id: caseId },
      { onConflict: "case_id" }
    )
    .select()
    .single();

  return throwOnError(data, error) as ProcedureContext;
}

// ─────────────────────────────────────────────────────────────────
// CLINICAL STATE SNAPSHOTS
// Always append — never overwrite
// ─────────────────────────────────────────────────────────────────

export async function appendClinicalState(
  supabase: SupabaseClient,
  caseId: string,
  payload: Omit<ClinicalStateSnapshot, "id" | "case_id" | "state_version" | "created_at" | "recorded_at">
): Promise<ClinicalStateSnapshot> {
  // Get current max version
  const { data: existing } = await supabase
    .from("clinical_state_snapshots")
    .select("state_version")
    .eq("case_id", caseId)
    .order("state_version", { ascending: false })
    .limit(1)
    .maybeSingle();

  const nextVersion = existing ? (existing as { state_version: number }).state_version + 1 : 1;

  const { data, error } = await supabase
    .from("clinical_state_snapshots")
    .insert({ ...payload, case_id: caseId, state_version: nextVersion })
    .select()
    .single();

  return throwOnError(data, error) as ClinicalStateSnapshot;
}

export async function getClinicalStateHistory(
  supabase: SupabaseClient,
  caseId: string
): Promise<ClinicalStateSnapshot[]> {
  const { data, error } = await supabase
    .from("clinical_state_snapshots")
    .select("*")
    .eq("case_id", caseId)
    .order("state_version", { ascending: true });

  return throwOnError(data, error) as ClinicalStateSnapshot[];
}

// ─────────────────────────────────────────────────────────────────
// CLINICAL IMPRESSIONS
// ─────────────────────────────────────────────────────────────────

export async function createImpression(
  supabase: SupabaseClient,
  caseId: string,
  payload: Omit<ClinicalImpression, "id" | "case_id" | "generated_at" | "created_at">
): Promise<ClinicalImpression> {
  const { data, error } = await supabase
    .from("clinical_impressions")
    .insert({ ...payload, case_id: caseId })
    .select()
    .single();

  return throwOnError(data, error) as ClinicalImpression;
}

export async function getLatestImpression(
  supabase: SupabaseClient,
  caseId: string
): Promise<ClinicalImpression | null> {
  const { data, error } = await supabase
    .from("clinical_impressions")
    .select("*")
    .eq("case_id", caseId)
    .order("generated_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) throw error;
  return data as ClinicalImpression | null;
}

// ─────────────────────────────────────────────────────────────────
// PROTOCOL RUNS
// ─────────────────────────────────────────────────────────────────

export async function startProtocolRun(
  supabase: SupabaseClient,
  caseId: string,
  protocolId: string
): Promise<ProtocolRun> {
  const { data, error } = await supabase
    .from("protocol_runs")
    .insert({
      case_id: caseId,
      protocol_id: protocolId,
      status: "in_progress",
      current_step_order: 1,
    })
    .select()
    .single();

  return throwOnError(data, error) as ProtocolRun;
}

export async function getActiveProtocolRun(
  supabase: SupabaseClient,
  caseId: string
): Promise<ProtocolRun | null> {
  const { data, error } = await supabase
    .from("protocol_runs")
    .select("*")
    .eq("case_id", caseId)
    .eq("status", "in_progress")
    .order("started_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) throw error;
  return data as ProtocolRun | null;
}

export async function getProtocolRunSteps(
  supabase: SupabaseClient,
  protocolRunId: string
): Promise<ProtocolRunStep[]> {
  const { data, error } = await supabase
    .from("protocol_run_steps")
    .select("*")
    .eq("protocol_run_id", protocolRunId)
    .order("step_order", { ascending: true });

  return throwOnError(data, error) as ProtocolRunStep[];
}

export async function completeProtocolStep(
  supabase: SupabaseClient,
  stepId: string,
  opts?: { performed_by?: string; notes?: string }
): Promise<ProtocolRunStep> {
  const { data, error } = await supabase
    .from("protocol_run_steps")
    .update({
      status: "completed",
      completed_at: new Date().toISOString(),
      performed_by: opts?.performed_by ?? null,
      notes: opts?.notes ?? null,
    })
    .eq("id", stepId)
    .select()
    .single();

  return throwOnError(data, error) as ProtocolRunStep;
}

export async function abortProtocolRun(
  supabase: SupabaseClient,
  runId: string
): Promise<ProtocolRun> {
  const { data, error } = await supabase
    .from("protocol_runs")
    .update({ status: "aborted", completed_at: new Date().toISOString() })
    .eq("id", runId)
    .select()
    .single();

  return throwOnError(data, error) as ProtocolRun;
}

// ─────────────────────────────────────────────────────────────────
// INTERVENTIONS
// ─────────────────────────────────────────────────────────────────

export async function logIntervention(
  supabase: SupabaseClient,
  caseId: string,
  payload: Omit<InterventionEvent, "id" | "case_id" | "performed_at" | "created_at">
): Promise<InterventionEvent> {
  const { data, error } = await supabase
    .from("intervention_events")
    .insert({ ...payload, case_id: caseId })
    .select()
    .single();

  return throwOnError(data, error) as InterventionEvent;
}

export async function getInterventionTimeline(
  supabase: SupabaseClient,
  caseId: string
): Promise<InterventionEvent[]> {
  const { data, error } = await supabase
    .from("intervention_events")
    .select("*")
    .eq("case_id", caseId)
    .order("performed_at", { ascending: true });

  return throwOnError(data, error) as InterventionEvent[];
}

// ─────────────────────────────────────────────────────────────────
// REASSESSMENTS
// ─────────────────────────────────────────────────────────────────

export async function logReassessment(
  supabase: SupabaseClient,
  caseId: string,
  payload: Omit<ReassessmentEvent, "id" | "case_id" | "performed_at" | "created_at">
): Promise<ReassessmentEvent> {
  const { data, error } = await supabase
    .from("reassessment_events")
    .insert({ ...payload, case_id: caseId })
    .select()
    .single();

  return throwOnError(data, error) as ReassessmentEvent;
}

// ─────────────────────────────────────────────────────────────────
// DISPOSITION
// ─────────────────────────────────────────────────────────────────

export async function setDisposition(
  supabase: SupabaseClient,
  caseId: string,
  payload: Omit<DispositionPlan, "id" | "case_id" | "decision_time" | "created_at">
): Promise<DispositionPlan> {
  const { data, error } = await supabase
    .from("disposition_plans")
    .insert({ ...payload, case_id: caseId })
    .select()
    .single();

  // Close the case
  await supabase
    .from("case_sessions")
    .update({ status: "closed" })
    .eq("id", caseId);

  return throwOnError(data, error) as DispositionPlan;
}

// ─────────────────────────────────────────────────────────────────
// LIVE VIEW (via FastAPI)
// Supabase doesn't aggregate this — FastAPI does the assembly
// ─────────────────────────────────────────────────────────────────

export async function getCaseLiveView(
  caseId: string,
  authToken: string,
  apiBase = "/api"
): Promise<CaseLiveView> {
  const res = await fetch(`${apiBase}/cases/${caseId}/live-view`, {
    headers: {
      Authorization: `Bearer ${authToken}`,
      "Content-Type": "application/json",
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Live view failed: ${res.status} ${body}`);
  }
  return res.json() as Promise<CaseLiveView>;
}

// ─────────────────────────────────────────────────────────────────
// PROTOCOL DEFINITIONS (read-only, public)
// ─────────────────────────────────────────────────────────────────

export async function listProtocols(supabase: SupabaseClient) {
  const { data, error } = await supabase
    .from("protocol_definitions")
    .select("id, condition_code, title, review_status, version")
    .order("condition_code");

  return throwOnError(data, error);
}

export async function getProtocol(
  supabase: SupabaseClient,
  protocolId: string
) {
  const { data, error } = await supabase
    .from("protocol_definitions")
    .select("*")
    .eq("id", protocolId)
    .single();

  return throwOnError(data, error);
}

// ─────────────────────────────────────────────────────────────────
// REAL-TIME SUBSCRIPTION: live case updates
// ─────────────────────────────────────────────────────────────────

export function subscribeToCaseChanges(
  supabase: SupabaseClient,
  caseId: string,
  onUpdate: (payload: unknown) => void
) {
  return supabase
    .channel(`case-${caseId}`)
    .on(
      "postgres_changes",
      {
        event: "*",
        schema: "public",
        table: "case_sessions",
        filter: `id=eq.${caseId}`,
      },
      onUpdate
    )
    .on(
      "postgres_changes",
      {
        event: "INSERT",
        schema: "public",
        table: "clinical_state_snapshots",
        filter: `case_id=eq.${caseId}`,
      },
      onUpdate
    )
    .on(
      "postgres_changes",
      {
        event: "INSERT",
        schema: "public",
        table: "intervention_events",
        filter: `case_id=eq.${caseId}`,
      },
      onUpdate
    )
    .subscribe();
}
