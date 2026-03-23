/**
 * AesthetiCite Vision — Complication Diagnosis Result Component
 *
 * Renders the VisualDX-style output from /api/vision/diagnose:
 *   1. Primary diagnosis card — "Possible complication: vascular occlusion"
 *   2. Confidence bar + urgency badge
 *   3. Visual evidence list (what the AI saw)
 *   4. Differential diagnoses (ranked alternatives)
 *   5. Clinical action — what to do now
 *   6. Bridge button → opens /decide pre-filled with detected complication
 *
 * Also exports:
 *   <VisionDiagnoseButton>  — upload button that triggers the full flow
 *   <VisionCompareResultPanel> — renders serial comparison results
 */

import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertTriangle, Camera, CheckCircle2, ChevronRight,
  Eye, ExternalLink, Info, RefreshCw, Shield,
  TrendingDown, TrendingUp, XCircle, Zap,
  Activity, Upload,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { getToken } from "@/lib/auth";
import { Link } from "wouter";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface VisionDiagnosis {
  complication: string;
  display_name: string;
  confidence: number;
  confidence_label: "low" | "medium" | "high";
  urgency: "immediate" | "urgent" | "same_day" | "routine";
  visual_evidence: string[];
  risk_level: "critical" | "high" | "moderate" | "low";
  action?: string;
  exclude_reason?: string;
  is_new_since_baseline?: boolean;
}

export interface VisionDiagnoseResult {
  image_quality: "good" | "acceptable" | "poor";
  visual_signs_detected: string[];
  primary: VisionDiagnosis;
  differentials: VisionDiagnosis[];
  safe_to_proceed: boolean;
  trigger_protocol: string | null;
  overall_risk_level: "critical" | "high" | "moderate" | "low";
  clinical_note: string;
  disclaimer: string;
  latency_ms: number;
  image_id: string;
}

export interface VisionCompareResult {
  change_status: "improved" | "stable" | "mildly_worsened" | "significantly_worsened";
  image_quality: "good" | "acceptable" | "poor";
  new_signs_detected: string[];
  resolved_signs: string[];
  persistent_signs: string[];
  primary_concern: VisionDiagnosis & { is_new_since_baseline: boolean };
  additional_concerns: VisionDiagnosis[];
  clinical_changes: {
    asymmetry: string;
    erythema: string;
    swelling: string;
    discolouration: string;
    blanching: string;
  };
  safe_to_continue_monitoring: boolean;
  trigger_protocol: string | null;
  clinical_note: string;
  disclaimer: string;
  latency_ms: number;
}

// ---------------------------------------------------------------------------
// Styling constants
// ---------------------------------------------------------------------------

const URGENCY_CONFIG = {
  immediate: {
    label: "IMMEDIATE",
    badge: "bg-red-600 text-white border-transparent",
    border: "border-red-500",
    icon: XCircle,
    pulsate: true,
  },
  urgent: {
    label: "URGENT",
    badge: "bg-orange-500 text-white border-transparent",
    border: "border-orange-400",
    icon: AlertTriangle,
    pulsate: false,
  },
  same_day: {
    label: "SAME DAY",
    badge: "bg-amber-500 text-white border-transparent",
    border: "border-amber-400",
    icon: Activity,
    pulsate: false,
  },
  routine: {
    label: "ROUTINE",
    badge: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200 border-transparent",
    border: "border-slate-200 dark:border-slate-700",
    icon: CheckCircle2,
    pulsate: false,
  },
} as const;

const CONFIDENCE_COLORS = {
  high:   "bg-emerald-500",
  medium: "bg-amber-500",
  low:    "bg-slate-400",
};

const RISK_BADGE = {
  critical: "bg-red-100 text-red-800 border-red-300 dark:bg-red-900/30 dark:text-red-300",
  high:     "bg-orange-100 text-orange-800 border-orange-300 dark:bg-orange-900/30 dark:text-orange-300",
  moderate: "bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/30 dark:text-amber-300",
  low:      "bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-400",
};

const CHANGE_CONFIG = {
  improved:               { label: "Improving",              icon: TrendingDown, cls: "text-emerald-600" },
  stable:                 { label: "Stable",                 icon: Activity,     cls: "text-blue-600" },
  mildly_worsened:        { label: "Mildly Worsened",        icon: TrendingUp,   cls: "text-amber-600" },
  significantly_worsened: { label: "Significantly Worsened", icon: TrendingUp,   cls: "text-red-600" },
};

// ---------------------------------------------------------------------------
// Confidence bar
// ---------------------------------------------------------------------------

