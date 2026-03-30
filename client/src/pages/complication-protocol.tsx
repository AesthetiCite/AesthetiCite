/**
 * AesthetiCite — Complication Protocol Engine
 * Route: /complications
 *
 * Calls:
 *   GET  /api/complications/protocols          → list available protocols
 *   POST /api/complications/protocol           → run protocol lookup
 *   POST /api/complications/export-pdf         → export protocol PDF
 *   POST /api/complications/feedback           → submit clinician feedback
 *   POST /api/complications/log-case           → log case to dataset
 */

import { useState, useEffect, useRef } from "react";
import { useLocation } from "wouter";
import {
  AlertTriangle, CheckCircle2, XCircle, Shield,
  ArrowLeft, FileDown, Loader2, ChevronDown, ChevronUp,
  Zap, BookOpen, Clock, Activity, ClipboardList,
  Star, RotateCcw, Info, TriangleAlert, Eye,
  Syringe, Thermometer, Brain
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getToken } from "@/lib/auth";

// ─── Types (mirrors Python ProtocolResponse exactly) ─────────────────────────

interface ProtocolStep {
  step_number: number;
  action: string;
  rationale: string;
  priority: "primary" | "secondary";
}

interface DoseGuidance {
  substance: string;
  recommendation: string;
  notes: string;
}

interface ProcedureInsight {
  procedure_name: string;
  likely_plane?: string;
  key_danger_zones: string[];
  technique_notes: string[];
  common_products_or_classes: string[];
}

interface RiskAssessment {
  risk_score: number;
  severity: "low" | "moderate" | "high" | "critical";
  urgency: "routine" | "same_day" | "urgent" | "immediate";
  likely_time_critical: boolean;
  evidence_strength: "limited" | "moderate" | "strong";
}

interface EvidenceItem {
  source_id: string;
  title: string;
  note: string;
  citation_text?: string;
  url?: string;
  source_type?: string;
  relevance_score?: number;
}

interface ProtocolResponse {
  request_id: string;
  engine_version: string;
  protocol_revision: string;
  generated_at_utc: string;
  matched_protocol_key: string;
  matched_protocol_name: string;
  confidence: number;
  risk_assessment: RiskAssessment;
  clinical_summary: string;
  immediate_actions: ProtocolStep[];
  dose_guidance: DoseGuidance[];
  procedure_insight?: ProcedureInsight;
  red_flags: string[];
  escalation: string[];
  monitoring: string[];
  limitations: string[];
  follow_up_questions: string[];
  evidence: EvidenceItem[];
  disclaimer: string;
}

interface AvailableProtocol {
  key: string;
  name: string;
  severity: string;
  urgency: string;
}

// ─── Form state ──────────────────────────────────────────────────────────────

interface FormState {
  query: string;
  region: string;
  procedure: string;
  product_type: string;
  symptoms: string[];
  time_since_injection_minutes: string;
  visual_symptoms: boolean;
  skin_color_change: string;
  pain_score_10: string;
  capillary_refill_delayed: boolean;
  filler_confirmed_ha: boolean;
  tenderness: boolean;
  warmth: boolean;
  erythema: boolean;
  fluctuance: boolean;
  fever: boolean;
  wheeze: boolean;
  hypotension: boolean;
  facial_or_tongue_swelling: boolean;
  eyelid_droop: boolean;
  diplopia: boolean;
  toxin_recent: boolean;
}

const EMPTY_FORM: FormState = {
  query: "",
  region: "",
  procedure: "",
  product_type: "",
  symptoms: [],
  time_since_injection_minutes: "",
  visual_symptoms: false,
  skin_color_change: "",
  pain_score_10: "",
  capillary_refill_delayed: false,
  filler_confirmed_ha: false,
  tenderness: false,
  warmth: false,
  erythema: false,
  fluctuance: false,
  fever: false,
  wheeze: false,
  hypotension: false,
  facial_or_tongue_swelling: false,
  eyelid_droop: false,
  diplopia: false,
  toxin_recent: false,
};

// ─── Quick-select symptom clusters ──────────────────────────────────────────

