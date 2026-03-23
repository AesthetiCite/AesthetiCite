/**
 * AesthetiCite — Aesthetic Drug Interactions
 * ============================================
 * Drop into: client/src/pages/drug-interactions.tsx
 * Route:     /drug-interactions  (already registered in App.tsx)
 *
 * Replaces the existing drug interactions page with a full
 * aesthetic-medicine-specific drug interaction checker.
 *
 * Drug database sourced from:
 * - Clinical pharmacology of aesthetic injectables
 * - IAPAM 2025/2026 — GLP-1 impact on aesthetic medicine
 * - Anticoagulation guidance for elective aesthetic procedures
 * - CMAC 2025 — drug interactions in aesthetic practice
 */

import { useState, useMemo } from "react";
import { Link } from "wouter";
import {
  Pill, ArrowLeft, AlertTriangle, CheckCircle2, XCircle,
  ChevronRight, Search, Info, Activity
} from "lucide-react";

// ─── Drug interaction database ────────────────────────────────────────────────

type Severity = "contraindicated" | "high" | "moderate" | "low" | "monitor";

interface DrugInteraction {
  drug: string;
  drug_class: string;
  common_brands: string[];
  severity: Severity;
  mechanism: string;
  aesthetic_impact: string;
  procedure_specific: string[];
  management: string;
  timing_note?: string;
  glp1_specific?: boolean;
}