function ConfidenceBar({ label, value }: { label: "low" | "medium" | "high"; value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 bg-muted rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${CONFIDENCE_COLORS[label]} transition-all duration-700`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[11px] text-muted-foreground w-8 text-right">{pct}%</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Primary diagnosis card
// ---------------------------------------------------------------------------

function PrimaryDiagnosisCard({
  diagnosis,
  imageId,
}: {
  diagnosis: VisionDiagnosis;
  imageId?: string;
}) {
  const urg = URGENCY_CONFIG[diagnosis.urgency] ?? URGENCY_CONFIG.routine;
  const UrgIcon = urg.icon;

  return (
    <Card className={`border-2 ${urg.border}`} data-testid={`card-vision-primary-${diagnosis.complication}`}>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] text-muted-foreground uppercase tracking-wide font-semibold mb-0.5">
              Possible Complication
            </p>
            <p className="font-bold text-lg leading-tight">{diagnosis.display_name}</p>
          </div>
          <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
            <Badge
              className={`text-xs font-bold ${urg.badge} ${urg.pulsate ? "animate-pulse" : ""}`}
              data-testid={`badge-urgency-${diagnosis.urgency}`}
            >
              <UrgIcon className="h-3 w-3 mr-1" />
              {urg.label}
            </Badge>
            <Badge
              variant="outline"
              className={`text-[11px] ${RISK_BADGE[diagnosis.risk_level]}`}
            >
              {diagnosis.risk_level.toUpperCase()} RISK
            </Badge>
          </div>
        </div>

        <div>
          <div className="flex justify-between text-[11px] text-muted-foreground mb-1">
            <span>Confidence</span>
            <span className="capitalize">{diagnosis.confidence_label}</span>
          </div>
          <ConfidenceBar label={diagnosis.confidence_label} value={diagnosis.confidence} />
        </div>

        {diagnosis.visual_evidence?.length > 0 && (
          <div>
            <p className="text-[11px] text-muted-foreground font-medium mb-1">Visual evidence observed:</p>
            <ul className="space-y-0.5">
              {diagnosis.visual_evidence.map((ev, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs">
                  <Eye className="h-3 w-3 flex-shrink-0 mt-0.5 text-blue-500" />
                  {ev}
                </li>
              ))}
            </ul>
          </div>
        )}

        {diagnosis.action && (
          <div className={`rounded-lg p-2.5 text-xs font-medium ${
            diagnosis.urgency === "immediate" ? "bg-red-50 dark:bg-red-950/20 text-red-800 dark:text-red-300" :
            diagnosis.urgency === "urgent"    ? "bg-orange-50 dark:bg-orange-950/20 text-orange-800 dark:text-orange-300" :
            "bg-muted text-muted-foreground"
          }`}>
            <Zap className="h-3.5 w-3.5 inline mr-1.5" />
            {diagnosis.action}
          </div>
        )}

        {diagnosis.complication && diagnosis.complication !== "normal_post_procedure" && (
          <Link href={`/decide?complication=${encodeURIComponent(diagnosis.display_name)}`}>
            <Button
              size="sm"
              className="w-full gap-1.5"
              variant={diagnosis.urgency === "immediate" ? "destructive" : "default"}
              data-testid="button-open-clinical-protocol"
            >
              <Shield className="h-3.5 w-3.5" />
              Open Clinical Protocol
              <ExternalLink className="h-3 w-3 ml-auto" />
            </Button>
          </Link>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Differential row
// ---------------------------------------------------------------------------

function DifferentialRow({ diff }: { diff: VisionDiagnosis }) {
  const [open, setOpen] = useState(false);
  const pct = Math.round(diff.confidence * 100);
  const urg = URGENCY_CONFIG[diff.urgency] ?? URGENCY_CONFIG.routine;

  return (
    <div
      className="py-2 border-b last:border-0 cursor-pointer"
      onClick={() => setOpen(!open)}
    >
      <div className="flex items-center gap-3">
        <div className="w-12 text-[11px] text-muted-foreground text-right flex-shrink-0">{pct}%</div>
        <div className="h-1.5 flex-1 bg-muted rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${CONFIDENCE_COLORS[diff.confidence_label]}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-xs font-medium flex-shrink-0 min-w-0">{diff.display_name}</p>
        <Badge className={`text-[10px] ${urg.badge} flex-shrink-0`}>{urg.label}</Badge>
        <ChevronRight className={`h-3.5 w-3.5 text-muted-foreground flex-shrink-0 transition-transform ${open ? "rotate-90" : ""}`} />
      </div>

      {open && (
        <div className="mt-2 pl-15 space-y-1.5 ml-12">
          {diff.visual_evidence?.length > 0 && (
            <ul className="space-y-0.5">
              {diff.visual_evidence.map((ev, i) => (
                <li key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
                  <Eye className="h-3 w-3 flex-shrink-0 mt-0.5 text-blue-400" />{ev}
                </li>
              ))}
            </ul>
          )}
          {diff.exclude_reason && (
            <p className="text-xs text-muted-foreground italic">
              Less likely: {diff.exclude_reason}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main result component — single image diagnosis
// ---------------------------------------------------------------------------

interface VisionDiagnoseResultProps {
  result: VisionDiagnoseResult;
  onReset?: () => void;
}

export function VisionDiagnoseResultPanel({ result, onReset }: VisionDiagnoseResultProps) {
  const top3Differentials = (result.differentials ?? []).slice(0, 4);

  return (
    <div className="space-y-4" data-testid="panel-vision-diagnose-result">
      {result.image_quality === "poor" && (
        <div className="flex items-center gap-2 p-2.5 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 rounded-lg text-xs text-amber-700 dark:text-amber-400">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          Image quality is poor — results may be less reliable. Consider retaking the photograph.
        </div>
      )}

      {result.clinical_note && (
        <div className="flex items-start gap-2 text-sm font-medium p-3 bg-muted/50 rounded-lg">
          <Info className="h-4 w-4 flex-shrink-0 mt-0.5 text-blue-500" />
          {result.clinical_note}
        </div>
      )}

      <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${
        result.safe_to_proceed
          ? "bg-emerald-50 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-400"
          : "bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-400"
      }`}>
        {result.safe_to_proceed
          ? <><CheckCircle2 className="h-4 w-4 flex-shrink-0" /> Proceed with monitoring and standard aftercare</>
          : <><XCircle className="h-4 w-4 flex-shrink-0" /> Do not proceed — complication management required</>
        }
      </div>

      <PrimaryDiagnosisCard diagnosis={result.primary} imageId={result.image_id} />

      {result.visual_signs_detected?.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            Visual Signs Observed
          </p>
          <div className="flex flex-wrap gap-1.5">
            {result.visual_signs_detected.map((sign, i) => (
              <Badge key={i} variant="secondary" className="text-xs">{sign}</Badge>
            ))}
          </div>
        </div>
      )}

      {top3Differentials.length > 0 && (
        <Card>
          <CardHeader className="pb-1.5 pt-3 px-4">
            <CardTitle className="text-xs text-muted-foreground font-semibold uppercase tracking-wide">
              Differential Diagnoses
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3">
            {top3Differentials.map((diff, i) => (
              <DifferentialRow key={i} diff={diff} />
            ))}
          </CardContent>
        </Card>
      )}

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{result.latency_ms}ms · GPT-4o Vision</span>
        {onReset && (
          <button
            type="button"
            onClick={onReset}
            className="hover:text-foreground flex items-center gap-1"
            data-testid="button-vision-reset"
          >
            <RefreshCw className="h-3 w-3" /> New image
          </button>
        )}
      </div>

      <p className="text-[10px] text-muted-foreground/60 leading-relaxed border-t pt-2">
        {result.disclaimer}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Serial comparison result panel
