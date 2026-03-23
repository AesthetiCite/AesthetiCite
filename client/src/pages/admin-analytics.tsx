import { useState, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { ThemeToggle } from "@/components/theme-toggle";
import { getToken } from "@/lib/auth";
import { useLocation, Link } from "wouter";
import {
  BarChart3, Shield, Activity, AlertTriangle, Globe,
  ArrowLeft, RefreshCw, Loader2, TrendingUp, CheckCircle,
  XCircle, Clock, Brain
} from "lucide-react";

interface GovernanceSummary {
  total_queries: number;
  avg_aci: number | null;
  avg_citation_density: number | null;
  low_density_pct: number;
  citation_fail_pct: number;
  intent_distribution: Record<string, number>;
  lang_distribution: Record<string, number>;
}

interface GovernanceLog {
  timestamp: number;
  question_hash: string;
  question_preview: string;
  source_ids: string[];
  source_count: number;
  aci_score: number | null;
  citation_density: number;
  citation_valid: boolean;
  lang: string;
  intent: string;
  total_ms: number;
  evidence_badge: string | null;
  gaps: string[];
}

const ADMIN_KEY_STORAGE = "aestheticite_admin_key";

function getAdminKey(): string {
  return localStorage.getItem(ADMIN_KEY_STORAGE) || "";
}

function MetricCard({ label, value, sub, icon: Icon, color }: {
  label: string; value: string | number; sub?: string;
  icon: typeof Activity; color?: string;
}) {
  return (
    <Card className="p-4" data-testid={`metric-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs text-muted-foreground font-medium">{label}</p>
          <p className={`text-2xl font-bold mt-1 ${color || ""}`}>{value}</p>
          {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
        </div>
        <div className="w-8 h-8 rounded-md bg-muted flex items-center justify-center flex-shrink-0">
          <Icon className="w-4 h-4 text-muted-foreground" />
        </div>
      </div>
    </Card>
  );
}

function BarRow({ label, value, max, color }: { label: string; value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="text-xs text-muted-foreground w-24 flex-shrink-0 truncate">{label}</span>
      <div className="flex-1">
        <Progress value={pct} className="h-2" />
      </div>
      <span className={`text-xs font-medium w-10 text-right ${color || ""}`}>{value}</span>
    </div>
  );
}

export default function AdminAnalyticsPage() {
  const [, setLocation] = useLocation();
  const [summary, setSummary] = useState<GovernanceSummary | null>(null);
  const [logs, setLogs] = useState<GovernanceLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [needsKey, setNeedsKey] = useState(false);
  const [keyInput, setKeyInput] = useState("");

  async function fetchData(key?: string) {
    setLoading(true);
    setError(null);
    setNeedsKey(false);
    const adminKey = key || getAdminKey();
    try {
      const res = await fetch(`/api/admin/governance-logs?limit=200&offset=0`, {
        headers: { "x-admin-key": adminKey },
      });
      if (res.status === 401 || res.status === 403) {
        setNeedsKey(true);
        setLoading(false);
        return;
      }
      if (!res.ok) throw new Error("Failed to fetch governance data");
      const data = await res.json();
      setSummary(data.summary || null);
      setLogs(data.logs || []);
      if (key) localStorage.setItem(ADMIN_KEY_STORAGE, key);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  function handleKeySubmit() {
    if (keyInput.trim()) fetchData(keyInput.trim());
  }

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLocation("/login");
      return;
    }
    fetchData();
  }, [setLocation]);

  const intentMax = summary ? Math.max(...Object.values(summary.intent_distribution || {}), 1) : 1;
  const langMax = summary ? Math.max(...Object.values(summary.lang_distribution || {}), 1) : 1;

  const recentLogs = logs.slice(0, 20);

  const avgLatency = logs.length > 0 ? Math.round(logs.reduce((s, l) => s + l.total_ms, 0) / logs.length) : 0;
  const avgSources = logs.length > 0 ? (logs.reduce((s, l) => s + l.source_count, 0) / logs.length).toFixed(1) : "0";

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-50 border-b bg-background/90 backdrop-blur">
        <div className="container mx-auto flex h-14 items-center justify-between gap-4 px-4">
          <div className="flex items-center gap-3">
            <Link href="/">
              <Button variant="ghost" size="icon" data-testid="button-back">
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </Link>
            <div className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-primary" />
              <span className="font-semibold">Governance Analytics</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => fetchData()} disabled={loading} data-testid="button-refresh">
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6 max-w-6xl">
        {loading && !summary ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : needsKey ? (
          <Card className="p-8 max-w-md mx-auto" data-testid="card-admin-key">
            <div className="flex items-center gap-2 mb-4">
              <Shield className="w-5 h-5 text-muted-foreground" />
              <h3 className="text-sm font-semibold">Admin Access Required</h3>
            </div>
            <p className="text-sm text-muted-foreground mb-4">Enter your admin API key to view governance analytics.</p>
            <div className="flex gap-2">
              <input
                type="password"
                value={keyInput}
                onChange={(e) => setKeyInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleKeySubmit()}
                placeholder="Admin API Key"
                className="flex-1 rounded-md border bg-background px-3 py-2 text-sm"
                data-testid="input-admin-key"
              />
              <Button size="sm" onClick={handleKeySubmit} data-testid="button-submit-key">
                Unlock
              </Button>
            </div>
          </Card>
        ) : error ? (
          <Card className="p-8 text-center">
            <AlertTriangle className="w-8 h-8 mx-auto text-muted-foreground mb-3" />
            <p className="text-sm text-muted-foreground">{error}</p>
            <Button variant="outline" size="sm" className="mt-4" onClick={() => fetchData()} data-testid="button-retry">
              Retry
            </Button>
          </Card>
        ) : summary ? (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="metrics-grid">
              <MetricCard label="Total Queries" value={summary.total_queries} icon={Activity} />
              <MetricCard
                label="Avg ACI Score"
                value={summary.avg_aci !== null ? `${summary.avg_aci}/10` : "N/A"}
                icon={Shield}
                color={summary.avg_aci !== null && summary.avg_aci >= 7 ? "text-emerald-600 dark:text-emerald-400" : summary.avg_aci !== null && summary.avg_aci >= 4 ? "text-amber-600 dark:text-amber-400" : ""}
              />
              <MetricCard
                label="Citation Density"
                value={summary.avg_citation_density !== null ? `${Math.round(summary.avg_citation_density * 100)}%` : "N/A"}
                sub={`${summary.low_density_pct}% below 50%`}
                icon={CheckCircle}
              />
              <MetricCard
                label="Citation Failures"
                value={`${summary.citation_fail_pct}%`}
                sub="Answers replaced with refusal"
                icon={XCircle}
                color={summary.citation_fail_pct > 10 ? "text-red-600 dark:text-red-400" : ""}
              />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MetricCard label="Avg Latency" value={`${avgLatency}ms`} icon={Clock} />
              <MetricCard label="Avg Sources" value={avgSources} sub="per answer" icon={Brain} />
              <MetricCard label="Languages Used" value={Object.keys(summary.lang_distribution || {}).length} icon={Globe} />
              <MetricCard label="Intent Types" value={Object.keys(summary.intent_distribution || {}).length} icon={TrendingUp} />
            </div>

            <div className="grid md:grid-cols-2 gap-6">
              <Card className="p-5" data-testid="card-intent-distribution">
                <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
                  <Brain className="w-4 h-4 text-muted-foreground" />
                  Intent Distribution
                </h3>
                <div className="space-y-1">
                  {Object.entries(summary.intent_distribution || {})
                    .sort(([, a], [, b]) => b - a)
                    .map(([intent, count]) => (
                      <BarRow key={intent} label={intent} value={count} max={intentMax} />
                    ))}
                  {Object.keys(summary.intent_distribution || {}).length === 0 && (
                    <p className="text-xs text-muted-foreground py-4 text-center">No data yet</p>
                  )}
                </div>
              </Card>

              <Card className="p-5" data-testid="card-language-distribution">
                <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
                  <Globe className="w-4 h-4 text-muted-foreground" />
                  Language Distribution
                </h3>
                <div className="space-y-1">
                  {Object.entries(summary.lang_distribution || {})
                    .sort(([, a], [, b]) => b - a)
                    .map(([lang, count]) => (
                      <BarRow key={lang} label={lang.toUpperCase()} value={count} max={langMax} />
                    ))}
                  {Object.keys(summary.lang_distribution || {}).length === 0 && (
                    <p className="text-xs text-muted-foreground py-4 text-center">No data yet</p>
                  )}
                </div>
              </Card>
            </div>

            <Card className="p-5" data-testid="card-recent-queries">
              <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
                <Activity className="w-4 h-4 text-muted-foreground" />
                Recent Queries ({logs.length} total)
              </h3>
              <ScrollArea className="max-h-[400px]">
                <div className="space-y-2">
                  {recentLogs.map((log, i) => (
                    <div key={`${log.question_hash}-${i}`} className="flex items-start gap-3 p-3 rounded-lg border text-sm" data-testid={`log-entry-${i}`}>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium truncate">{log.question_preview}</p>
                        <div className="flex flex-wrap items-center gap-1.5 mt-1">
                          <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">{log.intent}</Badge>
                          <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">{log.lang.toUpperCase()}</Badge>
                          {log.evidence_badge && (
                            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">{log.evidence_badge}</Badge>
                          )}
                          {!log.citation_valid && (
                            <Badge variant="destructive" className="text-[10px] px-1.5 py-0 h-4">REFUSED</Badge>
                          )}
                          {log.gaps.length > 0 && (
                            <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4">{log.gaps.length} gap{log.gaps.length > 1 ? "s" : ""}</Badge>
                          )}
                        </div>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <p className="text-xs font-medium">
                          {log.aci_score !== null ? `${log.aci_score}/10` : "-"}
                        </p>
                        <p className="text-[10px] text-muted-foreground">{log.source_count} sources</p>
                        <p className="text-[10px] text-muted-foreground">{log.total_ms}ms</p>
                      </div>
                    </div>
                  ))}
                  {recentLogs.length === 0 && (
                    <p className="text-xs text-muted-foreground py-8 text-center">No queries logged yet. Start searching to see analytics here.</p>
                  )}
                </div>
              </ScrollArea>
            </Card>
          </div>
        ) : (
          <Card className="p-8 text-center">
            <p className="text-sm text-muted-foreground">No governance data available</p>
          </Card>
        )}
      </main>
    </div>
  );
}
