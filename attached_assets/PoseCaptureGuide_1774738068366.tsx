/**
 * PoseCaptureGuide.tsx
 * --------------------
 * DermEngine-style standardised pose capture system.
 * Guides the clinician through 3 standardised angles before analysis,
 * making serial comparison clinically valid.
 *
 * Usage: drop into VisualCounselingPage in place of the raw file input.
 *
 *   import { PoseCaptureGuide } from "@/components/vision/PoseCaptureGuide";
 *
 *   <PoseCaptureGuide
 *     onComplete={(files) => {
 *       // files: { front?: File; left?: File; right?: File }
 *       setSelectedFiles(files);
 *     }}
 *     token={token}
 *     mode="serial"    // "serial" = all 3 poses; "single" = front only
 *   />
 */

import { useState, useRef, useCallback } from "react";
import { Camera, CheckCircle2, ChevronRight, RefreshCw, Upload, User, AlertTriangle } from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

type PoseKey = "front" | "left" | "right";

interface PoseConfig {
  key: PoseKey;
  label: string;
  angle: string;
  instruction: string;
  overlayGuide: React.ReactNode;
}

interface CapturedFiles {
  front?: File;
  left?: File;
  right?: File;
}

interface PoseCaptureGuideProps {
  onComplete: (files: CapturedFiles) => void;
  token?: string;
  mode?: "single" | "serial";
  required?: PoseKey[];
}

// ─── Pose SVG overlays ────────────────────────────────────────────────────────
// Silhouette guides matching DermEngine's standardised pose system

function FrontOverlay() {
  return (
    <svg viewBox="0 0 200 260" className="absolute inset-0 w-full h-full opacity-40 pointer-events-none">
      {/* Head oval */}
      <ellipse cx="100" cy="75" rx="45" ry="55" fill="none" stroke="white" strokeWidth="1.5" strokeDasharray="4,3" />
      {/* Shoulder line */}
      <path d="M 35 165 Q 55 145 100 140 Q 145 145 165 165" fill="none" stroke="white" strokeWidth="1.5" strokeDasharray="4,3" />
      {/* Chin marker */}
      <line x1="100" y1="128" x2="100" y2="135" stroke="white" strokeWidth="1.5" />
      {/* Centre vertical */}
      <line x1="100" y1="20" x2="100" y2="50" stroke="rgba(255,255,255,0.3)" strokeWidth="1" />
      <line x1="100" y1="100" x2="100" y2="130" stroke="rgba(255,255,255,0.3)" strokeWidth="1" />
      {/* Eye level */}
      <line x1="55" y1="68" x2="75" y2="68" stroke="rgba(255,255,255,0.3)" strokeWidth="0.8" />
      <line x1="125" y1="68" x2="145" y2="68" stroke="rgba(255,255,255,0.3)" strokeWidth="0.8" />
      {/* Corner markers */}
      <path d="M 25 25 L 25 40 M 25 25 L 40 25" stroke="white" strokeWidth="1.5" />
      <path d="M 175 25 L 175 40 M 175 25 L 160 25" stroke="white" strokeWidth="1.5" />
      <path d="M 25 235 L 25 220 M 25 235 L 40 235" stroke="white" strokeWidth="1.5" />
      <path d="M 175 235 L 175 220 M 175 235 L 160 235" stroke="white" strokeWidth="1.5" />
      {/* Label */}
      <text x="100" y="248" textAnchor="middle" fill="white" fontSize="10" fontFamily="monospace">FRONT — 0°</text>
    </svg>
  );
}

function LeftOverlay() {
  return (
    <svg viewBox="0 0 200 260" className="absolute inset-0 w-full h-full opacity-40 pointer-events-none">
      {/* Profile head shape */}
      <path d="M 120 30 Q 150 30 155 75 Q 160 110 145 128 L 80 135 Q 70 110 75 75 Q 80 30 120 30 Z"
        fill="none" stroke="white" strokeWidth="1.5" strokeDasharray="4,3" />
      {/* Nose projection */}
      <path d="M 155 85 L 165 95 L 155 100" fill="none" stroke="white" strokeWidth="1.2" strokeDasharray="3,2" />
      {/* Neck */}
      <path d="M 100 135 L 95 165" stroke="white" strokeWidth="1.5" strokeDasharray="4,3" />
      {/* Frankfort horizontal (eye-ear line) */}
      <line x1="80" y1="70" x2="155" y2="70" stroke="rgba(255,255,255,0.25)" strokeWidth="0.8" strokeDasharray="6,3" />
      {/* Corner markers */}
      <path d="M 25 25 L 25 40 M 25 25 L 40 25" stroke="white" strokeWidth="1.5" />
      <path d="M 175 25 L 175 40 M 175 25 L 160 25" stroke="white" strokeWidth="1.5" />
      <path d="M 25 235 L 25 220 M 25 235 L 40 235" stroke="white" strokeWidth="1.5" />
      <path d="M 175 235 L 175 220 M 175 235 L 160 235" stroke="white" strokeWidth="1.5" />
      {/* Arrow showing direction */}
      <path d="M 45 130 L 60 130 M 55 125 L 60 130 L 55 135" stroke="rgba(255,255,255,0.5)" strokeWidth="1" />
      {/* Label */}
      <text x="100" y="248" textAnchor="middle" fill="white" fontSize="10" fontFamily="monospace">LEFT — 45°</text>
    </svg>
  );
}

