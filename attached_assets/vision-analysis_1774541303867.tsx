/**
 * pages/vision-analysis.tsx
 * ─────────────────────────
 * The /vision-analysis page — AesthetiCite's Complication Vision Engine.
 *
 * Replaces /visual-counsel and /vision-followup with one unified flow:
 *
 *   Tab 1: Single photo analysis
 *     → Upload → Context → Run engine → Full structured output
 *
 *   Tab 2: Serial comparison (healing tracker)
 *     → Upload before + after → Compare → Trajectory assessment
 *
 * Register in App.tsx:
 *   import VisionAnalysisPage from "@/pages/vision-analysis";
 *   <Route path="/vision-analysis">{() => <ProtectedRoute component={VisionAnalysisPage} />}</Route>
 */

import React, { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Upload, Activity, ArrowLeftRight, Loader2,
  AlertTriangle, CheckCircle, ShieldCheck, Trash2,
  ChevronRight, RefreshCw, Clock
} from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { FacialInjectionMap, type FacialRegionId, FACIAL_REGIONS } from "@/components/FacialInjectionMap";
import { VisionAnalysisResult, type VisionAnalysisResponse } from "@/components/VisionAnalysisResult";

// ─────────────────────────────────────────────────────────────────
// API helpers
// ─────────────────────────────────────────────────────────────────

async function uploadPhoto(file: File, token: string): Promise<{ visual_id: string }> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("conversation_id", crypto.randomUUID());
  fd.append("kind", "vision_analysis");
  const res = await fetch("/api/visual/upload", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  });
  if (!res.ok) throw new Error("Upload failed");
  return res.json();
}

async function runAnalysis(
  visualId: string,
  ctx: {
    procedure_type?: string;
    days_post_procedure?: number;
    injected_region?: string;
    product_type?: string;
    patient_symptoms?: string[];
    clinical_notes?: string;
    ephemeral?: boolean;
  },
  token: string
): Promise<VisionAnalysisResponse> {
  const res = await fetch("/api/vision/analyse", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ visual_id: visualId, ...ctx }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Analysis failed");
  }
  return res.json();
}

interface SerialResult {
  change_summary: string;
  improving_features: string[];
  worsening_features: string[];
  stable_features: string[];
  overall_trajectory: string;
  clinical_interpretation: string;
  recommended_action: string;
}

async function runSerialCompare(
  beforeId: string,
  afterId: string,
  ctx: { days_between?: number; procedure_type?: string; clinical_notes?: string },
  token: string
): Promise<SerialResult> {
  const res = await fetch("/api/vision/serial-compare", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ visual_id_before: beforeId, visual_id_after: afterId, ...ctx }),
  });
  if (!res.ok) throw new Error("Comparison failed");
  return res.json();
}

