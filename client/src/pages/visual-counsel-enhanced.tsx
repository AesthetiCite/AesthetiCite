/**
 * VisualCounselEnhanced — master integration of all 6 visual DX improvements.
 * Drop-in replacement for /visual-counsel page content.
 */

import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import {
  Upload, ShieldCheck, Trash2, ChevronDown, ChevronUp,
  Loader2, AlertTriangle, CheckCircle, RefreshCw, ArrowLeft
} from "lucide-react";
import { Link } from "wouter";
import { useAuth } from "@/hooks/use-auth";
import { createConversation } from "@/lib/auth";

import { FacialInjectionMap, type FacialRegionId, FACIAL_REGIONS } from "@/components/FacialInjectionMap";
import { Top3SummaryCard, GuidedQuestions, answersToContext } from "@/components/GuidedWorkup";
import { ReferenceImageComparison } from "@/components/ReferenceImageComparison";
import { PatientExplanation } from "@/components/PatientExplanation";
import { VisualDifferential } from "@/components/VisualDifferential";

interface DifferentialResult {
  request_id: string;
  visual_id: string;
  overall_urgency: string;
  urgency_rationale: string;
  visual_summary: string;
  differential: any[];
  immediate_actions: any[];
  protocol_trigger: any;
  evidence: any[];
  disclaimer: string;
  limitations: string[];
}

async function uploadImage(file: File, token: string, conversationId: string): Promise<{ visual_id: string }> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("conversation_id", conversationId);
  fd.append("kind", "complication_photo");
  const res = await fetch("/api/visual/upload", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Upload failed");
  }
  return res.json();
}

async function runDifferential(
  visualId: string,
  context: {
    injectedRegion?: string;
    productType?: string;
    timeSinceInjection?: number;
    clinicalContext?: string;
    additionalSymptoms?: string[];
  },
  token: string
): Promise<DifferentialResult> {
  const res = await fetch("/api/visual/differential", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      visual_id: visualId,
      injected_region: context.injectedRegion || null,
      product_type: context.productType || null,
      time_since_injection_minutes: context.timeSinceInjection ?? null,
      clinical_context: context.clinicalContext || null,
      additional_symptoms: context.additionalSymptoms || [],
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Analysis failed");
  }
  return res.json();
}

async function deleteImage(visualId: string, token: string): Promise<void> {
  await fetch(`/api/visual/delete/${visualId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}

const STEPS = ["Upload", "Region", "Context", "Analysis"] as const;
type Step = 0 | 1 | 2 | 3;

function StepBar({ step }: { step: Step }) {
  return (
    <div className="flex items-center gap-0 mb-6">
      {STEPS.map((label, i) => (
        <span key={label} className="contents">
          <div className="flex flex-col items-center">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-200 ${
              i < step  ? "bg-teal-600 text-white" :
              i === step ? "bg-teal-700 text-white ring-2 ring-teal-300" :
                           "bg-gray-200 text-gray-500"
            }`}>
              {i < step ? <CheckCircle className="w-4 h-4" /> : i + 1}
            </div>
            <span className={`text-xs mt-1 font-medium ${i === step ? "text-teal-700" : "text-gray-400"}`}>
              {label}
            </span>
          </div>
          {i < STEPS.length - 1 && (
            <div className={`flex-1 h-0.5 mb-4 mx-1 ${i < step ? "bg-teal-600" : "bg-gray-200"}`} />
          )}
        </span>
      ))}
    </div>
  );
}

