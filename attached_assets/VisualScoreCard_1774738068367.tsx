/**
 * VisualScoreCard.tsx
 * -------------------
 * VISIA-inspired clinical assessment scoring card.
 * Displays the 7 numeric signals from extract_visual_scores() as a structured
 * clinical assessment — not a paragraph of text.
 *
 * Usage:
 *   import { VisualScoreCard } from "@/components/vision/VisualScoreCard";
 *
 *   // scores comes from the vision API response: response.visual_scores
 *   <VisualScoreCard scores={visualScores} analysedAt="2026-03-28T10:00:00Z" />
 */

import { AlertTriangle, CheckCircle2, ShieldAlert, Eye, Thermometer, Layers, TrendingUp } from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface VisualScores {
  skin_colour_change: number | null;    // 0–3
  swelling_severity: number | null;     // 0–3
  asymmetry_flag: boolean | null;
  infection_signal: number | null;      // 0–3
  ptosis_flag: boolean | null;
  fitzpatrick_type: string | null;      // I–VI
  tyndall_flag: boolean | null;
  overall_concern_level: "none" | "low" | "moderate" | "high" | "critical";
  assessed_at_utc: string;
}

interface VisualScoreCardProps {
  scores: VisualScores;
  analysedAt?: string;
  compact?: boolean;
}

// ─── Concern level config ─────────────────────────────────────────────────────

const CONCERN_CONFIG = {
  none:     { label: "No concern",   color: "text-green-600 dark:text-green-400",  bg: "bg-green-50 dark:bg-green-900/20",  border: "border-green-200 dark:border-green-800",  dot: "bg-green-500" },
  low:      { label: "Low",          color: "text-blue-600 dark:text-blue-400",    bg: "bg-blue-50 dark:bg-blue-900/20",    border: "border-blue-200 dark:border-blue-800",    dot: "bg-blue-400" },
  moderate: { label: "Moderate",     color: "text-yellow-700 dark:text-yellow-400",bg: "bg-yellow-50 dark:bg-yellow-900/20",border: "border-yellow-200 dark:border-yellow-800",dot: "bg-yellow-400" },
  high:     { label: "High",         color: "text-orange-600 dark:text-orange-400",bg: "bg-orange-50 dark:bg-orange-900/20",border: "border-orange-200 dark:border-orange-800",dot: "bg-orange-500" },
  critical: { label: "Critical",     color: "text-red-600 dark:text-red-400",      bg: "bg-red-50 dark:bg-red-900/20",      border: "border-red-200 dark:border-red-800",      dot: "bg-red-500 animate-pulse" },
};

// ─── Score bar ────────────────────────────────────────────────────────────────

interface ScoreBarProps {
  value: number | null;
  max: number;
  labels: string[];
  urgent?: boolean;
}

function ScoreBar({ value, max, labels, urgent }: ScoreBarProps) {
  if (value === null) {
    return <div className="h-1.5 rounded-full bg-gray-200 dark:bg-gray-700 opacity-40" />;
  }
  const pct = Math.round((value / max) * 100);
  const color = urgent && value >= 2
    ? "bg-red-500"
    : value >= 2
      ? "bg-orange-400"
      : value === 1
        ? "bg-yellow-400"
        : "bg-green-400";
  const label = labels[value] ?? labels[labels.length - 1];

  return (
    <div className="space-y-0.5">
      <div className="h-1.5 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${Math.max(pct, value > 0 ? 8 : 0)}%` }}
        />
      </div>
      <p className={`text-xs ${value === 0 ? "text-muted-foreground" : value >= 2 ? "text-orange-600 dark:text-orange-400 font-medium" : "text-foreground"}`}>
        {label}
      </p>
    </div>
  );
}

// ─── Boolean flag display ─────────────────────────────────────────────────────

