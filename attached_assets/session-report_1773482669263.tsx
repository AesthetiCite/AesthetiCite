/**
 * AesthetiCite — Session Safety Report
 * Route: /session-report
 *
 * Drop-in replacement for client/src/pages/session-report.tsx
 * Calls:
 *   POST /api/growth/session-reports              → create session
 *   POST /api/growth/session-reports/{id}/items   → add checked procedure
 *   POST /api/safety/preprocedure-check           → run safety check per item
 *   POST /api/growth/session-reports/{id}/export-pdf → export session PDF
 */

import { useState } from "react";
import { useLocation } from "wouter";
import {
  Shield, AlertTriangle, CheckCircle2, XCircle,
  FileDown, Loader2, ArrowLeft, Plus, Trash2,
  ChevronDown, ChevronUp, ClipboardList, Activity,
  BarChart3, Info, RotateCcw, Zap, Check
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getToken } from "@/lib/auth";

// ─── Types ─────────────────────────────────────────────────────────────────

interface SafetyAssessment {
  overall_risk_score: number;
  overall_risk_level: string;
  decision: "go" | "caution" | "high_risk";
  rationale: string;
}

interface TopRisk {
  complication: string;
  risk_score: number;
  risk_level: string;
  why_it_matters: string;
}

interface ProcedureInsight {
  procedure_name: string;
  region: string;
  danger_zones: string[];
  technical_notes: string[];
  likely_plane_or_target?: string;
}

interface EvidenceItem {
  source_id: string;
  title: string;
  note: string;
  citation_text?: string;
  url?: string;
}

interface PreProcedureResponse {
  request_id: string;
  engine_version: string;
  knowledge_revision: string;
  generated_at_utc: string;
  safety_assessment: SafetyAssessment;
  top_risks: TopRisk[];
  procedure_insight: ProcedureInsight;
  mitigation_steps: string[];
  caution_flags: string[];
  evidence: EvidenceItem[];
  disclaimer: string;
}

interface QueueItem {
  id: string; // local UUID before saving
  patient_label: string;
  procedure: string;
  region: string;
  product_type: string;
  technique: string;
  injector_experience_level: string;
  patient_factors: string[];
  // set after running
  result?: PreProcedureResponse;
  loading?: boolean;
  error?: string;
  expanded?: boolean;
}

interface SessionMeta {
  title: string;
  clinician: string;
  report_date: string;
  notes: string;
}

// ─── Constants ──────────────────────────────────────────────────────────────

const PROCEDURES = [
  "Nasolabial fold filler", "Tear trough filler", "Lip filler",
  "Glabellar toxin", "Jawline / chin / cheek filler",
  "Forehead / temple filler", "Nose filler",
];
const REGIONS = [
  "Nasolabial fold", "Tear trough / infraorbital", "Lips / perioral",
  "Glabella / forehead", "Jawline", "Chin", "Cheeks / malar",
  "Temple", "Nose", "Neck / décolletage",
];
const PRODUCT_TYPES = [
  "Hyaluronic acid filler", "Calcium hydroxylapatite", "Poly-L-lactic acid",
  "PMMA", "Botulinum toxin A", "Botulinum toxin B", "PRP", "Other",
];
const PATIENT_FACTORS = [
  "Prior vascular event", "Active infection", "Anticoagulation therapy",
  "Smoker", "Diabetes", "Immunosuppression", "Prior filler in area",
  "Keloid tendency", "Autoimmune condition",
];

const DEFAULT_ITEM: Omit<QueueItem, "id"> = {
  patient_label: "",
  procedure: "",
  region: "",
  product_type: "",
  technique: "needle",
  injector_experience_level: "intermediate",
  patient_factors: [],
};

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

// ─── Decision config ────────────────────────────────────────────────────────

function getDecision(decision: string) {
  switch (decision) {
    case "go":
      return { label: "GO", icon: CheckCircle2, color: "text-emerald-600 dark:text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/30", dot: "#22c55e" };
    case "caution":
      return { label: "CAUTION", icon: AlertTriangle, color: "text-amber-600 dark:text-amber-400", bg: "bg-amber-500/10 border-amber-500/30", dot: "#f59e0b" };
    case "high_risk":
      return { label: "HIGH RISK", icon: XCircle, color: "text-red-600 dark:text-red-400", bg: "bg-red-500/10 border-red-500/30", dot: "#ef4444" };
    default:
      return { label: "UNKNOWN", icon: Info, color: "text-muted-foreground", bg: "bg-muted/50 border-border", dot: "#6b7280" };
  }
}

