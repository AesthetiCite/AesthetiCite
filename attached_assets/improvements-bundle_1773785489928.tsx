/**
 * AesthetiCite — Improvements Bundle
 * client/src/improvements-bundle.tsx
 *
 * Contains 5 complete page/component implementations:
 *
 *   1. LandingPage          → client/src/pages/landing.tsx
 *   2. ClinicDashboardPage  → client/src/pages/clinic-dashboard.tsx
 *   3. DrugInteractionsPage → client/src/pages/drug-interactions.tsx
 *   4. HyaluronidaseCalc    → client/src/components/hyaluronidase-calc.tsx
 *   5. OnboardingDialog     → client/src/components/onboarding-dialog.tsx
 *
 * HOW TO USE:
 *   Copy each section between the ═══ dividers into its own file.
 *   All imports use existing shadcn/ui and lucide-react — no new deps.
 *
 * App.tsx changes needed:
 *   - /welcome route already uses LandingPage ✓
 *   - /clinic-dashboard route already exists ✓
 *   - /drug-interactions route already exists ✓
 *   - Import HyaluronidaseCalc into clinical-tools-panel.tsx or a new /hyaluronidase route
 *   - OnboardingDialog is already imported in ask.tsx ✓
 */

export {};


// ═══════════════════════════════════════════════════════════════════════════
// FILE 1: client/src/pages/landing.tsx
// Public-facing landing page — replaces the generic /welcome route
// Visible to any visitor before login. Conversion-optimised.
// ═══════════════════════════════════════════════════════════════════════════

