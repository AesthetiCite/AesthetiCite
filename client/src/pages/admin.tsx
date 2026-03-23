import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, AlertCircle, Users, Search, Clock, DollarSign, Shield, TrendingUp } from "lucide-react";

interface TimeWindow {
  fromISO: string;
  toISO: string;
}

interface ConnectionMetrics {
  active_last_5m: number;
  active_last_60m: number;
  unique_ip_last_24h: number;
  unique_users_last_24h: number;
}

interface UsageMetrics {
  queries_last_24h: number;
  queries_last_7d: number;
  tool_calls_last_24h: number;
  refusals_last_24h: number;
  refusal_rate_last_24h: number;
  errors_last_24h: number;
  error_rate_last_24h: number;
}

interface PerformanceMetrics {
  latency_ms_p50_last_24h: number;
  latency_ms_p95_last_24h: number;
  retrieval_ms_p50_last_24h: number;
  retrieval_ms_p95_last_24h: number;
  llm_ms_p50_last_24h: number;
  llm_ms_p95_last_24h: number;
}

interface CostMetrics {
  llm_usd_last_24h: number;
  llm_usd_last_7d: number;
}

interface QueryCount {
  query: string;
  count: number;
}

interface ReasonCount {
  reason: string;
  count: number;
}

interface ToolCount {
  tool: string;
  count: number;
}

interface ContentMetrics {
  top_queries_last_24h: QueryCount[];
  top_refusal_reasons_last_7d: ReasonCount[];
  top_tools_last_7d: ToolCount[];
}

interface SafetyMetrics {
  citation_mismatch_last_24h: number;
  citation_mismatch_rate_last_24h: number;
  dosing_requests_last_24h: number;
  interaction_checks_last_24h: number;
}

interface AdminMetrics {
  window: TimeWindow;
  connections: ConnectionMetrics;
  usage: UsageMetrics;
  performance: PerformanceMetrics;
  cost: CostMetrics;
  content: ContentMetrics;
  safety: SafetyMetrics;
}

function KPI({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-1">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="text-sm font-semibold">{value}</div>
    </div>
  );
}

function pct(x: number): string {
  return `${Math.round(x * 1000) / 10}%`;
}

