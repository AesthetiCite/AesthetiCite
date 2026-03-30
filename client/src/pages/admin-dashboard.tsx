import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "wouter";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import {
  Users, Search, FileText, Shield, Activity, Database,
  Clock, TrendingUp, AlertCircle, CheckCircle2, Server,
  ChevronRight, RefreshCw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getToken, getMe } from "@/lib/auth";

const SUPER_ADMIN_EMAIL = "support@aestheticite.com";

function authHeader(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function adminFetch(path: string) {
  const res = await fetch(path, { headers: authHeader() });
  if (res.status === 403) throw new Error("Unauthorized");
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface OverviewData {
  totalUsers: number;
  activeUsers24h: number;
  activeUsers7d: number;
  totalQueries: number;
  totalAnswers: number;
  totalCaseLogs: number;
  totalSafetyReports: number;
  avgQueriesPerUser: number;
  avgResponseTimeMs: number | null;
  topComplications: { name: string; count: number }[];
  topProtocols: { name: string; count: number }[];
  recentActivity: {
    type: string;
    label: string;
    email: string | null;
    createdAt: string | null;
    metadata: string | null;
  }[];
}

interface UsersData {
  users: {
    id: string;
    email: string;
    name: string | null;
    role: string;
    createdAt: string | null;
    lastSeenAt: string | null;
    queryCount: number;
    answerCount: number;
    caseLogCount: number;
  }[];
  total: number;
  page: number;
  pageSize: number;
}

interface AnalyticsData {
  dailyQueriesLast30d: { day: string; count: number }[];
  dailyActiveUsersLast30d: { day: string; count: number }[];
  complicationDistribution: { name: string; count: number }[];
  protocolDistribution: { name: string; count: number }[];
  queryLanguageDistribution: { name: string; count: number }[];
}

interface HealthData {
  dbConnected: boolean;
  totalDocuments: number;
  activeDocuments: number;
  totalChunks: number;
  chunkedDocuments: number;
  documentsWithoutChunks: number;
  latestQueryAt: string | null;
  latestCaseLogAt: string | null;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function shortDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "2-digit" });
}

const TYPE_COLORS: Record<string, string> = {
  query: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  signup: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  case_log: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  report: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
};

// ─── KPI Card ────────────────────────────────────────────────────────────────

function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  loading,
  iconColor = "text-primary",
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
  loading?: boolean;
  iconColor?: string;
}) {
  return (
    <Card data-testid={`card-kpi-${label.toLowerCase().replace(/\s+/g, "-")}`}>
      <CardHeader className="flex flex-row items-center justify-between pb-1 space-y-0">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
        <Icon className={`h-4 w-4 ${iconColor}`} />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-7 w-24 mt-1" />
        ) : (
          <div className="text-2xl font-bold tracking-tight" data-testid={`value-kpi-${label.toLowerCase().replace(/\s+/g, "-")}`}>
            {value}
          </div>
        )}
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}

// ─── Tab Button ──────────────────────────────────────────────────────────────