/*
import { useLocation } from "wouter";
import { Link } from "wouter";
import {
  Shield, AlertTriangle, ClipboardList, Activity,
  BookOpen, CheckCircle2, ArrowRight, Camera,
  Syringe, Zap, BarChart3, Globe, Lock, FileDown
} from "lucide-react";
import { Button } from "@/components/ui/button";

export default function LandingPage() {
  const [, setLocation] = useLocation();

  return (
    <div className="min-h-screen bg-background text-foreground">

      // ── NAV ──────────────────────────────────────────────────────────────
      <nav className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <img src="/aestheticite-logo.png" alt="AesthetiCite" className="w-7 h-7 rounded-lg object-contain" />
            <span className="font-bold text-sm tracking-tight">AesthetiCite</span>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login">
              <Button variant="ghost" size="sm" className="text-sm">Sign in</Button>
            </Link>
            <Link href="/request-access">
              <Button size="sm" className="text-sm shadow-lg shadow-primary/20">
                Request access
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      // ── HERO ─────────────────────────────────────────────────────────────
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-background to-background pointer-events-none" />
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-20 sm:py-28 text-center relative">

          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-primary/20 bg-primary/5 text-xs font-semibold text-primary mb-6">
            <Shield className="w-3.5 h-3.5" />
            Clinical safety and evidence engine for aesthetic medicine
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-tight mb-6">
            The safety platform
            <span className="block text-primary">aesthetic clinics trust</span>
          </h1>

          <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-8 leading-relaxed">
            Structured complication protocols, pre-procedure risk assessment,
            and 780,000+ peer-reviewed documents — built for injectors, not researchers.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-12">
            <Link href="/request-access">
              <Button size="lg" className="gap-2 shadow-xl shadow-primary/20 px-8">
                Request clinical access
                <ArrowRight className="w-4 h-4" />
              </Button>
            </Link>
            <Link href="/login">
              <Button size="lg" variant="outline" className="gap-2 px-8">
                Sign in
              </Button>
            </Link>
          </div>

          // Trust bar
          <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-xs text-muted-foreground">
            {[
              { icon: BookOpen, label: "780,000+ peer-reviewed documents" },
              { icon: CheckCircle2, label: "Server-validated citations only" },
              { icon: Lock, label: "GDPR compliant by design" },
              { icon: Globe, label: "25 languages supported" },
            ].map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-1.5">
                <Icon className="w-3.5 h-3.5 text-primary/60" />
                <span>{label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      // ── THE PROBLEM ───────────────────────────────────────────────────────
      <section className="border-t bg-muted/20">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-16 text-center">
          <h2 className="text-2xl sm:text-3xl font-bold mb-4">
            Aesthetic medicine needs better safety infrastructure
          </h2>
          <p className="text-muted-foreground max-w-2xl mx-auto text-base leading-relaxed">
            Vascular occlusion events, inconsistent complication management, junior injectors
            without structured protocols. AesthetiCite solves all three.
          </p>
        </div>
      </section>

      // ── THREE FEATURES ────────────────────────────────────────────────────
      <section className="max-w-5xl mx-auto px-4 sm:px-6 py-16">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            {
              icon: Shield,
              color: "emerald",
              title: "Pre-Procedure Safety Check",
              description:
                "Risk score before every treatment. GO / CAUTION / HIGH RISK decision with danger zones, mitigation steps, and a PDF for the clinical record.",
              href: "/safety-check",
              tag: "Before treatment",
            },
            {
              icon: AlertTriangle,
              color: "red",
              title: "Complication Protocols",
              description:
                "Structured protocols for vascular occlusion, anaphylaxis, ptosis, Tyndall effect, infection, and nodules — with dose guidance and escalation steps.",
              href: "/complications",
              tag: "During a complication",
            },
            {
              icon: ClipboardList,
              color: "blue",
              title: "Session Safety Report",
              description:
                "Queue multiple patients, run safety checks for each, and export one consolidated PDF at the end of the session.",
              href: "/session-report",
              tag: "After the session",
            },
          ].map((feature) => {
            const colorMap: Record<string, string> = {
              emerald: "border-emerald-500/30 bg-emerald-500/5",
              red: "border-red-500/30 bg-red-500/5",
              blue: "border-blue-500/30 bg-blue-500/5",
            };
            const iconColorMap: Record<string, string> = {
              emerald: "text-emerald-500",
              red: "text-red-500",
              blue: "text-blue-500",
            };
            return (
              <div key={feature.title}
                className={`rounded-2xl border p-6 space-y-4 transition-all hover:shadow-md ${colorMap[feature.color]}`}>
                <div className="flex items-center justify-between gap-2">
                  <feature.icon className={`w-6 h-6 ${iconColorMap[feature.color]}`} />
                  <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border ${colorMap[feature.color]} ${iconColorMap[feature.color]}`}>
                    {feature.tag}
                  </span>
                </div>
                <div>
                  <h3 className="font-bold text-base mb-2">{feature.title}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">{feature.description}</p>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      // ── ADDITIONAL FEATURES ───────────────────────────────────────────────
      <section className="border-t bg-muted/20">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-16">
          <h2 className="text-xl font-bold mb-8 text-center">Everything a clinical team needs</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            {[
              { icon: BookOpen,     label: "780K+ documents" },
              { icon: Syringe,      label: "Drug interactions" },
              { icon: Camera,       label: "Vision follow-up" },
              { icon: Activity,     label: "Evidence search" },
              { icon: BarChart3,    label: "Clinic dashboard" },
              { icon: FileDown,     label: "PDF export" },
            ].map(({ icon: Icon, label }) => (
              <div key={label} className="text-center p-4 rounded-xl border border-border bg-background space-y-2">
                <div className="w-8 h-8 mx-auto rounded-lg bg-primary/10 flex items-center justify-center">
                  <Icon className="w-4 h-4 text-primary" />
                </div>
                <p className="text-xs font-medium">{label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      // ── CTA ───────────────────────────────────────────────────────────────
      <section className="max-w-5xl mx-auto px-4 sm:px-6 py-20 text-center">
        <div className="rounded-3xl border border-primary/20 bg-primary/5 p-10 space-y-6">
          <h2 className="text-2xl sm:text-3xl font-bold">
            Ready to improve clinical safety in your clinic?
          </h2>
          <p className="text-muted-foreground max-w-xl mx-auto">
            AesthetiCite is currently available to qualified aesthetic medicine practitioners.
            Request access to start your free pilot.
          </p>
          <Link href="/request-access">
            <Button size="lg" className="gap-2 shadow-xl shadow-primary/20 px-10">
              Request clinical access
              <ArrowRight className="w-4 h-4" />
            </Button>
          </Link>
          <p className="text-xs text-muted-foreground">
            Clinical decision support only · Not a medical device · GDPR compliant
          </p>
        </div>
      </section>

      // ── FOOTER ────────────────────────────────────────────────────────────
      <footer className="border-t py-8">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <img src="/aestheticite-logo.png" alt="AesthetiCite" className="w-5 h-5 rounded object-contain" />
            <span>AesthetiCite — Clinical Safety Platform for Aesthetic Medicine</span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/governance" className="hover:text-foreground transition-colors">Governance</Link>
            <Link href="/login" className="hover:text-foreground transition-colors">Sign in</Link>
            <Link href="/request-access" className="hover:text-foreground transition-colors">Request access</Link>
          </div>
        </div>
      </footer>

    </div>
  );
}
*/


