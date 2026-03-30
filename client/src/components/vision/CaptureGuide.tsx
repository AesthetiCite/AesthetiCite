/**
 * CaptureGuide.tsx
 * -----------------
 * Improvement 1 — Image capture guidance + live quality validation.
 *
 * Usage: replace your current file-input with this component.
 *
 * <CaptureGuide
 *   onImageReady={(file, validation) => {
 *     setSelectedFile(file);
 *   }}
 * />
 */

import { useState, useRef, useCallback } from "react";
import {
  CheckCircle2, XCircle, AlertTriangle, Camera,
  Upload, RefreshCw, Sun, Focus, Maximize2, Aperture
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CaptureValidation {
  usable: boolean;
  quality_score: number;
  issues: string[];
  suggestions: string[];
  lighting: string;
  focus: string;
  angle: string;
  face_visible: boolean;
  treatment_area_visible: boolean;
}

interface CaptureGuideProps {
  onImageReady: (file: File, validation: CaptureValidation) => void;
  token?: string;
  skipValidation?: boolean;
}

// ─── Capture instructions ─────────────────────────────────────────────────────

const CHECKLIST = [
  { icon: <Sun className="h-4 w-4" />,       text: "Natural or overhead light — no flash, no harsh shadows" },
  { icon: <Focus className="h-4 w-4" />,      text: "Hold steady — image must be sharp, not blurred" },
  { icon: <Maximize2 className="h-4 w-4" />,  text: "30 cm distance — treatment area fills the frame" },
  { icon: <Aperture className="h-4 w-4" />,   text: "No filters, no beauty mode, no editing" },
  { icon: <Camera className="h-4 w-4" />,     text: "Frontal angle — patient looking straight ahead" },
];

// ─── Quality bar ─────────────────────────────────────────────────────────────

function QualityBar({ score }: { score: number }) {
  const color =
    score >= 80 ? "bg-green-500" :
    score >= 60 ? "bg-yellow-400" :
    "bg-red-500";

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>Image quality</span>
        <span className="font-semibold">{score}/100</span>
      </div>
      <div className="h-2 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );
}

// ─── Metadata pill ────────────────────────────────────────────────────────────

function MetaPill({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className={`flex items-center gap-1.5 text-xs rounded-full px-2.5 py-1 border
      ${ok
        ? "bg-green-50 border-green-200 text-green-700 dark:bg-green-900/20 dark:border-green-800 dark:text-green-400"
        : "bg-red-50 border-red-200 text-red-700 dark:bg-red-900/20 dark:border-red-800 dark:text-red-400"
      }`}>
      {ok
        ? <CheckCircle2 className="h-3 w-3 flex-shrink-0" />
        : <XCircle className="h-3 w-3 flex-shrink-0" />
      }
      <span>{label}: <span className="font-medium">{value}</span></span>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function CaptureGuide({ onImageReady, token, skipValidation = false }: CaptureGuideProps) {
  const [phase, setPhase] = useState<"guide" | "validating" | "result" | "ready">("guide");
  const [validation, setValidation] = useState<CaptureValidation | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    setSelectedFile(file);

    const url = URL.createObjectURL(file);
    setPreviewUrl(url);

    if (skipValidation) {
      const mockValidation: CaptureValidation = {
        usable: true, quality_score: 75, issues: [], suggestions: [],
        lighting: "adequate", focus: "sharp", angle: "frontal",
        face_visible: true, treatment_area_visible: true,
      };
      setValidation(mockValidation);
      setPhase("ready");
      onImageReady(file, mockValidation);
      return;
    }

    setPhase("validating");

    try {
      const fd = new FormData();
      fd.append("file", file);

      const res = await fetch("/api/visual/validate-capture", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });

      if (!res.ok) throw new Error("Validation request failed");
      const data: CaptureValidation = await res.json();
      setValidation(data);
      setPhase("result");

      if (data.usable) {
        setTimeout(() => {
          setPhase("ready");
          onImageReady(file, data);
        }, 1500);
      }
    } catch (e) {
      console.warn("Capture validation failed, proceeding anyway:", e);
      const fallback: CaptureValidation = {
        usable: true, quality_score: 50, issues: ["Quality check unavailable"],
        suggestions: [], lighting: "adequate", focus: "sharp", angle: "frontal",
        face_visible: true, treatment_area_visible: true,
      };
      setValidation(fallback);
      setPhase("ready");
      onImageReady(file, fallback);
    }
  }, [skipValidation, token, onImageReady]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const handleReset = () => {
    setPhase("guide");
    setValidation(null);
    setPreviewUrl(null);
    setSelectedFile(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  // ── Phase: guide ─────────────────────────────────────────────────────────
  if (phase === "guide") {
    return (
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50 p-5 space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Camera className="h-4 w-4 text-blue-500" />
            Before you upload
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Consistent photos make serial comparisons reliable.
          </p>
        </div>

        <ul className="space-y-2">
          {CHECKLIST.map((item, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span className="text-blue-500 mt-0.5 flex-shrink-0">{item.icon}</span>
              <span className="text-sm text-foreground">{item.text}</span>
            </li>
          ))}
        </ul>

        <div className="pt-1">
          <label className="cursor-pointer" data-testid="capture-guide-upload-label">
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleInputChange}
              data-testid="input-capture-file"
            />
            <div className="flex items-center justify-center gap-2 rounded-lg border-2 border-dashed border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/20 py-4 px-6 text-blue-600 dark:text-blue-400 hover:border-blue-400 transition-colors">
              <Upload className="h-5 w-5" />
              <span className="text-sm font-medium">Select image or drag here</span>
            </div>
          </label>
        </div>
      </div>
    );
  }

  // ── Phase: validating ─────────────────────────────────────────────────────
  if (phase === "validating") {
    return (
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50 p-5">
        <div className="flex flex-col items-center gap-3 py-4">
          <RefreshCw className="h-8 w-8 text-blue-500 animate-spin" />
          <div className="text-center">
            <p className="text-sm font-medium text-foreground">Checking image quality…</p>
            <p className="text-xs text-muted-foreground mt-0.5">This takes 2–3 seconds</p>
          </div>
          {previewUrl && (
            <img
              src={previewUrl}
              alt="Preview"
              className="h-32 w-32 object-cover rounded-lg border border-gray-200 dark:border-gray-700 opacity-60"
            />
          )}
        </div>
      </div>
    );
  }

  // ── Phase: result ─────────────────────────────────────────────────────────
  if (phase === "result" && validation) {
    const passed = validation.usable;

    return (
      <div className={`rounded-xl border p-5 space-y-4
        ${passed
          ? "border-green-300 dark:border-green-700 bg-green-50/50 dark:bg-green-900/20"
          : "border-red-300 dark:border-red-700 bg-red-50/50 dark:bg-red-900/20"
        }`}>

        <div className="flex items-start gap-3">
          {previewUrl && (
            <img
              src={previewUrl}
              alt="Preview"
              className="h-20 w-20 object-cover rounded-lg border border-gray-200 dark:border-gray-700 flex-shrink-0"
            />
          )}
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              {passed
                ? <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                : <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
              }
              <span className={`text-sm font-semibold
                ${passed ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}>
                {passed ? "Image quality: Acceptable" : "Image quality: Needs improvement"}
              </span>
            </div>
            <QualityBar score={validation.quality_score} />
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5">
          <MetaPill label="Lighting" value={validation.lighting} ok={validation.lighting === "adequate"} />
          <MetaPill label="Focus" value={validation.focus} ok={validation.focus === "sharp"} />
          <MetaPill label="Angle" value={validation.angle} ok={validation.angle === "frontal"} />
          <MetaPill label="Face" value={validation.face_visible ? "visible" : "not visible"} ok={validation.face_visible} />
          <MetaPill label="Area" value={validation.treatment_area_visible ? "visible" : "not visible"} ok={validation.treatment_area_visible} />
        </div>

        {validation.issues.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Issues</p>
            {validation.issues.map((issue, i) => (
              <div key={i} className="flex items-start gap-2 text-sm text-foreground">
                <AlertTriangle className="h-3.5 w-3.5 text-orange-500 flex-shrink-0 mt-0.5" />
                {issue}
              </div>
            ))}
          </div>
        )}

        {!passed && validation.suggestions.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">How to improve</p>
            {validation.suggestions.map((s, i) => (
              <div key={i} className="flex items-start gap-2 text-sm text-foreground">
                <span className="text-blue-500 flex-shrink-0">→</span>
                {s}
              </div>
            ))}
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <button
            data-testid="button-capture-retake"
            onClick={handleReset}
            className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-foreground hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retake
          </button>
          {!passed && (
            <button
              data-testid="button-capture-use-anyway"
              onClick={() => {
                if (selectedFile && validation) {
                  setPhase("ready");
                  onImageReady(selectedFile, validation);
                }
              }}
              className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg bg-gray-200 dark:bg-gray-700 text-foreground hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            >
              Use anyway
            </button>
          )}
          {passed && (
            <div className="flex items-center gap-1.5 text-sm text-green-600 dark:text-green-400">
              <CheckCircle2 className="h-4 w-4" />
              Proceeding to analysis…
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Phase: ready ──────────────────────────────────────────────────────────
  if (phase === "ready") {
    return (
      <div className="flex items-center justify-between rounded-lg border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 px-4 py-3">
        <div className="flex items-center gap-2">
          {previewUrl && (
            <img
              src={previewUrl}
              alt="Selected"
              className="h-10 w-10 object-cover rounded border border-green-200 dark:border-green-700"
            />
          )}
          <span className="text-sm text-green-700 dark:text-green-400 font-medium">
            {selectedFile?.name ?? "Image ready"}
          </span>
        </div>
        <button
          data-testid="button-capture-change"
          onClick={handleReset}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors underline"
        >
          Change
        </button>
      </div>
    );
  }

  return null;
}
