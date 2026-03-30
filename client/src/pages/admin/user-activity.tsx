/**
 * pages/admin/user-activity.tsx
 * ==============================
 * Super-admin session monitoring dashboard.
 * Only accessible when logged in as support@aestheticite.com.
 *
 * Shows for any user (default: dr.mehta@aestheticite.com):
 *   - Live status (online / offline)
 *   - Summary stats (total sessions, avg duration, total time, queries)
 *   - Session log table (date, duration, queries, end reason)
 *   - Activity by day (bar chart — last 30 days)
 *   - Activity by hour of day (heatmap row)
 *
 * INTEGRATION — App.tsx:
 *   import UserActivityPage from "@/pages/admin/user-activity";
 *   <Route path="/admin/user-activity">
 *     {() => <ProtectedRoute component={UserActivityPage} />}
 *   </Route>
 *
 * server/routes.ts:
 *   app.get("/api/admin/sessions/user/:email",       (req,res) => proxyToFastAPI(req,res,`/admin/sessions/user/${req.params.email}`));
 *   app.get("/api/admin/sessions/user/:email/stats", (req,res) => proxyToFastAPI(req,res,`/admin/sessions/user/${req.params.email}/stats`));
 *   app.post("/api/admin/sessions/start",            (req,res) => proxyToFastAPI(req,res,"/admin/sessions/start"));
 *   app.post("/api/admin/sessions/heartbeat",        (req,res) => proxyToFastAPI(req,res,"/admin/sessions/heartbeat"));
 *   app.post("/api/admin/sessions/end",              (req,res) => proxyToFastAPI(req,res,"/admin/sessions/end"));
 */

import { useState, useEffect, useCallback } from "react";
import { useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  RefreshCw, Activity, Clock, Calendar, Search,
  TrendingUp, Zap, LogOut, AlertTriangle, ChevronLeft,
} from "lucide-react";
import { getToken, getMe } from "@/lib/auth";

const SUPER_ADMIN = "support@aestheticite.com";
const DEFAULT_TARGET = "dr.mehta@aestheticite.com";

// ─────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────

interface SessionRow {
  session_id: string;
  email: string;
  started_at: string;
  last_heartbeat_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  query_count: number;
  end_reason: string | null;
  is_active: boolean;
}

interface DayStat {
  date: string;
  sessions: number;
  total_seconds: number;
  formatted: string;
  queries: number;
}

interface HourStat {
  hour: number;
  sessions: number;
}

interface Stats {
  summary: {
    total_sessions: number;
    active_now: number;
    avg_duration_seconds: number;
    avg_duration_formatted: string;
    longest_session_seconds: number;
    longest_formatted: string;
    total_time_seconds: number;
    total_time_formatted: string;
    total_queries: number;
    last_login: string | null;
    first_login: string | null;
    active_days: number;
  };
  by_day: DayStat[];
  by_hour: HourStat[];
}

// ─────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function fmtDuration(seconds: number | null): string {
  if (!seconds || seconds <= 0) return "—";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function endReasonBadge(reason: string | null, isActive: boolean) {
  if (isActive) return <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium"><span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />Online</span>;
  if (!reason) return <span className="text-xs text-muted-foreground">—</span>;
  const map: Record<string, [string, string]> = {
    logout:    ["bg-blue-100 text-blue-700", "Logout"],
    unload:    ["bg-gray-100 text-gray-600", "Tab closed"],
    expired:   ["bg-amber-100 text-amber-700", "Expired"],
    new_login: ["bg-purple-100 text-purple-700", "New login"],
    heartbeat_timeout: ["bg-red-100 text-red-700", "Timeout"],
  };
  const [cls, label] = map[reason] || ["bg-gray-100 text-gray-600", reason];
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>{label}</span>;
}

// ─────────────────────────────────────────────────────────────────
// Metric card
// ─────────────────────────────────────────────────────────────────

