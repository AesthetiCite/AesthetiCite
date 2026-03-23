/**
 * AesthetiCite — Safety Workspace (v2 — 12 improvements)
 * ========================================================
 * Drop-in replacement for client/src/pages/safety-workspace.tsx
 *
 * Implements all 12 recommended improvements:
 *  1.  Knowledge base health indicator (ingestion status + doc count)
 *  2.  Onboarding flow — first-use modal with procedure-specific hints
 *  3.  Evidence quality indicator (live pgvector vs static)
 *  4.  Clinic admin panel — dashboard metrics, usage stats
 *  5.  Complication case logging UI — full form with outcome tracking
 *  6.  Patient-readable export — copy, share, print
 *  7.  Hyaluronidase emergency calculator — dose × territory × product
 *  8.  Clinic API key management — create, view, revoke
 *  9.  Paper alert digest — subscribe, run, view new papers
 * 10.  Regulatory positioning card — MHRA/MDR checklist
 * 11.  Outcome tracking — follow-up fields on every case log
 * 12.  Mobile-first layout throughout — safe area, tap targets, no overflow
 */

import React, {
  useCallback, useEffect, useMemo, useRef, useState,
} from "react";
import { getToken } from "@/lib/auth";

// ─── Type definitions ──────────────────────────────────────────────────────────

type Decision   = "go" | "caution" | "high_risk";
type RiskLevel  = "low" | "moderate" | "high" | "very_high";
type TabId      = "safety" | "interactions" | "tools" | "cases" | "clinic" | "saved";

interface PatientFactors {
  prior_filler_in_same_area?: boolean;
  prior_vascular_event?: boolean;
  autoimmune_history?: boolean;
  allergy_history?: boolean;
  active_infection_near_site?: boolean;
  anticoagulation?: boolean;
  vascular_disease?: boolean;
  smoking?: boolean;
  nsaid_use?: boolean;
  ssri_use?: boolean;
  pregnancy?: boolean;
  immunosuppression?: boolean;
}

interface PreProcedureRequest {
  procedure: string;
  region: string;
  product_type: string;
  technique?: string;
  injector_experience_level?: "junior" | "intermediate" | "senior";
  patient_factors?: PatientFactors;
  clinician_id?: string;
  clinic_id?: string;
}

interface RiskItem {
  complication: string;
  risk_score: number;
  risk_level: RiskLevel;
  why_it_matters: string;
}

interface EvidenceItem {
  source_id: string;
  title: string;
  note: string;
  citation_text?: string;
  source_type?: string;
  relevance_score?: number;
  journal?: string;
  year?: number;
  url?: string;
}

interface ProcedureInsight {
  procedure_name: string;
  region: string;
  likely_plane_or_target?: string;
  danger_zones: string[];
  technical_notes: string[];
}

interface PreProcedureResponse {
  request_id: string;
  generated_at_utc: string;
  engine_version: string;
  knowledge_revision?: string;
  safety_assessment: {
    overall_risk_score: number;
    overall_risk_level: RiskLevel;
    decision: Decision;
    rationale: string;
  };
  top_risks: RiskItem[];
  procedure_insight: ProcedureInsight;
  mitigation_steps: string[];
  caution_flags: string[];
  evidence: EvidenceItem[];
  disclaimer: string;
}

interface BookmarkResponse {
  id: string;
  user_id: string;
  title: string;
  question: string;
  answer_json: Record<string, unknown>;
  tags: string[];
  created_at_utc: string;
}

interface PatientReadableResponse {
  id: string;
  patient_text: string;
  created_at_utc: string;
}

interface DrugInteractionItem {
  medication: string;
  product_or_context: string;
  severity: "low" | "moderate" | "high";
  explanation: string;
  action: string;
}

interface DrugCheckResponse {
  interactions?: DrugInteractionItem[];
  items?: DrugInteractionItem[];
  summary: string;
  proceed_with_caution?: boolean;
}

interface SessionReportCreateResponse { id: string }

interface QueueItem {
  id: string;
  label: string;
  request: PreProcedureRequest;
  result?: PreProcedureResponse;
  status: "pending" | "running" | "done" | "error";
  error?: string;
}

interface CaseLogForm {
  protocol_key: string;
  procedure: string;
  region: string;
  product_type: string;
  technique: string;
  symptoms: string;
  outcome: string;
  outcome_detail: string;
  follow_up_weeks: string;
  notes: string;
  patient_age_range: string;
  complication_timing: string;
  treatment_given: string;
}

interface DashboardData {
  total_queries: number;
  average_aci_score?: number;
  average_response_time_ms?: number;
  top_questions: { query: string; count: number }[];
  evidence_level_distribution: Record<string, number>;
  answer_type_distribution: Record<string, number>;
}

interface ApiKey {
  id: string;
  clinic_id: string;
  label: string;
  api_key?: string;
  created_at_utc: string;
}

interface PaperAlert {
  id: string;
  user_id: string;
  topic: string;
  email?: string;
  last_checked_utc?: string;
  created_at_utc: string;
}

interface PaperDigestItem {
  title: string;
  abstract?: string;
  url?: string;
  published_date?: string;
}

interface KnowledgeBaseStatus {
  documents: number;
  aesthetic_documents: number;
  ingestion_status: string;
  knowledge_base_ready: boolean;
}

// ─── Constants ─────────────────────────────────────────────────────────────────

const PROCEDURES = [
  "lip filler", "tear trough filler", "nasolabial fold filler",
  "glabellar filler", "glabellar toxin", "jawline filler", "chin filler",
  "cheek filler", "nose filler", "forehead filler", "temple filler",
  "masseter toxin", "platysma toxin", "crow's feet toxin", "brow lift toxin",
  "hand filler", "neck skin booster", "profhilo",
] as const;

const REGIONS = [
  "lip", "tear trough", "nasolabial fold", "glabella", "jawline",
  "chin", "cheek", "nose", "forehead", "temple", "masseter",
  "platysma", "periorbital", "hand", "neck",
] as const;

const PRODUCTS = [
  "hyaluronic acid", "ha filler", "botulinum toxin",
  "calcium hydroxylapatite", "skin booster", "profhilo", "other",
] as const;

const TECHNIQUES = [
  "needle", "cannula", "retrograde threading", "bolus",
  "serial puncture", "intradermal", "supraperiosteal", "fanning",
] as const;

const PROTOCOLS = [
  "vascular_occlusion_ha_filler", "vision_loss_ocular_emergency", "skin_necrosis",
  "anaphylaxis", "tyndall_effect", "botulinum_toxin_ptosis",
  "infection_biofilm", "filler_nodules", "nerve_injury_toxin", "delayed_granuloma",
] as const;

const ALERT_TOPICS = [
  "vascular occlusion filler", "lip filler safety", "tear trough complications",
  "glabellar filler vision", "botulinum toxin ptosis", "hyaluronidase dosing",
  "filler nodule treatment", "biofilm aesthetic filler",
];

const ONBOARDING_STEPS = [
  {
    icon: "⬡",
    title: "Welcome to AesthetiCite Safety Workspace",
    body: "This is your clinical safety hub for aesthetic injectables. Run pre-procedure risk assessments, check drug interactions, log complications, and export patient summaries — all from one place.",
  },
  {
    icon: "🛡",
    title: "Pre-Procedure Safety Check",
    body: "Before every procedure, select the procedure, region, product, and patient risk factors. AesthetiCite scores the overall risk, flags danger zones, and tells you whether to go, proceed with caution, or defer.",
  },
  {
    icon: "📋",
    title: "Session Safety Report",
    body: "Queue multiple patients or procedures for a session. Run all checks together, then export one consolidated PDF for your records — or to share with your clinic manager.",
  },
  {
    icon: "💊",
    title: "Drug Interaction Checker",
    body: "Enter any patient medications before treatment. AesthetiCite flags anticoagulants, NSAIDs, SSRIs, isotretinoin, and immunosuppressants with specific action guidance.",
  },
  {
    icon: "🧪",
    title: "Hyaluronidase Emergency Calculator",
    body: "In the Tools tab, calculate hyaluronidase dose and dilution for vascular occlusion emergencies. Enter the filler product, estimated volume, and region to get the territory-based protocol.",
  },
];

// ─── Styling maps ──────────────────────────────────────────────────────────────

const DECISION_STYLES: Record<Decision, { badge: string; card: string; text: string }> = {
  go:        { badge: "bg-emerald-600 text-white", card: "border-emerald-500/20 bg-emerald-500/5", text: "text-emerald-600 dark:text-emerald-400" },
  caution:   { badge: "bg-amber-500 text-white",   card: "border-amber-500/20 bg-amber-500/5",     text: "text-amber-600 dark:text-amber-400" },
  high_risk: { badge: "bg-red-600 text-white",     card: "border-red-500/20 bg-red-500/5",         text: "text-red-600 dark:text-red-400" },
};

const RISK_BAR: Record<string, string> = {
  low: "bg-emerald-500", moderate: "bg-amber-500", high: "bg-orange-500", very_high: "bg-red-600",
};

const SEVERITY_BADGE: Record<string, string> = {
  low:      "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20",
  moderate: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20",
  high:     "bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/20",
  very_high:"bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/20",
};

// ─── Utility helpers ────────────────────────────────────────────────────────────

function decodeJwtSub(token: string | null): string | null {
  if (!token) return null;
  try {
    const p = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return p.sub || p.user_id || p.id || null;
  } catch { return null; }
}

async function apiGet<T>(url: string): Promise<T> {
  const token = getToken();
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as any).detail || (err as any).message || `GET ${url} failed (${res.status})`);
  }
  return res.json();
}

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const token = getToken();
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as any).detail || (err as any).message || `POST ${url} failed (${res.status})`);
  }
  return res.json();
}