const AESTHETIC_DRUG_DB: DrugInteraction[] = [
  // ── Anticoagulants ────────────────────────────────────────────────────────
  {
    drug: "Warfarin",
    drug_class: "Anticoagulant (vitamin K antagonist)",
    common_brands: ["Coumadin", "Warfin"],
    severity: "high",
    mechanism: "Inhibits vitamin K-dependent clotting factors II, VII, IX, X. Prolongs PT/INR.",
    aesthetic_impact: "Significantly increased bruising, haematoma formation, and bleeding risk at injection sites. Ecchymosis may be extensive and slow to resolve.",
    procedure_specific: ["Dermal filler", "Botulinum toxin", "Thread lift", "PRP"],
    management: "Discuss with prescribing physician before proceeding. Do not stop warfarin without medical authorisation. If proceeding: use cannula technique, minimal passes, firm compression. Confirm INR is within therapeutic range. Ensure patient is counselled on bruising expectations.",
    timing_note: "Do not recommend stopping without medical supervision. Stopping warfarin carries thromboembolic risk.",
  },
  {
    drug: "Apixaban (Eliquis)",
    drug_class: "Direct oral anticoagulant (DOAC) — Factor Xa inhibitor",
    common_brands: ["Eliquis"],
    severity: "high",
    mechanism: "Directly inhibits Factor Xa, reducing thrombin generation. No reliable antidote for reversal in aesthetic settings.",
    aesthetic_impact: "Increased bruising and haematoma risk. Unlike warfarin, no INR monitoring — cannot quantify anticoagulant effect easily.",
    procedure_specific: ["Dermal filler", "Botulinum toxin", "Thread lift"],
    management: "Discuss with prescribing physician. Do NOT advise stopping without medical guidance — carries AF/DVT/PE risk. If patient must proceed: use cannula where possible, apply prolonged compression, use smallest effective needle gauge.",
    timing_note: "Peak effect 3–4 hours post-dose. Avoid injecting at peak if clinically feasible.",
  },
  {
    drug: "Rivaroxaban (Xarelto)",
    drug_class: "Direct oral anticoagulant (DOAC) — Factor Xa inhibitor",
    common_brands: ["Xarelto"],
    severity: "high",
    mechanism: "Direct Factor Xa inhibition. Once-daily dosing creates a predictable concentration curve.",
    aesthetic_impact: "Bruising and bleeding risk elevated. Haematoma risk especially for filler and threading procedures.",
    procedure_specific: ["Dermal filler", "Botulinum toxin", "Thread lift"],
    management: "Consult prescribing physician before elective aesthetic procedures. Once-daily: morning dose patient may have lower drug levels by afternoon — timing may help reduce bruising risk. Document patient is aware of increased bruising risk.",
    timing_note: "Consider injecting 12+ hours after last dose if prescribing physician is in agreement.",
  },
  {
    drug: "Dabigatran (Pradaxa)",
    drug_class: "Direct oral anticoagulant (DOAC) — Direct thrombin inhibitor",
    common_brands: ["Pradaxa"],
    severity: "high",
    mechanism: "Directly inhibits thrombin (Factor IIa). Renal elimination — renal impairment increases drug exposure.",
    aesthetic_impact: "Significant bruising and haematoma risk. Renal function affects drug clearance.",
    procedure_specific: ["Dermal filler", "Botulinum toxin", "Thread lift"],
    management: "Medical consultation required before elective procedures. Assess renal function in elderly patients. Use cannula technique, gentle approach, extended compression post-injection.",
    timing_note: "Peak effect 1–3 hours after dose. Some clinicians time injections to trough levels with prescriber agreement.",
  },

  // ── NSAIDs ────────────────────────────────────────────────────────────────
  {
    drug: "Ibuprofen / NSAIDs",
    drug_class: "Non-steroidal anti-inflammatory drug",
    common_brands: ["Nurofen", "Advil", "Brufen", "Naproxen", "Diclofenac"],
    severity: "low",
    mechanism: "Reversible platelet aggregation inhibition via COX-1 inhibition. Effect lasts duration of drug (not irreversible like aspirin).",
    aesthetic_impact: "Mild increase in bruising risk. Effect wears off as drug clears.",
    procedure_specific: ["Dermal filler", "Botulinum toxin"],
    management: "Advise patients to avoid NSAIDs 5–7 days before elective filler procedures if possible. If patient has taken NSAIDs recently, proceed with awareness of mild bleeding risk and counsel on bruising. Do not stop if prescribed for chronic pain without GP guidance.",
    timing_note: "Effect resolves with drug elimination (t½ varies: ibuprofen ~2h, naproxen ~12–17h).",
  },
  {
    drug: "Aspirin (low-dose)",
    drug_class: "Antiplatelet — irreversible COX-1 inhibitor",
    common_brands: ["Aspirin 75mg", "Cardiprin", "Disprin"],
    severity: "moderate",
    mechanism: "Irreversibly inhibits platelet COX-1. Effect lasts platelet lifespan (~7–10 days) until new platelets produced.",
    aesthetic_impact: "Increased bruising, especially with filler and threading. Cannot be reversed quickly — effect persists until platelet turnover.",
    procedure_specific: ["Dermal filler", "Thread lift", "PRP"],
    management: "If aspirin is prescribed for cardiovascular protection (secondary prevention) — do NOT stop without cardiologist or GP approval. Stopping carries genuine MI/stroke risk. Proceed with procedure: use cannula, compression, and counsel on bruising. If aspirin is self-prescribed for general analgesia — advise stopping 10 days pre-procedure.",
    timing_note: "Irreversible — effect persists ~10 days. Only resolves as new platelets replace old ones.",
  },
  {
    drug: "Clopidogrel (Plavix)",
    drug_class: "Antiplatelet — P2Y12 inhibitor",
    common_brands: ["Plavix", "Iscover"],
    severity: "high",
    mechanism: "Irreversibly inhibits ADP-induced platelet aggregation. Used after MI, stroke, coronary stent.",
    aesthetic_impact: "Significant bleeding and haematoma risk. Stopping is almost never appropriate in aesthetic practice — risk of stent thrombosis is life-threatening.",
    procedure_specific: ["Dermal filler", "Thread lift"],
    management: "Do NOT stop clopidogrel. Consult with cardiology if there is any clinical concern. Proceed with maximum haemostatic care: cannula technique, minimal passes, prolonged firm compression. Advise patient of significant bruising risk and document consent.",
    timing_note: "Effect irreversible for platelet lifespan. Stopping for any elective aesthetic procedure is rarely appropriate.",
  },

  // ── SSRIs / SNRIs ─────────────────────────────────────────────────────────
  {
    drug: "SSRIs (Fluoxetine, Sertraline, Escitalopram, Paroxetine)",
    drug_class: "Selective serotonin reuptake inhibitor",
    common_brands: ["Prozac", "Zoloft", "Cipralex", "Seroxat", "Citalopram"],
    severity: "low",
    mechanism: "Serotonin depletion in platelets reduces platelet aggregation response. Effect is mild but additive with other antiplatelet agents.",
    aesthetic_impact: "Mildly increased bruising risk. More clinically relevant when combined with NSAIDs or anticoagulants.",
    procedure_specific: ["Dermal filler", "Botulinum toxin"],
    management: "No need to stop SSRIs for aesthetic procedures. Advise patient of mild bruising potential. Particularly important to flag if patient is ALSO on aspirin or NSAIDs — additive bleeding risk. Document medications at consultation.",
    timing_note: "Effect is ongoing during treatment — not dose-timing dependent for aesthetic procedures.",
  },
  {
    drug: "SNRIs (Venlafaxine, Duloxetine)",
    drug_class: "Serotonin-norepinephrine reuptake inhibitor",
    common_brands: ["Effexor", "Cymbalta"],
    severity: "low",
    mechanism: "Similar platelet serotonin depletion to SSRIs. Mild antiplatelet effect.",
    aesthetic_impact: "Mild bruising risk increase. Clinically low significance unless combined with other agents.",
    procedure_specific: ["Dermal filler"],
    management: "Do not stop. Counsel on mild bruising potential. Flag additive risk if other antiplatelet or anticoagulant agents also present.",
  },

  // ── GLP-1 ─────────────────────────────────────────────────────────────────
  {
    drug: "Semaglutide (Ozempic / Wegovy)",
    drug_class: "GLP-1 receptor agonist",
    common_brands: ["Ozempic", "Wegovy", "Rybelsus"],
    severity: "moderate",
    mechanism: "GLP-1 agonism causes significant weight loss through appetite suppression and reduced gastric emptying. Rapid fat loss affects facial anatomy.",
    aesthetic_impact: "Rapid and significant facial fat loss changes volume distribution, tissue planes, and structural support. Standard filler volumes may overcorrect. 'Ozempic face' describes temporal hollowing, jowling, and loss of mid-face volume in rapid weight-loss patients. Skin laxity may be disproportionate to age.",
    procedure_specific: ["Dermal filler", "Thread lift", "Botulinum toxin"],
    management: "Reassess facial anatomy at each consultation — it may change between appointments. Reduce filler volumes from prior treatment plans. Consider structural support (collagen stimulators) alongside HA filler. Discuss skin laxity management. Allow weight to stabilise before complex volumisation. Document GLP-1 status at each appointment.",
    timing_note: "Effects are ongoing during treatment. Anatomy may continue to change month-to-month.",
    glp1_specific: true,
  },
  {
    drug: "Tirzepatide (Mounjaro / Zepbound)",
    drug_class: "GLP-1 / GIP dual receptor agonist",
    common_brands: ["Mounjaro", "Zepbound"],
    severity: "moderate",
    mechanism: "Dual GLP-1/GIP agonism produces more rapid and pronounced weight loss than GLP-1 monotherapy. More significant body composition change.",
    aesthetic_impact: "More pronounced facial volume loss than semaglutide in some patients. Same anatomical considerations apply — particularly temporal and mid-face hollowing, jowling, skin laxity.",
    procedure_specific: ["Dermal filler", "Thread lift", "Botulinum toxin", "Energy-based device"],
    management: "Same principles as semaglutide but may require more frequent reassessment due to more rapid weight loss. Strongly advise against aggressive volumisation while weight is actively declining — results will become outdated quickly. Collagen biostimulators may provide longer-lasting support than HA during active weight loss phase.",
    timing_note: "Particularly active weight loss during dose escalation phase (first 6 months). Plan conservatively during this period.",
    glp1_specific: true,
  },
  {
    drug: "Liraglutide (Victoza / Saxenda)",
    drug_class: "GLP-1 receptor agonist",
    common_brands: ["Victoza", "Saxenda"],
    severity: "low",
    mechanism: "Older GLP-1 agonist with lower weight-loss efficacy than semaglutide or tirzepatide.",
    aesthetic_impact: "Modest facial volume changes. Less dramatic than newer agents but same anatomical principles apply.",
    procedure_specific: ["Dermal filler"],
    management: "Document at consultation. Reassess volume needs. Counsel on ongoing change if weight loss is still occurring.",
    glp1_specific: true,
  },

  // ── Immunosuppressants ────────────────────────────────────────────────────
  {
    drug: "Methotrexate",
    drug_class: "Immunosuppressant / DMARD",
    common_brands: ["Methofar", "Matrex"],
    severity: "high",
    mechanism: "Folic acid antagonist causing immunosuppression. Impairs wound healing and infection response.",
    aesthetic_impact: "Significantly impaired wound healing, infection risk, and tissue repair. Filler complications may be harder to manage. Contraindicated for most elective injectable procedures without specialist clearance.",
    procedure_specific: ["Dermal filler", "Thread lift", "PRP"],
    management: "Obtain specialist clearance from rheumatologist or dermatologist before proceeding. Avoid thread lifts. For filler: assess on case-by-case basis with treating physician agreement. Document immunosuppression status carefully.",
  },
  {
    drug: "Biologics (Adalimumab, Etanercept, Ustekinumab)",
    drug_class: "Biologic immunosuppressant",
    common_brands: ["Humira", "Enbrel", "Stelara"],
    severity: "moderate",
    mechanism: "TNF-alpha or IL inhibition causing systemic immunosuppression. Infection risk increased, wound healing may be impaired.",
    aesthetic_impact: "Risk of injection-site infection and impaired healing. Filler nodules and granulomas may present atypically or be more difficult to resolve.",
    procedure_specific: ["Dermal filler", "Thread lift"],
    management: "Proceed with caution. Consider timing injections mid-cycle (between biologic doses) when immunosuppression is lowest. Inform patient of elevated infection risk. Avoid thread lift procedures. Monitor closely for any signs of infection post-treatment.",
  },

  // ── Corticosteroids ───────────────────────────────────────────────────────
  {
    drug: "Systemic Corticosteroids (Prednisolone etc.)",
    drug_class: "Systemic corticosteroid",
    common_brands: ["Prednisolone", "Prednisone", "Dexamethasone"],
    severity: "moderate",
    mechanism: "Prolonged use causes skin atrophy, impaired wound healing, and immune suppression.",
    aesthetic_impact: "Skin thinning, fragility, and impaired healing. Filler may behave unexpectedly in atrophic skin. Infection risk elevated.",
    procedure_specific: ["Dermal filler", "Thread lift"],
    management: "Assess skin condition carefully before injection. Reduce volumes. Avoid threading in thin or atrophic skin. Discuss with prescribing physician if high-dose or prolonged systemic steroids.",
  },

  // ── Retinoids ─────────────────────────────────────────────────────────────
  {
    drug: "Isotretinoin (Roaccutane)",
    drug_class: "Systemic retinoid",
    common_brands: ["Roaccutane", "Accutane", "Oratane"],
    severity: "high",
    mechanism: "Causes significant skin changes — sebaceous gland suppression, altered wound healing, skin fragility. Effects persist beyond cessation.",
    aesthetic_impact: "Thread lift and surgical procedures carry significantly elevated scarring and healing risk during and after isotretinoin. Filler placement is generally considered safer but some clinicians still advise caution.",
    procedure_specific: ["Thread lift", "Laser resurfacing", "Dermal filler"],
    management: "Thread lifts and resurfacing: defer 12 months after completing isotretinoin. Filler: many practitioners proceed with caution during treatment or within 6 months — no high-quality evidence mandates delay for filler alone, but document discussion. Always check local guidelines.",
    timing_note: "Wound healing and skin properties may remain altered for months after stopping.",
  },
];

