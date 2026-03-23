import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Building2, BarChart3, TrendingUp, TrendingDown, Activity,
  Cpu, CheckCircle2, AlertCircle, Eye, Copy, Printer, Bookmark,
  Network,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useClinicContext } from "@/hooks/use-clinic-context";
import { ClinicSwitcher } from "@/components/clinic-switcher";
import { getToken } from "@/lib/auth";

// ---------------------------------------------------------------------------
// API
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
// Org Overview tab (Pigment-inspired)
// ---------------------------------------------------------------------------

function OrgOverviewTab({ orgId }: { orgId: string }) {
  const [period, setPeriod] = useState(30);

  const { data, isLoading } = useQuery({
    queryKey: ["org-overview", orgId, period],
    queryFn: () => api<any>(`/api/analytics/org-overview/${orgId}?period_days=${period}`),
    enabled: !!orgId,
  });

  const maxCases = Math.max(...(data?.clinics ?? []).map((c: any) => c.case_logs), 1);

  return (
    <div className="space-y-5">
      {/* Period selector */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Period:</span>
        {[7, 30, 90].map((d) => (
          <Button
            key={d}
            size="sm"
            variant={period === d ? "default" : "outline"}
            className="h-7 px-3 text-xs"
            onClick={() => setPeriod(d)}
          >
            {d}d
          </Button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-3">{[1,2,3].map(i => <Skeleton key={i} className="h-24 w-full" />)}</div>
      ) : !data ? null : (
        <>
          {/* Network summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: "Total Case Logs", value: data.network_summary.total_case_logs, icon: Activity },
              { label: "Active Alerts", value: data.network_summary.total_active_alerts, icon: AlertCircle },
              { label: "Clinics", value: data.clinic_count, icon: Building2 },
              {
                label: "Avg Cases / Clinic",
                value: data.network_summary.avg_case_logs_per_clinic,
                icon: BarChart3
              },
            ].map(({ label, value, icon: Icon }) => (
              <Card key={label}>
                <CardContent className="p-4 flex items-start justify-between">
                  <div>
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="text-2xl font-semibold mt-1">{value ?? 0}</p>
                  </div>
                  <Icon className="h-5 w-5 text-muted-foreground" />
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Per-clinic comparison */}
          <Card>
            <CardHeader className="pb-2 pt-3 px-4">
              <CardTitle className="text-sm flex items-center gap-2">
                <Building2 className="h-4 w-4" /> Clinic Comparison
              </CardTitle>
              <CardDescription className="text-xs">
                Sorted by risk index (critical alerts × 5 + alerts × 2) / cases
              </CardDescription>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">Clinic</TableHead>
                    <TableHead className="text-xs text-right">Cases</TableHead>
                    <TableHead className="text-xs text-right">Alerts</TableHead>
                    <TableHead className="text-xs text-right">Critical</TableHead>
                    <TableHead className="text-xs text-right">Risk Index</TableHead>
                    <TableHead className="text-xs">Volume</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(data.clinics ?? []).map((c: any) => (
                    <TableRow key={c.clinic_id}>
                      <TableCell className="text-xs">
                        <div>
                          <p className="font-medium">{c.clinic_name}</p>
                          {c.location && <p className="text-muted-foreground">{c.location}</p>}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-right">{c.case_logs}</TableCell>
                      <TableCell className="text-xs text-right">
                        {c.active_alerts > 0 ? (
                          <Badge variant="outline" className="text-xs bg-amber-100 text-amber-700">{c.active_alerts}</Badge>
                        ) : "0"}
                      </TableCell>
                      <TableCell className="text-xs text-right">
                        {c.critical_alerts > 0 ? (
                          <Badge variant="destructive" className="text-xs">{c.critical_alerts}</Badge>
                        ) : "0"}
                      </TableCell>
                      <TableCell className="text-xs text-right font-medium">{c.risk_index}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className="h-2 bg-muted rounded-full flex-1 max-w-20">
                            <div
                              className="h-full bg-blue-500 rounded-full"
                              style={{ width: `${(c.case_logs / maxCases) * 100}%` }}
                            />
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Top network complications */}
          <Card>
            <CardHeader className="pb-2 pt-3 px-4">
              <CardTitle className="text-sm">Network-Wide Complications</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-3 space-y-2">
              {(data.network_summary.top_complications ?? []).map((c: any, i: number) => {
                const max = data.network_summary.top_complications[0]?.cnt ?? 1;
                return (
                  <div key={i}>
                    <div className="flex justify-between text-xs mb-0.5">
                      <span>{c.complication_type}</span>
                      <span className="text-muted-foreground">{c.cnt}</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div className="h-full bg-red-400 rounded-full" style={{ width: `${(c.cnt / max) * 100}%` }} />
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Session Heatmap tab (Contentsquare-inspired)
// ---------------------------------------------------------------------------

function SessionHeatmapTab({ clinicId }: { clinicId: string }) {
  const [period, setPeriod] = useState(30);

  const { data, isLoading } = useQuery({
    queryKey: ["session-heatmap", clinicId, period],
    queryFn: () => api<any>(`/api/analytics/session-heatmap?clinic_id=${clinicId}&period_days=${period}`),
    enabled: !!clinicId,
  });

  const EVENT_ICONS: Record<string, React.ElementType> = {
    copy: Copy,
    print: Printer,
    save: Bookmark,
    expand: Eye,
    view: Eye,
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Period:</span>
        {[7, 30, 90].map((d) => (
          <Button key={d} size="sm" variant={period === d ? "default" : "outline"} className="h-7 px-3 text-xs" onClick={() => setPeriod(d)}>
            {d}d
          </Button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-3">{[1,2,3].map(i => <Skeleton key={i} className="h-20 w-full" />)}</div>
      ) : !data ? null : (
        <>
          {/* Highest-value sections */}
          <Card>
            <CardHeader className="pb-2 pt-3 px-4">
              <CardTitle className="text-sm">Highest-Value Answer Sections</CardTitle>
              <CardDescription className="text-xs">
                Ranked by copy + print + save + expand interactions. Shows what clinicians actually use.
              </CardDescription>
            </CardHeader>
            <CardContent className="px-4 pb-3 space-y-2">
              {!data.highest_value_sections?.length ? (
                <p className="text-xs text-muted-foreground">No interaction data yet. Events are tracked as clinicians use answers.</p>
              ) : (
                data.highest_value_sections.map((s: any, i: number) => (
                  <div key={s.section} className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground w-4">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium truncate capitalize">{s.section.replace(/_/g, " ")}</p>
                    </div>
                    <Badge variant="secondary" className="text-xs flex-shrink-0">{s.value_score} pts</Badge>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          {/* Section heatmap */}
          {Object.keys(data.section_heatmap ?? {}).length > 0 && (
            <Card>
              <CardHeader className="pb-2 pt-3 px-4">
                <CardTitle className="text-sm">Section Interaction Matrix</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-3">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Section</TableHead>
                      {["view", "copy", "expand", "save", "print"].map((ev) => (
                        <TableHead key={ev} className="text-xs text-center capitalize">{ev}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Object.entries(data.section_heatmap).map(([section, events]: [string, any]) => (
                      <TableRow key={section}>
                        <TableCell className="text-xs capitalize">{section.replace(/_/g, " ")}</TableCell>
                        {["view", "copy", "expand", "save", "print"].map((ev) => (
                          <TableCell key={ev} className="text-center text-xs">
                            {events[ev] ? (
                              <span className={events[ev] > 5 ? "font-semibold text-blue-600" : "text-muted-foreground"}>
                                {events[ev]}
                              </span>
                            ) : <span className="text-muted-foreground/30">—</span>}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}

          {/* Top events */}
          <Card>
            <CardHeader className="pb-2 pt-3 px-4">
              <CardTitle className="text-sm">Top Clinician Events</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-3">
              <div className="space-y-2">
                {(data.top_events ?? []).map((e: any, i: number) => {
                  const Icon = EVENT_ICONS[e.event_type] ?? Activity;
                  const max = data.top_events[0]?.cnt ?? 1;
                  return (
                    <div key={i} className="flex items-center gap-3">
                      <Icon className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex justify-between text-xs mb-0.5">
                          <span className="capitalize">{e.event_type.replace(/_/g, " ")}</span>
                          <span className="text-muted-foreground">{e.cnt}</span>
                        </div>
                        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                          <div className="h-full bg-blue-500 rounded-full" style={{ width: `${(e.cnt / max) * 100}%` }} />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// LLM Provider config tab (Mistral-inspired)
// ---------------------------------------------------------------------------

const PROVIDERS_INFO: Record<string, { name: string; description: string; gdpr: boolean }> = {
  openai:       { name: "OpenAI", description: "GPT-4o · Best quality, default.", gdpr: false },
  mistral:      { name: "Mistral AI", description: "French infrastructure · GDPR-compliant · Strong multilingual.", gdpr: true },
  azure_openai: { name: "Azure OpenAI", description: "Enterprise Azure deployment · Your data stays in your region.", gdpr: true },
  local:        { name: "Local / On-Premise", description: "Fully air-gapped · No data leaves the clinic · Ollama or vLLM.", gdpr: true },
};

const PROVIDER_MODELS: Record<string, string[]> = {
  openai:       ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
  mistral:      ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest", "open-mistral-nemo"],
  azure_openai: ["gpt-4o", "gpt-4-turbo"],
  local:        ["mistral-7b-instruct", "llama-3-8b", "custom"],
};

function LLMProviderTab({ orgId }: { orgId: string }) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [form, setForm] = useState({
    provider: "openai",
    model: "gpt-4o",
    api_key: "",
    base_url: "",
    on_premise: false,
  });

  const { data: config, isLoading } = useQuery({
    queryKey: ["llm-config", orgId],
    queryFn: () => api<any>(`/api/llm/config/${orgId}`),
    enabled: !!orgId,
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      api(`/api/llm/config/${orgId}`, {
        method: "POST",
        body: JSON.stringify(form),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["llm-config"] });
      toast({ title: "LLM provider saved" });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const testMutation = useMutation({
    mutationFn: () =>
      api("/api/llm/test", {
        method: "POST",
        body: JSON.stringify({ org_id: orgId }),
      }),
    onSuccess: (data: any) => {
      toast({
        title: `✓ ${data.provider} — ${data.model}`,
        description: data.response,
      });
    },
    onError: (e: Error) => toast({ title: "Connection failed", description: e.message, variant: "destructive" }),
  });

  return (
    <div className="space-y-4 max-w-lg">
      <Card>
        <CardHeader className="pb-3 pt-3 px-4">
          <CardTitle className="text-sm flex items-center gap-2">
            <Cpu className="h-4 w-4" /> AI Model Provider
          </CardTitle>
          <CardDescription className="text-xs">
            Configure which LLM powers AesthetiCite for your organisation.
            GDPR-compliant options use European infrastructure.
          </CardDescription>
        </CardHeader>
        <CardContent className="px-4 pb-4 space-y-4">
          {isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : (
            <>
              {/* Current config badge */}
              {config?.configured && (
                <div className="flex items-center gap-2 p-2 bg-muted rounded-lg text-xs">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                  <span>Current: <strong>{config.provider}</strong> · {config.model}</span>
                  {config.on_premise && <Badge className="text-xs bg-emerald-100 text-emerald-700">On-Premise</Badge>}
                </div>
              )}

              {/* Provider selector */}
              <div>
                <Label className="text-xs">Provider</Label>
                <div className="grid grid-cols-1 gap-2 mt-1">
                  {Object.entries(PROVIDERS_INFO).map(([key, info]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => {
                        setForm((p) => ({
                          ...p,
                          provider: key,
                          model: PROVIDER_MODELS[key][0],
                          on_premise: key === "local",
                        }));
                      }}
                      className={`flex items-start gap-3 p-3 rounded-lg border text-left transition-colors ${
                        form.provider === key
                          ? "border-blue-500 bg-blue-50 dark:bg-blue-950/20"
                          : "border-border hover:border-muted-foreground"
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-xs font-medium">{info.name}</p>
                          {info.gdpr && (
                            <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-emerald-600 border-emerald-400">
                              GDPR ✓
                            </Badge>
                          )}
                        </div>
                        <p className="text-[11px] text-muted-foreground mt-0.5">{info.description}</p>
                      </div>
                      {form.provider === key && (
                        <CheckCircle2 className="h-4 w-4 text-blue-500 flex-shrink-0 mt-0.5" />
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {/* Model selector */}
              <div>
                <Label className="text-xs">Model</Label>
                <Select value={form.model} onValueChange={(v) => setForm((p) => ({ ...p, model: v }))}>
                  <SelectTrigger className="mt-1 h-8 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(PROVIDER_MODELS[form.provider] ?? []).map((m) => (
                      <SelectItem key={m} value={m} className="text-sm">{m}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* API key */}
              <div>
                <Label className="text-xs">API Key {config?.configured && "(leave blank to keep existing)"}</Label>
                <Input
                  className="mt-1 h-8 text-sm font-mono"
                  type="password"
                  placeholder={config?.configured ? "••••••••" : "sk-..."}
                  value={form.api_key}
                  onChange={(e) => setForm((p) => ({ ...p, api_key: e.target.value }))}
                />
              </div>

              {/* Base URL (for azure/local) */}
              {["azure_openai", "local", "mistral"].includes(form.provider) && (
                <div>
                  <Label className="text-xs">
                    Base URL
                    {form.provider === "local" ? " (e.g. http://localhost:11434/v1)" :
                     form.provider === "mistral" ? " (default: https://api.mistral.ai/v1)" : ""}
                  </Label>
                  <Input
                    className="mt-1 h-8 text-sm font-mono"
                    placeholder={
                      form.provider === "local" ? "http://localhost:11434/v1" :
                      form.provider === "mistral" ? "https://api.mistral.ai/v1" :
                      "https://your-resource.openai.azure.com/"
                    }
                    value={form.base_url}
                    onChange={(e) => setForm((p) => ({ ...p, base_url: e.target.value }))}
                  />
                </div>
              )}

              <div className="flex gap-2">
                <Button size="sm" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
                  {saveMutation.isPending ? "Saving…" : "Save Config"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => testMutation.mutate()}
                  disabled={testMutation.isPending}
                >
                  {testMutation.isPending ? "Testing…" : "Test Connection"}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function OrgAnalyticsPage() {
  const { selectedClinic, isReady } = useClinicContext();

  const orgId = selectedClinic?.org_id ?? "";
  const clinicId = selectedClinic?.clinic_id ?? "";

  if (!isReady) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Skeleton className="h-12 w-64" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="border-b bg-background/95 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Network className="h-5 w-5 text-violet-500 flex-shrink-0" />
            <div>
              <h1 className="font-semibold text-sm">Organisation Analytics</h1>
              <p className="text-xs text-muted-foreground hidden sm:block">
                Cross-clinic benchmarks · Session intelligence · AI provider config
              </p>
            </div>
          </div>
          <ClinicSwitcher />
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-6">
        <Tabs defaultValue="org">
          <TabsList className="mb-6">
            <TabsTrigger value="org" className="text-xs gap-1.5">
              <Building2 className="h-3.5 w-3.5" /> Network Overview
            </TabsTrigger>
            <TabsTrigger value="heatmap" className="text-xs gap-1.5">
              <Eye className="h-3.5 w-3.5" /> Session Heatmap
            </TabsTrigger>
            <TabsTrigger value="llm" className="text-xs gap-1.5">
              <Cpu className="h-3.5 w-3.5" /> AI Provider
            </TabsTrigger>
          </TabsList>

          <TabsContent value="org">
            <OrgOverviewTab orgId={orgId} />
          </TabsContent>

          <TabsContent value="heatmap">
            <SessionHeatmapTab clinicId={clinicId} />
          </TabsContent>

          <TabsContent value="llm">
            <LLMProviderTab orgId={orgId} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
