import { useState, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertTriangle, Shield, Zap, BookOpen, FileText, Copy,
  Printer, CheckCircle2, XCircle, ChevronRight, Activity,
  Stethoscope, Syringe, Clock, AlertCircle, TrendingUp,
  Download, RefreshCw, Info,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { getToken } from "@/lib/auth";

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

async function api<T>(path: string, body: unknown): Promise<T> {
  const token = getToken();
  const res = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Complication options (quick-select)
// ---------------------------------------------------------------------------

const COMPLICATIONS = [
  { id: "vascular occlusion", label: "Vascular Occlusion", icon: "🚨", urgent: true },
  { id: "anaphylaxis", label: "Anaphylaxis", icon: "🆘", urgent: true },
  { id: "skin necrosis", label: "Necrosis", icon: "⚠️", urgent: true },
  { id: "ptosis eyelid drooping", label: "Ptosis", icon: "👁️", urgent: false },
  { id: "nodule lump post filler", label: "Nodule", icon: "🔵", urgent: false },
  { id: "infection biofilm", label: "Infection", icon: "🦠", urgent: false },
  { id: "tyndall effect blue filler", label: "Tyndall Effect", icon: "💙", urgent: false },
  { id: "delayed inflammatory reaction", label: "DIR", icon: "🔴", urgent: false },
];

const SYMPTOM_CHIPS = [
  "Blanching", "Livedo reticularis", "Pain", "Visual changes",
  "Swelling", "Erythema", "Fever", "Nodule", "Skin discolouration",
  "Oedema", "Asymmetry",
];

// ---------------------------------------------------------------------------
// Evidence badge
// ---------------------------------------------------------------------------

const EVIDENCE_BADGE_STYLES: Record<string, string> = {
  "🟢 Guideline-based": "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300 border-emerald-300",
  "🔵 Consensus":       "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 border-blue-300",
  "🟡 Review":          "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 border-amber-300",
  "🟡 RCT":             "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 border-amber-300",
  "⚪ Limited":         "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-300",
};

function EvidenceBadge({ label }: { label: string }) {
  const cls = EVIDENCE_BADGE_STYLES[label] ?? EVIDENCE_BADGE_STYLES["⚪ Limited"];
  return (
    <Badge variant="outline" className={`text-xs px-2 py-0.5 ${cls}`}>
      {label}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Risk level colours
// ---------------------------------------------------------------------------

const RISK_COLORS = {
  critical: "text-red-600 dark:text-red-400",
  high:     "text-orange-600 dark:text-orange-400",
  moderate: "text-amber-600 dark:text-amber-400",
  low:      "text-emerald-600 dark:text-emerald-400",
  unknown:  "text-muted-foreground",
};

const CONFIDENCE_COLORS = {
  high:   "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  low:    "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
};

// ---------------------------------------------------------------------------
// Section wrapper
// ---------------------------------------------------------------------------

function Section({
  number, title, icon: Icon, children, urgent = false,
}: {
  number: string; title: string; icon: React.ElementType;
  children: React.ReactNode; urgent?: boolean;
}) {
  return (
    <Card className={urgent ? "border-red-300 dark:border-red-800" : ""}>
      <CardHeader className="pb-2 pt-3 px-4">
        <CardTitle className={`text-sm flex items-center gap-2 ${urgent ? "text-red-600 dark:text-red-400" : ""}`}>
          <span className="text-muted-foreground font-normal text-xs">{number}</span>
          <Icon className="h-4 w-4" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4">{children}</CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Workflow step
// ---------------------------------------------------------------------------

function WorkflowStep({
  step, onComplete, completed,
}: {
  step: { step: number; action: string; critical: boolean; detail: string };
  onComplete: () => void;
  completed: boolean;
}) {
  return (
    <div
      className={`flex items-start gap-3 p-3 rounded-lg border transition-all cursor-pointer ${
        completed
          ? "border-emerald-300 bg-emerald-50 dark:bg-emerald-950/20 dark:border-emerald-800"
          : step.critical
          ? "border-red-200 dark:border-red-900 bg-red-50/50 dark:bg-red-950/10"
          : "border-border hover:border-muted-foreground/50"
      }`}
      onClick={onComplete}
    >
      <div className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold mt-0.5 ${
        completed
          ? "bg-emerald-500 text-white"
          : step.critical
          ? "bg-red-500 text-white"
          : "bg-muted text-muted-foreground"
      }`}>
        {completed ? <CheckCircle2 className="h-4 w-4" /> : step.step}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <p className={`text-sm font-medium leading-snug ${
            completed ? "line-through text-muted-foreground" : step.critical ? "text-red-700 dark:text-red-300" : ""
          }`}>
            {step.action}
          </p>
          {step.critical && !completed && (
            <Badge variant="destructive" className="text-[10px] px-1.5 flex-shrink-0">NOW</Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{step.detail}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Report modal
// ---------------------------------------------------------------------------

function ReportPanel({
  result, onClose,
}: {
  result: any; onClose: () => void;
}) {
  const { toast } = useToast();
  const [form, setForm] = useState({
    procedure: "", region: "", product: "", event_date: "",
    practitioner: "", onset: "", symptoms: "", treatment: "",
    outcome: "", timeline: "", notes: "", escalation: "", referral: "",
    complication_type: result?.workflow_key?.replace(/_/g, " ") ?? "",
    actions_taken: (result?.workflow ?? []).filter((s: any) => s.completed).map((s: any) => s.action),
  });
  const [loading, setLoading] = useState(false);

  const generatePDF = async () => {
    setLoading(true);
    try {
      const token = getToken();
      const res = await fetch("/api/decide/report", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ ...form, format: "pdf" }),
      });
      if (!res.ok) throw new Error("Report failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "aestheticite-incident-report.pdf";
      a.click();
      toast({ title: "Report downloaded" });
    } catch (e: any) {
      toast({ title: "Error", description: e.message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const copyText = () => {
    const text = [
      `PROCEDURE: ${form.procedure}`,
      `COMPLICATION: ${form.complication_type}`,
      `SYMPTOMS: ${form.symptoms}`,
      `TREATMENT: ${form.treatment}`,
      `OUTCOME: ${form.outcome}`,
      `NOTES: ${form.notes}`,
    ].join("\n");
    navigator.clipboard.writeText(text);
    toast({ title: "Copied to clipboard" });
  };

  const fields: { key: keyof typeof form; label: string; placeholder?: string }[] = [
    { key: "procedure", label: "Procedure", placeholder: "e.g. Lip filler 1ml" },
    { key: "region", label: "Region", placeholder: "e.g. Lips" },
    { key: "product", label: "Product", placeholder: "e.g. Juvederm Ultra" },
    { key: "event_date", label: "Date/Time", placeholder: "e.g. 19 March 2026, 14:30" },
    { key: "practitioner", label: "Practitioner", placeholder: "Dr. Name" },
    { key: "complication_type", label: "Complication Type" },
    { key: "onset", label: "Onset", placeholder: "e.g. Immediate, 2 minutes post-injection" },
    { key: "symptoms", label: "Symptoms", placeholder: "e.g. Blanching, pain, livedo" },
    { key: "treatment", label: "Treatment Given", placeholder: "e.g. Hyaluronidase 1500 IU IM" },
    { key: "outcome", label: "Outcome", placeholder: "e.g. Resolved at 90 min" },
    { key: "timeline", label: "Timeline", placeholder: "e.g. Full resolution at 2h" },
    { key: "escalation", label: "Escalation", placeholder: "e.g. No escalation required" },
    { key: "referral", label: "Referral", placeholder: "e.g. None / Ophthalmology" },
    { key: "notes", label: "Additional Notes", placeholder: "Free text" },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <div className="bg-background rounded-xl border shadow-2xl w-full max-w-xl max-h-[85vh] overflow-y-auto">
        <div className="sticky top-0 bg-background border-b p-4 flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-sm">Medico-Legal Incident Report</h2>
            <p className="text-xs text-muted-foreground">Complete the fields and export PDF</p>
          </div>
          <Button size="sm" variant="ghost" onClick={onClose}>✕</Button>
        </div>
        <div className="p-4 space-y-3">
          {fields.map(({ key, label, placeholder }) => (
            <div key={key}>
              <label className="text-xs font-medium text-muted-foreground">{label}</label>
              <input
                className="mt-0.5 w-full h-8 px-3 text-sm border rounded-md bg-background focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder={placeholder ?? label}
                value={String(form[key] ?? "")}
                onChange={(e) => setForm((p) => ({ ...p, [key]: e.target.value }))}
              />
            </div>
          ))}
        </div>
        <div className="sticky bottom-0 bg-background border-t p-4 flex gap-2">
          <Button size="sm" onClick={generatePDF} disabled={loading} className="flex-1">
            <Download className="h-3.5 w-3.5 mr-1.5" />
            {loading ? "Generating…" : "Export PDF"}
          </Button>
          <Button size="sm" variant="outline" onClick={copyText}>
            <Copy className="h-3.5 w-3.5 mr-1.5" /> Copy
          </Button>
          <Button size="sm" variant="outline" onClick={() => window.print()}>
            <Printer className="h-3.5 w-3.5 mr-1.5" /> Print
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ComplicationDecisionPage() {
  const { toast } = useToast();
  const [selected, setSelected] = useState<string | null>(null);
  const [customQuery, setCustomQuery] = useState("");
  const [symptoms, setSymptoms] = useState<string[]>([]);
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());
  const [showReport, setShowReport] = useState(false);
  const [result, setResult] = useState<any>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  const mutation = useMutation({
    mutationFn: (query: string) =>
      api<any>("/api/decide", {
        query,
        symptoms,
        include_similar_cases: true,
      }),
    onSuccess: (data) => {
      setResult(data);
      setCompletedSteps(new Set());
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const handleSubmit = () => {
    const q = selected ?? customQuery;
    if (!q.trim()) return;
    mutation.mutate(q.trim());
  };

  const toggleSymptom = (s: string) =>
    setSymptoms((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    );

  const toggleStep = (stepNum: number) =>
    setCompletedSteps((prev) => {
      const next = new Set(prev);
      next.has(stepNum) ? next.delete(stepNum) : next.add(stepNum);
      return next;
    });

  const completedCount = completedSteps.size;
  const totalSteps = result?.workflow?.length ?? 0;
  const progressPct = totalSteps > 0 ? Math.round((completedCount / totalSteps) * 100) : 0;

  const safetyRisk = result?.safety?.risk_level ?? "unknown";
  const riskColor = RISK_COLORS[safetyRisk as keyof typeof RISK_COLORS] ?? RISK_COLORS.unknown;

  return (
    <div className="min-h-screen bg-background">
      {/* Sticky header */}
      <div className="border-b bg-background/95 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-blue-500 flex-shrink-0" />
            <span className="font-semibold text-sm">AesthetiCite</span>
            <span className="text-muted-foreground text-xs hidden sm:inline">· Clinical Decision</span>
          </div>
          {result && (
            <div className="flex items-center gap-2">
              {result.safety?.call_emergency && (
                <Badge variant="destructive" className="text-xs animate-pulse">
                  🆘 CALL 999
                </Badge>
              )}
              <Badge variant="outline" className={`text-xs ${riskColor}`}>
                {safetyRisk.toUpperCase()} RISK
              </Badge>
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setShowReport(true)}>
                <FileText className="h-3 w-3 mr-1" /> Report
              </Button>
            </div>
          )}
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">

        {/* INPUT SECTION */}
        <div className="space-y-4">
          <div>
            <h1 className="text-lg font-semibold">What complication are you facing?</h1>
            <p className="text-sm text-muted-foreground">Select or type — get a full clinical decision in under 2 seconds.</p>
          </div>

          {/* Quick-select complication buttons */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {COMPLICATIONS.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => { setSelected(c.id); setCustomQuery(""); }}
                className={`p-2.5 rounded-lg border text-left transition-all text-sm ${
                  selected === c.id
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30"
                    : c.urgent
                    ? "border-red-200 dark:border-red-900 hover:border-red-400"
                    : "border-border hover:border-muted-foreground/50"
                }`}
              >
                <span className="text-base mr-1">{c.icon}</span>
                <span className={c.urgent ? "font-medium" : ""}>{c.label}</span>
              </button>
            ))}
          </div>

          {/* Custom input */}
          <div className="flex gap-2">
            <input
              className="flex-1 h-9 px-3 text-sm border rounded-md bg-background focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Or describe the complication…"
              value={customQuery}
              onChange={(e) => { setCustomQuery(e.target.value); setSelected(null); }}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            />
            <Button
              onClick={handleSubmit}
              disabled={(!selected && !customQuery.trim()) || mutation.isPending}
              className="h-9 px-4"
            >
              {mutation.isPending ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </Button>
          </div>

          {/* Symptom chips */}
          <div>
            <p className="text-xs text-muted-foreground mb-2">Signs present (optional):</p>
            <div className="flex flex-wrap gap-1.5">
              {SYMPTOM_CHIPS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => toggleSymptom(s)}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    symptoms.includes(s)
                      ? "bg-blue-600 border-blue-600 text-white"
                      : "border-border text-muted-foreground hover:border-blue-400"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* LOADING */}
        {mutation.isPending && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <RefreshCw className="h-4 w-4 animate-spin" />
              Generating clinical decision…
            </div>
            {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-28 w-full rounded-lg" />)}
          </div>
        )}

        {/* RESULTS */}
        {result && !mutation.isPending && (
          <div ref={resultsRef} className="space-y-4">

            {/* EMERGENCY BANNER */}
            {result.safety?.call_emergency && (
              <div className="bg-red-600 text-white rounded-xl p-4 flex items-center gap-3">
                <AlertCircle className="h-6 w-6 flex-shrink-0" />
                <div>
                  <p className="font-bold">CALL 999 / EMERGENCY SERVICES IMMEDIATELY</p>
                  <p className="text-sm opacity-90">This is a life-threatening complication.</p>
                </div>
              </div>
            )}

            {/* Latency + evidence level bar */}
            <div className="flex items-center justify-between flex-wrap gap-2">
              <EvidenceBadge label={result.evidence_level ?? "⚪ Limited"} />
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                {result.cache_hit && <span className="text-emerald-500">⚡ Cached</span>}
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" /> {result.latency_ms}ms
                </span>
              </div>
            </div>

            {/* SECTION 1 — DIAGNOSIS */}
            <Section number="1" title="Diagnosis & Clinical Reasoning" icon={Stethoscope}>
              <div className="space-y-3">
                <div className="flex items-start gap-3">
                  <div className="flex-1">
                    <p className="font-medium text-sm">{result.diagnosis?.diagnosis}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{result.diagnosis?.confidence_explanation}</p>
                  </div>
                  <Badge
                    variant="outline"
                    className={`text-xs flex-shrink-0 ${CONFIDENCE_COLORS[result.diagnosis?.confidence as keyof typeof CONFIDENCE_COLORS] ?? ""}`}
                  >
                    {(result.diagnosis?.confidence ?? "low").toUpperCase()} confidence
                  </Badge>
                </div>

                {result.diagnosis?.key_supporting_signs?.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mb-1">Key supporting signs:</p>
                    <div className="flex flex-wrap gap-1.5">
                      {result.diagnosis.key_supporting_signs.map((s: string, i: number) => (
                        <Badge key={i} variant="secondary" className="text-xs">{s}</Badge>
                      ))}
                    </div>
                  </div>
                )}

                {result.diagnosis?.differentials_to_exclude?.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mb-1">Differentials to exclude:</p>
                    <ul className="space-y-0.5">
                      {result.diagnosis.differentials_to_exclude.map((d: string, i: number) => (
                        <li key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                          <XCircle className="h-3 w-3 flex-shrink-0 mt-0.5 text-muted-foreground/50" />
                          {d}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </Section>

            {/* SECTION 2 — IMMEDIATE ACTIONS / WORKFLOW */}
            <Section number="2" title="Immediate Actions" icon={Zap} urgent={result.safety?.stop_immediately}>
              {/* Progress bar */}
              {totalSteps > 0 && (
                <div className="mb-4">
                  <div className="flex justify-between text-xs text-muted-foreground mb-1">
                    <span>Progress</span>
                    <span>{completedCount}/{totalSteps} steps completed</span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        progressPct === 100 ? "bg-emerald-500" : "bg-blue-500"
                      }`}
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                </div>
              )}

              <p className="text-xs text-muted-foreground mb-3">Tap each step to mark complete</p>
              <div className="space-y-2">
                {(result.workflow ?? []).map((step: any) => (
                  <WorkflowStep
                    key={step.step}
                    step={step}
                    completed={completedSteps.has(step.step)}
                    onComplete={() => toggleStep(step.step)}
                  />
                ))}
              </div>
            </Section>

            {/* SECTION 3 — HYALURONIDASE */}
            {result.hyaluronidase && (
              <Section number="3" title="Hyaluronidase Dosing" icon={Syringe} urgent={result.safety?.stop_immediately}>
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-muted/50 rounded-lg p-3">
                    <p className="text-xs text-muted-foreground">Recommended dose</p>
                    <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                      {result.hyaluronidase.recommended_dose_IU.toLocaleString()} IU
                    </p>
                  </div>
                  <div className="bg-muted/50 rounded-lg p-3">
                    <p className="text-xs text-muted-foreground">Maximum total</p>
                    <p className="text-2xl font-bold">
                      {result.hyaluronidase.maximum_total_IU.toLocaleString()} IU
                    </p>
                  </div>
                </div>
                <div className="mt-3 space-y-1 text-xs text-muted-foreground">
                  <p><span className="font-medium text-foreground">Reconstitution:</span> {result.hyaluronidase.reconstitution}</p>
                  <p><span className="font-medium text-foreground">Needle:</span> {result.hyaluronidase.needle}</p>
                  <p><span className="font-medium text-foreground">Repeat:</span> {result.hyaluronidase.repeat_interval}</p>
                  <p className="mt-2">{result.hyaluronidase.injection_note}</p>
                </div>
              </Section>
            )}

            {/* SECTION 4 — SAFETY & ESCALATION */}
            <Section number={result.hyaluronidase ? "4" : "3"} title="Safety & Escalation" icon={AlertTriangle} urgent={result.safety?.risk_level === "critical"}>
              <div className="space-y-3">
                {result.safety?.stop_immediately && (
                  <div className="flex items-center gap-2 p-2 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg text-sm font-medium text-red-700 dark:text-red-400">
                    <AlertCircle className="h-4 w-4 flex-shrink-0" />
                    STOP the procedure immediately
                  </div>
                )}

                <div>
                  <p className="text-xs font-medium mb-1">Escalation triggers:</p>
                  <ul className="space-y-1">
                    {(result.safety?.triggers ?? []).map((t: string, i: number) => (
                      <li key={i} className="flex items-start gap-2 text-xs">
                        <ChevronRight className="h-3 w-3 flex-shrink-0 mt-0.5 text-orange-500" />
                        {t}
                      </li>
                    ))}
                  </ul>
                </div>

                {result.safety?.time_critical && (
                  <div className="flex items-center gap-2 text-xs p-2 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                    <Clock className="h-4 w-4 text-amber-600 flex-shrink-0" />
                    <span className="font-medium text-amber-700 dark:text-amber-400">{result.safety.time_critical}</span>
                  </div>
                )}
              </div>
            </Section>

            {/* SECTION 5 — EVIDENCE */}
            {result.evidence?.length > 0 && (
              <Section number={result.hyaluronidase ? "5" : "4"} title={`Evidence (${result.evidence.length})`} icon={BookOpen}>
                <div className="space-y-2">
                  {result.evidence.map((ev: any, i: number) => (
                    <div key={i} className="flex items-start justify-between gap-3 py-2 border-b last:border-0 last:pb-0">
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium leading-snug">{ev.title}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {ev.source} · {ev.year}
                        </p>
                      </div>
                      <EvidenceBadge label={ev.evidence_badge ?? "⚪ Limited"} />
                    </div>
                  ))}
                </div>
                <p className="text-[10px] text-muted-foreground mt-3">
                  Evidence ranked by hierarchy: Guidelines → Consensus → Reviews → RCTs
                </p>
              </Section>
            )}

            {/* SECTION 6 — SIMILAR CASES */}
            {result.similar_cases?.length > 0 && (
              <Section number={result.hyaluronidase ? "6" : "5"} title="Similar Cases (Anonymous)" icon={Activity}>
                <div className="space-y-2">
                  {result.similar_cases.map((c: any, i: number) => (
                    <div key={i} className="flex items-start justify-between gap-3 p-2 rounded-lg bg-muted/50 text-xs">
                      <div>
                        <p className="font-medium">{c.complication_type} · {c.region}</p>
                        <p className="text-muted-foreground">{c.treatment_given}</p>
                        {c.hyaluronidase_dose && (
                          <p className="text-muted-foreground">Hyal: {c.hyaluronidase_dose}</p>
                        )}
                      </div>
                      <div className="text-right flex-shrink-0">
                        <Badge variant="outline" className="text-xs">{c.outcome}</Badge>
                        <p className="text-muted-foreground mt-1">{c.time_ago}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* DOCUMENTATION EXPORT */}
            <div className="flex flex-wrap gap-2 pt-2">
              <Button onClick={() => setShowReport(true)} variant="default" size="sm">
                <FileText className="h-3.5 w-3.5 mr-1.5" />
                Generate Incident Report
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  const text = [
                    `DIAGNOSIS: ${result.diagnosis?.diagnosis}`,
                    `CONFIDENCE: ${result.diagnosis?.confidence}`,
                    "",
                    "WORKFLOW:",
                    ...(result.workflow ?? []).map((s: any) => `${s.step}. ${s.action}`),
                    "",
                    "ESCALATION:",
                    ...(result.safety?.triggers ?? []),
                  ].join("\n");
                  navigator.clipboard.writeText(text);
                  toast({ title: "Copied" });
                }}
              >
                <Copy className="h-3.5 w-3.5 mr-1.5" /> Copy
              </Button>
              <Button variant="outline" size="sm" onClick={() => window.print()}>
                <Printer className="h-3.5 w-3.5 mr-1.5" /> Print
              </Button>
            </div>

            {/* Disclaimer */}
            <div className="flex items-start gap-2 p-3 rounded-lg bg-muted/50 text-xs text-muted-foreground">
              <Info className="h-4 w-4 flex-shrink-0 mt-0.5" />
              AesthetiCite is clinical decision support only. It does not replace clinical judgement.
              Escalate immediately if in doubt.
            </div>
          </div>
        )}
      </div>

      {/* Report modal */}
      {showReport && <ReportPanel result={result} onClose={() => setShowReport(false)} />}
    </div>
  );
}
