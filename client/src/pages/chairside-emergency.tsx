import { useMemo, useState } from "react";
import { useLocation } from "wouter";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Eye,
  FileDown,
  ShieldAlert,
  Syringe,
  Thermometer,
  PhoneCall,
  ArrowLeft,
  Loader2,
  XCircle,
  Zap,
} from "lucide-react";
import { getToken } from "@/lib/auth";

// ─── Types (mirrors real ProtocolResponse from complication engine) ──────────

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

interface EvidenceItem {
  source_id: string;
  title: string;
  note: string;
  citation_text?: string;
  url?: string;
}

interface RiskAssessment {
  risk_score: number;
  severity: "low" | "moderate" | "high" | "critical";
  urgency: "routine" | "same_day" | "urgent" | "immediate";
  likely_time_critical: boolean;
  evidence_strength: string;
}

interface ProtocolResponse {
  request_id: string;
  engine_version: string;
  matched_protocol_name: string;
  confidence: number;
  risk_assessment: RiskAssessment;
  clinical_summary: string;
  immediate_actions: ProtocolStep[];
  dose_guidance: DoseGuidance[];
  escalation: string[];
  monitoring: string[];
  red_flags: string[];
  follow_up_questions: string[];
  limitations: string[];
  evidence: EvidenceItem[];
  disclaimer: string;
}

// ─── Urgency mapping ─────────────────────────────────────────────────────────

type UrgencyLabel = "Emergency" | "High" | "Moderate" | "Low";

function toUrgencyLabel(urgency: string, severity: string): UrgencyLabel {
  if (urgency === "immediate" || severity === "critical") return "Emergency";
  if (urgency === "urgent" || severity === "high") return "High";
  if (urgency === "same_day" || severity === "moderate") return "Moderate";
  return "Low";
}

function badgeClass(level: UrgencyLabel) {
  if (level === "Emergency") return "bg-red-50 text-red-700 ring-red-200 dark:bg-red-900/30 dark:text-red-300 dark:ring-red-800";
  if (level === "High")      return "bg-orange-50 text-orange-700 ring-orange-200 dark:bg-orange-900/30 dark:text-orange-300";
  if (level === "Moderate")  return "bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-900/30 dark:text-amber-300";
  return "bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300";
}

// ─── Section component ────────────────────────────────────────────────────────