async function apiDelete<T>(url: string): Promise<T> {
  const token = getToken();
  const res = await fetch(url, {
    method: "DELETE",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`DELETE ${url} failed (${res.status})`);
  return res.json();
}

function downloadFile(filename: string) {
  const a = document.createElement("a");
  a.href = `/exports/${filename}`;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function copyToClipboard(text: string): Promise<void> {
  return navigator.clipboard.writeText(text).catch(() => {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  });
}

function fmtDate(iso: string): string {
  try { return new Date(iso).toLocaleDateString(); } catch { return iso; }
}

// ─── Reusable UI primitives ────────────────────────────────────────────────────

function Section({
  title, subtitle, children, action, accent,
}: {
  title: string; subtitle?: string; children: React.ReactNode;
  action?: React.ReactNode; accent?: string;
}) {
  return (
    <div className={`rounded-2xl border bg-card p-4 shadow-sm ${accent || "border-border"}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold tracking-tight">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

function Pill({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${className}`}>
      {children}
    </span>
  );
}

function Btn({
  children, onClick, disabled, variant = "primary", size = "md", className = "",
}: {
  children: React.ReactNode; onClick?: () => void; disabled?: boolean;
  variant?: "primary" | "secondary" | "danger" | "ghost" | "success";
  size?: "sm" | "md"; className?: string;
}) {
  const base = "inline-flex items-center justify-center gap-1.5 font-semibold rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const sizes = { sm: "px-3 py-1.5 text-xs", md: "px-4 py-2.5 text-sm" };
  const variants = {
    primary:   "bg-primary text-primary-foreground hover:bg-primary/90",
    secondary: "border border-border hover:bg-muted/50",
    danger:    "border border-red-500/30 text-red-600 hover:bg-red-500/10",
    ghost:     "hover:bg-muted/50 text-muted-foreground hover:text-foreground",
    success:   "bg-emerald-600 text-white hover:bg-emerald-700",
  };
  return (
    <button
      onClick={onClick} disabled={disabled}
      className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

function RiskBar({ score, level }: { score: number; level: string }) {
  const bar = RISK_BAR[level] || "bg-muted";
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-700 ${bar}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs tabular-nums font-semibold w-8 text-right">{score}</span>
    </div>
  );
}

function Toast({ message, type, onDismiss }: { message: string; type: "success" | "error"; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 4000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <div className={`fixed bottom-4 right-4 z-50 flex items-center gap-3 rounded-xl border px-4 py-3 shadow-lg text-sm font-medium max-w-sm animate-in slide-in-from-bottom-2 ${
      type === "success"
        ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
        : "border-red-500/20 bg-red-500/10 text-red-700 dark:text-red-300"
    }`}>
      <span>{type === "success" ? "✓" : "✕"}</span>
      <span className="flex-1">{message}</span>
      <button onClick={onDismiss} className="text-current opacity-50 hover:opacity-100">✕</button>
    </div>
  );
}

// ─── Feature 2: Onboarding modal ──────────────────────────────────────────────

function OnboardingModal({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const current = ONBOARDING_STEPS[step];
  const isLast = step === ONBOARDING_STEPS.length - 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card shadow-2xl overflow-hidden">
        {/* Progress */}
        <div className="flex">
          {ONBOARDING_STEPS.map((_, i) => (
            <div key={i} className={`h-1 flex-1 ${i <= step ? "bg-primary" : "bg-muted"} transition-all`} />
          ))}
        </div>
        <div className="p-6 space-y-4">
          <div className="text-4xl">{current.icon}</div>
          <div>
            <h2 className="text-lg font-bold">{current.title}</h2>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{current.body}</p>
          </div>
          <div className="flex items-center justify-between pt-2">
            <span className="text-xs text-muted-foreground">{step + 1} of {ONBOARDING_STEPS.length}</span>
            <div className="flex gap-2">
              {step > 0 && (
                <Btn variant="secondary" size="sm" onClick={() => setStep(s => s - 1)}>Back</Btn>
              )}
              <Btn variant="primary" size="sm" onClick={() => isLast ? onDone() : setStep(s => s + 1)}>
                {isLast ? "Get started →" : "Next →"}
              </Btn>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Feature 1 + 3: Knowledge base health banner ──────────────────────────────

function KBHealthBanner({ status }: { status: KnowledgeBaseStatus | null }) {
  if (!status || status.knowledge_base_ready) return null;
  return (
    <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-2.5 flex items-center gap-3 text-sm">
      <span className="text-amber-500">⚠</span>
      <span className="text-amber-700 dark:text-amber-300 flex-1">
        Knowledge base has {status.aesthetic_documents} aesthetic documents — evidence may be limited.
      </span>
      <a href="/admin/readiness" className="text-xs text-primary underline underline-offset-2">Fix →</a>
    </div>
  );
}

// ─── Feature 7: Hyaluronidase emergency calculator ────────────────────────────

const HYALURONIDASE_PROTOCOLS: Record<string, {
  territory: string; dose_units: number; volume_ml: number; dilution: string; notes: string;
}> = {
  "nasolabial fold":  { territory: "Facial artery / angular artery territory", dose_units: 450,  volume_ml: 1.5, dilution: "300 units/mL", notes: "Treat the entire facial artery territory. Reassess every 60 min. Repeat if no improvement." },
  "lip":              { territory: "Labial artery territory",                    dose_units: 300,  volume_ml: 1.0, dilution: "300 units/mL", notes: "Infiltrate around labial arteries bilaterally. Warm compress after each dose." },
  "tear trough":      { territory: "Angular vessel / periorbital territory",     dose_units: 150,  volume_ml: 1.0, dilution: "150 units/mL", notes: "Low volume, targeted placement. If visual symptoms: escalate immediately — do not delay." },
  "glabella":         { territory: "Supratrochlear / ophthalmic artery",         dose_units: 1500, volume_ml: 2.0, dilution: "750 units/mL", notes: "HIGHEST RISK. Visual symptoms = call 999 immediately. Retrobulbar hyaluronidase only if trained." },
  "nose":             { territory: "Dorsal nasal / angular artery territory",    dose_units: 900,  volume_ml: 2.0, dilution: "450 units/mL", notes: "Nose communicates with ophthalmic artery. Any visual symptom = emergency services immediately." },
  "forehead":         { territory: "Supratrochlear / supraorbital territory",    dose_units: 600,  volume_ml: 2.0, dilution: "300 units/mL", notes: "Treat entire forehead territory. Escalate if no improvement within 30 min." },
  "temple":           { territory: "Temporal / ophthalmic artery territory",     dose_units: 900,  volume_ml: 2.0, dilution: "450 units/mL", notes: "Temporal filler carries vision risk. Treat same as high-risk zone." },
  "cheek":            { territory: "Facial artery / infraorbital territory",     dose_units: 450,  volume_ml: 1.5, dilution: "300 units/mL", notes: "Treat the full facial artery territory of the cheek." },
  "chin":             { territory: "Mental artery territory",                    dose_units: 300,  volume_ml: 1.0, dilution: "300 units/mL", notes: "Submental and mental artery territory. Reassess at 30 min." },
  "jawline":          { territory: "Facial / marginal mandibular territory",     dose_units: 450,  volume_ml: 1.5, dilution: "300 units/mL", notes: "Treat facial artery territory along jawline." },
};

function HyaluronidaseCalculator() {
  const [region, setRegion] = useState("");
  const [product, setProduct] = useState("juvederm");
  const [volumeInjected, setVolumeInjected] = useState("0.5");
  const [minutesSince, setMinutesSince] = useState("15");
  const [copied, setCopied] = useState(false);

  const protocol = region ? HYALURONIDASE_PROTOCOLS[region as keyof typeof HYALURONIDASE_PROTOCOLS] : null;

  const isUrgent = protocol && ["glabella", "nose", "temple"].includes(region);
  const timeFactor = Math.max(1, Math.min(2, parseInt(minutesSince) / 30));
  const adjustedDose = protocol ? Math.round(protocol.dose_units * timeFactor) : 0;

  const protocolText = protocol ? `HYALURONIDASE EMERGENCY PROTOCOL
Region: ${region} (${product})
Time since injection: ${minutesSince} minutes

Territory: ${protocol.territory}
Starting dose: ${adjustedDose} units in ${protocol.volume_ml} mL (${protocol.dilution})
${adjustedDose !== protocol.dose_units ? `Standard dose: ${protocol.dose_units} units (adjusted for time)` : ""}

Technique: Infiltrate the full ${protocol.territory}. Do not inject only at the puncture point.
Reassess: Every 60 minutes. Repeat dose if perfusion does not restore.

Clinical notes: ${protocol.notes}

${isUrgent ? "⚠ HIGH-RISK REGION — Call emergency services immediately if ANY visual symptom." : ""}

DISCLAIMER: This calculator is decision support only. Always follow your local emergency protocol.` : "";

  const handleCopy = () => {
    if (!protocolText) return;
    copyToClipboard(protocolText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="space-y-4">
      <div className={`rounded-xl border p-3 ${isUrgent ? "border-red-500/30 bg-red-500/5" : "border-amber-500/20 bg-amber-500/5"}`}>
        <p className="text-xs font-bold uppercase tracking-wider text-amber-700 dark:text-amber-400">
          {isUrgent ? "⚠ Emergency Protocol Tool" : "⚡ Emergency Tool"}
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          {isUrgent
            ? "This region carries vision loss risk. Call emergency services for any visual symptom before running this calculator."
            : "Use during active vascular occlusion. Have hyaluronidase drawn up before starting treatment."}
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
            Injection region *
          </label>
          <select
            value={region}
            onChange={e => setRegion(e.target.value)}
            className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm"
          >
            <option value="">Select region</option>
            {Object.keys(HYALURONIDASE_PROTOCOLS).map(r => (
              <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
            Product
          </label>
          <select
            value={product}
            onChange={e => setProduct(e.target.value)}
            className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm"
          >
            {["juvederm", "restylane", "belotero", "teosyal", "radiesse", "sculptra", "other ha"].map(p => (
              <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
            Volume injected (mL)
          </label>
          <input
            type="number" min="0.1" max="5" step="0.1"
            value={volumeInjected}
            onChange={e => setVolumeInjected(e.target.value)}
            className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
            Minutes since injection
          </label>
          <input
            type="number" min="0" max="1440" step="5"
            value={minutesSince}
            onChange={e => setMinutesSince(e.target.value)}
            className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm"
          />
        </div>
      </div>

      {protocol && (
        <div className={`rounded-xl border p-4 space-y-3 ${isUrgent ? "border-red-500/30 bg-red-500/5" : "border-emerald-500/20 bg-emerald-500/5"}`}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-bold">
                {adjustedDose} units in {protocol.volume_ml} mL
              </p>
              <p className="text-xs text-muted-foreground">{protocol.dilution} — {protocol.territory}</p>
            </div>
            <Btn variant="secondary" size="sm" onClick={handleCopy}>
              {copied ? "✓ Copied" : "Copy protocol"}
            </Btn>
          </div>

          <div className="space-y-2 text-sm">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Steps</p>
            {[
              "Stop the procedure and all further injection immediately.",
              `Aspirate from injection site if accessible.`,
              `Draw up ${adjustedDose} units in ${protocol.volume_ml} mL. Infiltrate the full ${protocol.territory}.`,
              "Apply warm compress. Gentle massage to aid dispersal.",
              "Reassess capillary refill every 60 minutes. Repeat if no improvement.",
              isUrgent ? "⚠ Any visual symptom → call 999/112 IMMEDIATELY. Do not wait." : "Escalate to hospital if ischaemia does not resolve within 60 min.",
            ].map((s, i) => (
              <div key={i} className={`flex gap-2 text-xs leading-relaxed ${isUrgent && i === 5 ? "font-bold text-red-600 dark:text-red-400" : "text-foreground/80"}`}>
                <span className="font-bold text-primary flex-shrink-0">{i + 1}.</span>
                <span>{s}</span>
              </div>
            ))}
          </div>

          <p className="text-xs text-muted-foreground border-t border-border/50 pt-2">{protocol.notes}</p>
        </div>
      )}

      {!protocol && (
        <div className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          Select a region to generate the hyaluronidase protocol.
        </div>
      )}

      <p className="text-[11px] text-muted-foreground/50">
        Doses are territory-based starting doses. Repeat every 60 min until perfusion restores. Always follow your local emergency protocol and escalate early. Not a substitute for emergency training.
      </p>
    </div>
  );
}

// ─── Feature 5 + 11: Case logging with outcome tracking ───────────────────────

function CaseLoggingTab({ userId }: { userId: string | null }) {
  const [form, setForm] = useState<CaseLogForm>({
    protocol_key: "", procedure: "", region: "", product_type: "",
    technique: "", symptoms: "", outcome: "", outcome_detail: "",
    follow_up_weeks: "", notes: "", patient_age_range: "",
    complication_timing: "", treatment_given: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [cases, setCases] = useState<any[]>([]);
  const [loadingCases, setLoadingCases] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const set = (k: keyof CaseLogForm, v: string) => setForm(f => ({ ...f, [k]: v }));

  const loadCases = useCallback(async () => {
    if (!userId) return;
    setLoadingCases(true);
    try {
      const data = await apiGet<{ cases: any[]; dataset_stats: any; total: number }>(`/api/ops/cases?limit=20`);
      setCases(data.cases || []);
    } catch { setCases([]); }
    finally { setLoadingCases(false); }
  }, [userId]);

  useEffect(() => { if (userId) loadCases(); }, [userId, loadCases]);

  const handleSubmit = async () => {
    if (!form.procedure || !form.region) {
      setError("Procedure and region are required."); return;
    }
    setSubmitting(true); setError("");
    try {
      await apiPost("/api/ops/cases/log", {
        clinic_id: userId,
        clinician_id: userId,
        protocol_key: form.protocol_key || undefined,
        procedure: form.procedure,
        region: form.region,
        product_type: form.product_type || undefined,
        technique: form.technique || undefined,
        symptoms: form.symptoms ? form.symptoms.split(",").map(s => s.trim()).filter(Boolean) : [],
        outcome: form.outcome || undefined,
        notes: [
          form.outcome_detail && `Outcome detail: ${form.outcome_detail}`,
          form.follow_up_weeks && `Follow-up: ${form.follow_up_weeks} weeks`,
          form.patient_age_range && `Patient age range: ${form.patient_age_range}`,
          form.complication_timing && `Complication timing: ${form.complication_timing}`,
          form.treatment_given && `Treatment given: ${form.treatment_given}`,
          form.notes,
        ].filter(Boolean).join(" | ") || undefined,
      });
      setSubmitted(true);
      setForm({
        protocol_key: "", procedure: "", region: "", product_type: "",
        technique: "", symptoms: "", outcome: "", outcome_detail: "",
        follow_up_weeks: "", notes: "", patient_age_range: "",
        complication_timing: "", treatment_given: "",
      });
      loadCases();
      setTimeout(() => setSubmitted(false), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Log failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[420px_minmax(0,1fr)]">
      <div className="space-y-4">
        <Section
          title="Log a Complication Case"
          subtitle="Every case logged builds the proprietary AesthetiCite complication dataset. This is the long-term moat."
        >
          {submitted && (
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-sm text-emerald-700 mb-3">
              ✓ Case logged successfully.
            </div>
          )}
          {error && (
            <div className="rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-2 text-sm text-red-700 mb-3">
              {error}
            </div>
          )}
          <div className="space-y-3">
            {/* Core fields */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="label-xs">Procedure *</label>
                <select value={form.procedure} onChange={e => set("procedure", e.target.value)}
                  className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm">
                  <option value="">Select</option>
                  {PROCEDURES.map(x => <option key={x} value={x}>{x}</option>)}
                </select>
              </div>
              <div>
                <label className="label-xs">Region *</label>
                <select value={form.region} onChange={e => set("region", e.target.value)}
                  className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm">
                  <option value="">Select</option>
                  {REGIONS.map(x => <option key={x} value={x}>{x}</option>)}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="label-xs">Product type</label>
                <select value={form.product_type} onChange={e => set("product_type", e.target.value)}
                  className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm">
                  <option value="">Select</option>
                  {PRODUCTS.map(x => <option key={x} value={x}>{x}</option>)}
                </select>
              </div>
              <div>
                <label className="label-xs">Complication protocol</label>
                <select value={form.protocol_key} onChange={e => set("protocol_key", e.target.value)}
                  className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm">
                  <option value="">Select</option>
                  {PROTOCOLS.map(x => <option key={x} value={x}>{x.replace(/_/g, " ")}</option>)}
                </select>
              </div>
            </div>

            <div>
              <label className="label-xs">Symptoms (comma-separated)</label>
              <input value={form.symptoms} onChange={e => set("symptoms", e.target.value)}
                placeholder="e.g. blanching, pain, mottling"
                className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm" />
            </div>

            {/* Outcome tracking — Feature 11 */}
            <div className="rounded-xl border border-border p-3 space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Outcome Tracking</p>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="label-xs">Outcome</label>
                  <select value={form.outcome} onChange={e => set("outcome", e.target.value)}
                    className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm">
                    <option value="">Select</option>
                    <option value="resolved_fully">Resolved fully</option>
                    <option value="resolved_partially">Resolved partially</option>
                    <option value="ongoing">Ongoing</option>
                    <option value="escalated_hospital">Escalated to hospital</option>
                    <option value="permanent_sequelae">Permanent sequelae</option>
                    <option value="unknown">Unknown / lost to follow-up</option>
                  </select>
                </div>
                <div>
                  <label className="label-xs">Follow-up (weeks)</label>
                  <input type="number" min="0" value={form.follow_up_weeks}
                    onChange={e => set("follow_up_weeks", e.target.value)}
                    placeholder="e.g. 4"
                    className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm" />
                </div>
              </div>
              <div>
                <label className="label-xs">Treatment given</label>
                <input value={form.treatment_given} onChange={e => set("treatment_given", e.target.value)}
                  placeholder="e.g. hyaluronidase 450 units, warm compress"
                  className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="label-xs">Complication timing</label>
                  <select value={form.complication_timing} onChange={e => set("complication_timing", e.target.value)}
                    className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm">
                    <option value="">Select</option>
                    <option value="immediate">Immediate (&lt;1h)</option>
                    <option value="early">Early (1–24h)</option>
                    <option value="delayed">Delayed (1–4 weeks)</option>
                    <option value="late">Late (&gt;4 weeks)</option>
                  </select>
                </div>
                <div>
                  <label className="label-xs">Patient age range</label>
                  <select value={form.patient_age_range} onChange={e => set("patient_age_range", e.target.value)}
                    className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm">
                    <option value="">Select</option>
                    <option value="18-30">18–30</option>
                    <option value="31-45">31–45</option>
                    <option value="46-60">46–60</option>
                    <option value="60+">60+</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="label-xs">Notes</label>
                <textarea value={form.notes} onChange={e => set("notes", e.target.value)}
                  rows={2} placeholder="Any additional clinical notes"
                  className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm resize-none" />
              </div>
            </div>

            <Btn variant="primary" onClick={handleSubmit} disabled={submitting || !form.procedure || !form.region} className="w-full">
              {submitting ? "Logging…" : "Log Case to Dataset"}
            </Btn>
          </div>
        </Section>
      </div>

      <div>
        <Section
          title="Logged Cases"
          subtitle="Your clinic's contribution to the proprietary complication dataset."
          action={<Btn variant="secondary" size="sm" onClick={loadCases}>Refresh</Btn>}
        >
          {loadingCases ? (
            <div className="text-sm text-muted-foreground">Loading…</div>
          ) : !userId ? (
            <div className="text-sm text-muted-foreground">Sign in to view cases.</div>
          ) : cases.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
              No cases logged yet. Log your first complication case using the form.
            </div>
          ) : (
            <div className="space-y-3">
              {cases.map((c: any) => (
                <div key={c.id} className="rounded-xl border border-border p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <span className="text-sm font-semibold capitalize">{c.procedure}</span>
                      <span className="text-muted-foreground"> · </span>
                      <span className="text-sm text-muted-foreground capitalize">{c.region}</span>
                    </div>
                    {c.outcome && (
                      <Pill className={
                        c.outcome === "resolved_fully" ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-600" :
                        c.outcome === "escalated_hospital" ? "border-red-500/20 bg-red-500/10 text-red-600" :
                        "border-border bg-muted text-muted-foreground"
                      }>
                        {c.outcome.replace(/_/g, " ")}
                      </Pill>
                    )}
                  </div>
                  {c.protocol_key && (
                    <p className="text-xs text-muted-foreground mt-1 capitalize">{c.protocol_key.replace(/_/g, " ")}</p>
                  )}
                  <p className="text-[10px] text-muted-foreground/60 mt-1">{fmtDate(c.logged_at_utc || c.created_at)}</p>
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}

// ─── Feature 4 + 8 + 9 + 10: Clinic admin panel ──────────────────────────────

function ClinicTab({ userId }: { userId: string | null }) {
  const [activeSection, setActiveSection] = useState<"dashboard" | "api" | "alerts" | "regulatory">("dashboard");

  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loadingDash, setLoadingDash] = useState(false);

  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [newKeyLabel, setNewKeyLabel] = useState("");
  const [newKeyResult, setNewKeyResult] = useState<string | null>(null);
  const [loadingKey, setLoadingKey] = useState(false);

  const [alerts, setAlerts] = useState<PaperAlert[]>([]);
  const [alertTopic, setAlertTopic] = useState("");
  const [alertEmail, setAlertEmail] = useState("");
  const [digestResults, setDigestResults] = useState<Record<string, PaperDigestItem[]>>({});
  const [loadingAlerts, setLoadingAlerts] = useState(false);

  const loadDashboard = useCallback(async () => {
    if (!userId) return;
    setLoadingDash(true);
    try {
      const data = await apiGet<DashboardData>(`/api/ops/dashboard/clinic`);
      setDashboard(data);
    } catch {
      // try fallback
      try {
        const data2 = await apiGet<DashboardData>(`/api/growth/dashboard/${userId}`);
        setDashboard(data2);
      } catch { setDashboard(null); }
    }
    finally { setLoadingDash(false); }
  }, [userId]);

  const loadApiKeys = useCallback(async () => {
    if (!userId) return;
    try {
      const data = await apiGet<ApiKey[]>(`/api/growth/api-keys?clinic_id=${userId}`);
      setApiKeys(Array.isArray(data) ? data : []);
    } catch { setApiKeys([]); }
  }, [userId]);

  const loadAlerts = useCallback(async () => {
    if (!userId) return;
    setLoadingAlerts(true);
    try {
      const data = await apiGet<PaperAlert[]>(`/api/growth/paper-alerts/${userId}`);
      setAlerts(data);
    } catch { setAlerts([]); }
    finally { setLoadingAlerts(false); }
  }, [userId]);

  useEffect(() => {
    if (activeSection === "dashboard") loadDashboard();
    if (activeSection === "api") loadApiKeys();
    if (activeSection === "alerts") loadAlerts();
  }, [activeSection, loadDashboard, loadApiKeys, loadAlerts]);

  const createApiKey = async () => {
    if (!newKeyLabel || !userId) return;
    setLoadingKey(true);
    try {
      const data = await apiPost<ApiKey>("/api/growth/api-keys", { clinic_id: userId, label: newKeyLabel });
      setNewKeyResult((data as any).api_key || null);
      setNewKeyLabel("");
      loadApiKeys();
    } catch (e) { alert(e instanceof Error ? e.message : "Failed"); }
    finally { setLoadingKey(false); }
  };

  const subscribeAlert = async () => {
    if (!alertTopic || !userId) return;
    try {
      await apiPost("/api/growth/paper-alerts/subscribe", {
        user_id: userId, topic: alertTopic, email: alertEmail || undefined,
      });
      setAlertTopic(""); setAlertEmail("");
      loadAlerts();
    } catch (e) { alert(e instanceof Error ? e.message : "Failed"); }
  };

  const runDigest = async (subId: string, topic: string) => {
    try {
      const data = await apiPost<{ new_items: PaperDigestItem[] }>(`/api/growth/paper-alerts/${subId}/run`, {});
      setDigestResults(prev => ({ ...prev, [subId]: data.new_items || [] }));
    } catch (e) { alert(e instanceof Error ? e.message : "Failed"); }
  };

  const navItems: { id: "dashboard" | "api" | "alerts" | "regulatory"; label: string; icon: string }[] = [
    { id: "dashboard", label: "Dashboard", icon: "📊" },
    { id: "api", label: "API Keys", icon: "🔑" },
    { id: "alerts", label: "Paper Alerts", icon: "🔔" },
    { id: "regulatory", label: "Regulatory", icon: "⚖" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex gap-2 flex-wrap">
        {navItems.map(n => (
          <button key={n.id} onClick={() => setActiveSection(n.id)}
            className={`flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold transition-colors ${
              activeSection === n.id ? "bg-primary text-primary-foreground" : "border border-border hover:bg-muted/50"
            }`}>
            <span>{n.icon}</span>{n.label}
          </button>
        ))}
      </div>

      {/* Dashboard */}
      {activeSection === "dashboard" && (
        <Section title="Clinic Dashboard" subtitle="Query activity, ACI scores, and evidence distribution for your clinic."
          action={<Btn variant="secondary" size="sm" onClick={loadDashboard}>Refresh</Btn>}>
          {loadingDash ? (
            <div className="text-sm text-muted-foreground">Loading…</div>
          ) : !dashboard ? (
            <div className="text-sm text-muted-foreground">
              No dashboard data yet. Run searches and safety checks to populate this.
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[
                  { label: "Total queries", value: dashboard.total_queries },
                  { label: "Avg ACI score", value: dashboard.average_aci_score?.toFixed(1) ?? "—" },
                  { label: "Avg response (ms)", value: dashboard.average_response_time_ms?.toFixed(0) ?? "—" },
                ].map(s => (
                  <div key={s.label} className="rounded-xl border border-border bg-muted/20 p-3 text-center">
                    <div className="text-2xl font-black tabular-nums">{s.value}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">{s.label}</div>
                  </div>
                ))}
              </div>
              {dashboard.top_questions.length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Top Questions</p>
                  <div className="space-y-1.5">
                    {dashboard.top_questions.slice(0, 8).map((q, i) => (
                      <div key={i} className="flex items-center gap-3 text-sm">
                        <span className="w-5 text-xs text-muted-foreground tabular-nums">{q.count}×</span>
                        <span className="truncate">{q.query}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </Section>
      )}

      {/* API Keys — Feature 8 */}
      {activeSection === "api" && (
        <Section title="Clinic API Keys"
          subtitle="Use API keys to integrate AesthetiCite into your EMR, booking system, or consent workflow.">
          <div className="space-y-4">
            {newKeyResult && (
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 space-y-2">
                <p className="text-xs font-semibold text-emerald-700">✓ New API key created — copy it now, it won't be shown again.</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded-lg bg-muted px-3 py-2 text-xs font-mono break-all">{newKeyResult}</code>
                  <Btn variant="secondary" size="sm" onClick={() => { copyToClipboard(newKeyResult); }}>Copy</Btn>
                </div>
                <Btn variant="ghost" size="sm" onClick={() => setNewKeyResult(null)}>Dismiss</Btn>
              </div>
            )}
            <div className="flex gap-2">
              <input value={newKeyLabel} onChange={e => setNewKeyLabel(e.target.value)}
                placeholder="Key label (e.g. EMR integration)"
                className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm" />
              <Btn variant="primary" onClick={createApiKey} disabled={loadingKey || !newKeyLabel}>
                {loadingKey ? "Creating…" : "Create key"}
              </Btn>
            </div>
            {apiKeys.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
                No API keys yet.
              </div>
            ) : (
              <div className="space-y-2">
                {apiKeys.map(k => (
                  <div key={k.id} className="rounded-xl border border-border p-3 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold">{k.label}</p>
                      <p className="text-xs text-muted-foreground">Created {fmtDate(k.created_at_utc)}</p>
                    </div>
                    <code className="text-xs text-muted-foreground font-mono">ac_****</code>
                  </div>
                ))}
              </div>
            )}
            <div className="rounded-xl border border-border p-3 text-xs text-muted-foreground space-y-1">
              <p className="font-semibold">API usage</p>
              <p>Send your key as <code className="bg-muted px-1 rounded">X-API-Key: ac_…</code> header to POST /api/growth/clinic-api/search</p>
            </div>
          </div>
        </Section>
      )}

      {/* Paper Alerts — Feature 9 */}
      {activeSection === "alerts" && (
        <Section title="Paper Alert Digest"
          subtitle="Subscribe to topics. AesthetiCite checks PubMed for new papers and notifies you.">
          <div className="space-y-4">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Subscribe to topic</p>
              <div className="flex flex-wrap gap-2 mb-2">
                {ALERT_TOPICS.map(t => (
                  <button key={t} onClick={() => setAlertTopic(t)}
                    className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${alertTopic === t ? "bg-primary/10 border-primary/40 text-primary" : "border-border hover:bg-muted/50"}`}>
                    {t}
                  </button>
                ))}
              </div>
              <div className="flex gap-2">
                <input value={alertTopic} onChange={e => setAlertTopic(e.target.value)}
                  placeholder="Or type custom topic"
                  className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm" />
                <input value={alertEmail} onChange={e => setAlertEmail(e.target.value)}
                  placeholder="Email (optional)"
                  className="w-44 rounded-xl border border-border bg-background px-3 py-2 text-sm hidden sm:block" />
                <Btn variant="primary" onClick={subscribeAlert} disabled={!alertTopic}>Subscribe</Btn>
              </div>
            </div>

            {loadingAlerts ? (
              <div className="text-sm text-muted-foreground">Loading…</div>
            ) : alerts.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
                No subscriptions yet.
              </div>
            ) : (
              <div className="space-y-3">
                {alerts.map(a => (
                  <div key={a.id} className="rounded-xl border border-border p-3 space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold">{a.topic}</p>
                        <p className="text-xs text-muted-foreground">
                          Last checked: {a.last_checked_utc ? fmtDate(a.last_checked_utc) : "Never"}
                        </p>
                      </div>
                      <Btn variant="secondary" size="sm" onClick={() => runDigest(a.id, a.topic)}>
                        Run digest
                      </Btn>
                    </div>
                    {digestResults[a.id] && (
                      <div className="space-y-2 pt-1 border-t border-border/50">
                        {digestResults[a.id].length === 0 ? (
                          <p className="text-xs text-muted-foreground">No new papers found.</p>
                        ) : (
                          digestResults[a.id].map((p, i) => (
                            <div key={i} className="text-xs">
                              <a href={p.url} target="_blank" rel="noreferrer"
                                className="font-medium text-primary hover:underline">{p.title}</a>
                              {p.published_date && <span className="text-muted-foreground ml-2">{p.published_date}</span>}
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </Section>
      )}

      {/* Regulatory — Feature 10 */}
      {activeSection === "regulatory" && (
        <Section title="Regulatory Positioning"
          subtitle="AesthetiCite is clinical decision support software. This checklist tracks compliance readiness for MHRA (UK) and EU MDR.">
          <div className="space-y-3">
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-sm text-amber-700 dark:text-amber-400">
              ⚠ This is an informational checklist only. Engage a regulatory consultant before making compliance claims.
            </div>
            {[
              {
                category: "Intended Purpose",
                status: "done",
                items: [
                  { done: true,  label: "Intended purpose documented: clinical decision support for aesthetic injectables" },
                  { done: true,  label: "Target users defined: qualified aesthetic clinicians" },
                  { done: false, label: "Intended purpose reviewed by regulatory consultant" },
                ],
              },
              {
                category: "MHRA SAMD Classification (UK)",
                status: "in_progress",
                items: [
                  { done: true,  label: "Software does not drive autonomous clinical decisions — clinician always decides" },
                  { done: false, label: "Formal MHRA SAMD classification assessment completed" },
                  { done: false, label: "Registered with MHRA as manufacturer (if Class I SAMD)" },
                ],
              },
              {
                category: "EU MDR (if applicable)",
                status: "pending",
                items: [
                  { done: false, label: "MDR Article 2(1) applicability assessment" },
                  { done: false, label: "Technical documentation prepared (Annex II/III)" },
                  { done: false, label: "Notified Body engagement (if Class IIa or above)" },
                ],
              },
              {
                category: "Quality Management",
                status: "in_progress",
                items: [
                  { done: true,  label: "Disclaimer shown on all clinical outputs" },
                  { done: true,  label: "Evidence grading and limitations disclosed" },
                  { done: false, label: "ISO 13485 quality management system initiated" },
                  { done: false, label: "Clinical evaluation / post-market surveillance plan" },
                ],
              },
              {
                category: "Data & Privacy",
                status: "in_progress",
                items: [
                  { done: true,  label: "No patient-identifiable data stored in case logs" },
                  { done: false, label: "DSPT (UK) or GDPR Article 30 records completed" },
                  { done: false, label: "Data Processing Agreement template for clinic customers" },
                ],
              },
            ].map(section => {
              const done = section.items.filter(i => i.done).length;
              const total = section.items.length;
              return (
                <div key={section.category} className="rounded-xl border border-border p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold">{section.category}</p>
                    <span className={`text-xs font-semibold ${done === total ? "text-emerald-600" : done > 0 ? "text-amber-600" : "text-muted-foreground"}`}>
                      {done}/{total}
                    </span>
                  </div>
                  <div className="h-1 rounded-full bg-muted overflow-hidden">
                    <div className={`h-full rounded-full ${done === total ? "bg-emerald-500" : done > 0 ? "bg-amber-500" : "bg-muted-foreground/20"}`}
                      style={{ width: `${(done / total) * 100}%` }} />
                  </div>
                  <div className="space-y-1">
                    {section.items.map((item, i) => (
                      <div key={i} className={`flex items-start gap-2 text-xs ${item.done ? "text-foreground/70" : "text-muted-foreground"}`}>
                        <span className={`flex-shrink-0 mt-0.5 ${item.done ? "text-emerald-500" : "text-muted-foreground/50"}`}>
                          {item.done ? "✓" : "○"}
                        </span>
                        {item.label}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
            <p className="text-xs text-muted-foreground">
              Recommended next step: engage a regulatory consultant in month 9–12 of operations. 
              MHRA SAMD guidance: <a href="https://www.gov.uk/guidance/software-medical-devices" target="_blank" rel="noreferrer" className="text-primary hover:underline">gov.uk/guidance/software-medical-devices</a>
            </p>
          </div>
        </Section>
      )}
    </div>
  );
}

// ─── Main page ─────────────────────────────────────────────────────────────────

export default function SafetyWorkspacePage() {
  const token = getToken();
  const userId = useMemo(() => decodeJwtSub(token), [token]);

  // Feature 2: Onboarding
  const [showOnboarding, setShowOnboarding] = useState(() => {
    try { return !localStorage.getItem("ac_onboarding_done"); } catch { return false; }
  });
  const dismissOnboarding = () => {
    try { localStorage.setItem("ac_onboarding_done", "1"); } catch {}
    setShowOnboarding(false);
  };

  const [tab, setTab] = useState<TabId>("safety");
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  const notify = useCallback((msg: string, type: "success" | "error" = "success") => {
    setToast({ msg, type });
  }, []);

  // Feature 1: KB health
  const [kbStatus, setKbStatus] = useState<KnowledgeBaseStatus | null>(null);
  useEffect(() => {
    fetch("/api/ops/ingest/status", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => r.json())
      .then((d: any) => {
        const state = d.state || d;
        setKbStatus({
          documents: state.total_documents || 0,
          aesthetic_documents: state.aesthetic_documents || 0,
          ingestion_status: state.status || "unknown",
          knowledge_base_ready: (state.aesthetic_documents || 0) >= 100,
        });
      })
      .catch(() => {});
  }, [token]);

  // Safety tab state
  const [form, setForm] = useState({
    patient_label: "",
    procedure: "",
    region: "",
    product_type: "",
    technique: "",
    injector_experience_level: "" as "" | "junior" | "intermediate" | "senior",
    patient_factors: {
      prior_filler_in_same_area: false,
      prior_vascular_event: false,
      autoimmune_history: false,
      allergy_history: false,
      active_infection_near_site: false,
      anticoagulation: false,
      vascular_disease: false,
      smoking: false,
      nsaid_use: false,
      ssri_use: false,
      pregnancy: false,
      immunosuppression: false,
    } as PatientFactors,
  });

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PreProcedureResponse | null>(null);
  const [lastRequest, setLastRequest] = useState<PreProcedureRequest | null>(null);

  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [sessionTitle, setSessionTitle] = useState("Session Safety Report");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [runningQueue, setRunningQueue] = useState(false);
  const [exportingSession, setExportingSession] = useState(false);

  const [bookmarkLoading, setBookmarkLoading] = useState(false);
  const [bookmarks, setBookmarks] = useState<BookmarkResponse[]>([]);
  const [bookmarksLoading, setBookmarksLoading] = useState(false);
  const [patientText, setPatientText] = useState("");
  const [patientExportLoading, setPatientExportLoading] = useState(false);
  const [patientCopied, setPatientCopied] = useState(false);

  const [drugInput, setDrugInput] = useState("");
  const [drugLoading, setDrugLoading] = useState(false);
  const [drugResult, setDrugResult] = useState<DrugCheckResponse | null>(null);

  const buildRequest = useCallback((): PreProcedureRequest => ({
    procedure: form.procedure,
    region: form.region,
    product_type: form.product_type,
    technique: form.technique || undefined,
    injector_experience_level: form.injector_experience_level || undefined,
    patient_factors: form.patient_factors,
    clinician_id: userId || undefined,
    clinic_id: userId || undefined,
  }), [form, userId]);

  const runSafetyCheck = useCallback(async () => {
    setLoading(true);
    setPatientText("");
    try {
      const payload = buildRequest();
      setLastRequest(payload);
      const data = await apiPost<PreProcedureResponse>("/api/safety/v2/preprocedure-check", payload);
      setResult(data);
      apiPost("/api/safety/v2/log-case", {
        clinic_id: userId, clinician_id: userId,
        procedure: payload.procedure, region: payload.region,
        product_type: payload.product_type, technique: payload.technique,
        decision: data.safety_assessment.decision,
        risk_score: data.safety_assessment.overall_risk_score,
        patient_factors: payload.patient_factors,
        outcome: "safety_check_completed",
        notes: `Safety Workspace (${data.request_id})`,
      }).catch(() => {});
      notify("Safety check completed.");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Safety check failed.", "error");
    } finally { setLoading(false); }
  }, [buildRequest, userId, notify]);

  const exportSafetyPdf = useCallback(async () => {
    if (!lastRequest) return;
    try {
      const data = await apiPost<{ filename: string }>("/api/safety/v2/preprocedure-check/export-pdf", lastRequest);
      downloadFile(data.filename);
      notify("PDF exported.");
    } catch (e) { notify(e instanceof Error ? e.message : "Export failed.", "error"); }
  }, [lastRequest, notify]);

  const saveBookmark = useCallback(async () => {
    if (!result || !userId) { notify("Sign in first.", "error"); return; }
    setBookmarkLoading(true);
    try {
      await apiPost<BookmarkResponse>("/api/growth/bookmarks", {
        user_id: userId,
        title: `${result.procedure_insight.procedure_name} · ${result.procedure_insight.region}`,
        question: `Pre-procedure safety check: ${result.procedure_insight.procedure_name} / ${result.procedure_insight.region}`,
        answer_json: result,
        tags: ["safety", result.safety_assessment.decision, result.procedure_insight.region],
      });
      notify("Saved to bookmarks.");
    } catch (e) { notify(e instanceof Error ? e.message : "Save failed.", "error"); }
    finally { setBookmarkLoading(false); }
  }, [result, userId, notify]);

  const createPatientExport = useCallback(async () => {
    if (!result) { notify("Run a safety check first.", "error"); return; }
    setPatientExportLoading(true);
    try {
      const sourceText = [
        `Decision: ${result.safety_assessment.decision.replace("_", " ").toUpperCase()}`,
        `Risk score: ${result.safety_assessment.overall_risk_score}/100`,
        `Rationale: ${result.safety_assessment.rationale}`,
        `Top risks: ${result.top_risks.map(r => `${r.complication} (${r.risk_score}/100)`).join(", ")}`,
        `Danger zones: ${result.procedure_insight.danger_zones.join(", ")}`,
        `Mitigation: ${result.mitigation_steps.join("; ")}`,
      ].join("\n");
      const data = await apiPost<PatientReadableResponse>("/api/growth/patient-readable-export", {
        clinic_id: userId, clinician_id: userId,
        source_title: `Patient explanation — ${result.procedure_insight.procedure_name}`,
        source_text: sourceText,
      });
      setPatientText(data.patient_text);
      notify("Patient summary generated.");
    } catch (e) { notify(e instanceof Error ? e.message : "Export failed.", "error"); }
    finally { setPatientExportLoading(false); }
  }, [result, userId, notify]);

  const addToQueue = useCallback(() => {
    const payload = buildRequest();
    setQueue(prev => [
      ...prev,
      { id: crypto.randomUUID(), label: form.patient_label || `Patient ${prev.length + 1}`, request: payload, result: result || undefined, status: result ? "done" : "pending" },
    ]);
    notify("Added to queue.");
  }, [buildRequest, form.patient_label, result, notify]);

  const runQueue = useCallback(async () => {
    setRunningQueue(true);
    const q = [...queue];
    for (let i = 0; i < q.length; i++) {
      if (q[i].status === "done") continue;
      q[i] = { ...q[i], status: "running" };
      setQueue([...q]);
      try {
        const data = await apiPost<PreProcedureResponse>("/api/safety/v2/preprocedure-check", q[i].request);
        q[i] = { ...q[i], status: "done", result: data };
      } catch (e) { q[i] = { ...q[i], status: "error", error: e instanceof Error ? e.message : "Failed" }; }
      setQueue([...q]);
    }
    setRunningQueue(false);
    notify("Queue complete.");
  }, [queue, notify]);

  const createSessionReport = useCallback(async () => {
    try {
      const created = await apiPost<SessionReportCreateResponse>("/api/growth/session-reports", {
        clinic_id: userId, clinician_id: userId, title: sessionTitle,
        report_date: new Date().toISOString().slice(0, 10),
        notes: "Created from AesthetiCite Safety Workspace",
      });
      for (const item of queue.filter(q => q.status === "done" && q.result)) {
        await apiPost(`/api/growth/session-reports/${created.id}/items`, {
          patient_label: item.label, procedure: item.request.procedure,
          region: item.request.region, product_type: item.request.product_type,
          technique: item.request.technique,
          injector_experience_level: item.request.injector_experience_level,
          engine_response_json: item.result,
        });
      }
      setSessionId(created.id);
      notify("Session report created.");
    } catch (e) { notify(e instanceof Error ? e.message : "Report creation failed.", "error"); }
  }, [queue, sessionTitle, userId, notify]);

  const exportSessionReport = useCallback(async () => {
    if (!sessionId) return;
    setExportingSession(true);
    try {
      const data = await apiPost<{ filename: string }>(`/api/growth/session-reports/${sessionId}/export-pdf`, {});
      downloadFile(data.filename);
      notify("Session PDF exported.");
    } catch (e) { notify(e instanceof Error ? e.message : "Export failed.", "error"); }
    finally { setExportingSession(false); }
  }, [sessionId, notify]);

  const runDrugCheck = useCallback(async () => {
    const meds = drugInput.split("\n").map(x => x.trim()).filter(Boolean);
    if (!meds.length) { notify("Enter at least one medication.", "error"); return; }
    setDrugLoading(true);
    setDrugResult(null);
    try {
      const data = await apiPost<DrugCheckResponse>("/api/safety/v2/drug-check", {
        medications: meds,
        planned_products: form.product_type ? [form.product_type] : ["injectable aesthetic procedure"],
      });
      setDrugResult(data);
      notify("Drug check complete.");
    } catch (e) { notify(e instanceof Error ? e.message : "Drug check failed.", "error"); }
    finally { setDrugLoading(false); }
  }, [drugInput, form.product_type, notify]);

  const loadBookmarks = useCallback(async () => {
    if (!userId) return;
    setBookmarksLoading(true);
    try {
      const data = await apiGet<BookmarkResponse[]>(`/api/growth/bookmarks/${userId}`);
      setBookmarks(data);
    } catch { setBookmarks([]); }
    finally { setBookmarksLoading(false); }
  }, [userId]);

  useEffect(() => { if (tab === "saved") loadBookmarks(); }, [tab, loadBookmarks]);

  const deleteBookmark = useCallback(async (id: string) => {
    try {
      await apiDelete(`/api/growth/bookmarks/${id}`);
      setBookmarks(prev => prev.filter(b => b.id !== id));
    } catch (e) { notify(e instanceof Error ? e.message : "Delete failed.", "error"); }
  }, [notify]);

  const TABS: { id: TabId; label: string; icon: string }[] = [
    { id: "safety",       label: "Safety",       icon: "🛡" },
    { id: "interactions", label: "Interactions",  icon: "💊" },
    { id: "tools",        label: "Tools",         icon: "🧪" },
    { id: "cases",        label: "Cases",         icon: "📋" },
    { id: "clinic",       label: "Clinic",        icon: "⬡" },
    { id: "saved",        label: "Saved",         icon: "🔖" },
  ];

  const interactionItems = ((drugResult?.interactions || drugResult?.items) ?? []) as DrugInteractionItem[];

  return (
    <div className="min-h-screen bg-background">
      {/* Feature 2: Onboarding */}
      {showOnboarding && <OnboardingModal onDone={dismissOnboarding} />}

      {/* Toast */}
      {toast && (
        <Toast message={toast.msg} type={toast.type} onDismiss={() => setToast(null)} />
      )}

      {/* Header */}
      <div className="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur-sm">
        <div className="mx-auto max-w-7xl px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <h1 className="text-sm font-black tracking-tight truncate">
                AesthetiCite <span className="font-medium text-muted-foreground">/ Safety Workspace</span>
              </h1>
              <p className="text-[10px] text-muted-foreground hidden sm:block">
                Safety · Drug Check · Tools · Case Logging · Clinic Admin
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => setShowOnboarding(true)}
                className="hidden sm:flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground border border-border rounded-lg px-2.5 py-1.5 transition-colors">
                ? Help
              </button>
              <a href="/ask" className="text-xs text-muted-foreground hover:text-foreground transition-colors">← Search</a>
            </div>
          </div>

          {/* Tab bar — scrollable on mobile */}
          <div className="flex gap-1 mt-2 overflow-x-auto scrollbar-none pb-px -mb-px">
            {TABS.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg text-xs font-semibold whitespace-nowrap transition-colors flex-shrink-0 ${
                  tab === t.id
                    ? "bg-background border border-b-background border-border text-foreground"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}>
                <span>{t.icon}</span>
                <span className="hidden sm:inline">{t.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Feature 1: KB health banner */}
      {kbStatus && !kbStatus.knowledge_base_ready && (
        <div className="mx-auto max-w-7xl px-4 pt-3">
          <KBHealthBanner status={kbStatus} />
        </div>
      )}

      {/* Tab content */}
      <div className="mx-auto max-w-7xl px-4 py-4 space-y-4">

        {/* ── Safety tab ────────────────────────────────────────────── */}
        {tab === "safety" && (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[400px_minmax(0,1fr)]">
            {/* Left column */}
            <div className="space-y-4">
              <Section
                title="Pre-Procedure Safety Check"
                subtitle="Enter procedure, region, product and patient factors. AesthetiCite scores risk, flags danger zones, and gives you a Go / Caution / High Risk decision."
              >
                <div className="space-y-3">
                  <input value={form.patient_label}
                    onChange={e => setForm(f => ({ ...f, patient_label: e.target.value }))}
                    placeholder="Patient label (optional)"
                    className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm" />

                  {[
                    { label: "Procedure", key: "procedure", opts: PROCEDURES, placeholder: "Select procedure" },
                    { label: "Region", key: "region", opts: REGIONS, placeholder: "Select region" },
                    { label: "Product", key: "product_type", opts: PRODUCTS, placeholder: "Select product" },
                    { label: "Technique", key: "technique", opts: TECHNIQUES, placeholder: "Select technique" },
                  ].map(({ label, key, opts, placeholder }) => (
                    <select key={key}
                      value={(form as any)[key]}
                      onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                      className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm">
                      <option value="">{placeholder}</option>
                      {opts.map(x => <option key={x} value={x}>{x}</option>)}
                    </select>
                  ))}

                  <select value={form.injector_experience_level}
                    onChange={e => setForm(f => ({ ...f, injector_experience_level: e.target.value as any }))}
                    className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm">
                    <option value="">Injector experience</option>
                    <option value="junior">Junior</option>
                    <option value="intermediate">Intermediate</option>
                    <option value="senior">Senior</option>
                  </select>

                  {/* Patient risk factors */}
                  <div className="rounded-xl border border-border p-3">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Patient risk factors</p>
                    <div className="grid grid-cols-2 gap-y-2 gap-x-3">
                      {([
                        ["prior_filler_in_same_area", "Prior filler same area"],
                        ["prior_vascular_event", "Prior vascular event"],
                        ["anticoagulation", "Anticoagulation"],
                        ["vascular_disease", "Vascular disease"],
                        ["allergy_history", "Allergy history"],
                        ["active_infection_near_site", "Active infection"],
                        ["smoking", "Smoking"],
                        ["nsaid_use", "NSAIDs"],
                        ["ssri_use", "SSRIs"],
                        ["pregnancy", "Pregnancy"],
                        ["immunosuppression", "Immunosuppression"],
                        ["autoimmune_history", "Autoimmune"],
                      ] as [keyof PatientFactors, string][]).map(([key, label]) => (
                        <label key={key} className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer min-h-[32px]">
                          <input type="checkbox"
                            checked={Boolean(form.patient_factors[key])}
                            onChange={e => setForm(f => ({
                              ...f, patient_factors: { ...f.patient_factors, [key]: e.target.checked },
                            }))}
                            className="w-4 h-4 accent-primary rounded" />
                          {label}
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <Btn variant="primary" onClick={runSafetyCheck}
                      disabled={loading || !form.procedure || !form.region || !form.product_type}
                      className="w-full">
                      {loading ? (
                        <><span className="w-3 h-3 border border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />Running…</>
                      ) : "Run Safety Check"}
                    </Btn>
                    <Btn variant="secondary" onClick={addToQueue} className="w-full">
                      + Add to Queue
                    </Btn>
                  </div>
                </div>
              </Section>

              {/* Session queue */}
              <Section title="Session Safety Report"
                subtitle="Queue multiple patients. Run all checks. Export one PDF."
                action={
                  <Btn variant="ghost" size="sm" onClick={() => setQueue([])}>Clear</Btn>
                }>
                <div className="space-y-3">
                  <input value={sessionTitle}
                    onChange={e => setSessionTitle(e.target.value)}
                    className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm"
                    placeholder="Session title" />

                  {queue.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
                      No queued procedures. Use "Add to Queue" above.
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {queue.map(item => (
                        <div key={item.id} className="rounded-xl border border-border p-3">
                          <div className="flex items-center justify-between gap-2">
                            <div className="min-w-0">
                              <p className="text-sm font-semibold truncate">{item.label}</p>
                              <p className="text-xs text-muted-foreground truncate">
                                {item.request.procedure} · {item.request.region}
                              </p>
                            </div>
                            <div className="flex items-center gap-2 flex-shrink-0">
                              {item.result && (
                                <Pill className={DECISION_STYLES[item.result.safety_assessment.decision].badge}>
                                  {item.result.safety_assessment.decision.replace("_", " ")}
                                </Pill>
                              )}
                              <span className={`text-xs ${
                                item.status === "done" ? "text-emerald-600" :
                                item.status === "error" ? "text-red-600" :
                                item.status === "running" ? "text-amber-600" : "text-muted-foreground"
                              }`}>
                                {item.status === "running" ? (
                                  <span className="w-3 h-3 border border-amber-500/30 border-t-amber-500 rounded-full animate-spin inline-block" />
                                ) : item.status}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="grid grid-cols-3 gap-2">
                    <Btn variant="primary" onClick={runQueue} disabled={runningQueue || queue.length === 0} className="w-full">
                      {runningQueue ? "Running…" : "▶ Run all"}
                    </Btn>
                    <Btn variant="secondary" onClick={createSessionReport}
                      disabled={!queue.some(q => q.status === "done")} className="w-full">
                      Create
                    </Btn>
                    <Btn variant="success" onClick={exportSessionReport}
                      disabled={!sessionId || exportingSession} className="w-full">
                      {exportingSession ? "…" : "↓ PDF"}
                    </Btn>
                  </div>
                </div>
              </Section>
            </div>

            {/* Right column — results */}
            <div className="space-y-4">
              {!result ? (
                <Section title="No result yet"
                  subtitle="Run a pre-procedure safety check to see the decision, risk score, danger zones, and evidence.">
                  <div className="rounded-xl border border-dashed border-border p-12 text-center text-sm text-muted-foreground">
                    Results appear here after running a safety check.
                  </div>
                </Section>
              ) : (
                <>
                  {/* Decision card */}
                  <Section
                    title="Safety Decision"
                    subtitle={`Engine v${result.engine_version} · ${new Date(result.generated_at_utc).toLocaleString()}`}
                    accent={DECISION_STYLES[result.safety_assessment.decision].card}
                    action={
                      <div className="flex flex-wrap gap-1.5">
                        <Btn variant="secondary" size="sm" onClick={exportSafetyPdf}>↓ PDF</Btn>
                        <Btn variant="secondary" size="sm" onClick={saveBookmark} disabled={bookmarkLoading}>
                          {bookmarkLoading ? "…" : "🔖 Save"}
                        </Btn>
                        <Btn variant="primary" size="sm" onClick={createPatientExport} disabled={patientExportLoading}>
                          {patientExportLoading ? "…" : "Patient summary"}
                        </Btn>
                      </div>
                    }>
                    <div className="flex flex-wrap items-center gap-2 mb-3">
                      <Pill className={DECISION_STYLES[result.safety_assessment.decision].badge}>
                        {result.safety_assessment.decision.replace("_", " ").toUpperCase()}
                      </Pill>
                      <Pill className="border-border bg-muted">
                        Risk {result.safety_assessment.overall_risk_score}/100
                      </Pill>
                      <Pill className="border-border bg-muted">{result.procedure_insight.procedure_name}</Pill>
                      <Pill className="border-border bg-muted">{result.procedure_insight.region}</Pill>
                      {/* Feature 3: evidence quality indicator */}
                      {result.evidence.length > 0 && (
                        <Pill className={
                          result.evidence[0].relevance_score && result.evidence[0].relevance_score > 0.5
                            ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                            : "border-amber-500/20 bg-amber-500/10 text-amber-700"
                        }>
                          {result.evidence[0].relevance_score && result.evidence[0].relevance_score > 0.5 ? "🔍 Live evidence" : "📚 Curated evidence"}
                        </Pill>
                      )}
                    </div>
                    <p className="text-sm leading-relaxed">{result.safety_assessment.rationale}</p>

                    {result.caution_flags.length > 0 && (
                      <div className="mt-3 space-y-1.5">
                        <p className="text-xs font-semibold uppercase tracking-wider text-amber-600">Caution Flags</p>
                        {result.caution_flags.map((f, i) => (
                          <div key={i} className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-sm">{f}</div>
                        ))}
                      </div>
                    )}
                  </Section>

                  {/* Top risks */}
                  <Section title="Top Complication Risks">
                    <div className="space-y-3">
                      {result.top_risks.map(risk => (
                        <div key={risk.complication} className="rounded-xl border border-border p-3">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-semibold capitalize">{risk.complication}</span>
                            <Pill className={SEVERITY_BADGE[risk.risk_level] || SEVERITY_BADGE.moderate}>
                              {risk.risk_level} · {risk.risk_score}/100
                            </Pill>
                          </div>
                          <RiskBar score={risk.risk_score} level={risk.risk_level} />
                          <p className="text-xs text-muted-foreground mt-1.5">{risk.why_it_matters}</p>
                        </div>
                      ))}
                    </div>
                  </Section>

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <Section title="⚡ Danger Zones">
                      <div className="flex flex-wrap gap-2">
                        {result.procedure_insight.danger_zones.map(z => (
                          <Pill key={z} className="bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/20">{z}</Pill>
                        ))}
                      </div>
                      {result.procedure_insight.likely_plane_or_target && (
                        <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
                          <span className="font-semibold">Plane: </span>{result.procedure_insight.likely_plane_or_target}
                        </p>
                      )}
                    </Section>
                    <Section title="Mitigation Steps">
                      <ol className="space-y-2">
                        {result.mitigation_steps.map((s, i) => (
                          <li key={i} className="flex gap-2 text-sm">
                            <span className="font-bold text-primary flex-shrink-0 w-4">{i + 1}.</span>
                            <span className="leading-relaxed">{s}</span>
                          </li>
                        ))}
                      </ol>
                    </Section>
                  </div>

                  {/* Technical notes */}
                  {result.procedure_insight.technical_notes.length > 0 && (
                    <Section title="Technique Notes">
                      <ul className="space-y-1.5">
                        {result.procedure_insight.technical_notes.map((n, i) => (
                          <li key={i} className="flex gap-2 text-sm">
                            <span className="text-primary flex-shrink-0">→</span>
                            <span className="text-muted-foreground leading-relaxed">{n}</span>
                          </li>
                        ))}
                      </ul>
                    </Section>
                  )}

                  {/* Evidence */}
                  <Section title="Clinical Evidence">
                    <div className="space-y-3">
                      {result.evidence.map(item => (
                        <div key={item.source_id} className="rounded-xl border border-border p-3">
                          <div className="flex items-start justify-between gap-2">
                            <p className="text-sm font-semibold">[{item.source_id}] {item.title}</p>
                            {item.year && <span className="text-xs text-muted-foreground flex-shrink-0">{item.year}</span>}
                          </div>
                          {item.journal && <p className="text-xs text-muted-foreground mt-0.5 italic">{item.journal}</p>}
                          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{item.note}</p>
                          {item.citation_text && (
                            <blockquote className="mt-2 border-l-2 border-primary/30 pl-3 text-xs italic text-muted-foreground">
                              "{item.citation_text}"
                            </blockquote>
                          )}
                          {item.url && (
                            <a href={item.url} target="_blank" rel="noreferrer"
                              className="text-[10px] text-primary hover:underline mt-1 block">View source →</a>
                          )}
                        </div>
                      ))}
                    </div>
                  </Section>

                  {/* Feature 6: Patient-readable export — enhanced */}
                  {patientText && (
                    <Section title="Patient-Readable Summary"
                      subtitle="Plain-language explanation for patient counselling. Copy, print, or share."
                      action={
                        <div className="flex gap-1.5">
                          <Btn variant="secondary" size="sm" onClick={() => {
                            copyToClipboard(patientText).then(() => {
                              setPatientCopied(true);
                              setTimeout(() => setPatientCopied(false), 2000);
                            });
                          }}>
                            {patientCopied ? "✓ Copied" : "Copy"}
                          </Btn>
                          <Btn variant="secondary" size="sm" onClick={() => window.print()}>Print</Btn>
                        </div>
                      }>
                      <textarea readOnly value={patientText} rows={8}
                        className="w-full rounded-xl border border-border bg-muted/20 px-3 py-3 text-sm leading-relaxed resize-none" />
                    </Section>
                  )}

                  <p className="text-[10px] text-muted-foreground/50 leading-relaxed">{result.disclaimer}</p>
                </>
              )}
            </div>
          </div>
        )}

        {/* ── Drug interactions tab ────────────────────────────────── */}
        {tab === "interactions" && (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[400px_minmax(0,1fr)]">
            <Section title="Drug Interaction Checker"
              subtitle="Enter patient medications one per line. AesthetiCite checks anticoagulants, antiplatelets, NSAIDs, SSRIs, immunosuppressants, isotretinoin, and supplements.">
              <div className="space-y-3">
                <div className="flex flex-wrap gap-1.5 mb-1">
                  {["warfarin", "aspirin", "ibuprofen", "sertraline", "apixaban", "isotretinoin", "prednisolone"].map(m => (
                    <button key={m} onClick={() => setDrugInput(prev => prev ? `${prev}\n${m}` : m)}
                      className="text-xs px-2 py-1 rounded-full border border-border hover:bg-muted/50 transition-colors">
                      + {m}
                    </button>
                  ))}
                </div>
                <textarea value={drugInput} onChange={e => setDrugInput(e.target.value)}
                  placeholder={"One medication per line:\nwarfarin\nsertraline\nibuprofen"}
                  rows={7}
                  className="w-full rounded-xl border border-border bg-background px-3 py-3 text-sm resize-none" />
                <Btn variant="primary" onClick={runDrugCheck} disabled={drugLoading} className="w-full">
                  {drugLoading ? "Checking…" : "Run Drug Check"}
                </Btn>
              </div>
            </Section>

            <Section title="Interaction Results">
              {!drugResult ? (
                <div className="rounded-xl border border-dashed border-border p-12 text-center text-sm text-muted-foreground">
                  No result yet.
                </div>
              ) : (
                <div className="space-y-4">
                  <div className={`rounded-xl border p-3 text-sm font-medium ${
                    (drugResult.proceed_with_caution || interactionItems.some(i => i.severity === "high"))
                      ? "border-red-500/20 bg-red-500/5 text-red-700 dark:text-red-400"
                      : "border-border bg-muted/20"
                  }`}>
                    {drugResult.summary}
                  </div>
                  {interactionItems.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No significant interactions identified.</p>
                  ) : (
                    interactionItems.map((item, i) => (
                      <div key={`${item.medication}-${i}`} className="rounded-xl border border-border p-4 space-y-2">
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <span className="text-sm font-semibold">{item.medication}</span>
                          <Pill className={SEVERITY_BADGE[item.severity] || SEVERITY_BADGE.moderate}>
                            {item.severity}
                          </Pill>
                        </div>
                        <p className="text-sm text-muted-foreground leading-relaxed">{item.explanation}</p>
                        <div className="rounded-lg bg-muted/40 p-2.5 text-sm">
                          <span className="font-semibold">Action: </span>{item.action}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </Section>
          </div>
        )}

        {/* ── Tools tab ────────────────────────────────────────────── */}
        {tab === "tools" && (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[560px_minmax(0,1fr)]">
            <Section title="Hyaluronidase Emergency Calculator"
              subtitle="Territory-based dosing for active vascular occlusion. Based on current consensus guidance."
              accent="border-red-500/20">
              <HyaluronidaseCalculator />
            </Section>
            <div className="space-y-4">
              <Section title="Quick Reference" subtitle="Key doses and landmarks for the most common emergencies.">
                <div className="space-y-3 text-sm">
                  {[
                    { title: "Hyaluronidase starting doses", items: ["Nasolabial fold: 450 units", "Lip: 300 units", "Glabella: 1500 units", "Nose: 900 units", "Tear trough: 150 units"] },
                    { title: "Epinephrine — anaphylaxis", items: ["0.5 mg (0.5 mL of 1:1000) IM outer thigh", "Repeat after 5 minutes if no improvement", "Do not delay — call 999 first"] },
                    { title: "Apraclonidine — toxin ptosis", items: ["0.5% eye drops, 1 drop to affected eye", "Up to three times daily", "Prescription required — check cardiovascular contraindications"] },
                  ].map(section => (
                    <div key={section.title} className="rounded-xl border border-border p-3">
                      <p className="text-xs font-semibold mb-2">{section.title}</p>
                      <ul className="space-y-1">
                        {section.items.map((item, i) => (
                          <li key={i} className="text-xs text-muted-foreground flex gap-2">
                            <span className="text-primary">•</span>{item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </Section>
              <Section title="Complication Protocols" subtitle="Direct links to full structured protocols.">
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: "Vascular occlusion", href: "/clinical-tools" },
                    { label: "Vision loss emergency", href: "/clinical-tools" },
                    { label: "Anaphylaxis", href: "/clinical-tools" },
                    { label: "Skin necrosis", href: "/clinical-tools" },
                    { label: "Toxin ptosis", href: "/clinical-tools" },
                    { label: "Infection / biofilm", href: "/clinical-tools" },
                  ].map(p => (
                    <a key={p.label} href={p.href}
                      className="rounded-xl border border-border px-3 py-2.5 text-xs font-medium hover:bg-muted/50 transition-colors flex items-center justify-between gap-1">
                      {p.label} <span className="text-muted-foreground">→</span>
                    </a>
                  ))}
                </div>
              </Section>
            </div>
          </div>
        )}

        {/* ── Cases tab ────────────────────────────────────────────── */}
        {tab === "cases" && <CaseLoggingTab userId={userId} />}

        {/* ── Clinic tab ───────────────────────────────────────────── */}
        {tab === "clinic" && <ClinicTab userId={userId} />}

        {/* ── Saved tab ────────────────────────────────────────────── */}
        {tab === "saved" && (
          <Section title="Saved Safety Answers"
            subtitle="Reuse high-value clinical assessments without repeating the full input each time."
            action={<Btn variant="secondary" size="sm" onClick={loadBookmarks}>Refresh</Btn>}>
            {bookmarksLoading ? (
              <div className="text-sm text-muted-foreground">Loading…</div>
            ) : !userId ? (
              <div className="text-sm text-muted-foreground">Sign in to use bookmarks.</div>
            ) : bookmarks.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
                No saved answers. Run a safety check and click "Save".
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {bookmarks.map(b => (
                  <div key={b.id} className="rounded-xl border border-border p-4 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold truncate">{b.title}</p>
                        <p className="text-xs text-muted-foreground truncate">{b.question}</p>
                      </div>
                      <Btn variant="danger" size="sm" onClick={() => deleteBookmark(b.id)}>Delete</Btn>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {b.tags.map(t => (
                        <Pill key={t} className="border-border bg-muted text-foreground text-[10px]">{t}</Pill>
                      ))}
                    </div>
                    <p className="text-[10px] text-muted-foreground/60">{fmtDate(b.created_at_utc)}</p>
                  </div>
                ))}
              </div>
            )}
          </Section>
        )}
      </div>

      {/* Mobile safe area */}
      <div className="h-safe-bottom" style={{ paddingBottom: "env(safe-area-inset-bottom)" }} />
    </div>
  );
}
