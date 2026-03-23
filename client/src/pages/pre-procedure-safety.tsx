/**
 * AesthetiCite Pre-Procedure Safety UI — Enhanced v2.0
 * =====================================================
 * Additions from congress intelligence (2025/2026):
 *   1. Ultrasound Recommended flags for high-risk zones
 *   2. Complication Differential Mode (symptom → ranked differentials)
 *   3. GLP-1 patient risk factor
 *   4. Biostimulator product-class safety cards
 *
 * Drop into: client/src/pages/pre-procedure-safety.tsx
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "wouter";
import {
  ShieldAlert, FileText, AlertTriangle, CheckCircle2, XCircle,
  ChevronRight, Microscope, Activity, Zap, Eye, Download,
  ArrowLeft, FlaskConical, Waves
} from "lucide-react";

// ─── Types ─────────────────────────────────────────────────────────────────

interface PatientFactors {
  prior_filler_in_same_area?: boolean;
  prior_vascular_event?: boolean;
  autoimmune_history?: boolean;
  allergy_history?: boolean;
  active_infection_near_site?: boolean;
  anticoagulation?: boolean;
  vascular_disease?: boolean;
  smoking?: boolean;
  glp1_patient?: boolean;
}

interface PreProcedureRequest {
  procedure: string;
  region: string;
  product_type: string;
  technique?: string;
  injector_experience_level?: "junior" | "intermediate" | "senior";
  patient_factors?: PatientFactors;
}

interface RiskItem {
  complication: string;
  risk_score: number;
  risk_level: "low" | "moderate" | "high" | "very_high";
  why_it_matters: string;
}

interface EvidenceItem {
  source_id: string;
  title: string;
  note: string;
  citation_text?: string;
  source_type?: string;
}

interface ProcedureInsight {
  procedure_name: string;
  region: string;
  likely_plane_or_target?: string;
  danger_zones: string[];
  technical_notes: string[];
  ultrasound_recommended?: boolean;
  ultrasound_note?: string;
}

interface SafetyAssessment {
  overall_risk_score: number;
  overall_risk_level: "low" | "moderate" | "high" | "very_high";
  decision: "go" | "caution" | "high_risk";
  rationale: string;
}

interface PreProcedureResponse {
  request_id: string;
  generated_at_utc: string;
  engine_version: string;
  safety_assessment: SafetyAssessment;
  top_risks: RiskItem[];
  procedure_insight: ProcedureInsight;
  mitigation_steps: string[];
  caution_flags: string[];
  evidence: EvidenceItem[];
  disclaimer: string;
}

// ─── Differential Diagnosis types ──────────────────────────────────────────

interface DiffSymptoms {
  onset: string;
  appearance: string;
  pain: string;
  location: string;
  product_used: string;
  time_since_injection: string;
}

interface DifferentialResult {
  rank: number;
  diagnosis: string;
  probability: "high" | "moderate" | "low";
  key_clues: string[];
  immediate_actions: string[];
  rule_out: string[];
}

// ─── Utilities ─────────────────────────────────────────────────────────────

function decisionConfig(decision: string) {
  if (decision === "go") return {
    label: "PROCEED", bg: "bg-emerald-50", border: "border-emerald-200",
    text: "text-emerald-700", badgeBg: "bg-emerald-600", icon: <CheckCircle2 className="w-5 h-5" />
  };
  if (decision === "caution") return {
    label: "CAUTION", bg: "bg-amber-50", border: "border-amber-200",
    text: "text-amber-700", badgeBg: "bg-amber-500", icon: <AlertTriangle className="w-5 h-5" />
  };
  return {
    label: "HIGH RISK", bg: "bg-red-50", border: "border-red-200",
    text: "text-red-700", badgeBg: "bg-red-600", icon: <XCircle className="w-5 h-5" />
  };
}

function riskColor(level: string) {
  if (level === "very_high" || level === "high") return "text-red-600";
  if (level === "moderate") return "text-amber-600";
  return "text-emerald-600";
}

function riskBarColor(level: string) {
  if (level === "very_high" || level === "high") return "bg-red-500";
  if (level === "moderate") return "bg-amber-400";
  return "bg-emerald-500";
}

function biostimulatorWarning(product: string): string | null {
  const p = product.toLowerCase();
  if (p.includes("sculptra") || p.includes("plla") || p.includes("poly-l-lactic")) {
    return "PLLA (Sculptra): Although generally considered lower-risk, recent evidence shows PLLA can cause unexpected vascular adverse events. Region-specific vascular risk still applies. Do not assume 'safe product = safe procedure'.";
  }
  if (p.includes("radiesse") || p.includes("caha") || p.includes("calcium hydroxylapatite")) {
    return "CaHA (Radiesse): Cannot be dissolved with hyaluronidase. Vascular occlusion management differs from HA fillers — ensure your protocol accounts for non-dissoluble filler.";
  }
  if (p.includes("exosome") || p.includes("prp") || p.includes("platelet")) {
    return "Biostimulatory injectables: Regulatory landscape varies by jurisdiction. Verify your clinic meets current standards for handling biological products.";
  }
  return null;
}

// ─── Differential Engine (client-side) ─────────────────────────────────────

function computeDifferentials(symptoms: DiffSymptoms): DifferentialResult[] {
  const results: DifferentialResult[] = [];
  const a = symptoms.appearance.toLowerCase();
  const p = symptoms.pain.toLowerCase();
  const o = symptoms.onset.toLowerCase();
  const t = symptoms.time_since_injection.toLowerCase();

  const voScore =
    (a.includes("pale") || a.includes("blanch") || a.includes("white") || a.includes("mottl") ? 3 : 0) +
    (p.includes("severe") || p.includes("intense") || p.includes("burning") ? 2 : 0) +
    (o.includes("immediate") || o.includes("during") ? 2 : 0);

  if (voScore >= 3) {
    results.push({
      rank: 1,
      diagnosis: "Vascular Occlusion (VO)",
      probability: voScore >= 5 ? "high" : "moderate",
      key_clues: ["Blanching or pallor at injection site", "Severe or burning pain", "Immediate or rapid onset", "Mottling or livedo pattern"],
      immediate_actions: [
        "STOP injection immediately",
        "Inject hyaluronidase NOW if HA filler (do not wait)",
        "Apply warm compress to area",
        "Initiate vascular occlusion protocol",
        "Escalate if no improvement within 60 minutes"
      ],
      rule_out: ["Bruising (VO appears white/pale, not purple)", "Normal swelling (VO has demarcated ischemic pattern)"]
    });
  }

  const donScore =
    (t.includes("week") || t.includes("month") || t.includes("day") ? 2 : 0) +
    (a.includes("lump") || a.includes("nodule") || a.includes("hard") || a.includes("firm") ? 3 : 0) +
    (p.includes("mild") || p.includes("tender") ? 1 : 0);

  if (donScore >= 3) {
    results.push({
      rank: results.length + 1,
      diagnosis: "Delayed-Onset Nodule (DON)",
      probability: donScore >= 5 ? "high" : "moderate",
      key_clues: ["Palpable firm nodule (days to months post-procedure)", "Non-blanching", "May be tender or asymptomatic"],
      immediate_actions: [
        "Assess if filler-related or inflammatory",
        "If HA: consider hyaluronidase trial",
        "If infected: swab, antibiotics, do not inject further",
        "Ultrasound can differentiate filler mass from abscess"
      ],
      rule_out: ["Infection (DON typically non-infected but can progress)", "Granuloma (delayed, firm, inflammatory)"]
    });
  }

  const infScore =
    (a.includes("red") || a.includes("erythema") || a.includes("warm") ? 2 : 0) +
    (a.includes("pus") || a.includes("discharge") ? 3 : 0) +
    (t.includes("week") || t.includes("month") ? 1 : 0) +
    (p.includes("throbbing") || p.includes("severe") ? 1 : 0);

  if (infScore >= 3) {
    results.push({
      rank: results.length + 1,
      diagnosis: "Infection / Biofilm",
      probability: infScore >= 4 ? "high" : "moderate",
      key_clues: ["Erythema, warmth, swelling", "Possible pus or discharge", "Pain, especially throbbing", "Onset days to weeks"],
      immediate_actions: [
        "Do NOT inject more filler",
        "Swab for culture if discharge present",
        "Start broad-spectrum antibiotics",
        "Consider hyaluronidase if HA filler and firm nodule",
        "Refer to appropriate specialist if not improving in 48h"
      ],
      rule_out: ["Hypersensitivity (no fever, more urticarial)", "Normal post-procedure swelling (resolves 24-48h)"]
    });
  }

  const hsScore =
    (a.includes("itch") || a.includes("urtic") || a.includes("hive") || a.includes("rash") ? 3 : 0) +
    (o.includes("immediate") || o.includes("minutes") ? 2 : 0) +
    (symptoms.location.toLowerCase().includes("widespread") || symptoms.location.toLowerCase().includes("whole") ? 1 : 0);

  if (hsScore >= 3) {
    results.push({
      rank: results.length + 1,
      diagnosis: "Hypersensitivity / Allergic Reaction",
      probability: hsScore >= 4 ? "high" : "moderate",
      key_clues: ["Urticaria, pruritus, or erythema", "Rapid onset (minutes)", "Possibly widespread", "May involve throat tightness (anaphylaxis)"],
      immediate_actions: [
        "Assess airway, breathing, circulation FIRST",
        "If anaphylaxis: adrenaline (epinephrine) 0.5mg IM immediately",
        "Antihistamine and corticosteroid as adjuncts",
        "Call emergency services if systemic signs",
        "Do not leave patient alone"
      ],
      rule_out: ["Normal post-procedure erythema (localised, not urticarial)", "VO (localised ischemic pattern, not urticarial)"]
    });
  }

  const tyndallScore =
    (a.includes("blue") || a.includes("grey") || a.includes("discolour") ? 3 : 0) +
    (t.includes("week") || t.includes("month") ? 1 : 0) +
    (symptoms.location.toLowerCase().includes("tear") || symptoms.location.toLowerCase().includes("eye") || symptoms.location.toLowerCase().includes("periorbital") ? 2 : 0);

  if (tyndallScore >= 3) {
    results.push({
      rank: results.length + 1,
      diagnosis: "Tyndall Effect",
      probability: tyndallScore >= 4 ? "high" : "moderate",
      key_clues: ["Blue-grey discolouration under skin", "Periorbital or superficial location", "No pain typically", "Gradual onset"],
      immediate_actions: [
        "Confirm with Wood's lamp or clinical assessment",
        "Hyaluronidase dissolving treatment if HA filler",
        "Manage patient expectations: may take multiple sessions",
        "Document and photograph"
      ],
      rule_out: ["Bruising (purple, resolves in days)", "Infection (warm, painful, erythematous)"]
    });
  }

  if (results.length === 0) {
    results.push({
      rank: 1,
      diagnosis: "Insufficient symptom data for confident differential",
      probability: "low",
      key_clues: ["Symptom pattern does not clearly match common complication profiles"],
      immediate_actions: ["Perform a full clinical assessment", "Use ultrasound if available", "Consult experienced colleague"],
      rule_out: ["Consider vascular occlusion until proven otherwise in any post-filler concern"]
    });
  }

  return results.sort((a, b) => {
    const order = { high: 0, moderate: 1, low: 2 };
    return order[a.probability] - order[b.probability];
  }).map((r, i) => ({ ...r, rank: i + 1 }));
}

// ─── API Call ───────────────────────────────────────────────────────────────

async function runSafetyCheck(payload: PreProcedureRequest): Promise<PreProcedureResponse> {
  const res = await fetch("/api/safety/preprocedure-check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Safety check failed");
  }
  return res.json();
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function RiskGauge({ score, level }: { score: number; level: string }) {
  const color = level === "very_high" || level === "high" ? "#ef4444"
    : level === "moderate" ? "#f59e0b" : "#10b981";

  const radius = 52;
  const circumference = Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="130" height="75" viewBox="0 0 130 75">
        <path
          d="M 15 70 A 52 52 0 0 1 115 70"
          fill="none" stroke="#e5e7eb" strokeWidth="12" strokeLinecap="round"
        />
        <path
          d="M 15 70 A 52 52 0 0 1 115 70"
          fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 0.8s ease" }}
        />
        <text x="65" y="62" textAnchor="middle" fontSize="22" fontWeight="700" fill={color}>
          {score}
        </text>
        <text x="65" y="74" textAnchor="middle" fontSize="9" fill="#6b7280">
          /100
        </text>
      </svg>
      <span className="text-xs font-semibold uppercase tracking-wider" style={{ color }}>
        {level.replace("_", " ")} risk
      </span>
    </div>
  );
}

function UltrasoundBanner({ note }: { note?: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3">
      <Waves className="w-5 h-5 text-sky-600 flex-shrink-0 mt-0.5" />
      <div>
        <p className="text-sm font-semibold text-sky-800">Ultrasound Guidance Recommended</p>
        <p className="text-xs text-sky-700 mt-0.5">
          {note || "This region carries significant vascular complexity. Ultrasound guidance is recommended before injection to map local vasculature and reduce ischemic risk. Consider portable high-frequency US with Doppler for real-time vessel identification."}
        </p>
        <p className="text-xs text-sky-600 mt-1 font-medium">
          Evidence: RSNA 2025 — ultrasound identified vascular compromise in 77% of filler-related adverse outcomes studied across 6 centres.
        </p>
      </div>
    </div>
  );
}

function BiostimulatorCard({ product }: { product: string }) {
  const warning = biostimulatorWarning(product);
  if (!warning) return null;
  return (
    <div className="flex items-start gap-3 rounded-xl border border-violet-200 bg-violet-50 px-4 py-3">
      <FlaskConical className="w-5 h-5 text-violet-600 flex-shrink-0 mt-0.5" />
      <div>
        <p className="text-sm font-semibold text-violet-800">Biostimulator Safety Note</p>
        <p className="text-xs text-violet-700 mt-0.5">{warning}</p>
      </div>
    </div>
  );
}

function Glp1Banner() {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-orange-200 bg-orange-50 px-4 py-3">
      <Activity className="w-5 h-5 text-orange-600 flex-shrink-0 mt-0.5" />
      <div>
        <p className="text-sm font-semibold text-orange-800">GLP-1 Patient Advisory</p>
        <p className="text-xs text-orange-700 mt-0.5">
          GLP-1 medications (semaglutide, tirzepatide) cause rapid facial fat loss and volume redistribution.
          Reassess filler volume planning — standard quantities may overcorrect. Tissue planes may be altered.
          Skin laxity changes may affect expected outcomes. Document and counsel patient accordingly.
        </p>
      </div>
    </div>
  );
}

// ─── Checkbox helper ─────────────────────────────────────────────────────────

function CheckField({
  label, desc, checked, onChange
}: { label: string; desc?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer group">
      <div className="relative mt-0.5">
        <input
          type="checkbox"
          checked={checked}
          onChange={e => onChange(e.target.checked)}
          className="sr-only"
        />
        <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-colors
          ${checked ? "bg-slate-700 border-slate-700" : "border-slate-300 group-hover:border-slate-400"}`}>
          {checked && <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 10 10">
            <path d="M1.5 5l2.5 2.5 4.5-4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>}
        </div>
      </div>
      <div>
        <span className="text-sm text-slate-700 font-medium">{label}</span>
        {desc && <p className="text-xs text-slate-400 mt-0.5">{desc}</p>}
      </div>
    </label>
  );
}

// ─── Form select helper ───────────────────────────────────────────────────────

function SelectField({
  label, value, onChange, options, placeholder
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:border-transparent transition-all"
      >
        <option value="">{placeholder || `Select ${label.toLowerCase()}`}</option>
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

function TextInputField({
  label, value, onChange, placeholder
}: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">{label}</label>
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder || ""}
        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:border-transparent transition-all"
      />
    </div>
  );
}

// ─── PreScan type ─────────────────────────────────────────────────────────────

interface PreScanBriefingResponse {
  request_id: string;
  generated_at_utc: string;
  region_label: string;
  risk_level: string;
  structures_to_identify: string[];
  doppler_settings: string;
  key_findings_to_document: string[];
  safe_windows: string[];
  abort_criteria: string[];
  evidence_note: string;
  disclaimer: string;
  junior_note?: string;
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function PreProcedureSafetyPage() {
  const [activeTab, setActiveTab] = useState<"check" | "differential" | "prescan">("check");

  const [procedure, setProcedure] = useState("");
  const [region, setRegion] = useState("");
  const [productType, setProductType] = useState("");
  const [technique, setTechnique] = useState("");
  const [experience, setExperience] = useState<"" | "junior" | "intermediate" | "senior">("");
  const [patientFactors, setPatientFactors] = useState<PatientFactors>({});

  const toggleFactor = (key: keyof PatientFactors) => {
    setPatientFactors(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const [result, setResult] = useState<PreProcedureResponse | null>(null);
  const [formError, setFormError] = useState("");

  const safetyMutation = useMutation({
    mutationFn: runSafetyCheck,
    onSuccess: (data) => { setResult(data); setFormError(""); },
    onError: (err: Error) => { setFormError(err.message); },
  });

  function handleRunCheck() {
    if (!procedure || !region || !productType) {
      setFormError("Procedure, region, and product type are required.");
      return;
    }
    setResult(null);
    safetyMutation.mutate({
      procedure,
      region,
      product_type: productType,
      technique: technique || undefined,
      injector_experience_level: experience || undefined,
      patient_factors: Object.keys(patientFactors).length > 0 ? patientFactors : undefined,
    });
  }

  async function handleExportPDF() {
    if (!result) return;
    const res = await fetch("/api/safety/preprocedure-check/export-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        procedure, region, product_type: productType,
        technique: technique || undefined,
        injector_experience_level: experience || undefined,
        patient_factors: Object.keys(patientFactors).length > 0 ? patientFactors : undefined,
      }),
    });
    if (res.ok) {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `AesthetiCite_Safety_${result.request_id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    }
  }

  const ULTRASOUND_REGIONS = ["nose", "nasal", "temple", "forehead", "frontal", "tear trough", "periorbital", "infraorbital", "glabella"];
  const shouldShowUltrasound = result?.procedure_insight?.ultrasound_recommended
    || ULTRASOUND_REGIONS.some(r => result?.procedure_insight?.region?.toLowerCase().includes(r) || region.toLowerCase().includes(r));

  const [diffSymptoms, setDiffSymptoms] = useState<DiffSymptoms>({
    onset: "", appearance: "", pain: "", location: "", product_used: "", time_since_injection: ""
  });
  const [differentials, setDifferentials] = useState<DifferentialResult[]>([]);
  const [diffRun, setDiffRun] = useState(false);

  // Pre-Scan Briefing state
  const [prescanRegion, setPrescanRegion] = useState("");
  const [prescanExperience, setPrescanExperience] = useState("");
  const [prescanResult, setPrescanResult] = useState<PreScanBriefingResponse | null>(null);
  const [prescanLoading, setPrescanLoading] = useState(false);
  const [prescanError, setPrescanError] = useState("");

  async function handleRunPrescan() {
    if (!prescanRegion) { setPrescanError("Select a region first."); return; }
    setPrescanLoading(true); setPrescanError(""); setPrescanResult(null);
    try {
      const res = await fetch("/api/complications/prescan-briefing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          region: prescanRegion,
          injector_experience_level: prescanExperience || undefined,
          has_ultrasound: true,
        }),
      });
      if (!res.ok) throw new Error("Briefing failed");
      const data = await res.json();
      setPrescanResult(data);
    } catch (e: any) {
      setPrescanError(e.message || "Failed to load briefing");
    } finally {
      setPrescanLoading(false);
    }
  }

  function handleRunDifferential() {
    const results = computeDifferentials(diffSymptoms);
    setDifferentials(results);
    setDiffRun(true);
  }

  const probColor = (p: string) =>
    p === "high" ? "bg-red-100 text-red-700 border-red-200"
    : p === "moderate" ? "bg-amber-100 text-amber-700 border-amber-200"
    : "bg-slate-100 text-slate-600 border-slate-200";

  return (
    <div className="min-h-screen bg-slate-50 font-[system-ui]">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur-sm">
        <div className="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/ask" className="flex items-center gap-1 text-slate-400 hover:text-slate-600 text-sm transition-colors">
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-slate-800 flex items-center justify-center">
                <ShieldAlert className="w-4 h-4 text-white" />
              </div>
              <div>
                <h1 className="text-sm font-bold text-slate-800 leading-none">AesthetiCite</h1>
                <p className="text-[10px] text-slate-500 leading-none mt-0.5">Pre-Procedure Safety Check</p>
              </div>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex items-center gap-1 bg-slate-100 rounded-lg p-1">
            <button
              data-testid="tab-safety-check"
              onClick={() => setActiveTab("check")}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${activeTab === "check" ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              Safety Check
            </button>
            <button
              data-testid="tab-differential"
              onClick={() => setActiveTab("differential")}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all flex items-center gap-1.5 ${activeTab === "differential" ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              <Microscope className="w-3 h-3" />
              Complication Differential
            </button>
            <button
              data-testid="tab-prescan"
              onClick={() => setActiveTab("prescan")}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all flex items-center gap-1.5 ${activeTab === "prescan" ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              <Waves className="w-3 h-3" />
              Pre-Scan Briefing
            </button>
          </div>

          <div className="w-20" />
        </div>
      </header>

      {/* ══════════════════════════════════════════════════════════════════ */}
      {/*  TAB 1: SAFETY CHECK                                              */}
      {/* ══════════════════════════════════════════════════════════════════ */}

      {activeTab === "check" && (
        <div className="mx-auto max-w-6xl px-4 py-6 grid grid-cols-1 lg:grid-cols-5 gap-6">

          {/* ── Form ──────────────────────────────────────────────────── */}
          <div className="lg:col-span-2 space-y-5">

            <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
              <h2 className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
                <Zap className="w-4 h-4 text-slate-600" />
                Procedure Details
              </h2>
              <div className="space-y-3">
                <SelectField
                  label="Procedure"
                  value={procedure}
                  onChange={setProcedure}
                  options={[
                    { value: "nasolabial fold filler", label: "Nasolabial Fold Filler" },
                    { value: "tear trough filler", label: "Tear Trough Filler" },
                    { value: "lip filler", label: "Lip Filler" },
                    { value: "glabellar toxin", label: "Glabellar Toxin" },
                    { value: "jawline filler", label: "Jawline Filler" },
                    { value: "chin filler", label: "Chin Filler" },
                    { value: "cheek filler", label: "Cheek Filler" },
                    { value: "temple filler", label: "Temple Filler" },
                    { value: "forehead botox", label: "Forehead Toxin" },
                    { value: "nose filler", label: "Nose Filler (Non-surgical rhinoplasty)" },
                  ]}
                />
                <SelectField
                  label="Region"
                  value={region}
                  onChange={setRegion}
                  options={[
                    { value: "nasolabial fold", label: "Nasolabial Fold" },
                    { value: "tear trough", label: "Tear Trough / Periorbital" },
                    { value: "lip", label: "Lip" },
                    { value: "glabella", label: "Glabella / Frown Lines" },
                    { value: "jawline", label: "Jawline" },
                    { value: "chin", label: "Chin" },
                    { value: "cheek", label: "Cheek / Malar" },
                    { value: "temple", label: "Temple / Temporal" },
                    { value: "forehead", label: "Forehead" },
                    { value: "nose", label: "Nose / Nasal" },
                  ]}
                />
                <SelectField
                  label="Product Type"
                  value={productType}
                  onChange={setProductType}
                  options={[
                    { value: "hyaluronic acid filler", label: "Hyaluronic Acid Filler (HA)" },
                    { value: "calcium hydroxylapatite", label: "Calcium Hydroxylapatite (CaHA / Radiesse)" },
                    { value: "sculptra plla", label: "PLLA (Sculptra)" },
                    { value: "botulinum toxin", label: "Botulinum Toxin" },
                    { value: "prp", label: "PRP / Biostimulator" },
                    { value: "exosome", label: "Exosome-based Injectable" },
                  ]}
                />
                <SelectField
                  label="Technique"
                  value={technique}
                  onChange={setTechnique}
                  options={[
                    { value: "needle", label: "Needle" },
                    { value: "cannula", label: "Cannula" },
                  ]}
                  placeholder="Select technique (optional)"
                />
                <SelectField
                  label="Injector Experience"
                  value={experience}
                  onChange={v => setExperience(v as "" | "junior" | "intermediate" | "senior")}
                  options={[
                    { value: "junior", label: "Junior (< 2 years)" },
                    { value: "intermediate", label: "Intermediate (2–5 years)" },
                    { value: "senior", label: "Senior (5+ years)" },
                  ]}
                  placeholder="Select experience level"
                />
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
              <h2 className="text-sm font-bold text-slate-800 mb-4">Patient Risk Factors</h2>
              <div className="space-y-3">
                <CheckField
                  label="Prior filler in same area"
                  checked={!!patientFactors.prior_filler_in_same_area}
                  onChange={() => toggleFactor("prior_filler_in_same_area")}
                />
                <CheckField
                  label="Prior vascular event"
                  checked={!!patientFactors.prior_vascular_event}
                  onChange={() => toggleFactor("prior_vascular_event")}
                />
                <CheckField
                  label="Anticoagulation therapy"
                  checked={!!patientFactors.anticoagulation}
                  onChange={() => toggleFactor("anticoagulation")}
                />
                <CheckField
                  label="Active infection near site"
                  checked={!!patientFactors.active_infection_near_site}
                  onChange={() => toggleFactor("active_infection_near_site")}
                />
                <CheckField
                  label="Autoimmune history"
                  checked={!!patientFactors.autoimmune_history}
                  onChange={() => toggleFactor("autoimmune_history")}
                />
                <CheckField
                  label="Allergy history"
                  checked={!!patientFactors.allergy_history}
                  onChange={() => toggleFactor("allergy_history")}
                />
                <CheckField
                  label="Vascular disease"
                  checked={!!patientFactors.vascular_disease}
                  onChange={() => toggleFactor("vascular_disease")}
                />
                <CheckField
                  label="Smoker"
                  checked={!!patientFactors.smoking}
                  onChange={() => toggleFactor("smoking")}
                />
                <div className="pt-1 border-t border-slate-100">
                  <CheckField
                    label="GLP-1 medication (semaglutide / tirzepatide)"
                    desc="Ozempic, Wegovy, Mounjaro — affects facial fat distribution and volume planning"
                    checked={!!patientFactors.glp1_patient}
                    onChange={() => toggleFactor("glp1_patient")}
                  />
                </div>
              </div>
            </div>

            {formError && (
              <p className="text-sm text-red-600 bg-red-50 rounded-lg px-4 py-2.5 border border-red-200">{formError}</p>
            )}

            <button
              data-testid="button-run-safety-check"
              onClick={handleRunCheck}
              disabled={safetyMutation.isPending}
              className="w-full bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-white font-semibold rounded-xl py-3 text-sm transition-colors flex items-center justify-center gap-2 shadow-md"
            >
              {safetyMutation.isPending ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Running safety check…
                </>
              ) : (
                <>
                  <ShieldAlert className="w-4 h-4" />
                  Run Pre-Procedure Safety Check
                </>
              )}
            </button>
          </div>

          {/* ── Results ───────────────────────────────────────────────── */}
          <div className="lg:col-span-3 space-y-4">

            {!result && !safetyMutation.isPending && (
              <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-12 flex flex-col items-center justify-center text-center gap-3">
                <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center">
                  <ShieldAlert className="w-6 h-6 text-slate-400" />
                </div>
                <p className="text-sm font-medium text-slate-500">Complete the form to run a safety assessment</p>
                <p className="text-xs text-slate-400 max-w-xs">
                  AesthetiCite will return a decision badge, risk score, danger zones, ultrasound guidance flags, and evidence-based mitigation steps.
                </p>
              </div>
            )}

            {safetyMutation.isPending && (
              <div className="bg-white rounded-2xl border border-slate-200 p-12 flex flex-col items-center gap-4">
                <div className="w-10 h-10 border-[3px] border-slate-200 border-t-slate-700 rounded-full animate-spin" />
                <p className="text-sm text-slate-500">Analysing procedure risk…</p>
              </div>
            )}

            {result && (
              <>
                {(() => {
                  const cfg = decisionConfig(result.safety_assessment.decision);
                  return (
                    <div className={`rounded-2xl border-2 ${cfg.border} ${cfg.bg} p-5`}>
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-center gap-3">
                          <div className={`w-10 h-10 rounded-xl ${cfg.badgeBg} flex items-center justify-center text-white`}>
                            {cfg.icon}
                          </div>
                          <div>
                            <div className={`text-xl font-black tracking-tight ${cfg.text}`}>
                              {cfg.label}
                            </div>
                            <p className={`text-xs mt-0.5 ${cfg.text} opacity-80`}>
                              {result.safety_assessment.decision === "go"
                                ? "Proceed with standard precautions"
                                : result.safety_assessment.decision === "caution"
                                ? "Proceed with enhanced vigilance"
                                : "Elevated risk — enhanced prep required"}
                            </p>
                          </div>
                        </div>
                        <RiskGauge
                          score={result.safety_assessment.overall_risk_score}
                          level={result.safety_assessment.overall_risk_level}
                        />
                      </div>
                      <p className={`text-xs mt-3 leading-relaxed ${cfg.text} opacity-90`}>
                        {result.safety_assessment.rationale}
                      </p>
                    </div>
                  );
                })()}

                {shouldShowUltrasound && (
                  <UltrasoundBanner note={result.procedure_insight.ultrasound_note} />
                )}

                {patientFactors.glp1_patient && <Glp1Banner />}

                <BiostimulatorCard product={productType} />

                {result.caution_flags.length > 0 && (
                  <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Caution Flags</h3>
                    <div className="space-y-1.5">
                      {result.caution_flags.map((flag, i) => (
                        <div key={i} className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
                          <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                          {flag}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
                  <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Top Complication Risks</h3>
                  <div className="space-y-3">
                    {result.top_risks.map((risk, i) => (
                      <div key={i}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-semibold text-slate-700 capitalize">{risk.complication}</span>
                          <span className={`text-xs font-bold ${riskColor(risk.risk_level)}`}>
                            {risk.risk_score}/100
                          </span>
                        </div>
                        <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${riskBarColor(risk.risk_level)}`}
                            style={{ width: `${risk.risk_score}%` }}
                          />
                        </div>
                        <p className="text-xs text-slate-500 mt-1">{risk.why_it_matters}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
                  <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Procedure Intelligence</h3>
                  {result.procedure_insight.likely_plane_or_target && (
                    <p className="text-xs text-slate-600 mb-3 bg-slate-50 rounded-lg px-3 py-2">
                      <span className="font-semibold">Plane / Target:</span> {result.procedure_insight.likely_plane_or_target}
                    </p>
                  )}
                  {result.procedure_insight.danger_zones.length > 0 && (
                    <div className="mb-3">
                      <p className="text-xs font-semibold text-red-600 mb-1.5">⚠ Danger Zones</p>
                      <div className="flex flex-wrap gap-1.5">
                        {result.procedure_insight.danger_zones.map((dz, i) => (
                          <span key={i} className="text-xs bg-red-50 border border-red-200 text-red-700 rounded-md px-2 py-1">
                            {dz}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {result.procedure_insight.technical_notes.length > 0 && (
                    <div className="space-y-1.5">
                      {result.procedure_insight.technical_notes.map((note, i) => (
                        <div key={i} className="flex items-start gap-2 text-xs text-slate-600">
                          <ChevronRight className="w-3 h-3 flex-shrink-0 mt-0.5 text-slate-400" />
                          {note}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
                  <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Mitigation Steps</h3>
                  <ol className="space-y-2">
                    {result.mitigation_steps.map((step, i) => (
                      <li key={i} className="flex items-start gap-2.5 text-xs text-slate-700">
                        <span className="flex-shrink-0 w-5 h-5 rounded-full bg-slate-100 text-slate-500 font-bold flex items-center justify-center text-[10px]">
                          {i + 1}
                        </span>
                        {step}
                      </li>
                    ))}
                  </ol>
                </div>

                {result.evidence.length > 0 && (
                  <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                      <Eye className="w-3 h-3" />
                      Supporting Evidence
                    </h3>
                    <div className="space-y-3">
                      {result.evidence.map((ev, i) => (
                        <div key={i} className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2.5">
                          <div className="flex items-start justify-between gap-2">
                            <p className="text-xs font-semibold text-slate-700">{ev.title}</p>
                            {ev.source_type && (
                              <span className="text-[10px] bg-slate-200 text-slate-600 rounded px-1.5 py-0.5 flex-shrink-0">{ev.source_type}</span>
                            )}
                          </div>
                          <p className="text-xs text-slate-500 mt-1">{ev.note}</p>
                          {ev.citation_text && (
                            <p className="text-xs text-slate-400 italic mt-1">"{ev.citation_text}"</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-between gap-3 bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
                  <p className="text-[10px] text-slate-400 leading-relaxed max-w-sm">
                    {result.disclaimer}
                  </p>
                  <button
                    data-testid="button-export-pdf"
                    onClick={handleExportPDF}
                    className="flex-shrink-0 flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold rounded-xl px-4 py-2.5 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Export PDF
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════ */}
      {/*  TAB 2: COMPLICATION DIFFERENTIAL MODE                            */}
      {/* ══════════════════════════════════════════════════════════════════ */}

      {activeTab === "differential" && (
        <div className="mx-auto max-w-5xl px-4 py-6 grid grid-cols-1 lg:grid-cols-5 gap-6">

          <div className="lg:col-span-2 space-y-4">
            <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
              <div className="flex items-center gap-2 mb-1">
                <Microscope className="w-4 h-4 text-slate-600" />
                <h2 className="text-sm font-bold text-slate-800">Complication Differential</h2>
              </div>
              <p className="text-xs text-slate-500 mb-4 leading-relaxed">
                Enter the clinical presentation. AesthetiCite will return a ranked differential with immediate action steps — the "Sherlock Holmes" complication framework from CMAC 2025.
              </p>
              <div className="space-y-3">
                <SelectField
                  label="Onset"
                  value={diffSymptoms.onset}
                  onChange={v => setDiffSymptoms(p => ({ ...p, onset: v }))}
                  options={[
                    { value: "immediate", label: "Immediate (during injection)" },
                    { value: "minutes after", label: "Minutes after" },
                    { value: "hours after", label: "Hours after" },
                    { value: "days after", label: "Days after procedure" },
                    { value: "weeks after", label: "Weeks after procedure" },
                    { value: "months after", label: "Months after procedure" },
                  ]}
                  placeholder="Select onset timing"
                />
                <SelectField
                  label="Appearance"
                  value={diffSymptoms.appearance}
                  onChange={v => setDiffSymptoms(p => ({ ...p, appearance: v }))}
                  options={[
                    { value: "pale/blanching/white", label: "Pale / Blanching / White" },
                    { value: "mottled/livedo", label: "Mottled / Livedo pattern" },
                    { value: "red/erythema/warm", label: "Red / Erythema / Warm" },
                    { value: "lump/nodule/firm", label: "Lump / Nodule / Firm" },
                    { value: "blue/grey/discolour", label: "Blue-grey Discolouration" },
                    { value: "itch/urticarial/rash", label: "Itch / Urticaria / Rash" },
                    { value: "pus/discharge", label: "Pus / Discharge" },
                    { value: "swelling/oedema", label: "Swelling / Oedema (expected)" },
                  ]}
                  placeholder="Select appearance"
                />
                <SelectField
                  label="Pain Character"
                  value={diffSymptoms.pain}
                  onChange={v => setDiffSymptoms(p => ({ ...p, pain: v }))}
                  options={[
                    { value: "severe/intense", label: "Severe / Intense" },
                    { value: "burning", label: "Burning" },
                    { value: "throbbing", label: "Throbbing" },
                    { value: "mild/tender", label: "Mild / Tender" },
                    { value: "none", label: "None / Asymptomatic" },
                  ]}
                  placeholder="Select pain character"
                />
                <TextInputField
                  label="Location"
                  value={diffSymptoms.location}
                  onChange={v => setDiffSymptoms(p => ({ ...p, location: v }))}
                  placeholder="e.g. nose tip, tear trough, lip"
                />
                <SelectField
                  label="Product Used"
                  value={diffSymptoms.product_used}
                  onChange={v => setDiffSymptoms(p => ({ ...p, product_used: v }))}
                  options={[
                    { value: "ha filler", label: "HA Filler" },
                    { value: "caha radiesse", label: "CaHA (Radiesse)" },
                    { value: "sculptra plla", label: "PLLA (Sculptra)" },
                    { value: "botulinum toxin", label: "Botulinum Toxin" },
                    { value: "unknown", label: "Unknown" },
                  ]}
                  placeholder="Select product"
                />
                <SelectField
                  label="Time Since Injection"
                  value={diffSymptoms.time_since_injection}
                  onChange={v => setDiffSymptoms(p => ({ ...p, time_since_injection: v }))}
                  options={[
                    { value: "immediate", label: "Immediate (during/minutes)" },
                    { value: "hours", label: "Hours" },
                    { value: "days", label: "Days" },
                    { value: "weeks", label: "Weeks" },
                    { value: "months", label: "Months" },
                  ]}
                  placeholder="Select timeframe"
                />
              </div>
            </div>

            <button
              data-testid="button-generate-differential"
              onClick={handleRunDifferential}
              className="w-full bg-slate-800 hover:bg-slate-700 text-white font-semibold rounded-xl py-3 text-sm transition-colors flex items-center justify-center gap-2"
            >
              <Microscope className="w-4 h-4" />
              Generate Differential
            </button>
          </div>

          {/* ── Differential results ──────────────────────────────────── */}
          <div className="lg:col-span-3 space-y-4">

            {!diffRun && (
              <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-12 flex flex-col items-center text-center gap-3">
                <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center">
                  <Microscope className="w-6 h-6 text-slate-400" />
                </div>
                <p className="text-sm font-medium text-slate-500">Enter symptoms to generate a ranked complication differential</p>
                <p className="text-xs text-slate-400 max-w-xs">
                  Based on the structured complication framework presented at CMAC 2025 — onset, appearance, pain, and timing layered to surface the most likely diagnosis.
                </p>
              </div>
            )}

            {diffRun && differentials.map((diff) => (
              <div key={diff.rank} className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
                  <div className="flex items-center gap-2.5">
                    <span className="w-6 h-6 rounded-full bg-slate-100 text-slate-500 text-xs font-bold flex items-center justify-center">
                      {diff.rank}
                    </span>
                    <h3 className="text-sm font-bold text-slate-800">{diff.diagnosis}</h3>
                  </div>
                  <span className={`text-xs font-semibold border rounded-full px-2.5 py-1 ${probColor(diff.probability)}`}>
                    {diff.probability.toUpperCase()} probability
                  </span>
                </div>

                <div className="px-5 py-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Key Clues</p>
                    <ul className="space-y-1">
                      {diff.key_clues.map((c, i) => (
                        <li key={i} className="text-xs text-slate-600 flex items-start gap-1.5">
                          <span className="text-slate-300 flex-shrink-0">•</span>{c}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <p className="text-[10px] font-bold text-red-400 uppercase tracking-wider mb-2">Immediate Actions</p>
                    <ul className="space-y-1">
                      {diff.immediate_actions.map((a, i) => (
                        <li key={i} className="text-xs text-slate-700 flex items-start gap-1.5">
                          <ChevronRight className="w-3 h-3 flex-shrink-0 mt-0.5 text-red-400" />{a}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Rule Out</p>
                    <ul className="space-y-1">
                      {diff.rule_out.map((r, i) => (
                        <li key={i} className="text-xs text-slate-500 flex items-start gap-1.5">
                          <span className="text-slate-300 flex-shrink-0">↳</span>{r}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ))}

            {diffRun && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-xs text-amber-700">
                <span className="font-semibold">Clinical reminder:</span> This differential is decision support, not a substitute for clinical assessment. In any post-filler concern, treat as vascular occlusion until proven otherwise. Use ultrasound if available to differentiate.
              </div>
            )}
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════ */}
      {/*  TAB 3: PRE-SCAN BRIEFING                                        */}
      {/* ══════════════════════════════════════════════════════════════════ */}

      {activeTab === "prescan" && (
        <div className="mx-auto max-w-5xl px-4 py-6 grid grid-cols-1 lg:grid-cols-5 gap-6">

          {/* Form */}
          <div className="lg:col-span-2 space-y-4">
            <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
              <div className="flex items-center gap-2 mb-1">
                <Waves className="w-4 h-4 text-sky-600" />
                <h2 className="text-sm font-bold text-slate-800">Pre-Scan Briefing</h2>
              </div>
              <p className="text-xs text-slate-500 mb-4 leading-relaxed">
                Before using your ultrasound, AesthetiCite tells you exactly which structures
                to identify, safe injection windows, and abort criteria for the selected region.
                Based on RSNA 2025 and J Cosm Dermatology 2025 protocols.
              </p>

              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                    Injection Region *
                  </label>
                  <select
                    value={prescanRegion}
                    onChange={e => setPrescanRegion(e.target.value)}
                    data-testid="select-prescan-region"
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 transition-all"
                  >
                    <option value="">Select region</option>
                    <option value="nose">Nose / Nasal Dorsum</option>
                    <option value="temple">Temple / Temporal Hollow</option>
                    <option value="forehead">Forehead / Frontal</option>
                    <option value="tear trough">Tear Trough / Periorbital</option>
                    <option value="glabella">Glabella / Frown Lines</option>
                    <option value="nasolabial fold">Nasolabial Fold</option>
                    <option value="lip">Lip / Perioral</option>
                    <option value="jawline">Jawline / Chin</option>
                    <option value="cheek">Cheek / Malar</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                    Injector Experience
                  </label>
                  <select
                    value={prescanExperience}
                    onChange={e => setPrescanExperience(e.target.value)}
                    data-testid="select-prescan-experience"
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 transition-all"
                  >
                    <option value="">Select level</option>
                    <option value="junior">Junior (&lt; 2 years)</option>
                    <option value="intermediate">Intermediate (2–5 years)</option>
                    <option value="senior">Senior (5+ years)</option>
                  </select>
                </div>
              </div>
            </div>

            {prescanError && (
              <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {prescanError}
              </p>
            )}

            <button
              onClick={handleRunPrescan}
              disabled={prescanLoading}
              data-testid="button-generate-prescan"
              className="w-full bg-sky-700 hover:bg-sky-600 disabled:opacity-50 text-white font-semibold rounded-xl py-3 text-sm transition-colors flex items-center justify-center gap-2"
            >
              {prescanLoading ? (
                <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Generating briefing…</>
              ) : (
                <><Waves className="w-4 h-4" />Generate Pre-Scan Briefing</>
              )}
            </button>
          </div>

          {/* Results */}
          <div className="lg:col-span-3 space-y-4">

            {!prescanResult && !prescanLoading && (
              <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-12 flex flex-col items-center text-center gap-3">
                <div className="w-12 h-12 rounded-full bg-sky-50 flex items-center justify-center">
                  <Waves className="w-6 h-6 text-sky-400" />
                </div>
                <p className="text-sm font-medium text-slate-500">Select a region to generate your pre-scan checklist</p>
                <p className="text-xs text-slate-400 max-w-xs">
                  AesthetiCite will tell you which structures to identify before injection,
                  Doppler settings, safe injection windows, and abort criteria.
                </p>
              </div>
            )}

            {prescanLoading && (
              <div className="bg-white rounded-2xl border border-slate-200 p-12 flex flex-col items-center gap-4">
                <div className="w-10 h-10 border-2 border-sky-200 border-t-sky-600 rounded-full animate-spin" />
                <p className="text-sm text-slate-500">Generating ultrasound briefing…</p>
              </div>
            )}

            {prescanResult && (
              <>
                {/* Header card */}
                <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-base font-black text-slate-800">{prescanResult.region_label}</h3>
                      <p className="text-xs text-slate-500 mt-0.5">Pre-scan ultrasound briefing</p>
                    </div>
                    <span className={`text-xs font-bold border rounded-lg px-3 py-1.5 ${
                      prescanResult.risk_level === "very_high" ? "text-red-700 bg-red-50 border-red-200"
                      : prescanResult.risk_level === "high" ? "text-red-600 bg-red-50 border-red-100"
                      : prescanResult.risk_level === "moderate" ? "text-amber-700 bg-amber-50 border-amber-200"
                      : "text-emerald-700 bg-emerald-50 border-emerald-200"
                    }`}>
                      {prescanResult.risk_level.replace("_", " ").toUpperCase()} RISK
                    </span>
                  </div>
                  {/* Doppler settings */}
                  <div className="mt-3 bg-sky-50 border border-sky-200 rounded-xl px-3 py-2.5">
                    <p className="text-[10px] font-bold text-sky-600 uppercase tracking-wider mb-1">Doppler Settings</p>
                    <p className="text-xs text-sky-800">{prescanResult.doppler_settings}</p>
                  </div>
                </div>

                {/* Structures to identify */}
                <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
                  <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
                    Structures to Identify
                  </h4>
                  <ul className="space-y-2">
                    {prescanResult.structures_to_identify.map((s: string, i: number) => (
                      <li key={i} className="flex items-start gap-2.5 text-xs text-slate-700">
                        <span className="flex-shrink-0 w-5 h-5 rounded-full bg-slate-100 text-slate-500 font-bold flex items-center justify-center text-[10px]">
                          {i + 1}
                        </span>
                        {s}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Key findings + Safe windows — 2 col */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
                      Document These Findings
                    </h4>
                    <ul className="space-y-1.5">
                      {prescanResult.key_findings_to_document.map((f: string, i: number) => (
                        <li key={i} className="flex items-start gap-2 text-xs text-slate-600">
                          <span className="text-slate-400 flex-shrink-0">›</span>{f}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="bg-emerald-50 rounded-2xl border border-emerald-200 p-4">
                    <h4 className="text-xs font-bold text-emerald-600 uppercase tracking-wider mb-3">
                      Safe Injection Windows
                    </h4>
                    <ul className="space-y-1.5">
                      {prescanResult.safe_windows.map((w: string, i: number) => (
                        <li key={i} className="flex items-start gap-2 text-xs text-emerald-800">
                          <span className="text-emerald-500 flex-shrink-0">✓</span>{w}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Abort criteria */}
                <div className="bg-red-50 rounded-2xl border border-red-200 p-4">
                  <h4 className="text-xs font-bold text-red-600 uppercase tracking-wider mb-3">
                    Abort Criteria — Do Not Inject If:
                  </h4>
                  <ul className="space-y-1.5">
                    {prescanResult.abort_criteria.map((c: string, i: number) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-red-700">
                        <span className="flex-shrink-0 font-bold">✗</span>{c}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Junior note */}
                {prescanResult.junior_note && (
                  <div className="bg-violet-50 rounded-xl border border-violet-200 px-4 py-3">
                    <p className="text-xs text-violet-700">{prescanResult.junior_note}</p>
                  </div>
                )}

                {/* Evidence note */}
                <div className="bg-slate-50 rounded-xl border border-slate-200 px-4 py-3">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Evidence Base</p>
                  <p className="text-xs text-slate-600">{prescanResult.evidence_note}</p>
                </div>

                {/* Disclaimer */}
                <p className="text-[10px] text-slate-400 leading-relaxed px-1">
                  {prescanResult.disclaimer}
                </p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
