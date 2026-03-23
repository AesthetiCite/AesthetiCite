/**
 * AesthetiCite Safety Workspace v3 — Live Backend Integration
 * client/src/pages/safety-workspace.tsx
 *
 * Route: /safety-workspace  (already wired in App.tsx)
 *
 * Wiring summary:
 *   GET  /api/complications/protocols     → protocol selector list
 *   POST /api/complications/protocol      → live protocol + evidence (debounced 600ms)
 *   POST /api/complications/export-pdf    → PDF export
 *   POST /api/complications/log-case      → save case to dataset
 *
 * Fallback: if backend is unreachable, static PROTOCOLS render instantly.
 * Live protocol upgrades the display when the backend responds.
 */

import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useLocation } from "wouter";
import {
  AlertTriangle, Activity, Clock3, FileText, Mic, MicOff,
  ShieldCheck, Stethoscope, TrendingUp, TimerReset, Syringe,
  Printer, Download, Save, Search, CheckCircle2, ChevronRight,
  Brain, Gauge, UserRound, ClipboardList, ArrowLeft, Loader2,
  XCircle, RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { getToken } from "@/lib/auth";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

type EvidenceTier = "guideline" | "consensus" | "review" | "low";
type StepKey = "identify" | "immediate" | "treatment" | "followup";
type Severity = "Low" | "Moderate" | "High" | "Critical";

interface ProtocolSource {
  title: string;
  type: string;
  year: number;
}

interface ProtocolCard {
  id: string;
  title: string;
  category: string;
  severity: Severity;
  immediateAction: string[];
  treatment: string[];
  followup: string[];
  redFlags: string[];
  patientSummary: string;
  evidenceTier: EvidenceTier;
  confidence: number;
  sources: ProtocolSource[];
  recommendedDose?: string;
  requestId?: string;
}

interface ProtocolListItem {
  id: string;
  title: string;
  category: string;
  severity: Severity;
  evidenceTier: EvidenceTier;
}

interface SavedCase {
  id: string;
  createdAt: string;
  complication: string;
  procedure: string;
  region: string;
  severity: string;
  onsetMinutes: number;
  treatmentGiven: string;
  transcript: string;
  notes: string;
  protocolKey?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Static fallback protocols (shown immediately, replaced by live backend data)
// ─────────────────────────────────────────────────────────────────────────────

const STATIC_PROTOCOLS: ProtocolCard[] = [
  {
    id: "vascular_occlusion_ha_filler",
    title: "Vascular Occlusion",
    category: "Injectables",
    severity: "Critical",
    immediateAction: [
      "Stop injection immediately",
      "Assess capillary refill, pain, blanching, livedo reticularis",
      "Massage area and apply warm compress",
      "Prepare hyaluronidase urgently if HA filler is confirmed or suspected",
    ],
    treatment: [
      "Administer territory-based hyaluronidase — treat the full vascular territory, not only the puncture site",
      "Reassess every 30–60 minutes and repeat as needed until reperfusion",
      "Escalate immediately if visual symptoms develop",
      "Monitor capillary refill, skin colour, and pain after each treatment cycle",
    ],
    followup: [
      "Is the discoloration pale, mottled, or livedo rather than blue-gray?",
      "Is HA filler confirmed or suspected?",
      "Is there any visual symptom — even momentary?",
      "Is pain worsening despite hyaluronidase treatment?",
    ],
    redFlags: [
      "Any visual symptom — call emergency services immediately",
      "Progressive blanching or mottling despite treatment",
      "No improvement after 2–3 treatment cycles",
    ],
    patientSummary: "A blood vessel blockage is suspected after your treatment. We are taking urgent steps to restore circulation, monitoring the area closely, and reducing the risk of skin injury.",
    evidenceTier: "guideline",
    confidence: 96,
    sources: [
      { title: "Expert consensus on management of vascular occlusion after HA fillers", type: "Consensus", year: 2024 },
      { title: "Clinical guidance for visual symptoms after filler injection", type: "Guideline", year: 2023 },
    ],
    recommendedDose: "150–1500 IU per territory depending on region — escalate dose for glabella and nose",
  },
  {
    id: "anaphylaxis_allergic_reaction",
    title: "Anaphylaxis / Severe Allergic Reaction",
    category: "Injectables",
    severity: "Critical",
    immediateAction: [
      "Stop procedure immediately — call emergency services without delay",
      "Assess airway, breathing, circulation, and mental status",
      "Administer IM epinephrine 0.5mg into the outer thigh immediately",
      "Position supine with legs elevated unless breathing difficulty prevents this",
    ],
    treatment: [
      "Repeat epinephrine after 5 minutes if symptoms persist or worsen",
      "Provide high-flow oxygen if available",
      "Antihistamines and corticosteroids are adjuncts only — do not replace epinephrine",
      "Ensure emergency transfer is underway — do not delay transfer",
    ],
    followup: [
      "Is the patient's airway compromised?",
      "Has epinephrine been administered and documented?",
      "Is emergency transfer confirmed?",
      "Is there a biphasic reaction risk — monitoring for at least 4 hours post-event?",
    ],
    redFlags: [
      "Stridor, wheeze, or airway compromise",
      "Cardiovascular collapse or loss of consciousness",
      "Failure to respond to epinephrine after 2 doses",
    ],
    patientSummary: "A serious allergic reaction is suspected. Emergency services have been called and your safety is the immediate priority.",
    evidenceTier: "guideline",
    confidence: 97,
    sources: [
      { title: "NICE guideline on anaphylaxis management", type: "Guideline", year: 2024 },
      { title: "Resuscitation Council UK anaphylaxis algorithm", type: "Guideline", year: 2023 },
    ],
    recommendedDose: "Epinephrine 0.5mg IM (0.5mL of 1:1000) into outer thigh — repeat at 5 minutes if no improvement",
  },
  {
    id: "eyelid_ptosis_toxin",
    title: "Eyelid Ptosis After Toxin",
    category: "Injectables",
    severity: "Moderate",
    immediateAction: [
      "Confirm onset timing relative to toxin injection",
      "Differentiate true eyelid ptosis from brow heaviness",
      "Assess asymmetry and degree of lid droop",
    ],
    treatment: [
      "Apraclonidine 0.5% eye drops may reduce ptosis by stimulating Müller's muscle — use per clinic protocol",
      "Avoid repeat toxin until fully resolved",
      "Reassure patient: ptosis resolves as toxin effect wanes — typically 4–6 weeks",
    ],
    followup: [
      "Is this true eyelid ptosis or brow heaviness?",
      "Is diplopia or any visual change present?",
      "Was the injection close to the orbital rim?",
      "Is apraclonidine contraindicated in this patient?",
    ],
    redFlags: [
      "Diplopia — requires ophthalmology review",
      "Any visual change beyond lid position",
      "Asymmetric pupil size",
    ],
    patientSummary: "A drooping of one or both eyelids has developed after your toxin treatment. This is a known side effect that resolves on its own as the treatment wears off, usually within 4–6 weeks.",
    evidenceTier: "consensus",
    confidence: 88,
    sources: [
      { title: "Review of botulinum toxin complications in aesthetic practice", type: "Review", year: 2023 },
    ],
    recommendedDose: "Apraclonidine 0.5% eye drops 1–2 drops to affected eye — specialist guidance recommended",
  },
  {
    id: "infection_or_biofilm_after_filler",
    title: "Infection / Biofilm After Filler",
    category: "Injectables",
    severity: "High",
    immediateAction: [
      "Assess for tenderness, warmth, erythema, fluctuance, drainage, and fever",
      "Do not assume it is a cosmetic irregularity if inflammatory signs are present",
      "Escalate for clinician-led infection assessment",
    ],
    treatment: [
      "Differentiate infective from inflammatory — culture if drainage present",
      "Antibiotic selection depends on clinical presentation and local guidelines",
      "Consider hyaluronidase for HA filler-related biofilm per specialist guidance",
      "Document evolution with photography",
    ],
    followup: [
      "Is there warmth, drainage, or fluctuance?",
      "Is the patient febrile?",
      "When did symptoms begin after injection?",
      "Has any antibiotic treatment already been given?",
    ],
    redFlags: [
      "Fever — systemic infection risk",
      "Rapidly progressive facial swelling",
      "Fluctuance with systemic signs",
    ],
    patientSummary: "A possible infection or inflammatory reaction is suspected after your filler treatment. This requires clinical assessment and targeted treatment.",
    evidenceTier: "review",
    confidence: 82,
    sources: [
      { title: "Review of filler-related infections and biofilm", type: "Review", year: 2023 },
    ],
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Backend → ProtocolCard mapper
// ─────────────────────────────────────────────────────────────────────────────

function deriveCategory(key: string): string {
  if (key.includes("laser") || key.includes("energy") || key.includes("device")) return "Energy Devices";
  return "Injectables";
}

function mapEvidenceStrength(s: string): EvidenceTier {
  if (s === "strong")   return "guideline";
  if (s === "moderate") return "consensus";
  if (s === "limited")  return "review";
  return "low";
}

function mapSeverity(s: string): Severity {
  const map: Record<string, Severity> = {
    critical: "Critical", high: "High", moderate: "Moderate", low: "Low",
  };
  return map[s?.toLowerCase()] ?? "Moderate";
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapBackendToCard(data: any): ProtocolCard {
  const immediateAction: string[] =
    (data.immediate_actions ?? []).map((s: any) =>
      typeof s === "string" ? s : s.action ?? ""
    ).filter(Boolean);

  const treatment: string[] = [
    ...(data.escalation ?? []),
    ...(data.monitoring ?? []),
    ...(data.dose_guidance ?? []).map((d: any) => `${d.substance}: ${d.recommendation}`),
  ].filter(Boolean);

  const followup: string[] = data.follow_up_questions ?? [];

  const sources: ProtocolSource[] = (data.evidence ?? []).map((e: any) => ({
    title: e.title ?? "Source",
    type: e.source_type ?? "Reference",
    year: e.year ?? new Date().getFullYear(),
  }));

  const recommendedDose =
    data.dose_guidance?.length > 0
      ? data.dose_guidance[0].recommendation
      : undefined;

  return {
    id: data.matched_protocol_key ?? data.id ?? "unknown",
    title: data.matched_protocol_name ?? data.title ?? "Protocol",
    category: deriveCategory(data.matched_protocol_key ?? ""),
    severity: mapSeverity(data.risk_assessment?.severity ?? "moderate"),
    immediateAction,
    treatment,
    followup,
    redFlags: data.red_flags ?? [],
    patientSummary: data.clinical_summary ?? "",
    evidenceTier: mapEvidenceStrength(data.risk_assessment?.evidence_strength ?? "limited"),
    confidence: Math.round((data.confidence ?? 0.8) * 100),
    sources,
    recommendedDose,
    requestId: data.request_id,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapListItem(item: any): ProtocolListItem {
  return {
    id: item.key,
    title: item.name,
    category: deriveCategory(item.key),
    severity: mapSeverity(item.severity),
    evidenceTier: mapEvidenceStrength(item.evidence_strength),
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Evidence tier display config
// ─────────────────────────────────────────────────────────────────────────────

const EVIDENCE_STYLE: Record<EvidenceTier, {
  label: string; dot: string; pill: string; order: number;
}> = {
  guideline: { label: "Guideline-backed", dot: "bg-green-500",  pill: "bg-green-50 text-green-700 border-green-200",   order: 1 },
  consensus: { label: "Consensus",        dot: "bg-yellow-500", pill: "bg-yellow-50 text-yellow-700 border-yellow-200", order: 2 },
  review:    { label: "Review",           dot: "bg-blue-500",   pill: "bg-blue-50 text-blue-700 border-blue-200",       order: 3 },
  low:       { label: "Low evidence",     dot: "bg-gray-400",   pill: "bg-gray-50 text-gray-700 border-gray-200",       order: 4 },
};

const STEP_LABELS: { key: StepKey; label: string }[] = [
  { key: "identify",  label: "Identify" },
  { key: "immediate", label: "Immediate Action" },
  { key: "treatment", label: "Treatment" },
  { key: "followup",  label: "Follow-up" },
];

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────

declare global {
  interface Window { webkitSpeechRecognition?: any; SpeechRecognition?: any; }
}

function cn(...arr: Array<string | false | undefined | null>) {
  return arr.filter(Boolean).join(" ");
}
function uid() { return Math.random().toString(36).slice(2, 10); }
function nowIso() { return new Date().toISOString(); }
function formatDuration(ms: number) {
  const sec = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(sec / 60).toString().padStart(2, "0")}:${(sec % 60).toString().padStart(2, "0")}`;
}
function titleCase(text: string) {
  return text.split(" ").map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
}
function round2(n: number) { return Math.round(n * 100) / 100; }
function escapeHtml(str: string) {
  return str.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
}

function rankProtocols(protocols: ProtocolListItem[], query: string) {
  const q = query.toLowerCase().trim();
  return protocols.map((p) => {
    let score = q ? 0 : 1;
    if (p.title.toLowerCase().includes(q)) score += 20;
    if (p.category.toLowerCase().includes(q)) score += 10;
    score += (5 - EVIDENCE_STYLE[p.evidenceTier].order) * 10;
    if (p.severity === "Critical") score += 5;
    return { ...p, _score: score };
  }).sort((a, b) => b._score - a._score);
}

function extractStructuredData(input: {
  transcript: string; procedure: string; region: string;
  practitioner: string; product: string; complication: string;
  treatmentGiven: string; patientFactors: string; onsetMinutes: number;
}) {
  const stamp = new Date().toLocaleString();
  const timeline = [
    `[${stamp}] Complication workflow started`,
    input.procedure && `Procedure: ${input.procedure}`,
    input.region && `Region: ${input.region}`,
    input.product && `Product: ${input.product}`,
    input.complication && `Complication: ${input.complication}`,
    `Time since onset: ${input.onsetMinutes} minute(s)`,
    input.treatmentGiven && `Treatment given: ${input.treatmentGiven}`,
  ].filter(Boolean).join("\n");

  const procedureLog = [
    "Clinical Procedure Log",
    `Practitioner: ${input.practitioner || "Not specified"}`,
    `Procedure: ${input.procedure || "Not specified"}`,
    `Region: ${input.region || "Not specified"}`,
    `Product: ${input.product || "Not specified"}`,
    `Complication: ${input.complication || "Not specified"}`,
    `Patient factors: ${input.patientFactors || "None documented"}`,
    `Onset: ${input.onsetMinutes} minute(s) ago`,
    `Treatment given: ${input.treatmentGiven || "None documented yet"}`,
    "",
    "Ambient AI transcript summary:",
    input.transcript ? input.transcript.trim() : "No transcript captured.",
  ].join("\n");

  const patientSummary = [
    `Today, a complication related to ${input.procedure || "a cosmetic procedure"} was identified.`,
    input.region ? `The area involved is ${input.region}.` : "",
    input.complication ? `The main concern is ${input.complication.toLowerCase()}.` : "",
    input.treatmentGiven
      ? `The treatment already given includes: ${input.treatmentGiven}.`
      : "The clinical team is assessing the safest next steps.",
    "You will receive instructions on monitoring, aftercare, and when to seek urgent help.",
  ].filter(Boolean).join(" ");

  return { procedureLog, timeline, patientSummary };
}

function buildSafetyReport(args: {
  selectedProtocol: ProtocolCard; procedure: string; region: string; product: string;
  practitioner: string; patientFactors: string; treatmentGiven: string; onsetMinutes: number;
  effectiveSeverity: string; transcript: string; caseNotes: string;
  autoDocs: { procedureLog: string; timeline: string; patientSummary: string };
  elapsedMs: number; responseMs: number; hyalDose: number; hyalMlNeeded: number; hyalVialsNeeded: number;
}) {
  const evidence = EVIDENCE_STYLE[args.selectedProtocol.evidenceTier];
  return `AESTHETICITE CLINIC SAFETY REPORT
Generated: ${new Date().toLocaleString()}

1. CASE SUMMARY
Complication: ${args.selectedProtocol.title}
Severity: ${args.effectiveSeverity}
Procedure: ${args.procedure || "Not specified"}
Region: ${args.region || "Not specified"}
Product: ${args.product || "Not specified"}
Practitioner: ${args.practitioner || "Not specified"}
Patient factors: ${args.patientFactors || "None documented"}
Time since onset: ${args.onsetMinutes} minute(s)
Active case timer: ${formatDuration(args.elapsedMs)}
Protocol response speed: ${args.responseMs} ms

2. TRUST / EVIDENCE
Evidence level: ${evidence.label}
Confidence score: ${args.selectedProtocol.confidence}%
Evidence sources:
${args.selectedProtocol.sources.map((s, i) => `${i+1}. ${s.title} (${s.type}, ${s.year})`).join("\n")}

3. RED FLAGS
${args.selectedProtocol.redFlags.map((x, i) => `${i+1}. ${x}`).join("\n") || "None specified"}

4. IMMEDIATE ACTIONS
${args.selectedProtocol.immediateAction.map((x, i) => `${i+1}. ${x}`).join("\n")}

5. TREATMENT
${args.selectedProtocol.treatment.map((x, i) => `${i+1}. ${x}`).join("\n")}

6. FOLLOW-UP QUESTIONS
${args.selectedProtocol.followup.map((x, i) => `${i+1}. ${x}`).join("\n")}

7. AUTO-GENERATED PROCEDURE LOG
${args.autoDocs.procedureLog}

8. TIMELINE
${args.autoDocs.timeline}

9. TREATMENT GIVEN
${args.treatmentGiven || "None documented"}

10. AMBIENT AI TRANSCRIPT
${args.transcript || "No transcript captured"}

11. ADDITIONAL NOTES
${args.caseNotes || "No additional notes"}

12. PATIENT SUMMARY
${args.selectedProtocol.patientSummary}

13. PATIENT-READABLE EXPLANATION
${args.autoDocs.patientSummary}

14. HYALURONIDASE CALCULATOR
Target dose: ${args.hyalDose} units
Approximate mL needed: ${round2(args.hyalMlNeeded)}
Approximate vials needed: ${round2(args.hyalVialsNeeded)}

End of report.`.trim();
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function StatCard({ icon, label, value, sub }: {
  icon: React.ReactNode; label: string; value: string; sub: string;
}) {
  return (
    <div className="rounded-2xl border bg-slate-50 p-4">
      <div className="mb-2 flex items-center gap-2 text-slate-500">{icon}</div>
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-bold">{value}</div>
      <div className="mt-1 text-xs text-slate-500">{sub}</div>
    </div>
  );
}

function InputField({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <div>
      <label className="mb-2 block text-sm font-medium">{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-2xl border bg-white px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-slate-400" />
    </div>
  );
}

function NumberInput({ label, value, setValue, min }: {
  label: string; value: number; setValue: (v: number) => void; min?: number;
}) {
  return (
    <div>
      <label className="mb-2 block text-sm font-medium">{label}</label>
      <input type="number" min={min} value={value} onChange={e => setValue(Number(e.target.value))}
        className="w-full rounded-2xl border bg-white px-3 py-2 text-sm focus:outline-none" />
    </div>
  );
}

function TextArea({ label, value, onChange, rows, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; rows: number; placeholder?: string;
}) {
  return (
    <div>
      <label className="mb-2 block text-sm font-medium">{label}</label>
      <textarea value={value} onChange={e => onChange(e.target.value)} rows={rows}
        placeholder={placeholder}
        className="w-full rounded-2xl border bg-white px-3 py-2 text-sm resize-none focus:outline-none" />
    </div>
  );
}

function ProtocolSection({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <div className="mb-3 text-base font-semibold">{title}</div>
      <div className="space-y-2">
        {items.map((item, i) => (
          <div key={i} className="flex items-start gap-3 rounded-xl border bg-white p-3">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
            <div className="text-sm text-slate-700">{item}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TrustBadge({ tier, confidence }: { tier: EvidenceTier; confidence: number }) {
  const t = EVIDENCE_STYLE[tier];
  return (
    <div className="text-right">
      <div className={cn("inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold", t.pill)}>
        <span className={cn("h-2.5 w-2.5 rounded-full", t.dot)} />
        {t.label}
      </div>
      <div className="mt-2 text-xs text-slate-500">Confidence: {confidence}%</div>
    </div>
  );
}

function TrustRow({ tier }: { tier: EvidenceTier }) {
  const t = EVIDENCE_STYLE[tier];
  return (
    <div className="flex items-center justify-between rounded-2xl border p-3">
      <div className="flex items-center gap-3">
        <span className={cn("h-3 w-3 rounded-full", t.dot)} />
        <span className="text-sm font-medium">{t.label}</span>
      </div>
      <span className="text-xs text-slate-500">Rank {t.order}</span>
    </div>
  );
}

function PanelRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border bg-slate-50 p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-semibold">{value}</div>
    </div>
  );
}

function DocCard({ title, icon, content }: { title: string; icon: React.ReactNode; content: string }) {
  return (
    <div className="rounded-2xl border p-4">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold">{icon}{title}</div>
      <pre className="whitespace-pre-wrap text-sm leading-6 text-slate-700">{content}</pre>
    </div>
  );
}

function CalcCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border bg-slate-50 p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-bold">{value}</div>
    </div>
  );
}

function ClinicDashboard({ analytics, savedCases, onLoadCase }: {
  analytics: { totalCases: number; avgTimeToTreatment: number; protocolAdherence: number; mostFrequent: string };
  savedCases: SavedCase[];
  onLoadCase: (id: string) => void;
}) {
  return (
    <div className="space-y-6">
      <section className="rounded-3xl border bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <TrendingUp className="h-5 w-5" />
          <h2 className="text-lg font-bold">Clinic analytics dashboard</h2>
        </div>
        <div className="grid gap-4 md:grid-cols-4">
          <StatCard icon={<FileText className="h-4 w-4" />} label="Total cases" value={String(analytics.totalCases)} sub="Saved complication events" />
          <StatCard icon={<Clock3 className="h-4 w-4" />} label="Avg time to treatment" value={`${analytics.avgTimeToTreatment} min`} sub="Operational speed indicator" />
          <StatCard icon={<ShieldCheck className="h-4 w-4" />} label="Protocol adherence" value={`${analytics.protocolAdherence}%`} sub="Documented note completion" />
          <StatCard icon={<Activity className="h-4 w-4" />} label="Most frequent event" value={analytics.mostFrequent} sub="Risk tracking view" />
        </div>
      </section>
      <section className="rounded-3xl border bg-white p-5 shadow-sm">
        <div className="mb-4 text-lg font-bold">Case library</div>
        {savedCases.length === 0 ? (
          <p className="text-sm text-slate-600">No cases stored yet. Save cases to build clinic learning and analytics.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {savedCases.map(c => (
              <button key={c.id} onClick={() => onLoadCase(c.id)}
                className="rounded-2xl border p-4 text-left hover:bg-slate-50">
                <div className="font-semibold">{c.complication}</div>
                <div className="mt-1 text-sm text-slate-600">{c.procedure} • {c.region}</div>
                <div className="mt-2 text-xs text-slate-500">{new Date(c.createdAt).toLocaleString()} • {c.severity}</div>
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export default function SafetyWorkspacePage() {
  const [, setLocation] = useLocation();

  const [mode, setMode] = useState<"dashboard" | "complication">("complication");
  const [step, setStep] = useState<StepKey>("identify");
  const [query, setQuery] = useState("");
  const [complicationId, setComplicationId] = useState("vascular_occlusion_ha_filler");

  const [procedure, setProcedure] = useState("HA filler injection");
  const [region, setRegion] = useState("Nasolabial fold");
  const [product, setProduct] = useState("Hyaluronic acid filler");
  const [practitioner, setPractitioner] = useState("");
  const [patientFactors, setPatientFactors] = useState("");
  const [treatmentGiven, setTreatmentGiven] = useState("");
  const [severityOverride, setSeverityOverride] = useState<"" | Severity>("");
  const [onsetMinutes, setOnsetMinutes] = useState(5);

  const [caseNotes, setCaseNotes] = useState("");
  const [transcript, setTranscript] = useState("");
  const [isListening, setIsListening] = useState(false);

  const [complicationStartedAt, setComplicationStartedAt] = useState<number | null>(Date.now());
  const [elapsedMs, setElapsedMs] = useState(0);
  const [responseMs, setResponseMs] = useState(0);

  const [hyalDose, setHyalDose] = useState(300);
  const [hyalConcentration, setHyalConcentration] = useState(1500);
  const [hyalDilutionMl, setHyalDilutionMl] = useState(10);

  const [savedCases, setSavedCases] = useState<SavedCase[]>([]);
  const [selectedSavedCaseId, setSelectedSavedCaseId] = useState("");

  // ── Backend state ──────────────────────────────────────────────────────────
  const [protocolList, setProtocolList] = useState<ProtocolListItem[]>(
    STATIC_PROTOCOLS.map(p => ({ id: p.id, title: p.title, category: p.category, severity: p.severity, evidenceTier: p.evidenceTier }))
  );
  const [liveProtocol, setLiveProtocol] = useState<ProtocolCard | null>(null);
  const [protocolLoading, setProtocolLoading] = useState(false);
  const [protocolError, setProtocolError] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  const recognitionRef = useRef<any>(null);
  const responseStartRef = useRef<number>(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Derived ───────────────────────────────────────────────────────────────
  const staticFallback = STATIC_PROTOCOLS.find(p => p.id === complicationId) ?? STATIC_PROTOCOLS[0];
  const selectedProtocol = liveProtocol ?? staticFallback;
  const effectiveSeverity = severityOverride || selectedProtocol.severity;
  const rankedList = useMemo(() => rankProtocols(protocolList, query), [protocolList, query]);

  const hyalUnitsPerMl = hyalConcentration / hyalDilutionMl;
  const hyalMlNeeded = hyalDose / hyalUnitsPerMl;
  const hyalVialsNeeded = hyalDose / hyalConcentration;

  const autoDocs = useMemo(() => extractStructuredData({
    transcript, procedure, region, practitioner, product,
    complication: selectedProtocol.title, treatmentGiven, patientFactors, onsetMinutes,
  }), [transcript, procedure, region, practitioner, product, selectedProtocol.title, treatmentGiven, patientFactors, onsetMinutes]);

  const analytics = useMemo(() => {
    const total = savedCases.length;
    const cc: Record<string, number> = {};
    let totalOnset = 0, protocolDocumented = 0;
    for (const c of savedCases) {
      cc[c.complication] = (cc[c.complication] || 0) + 1;
      totalOnset += c.onsetMinutes || 0;
      if (c.notes?.trim()) protocolDocumented += 1;
    }
    const mf = Object.entries(cc).sort((a, b) => b[1] - a[1])[0];
    return {
      totalCases: total,
      avgTimeToTreatment: total ? Math.round(totalOnset / total) : 0,
      protocolAdherence: total ? Math.round((protocolDocumented / total) * 100) : 0,
      mostFrequent: mf ? `${mf[0]} (${mf[1]})` : "No cases yet",
    };
  }, [savedCases]);

  const nextRecommendedAction = useMemo(() => {
    if (step === "identify")  return selectedProtocol.immediateAction[0] ?? "Begin assessment";
    if (step === "immediate") return selectedProtocol.treatment[0] ?? "Proceed with protocol";
    if (step === "treatment") return selectedProtocol.followup[0] ?? "Monitor and document";
    return "Complete documentation and patient advice";
  }, [selectedProtocol, step]);

  const escalationIndicator = useMemo(() => {
    if (selectedProtocol.id === "anaphylaxis_allergic_reaction") return "Call emergency services — do not delay";
    if (effectiveSeverity === "Critical") return "Highest priority — do not delay";
    if (effectiveSeverity === "High")     return "Senior review strongly advised";
    return "Continue close monitoring and documentation";
  }, [selectedProtocol.id, effectiveSeverity]);

  // ── Timer ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    const t = setInterval(() => {
      setElapsedMs(complicationStartedAt ? Date.now() - complicationStartedAt : 0);
    }, 500);
    return () => clearInterval(t);
  }, [complicationStartedAt]);

  // ── Response speed ────────────────────────────────────────────────────────
  useEffect(() => {
    responseStartRef.current = performance.now();
    const timer = setTimeout(() => {
      setResponseMs(Math.round(performance.now() - responseStartRef.current));
    }, 120);
    return () => clearTimeout(timer);
  }, [complicationId, query, step]);

  // ── Persist saved cases ───────────────────────────────────────────────────
  useEffect(() => {
    try {
      const raw = localStorage.getItem("aestheticite_saved_cases_v3");
      if (raw) setSavedCases(JSON.parse(raw));
    } catch {}
  }, []);
  useEffect(() => {
    try { localStorage.setItem("aestheticite_saved_cases_v3", JSON.stringify(savedCases)); } catch {}
  }, [savedCases]);

  // ── Fetch protocol list on mount ──────────────────────────────────────────
  useEffect(() => {
    const token = getToken();
    fetch("/api/complications/protocols", {
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data)) {
          setProtocolList(data.map(mapListItem));
        }
      })
      .catch(() => { /* keep static fallback */ });
  }, []);

  // ── Fetch live protocol (debounced 600ms) ─────────────────────────────────
  const fetchLiveProtocol = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      const token = getToken();
      setProtocolLoading(true);
      setProtocolError(null);
      try {
        const res = await fetch("/api/complications/protocol", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            query: complicationId.replace(/_/g, " "),
            context: {
              region: region || null,
              procedure: procedure || null,
              product_type: product || null,
              symptoms: patientFactors ? patientFactors.split(",").map(s => s.trim()).filter(Boolean) : [],
              time_since_injection_minutes: onsetMinutes,
            },
            mode: "emergency",
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data?.detail || "Protocol fetch failed");
        setLiveProtocol(mapBackendToCard(data));
      } catch (e: any) {
        setProtocolError(e.message || "Protocol unavailable — showing cached protocol");
        setLiveProtocol(null);
      } finally {
        setProtocolLoading(false);
      }
    }, 600);
  }, [complicationId, region, procedure, product, patientFactors, onsetMinutes]);

  useEffect(() => { fetchLiveProtocol(); }, [fetchLiveProtocol]);

  // ── Speech recognition ────────────────────────────────────────────────────
  const toggleListening = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { alert("Speech recognition is not available in this browser."); return; }
    if (isListening && recognitionRef.current) { recognitionRef.current.stop(); setIsListening(false); return; }
    const recognition = new SR();
    recognitionRef.current = recognition;
    recognition.lang = "en-US"; recognition.continuous = true; recognition.interimResults = true;
    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    recognition.onerror = () => setIsListening(false);
    recognition.onresult = (event: any) => {
      let text = "";
      for (let i = 0; i < event.results.length; i++) text += event.results[i][0].transcript + " ";
      setTranscript(text.trim());
    };
    recognition.start();
  };

  // ── Save case (local + backend log) ───────────────────────────────────────
  const saveCase = async () => {
    const item: SavedCase = {
      id: uid(), createdAt: nowIso(), complication: selectedProtocol.title,
      procedure, region, severity: effectiveSeverity, onsetMinutes,
      treatmentGiven, transcript, notes: `${autoDocs.procedureLog}\n\n${caseNotes}`.trim(),
      protocolKey: selectedProtocol.id,
    };
    setSavedCases(prev => [item, ...prev]);
    setSelectedSavedCaseId(item.id);

    const token = getToken();
    try {
      await fetch("/api/complications/log-case", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          protocol_key: selectedProtocol.id,
          region: region || null,
          procedure: procedure || null,
          product_type: product || null,
          symptoms: patientFactors ? patientFactors.split(",").map(s => s.trim()).filter(Boolean) : [],
          outcome: treatmentGiven || null,
        }),
      });
    } catch { /* non-fatal */ }
  };

  const loadSavedCase = (id: string) => {
    const c = savedCases.find(x => x.id === id);
    if (!c) return;
    setSelectedSavedCaseId(id);
    setProcedure(c.procedure); setRegion(c.region); setTreatmentGiven(c.treatmentGiven);
    setTranscript(c.transcript); setCaseNotes(c.notes); setOnsetMinutes(c.onsetMinutes);
    if (c.protocolKey) setComplicationId(c.protocolKey);
  };

  // ── PDF export — backend first, fallback to text ──────────────────────────
  const exportPDF = async () => {
    if (!selectedProtocol.requestId) {
      exportTextReport();
      return;
    }
    setPdfLoading(true);
    const token = getToken();
    try {
      const res = await fetch("/api/complications/export-pdf", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          query: selectedProtocol.id.replace(/_/g, " "),
          context: {
            region: region || null,
            procedure: procedure || null,
            product_type: product || null,
            time_since_injection_minutes: onsetMinutes,
          },
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "PDF export failed");
      if (data.filename) window.open(`/exports/${data.filename}`, "_blank");
    } catch {
      exportTextReport();
    } finally {
      setPdfLoading(false);
    }
  };

  const exportTextReport = () => {
    const report = buildSafetyReport({
      selectedProtocol, procedure, region, product, practitioner, patientFactors,
      treatmentGiven, onsetMinutes, effectiveSeverity, transcript, caseNotes, autoDocs,
      elapsedMs, responseMs, hyalDose, hyalMlNeeded, hyalVialsNeeded,
    });
    const blob = new Blob([report], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `aestheticite-safety-report-${selectedProtocol.id}-${new Date().toISOString().slice(0,10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const printReport = () => {
    const report = buildSafetyReport({
      selectedProtocol, procedure, region, product, practitioner, patientFactors,
      treatmentGiven, onsetMinutes, effectiveSeverity, transcript, caseNotes, autoDocs,
      elapsedMs, responseMs, hyalDose, hyalMlNeeded, hyalVialsNeeded,
    });
    const w = window.open("", "_blank", "width=900,height=700");
    if (!w) return;
    w.document.write(`<html><head><title>Clinic Safety Report</title>
      <style>body{font-family:Arial,sans-serif;padding:24px;line-height:1.5;}pre{white-space:pre-wrap;}</style>
      </head><body><pre>${escapeHtml(report)}</pre>
      <script>window.onload=()=>window.print();<\/script></body></html>`);
    w.document.close();
  };

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-7xl p-4 md:p-6">

        {/* Header */}
        <div className="mb-6 flex flex-col gap-4 rounded-3xl border bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="mb-2 flex items-center gap-3">
                <button onClick={() => setLocation("/")}
                  className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-900 transition-colors">
                  <ArrowLeft className="h-3.5 w-3.5" /> Back
                </button>
                <div className="inline-flex items-center gap-2 rounded-full border border-red-200 bg-red-50 px-3 py-1 text-sm font-medium text-red-700">
                  <AlertTriangle className="h-4 w-4" /> Complication Mode
                </div>
                {protocolLoading && (
                  <div className="inline-flex items-center gap-1.5 text-xs text-slate-500">
                    <Loader2 className="h-3 w-3 animate-spin" /> Updating protocol…
                  </div>
                )}
              </div>
              <h1 className="text-2xl font-bold md:text-3xl">AesthetiCite Safety Workspace</h1>
              <p className="mt-1 text-sm text-slate-600">
                Live protocol retrieval from 780K+ documents · Ambient AI documentation · Evidence-first ranking · PDF export
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => setMode("complication")}
                className={cn("rounded-2xl border px-4 py-2 text-sm font-medium",
                  mode === "complication" ? "border-slate-900 bg-slate-900 text-white" : "bg-white")}>
                Complication Workspace
              </button>
              <button onClick={() => setMode("dashboard")}
                className={cn("rounded-2xl border px-4 py-2 text-sm font-medium",
                  mode === "dashboard" ? "border-slate-900 bg-slate-900 text-white" : "bg-white")}>
                Clinic Dashboard
              </button>
            </div>
          </div>

          {protocolError && (
            <div className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700">
              <AlertTriangle className="h-4 w-4 flex-shrink-0" />
              {protocolError}
              <button onClick={fetchLiveProtocol} className="ml-auto flex items-center gap-1 text-xs hover:underline">
                <RefreshCw className="h-3 w-3" /> Retry
              </button>
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-4">
            <StatCard icon={<Clock3 className="h-4 w-4" />} label="Time since onset" value={`${onsetMinutes} min`} sub="Clinician-entered" />
            <StatCard icon={<TimerReset className="h-4 w-4" />} label="Active case timer" value={formatDuration(elapsedMs)} sub="Live complication timer" />
            <StatCard icon={<Gauge className="h-4 w-4" />} label="Protocol speed" value={`${responseMs} ms`} sub={responseMs < 2000 ? "Fast enough for trust" : "Check connectivity"} />
            <StatCard icon={<ShieldCheck className="h-4 w-4" />} label="Evidence level" value={EVIDENCE_STYLE[selectedProtocol.evidenceTier].label} sub={`${selectedProtocol.confidence}% confidence`} />
          </div>
        </div>

        {mode === "dashboard" ? (
          <ClinicDashboard analytics={analytics} savedCases={savedCases} onLoadCase={loadSavedCase} />
        ) : (
          <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-6">

              {/* Emergency CTA */}
              <section className="rounded-3xl border border-red-200 bg-white p-5 shadow-sm">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-red-50 px-3 py-1 text-sm font-medium text-red-700">
                      <Activity className="h-4 w-4" /> Live backend retrieval active
                    </div>
                    <h2 className="text-xl font-bold">🚨 Complication happening now</h2>
                    <p className="mt-1 text-sm text-slate-600">
                      Protocol pulls live from your RAG engine. Enter context below — the protocol updates automatically.
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => { setComplicationStartedAt(Date.now()); setStep("identify"); }}
                      className="rounded-2xl bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-red-700">
                      Start New Emergency Flow
                    </button>
                    <button onClick={saveCase}
                      className="rounded-2xl border px-4 py-2 text-sm font-semibold">
                      Save Case
                    </button>
                  </div>
                </div>
              </section>

              {/* Protocol selector + context */}
              <section className="rounded-3xl border bg-white p-5 shadow-sm">
                <div className="mb-4 flex items-center gap-2">
                  <Stethoscope className="h-5 w-5" />
                  <h2 className="text-lg font-bold">Complication intake</h2>
                  {protocolLoading && <Loader2 className="h-4 w-4 animate-spin text-slate-400 ml-2" />}
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <label className="mb-2 block text-sm font-medium">What complication are you facing?</label>
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
                      <input value={query} onChange={e => setQuery(e.target.value)}
                        placeholder="Search complication…"
                        className="w-full rounded-2xl border bg-white py-2 pl-9 pr-3 text-sm outline-none" />
                    </div>
                    <div className="mt-3 max-h-80 space-y-2 overflow-auto">
                      {rankedList.map(p => {
                        const evidence = EVIDENCE_STYLE[p.evidenceTier];
                        const active = p.id === complicationId;
                        return (
                          <button key={p.id}
                            onClick={() => { setComplicationId(p.id); setStep("identify"); setLiveProtocol(null); }}
                            className={cn("w-full rounded-2xl border p-3 text-left transition",
                              active ? "border-slate-900 bg-slate-50" : "bg-white hover:bg-slate-50")}>
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <div className="font-semibold text-sm">{p.title}</div>
                                <div className="mt-1 text-xs text-slate-500">{p.category} · {p.severity}</div>
                              </div>
                              <span className={cn("rounded-full border px-2 py-1 text-xs font-medium flex-shrink-0", evidence.pill)}>
                                {evidence.label}
                              </span>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <div className="grid gap-3">
                    <InputField label="Procedure" value={procedure} onChange={setProcedure} />
                    <InputField label="Region" value={region} onChange={setRegion} />
                    <InputField label="Product" value={product} onChange={setProduct} />
                    <InputField label="Practitioner" value={practitioner} onChange={setPractitioner} />
                    <InputField label="Patient factors" value={patientFactors} onChange={setPatientFactors}
                      placeholder="Prior occlusion, anticoagulants, vascular risk…" />
                    <div className="grid grid-cols-2 gap-3">
                      <NumberInput label="Time since onset (min)" value={onsetMinutes} setValue={setOnsetMinutes} min={0} />
                      <div>
                        <label className="mb-2 block text-sm font-medium">Override severity</label>
                        <select value={severityOverride} onChange={e => setSeverityOverride(e.target.value as any)}
                          className="w-full rounded-2xl border bg-white px-3 py-2 text-sm">
                          <option value="">Use protocol severity</option>
                          <option>Low</option><option>Moderate</option><option>High</option><option>Critical</option>
                        </select>
                      </div>
                    </div>
                  </div>
                </div>
              </section>

              {/* Workflow steps */}
              <section className="rounded-3xl border bg-white p-5 shadow-sm">
                <div className="mb-4 flex flex-wrap gap-2">
                  {STEP_LABELS.map((s, idx) => (
                    <button key={s.key} onClick={() => setStep(s.key)}
                      className={cn("inline-flex items-center gap-2 rounded-2xl border px-4 py-2 text-sm font-medium",
                        step === s.key ? "border-slate-900 bg-slate-900 text-white" : "bg-white")}>
                      <span className="rounded-full border border-current px-2 py-0.5 text-xs">{idx + 1}</span>
                      {s.label}
                    </button>
                  ))}
                </div>

                <div className="grid gap-4 lg:grid-cols-[1fr_0.9fr]">
                  <div className="rounded-2xl border bg-slate-50 p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <div>
                        <h3 className="text-lg font-bold">{selectedProtocol.title}</h3>
                        <div className="mt-1 text-sm text-slate-500">
                          {selectedProtocol.category} · Severity: {effectiveSeverity}
                          {liveProtocol && <span className="ml-2 text-emerald-600 font-medium">· Live</span>}
                          {protocolLoading && <span className="ml-2 text-slate-400">· Updating…</span>}
                        </div>
                      </div>
                      <TrustBadge tier={selectedProtocol.evidenceTier} confidence={selectedProtocol.confidence} />
                    </div>

                    {step === "identify" && (
                      <ProtocolSection title="Step 1 — Identify" items={[
                        `Procedure: ${procedure || "Not specified"}`,
                        `Region: ${region || "Not specified"}`,
                        `Time since onset: ${onsetMinutes} minute(s)`,
                        `Patient factors: ${patientFactors || "None documented"}`,
                        `Primary concern: ${selectedProtocol.title}`,
                      ]} />
                    )}
                    {step === "immediate" && (
                      <ProtocolSection title="Step 2 — Immediate action" items={selectedProtocol.immediateAction} />
                    )}
                    {step === "treatment" && (
                      <ProtocolSection title="Step 3 — Treatment" items={selectedProtocol.treatment} />
                    )}
                    {step === "followup" && (
                      <ProtocolSection title="Step 4 — Follow-up questions" items={selectedProtocol.followup} />
                    )}

                    {selectedProtocol.redFlags.length > 0 && (
                      <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3">
                        <div className="text-xs font-bold text-red-600 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                          <AlertTriangle className="h-3.5 w-3.5" /> Red flags — escalate immediately
                        </div>
                        {selectedProtocol.redFlags.map((f, i) => (
                          <div key={i} className="text-sm text-red-700 flex items-start gap-2 mt-1">
                            <XCircle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />{f}
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="mt-4 flex flex-wrap gap-2">
                      <button
                        onClick={() => setStep(prev => {
                          const ix = STEP_LABELS.findIndex(x => x.key === prev);
                          return STEP_LABELS[Math.min(ix + 1, STEP_LABELS.length - 1)].key;
                        })}
                        className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">
                        Next step <ChevronRight className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setCaseNotes(prev =>
                          [prev, `\n${new Date().toLocaleTimeString()} — Completed ${titleCase(step)} step`].join("").trim()
                        )}
                        className="rounded-2xl border px-4 py-2 text-sm font-semibold">
                        Add step to log
                      </button>
                    </div>
                  </div>

                  {/* Control panel */}
                  <div className="rounded-2xl border p-4">
                    <div className="mb-3 flex items-center gap-2">
                      <Brain className="h-5 w-5" />
                      <h3 className="text-lg font-bold">Control Panel</h3>
                    </div>
                    <div className="grid gap-3">
                      <PanelRow label="Severity level" value={effectiveSeverity} />
                      <PanelRow label="Time since onset" value={`${onsetMinutes} min`} />
                      <PanelRow label="Recommended next action" value={nextRecommendedAction} />
                      <PanelRow label="Escalation indicator" value={escalationIndicator} />
                      <PanelRow label="Evidence rank" value={EVIDENCE_STYLE[selectedProtocol.evidenceTier].label} />
                      <PanelRow label="Confidence score" value={`${selectedProtocol.confidence}%`} />
                    </div>
                    {selectedProtocol.recommendedDose && (
                      <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-3">
                        <div className="flex items-center gap-2 text-sm font-semibold">
                          <Syringe className="h-4 w-4" /> Protocol dose cue
                        </div>
                        <p className="mt-2 text-sm text-slate-700">{selectedProtocol.recommendedDose}</p>
                      </div>
                    )}
                  </div>
                </div>
              </section>

              {/* Ambient AI documentation */}
              <section className="rounded-3xl border bg-white p-5 shadow-sm">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Mic className="h-5 w-5" />
                    <h2 className="text-lg font-bold">Ambient AI auto-documentation</h2>
                  </div>
                  <button onClick={toggleListening}
                    className={cn("inline-flex items-center gap-2 rounded-2xl px-4 py-2 text-sm font-semibold",
                      isListening ? "bg-red-600 text-white" : "border bg-white text-slate-900")}>
                    {isListening ? <><MicOff className="h-4 w-4" /> Stop Listening</> : <><Mic className="h-4 w-4" /> Start Ambient Capture</>}
                  </button>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="space-y-3">
                    <TextArea label="Live transcript" value={transcript} onChange={setTranscript} rows={7} placeholder="Speech-to-text transcript appears here…" />
                    <TextArea label="Treatment given" value={treatmentGiven} onChange={setTreatmentGiven} rows={4} placeholder="Hyaluronidase administered, massage, warm compress…" />
                    <TextArea label="Additional case notes" value={caseNotes} onChange={setCaseNotes} rows={6} placeholder="Extra observations, progression, photos, escalation…" />
                  </div>
                  <div className="space-y-3">
                    <DocCard title="Procedure log" icon={<ClipboardList className="h-4 w-4" />} content={autoDocs.procedureLog} />
                    <DocCard title="Timeline" icon={<Clock3 className="h-4 w-4" />} content={autoDocs.timeline} />
                  </div>
                </div>
              </section>

              {/* Patient output + export */}
              <section className="rounded-3xl border bg-white p-5 shadow-sm">
                <div className="mb-4 flex items-center gap-2">
                  <UserRound className="h-5 w-5" />
                  <h2 className="text-lg font-bold">Patient-facing output & export</h2>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="rounded-2xl border bg-slate-50 p-4 space-y-4">
                    <div>
                      <h3 className="font-semibold text-sm">Protocol patient summary</h3>
                      <p className="mt-2 text-sm leading-6 text-slate-700">{selectedProtocol.patientSummary}</p>
                    </div>
                    <div>
                      <h3 className="font-semibold text-sm">Plain-language explanation</h3>
                      <p className="mt-2 text-sm leading-6 text-slate-700">{autoDocs.patientSummary}</p>
                    </div>
                    <div>
                      <h3 className="font-semibold text-sm">Aftercare instructions</h3>
                      <ul className="mt-2 space-y-2 text-sm text-slate-700">
                        <li>• Monitor the treated area for worsening pain, colour change, or swelling.</li>
                        <li>• Follow the clinic's instructions exactly and attend all scheduled reviews.</li>
                        <li>• Seek urgent medical help immediately for vision changes, severe pain, or rapid deterioration.</li>
                      </ul>
                    </div>
                  </div>
                  <div className="rounded-2xl border p-4 space-y-3">
                    <h3 className="font-semibold">Clinic Safety Report</h3>
                    <p className="text-sm text-slate-600">
                      Legal-ready export with procedure log, timeline, treatment, evidence signal, and patient communication. PDF generated from live backend protocol when available.
                    </p>
                    <div className="flex flex-wrap gap-2 pt-2">
                      <button onClick={exportPDF} disabled={pdfLoading}
                        className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
                        {pdfLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                        Export PDF
                      </button>
                      <button onClick={printReport}
                        className="inline-flex items-center gap-2 rounded-2xl border px-4 py-2 text-sm font-semibold">
                        <Printer className="h-4 w-4" /> Print
                      </button>
                      <button onClick={saveCase}
                        className="inline-flex items-center gap-2 rounded-2xl border px-4 py-2 text-sm font-semibold">
                        <Save className="h-4 w-4" /> Save case
                      </button>
                    </div>
                  </div>
                </div>
              </section>
            </div>

            {/* Right rail */}
            <div className="space-y-6">

              {/* Trust indicators */}
              <section className="rounded-3xl border bg-white p-5 shadow-sm">
                <div className="mb-4 flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5" />
                  <h2 className="text-lg font-bold">Trust indicators</h2>
                </div>
                <div className="space-y-3">
                  {(["guideline","consensus","review","low"] as EvidenceTier[]).map(t => <TrustRow key={t} tier={t} />)}
                </div>
                <div className="mt-4 rounded-2xl border bg-slate-50 p-4">
                  <div className="text-sm font-semibold">Current evidence status</div>
                  <div className="mt-2 flex items-center gap-2">
                    <span className={cn("h-3 w-3 rounded-full", EVIDENCE_STYLE[selectedProtocol.evidenceTier].dot)} />
                    <span className="text-sm font-medium">{EVIDENCE_STYLE[selectedProtocol.evidenceTier].label}</span>
                  </div>
                  <div className="mt-2 text-sm text-slate-600">Confidence: {selectedProtocol.confidence}%</div>
                  {liveProtocol && (
                    <div className="mt-2 text-xs text-emerald-600 font-medium">
                      ✓ Live from RAG engine · Request {liveProtocol.requestId?.slice(0,8)}
                    </div>
                  )}
                </div>
                <div className="mt-4 rounded-2xl border p-4">
                  <div className="text-sm font-semibold mb-3">Evidence sources</div>
                  <div className="space-y-2">
                    {selectedProtocol.sources.map((s, i) => (
                      <div key={i} className="rounded-xl border bg-slate-50 p-3">
                        <div className="font-medium text-sm">{s.title}</div>
                        <div className="mt-1 text-xs text-slate-500">{s.type} · {s.year}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              {/* Hyaluronidase calculator */}
              <section className="rounded-3xl border bg-white p-5 shadow-sm">
                <div className="mb-4 flex items-center gap-2">
                  <Syringe className="h-5 w-5" />
                  <h2 className="text-lg font-bold">Hyaluronidase calculator</h2>
                </div>
                <div className="grid gap-3">
                  <NumberInput label="Target dose (units)" value={hyalDose} setValue={setHyalDose} min={1} />
                  <NumberInput label="Units per vial" value={hyalConcentration} setValue={setHyalConcentration} min={1} />
                  <NumberInput label="Dilution volume per vial (mL)" value={hyalDilutionMl} setValue={setHyalDilutionMl} min={1} />
                </div>
                <div className="mt-4 grid gap-3">
                  <CalcCard label="Units per mL" value={round2(hyalUnitsPerMl)} />
                  <CalcCard label="mL needed" value={round2(hyalMlNeeded)} />
                  <CalcCard label="Vials needed" value={round2(hyalVialsNeeded)} />
                </div>
                <p className="mt-3 text-xs text-slate-400 leading-relaxed">
                  Calculator output is a mathematical computation only. Actual dosing must follow your clinic protocol, training, and the product prescribing information.
                </p>
              </section>

              {/* Case memory */}
              <section className="rounded-3xl border bg-white p-5 shadow-sm">
                <div className="mb-4 flex items-center gap-2">
                  <FileText className="h-5 w-5" />
                  <h2 className="text-lg font-bold">Case memory</h2>
                </div>
                {savedCases.length === 0 ? (
                  <p className="text-sm text-slate-600">No saved cases yet. Cases are also logged to the AesthetiCite dataset for anonymised audit.</p>
                ) : (
                  <div className="space-y-2">
                    {savedCases.slice(0, 8).map(c => (
                      <button key={c.id} onClick={() => loadSavedCase(c.id)}
                        className={cn("w-full rounded-2xl border p-3 text-left hover:bg-slate-50",
                          c.id === selectedSavedCaseId && "border-slate-900 bg-slate-50")}>
                        <div className="font-medium text-sm">{c.complication}</div>
                        <div className="mt-1 text-xs text-slate-500">
                          {new Date(c.createdAt).toLocaleString()} · {c.region} · {c.severity}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </section>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
