/**
 * VisualDifferential.tsx
 * ----------------------
 * Structured differential diagnosis output component for AesthetiCite Visual Counseling.
 *
 * Drop this into the /visual-counsel page below the existing photo upload / stream section.
 *
 * Usage:
 *   import { VisualDifferential } from "@/components/VisualDifferential";
 *
 *   <VisualDifferential
 *     visualId={visualId}
 *     token={token}
 *     clinicalContext={contextString}
 *     injectedRegion={region}
 *     productType={product}
 *     timeSinceInjection={minutes}
 *     additionalSymptoms={symptoms}
 *   />
 *
 * The component calls POST /api/visual/differential and renders the result.
 * If a protocol is triggered, it shows a full-width emergency/protocol card with
 * a redirect button to the relevant protocol page.
 */

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { AlertTriangle, CheckCircle, Clock, Info, ChevronRight, Loader2, FileText, Zap } from "lucide-react";

// ---------------------------------------------------------------------------
// Types — mirror the backend Pydantic models
// ---------------------------------------------------------------------------

interface DiagnosisItem {
  rank: number;
  diagnosis: string;
  tier: "most_likely" | "possible" | "rule_out";
  confidence: number;
  confidence_label: "High" | "Moderate" | "Low";
  key_visual_findings: string[];
  distinguishing_features: string;
  urgency: "immediate" | "urgent" | "same_day" | "routine";
  protocol_key: string | null;
}

interface ImmediateAction {
  action: string;
  priority: "primary" | "secondary";
  rationale: string;
}

interface EvidenceRef {
  source_id: string;
  title: string;
  note: string;
  source_type: string;
}

interface ProtocolTrigger {
  triggered: boolean;
  protocol_key: string | null;
  protocol_name: string | null;
  trigger_reason: string | null;
  urgency: string | null;
  redirect_url: string | null;
}

