/**
 * AesthetiCite Vision
 * client/src/pages/vision-followup.tsx
 * Route: /vision-followup
 */

import { useState, useRef, useCallback } from "react";
import { useLocation } from "wouter";
import {
  ArrowLeft, Upload, Camera, Loader2, FileDown,
  AlertTriangle, CheckCircle2, XCircle, ChevronDown,
  ChevronUp, RotateCcw, Activity, Eye, Shield,
  Info, ImagePlus, Trash2, TriangleAlert, Clock
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { getToken } from "@/lib/auth";
import { VisionCompareResultPanel, type VisionCompareResult } from "@/components/vision-diagnosis-result";

// ─── Types ─────────────────────────────────────────────────────────────────

interface ImageMetrics {
  filename: string;
  time_hint_days: number;
  asymmetry_raw: number;
  redness_raw: number;
  brightness_raw: number;
  asymmetry_label: string;
  redness_label: string;
  asymmetry_class: string;
  redness_class: string;
}

interface VisionAssessment {
  urgency: string;
  urgency_class: string;
  healing_trend: string;
  trend_class: string;
  summary: string;
  findings: string[];
  concerns: string[];
  recommendations: string[];
  patient_message: string;
  positioning_note: string;
}

interface VisionResponse {
  request_id: string;
  engine_version: string;
  generated_at_utc: string;
  procedure: string;
  notes: string;
  image_count: number;
  timeline: string[];
  series_metrics: ImageMetrics[];
  assessment: VisionAssessment;
  baseline_preview: string;
  latest_preview: string;
  disclaimer: string;
}

interface ProcedureOption {
  value: string;
  label: string;
}

// ─── Constants ──────────────────────────────────────────────────────────────

const PROCEDURES: ProcedureOption[] = [
  { value: "injectables", label: "Injectables (Fillers / Toxin)" },
  { value: "breast_augmentation", label: "Breast Augmentation" },
  { value: "rhinoplasty", label: "Rhinoplasty / Nose" },
  { value: "blepharoplasty", label: "Blepharoplasty" },
  { value: "facelift", label: "Facelift / Rhytidectomy" },
  { value: "liposuction", label: "Liposuction / Body Contouring" },
  { value: "skin_resurfacing", label: "Skin Resurfacing / Laser" },
  { value: "other", label: "Other / General" },
];

// ─── Urgency helpers ─────────────────────────────────────────────────────────

function getUrgencyConfig(urgencyClass: string) {
  switch (urgencyClass) {
    case "danger":
      return {
        bg: "bg-red-500/10 border-red-500/40",
        text: "text-red-600 dark:text-red-400",
        icon: XCircle,
        dot: "#ef4444",
      };
    case "warn":
      return {
        bg: "bg-amber-500/10 border-amber-500/40",
        text: "text-amber-600 dark:text-amber-400",
        icon: AlertTriangle,
        dot: "#f59e0b",
      };
    default:
      return {
        bg: "bg-emerald-500/10 border-emerald-500/40",
        text: "text-emerald-600 dark:text-emerald-400",
        icon: CheckCircle2,
        dot: "#22c55e",
      };
  }
}

function getMetricClass(cls: string) {
  switch (cls) {
    case "danger": return "text-red-600 dark:text-red-400 bg-red-500/10 border-red-500/20";
    case "warn":   return "text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20";
    default:       return "text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20";
  }
}

// ─── Slider comparison ───────────────────────────────────────────────────────

function SliderComparison({ baseline, latest }: { baseline: string; latest: string }) {
  const [split, setSplit] = useState(50);

  return (
    <div className="space-y-2">
      <div className="relative rounded-xl overflow-hidden border border-border bg-black select-none"
        style={{ aspectRatio: "1 / 1" }}>
        <img src={latest} alt="Latest" className="absolute inset-0 w-full h-full object-contain" />
        <div className="absolute inset-0 overflow-hidden" style={{ width: `${split}%` }}>
          <img src={baseline} alt="Baseline"
            className="absolute inset-0 object-contain"
            style={{ width: `${10000 / split}%`, maxWidth: "none" }} />
        </div>
        <div className="absolute top-0 bottom-0 w-0.5 bg-white shadow-lg pointer-events-none"
          style={{ left: `${split}%` }}>
          <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-6 h-6 rounded-full bg-white shadow-lg flex items-center justify-center">
            <div className="w-2 h-2 rounded-full bg-slate-400" />
          </div>
        </div>
        <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-black/60 text-white text-xs font-medium">
          Baseline
        </div>
        <div className="absolute top-2 right-2 px-2 py-0.5 rounded bg-black/60 text-white text-xs font-medium">
          Latest
        </div>
      </div>
      <input
        type="range" min={0} max={100} value={split}
        onChange={(e) => setSplit(Number(e.target.value))}
        className="w-full accent-primary"
        aria-label="Slide to compare baseline and latest images"
        data-testid="slider-compare"
      />
      <p className="text-[10px] text-muted-foreground text-center">
        Drag to compare baseline (left) vs latest (right)
      </p>
    </div>
  );
}

// ─── Metric bar ──────────────────────────────────────────────────────────────

function MetricBar({ value, max = 0.15, color }: { value: number; max?: number; color: string }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="h-1.5 rounded-full bg-muted overflow-hidden">
      <div className="h-full rounded-full transition-all duration-700"
        style={{ width: `${pct}%`, backgroundColor: color }} />
    </div>
  );
}