// ─── Severity config ──────────────────────────────────────────────────────────

function severityConfig(s: Severity) {
  const configs = {
    contraindicated: { label: "Contraindicated", bg: "bg-red-600", text: "text-white", border: "border-red-600", badge: "bg-red-100 text-red-700 border-red-200" },
    high: { label: "High Risk", bg: "bg-red-500", text: "text-white", border: "border-red-400", badge: "bg-red-100 text-red-700 border-red-200" },
    moderate: { label: "Moderate", bg: "bg-amber-400", text: "text-white", border: "border-amber-400", badge: "bg-amber-100 text-amber-700 border-amber-200" },
    low: { label: "Low Risk", bg: "bg-slate-400", text: "text-white", border: "border-slate-300", badge: "bg-slate-100 text-slate-600 border-slate-200" },
    monitor: { label: "Monitor", bg: "bg-sky-400", text: "text-white", border: "border-sky-400", badge: "bg-sky-100 text-sky-700 border-sky-200" },
  };
  return configs[s] || configs.monitor;
}

const CLASS_GROUPS = [
  { label: "All", value: "" },
  { label: "Anticoagulants", value: "Anticoagulant" },
  { label: "Antiplatelets", value: "Antiplatelet" },
  { label: "NSAIDs", value: "Non-steroidal" },
  { label: "SSRIs / SNRIs", value: "reuptake inhibitor" },
  { label: "GLP-1 / Weight Loss", value: "GLP-1" },
  { label: "Immunosuppressants", value: "mmuno" },
  { label: "Retinoids", value: "etinoid" },
];