function Metric({ label, value, sub, accent = false }: {
  label: string; value: string; sub?: string; accent?: boolean;
}) {
  return (
    <div className={`rounded-lg p-4 border ${accent ? "bg-teal-50 border-teal-200" : "bg-muted/40 border-border"}`}>
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      <p className={`text-2xl font-semibold ${accent ? "text-teal-700" : "text-foreground"}`}>{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Day activity bar chart (inline SVG)
// ─────────────────────────────────────────────────────────────────

function DayChart({ days }: { days: DayStat[] }) {
  if (!days.length) return <p className="text-sm text-muted-foreground">No data yet.</p>;
  const reversed = [...days].reverse();
  const maxSec = Math.max(...reversed.map(d => d.total_seconds), 1);

  return (
    <div className="space-y-1">
      {reversed.slice(0, 14).map(d => (
        <div key={d.date} className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground w-24 flex-shrink-0">
            {new Date(d.date).toLocaleDateString("en-GB", { day: "2-digit", month: "short" })}
          </span>
          <div className="flex-1 h-5 bg-muted rounded overflow-hidden">
            <div
              className="h-full bg-teal-500 rounded transition-all"
              style={{ width: `${Math.max((d.total_seconds / maxSec) * 100, 1)}%` }}
            />
          </div>
          <span className="text-muted-foreground w-16 text-right">{d.formatted || "—"}</span>
          <span className="text-muted-foreground w-16 text-right">{d.queries} queries</span>
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Hour-of-day heatmap
// ─────────────────────────────────────────────────────────────────

function HourHeatmap({ hours }: { hours: HourStat[] }) {
  const map: Record<number, number> = {};
  hours.forEach(h => { map[h.hour] = h.sessions; });
  const max = Math.max(...hours.map(h => h.sessions), 1);

  return (
    <div className="flex gap-1 flex-wrap">
      {Array.from({ length: 24 }, (_, i) => {
        const count = map[i] || 0;
        const intensity = count / max;
        const bg = count === 0
          ? "bg-muted"
          : intensity < 0.3 ? "bg-teal-100"
          : intensity < 0.6 ? "bg-teal-300"
          : "bg-teal-600";
        return (
          <div key={i} title={`${i}:00 — ${count} session${count !== 1 ? "s" : ""}`}
            className={`w-8 h-8 rounded flex items-center justify-center text-[10px] font-medium ${bg} ${count > 0 ? "text-teal-900" : "text-muted-foreground"} cursor-default`}>
            {i}
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────

export default function UserActivityPage() {
  const [, navigate] = useLocation();
  const token = getToken();

  const [targetEmail, setTargetEmail] = useState(DEFAULT_TARGET);
  const [inputEmail, setInputEmail] = useState(DEFAULT_TARGET);
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [accessDenied, setAccessDenied] = useState(false);

  // ── Auth guard — super admin only ──────────────────────────────
  useEffect(() => {
    if (!token) { navigate("/login"); return; }
    getMe(token).then(user => {
      if (user?.email !== SUPER_ADMIN) setAccessDenied(true);
    }).catch(() => setAccessDenied(true));
  }, [token, navigate]);

  // ── Fetch data ─────────────────────────────────────────────────
  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [sessRes, statsRes] = await Promise.all([
        fetch(`/api/admin/sessions/user/${encodeURIComponent(targetEmail)}?limit=50`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`/api/admin/sessions/user/${encodeURIComponent(targetEmail)}/stats`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);

      if (sessRes.status === 403 || statsRes.status === 403) {
        setAccessDenied(true); return;
      }
      if (!sessRes.ok || !statsRes.ok) {
        throw new Error("Failed to load session data");
      }

      const sessData = await sessRes.json();
      const statsData = await statsRes.json();
      setSessions(sessData.sessions || []);
      setStats(statsData);
      setLastRefresh(new Date());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, targetEmail]);

  useEffect(() => { load(); }, [load]);

  // ── Access denied ──────────────────────────────────────────────
  if (accessDenied) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-3">
          <AlertTriangle className="w-10 h-10 text-red-500 mx-auto" />
          <p className="text-lg font-semibold">Access restricted</p>
          <p className="text-sm text-muted-foreground">This page is only accessible to {SUPER_ADMIN}</p>
          <Button variant="outline" onClick={() => navigate("/admin")}>Back to admin</Button>
        </div>
      </div>
    );
  }

  const isOnline = stats?.summary.active_now ? stats.summary.active_now > 0 : false;

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-background sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => navigate("/admin")} className="gap-1 text-xs">
              <ChevronLeft className="w-3.5 h-3.5" /> Admin
            </Button>
            <div>
              <h1 className="text-base font-semibold text-foreground">User activity</h1>
              <p className="text-xs text-muted-foreground">Session monitoring  ·  {SUPER_ADMIN}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {lastRefresh && (
              <span className="text-xs text-muted-foreground hidden sm:block">
                Updated {lastRefresh.toLocaleTimeString()}
              </span>
            )}
            <Button variant="outline" size="sm" onClick={load} disabled={loading} className="gap-1.5 text-xs">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-6 space-y-6">

        {/* User selector */}
        <div className="flex gap-2">
          <input
            type="email"
            value={inputEmail}
            onChange={e => setInputEmail(e.target.value)}
            placeholder="user@aestheticite.com"
            className="flex-1 text-sm rounded-lg border border-border px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-teal-500"
            onKeyDown={e => { if (e.key === "Enter") { setTargetEmail(inputEmail); } }}
          />
          <Button onClick={() => setTargetEmail(inputEmail)} className="gap-1.5 text-sm bg-teal-700 hover:bg-teal-800 text-white">
            <Search className="w-3.5 h-3.5" /> View activity
          </Button>
        </div>

        {/* User banner */}
        <div className="flex items-center gap-3 rounded-xl border border-border p-4 bg-muted/30">
          <div className="w-10 h-10 rounded-full bg-teal-100 flex items-center justify-center text-teal-700 font-bold text-sm flex-shrink-0">
            {targetEmail.split("@")[0].slice(0, 2).toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-foreground truncate">{targetEmail}</p>
            <p className="text-xs text-muted-foreground">
              {stats?.summary.first_login
                ? `Member since ${new Date(stats.summary.first_login).toLocaleDateString("en-GB", { day: "2-digit", month: "long", year: "numeric" })}`
                : "No sessions recorded yet"}
            </p>
          </div>
          {isOnline ? (
            <span className="flex items-center gap-1.5 text-xs font-semibold text-green-700 bg-green-100 px-3 py-1.5 rounded-full">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" /> Online now
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground bg-muted px-3 py-1.5 rounded-full">
              <span className="w-2 h-2 rounded-full bg-gray-400" /> Offline
            </span>
          )}
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {stats && (
          <>
            {/* Metric cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Metric
                label="Total sessions"
                value={stats.summary.total_sessions.toString()}
                sub={`${stats.summary.active_days} active days`}
                accent
              />
              <Metric
                label="Avg session length"
                value={stats.summary.avg_duration_formatted || "—"}
                sub={`Longest: ${stats.summary.longest_formatted}`}
              />
              <Metric
                label="Total connected time"
                value={stats.summary.total_time_formatted || "—"}
                sub="All sessions combined"
              />
              <Metric
                label="Total queries"
                value={stats.summary.total_queries.toString()}
                sub={`Last login: ${stats.summary.last_login ? new Date(stats.summary.last_login).toLocaleDateString("en-GB") : "—"}`}
              />
            </div>

            {/* Activity by day */}
            <div className="rounded-xl border border-border p-5">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp className="w-4 h-4 text-teal-600" />
                <h2 className="text-sm font-semibold text-foreground">Daily activity — last 14 days</h2>
              </div>
              <DayChart days={stats.by_day} />
            </div>

            {/* Hour heatmap */}
            <div className="rounded-xl border border-border p-5">
              <div className="flex items-center gap-2 mb-4">
                <Clock className="w-4 h-4 text-teal-600" />
                <h2 className="text-sm font-semibold text-foreground">Time of day (hour of login)</h2>
                <span className="text-xs text-muted-foreground ml-auto">Darker = more sessions</span>
              </div>
              <HourHeatmap hours={stats.by_hour} />
            </div>
          </>
        )}

        {/* Session log table */}
        <div className="rounded-xl border border-border overflow-hidden">
          <div className="px-5 py-3 border-b border-border bg-muted/30 flex items-center gap-2">
            <Activity className="w-4 h-4 text-teal-600" />
            <h2 className="text-sm font-semibold text-foreground">Session log</h2>
            <span className="text-xs text-muted-foreground ml-auto">{sessions.length} sessions</span>
          </div>
          {sessions.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-muted-foreground">
              No sessions recorded yet for {targetEmail}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/20">
                    <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">Started</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">Duration</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">Queries</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">Last seen</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">Ended</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((s, i) => (
                    <tr
                      key={s.session_id}
                      className={`border-b border-border ${s.is_active ? "bg-green-50/50" : ""} hover:bg-muted/30 transition-colors`}
                    >
                      <td className="px-4 py-3 text-xs text-foreground font-medium">
                        {fmtDate(s.started_at)}
                      </td>
                      <td className="px-4 py-3 text-xs text-foreground">
                        {s.is_active
                          ? <span className="text-green-700 font-medium">Active now</span>
                          : fmtDuration(s.duration_seconds)}
                      </td>
                      <td className="px-4 py-3 text-xs text-foreground">
                        {s.query_count}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {fmtDate(s.last_heartbeat_at)}
                      </td>
                      <td className="px-4 py-3">
                        {endReasonBadge(s.end_reason, s.is_active)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
