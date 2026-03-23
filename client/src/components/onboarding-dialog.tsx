import { useState, useEffect } from "react";
import { useLocation } from "wouter";
import {
  Shield, AlertTriangle, ClipboardList,
  ArrowRight, X, CheckCircle2
} from "lucide-react";
import { Button } from "@/components/ui/button";

const STEPS = [
  {
    icon: Shield,
    color: "emerald",
    title: "Pre-Procedure Safety Check",
    description:
      "Before any injectable treatment, run a safety check. Enter the procedure, region, product, and patient factors — and get a risk score, danger zones, and mitigation steps in seconds.",
    action: "Try it now →",
    href: "/safety-check",
  },
  {
    icon: AlertTriangle,
    color: "red",
    title: "Complication Protocols",
    description:
      "If something goes wrong during a treatment, open the Complication Protocols page. Select the scenario — vascular occlusion, anaphylaxis, ptosis, or infection — and get immediate structured guidance.",
    action: "See protocols →",
    href: "/complications",
  },
  {
    icon: ClipboardList,
    color: "blue",
    title: "Session Safety Report",
    description:
      "At the start of a clinic session, queue your patients, run pre-procedure checks for each, and export one consolidated safety report as a PDF for your clinical records.",
    action: "Start a session →",
    href: "/session-report",
  },
];

const STORAGE_KEY = "aestheticite_onboarding_v2";

export function OnboardingDialog() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [, setLocation] = useLocation();

  useEffect(() => {
    try {
      const done = localStorage.getItem(STORAGE_KEY);
      if (!done) setOpen(true);
    } catch {}
  }, []);

  function dismiss() {
    try { localStorage.setItem(STORAGE_KEY, "1"); } catch {}
    setOpen(false);
  }

  function goToFeature(href: string) {
    dismiss();
    setLocation(href);
  }

  if (!open) return null;

  const current = STEPS[step];
  const colorMap: Record<string, string> = {
    emerald: "border-emerald-500/30 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400",
    red:     "border-red-500/30 bg-red-500/5 text-red-600 dark:text-red-400",
    blue:    "border-blue-500/30 bg-blue-500/5 text-blue-600 dark:text-blue-400",
  };
  const iconBg: Record<string, string> = {
    emerald: "bg-emerald-500/10",
    red:     "bg-red-500/10",
    blue:    "bg-blue-500/10",
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
      data-testid="onboarding-overlay"
    >
      <div className="w-full max-w-md bg-background rounded-2xl border shadow-2xl overflow-hidden">

        <div className="flex items-center justify-between px-5 py-4 border-b">
          <div className="flex items-center gap-2">
            <img src="/aestheticite-logo.png" alt="" className="w-6 h-6 rounded object-contain" />
            <span className="font-semibold text-sm">Welcome to AesthetiCite</span>
          </div>
          <button
            onClick={dismiss}
            data-testid="button-close-onboarding"
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex gap-1.5 px-5 pt-4">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-full transition-all ${
                i <= step ? "bg-primary" : "bg-muted"
              }`}
              data-testid={`onboarding-dot-${i}`}
            />
          ))}
        </div>

        <div className="px-5 py-5 space-y-4">
          <div className={`rounded-xl border p-4 ${colorMap[current.color]}`}>
            <div className={`w-10 h-10 rounded-xl ${iconBg[current.color]} flex items-center justify-center mb-3`}>
              <current.icon className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-base mb-2" data-testid="onboarding-title">{current.title}</h3>
            <p className="text-sm leading-relaxed opacity-80">{current.description}</p>
          </div>

          <p className="text-xs text-muted-foreground text-center">
            Feature {step + 1} of {STEPS.length}
          </p>
        </div>

        <div className="px-5 pb-5 flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => step > 0 ? setStep(step - 1) : dismiss()}
            className="text-xs"
            data-testid={step === 0 ? "button-skip-onboarding" : "button-onboarding-back"}
          >
            {step === 0 ? "Skip tour" : "Back"}
          </Button>
          <div className="flex-1" />
          <Button
            variant="outline"
            size="sm"
            onClick={() => goToFeature(current.href)}
            className="gap-1.5 text-xs"
            data-testid="button-onboarding-try"
          >
            {current.action}
          </Button>
          {step < STEPS.length - 1 ? (
            <Button
              size="sm"
              onClick={() => setStep(step + 1)}
              className="gap-1.5 text-xs"
              data-testid="button-onboarding-next"
            >
              Next <ArrowRight className="w-3.5 h-3.5" />
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={dismiss}
              className="gap-1.5 text-xs"
              data-testid="button-onboarding-done"
            >
              <CheckCircle2 className="w-3.5 h-3.5" /> Start using AesthetiCite
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