interface DifferentialResponse {
  request_id: string;
  visual_id: string;
  generated_at_utc: string;
  processing_ms: number;
  overall_urgency: string;
  urgency_rationale: string;
  visual_summary: string;
  differential: DiagnosisItem[];
  immediate_actions: ImmediateAction[];
  protocol_trigger: ProtocolTrigger;
  evidence: EvidenceRef[];
  disclaimer: string;
  limitations: string[];
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface Props {
  visualId: string;
  token: string;
  clinicalContext?: string;
  injectedRegion?: string;
  productType?: string;
  timeSinceInjection?: number;
  additionalSymptoms?: string[];
  onProtocolTrigger?: (trigger: ProtocolTrigger) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const URGENCY_CONFIG = {
  immediate: {
    label: "IMMEDIATE",
    bg: "bg-red-50 border-red-400",
    badge: "bg-red-100 text-red-800 border-red-300",
    icon: <AlertTriangle className="w-4 h-4" />,
    dot: "bg-red-500",
  },
  urgent: {
    label: "URGENT",
    bg: "bg-orange-50 border-orange-400",
    badge: "bg-orange-100 text-orange-800 border-orange-300",
    icon: <Clock className="w-4 h-4" />,
    dot: "bg-orange-500",
  },
  same_day: {
    label: "SAME DAY",
    bg: "bg-amber-50 border-amber-300",
    badge: "bg-amber-100 text-amber-800 border-amber-300",
    icon: <Clock className="w-4 h-4" />,
    dot: "bg-amber-400",
  },
  routine: {
    label: "ROUTINE",
    bg: "bg-green-50 border-green-300",
    badge: "bg-green-100 text-green-800 border-green-300",
    icon: <CheckCircle className="w-4 h-4" />,
    dot: "bg-green-500",
  },
  none: {
    label: "NO COMPLICATION",
    bg: "bg-gray-50 border-gray-200",
    badge: "bg-gray-100 text-gray-700 border-gray-200",
    icon: <CheckCircle className="w-4 h-4" />,
    dot: "bg-gray-400",
  },
};

const TIER_CONFIG = {
  most_likely: { label: "Most likely", color: "text-red-700 bg-red-50 border-red-200" },
  possible: { label: "Possible", color: "text-amber-700 bg-amber-50 border-amber-200" },
  rule_out: { label: "Rule out", color: "text-blue-700 bg-blue-50 border-blue-200" },
};

const CONFIDENCE_BAR = {
  High: { width: "w-4/5", color: "bg-red-500" },
  Moderate: { width: "w-1/2", color: "bg-amber-400" },
  Low: { width: "w-1/4", color: "bg-gray-400" },
};

function UrgencyBanner({ urgency, rationale }: { urgency: string; rationale: string }) {
  const cfg = URGENCY_CONFIG[urgency as keyof typeof URGENCY_CONFIG] || URGENCY_CONFIG.routine;
  return (
    <div className={`flex items-start gap-3 rounded-lg border-2 px-4 py-3 ${cfg.bg}`}>
      <span className={`mt-0.5 flex-shrink-0 ${cfg.badge} rounded p-1 border text-xs font-bold`}>
        {cfg.icon}
      </span>
      <div>
        <p className="text-sm font-semibold text-gray-900">
          {cfg.label}
        </p>
        <p className="text-xs text-gray-600 mt-0.5">{rationale}</p>
      </div>
    </div>
  );
}

function ProtocolTriggerCard({ trigger }: { trigger: ProtocolTrigger }) {
  if (!trigger.triggered) return null;
  const isEmergency = trigger.urgency === "immediate";
  return (
    <div className={`rounded-lg border-2 p-4 ${isEmergency ? "bg-red-50 border-red-500" : "bg-amber-50 border-amber-400"}`}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Zap className={`w-5 h-5 ${isEmergency ? "text-red-600" : "text-amber-600"}`} />
          <div>
            <p className={`text-sm font-bold ${isEmergency ? "text-red-800" : "text-amber-800"}`}>
              Protocol triggered: {trigger.protocol_name}
            </p>
            {trigger.trigger_reason && (
              <p className="text-xs text-gray-600 mt-0.5">{trigger.trigger_reason}</p>
            )}
          </div>
        </div>
        {trigger.redirect_url && (
          <a href={trigger.redirect_url}>
            <Button
              size="sm"
              className={`text-white text-xs gap-1.5 ${isEmergency ? "bg-red-600 hover:bg-red-700" : "bg-amber-600 hover:bg-amber-700"}`}
            >
              Open protocol
              <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </a>
        )}
      </div>
    </div>
  );
}

function DiagnosisCard({ item, index }: { item: DiagnosisItem; index: number }) {
  const [expanded, setExpanded] = useState(index === 0);
  const tierCfg = TIER_CONFIG[item.tier] || TIER_CONFIG.possible;
  const confBar = CONFIDENCE_BAR[item.confidence_label] || CONFIDENCE_BAR.Low;
  const urgencyCfg = URGENCY_CONFIG[item.urgency as keyof typeof URGENCY_CONFIG] || URGENCY_CONFIG.routine;

  return (
    <div
      className={`rounded-lg border bg-white transition-all ${
        item.tier === "most_likely" ? "border-red-200 shadow-sm" : "border-gray-200"
      }`}
    >
      {/* Header row */}
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        {/* Rank bubble */}
        <span
          className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
            item.tier === "most_likely"
              ? "bg-red-100 text-red-700"
              : item.tier === "possible"
              ? "bg-amber-100 text-amber-700"
              : "bg-blue-100 text-blue-700"
          }`}
        >
          {item.rank}
        </span>

        {/* Diagnosis name */}
        <span className="flex-1 text-sm font-semibold text-gray-900">{item.diagnosis}</span>

        {/* Tier badge */}
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${tierCfg.color}`}>
          {tierCfg.label}
        </span>

        {/* Confidence bar */}
        <div className="hidden sm:flex items-center gap-1.5 w-28">
          <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${confBar.color} ${confBar.width}`} />
          </div>
          <span className="text-xs text-gray-500 w-8 text-right">{item.confidence}%</span>
        </div>

        {/* Urgency dot */}
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${urgencyCfg.dot}`} title={urgencyCfg.label} />