const QUICK_SCENARIOS = [
  {
    label: "Blanching / mottling after filler",
    icon: "🔴",
    fill: {
      query: "Patient has blanching and mottling after HA filler injection",
      procedure: "HA filler",
      skin_color_change: "blanching",
      capillary_refill_delayed: true,
      filler_confirmed_ha: true,
      symptoms: ["blanching", "mottling"],
    },
  },
  {
    label: "Visual symptoms after filler",
    icon: "👁️",
    fill: {
      query: "Visual disturbance after filler injection — possible vascular event",
      visual_symptoms: true,
      filler_confirmed_ha: true,
      symptoms: ["visual disturbance"],
    },
  },
  {
    label: "Ptosis after toxin",
    icon: "⬇️",
    fill: {
      query: "Eyelid ptosis after botulinum toxin treatment",
      procedure: "botulinum toxin",
      eyelid_droop: true,
      toxin_recent: true,
      symptoms: ["eyelid ptosis"],
    },
  },
  {
    label: "Nodule / lump after filler",
    icon: "🔵",
    fill: {
      query: "Palpable nodule or lump after filler injection",
      filler_confirmed_ha: true,
      symptoms: ["nodule", "lump"],
    },
  },
  {
    label: "Tyndall effect",
    icon: "💙",
    fill: {
      query: "Blue-grey discoloration consistent with Tyndall effect after superficial filler",
      procedure: "superficial HA filler",
      skin_color_change: "blue-grey",
      filler_confirmed_ha: true,
      symptoms: ["Tyndall effect", "bluish discoloration"],
    },
  },
  {
    label: "Anaphylaxis / allergic reaction",
    icon: "⚠️",
    fill: {
      query: "Systemic allergic reaction or possible anaphylaxis after aesthetic treatment",
      wheeze: true,
      symptoms: ["urticaria", "wheeze", "systemic reaction"],
    },
  },
  {
    label: "Infection / hot nodule",
    icon: "🔥",
    fill: {
      query: "Tender erythematous swelling suggesting infection or biofilm after filler",
      tenderness: true,
      warmth: true,
      erythema: true,
      symptoms: ["tender swelling", "erythema", "warmth"],
    },
  },
];

// ─── Severity / urgency display helpers ─────────────────────────────────────

function getSeverityStyle(severity: string) {
  switch (severity) {
    case "critical": return { bg: "bg-red-500/15 border-red-500/40", text: "text-red-600 dark:text-red-400", label: "CRITICAL", dot: "#ef4444" };
    case "high":     return { bg: "bg-orange-500/15 border-orange-500/40", text: "text-orange-600 dark:text-orange-400", label: "HIGH", dot: "#f97316" };
    case "moderate": return { bg: "bg-amber-500/15 border-amber-500/40", text: "text-amber-600 dark:text-amber-400", label: "MODERATE", dot: "#f59e0b" };
    default:         return { bg: "bg-emerald-500/15 border-emerald-500/40", text: "text-emerald-600 dark:text-emerald-400", label: "LOW", dot: "#22c55e" };
  }
}

function getUrgencyLabel(urgency: string) {
  switch (urgency) {
    case "immediate":  return { label: "Act immediately", color: "text-red-600 dark:text-red-400" };
    case "urgent":     return { label: "Urgent — act now", color: "text-orange-600 dark:text-orange-400" };
    case "same_day":   return { label: "Same-day review", color: "text-amber-600 dark:text-amber-400" };
    default:           return { label: "Routine", color: "text-emerald-600 dark:text-emerald-400" };
  }
}

// ─── Toggle chip ─────────────────────────────────────────────────────────────