function RightOverlay() {
  return (
    <svg viewBox="0 0 200 260" className="absolute inset-0 w-full h-full opacity-40 pointer-events-none">
      {/* Profile head shape (mirrored) */}
      <path d="M 80 30 Q 50 30 45 75 Q 40 110 55 128 L 120 135 Q 130 110 125 75 Q 120 30 80 30 Z"
        fill="none" stroke="white" strokeWidth="1.5" strokeDasharray="4,3" />
      {/* Nose projection */}
      <path d="M 45 85 L 35 95 L 45 100" fill="none" stroke="white" strokeWidth="1.2" strokeDasharray="3,2" />
      {/* Neck */}
      <path d="M 100 135 L 105 165" stroke="white" strokeWidth="1.5" strokeDasharray="4,3" />
      {/* Frankfort horizontal */}
      <line x1="45" y1="70" x2="120" y2="70" stroke="rgba(255,255,255,0.25)" strokeWidth="0.8" strokeDasharray="6,3" />
      {/* Corner markers */}
      <path d="M 25 25 L 25 40 M 25 25 L 40 25" stroke="white" strokeWidth="1.5" />
      <path d="M 175 25 L 175 40 M 175 25 L 160 25" stroke="white" strokeWidth="1.5" />
      <path d="M 25 235 L 25 220 M 25 235 L 40 235" stroke="white" strokeWidth="1.5" />
      <path d="M 175 235 L 175 220 M 175 235 L 160 235" stroke="white" strokeWidth="1.5" />
      {/* Arrow showing direction */}
      <path d="M 155 130 L 140 130 M 145 125 L 140 130 L 145 135" stroke="rgba(255,255,255,0.5)" strokeWidth="1" />
      {/* Label */}
      <text x="100" y="248" textAnchor="middle" fill="white" fontSize="10" fontFamily="monospace">RIGHT — 45°</text>
    </svg>
  );
}

// ─── Pose configurations ───────────────────────────────────────────────────

const POSES: PoseConfig[] = [
  {
    key: "front",
    label: "Front — 0°",
    angle: "Direct frontal",
    instruction: "Patient looks straight ahead. Camera at eye level, 30cm distance.",
    overlayGuide: <FrontOverlay />,
  },
  {
    key: "left",
    label: "Left — 45°",
    angle: "Left oblique",
    instruction: "Patient turns head 45° left. Keep eye level. Same 30cm distance.",
    overlayGuide: <LeftOverlay />,
  },
  {
    key: "right",
    label: "Right — 45°",
    angle: "Right oblique",
    instruction: "Patient turns head 45° right. Keep eye level. Same 30cm distance.",
    overlayGuide: <RightOverlay />,
  },
];

// ─── Single pose capture ──────────────────────────────────────────────────────

interface PoseCaptureProps {
  pose: PoseConfig;
  onCapture: (file: File) => void;
  captured?: File;
  isActive: boolean;
}

