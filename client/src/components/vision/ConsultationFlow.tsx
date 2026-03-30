/**
 * ConsultationFlow.tsx
 * ---------------------
 * Nextmotion-inspired 5-step visual consultation workflow.
 * Orchestrates the complete AesthetiCite Vision experience:
 *
 *   Step 1 → Capture     — PoseCaptureGuide (standardised angles)
 *   Step 2 → Analyse     — GPT-4o visual analysis + structured scores
 *   Step 3 → Signals     — Complication protocol bridge alerts
 *   Step 4 → Simulate    — SkinGPT treated vs untreated outcomes
 *   Step 5 → Export      — PDF session report
 *
 * Usage:
 *   <ConsultationFlow token={token} clinicianId={user.id} />
 */

import { useState, useCallback, useRef } from "react";
import {
  Camera, Cpu, ShieldAlert, Sparkles, FileDown,
  ChevronRight, ChevronLeft, CheckCircle2, Loader2,
  AlertTriangle, RefreshCw, Clock
} from "lucide-react";
import { PoseCaptureGuide } from "./PoseCaptureGuide";
import { VisualScoreCard, type VisualScores } from "./VisualScoreCard";

// ─── Types ────────────────────────────────────────────────────────────────────

interface TriggeredProtocol {
  protocol_key: string;
  protocol_name: string;
  urgency: "critical" | "high" | "moderate";
  confidence: number;
  detected_signals: string[];
  headline: string;
  immediate_action: string;
  view_protocol_url: string;
}

interface SimulationScenario {
  scenario_id: string;
  label: string;
  treatment: string;
  timeline_weeks: number;
  expected_outcome: string;
  image_b64: string | null;
  is_mock: boolean;
  mock_message?: string;
}

interface SimulationResult {
  complication_key: string;
  complication_label: string;
  complication_description: string;
  scenarios: SimulationScenario[];
}

type StepKey = "capture" | "analyse" | "signals" | "simulate" | "export";

interface StepConfig {
  key: StepKey;
  label: string;
  icon: React.ReactNode;
}

interface ConsultationFlowProps {
  token: string;
  clinicianId?: string;
  clinicId?: string;
}

// ─── Step configuration ───────────────────────────────────────────────────────

const STEPS: StepConfig[] = [
  { key: "capture",  label: "Capture",  icon: <Camera className="h-4 w-4" /> },
  { key: "analyse",  label: "Analyse",  icon: <Cpu className="h-4 w-4" /> },
  { key: "signals",  label: "Signals",  icon: <ShieldAlert className="h-4 w-4" /> },
  { key: "simulate", label: "Simulate", icon: <Sparkles className="h-4 w-4" /> },
  { key: "export",   label: "Export",   icon: <FileDown className="h-4 w-4" /> },
];

// ─── Step bar ─────────────────────────────────────────────────────────────────