function Tab({
  id, label, active, onClick,
}: {
  id: string; label: string; active: boolean; onClick: () => void;
}) {
  return (
    <button
      data-testid={`tab-${id}`}
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
        active
          ? "bg-primary text-primary-foreground"
          : "text-muted-foreground hover:text-foreground hover:bg-muted"
      }`}
    >
      {label}
    </button>
  );
}

// ─── Overview Tab ─────────────────────────────────────────────────────────────

function OverviewTab() {
  const { data, isLoading, error, refetch, isFetching } = useQuery<OverviewData>({
    queryKey: ["/api/admin/dashboard/overview"],
    queryFn: () => adminFetch("/api/admin/dashboard/overview"),
    refetchInterval: 60000,
  });

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 flex items-center gap-3 text-destructive">
        <AlertCircle className="h-5 w-5 shrink-0" />
        <span>{(error as Error).message}</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Platform Overview</h2>
        <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={isFetching} data-testid="button-refresh-overview">
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <KpiCard icon={Users} label="Total Users" value={data ? fmt(data.totalUsers) : "—"} loading={isLoading} iconColor="text-blue-500" />
        <KpiCard icon={Activity} label="Active 24h" value={data ? data.activeUsers24h : "—"} loading={isLoading} iconColor="text-green-500" />
        <KpiCard icon={Activity} label="Active 7d" value={data ? data.activeUsers7d : "—"} loading={isLoading} iconColor="text-emerald-500" />
        <KpiCard icon={Search} label="Total Queries" value={data ? fmt(data.totalQueries) : "—"} loading={isLoading} iconColor="text-violet-500" />
        <KpiCard icon={FileText} label="Total Case Logs" value={data ? fmt(data.totalCaseLogs) : "—"} loading={isLoading} iconColor="text-orange-500" />
        <KpiCard icon={Shield} label="Safety Reports" value={data ? fmt(data.totalSafetyReports) : "—"} loading={isLoading} iconColor="text-red-500" />
        <KpiCard icon={TrendingUp} label="Avg Q / User" value={data ? data.avgQueriesPerUser.toFixed(1) : "—"} loading={isLoading} />
        <KpiCard icon={Clock} label="Avg Response" value={data?.avgResponseTimeMs ? `${data.avgResponseTimeMs}ms` : "—"} loading={isLoading} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Top Complications</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-2">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
            ) : !data?.topComplications?.length ? (
              <p className="text-sm text-muted-foreground">No data yet</p>
            ) : (
              <div className="space-y-1.5">
                {data.topComplications.slice(0, 8).map((c, i) => (
                  <div key={i} className="flex items-center gap-2" data-testid={`row-complication-${i}`}>
                    <div className="text-xs text-muted-foreground w-5 text-right">{i + 1}</div>
                    <div className="flex-1 text-sm truncate">{c.name}</div>
                    <Badge variant="secondary" className="text-xs">{c.count}</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Recent Activity</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-2">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
            ) : !data?.recentActivity?.length ? (
              <p className="text-sm text-muted-foreground">No activity yet</p>
            ) : (
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {data.recentActivity.map((a, i) => (
                  <div key={i} className="flex items-start gap-2.5 text-sm" data-testid={`row-activity-${i}`}>
                    <span className={`mt-0.5 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold shrink-0 ${TYPE_COLORS[a.type] ?? "bg-muted text-muted-foreground"}`}>
                      {a.type.replace("_", " ")}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="truncate leading-tight">{a.label}</p>
                      {a.email && <p className="text-xs text-muted-foreground truncate">{a.email}</p>}
                    </div>
                    <span className="text-xs text-muted-foreground shrink-0">{timeAgo(a.createdAt)}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ─── Analytics Tab ────────────────────────────────────────────────────────────

function AnalyticsTab() {
  const { data, isLoading, error } = useQuery<AnalyticsData>({
    queryKey: ["/api/admin/dashboard/analytics"],
    queryFn: () => adminFetch("/api/admin/dashboard/analytics"),
  });

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 flex items-center gap-3 text-destructive">
        <AlertCircle className="h-5 w-5 shrink-0" />
        <span>{(error as Error).message}</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Analytics — Last 30 Days</h2>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Daily Queries</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-48 w-full" />
            ) : !data?.dailyQueriesLast30d?.length ? (
              <p className="text-sm text-muted-foreground py-8 text-center">No query data</p>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={data.dailyQueriesLast30d} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="day" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
                  <YAxis tick={{ fontSize: 10 }} width={32} />
                  <Tooltip labelFormatter={(v) => v} contentStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="count" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} name="Queries" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Daily Active Users</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-48 w-full" />
            ) : !data?.dailyActiveUsersLast30d?.length ? (
              <p className="text-sm text-muted-foreground py-8 text-center">No data</p>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={data.dailyActiveUsersLast30d} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="day" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
                  <YAxis tick={{ fontSize: 10 }} width={32} />
                  <Tooltip labelFormatter={(v) => v} contentStyle={{ fontSize: 12 }} />
                  <Bar dataKey="count" fill="hsl(var(--primary))" radius={[2, 2, 0, 0]} name="Active Users" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Complication Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-48 w-full" />
            ) : !data?.complicationDistribution?.length ? (
              <p className="text-sm text-muted-foreground py-8 text-center">No complication data</p>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={data.complicationDistribution} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 10 }} />
                  <YAxis dataKey="name" type="category" tick={{ fontSize: 10 }} width={120} />
                  <Tooltip contentStyle={{ fontSize: 12 }} />
                  <Bar dataKey="count" fill="hsl(var(--destructive) / 0.7)" radius={[0, 2, 2, 0]} name="Cases" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Query Domains</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-48 w-full" />
            ) : !data?.queryLanguageDistribution?.length ? (
              <p className="text-sm text-muted-foreground py-8 text-center">No domain data</p>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={data.queryLanguageDistribution} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 10 }} />
                  <YAxis dataKey="name" type="category" tick={{ fontSize: 10 }} width={120} />
                  <Tooltip contentStyle={{ fontSize: 12 }} />
                  <Bar dataKey="count" fill="hsl(var(--primary) / 0.65)" radius={[0, 2, 2, 0]} name="Queries" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ─── Users Tab ────────────────────────────────────────────────────────────────

function UsersTab() {
  const [page, setPage] = useState(1);
  const { data, isLoading, error } = useQuery<UsersData>({
    queryKey: ["/api/admin/dashboard/users", page],
    queryFn: () => adminFetch(`/api/admin/dashboard/users?page=${page}&page_size=50`),
  });

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 flex items-center gap-3 text-destructive">
        <AlertCircle className="h-5 w-5 shrink-0" />
        <span>{(error as Error).message}</span>
      </div>
    );
  }

  const totalPages = data ? Math.ceil(data.total / data.pageSize) : 1;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          Users {data ? `(${data.total} total)` : ""}
        </h2>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span>Page {page} / {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)} data-testid="button-users-prev">←</Button>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} data-testid="button-users-next">→</Button>
        </div>
      </div>

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="table-users">
            <thead>
              <tr className="border-b">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Email</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Role</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Created</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Last Active</th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">Queries</th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">Cases</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                [...Array(10)].map((_, i) => (
                  <tr key={i} className="border-b">
                    {[...Array(6)].map((__, j) => (
                      <td key={j} className="px-4 py-3"><Skeleton className="h-4 w-full" /></td>
                    ))}
                  </tr>
                ))
              ) : !data?.users?.length ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">No users found</td>
                </tr>
              ) : (
                data.users.map((u) => (
                  <tr key={u.id} className="border-b hover:bg-muted/30 transition-colors" data-testid={`row-user-${u.id}`}>
                    <td className="px-4 py-3">
                      <div className="font-medium truncate max-w-[220px]">{u.email}</div>
                      {u.name && <div className="text-xs text-muted-foreground">{u.name}</div>}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={u.role === "admin" ? "default" : "outline"} className="text-xs">{u.role}</Badge>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{shortDate(u.createdAt)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{timeAgo(u.lastSeenAt)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{u.queryCount}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{u.caseLogCount}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// ─── Health Tab ───────────────────────────────────────────────────────────────

function HealthTab() {
  const { data, isLoading, error, refetch, isFetching } = useQuery<HealthData>({
    queryKey: ["/api/admin/dashboard/health"],
    queryFn: () => adminFetch("/api/admin/dashboard/health"),
    refetchInterval: 120000,
  });

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 flex items-center gap-3 text-destructive">
        <AlertCircle className="h-5 w-5 shrink-0" />
        <span>{(error as Error).message}</span>
      </div>
    );
  }

  function Row({ label, value, ok }: { label: string; value: React.ReactNode; ok?: boolean }) {
    return (
      <div className="flex items-center justify-between py-2.5 border-b last:border-0">
        <span className="text-sm text-muted-foreground">{label}</span>
        <div className="flex items-center gap-2">
          {ok !== undefined && (
            ok ? <CheckCircle2 className="h-4 w-4 text-green-500" /> : <AlertCircle className="h-4 w-4 text-destructive" />
          )}
          <span className="text-sm font-medium">{value}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">System Health</h2>
        <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={isFetching} data-testid="button-refresh-health">
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Server className="h-4 w-4" /> Database
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-2">{[...Array(7)].map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
            ) : !data ? null : (
              <>
                <Row label="DB Connected" value={data.dbConnected ? "Yes" : "No"} ok={data.dbConnected} />
                <Row label="Total Documents" value={fmt(data.totalDocuments)} />
                <Row label="Active Documents" value={fmt(data.activeDocuments)} />
                <Row label="Total Chunks" value={fmt(data.totalChunks)} />
                <Row label="Chunked Documents" value={fmt(data.chunkedDocuments)} />
                <Row label="Docs Without Chunks" value={fmt(data.documentsWithoutChunks)} ok={data.documentsWithoutChunks === 0} />
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Activity className="h-4 w-4" /> Activity Timestamps
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-2">{[...Array(2)].map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
            ) : !data ? null : (
              <>
                <Row label="Latest Query" value={data.latestQueryAt ? new Date(data.latestQueryAt).toLocaleString() : "—"} />
                <Row label="Latest Case Log" value={data.latestCaseLogAt ? new Date(data.latestCaseLogAt).toLocaleString() : "—"} />
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

type TabId = "overview" | "analytics" | "users" | "health";

export default function AdminDashboardPage() {
  const [, navigate] = useLocation();
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  const token = getToken();

  const { data: me, isLoading: meLoading } = useQuery({
    queryKey: ["/api/auth/me"],
    queryFn: () => (token ? getMe(token) : Promise.reject("No token")),
    enabled: !!token,
    retry: false,
  });

  if (!token) {
    navigate("/login");
    return null;
  }

  if (meLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="space-y-2 text-center">
          <Skeleton className="h-8 w-48 mx-auto" />
          <Skeleton className="h-4 w-32 mx-auto" />
        </div>
      </div>
    );
  }

  if (!me || me.email !== SUPER_ADMIN_EMAIL) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center space-y-3 max-w-sm">
          <div className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-destructive/10 mx-auto">
            <Shield className="h-7 w-7 text-destructive" />
          </div>
          <h1 className="text-xl font-semibold">Access Denied</h1>
          <p className="text-sm text-muted-foreground">
            This dashboard is restricted to the platform super-admin account only.
          </p>
          <Button variant="outline" onClick={() => navigate("/")} data-testid="button-go-home">
            Back to Home
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="border-b bg-background/95 backdrop-blur sticky top-0 z-10">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-14 items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Database className="h-5 w-5 text-primary" />
              <h1 className="text-base font-semibold" data-testid="text-admin-title">AesthetiCite Admin</h1>
              <Badge variant="secondary" className="text-xs hidden sm:inline-flex">support@aestheticite.com</Badge>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-xs hidden sm:inline-flex">Auto-refresh 60s</Badge>
              <Button variant="outline" size="sm" onClick={() => navigate("/admin/user-activity")} data-testid="button-user-activity" className="gap-1.5 text-xs">
                <Activity className="h-3.5 w-3.5" />
                User Activity
              </Button>
              <Button variant="ghost" size="sm" onClick={() => navigate("/")} data-testid="button-back-home">
                ← Back
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6">
        <div className="flex items-center gap-1.5 mb-6 flex-wrap">
          <Tab id="overview" label="Overview" active={activeTab === "overview"} onClick={() => setActiveTab("overview")} />
          <Tab id="analytics" label="Analytics" active={activeTab === "analytics"} onClick={() => setActiveTab("analytics")} />
          <Tab id="users" label="Users" active={activeTab === "users"} onClick={() => setActiveTab("users")} />
          <Tab id="health" label="System Health" active={activeTab === "health"} onClick={() => setActiveTab("health")} />
        </div>

        {activeTab === "overview" && <OverviewTab />}
        {activeTab === "analytics" && <AnalyticsTab />}
        {activeTab === "users" && <UsersTab />}
        {activeTab === "health" && <HealthTab />}
      </div>
    </div>
  );
}
