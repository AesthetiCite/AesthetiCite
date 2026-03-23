/**
 * AesthetiCite — Clinical Reasoning Section
 * Glass Health-inspired structured clinical reasoning UI.
 *
 * Architecture:
 *   - Fetches /api/reasoning/stream (SSE) in parallel with /api/decide
 *   - Shows a skeleton/typing indicator while LLM streams
 *   - Renders structured output: diagnosis → reasoning chain → differentials → red flags
 *   - Zero added latency to the main workflow (runs concurrently)
 */

import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Brain, ChevronRight, AlertTriangle, XCircle,
  CheckCircle2, Info, Minus,
} from "lucide-react";
import { getToken } from "@/lib/auth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ReasoningStep {
  step: number;
  label: string;
  content: string;
}

export interface Differential {
  diagnosis: string;
  exclude_reason: string;
  likelihood: "low" | "medium" | "high";
}

export interface ClinicalReasoningResult {
  diagnosis: string;
  confidence: "low" | "medium" | "high";
  confidence_why: string;
  reasoning: ReasoningStep[];
  key_signs: string[];
  against_signs: string[];
  differentials: Differential[];
  red_flags: string[];
  limitations: string;
  evidence_refs: string[];
  cache_hit?: boolean;
  latency_ms?: number;
}

// ---------------------------------------------------------------------------
// Confidence styling
// ---------------------------------------------------------------------------

const CONFIDENCE_CONFIG = {
  high: {
    label: "High Confidence",
    badge: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300 border-emerald-300",
    bar: "bg-emerald-500",
    barWidth: "w-full",
    icon: CheckCircle2,
  },
  medium: {
    label: "Medium Confidence",
    badge: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 border-amber-300",
    bar: "bg-amber-500",
    barWidth: "w-2/3",
    icon: Minus,
  },
  low: {
    label: "Low Confidence",
    badge: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border-slate-300",
    bar: "bg-slate-400",
    barWidth: "w-1/3",
    icon: Info,
  },
} as const;