function PoseCapture({ pose, onCapture, captured, isActive }: PoseCaptureProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);

  const handleFile = (file: File) => {
    const url = URL.createObjectURL(file);
    setPreview(url);
    onCapture(file);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div className={`rounded-xl border-2 transition-all duration-200 overflow-hidden
      ${isActive
        ? "border-blue-400 dark:border-blue-500 shadow-lg shadow-blue-500/10"
        : captured
          ? "border-green-400 dark:border-green-600"
          : "border-gray-200 dark:border-gray-700 opacity-50"
      }`}>

      {/* Capture viewport */}
      <div
        className="relative bg-gray-900 cursor-pointer group"
        style={{ aspectRatio: "3/4" }}
        onClick={() => isActive && inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={handleChange}
        />

        {/* Preview or overlay */}
        {preview ? (
          <img src={preview} alt={pose.label} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gray-800">
            <User className="h-12 w-12 text-gray-600" />
          </div>
        )}

        {/* Pose overlay guide */}
        {pose.overlayGuide}

        {/* Upload hover overlay */}
        {isActive && !preview && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/40 group-hover:bg-black/50 transition-colors">
            <Camera className="h-8 w-8 text-white mb-2" />
            <span className="text-white text-xs font-medium">Tap to capture</span>
          </div>
        )}

        {/* Captured tick */}
        {captured && (
          <div className="absolute top-2 right-2 bg-green-500 rounded-full p-0.5">
            <CheckCircle2 className="h-4 w-4 text-white" />
          </div>
        )}

        {/* Retake button */}
        {captured && isActive && (
          <button
            onClick={(e) => { e.stopPropagation(); inputRef.current?.click(); }}
            className="absolute bottom-2 right-2 bg-black/60 hover:bg-black/80 text-white text-xs px-2 py-1 rounded-full flex items-center gap-1 transition-colors"
          >
            <RefreshCw className="h-3 w-3" />
            Retake
          </button>
        )}
      </div>

      {/* Pose label */}
      <div className={`px-3 py-2 transition-colors
        ${isActive ? "bg-blue-50 dark:bg-blue-950/30" : "bg-gray-50 dark:bg-gray-900"}`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-bold text-foreground tracking-wide">{pose.label}</p>
            <p className="text-xs text-muted-foreground">{pose.angle}</p>
          </div>
          {captured && <CheckCircle2 className="h-4 w-4 text-green-500" />}
        </div>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function PoseCaptureGuide({
  onComplete,
  mode = "serial",
  required = ["front"],
}: PoseCaptureGuideProps) {
  const [captured, setCaptured] = useState<CapturedFiles>({});
  const [activePose, setActivePose] = useState<PoseKey>("front");
  const [submitted, setSubmitted] = useState(false);

  const poses = mode === "single" ? POSES.slice(0, 1) : POSES;
  const activeConfig = POSES.find(p => p.key === activePose)!;

  const handleCapture = useCallback((key: PoseKey, file: File) => {
    setCaptured(prev => {
      const next = { ...prev, [key]: file };
      // Auto-advance to next pose
      const keys = poses.map(p => p.key);
      const idx = keys.indexOf(key);
      if (idx < keys.length - 1) {
        setActivePose(keys[idx + 1]);
      }
      return next;
    });
  }, [poses]);

  const canSubmit = required.every(k => !!captured[k]);

  const handleSubmit = () => {
    if (canSubmit) {
      setSubmitted(true);
      onComplete(captured);
    }
  };

  if (submitted) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 p-4">
        <CheckCircle2 className="h-6 w-6 text-green-500 flex-shrink-0" />
        <div>
          <p className="text-sm font-semibold text-green-700 dark:text-green-400">
            {Object.keys(captured).length} pose{Object.keys(captured).length > 1 ? "s" : ""} captured
          </p>
          <p className="text-xs text-muted-foreground">Standardised capture complete — serial comparison enabled</p>
        </div>
        <button
          onClick={() => { setSubmitted(false); setCaptured({}); setActivePose("front"); }}
          className="ml-auto text-xs text-muted-foreground hover:text-foreground underline"
        >
          Restart
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Camera className="h-4 w-4 text-blue-500" />
            Standardised capture
            {mode === "serial" && (
              <span className="text-xs font-normal text-muted-foreground ml-1">
                — 3-angle protocol
              </span>
            )}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Consistent angles ensure reliable serial comparisons
          </p>
        </div>
        <div className="flex gap-1">
          {poses.map(p => (
            <button
              key={p.key}
              onClick={() => setActivePose(p.key)}
              className={`w-2 h-2 rounded-full transition-colors ${
                activePose === p.key
                  ? "bg-blue-500"
                  : captured[p.key]
                    ? "bg-green-400"
                    : "bg-gray-300 dark:bg-gray-600"
              }`}
            />
          ))}
        </div>
      </div>

      {/* Active pose instruction */}
      <div className="rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 px-3 py-2">
        <p className="text-xs font-semibold text-blue-700 dark:text-blue-400 mb-0.5">
          Now: {activeConfig.label}
        </p>
        <p className="text-xs text-blue-600 dark:text-blue-300">{activeConfig.instruction}</p>
      </div>

      {/* Pose grid */}
      <div className={`grid gap-3 ${mode === "serial" ? "grid-cols-3" : "grid-cols-1 max-w-[200px]"}`}>
        {poses.map(pose => (
          <PoseCapture
            key={pose.key}
            pose={pose}
            onCapture={(file) => handleCapture(pose.key, file)}
            captured={captured[pose.key]}
            isActive={activePose === pose.key}
          />
        ))}
      </div>

      {/* Progress + submit */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {required.filter(k => !captured[k]).length > 0 ? (
            <>
              <AlertTriangle className="h-3.5 w-3.5 text-orange-400" />
              {required.filter(k => !captured[k]).length} required pose{required.filter(k => !captured[k]).length > 1 ? "s" : ""} remaining
            </>
          ) : (
            <>
              <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
              All required poses captured
            </>
          )}
        </div>

        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className={`flex items-center gap-1.5 text-sm px-4 py-1.5 rounded-lg font-medium transition-all
            ${canSubmit
              ? "bg-blue-600 hover:bg-blue-700 text-white shadow-sm"
              : "bg-gray-200 dark:bg-gray-700 text-gray-400 cursor-not-allowed"
            }`}
        >
          Analyse
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      {/* Mode toggle */}
      {mode === "serial" && (
        <p className="text-xs text-muted-foreground text-center">
          For quick analysis, front-only capture is sufficient. All 3 angles enable serial comparison.
        </p>
      )}
    </div>
  );
}
