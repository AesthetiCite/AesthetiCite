/**
 * AesthetiCite — Case Logging UI
 * ================================
 * Drop into: client/src/pages/case-log.tsx
 * Route:     /case-log  (add to App.tsx)
 *
 * Connects to existing backend endpoints:
 *   POST /api/complications/log-case
 *   GET  /api/complications/stats
 *
 * Purpose: Build AesthetiCite's proprietary complication dataset.
 * Each logged case becomes a data point no conference or competitor can replicate.
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "wouter";
import {
  Database, ArrowLeft, Plus, CheckCircle2, BarChart3,
  FileText, AlertTriangle, Activity, ChevronDown, ChevronUp, X
} from "lucide-react";

// ─── Types ───────────────────────────────────────────────────────────────────

interface LogCasePayload {
  clinic_id?: string;
  clinician_id?: string;
  protocol_key: string;
  region?: string;
  procedure?: string;
  product_type?: string;
  symptoms: string[];
  outcome?: string;
}

interface DatasetStats {
  total_cases: number;
  by_protocol: Record<string, number>;
  by_region: Record<string, number>;
  by_procedure: Record<string, number>;
}

// ─── API ─────────────────────────────────────────────────────────────────────

async function logCase(payload: LogCasePayload): Promise<{ status: string; case_id: string }> {
  const res = await fetch("/api/complications/log-case", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to log case");
  return res.json();
}

async function fetchStats(): Promise<DatasetStats> {
  const res = await fetch("/api/complications/stats");
  if (!res.ok) throw new Error("Failed to load stats");
  return res.json();
}

// ─── Constants ───────────────────────────────────────────────────────────────

const PROTOCOL_OPTIONS = [
  { value: "vascular_occlusion", label: "Vascular Occlusion" },
  { value: "anaphylaxis", label: "Anaphylaxis / Hypersensitivity" },
  { value: "tyndall_effect", label: "Tyndall Effect" },
  { value: "ptosis", label: "Ptosis / Toxin Complication" },
  { value: "infection_biofilm", label: "Infection / Biofilm" },
  { value: "filler_nodules", label: "Filler Nodules / Granuloma" },
  { value: "neuromodulator_resistance", label: "Neuromodulator Resistance" },
  { value: "skin_necrosis", label: "Skin Necrosis" },
  { value: "vision_change", label: "Vision Change / Ocular Emergency" },
  { value: "other", label: "Other" },
];

const REGION_OPTIONS = [
  "Nasolabial fold", "Tear trough", "Lip", "Glabella", "Jawline",
  "Chin", "Cheek / Malar", "Temple", "Forehead", "Nose", "Other"
];

const PROCEDURE_OPTIONS = [
  "HA filler", "CaHA filler (Radiesse)", "PLLA (Sculptra)", "Botulinum toxin",
  "Thread lift", "PRP / biostimulator", "Exosome injectable", "Other"
];

const SYMPTOM_OPTIONS = [
  "Blanching / pallor", "Mottling / livedo", "Severe pain", "Burning pain",
  "Visual disturbance", "Swelling", "Erythema / warmth", "Pus / discharge",
  "Nodule / lump", "Bruising", "Blue-grey discolouration", "Urticaria / itch",
  "Throat tightness", "Shortness of breath", "Eyelid droop", "Brow heaviness",
  "Asymmetry", "Reduced toxin duration", "No toxin response",
];

const OUTCOME_OPTIONS = [
  { value: "resolved_fully", label: "Resolved fully" },
  { value: "resolved_partially", label: "Resolved partially" },
  { value: "ongoing_monitoring", label: "Ongoing — monitoring" },
  { value: "referred", label: "Referred to specialist" },
  { value: "emergency_escalated", label: "Emergency escalation required" },
  { value: "adverse_outcome", label: "Adverse outcome recorded" },
  { value: "pending", label: "Outcome pending" },
];

const PROTOCOL_COLORS: Record<string, string> = {
  vascular_occlusion: "bg-red-100 text-red-700",
  anaphylaxis: "bg-red-100 text-red-700",
  skin_necrosis: "bg-red-100 text-red-700",
  vision_change: "bg-red-100 text-red-700",
  tyndall_effect: "bg-sky-100 text-sky-700",
  ptosis: "bg-amber-100 text-amber-700",
  infection_biofilm: "bg-orange-100 text-orange-700",
  filler_nodules: "bg-slate-100 text-slate-700",
  neuromodulator_resistance: "bg-violet-100 text-violet-700",
  other: "bg-slate-100 text-slate-500",
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function SelectField({ label, value, onChange, options, placeholder }: {
  label: string; value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[]; placeholder?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 transition-all"
      >
        <option value="">{placeholder || `Select ${label.toLowerCase()}`}</option>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{label}</p>
      <p className="text-2xl font-black text-slate-800 mt-1">{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function DistributionBar({ label, count, total, color }: {
  label: string; count: number; total: number; color: string;
}) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center">
        <span className="text-xs text-slate-600 capitalize">{label.replace(/_/g, " ")}</span>
        <span className="text-xs font-semibold text-slate-700">{count}</span>
      </div>
      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function CaseLogPage() {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [successId, setSuccessId] = useState<string | null>(null);

  // Form state
  const [protocolKey, setProtocolKey] = useState("");
  const [region, setRegion] = useState("");
  const [procedure, setProcedure] = useState("");
  const [productType, setProductType] = useState("");
  const [selectedSymptoms, setSelectedSymptoms] = useState<string[]>([]);
  const [outcome, setOutcome] = useState("");
  const [clinicianId, setClinicianId] = useState("");
  const [formError, setFormError] = useState("");

  const toggleSymptom = (s: string) => {
    setSelectedSymptoms(prev =>
      prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]
    );
  };

  // Stats
  const { data: stats, isLoading: statsLoading } = useQuery<DatasetStats>({
    queryKey: ["case-log-stats"],
    queryFn: fetchStats,
  });

  // Mutation
  const logMutation = useMutation({
    mutationFn: logCase,
    onSuccess: (data) => {
      setSuccessId(data.case_id);
      setFormOpen(false);
      resetForm();
      queryClient.invalidateQueries({ queryKey: ["case-log-stats"] });
    },
    onError: () => setFormError("Failed to log case. Please try again."),
  });

  function resetForm() {
    setProtocolKey(""); setRegion(""); setProcedure("");
    setProductType(""); setSelectedSymptoms([]); setOutcome("");
    setClinicianId(""); setFormError("");
  }

  function handleSubmit() {
    if (!protocolKey) { setFormError("Complication type is required."); return; }
    setFormError("");
    logMutation.mutate({
      protocol_key: protocolKey,
      region: region || undefined,
      procedure: procedure || undefined,
      product_type: productType || undefined,
      symptoms: selectedSymptoms,
      outcome: outcome || undefined,
      clinician_id: clinicianId || undefined,
    });
  }

  const topProtocol = stats
    ? Object.entries(stats.by_protocol).sort((a, b) => b[1] - a[1])[0]
    : null;

  const topRegion = stats
    ? Object.entries(stats.by_region).sort((a, b) => b[1] - a[1])[0]
    : null;

  return (
    <div className="min-h-screen bg-slate-50">

      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur-sm">
        <div className="mx-auto max-w-5xl px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/ask" className="text-slate-400 hover:text-slate-600 transition-colors">
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-slate-800 flex items-center justify-center">
                <Database className="w-4 h-4 text-white" />
              </div>
              <div>
                <h1 className="text-sm font-bold text-slate-800 leading-none">Case Log</h1>
                <p className="text-[10px] text-slate-500 leading-none mt-0.5">AesthetiCite Complication Dataset</p>
              </div>
            </div>
          </div>
          <button
            onClick={() => { setFormOpen(true); setSuccessId(null); }}
            className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold rounded-xl px-4 py-2 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Log New Case
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-6 space-y-6">

        {/* Value proposition banner */}
        <div className="bg-slate-800 rounded-2xl p-5 text-white">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center flex-shrink-0">
              <Database className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="font-bold text-base">Build your clinic's proprietary dataset</h2>
              <p className="text-sm text-white/70 mt-1 leading-relaxed">
                Every case you log becomes a data point that no conference, competitor, or AI model can replicate.
                Your complication dataset is AesthetiCite's most defensible long-term asset — and yours.
              </p>
              <div className="flex gap-4 mt-3">
                <div className="text-center">
                  <p className="text-lg font-black">{stats?.total_cases ?? "—"}</p>
                  <p className="text-[10px] text-white/60">Cases logged</p>
                </div>
                <div className="text-center">
                  <p className="text-lg font-black">{Object.keys(stats?.by_protocol ?? {}).length || "—"}</p>
                  <p className="text-[10px] text-white/60">Complication types</p>
                </div>
                <div className="text-center">
                  <p className="text-lg font-black">{Object.keys(stats?.by_region ?? {}).length || "—"}</p>
                  <p className="text-[10px] text-white/60">Regions tracked</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Success message */}
        {successId && (
          <div className="flex items-center justify-between bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <p className="text-sm font-semibold text-emerald-700">Case logged successfully</p>
              <span className="text-xs text-emerald-500 font-mono">#{successId.slice(0, 8)}</span>
            </div>
            <button onClick={() => setSuccessId(null)} className="text-emerald-400 hover:text-emerald-600">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Stats grid */}
        {!statsLoading && stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Total Cases" value={stats.total_cases} />
            <StatCard
              label="Most Common"
              value={topProtocol ? topProtocol[0].replace(/_/g, " ") : "—"}
              sub={topProtocol ? `${topProtocol[1]} cases` : undefined}
            />
            <StatCard
              label="Top Region"
              value={topRegion ? topRegion[0] : "—"}
              sub={topRegion ? `${topRegion[1]} cases` : undefined}
            />
            <StatCard
              label="Types Tracked"
              value={Object.keys(stats.by_protocol).length}
              sub="complication types"
            />
          </div>
        )}

        {/* Distribution charts */}
        {!statsLoading && stats && stats.total_cases > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* By protocol */}
            <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                <BarChart3 className="w-3 h-3" />
                By Complication
              </h3>
              <div className="space-y-2.5">
                {Object.entries(stats.by_protocol)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 6)
                  .map(([key, count]) => (
                    <DistributionBar
                      key={key}
                      label={key}
                      count={count}
                      total={stats.total_cases}
                      color="bg-slate-700"
                    />
                  ))}
              </div>
            </div>

            {/* By region */}
            <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                <Activity className="w-3 h-3" />
                By Region
              </h3>
              <div className="space-y-2.5">
                {Object.entries(stats.by_region)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 6)
                  .map(([key, count]) => (
                    <DistributionBar
                      key={key}
                      label={key}
                      count={count}
                      total={stats.total_cases}
                      color="bg-red-400"
                    />
                  ))}
              </div>
            </div>

            {/* By procedure */}
            <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                <FileText className="w-3 h-3" />
                By Procedure
              </h3>
              <div className="space-y-2.5">
                {Object.entries(stats.by_procedure)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 6)
                  .map(([key, count]) => (
                    <DistributionBar
                      key={key}
                      label={key}
                      count={count}
                      total={stats.total_cases}
                      color="bg-amber-400"
                    />
                  ))}
              </div>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!statsLoading && stats && stats.total_cases === 0 && (
          <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-12 text-center">
            <Database className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <p className="text-sm font-medium text-slate-500">No cases logged yet</p>
            <p className="text-xs text-slate-400 mt-1">Log your first complication to start building your dataset</p>
            <button
              onClick={() => setFormOpen(true)}
              className="mt-4 inline-flex items-center gap-2 bg-slate-800 text-white text-xs font-semibold rounded-lg px-4 py-2"
            >
              <Plus className="w-3.5 h-3.5" />
              Log First Case
            </button>
          </div>
        )}

      </div>

      {/* ── Slide-in form panel ─────────────────────────────────────────────── */}
      {formOpen && (
        <div className="fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            onClick={() => setFormOpen(false)}
          />
          {/* Panel */}
          <div className="relative ml-auto w-full max-w-md bg-white shadow-2xl flex flex-col h-full overflow-y-auto">
            <div className="sticky top-0 z-10 bg-white border-b border-slate-200 px-5 py-4 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-bold text-slate-800">Log Complication Case</h2>
                <p className="text-xs text-slate-400 mt-0.5">All fields are de-identified — no patient data is stored</p>
              </div>
              <button onClick={() => setFormOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 px-5 py-5 space-y-5">

              {/* Protocol */}
              <SelectField
                label="Complication Type *"
                value={protocolKey}
                onChange={setProtocolKey}
                options={PROTOCOL_OPTIONS}
                placeholder="Select complication type"
              />

              {/* Region */}
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Region</label>
                <select
                  value={region}
                  onChange={e => setRegion(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 transition-all"
                >
                  <option value="">Select region</option>
                  {REGION_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>

              {/* Procedure / Product */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Product</label>
                  <select
                    value={procedure}
                    onChange={e => setProcedure(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 transition-all"
                  >
                    <option value="">Select product</option>
                    {PROCEDURE_OPTIONS.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Outcome</label>
                  <select
                    value={outcome}
                    onChange={e => setOutcome(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 transition-all"
                  >
                    <option value="">Select outcome</option>
                    {OUTCOME_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
              </div>

              {/* Symptoms */}
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                  Symptoms Observed
                  {selectedSymptoms.length > 0 && (
                    <span className="ml-2 bg-slate-700 text-white text-[10px] rounded-full px-2 py-0.5">
                      {selectedSymptoms.length}
                    </span>
                  )}
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {SYMPTOM_OPTIONS.map(s => (
                    <button
                      key={s}
                      onClick={() => toggleSymptom(s)}
                      className={`text-xs rounded-lg px-2.5 py-1.5 border transition-all ${
                        selectedSymptoms.includes(s)
                          ? "bg-slate-800 text-white border-slate-800"
                          : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
                      }`}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              {/* Clinician ID */}
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                  Clinician Reference (optional)
                </label>
                <input
                  type="text"
                  value={clinicianId}
                  onChange={e => setClinicianId(e.target.value)}
                  placeholder="e.g. DR-001 (not real name)"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-400 transition-all"
                />
              </div>

              {/* Protocol tag preview */}
              {protocolKey && (
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-semibold rounded-full px-3 py-1 ${PROTOCOL_COLORS[protocolKey] || "bg-slate-100 text-slate-600"}`}>
                    {PROTOCOL_OPTIONS.find(p => p.value === protocolKey)?.label}
                  </span>
                  {region && <span className="text-xs text-slate-500">· {region}</span>}
                </div>
              )}

              {formError && (
                <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 border border-red-200">
                  {formError}
                </p>
              )}

              <div className="pt-2 pb-6">
                <div className="bg-amber-50 border border-amber-200 rounded-xl px-3 py-2.5 mb-4">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-600 flex-shrink-0 mt-0.5" />
                    <p className="text-xs text-amber-700">
                      Do not enter patient names, dates of birth, or any identifying information.
                      Log clinical data only.
                    </p>
                  </div>
                </div>
                <button
                  onClick={handleSubmit}
                  disabled={logMutation.isPending}
                  className="w-full bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-white font-semibold rounded-xl py-3 text-sm transition-colors flex items-center justify-center gap-2"
                >
                  {logMutation.isPending ? (
                    <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Logging case…</>
                  ) : (
                    <><Database className="w-4 h-4" /> Log Case</>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
