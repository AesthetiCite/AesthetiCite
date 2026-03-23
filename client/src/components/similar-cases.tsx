/**
 * Similar Cases — Doximity-inspired network outcome data
 *
 * SimilarCasesPanel  — collapsible panel showing outcome stats + case list
 * LogCaseButton      — frictionless 10-second case logging (pre-filled)
 * NetworkStatsBar    — compact bar showing total network size (empty state)
 */

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  ChevronDown, ChevronRight, Users, TrendingUp,
  Clock, Syringe, CheckCircle2, PlusCircle, Database,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { cn } from "@/lib/utils";

// ─── Types ───────────────────────────────────────────────────────────────────

interface OutcomeStats {
  total_cases: number;
  resolution_rate_pct: number;
  outcome_breakdown: Record<string, number>;
  top_treatments: { treatment: string; cases: number }[];
  hyaluronidase_doses: { dose: string; cases: number }[];
  resolution_time?: {
    median_minutes: number;
    average_minutes: number;
    fastest_minutes: number;
    slowest_minutes: number;
    sample_size: number;
  };
}

interface SimilarCase {
  complication: string;
  treatment: string;
  outcome: string;
  region?: string;
  procedure?: string;
  product?: string;
  hyal_dose?: string;
  time_ago: string;
}

interface SimilarCasesResponse {
  complication: string;
  network_size: number;
  outcome_stats: OutcomeStats | null;
  similar_cases: SimilarCase[];
  message?: string;
}

interface NetworkStats {
  total_cases: number;
  resolved_cases: number;
  resolution_rate_pct: number;
  top_complications: { complication: string; count: number }[];
  data_quality: "early" | "building" | "good";
}

// ─── NetworkStatsBar ─────────────────────────────────────────────────────────

export function NetworkStatsBar({ className }: { className?: string }) {
  const { data } = useQuery<NetworkStats>({
    queryKey: ["/api/cases/stats"],
    staleTime: 5 * 60 * 1000,
  });

  if (!data || data.total_cases === 0) return null;

  return (
    <div className={cn("flex items-center gap-2 text-xs text-muted-foreground", className)}>
      <Database className="h-3.5 w-3.5 text-blue-500 flex-shrink-0" />
      <span>
        <span className="font-medium text-foreground">{data.total_cases}</span> cases in network
        {data.resolution_rate_pct > 0 && (
          <> · <span className="text-emerald-600 font-medium">{data.resolution_rate_pct}%</span> resolved</>
        )}
      </span>
    </div>
  );
}

// ─── SimilarCasesPanel ───────────────────────────────────────────────────────

interface SimilarCasesPanelProps {
  complication: string;
  region?: string;
  defaultExpanded?: boolean;
  className?: string;
}