export default function VisualCounselEnhanced() {
  const { token, user, loading: authLoading } = useAuth();

  const [step, setStep] = useState<Step>(0);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [visualId, setVisualId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const conversationIdRef = useRef<string>("");

  const [region, setRegion] = useState<FacialRegionId | null>(null);
  const [product, setProduct] = useState("");
  const [timeMins, setTimeMins] = useState<number | "">("");
  const [symptoms, setSymptoms] = useState("");

  const [ephemeral, setEphemeral] = useState(false);
  const [imageDeleted, setImageDeleted] = useState(false);

  const [result, setResult] = useState<DifferentialResult | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showReference, setShowReference] = useState(true);
  const [showGuidedQ, setShowGuidedQ] = useState(true);
  const [showEvidence, setShowEvidence] = useState(false);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f || !token || !user) return;
    setFile(f);
    setPreviewUrl(URL.createObjectURL(f));
    setUploading(true);
    setError(null);
    try {
      if (!conversationIdRef.current) {
        conversationIdRef.current = await createConversation(user.id, "Visual Complication Analysis");
      }
      const { visual_id } = await uploadImage(f, token, conversationIdRef.current);
      setVisualId(visual_id);
      setStep(1);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleAnalyze = async (extraContext?: string) => {
    if (!visualId || !token) return;
    setAnalyzing(true);
    setError(null);
    try {
      const ctx = [symptoms, extraContext].filter(Boolean).join(". ");
      const data = await runDifferential(visualId, {
        injectedRegion: region ? FACIAL_REGIONS.find(r => r.id === region)?.label : undefined,
        productType: product || undefined,
        timeSinceInjection: timeMins !== "" ? Number(timeMins) : undefined,
        clinicalContext: ctx || undefined,
      }, token);
      setResult(data);
      setStep(3);
      if (ephemeral) {
        await deleteImage(visualId, token);
        setImageDeleted(true);
        setPreviewUrl(null);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleRefinement = async (answers: any) => {
    const extra = answersToContext(answers);
    if (extra) await handleAnalyze(extra);
  };

  const handleDeleteImage = async () => {
    if (!visualId || !token) return;
    await deleteImage(visualId, token);
    setImageDeleted(true);
    setPreviewUrl(null);
  };

  const reset = () => {
    setStep(0); setFile(null); setPreviewUrl(null); setVisualId(null);
    setRegion(null); setProduct(""); setTimeMins(""); setSymptoms("");
    setResult(null); setError(null); setImageDeleted(false);
    conversationIdRef.current = "";
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-teal-600" />
      </div>
    );
  }

  const topDiagnosis = result?.differential?.[0];
  const topProtocolKey = topDiagnosis?.protocol_key || result?.protocol_trigger?.protocol_key || null;

  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <div className="border-b border-border px-4 py-3 flex items-center gap-3">
        <Link href="/ask">
          <Button variant="ghost" size="sm" className="gap-1.5 text-xs">
            <ArrowLeft className="w-3.5 h-3.5" /> Back
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-sm font-bold text-foreground">Visual Complication Analysis</h1>
          <p className="text-xs text-muted-foreground">Upload · Region · Context · Differential</p>
        </div>
        {step > 0 && (
          <Button variant="ghost" size="sm" onClick={reset} className="text-xs gap-1 text-muted-foreground">
            <RefreshCw className="w-3.5 h-3.5" /> New
          </Button>
        )}
      </div>

      <div className="max-w-xl mx-auto px-4 py-6 space-y-5">

        <StepBar step={step} />

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Step 0: Upload */}
        {step === 0 && (
          <div className="space-y-3">
            <div
              className="border-2 border-dashed border-gray-300 rounded-xl p-8 flex flex-col items-center gap-3 cursor-pointer hover:border-teal-400 hover:bg-teal-50 transition-all"
              onClick={() => fileRef.current?.click()}
              data-testid="dropzone-visual-upload"
            >
              <div className="w-12 h-12 rounded-full bg-teal-100 flex items-center justify-center">
                <Upload className="w-6 h-6 text-teal-600" />
              </div>
              <p className="text-sm font-semibold text-gray-700">Upload clinical photo</p>
              <p className="text-xs text-gray-400 text-center">
                Post-injection complications, skin reactions, suspected VO, ptosis, nodules
              </p>
              {uploading && <Loader2 className="w-5 h-5 animate-spin text-teal-600" />}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFileSelect}
              data-testid="input-visual-file"
            />

            {/* Ephemeral toggle */}
            <div className="flex items-center gap-2 text-sm">
              <button
                onClick={() => setEphemeral(e => !e)}
                data-testid="toggle-ephemeral"
                className={`w-9 h-5 rounded-full transition-colors relative ${ephemeral ? "bg-teal-600" : "bg-gray-300"}`}
              >
                <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${ephemeral ? "translate-x-4" : "translate-x-0.5"}`} />
              </button>
              <span className="text-xs text-gray-600">Delete image from server immediately after analysis</span>
              {ephemeral && (
                <span className="text-xs text-teal-600 font-medium flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3" /> Ephemeral mode on
                </span>
              )}
            </div>
          </div>
        )}

        {/* Step 1: Region */}
        {step === 1 && (
          <div className="space-y-4">
            {previewUrl && (
              <img src={previewUrl} alt="Uploaded" className="w-24 h-24 object-cover rounded-xl border border-gray-200 mx-auto" />
            )}
            <FacialInjectionMap selected={region} onChange={setRegion} />
            <Button
              onClick={() => setStep(2)}
              className="w-full bg-teal-700 hover:bg-teal-800 text-white"
              data-testid="button-region-continue"
            >
              {region ? `Continue — ${FACIAL_REGIONS.find(r => r.id === region)?.label}` : "Skip region →"}
            </Button>
          </div>
        )}

        {/* Step 2: Context */}
        {step === 2 && (
          <div className="space-y-4">
            <p className="text-sm font-semibold text-gray-700">Add clinical context (optional)</p>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">Product / filler type</label>
                <input
                  type="text"
                  value={product}
                  onChange={e => setProduct(e.target.value)}
                  placeholder="e.g. Juvederm Ultra, Botox 50U"
                  className="w-full text-sm rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400"
                  data-testid="input-product-type"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">Time since injection (minutes)</label>
                <input
                  type="number"
                  value={timeMins}
                  onChange={e => setTimeMins(e.target.value === "" ? "" : Number(e.target.value))}
                  placeholder="e.g. 15"
                  className="w-full text-sm rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400"
                  data-testid="input-time-mins"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">Additional symptoms</label>
                <textarea
                  value={symptoms}
                  onChange={e => setSymptoms(e.target.value)}
                  placeholder="e.g. patient reports pain, blanching visible, no visual symptoms"
                  rows={2}
                  className="w-full text-sm rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400 resize-none"
                  data-testid="input-symptoms"
                />
              </div>
            </div>
            <Button
              onClick={() => handleAnalyze()}
              disabled={analyzing}
              className="w-full bg-teal-700 hover:bg-teal-800 text-white gap-2"
              data-testid="button-run-analysis"
            >
              {analyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              {analyzing ? "Analysing…" : "Run differential analysis"}
            </Button>
          </div>
        )}

        {/* Step 3: Results */}
        {step === 3 && result && (
          <div className="space-y-5">

            {/* Top-3 summary (Improvement 3) */}
            <Top3SummaryCard differential={result.differential} />

            {/* Full differential */}
            <VisualDifferential
              visualId={result.visual_id}
              token={token!}
              injectedRegion={region ? FACIAL_REGIONS.find(r => r.id === region)?.label : undefined}
              onProtocolTrigger={(trigger) => {
                if (trigger.triggered && trigger.urgency === "immediate") {
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }
              }}
            />

            {/* Reference image comparison (Improvement 4) */}
            {topProtocolKey && (
              <div>
                <button
                  className="flex items-center gap-2 text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2"
                  onClick={() => setShowReference(s => !s)}
                >
                  Reference comparison
                  {showReference ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </button>
                {showReference && (
                  <ReferenceImageComparison
                    uploadedImageUrl={imageDeleted ? null : previewUrl}
                    protocolKey={topProtocolKey}
                    diagnosis={topDiagnosis?.diagnosis || ""}
                  />
                )}
              </div>
            )}

            {/* Guided questions (Improvement 1) */}
            <div>
              <button
                className="flex items-center gap-2 text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2"
                onClick={() => setShowGuidedQ(s => !s)}
              >
                Refine with clinical questions
                {showGuidedQ ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>
              {showGuidedQ && (
                <GuidedQuestions
                  urgency={result.overall_urgency}
                  topDiagnosis={topDiagnosis?.diagnosis}
                  onRefine={handleRefinement}
                  loading={analyzing}
                />
              )}
            </div>

            {/* Patient explanation (Improvement 5) */}
            <PatientExplanation
              differential={result.differential}
              visualSummary={result.visual_summary}
              token={token!}
            />

            {/* Evidence (collapsible) */}
            {result.evidence?.length > 0 && (
              <div>
                <button
                  className="flex items-center gap-2 text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2"
                  onClick={() => setShowEvidence(s => !s)}
                >
                  Evidence ({result.evidence.length})
                  {showEvidence ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </button>
                {showEvidence && (
                  <div className="space-y-1.5">
                    {result.evidence.map((e: any, i: number) => (
                      <div key={i} className="flex gap-2 text-xs text-gray-600">
                        <span className="font-mono text-gray-400">[{e.source_id}]</span>
                        <span><span className="font-medium">{e.title}</span> — {e.note}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Image deletion (Improvement 6) */}
            {visualId && !imageDeleted && (
              <div className={`rounded-lg border px-4 py-3 flex items-center justify-between gap-3 ${
                ephemeral ? "border-red-200 bg-red-50" : "border-gray-200 bg-gray-50"
              }`}>
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-gray-500 flex-shrink-0" />
                  <span className="text-xs text-gray-600">
                    {ephemeral
                      ? "Ephemeral mode: image is ready to be deleted"
                      : "Image is stored on server. Delete it now if not needed."}
                  </span>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDeleteImage}
                  className="text-xs gap-1 text-red-600 border-red-200 hover:bg-red-50 flex-shrink-0"
                  data-testid="button-delete-image"
                >
                  <Trash2 className="w-3 h-3" /> Delete image
                </Button>
              </div>
            )}

            {imageDeleted && (
              <div className="rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 flex items-center gap-2 text-xs text-teal-700">
                <CheckCircle className="w-4 h-4 flex-shrink-0" />
                Image deleted from server. No image data is retained.
              </div>
            )}

            <p className="text-xs text-gray-400 italic leading-relaxed">{result.disclaimer}</p>
          </div>
        )}
      </div>
    </div>
  );
}
