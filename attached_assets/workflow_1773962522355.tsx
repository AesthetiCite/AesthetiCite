/**
 * AesthetiCite Workflow Runner
 * The "secret weapon" — fullscreen action-first step-by-step UI.
 *
 * NOT text. ACTIONS.
 *
 * Design:
 *   - One step fills the screen at a time (optional focus mode)
 *   - Each step is a large tap target labelled with a verb
 *   - Critical steps pulsate red
 *   - Timer steps show a countdown
 *   - Branch conditions show as an interrupt banner
 *   - Tap to complete, swipe or button to advance
 *   - Progress bar across the top
 *   - Completion screen with "Log this case" CTA
 *
 * Can be used two ways:
 *   1. <WorkflowRunner> — standalone, fetches from /api/workflow
 *   2. Embedded in complication-decision.tsx
 *
 * Route: /workflow?complication=vascular_occlusion
 */

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight,
  Clock, Maximize2, Minimize2, RotateCcw, Syringe,
  XCircle, Activity, FileText, Eye, Shield,
  Pause, Play,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useLocation } from "wouter";
import { getToken } from "@/lib/auth";
import { LogCaseButton } from "@/components/similar-cases";

// ---------------------------------------------------------------------------
// Types (mirrors workflow_engine.py)
// ---------------------------------------------------------------------------

type StepType = "action" | "assess" | "monitor" | "escalate" | "document" | "wait";
type Priority = "critical" | "high" | "normal";
type Urgency = "immediate" | "urgent" | "same_day" | "routine";
type Risk = "critical" | "high" | "moderate" | "low";

interface Branch {
  condition: string;
  action: string;
  severity: string;
}

interface WorkflowStep {
  step: number;
  type: StepType;
  priority: Priority;
  action: string;
  detail: string;
  timer_seconds?: number;
  drug?: string;
  dose?: string;
  branch?: Branch;
  checkpoint?: string;
}

interface Workflow {
  complication: string;
  display_name: string;
  urgency: Urgency;
  risk_level: Risk;
  time_critical?: string;
  total_steps: number;
  steps: WorkflowStep[];
  completion_criteria: string;
  escalation_trigger: string;
  evidence_basis: string;
}

// ---------------------------------------------------------------------------
// Style constants
// ---------------------------------------------------------------------------

const PRIORITY_STYLES: Record<Priority, {
  bg: string; border: string; number: string; label: string;
}> = {
  critical: {
    bg: "bg-red-600 dark:bg-red-700",
    border: "border-red-500",
    number: "bg-red-600 text-white",
    label: "text-red-100",
  },
  high: {
    bg: "bg-orange-500 dark:bg-orange-600",
    border: "border-orange-400",
    number: "bg-orange-500 text-white",
    label: "text-orange-100",
  },
  normal: {
    bg: "bg-slate-700 dark:bg-slate-800",
    border: "border-slate-600",
    number: "bg-slate-600 text-white",
    label: "text-slate-300",
  },
};

const URGENCY_BADGE: Record<Urgency, string> = {
  immediate: "bg-red-600 text-white",
  urgent:    "bg-orange-500 text-white",
  same_day:  "bg-amber-500 text-white",
  routine:   "bg-slate-500 text-white",
};

const STEP_TYPE_ICON: Record<StepType, React.ElementType> = {
  action:   Shield,
  assess:   Eye,
  monitor:  Activity,
  escalate: AlertTriangle,
  document: FileText,
  wait:     Clock,
};

// ---------------------------------------------------------------------------
// Countdown timer hook
// ---------------------------------------------------------------------------

function useCountdown(seconds: number | undefined, active: boolean) {
  const [remaining, setRemaining] = useState(seconds ?? 0);
  const [paused, setPaused] = useState(false);
  const ref = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setRemaining(seconds ?? 0);
    setPaused(false);
  }, [seconds]);

  useEffect(() => {
    if (!active || !seconds || paused) return;
    ref.current = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          clearInterval(ref.current!);
          return 0;
        }
        return r - 1;
      });
    }, 1000);
    return () => { if (ref.current) clearInterval(ref.current); };
  }, [active, seconds, paused]);

  const reset = () => setRemaining(seconds ?? 0);
  const toggle = () => setPaused((p) => !p);

  return { remaining, paused, reset, toggle };
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m > 0 ? `${m}m ${sec.toString().padStart(2, "0")}s` : `${s}s`;
}

// ---------------------------------------------------------------------------
// Timer display
// ---------------------------------------------------------------------------

