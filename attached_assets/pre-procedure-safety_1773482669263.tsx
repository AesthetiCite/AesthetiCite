/**
 * AesthetiCite — Pre-Procedure Safety Check
 * Route: /safety-check
 *
 * Drop-in replacement for client/src/pages/pre-procedure-safety.tsx
 * Calls: POST /api/safety/preprocedure-check
 *        POST /api/safety/preprocedure-check/export-pdf
 */

import { useState, useRef } from "react";
import { useLocation } from "wouter";
import {
  Shield, AlertTriangle, CheckCircle2, XCircle,
  ChevronDown, ChevronUp, FileDown, Loader2,
  ArrowLeft, Zap, MapPin, Lightbulb, BookOpen,
  Activity, RotateCcw, Plus, Minus, Info
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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

interface FormState {
  procedure: string;
  region: string;
  product_type: string;
  technique: string;
  injector_experience_level: string;
  patient_factors: string[];
}

// ─── Constants ──────────────────────────────────────────────────────────────

const PROCEDURES = [
  "Nasolabial fold filler",
  "Tear trough filler",
  "Lip filler",
  "Glabellar toxin",
  "Jawline / chin / cheek filler",
  "Forehead / temple filler",
  "Nose filler",
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

const TECHNIQUES = ["needle", "cannula"];

const EXPERIENCE_LEVELS = [
  { value: "novice", label: "Novice (<1 year)" },
  { value: "intermediate", label: "Intermediate (1–5 years)" },
  { value: "advanced", label: "Advanced (5+ years)" },
];

const PATIENT_FACTORS = [
  "Prior vascular event",
  "Active infection",
  "Anticoagulation therapy",
  "Smoker",
  "Diabetes",
  "Immunosuppression",
  "Prior filler in area",
  "Keloid tendency",
  "Autoimmune condition",
];

const DEFAULT_FORM: FormState = {
  procedure: "",
  region: "",
  product_type: "",
  technique: "needle",
  injector_experience_level: "intermediate",
  patient_factors: [],
};

// ─── Decision config ────────────────────────────────────────────────────────

function getDecisionConfig(decision: string) {
  switch (decision) {
    case "go":
      return {
        label: "PROCEED",
        icon: CheckCircle2,
        bg: "bg-emerald-500/10 border-emerald-500/30",
        text: "text-emerald-600 dark:text-emerald-400",
        badgeClass: "bg-emerald-500 text-white",
        gaugeColor: "#22c55e",
      };
    case "caution":
      return {
        label: "CAUTION",
        icon: AlertTriangle,
        bg: "bg-amber-500/10 border-amber-500/30",
        text: "text-amber-600 dark:text-amber-400",
        badgeClass: "bg-amber-500 text-white",
        gaugeColor: "#f59e0b",
      };
    case "high_risk":
      return {
        label: "HIGH RISK",
        icon: XCircle,
        bg: "bg-red-500/10 border-red-500/30",
        text: "text-red-600 dark:text-red-400",
        badgeClass: "bg-red-600 text-white",
        gaugeColor: "#ef4444",
      };
    default:
      return {
        label: "UNKNOWN",
        icon: Info,
        bg: "bg-muted/50 border-border",
        text: "text-muted-foreground",
        badgeClass: "bg-muted text-muted-foreground",
        gaugeColor: "#6b7280",
      };
  }
}

function getRiskLevelColor(level: string) {
  switch (level?.toLowerCase()) {
    case "high": return "text-red-600 dark:text-red-400 bg-red-500/10 border-red-500/20";
    case "moderate": return "text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20";
    case "low": return "text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20";
    default: return "text-muted-foreground bg-muted/50 border-border";
  }
}

// ─── Gauge SVG ──────────────────────────────────────────────────────────────

function RiskGauge({ score, color }: { score: number; color: string }) {
  const radius = 52;
  const cx = 64;
  const cy = 64;
  const startAngle = -210;
  const totalArc = 240;
  const pct = Math.min(1, Math.max(0, score / 100));
  const filled = totalArc * pct;

  function polar(angleDeg: number, r: number) {
    const rad = ((angleDeg - 90) * Math.PI) / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }

  function arcPath(startDeg: number, endDeg: number, r: number) {
    const s = polar(startDeg, r);
    const e = polar(endDeg, r);
    const large = Math.abs(endDeg - startDeg) > 180 ? 1 : 0;
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`;
  }

  const trackStart = startAngle;
  const trackEnd = startAngle + totalArc;
  const fillEnd = startAngle + filled;

  return (
    <svg viewBox="0 0 128 128" className="w-40 h-40 mx-auto">
      {/* Track */}
      <path
        d={arcPath(trackStart, trackEnd, radius)}
        fill="none"
        stroke="currentColor"
        strokeOpacity={0.12}
        strokeWidth={10}
        strokeLinecap="round"
      />
      {/* Fill */}
      {score > 0 && (
        <path
          d={arcPath(trackStart, fillEnd, radius)}
          fill="none"
          stroke={color}
          strokeWidth={10}
          strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 6px ${color}80)` }}
        />
      )}
      {/* Score */}
      <text x={cx} y={cy - 4} textAnchor="middle" fontSize={24} fontWeight="700" fill={color}>
        {score}
      </text>
      <text x={cx} y={cy + 13} textAnchor="middle" fontSize={9} fill="currentColor" opacity={0.5}>
        RISK SCORE
      </text>
    </svg>
  );
}