// ---------------------------------------------------------------------------

interface VisionCompareResultProps {
  result: VisionCompareResult;
  onReset?: () => void;
}

export function VisionCompareResultPanel({ result, onReset }: VisionCompareResultProps) {
  const changeCfg = CHANGE_CONFIG[result.change_status] ?? CHANGE_CONFIG.stable;
  const ChangeIcon = changeCfg.icon;
  const concern = result.primary_concern;
  const urg = concern ? (URGENCY_CONFIG[concern.urgency] ?? URGENCY_CONFIG.routine) : URGENCY_CONFIG.routine;

  return (
    <div className="space-y-4" data-testid="panel-vision-compare-result">
      <div className={`flex items-center gap-2 p-3 rounded-lg border ${
        result.change_status === "significantly_worsened" ? "border-red-400 bg-red-50 dark:bg-red-950/20" :
        result.change_status === "mildly_worsened"        ? "border-amber-400 bg-amber-50 dark:bg-amber-950/20" :
        result.change_status === "stable"                 ? "border-blue-200 bg-blue-50 dark:bg-blue-950/20" :
        "border-emerald-200 bg-emerald-50 dark:bg-emerald-950/20"
      }`}>
        <ChangeIcon className={`h-5 w-5 flex-shrink-0 ${changeCfg.cls}`} />
        <div>
          <p className="font-semibold text-sm">{changeCfg.label}</p>
          {result.clinical_note && (
            <p className="text-xs text-muted-foreground mt-0.5">{result.clinical_note}</p>
          )}
        </div>
      </div>

      {result.clinical_changes && (
        <Card>
          <CardHeader className="pb-1.5 pt-3 px-4">
            <CardTitle className="text-xs text-muted-foreground font-semibold uppercase tracking-wide">
              Clinical Change Summary
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3">
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              {Object.entries(result.clinical_changes).map(([key, val]) => {
                if (val === "not_applicable") return null;
                const cls =
                  val === "improved"  ? "text-emerald-600 dark:text-emerald-400" :
                  val === "worsened"  ? "text-red-600 dark:text-red-400" :
                  val === "present"   ? "text-red-600 dark:text-red-400" :
                  "text-muted-foreground";
                return (
                  <div key={key} className="flex items-center justify-between text-xs">
                    <span className="capitalize font-medium">{key}</span>
                    <span className={`capitalize ${cls}`}>{val}</span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {concern && concern.complication !== "normal_post_procedure" && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2 flex items-center gap-2">
            Primary Concern
            {concern.is_new_since_baseline && (
              <Badge className="text-[10px] bg-red-100 text-red-700 border-red-300">NEW</Badge>
            )}
          </p>
          <PrimaryDiagnosisCard diagnosis={concern} />
        </div>
      )}

      {result.new_signs_detected?.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
            New Signs Since Baseline
          </p>
          <div className="flex flex-wrap gap-1.5">
            {result.new_signs_detected.map((s, i) => (
              <Badge key={i} variant="outline" className="text-xs bg-red-50 dark:bg-red-950/20 border-red-200 text-red-700 dark:text-red-400">
                ↑ {s}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {result.resolved_signs?.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
            Resolved Since Baseline
          </p>
          <div className="flex flex-wrap gap-1.5">
            {result.resolved_signs.map((s, i) => (
              <Badge key={i} variant="outline" className="text-xs bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 text-emerald-700 dark:text-emerald-400">
                ✓ {s}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{result.latency_ms}ms · GPT-4o Vision</span>
        {onReset && (
          <button
            type="button"
            onClick={onReset}
            className="hover:text-foreground flex items-center gap-1"
            data-testid="button-vision-compare-reset"
          >
            <RefreshCw className="h-3 w-3" /> New comparison
          </button>
        )}
      </div>

      <p className="text-[10px] text-muted-foreground/60 leading-relaxed border-t pt-2">
        {result.disclaimer}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// VisionDiagnoseButton — drop-in upload button for existing pages
// ---------------------------------------------------------------------------

interface VisionDiagnoseButtonProps {
  procedure?: string;
  region?: string;
  timeSince?: string;
  product?: string;
  onResult?: (result: VisionDiagnoseResult) => void;
  label?: string;
  variant?: "default" | "outline" | "secondary";
  size?: "sm" | "default";
}

export function VisionDiagnoseButton({
  procedure = "",
  region = "",
  timeSince = "",
  product = "",
  onResult,
  label = "Analyse Image for Complications",
  variant = "outline",
  size = "sm",
}: VisionDiagnoseButtonProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();
  const [result, setResult] = useState<VisionDiagnoseResult | null>(null);

  const mutation = useMutation({
    mutationFn: async (file: File) => {
      const token = getToken();
      const fd = new FormData();
      fd.append("file", file);
      if (procedure) fd.append("procedure", procedure);
      if (region)    fd.append("region", region);
      if (timeSince) fd.append("time_since", timeSince);
      if (product)   fd.append("product", product);

      const res = await fetch("/api/vision/diagnose", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? "Vision diagnosis failed");
      }
      return res.json() as Promise<VisionDiagnoseResult>;
    },
    onSuccess: (data) => {
      setResult(data);
      onResult?.(data);
      if (data.primary?.urgency === "immediate") {
        toast({
          title: `⚠️ ${data.primary.display_name} detected`,
          description: data.primary.action ?? "Act immediately.",
          variant: "destructive",
        });
      }
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) mutation.mutate(file);
    e.target.value = "";
  };

  if (result) {
    return (
      <div className="space-y-3">
        <VisionDiagnoseResultPanel result={result} onReset={() => setResult(null)} />
      </div>
    );
  }

  return (
    <>
      <input
        type="file"
        accept="image/*"
        ref={fileRef}
        className="hidden"
        onChange={handleFile}
        data-testid="input-vision-file"
      />
      <Button
        variant={variant}
        size={size}
        onClick={() => fileRef.current?.click()}
        disabled={mutation.isPending}
        className="gap-2"
        data-testid="button-vision-diagnose"
      >
        {mutation.isPending ? (
          <><RefreshCw className="h-3.5 w-3.5 animate-spin" /> Analysing…</>
        ) : (
          <><Camera className="h-3.5 w-3.5" /> {label}</>
        )}
      </Button>
    </>
  );
}
