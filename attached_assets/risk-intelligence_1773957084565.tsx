import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  AlertTriangle, Shield, TrendingUp, Activity, Zap, CheckCircle2,
  XCircle, RefreshCw, ChevronRight, Eye, BarChart3, MapPin,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useClinicContext } from "@/hooks/use-clinic-context";
import { ClinicSwitcher } from "@/components/clinic-switcher";
import { getToken } from "@/lib/auth";

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------

async function api<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Risk level styling
// ---------------------------------------------------------------------------

const RISK_STYLES: Record<string, { badge: string; bg: string; icon: React.ElementType }> = {
  normal:   { badge: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300", bg: "", icon: CheckCircle2 },
  elevated: { badge: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300", bg: "border-amber-200 dark:border-amber-800", icon: TrendingUp },
  high:     { badge: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300", bg: "border-orange-300 dark:border-orange-700", icon: AlertTriangle },
  critical: { badge: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300", bg: "border-red-400 dark:border-red-700", icon: XCircle },
};

const SEVERITY_STYLES: Record<string, string> = {
  info:     "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  warning:  "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  critical: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
};

function RiskBadge({ level }: { level: string }) {
  const s = RISK_STYLES[level] ?? RISK_STYLES.normal;
  return (
    <Badge variant="outline" className={`text-xs capitalize ${s.badge}`}>
      {level}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Practitioner risk card
// ---------------------------------------------------------------------------

function PractitionerCard({ score }: { score: any }) {
  const [expanded, setExpanded] = useState(false);
  const s = RISK_STYLES[score.risk_level] ?? RISK_STYLES.normal;
  const Icon = s.icon;

  return (
    <Card className={`transition-colors ${s.bg}`}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0 flex-1">
            <Icon className={`h-5 w-5 flex-shrink-0 mt-0.5 ${
              score.risk_level === "critical" ? "text-red-500" :
              score.risk_level === "high" ? "text-orange-500" :
              score.risk_level === "elevated" ? "text-amber-500" : "text-emerald-500"
            }`} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="font-medium text-sm">{score.practitioner_name}</p>
                <RiskBadge level={score.risk_level} />
              </div>
              <div className="flex gap-4 mt-1 flex-wrap">
                <span className="text-xs text-muted-foreground">{score.total_cases} cases</span>
                {score.high_risk_cases > 0 && (
                  <span className="text-xs text-amber-600 dark:text-amber-400">{score.high_risk_cases} high-risk</span>
                )}
                {score.vascular_cases > 0 && (
                  <span className="text-xs text-red-600 dark:text-red-400">{score.vascular_cases} vascular</span>
                )}
                {score.unresolved_cases > 0 && (
                  <span className="text-xs text-orange-600 dark:text-orange-400">{score.unresolved_cases} unresolved</span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            <div className="text-right">
              <p className="text-lg font-semibold">{score.risk_score}</p>
              <p className="text-xs text-muted-foreground">risk score</p>
            </div>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 w-7 p-0"
              onClick={() => setExpanded(!expanded)}
            >
              <ChevronRight className={`h-4 w-4 transition-transform ${expanded ? "rotate-90" : ""}`} />
            </Button>
          </div>
        </div>

        {/* Risk score bar */}
        <div className="mt-3 h-1.5 bg-muted rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              score.risk_level === "critical" ? "bg-red-500" :
              score.risk_level === "high" ? "bg-orange-500" :
              score.risk_level === "elevated" ? "bg-amber-500" : "bg-emerald-500"
            }`}
            style={{ width: `${Math.min(score.risk_score * 3, 100)}%` }}
          />
        </div>

        {expanded && score.top_complications?.length > 0 && (
          <div className="mt-3 pt-3 border-t">
            <p className="text-xs text-muted-foreground mb-2">Top complications</p>
            <div className="flex flex-wrap gap-1.5">
              {score.top_complications.map((c: any) => (
                <Badge key={c.type} variant="secondary" className="text-xs">
                  {c.type} ({c.count})
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Alert card
// ---------------------------------------------------------------------------

function AlertCard({ alert, onDismiss }: { alert: any; onDismiss: (id: string) => void }) {
  const sev = alert.severity as string;
  const sClass = SEVERITY_STYLES[sev] ?? SEVERITY_STYLES.info;

  return (
    <Card className={`border-l-4 ${
      sev === "critical" ? "border-l-red-500" :
      sev === "warning" ? "border-l-amber-500" : "border-l-blue-500"
    }`}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <Badge variant="outline" className={`text-xs ${sClass}`}>{sev.toUpperCase()}</Badge>
              <p className="font-medium text-sm">{alert.title}</p>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">{alert.body}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {new Date(alert.created_at).toLocaleString()}
            </p>
          </div>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs flex-shrink-0"
            onClick={() => onDismiss(alert.id)}
          >
            Dismiss
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Heatmap table
// ---------------------------------------------------------------------------

function HeatmapTable({ data }: { data: any }) {
  if (!data?.raw?.length) {
    return <p className="text-sm text-muted-foreground py-4">No data for this period.</p>;
  }

  const procedures = [...new Set(data.raw.map((r: any) => r.procedure))];
  const regions = [...new Set(data.raw.map((r: any) => r.region))];
  const maxCount = Math.max(...data.raw.map((r: any) => r.cnt));

  const lookup: Record<string, Record<string, number>> = {};
  for (const r of data.raw) {
    if (!lookup[r.procedure]) lookup[r.procedure] = {};
    lookup[r.procedure][r.region] = (lookup[r.procedure][r.region] ?? 0) + r.cnt;
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="text-xs w-40">Procedure</TableHead>
            {regions.slice(0, 8).map((r: any) => (
              <TableHead key={r} className="text-xs text-center">{r}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {procedures.map((proc: any) => (
            <TableRow key={proc}>
              <TableCell className="text-xs font-medium">{proc}</TableCell>
              {regions.slice(0, 8).map((reg: any) => {
                const cnt = lookup[proc]?.[reg] ?? 0;
                const intensity = cnt / maxCount;
                return (
                  <TableCell key={reg} className="text-center p-1">
                    {cnt > 0 ? (
                      <div
                        className="mx-auto rounded text-xs font-medium py-0.5 px-1"
                        style={{
                          backgroundColor: `rgba(239, 68, 68, ${intensity * 0.7 + 0.1})`,
                          color: intensity > 0.5 ? "white" : "#7f1d1d",
                          minWidth: "24px",
                        }}
                      >
                        {cnt}
                      </div>
                    ) : (
                      <span className="text-muted-foreground/30 text-xs">—</span>
                    )}
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function RiskIntelligencePage() {
  const { selectedClinic, isReady, canAdmin } = useClinicContext();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [period] = useState(90);

  const clinicId = selectedClinic?.clinic_id ?? "";

  const { data: scores, isLoading: scoresLoading } = useQuery({
    queryKey: ["risk-scores", clinicId],
    queryFn: () => api<any[]>(`/api/risk/scores?clinic_id=${clinicId}`),
    enabled: !!clinicId && canAdmin,
  });

  const { data: alerts, isLoading: alertsLoading } = useQuery({
    queryKey: ["risk-alerts", clinicId],
    queryFn: () => api<any[]>(`/api/risk/alerts?clinic_id=${clinicId}`),
    enabled: !!clinicId,
  });

  const { data: heatmap, isLoading: heatmapLoading } = useQuery({
    queryKey: ["risk-heatmap", clinicId, period],
    queryFn: () => api<any>(`/api/risk/heatmap?clinic_id=${clinicId}&period_days=${period}`),
    enabled: !!clinicId && canAdmin,
  });

  const computeMutation = useMutation({
    mutationFn: () =>
      api("/api/risk/scores/compute", {
        method: "POST",
        body: JSON.stringify({ clinic_id: clinicId, period_days: period }),
      }),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ["risk-scores"] });
      qc.invalidateQueries({ queryKey: ["risk-alerts"] });
      toast({
        title: `Risk scores computed`,
        description: `${data.practitioner_count} practitioners scored. ${data.alerts_triggered.length} new alerts.`,
      });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const detectMutation = useMutation({
    mutationFn: () =>
      api("/api/risk/detect-patterns", {
        method: "POST",
        body: JSON.stringify({ clinic_id: clinicId, window_days: 30 }),
      }),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ["risk-alerts"] });
      toast({
        title: `Pattern detection complete`,
        description: `${data.patterns_triggered} pattern(s) triggered.`,
      });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const dismissMutation = useMutation({
    mutationFn: (alertId: string) =>
      api(`/api/risk/alerts/${alertId}/dismiss`, {
        method: "POST",
        body: JSON.stringify({ clinic_id: clinicId }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["risk-alerts"] });
      toast({ title: "Alert dismissed" });
    },
  });

  const criticalAlerts = (alerts ?? []).filter((a) => a.severity === "critical");
  const otherAlerts = (alerts ?? []).filter((a) => a.severity !== "critical");

  if (!isReady) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Skeleton className="h-12 w-64" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-background/95 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Shield className="h-5 w-5 text-red-500 flex-shrink-0" />
            <div>
              <h1 className="font-semibold text-sm">Risk Intelligence</h1>
              <p className="text-xs text-muted-foreground hidden sm:block">
                Practitioner safety scoring · Pattern detection · Complication alerts
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ClinicSwitcher />
            {canAdmin && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => detectMutation.mutate()}
                  disabled={detectMutation.isPending}
                  className="hidden sm:flex"
                >
                  <Activity className="h-3.5 w-3.5 mr-1.5" />
                  {detectMutation.isPending ? "Detecting…" : "Detect Patterns"}
                </Button>
                <Button
                  size="sm"
                  onClick={() => computeMutation.mutate()}
                  disabled={computeMutation.isPending}
                >
                  <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${computeMutation.isPending ? "animate-spin" : ""}`} />
                  {computeMutation.isPending ? "Computing…" : "Compute Scores"}
                </Button>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {/* Critical alerts banner */}
        {criticalAlerts.length > 0 && (
          <Card className="border-red-400 dark:border-red-700 bg-red-50 dark:bg-red-950/20">
            <CardHeader className="pb-2 pt-3 px-4">
              <CardTitle className="text-sm text-red-700 dark:text-red-400 flex items-center gap-2">
                <XCircle className="h-4 w-4" />
                {criticalAlerts.length} Critical Alert{criticalAlerts.length > 1 ? "s" : ""} — Immediate Review Required
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-3 space-y-2">
              {criticalAlerts.map((a) => (
                <AlertCard key={a.id} alert={a} onDismiss={(id) => dismissMutation.mutate(id)} />
              ))}
            </CardContent>
          </Card>
        )}

        <Tabs defaultValue="scores">
          <TabsList className="mb-4">
            <TabsTrigger value="scores" className="text-xs gap-1.5">
              <BarChart3 className="h-3.5 w-3.5" /> Practitioner Scores
              {scores?.length ? (
                <Badge variant="secondary" className="text-xs ml-1">{scores.length}</Badge>
              ) : null}
            </TabsTrigger>
            <TabsTrigger value="alerts" className="text-xs gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5" /> Alerts
              {(alerts ?? []).length > 0 && (
                <Badge variant="destructive" className="text-xs ml-1">{alerts!.length}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="heatmap" className="text-xs gap-1.5">
              <MapPin className="h-3.5 w-3.5" /> Complication Heatmap
            </TabsTrigger>
          </TabsList>

          {/* SCORES TAB */}
          <TabsContent value="scores">
            {!canAdmin ? (
              <div className="py-12 text-center text-sm text-muted-foreground">
                Admin role required to view practitioner risk scores.
              </div>
            ) : scoresLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-24 w-full" />)}
              </div>
            ) : !scores?.length ? (
              <div className="py-16 text-center">
                <BarChart3 className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
                <p className="text-sm font-medium text-muted-foreground">No scores computed yet</p>
                <p className="text-xs text-muted-foreground/60 mt-1">Click "Compute Scores" to analyse case logs.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {/* Summary */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {(["critical", "high", "elevated", "normal"] as const).map((level) => {
                    const count = scores.filter((s) => s.risk_level === level).length;
                    const s = RISK_STYLES[level];
                    const Icon = s.icon;
                    return (
                      <Card key={level} className={count > 0 && level !== "normal" ? s.bg : ""}>
                        <CardContent className="p-3 flex items-center gap-2">
                          <Icon className={`h-4 w-4 flex-shrink-0 ${
                            level === "critical" ? "text-red-500" :
                            level === "high" ? "text-orange-500" :
                            level === "elevated" ? "text-amber-500" : "text-emerald-500"
                          }`} />
                          <div>
                            <p className="text-lg font-semibold">{count}</p>
                            <p className="text-xs capitalize text-muted-foreground">{level}</p>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
                {scores.map((score) => (
                  <PractitionerCard key={score.practitioner_name} score={score} />
                ))}
              </div>
            )}
          </TabsContent>

          {/* ALERTS TAB */}
          <TabsContent value="alerts">
            {alertsLoading ? (
              <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} className="h-20 w-full" />)}</div>
            ) : !alerts?.length ? (
              <div className="py-16 text-center">
                <CheckCircle2 className="h-12 w-12 text-emerald-500/40 mx-auto mb-4" />
                <p className="text-sm font-medium text-muted-foreground">No active alerts</p>
                <p className="text-xs text-muted-foreground/60 mt-1">Run pattern detection to check for cluster events.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {[...criticalAlerts, ...otherAlerts].map((alert) => (
                  <AlertCard key={alert.id} alert={alert} onDismiss={(id) => dismissMutation.mutate(id)} />
                ))}
              </div>
            )}
          </TabsContent>

          {/* HEATMAP TAB */}
          <TabsContent value="heatmap">
            {!canAdmin ? (
              <div className="py-12 text-center text-sm text-muted-foreground">Admin role required.</div>
            ) : (
              <Card>
                <CardHeader className="pb-2 pt-3 px-4">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <MapPin className="h-4 w-4 text-red-500" />
                    Complication Frequency — Procedure × Region
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Darker = higher complication count. Last {period} days.
                  </CardDescription>
                </CardHeader>
                <CardContent className="px-4 pb-4">
                  {heatmapLoading ? (
                    <Skeleton className="h-48 w-full" />
                  ) : (
                    <HeatmapTable data={heatmap} />
                  )}
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