export default function AdminPage() {
  const { data, isLoading, error } = useQuery<AdminMetrics>({
    queryKey: ["/admin/metrics"],
    queryFn: async () => {
      const adminKey = localStorage.getItem("aestheticite-admin-key");
      if (!adminKey) {
        throw new Error("Admin API key not configured. Set it in localStorage as 'aestheticite-admin-key'.");
      }
      const res = await fetch("/api/admin/metrics", {
        headers: {
          "x-admin-api-key": adminKey,
        },
      });
      if (!res.ok) {
        throw new Error(`Failed to load metrics: ${res.status}`);
      }
      return res.json();
    },
    refetchInterval: 30000,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-background p-6">
        <div className="mx-auto max-w-6xl">
          <h1 className="text-2xl font-semibold">AesthetiCite Admin</h1>
          <div className="mt-4 p-4 rounded-lg bg-destructive/10 text-destructive flex items-center gap-2">
            <AlertCircle className="h-5 w-5" />
            <span>{error instanceof Error ? error.message : "Failed to load metrics"}</span>
          </div>
          <p className="mt-4 text-sm text-muted-foreground">
            To access admin metrics, set your admin API key in localStorage:
            <code className="ml-2 px-2 py-1 bg-muted rounded text-xs">
              localStorage.setItem("aestheticite-admin-key", "your-key")
            </code>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-6xl">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold" data-testid="text-admin-title">AesthetiCite Admin</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Window: {new Date(data.window.fromISO).toLocaleString()} → {new Date(data.window.toISO).toLocaleString()}
            </p>
          </div>
          <Badge variant="outline" className="text-xs">
            Auto-refresh: 30s
          </Badge>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Connections</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <KPI label="Active (last 5m)" value={data.connections.active_last_5m} />
              <KPI label="Active (last 60m)" value={data.connections.active_last_60m} />
              <KPI label="Unique IPs (24h)" value={data.connections.unique_ip_last_24h} />
              <KPI label="Unique users (24h)" value={data.connections.unique_users_last_24h} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Usage (24h)</CardTitle>
              <Search className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <KPI label="Queries" value={data.usage.queries_last_24h} />
              <KPI label="Tool calls" value={data.usage.tool_calls_last_24h} />
              <KPI label="Refusals" value={`${data.usage.refusals_last_24h} (${pct(data.usage.refusal_rate_last_24h)})`} />
              <KPI label="Errors" value={`${data.usage.errors_last_24h} (${pct(data.usage.error_rate_last_24h)})`} />
              <div className="mt-2 text-xs text-muted-foreground">
                Queries (7d): <span className="font-semibold">{data.usage.queries_last_7d}</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Performance (24h)</CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <KPI label="Latency p50" value={`${data.performance.latency_ms_p50_last_24h} ms`} />
              <KPI label="Latency p95" value={`${data.performance.latency_ms_p95_last_24h} ms`} />
              <KPI label="Retrieval p50" value={`${data.performance.retrieval_ms_p50_last_24h} ms`} />
              <KPI label="Retrieval p95" value={`${data.performance.retrieval_ms_p95_last_24h} ms`} />
              <KPI label="LLM p50" value={`${data.performance.llm_ms_p50_last_24h} ms`} />
              <KPI label="LLM p95" value={`${data.performance.llm_ms_p95_last_24h} ms`} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Cost (LLM)</CardTitle>
              <DollarSign className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <KPI label="Last 24h" value={`$${data.cost.llm_usd_last_24h.toFixed(2)}`} />
              <KPI label="Last 7d" value={`$${data.cost.llm_usd_last_7d.toFixed(2)}`} />
              <div className="mt-2 text-xs text-muted-foreground">
                Token usage tracking for accurate cost reporting.
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Safety (24h)</CardTitle>
              <Shield className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <KPI label="Citation mismatches" value={`${data.safety.citation_mismatch_last_24h} (${pct(data.safety.citation_mismatch_rate_last_24h)})`} />
              <KPI label="Dosing requests" value={data.safety.dosing_requests_last_24h} />
              <KPI label="Interaction checks" value={data.safety.interaction_checks_last_24h} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Top Queries (24h)</CardTitle>
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {data.content.top_queries_last_24h.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No queries yet</p>
                ) : (
                  data.content.top_queries_last_24h.slice(0, 8).map((q, i) => (
                    <div key={i} className="rounded-lg bg-muted p-2">
                      <div className="text-xs text-muted-foreground">{q.count}x</div>
                      <div className="text-sm truncate">{q.query}</div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Top Refusal Reasons (7d)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {data.content.top_refusal_reasons_last_7d.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No refusals</p>
                ) : (
                  data.content.top_refusal_reasons_last_7d.slice(0, 8).map((r, i) => (
                    <div key={i} className="flex items-center justify-between rounded-lg bg-muted p-2">
                      <div className="text-sm">{r.reason}</div>
                      <div className="text-sm font-semibold">{r.count}</div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Top Tools (7d)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {data.content.top_tools_last_7d.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No tool usage</p>
                ) : (
                  data.content.top_tools_last_7d.slice(0, 10).map((t, i) => (
                    <div key={i} className="flex items-center justify-between rounded-lg bg-muted p-2">
                      <div className="text-sm">{t.tool}</div>
                      <div className="text-sm font-semibold">{t.count}</div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        <Card className="mt-6">
          <CardContent className="pt-4">
            <div className="text-sm font-semibold">Security Notes</div>
            <ul className="mt-2 list-disc pl-5 text-xs text-muted-foreground space-y-1">
              <li>Admin access requires ADMIN_API_KEY authentication.</li>
              <li>Metrics are refreshed every 30 seconds automatically.</li>
              <li>All data is aggregated from the last 24h/7d windows.</li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
