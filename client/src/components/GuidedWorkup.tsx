/**
 * GuidedWorkup.tsx — Improvements 1 + 3
 *
 * 1. Guided follow-up questions after image analysis
 *    After showing initial differential, asks 2–4 rapid-tap clinical questions
 *    and calls onRefine() with the answers so the caller can re-run the
 *    differential with richer context.
 *
 * 3. Top-3 confidence summary card
 *    Shows the top 3 diagnoses as a prominent summary bar BEFORE the full
 *    ranked differential list. Reduces cognitive load for busy clinicians.
 *
 * Usage:
 *   import { Top3SummaryCard } from "@/components/GuidedWorkup";
 *   import { GuidedQuestions }  from "@/components/GuidedWorkup";
 *
 *   // Render Top3 above the DiagnosisCard list:
 *   <Top3SummaryCard differential={result.differential} />
 *
 *   // Render guided questions below the differential:
 *   <GuidedQuestions
 *     urgency={result.overall_urgency}
 *     topDiagnosis={result.differential[0]?.diagnosis}
 *     onRefine={(answers) => reRunWithContext(answers)}
 *   />
 */

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { CheckCircle, ChevronRight, RefreshCw } from "lucide-react";

// ─────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────

interface DiagnosisItem {
  rank: number;
  diagnosis: string;
  tier: "most_likely" | "possible" | "rule_out";
  confidence: number;
  confidence_label: "High" | "Moderate" | "Low";
  urgency: string;
  protocol_key: string | null;
}

interface RefinementAnswers {
  blanching_present:       boolean | null;
  visual_symptoms:         boolean | null;
  pain_level:              "severe" | "moderate" | "mild" | "none" | null;
  time_bucket:             "under_30min" | "30_to_120min" | "over_2hr" | "days_weeks" | null;
}

// ─────────────────────────────────────────────────────────────────
// Improvement 3 — Top-3 confidence summary card
// ─────────────────────────────────────────────────────────────────

const TIER_STYLES = {
  most_likely: { bg: "bg-red-50",    border: "border-red-200",    dot: "bg-red-500",    label: "Most likely" },
  possible:    { bg: "bg-amber-50",  border: "border-amber-200",  dot: "bg-amber-400",  label: "Possible"    },
  rule_out:    { bg: "bg-blue-50",   border: "border-blue-200",   dot: "bg-blue-400",   label: "Rule out"    },
};

const URGENCY_DOT: Record<string, string> = {
  immediate: "bg-red-600",
  urgent:    "bg-orange-500",
  same_day:  "bg-amber-400",
  routine:   "bg-green-500",
};