// ═══════════════════════════════════════════════════════════════════════════
// FILE 2: client/src/pages/clinic-dashboard.tsx
// Clinic admin panel — wired to GET /api/growth/dashboard/{clinic_id}
// ═══════════════════════════════════════════════════════════════════════════

/*
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
  label: string; value: string; sub?: string;
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
          <Icon className={`w-4.5 h-4.5 ${iconMap[accent]}`} />
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
              className="rounded-md border border-border bg-background px-3 py-1.5 text-xs w-28 focus:outline-none focus:ring-1 focus:ring-primary/40"
              onBlur={() => { localStorage.setItem("aestheticite_clinic_id", clinicId); fetchDashboard(); }}
            />
            <Button variant="outline" size="sm" onClick={fetchDashboard} disabled={loading} className="gap-1.5">
              {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
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
            // Stat cards
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

            // Top questions
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
                    <div key={i}
                      className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-muted/40 transition-colors">
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

            // Evidence + answer distribution
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
                              <div className="h-full rounded-full transition-all duration-700"
                                style={{ width: `${pct}%`, backgroundColor: color }} />
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
                              <div className="h-full rounded-full bg-primary/60 transition-all duration-700"
                                style={{ width: `${pct}%` }} />
                            </div>
                          </div>
                        );
                      })}
                  </CardContent>
                </Card>
              )}
            </div>

            // ACI quality note
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
*/


// ═══════════════════════════════════════════════════════════════════════════
// FILE 3: client/src/pages/drug-interactions.tsx
// Complete drug interaction checker — wired to POST /api/growth/drug-interactions
// ═══════════════════════════════════════════════════════════════════════════