function ToggleChip({
  label, value, onChange, danger = false
}: {
  label: string; value: boolean; onChange: (v: boolean) => void; danger?: boolean;
}) {
  return (
    <button
      onClick={() => onChange(!value)}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium transition-all ${
        value
          ? danger
            ? "bg-red-500/15 border-red-500/40 text-red-700 dark:text-red-300"
            : "bg-amber-500/15 border-amber-500/40 text-amber-700 dark:text-amber-300"
          : "border-border text-muted-foreground hover:border-primary/40 hover:bg-muted/40"
      }`}
    >
      {value ? "✓" : "+"} {label}
    </button>
  );
}

// ─── Collapsible section wrapper ─────────────────────────────────────────────

function Section({
  icon, title, accent = "default", children, defaultOpen = true
}: {
  icon: React.ReactNode; title: string; accent?: "red" | "amber" | "emerald" | "blue" | "default";
  children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const accentMap = {
    red:     "border-red-500/30 bg-red-500/5",
    amber:   "border-amber-500/30 bg-amber-500/5",
    emerald: "border-emerald-500/30 bg-emerald-500/5",
    blue:    "border-blue-500/30 bg-blue-500/5",
    default: "border-border bg-background",
  };
  const textMap = {
    red: "text-red-600 dark:text-red-400",
    amber: "text-amber-600 dark:text-amber-400",
    emerald: "text-emerald-600 dark:text-emerald-400",
    blue: "text-blue-600 dark:text-blue-400",
    default: "text-foreground",
  };

  return (
    <Card className={`border ${accentMap[accent]}`}>
      <CardContent className="p-4">
        <button
          onClick={() => setOpen(!open)}
          className="w-full flex items-center justify-between gap-2 text-left"
        >
          <div className={`flex items-center gap-2 text-sm font-semibold ${textMap[accent]}`}>
            {icon}
            {title}
          </div>
          {open ? <ChevronUp className="w-3.5 h-3.5 text-muted-foreground" /> : <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />}
        </button>
        {open && <div className="mt-3">{children}</div>}
      </CardContent>
    </Card>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function ComplicationProtocolPage() {
  const [, setLocation] = useLocation();
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [availableProtocols, setAvailableProtocols] = useState<AvailableProtocol[]>([]);
  const [result, setResult] = useState<ProtocolResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"decision_support" | "emergency" | "teaching">("decision_support");
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/api/complications/protocols")
      .then((r) => r.json())
      .then((d) => {
        if (Array.isArray(d)) setAvailableProtocols(d);
        else if (Array.isArray(d?.protocols)) setAvailableProtocols(d.protocols);
      })
      .catch(() => {});
  }, []);

  function setField<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function applyQuickScenario(fill: Partial<FormState>) {
    setForm((f) => ({ ...EMPTY_FORM, ...fill }));
    setResult(null);
    setError(null);
  }

  function buildPayload() {
    const context: Record<string, unknown> = {};
    if (form.region)          context.region                    = form.region;
    if (form.procedure)       context.procedure                 = form.procedure;
    if (form.product_type)    context.product_type              = form.product_type;
    if (form.symptoms.length) context.symptoms                  = form.symptoms;
    if (form.time_since_injection_minutes) {
      context.time_since_injection_minutes = parseInt(form.time_since_injection_minutes, 10);
    }
    if (form.skin_color_change)            context.skin_color_change          = form.skin_color_change;
    if (form.pain_score_10)                context.pain_score_10              = parseInt(form.pain_score_10, 10);
    if (form.visual_symptoms)              context.visual_symptoms            = true;
    if (form.capillary_refill_delayed)     context.capillary_refill_delayed   = true;
    if (form.filler_confirmed_ha)          context.filler_confirmed_ha        = true;
    if (form.tenderness)                   context.tenderness                 = true;
    if (form.warmth)                       context.warmth                     = true;
    if (form.erythema)                     context.erythema                   = true;
    if (form.fluctuance)                   context.fluctuance                 = true;
    if (form.fever)                        context.fever                      = true;
    if (form.wheeze)                       context.wheeze                     = true;
    if (form.hypotension)                  context.hypotension                = true;
    if (form.facial_or_tongue_swelling)    context.facial_or_tongue_swelling  = true;
    if (form.eyelid_droop)                 context.eyelid_droop               = true;
    if (form.diplopia)                     context.diplopia                   = true;
    if (form.toxin_recent)                 context.toxin_recent               = true;

    return { query: form.query, context, mode };
  }

  async function handleSubmit() {
    if (!form.query.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setFeedbackSent(false);
    try {
      const token = getToken();
      const res = await fetch("/api/complications/protocol", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(buildPayload()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Protocol lookup failed");
      setResult(data as ProtocolResponse);
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    } catch (err: any) {
      setError(err.message || "Failed to generate protocol. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleExportPDF() {
    if (!form.query.trim()) return;
    setPdfLoading(true);
    try {
      const token = getToken();
      const res = await fetch("/api/complications/export-pdf", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(buildPayload()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "PDF export failed");
      if (data.filename) window.open(`/exports/${data.filename}`, "_blank");
    } catch (err: any) {
      setError(err.message || "PDF export failed.");
    } finally {
      setPdfLoading(false);
    }
  }

  async function submitFeedback(useful: boolean) {
    if (!result) return;
    try {
      const token = getToken();
      await fetch("/api/complications/feedback", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          request_id: result.request_id,
          rating: useful ? 5 : 2,
          was_useful: useful,
          selected_protocol_key: result.matched_protocol_key,
        }),
      });
      setFeedbackSent(true);
    } catch { /* non-fatal */ }
  }

  const severityStyle = result ? getSeverityStyle(result.risk_assessment.severity) : null;
  const urgencyInfo = result ? getUrgencyLabel(result.risk_assessment.urgency) : null;

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => setLocation("/")} className="gap-2 -ml-2">
              <ArrowLeft className="w-4 h-4" />
              <span className="hidden sm:inline">Back</span>
            </Button>
            <div className="w-px h-5 bg-border" />
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-red-500/10 flex items-center justify-center">
                <AlertTriangle className="w-4 h-4 text-red-500" />
              </div>
              <div>
                <span className="font-semibold text-sm">Complication Protocol Engine</span>
                <span className="hidden sm:inline text-xs text-muted-foreground ml-2">
                  v{result?.engine_version ?? "3.1"}
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {result && (
              <Button
                variant="outline" size="sm"
                onClick={() => { setResult(null); setForm(EMPTY_FORM); setError(null); }}
                className="gap-1.5 text-xs"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                New
              </Button>
            )}
            <Button
              variant="outline" size="sm"
              onClick={handleExportPDF}
              disabled={pdfLoading || !result}
              className="gap-1.5"
            >
              {pdfLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileDown className="w-3.5 h-3.5" />}
              PDF
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-5">

        {/* Quick scenario chips */}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Quick scenarios</p>
          <div className="flex flex-wrap gap-2">
            {QUICK_SCENARIOS.map((s) => (
              <button
                key={s.label}
                onClick={() => applyQuickScenario(s.fill as Partial<FormState>)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border text-xs font-medium hover:border-primary/50 hover:bg-muted/40 transition-all"
              >
                <span>{s.icon}</span>
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {/* Input card */}
        <Card>
          <CardContent className="p-4 space-y-4">
            {/* Query */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Clinical presentation <span className="text-red-500">*</span>
              </label>
              <textarea
                rows={2}
                value={form.query}
                onChange={(e) => setField("query", e.target.value)}
                placeholder="e.g. Patient has blanching and pain after HA filler to nasolabial fold — capillary refill delayed"
                className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>

            {/* Context row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Procedure</label>
                <input
                  type="text"
                  value={form.procedure}
                  onChange={(e) => setField("procedure", e.target.value)}
                  placeholder="e.g. HA filler"
                  className="w-full rounded-md border border-border bg-background px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary/40"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Region</label>
                <input
                  type="text"
                  value={form.region}
                  onChange={(e) => setField("region", e.target.value)}
                  placeholder="e.g. nasolabial fold"
                  className="w-full rounded-md border border-border bg-background px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary/40"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Time since injection</label>
                <input
                  type="number"
                  value={form.time_since_injection_minutes}
                  onChange={(e) => setField("time_since_injection_minutes", e.target.value)}
                  placeholder="minutes"
                  className="w-full rounded-md border border-border bg-background px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary/40"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Pain (0–10)</label>
                <input
                  type="number"
                  min={0} max={10}
                  value={form.pain_score_10}
                  onChange={(e) => setField("pain_score_10", e.target.value)}
                  placeholder="0–10"
                  className="w-full rounded-md border border-border bg-background px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary/40"
                />
              </div>
            </div>

            {/* Clinical flags */}
            <div className="space-y-2">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Clinical flags</p>
              <div className="flex flex-wrap gap-2">
                <ToggleChip label="Visual symptoms" value={form.visual_symptoms} onChange={(v) => setField("visual_symptoms", v)} danger />
                <ToggleChip label="Delayed capillary refill" value={form.capillary_refill_delayed} onChange={(v) => setField("capillary_refill_delayed", v)} danger />
                <ToggleChip label="HA filler confirmed" value={form.filler_confirmed_ha} onChange={(v) => setField("filler_confirmed_ha", v)} />
                <ToggleChip label="Tenderness" value={form.tenderness} onChange={(v) => setField("tenderness", v)} />
                <ToggleChip label="Warmth" value={form.warmth} onChange={(v) => setField("warmth", v)} />
                <ToggleChip label="Erythema" value={form.erythema} onChange={(v) => setField("erythema", v)} />
                <ToggleChip label="Fluctuance" value={form.fluctuance} onChange={(v) => setField("fluctuance", v)} danger />
                <ToggleChip label="Fever" value={form.fever} onChange={(v) => setField("fever", v)} danger />
                <ToggleChip label="Wheeze" value={form.wheeze} onChange={(v) => setField("wheeze", v)} danger />
                <ToggleChip label="Hypotension" value={form.hypotension} onChange={(v) => setField("hypotension", v)} danger />
                <ToggleChip label="Facial/tongue swelling" value={form.facial_or_tongue_swelling} onChange={(v) => setField("facial_or_tongue_swelling", v)} danger />
                <ToggleChip label="Eyelid droop" value={form.eyelid_droop} onChange={(v) => setField("eyelid_droop", v)} />
                <ToggleChip label="Diplopia" value={form.diplopia} onChange={(v) => setField("diplopia", v)} danger />
                <ToggleChip label="Recent toxin" value={form.toxin_recent} onChange={(v) => setField("toxin_recent", v)} />
              </div>
            </div>

            {/* Mode + Submit */}
            <div className="flex flex-wrap items-center gap-3 pt-1">
              <div className="flex gap-1.5">
                {(["decision_support", "emergency", "teaching"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all capitalize ${
                      mode === m
                        ? m === "emergency"
                          ? "bg-red-500 text-white border-red-500"
                          : "bg-primary text-primary-foreground border-primary"
                        : "border-border text-muted-foreground hover:border-primary/40"
                    }`}
                  >
                    {m.replace("_", " ")}
                  </button>
                ))}
              </div>
              <Button
                onClick={handleSubmit}
                disabled={!form.query.trim() || loading}
                className="gap-2 shadow-lg shadow-primary/20"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                {loading ? "Generating…" : "Get Protocol"}
              </Button>
            </div>

            {error && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-sm text-destructive">
                <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                {error}
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── RESULTS ──────────────────────────────────────────────────────── */}
        {result && severityStyle && urgencyInfo && (
          <div ref={resultsRef} className="space-y-4">

            {/* Protocol header */}
            <div className={`rounded-xl border p-5 ${severityStyle.bg}`}>
              <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                <div className="flex-1 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${severityStyle.bg} ${severityStyle.text}`}>
                      {severityStyle.label}
                    </span>
                    <span className={`text-xs font-semibold ${urgencyInfo.color}`}>
                      <Clock className="w-3 h-3 inline mr-1" />
                      {urgencyInfo.label}
                    </span>
                    {result.risk_assessment.likely_time_critical && (
                      <span className="text-xs font-bold text-red-600 dark:text-red-400 animate-pulse">
                        ⏱ TIME CRITICAL
                      </span>
                    )}
                  </div>
                  <h2 className={`text-base font-bold ${severityStyle.text}`}>
                    {result.matched_protocol_name}
                  </h2>
                  <p className="text-sm text-foreground/80 leading-relaxed">
                    {result.clinical_summary}
                  </p>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    <span>Confidence: {Math.round(result.confidence * 100)}%</span>
                    <span>·</span>
                    <span>Evidence: {result.risk_assessment.evidence_strength}</span>
                    <span>·</span>
                    <span>Risk score: {result.risk_assessment.risk_score}/100</span>
                    <span>·</span>
                    <span>v{result.engine_version} · {result.protocol_revision}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Red flags — always prominent */}
            {result.red_flags.length > 0 && (
              <Card className="border-red-500/40 bg-red-500/8">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <TriangleAlert className="w-4 h-4 text-red-500" />
                    <span className="text-sm font-bold text-red-600 dark:text-red-400">Red Flags — escalate if present</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {result.red_flags.map((flag, i) => (
                      <span key={i} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-red-500/15 border border-red-500/30 text-xs font-medium text-red-700 dark:text-red-300">
                        ⚠ {flag}
                      </span>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Immediate actions */}
            <Section icon={<Syringe className="w-4 h-4" />} title="Immediate Actions" accent="red" defaultOpen>
              <ol className="space-y-3">
                {result.immediate_actions.map((step, i) => (
                  <li key={i} className={`flex gap-3 ${step.priority === "secondary" ? "opacity-80" : ""}`}>
                    <span className={`flex-shrink-0 w-6 h-6 rounded-full text-xs font-bold flex items-center justify-center mt-0.5 ${
                      step.priority === "primary"
                        ? "bg-red-500 text-white"
                        : "bg-muted text-muted-foreground"
                    }`}>
                      {step.step_number}
                    </span>
                    <div>
                      <p className="text-sm font-medium text-foreground">{step.action}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">{step.rationale}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </Section>

            {/* Dose guidance */}
            {result.dose_guidance.length > 0 && (
              <Section icon={<Activity className="w-4 h-4" />} title="Dose Guidance" accent="amber" defaultOpen>
                <div className="space-y-3">
                  {result.dose_guidance.map((dose, i) => (
                    <div key={i} className="p-3 rounded-lg bg-background border border-border/60">
                      <p className="text-sm font-semibold text-foreground">{dose.substance}</p>
                      <p className="text-sm mt-1 text-foreground/85">{dose.recommendation}</p>
                      {dose.notes && (
                        <p className="text-xs text-muted-foreground mt-1 italic">{dose.notes}</p>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Escalation */}
            {result.escalation.length > 0 && (
              <Section icon={<AlertTriangle className="w-4 h-4" />} title="Escalation" accent="amber" defaultOpen>
                <ul className="space-y-2">
                  {result.escalation.map((e, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-1.5 flex-shrink-0" />
                      {e}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {/* Monitoring */}
            {result.monitoring.length > 0 && (
              <Section icon={<Eye className="w-4 h-4" />} title="Monitoring" accent="blue" defaultOpen>
                <ul className="space-y-2">
                  {result.monitoring.map((m, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <CheckCircle2 className="w-3.5 h-3.5 text-blue-500 mt-0.5 flex-shrink-0" />
                      {m}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {/* Procedure insight */}
            {result.procedure_insight && (
              <Section icon={<Brain className="w-4 h-4" />} title="Procedure Intelligence" accent="default" defaultOpen={false}>
                <div className="space-y-3">
                  {result.procedure_insight.likely_plane && (
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Injection plane</p>
                      <p className="text-sm text-foreground/80">{result.procedure_insight.likely_plane}</p>
                    </div>
                  )}
                  {result.procedure_insight.key_danger_zones.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Danger zones</p>
                      <div className="flex flex-wrap gap-1.5">
                        {result.procedure_insight.key_danger_zones.map((z, i) => (
                          <span key={i} className="px-2.5 py-1 rounded-md bg-red-500/10 border border-red-500/20 text-xs text-red-700 dark:text-red-300 font-medium">
                            ⚠ {z}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {result.procedure_insight.technique_notes.length > 0 && (
                    <ul className="space-y-1">
                      {result.procedure_insight.technique_notes.map((n, i) => (
                        <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                          <span className="mt-1 w-1 h-1 rounded-full bg-muted-foreground flex-shrink-0" />
                          {n}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </Section>
            )}

            {/* Follow-up questions */}
            {result.follow_up_questions.length > 0 && (
              <Section icon={<ClipboardList className="w-4 h-4" />} title="Clinical Follow-up Questions" accent="default" defaultOpen={false}>
                <ul className="space-y-2">
                  {result.follow_up_questions.map((q, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                      <span className="flex-shrink-0 w-4 h-4 rounded-full bg-muted text-xs font-bold flex items-center justify-center mt-0.5">
                        {i + 1}
                      </span>
                      {q}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {/* Limitations */}
            {result.limitations.length > 0 && (
              <Section icon={<Info className="w-4 h-4" />} title="Limitations" accent="default" defaultOpen={false}>
                <ul className="space-y-1.5">
                  {result.limitations.map((l, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                      <span className="mt-1 w-1 h-1 rounded-full bg-muted-foreground flex-shrink-0" />
                      {l}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {/* Evidence */}
            <Card>
              <CardContent className="p-4">
                <button
                  onClick={() => setEvidenceOpen(!evidenceOpen)}
                  className="w-full flex items-center justify-between gap-2"
                >
                  <div className="flex items-center gap-2">
                    <BookOpen className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm font-semibold">Evidence ({result.evidence.length} sources)</span>
                  </div>
                  {evidenceOpen ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                </button>
                {evidenceOpen && (
                  <div className="mt-3 space-y-3">
                    {result.evidence.map((ev, i) => (
                      <div key={i} className="p-3 rounded-lg bg-muted/40 border border-border/50 space-y-1">
                        <div className="flex items-start justify-between gap-2">
                          <span className="text-xs font-semibold text-primary">[{ev.source_id}]</span>
                          {ev.url && (
                            <a href={ev.url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">
                              View ↗
                            </a>
                          )}
                        </div>
                        <p className="text-xs font-medium text-foreground/90">{ev.title}</p>
                        <p className="text-xs text-muted-foreground">{ev.note}</p>
                        {ev.citation_text && (
                          <blockquote className="text-xs italic text-muted-foreground border-l-2 border-primary/30 pl-2 mt-1">
                            "{ev.citation_text}"
                          </blockquote>
                        )}
                        {ev.source_type && (
                          <span className="inline-block text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                            {ev.source_type}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Feedback */}
            <div className="flex items-center gap-3 justify-center py-1">
              {!feedbackSent ? (
                <>
                  <span className="text-xs text-muted-foreground">Was this protocol useful?</span>
                  <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7" onClick={() => submitFeedback(true)}>
                    <Star className="w-3 h-3" /> Yes
                  </Button>
                  <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7" onClick={() => submitFeedback(false)}>
                    No
                  </Button>
                </>
              ) : (
                <span className="text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Feedback recorded
                </span>
              )}
            </div>

            {/* Disclaimer */}
            <p className="text-xs text-muted-foreground/60 text-center leading-relaxed px-4 pb-2">
              <Shield className="w-3 h-3 inline mr-1" />
              {result.disclaimer}
            </p>
          </div>
        )}

        {/* Available protocols list (when no result) */}
        {!result && availableProtocols.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Available protocols</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {availableProtocols.map((p) => {
                const s = getSeverityStyle(p.severity);
                return (
                  <button
                    key={p.key}
                    onClick={() => {
                      setField("query", p.name);
                      setResult(null);
                    }}
                    className="flex items-start gap-3 p-3 rounded-lg border border-border hover:border-primary/40 hover:bg-muted/30 text-left transition-all"
                  >
                    <span className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0" style={{ backgroundColor: s.dot }} />
                    <div>
                      <p className="text-xs font-medium text-foreground">{p.name}</p>
                      <p className={`text-xs ${s.text} capitalize`}>{p.severity} · {p.urgency.replace("_", " ")}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