function FlagBadge({ value, trueLabel, falseLabel, urgent }: {
  value: boolean | null;
  trueLabel: string;
  falseLabel: string;
  urgent?: boolean;
}) {
  if (value === null) {
    return <span className="text-xs text-muted-foreground italic">Not assessed</span>;
  }
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium rounded-full px-2 py-0.5
      ${value
        ? urgent
          ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300"
          : "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300"
        : "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300"
      }`}>
      {value
        ? <AlertTriangle className="h-3 w-3 flex-shrink-0" />
        : <CheckCircle2 className="h-3 w-3 flex-shrink-0" />
      }
      {value ? trueLabel : falseLabel}
    </span>
  );
}

// ─── Fitzpatrick badge ────────────────────────────────────────────────────────

const FITZ_COLORS: Record<string, { bg: string; text: string; desc: string }> = {
  I:   { bg: "bg-amber-50",   text: "text-amber-900",   desc: "Very fair" },
  II:  { bg: "bg-amber-100",  text: "text-amber-900",   desc: "Fair" },
  III: { bg: "bg-amber-200",  text: "text-amber-900",   desc: "Medium" },
  IV:  { bg: "bg-amber-400",  text: "text-amber-950",   desc: "Olive / brown" },
  V:   { bg: "bg-amber-600",  text: "text-white",       desc: "Brown" },
  VI:  { bg: "bg-amber-900",  text: "text-white",       desc: "Dark brown" },
};

function FitzpatrickBadge({ type }: { type: string | null }) {
  if (!type) return <span className="text-xs text-muted-foreground italic">Not detected</span>;
  const config = FITZ_COLORS[type] ?? FITZ_COLORS.III;
  return (
    <div className="flex items-center gap-2">
      <div className={`w-5 h-5 rounded-full ${config.bg} border border-black/10 flex-shrink-0`} />
      <span className="text-xs font-semibold text-foreground">Type {type}</span>
      <span className="text-xs text-muted-foreground">— {config.desc}</span>
    </div>
  );
}

// ─── Score rows ───────────────────────────────────────────────────────────────

const SCORE_ROWS = [
  {
    key: "skin_colour_change" as keyof VisualScores,
    label: "Perfusion / colour",
    icon: <Layers className="h-4 w-4" />,
    type: "bar" as const,
    max: 3,
    urgent: true,
    labels: ["Normal", "Mild erythema", "Mottling / dusky", "Blanching / cyanosis"],
  },
  {
    key: "swelling_severity" as keyof VisualScores,
    label: "Swelling / oedema",
    icon: <Thermometer className="h-4 w-4" />,
    type: "bar" as const,
    max: 3,
    urgent: false,
    labels: ["None", "Mild", "Moderate", "Severe / angioedema"],
  },
  {
    key: "infection_signal" as keyof VisualScores,
    label: "Infection signal",
    icon: <ShieldAlert className="h-4 w-4" />,
    type: "bar" as const,
    max: 3,
    urgent: true,
    labels: ["None", "Erythema only", "Swelling + erythema", "Fluctuance / purulent"],
  },
  {
    key: "asymmetry_flag" as keyof VisualScores,
    label: "Asymmetry",
    icon: <TrendingUp className="h-4 w-4" />,
    type: "flag" as const,
    trueLabel: "Asymmetry noted",
    falseLabel: "Symmetrical",
    urgent: false,
  },
  {
    key: "ptosis_flag" as keyof VisualScores,
    label: "Eyelid / brow ptosis",
    icon: <Eye className="h-4 w-4" />,
    type: "flag" as const,
    trueLabel: "Ptosis pattern",
    falseLabel: "Normal position",
    urgent: true,
  },
  {
    key: "tyndall_flag" as keyof VisualScores,
    label: "Tyndall effect",
    icon: <Layers className="h-4 w-4" />,
    type: "flag" as const,
    trueLabel: "Blue-grey signal",
    falseLabel: "Not detected",
    urgent: false,
  },
];

// ─── Main component ───────────────────────────────────────────────────────────

export function VisualScoreCard({ scores, analysedAt, compact = false }: VisualScoreCardProps) {
  const concern = CONCERN_CONFIG[scores.overall_concern_level];

  return (
    <div className={`rounded-xl border ${concern.border} overflow-hidden`}>

      {/* Header — overall concern level */}
      <div className={`px-4 py-3 ${concern.bg} flex items-center justify-between`}>
        <div className="flex items-center gap-2.5">
          <div className={`w-2.5 h-2.5 rounded-full ${concern.dot} flex-shrink-0`} />
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Clinical Visual Assessment
            </p>
            <p className={`text-sm font-bold ${concern.color}`}>
              {concern.label} concern level
            </p>
          </div>
        </div>
        {analysedAt && (
          <p className="text-xs text-muted-foreground hidden sm:block">
            {new Date(analysedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </p>
        )}
      </div>

      {/* Score grid */}
      <div className="divide-y divide-border">
        {SCORE_ROWS.map((row) => {
          const value = scores[row.key];
          return (
            <div key={row.key} className="px-4 py-2.5 flex items-start gap-3">
              <div className="text-muted-foreground mt-0.5 flex-shrink-0">{row.icon}</div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-foreground mb-1">{row.label}</p>
                {row.type === "bar" ? (
                  <ScoreBar
                    value={value as number | null}
                    max={row.max}
                    labels={row.labels}
                    urgent={row.urgent}
                  />
                ) : (
                  <FlagBadge
                    value={value as boolean | null}
                    trueLabel={row.trueLabel}
                    falseLabel={row.falseLabel}
                    urgent={row.urgent}
                  />
                )}
              </div>
            </div>
          );
        })}

        {/* Fitzpatrick row */}
        <div className="px-4 py-2.5 flex items-start gap-3">
          <div className="text-muted-foreground mt-0.5 flex-shrink-0">
            <div className="w-4 h-4 rounded-full bg-gradient-to-br from-amber-200 to-amber-700 border border-black/10" />
          </div>
          <div className="flex-1">
            <p className="text-xs font-semibold text-foreground mb-1">Fitzpatrick type (estimated)</p>
            <FitzpatrickBadge type={scores.fitzpatrick_type} />
          </div>
        </div>
      </div>

      {/* Disclaimer */}
      {!compact && (
        <div className="px-4 py-2 bg-gray-50 dark:bg-gray-900/50 border-t border-border">
          <p className="text-xs text-muted-foreground italic">
            AI-assisted visual scoring. Not a substitute for clinical examination.
            Scores derived from GPT-4o image description — hardware multi-spectral imaging (VISIA) provides higher accuracy.
          </p>
        </div>
      )}
    </div>
  );
}
