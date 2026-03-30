/**
 * VisionAdvancedUI.tsx
 * ─────────────────────
 * Frontend components for all new Vision improvements:
 *
 *  ImageAnnotator         — canvas drawing / markup layer (Improvement #4)
 *  MeasurementRuler       — click-to-measure distance overlay (Improvement #7)
 *  SerialDeltaDisplay     — quantified score diff between visits (Improvement #1)
 *  AnalysisConfidenceBadge— badge with tooltip (Improvement #3)
 *  ColourCalibrationGuide — pre-capture calibration instructions (Improvement #8)
 *  SharedReviewBanner     — expired/live shared review indicator (Improvement #6)
 *  PopulationBaseline     — expected appearance card (Improvement #9)
 *  AutoLogButton          — 1-click session logging (Improvement #2)
 *
 * Usage: import the components you need into ConsultationFlow.tsx or
 * VisualCounselingPage.
 */

import { useState, useRef, useEffect, useCallback } from "react";
import {
  Edit3, Ruler, TrendingUp, TrendingDown, Minus,
  CheckCircle2, AlertTriangle, Share2, Copy, Clock,
  Sun, Info, Loader2, Database, ChevronRight
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface VisualScores {
  skin_colour_change: number | null;
  swelling_severity:  number | null;
  asymmetry_flag:     boolean | null;
  infection_signal:   number | null;
  ptosis_flag:        boolean | null;
  tyndall_flag:       boolean | null;
  overall_concern_level: string;
}

interface ScoreDelta {
  field:      string;
  label:      string;
  before:     number | boolean | null;
  after:      number | boolean | null;
  change:     number | string;
  direction:  "improved" | "worsened" | "unchanged" | "resolved" | "appeared";
  pct_change: number | null;
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. Image Annotator — canvas drawing layer (Improvement #4)
// ═══════════════════════════════════════════════════════════════════════════

type DrawTool = "pen" | "arrow" | "circle" | "text" | "eraser";

interface Annotation {
  tool: DrawTool;
  points: Array<{ x: number; y: number }>;
  color: string;
  width: number;
  text?: string;
}

interface ImageAnnotatorProps {
  imageUrl: string;
  onAnnotationsChange?: (annotations: Annotation[]) => void;
  onExport?: (dataUrl: string) => void;
  height?: number;
}

const COLORS = ["#ef4444", "#f97316", "#22c55e", "#3b82f6", "#ffffff", "#000000"];
const TOOLS: Array<{ key: DrawTool; label: string }> = [
  { key: "pen",    label: "Draw" },
  { key: "arrow",  label: "Arrow" },
  { key: "circle", label: "Circle" },
  { key: "text",   label: "Label" },
  { key: "eraser", label: "Erase" },
];

export function ImageAnnotator({ imageUrl, onAnnotationsChange, onExport, height = 400 }: ImageAnnotatorProps) {
  const canvasRef    = useRef<HTMLCanvasElement>(null);
  const imgRef       = useRef<HTMLImageElement>(null);
  const [tool, setTool]         = useState<DrawTool>("pen");
  const [color, setColor]       = useState("#ef4444");
  const [width, setWidth]       = useState(3);
  const [drawing, setDrawing]   = useState(false);
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [current, setCurrent]   = useState<Annotation | null>(null);

  // Draw all annotations on canvas
  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !imgRef.current) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(imgRef.current, 0, 0, canvas.width, canvas.height);

    const all = current ? [...annotations, current] : annotations;
    all.forEach(ann => {
      if (ann.points.length < 2) return;
      ctx.strokeStyle = ann.color;
      ctx.lineWidth   = ann.width;
      ctx.lineCap     = "round";
      ctx.lineJoin    = "round";

      if (ann.tool === "pen") {
        ctx.beginPath();
        ctx.moveTo(ann.points[0].x, ann.points[0].y);
        ann.points.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
        ctx.stroke();
      } else if (ann.tool === "arrow") {
        const [start, end] = [ann.points[0], ann.points[ann.points.length - 1]];
        ctx.beginPath(); ctx.moveTo(start.x, start.y); ctx.lineTo(end.x, end.y); ctx.stroke();
        const angle = Math.atan2(end.y - start.y, end.x - start.x);
        const al = 15;
        ctx.beginPath();
        ctx.moveTo(end.x, end.y);
        ctx.lineTo(end.x - al * Math.cos(angle - 0.4), end.y - al * Math.sin(angle - 0.4));
        ctx.lineTo(end.x - al * Math.cos(angle + 0.4), end.y - al * Math.sin(angle + 0.4));
        ctx.closePath(); ctx.fillStyle = ann.color; ctx.fill();
      } else if (ann.tool === "circle") {
        const [c, e] = [ann.points[0], ann.points[ann.points.length - 1]];
        const r = Math.hypot(e.x - c.x, e.y - c.y);
        ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, Math.PI * 2); ctx.stroke();
      }

      if (ann.tool === "text" && ann.text) {
        ctx.font = `${ann.width * 5}px sans-serif`;
        ctx.fillStyle = ann.color;
        ctx.fillText(ann.text, ann.points[0].x, ann.points[0].y);
      }
    });
  }, [annotations, current]);

  useEffect(() => { redraw(); }, [redraw]);

  const getPos = (e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const scaleX = canvasRef.current!.width / rect.width;
    const scaleY = canvasRef.current!.height / rect.height;
    return { x: (e.clientX - rect.left) * scaleX, y: (e.clientY - rect.top) * scaleY };
  };

  const onMouseDown = (e: React.MouseEvent) => {
    if (tool === "text") {
      const label = prompt("Annotation label:");
      if (!label) return;
      const pos = getPos(e);
      const ann: Annotation = { tool, points: [pos], color, width, text: label };
      const next = [...annotations, ann];
      setAnnotations(next);
      onAnnotationsChange?.(next);
      return;
    }
    setDrawing(true);
    setCurrent({ tool, points: [getPos(e)], color, width });
  };

  const onMouseMove = (e: React.MouseEvent) => {
    if (!drawing || !current) return;
    setCurrent(prev => prev ? { ...prev, points: [...prev.points, getPos(e)] } : null);
  };

  const onMouseUp = () => {
    if (!drawing || !current) return;
    setDrawing(false);
    if (current.points.length > 1) {
      const next = tool === "eraser"
        ? annotations.slice(0, -1)   // simple: remove last annotation
        : [...annotations, current];
      setAnnotations(next);
      onAnnotationsChange?.(next);
    }
    setCurrent(null);
  };

  const handleExport = () => {
    const dataUrl = canvasRef.current?.toDataURL("image/jpeg", 0.92);
    if (dataUrl) onExport?.(dataUrl);
  };

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Tools */}
        <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
          {TOOLS.map(t => (
            <button
              key={t.key}
              onClick={() => setTool(t.key)}
              className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors
                ${tool === t.key
                  ? "bg-white dark:bg-gray-700 text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"}`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Colours */}
        <div className="flex items-center gap-1">
          {COLORS.map(c => (
            <button
              key={c}
              onClick={() => setColor(c)}
              className={`w-5 h-5 rounded-full border-2 transition-transform
                ${color === c ? "scale-125 border-blue-500" : "border-gray-300 dark:border-gray-600"}`}
              style={{ backgroundColor: c }}
            />
          ))}
        </div>

        {/* Stroke width */}
        <select
          value={width}
          onChange={e => setWidth(Number(e.target.value))}
          className="text-xs border border-border rounded px-1.5 py-1 bg-background text-foreground"
        >
          {[2, 3, 5, 8].map(w => <option key={w} value={w}>{w}px</option>)}
        </select>

        {/* Clear + Export */}
        <button
          onClick={() => { setAnnotations([]); onAnnotationsChange?.([]); }}
          className="text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded border border-border transition-colors"
        >
          Clear
        </button>
        {onExport && (
          <button
            onClick={handleExport}
            className="text-xs bg-blue-600 hover:bg-blue-700 text-white px-2.5 py-1 rounded transition-colors"
          >
            Save annotated
          </button>
        )}
      </div>

      {/* Canvas */}
      <div className="relative rounded-xl overflow-hidden border border-border">
        <img
          ref={imgRef}
          src={imageUrl}
          alt="Annotate"
          className="hidden"
          onLoad={redraw}
        />
        <canvas
          ref={canvasRef}
          width={800}
          height={height}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={onMouseUp}
          className="w-full cursor-crosshair"
          style={{ touchAction: "none" }}
        />
        <div className="absolute top-2 left-2 bg-black/60 text-white text-xs px-2 py-1 rounded">
          <Edit3 className="h-3 w-3 inline mr-1" />
          Annotate — click and drag
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// 2. Measurement Ruler (Improvement #7)
// ═══════════════════════════════════════════════════════════════════════════

interface MeasurementRulerProps {
  imageUrl: string;
  referenceDistanceMm?: number;   // known anatomical reference (e.g. 30mm pupil-pupil)
  onMeasurement?: (distanceMm: number) => void;
}

export function MeasurementRuler({ imageUrl, referenceDistanceMm = 30, onMeasurement }: MeasurementRulerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef    = useRef<HTMLImageElement>(null);
  const [points, setPoints]       = useState<Array<{x:number;y:number}>>([]);
  const [pixelDist, setPixelDist] = useState<number | null>(null);
  const [calibrated, setCalibrated] = useState(false);
  const [pxPerMm, setPxPerMm]     = useState<number | null>(null);
  const [mode, setMode]           = useState<"calibrate" | "measure">("measure");
  const [measurements, setMeasurements] = useState<Array<{label:string;mm:number}>>([]);

  const redraw = useCallback(() => {
    const c = canvasRef.current; const ctx = c?.getContext("2d");
    if (!c || !ctx || !imgRef.current) return;
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.drawImage(imgRef.current, 0, 0, c.width, c.height);

    if (points.length >= 2) {
      ctx.strokeStyle = mode === "calibrate" ? "#22c55e" : "#f97316";
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 3]);
      ctx.beginPath();
      ctx.moveTo(points[0].x, points[0].y);
      ctx.lineTo(points[1].x, points[1].y);
      ctx.stroke();
      ctx.setLineDash([]);

      // Endpoints
      [points[0], points[1]].forEach(p => {
        ctx.fillStyle = mode === "calibrate" ? "#22c55e" : "#f97316";
        ctx.beginPath(); ctx.arc(p.x, p.y, 5, 0, Math.PI * 2); ctx.fill();
      });

      // Distance label
      const dist = Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y);
      setPixelDist(dist);
      const mx = (points[0].x + points[1].x) / 2;
      const my = (points[0].y + points[1].y) / 2;
      const distLabel = pxPerMm ? `${(dist / pxPerMm).toFixed(1)}mm` : `${dist.toFixed(0)}px`;
      ctx.font = "bold 13px sans-serif";
      ctx.fillStyle = "#ffffff";
      ctx.strokeStyle = "#000000";
      ctx.lineWidth = 3;
      ctx.strokeText(distLabel, mx + 8, my - 8);
      ctx.fillText(distLabel, mx + 8, my - 8);
    }

    points.forEach(p => {
      ctx.fillStyle = "#3b82f6";
      ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI * 2); ctx.fill();
    });
  }, [points, pxPerMm, mode]);

  useEffect(() => { redraw(); }, [redraw]);

  const getPos = (e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) * (canvasRef.current!.width / rect.width),
      y: (e.clientY - rect.top)  * (canvasRef.current!.height / rect.height),
    };
  };

  const handleClick = (e: React.MouseEvent) => {
    const pos = getPos(e);
    if (points.length >= 2) {
      setPoints([pos]);
    } else {
      const next = [...points, pos];
      setPoints(next);
      if (next.length === 2 && mode === "calibrate") {
        const dist = Math.hypot(next[1].x - next[0].x, next[1].y - next[0].y);
        const px_per_mm = dist / referenceDistanceMm;
        setPxPerMm(px_per_mm);
        setCalibrated(true);
        setMode("measure");
      } else if (next.length === 2 && mode === "measure" && pxPerMm) {
        const dist = Math.hypot(next[1].x - next[0].x, next[1].y - next[0].y);
        const mm = dist / pxPerMm;
        const label = `${new Date().toLocaleTimeString()}: ${mm.toFixed(1)}mm`;
        setMeasurements(prev => [...prev, { label, mm }]);
        onMeasurement?.(mm);
      }
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
          <button
            onClick={() => { setMode("calibrate"); setPoints([]); }}
            className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors
              ${mode === "calibrate" ? "bg-white dark:bg-gray-700 text-foreground shadow-sm" : "text-muted-foreground"}`}
          >
            Calibrate ({referenceDistanceMm}mm ref)
          </button>
          <button
            onClick={() => { setMode("measure"); setPoints([]); }}
            disabled={!calibrated}
            className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors disabled:opacity-40
              ${mode === "measure" ? "bg-white dark:bg-gray-700 text-foreground shadow-sm" : "text-muted-foreground"}`}
          >
            Measure
          </button>
        </div>
        {calibrated && (
          <span className="text-xs text-green-600 dark:text-green-400 flex items-center gap-1">
            <CheckCircle2 className="h-3.5 w-3.5" /> Calibrated
          </span>
        )}
        {!calibrated && (
          <span className="text-xs text-muted-foreground">
            Click two points on a known {referenceDistanceMm}mm reference to calibrate
          </span>
        )}
      </div>

      <div className="rounded-xl overflow-hidden border border-border">
        <img ref={imgRef} src={imageUrl} alt="" className="hidden" onLoad={redraw} />
        <canvas
          ref={canvasRef}
          width={800} height={500}
          onClick={handleClick}
          className="w-full cursor-crosshair"
        />
      </div>

      {measurements.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Measurements</p>
          {measurements.map((m, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <Ruler className="h-3.5 w-3.5 text-orange-500" />
              <span className="font-medium">{m.mm.toFixed(1)} mm</span>
              <span className="text-muted-foreground text-xs">{m.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// 3. Serial Delta Display (Improvement #1)
// ═══════════════════════════════════════════════════════════════════════════

interface SerialDeltaDisplayProps {
  deltas:            ScoreDelta[];
  trajectory:        string;
  summary:           string;
  daysBetween?:      number;
}

const DIRECTION_ICONS: Record<string, React.ReactNode> = {
  improved:  <TrendingUp   className="h-4 w-4 text-green-500" />,
  resolved:  <CheckCircle2 className="h-4 w-4 text-green-500" />,
  worsened:  <TrendingDown className="h-4 w-4 text-red-500" />,
  appeared:  <AlertTriangle className="h-4 w-4 text-orange-400" />,
  unchanged: <Minus        className="h-4 w-4 text-muted-foreground" />,
};

const DIRECTION_COLORS: Record<string, string> = {
  improved:  "text-green-600 dark:text-green-400",
  resolved:  "text-green-600 dark:text-green-400",
  worsened:  "text-red-600 dark:text-red-400",
  appeared:  "text-orange-500 dark:text-orange-400",
  unchanged: "text-muted-foreground",
};

export function SerialDeltaDisplay({ deltas, trajectory, summary, daysBetween }: SerialDeltaDisplayProps) {
  const trajectoryColor = {
    improving: "bg-green-50 border-green-200 dark:bg-green-900/20 dark:border-green-800 text-green-700 dark:text-green-400",
    worsening: "bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-800 text-red-700 dark:text-red-400",
    stable:    "bg-gray-50 border-gray-200 dark:bg-gray-900 dark:border-gray-700 text-muted-foreground",
    resolved:  "bg-green-50 border-green-200 dark:bg-green-900/20 dark:border-green-800 text-green-700 dark:text-green-400",
    mixed:     "bg-yellow-50 border-yellow-200 dark:bg-yellow-900/20 dark:border-yellow-800 text-yellow-700 dark:text-yellow-400",
  }[trajectory] || "bg-gray-50 border-gray-200 text-foreground";

  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <div className={`px-4 py-3 border-b border-border/50 ${trajectoryColor}`}>
        <div className="flex items-center justify-between">
          <p className="text-sm font-bold capitalize">
            Trajectory: {trajectory}
            {daysBetween && <span className="font-normal text-xs ml-2">over {daysBetween} days</span>}
          </p>
        </div>
        <p className="text-xs mt-0.5">{summary}</p>
      </div>

      <div className="divide-y divide-border">
        {deltas.map(d => (
          <div key={d.field} className="flex items-center gap-3 px-4 py-2.5">
            <div className="flex-shrink-0">{DIRECTION_ICONS[d.direction]}</div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground">{d.label}</p>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>{String(d.before ?? "—")} → {String(d.after ?? "—")}</span>
                {d.pct_change !== null && d.pct_change !== undefined && (
                  <span className={DIRECTION_COLORS[d.direction]}>
                    {d.direction === "improved" ? "↓" : "↑"}{Math.abs(d.pct_change)}%
                  </span>
                )}
              </div>
            </div>
            <span className={`text-xs font-semibold capitalize ${DIRECTION_COLORS[d.direction]}`}>
              {d.direction}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// 4. Analysis Confidence Badge (Improvement #3)
// ═══════════════════════════════════════════════════════════════════════════

interface ConfidenceBadgeProps {
  score:          number;
  label:          "High" | "Moderate" | "Low" | "Insufficient";
  color:          "green" | "yellow" | "orange" | "red";
  limitingFactors:string[];
  tooltip:        string;
}

export function AnalysisConfidenceBadge({ score, label, color, limitingFactors, tooltip }: ConfidenceBadgeProps) {
  const [expanded, setExpanded] = useState(false);

  const colorMap = {
    green:  "bg-green-100 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-700",
    yellow: "bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-300 dark:border-yellow-700",
    orange: "bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-900/30 dark:text-orange-300 dark:border-orange-700",
    red:    "bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-700",
  };

  return (
    <div className="space-y-1">
      <button
        onClick={() => setExpanded(v => !v)}
        className={`inline-flex items-center gap-1.5 text-xs font-semibold rounded-full px-2.5 py-1 border
          cursor-pointer transition-opacity hover:opacity-80 ${colorMap[color]}`}
        title={tooltip}
      >
        <span>Analysis confidence: {label}</span>
        <span className="font-normal opacity-70">({score}/100)</span>
        <Info className="h-3 w-3" />
      </button>

      {expanded && limitingFactors.length > 0 && (
        <div className="rounded-lg bg-gray-50 dark:bg-gray-900 border border-border p-2.5 space-y-1">
          <p className="text-xs font-semibold text-muted-foreground">Limiting factors:</p>
          {limitingFactors.map((f, i) => (
            <p key={i} className="text-xs text-foreground flex items-start gap-1.5">
              <AlertTriangle className="h-3 w-3 text-orange-400 flex-shrink-0 mt-0.5" />
              {f}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// 5. Colour Calibration Guide (Improvement #8)
// ═══════════════════════════════════════════════════════════════════════════

export function ColourCalibrationGuide({ onDismiss }: { onDismiss?: () => void }) {
  return (
    <div className="rounded-xl border border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-900/20 p-4 space-y-3">
      <div className="flex items-start gap-3">
        <Sun className="h-5 w-5 text-yellow-600 dark:text-yellow-400 flex-shrink-0 mt-0.5" />
        <div>
          <h3 className="text-sm font-semibold text-yellow-800 dark:text-yellow-300">
            Colour calibration tip
          </h3>
          <p className="text-xs text-yellow-700 dark:text-yellow-400 mt-0.5 leading-relaxed">
            For the most accurate skin colour analysis, hold a <strong>white sheet of paper</strong> next
            to the treatment area when photographing. This helps AesthetiCite calibrate its
            colour interpretation for your lighting conditions.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex gap-2">
          {["Good", "Avoid", "Avoid"].map((label, i) => (
            <div key={i} className="text-center">
              <div className={`w-8 h-8 rounded-lg border-2 ${
                i === 0 ? "bg-white border-green-400" :
                i === 1 ? "bg-yellow-200 border-orange-300" :
                "bg-gray-700 border-red-300"
              }`} />
              <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
              <p className="text-xs text-muted-foreground">{
                i === 0 ? "Natural" : i === 1 ? "Warm light" : "Low light"
              }</p>
            </div>
          ))}
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="ml-auto text-xs text-muted-foreground hover:text-foreground underline"
          >
            Got it
          </button>
        )}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// 6. Shared Review Banner (Improvement #6)
// ═══════════════════════════════════════════════════════════════════════════

interface ShareBannerProps {
  token:       string;
  expiresAt:   string;
  shareUrl:    string;
  onCopy?:     () => void;
}

export function SharedReviewBanner({ token, expiresAt, shareUrl, onCopy }: ShareBannerProps) {
  const [copied, setCopied] = useState(false);
  const expires = new Date(expiresAt);
  const isExpired = expires < new Date();
  const hoursLeft = Math.max(0, Math.round((expires.getTime() - Date.now()) / 3600000));

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      onCopy?.();
    } catch {}
  };

  return (
    <div className={`rounded-xl border p-4 space-y-2
      ${isExpired
        ? "border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900"
        : "border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20"
      }`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Share2 className={`h-4 w-4 flex-shrink-0 ${isExpired ? "text-muted-foreground" : "text-blue-500"}`} />
          <p className={`text-sm font-semibold ${isExpired ? "text-muted-foreground" : "text-blue-700 dark:text-blue-400"}`}>
            {isExpired ? "Shared review — expired" : "Shared review link active"}
          </p>
        </div>
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3.5 w-3.5" />
          {isExpired ? "Expired" : `${hoursLeft}h remaining`}
        </div>
      </div>

      {!isExpired && (
        <div className="flex items-center gap-2">
          <code className="flex-1 text-xs bg-white/70 dark:bg-black/30 rounded px-2 py-1.5 border border-blue-200 dark:border-blue-800 truncate">
            {shareUrl}
          </code>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 text-xs bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg transition-colors"
          >
            {copied ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        {isExpired
          ? "This review link has expired. Create a new one to share again."
          : "Anyone with this link can view the analysis, scores, and protocols — no account required."
        }
      </p>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// 7. Population Baseline Card (Improvement #9)
// ═══════════════════════════════════════════════════════════════════════════

interface PopulationBaselineProps {
  procedure:          string;
  daysPost:           int;
  typicalAppearance:  string;
  expectedResolution: string;
  amberFlags:         string[];
  redFlags:           string[];
  evidenceBasis:      string;
}

type int = number;

export function PopulationBaseline({
  procedure, daysPost, typicalAppearance, expectedResolution,
  amberFlags, redFlags, evidenceBasis
}: PopulationBaselineProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 dark:bg-gray-900 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        onClick={() => setExpanded(v => !v)}
      >
        <div className="flex items-center gap-2 text-left">
          <Info className="h-4 w-4 text-blue-500 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-foreground">
              Typical appearance: {procedure}
            </p>
            <p className="text-xs text-muted-foreground">Day {daysPost} post-treatment</p>
          </div>
        </div>
        <ChevronRight className={`h-4 w-4 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`} />
      </button>

      {expanded && (
        <div className="p-4 space-y-4 border-t border-border">
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Expected at day {daysPost}</p>
            <p className="text-sm text-foreground">{typicalAppearance}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Resolution timeline</p>
            <p className="text-sm text-foreground">{expectedResolution}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-yellow-600 dark:text-yellow-400 uppercase tracking-wide mb-1">⚠ Amber — review if present</p>
            {amberFlags.slice(0, 3).map((f, i) => (
              <p key={i} className="text-xs text-foreground">• {f}</p>
            ))}
          </div>
          <div>
            <p className="text-xs font-semibold text-red-600 dark:text-red-400 uppercase tracking-wide mb-1">🔴 Red — act immediately</p>
            {redFlags.slice(0, 3).map((f, i) => (
              <p key={i} className="text-xs text-foreground">• {f}</p>
            ))}
          </div>
          <p className="text-xs text-muted-foreground italic">{evidenceBasis}</p>
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// 8. Auto-Log Button (Improvement #2)
// ═══════════════════════════════════════════════════════════════════════════

interface AutoLogButtonProps {
  sessionData:  Record<string, any>;
  token:        string;
  onLogged?:    (caseId: string) => void;
}

export function AutoLogButton({ sessionData, token, onLogged }: AutoLogButtonProps) {
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [caseId, setCaseId] = useState<string | null>(null);

  const handleLog = async () => {
    setState("loading");
    try {
      const res = await fetch("/api/visual/auto-log", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(sessionData),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setCaseId(data.case_id);
      setState("done");
      onLogged?.(data.case_id);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 3000);
    }
  };

  if (state === "done") {
    return (
      <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
        <CheckCircle2 className="h-4 w-4" />
        <span>Session logged</span>
        {caseId && <span className="text-xs text-muted-foreground font-mono">{caseId.slice(0, 8)}</span>}
      </div>
    );
  }

  return (
    <button
      onClick={handleLog}
      disabled={state === "loading"}
      className={`flex items-center gap-2 text-sm px-4 py-2 rounded-lg font-medium transition-all
        ${state === "error"
          ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300"
          : "bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-foreground"
        } disabled:opacity-50`}
    >
      {state === "loading"
        ? <Loader2 className="h-4 w-4 animate-spin" />
        : <Database className="h-4 w-4" />
      }
      {state === "loading" ? "Logging…" : state === "error" ? "Failed — retry" : "Log this session"}
    </button>
  );
}