const LIKELIHOOD_CONFIG = {
  high:   { label: "Likely",   cls: "bg-amber-100 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400" },
  medium: { label: "Possible", cls: "bg-blue-100 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400" },
  low:    { label: "Unlikely", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400" },
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TypingIndicator() {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <Brain className="h-4 w-4 animate-pulse text-blue-500" />
      <span>Analysing clinical presentation…</span>
      <span className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </span>
    </div>
  );
}

function SkeletonReasoning() {
  return (
    <div className="space-y-4 animate-pulse">
      <Skeleton className="h-6 w-3/4" />
      <Skeleton className="h-4 w-1/3" />
      <div className="space-y-3 mt-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="flex gap-3">
            <Skeleton className="h-7 w-7 rounded-full flex-shrink-0" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3.5 w-1/4" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-4/5" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReasoningStepCard({ step }: { step: ReasoningStep }) {
  return (
    <div className="flex gap-3">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 flex items-center justify-center text-[11px] font-bold text-blue-600 dark:text-blue-400 mt-0.5">
        {step.step}
      </div>
      <div className="flex-1 min-w-0 pb-3 border-b last:border-0 last:pb-0">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-0.5">
          {step.label}
        </p>
        <p className="text-sm leading-relaxed">{step.content}</p>
      </div>
    </div>
  );
}

function DifferentialRow({ diff }: { diff: Differential }) {
  const lk = LIKELIHOOD_CONFIG[diff.likelihood] ?? LIKELIHOOD_CONFIG.low;
  return (
    <div className="flex items-start gap-3 py-2 border-b last:border-0 last:pb-0">
      <XCircle className="h-4 w-4 text-muted-foreground/50 flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-0.5">
          <p className="text-xs font-medium">{diff.diagnosis}</p>
          <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${lk.cls}`}>
            {lk.label}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">{diff.exclude_reason}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SSE hook
// ---------------------------------------------------------------------------

type StreamState =
  | { status: "idle" }
  | { status: "loading"; tokensSoFar: number }
  | { status: "done"; data: ClinicalReasoningResult; cacheHit: boolean }
  | { status: "error"; message: string };

function useReasoningStream(params: {
  complication: string;
  symptoms: string[];
  region?: string;
  procedure?: string;
  product?: string;
  time_since_minutes?: number;
  enabled: boolean;
}) {
  const [state, setState] = useState<StreamState>({ status: "idle" });
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!params.enabled || !params.complication) return;

    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setState({ status: "loading", tokensSoFar: 0 });

    (async () => {
      const token = getToken();
      try {
        const res = await fetch("/api/reasoning/stream", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            complication_type: params.complication,
            symptoms: params.symptoms,
            region: params.region,
            procedure: params.procedure,
            product: params.product,
            time_since_minutes: params.time_since_minutes,
            include_evidence_context: true,
          }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          setState({ status: "error", message: "Reasoning unavailable" });
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let tokenCount = 0;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const evt = JSON.parse(line.slice(6));

              if (evt.type === "token") {
                tokenCount++;
                setState({ status: "loading", tokensSoFar: tokenCount });
              } else if (evt.type === "reasoning") {
                setState({
                  status: "done",
                  data: evt.data as ClinicalReasoningResult,
                  cacheHit: evt.cache_hit ?? false,
                });
              } else if (evt.type === "error") {
                setState({ status: "error", message: evt.message ?? "Reasoning failed" });
              }
            } catch {
              // malformed SSE line — ignore
            }
          }
        }
      } catch (err: any) {
        if (err?.name === "AbortError") return;
        setState({ status: "error", message: "Connection failed" });
      }
    })();

    return () => {
      controller.abort();
    };
  }, [
    params.complication,
    params.symptoms.join(","),
    params.region,
    params.enabled,
  ]);

  return state;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface ClinicalReasoningSectionProps {
  complication: string;
  symptoms?: string[];
  region?: string;
  procedure?: string;
  product?: string;
  time_since_minutes?: number;
  autoFetch?: boolean;
  className?: string;
  prefetchedResult?: ClinicalReasoningResult | null;
}

export function ClinicalReasoningSection({
  complication,
  symptoms = [],
  region,
  procedure,
  product,
  time_since_minutes,
  autoFetch = true,
  className = "",
  prefetchedResult = null,
}: ClinicalReasoningSectionProps) {
  const [triggered, setTriggered] = useState(autoFetch);
  const [expanded, setExpanded] = useState(true);

  const state = useReasoningStream({
    complication,
    symptoms,
    region,
    procedure,
    product,
    time_since_minutes,
    enabled: triggered && !prefetchedResult,
  });

  const result: ClinicalReasoningResult | null =
    prefetchedResult ?? (state.status === "done" ? state.data : null);

  const isLoading = !prefetchedResult && state.status === "loading";
  const isError   = !prefetchedResult && state.status === "error";
  const tokensSoFar = state.status === "loading" ? state.tokensSoFar : 0;

  const confidence = result?.confidence ?? "low";
  const confConfig = CONFIDENCE_CONFIG[confidence];
  const ConfIcon   = confConfig.icon;

  return (
    <Card className={`${className}`}>
      <CardHeader className="pb-2 pt-3 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <Brain className="h-4 w-4 text-blue-500" />
            Clinical Reasoning
            {state.status === "done" && state.cacheHit && (
              <span className="text-[10px] text-emerald-500 font-normal">⚡ cached</span>
            )}
          </CardTitle>
          <div className="flex items-center gap-2">
            {!triggered && (
              <button
                type="button"
                onClick={() => setTriggered(true)}
                className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                data-testid="button-analyse-reasoning"
              >
                Analyse
              </button>
            )}
            {result && (
              <button
                type="button"
                onClick={() => setExpanded(!expanded)}
                className="text-xs text-muted-foreground hover:text-foreground"
                data-testid="button-toggle-reasoning"
              >
                {expanded ? "Collapse" : "Expand"}
              </button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="px-4 pb-4">

        {!triggered && (
          <button
            type="button"
            onClick={() => setTriggered(true)}
            className="w-full py-3 border-2 border-dashed rounded-lg text-sm text-muted-foreground hover:border-blue-400 hover:text-blue-600 transition-colors"
            data-testid="button-trigger-reasoning"
          >
            <Brain className="h-5 w-5 mx-auto mb-1 opacity-40" />
            Click to analyse clinical presentation
          </button>
        )}

        {triggered && isLoading && !prefetchedResult && (
          <div className="space-y-4">
            <TypingIndicator />
            {tokensSoFar > 20 && <SkeletonReasoning />}
          </div>
        )}

        {isError && state.status === "error" && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground p-3 bg-muted/50 rounded-lg">
            <Info className="h-4 w-4 flex-shrink-0" />
            {(state as any).message ?? "Reasoning temporarily unavailable."}
          </div>
        )}

        {result && expanded && (
          <div className="space-y-5">

            {/* DIAGNOSIS + CONFIDENCE */}
            <div className="space-y-2">
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                  Most Likely Diagnosis
                </p>
                <p className="font-semibold text-base leading-snug" data-testid="text-reasoning-diagnosis">{result.diagnosis}</p>
              </div>

              <div>
                <div className="flex items-center gap-2 mb-1">
                  <ConfIcon className={`h-3.5 w-3.5 flex-shrink-0 ${
                    confidence === "high" ? "text-emerald-500" :
                    confidence === "medium" ? "text-amber-500" : "text-slate-400"
                  }`} />
                  <Badge variant="outline" className={`text-[11px] px-2 py-0 ${confConfig.badge}`} data-testid="badge-reasoning-confidence">
                    {confConfig.label}
                  </Badge>
                </div>
                <div className="h-1.5 bg-muted rounded-full overflow-hidden mb-1">
                  <div className={`h-full rounded-full ${confConfig.bar} ${confConfig.barWidth} transition-all duration-700`} />
                </div>
                {result.confidence_why && (
                  <p className="text-xs text-muted-foreground">{result.confidence_why}</p>
                )}
              </div>
            </div>

            {/* REASONING CHAIN */}
            {result.reasoning?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                  Reasoning
                </p>
                <div className="space-y-0">
                  {result.reasoning.map((step) => (
                    <ReasoningStepCard key={step.step} step={step} />
                  ))}
                </div>
              </div>
            )}

            {/* KEY SIGNS FOR / AGAINST */}
            {(result.key_signs?.length > 0 || result.against_signs?.length > 0) && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {result.key_signs?.length > 0 && (
                  <div className="bg-emerald-50 dark:bg-emerald-950/20 rounded-lg p-3">
                    <p className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 mb-2 flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      Supporting Signs
                    </p>
                    <ul className="space-y-1">
                      {result.key_signs.map((s, i) => (
                        <li key={i} className="flex items-start gap-1.5 text-xs text-emerald-800 dark:text-emerald-300">
                          <ChevronRight className="h-3 w-3 flex-shrink-0 mt-0.5" />
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {result.against_signs?.length > 0 && (
                  <div className="bg-slate-50 dark:bg-slate-950/30 rounded-lg p-3">
                    <p className="text-xs font-semibold text-slate-600 dark:text-slate-400 mb-2 flex items-center gap-1">
                      <Minus className="h-3.5 w-3.5" />
                      Against / Absent
                    </p>
                    <ul className="space-y-1">
                      {result.against_signs.map((s, i) => (
                        <li key={i} className="flex items-start gap-1.5 text-xs text-slate-700 dark:text-slate-400">
                          <ChevronRight className="h-3 w-3 flex-shrink-0 mt-0.5 opacity-50" />
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* DIFFERENTIALS */}
            {result.differentials?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  Differentials to Exclude
                </p>
                <div className="rounded-lg border overflow-hidden">
                  {result.differentials.map((diff, i) => (
                    <DifferentialRow key={i} diff={diff} />
                  ))}
                </div>
              </div>
            )}

            {/* RED FLAGS */}
            {result.red_flags?.length > 0 && (
              <div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900 rounded-lg p-3">
                <p className="text-xs font-semibold text-red-700 dark:text-red-400 mb-2 flex items-center gap-1.5">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  Red Flags — Escalate Immediately if Present
                </p>
                <ul className="space-y-1">
                  {result.red_flags.map((flag, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-xs text-red-800 dark:text-red-300">
                      <ChevronRight className="h-3 w-3 flex-shrink-0 mt-0.5" />
                      {flag}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* LIMITATIONS */}
            {result.limitations && (
              <div className="flex items-start gap-2 p-2.5 bg-muted/50 rounded-lg">
                <Info className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0 mt-0.5" />
                <p className="text-xs text-muted-foreground leading-relaxed">
                  <span className="font-medium">Limitations: </span>
                  {result.limitations}
                </p>
              </div>
            )}

            {/* EVIDENCE REFS */}
            {result.evidence_refs?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
                  Evidence Used in Reasoning
                </p>
                <ul className="space-y-0.5">
                  {result.evidence_refs.map((ref, i) => (
                    <li key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                      <span className="text-muted-foreground/40 flex-shrink-0">[{i + 1}]</span>
                      {ref}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <p className="text-[10px] text-muted-foreground/60 pt-1 border-t leading-relaxed">
              Clinical reasoning is AI-generated and must be reviewed by a qualified clinician.
              Confidence levels reflect pattern matching, not diagnostic certainty.
            </p>
          </div>
        )}

        {result && !expanded && (
          <div className="flex items-center gap-3 py-1">
            <Badge variant="outline" className={`text-xs ${confConfig.badge}`}>
              {confConfig.label}
            </Badge>
            <p className="text-sm font-medium truncate">{result.diagnosis}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
