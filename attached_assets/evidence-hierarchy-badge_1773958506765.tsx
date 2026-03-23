/**
 * AesthetiCite — Evidence Hierarchy Badge Component
 *
 * Renders the 4-tier badge system:
 *   🟢 Guideline-based
 *   🔵 Consensus / Meta-Analysis / Systematic Review
 *   🟡 RCT / Review
 *   ⚪ Limited / Case / Expert
 *
 * Usage:
 *   <EvidenceHierarchyBadge type="Guideline" />
 *   <EvidenceHierarchyBadge type="RCT" size="lg" showRank />
 *   <TopEvidenceBadge citations={citations} />
 *   <CitationCard citation={c} />
 */

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { BookOpen, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";

// ---------------------------------------------------------------------------
// Type system — mirrors app/engine/evidence_hierarchy.py
// ---------------------------------------------------------------------------

export type EvidenceTypeDisplay =
  | "Guideline"
  | "Consensus Statement"
  | "Meta-Analysis"
  | "Systematic Review"
  | "RCT"
  | "Review"
  | "Cohort Study"
  | "Case Series"
  | "Case Report"
  | "Expert Opinion"
  | "Other";

interface BadgeConfig {
  emoji: string;
  label: string;
  tailwind: string;       // for Badge variant styling
  description: string;    // shown in hover card
  rank: number;           // 1 = best
}

// Canonical badge config matching the Python BADGE_CONFIG
export const EVIDENCE_BADGE_CONFIG: Record<string, BadgeConfig> = {
  "Guideline": {
    emoji: "🟢",
    label: "Guideline-based",
    tailwind: "bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-900/30 dark:text-emerald-300 dark:border-emerald-700",
    description: "Clinical practice guideline or regulatory recommendation — highest evidence tier.",
    rank: 1,
  },
  "Consensus Statement": {
    emoji: "🔵",
    label: "Consensus",
    tailwind: "bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-700",
    description: "Expert consensus statement — based on structured multi-expert agreement.",
    rank: 2,
  },
  "Meta-Analysis": {
    emoji: "🔵",
    label: "Meta-Analysis",
    tailwind: "bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-700",
    description: "Quantitative synthesis of multiple studies — high statistical confidence.",
    rank: 3,
  },
  "Systematic Review": {
    emoji: "🔵",
    label: "Systematic Review",
    tailwind: "bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-700",
    description: "Comprehensive structured review of all available evidence.",
    rank: 3,
  },
  "RCT": {
    emoji: "🟡",
    label: "RCT",
    tailwind: "bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-700",
    description: "Randomised controlled trial — gold standard for intervention evidence.",
    rank: 4,
  },
  "Review": {
    emoji: "🟡",
    label: "Review",
    tailwind: "bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-700",
    description: "Narrative or scoping review — useful synthesis but lower than systematic review.",
    rank: 5,
  },
  "Cohort Study": {
    emoji: "⚪",
    label: "Observational",
    tailwind: "bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800/50 dark:text-slate-400 dark:border-slate-600",
    description: "Observational / cohort study — descriptive but no experimental control.",
    rank: 6,
  },
  "Case Series": {
    emoji: "⚪",
    label: "Case Series",
    tailwind: "bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800/50 dark:text-slate-400 dark:border-slate-600",
    description: "Series of similar clinical cases — limited generalisability.",
    rank: 7,
  },
  "Case Report": {
    emoji: "⚪",
    label: "Case Report",
    tailwind: "bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800/50 dark:text-slate-400 dark:border-slate-600",
    description: "Single case — lowest evidence tier. Useful for rare events.",
    rank: 8,
  },
  "Expert Opinion": {
    emoji: "⚪",
    label: "Expert Opinion",
    tailwind: "bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800/50 dark:text-slate-400 dark:border-slate-600",
    description: "Expert opinion or editorial — no primary data.",
    rank: 9,
  },
  "Other": {
    emoji: "⚪",
    label: "Limited",
    tailwind: "bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800/50 dark:text-slate-400 dark:border-slate-600",
    description: "Evidence type not classified or limited source quality.",
    rank: 10,
  },
};

function getBadgeConfig(evidenceType: string | undefined | null): BadgeConfig {
  if (!evidenceType) return EVIDENCE_BADGE_CONFIG["Other"];
  // Exact match first
  if (EVIDENCE_BADGE_CONFIG[evidenceType]) return EVIDENCE_BADGE_CONFIG[evidenceType];
  // Partial match
  const key = Object.keys(EVIDENCE_BADGE_CONFIG).find(
    (k) => k.toLowerCase() === evidenceType.toLowerCase()
  );
  return key ? EVIDENCE_BADGE_CONFIG[key] : EVIDENCE_BADGE_CONFIG["Other"];
}

// ---------------------------------------------------------------------------
// EvidenceHierarchyBadge — single citation badge
// ---------------------------------------------------------------------------

interface BadgeProps {
  type?: string;              // evidence_type from API (e.g. "Guideline", "RCT")
  size?: "sm" | "md" | "lg"; // visual size
  showRank?: boolean;         // show numeric rank (1–10)
  showDescription?: boolean;  // hover card with description
  className?: string;
}

export function EvidenceHierarchyBadge({
  type,
  size = "sm",
  showRank = false,
  showDescription = true,
  className = "",
}: BadgeProps) {
  const config = getBadgeConfig(type);

  const sizeClass =
    size === "lg" ? "text-xs px-2.5 py-1" :
    size === "md" ? "text-xs px-2 py-0.5" :
    "text-[11px] px-1.5 py-0";

  const badge = (
    <Badge
      variant="outline"
      className={`${config.tailwind} ${sizeClass} flex-shrink-0 font-medium ${className}`}
      data-evidence-type={type}
      data-evidence-rank={config.rank}
    >
      <span className="mr-1 text-[10px]">{config.emoji}</span>
      {config.label}
      {showRank && (
        <span className="ml-1 opacity-60 text-[10px]">({config.rank})</span>
      )}
    </Badge>
  );

  if (!showDescription) return badge;

  return (
    <HoverCard openDelay={300}>
      <HoverCardTrigger asChild>{badge}</HoverCardTrigger>
      <HoverCardContent side="top" className="w-64 p-3">
        <div className="flex items-start gap-2">
          <span className="text-lg">{config.emoji}</span>
          <div>
            <p className="text-xs font-semibold">{config.label}</p>
            <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
              {config.description}
            </p>
            <p className="text-[10px] text-muted-foreground/60 mt-1">
              Evidence tier {config.rank}/10 — {
                config.rank <= 2 ? "Authoritative" :
                config.rank <= 4 ? "High quality" :
                config.rank <= 6 ? "Moderate" : "Lower quality"
              }
            </p>
          </div>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}

// ---------------------------------------------------------------------------
// TopEvidenceBadge — best badge across a result set (session-level)
// ---------------------------------------------------------------------------

interface TopBadge {
  emoji?: string;
  label?: string;
  color?: string;
  level?: string;  // "High" | "Moderate" | "Low"
  best_type?: string;
}

interface TopEvidenceBadgeProps {
  badge?: TopBadge;
  citations?: Citation[];  // fallback if no badge prop
  size?: "sm" | "md";
  className?: string;
}

export function TopEvidenceBadge({ badge, citations, size = "sm", className = "" }: TopEvidenceBadgeProps) {
  // If no badge, derive from citations
  const derived = badge ?? deriveTopBadge(citations ?? []);
  const config = getBadgeConfig(derived.best_type ?? derived.label);

  const sizeClass = size === "md" ? "text-xs px-2.5 py-1" : "text-[11px] px-2 py-0.5";

  return (
    <HoverCard openDelay={300}>
      <HoverCardTrigger asChild>
        <Badge
          variant="outline"
          className={`${config.tailwind} ${sizeClass} font-medium cursor-default ${className}`}
        >
          <span className="mr-1">{config.emoji}</span>
          {config.label}
        </Badge>
      </HoverCardTrigger>
      <HoverCardContent side="top" className="w-72 p-3">
        <p className="text-xs font-semibold mb-1">Evidence Level: {derived.level ?? "—"}</p>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Best available source type: <strong>{derived.best_type ?? config.label}</strong>
        </p>
        <div className="mt-2 pt-2 border-t">
          <p className="text-[10px] text-muted-foreground">Evidence hierarchy (best to least):</p>
          <div className="flex flex-wrap gap-1 mt-1">
            {["🟢 Guideline", "🔵 Consensus", "🟡 Review", "⚪ Limited"].map((b) => (
              <span key={b} className="text-[10px] text-muted-foreground">{b}</span>
            ))}
          </div>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}

function deriveTopBadge(citations: Citation[]): TopBadge {
  if (!citations.length) return { emoji: "⚪", label: "Limited", level: "Low", best_type: "Other" };
  const best = citations.reduce((acc, c) => {
    const rank = getBadgeConfig(c.evidence_type).rank;
    const accRank = getBadgeConfig(acc.evidence_type).rank;
    return rank < accRank ? c : acc;
  }, citations[0]);
  const config = getBadgeConfig(best.evidence_type);
  const level = config.rank <= 2 ? "High" : config.rank <= 5 ? "Moderate" : "Low";
  return { emoji: config.emoji, label: config.label, level, best_type: best.evidence_type };
}

// ---------------------------------------------------------------------------
// Citation type (mirrors what the API sends)
// ---------------------------------------------------------------------------

export interface Citation {
  id: number;
  label?: string;
  title: string;
  source?: string;
  year?: number;
  url?: string;
  doi?: string;
  authors?: string;
  evidence_type?: string;       // display label, e.g. "Guideline"
  evidence_type_raw?: string;   // canonical, e.g. "guideline"
  evidence_rank?: number;
  evidence_tier?: string;
  evidence_badge?: { emoji: string; label: string; color: string };
}

// ---------------------------------------------------------------------------
// CitationCard — full citation with badge, used in answer view
// ---------------------------------------------------------------------------

interface CitationCardProps {
  citation: Citation;
  index?: number;
  defaultExpanded?: boolean;
}

export function CitationCard({ citation, index, defaultExpanded = false }: CitationCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const config = getBadgeConfig(citation.evidence_type);

  return (
    <div
      className={`rounded-lg border p-3 transition-colors text-sm ${
        config.rank <= 2
          ? "border-emerald-200 dark:border-emerald-900"
          : config.rank <= 4
          ? "border-blue-100 dark:border-blue-900"
          : "border-border"
      }`}
      data-citation-id={citation.id}
    >
      <div className="flex items-start gap-2">
        {/* Citation number */}
        <span className="flex-shrink-0 w-6 h-6 rounded-full bg-muted flex items-center justify-center text-[10px] font-bold text-muted-foreground mt-0.5">
          {index ?? citation.id}
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              {/* Title */}
              <p className="text-xs font-medium leading-snug line-clamp-2">
                {citation.url ? (
                  <a
                    href={citation.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {citation.title}
                    <ExternalLink className="inline h-3 w-3 ml-1 opacity-50" />
                  </a>
                ) : (
                  citation.title
                )}
              </p>
              {/* Source + year */}
              <p className="text-[11px] text-muted-foreground mt-0.5">
                {[citation.source, citation.year].filter(Boolean).join(" · ")}
                {citation.authors && <> · {citation.authors}</>}
              </p>
            </div>

            {/* Evidence badge */}
            <EvidenceHierarchyBadge type={citation.evidence_type} size="sm" />
          </div>

          {/* Expand button */}
          {(citation.doi || citation.evidence_tier) && (
            <button
              type="button"
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground mt-1.5 transition-colors"
            >
              {expanded ? (
                <><ChevronUp className="h-3 w-3" /> Less</>
              ) : (
                <><ChevronDown className="h-3 w-3" /> Details</>
              )}
            </button>
          )}

          {/* Expanded details */}
          {expanded && (
            <div className="mt-2 pt-2 border-t space-y-1">
              {citation.evidence_tier && (
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span className="font-medium">Tier:</span>
                  <span>{citation.evidence_tier.replace(/_/g, " ")}</span>
                </div>
              )}
              {citation.doi && (
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span className="font-medium">DOI:</span>
                  <a
                    href={`https://doi.org/${citation.doi}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:underline truncate"
                  >
                    {citation.doi}
                  </a>
                </div>
              )}
              {citation.evidence_rank && (
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span className="font-medium">Evidence rank:</span>
                  <span>{citation.evidence_rank}/10</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EvidencePanel — full ranked citation list for an answer
// ---------------------------------------------------------------------------

interface EvidencePanelProps {
  citations: Citation[];
  topBadge?: TopBadge;
  className?: string;
}

export function EvidencePanel({ citations, topBadge, className = "" }: EvidencePanelProps) {
  const [showAll, setShowAll] = useState(false);

  if (!citations.length) return null;

  // Sort by evidence_rank ascending (best first) — should already be sorted from API
  const sorted = [...citations].sort(
    (a, b) => (a.evidence_rank ?? 10) - (b.evidence_rank ?? 10)
  );
  const visible = showAll ? sorted : sorted.slice(0, 4);

  // Count by type for summary
  const typeCounts: Record<string, number> = {};
  for (const c of sorted) {
    const t = c.evidence_type ?? "Other";
    typeCounts[t] = (typeCounts[t] ?? 0) + 1;
  }

  return (
    <div className={`space-y-3 ${className}`}>
      {/* Summary row */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <BookOpen className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs text-muted-foreground font-medium">
            {sorted.length} source{sorted.length !== 1 ? "s" : ""}
          </span>
          {/* Type breakdown pills */}
          {Object.entries(typeCounts)
            .sort(([a], [b]) => (getBadgeConfig(a).rank - getBadgeConfig(b).rank))
            .slice(0, 3)
            .map(([type, count]) => (
              <div key={type} className="flex items-center gap-1">
                <EvidenceHierarchyBadge type={type} size="sm" showDescription={false} />
                <span className="text-[10px] text-muted-foreground">×{count}</span>
              </div>
            ))}
        </div>

        {topBadge && (
          <TopEvidenceBadge badge={topBadge} size="sm" />
        )}
      </div>

      {/* Citation cards */}
      <div className="space-y-2">
        {visible.map((c, i) => (
          <CitationCard key={c.id ?? i} citation={c} index={i + 1} />
        ))}
      </div>

      {/* Show more */}
      {sorted.length > 4 && (
        <button
          type="button"
          onClick={() => setShowAll(!showAll)}
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
        >
          {showAll ? (
            <><ChevronUp className="h-3 w-3" /> Show less</>
          ) : (
            <><ChevronDown className="h-3 w-3" /> Show all {sorted.length} sources</>
          )}
        </button>
      )}

      {/* Legend */}
      <div className="flex items-center gap-3 pt-1 border-t flex-wrap">
        <span className="text-[10px] text-muted-foreground">Evidence hierarchy:</span>
        {[
          { type: "Guideline", label: "Guideline" },
          { type: "Consensus Statement", label: "Consensus" },
          { type: "RCT", label: "RCT/Review" },
          { type: "Other", label: "Limited" },
        ].map(({ type, label }) => {
          const cfg = getBadgeConfig(type);
          return (
            <span key={type} className="text-[10px] text-muted-foreground flex items-center gap-0.5">
              {cfg.emoji} {label}
            </span>
          );
        })}
      </div>
    </div>
  );
}