export function Top3SummaryCard({ differential }: { differential: DiagnosisItem[] }) {
  const top3 = differential.slice(0, 3);
  if (!top3.length) return null;

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
          Top findings
        </span>
        <span className="text-xs text-gray-400">{differential.length} diagnoses total</span>
      </div>

      {/* Top 3 rows */}
      <div className="divide-y divide-gray-100">
        {top3.map((d, i) => {
          const ts = TIER_STYLES[d.tier] || TIER_STYLES.possible;
          const urgDot = URGENCY_DOT[d.urgency] || "bg-gray-400";

          return (
            <div key={d.rank} className={`flex items-center gap-3 px-4 py-3 ${i === 0 ? ts.bg : ""}`}>
              {/* Rank */}
              <span className={`
                w-6 h-6 rounded-full flex items-center justify-center
                text-xs font-bold flex-shrink-0
                ${i === 0 ? "bg-red-100 text-red-700" : i === 1 ? "bg-amber-100 text-amber-700" : "bg-blue-100 text-blue-700"}
              `}>
                {d.rank}
              </span>

              {/* Diagnosis */}
              <span className="flex-1 text-sm font-medium text-gray-900 truncate">
                {d.diagnosis}
              </span>

              {/* Tier badge */}
              <span className={`
                text-xs font-medium px-2 py-0.5 rounded-full border
                ${ts.bg} ${ts.border}
                ${i === 0 ? "text-red-700" : i === 1 ? "text-amber-700" : "text-blue-700"}
              `}>
                {ts.label}
              </span>

              {/* Confidence bar */}
              <div className="flex items-center gap-1.5 w-24 flex-shrink-0">
                <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      d.confidence >= 70 ? "bg-red-500" :
                      d.confidence >= 40 ? "bg-amber-400" : "bg-gray-400"
                    }`}
                    style={{ width: `${d.confidence}%` }}
                  />
                </div>
                <span className="text-xs text-gray-500 w-8 text-right tabular-nums">
                  {d.confidence}%
                </span>
              </div>

              {/* Urgency dot */}
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${urgDot}`} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Improvement 1 — Guided follow-up questions
// ─────────────────────────────────────────────────────────────────

// Clinical questions — scoped to injectable complications
const QUESTIONS: {
  key: keyof RefinementAnswers;
  text: string;
  showIf?: (urgency: string, topDx: string) => boolean;
  options: { label: string; value: string; urgent?: boolean }[];
}[] = [
  {
    key: "blanching_present",
    text: "Is blanching or pallor visible at or near the injection site?",
    options: [
      { label: "Yes — blanching present",   value: "true",  urgent: true  },
      { label: "No — skin colour normal",   value: "false"                },
      { label: "Unsure / partially",        value: "false"                },
    ],
  },
  {
    key: "visual_symptoms",
    text: "Does the patient report any visual symptoms?",
    options: [
      { label: "Yes — blurred vision, diplopia, or loss", value: "true",  urgent: true },
      { label: "No visual symptoms",                       value: "false"              },
    ],
  },
  {
    key: "pain_level",
    text: "How is the patient describing pain at the site?",
    options: [
      { label: "Severe / escalating",  value: "severe",   urgent: true },
      { label: "Moderate",             value: "moderate"               },
      { label: "Mild / expected",      value: "mild"                   },
      { label: "No pain",              value: "none"                   },
    ],
  },
  {
    key: "time_bucket",
    text: "How long ago was the injection performed?",
    options: [
      { label: "Under 30 minutes",     value: "under_30min"   },
      { label: "30 min – 2 hours",     value: "30_to_120min"  },
      { label: "Over 2 hours",         value: "over_2hr"      },
      { label: "Days / weeks ago",     value: "days_weeks"    },
    ],
  },
];

interface GuidedQuestionsProps {
  urgency: string;
  topDiagnosis?: string;
  onRefine: (answers: Partial<RefinementAnswers>) => void;
  loading?: boolean;
}

export function GuidedQuestions({
  urgency,
  topDiagnosis = "",
  onRefine,
  loading = false,
}: GuidedQuestionsProps) {
  const [answers, setAnswers] = useState<Partial<RefinementAnswers>>({});
  const [step, setStep]       = useState(0);
  const [done, setDone]       = useState(false);
  const [urgentFlag, setUrgentFlag] = useState(false);

  const activeQuestions = QUESTIONS.filter(q =>
    !q.showIf || q.showIf(urgency, topDiagnosis)
  );

  const current = activeQuestions[step];
  const progress = Math.round(((step) / activeQuestions.length) * 100);

  const handleSelect = (key: keyof RefinementAnswers, rawValue: string, urgent?: boolean) => {
    const parsed: any =
      rawValue === "true"  ? true  :
      rawValue === "false" ? false :
      rawValue;

    const next = { ...answers, [key]: parsed };
    setAnswers(next);

    if (urgent) setUrgentFlag(true);

    if (step < activeQuestions.length - 1) {
      setStep(s => s + 1);
    } else {
      setDone(true);
      onRefine(next);
    }
  };

  if (done) {
    return (
      <div className={`rounded-lg border px-4 py-3 flex items-center justify-between gap-3 ${
        urgentFlag
          ? "bg-red-50 border-red-300"
          : "bg-teal-50 border-teal-200"
      }`}>
        <div className="flex items-center gap-2">
          <CheckCircle className={`w-4 h-4 ${urgentFlag ? "text-red-600" : "text-teal-600"}`} />
          <span className={`text-sm font-medium ${urgentFlag ? "text-red-800" : "text-teal-800"}`}>
            {urgentFlag
              ? "High-risk answers detected — differential updated"
              : "Workup complete — differential refined"}
          </span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="text-xs gap-1 text-gray-500"
          onClick={() => { setDone(false); setStep(0); setAnswers({}); setUrgentFlag(false); }}
        >
          <RefreshCw className="w-3 h-3" /> Redo
        </Button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-teal-200 bg-teal-50 overflow-hidden">
      {/* Progress bar */}
      <div className="h-1 bg-teal-100">
        <div
          className="h-full bg-teal-500 transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="px-4 py-4">
        {/* Step indicator */}
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs text-teal-600 font-medium">
            Question {step + 1} of {activeQuestions.length}
          </span>
          <span className="text-xs text-teal-500">
            Refining differential
          </span>
        </div>

        {/* Question */}
        <p className="text-sm font-semibold text-gray-900 mb-3">
          {current?.text}
        </p>

        {/* Options */}
        <div className="space-y-2">
          {current?.options.map((opt) => (
            <button
              key={opt.value}
              disabled={loading}
              onClick={() => handleSelect(current.key, opt.value, opt.urgent)}
              className={`
                w-full text-left text-sm px-3 py-2.5 rounded-lg border transition-all
                flex items-center justify-between gap-2
                ${opt.urgent
                  ? "border-red-200 bg-white hover:bg-red-50 hover:border-red-400 text-gray-800"
                  : "border-gray-200 bg-white hover:bg-teal-50 hover:border-teal-300 text-gray-800"
                }
              `}
            >
              <span>{opt.label}</span>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {opt.urgent && (
                  <span className="text-xs font-bold text-red-600 bg-red-100 px-1.5 py-0.5 rounded">
                    HIGH RISK
                  </span>
                )}
                <ChevronRight className="w-3.5 h-3.5 text-gray-400" />
              </div>
            </button>
          ))}
        </div>

        {/* Skip */}
        <button
          className="mt-3 text-xs text-gray-400 hover:text-gray-600 underline"
          onClick={() => {
            if (step < activeQuestions.length - 1) {
              setStep(s => s + 1);
            } else {
              setDone(true);
              onRefine(answers);
            }
          }}
        >
          Skip this question
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Helper: convert answers to context string for the API call
// ─────────────────────────────────────────────────────────────────

export function answersToContext(answers: Partial<RefinementAnswers>): string {
  const parts: string[] = [];
  if (answers.blanching_present === true)  parts.push("Blanching or pallor is present at the injection site.");
  if (answers.blanching_present === false) parts.push("No blanching present.");
  if (answers.visual_symptoms === true)    parts.push("Patient is reporting visual symptoms — URGENT.");
  if (answers.visual_symptoms === false)   parts.push("No visual symptoms reported.");
  if (answers.pain_level)                  parts.push(`Pain level: ${answers.pain_level}.`);
  if (answers.time_bucket === "under_30min")  parts.push("Injection was performed under 30 minutes ago.");
  if (answers.time_bucket === "30_to_120min") parts.push("Injection was 30 minutes to 2 hours ago.");
  if (answers.time_bucket === "over_2hr")     parts.push("Injection was over 2 hours ago.");
  if (answers.time_bucket === "days_weeks")   parts.push("Presentation is days or weeks post-injection.");
  return parts.join(" ");
}
