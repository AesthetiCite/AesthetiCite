/**
 * VisionAnalysisResult.tsx
 * =========================
 * Renders the full structured output from the Vision Engine.
 *
 * Sections:
 *   1. Risk classification banner + score bar
 *   2. Red flags (if any)
 *   3. Primary clinical action
 *   4. Visual feature grid
 *   5. Suggested causes (expandable cards)
 *   6. Secondary actions
 *   7. Reassuring signs
 *   8. Imaging indicator
 *   9. Next review recommendation
 *  10. Evidence (collapsible)
 *  11. Disclaimer + limitations
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  AlertTriangle, CheckCircle, Clock, Activity,
  ChevronDown, ChevronUp, ChevronRight,
  Microscope, FileText, RefreshCw, Eye,
} from "lucide-react";
import { Link } from "wouter";

// ─────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────

export interface VisualFeature {
  feature: string;
  severity: "absent" | "mild" | "moderate" | "marked";
  severity_score: number;
  location: string;
  clinical_note: string;
  flag: boolean;
}

export interface RiskClassification {
  level: "low" | "moderate" | "high";
  score: number;
  label: string;
  rationale: string;
  colour: "green" | "amber" | "red";
}

export interface SuggestedCause {
  rank: number;
  cause: string;
  category: string;
  confidence: number;
  confidence_label: string;
  supporting_features: string[];
  timeline_fit: string;
  protocol_key: string | null;
  protocol_url: string | null;
}

export interface ClinicalAction {
  priority: string;
  action: string;
  rationale: string;
  timeframe: string;
  escalation_trigger: string | null;
}

export interface EvidenceItem {
  source_id: string;
  title: string;
  note: string;
  relevance: string;
  source_type: string;
}

export interface VisionAnalysisResponse {
  request_id: string;
  visual_id: string;
  generated_at_utc: string;
  processing_ms: number;
  image_quality: string;
  image_quality_note: string;
  visual_features: VisualFeature[];
  risk_classification: RiskClassification;
  suggested_causes: SuggestedCause[];
  primary_action: ClinicalAction;
  secondary_actions: ClinicalAction[];
  evidence: EvidenceItem[];
  red_flags_present: string[];
  reassuring_signs: string[];
  next_review_recommendation: string;
  imaging_indicated: boolean;
  imaging_rationale: string | null;
  disclaimer: string;
  limitations: string[];
}

// ─────────────────────────────────────────────────────────────────
// Style maps
// ─────────────────────────────────────────────────────────────────

const RISK_STYLE = {
  low:      { wrap: "bg-green-50 border-green-400",  text: "text-green-800",  bar: "bg-green-500",   icon: <CheckCircle className="w-5 h-5" /> },
  moderate: { wrap: "bg-amber-50 border-amber-400",  text: "text-amber-800",  bar: "bg-amber-400",   icon: <Clock className="w-5 h-5" /> },
  high:     { wrap: "bg-red-50 border-red-500",      text: "text-red-800",    bar: "bg-red-500",     icon: <AlertTriangle className="w-5 h-5" /> },
};

const ACTION_STYLE: Record<string, { wrap: string; text: string }> = {
  immediate: { wrap: "bg-red-50 border-red-500",     text: "text-red-800"    },
  urgent:    { wrap: "bg-orange-50 border-orange-400",text: "text-orange-800" },
  review:    { wrap: "bg-amber-50 border-amber-300", text: "text-amber-800"  },
  monitor:   { wrap: "bg-blue-50 border-blue-300",   text: "text-blue-800"   },
  reassure:  { wrap: "bg-green-50 border-green-300", text: "text-green-800"  },
};

const SEVERITY_BAR: Record<string, { w: string; bg: string }> = {
  absent:   { w: "w-0",    bg: "bg-gray-200"  },
  mild:     { w: "w-1/4",  bg: "bg-green-400" },
  moderate: { w: "w-1/2",  bg: "bg-amber-400" },
  marked:   { w: "w-full", bg: "bg-red-500"   },
};

const CAT_BADGE: Record<string, string> = {
  vascular:       "bg-red-100 text-red-700",
  infectious:     "bg-orange-100 text-orange-700",
  inflammatory:   "bg-amber-100 text-amber-700",
  mechanical:     "bg-blue-100 text-blue-700",
  normal_healing: "bg-green-100 text-green-700",
};

// ─────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────

function RiskBanner({ risk }: { risk: RiskClassification }) {
  const s = RISK_STYLE[risk.level] ?? RISK_STYLE.low;
  return (
    <div className={`rounded-xl border-2 px-4 py-4 ${s.wrap}`}>
      <div className="flex items-start gap-3">
        <span className={s.text}>{s.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-base font-bold ${s.text}`}>{risk.label}</span>
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${s.wrap.replace("border-2","border")} ${s.text}`}>
              {risk.score}/100
            </span>
          </div>
          <p className={`text-sm ${s.text} opacity-80 leading-relaxed`}>{risk.rationale}</p>
        </div>
      </div>
      <div className="mt-3 h-2 bg-white/60 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${s.bar}`} style={{ width: `${risk.score}%` }} />
      </div>
    </div>
  );
}

function FeatureGrid({ features }: { features: VisualFeature[] }) {
  const visible = features.filter(f => f.severity !== "absent");
  if (!visible.length) return null;
  return (
    <div>
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
        Visual features — {visible.length} detected
      </p>
      <div className="grid grid-cols-2 gap-2">
        {visible.map((f, i) => {
          const bar = SEVERITY_BAR[f.severity] ?? SEVERITY_BAR.absent;
          return (
            <div key={i} className={`rounded-lg border p-3 ${f.flag ? "border-red-300 bg-red-50" : "border-gray-200 bg-white"}`}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-semibold text-gray-800 capitalize">
                  {f.feature.replace(/_/g, " ")}
                </span>
                {f.flag && <AlertTriangle className="w-3 h-3 text-red-500 flex-shrink-0" />}
              </div>
              <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden mb-1.5">
                <div className={`h-full rounded-full ${bar.bg} ${bar.w}`} />
              </div>
              <p className="text-xs text-gray-500 capitalize">{f.severity} · {f.location}</p>
              <p className="text-xs text-gray-600 mt-1 leading-relaxed">{f.clinical_note}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CauseCard({ cause, index }: { cause: SuggestedCause; index: number }) {
  const [open, setOpen] = useState(index === 0);
  const catBadge = CAT_BADGE[cause.category] ?? "bg-gray-100 text-gray-700";
  const rankBg = index === 0 ? "bg-red-100 text-red-700" : index === 1 ? "bg-amber-100 text-amber-700" : "bg-gray-100 text-gray-600";

  return (
    <div className={`rounded-lg border bg-white overflow-hidden ${index === 0 ? "border-gray-300 shadow-sm" : "border-gray-200"}`}>
      <button className="w-full flex items-center gap-2.5 px-4 py-3 text-left" onClick={() => setOpen(o => !o)}>
        <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${rankBg}`}>
          {cause.rank}
        </span>
        <span className="flex-1 text-sm font-semibold text-gray-900 min-w-0">{cause.cause}</span>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full flex-shrink-0 ${catBadge}`}>
          {cause.category.replace(/_/g, " ")}
        </span>
        <div className="flex items-center gap-1.5 w-20 flex-shrink-0">
          <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${cause.confidence >= 70 ? "bg-red-500" : cause.confidence >= 40 ? "bg-amber-400" : "bg-gray-400"}`}
              style={{ width: `${cause.confidence}%` }}
            />
          </div>
          <span className="text-xs text-gray-500 tabular-nums w-6 text-right">{cause.confidence}%</span>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
      </button>
      {open && (
        <div className="border-t border-gray-100 px-4 py-3 space-y-2">
          {cause.supporting_features.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 mb-1">Supporting features</p>
              <div className="flex flex-wrap gap-1.5">
                {cause.supporting_features.map((f, i) => (
                  <span key={i} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{f}</span>
                ))}
              </div>
            </div>
          )}
          {cause.timeline_fit && (
            <p className="text-xs text-gray-600">
              <span className="font-medium">Timeline: </span>{cause.timeline_fit}
            </p>
          )}
          {cause.protocol_url && (
            <Link href={cause.protocol_url}>
              <Button variant="outline" size="sm" className="text-xs gap-1.5 mt-1 h-7">
                View protocol <ChevronRight className="w-3 h-3" />
              </Button>
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

function ActionCard({ action, isPrimary }: { action: ClinicalAction; isPrimary?: boolean }) {
  const s = ACTION_STYLE[action.priority] ?? ACTION_STYLE.monitor;
  return (
    <div className={`rounded-lg border-2 px-4 py-3 ${s.wrap}`}>
      <div className="flex items-start justify-between gap-2 mb-1 flex-wrap">
        <span className={`text-xs font-bold uppercase tracking-wide ${s.text}`}>
          {isPrimary ? "Primary action" : "Additional"} · {action.priority.toUpperCase()}
        </span>
        <span className={`text-xs ${s.text} opacity-70`}>{action.timeframe}</span>
      </div>
      <p className={`text-sm font-semibold ${s.text} mb-1`}>{action.action}</p>
      <p className={`text-xs ${s.text} opacity-80`}>{action.rationale}</p>
      {action.escalation_trigger && (
        <p className={`text-xs mt-2 font-medium ${s.text}`}>
          ⚠ Escalate if: {action.escalation_trigger}
        </p>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Main export
// ─────────────────────────────────────────────────────────────────

interface Props {
  result: VisionAnalysisResponse;
  onRerun?: () => void;
}

export function VisionAnalysisResult({ result, onRerun }: Props) {
  const [showEvidence, setShowEvidence] = useState(false);
  const [showLimitations, setShowLimitations] = useState(false);

  return (
    <div className="space-y-4">

      {/* Image quality warning */}
      {result.image_quality === "poor" && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 flex items-center gap-2">
          <Eye className="w-4 h-4 text-amber-600 flex-shrink-0" />
          <p className="text-xs text-amber-800">
            <span className="font-semibold">Image quality: poor</span> — {result.image_quality_note}
          </p>
        </div>
      )}

      {/* Risk banner */}
      <RiskBanner risk={result.risk_classification} />

      {/* Red flags */}
      {result.red_flags_present.length > 0 && (
        <div className="rounded-lg border-2 border-red-300 bg-red-50 px-4 py-3">
          <p className="text-xs font-bold text-red-700 uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> Red flags detected
          </p>
          <ul className="space-y-1">
            {result.red_flags_present.map((f, i) => (
              <li key={i} className="text-sm text-red-800 flex items-start gap-2">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Primary action */}
      <ActionCard action={result.primary_action} isPrimary />

      {/* Visual features */}
      <FeatureGrid features={result.visual_features} />

      {/* Suggested causes */}
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
          Suggested causes — {result.suggested_causes.length} assessed
        </p>
        <div className="space-y-2">
          {result.suggested_causes.map((c, i) => (
            <CauseCard key={c.rank} cause={c} index={i} />
          ))}
        </div>
      </div>

      {/* Secondary actions */}
      {result.secondary_actions.length > 0 && (
        <div className="space-y-2">
          {result.secondary_actions.map((a, i) => <ActionCard key={i} action={a} />)}
        </div>
      )}

      {/* Reassuring signs */}
      {result.reassuring_signs.length > 0 && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3">
          <p className="text-xs font-bold text-green-700 uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <CheckCircle className="w-3.5 h-3.5" /> Reassuring signs
          </p>
          <ul className="space-y-1">
            {result.reassuring_signs.map((s, i) => (
              <li key={i} className="text-sm text-green-800 flex items-start gap-2">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Imaging */}
      {result.imaging_indicated && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 flex items-start gap-2">
          <Microscope className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-blue-800">Imaging may be indicated</p>
            {result.imaging_rationale && (
              <p className="text-xs text-blue-700 mt-0.5">{result.imaging_rationale}</p>
            )}
          </div>
        </div>
      )}

      {/* Next review */}
      {result.next_review_recommendation && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Next review</p>
          <p className="text-sm text-gray-700">{result.next_review_recommendation}</p>
        </div>
      )}

      {/* Evidence */}
      {result.evidence.length > 0 && (
        <div>
          <button
            className="flex items-center gap-2 text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2"
            onClick={() => setShowEvidence(s => !s)}
          >
            <FileText className="w-3.5 h-3.5" />
            Evidence ({result.evidence.length})
            {showEvidence ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          {showEvidence && (
            <div className="space-y-1.5">
              {result.evidence.map((e, i) => (
                <div key={i} className="flex gap-2 text-xs text-gray-600">
                  <span className="font-mono text-gray-400 flex-shrink-0">[{e.source_id}]</span>
                  <span>
                    <span className="font-medium">{e.title}</span>
                    {e.note && <span className="text-gray-500"> — {e.note}</span>}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 space-y-2">
        <p className="text-xs text-gray-400 italic leading-relaxed">{result.disclaimer}</p>
        <button
          className="text-xs text-gray-400 underline"
          onClick={() => setShowLimitations(s => !s)}
        >
          {showLimitations ? "Hide" : "Show"} limitations
        </button>
        {showLimitations && (
          <ul className="space-y-0.5">
            {result.limitations.map((l, i) => (
              <li key={i} className="text-xs text-gray-400 flex gap-2">
                <span>·</span>{l}
              </li>
            ))}
          </ul>
        )}
        {result.processing_ms > 0 && (
          <p className="text-xs text-gray-300">Processed in {result.processing_ms}ms</p>
        )}
      </div>

      {/* Rerun */}
      {onRerun && (
        <Button variant="outline" size="sm" onClick={onRerun} className="w-full text-xs gap-1.5">
          <RefreshCw className="w-3.5 h-3.5" /> Re-analyse
        </Button>
      )}
    </div>
  );
}