async function deletePhoto(visualId: string, token: string) {
  await fetch(`/api/visual/delete/${visualId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}

// ─────────────────────────────────────────────────────────────────
// Shared: upload zone
// ─────────────────────────────────────────────────────────────────

interface UploadZoneProps {
  label: string;
  previewUrl: string | null;
  loading: boolean;
  onClick: () => void;
}

function UploadZone({ label, previewUrl, loading, onClick }: UploadZoneProps) {
  return (
    <div
      className={`
        border-2 border-dashed rounded-xl cursor-pointer transition-all
        flex flex-col items-center justify-center gap-2 overflow-hidden
        ${previewUrl ? "border-teal-400" : "border-gray-300 hover:border-teal-400 hover:bg-teal-50"}
      `}
      style={{ minHeight: 140 }}
      onClick={onClick}
    >
      {loading ? (
        <Loader2 className="w-6 h-6 animate-spin text-teal-600" />
      ) : previewUrl ? (
        <img src={previewUrl} alt={label} className="w-full h-full object-cover" style={{ maxHeight: 160 }} />
      ) : (
        <>
          <div className="w-10 h-10 rounded-full bg-teal-100 flex items-center justify-center">
            <Upload className="w-5 h-5 text-teal-600" />
          </div>
          <p className="text-xs font-medium text-gray-600 text-center px-2">{label}</p>
        </>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Tab 1: Single analysis
// ─────────────────────────────────────────────────────────────────

function SingleAnalysis({ token }: { token: string }) {
  const fileRef = useRef<HTMLInputElement>(null);

  const [previewUrl,  setPreviewUrl]  = useState<string | null>(null);
  const [visualId,    setVisualId]    = useState<string | null>(null);
  const [uploading,   setUploading]   = useState(false);

  const [region,      setRegion]      = useState<FacialRegionId | null>(null);
  const [procedure,   setProcedure]   = useState("");
  const [product,     setProduct]     = useState("");
  const [daysPP,      setDaysPP]      = useState<number | "">("");
  const [symptoms,    setSymptoms]    = useState("");
  const [notes,       setNotes]       = useState("");
  const [ephemeral,   setEphemeral]   = useState(false);

  const [result,      setResult]      = useState<VisionAnalysisResponse | null>(null);
  const [analyzing,   setAnalyzing]   = useState(false);
  const [error,       setError]       = useState<string | null>(null);
  const [deleted,     setDeleted]     = useState(false);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setPreviewUrl(URL.createObjectURL(f));
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const { visual_id } = await uploadPhoto(f, token);
      setVisualId(visual_id);
    } catch (err: any) { setError(err.message); }
    finally { setUploading(false); }
  };

  const analyse = async () => {
    if (!visualId) return;
    setAnalyzing(true); setError(null);
    try {
      const data = await runAnalysis(visualId, {
        procedure_type: procedure || undefined,
        days_post_procedure: daysPP !== "" ? Number(daysPP) : undefined,
        injected_region: region ? FACIAL_REGIONS.find(r => r.id === region)?.label : undefined,
        product_type: product || undefined,
        patient_symptoms: symptoms ? symptoms.split(",").map(s => s.trim()).filter(Boolean) : [],
        clinical_notes: notes || undefined,
        ephemeral,
      }, token);
      setResult(data);
      if (ephemeral) setDeleted(true);
    } catch (err: any) { setError(err.message); }
    finally { setAnalyzing(false); }
  };

  const reset = () => {
    setPreviewUrl(null); setVisualId(null); setResult(null);
    setRegion(null); setProcedure(""); setProduct(""); setDaysPP("");
    setSymptoms(""); setNotes(""); setDeleted(false); setError(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="space-y-5">
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 flex gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />{error}
        </div>
      )}

      {!result ? (
        <>
          {/* Upload */}
          <UploadZone
            label="Upload clinical photo"
            previewUrl={previewUrl}
            loading={uploading}
            onClick={() => fileRef.current?.click()}
          />
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleFile} />

          {visualId && (
            <>
              {/* Region map */}
              <FacialInjectionMap selected={region} onChange={setRegion} />

              {/* Context fields */}
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-medium text-gray-600 block mb-1">Procedure type</label>
                    <input type="text" value={procedure} onChange={e => setProcedure(e.target.value)}
                      placeholder="e.g. lip filler" className="w-full text-sm rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600 block mb-1">Product</label>
                    <input type="text" value={product} onChange={e => setProduct(e.target.value)}
                      placeholder="e.g. Juvederm" className="w-full text-sm rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400" />
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-gray-600 block mb-1">Days post-procedure</label>
                  <input type="number" value={daysPP} onChange={e => setDaysPP(e.target.value === "" ? "" : Number(e.target.value))}
                    placeholder="e.g. 3" className="w-full text-sm rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400" />
                </div>

                <div>
                  <label className="text-xs font-medium text-gray-600 block mb-1">Patient symptoms (comma-separated)</label>
                  <input type="text" value={symptoms} onChange={e => setSymptoms(e.target.value)}
                    placeholder="e.g. pain, swelling, no visual changes" className="w-full text-sm rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400" />
                </div>

                <div>
                  <label className="text-xs font-medium text-gray-600 block mb-1">Clinical notes</label>
                  <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} placeholder="Any additional context..."
                    className="w-full text-sm rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400 resize-none" />
                </div>
              </div>

              {/* Ephemeral toggle */}
              <div className="flex items-center gap-2 text-sm">
                <button
                  onClick={() => setEphemeral(e => !e)}
                  className={`w-9 h-5 rounded-full transition-colors relative ${ephemeral ? "bg-teal-600" : "bg-gray-300"}`}
                >
                  <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${ephemeral ? "translate-x-4" : "translate-x-0.5"}`} />
                </button>
                <span className="text-xs text-gray-600">Delete image from server after analysis</span>
                {ephemeral && <ShieldCheck className="w-3.5 h-3.5 text-teal-600" />}
              </div>

              <Button onClick={analyse} disabled={analyzing} className="w-full bg-teal-700 hover:bg-teal-800 text-white gap-2">
                {analyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
                {analyzing ? "Analysing visual patterns…" : "Run complication vision analysis"}
              </Button>
            </>
          )}
        </>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {previewUrl && !deleted && (
                <img src={previewUrl} alt="Analysed" className="w-10 h-10 rounded-lg object-cover border border-gray-200" />
              )}
              <div>
                <p className="text-sm font-semibold text-gray-900">Vision analysis complete</p>
                <p className="text-xs text-gray-400">{new Date(result.generated_at_utc).toLocaleString()}</p>
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={reset} className="text-xs gap-1 text-gray-500">
              <RefreshCw className="w-3.5 h-3.5" /> New
            </Button>
          </div>

          <VisionAnalysisResult result={result} onRerun={analyse} />

          {/* Manual delete if not ephemeral */}
          {visualId && !deleted && !ephemeral && (
            <Button
              variant="outline" size="sm"
              onClick={async () => { await deletePhoto(visualId, token); setDeleted(true); setPreviewUrl(null); }}
              className="w-full text-xs gap-1.5 text-red-600 border-red-200 hover:bg-red-50"
            >
              <Trash2 className="w-3.5 h-3.5" /> Delete image from server
            </Button>
          )}
          {deleted && (
            <div className="rounded-lg border border-teal-200 bg-teal-50 px-4 py-2.5 flex items-center gap-2 text-xs text-teal-700">
              <CheckCircle className="w-4 h-4 flex-shrink-0" /> Image deleted from server.
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Tab 2: Serial comparison
// ─────────────────────────────────────────────────────────────────

const TRAJ_CONFIG: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
  improving: { bg: "bg-green-50 border-green-300", text: "text-green-800", icon: <CheckCircle className="w-4 h-4" /> },
  stable:    { bg: "bg-blue-50 border-blue-300",   text: "text-blue-800",  icon: <Clock className="w-4 h-4" />     },
  worsening: { bg: "bg-red-50 border-red-400",     text: "text-red-800",   icon: <AlertTriangle className="w-4 h-4" /> },
  mixed:     { bg: "bg-amber-50 border-amber-300", text: "text-amber-800", icon: <Activity className="w-4 h-4" />  },
};

function SerialComparison({ token }: { token: string }) {
  const beforeRef = useRef<HTMLInputElement>(null);
  const afterRef  = useRef<HTMLInputElement>(null);

  const [beforePreview, setBeforePreview] = useState<string | null>(null);
  const [afterPreview,  setAfterPreview]  = useState<string | null>(null);
  const [beforeId,      setBeforeId]      = useState<string | null>(null);
  const [afterId,       setAfterId]       = useState<string | null>(null);
  const [loadingB,      setLoadingB]      = useState(false);
  const [loadingA,      setLoadingA]      = useState(false);

  const [days,      setDays]      = useState<number | "">("");
  const [procedure, setProcedure] = useState("");

  const [result,   setResult]   = useState<SerialResult | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  const handleUpload = async (
    file: File,
    setPreview: (u: string) => void,
    setId: (id: string) => void,
    setLoading: (b: boolean) => void
  ) => {
    setPreview(URL.createObjectURL(file));
    setLoading(true);
    try {
      const { visual_id } = await uploadPhoto(file, token);
      setId(visual_id);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const compare = async () => {
    if (!beforeId || !afterId) return;
    setLoading(true); setError(null);
    try {
      const data = await runSerialCompare(beforeId, afterId, {
        days_between: days !== "" ? Number(days) : undefined,
        procedure_type: procedure || undefined,
      }, token);
      setResult(data);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const traj = result ? (TRAJ_CONFIG[result.overall_trajectory] || TRAJ_CONFIG.stable) : null;

  return (
    <div className="space-y-5">
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {/* Upload pair */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs font-medium text-gray-600 mb-1.5">Before / earlier photo</p>
          <UploadZone label="Upload before photo" previewUrl={beforePreview} loading={loadingB}
            onClick={() => beforeRef.current?.click()} />
          <input ref={beforeRef} type="file" accept="image/*" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if(f) handleUpload(f, setBeforePreview, setBeforeId, setLoadingB); }} />
        </div>
        <div>
          <p className="text-xs font-medium text-gray-600 mb-1.5">After / latest photo</p>
          <UploadZone label="Upload after photo" previewUrl={afterPreview} loading={loadingA}
            onClick={() => afterRef.current?.click()} />
          <input ref={afterRef} type="file" accept="image/*" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if(f) handleUpload(f, setAfterPreview, setAfterId, setLoadingA); }} />
        </div>
      </div>

      {beforeId && afterId && !result && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Days between photos</label>
              <input type="number" value={days} onChange={e => setDays(e.target.value === "" ? "" : Number(e.target.value))}
                placeholder="e.g. 7" className="w-full text-sm rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400" />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Procedure</label>
              <input type="text" value={procedure} onChange={e => setProcedure(e.target.value)}
                placeholder="e.g. lip filler" className="w-full text-sm rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400" />
            </div>
          </div>
          <Button onClick={compare} disabled={loading} className="w-full bg-teal-700 hover:bg-teal-800 text-white gap-2">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowLeftRight className="w-4 h-4" />}
            {loading ? "Comparing…" : "Compare healing progress"}
          </Button>
        </>
      )}

      {/* Serial result */}
      {result && traj && (
        <div className="space-y-4">
          {/* Trajectory banner */}
          <div className={`rounded-xl border-2 px-4 py-3 ${traj.bg}`}>
            <div className="flex items-center gap-2 mb-1">
              <span className={traj.text}>{traj.icon}</span>
              <span className={`font-bold text-sm capitalize ${traj.text}`}>
                {result.overall_trajectory}
              </span>
            </div>
            <p className={`text-sm ${traj.text} opacity-80`}>{result.change_summary}</p>
          </div>

          {/* Feature lists */}
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Improving",  items: result.improving_features, color: "text-green-700", bg: "bg-green-50 border-green-200"  },
              { label: "Stable",     items: result.stable_features,    color: "text-blue-700",  bg: "bg-blue-50 border-blue-200"    },
              { label: "Worsening",  items: result.worsening_features,  color: "text-red-700",   bg: "bg-red-50 border-red-200"      },
            ].map(({ label, items, color, bg }) => (
              <div key={label} className={`rounded-lg border p-3 ${bg}`}>
                <p className={`text-xs font-bold mb-2 ${color}`}>{label}</p>
                {items.length ? (
                  <ul className="space-y-1">
                    {items.map((f, i) => (
                      <li key={i} className={`text-xs ${color} opacity-80`}>{f}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-gray-400 italic">None</p>
                )}
              </div>
            ))}
          </div>

          {/* Interpretation */}
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 space-y-2">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Clinical interpretation</p>
            <p className="text-sm text-gray-700">{result.clinical_interpretation}</p>
          </div>

          {/* Action */}
          <div className="rounded-lg border border-teal-200 bg-teal-50 px-4 py-3">
            <p className="text-xs font-semibold text-teal-600 uppercase tracking-wide mb-1">Recommended action</p>
            <p className="text-sm text-teal-800 font-medium">{result.recommended_action}</p>
          </div>

          <Button variant="outline" size="sm" onClick={() => setResult(null)} className="w-full text-xs gap-1.5">
            <RefreshCw className="w-3.5 h-3.5" /> New comparison
          </Button>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────

export default function VisionAnalysisPage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<"single" | "serial">("single");

  return (
    <div className="max-w-xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <Activity className="w-5 h-5 text-teal-600" />
          <h1 className="text-lg font-bold text-gray-900">AesthetiCite Vision</h1>
          <span className="text-xs bg-teal-100 text-teal-700 px-2 py-0.5 rounded-full font-medium">Beta</span>
        </div>
        <p className="text-xs text-gray-500 leading-relaxed">
          AI highlights visual patterns that may indicate complications and guides next steps.
          Not a diagnosis — clinical assessment remains the clinician's responsibility.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-lg p-1 mb-6">
        {[
          { id: "single",  label: "Single photo",       icon: <Activity className="w-3.5 h-3.5" />     },
          { id: "serial",  label: "Healing tracker",    icon: <ArrowLeftRight className="w-3.5 h-3.5" /> },
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id as any)}
            className={`
              flex-1 flex items-center justify-center gap-1.5 text-xs font-medium py-2 rounded-md transition-all
              ${tab === t.id ? "bg-white text-teal-700 shadow-sm" : "text-gray-500 hover:text-gray-700"}
            `}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === "single" && <SingleAnalysis token={token!} />}
      {tab === "serial" && <SerialComparison token={token!} />}
    </div>
  );
}