/*
import { useState } from "react";
import { useLocation } from "wouter";
import {
  ArrowLeft, Pill, AlertTriangle, CheckCircle2,
  XCircle, Plus, Trash2, Loader2, Shield, Info
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { getToken } from "@/lib/auth";

interface DrugInteractionItem {
  medication: string;
  product_or_context: string;
  severity: "low" | "moderate" | "high";
  explanation: string;
  action: string;
}

interface DrugInteractionResponse {
  items: DrugInteractionItem[];
  summary: string;
}

const COMMON_MEDICATIONS = [
  "Warfarin", "Apixaban", "Rivaroxaban", "Dabigatran",
  "Aspirin", "Clopidogrel", "Ibuprofen", "Naproxen",
  "Sertraline", "Fluoxetine", "Escitalopram",
  "Metformin", "Atorvastatin", "Amlodipine",
];

const COMMON_PRODUCTS = [
  "HA filler", "Botulinum toxin", "Calcium hydroxylapatite",
  "Poly-L-lactic acid", "PRP", "Laser treatment", "Injectable treatment",
];

function SeverityBadge({ severity }: { severity: string }) {
  const map = {
    high:     { label: "High",     cls: "bg-red-500/15 border-red-500/30 text-red-700 dark:text-red-300",     icon: XCircle },
    moderate: { label: "Moderate", cls: "bg-amber-500/15 border-amber-500/30 text-amber-700 dark:text-amber-300", icon: AlertTriangle },
    low:      { label: "Low",      cls: "bg-emerald-500/15 border-emerald-500/30 text-emerald-700 dark:text-emerald-300", icon: CheckCircle2 },
  };
  const config = map[severity as keyof typeof map] || map.low;
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-xs font-semibold ${config.cls}`}>
      <config.icon className="w-3 h-3" />
      {config.label} risk
    </span>
  );
}

export default function DrugInteractionsPage() {
  const [, setLocation] = useLocation();
  const [medications, setMedications] = useState<string[]>([""]);
  const [products, setProducts] = useState<string[]>(["Injectable treatment"]);
  const [result, setResult] = useState<DrugInteractionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateMed(i: number, val: string) {
    setMedications((prev) => prev.map((m, idx) => idx === i ? val : m));
  }
  function addMed() { setMedications((prev) => [...prev, ""]); }
  function removeMed(i: number) { setMedications((prev) => prev.filter((_, idx) => idx !== i)); }

  async function handleCheck() {
    const meds = medications.filter((m) => m.trim());
    if (meds.length === 0) { setError("Enter at least one medication."); return; }
    setLoading(true); setError(null); setResult(null);
    try {
      const token = getToken();
      const res = await fetch("/api/growth/drug-interactions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ medications: meds, planned_products: products.filter(Boolean) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Check failed");
      setResult(data);
    } catch (err: any) {
      setError(err.message || "Drug interaction check failed.");
    } finally {
      setLoading(false);
    }
  }

  const hasHighRisk = result?.items.some((i) => i.severity === "high");

  return (
    <div className="min-h-screen bg-background">
      <div className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => setLocation("/")} className="gap-2 -ml-2">
              <ArrowLeft className="w-4 h-4" />
              <span className="hidden sm:inline">Back</span>
            </Button>
            <div className="w-px h-5 bg-border" />
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-amber-500/10 flex items-center justify-center">
                <Pill className="w-4 h-4 text-amber-500" />
              </div>
              <span className="font-semibold text-sm">Drug Interaction Checker</span>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-4">

        // Medications input
        <Card>
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Patient medications
              </label>
              <Button variant="ghost" size="sm" onClick={addMed} className="gap-1 text-xs h-7">
                <Plus className="w-3 h-3" /> Add
              </Button>
            </div>

            // Quick add chips
            <div className="flex flex-wrap gap-1.5">
              {COMMON_MEDICATIONS.map((med) => (
                <button
                  key={med}
                  onClick={() => {
                    if (!medications.includes(med))
                      setMedications((prev) => [...prev.filter(Boolean), med]);
                  }}
                  className={`px-2.5 py-1 rounded-full border text-xs transition-all ${
                    medications.includes(med)
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:border-primary/40"
                  }`}
                >
                  {med}
                </button>
              ))}
            </div>

            // Free text inputs
            <div className="space-y-2">
              {medications.map((med, i) => (
                <div key={i} className="flex gap-2">
                  <input
                    type="text"
                    value={med}
                    onChange={(e) => updateMed(i, e.target.value)}
                    placeholder="e.g. Warfarin 5mg"
                    className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary/40"
                  />
                  {medications.length > 1 && (
                    <button onClick={() => removeMed(i)}
                      className="text-muted-foreground/50 hover:text-destructive transition-colors px-2">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        // Planned products
        <Card>
          <CardContent className="p-4 space-y-3">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Planned aesthetic treatment
            </label>
            <div className="flex flex-wrap gap-1.5">
              {COMMON_PRODUCTS.map((p) => (
                <button
                  key={p}
                  onClick={() => setProducts([p])}
                  className={`px-2.5 py-1 rounded-full border text-xs transition-all ${
                    products.includes(p)
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:border-primary/40"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        <Button
          onClick={handleCheck}
          disabled={loading || medications.filter(Boolean).length === 0}
          className="w-full gap-2 shadow-lg shadow-primary/20"
        >
          {loading
            ? <><Loader2 className="w-4 h-4 animate-spin" /> Checking…</>
            : <><Pill className="w-4 h-4" /> Check Interactions</>}
        </Button>

        {error && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-sm text-destructive">
            <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />{error}
          </div>
        )}

        // Results
        {result && (
          <div className="space-y-3">

            // Summary banner
            <div className={`rounded-xl border p-4 ${
              hasHighRisk
                ? "border-red-500/40 bg-red-500/8"
                : result.items.length > 0
                ? "border-amber-500/30 bg-amber-500/5"
                : "border-emerald-500/30 bg-emerald-500/5"
            }`}>
              <div className="flex items-start gap-2">
                {hasHighRisk
                  ? <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                  : result.items.length > 0
                  ? <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                  : <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />}
                <p className={`text-sm font-medium ${
                  hasHighRisk ? "text-red-700 dark:text-red-300"
                  : result.items.length > 0 ? "text-amber-700 dark:text-amber-300"
                  : "text-emerald-700 dark:text-emerald-300"
                }`}>
                  {result.summary}
                </p>
              </div>
            </div>

            // Interaction cards
            {result.items.length > 0 && (
              <div className="space-y-3">
                {result.items.map((item, i) => (
                  <Card key={i} className={`border ${
                    item.severity === "high" ? "border-red-500/30 bg-red-500/5"
                    : item.severity === "moderate" ? "border-amber-500/20"
                    : "border-border"
                  }`}>
                    <CardContent className="p-4 space-y-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <span className="text-sm font-semibold capitalize">{item.medication}</span>
                          <span className="text-xs text-muted-foreground ml-2">+ {item.product_or_context}</span>
                        </div>
                        <SeverityBadge severity={item.severity} />
                      </div>
                      <p className="text-sm text-foreground/80">{item.explanation}</p>
                      <div className="flex items-start gap-2 p-2.5 rounded-lg bg-muted/40 border border-border/50">
                        <Info className="w-3.5 h-3.5 text-primary mt-0.5 flex-shrink-0" />
                        <p className="text-xs text-foreground/75">{item.action}</p>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            // No interactions
            {result.items.length === 0 && (
              <Card className="border-emerald-500/30 bg-emerald-500/5">
                <CardContent className="p-4 flex items-center gap-3">
                  <CheckCircle2 className="w-5 h-5 text-emerald-500 flex-shrink-0" />
                  <p className="text-sm text-emerald-700 dark:text-emerald-300">
                    No interactions identified by the current ruleset for the medications entered.
                  </p>
                </CardContent>
              </Card>
            )}

            <p className="text-xs text-muted-foreground/60 text-center leading-relaxed">
              <Shield className="w-3 h-3 inline mr-1" />
              This checker uses a rule-based system and does not replace clinical pharmacology judgment.
              Always verify against current prescribing information and patient history.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
*/