// ─── Timeline strip ──────────────────────────────────────────────────────────

function TimelineStrip({ metrics }: { metrics: ImageMetrics[] }) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-1">
      {metrics.map((m, i) => (
        <div key={i}
          className="flex-shrink-0 rounded-lg border border-border bg-muted/30 p-2.5 min-w-[120px] space-y-2">
          <div className="text-[10px] font-medium text-muted-foreground truncate" title={m.filename}>
            {i === 0 ? "Baseline" : i === metrics.length - 1 ? "Latest" : `#${i + 1}`}
          </div>
          <div className="text-[10px] truncate text-foreground/70">{m.filename}</div>
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-1">
              <span className="text-[9px] text-muted-foreground">Asym</span>
              <span className={`text-[9px] font-semibold px-1.5 py-0 rounded-full border ${getMetricClass(m.asymmetry_class)}`}>
                {m.asymmetry_label}
              </span>
            </div>
            <MetricBar value={m.asymmetry_raw} max={0.12}
              color={m.asymmetry_class === "danger" ? "#ef4444" : m.asymmetry_class === "warn" ? "#f59e0b" : "#22c55e"} />
            <div className="flex items-center justify-between gap-1 mt-1">
              <span className="text-[9px] text-muted-foreground">Red</span>
              <span className={`text-[9px] font-semibold px-1.5 py-0 rounded-full border ${getMetricClass(m.redness_class)}`}>
                {m.redness_label}
              </span>
            </div>
            <MetricBar value={m.redness_raw} max={0.10}
              color={m.redness_class === "danger" ? "#ef4444" : m.redness_class === "warn" ? "#f59e0b" : "#22c55e"} />
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function VisionFollowupPage() {
  const [, setLocation] = useLocation();

  const [procedure, setProcedure] = useState("injectables");
  const [notes, setNotes] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);

  const [loading, setLoading] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VisionResponse | null>(null);
  const [visionCompareResult, setVisionCompareResult] = useState<VisionCompareResult | null>(null);

  const [findingsOpen, setFindingsOpen] = useState(true);
  const [metricsOpen, setMetricsOpen] = useState(false);
  const [patientMsgOpen, setPatientMsgOpen] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFilesSelected = useCallback((selected: FileList | null) => {
    if (!selected) return;
    const arr = Array.from(selected);
    setFiles(arr);
    setResult(null);
    setError(null);
    const readers = arr.map(
      (f) =>
        new Promise<string>((resolve) => {
          const reader = new FileReader();
          reader.onload = (e) => resolve(e.target?.result as string);
          reader.readAsDataURL(f);
        })
    );
    Promise.all(readers).then(setPreviews);
  }, []);

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setPreviews((prev) => prev.filter((_, i) => i !== index));
  };

  async function handleAnalyze() {
    if (files.length < 2) {
      setError("Upload at least 2 images to begin timeline analysis.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    setVisionCompareResult(null);

    try {
      const token = getToken();
      const fd = new FormData();
      fd.append("procedure", procedure);
      fd.append("notes", notes);
      files.forEach((f) => fd.append("files", f));

      const res = await fetch("/api/vision/analyze", {
        method: "POST",
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: fd,
      });

      const text = await res.text();
      let data: any;
      try { data = JSON.parse(text); } catch { throw new Error(text.slice(0, 200)); }
      if (!res.ok) throw new Error(data?.detail || "Analysis failed");
      setResult(data as VisionResponse);

      // Run structured complication differential on baseline vs follow-up
      if (files.length >= 2) {
        try {
          const cfd = new FormData();
          cfd.append("baseline", files[0]);
          cfd.append("followup", files[files.length - 1]);
          if (procedure) cfd.append("procedure", procedure);
          const cRes = await fetch("/api/vision/diagnose-compare", {
            method: "POST",
            headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
            body: cfd,
          });
          if (cRes.ok) {
            const cData = await cRes.json();
            setVisionCompareResult(cData as VisionCompareResult);
          }
        } catch {
          // compare diagnosis is non-blocking
        }
      }
    } catch (err: any) {
      setError(err.message || "Analysis failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleExportPDF() {
    if (files.length < 2) return;
    setPdfLoading(true);
    try {
      const token = getToken();
      const fd = new FormData();
      fd.append("procedure", procedure);
      fd.append("notes", notes);
      files.forEach((f) => fd.append("files", f));

      const res = await fetch("/api/vision/analyze/export", {
        method: "POST",
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "PDF export failed");
      if (data.filename) window.open(`/exports/${data.filename}`, "_blank");
    } catch (err: any) {
      setError(err.message || "PDF export failed.");
    } finally {
      setPdfLoading(false);
    }
  }

  function handleReset() {
    setFiles([]);
    setPreviews([]);
    setResult(null);
    setError(null);
    setNotes("");
  }

  const uc = result ? getUrgencyConfig(result.assessment.urgency_class) : null;
  const canAnalyze = files.length >= 2 && !loading;

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => setLocation("/")} className="gap-2 -ml-2">
              <ArrowLeft className="w-4 h-4" />
              <span className="hidden sm:inline">Back</span>
            </Button>
            <div className="w-px h-5 bg-border" />
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
                <Camera className="w-4 h-4 text-primary" />
              </div>
              <div>
                <span className="font-semibold text-sm">AesthetiCite Vision</span>
                <span className="hidden sm:inline text-xs text-muted-foreground ml-2">
                  Post-Procedure Follow-up Analysis
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {result && (
              <Button variant="outline" size="sm" onClick={handleReset} className="gap-1.5 text-xs" data-testid="button-new-analysis">
                <RotateCcw className="w-3.5 h-3.5" /> New Analysis
              </Button>
            )}
            <Button
              variant="outline" size="sm"
              onClick={handleExportPDF}
              disabled={pdfLoading || files.length < 2}
              className="gap-1.5"
              data-testid="button-export-pdf"
            >
              {pdfLoading
                ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                : <FileDown className="w-3.5 h-3.5" />}
              Export PDF
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6">

          {/* ── LEFT PANEL ── */}
          <div className="space-y-4">

            <Card>
              <CardContent className="p-4 space-y-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Procedure
                  </label>
                  <select
                    value={procedure}
                    onChange={(e) => setProcedure(e.target.value)}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                    data-testid="select-procedure"
                  >
                    {PROCEDURES.map((p) => (
                      <option key={p.value} value={p.value}>{p.label}</option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Symptoms / Clinical Notes
                  </label>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    rows={4}
                    placeholder="Optional: redness, pain, swelling, warmth, blanching, discharge, visual changes..."
                    className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/30"
                    data-testid="input-clinical-notes"
                  />
                  <p className="text-[10px] text-muted-foreground">
                    Symptom keywords (e.g. "blanching", "pain") directly affect urgency classification.
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Upload zone */}
            <Card
              className={`border-2 border-dashed transition-all cursor-pointer ${
                files.length > 0 ? "border-primary/30 bg-primary/5" : "border-border hover:border-primary/40 hover:bg-muted/30"
              }`}
              onClick={() => fileInputRef.current?.click()}
              data-testid="upload-zone"
            >
              <CardContent className="p-6 text-center space-y-2">
                <div className="w-10 h-10 mx-auto rounded-xl bg-primary/10 flex items-center justify-center">
                  <ImagePlus className="w-5 h-5 text-primary" />
                </div>
                <div className="text-sm font-medium">
                  {files.length > 0 ? `${files.length} image${files.length > 1 ? "s" : ""} selected` : "Upload serial photos"}
                </div>
                <div className="text-xs text-muted-foreground">
                  2–10 images · JPEG/PNG · max 20 MB each
                </div>
                <div className="text-[10px] text-muted-foreground/70">
                  Name files with time hints: day0, week1, month1, etc. for automatic sorting
                </div>
              </CardContent>
            </Card>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => handleFilesSelected(e.target.files)}
              data-testid="input-file-upload"
            />

            {/* File previews */}
            {previews.length > 0 && (
              <div className="grid grid-cols-3 gap-2">
                {previews.map((src, i) => (
                  <div key={i} className="relative group rounded-lg overflow-hidden border border-border bg-black aspect-square"
                    data-testid={`img-preview-${i}`}>
                    <img src={src} alt={files[i]?.name} className="w-full h-full object-contain" />
                    <div className="absolute inset-x-0 bottom-0 bg-black/60 p-1">
                      <p className="text-[9px] text-white truncate">{files[i]?.name}</p>
                    </div>
                    {i === 0 && (
                      <div className="absolute top-1 left-1 px-1.5 py-0.5 rounded bg-primary text-primary-foreground text-[9px] font-bold">
                        BASE
                      </div>
                    )}
                    {i === files.length - 1 && files.length > 1 && (
                      <div className="absolute top-1 left-1 px-1.5 py-0.5 rounded bg-emerald-600 text-white text-[9px] font-bold">
                        LATEST
                      </div>
                    )}
                    <button
                      onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                      className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/70 text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
                      data-testid={`button-remove-image-${i}`}
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <Button
              onClick={handleAnalyze}
              disabled={!canAnalyze}
              className="w-full gap-2 shadow-lg shadow-primary/20"
              data-testid="button-analyse"
            >
              {loading ? (
                <><Loader2 className="w-4 h-4 animate-spin" />Analysing…</>
              ) : (
                <><Activity className="w-4 h-4" />Analyse Timeline</>
              )}
            </Button>

            {error && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-sm text-destructive"
                data-testid="status-error">
                <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                {error}
              </div>
            )}

            <div className="flex items-start gap-2 p-3 rounded-lg bg-muted/40 border border-border/50">
              <Info className="w-3.5 h-3.5 text-muted-foreground mt-0.5 flex-shrink-0" />
              <p className="text-[10px] text-muted-foreground leading-relaxed">
                For reliable serial comparison: consistent patient positioning, similar lighting,
                same camera distance, and front-facing angle across all photos.
              </p>
            </div>
          </div>

          {/* ── RIGHT PANEL ── */}
          <div className="space-y-4">
            {!result && !loading && (
              <div className="h-full min-h-[400px] flex flex-col items-center justify-center text-center space-y-3 text-muted-foreground">
                <div className="w-16 h-16 rounded-2xl bg-muted/50 flex items-center justify-center">
                  <Eye className="w-8 h-8 text-muted-foreground/40" />
                </div>
                <div className="text-sm font-medium">Upload images and run analysis</div>
                <div className="text-xs max-w-xs">
                  AesthetiCite Vision analyses serial post-procedure photos for healing trends,
                  asymmetry patterns, and complication signals.
                </div>
              </div>
            )}

            {result && uc && (
              <>
                {/* Urgency banner */}
                <div className={`rounded-xl border-2 p-5 ${uc.bg}`} data-testid="status-urgency">
                  <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                    <div className="flex-1 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-bold ${
                          uc.text
                        } bg-background border ${uc.bg.split(" ")[1]}`}>
                          <uc.icon className="w-4 h-4" />
                          {result.assessment.urgency}
                        </span>
                        <span className={`text-xs font-medium ${uc.text}`}>
                          {result.assessment.healing_trend}
                        </span>
                        {result.assessment.urgency === "Emergency" && (
                          <span className="text-xs font-bold text-red-500 animate-pulse">
                            ACT NOW
                          </span>
                        )}
                      </div>
                      <p className={`text-sm leading-relaxed ${uc.text}`}>
                        {result.assessment.summary}
                      </p>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted-foreground">
                        <span>Engine v{result.engine_version}</span>
                        <span>·</span>
                        <span>{result.image_count} images · {result.timeline[0]} → {result.timeline[result.timeline.length - 1]}</span>
                        <span>·</span>
                        <span>{new Date(result.generated_at_utc).toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Concerns */}
                {result.assessment.concerns.length > 0 && (
                  <Card className={`border-2 ${
                    result.assessment.urgency_class === "danger"
                      ? "border-red-500/40 bg-red-500/5"
                      : "border-amber-500/30 bg-amber-500/5"
                  }`} data-testid="status-concerns">
                    <CardContent className="p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <TriangleAlert className={`w-4 h-4 ${
                          result.assessment.urgency_class === "danger" ? "text-red-500" : "text-amber-500"
                        }`} />
                        <span className={`text-sm font-bold ${
                          result.assessment.urgency_class === "danger"
                            ? "text-red-600 dark:text-red-400"
                            : "text-amber-600 dark:text-amber-400"
                        }`}>
                          Clinical Concerns
                        </span>
                      </div>
                      <ul className="space-y-2">
                        {result.assessment.concerns.map((c, i) => (
                          <li key={i} className="flex items-start gap-2 text-sm">
                            <span className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                              result.assessment.urgency_class === "danger" ? "bg-red-500" : "bg-amber-500"
                            }`} />
                            <span className={
                              result.assessment.urgency_class === "danger"
                                ? "text-red-800 dark:text-red-200"
                                : "text-amber-800 dark:text-amber-200"
                            }>{c}</span>
                          </li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                )}

                {/* Slider comparison */}
                <Card>
                  <CardContent className="p-4 space-y-3">
                    <div className="flex items-center gap-2">
                      <Eye className="w-4 h-4 text-primary" />
                      <span className="text-sm font-semibold">Baseline vs Latest</span>
                    </div>
                    <SliderComparison
                      baseline={result.baseline_preview}
                      latest={result.latest_preview}
                    />
                  </CardContent>
                </Card>

                {/* Timeline strip (3+ images) */}
                {result.series_metrics.length > 2 && (
                  <Card>
                    <CardContent className="p-4 space-y-3">
                      <div className="flex items-center gap-2">
                        <Clock className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm font-semibold">Timeline Metrics</span>
                      </div>
                      <TimelineStrip metrics={result.series_metrics} />
                    </CardContent>
                  </Card>
                )}

                {/* Findings + recommendations */}
                <Card>
                  <CardContent className="p-4">
                    <button
                      onClick={() => setFindingsOpen(!findingsOpen)}
                      className="w-full flex items-center justify-between gap-2"
                      data-testid="button-toggle-findings"
                    >
                      <div className="flex items-center gap-2">
                        <Activity className="w-4 h-4 text-primary" />
                        <span className="text-sm font-semibold">Findings & Recommendations</span>
                      </div>
                      {findingsOpen
                        ? <ChevronUp className="w-4 h-4 text-muted-foreground" />
                        : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                    </button>

                    {findingsOpen && (
                      <div className="mt-4 space-y-4">
                        <div>
                          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                            Findings
                          </p>
                          <ul className="space-y-2">
                            {result.assessment.findings.map((f, i) => (
                              <li key={i} className="flex items-start gap-2 text-sm">
                                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 mt-0.5 flex-shrink-0" />
                                <span className="text-foreground/80">{f}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                            Recommendations
                          </p>
                          <ol className="space-y-2">
                            {result.assessment.recommendations.map((r, i) => (
                              <li key={i} className="flex items-start gap-3 text-sm">
                                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">
                                  {i + 1}
                                </span>
                                <span className="text-foreground/85">{r}</span>
                              </li>
                            ))}
                          </ol>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Per-image metrics */}
                <Card>
                  <CardContent className="p-4">
                    <button
                      onClick={() => setMetricsOpen(!metricsOpen)}
                      className="w-full flex items-center justify-between gap-2"
                      data-testid="button-toggle-metrics"
                    >
                      <div className="flex items-center gap-2">
                        <Activity className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm font-semibold">Image Metrics ({result.series_metrics.length} images)</span>
                      </div>
                      {metricsOpen
                        ? <ChevronUp className="w-4 h-4 text-muted-foreground" />
                        : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                    </button>
                    {metricsOpen && (
                      <div className="mt-3 space-y-2">
                        {result.series_metrics.map((m, i) => (
                          <div key={i}
                            className="flex items-center gap-3 p-2.5 rounded-lg bg-muted/30 border border-border/50 text-xs"
                            data-testid={`row-metric-${i}`}>
                            <span className="font-medium w-5 text-center">{i + 1}</span>
                            <span className="flex-1 truncate text-muted-foreground">{m.filename}</span>
                            <span className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold ${getMetricClass(m.asymmetry_class)}`}>
                              Asym: {m.asymmetry_label}
                            </span>
                            <span className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold ${getMetricClass(m.redness_class)}`}>
                              Red: {m.redness_label}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Patient message */}
                <Card>
                  <CardContent className="p-4">
                    <button
                      onClick={() => setPatientMsgOpen(!patientMsgOpen)}
                      className="w-full flex items-center justify-between gap-2"
                      data-testid="button-toggle-patient-msg"
                    >
                      <div className="flex items-center gap-2">
                        <Shield className="w-4 h-4 text-blue-500" />
                        <span className="text-sm font-semibold">Patient Communication</span>
                      </div>
                      {patientMsgOpen
                        ? <ChevronUp className="w-4 h-4 text-muted-foreground" />
                        : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                    </button>
                    {patientMsgOpen && (
                      <div className="mt-3 p-3 rounded-lg bg-blue-500/5 border border-blue-500/20 text-sm text-foreground/80 leading-relaxed"
                        data-testid="text-patient-message">
                        {result.assessment.patient_message}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Positioning note */}
                <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-500/5 border border-amber-500/20">
                  <Info className="w-3.5 h-3.5 text-amber-500 mt-0.5 flex-shrink-0" />
                  <p className="text-[10px] text-amber-800 dark:text-amber-200 leading-relaxed">
                    <span className="font-semibold">Positioning note: </span>
                    {result.assessment.positioning_note}
                  </p>
                </div>

                {/* Disclaimer */}
                <p className="text-[10px] text-muted-foreground/60 text-center leading-relaxed pb-2">
                  <Shield className="w-3 h-3 inline mr-1" />
                  {result.disclaimer}
                </p>
              </>
            )}

            {visionCompareResult && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                  <Shield className="h-3.5 w-3.5 text-blue-500" />
                  Complication Differential
                </p>
                <VisionCompareResultPanel
                  result={visionCompareResult}
                  onReset={() => setVisionCompareResult(null)}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