export function SimilarCasesPanel({
  complication,
  region,
  defaultExpanded = false,
  className,
}: SimilarCasesPanelProps) {
  const [open, setOpen] = useState(defaultExpanded);

  const { data, isLoading } = useQuery<SimilarCasesResponse>({
    queryKey: ["/api/cases", complication, region],
    queryFn: async () => {
      const params = new URLSearchParams({ complication });
      if (region) params.set("region", region);
      const res = await fetch(`/api/cases?${params}`);
      if (!res.ok) throw new Error("Failed");
      return res.json();
    },
    enabled: !!complication && open,
    staleTime: 2 * 60 * 1000,
  });

  const stats = data?.outcome_stats;
  const hasData = data && data.network_size > 0;

  return (
    <Collapsible open={open} onOpenChange={setOpen} className={className}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          data-testid="button-toggle-similar-cases"
          className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors py-1 w-full text-left"
        >
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          <Users className="h-3.5 w-3.5 text-blue-500" />
          <span className="font-medium">Network Outcomes</span>
          {data && (
            <Badge variant="secondary" className="ml-1 text-[10px] h-4 px-1.5">
              {data.network_size} cases
            </Badge>
          )}
        </button>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <Card className="mt-2 border-blue-100 dark:border-blue-900/50">
          <CardContent className="p-3 space-y-3">
            {isLoading && (
              <div className="text-xs text-muted-foreground animate-pulse">Loading network data…</div>
            )}

            {!isLoading && !hasData && (
              <div className="text-xs text-muted-foreground">
                {data?.message ?? "No cases logged yet. Be the first to contribute."}
              </div>
            )}

            {!isLoading && hasData && stats && (
              <>
                {/* Key stats row */}
                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-emerald-50 dark:bg-emerald-950/20 rounded-lg p-2 text-center">
                    <p className="text-[10px] text-muted-foreground">Resolved</p>
                    <p className="text-lg font-bold text-emerald-600" data-testid="text-resolution-rate">
                      {stats.resolution_rate_pct}%
                    </p>
                    <p className="text-[10px] text-muted-foreground">n={stats.total_cases}</p>
                  </div>

                  {stats.resolution_time && (
                    <div className="bg-blue-50 dark:bg-blue-950/20 rounded-lg p-2 text-center">
                      <p className="text-[10px] text-muted-foreground">Median time</p>
                      <p className="text-lg font-bold text-blue-600">
                        {stats.resolution_time.median_minutes}
                      </p>
                      <p className="text-[10px] text-muted-foreground">min (n={stats.resolution_time.sample_size})</p>
                    </div>
                  )}

                  {stats.top_treatments.length > 0 && (
                    <div className="bg-muted/50 rounded-lg p-2 text-center">
                      <p className="text-[10px] text-muted-foreground">Top treatment</p>
                      <p className="text-xs font-semibold mt-1 leading-tight capitalize">
                        {stats.top_treatments[0].treatment}
                      </p>
                      <p className="text-[10px] text-muted-foreground">{stats.top_treatments[0].cases} cases</p>
                    </div>
                  )}
                </div>

                {/* Hyaluronidase dose distribution */}
                {stats.hyaluronidase_doses.length > 0 && (
                  <div>
                    <p className="text-[10px] font-medium text-muted-foreground mb-1.5 flex items-center gap-1">
                      <Syringe className="h-3 w-3" /> Hyaluronidase doses used
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {stats.hyaluronidase_doses.map((d) => (
                        <Badge key={d.dose} variant="outline" className="text-[10px]">
                          {d.dose} × {d.cases}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Resolution time insight */}
                {stats.resolution_time && stats.resolution_time.median_minutes > 0 && (
                  <div className="flex items-start gap-2 p-2 bg-amber-50 dark:bg-amber-950/20 rounded-lg text-xs">
                    <Clock className="h-3.5 w-3.5 text-amber-600 flex-shrink-0 mt-0.5" />
                    <span className="text-amber-700 dark:text-amber-400">
                      Median resolution {stats.resolution_time.median_minutes} min — if beyond this, consider escalation.
                    </span>
                  </div>
                )}

                {/* Individual cases */}
                {data.similar_cases.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-[10px] font-medium text-muted-foreground">Recent cases (anonymised)</p>
                    {data.similar_cases.slice(0, 4).map((c, i) => (
                      <div
                        key={i}
                        className="flex items-start justify-between gap-3 p-2 rounded-lg bg-muted/40 text-xs"
                        data-testid={`similar-case-${i}`}
                      >
                        <div className="min-w-0 flex-1">
                          <p className="font-medium truncate">{c.treatment}</p>
                          {c.region && <p className="text-muted-foreground">{c.region}</p>}
                          {c.hyal_dose && <p className="text-muted-foreground">Hyal: {c.hyal_dose}</p>}
                        </div>
                        <div className="text-right flex-shrink-0">
                          <Badge variant="outline" className="text-[10px]">{c.outcome}</Badge>
                          <p className="text-muted-foreground mt-1">{c.time_ago}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </CollapsibleContent>
    </Collapsible>
  );
}

// ─── LogCaseButton ───────────────────────────────────────────────────────────

interface LogCaseButtonProps {
  complication: string;
  procedure?: string;
  region?: string;
  product?: string;
  prefillTreatment?: string;
  onLogged?: (caseId: string) => void;
  size?: "sm" | "default";
  variant?: "default" | "outline" | "ghost";
  label?: string;
  className?: string;
}

const OUTCOME_OPTIONS = [
  "Resolved",
  "Partially resolved",
  "Ongoing — monitoring",
  "Urgent referral",
  "A&E transfer",
  "Patient declined treatment",
];

export function LogCaseButton({
  complication,
  prefillTreatment = "",
  onLogged,
  size = "sm",
  variant = "outline",
  label = "Log Case",
  className,
}: LogCaseButtonProps) {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [treatment, setTreatment] = useState(prefillTreatment);
  const [outcome, setOutcome] = useState("");
  const [timeToResolution, setTimeToResolution] = useState("");
  const [region, setRegion] = useState("");
  const [hyal, setHyal] = useState("");

  const mutation = useMutation({
    mutationFn: async () => {
      if (!outcome) throw new Error("Outcome required");
      return apiRequest("POST", "/api/cases", {
        complication,
        treatment: treatment || "As per protocol",
        outcome,
        time_to_resolution: timeToResolution || undefined,
        region: region || undefined,
        hyaluronidase_dose: hyal || undefined,
      });
    },
    onSuccess: async (res: any) => {
      const data = await res.json();
      setOpen(false);
      toast({ title: "Case logged", description: `ID: ${data.case_id?.slice(0, 8)}…` });
      queryClient.invalidateQueries({ queryKey: ["/api/cases"] });
      queryClient.invalidateQueries({ queryKey: ["/api/cases/stats"] });
      onLogged?.(data.case_id);
    },
    onError: () => {
      toast({ title: "Failed to log case", variant: "destructive" });
    },
  });

  return (
    <>
      <Button
        size={size}
        variant={variant}
        onClick={() => setOpen(true)}
        className={cn("gap-1.5", className)}
        data-testid="button-log-case"
      >
        <PlusCircle className="h-3.5 w-3.5" />
        {label}
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-sm flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-blue-500" />
              Log Case — {complication}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-3 py-1">
            <div>
              <Label className="text-xs">Outcome <span className="text-red-500">*</span></Label>
              <Select value={outcome} onValueChange={setOutcome}>
                <SelectTrigger className="mt-1 h-8 text-xs" data-testid="select-case-outcome">
                  <SelectValue placeholder="Select outcome…" />
                </SelectTrigger>
                <SelectContent>
                  {OUTCOME_OPTIONS.map((o) => (
                    <SelectItem key={o} value={o} className="text-xs">{o}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label className="text-xs">Treatment given</Label>
              <Input
                className="mt-1 h-8 text-xs"
                placeholder="e.g. hyaluronidase 1500 IU + aspirin"
                value={treatment}
                onChange={(e) => setTreatment(e.target.value)}
                data-testid="input-case-treatment"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Time to resolution</Label>
                <Input
                  className="mt-1 h-8 text-xs"
                  placeholder="e.g. 90 min, 2h"
                  value={timeToResolution}
                  onChange={(e) => setTimeToResolution(e.target.value)}
                  data-testid="input-case-time"
                />
              </div>
              <div>
                <Label className="text-xs">Region (optional)</Label>
                <Input
                  className="mt-1 h-8 text-xs"
                  placeholder="e.g. lips"
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  data-testid="input-case-region"
                />
              </div>
            </div>

            <div>
              <Label className="text-xs">Hyaluronidase dose (if used)</Label>
              <Input
                className="mt-1 h-8 text-xs"
                placeholder="e.g. 1500 IU"
                value={hyal}
                onChange={(e) => setHyal(e.target.value)}
                data-testid="input-case-hyal"
              />
            </div>

            <p className="text-[10px] text-muted-foreground">
              Fully anonymised — no patient data, no clinic name stored. Contributes to network outcome statistics.
            </p>
          </div>

          <DialogFooter className="gap-2">
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => mutation.mutate()}
              disabled={!outcome || mutation.isPending}
              data-testid="button-submit-case"
            >
              {mutation.isPending ? (
                "Logging…"
              ) : (
                <><CheckCircle2 className="h-3.5 w-3.5 mr-1.5" /> Log Case</>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