// ═══════════════════════════════════════════════════════════════════════════
// FILE 4: client/src/components/hyaluronidase-calc.tsx
// Hyaluronidase dose calculator — standalone component
// Add to /clinical-tools route or as a panel in the safety pages
//
// To add as a route: import in App.tsx as HyaluronidaseCalcPage,
// wrap in a simple page shell, add route /hyaluronidase
// ═══════════════════════════════════════════════════════════════════════════

/*
import { useState } from "react";
import {
  Syringe, AlertTriangle, CheckCircle2,
  ChevronDown, ChevronUp, Shield
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface DoseResult {
  initial_dose_iu: string;
  repeat_interval: string;
  max_sessions: string;
  technique: string;
  monitoring: string[];
  red_flags: string[];
  evidence_note: string;
}

const REGION_PROTOCOLS: Record<string, DoseResult> = {
  "nasolabial_fold": {
    initial_dose_iu: "200–500 IU",
    repeat_interval: "Every 30–60 minutes until reperfusion improves",
    max_sessions: "Repeat as needed — no fixed maximum when active ischemia is present",
    technique: "Inject across the full affected vascular territory, not just the puncture site. Fan technique to cover the region.",
    monitoring: [
      "Reassess capillary refill every 15–30 minutes",
      "Monitor pain, skin colour, and livedo pattern after each cycle",
      "Photograph before and after each treatment cycle",
      "Discontinue when perfusion is restored and stable",
    ],
    red_flags: [
      "Visual disturbance or any ocular symptom — emergency escalation immediately",
      "No improvement after 2–3 treatment cycles",
      "Rapidly expanding livedo pattern beyond initial territory",
      "Progressive darkening or blistering of skin",
    ],
    evidence_note: "Dosing based on expert consensus. Optimal dose and interval are not standardised in RCT evidence. Treat the territory, not the puncture point.",
  },
  "lips": {
    initial_dose_iu: "150–300 IU",
    repeat_interval: "Every 30–60 minutes until clinical improvement",
    max_sessions: "Repeat as clinically required",
    technique: "Cover the superior and inferior labial artery territories. Retrograde along the length of the lip if blanching extends.",
    monitoring: [
      "Monitor labial artery territory colour and capillary refill",
      "Reassess every 15–30 minutes",
      "Document product, volume injected, and injection sites",
    ],
    red_flags: [
      "Extension of blanching toward nasal tip or nasolabial fold",
      "Severe escalating pain",
      "Any visual symptom — immediate emergency escalation",
    ],
    evidence_note: "Expert consensus. Labial arteries are superficial — prompt treatment is critical.",
  },
  "tear_trough": {
    initial_dose_iu: "75–150 IU",
    repeat_interval: "Every 30–60 minutes",
    max_sessions: "Use conservative doses due to proximity to orbit",
    technique: "Small incremental doses. Avoid periorbital spread — target the infraorbital territory specifically.",
    monitoring: [
      "Monitor infraorbital skin colour and capillary refill closely",
      "Any eyelid oedema or periorbital change requires immediate review",
      "Ophthalmology referral if any visual symptom arises",
    ],
    red_flags: [
      "ANY visual symptom — ophthalmic emergency",
      "Periorbital oedema or skin necrosis",
      "Absence of reperfusion after initial treatment",
    ],
    evidence_note: "Periorbital territory carries highest risk for ophthalmic artery involvement. Low doses and close monitoring.",
  },
  "glabella": {
    initial_dose_iu: "300–1500 IU",
    repeat_interval: "Every 30–60 minutes until reperfusion",
    max_sessions: "No maximum — priority is tissue perfusion. Use high doses early.",
    technique: "Glabella is the highest-risk region for retrograde embolism. Treat the supratrochlear and supraorbital territories broadly.",
    monitoring: [
      "Ophthalmology emergency contact must be on standby",
      "Any visual symptom — do not delay emergency services",
      "Monitor full forehead and periorbital territory",
    ],
    red_flags: [
      "ANY visual symptom — call emergency services immediately",
      "Diplopia, ptosis, or any ocular motility change",
      "This is the highest-risk region for permanent vision loss",
    ],
    evidence_note: "Glabellar occlusion carries the highest risk of ophthalmic artery involvement and vision loss. Emergency escalation threshold must be very low.",
  },
  "nose": {
    initial_dose_iu: "200–500 IU",
    repeat_interval: "Every 30–60 minutes",
    max_sessions: "Repeat as required — nasal tip ischemia can progress rapidly",
    technique: "Target the columellar and lateral nasal artery territories. The nose has end-artery anatomy — tissue necrosis risk is high.",
    monitoring: [
      "Monitor nasal tip colour and temperature closely",
      "Document progression with serial photography",
      "Low threshold for emergency referral",
    ],
    red_flags: [
      "Darkening of nasal tip — high necrosis risk",
      "Any visual symptom",
      "No response after initial treatment cycle",
    ],
    evidence_note: "Nasal filler carries high tissue necrosis risk due to end-artery anatomy. Aggressive early treatment is preferred.",
  },
  "cheek_jaw": {
    initial_dose_iu: "300–600 IU",
    repeat_interval: "Every 30–60 minutes",
    max_sessions: "Repeat as clinically indicated",
    technique: "Cover the facial artery territory for cheek. For jawline, address the inferior labial and submental artery territories.",
    monitoring: [
      "Monitor cheek and perioral skin colour",
      "Reassess capillary refill at 15–30 minute intervals",
    ],
    red_flags: [
      "Extension toward perioral or nasal territory",
      "Any visual symptom",
      "Progressive blanching despite treatment",
    ],
    evidence_note: "Expert consensus. Facial artery territory is large — ensure full territory coverage.",
  },
};

const REGIONS = [
  { value: "nasolabial_fold", label: "Nasolabial fold" },
  { value: "lips",            label: "Lips / perioral" },
  { value: "tear_trough",     label: "Tear trough / infraorbital" },
  { value: "glabella",        label: "Glabella / forehead" },
  { value: "nose",            label: "Nose" },
  { value: "cheek_jaw",       label: "Cheek / jawline" },
];

export function HyaluronidaseCalc() {
  const [region, setRegion] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  const protocol = region ? REGION_PROTOCOLS[region] : null;

  return (
    <div className="space-y-4">
      // Emergency header
      <div className="flex items-start gap-2 p-3 rounded-xl border border-red-500/30 bg-red-500/8">
        <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
        <div className="text-sm">
          <span className="font-bold text-red-600 dark:text-red-400">Emergency protocol. </span>
          <span className="text-red-800 dark:text-red-200">
            If any visual symptom is present — stop reading and call emergency services immediately.
            This calculator is for HA filler vascular occlusion only.
          </span>
        </div>
      </div>

      // Region select
      <div className="space-y-1.5">
        <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Injection region
        </label>
        <select
          value={region}
          onChange={(e) => { setRegion(e.target.value); setConfirmed(false); }}
          className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
        >
          <option value="">Select region…</option>
          {REGIONS.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
      </div>

      // HA confirmed checkbox
      {region && (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
            className="w-4 h-4 rounded accent-primary"
          />
          <span className="text-sm">I confirm the product is hyaluronic acid filler</span>
        </label>
      )}

      // Protocol output
      {protocol && confirmed && (
        <div className="space-y-3">

          // Dose
          <Card className="border-red-500/30 bg-red-500/5">
            <CardContent className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Syringe className="w-4 h-4 text-red-500" />
                <span className="text-sm font-bold text-red-600 dark:text-red-400">Hyaluronidase dose</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-3 rounded-lg bg-background border border-border/60 text-center">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Initial dose</p>
                  <p className="text-lg font-bold text-red-600 dark:text-red-400">{protocol.initial_dose_iu}</p>
                </div>
                <div className="p-3 rounded-lg bg-background border border-border/60 text-center">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Repeat at</p>
                  <p className="text-sm font-semibold">{protocol.repeat_interval}</p>
                </div>
                <div className="p-3 rounded-lg bg-background border border-border/60 text-center">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Max sessions</p>
                  <p className="text-sm font-semibold">{protocol.max_sessions}</p>
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-background/60 border border-border/50">
                <p className="text-xs text-foreground/80"><span className="font-semibold">Technique: </span>{protocol.technique}</p>
              </div>
            </CardContent>
          </Card>

          // Red flags
          <Card className="border-red-500/40 bg-red-500/8">
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle className="w-4 h-4 text-red-500" />
                <span className="text-xs font-bold text-red-600 dark:text-red-400 uppercase tracking-wider">Red flags — escalate immediately</span>
              </div>
              {protocol.red_flags.map((flag, i) => (
                <div key={i} className="flex items-start gap-2 text-sm text-red-800 dark:text-red-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-500 mt-1.5 flex-shrink-0" />
                  {flag}
                </div>
              ))}
            </CardContent>
          </Card>

          // Monitoring
          <Card>
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Monitoring</span>
              </div>
              {protocol.monitoring.map((item, i) => (
                <div key={i} className="flex items-start gap-2 text-sm text-foreground/80">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-1.5 flex-shrink-0" />
                  {item}
                </div>
              ))}
            </CardContent>
          </Card>

          // Evidence note
          <button
            onClick={() => setEvidenceOpen(!evidenceOpen)}
            className="w-full flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <Shield className="w-3 h-3" />
            Evidence note
            {evidenceOpen ? <ChevronUp className="w-3 h-3 ml-auto" /> : <ChevronDown className="w-3 h-3 ml-auto" />}
          </button>
          {evidenceOpen && (
            <p className="text-xs text-muted-foreground/80 leading-relaxed px-2">
              {protocol.evidence_note}
            </p>
          )}

          <p className="text-[10px] text-muted-foreground/60 text-center leading-relaxed">
            Clinical decision support only. Not a substitute for clinical training, local emergency
            protocols, or manufacturer prescribing information.
          </p>
        </div>
      )}
    </div>
  );
}
*/


