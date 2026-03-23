import { useState, useEffect } from "react";
import { useLocation } from "wouter";
import {
  ArrowLeft, BarChart3, Activity, Clock, BookOpen,
  TrendingUp, Users, Shield, Loader2, RefreshCw,
  AlertTriangle, CheckCircle2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getToken } from "@/lib/auth";

interface DashboardData {
  total_queries: number;
  average_aci_score: number | null;
  average_response_time_ms: number | null;
  top_questions: { query: string; count: number }[];
  evidence_level_distribution: Record<string, number>;
  answer_type_distribution: Record<string, number>;
}

function StatCard({
  icon: Icon, label, value, sub, accent = "default"
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  sub?: string;
  accent?: "emerald" | "amber" | "blue" | "default";
}) {
  const accentMap = {
    emerald: "border-emerald-500/20 bg-emerald-500/5",
    amber:   "border-amber-500/20 bg-amber-500/5",
    blue:    "border-blue-500/20 bg-blue-500/5",
    default: "border-border bg-background",
  };
  const iconMap = {
    emerald: "text-emerald-500",
    amber:   "text-amber-500",
    blue:    "text-blue-500",
    default: "text-primary",
  };
  return (
    <Card className={`border ${accentMap[accent]}`}>
      <CardContent className="p-5 flex items-start gap-4">
        <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ${accentMap[accent]}`}>
          <Icon className={`w-4 h-4 ${iconMap[accent]}`} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold mb-1">{label}</p>
          <p className="text-2xl font-bold tabular-nums">{value}</p>
          {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

export default function ClinicDashboardPage() {
  const [, setLocation] = useLocation();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [clinicId, setClinicId] = useState<string>(() =>
    localStorage.getItem("aestheticite_clinic_id") || "default"
  );

  async function fetchDashboard() {
    setLoading(true);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(`/api/growth/dashboard/${clinicId}`, {
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d?.detail || "Failed to load dashboard");
      setData(d);
    } catch (err: any) {
      setError(err.message || "Dashboard unavailable");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchDashboard(); }, [clinicId]);

  const aciPct = data?.average_aci_score != null
    ? Math.round(data.average_aci_score * 10)
    : null;

  const aciAccent = aciPct == null ? "default"
    : aciPct >= 70 ? "emerald"
    : aciPct >= 45 ? "amber"
    : "default";

  const totalEvidence = Object.values(data?.evidence_level_distribution || {})
    .reduce((a, b) => a + b, 0);

  return (
    <div className="min-h-screen bg-background">
      <div className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => setLocation("/")} className="gap-2 -ml-2">
              <ArrowLeft className="w-4 h-4" />
              <span className="hidden sm:inline">Back</span>
            </Button>
            <div className="w-px h-5 bg-border" />
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
                <BarChart3 className="w-4 h-4 text-primary" />
              </div>
              <span className="font-semibold text-sm">Clinic Dashboard</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={clinicId}
              onChange={(e) => setClinicId(e.target.value)}
              placeholder="Clinic ID"
              data-testid="input-clinic-id"
              className="rounded-md border border-border bg-background px-3 py-1.5 text-xs w-28 focus:outline-none focus:ring-1 focus:ring-primary/40"
              onBlur={() => {
                localStorage.setItem("aestheticite_clinic_id", clinicId);
                fetchDashboard();
              }}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={fetchDashboard}
              disabled={loading}
              className="gap-1.5"
              data-testid="button-refresh-dashboard"
            >
              {loading
                ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                : <RefreshCw className="w-3.5 h-3.5" />}
              Refresh
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-6">

        {error && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-sm text-destructive">
            <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            {error} — Ensure your Clinic ID is set and queries have been logged.
          </div>
        )}

        {loading && !data && (
          <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
            <Loader2 className="w-5 h-5 animate-spin" />
            Loading dashboard…
          </div>
        )}

        {data && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <StatCard
                icon={Activity}
                label="Total Queries"
                value={data.total_queries.toLocaleString()}
                sub="All time"
                accent="blue"
              />
              <StatCard
                icon={Shield}
                label="Avg ACI Score"
                value={data.average_aci_score != null
                  ? `${data.average_aci_score.toFixed(1)} / 10` : "—"}
                sub="Evidence confidence"
                accent={aciAccent}
              />
              <StatCard
                icon={Clock}
                label="Avg Response"
                value={data.average_response_time_ms != null
                  ? `${(data.average_response_time_ms / 1000).toFixed(1)}s` : "—"}
                sub="Per query"
              />
              <StatCard
                icon={BookOpen}
                label="Evidence Refs"
                value={totalEvidence.toLocaleString()}
                sub="Citations retrieved"
                accent="emerald"
              />
            </div>

            {data.top_questions.length > 0 && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-primary" />
                    Top Clinical Questions
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-4 pt-0 space-y-2">
                  {data.top_questions.slice(0, 8).map((item, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-muted/40 transition-colors"
                      data-testid={`question-item-${i}`}
                    >
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center">
                        {i + 1}
                      </span>
                      <span className="flex-1 text-sm text-foreground/85 line-clamp-1">{item.query}</span>
                      <span className="flex-shrink-0 text-xs font-semibold text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                        {item.count}×
                      </span>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

              {Object.keys(data.evidence_level_distribution).length > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <BookOpen className="w-4 h-4 text-primary" />
                      Evidence Level Distribution
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-4 pt-0 space-y-2">
                    {Object.entries(data.evidence_level_distribution)
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([level, count]) => {
                        const pct = totalEvidence > 0 ? Math.round((count / totalEvidence) * 100) : 0;
                        const color = level === "I" ? "#22c55e"
                          : level === "II" ? "#3b82f6"
                          : level === "III" ? "#f59e0b"
                          : "#ef4444";
                        return (
                          <div key={level} className="space-y-1">
                            <div className="flex items-center justify-between text-xs">
                              <span className="font-medium">Level {level}</span>
                              <span className="text-muted-foreground">{count} ({pct}%)</span>
                            </div>
                            <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                              <div
                                className="h-full rounded-full transition-all duration-700"
                                style={{ width: `${pct}%`, backgroundColor: color }}
                              />
                            </div>
                          </div>
                        );
                      })}
                  </CardContent>
                </Card>
              )}

              {Object.keys(data.answer_type_distribution).length > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Users className="w-4 h-4 text-primary" />
                      Answer Type Distribution
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-4 pt-0 space-y-2">
                    {Object.entries(data.answer_type_distribution)
                      .sort(([, a], [, b]) => b - a)
                      .map(([type, count]) => {
                        const total = Object.values(data.answer_type_distribution).reduce((a, b) => a + b, 0);
                        const pct = total > 0 ? Math.round((count / total) * 100) : 0;
                        return (
                          <div key={type} className="space-y-1">
                            <div className="flex items-center justify-between text-xs">
                              <span className="font-medium capitalize">{type.replace(/_/g, " ")}</span>
                              <span className="text-muted-foreground">{count} ({pct}%)</span>
                            </div>
                            <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                              <div
                                className="h-full rounded-full bg-primary/60 transition-all duration-700"
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                  </CardContent>
                </Card>
              )}
            </div>

            {data.average_aci_score != null && (
              <div className={`flex items-start gap-3 p-4 rounded-xl border ${
                aciAccent === "emerald"
                  ? "border-emerald-500/30 bg-emerald-500/5"
                  : aciAccent === "amber"
                  ? "border-amber-500/30 bg-amber-500/5"
                  : "border-border bg-muted/20"
              }`}>
                <CheckCircle2 className={`w-4 h-4 mt-0.5 flex-shrink-0 ${
                  aciAccent === "emerald" ? "text-emerald-500"
                  : aciAccent === "amber" ? "text-amber-500"
                  : "text-muted-foreground"
                }`} />
                <div className="text-sm">
                  <span className="font-semibold">Evidence quality: </span>
                  <span className="text-muted-foreground">
                    Average ACI score of {data.average_aci_score.toFixed(1)}/10 indicates{" "}
                    {aciAccent === "emerald"
                      ? "strong evidence grounding across clinic queries."
                      : aciAccent === "amber"
                      ? "moderate evidence quality — some queries may benefit from more specific phrasing."
                      : "evidence quality that could improve with more targeted clinical questions."}
                  </span>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