// ─── Select Component ────────────────────────────────────────────────────────

function FieldSelect({
  label, value, onChange, options, placeholder, required
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[] | string[];
  placeholder?: string;
  required?: boolean;
}) {
  const opts = options.map((o) =>
    typeof o === "string" ? { value: o, label: o } : o
  );
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
      >
        <option value="">{placeholder || "Select…"}</option>
        {opts.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function PreProcedureSafetyPage() {
  const [, setLocation] = useLocation();
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PreProcedureResponse | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [evidenceExpanded, setEvidenceExpanded] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);

  function setField<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function togglePatientFactor(factor: string) {
    setForm((f) => ({
      ...f,
      patient_factors: f.patient_factors.includes(factor)
        ? f.patient_factors.filter((x) => x !== factor)
        : [...f.patient_factors, factor],
    }));
  }

  const isFormValid = form.procedure && form.region && form.product_type;

  async function handleSubmit() {
    if (!isFormValid) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const token = getToken();
      const res = await fetch("/api/safety/preprocedure-check", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Safety check failed");
      setResult(data as PreProcedureResponse);
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    } catch (err: any) {
      setError(err.message || "Failed to run safety check. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleExportPDF() {
    if (!isFormValid) return;
    setPdfLoading(true);
    try {
      const token = getToken();
      const res = await fetch("/api/safety/preprocedure-check/export-pdf", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "PDF export failed");
      if (data.filename) {
        window.open(`/exports/${data.filename}`, "_blank");
      }
    } catch (err: any) {
      setError(err.message || "PDF export failed.");
    } finally {
      setPdfLoading(false);
    }
  }

  function handleReset() {
    setForm(DEFAULT_FORM);
    setResult(null);
    setError(null);
  }

  const dc = result ? getDecisionConfig(result.safety_assessment.decision) : null;

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => setLocation("/")} className="gap-2 -ml-2">
              <ArrowLeft className="w-4 h-4" />
              <span className="hidden sm:inline">Back</span>
            </Button>
            <div className="w-px h-5 bg-border" />
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
                <Shield className="w-4 h-4 text-primary" />
              </div>
              <div>
                <span className="font-semibold text-sm">Pre-Procedure Safety Check</span>
                <span className="hidden sm:inline text-xs text-muted-foreground ml-2">AesthetiCite Clinical Safety Engine</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {result && (
              <Button variant="outline" size="sm" onClick={handleReset} className="gap-1.5">
                <RotateCcw className="w-3.5 h-3.5" />
                New Check
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={handleExportPDF}
              disabled={pdfLoading || !result}
              className="gap-1.5"
            >
              {pdfLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileDown className="w-3.5 h-3.5" />}
              Export PDF
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">

        {/* Form card */}
        <Card className="border">
          <CardHeader className="pb-4">
            <CardTitle className="text-base flex items-center gap-2">
              <Activity className="w-4 h-4 text-primary" />
              Procedure Parameters
            </CardTitle>
            <p className="text-xs text-muted-foreground mt-1">
              Enter procedure details to receive a structured safety assessment with risk scoring and mitigation guidance.
            </p>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* Row 1: Procedure + Region */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FieldSelect
                label="Procedure"
                value={form.procedure}
                onChange={(v) => setField("procedure", v)}
                options={PROCEDURES}
                placeholder="Select procedure"
                required
              />
              <FieldSelect
                label="Region"
                value={form.region}
                onChange={(v) => setField("region", v)}
                options={REGIONS}
                placeholder="Select region"
                required
              />
            </div>

            {/* Row 2: Product + Technique + Experience */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <FieldSelect
                label="Product Type"
                value={form.product_type}
                onChange={(v) => setField("product_type", v)}
                options={PRODUCT_TYPES}
                placeholder="Select product"
                required
              />
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Technique</label>
                <div className="flex gap-2">
                  {TECHNIQUES.map((t) => (
                    <button
                      key={t}
                      onClick={() => setField("technique", t)}
                      className={`flex-1 py-2 rounded-lg border text-sm font-medium capitalize transition-all ${
                        form.technique === t
                          ? "bg-primary text-primary-foreground border-primary"
                          : "border-border hover:border-primary/50 hover:bg-muted/50"
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <FieldSelect
                label="Injector Experience"
                value={form.injector_experience_level}
                onChange={(v) => setField("injector_experience_level", v)}
                options={EXPERIENCE_LEVELS}
                placeholder="Select level"
              />
            </div>

            {/* Patient factors */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Patient Risk Factors
                {form.patient_factors.length > 0 && (
                  <span className="ml-2 text-primary normal-case font-normal">
                    {form.patient_factors.length} selected
                  </span>
                )}
              </label>
              <div className="flex flex-wrap gap-2">
                {PATIENT_FACTORS.map((f) => {
                  const active = form.patient_factors.includes(f);
                  return (
                    <button
                      key={f}
                      onClick={() => togglePatientFactor(f)}
                      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium transition-all ${
                        active
                          ? "bg-amber-500/15 border-amber-500/40 text-amber-700 dark:text-amber-300"
                          : "border-border hover:border-primary/40 hover:bg-muted/50 text-muted-foreground"
                      }`}
                    >
                      {active ? <Minus className="w-3 h-3" /> : <Plus className="w-3 h-3" />}
                      {f}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Submit */}
            <div className="flex items-center gap-3 pt-1">
              <Button
                onClick={handleSubmit}
                disabled={!isFormValid || loading}
                className="gap-2 shadow-lg shadow-primary/20 px-6"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Analysing…
                  </>
                ) : (
                  <>
                    <Zap className="w-4 h-4" />
                    Run Safety Check
                  </>
                )}
              </Button>
              {!isFormValid && (
                <p className="text-xs text-muted-foreground">
                  Select procedure, region, and product type to continue
                </p>
              )}
            </div>

            {error && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-sm text-destructive">
                <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                {error}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Results */}
        {result && dc && (
          <div ref={resultsRef} className="space-y-4">

            {/* Decision banner */}
            <div className={`rounded-xl border p-5 ${dc.bg}`}>
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-5">
                {/* Gauge */}
                <div className="flex-shrink-0">
                  <RiskGauge score={result.safety_assessment.overall_risk_score} color={dc.gaugeColor} />
                </div>

                <div className="flex-1 min-w-0 space-y-2">
                  {/* Decision badge */}
                  <div className="flex items-center gap-3">
                    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-bold tracking-wide ${dc.badgeClass}`}>
                      <dc.icon className="w-4 h-4" />
                      {dc.label}
                    </span>
                    <span className="text-sm text-muted-foreground capitalize">
                      {result.safety_assessment.overall_risk_level} risk
                    </span>
                  </div>

                  {/* Rationale */}
                  <p className={`text-sm leading-relaxed ${dc.text}`}>
                    {result.safety_assessment.rationale}
                  </p>

                  {/* Meta */}
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground pt-1">
                    <span>Engine v{result.engine_version}</span>
                    <span>·</span>
                    <span>Request: {result.request_id.slice(0, 12)}…</span>
                    <span>·</span>
                    <span>{new Date(result.generated_at_utc).toLocaleString()}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Caution flags */}
            {result.caution_flags.length > 0 && (
              <Card className="border-amber-500/30 bg-amber-500/5">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle className="w-4 h-4 text-amber-500" />
                    <span className="text-sm font-semibold text-amber-700 dark:text-amber-300">Caution Flags</span>
                  </div>
                  <ul className="space-y-1.5">
                    {result.caution_flags.map((flag, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-amber-800 dark:text-amber-200">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-1.5 flex-shrink-0" />
                        {flag}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            {/* Top risks + Danger zones row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

              {/* Top Risks */}
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-4">
                    <Activity className="w-4 h-4 text-primary" />
                    <span className="text-sm font-semibold">Top Complication Risks</span>
                  </div>
                  <div className="space-y-3">
                    {result.top_risks.map((risk, i) => (
                      <div key={i} className="space-y-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium capitalize">{risk.complication}</span>
                          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${getRiskLevelColor(risk.risk_level)}`}>
                            {risk.risk_score}/100
                          </span>
                        </div>
                        {/* Score bar */}
                        <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-700"
                            style={{
                              width: `${risk.risk_score}%`,
                              backgroundColor:
                                risk.risk_level === "high" ? "#ef4444" :
                                risk.risk_level === "moderate" ? "#f59e0b" : "#22c55e",
                            }}
                          />
                        </div>
                        <p className="text-xs text-muted-foreground">{risk.why_it_matters}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Danger Zones + Procedure Insight */}
              <Card>
                <CardContent className="p-4 space-y-4">
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <MapPin className="w-4 h-4 text-red-500" />
                      <span className="text-sm font-semibold">Danger Zones</span>
                    </div>
                    {result.procedure_insight.danger_zones.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {result.procedure_insight.danger_zones.map((zone, i) => (
                          <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-red-500/10 border border-red-500/20 text-xs text-red-700 dark:text-red-300 font-medium">
                            ⚠ {zone}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">No specific danger zones flagged for this configuration.</p>
                    )}
                  </div>

                  {result.procedure_insight.likely_plane_or_target && (
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <Lightbulb className="w-4 h-4 text-blue-500" />
                        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Injection Plane / Target</span>
                      </div>
                      <p className="text-sm text-foreground/80">{result.procedure_insight.likely_plane_or_target}</p>
                    </div>
                  )}

                  {result.procedure_insight.technical_notes.length > 0 && (
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <Info className="w-4 h-4 text-muted-foreground" />
                        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Technique Notes</span>
                      </div>
                      <ul className="space-y-1">
                        {result.procedure_insight.technical_notes.map((note, i) => (
                          <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                            <span className="mt-1 w-1 h-1 rounded-full bg-muted-foreground flex-shrink-0" />
                            {note}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Mitigation Steps */}
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-3">
                  <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                  <span className="text-sm font-semibold">Mitigation Steps</span>
                </div>
                <ol className="space-y-2">
                  {result.mitigation_steps.map((step, i) => (
                    <li key={i} className="flex items-start gap-3 text-sm">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">
                        {i + 1}
                      </span>
                      <span className="text-foreground/85">{step}</span>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>

            {/* Evidence */}
            <Card>
              <CardContent className="p-4">
                <button
                  onClick={() => setEvidenceExpanded(!evidenceExpanded)}
                  className="w-full flex items-center justify-between gap-2 text-left"
                >
                  <div className="flex items-center gap-2">
                    <BookOpen className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm font-semibold">Evidence ({result.evidence.length} sources)</span>
                  </div>
                  {evidenceExpanded ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                </button>

                {evidenceExpanded && (
                  <div className="mt-4 space-y-3">
                    {result.evidence.map((ev, i) => (
                      <div key={i} className="p-3 rounded-lg bg-muted/40 border border-border/50 space-y-1">
                        <div className="flex items-start justify-between gap-2">
                          <span className="text-xs font-semibold text-primary">[{ev.source_id}]</span>
                          {ev.url && (
                            <a href={ev.url} target="_blank" rel="noreferrer"
                              className="text-xs text-primary hover:underline flex-shrink-0">
                              View source ↗
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
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Disclaimer */}
            <p className="text-xs text-muted-foreground/60 text-center leading-relaxed px-4 pb-2">
              <Shield className="w-3 h-3 inline-block mr-1" />
              {result.disclaimer}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