function Section({
  title,
  icon,
  items,
  accent = "default",
}: {
  title: string;
  icon: React.ReactNode;
  items: string[];
  accent?: "default" | "danger";
}) {
  if (!items.length) return null;
  return (
    <div className="rounded-3xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-3">
        <div
          className={`rounded-2xl p-2 ${
            accent === "danger"
              ? "bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400"
              : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300"
          }`}
        >
          {icon}
        </div>
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
      </div>
      <ul className="space-y-3">
        {items.map((item, i) => (
          <li key={i} className="flex gap-3 text-sm leading-6 text-slate-700 dark:text-slate-300">
            {accent === "danger" ? (
              <AlertTriangle className="mt-1 h-4 w-4 shrink-0 text-red-500" />
            ) : (
              <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" />
            )}
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ─── Toggle chip ─────────────────────────────────────────────────────────────

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`flex items-center justify-between rounded-2xl border px-4 py-3 text-sm font-medium transition-all ${
        checked
          ? "border-slate-900 dark:border-slate-200 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900"
          : "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
      }`}
    >
      <span>{label}</span>
      <span
        className={`ml-3 rounded-full px-2 py-0.5 text-xs ${
          checked
            ? "bg-white/15 text-white dark:bg-black/20 dark:text-slate-900"
            : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400"
        }`}
      >
        {checked ? "Yes" : "No"}
      </span>
    </button>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function ChairsideEmergencyPage() {
  const [, setLocation] = useLocation();

  const [procedure, setProcedure] = useState("HA filler");
  const [product, setProduct] = useState("Juvederm Voluma");
  const [region, setRegion] = useState("Nasolabial fold");
  const [timeFromInjection, setTimeFromInjection] = useState("2 minutes");
  const [blanching, setBlanching] = useState(true);
  const [severePain, setSeverePain] = useState(true);
  const [livedo, setLivedo] = useState(true);
  const [visualSymptoms, setVisualSymptoms] = useState(false);
  const [duskySkin, setDuskySkin] = useState(false);
  const [coldSkin, setColdSkin] = useState(true);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProtocolResponse | null>(null);

  const triageLabel = useMemo(() => {
    if (visualSymptoms) return "VISION EMERGENCY";
    if (blanching && severePain) return "PROBABLE VASCULAR COMPROMISE";
    if (livedo || duskySkin) return "HIGH-RISK TISSUE ISCHEMIA";
    return "REQUIRES ASSESSMENT";
  }, [visualSymptoms, blanching, severePain, livedo, duskySkin]);

  const activeSymptoms = useMemo(() => {
    const s: string[] = [];
    if (blanching)      s.push("blanching");
    if (severePain)     s.push("severe pain");
    if (livedo)         s.push("livedo");
    if (visualSymptoms) s.push("visual symptoms");
    if (duskySkin)      s.push("dusky skin");
    if (coldSkin)       s.push("cold skin");
    return s;
  }, [blanching, severePain, livedo, visualSymptoms, duskySkin, coldSkin]);

  const urgencyLabel = result
    ? toUrgencyLabel(result.risk_assessment.urgency, result.risk_assessment.severity)
    : null;

  const immediateActionTexts = result?.immediate_actions.map((s) => s.action) ?? [];
  const treatmentTexts = result?.dose_guidance.map(
    (d) => `${d.substance}: ${d.recommendation}${d.notes ? ` — ${d.notes}` : ""}`
  ) ?? [];
  const citationsForDisplay = result?.evidence.map((e) => ({
    id: e.source_id,
    title: e.title,
    locator: e.citation_text ? undefined : undefined,
    snippet: e.note,
    url: e.url,
  })) ?? [];

  const reportLines = useMemo(() => {
    if (!result) return "";
    return [
      "AesthetiCite Chairside Emergency Report",
      "",
      `Procedure: ${procedure}`,
      `Product: ${product}`,
      `Region: ${region}`,
      `Time from injection: ${timeFromInjection}`,
      `Blanching: ${blanching ? "Yes" : "No"}`,
      `Severe pain: ${severePain ? "Yes" : "No"}`,
      `Livedo: ${livedo ? "Yes" : "No"}`,
      `Visual symptoms: ${visualSymptoms ? "Yes" : "No"}`,
      `Dusky skin: ${duskySkin ? "Yes" : "No"}`,
      `Cold skin: ${coldSkin ? "Yes" : "No"}`,
      "",
      `Triage: ${triageLabel}`,
      `Protocol: ${result.matched_protocol_name}`,
      `Urgency: ${urgencyLabel}`,
      `Confidence: ${Math.round(result.confidence * 100)}%`,
      "",
      "Immediate Actions",
      ...immediateActionTexts.map((x) => `• ${x}`),
      "",
      "Treatment / Dose Guidance",
      ...treatmentTexts.map((x) => `• ${x}`),
      "",
      "Escalation",
      ...result.escalation.map((x) => `• ${x}`),
      "",
      "Monitoring",
      ...result.monitoring.map((x) => `• ${x}`),
      "",
      "Red Flags",
      ...result.red_flags.map((x) => `• ${x}`),
      "",
      "Summary",
      result.clinical_summary,
      "",
      result.disclaimer,
    ].join("\n");
  }, [
    result, procedure, product, region, timeFromInjection,
    blanching, severePain, livedo, visualSymptoms, duskySkin, coldSkin,
    triageLabel, urgencyLabel, immediateActionTexts, treatmentTexts,
  ]);

  async function runEmergencyMode() {
    if (!procedure.trim() && !region.trim() && activeSymptoms.length === 0) return;
    setLoading(true);
    setError(null);
    setResult(null);

    const symptomList = activeSymptoms.length > 0 ? activeSymptoms.join(", ") : "clinical concern";
    const query = `${symptomList} after ${procedure || "injection"} to ${region || "treatment area"}, ${timeFromInjection} after injection`;

    try {
      const token = getToken();
      const res = await fetch("/api/complications/protocol", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          query,
          context: {
            procedure,
            product_type: product,
            region,
            symptoms: activeSymptoms,
            visual_symptoms: visualSymptoms,
            capillary_refill_delayed: blanching,
            filler_confirmed_ha: true,
          },
          mode: "emergency",
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Protocol lookup failed");
      setResult(data as ProtocolResponse);
    } catch (err: any) {
      setError(err.message || "Failed to generate protocol. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function exportReport() {
    const blob = new Blob([reportLines], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "aestheticite-chairside-emergency-report.txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 p-4 md:p-6">
      <div className="mx-auto max-w-7xl">

        {/* Header */}
        <div className="mb-6 rounded-[32px] border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="mb-3 flex items-center gap-3">
                <button
                  onClick={() => setLocation("/")}
                  className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                  Back
                </button>
              </div>
              <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-red-50 dark:bg-red-900/30 px-3 py-1 text-xs font-semibold text-red-700 dark:text-red-400 ring-1 ring-red-200 dark:ring-red-800">
                <ShieldAlert className="h-4 w-4" />
                Open during injections
              </div>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
                Chairside Emergency Mode
              </h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-400">
                Ultra-fast triage, immediate protocol, escalation guidance, and exportable documentation on one screen — open this during injections.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {[
                { label: "Mode", value: "Chairside" },
                { label: "Focus", value: "Emergency triage" },
                { label: "Evidence", value: "Grounded" },
                { label: "Use case", value: "During injection" },
              ].map((item) => (
                <div key={item.label} className="rounded-2xl border border-slate-200 dark:border-slate-700 p-4">
                  <div className="text-xs text-slate-500 dark:text-slate-400">{item.label}</div>
                  <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{item.value}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">

          {/* ── LEFT: Inputs ──────────────────────────────────────────────── */}
          <div className="space-y-6">
            <div className="rounded-[32px] border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm">
              <div className="mb-4 flex items-center gap-2">
                <Syringe className="h-5 w-5 text-slate-700 dark:text-slate-300" />
                <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Fast chairside inputs</h2>
              </div>
              <div className="space-y-3">
                <input
                  className="w-full rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-3 text-sm text-slate-900 dark:text-slate-100 outline-none placeholder:text-slate-400 focus:border-slate-400 dark:focus:border-slate-500"
                  value={procedure}
                  onChange={(e) => setProcedure(e.target.value)}
                  placeholder="Procedure (e.g. HA filler)"
                />
                <input
                  className="w-full rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-3 text-sm text-slate-900 dark:text-slate-100 outline-none placeholder:text-slate-400 focus:border-slate-400 dark:focus:border-slate-500"
                  value={product}
                  onChange={(e) => setProduct(e.target.value)}
                  placeholder="Product (e.g. Juvederm Voluma)"
                />
                <input
                  className="w-full rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-3 text-sm text-slate-900 dark:text-slate-100 outline-none placeholder:text-slate-400 focus:border-slate-400 dark:focus:border-slate-500"
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  placeholder="Region (e.g. Nasolabial fold)"
                />
                <input
                  className="w-full rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-3 text-sm text-slate-900 dark:text-slate-100 outline-none placeholder:text-slate-400 focus:border-slate-400 dark:focus:border-slate-500"
                  value={timeFromInjection}
                  onChange={(e) => setTimeFromInjection(e.target.value)}
                  placeholder="Time since injection (e.g. 2 minutes)"
                />
              </div>
            </div>

            <div className="rounded-[32px] border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm">
              <div className="mb-4 flex items-center gap-2">
                <Thermometer className="h-5 w-5 text-slate-700 dark:text-slate-300" />
                <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Presenting symptoms</h2>
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
                <Toggle checked={blanching}      onChange={setBlanching}      label="Blanching / mottling" />
                <Toggle checked={severePain}     onChange={setSeverePain}     label="Severe pain" />
                <Toggle checked={livedo}         onChange={setLivedo}         label="Livedo reticularis" />
                <Toggle checked={visualSymptoms} onChange={setVisualSymptoms} label="Visual symptoms" />
                <Toggle checked={duskySkin}      onChange={setDuskySkin}      label="Dusky / dark skin" />
                <Toggle checked={coldSkin}       onChange={setColdSkin}       label="Cold skin" />
              </div>
            </div>

            {/* Triage panel */}
            <div className={`rounded-[32px] border p-5 shadow-sm ${
              visualSymptoms || (blanching && severePain)
                ? "border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20"
                : livedo || duskySkin
                ? "border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-900/20"
                : "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900"
            }`}>
              <div className="flex items-center gap-2 mb-2">
                <PhoneCall className={`h-5 w-5 ${
                  visualSymptoms || (blanching && severePain) ? "text-red-600 dark:text-red-400" : "text-slate-500 dark:text-slate-400"
                }`} />
                <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Triage</span>
              </div>
              <p className={`text-lg font-bold ${
                visualSymptoms ? "text-red-700 dark:text-red-400 animate-pulse"
                : blanching && severePain ? "text-red-600 dark:text-red-400"
                : livedo || duskySkin ? "text-orange-600 dark:text-orange-400"
                : "text-slate-700 dark:text-slate-300"
              }`}>
                {triageLabel}
              </p>
            </div>

            {/* Action button */}
            <button
              onClick={runEmergencyMode}
              disabled={loading}
              className="w-full rounded-2xl bg-slate-900 dark:bg-slate-100 px-6 py-4 text-sm font-semibold text-white dark:text-slate-900 shadow-lg transition-all hover:bg-slate-800 dark:hover:bg-white disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading
                ? <><Loader2 className="h-4 w-4 animate-spin" /> Generating protocol…</>
                : <><Zap className="h-4 w-4" /> Get Emergency Protocol</>
              }
            </button>

            {error && (
              <div className="flex items-start gap-2 rounded-2xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-700 dark:text-red-400">
                <XCircle className="h-4 w-4 mt-0.5 shrink-0" />
                {error}
              </div>
            )}

            {result && (
              <button
                onClick={exportReport}
                className="w-full flex items-center justify-center gap-2 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-3 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all shadow-sm"
              >
                <FileDown className="h-4 w-4" />
                Export chairside report (.txt)
              </button>
            )}
          </div>

          {/* ── RIGHT: Results ────────────────────────────────────────────── */}
          <div className="space-y-6">
            {!result && !loading && !error && (
              <div className="rounded-[32px] border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-12 shadow-sm flex flex-col items-center justify-center text-center gap-4">
                <div className="w-16 h-16 rounded-3xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
                  <ShieldAlert className="h-8 w-8 text-slate-400 dark:text-slate-500" />
                </div>
                <div>
                  <p className="text-base font-semibold text-slate-900 dark:text-slate-100">Ready for emergency triage</p>
                  <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                    Enter the presenting symptoms and click "Get Emergency Protocol"
                  </p>
                </div>
              </div>
            )}

            {result && urgencyLabel && (
              <>
                {/* Protocol header */}
                <div className="rounded-[32px] border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
                  <div className="flex flex-wrap items-center gap-3 mb-4">
                    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ring-1 ${badgeClass(urgencyLabel)}`}>
                      {urgencyLabel === "Emergency" && <span className="animate-pulse">●</span>}
                      {urgencyLabel}
                    </span>
                    {result.risk_assessment.likely_time_critical && (
                      <span className="text-xs font-bold text-red-600 dark:text-red-400 animate-pulse">
                        ⏱ TIME CRITICAL
                      </span>
                    )}
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      Confidence: {Math.round(result.confidence * 100)}%
                    </span>
                  </div>
                  <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100 mb-3">
                    {result.matched_protocol_name}
                  </h2>
                  <p className="text-sm leading-7 text-slate-600 dark:text-slate-400">
                    {result.clinical_summary}
                  </p>
                </div>

                {/* Red flags always at the top */}
                {result.red_flags.length > 0 && (
                  <div className="rounded-[32px] border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-5 shadow-sm">
                    <div className="flex items-center gap-2 mb-3">
                      <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400" />
                      <span className="text-sm font-bold text-red-700 dark:text-red-400">Red Flags — escalate if present</span>
                    </div>
                    <ul className="space-y-2">
                      {result.red_flags.map((flag, i) => (
                        <li key={i} className="flex gap-2 text-sm text-red-700 dark:text-red-400">
                          <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                          {flag}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <Section
                  title="Immediate Actions"
                  icon={<Syringe className="h-5 w-5" />}
                  items={immediateActionTexts}
                  accent="default"
                />

                <Section
                  title="Treatment / Dose Guidance"
                  icon={<CheckCircle2 className="h-5 w-5" />}
                  items={treatmentTexts}
                />

                <Section
                  title="Escalation"
                  icon={<PhoneCall className="h-5 w-5" />}
                  items={result.escalation}
                  accent="danger"
                />

                <Section
                  title="Monitoring"
                  icon={<Eye className="h-5 w-5" />}
                  items={result.monitoring}
                />

                {/* Report preview */}
                <div className="rounded-[32px] border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
                  <div className="mb-4 flex items-center gap-2">
                    <FileDown className="h-5 w-5 text-slate-700 dark:text-slate-300" />
                    <h3 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Chairside report preview</h3>
                  </div>
                  <div className="rounded-3xl bg-slate-50 dark:bg-slate-800 p-4 ring-1 ring-slate-200 dark:ring-slate-700">
                    <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-xs leading-6 text-slate-700 dark:text-slate-300">
                      {reportLines}
                    </pre>
                  </div>
                </div>

                {/* Grounded evidence */}
                {citationsForDisplay.length > 0 && (
                  <div className="rounded-[32px] border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
                    <div className="mb-4 text-xl font-semibold text-slate-900 dark:text-slate-100">Grounded evidence</div>
                    <div className="mb-4 rounded-2xl bg-emerald-50 dark:bg-emerald-900/20 px-4 py-3 text-xs font-semibold text-emerald-700 dark:text-emerald-400 ring-1 ring-emerald-200 dark:ring-emerald-800">
                      All citations retrieved from AesthetiCite's validated evidence base.
                    </div>
                    <div className="space-y-4">
                      {citationsForDisplay.map((c) => (
                        <div key={c.id} className="rounded-3xl border border-slate-200 dark:border-slate-700 p-4">
                          <div className="flex items-start justify-between gap-2">
                            <div className="text-xs font-bold text-slate-500 dark:text-slate-400">[{c.id}]</div>
                            {(c as any).url && (
                              <a href={(c as any).url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">
                                View ↗
                              </a>
                            )}
                          </div>
                          <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{c.title}</div>
                          {c.snippet && (
                            <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-400">{c.snippet}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Disclaimer */}
                <p className="text-xs text-slate-400 dark:text-slate-500 text-center leading-relaxed px-4 pb-2">
                  {result.disclaimer}
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
