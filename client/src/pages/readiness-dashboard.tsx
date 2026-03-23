import React from "react";
/**
 * AesthetiCite — Readiness Dashboard
 * =====================================
 * Place at: client/src/pages/readiness-dashboard.tsx
 * Add route in App.tsx:
 *   import ReadinessDashboardPage from "@/pages/readiness-dashboard";
 *   <Route path="/admin/readiness">{() => <ProtectedRoute component={ReadinessDashboardPage} />}</Route>
 *
 * Add to routes.ts:
 *   app.get("/api/ops/readiness",          (req,res) => proxyToFastAPI(req,res,"/api/ops/readiness"));
 *   app.post("/api/ops/readiness/fix",     (req,res) => proxyToFastAPI(req,res,"/api/ops/readiness/fix"));
 *   app.get("/api/ops/readiness/history",  (req,res) => proxyToFastAPI(req,res,"/api/ops/readiness/history"));
 *   app.get("/api/ops/readiness/quick",    (req,res) => proxyToFastAPI(req,res,"/api/ops/readiness/quick"));
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { getToken } from "@/lib/auth";
import { Link } from "wouter";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Check {
  id: string;
  label: string;
  ok: boolean;
  weight: number;
  category: string;
  fix_available: boolean;
  blocker: string;
  remediation: string;
}

interface CategoryScore {
  total: number;
  achieved: number;
  score: number;
  checks: string[];
}

interface Summary {
  readiness_score: number;
  status: string;
  status_label: string;
  status_colour: string;
  potential_score_after_fix: number;
  checks_passed: number;
  checks_total: number;
  blockers: Array<{ id: string; label: string; blocker: string; remediation: string; weight: number; fix_available: boolean }>;
  warnings: Array<{ id: string; label: string; remediation: string; weight: number; fix_available: boolean }>;
  by_category: Record<string, CategoryScore>;
}

interface ReadinessReport {
  generated_at_utc: string;
  summary: Summary;
  checks: Check[];
  recommendation: string;
  details: {
    environment: Record<string, any>;
    database: Record<string, any>;
    evidence_retrieval: Record<string, any>;
    auth_flow: Record<string, any>;
    ingestion: Record<string, any>;
    monitoring: Record<string, any>;
    activity: Record<string, any>;
    pdf_storage: Record<string, any>;
  };
  fix_result?: {
    fixed: Array<{ id: string; message: string }>;
    failed: Array<{ id: string; error: string }>;
    skipped: Array<{ id: string; reason: string }>;
    fixed_count: number;
    failed_count: number;
    next_step: string;
  };
}

// ─── Colour helpers ───────────────────────────────────────────────────────────

const SCORE_COLOURS: Record<string, { ring: string; fill: string; text: string; badge: string; card: string }> = {
  green:   { ring: "#10b981", fill: "#10b981", text: "text-emerald-400", badge: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25", card: "border-emerald-500/20 bg-emerald-500/5" },
  emerald: { ring: "#10b981", fill: "#10b981", text: "text-emerald-400", badge: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25", card: "border-emerald-500/20 bg-emerald-500/5" },
  amber:   { ring: "#f59e0b", fill: "#f59e0b", text: "text-amber-400",   badge: "bg-amber-500/15 text-amber-400 border-amber-500/25",       card: "border-amber-500/20 bg-amber-500/5" },
  orange:  { ring: "#f97316", fill: "#f97316", text: "text-orange-400",  badge: "bg-orange-500/15 text-orange-400 border-orange-500/25",     card: "border-orange-500/20 bg-orange-500/5" },
  red:     { ring: "#ef4444", fill: "#ef4444", text: "text-red-400",     badge: "bg-red-500/15 text-red-400 border-red-500/25",             card: "border-red-500/20 bg-red-500/5" },
};

const CATEGORY_ICONS: Record<string, string> = {
  infrastructure: "⬡",
  environment:    "⚙",
  data:           "📊",
  activity:       "📋",
  auth:           "🔐",
  monitoring:     "👁",
};

const CATEGORY_LABELS: Record<string, string> = {
  infrastructure: "Infrastructure",
  environment:    "Environment",
  data:           "Knowledge Base",
  activity:       "Clinic Activity",
  auth:           "Auth Flow",
  monitoring:     "Monitoring",
};

// ─── Score Ring ───────────────────────────────────────────────────────────────

function ScoreRing({ score, colour, size = 120 }: { score: number; colour: string; size?: number }) {
  const cfg = SCORE_COLOURS[colour] ?? SCORE_COLOURS.red;
  const r = size * 0.38;
  const circ = 2 * Math.PI * r;
  const dash = circ * (score / 100);
  const cx = size / 2;
  const cy = size / 2;

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={cx} cy={cy} r={r} fill="none"
          stroke="currentColor" strokeWidth={size * 0.055}
          className="text-white/8" />
        <circle cx={cx} cy={cy} r={r} fill="none"
          stroke={cfg.ring} strokeWidth={size * 0.055}
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cy})`}
          style={{ transition: "stroke-dasharray 1s cubic-bezier(.4,0,.2,1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`font-black tabular-nums leading-none ${cfg.text}`}
              style={{ fontSize: size * 0.22 }}>
          {score}
        </span>
        <span className="text-white/40 font-medium" style={{ fontSize: size * 0.09 }}>
          / 100
        </span>
      </div>
    </div>
  );
}

// ─── Category bar ─────────────────────────────────────────────────────────────

function CategoryBar({ name, data }: { name: string; data: CategoryScore }) {
  const icon = CATEGORY_ICONS[name] || "◆";
  const label = CATEGORY_LABELS[name] || name;
  const pct = data.score;
  const barColour = pct >= 90 ? "bg-emerald-500" : pct >= 65 ? "bg-amber-500" : "bg-red-500";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 text-white/70">
          <span>{icon}</span>
          <span className="font-medium">{label}</span>
        </span>
        <span className={`font-bold tabular-nums ${pct >= 90 ? "text-emerald-400" : pct >= 65 ? "text-amber-400" : "text-red-400"}`}>
          {pct}%
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-white/8 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${barColour}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ─── Check Row ────────────────────────────────────────────────────────────────

function CheckRow({ check, onFixClick, fixing }: {
  check: Check;
  onFixClick?: (id: string) => void;
  fixing: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={`rounded-lg border transition-colors ${
      check.ok
        ? "border-white/8 bg-white/3"
        : "border-red-500/20 bg-red-500/5"
    }`}>
      <div
        className="flex items-center gap-3 px-3 py-2.5 cursor-pointer select-none"
        onClick={() => !check.ok && setExpanded((v) => !v)}
      >
        {/* Status dot */}
        <span className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold ${
          check.ok
            ? "bg-emerald-500/20 text-emerald-400"
            : "bg-red-500/20 text-red-400"
        }`}>
          {check.ok ? "✓" : "✕"}
        </span>

        {/* Label */}
        <span className={`flex-1 text-sm font-medium ${check.ok ? "text-white/80" : "text-white/90"}`}>
          {check.label}
        </span>

        {/* Weight badge */}
        <span className="text-[10px] text-white/30 tabular-nums hidden sm:block">
          {check.weight}pt
        </span>

        {/* Category badge */}
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/8 text-white/40 hidden md:block capitalize">
          {check.category}
        </span>

        {/* Fix badge */}
        {!check.ok && check.fix_available && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/25 font-medium">
            auto-fix
          </span>
        )}

        {/* Expand arrow */}
        {!check.ok && (
          <span className="text-white/30 text-xs">{expanded ? "▲" : "▼"}</span>
        )}
      </div>

      {/* Expanded remediation */}
      {expanded && !check.ok && (
        <div className="px-3 pb-3 pt-1 space-y-2 border-t border-white/6">
          <p className="text-xs text-red-300/90 leading-relaxed">{check.blocker}</p>
          <p className="text-xs text-white/50 leading-relaxed">{check.remediation}</p>
          {check.fix_available && onFixClick && (
            <button
              onClick={(e) => { e.stopPropagation(); onFixClick(check.id); }}
              disabled={fixing}
              className="mt-1 flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/30 transition-colors disabled:opacity-40"
            >
              {fixing ? (
                <span className="w-3 h-3 border border-indigo-300/30 border-t-indigo-300 rounded-full animate-spin" />
              ) : "⚡"}
              Run auto-fix
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Fix Result Panel ─────────────────────────────────────────────────────────

function FixResultPanel({ result }: { result: NonNullable<ReadinessReport["fix_result"]> }) {
  return (
    <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-indigo-300">Auto-fix completed</p>
        <div className="flex gap-2 text-xs">
          <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400">
            {result.fixed_count} fixed
          </span>
          {result.failed_count > 0 && (
            <span className="px-2 py-0.5 rounded-full bg-red-500/20 text-red-400">
              {result.failed_count} failed
            </span>
          )}
        </div>
      </div>

      {result.fixed.length > 0 && (
        <ul className="space-y-1">
          {result.fixed.map((f) => (
            <li key={f.id} className="text-xs text-emerald-400/80 flex items-start gap-1.5">
              <span>✓</span>{f.message}
            </li>
          ))}
        </ul>
      )}

      {result.failed.length > 0 && (
        <ul className="space-y-1">
          {result.failed.map((f) => (
            <li key={f.id} className="text-xs text-red-400/80 flex items-start gap-1.5">
              <span>✕</span>{f.id}: {f.error}
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-white/50 border-t border-white/8 pt-2">{result.next_step}</p>
    </div>
  );
}

// ─── History Sparkline ────────────────────────────────────────────────────────

function Sparkline({ history }: { history: Array<{ score: number; timestamp_utc: string }> }) {
  if (history.length < 2) return null;

  const w = 200;
  const h = 40;
  const min = Math.min(...history.map((h) => h.score));
  const max = Math.max(...history.map((h) => h.score)) || 100;
  const pad = 4;

  const points = history.map((item, i) => {
    const x = pad + (i / (history.length - 1)) * (w - pad * 2);
    const y = h - pad - ((item.score - min) / (max - min || 1)) * (h - pad * 2);
    return `${x},${y}`;
  }).join(" ");

  const latest = history[history.length - 1];
  const prev = history[history.length - 2];
  const trend = latest.score - prev.score;

  return (
    <div className="flex items-center gap-3">
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible">
        <polyline
          points={points}
          fill="none"
          stroke="#6366f1"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.7"
        />
        {/* Last point dot */}
        {history.length > 0 && (() => {
          const last = points.split(" ").pop()?.split(",") || ["0", "0"];
          return (
            <circle cx={last[0]} cy={last[1]} r="2.5"
              fill="#6366f1" opacity="0.9" />
          );
        })()}
      </svg>
      <span className={`text-xs font-semibold ${trend > 0 ? "text-emerald-400" : trend < 0 ? "text-red-400" : "text-white/40"}`}>
        {trend > 0 ? "↑" : trend < 0 ? "↓" : "→"} {Math.abs(trend)}pt
      </span>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ReadinessDashboardPage() {
  const [report, setReport] = useState<ReadinessReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [fixing, setFixing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Array<{ score: number; timestamp_utc: string; status: string }>>([]);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchReport = useCallback(async () => {
    try {
      const token = getToken();
      const res = await fetch("/api/ops/readiness", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data: ReadinessReport = await res.json();
      setReport(data);
      setLastRefreshed(new Date());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load readiness report");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const token = getToken();
      const res = await fetch("/api/ops/readiness/history", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setHistory(data.history || []);
      }
    } catch {}
  }, []);

  const runFix = useCallback(async () => {
    setFixing(true);
    try {
      const token = getToken();
      const res = await fetch("/api/ops/readiness/fix", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      const data: ReadinessReport = await res.json();
      setReport(data);
      setLastRefreshed(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fix failed");
    } finally {
      setFixing(false);
    }
  }, []);

  useEffect(() => {
    fetchReport();
    fetchHistory();
    // Poll every 60 seconds
    intervalRef.current = setInterval(() => {
      fetchReport();
      fetchHistory();
    }, 60000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [fetchReport, fetchHistory]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0f1e] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
          <p className="text-white/50 text-sm">Running readiness checks…</p>
        </div>
      </div>
    );
  }

  if (error && !report) {
    return (
      <div className="min-h-screen bg-[#0a0f1e] flex items-center justify-center p-4">
        <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-6 max-w-sm text-center">
          <p className="text-red-400 font-semibold mb-2">Failed to load readiness report</p>
          <p className="text-white/40 text-sm mb-4">{error}</p>
          <button onClick={fetchReport}
            className="px-4 py-2 rounded-lg bg-red-500/20 text-red-300 text-sm hover:bg-red-500/30 transition-colors">
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!report) return null;

  const { summary, checks, recommendation, details } = report;
  const cfg = SCORE_COLOURS[summary.status_colour] ?? SCORE_COLOURS.red;
  const fixableChecks = checks.filter((c) => !c.ok && c.fix_available);

  const categories = Object.keys(summary.by_category);
  const filteredChecks = activeCategory
    ? checks.filter((c) => c.category === activeCategory)
    : checks;

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white">
      {/* Header */}
      <div className="sticky top-0 z-20 border-b border-white/8 bg-[#0a0f1e]/90 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link href="/admin" className="text-white/40 hover:text-white/70 transition-colors text-sm">
              ← Admin
            </Link>
            <span className="text-white/20">/</span>
            <div>
              <h1 className="text-sm font-bold text-white/90">Operational Readiness</h1>
              {lastRefreshed && (
                <p className="text-[10px] text-white/30">
                  Updated {lastRefreshed.toLocaleTimeString()} · auto-refreshes every 60s
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchReport}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 text-white/50 hover:text-white/80 hover:border-white/20 text-xs transition-colors"
            >
              ↺ Refresh
            </button>
            {fixableChecks.length > 0 && (
              <button
                onClick={runFix}
                disabled={fixing}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-indigo-500/90 text-white font-semibold text-xs hover:bg-indigo-600 transition-colors disabled:opacity-40"
              >
                {fixing ? (
                  <span className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" />
                ) : "⚡"}
                Fix {fixableChecks.length} issue{fixableChecks.length !== 1 ? "s" : ""}
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">

        {/* Fix result */}
        {report.fix_result && (
          <FixResultPanel result={report.fix_result} />
        )}

        {/* Top row: score + summary */}
        <div className={`rounded-2xl border p-6 ${cfg.card}`}>
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-6">
            {/* Score ring */}
            <div className="flex-shrink-0">
              <ScoreRing score={summary.readiness_score} colour={summary.status_colour} size={128} />
            </div>

            {/* Status */}
            <div className="flex-1 min-w-0 space-y-3">
              <div className="flex items-center gap-3 flex-wrap">
                <span className={`px-3 py-1 rounded-full text-sm font-bold border ${cfg.badge}`}>
                  {summary.status_label}
                </span>
                <span className="text-white/40 text-sm tabular-nums">
                  {summary.checks_passed}/{summary.checks_total} checks passed
                </span>
                {summary.potential_score_after_fix > summary.readiness_score && (
                  <span className="text-xs text-indigo-400/80 flex items-center gap-1">
                    ⚡ can reach {summary.potential_score_after_fix}% automatically
                  </span>
                )}
              </div>

              <p className="text-sm text-white/60 leading-relaxed max-w-xl">{recommendation}</p>

              {/* Sparkline */}
              {history.length >= 2 && (
                <div className="pt-1">
                  <p className="text-[10px] text-white/30 mb-1 uppercase tracking-wider">Score history</p>
                  <Sparkline history={history} />
                </div>
              )}
            </div>

            {/* Category scores */}
            <div className="w-full sm:w-56 space-y-3 flex-shrink-0">
              {categories.map((cat) => (
                <CategoryBar key={cat} name={cat} data={summary.by_category[cat]} />
              ))}
            </div>
          </div>
        </div>

        {/* Blockers */}
        {summary.blockers.length > 0 && (
          <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-5 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-bold text-red-400 uppercase tracking-wider">
                ⚠ Blockers ({summary.blockers.length})
              </p>
              {fixableChecks.length > 0 && (
                <button
                  onClick={runFix}
                  disabled={fixing}
                  className="text-xs px-3 py-1.5 rounded-lg bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/30 transition-colors disabled:opacity-40 flex items-center gap-1.5"
                >
                  {fixing ? <span className="w-3 h-3 border border-indigo-300/30 border-t-indigo-300 rounded-full animate-spin" /> : "⚡"}
                  Auto-fix {fixableChecks.length} of these
                </button>
              )}
            </div>
            <div className="space-y-2">
              {summary.blockers.map((b) => (
                <div key={b.id} className="flex items-start gap-3 rounded-lg bg-white/3 border border-white/6 px-3 py-2.5">
                  <span className="text-red-400 text-xs mt-0.5 flex-shrink-0">✕</span>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-white/90">{b.label}</p>
                    <p className="text-xs text-white/40 mt-0.5 leading-relaxed">{b.remediation}</p>
                  </div>
                  <div className="flex-shrink-0 flex items-center gap-1.5">
                    <span className="text-[10px] text-white/30">{b.weight}pt</span>
                    {b.fix_available && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300">fix</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Quick actions */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <QuickActionCard
            icon="📥"
            title="Populate Knowledge Base"
            description={`${details.database.documents_count || 0} documents · ${details.ingestion.aesthetic_documents || 0} aesthetic`}
            action={details.ingestion.ingestion_needed ? "Run ingestion →" : ""}
            status={details.database.knowledge_base_populated ? "ok" : "needed"}
            href="/admin"
          />
          <QuickActionCard
            icon="🔐"
            title="Auth Flow"
            description={`Reset: ${details.auth_flow.password_reset_wired ? "✓" : "✗"} · Verify: ${details.auth_flow.email_verify_wired ? "✓" : "✗"} · SMTP: ${details.auth_flow.smtp_configured ? "✓" : "✗"}`}
            action={!details.auth_flow.email_flow_fully_operational ? "Configure →" : ""}
            status={details.auth_flow.email_flow_fully_operational ? "ok" : "needed"}
          />
          <QuickActionCard
            icon="📡"
            title="Monitoring"
            description={`Sentry: ${details.monitoring.sentry_active ? "active" : "inactive"} · PDF: ${details.pdf_storage.storage_mode}`}
            action={!details.monitoring.sentry_active ? "Set SENTRY_DSN →" : ""}
            status={details.monitoring.sentry_active ? "ok" : "warning"}
          />
        </div>

        {/* All checks */}
        <div className="rounded-2xl border border-white/8 bg-white/2 overflow-hidden">
          <div className="p-4 border-b border-white/8 flex items-center gap-3 flex-wrap">
            <p className="text-sm font-semibold text-white/80 mr-auto">All Checks</p>
            {/* Category filter */}
            <button
              onClick={() => setActiveCategory(null)}
              className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
                !activeCategory ? "bg-white/15 text-white" : "text-white/40 hover:text-white/70"
              }`}
            >
              All
            </button>
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setActiveCategory(activeCategory === cat ? null : cat)}
                className={`text-xs px-2.5 py-1 rounded-full transition-colors capitalize ${
                  activeCategory === cat
                    ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                    : "text-white/40 hover:text-white/70"
                }`}
              >
                {CATEGORY_ICONS[cat]} {CATEGORY_LABELS[cat] || cat}
              </button>
            ))}
          </div>
          <div className="p-4 space-y-2">
            {/* Passed */}
            <div className="space-y-1.5">
              {filteredChecks
                .filter((c) => c.ok)
                .map((c) => (
                  <CheckRow key={c.id} check={c} fixing={fixing} />
                ))}
            </div>
            {/* Failed */}
            {filteredChecks.some((c) => !c.ok) && (
              <div className="mt-3 space-y-1.5">
                <p className="text-[10px] text-white/30 uppercase tracking-wider px-1 pt-2">Failing</p>
                {filteredChecks
                  .filter((c) => !c.ok)
                  .sort((a, b) => b.weight - a.weight)
                  .map((c) => (
                    <CheckRow key={c.id} check={c} onFixClick={() => runFix()} fixing={fixing} />
                  ))}
              </div>
            )}
          </div>
        </div>

        {/* Detail panels */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <DetailPanel title="Database & Knowledge Base" icon="🗄">
            <DetailRow label="PostgreSQL" value={details.database.database_ok ? "Connected" : "Error"} ok={details.database.database_ok} />
            <DetailRow label="Documents" value={String(details.database.documents_count || 0)} />
            <DetailRow label="Aesthetic docs" value={String(details.database.documents_count_aesthetic || 0)} />
            <DetailRow label="Chunks with embeddings" value={String(details.database.chunks_with_embeddings || 0)} />
            <DetailRow label="pgvector" value={details.database.pgvector_extension_installed ? "Installed" : "Missing"} ok={details.database.pgvector_extension_installed} />
          </DetailPanel>

          <DetailPanel title="Ingestion Pipeline" icon="📥">
            <DetailRow label="Status" value={details.ingestion.ingestion_status} />
            <DetailRow label="Papers found" value={String(details.ingestion.papers_found || 0)} />
            <DetailRow label="Papers inserted" value={String(details.ingestion.papers_inserted || 0)} />
            <DetailRow label="Last completed" value={details.ingestion.last_completed || "Never"} ok={!!details.ingestion.last_completed} />
            <DetailRow label="Knowledge base ready" value={details.ingestion.knowledge_base_ready ? "Yes" : "No"} ok={details.ingestion.knowledge_base_ready} />
          </DetailPanel>

          <DetailPanel title="Evidence Retrieval" icon="🔍">
            <DetailRow label="Pre-procedure engine" value={details.evidence_retrieval.preprocedure_engine_patched ? "Live pgvector" : "DummyRetriever"} ok={details.evidence_retrieval.preprocedure_engine_patched} />
            <DetailRow label="Complication engine" value={details.evidence_retrieval.complication_engine_patched ? "Live pgvector" : "DummyRetriever"} ok={details.evidence_retrieval.complication_engine_patched} />
            <DetailRow label="pgvector flag" value={details.evidence_retrieval.pgvector_enabled_flag ? "Enabled" : "Disabled"} ok={details.evidence_retrieval.pgvector_enabled_flag} />
            {details.evidence_retrieval.retrieval_test && (
              <DetailRow
                label="Retrieval test"
                value={details.evidence_retrieval.retrieval_test.ok
                  ? `${details.evidence_retrieval.retrieval_test.results_count} results`
                  : "Failed"}
                ok={details.evidence_retrieval.retrieval_test.ok}
              />
            )}
          </DetailPanel>

          <DetailPanel title="Clinic Activity" icon="📋">
            <DetailRow label="Query logging" value={details.activity.query_logging_live ? "Active" : "No logs yet"} ok={details.activity.query_logging_live} />
            <DetailRow label="Session reports" value={details.activity.session_reporting_live ? "Active" : "No reports yet"} ok={details.activity.session_reporting_live} />
            <DetailRow label="Case logging" value={details.activity.case_logging_live ? "Active" : "No cases yet"} ok={details.activity.case_logging_live} />
          </DetailPanel>

          <DetailPanel title="Auth & Email" icon="🔐">
            <DetailRow label="Auth tokens table" value={details.auth_flow.auth_tokens_table_ok ? "Ready" : "Missing"} ok={details.auth_flow.auth_tokens_table_ok} />
            <DetailRow label="Password reset" value={details.auth_flow.password_reset_wired ? "Wired" : "Not wired"} ok={details.auth_flow.password_reset_wired} />
            <DetailRow label="Email verification" value={details.auth_flow.email_verify_wired ? "Wired" : "Not wired"} ok={details.auth_flow.email_verify_wired} />
            <DetailRow label="SMTP" value={details.auth_flow.smtp_configured ? "Configured" : "Not configured"} ok={details.auth_flow.smtp_configured} />
            <DetailRow label="APP_BASE_URL" value={details.auth_flow.app_base_url_configured ? "Set" : "Not set"} ok={details.auth_flow.app_base_url_configured} />
          </DetailPanel>

          <DetailPanel title="Infrastructure" icon="⬡">
            <DetailRow label="PDF storage" value={details.pdf_storage.storage_mode} ok={details.pdf_storage.storage_ok} />
            <DetailRow label="S3 configured" value={details.pdf_storage.s3_configured ? `${details.environment.s3_configured ? "Yes" : "No"}` : "No"} ok={details.pdf_storage.s3_configured} />
            <DetailRow label="PDFs generated" value={String(details.pdf_storage.pdf_count_local)} />
            <DetailRow label="Sentry" value={details.monitoring.sentry_active ? "Active" : "Inactive"} ok={details.monitoring.sentry_active} />
            <DetailRow label="NCBI key" value={details.environment.ncbi_key_configured ? "Set" : "Not set"} ok={details.environment.ncbi_key_configured} />
          </DetailPanel>
        </div>

        {/* Footer */}
        <p className="text-center text-[10px] text-white/20 pb-4">
          AesthetiCite Operational Readiness · Engine v2.0.0 · Generated {report.generated_at_utc}
        </p>
      </div>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function QuickActionCard({
  icon, title, description, action, status, href,
}: {
  icon: string;
  title: string;
  description: string;
  action: string;
  status: "ok" | "needed" | "warning";
  href?: string;
}) {
  const colours = {
    ok:      "border-emerald-500/20 bg-emerald-500/5",
    needed:  "border-red-500/20 bg-red-500/5",
    warning: "border-amber-500/20 bg-amber-500/5",
  };
  const dot = {
    ok:      "bg-emerald-500",
    needed:  "bg-red-500",
    warning: "bg-amber-500",
  };

  const content = (
    <div className={`rounded-xl border p-4 space-y-2 h-full ${colours[status]}`}>
      <div className="flex items-center gap-2">
        <span className="text-lg">{icon}</span>
        <span className="text-sm font-semibold text-white/90">{title}</span>
        <span className={`ml-auto w-2 h-2 rounded-full flex-shrink-0 ${dot[status]}`} />
      </div>
      <p className="text-xs text-white/50 leading-relaxed">{description}</p>
      {action && (
        <p className="text-xs text-indigo-400 font-medium">{action}</p>
      )}
    </div>
  );

  return href ? <a href={href} className="block h-full">{content}</a> : content;
}

function DetailPanel({ title, icon, children }: {
  title: string;
  icon: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/2 overflow-hidden">
      <div className="px-4 py-3 border-b border-white/8 flex items-center gap-2">
        <span className="text-base">{icon}</span>
        <p className="text-xs font-semibold text-white/70 uppercase tracking-wider">{title}</p>
      </div>
      <div className="p-4 space-y-2">{children}</div>
    </div>
  );
}

function DetailRow({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-xs text-white/40">{label}</span>
      <span className={`text-xs font-medium ${
        ok === true ? "text-emerald-400" :
        ok === false ? "text-red-400" :
        "text-white/70"
      }`}>
        {value}
      </span>
    </div>
  );
}