function StepBar({ current, completed }: { current: StepKey; completed: Set<StepKey> }) {
  const idx = STEPS.findIndex(s => s.key === current);
  return (
    <div className="flex items-center gap-0">
      {STEPS.map((step, i) => {
        const done = completed.has(step.key);
        const active = step.key === current;
        return (
          <div key={step.key} className="flex items-center">
            <div className="flex flex-col items-center">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300 border-2
                ${done
                  ? "bg-green-500 border-green-500 text-white"
                  : active
                    ? "bg-blue-600 border-blue-600 text-white shadow-lg shadow-blue-500/20"
                    : "bg-transparent border-gray-300 dark:border-gray-600 text-muted-foreground"
                }`}>
                {done ? <CheckCircle2 className="h-4 w-4" /> : step.icon}
              </div>
              <span className={`text-xs mt-1 font-medium hidden sm:block whitespace-nowrap
                ${active ? "text-foreground" : "text-muted-foreground"}`}>
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`h-0.5 w-8 sm:w-12 mx-1 transition-all duration-300 ${
                i < idx ? "bg-green-400" : "bg-gray-200 dark:bg-gray-700"
              }`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Urgency badge ────────────────────────────────────────────────────────────

function UrgencyBadge({ urgency }: { urgency: string }) {
  const map: Record<string, string> = {
    critical: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300 border-red-200",
    high:     "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300 border-orange-200",
    moderate: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300 border-yellow-200",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border font-semibold uppercase tracking-wide ${map[urgency] ?? map.moderate}`}>
      {urgency}
    </span>
  );
}

// ─── Protocol card ────────────────────────────────────────────────────────────

function ProtocolCard({ p }: { p: TriggeredProtocol }) {
  const [expanded, setExpanded] = useState(p.urgency === "critical");
  return (
    <div className={`rounded-lg border-l-4 p-3 space-y-2
      ${p.urgency === "critical" ? "border-red-500 bg-red-50 dark:bg-red-950/20"
        : p.urgency === "high" ? "border-orange-400 bg-orange-50 dark:bg-orange-950/20"
        : "border-yellow-400 bg-yellow-50 dark:bg-yellow-950/20"}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2">
          <AlertTriangle className={`h-4 w-4 flex-shrink-0 mt-0.5 ${
            p.urgency === "critical" ? "text-red-600" : p.urgency === "high" ? "text-orange-500" : "text-yellow-500"
          }`} />
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <UrgencyBadge urgency={p.urgency} />
              <span className="text-sm font-semibold text-foreground">{p.protocol_name}</span>
            </div>
            <p className="text-xs text-foreground mt-0.5">{p.headline}</p>
          </div>
        </div>
        <button onClick={() => setExpanded(v => !v)} className="text-muted-foreground text-xs underline flex-shrink-0">
          {expanded ? "Less" : "More"}
        </button>
      </div>
      {expanded && (
        <div className="pl-6 space-y-2">
          <p className="text-xs text-foreground"><span className="font-semibold">Action: </span>{p.immediate_action}</p>
          <div className="flex flex-wrap gap-1">
            {p.detected_signals.map(s => (
              <span key={s} className="text-xs bg-white/70 dark:bg-white/10 border border-gray-200 dark:border-gray-600 rounded px-1.5 py-0.5 text-muted-foreground">
                {s.replace(/_/g, " ")}
              </span>
            ))}
          </div>
          <a href={p.view_protocol_url} className="text-xs text-blue-600 dark:text-blue-400 hover:underline">
            Open full protocol →
          </a>
        </div>
      )}
    </div>
  );
}

// ─── Simulation card ──────────────────────────────────────────────────────────

function SimulationCard({ result }: { result: SimulationResult }) {
  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <div className="px-4 py-2.5 bg-gray-50 dark:bg-gray-900 border-b border-border">
        <p className="text-sm font-semibold text-foreground">{result.complication_label}</p>
        <p className="text-xs text-muted-foreground">{result.complication_description}</p>
      </div>
      <div className="grid grid-cols-2 divide-x divide-border">
        {result.scenarios.map(sc => (
          <div key={sc.scenario_id} className="p-3 space-y-2">
            <p className="text-xs font-semibold text-foreground">{sc.label}</p>
            {sc.image_b64 ? (
              <img
                src={`data:image/jpeg;base64,${sc.image_b64}`}
                alt={sc.label}
                className="w-full rounded-lg object-cover"
                style={{ aspectRatio: "3/4" }}
              />
            ) : (
              <div
                className="w-full rounded-lg bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-800 dark:to-gray-700 flex flex-col items-center justify-center gap-2 p-4"
                style={{ aspectRatio: "3/4" }}
              >
                {sc.is_mock ? (
                  <>
                    <Sparkles className="h-6 w-6 text-gray-400" />
                    <p className="text-xs text-muted-foreground text-center">
                      Live simulation requires SkinGPT API key
                    </p>
                  </>
                ) : (
                  <Loader2 className="h-6 w-6 text-gray-400 animate-spin" />
                )}
              </div>
            )}
            <p className="text-xs text-muted-foreground leading-relaxed">{sc.expected_outcome}</p>
            {sc.is_mock && (
              <p className="text-xs text-blue-600 dark:text-blue-400">↗ Activate at haut.ai/contact</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function ConsultationFlow({ token, clinicianId, clinicId }: ConsultationFlowProps) {
  const [currentStep, setCurrentStep] = useState<StepKey>("capture");
  const [completed, setCompleted] = useState<Set<StepKey>>(new Set());

  const [capturedFiles, setCapturedFiles] = useState<Record<string, File>>({});
  const [uploadedVisualId, setUploadedVisualId] = useState<string | null>(null);
  const [analysisText, setAnalysisText] = useState<string>("");
  const [visualScores, setVisualScores] = useState<VisualScores | null>(null);
  const [triggeredProtocols, setTriggeredProtocols] = useState<TriggeredProtocol[]>([]);
  const [simulations, setSimulations] = useState<SimulationResult[]>([]);
  const [clinicianNotes, setClinicianNotes] = useState("");
  const [patientRef, setPatientRef] = useState("");

  const [loading, setLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState("");
  const [error, setError] = useState<string | null>(null);

  const startTime = useRef<number | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);

  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const markComplete = (step: StepKey) => setCompleted(prev => new Set(Array.from(prev).concat(step)));
  const advance = (to: StepKey) => { setCurrentStep(to); setError(null); };

  // ── Step 1: Capture ─────────────────────────────────────────────────────────
  const handleCaptureComplete = useCallback(async (files: Record<string, File>) => {
    setCapturedFiles(files);
    markComplete("capture");
    startTime.current = Date.now();

    const front = files.front || Object.values(files)[0];
    if (!front) return;

    try {
      setLoading(true);
      setLoadingMsg("Uploading image…");
      setCurrentStep("analyse");

      const fd = new FormData();
      fd.append("file", front);
      fd.append("conversation_id", `consult_${Date.now()}`);
      fd.append("kind", "photo");

      const uploadRes = await fetch("/api/visual/upload", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      const uploadData = await uploadRes.json();
      if (!uploadRes.ok) throw new Error(uploadData.detail || "Upload failed");
      setUploadedVisualId(uploadData.visual_id);
      setLoadingMsg("Running visual analysis…");
      await runAnalysis(uploadData.visual_id, front);
    } catch (e: any) {
      setError(e.message);
      setLoading(false);
    }
  }, [token]);

  // ── Step 2: Analysis ────────────────────────────────────────────────────────
  const runAnalysis = async (visualId: string, _frontFile: File) => {
    try {
      const streamRes = await fetch("/api/ask/visual/stream", {
        method: "POST",
        headers,
        body: JSON.stringify({
          q: "Assess this image for post-injectable complication signals using the structured safety assessment format.",
          conversation_id: `consult_${Date.now()}`,
          visual_id: visualId,
          k: 10,
        }),
      });

      if (!streamRes.ok) throw new Error("Visual analysis failed");

      const reader = streamRes.body?.getReader();
      if (!reader) throw new Error("No stream");

      const decoder = new TextDecoder();
      let buffer = "";
      let fullText = "";
      let scores: VisualScores | null = null;
      let protocols: TriggeredProtocol[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === "content" && typeof data.data === "string") {
              fullText += data.data;
              setAnalysisText(fullText);
            }
            if (data.type === "visual_scores" && data.data) {
              scores = data.data;
              setVisualScores(data.data);
            }
            if (data.type === "protocol_alert") {
              protocols = data.triggered_protocols ?? [];
              setTriggeredProtocols(protocols);
            }
          } catch {}
        }
      }

      setAnalysisText(fullText);
      if (scores) setVisualScores(scores);
      if (protocols.length) setTriggeredProtocols(protocols);

      markComplete("analyse");
      setLoading(false);
      advance("signals");
    } catch (e: any) {
      setError(e.message);
      setLoading(false);
    }
  };

  // ── Step 3: Signals confirmed ────────────────────────────────────────────────
  const handleSignalsConfirmed = () => {
    markComplete("signals");
    advance("simulate");
    runSimulations();
  };

  // ── Step 4: Simulations ─────────────────────────────────────────────────────
  const runSimulations = async () => {
    const detectedSignals = [
      ...(visualScores?.tyndall_flag ? ["tyndall_flag"] : []),
      ...(visualScores?.skin_colour_change != null && visualScores.skin_colour_change >= 3 ? ["blanching"] : []),
      ...(visualScores?.skin_colour_change != null && visualScores.skin_colour_change === 2 ? ["mottling"] : []),
      ...(visualScores?.skin_colour_change != null && visualScores.skin_colour_change === 1 ? ["erythema"] : []),
      ...(visualScores?.infection_signal != null && visualScores.infection_signal >= 2 ? ["infection_signs"] : []),
      ...(visualScores?.swelling_severity != null && visualScores.swelling_severity >= 1 ? ["swelling"] : []),
      ...triggeredProtocols.flatMap(p => p.detected_signals),
    ];

    if (detectedSignals.length === 0) {
      markComplete("simulate");
      advance("export");
      return;
    }

    try {
      setLoadingMsg("Running SkinGPT outcome simulations…");
      setLoading(true);

      const simRes = await fetch("/api/visual/simulate-scenarios", {
        method: "POST",
        headers,
        body: JSON.stringify({
          visual_id: uploadedVisualId,
          detected_signals: Array.from(new Set(detectedSignals)),
          fitzpatrick_type: visualScores?.fitzpatrick_type,
          clinician_id: clinicianId,
          max_scenarios: 2,
        }),
      });

      if (!simRes.ok) throw new Error("Simulation failed");
      const simData = await simRes.json();
      setSimulations(simData.simulations ?? []);
    } catch (e: any) {
      setError(`Simulation unavailable: ${e.message}. You can continue to export.`);
    } finally {
      setLoading(false);
      markComplete("simulate");
    }
  };

  // ── Step 5: Export PDF ──────────────────────────────────────────────────────
  const handleExport = async () => {
    try {
      setLoading(true);
      setLoadingMsg("Generating PDF report…");

      const exportRes = await fetch("/api/visual/export-pdf", {
        method: "POST",
        headers,
        body: JSON.stringify({
          clinician_id: clinicianId,
          clinic_id: clinicId,
          patient_ref: patientRef || undefined,
          visual_id: uploadedVisualId,
          analysis_text: analysisText,
          triggered_protocols: triggeredProtocols,
          notes: clinicianNotes || undefined,
        }),
      });

      if (!exportRes.ok) throw new Error("PDF export failed");
      const exportData = await exportRes.json();

      const a = document.createElement("a");
      a.href = `/api/visual/download-pdf/${exportData.filename}`;
      a.download = exportData.filename;
      a.click();

      if (startTime.current) {
        setElapsed(Math.round((Date.now() - startTime.current) / 1000));
      }
      markComplete("export");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const restart = () => {
    setCurrentStep("capture");
    setCompleted(new Set());
    setCapturedFiles({});
    setUploadedVisualId(null);
    setAnalysisText("");
    setVisualScores(null);
    setTriggeredProtocols([]);
    setSimulations([]);
    setClinicianNotes("");
    setPatientRef("");
    setError(null);
    setElapsed(null);
    startTime.current = null;
  };

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 pb-8">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-muted-foreground">Photo → Analysis → Protocols → Outcomes → PDF</p>
        </div>
        <div className="flex items-center gap-2">
          {elapsed !== null && (
            <div className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
              <Clock className="h-3.5 w-3.5" />
              {elapsed}s
            </div>
          )}
          {completed.size > 0 && (
            <button
              data-testid="button-consultation-new"
              onClick={restart}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground border border-border rounded-lg px-2.5 py-1.5 transition-colors"
            >
              <RefreshCw className="h-3 w-3" />
              New
            </button>
          )}
        </div>
      </div>

      {/* Step bar */}
      <div className="flex justify-center">
        <StepBar current={currentStep} completed={completed} />
      </div>

      {/* Error banner */}
      {error && (
        <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/20 px-4 py-3 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center gap-3 rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/20 px-4 py-4">
          <Loader2 className="h-5 w-5 text-blue-500 animate-spin flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-blue-700 dark:text-blue-300">{loadingMsg}</p>
            <p className="text-xs text-blue-500">This takes a few seconds…</p>
          </div>
        </div>
      )}

      {/* ── Step 1: Capture ───────────────────────────────────────────────────── */}
      {currentStep === "capture" && (
        <div className="space-y-4">
          <div>
            <input
              type="text"
              value={patientRef}
              onChange={e => setPatientRef(e.target.value)}
              placeholder="Patient reference (optional, de-identified)"
              data-testid="input-patient-ref"
              className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
          </div>
          <PoseCaptureGuide
            onComplete={handleCaptureComplete}
            token={token}
            mode="serial"
            required={["front"]}
          />
        </div>
      )}

      {/* ── Step 2: Analysis ──────────────────────────────────────────────────── */}
      {currentStep === "analyse" && !loading && analysisText && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border overflow-hidden">
            <div className="px-4 py-3 bg-gray-50 dark:bg-gray-900 border-b border-border flex items-center gap-2">
              <Cpu className="h-4 w-4 text-blue-500" />
              <p className="text-sm font-semibold text-foreground">Visual Analysis</p>
            </div>
            <div className="p-4">
              <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">{analysisText}</p>
            </div>
          </div>

          {visualScores && (
            <VisualScoreCard scores={visualScores} analysedAt={new Date().toISOString()} />
          )}

          <button
            data-testid="button-review-signals"
            onClick={() => { markComplete("analyse"); advance("signals"); }}
            className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl px-4 py-3 text-sm font-medium transition-colors"
          >
            Review complication signals
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* ── Step 3: Signals ───────────────────────────────────────────────────── */}
      {currentStep === "signals" && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <ShieldAlert className={`h-5 w-5 ${triggeredProtocols.length ? "text-orange-500" : "text-green-500"}`} />
            <h2 className="text-sm font-bold text-foreground">
              {triggeredProtocols.length
                ? `${triggeredProtocols.length} complication protocol${triggeredProtocols.length > 1 ? "s" : ""} triggered`
                : "No complication signals detected"
              }
            </h2>
          </div>

          {triggeredProtocols.length > 0 ? (
            <div className="space-y-2">
              {triggeredProtocols.map(p => (
                <ProtocolCard key={p.protocol_key} p={p} />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 px-4 py-4 flex items-center gap-3">
              <CheckCircle2 className="h-5 w-5 text-green-500 flex-shrink-0" />
              <p className="text-sm text-green-700 dark:text-green-300">
                No significant complication signals detected. Standard post-treatment monitoring applies.
              </p>
            </div>
          )}

          <div className="flex gap-2">
            <button
              data-testid="button-back-analyse"
              onClick={() => advance("analyse")}
              className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg border border-border text-foreground hover:bg-muted transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
              Back
            </button>
            <button
              data-testid="button-confirm-signals"
              onClick={handleSignalsConfirmed}
              className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl px-4 py-2.5 text-sm font-medium transition-colors"
            >
              {triggeredProtocols.length ? "Run outcome simulations" : "Continue to export"}
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* ── Step 4: Simulate ──────────────────────────────────────────────────── */}
      {currentStep === "simulate" && !loading && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-purple-500" />
            <h2 className="text-sm font-bold text-foreground">Treatment outcome simulation</h2>
            <span className="text-xs text-muted-foreground ml-auto">Powered by SkinGPT</span>
          </div>

          {simulations.length > 0 ? (
            <div className="space-y-4">
              {simulations.map(sim => (
                <SimulationCard key={sim.complication_key} result={sim} />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-border bg-gray-50 dark:bg-gray-900 px-4 py-6 text-center space-y-2">
              <Sparkles className="h-8 w-8 text-gray-300 mx-auto" />
              <p className="text-sm text-muted-foreground">No simulatable signals detected.</p>
              <p className="text-xs text-muted-foreground">Simulations activate when complication signals are present.</p>
            </div>
          )}

          <div className="flex gap-2">
            <button
              data-testid="button-back-signals"
              onClick={() => advance("signals")}
              className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg border border-border text-foreground hover:bg-muted transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
              Back
            </button>
            <button
              data-testid="button-to-export"
              onClick={() => { markComplete("simulate"); advance("export"); }}
              className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl px-4 py-2.5 text-sm font-medium transition-colors"
            >
              Export session report
              <FileDown className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* ── Step 5: Export ────────────────────────────────────────────────────── */}
      {currentStep === "export" && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border overflow-hidden">
            <div className="px-4 py-3 bg-gray-50 dark:bg-gray-900 border-b border-border">
              <p className="text-sm font-semibold text-foreground">Session summary</p>
            </div>
            <div className="divide-y divide-border text-sm">
              <div className="px-4 py-2.5 flex justify-between">
                <span className="text-muted-foreground">Patient ref</span>
                <span className="font-medium">{patientRef || "—"}</span>
              </div>
              <div className="px-4 py-2.5 flex justify-between">
                <span className="text-muted-foreground">Poses captured</span>
                <span className="font-medium">{Object.keys(capturedFiles).length}</span>
              </div>
              <div className="px-4 py-2.5 flex justify-between">
                <span className="text-muted-foreground">Protocols triggered</span>
                <span className={`font-medium ${triggeredProtocols.length ? "text-orange-600" : "text-green-600"}`}>
                  {triggeredProtocols.length}
                </span>
              </div>
              <div className="px-4 py-2.5 flex justify-between">
                <span className="text-muted-foreground">Simulations</span>
                <span className="font-medium">{simulations.length}</span>
              </div>
            </div>
          </div>

          <textarea
            value={clinicianNotes}
            onChange={e => setClinicianNotes(e.target.value)}
            placeholder="Clinician notes (optional — included in PDF report)"
            rows={3}
            data-testid="textarea-clinician-notes"
            className="w-full text-sm border border-border rounded-xl px-3 py-2.5 bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-blue-400 resize-none"
          />

          <div className="flex gap-2">
            <button
              data-testid="button-back-simulate"
              onClick={() => advance("simulate")}
              className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg border border-border text-foreground hover:bg-muted transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
              Back
            </button>
            <button
              data-testid="button-download-pdf"
              onClick={handleExport}
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700 text-white rounded-xl px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-50"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />}
              Download PDF report
            </button>
          </div>

          {completed.has("export") && elapsed !== null && (
            <div className="flex items-center justify-center gap-2 text-sm text-green-600 dark:text-green-400">
              <CheckCircle2 className="h-4 w-4" />
              Session complete in {elapsed} seconds
            </div>
          )}
        </div>
      )}
    </div>
  );
}