// ─── Component ────────────────────────────────────────────────────────────────

export default function DrugInteractionsPage() {
  const [search, setSearch] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState<Severity | "">("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const filtered = useMemo(() => {
    return AESTHETIC_DRUG_DB.filter(d => {
      const q = search.toLowerCase();
      const matchesSearch = !q ||
        d.drug.toLowerCase().includes(q) ||
        d.drug_class.toLowerCase().includes(q) ||
        d.common_brands.some(b => b.toLowerCase().includes(q));
      const matchesClass = !classFilter || d.drug_class.toLowerCase().includes(classFilter.toLowerCase());
      const matchesSeverity = !severityFilter || d.severity === severityFilter;
      return matchesSearch && matchesClass && matchesSeverity;
    });
  }, [search, classFilter, severityFilter]);

  const glp1Drugs = AESTHETIC_DRUG_DB.filter(d => d.glp1_specific);

  return (
    <div className="min-h-screen bg-slate-50">

      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur-sm">
        <div className="mx-auto max-w-5xl px-4 py-3 flex items-center gap-3">
          <Link href="/ask" className="text-slate-400 hover:text-slate-600 transition-colors">
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-slate-800 flex items-center justify-center">
              <Pill className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-slate-800 leading-none">Drug Interactions</h1>
              <p className="text-[10px] text-slate-500 leading-none mt-0.5">Aesthetic Medicine — Injectable Safety</p>
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-6 space-y-5">

        {/* GLP-1 spotlight */}
        <div className="bg-orange-50 border border-orange-200 rounded-2xl p-4">
          <div className="flex items-start gap-3">
            <Activity className="w-5 h-5 text-orange-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-bold text-orange-800">GLP-1 Medications — 2025/2026 Priority Alert</p>
              <p className="text-xs text-orange-700 mt-1 leading-relaxed">
                Semaglutide (Ozempic/Wegovy) and tirzepatide (Mounjaro) are now among the most common
                patient medications seen in aesthetic clinics. IAPAM 2025 identified these as a major emerging
                factor affecting volume planning, facial anatomy, and treatment outcomes.
                Check the GLP-1 section below before treating any patient on weight-loss medication.
              </p>
              <div className="flex gap-2 mt-2">
                {glp1Drugs.map(d => (
                  <span key={d.drug} className="text-[10px] bg-orange-100 text-orange-700 border border-orange-200 rounded-full px-2 py-1">
                    {d.drug.split(" ")[0]}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm space-y-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search drug, class, or brand name…"
              className="w-full pl-9 pr-4 py-2.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 transition-all"
            />
          </div>

          {/* Class filter */}
          <div className="flex flex-wrap gap-1.5">
            {CLASS_GROUPS.map(g => (
              <button
                key={g.value}
                onClick={() => setClassFilter(classFilter === g.value ? "" : g.value)}
                className={`text-xs rounded-lg px-3 py-1.5 border transition-all ${
                  classFilter === g.value
                    ? "bg-slate-800 text-white border-slate-800"
                    : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
                }`}
              >
                {g.label}
              </button>
            ))}
          </div>

          {/* Severity filter */}
          <div className="flex gap-1.5">
            {(["high", "moderate", "low"] as Severity[]).map(s => {
              const cfg = severityConfig(s);
              return (
                <button
                  key={s}
                  onClick={() => setSeverityFilter(severityFilter === s ? "" : s)}
                  className={`text-xs rounded-lg px-3 py-1.5 border transition-all ${
                    severityFilter === s
                      ? `${cfg.bg} text-white border-transparent`
                      : `${cfg.badge} hover:opacity-80`
                  }`}
                >
                  {cfg.label}
                </button>
              );
            })}
          </div>

          <p className="text-xs text-slate-400">{filtered.length} drug{filtered.length !== 1 ? "s" : ""} shown</p>
        </div>

        {/* Drug cards */}
        <div className="space-y-3">
          {filtered.map(drug => {
            const cfg = severityConfig(drug.severity);
            const isOpen = expanded === drug.drug;

            return (
              <div
                key={drug.drug}
                className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden"
              >
                {/* Card header */}
                <button
                  onClick={() => setExpanded(isOpen ? null : drug.drug)}
                  className="w-full px-5 py-4 flex items-center justify-between gap-3 text-left hover:bg-slate-50 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.bg}`} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-sm font-bold text-slate-800">{drug.drug}</h3>
                        {drug.glp1_specific && (
                          <span className="text-[10px] bg-orange-100 text-orange-700 border border-orange-200 rounded-full px-2 py-0.5">
                            GLP-1
                          </span>
                        )}
                        <span className={`text-[10px] font-semibold border rounded-full px-2 py-0.5 ${cfg.badge}`}>
                          {cfg.label}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5 truncate">{drug.drug_class}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <div className="hidden sm:flex gap-1">
                      {drug.procedure_specific.slice(0, 2).map(p => (
                        <span key={p} className="text-[10px] bg-slate-100 text-slate-500 rounded px-1.5 py-0.5">
                          {p.split(" ")[0]}
                        </span>
                      ))}
                    </div>
                    {isOpen ? <ChevronRight className="w-4 h-4 text-slate-400 rotate-90" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                  </div>
                </button>

                {/* Expanded detail */}
                {isOpen && (
                  <div className="border-t border-slate-100 px-5 py-4 space-y-4">
                    {/* Brands */}
                    <div className="flex flex-wrap gap-1.5">
                      {drug.common_brands.map(b => (
                        <span key={b} className="text-xs bg-slate-100 text-slate-600 rounded-md px-2 py-1">
                          {b}
                        </span>
                      ))}
                    </div>

                    {/* Grid */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Mechanism</p>
                        <p className="text-xs text-slate-600 leading-relaxed">{drug.mechanism}</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Aesthetic Impact</p>
                        <p className="text-xs text-slate-600 leading-relaxed">{drug.aesthetic_impact}</p>
                      </div>
                    </div>

                    {/* Management */}
                    <div className={`rounded-xl px-4 py-3 border ${
                      drug.severity === "high" || drug.severity === "contraindicated"
                        ? "bg-red-50 border-red-200"
                        : drug.severity === "moderate"
                        ? "bg-amber-50 border-amber-200"
                        : "bg-slate-50 border-slate-200"
                    }`}>
                      <p className="text-[10px] font-bold uppercase tracking-wider mb-1.5 text-slate-500">Clinical Management</p>
                      <p className="text-xs text-slate-700 leading-relaxed">{drug.management}</p>
                    </div>

                    {/* Timing note */}
                    {drug.timing_note && (
                      <div className="flex items-start gap-2 bg-sky-50 border border-sky-200 rounded-lg px-3 py-2.5">
                        <Info className="w-3.5 h-3.5 text-sky-600 flex-shrink-0 mt-0.5" />
                        <p className="text-xs text-sky-700">{drug.timing_note}</p>
                      </div>
                    )}

                    {/* Procedures affected */}
                    <div>
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Procedures Affected</p>
                      <div className="flex flex-wrap gap-1.5">
                        {drug.procedure_specific.map(p => (
                          <span key={p} className="text-xs bg-slate-100 text-slate-600 border border-slate-200 rounded-md px-2.5 py-1">
                            {p}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {filtered.length === 0 && (
            <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-10 text-center">
              <Pill className="w-8 h-8 text-slate-300 mx-auto mb-2" />
              <p className="text-sm text-slate-400">No drugs match your filters</p>
            </div>
          )}
        </div>

        {/* Disclaimer */}
        <div className="bg-slate-100 rounded-xl px-4 py-3 flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 text-slate-500 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-slate-500 leading-relaxed">
            This drug interaction reference is for clinical decision support only.
            It does not replace prescribing guidance, pharmacist consultation, or clinical judgement.
            Never advise a patient to stop prescribed medication without consulting their prescribing physician.
            Some drug interactions carry life-threatening implications if management advice is not followed.
          </p>
        </div>
      </div>
    </div>
  );
}