// ─── Mini select ────────────────────────────────────────────────────────────

function MiniSelect({
  value, onChange, options, placeholder
}: {
  value: string; onChange: (v: string) => void;
  options: string[]; placeholder: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-md border border-border bg-background px-2.5 py-2 text-xs transition-colors focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary"
    >
      <option value="">{placeholder}</option>
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

// ─── Queue Item Card ────────────────────────────────────────────────────────

function QueueItemCard({
  item, index, onChange, onRemove, onRun
}: {
  item: QueueItem;
  index: number;
  onChange: (update: Partial<QueueItem>) => void;
  onRemove: () => void;
  onRun: () => void;
}) {
  const [detailsOpen, setDetailsOpen] = useState(!item.result);
  const [factorsOpen, setFactorsOpen] = useState(false);

  const dc = item.result ? getDecision(item.result.safety_assessment.decision) : null;
  const canRun = !!item.procedure && !!item.region && !!item.product_type;

  return (
    <Card className={`border transition-all ${item.result ? (dc?.bg || "border") : "border"}`}>
      <CardContent className="p-4 space-y-3">
        {/* Header row */}
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center">
            {index + 1}
          </div>
          <div className="flex-1 min-w-0">
            <input
              type="text"
              placeholder="Patient label (e.g. Patient A, Room 3)"
              value={item.patient_label}
              onChange={(e) => onChange({ patient_label: e.target.value })}
              className="w-full text-sm font-medium bg-transparent border-b border-border/60 pb-1 focus:outline-none focus:border-primary placeholder:text-muted-foreground/50"
            />
            {item.result && (
              <div className={`flex items-center gap-1.5 mt-1.5 text-xs font-semibold ${dc?.color}`}>
                {dc && <dc.icon className="w-3.5 h-3.5" />}
                {dc?.label} · Risk {item.result.safety_assessment.overall_risk_score}/100
              </div>
            )}
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            {item.result && (
              <button
                onClick={() => setDetailsOpen(!detailsOpen)}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                {detailsOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            )}
            <button onClick={onRemove} className="text-muted-foreground/50 hover:text-destructive transition-colors">
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Form fields — always visible if no result, collapsible if result exists */}
        {(!item.result || detailsOpen) && (
          <div className="space-y-2">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <MiniSelect value={item.procedure} onChange={(v) => onChange({ procedure: v })} options={PROCEDURES} placeholder="Procedure *" />
              <MiniSelect value={item.region} onChange={(v) => onChange({ region: v })} options={REGIONS} placeholder="Region *" />
              <MiniSelect value={item.product_type} onChange={(v) => onChange({ product_type: v })} options={PRODUCT_TYPES} placeholder="Product *" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="flex gap-1.5">
                {["needle", "cannula"].map((t) => (
                  <button
                    key={t}
                    onClick={() => onChange({ technique: t })}
                    className={`flex-1 py-1.5 rounded border text-xs font-medium capitalize transition-all ${
                      item.technique === t
                        ? "bg-primary text-primary-foreground border-primary"
                        : "border-border hover:border-primary/40"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
              <select
                value={item.injector_experience_level}
                onChange={(e) => onChange({ injector_experience_level: e.target.value })}
                className="rounded-md border border-border bg-background px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary/40"
              >
                <option value="novice">Novice</option>
                <option value="intermediate">Intermediate</option>
                <option value="advanced">Advanced</option>
              </select>
            </div>

            {/* Patient factors collapsible */}
            <div>
              <button
                onClick={() => setFactorsOpen(!factorsOpen)}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                {factorsOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                Patient factors
                {item.patient_factors.length > 0 && (
                  <span className="ml-1 text-amber-500 font-semibold">({item.patient_factors.length})</span>
                )}
              </button>
              {factorsOpen && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {PATIENT_FACTORS.map((f) => {
                    const active = item.patient_factors.includes(f);
                    return (
                      <button
                        key={f}
                        onClick={() => onChange({
                          patient_factors: active
                            ? item.patient_factors.filter((x) => x !== f)
                            : [...item.patient_factors, f]
                        })}
                        className={`px-2 py-1 rounded text-xs border transition-all ${
                          active
                            ? "bg-amber-500/15 border-amber-500/40 text-amber-700 dark:text-amber-300"
                            : "border-border text-muted-foreground hover:border-primary/40"
                        }`}
                      >
                        {f}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Run button for this item */}
            <div className="flex items-center gap-2 pt-1">
              <Button
                size="sm"
                variant={item.result ? "outline" : "default"}
                onClick={onRun}
                disabled={!canRun || item.loading}
                className="gap-1.5 text-xs h-8"
              >
                {item.loading ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : item.result ? (
                  <RotateCcw className="w-3 h-3" />
                ) : (
                  <Zap className="w-3 h-3" />
                )}
                {item.result ? "Re-check" : "Run Check"}
              </Button>
              {item.error && <span className="text-xs text-destructive">{item.error}</span>}
            </div>
          </div>
        )}

        {/* Result summary (when collapsed) */}
        {item.result && !detailsOpen && (
          <div className="text-xs text-muted-foreground pl-10">
            {item.procedure} · {item.region} · {item.product_type}
          </div>
        )}

        {/* Full result when expanded */}
        {item.result && detailsOpen && (
          <div className="pl-10 space-y-3 pt-1 border-t border-border/50">
            <p className={`text-xs leading-relaxed ${getDecision(item.result.safety_assessment.decision).color}`}>
              {item.result.safety_assessment.rationale}
            </p>

            {item.result.caution_flags.length > 0 && (
              <div className="p-2.5 rounded-lg bg-amber-500/8 border border-amber-500/20">
                <div className="text-xs font-semibold text-amber-600 dark:text-amber-400 mb-1.5">Caution Flags</div>
                <ul className="space-y-1">
                  {item.result.caution_flags.map((f, i) => (
                    <li key={i} className="text-xs text-amber-800 dark:text-amber-200 flex items-start gap-1.5">
                      <span className="mt-1 w-1 h-1 bg-amber-500 rounded-full flex-shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {item.result.top_risks.slice(0, 3).map((r, i) => (
              <div key={i} className="flex items-center gap-3 text-xs">
                <span
                  className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white"
                  style={{ backgroundColor: r.risk_level === "high" ? "#ef4444" : r.risk_level === "moderate" ? "#f59e0b" : "#22c55e" }}
                >
                  {r.risk_score}
                </span>
                <div>
                  <span className="font-medium capitalize">{r.complication}</span>
                  <span className="text-muted-foreground ml-2">{r.why_it_matters}</span>
                </div>
              </div>
            ))}

            {item.result.danger_zones.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {item.result.danger_zones.map((z, i) => (
                  <span key={i} className="px-2 py-0.5 rounded bg-red-500/10 border border-red-500/20 text-xs text-red-600 dark:text-red-400">
                    ⚠ {z}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Session Summary ────────────────────────────────────────────────────────

function SessionSummary({ items }: { items: QueueItem[] }) {
  const checked = items.filter((i) => i.result);
  const go = checked.filter((i) => i.result?.safety_assessment.decision === "go").length;
  const caution = checked.filter((i) => i.result?.safety_assessment.decision === "caution").length;
  const highRisk = checked.filter((i) => i.result?.safety_assessment.decision === "high_risk").length;
  const avgScore = checked.length
    ? Math.round(checked.reduce((s, i) => s + (i.result?.safety_assessment.overall_risk_score ?? 0), 0) / checked.length)
    : 0;

  if (checked.length === 0) return null;

  return (
    <Card className="border">
      <CardContent className="p-4">
        <div className="flex items-center gap-2 mb-3">
          <BarChart3 className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Session Summary</span>
          <span className="text-xs text-muted-foreground ml-1">({checked.length}/{items.length} checked)</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="text-center p-3 rounded-lg bg-muted/40">
            <div className="text-2xl font-bold text-foreground">{avgScore}</div>
            <div className="text-xs text-muted-foreground mt-0.5">Avg Risk</div>
          </div>
          <div className="text-center p-3 rounded-lg bg-emerald-500/8 border border-emerald-500/20">
            <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">{go}</div>
            <div className="text-xs text-emerald-600/80 dark:text-emerald-400/80 mt-0.5">Proceed</div>
          </div>
          <div className="text-center p-3 rounded-lg bg-amber-500/8 border border-amber-500/20">
            <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">{caution}</div>
            <div className="text-xs text-amber-600/80 dark:text-amber-400/80 mt-0.5">Caution</div>
          </div>
          <div className="text-center p-3 rounded-lg bg-red-500/8 border border-red-500/20">
            <div className="text-2xl font-bold text-red-600 dark:text-red-400">{highRisk}</div>
            <div className="text-xs text-red-600/80 dark:text-red-400/80 mt-0.5">High Risk</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function SessionReportPage() {
  const [, setLocation] = useLocation();

  // Session meta
  const [meta, setMeta] = useState<SessionMeta>({
    title: `Session — ${new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}`,
    clinician: "",
    report_date: today(),
    notes: "",
  });
  const [metaOpen, setMetaOpen] = useState(false);

  // Queue
  const [queue, setQueue] = useState<QueueItem[]>([
    { id: uid(), ...DEFAULT_ITEM },
  ]);

  // Session state (after saving to backend)
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [runAllLoading, setRunAllLoading] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionSaved, setSessionSaved] = useState(false);

  // ── Queue operations ──

  function addItem() {
    setQueue((q) => [...q, { id: uid(), ...DEFAULT_ITEM }]);
  }

  function removeItem(id: string) {
    setQueue((q) => q.filter((i) => i.id !== id));
  }

  function updateItem(id: string, update: Partial<QueueItem>) {
    setQueue((q) => q.map((i) => i.id === id ? { ...i, ...update } : i));
  }

  // ── Run a single item ──

  async function runItem(id: string) {
    const item = queue.find((i) => i.id === id);
    if (!item || !item.procedure || !item.region || !item.product_type) return;
    updateItem(id, { loading: true, error: undefined });
    try {
      const token = getToken();
      const res = await fetch("/api/safety/preprocedure-check", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          procedure: item.procedure,
          region: item.region,
          product_type: item.product_type,
          technique: item.technique,
          injector_experience_level: item.injector_experience_level,
          patient_factors: item.patient_factors,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Safety check failed");
      updateItem(id, { result: data as PreProcedureResponse, loading: false });
    } catch (err: any) {
      updateItem(id, { error: err.message || "Failed", loading: false });
    }
  }

  // ── Run all ──

  async function runAll() {
    const unchecked = queue.filter((i) => !i.result && i.procedure && i.region && i.product_type);
    if (unchecked.length === 0) return;
    setRunAllLoading(true);
    for (const item of unchecked) {
      await runItem(item.id);
    }
    setRunAllLoading(false);
  }

  // ── Save session to backend ──

  async function saveSession() {
    const checked = queue.filter((i) => i.result);
    if (checked.length === 0) {
      setSessionError("Run at least one safety check before saving.");
      return;
    }
    setSaveLoading(true);
    setSessionError(null);
    try {
      const token = getToken();
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      // 1. Create session
      const createRes = await fetch("/api/growth/session-reports", {
        method: "POST",
        headers,
        body: JSON.stringify({
          title: meta.title,
          clinician_id: meta.clinician || undefined,
          report_date: meta.report_date || undefined,
          notes: meta.notes || undefined,
        }),
      });
      const created = await createRes.json();
      if (!createRes.ok) throw new Error(created?.detail || "Failed to create session");
      const sid = created.id;
      setSessionId(sid);

      // 2. Add each checked item
      for (const item of checked) {
        await fetch(`/api/growth/session-reports/${sid}/items`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            patient_label: item.patient_label || `Patient ${queue.indexOf(item) + 1}`,
            procedure: item.procedure,
            region: item.region,
            product_type: item.product_type,
            technique: item.technique,
            injector_experience_level: item.injector_experience_level,
            engine_response_json: item.result,
          }),
        });
      }

      setSessionSaved(true);
    } catch (err: any) {
      setSessionError(err.message || "Failed to save session.");
    } finally {
      setSaveLoading(false);
    }
  }

  // ── Export PDF ──

  async function exportPDF() {
    if (!sessionId) {
      // Save first, then export
      await saveSession();
    }
    const sid = sessionId;
    if (!sid) return;
    setPdfLoading(true);
    try {
      const token = getToken();
      const res = await fetch(`/api/growth/session-reports/${sid}/export-pdf`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "PDF export failed");
      if (data.filename) window.open(`/exports/${data.filename}`, "_blank");
    } catch (err: any) {
      setSessionError(err.message || "PDF export failed.");
    } finally {
      setPdfLoading(false);
    }
  }

  const checkedCount = queue.filter((i) => i.result).length;
  const uncheckedReady = queue.filter((i) => !i.result && i.procedure && i.region && i.product_type).length;

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => setLocation("/")} className="gap-2 -ml-2">
              <ArrowLeft className="w-4 h-4" />
              <span className="hidden sm:inline">Back</span>
            </Button>
            <div className="w-px h-5 bg-border" />
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
                <ClipboardList className="w-4 h-4 text-primary" />
              </div>
              <span className="font-semibold text-sm">Session Safety Report</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {uncheckedReady > 0 && (
              <Button
                size="sm"
                variant="outline"
                onClick={runAll}
                disabled={runAllLoading}
                className="gap-1.5 text-xs"
              >
                {runAllLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
                Run All ({uncheckedReady})
              </Button>
            )}
            {checkedCount > 0 && !sessionSaved && (
              <Button
                size="sm"
                variant="outline"
                onClick={saveSession}
                disabled={saveLoading}
                className="gap-1.5 text-xs"
              >
                {saveLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                Save Session
              </Button>
            )}
            <Button
              size="sm"
              onClick={exportPDF}
              disabled={pdfLoading || checkedCount === 0}
              className="gap-1.5 text-xs"
            >
              {pdfLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <FileDown className="w-3 h-3" />}
              Export PDF
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 space-y-4">

        {/* Session meta */}
        <Card className="border">
          <CardContent className="p-4">
            <button
              onClick={() => setMetaOpen(!metaOpen)}
              className="w-full flex items-center justify-between gap-2 text-left"
            >
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-primary" />
                <span className="text-sm font-semibold">{meta.title || "Untitled Session"}</span>
                {meta.clinician && (
                  <span className="text-xs text-muted-foreground">· {meta.clinician}</span>
                )}
                <span className="text-xs text-muted-foreground">· {meta.report_date}</span>
              </div>
              {metaOpen ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
            </button>

            {metaOpen && (
              <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="sm:col-span-2 space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Session Title</label>
                  <input
                    type="text"
                    value={meta.title}
                    onChange={(e) => setMeta((m) => ({ ...m, title: e.target.value }))}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary/40"
                    placeholder="e.g. Morning Clinic — 14 March 2026"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Clinician</label>
                  <input
                    type="text"
                    value={meta.clinician}
                    onChange={(e) => setMeta((m) => ({ ...m, clinician: e.target.value }))}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary/40"
                    placeholder="Dr. name"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Date</label>
                  <input
                    type="date"
                    value={meta.report_date}
                    onChange={(e) => setMeta((m) => ({ ...m, report_date: e.target.value }))}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary/40"
                  />
                </div>
                <div className="sm:col-span-2 space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Notes</label>
                  <textarea
                    value={meta.notes}
                    onChange={(e) => setMeta((m) => ({ ...m, notes: e.target.value }))}
                    rows={2}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-primary/40"
                    placeholder="Optional session notes"
                  />
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Session summary (appears after checks run) */}
        <SessionSummary items={queue} />

        {/* Saved confirmation */}
        {sessionSaved && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            Session saved. Click Export PDF to download the report.
            {sessionId && <span className="text-xs text-muted-foreground ml-auto">ID: {sessionId.slice(0, 12)}…</span>}
          </div>
        )}

        {/* Error */}
        {sessionError && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-sm text-destructive">
            <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            {sessionError}
          </div>
        )}

        {/* Queue header */}
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
            <Shield className="w-3.5 h-3.5" />
            Procedure Queue
            <span className="font-normal text-primary">
              {checkedCount}/{queue.length} checked
            </span>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={addItem}
            className="gap-1.5 text-xs"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Procedure
          </Button>
        </div>

        {/* Queue items */}
        <div className="space-y-3">
          {queue.map((item, index) => (
            <QueueItemCard
              key={item.id}
              item={item}
              index={index}
              onChange={(update) => updateItem(item.id, update)}
              onRemove={() => removeItem(item.id)}
              onRun={() => runItem(item.id)}
            />
          ))}
        </div>

        {/* Add more */}
        <button
          onClick={addItem}
          className="w-full py-3 rounded-xl border-2 border-dashed border-border hover:border-primary/40 hover:bg-muted/30 transition-all text-sm text-muted-foreground flex items-center justify-center gap-2"
        >
          <Plus className="w-4 h-4" />
          Add another procedure
        </button>

        {/* Footer disclaimer */}
        <p className="text-xs text-muted-foreground/60 text-center pb-4 leading-relaxed">
          <Shield className="w-3 h-3 inline-block mr-1" />
          Session Safety Reports are clinical decision support tools. They do not replace clinician judgment, anatomical expertise, or local emergency protocols.
        </p>
      </div>
    </div>
  );
}