function StepTimer({
  seconds,
  active,
  label,
}: {
  seconds: number;
  active: boolean;
  label?: string;
}) {
  const { remaining, paused, reset, toggle } = useCountdown(seconds, active);
  const pct = (remaining / seconds) * 100;
  const urgent = remaining < seconds * 0.25;

  return (
    <div className="flex items-center gap-3 bg-black/20 rounded-xl px-4 py-3">
      {/* Circular timer */}
      <div className="relative w-12 h-12 flex-shrink-0">
        <svg className="-rotate-90 w-12 h-12">
          <circle cx="24" cy="24" r="20" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="3" />
          <circle
            cx="24" cy="24" r="20" fill="none"
            stroke={urgent ? "#ef4444" : "#34d399"}
            strokeWidth="3"
            strokeDasharray={`${2 * Math.PI * 20}`}
            strokeDashoffset={`${2 * Math.PI * 20 * (1 - pct / 100)}`}
            className="transition-all duration-1000"
          />
        </svg>
        <span className={`absolute inset-0 flex items-center justify-center text-[10px] font-bold ${urgent ? "text-red-300" : "text-white"}`}>
          {remaining > 0 ? formatTime(remaining) : "—"}
        </span>
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-white/70">{label ?? "Reassess in"}</p>
        <p className={`text-sm font-bold ${urgent ? "text-red-300" : "text-white"}`}>
          {remaining > 0 ? formatTime(remaining) : "TIME — Reassess now"}
        </p>
      </div>
      <div className="flex gap-1.5">
        <button type="button" onClick={toggle} className="text-white/60 hover:text-white p-1">
          {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
        </button>
        <button type="button" onClick={reset} className="text-white/60 hover:text-white p-1">
          <RotateCcw className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Branch alert — appears if condition is met
// ---------------------------------------------------------------------------

function BranchAlert({ branch }: { branch: Branch }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  const isCritical = branch.severity === "critical";
  return (
    <div className={`rounded-xl border-2 p-3 ${
      isCritical ? "border-red-400 bg-red-900/40" : "border-amber-400 bg-amber-900/30"
    }`}>
      <div className="flex items-start gap-2.5 mb-2">
        <AlertTriangle className={`h-4 w-4 flex-shrink-0 mt-0.5 ${isCritical ? "text-red-300" : "text-amber-300"}`} />
        <div>
          <p className="text-xs font-semibold text-white/80 uppercase tracking-wide">If condition met:</p>
          <p className="text-sm font-medium text-white mt-0.5">{branch.condition}</p>
        </div>
      </div>
      <p className={`text-sm font-bold mb-2 ${isCritical ? "text-red-200" : "text-amber-200"}`}>
        → {branch.action}
      </p>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        className="text-xs text-white/50 hover:text-white/80"
      >
        Condition not met — continue
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single step card (fullscreen version)
// ---------------------------------------------------------------------------

function StepCard({
  step,
  isActive,
  isCompleted,
  isFocusMode,
  onComplete,
}: {
  step: WorkflowStep;
  isActive: boolean;
  isCompleted: boolean;
  isFocusMode: boolean;
  onComplete: () => void;
}) {
  const style = PRIORITY_STYLES[step.priority];
  const TypeIcon = STEP_TYPE_ICON[step.type];

  return (
    <div
      className={`
        relative rounded-2xl border-2 transition-all duration-200 select-none overflow-hidden
        ${isActive && !isCompleted ? style.border : "border-white/10"}
        ${isCompleted ? "opacity-50" : ""}
        ${isFocusMode && isActive ? "ring-4 ring-white/30" : ""}
      `}
    >
      {/* Background gradient for active critical step */}
      {isActive && step.priority === "critical" && !isCompleted && (
        <div className="absolute inset-0 bg-red-600/10 pointer-events-none" />
      )}

      <div className={`p-4 sm:p-6 ${isFocusMode ? "min-h-[280px] flex flex-col justify-center" : ""}`}>
        {/* Step header */}
        <div className="flex items-start gap-3 mb-4">
          {/* Step number */}
          <div className={`
            w-10 h-10 rounded-full flex items-center justify-center text-base font-bold flex-shrink-0
            ${isCompleted ? "bg-emerald-500 text-white" : style.number}
          `}>
            {isCompleted ? <CheckCircle2 className="h-5 w-5" /> : step.step}
          </div>

          <div className="flex-1 min-w-0">
            {/* Step type label */}
            <div className="flex items-center gap-1.5 mb-1">
              <TypeIcon className="h-3.5 w-3.5 text-white/50" />
              <span className="text-[10px] text-white/50 uppercase tracking-widest font-medium">
                {step.type}
              </span>
              {step.priority === "critical" && (
                <Badge className="text-[10px] bg-red-600 text-white px-1.5 py-0 animate-pulse ml-1">
                  CRITICAL
                </Badge>
              )}
            </div>

            {/* ACTION — the big headline */}
            <p className={`font-bold leading-tight text-white ${
              isFocusMode ? "text-2xl sm:text-3xl" : "text-xl"
            }`}>
              {step.action}
            </p>
          </div>
        </div>

        {/* Detail */}
        <p className={`text-white/75 leading-relaxed mb-4 ${isFocusMode ? "text-base" : "text-sm"}`}>
          {step.detail}
        </p>

        {/* Drug / dose block */}
        {(step.drug || step.dose) && (
          <div className="flex items-start gap-2 bg-white/10 rounded-xl p-3 mb-4">
            <Syringe className="h-4 w-4 text-blue-300 flex-shrink-0 mt-0.5" />
            <div className="text-sm">
              {step.drug && <p className="font-bold text-white">{step.drug}</p>}
              {step.dose && <p className="text-white/75">{step.dose}</p>}
            </div>
          </div>
        )}

        {/* Timer */}
        {step.timer_seconds && isActive && !isCompleted && (
          <div className="mb-4">
            <StepTimer
              seconds={step.timer_seconds}
              active={isActive && !isCompleted}
              label={step.type === "monitor" ? "Reassess in" : "Repeat in"}
            />
          </div>
        )}

        {/* Checkpoint */}
        {step.checkpoint && (
          <p className="text-xs text-white/50 italic mb-4">
            ✓ Before advancing: {step.checkpoint}
          </p>
        )}

        {/* Branch alert */}
        {step.branch && isActive && !isCompleted && (
          <div className="mb-4">
            <BranchAlert branch={step.branch} />
          </div>
        )}

        {/* Complete button */}
        {isActive && !isCompleted && (
          <button
            type="button"
            onClick={onComplete}
            className={`
              w-full py-4 rounded-xl font-bold text-white text-base
              transition-all duration-150 active:scale-95
              ${step.priority === "critical"
                ? "bg-red-500 hover:bg-red-400 shadow-lg shadow-red-500/30"
                : step.priority === "high"
                ? "bg-orange-500 hover:bg-orange-400"
                : "bg-white/20 hover:bg-white/30 border border-white/30"
              }
            `}
          >
            {step.type === "assess"    ? "✓ Assessed" :
             step.type === "document" ? "✓ Documented" :
             step.type === "monitor"  ? "✓ Checked" :
             step.type === "wait"     ? "✓ Done waiting" :
             "✓ Done"}
          </button>
        )}

        {/* Completed label */}
        {isCompleted && (
          <div className="flex items-center gap-2 text-emerald-400 text-sm">
            <CheckCircle2 className="h-4 w-4" />
            Completed
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main WorkflowRunner component
// ---------------------------------------------------------------------------

interface WorkflowRunnerProps {
  complication: string;
  procedure?: string;
  region?: string;
  product?: string;
  onComplete?: () => void;
  className?: string;
}

export function WorkflowRunner({
  complication,
  procedure,
  region,
  product,
  onComplete,
  className = "",
}: WorkflowRunnerProps) {
  const { toast } = useToast();
  const [currentStep, setCurrentStep] = useState(0);        // 0-indexed
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());
  const [focusMode, setFocusMode] = useState(false);
  const [finished, setFinished] = useState(false);
  const stepRef = useRef<HTMLDivElement>(null);

  const { data: workflow, isLoading, error } = useQuery({
    queryKey: ["workflow", complication],
    queryFn: async () => {
      const token = getToken();
      const res = await fetch(
        `/api/workflow?complication=${encodeURIComponent(complication)}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      if (!res.ok) throw new Error("Workflow not found");
      return res.json() as Promise<Workflow>;
    },
    staleTime: Infinity,  // workflow never changes during session
  });

  const steps = workflow?.steps ?? [];
  const totalSteps = steps.length;
  const progress = totalSteps > 0 ? Math.round((completedSteps.size / totalSteps) * 100) : 0;
  const activeStep = steps[currentStep];

  const completeStep = (idx: number) => {
    setCompletedSteps((prev) => new Set([...prev, idx]));
    if (idx === totalSteps - 1) {
      setFinished(true);
      onComplete?.();
    } else {
      setCurrentStep(idx + 1);
      setTimeout(() => stepRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    }
  };

  const reset = () => {
    setCurrentStep(0);
    setCompletedSteps(new Set());
    setFinished(false);
  };

  if (isLoading) {
    return (
      <div className={`bg-slate-900 rounded-2xl p-6 ${className}`}>
        <div className="flex items-center gap-3 text-white/60">
          <div className="h-5 w-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          Loading workflow…
        </div>
      </div>
    );
  }

  if (error || !workflow) {
    return (
      <div className={`bg-slate-900 rounded-2xl p-6 ${className}`}>
        <p className="text-white/60 text-sm">Workflow unavailable for "{complication}".</p>
      </div>
    );
  }

  return (
    <div className={`bg-slate-900 rounded-2xl overflow-hidden ${className}`}>
      {/* ── Header ── */}
      <div className="px-4 pt-4 pb-3 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <Badge className={`text-xs ${URGENCY_BADGE[workflow.urgency]}`}>
              {workflow.urgency.replace("_", " ").toUpperCase()}
            </Badge>
            <span className="text-white/50 text-xs">
              {completedSteps.size}/{totalSteps} steps
            </span>
          </div>
          <h2 className="text-white font-bold text-lg leading-tight">{workflow.display_name}</h2>
          {workflow.time_critical && (
            <p className="text-red-300 text-xs mt-0.5 flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {workflow.time_critical}
            </p>
          )}
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button
            type="button"
            onClick={reset}
            className="text-white/40 hover:text-white/80 p-1.5"
            title="Restart"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setFocusMode(!focusMode)}
            className="text-white/40 hover:text-white/80 p-1.5"
            title={focusMode ? "Exit focus mode" : "Focus mode"}
          >
            {focusMode ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {/* ── Progress bar ── */}
      <div className="h-1.5 bg-white/10 mx-4 rounded-full overflow-hidden mb-4">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            progress === 100 ? "bg-emerald-500" : "bg-blue-500"
          }`}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* ── Escalation trigger banner ── */}
      {workflow.escalation_trigger && workflow.urgency === "immediate" && (
        <div className="mx-4 mb-4 flex items-start gap-2 bg-red-900/40 border border-red-500/40 rounded-xl p-3">
          <AlertTriangle className="h-4 w-4 text-red-400 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-red-200">{workflow.escalation_trigger}</p>
        </div>
      )}

      {/* ── Steps ── */}
      <div className="px-4 pb-4 space-y-3" ref={stepRef}>
        {finished ? (
          /* Completion screen */
          <div className="text-center py-8 space-y-4">
            <div className="w-16 h-16 bg-emerald-500 rounded-full flex items-center justify-center mx-auto">
              <CheckCircle2 className="h-8 w-8 text-white" />
            </div>
            <div>
              <p className="text-white font-bold text-xl">Protocol Complete</p>
              <p className="text-white/60 text-sm mt-1">{workflow.completion_criteria}</p>
            </div>
            <div className="flex flex-col gap-2">
              <LogCaseButton
                complication={workflow.display_name}
                procedure={procedure}
                region={region}
                product={product}
                prefillTreatment={
                  steps
                    .filter((_, i) => completedSteps.has(i) && steps[i].drug)
                    .map((s) => `${s.drug} ${s.dose ?? ""}`.trim())
                    .join("; ")
                }
                label="Log This Case"
                variant="default"
              />
              <button
                type="button"
                onClick={reset}
                className="text-white/50 hover:text-white text-sm flex items-center justify-center gap-1.5"
              >
                <RotateCcw className="h-3.5 w-3.5" /> Run again
              </button>
            </div>
            <p className="text-[10px] text-white/30">
              Evidence basis: {workflow.evidence_basis}
            </p>
          </div>
        ) : focusMode ? (
          /* Focus mode: show only current step */
          <div className="space-y-4">
            {activeStep && (
              <StepCard
                step={activeStep}
                isActive={true}
                isCompleted={completedSteps.has(currentStep)}
                isFocusMode={true}
                onComplete={() => completeStep(currentStep)}
              />
            )}
            {/* Prev / Next navigation */}
            <div className="flex items-center justify-between">
              <button
                type="button"
                disabled={currentStep === 0}
                onClick={() => setCurrentStep((s) => Math.max(0, s - 1))}
                className="flex items-center gap-1 text-white/50 hover:text-white disabled:opacity-30 text-sm"
              >
                <ChevronLeft className="h-4 w-4" /> Previous
              </button>
              <span className="text-white/30 text-xs">
                {currentStep + 1} / {totalSteps}
              </span>
              <button
                type="button"
                disabled={currentStep === totalSteps - 1}
                onClick={() => setCurrentStep((s) => Math.min(totalSteps - 1, s + 1))}
                className="flex items-center gap-1 text-white/50 hover:text-white disabled:opacity-30 text-sm"
              >
                Next <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        ) : (
          /* Normal mode: show all steps, scroll through */
          steps.map((step, idx) => (
            <StepCard
              key={step.step}
              step={step}
              isActive={idx === currentStep}
              isCompleted={completedSteps.has(idx)}
              isFocusMode={false}
              onComplete={() => completeStep(idx)}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Standalone page — /workflow?complication=
// ---------------------------------------------------------------------------

export default function WorkflowPage() {
  const [loc] = useLocation();
  const params = new URLSearchParams(loc.split("?")[1] ?? "");
  const complication = params.get("complication") ?? "vascular_occlusion";

  return (
    <div className="min-h-screen bg-slate-950 py-4 px-3 sm:px-4">
      <div className="max-w-xl mx-auto">
        <WorkflowRunner
          complication={complication}
          className="min-h-[60vh]"
        />
      </div>
    </div>
  );
}
