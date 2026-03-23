/**
 * AesthetiCite — Clinical Decision Page (v2)
 * The single screen a clinician uses when a complication happens.
 *
 * 6 sections, numbered, always in the same order:
 *   1. Diagnosis          — what is this, confidence, red flags
 *   2. Immediate Actions  — WorkflowRunner (tap steps + timers)
 *   3. Treatment          — drug doses
 *   4. Safety             — escalation, when to stop, medico-legal
 *   5. Evidence           — citations with type labels
 *   6. Documentation      — report PDF + case log
 *
 * Design: dark clinical UI.
 * Route: /decide (replace existing /complication-decision)
 */

import { useEffect, useRef, useState } from "react";
import { useLocation } from "wouter";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertTriangle, Activity, BookOpen, CheckCircle2,
  ChevronDown, ChevronUp, Clock, FileText,
  Search, Shield, Syringe, Zap, RotateCcw,
  Eye, Microscope, HelpCircle,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { getToken } from "@/lib/auth";
import { WorkflowRunner } from "@/pages/workflow";
import { SafetyEscalationBlock } from "@/components/safety-escalation-block";
import { SimilarCasesPanel, LogCaseButton } from "@/components/similar-cases";
import { ReportExportButton } from "@/components/medico-legal-report";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ComplicationResult {
  matched_protocol_name: string;
  matched_protocol_key: string;
  confidence: number;
  risk_assessment: {
    risk_score: number;
    severity: "low" | "moderate" | "high" | "critical";
    urgency: "routine" | "same_day" | "urgent" | "immediate";
  };
  clinical_summary: string;
  red_flags: string[];
  dose_guidance: { substance: string; recommendation: string; notes: string }[];
  escalation: string[];
  evidence: { source_id: string; title: string; note: string; source_type?: string; year?: number }[];
  safety?: any;
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// Quick-select
// ---------------------------------------------------------------------------

const QUICK_OPTIONS = [
  { id: "vascular_occlusion", label: "Vascular Occlusion", query: "vascular occlusion management hyaluronidase treatment protocol", urgent: true,  icon: AlertTriangle },
  { id: "anaphylaxis",        label: "Anaphylaxis",        query: "anaphylaxis emergency management aesthetic injectable",          urgent: true,  icon: Zap },
  { id: "nodules",            label: "Nodules",            query: "filler nodule granuloma treatment management",                   urgent: false, icon: Activity },
  { id: "infection",          label: "Infection",          query: "post-filler infection biofilm treatment antibiotics",            urgent: false, icon: Microscope },
  { id: "ptosis",             label: "Ptosis",             query: "botulinum toxin ptosis management apraclonidine",                urgent: false, icon: Eye },
  { id: "tyndall",            label: "Tyndall Effect",     query: "tyndall effect filler hyaluronidase treatment",                 urgent: false, icon: Shield },
  { id: "dir",                label: "Delayed Inflammatory",query: "delayed inflammatory reaction filler management",              urgent: false, icon: Clock },
  { id: "other",              label: "Other",              query: "",                                                               urgent: false, icon: HelpCircle },
];

// ---------------------------------------------------------------------------
// Evidence type label colours
// ---------------------------------------------------------------------------

const EV_CLS: Record<string, string> = {
  "Guideline":           "bg-emerald-900/60 text-emerald-300 border-emerald-700",
  "Systematic Review":   "bg-blue-900/60 text-blue-300 border-blue-700",
  "Meta-Analysis":       "bg-blue-900/60 text-blue-300 border-blue-700",
  "Consensus Statement": "bg-violet-900/60 text-violet-300 border-violet-700",
  "RCT":                 "bg-sky-900/60 text-sky-300 border-sky-700",
  "Review":              "bg-slate-700/60 text-slate-300 border-slate-600",
  "Case Series":         "bg-amber-900/40 text-amber-300 border-amber-700",
};
function evCls(t?: string) {
  if (!t) return "bg-slate-700/60 text-slate-300 border-slate-600";
  for (const [k, v] of Object.entries(EV_CLS)) {
    if (t.toLowerCase().includes(k.toLowerCase())) return v;
  }
  return "bg-slate-700/60 text-slate-300 border-slate-600";
}

// ---------------------------------------------------------------------------
// Section wrapper
// ---------------------------------------------------------------------------

const ACCENT: Record<string, { border: string; icon: string; num: string; title: string }> = {
  red:     { border: "border-l-red-500",     icon: "text-red-400",     num: "bg-red-600",     title: "text-red-100" },
  orange:  { border: "border-l-orange-500",  icon: "text-orange-400",  num: "bg-orange-600",  title: "text-orange-100" },
  blue:    { border: "border-l-blue-500",    icon: "text-blue-400",    num: "bg-blue-600",    title: "text-blue-100" },
  emerald: { border: "border-l-emerald-500", icon: "text-emerald-400", num: "bg-emerald-600", title: "text-emerald-100" },
  slate:   { border: "border-l-slate-500",   icon: "text-slate-400",   num: "bg-slate-600",   title: "text-slate-100" },
  violet:  { border: "border-l-violet-500",  icon: "text-violet-400",  num: "bg-violet-600",  title: "text-violet-100" },
};

function Section({
  number, title, icon: Icon, accent = "slate",
  children, defaultOpen = true, badge, badgeCls,
}: {
  number: string; title: string; icon: React.ElementType;
  accent?: string; children: React.ReactNode;
  defaultOpen?: boolean; badge?: string; badgeCls?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const a = ACCENT[accent] ?? ACCENT.slate;
  return (
    <div className={`rounded-xl border border-white/8 bg-slate-900 border-l-4 ${a.border} overflow-hidden`}>
      <button
        type="button"
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/5 transition-colors text-left"
        onClick={() => setOpen(!open)}
      >
        <span className={`w-6 h-6 rounded flex items-center justify-center text-[11px] font-bold text-white flex-shrink-0 ${a.num}`}>
          {number}
        </span>
        <Icon className={`h-4 w-4 flex-shrink-0 ${a.icon}`} />
        <span className={`font-semibold text-sm flex-1 ${a.title}`}>{title}</span>
        {badge && <Badge className={`text-[10px] ${badgeCls ?? "bg-white/10 text-white/60"}`}>{badge}</Badge>}
        {open ? <ChevronUp className="h-3.5 w-3.5 text-white/30" /> : <ChevronDown className="h-3.5 w-3.5 text-white/30" />}
      </button>
      {open && <div className="px-4 pb-4 pt-1">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-section: Diagnosis
// ---------------------------------------------------------------------------

function DiagnosisSection({ r }: { r: ComplicationResult }) {
  const urgencyStyle = {
    immediate: { bg: "bg-red-600",    pulse: true,  label: "IMMEDIATE" },
    urgent:    { bg: "bg-orange-500", pulse: false, label: "URGENT" },
    same_day:  { bg: "bg-amber-500",  pulse: false, label: "SAME DAY" },
    routine:   { bg: "bg-slate-500",  pulse: false, label: "ROUTINE" },
  }[r.risk_assessment.urgency];
  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-white font-bold text-lg leading-tight">{r.matched_protocol_name}</p>
          <p className="text-white/40 text-xs mt-0.5">Confidence: {Math.round(r.confidence * 100)}%</p>
        </div>
        <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
          <span className={`px-2.5 py-1 rounded text-white text-xs font-bold ${urgencyStyle.bg} ${urgencyStyle.pulse ? "animate-pulse" : ""}`}>
            {urgencyStyle.label}
          </span>
          <span className="text-white/30 text-xs">Risk {r.risk_assessment.risk_score}/100</span>
        </div>
      </div>
      <p className="text-white/75 text-sm leading-relaxed">{r.clinical_summary}</p>
      {r.red_flags.length > 0 && (
        <div className="bg-red-950/40 border border-red-800/50 rounded-lg p-3">
          <p className="text-red-300 text-[11px] font-bold uppercase tracking-widest mb-2 flex items-center gap-1.5">
            <AlertTriangle className="h-3.5 w-3.5" /> Red Flags
          </p>
          <ul className="space-y-1">
            {r.red_flags.map((f, i) => (
              <li key={i} className="flex items-start gap-1.5 text-xs text-red-200">
                <span className="text-red-500 flex-shrink-0 mt-0.5">•</span>{f}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-section: Treatment
// ---------------------------------------------------------------------------

function TreatmentSection({ r }: { r: ComplicationResult }) {
  if (!r.dose_guidance?.length) return <p className="text-white/30 text-sm">No dose guidance for this protocol.</p>;
  return (
    <div className="space-y-2.5">
      {r.dose_guidance.map((d, i) => (
        <div key={i} className="bg-blue-950/40 border border-blue-800/40 rounded-lg p-3 flex items-start gap-2.5">
          <Syringe className="h-4 w-4 text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="min-w-0 flex-1">
            <p className="text-white font-bold text-sm">{d.substance}</p>
            <p className="text-blue-200 text-sm mt-0.5">{d.recommendation}</p>
            {d.notes && <p className="text-white/40 text-xs mt-1">{d.notes}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-section: Evidence
// ---------------------------------------------------------------------------

function EvidenceSection({ evidence }: { evidence: ComplicationResult["evidence"] }) {
  if (!evidence?.length) return <p className="text-white/30 text-sm">No evidence retrieved.</p>;
  return (
    <div className="space-y-2">
      {evidence.map((e, i) => (
        <div key={i} className="flex items-start gap-3 py-2 border-b border-white/8 last:border-0">
          <span className="text-[11px] font-mono text-white/25 w-5 flex-shrink-0 mt-0.5">[{i + 1}]</span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 flex-wrap mb-0.5">
              {e.source_type && (
                <Badge className={`text-[10px] border ${evCls(e.source_type)}`}>{e.source_type}</Badge>
              )}
              {e.year && <span className="text-[10px] text-white/25">{e.year}</span>}
            </div>
            <p className="text-white/75 text-xs font-medium leading-snug">{e.title}</p>
            {e.note && <p className="text-white/40 text-xs mt-0.5 leading-relaxed">{e.note}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state — selector
// ---------------------------------------------------------------------------

function ComplicationSelector({ onQuery, isLoading }: { onQuery: (q: string, id: string) => void; isLoading: boolean }) {
  const [custom, setCustom] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center px-4 py-12">
      <div className="text-center mb-10 max-w-lg">
        <div className="flex justify-center mb-6">
          <img src="/aestheticite-logo.png" alt="AesthetiCite" className="h-20 w-auto opacity-90" />
        </div>
        <h1 className="text-white text-3xl font-bold tracking-tight mb-2">
          What complication are you facing?
        </h1>
        <p className="text-white/35 text-sm">Clinical protocol · Evidence · Documentation — one screen</p>
      </div>
      <div className="w-full max-w-xl grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
        {QUICK_OPTIONS.map((opt) => {
          const Icon = opt.icon;
          return (
            <button
              key={opt.id}
              type="button"
              disabled={isLoading}
              onClick={() => {
                if (opt.id === "other") { inputRef.current?.focus(); return; }
                onQuery(opt.query, opt.id);
              }}
              className={`relative flex flex-col items-center justify-center gap-2 px-2 py-4 rounded-xl border
                transition-all duration-150 text-xs font-medium disabled:opacity-50
                ${opt.urgent
                  ? "border-red-800 hover:border-red-500 hover:bg-red-950/30 text-red-300"
                  : "border-white/10 hover:border-blue-500 hover:bg-blue-950/20 text-white/60 hover:text-white"
                }`}
            >
              <Icon className={`h-5 w-5 ${opt.urgent ? "text-red-400" : "text-white/35"}`} />
              <span className="text-center leading-tight">{opt.label}</span>
              {opt.urgent && <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-red-500 rounded-full" />}
            </button>
          );
        })}
      </div>
      <div className="w-full max-w-xl flex gap-2">
        <input
          ref={inputRef}
          type="text"
          placeholder="Or type any complication…"
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && custom.trim()) onQuery(custom.trim(), "custom"); }}
          disabled={isLoading}
          className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm
                     placeholder-white/20 focus:outline-none focus:border-blue-500 transition-colors disabled:opacity-50"
        />
        <Button
          onClick={() => { if (custom.trim()) onQuery(custom.trim(), "custom"); }}
          disabled={isLoading || !custom.trim()}
          className="rounded-xl px-4"
        >
          {isLoading
            ? <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            : <Search className="h-4 w-4" />
          }
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function LoadingSkeleton({ complication }: { complication: string }) {
  const phases = ["Retrieving evidence", "Running safety assessment", "Building protocol", "Generating workflow"];
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setPhase((p) => (p + 1) % phases.length), 900);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center px-4">
      <div className="max-w-md w-full space-y-6 text-center">
        <div className="w-14 h-14 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mx-auto" />
        <div>
          <p className="text-white font-bold text-lg">{complication}</p>
          <p className="text-white/35 text-sm mt-1">{phases[phase]}…</p>
        </div>
        <div className="h-1 bg-white/8 rounded-full overflow-hidden w-56 mx-auto">
          <div
            className="h-full bg-blue-500 rounded-full transition-all duration-700"
            style={{ width: `${25 + phase * 25}%` }}
          />
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
  const [result, setResult]       = useState<ComplicationResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [currentQuery, setQuery]  = useState("");
  const [selectedId, setId]       = useState("");
  const [safetyData, setSafety]   = useState<any>(null);
  const topRef = useRef<HTMLDivElement>(null);

  // Parse ?complication= from URL
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const c = p.get("complication");
    if (c && !result) {
      const opt = QUICK_OPTIONS.find((o) => o.label.toLowerCase().includes(c.toLowerCase()));
      handleQuery(opt?.query ?? c, opt?.id ?? "custom");
    }
  }, []);

  const handleQuery = async (query: string, id: string) => {
    if (!query.trim()) return;
    setQuery(query); setId(id); setIsLoading(true); setResult(null); setSafety(null);
    const token = getToken();
    const hdrs: Record<string, string> = { "Content-Type": "application/json" };
    if (token) hdrs["Authorization"] = `Bearer ${token}`;
    try {
      const res = await fetch("/api/complications/protocol", {
        method: "POST", headers: hdrs,
        body: JSON.stringify({ query, mode: "decision_support" }),
      });
      if (!res.ok) throw new Error("Protocol unavailable");
      setResult(await res.json());
      // Parallel safety fetch
      fetch("/api/safety/assess", { method: "POST", headers: hdrs, body: JSON.stringify({ query }) })
        .then((r) => r.ok ? r.json() : null).then((d) => { if (d) setSafety(d); }).catch(() => {});
    } catch (e: any) {
      toast({ title: "Unable to load protocol", description: e.message, variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => { setResult(null); setQuery(""); setId(""); setSafety(null); };

  if (!isLoading && !result) {
    return <div className="min-h-screen bg-slate-950"><ComplicationSelector onQuery={handleQuery} isLoading={isLoading} /></div>;
  }
  if (isLoading) {
    return <div className="min-h-screen bg-slate-950"><LoadingSkeleton complication={currentQuery} /></div>;
  }

  const urgencyAccent = result?.risk_assessment.urgency === "immediate" ? "red"
    : result?.risk_assessment.urgency === "urgent" ? "orange" : "blue";

  return (
    <div className="min-h-screen bg-slate-950 text-white" ref={topRef}>

      {/* ── Sticky header ── */}
      <div className="sticky top-0 z-40 bg-slate-950/95 backdrop-blur-sm border-b border-white/8">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <img src="/aestheticite-logo.png" alt="" className="h-6 w-auto opacity-60 flex-shrink-0" />
            <div className="min-w-0">
              <p className="text-white font-bold text-sm truncate">{result?.matched_protocol_name ?? currentQuery}</p>
              <p className="text-white/30 text-[10px]">AesthetiCite Clinical Decision</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            {result && (
              <Badge className={`text-[10px] text-white ${
                result.risk_assessment.urgency === "immediate" ? "bg-red-600 animate-pulse" :
                result.risk_assessment.urgency === "urgent"    ? "bg-orange-500" :
                result.risk_assessment.urgency === "same_day"  ? "bg-amber-500" : "bg-slate-600"
              }`}>
                {result.risk_assessment.urgency.replace("_", " ").toUpperCase()}
              </Badge>
            )}
            <button type="button" onClick={handleReset}
              className="text-white/25 hover:text-white p-1.5 rounded-lg hover:bg-white/8 transition-colors">
              <RotateCcw className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* ── 6 sections ── */}
      {result && (
        <div className="max-w-2xl mx-auto px-4 py-4 space-y-3">

          {/* 1 — DIAGNOSIS */}
          <Section number="1" title="Diagnosis" icon={CheckCircle2} accent={urgencyAccent}
            badge={`${result.risk_assessment.risk_score}/100`} badgeCls="bg-white/10 text-white/50">
            <DiagnosisSection r={result} />
          </Section>

          {/* 2 — IMMEDIATE ACTIONS */}
          <Section number="2" title="Immediate Actions" icon={Zap} accent={urgencyAccent}>
            <div className="-mx-4 -mb-4">
              <WorkflowRunner complication={result.matched_protocol_key} className="rounded-none rounded-b-xl" />
            </div>
          </Section>

          {/* 3 — TREATMENT */}
          <Section number="3" title="Treatment" icon={Syringe} accent="blue">
            <TreatmentSection r={result} />
          </Section>

          {/* 4 — SAFETY & ESCALATION */}
          <Section number="4" title="Safety & Escalation" icon={Shield} accent="orange"
            defaultOpen={result.risk_assessment.urgency !== "routine"}>
            {safetyData ? (
              <SafetyEscalationBlock safety={safetyData} className="bg-transparent border-0 shadow-none -mx-4 -mb-4" />
            ) : (
              <div className="space-y-2">
                {result.escalation.map((e, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <AlertTriangle className="h-3.5 w-3.5 text-orange-400 flex-shrink-0 mt-0.5" />
                    <span className="text-white/70">{e}</span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* 5 — EVIDENCE */}
          <Section number="5" title="Evidence" icon={BookOpen} accent="violet" defaultOpen={false}
            badge={result.evidence?.length ? `${result.evidence.length} sources` : undefined}
            badgeCls="bg-violet-900/60 text-violet-300">
            <EvidenceSection evidence={result.evidence ?? []} />
          </Section>

          {/* 6 — DOCUMENTATION */}
          <Section number="6" title="Documentation Export" icon={FileText} accent="emerald" defaultOpen={false}>
            <div className="space-y-3">
              <p className="text-white/40 text-xs">
                Generate an MDO-ready incident report pre-filled from this session.
              </p>
              <div className="flex flex-wrap gap-2">
                <ReportExportButton
                  complication={result.matched_protocol_name}
                  treatment={result.dose_guidance.map((d) => `${d.substance}: ${d.recommendation}`).join("; ")}
                  evidenceRefs={result.evidence?.slice(0, 5).map((e) => ({ title: e.title, year: e.year }))}
                  size="sm"
                />
                <LogCaseButton
                  complication={result.matched_protocol_name}
                  prefillTreatment={result.dose_guidance.map((d) => `${d.substance}: ${d.recommendation}`).join("; ")}
                  variant="outline" size="sm" label="Log Case"
                />
              </div>
              <SimilarCasesPanel
                complication={result.matched_protocol_key.replace(/_/g, " ")}
                defaultExpanded={false}
                className="bg-white/5 border-white/10"
              />
              <p className="text-white/15 text-[10px] leading-relaxed pt-1 border-t border-white/8">
                {result.disclaimer}
              </p>
            </div>
          </Section>

        </div>
      )}
      <div className="h-16" />
    </div>
  );
}