// ═══════════════════════════════════════════════════════════════════════════
// FILE 5: client/src/components/onboarding-dialog.tsx
// First-run onboarding — shows on first login, guides to 3 key features
// Replaces the existing onboarding-dialog.tsx
// ═══════════════════════════════════════════════════════════════════════════

/*
import { useState, useEffect } from "react";
import { useLocation } from "wouter";
import {
  Shield, AlertTriangle, ClipboardList,
  ArrowRight, X, CheckCircle2
} from "lucide-react";
import { Button } from "@/components/ui/button";

const STEPS = [
  {
    icon: Shield,
    color: "emerald",
    title: "Pre-Procedure Safety Check",
    description:
      "Before any injectable treatment, run a safety check. Enter the procedure, region, product, and patient factors — and get a risk score, danger zones, and mitigation steps in seconds.",
    action: "Try it now →",
    href: "/safety-check",
  },
  {
    icon: AlertTriangle,
    color: "red",
    title: "Complication Protocols",
    description:
      "If something goes wrong during a treatment, open the Complication Protocols page. Select the scenario — vascular occlusion, anaphylaxis, ptosis, or infection — and get immediate structured guidance.",
    action: "See protocols →",
    href: "/complications",
  },
  {
    icon: ClipboardList,
    color: "blue",
    title: "Session Safety Report",
    description:
      "At the start of a clinic session, queue your patients, run pre-procedure checks for each, and export one consolidated safety report as a PDF for your clinical records.",
    action: "Start a session →",
    href: "/session-report",
  },
];

const STORAGE_KEY = "aestheticite_onboarding_v2";

export function OnboardingDialog() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [, setLocation] = useLocation();

  useEffect(() => {
    try {
      const done = localStorage.getItem(STORAGE_KEY);
      if (!done) setOpen(true);
    } catch {}
  }, []);

  function dismiss() {
    try { localStorage.setItem(STORAGE_KEY, "1"); } catch {}
    setOpen(false);
  }

  function goToFeature(href: string) {
    dismiss();
    setLocation(href);
  }

  if (!open) return null;

  const current = STEPS[step];
  const colorMap: Record<string, string> = {
    emerald: "border-emerald-500/30 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400",
    red:     "border-red-500/30 bg-red-500/5 text-red-600 dark:text-red-400",
    blue:    "border-blue-500/30 bg-blue-500/5 text-blue-600 dark:text-blue-400",
  };
  const iconBg: Record<string, string> = {
    emerald: "bg-emerald-500/10",
    red:     "bg-red-500/10",
    blue:    "bg-blue-500/10",
  };

  return (
    // Backdrop
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-md bg-background rounded-2xl border shadow-2xl overflow-hidden">

        // Header
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <div className="flex items-center gap-2">
            <img src="/aestheticite-logo.png" alt="" className="w-6 h-6 rounded object-contain" />
            <span className="font-semibold text-sm">Welcome to AesthetiCite</span>
          </div>
          <button onClick={dismiss} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        // Step indicator
        <div className="flex gap-1.5 px-5 pt-4">
          {STEPS.map((_, i) => (
            <div key={i}
              className={`h-1 flex-1 rounded-full transition-all ${
                i <= step ? "bg-primary" : "bg-muted"
              }`} />
          ))}
        </div>

        // Step content
        <div className="px-5 py-5 space-y-4">
          <div className={`rounded-xl border p-4 ${colorMap[current.color]}`}>
            <div className={`w-10 h-10 rounded-xl ${iconBg[current.color]} flex items-center justify-center mb-3`}>
              <current.icon className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-base mb-2">{current.title}</h3>
            <p className="text-sm leading-relaxed opacity-80">{current.description}</p>
          </div>

          // Progress
          <p className="text-xs text-muted-foreground text-center">
            Feature {step + 1} of {STEPS.length}
          </p>
        </div>

        // Actions
        <div className="px-5 pb-5 flex items-center gap-3">
          <Button
            variant="ghost" size="sm"
            onClick={() => step > 0 ? setStep(step - 1) : dismiss()}
            className="text-xs"
          >
            {step === 0 ? "Skip tour" : "Back"}
          </Button>
          <div className="flex-1" />
          <Button
            variant="outline" size="sm"
            onClick={() => goToFeature(current.href)}
            className="gap-1.5 text-xs"
          >
            {current.action}
          </Button>
          {step < STEPS.length - 1 ? (
            <Button size="sm" onClick={() => setStep(step + 1)} className="gap-1.5 text-xs">
              Next <ArrowRight className="w-3.5 h-3.5" />
            </Button>
          ) : (
            <Button size="sm" onClick={dismiss} className="gap-1.5 text-xs">
              <CheckCircle2 className="w-3.5 h-3.5" /> Start using AesthetiCite
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
*/