        {/* Chevron */}
        <ChevronRight
          className={`w-4 h-4 text-gray-400 transition-transform flex-shrink-0 ${expanded ? "rotate-90" : ""}`}
        />
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-gray-100 px-4 py-3 space-y-3">
          {/* Key visual findings */}
          {item.key_visual_findings.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
                Key visual findings
              </p>
              <ul className="space-y-1">
                {item.key_visual_findings.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                    <span className="mt-1 w-1.5 h-1.5 rounded-full bg-gray-400 flex-shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Distinguishing features */}
          {item.distinguishing_features && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Why this diagnosis
              </p>
              <p className="text-sm text-gray-700">{item.distinguishing_features}</p>
            </div>
          )}

          {/* Footer row */}
          <div className="flex items-center justify-between pt-1 flex-wrap gap-2">
            <div className="flex items-center gap-1.5">
              <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${urgencyCfg.badge}`}>
                {urgencyCfg.label}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${tierCfg.color}`}>
                Confidence: {item.confidence_label} ({item.confidence}%)
              </span>
            </div>
            {item.protocol_key && (
              <a href={`/complications?protocol=${item.protocol_key}`}>
                <Button variant="ghost" size="sm" className="text-xs h-7 gap-1 text-blue-700">
                  View protocol
                  <ChevronRight className="w-3 h-3" />
                </Button>
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ImmediateActionsCard({ actions }: { actions: ImmediateAction[] }) {
  if (!actions.length) return null;
  return (
    <div className="rounded-lg border-2 border-red-300 bg-red-50 p-4">
      <p className="text-xs font-bold text-red-700 uppercase tracking-wide mb-3 flex items-center gap-1.5">
        <AlertTriangle className="w-3.5 h-3.5" />
        Immediate actions
      </p>
      <div className="space-y-2">
        {actions.map((a, i) => (
          <div
            key={i}
            className={`flex gap-3 rounded-md p-2.5 ${
              a.priority === "primary" ? "bg-red-100" : "bg-white border border-red-200"
            }`}
          >
            <span className="flex-shrink-0 w-5 h-5 rounded-full bg-red-600 text-white text-xs font-bold flex items-center justify-center mt-0.5">
              {i + 1}
            </span>
            <div>
              <p className="text-sm font-medium text-gray-900">{a.action}</p>
              <p className="text-xs text-gray-500 mt-0.5">{a.rationale}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EvidenceSection({ evidence }: { evidence: EvidenceRef[] }) {
  if (!evidence.length) return null;
  return (
    <div>
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Evidence</p>
      <div className="space-y-1.5">
        {evidence.map((e, i) => (
          <div key={i} className="flex gap-2 text-xs text-gray-600">
            <span className="font-mono text-gray-400 flex-shrink-0">[{e.source_id}]</span>
            <span>
              <span className="font-medium text-gray-700">{e.title}</span>
              {e.note && <span className="text-gray-500"> — {e.note}</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function VisualDifferential({
  visualId,
  token,
  clinicalContext,
  injectedRegion,
  productType,
  timeSinceInjection,
  additionalSymptoms,
  onProtocolTrigger,
}: Props) {
  const [result, setResult] = useState<DifferentialResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runDifferential = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/visual/differential", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          visual_id: visualId,
          clinical_context: clinicalContext || null,
          injected_region: injectedRegion || null,
          product_type: productType || null,
          time_since_injection_minutes: timeSinceInjection ?? null,
          additional_symptoms: additionalSymptoms || [],
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail || `Error ${res.status}`);
      }

      const data: DifferentialResponse = await res.json();
      setResult(data);
      if (data.protocol_trigger.triggered && onProtocolTrigger) {
        onProtocolTrigger(data.protocol_trigger);
      }
    } catch (e: any) {
      setError(e.message || "Analysis failed. Please retry.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Trigger button */}
      {!result && !loading && (
        <Button
          onClick={runDifferential}
          className="w-full bg-teal-700 hover:bg-teal-800 text-white gap-2"
          size="lg"
        >
          <FileText className="w-4 h-4" />
          Run differential diagnosis
        </Button>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center gap-3 py-10 text-sm text-gray-500">
          <Loader2 className="w-5 h-5 animate-spin text-teal-600" />
          Analysing image — this takes 5–10 seconds
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
          <Button variant="ghost" size="sm" className="ml-3 text-red-600" onClick={runDifferential}>
            Retry
          </Button>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="space-y-4">

          {/* Urgency banner */}
          <UrgencyBanner urgency={result.overall_urgency} rationale={result.urgency_rationale} />

          {/* Protocol trigger */}
          <ProtocolTriggerCard trigger={result.protocol_trigger} />

          {/* Immediate actions (only if urgent/immediate) */}
          {["immediate", "urgent"].includes(result.overall_urgency) && (
            <ImmediateActionsCard actions={result.immediate_actions} />
          )}

          {/* Visual summary */}
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1 flex items-center gap-1.5">
              <Info className="w-3.5 h-3.5" />
              Visual findings
            </p>
            <p className="text-sm text-gray-700 leading-relaxed">{result.visual_summary}</p>
          </div>

          {/* Differential */}
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Differential diagnosis — {result.differential.length} diagnoses ranked
            </p>
            <div className="space-y-2">
              {result.differential.map((d, i) => (
                <DiagnosisCard key={d.rank} item={d} index={i} />
              ))}
            </div>
          </div>

          {/* Evidence */}
          <EvidenceSection evidence={result.evidence} />

          {/* Limitations + disclaimer */}
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 space-y-2">
            {result.limitations.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Limitations</p>
                <ul className="space-y-0.5">
                  {result.limitations.map((l, i) => (
                    <li key={i} className="text-xs text-gray-500 flex gap-2">
                      <span className="flex-shrink-0">·</span>{l}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-xs text-gray-400 italic">{result.disclaimer}</p>
          </div>

          {/* Re-run */}
          <Button
            variant="outline"
            size="sm"
            onClick={runDifferential}
            className="w-full text-xs gap-1.5"
          >
            <Loader2 className="w-3 h-3" />
            Re-run analysis
          </Button>
        </div>
      )}
    </div>
  );
}
