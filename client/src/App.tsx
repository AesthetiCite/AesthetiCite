/**
 * AesthetiCite — client/src/App.tsx
 * Adds: ResetPasswordPage and VerifyEmailPage inline public routes
 * Preserves: all existing routes exactly
 */

import { Switch, Route, Redirect } from "wouter";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/components/theme-provider";
import { LocaleProvider } from "@/hooks/use-locale";
import LandingPage from "@/pages/landing";
import LoginPage from "@/pages/login";
import RequestAccessPage from "@/pages/request-access";
import SetPasswordPage from "@/pages/set-password";
import AskPage from "@/pages/ask";
import AdminPage from "@/pages/admin";
import AdminDashboardPage from "@/pages/admin-dashboard";
import AdminBenchmarkPage from "@/pages/admin-benchmark";
import UserActivityPage from "@/pages/admin/user-activity";
import BenchmarkReportPage from "@/pages/benchmark-report";
import ClinicalToolsPage from "@/pages/clinical-tools-expanded";
import ResearchToolsPage from "@/pages/research-tools";
import ToolsPage from "@/pages/tools-epocrates";
import ComparePage from "@/pages/compare";
import GovernancePage from "@/pages/governance";
import AdminAnalyticsPage from "@/pages/admin-analytics";
import VisionAnalysisPage from "@/pages/vision-analysis";
import AskOEPage from "@/pages/ask-oe";
import Hardest10Page from "@/pages/hardest10";
import PreProcedureSafetyPage from "@/pages/pre-procedure-safety";
import SafetyWorkspacePage from "@/pages/safety-workspace";
import BookmarksPage from "@/pages/bookmarks";
import DrugInteractionsPage from "@/pages/drug-interactions";
import PatientExportPage from "@/pages/patient-export";
import APIKeysPage from "@/pages/api-keys";
import ClinicDashboardPage from "@/pages/clinic-dashboard";
import PaperAlertsPage from "@/pages/paper-alerts";
import SessionReportPage from "@/pages/session-report";
import ComplicationProtocolPage from "@/pages/complication-protocol";
import ChairsideEmergencyPage from "@/pages/chairside-emergency";
import DailyClinicHomePage from "@/pages/daily-clinic-home";
import ReadinessDashboardPage from "@/pages/readiness-dashboard";
import VisionFollowupPage from "@/pages/vision-followup";
import HyaluronidaseCalcPage from "@/pages/hyaluronidase";
import CaseLogPage from "@/pages/case-log";
import ClinicHomePage from "@/pages/clinic-home";
import ScenarioEntryPage from "@/pages/scenario-entry";
import EmergencyPage from "@/pages/emergency";
import NetworkSafetyWorkspacePage from "@/pages/network-safety-workspace";
import RiskIntelligencePage from "@/pages/risk-intelligence";
import ComplicationMonitorPage from "@/pages/complication-monitor";
import OrgAnalyticsPage from "@/pages/org-analytics";
import ComplicationDecisionPage from "@/pages/complication-decision";
import ComplicationDecisionV2Page from "@/pages/complication-decision-v2";
import WorkflowPage from "@/pages/workflow";
import IngestPage from "@/pages/ingest";
import { ClinicProvider } from "@/hooks/use-clinic-context";
import NotFound from "@/pages/not-found";
import { isAuthenticated } from "@/lib/auth";
import React from "react";

// ─── Reset password page ──────────────────────────────────────────────────────
function ResetPasswordPage() {
  const [token] = React.useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("token") || "";
  });
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [status, setStatus] = React.useState<"idle" | "loading" | "done" | "error">("idle");
  const [message, setMessage] = React.useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) { setMessage("Passwords do not match."); setStatus("error"); return; }
    if (password.length < 8) { setMessage("Password must be at least 8 characters."); setStatus("error"); return; }
    setStatus("loading");
    try {
      const res = await fetch("/api/ops/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      });
      const data = await res.json();
      if (res.ok) {
        setStatus("done");
        setMessage(data.message || "Password updated. You can now log in.");
      } else {
        setStatus("error");
        setMessage(data.detail || "Reset failed. The link may have expired.");
      }
    } catch {
      setStatus("error");
      setMessage("Network error. Please try again.");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold">Reset your password</h1>
          <p className="text-muted-foreground mt-2 text-sm">Enter your new password below.</p>
        </div>
        {status === "done" ? (
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-6 text-center">
            <p className="text-sm text-emerald-600 dark:text-emerald-400 font-semibold mb-2">✓ {message}</p>
            <a href="/login" className="text-sm text-primary hover:underline">Go to login →</a>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 rounded-2xl border border-border bg-card p-6 shadow-sm">
            {message && status === "error" && (
              <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-sm text-red-600 dark:text-red-400">{message}</div>
            )}
            <div>
              <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">New password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder="At least 8 characters"
                required
                minLength={8}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Confirm password</label>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder="Repeat your new password"
                required
              />
            </div>
            <button
              type="submit"
              disabled={status === "loading"}
              className="w-full py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold text-sm disabled:opacity-40 hover:bg-primary/90 transition-colors"
            >
              {status === "loading" ? "Updating…" : "Set new password"}
            </button>
            <p className="text-center text-xs text-muted-foreground">
              <a href="/login" className="hover:text-foreground transition-colors">Back to login</a>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}

// ─── Email verify page ────────────────────────────────────────────────────────
function VerifyEmailPage() {
  const [status, setStatus] = React.useState<"loading" | "done" | "error">("loading");
  const [message, setMessage] = React.useState("");

  React.useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token") || "";
    if (!token) { setStatus("error"); setMessage("No verification token found in the link."); return; }
    fetch("/api/ops/auth/verify-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.access_token) {
          setStatus("done");
          setMessage("Email verified successfully. Redirecting…");
          setTimeout(() => { window.location.href = "/start"; }, 1500);
        } else {
          setStatus("error");
          setMessage(data.detail || "Verification failed. The link may have expired.");
        }
      })
      .catch(() => { setStatus("error"); setMessage("Network error. Please try again."); });
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm text-center">
        {status === "loading" && (
          <div>
            <div className="w-10 h-10 border-2 border-primary/30 border-t-primary rounded-full animate-spin mx-auto mb-4" />
            <p className="text-sm text-muted-foreground">Verifying your email…</p>
          </div>
        )}
        {status === "done" && (
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-6">
            <p className="text-2xl mb-3">✓</p>
            <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">{message}</p>
          </div>
        )}
        {status === "error" && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-6">
            <p className="text-2xl mb-3">✕</p>
            <p className="text-sm text-red-600 dark:text-red-400">{message}</p>
            <a href="/login" className="inline-block mt-4 text-sm text-primary hover:underline">Go to login</a>
          </div>
        )}
      </div>
    </div>
  );
}

function ProtectedRoute({ component: Component }: { component: React.ComponentType }) {
  if (!isAuthenticated()) {
    return <Redirect to="/login" />;
  }
  return <Component />;
}

function Router() {
  return (
    <Switch>
      {/* Public routes */}
      <Route path="/governance" component={GovernancePage} />
      <Route path="/welcome" component={LandingPage} />
      <Route path="/login" component={LoginPage} />
      <Route path="/tools" component={ToolsPage} />
      <Route path="/compare" component={ComparePage} />
      <Route path="/request-access" component={RequestAccessPage} />
      <Route path="/set-password" component={SetPasswordPage} />
      <Route path="/reset-password" component={ResetPasswordPage} />
      <Route path="/verify-email" component={VerifyEmailPage} />

      {/* Protected routes */}
      <Route path="/">
        {() => <Redirect to="/ask" />}
      </Route>
      <Route path="/home">
        {() => <ProtectedRoute component={ClinicHomePage} />}
      </Route>
      <Route path="/start">
        {() => <ProtectedRoute component={ScenarioEntryPage} />}
      </Route>
      <Route path="/emergency">
        {() => <ProtectedRoute component={EmergencyPage} />}
      </Route>
      <Route path="/ask">
        {() => <ProtectedRoute component={AskPage} />}
      </Route>
      <Route path="/admin/dashboard">
        {() => <ProtectedRoute component={AdminDashboardPage} />}
      </Route>
      <Route path="/admin">
        {() => <ProtectedRoute component={AdminPage} />}
      </Route>
      <Route path="/admin/analytics">
        {() => <ProtectedRoute component={AdminAnalyticsPage} />}
      </Route>
      <Route path="/admin/benchmark">
        {() => <ProtectedRoute component={AdminBenchmarkPage} />}
      </Route>
      <Route path="/admin/benchmark/report">
        {() => <ProtectedRoute component={BenchmarkReportPage} />}
      </Route>
      <Route path="/admin/user-activity">
        {() => <ProtectedRoute component={UserActivityPage} />}
      </Route>
      <Route path="/admin/readiness">
        {() => <ProtectedRoute component={ReadinessDashboardPage} />}
      </Route>
      <Route path="/clinical-tools">
        {() => <ProtectedRoute component={ClinicalToolsPage} />}
      </Route>
      <Route path="/research-tools">
        {() => <ProtectedRoute component={ResearchToolsPage} />}
      </Route>
      <Route path="/visual-counsel">
        {() => <Redirect to="/vision-analysis" />}
      </Route>
      <Route path="/vision-analysis">
        {() => <ProtectedRoute component={VisionAnalysisPage} />}
      </Route>
      <Route path="/vision-followup">
        {() => <ProtectedRoute component={VisionFollowupPage} />}
      </Route>
      <Route path="/ask-oe">
        {() => <ProtectedRoute component={AskOEPage} />}
      </Route>
      <Route path="/hardest-10">
        {() => <ProtectedRoute component={Hardest10Page} />}
      </Route>
      <Route path="/safety-check">
        {() => <ProtectedRoute component={PreProcedureSafetyPage} />}
      </Route>
      <Route path="/safety-workspace">
        {() => <ProtectedRoute component={SafetyWorkspacePage} />}
      </Route>
      <Route path="/bookmarks">
        {() => <ProtectedRoute component={BookmarksPage} />}
      </Route>
      <Route path="/drug-interactions">
        {() => <ProtectedRoute component={DrugInteractionsPage} />}
      </Route>
      <Route path="/patient-export">
        {() => <ProtectedRoute component={PatientExportPage} />}
      </Route>
      <Route path="/api-keys">
        {() => <ProtectedRoute component={APIKeysPage} />}
      </Route>
      <Route path="/clinic-dashboard">
        {() => <ProtectedRoute component={ClinicDashboardPage} />}
      </Route>
      <Route path="/paper-alerts">
        {() => <ProtectedRoute component={PaperAlertsPage} />}
      </Route>
      <Route path="/session-report">
        {() => <ProtectedRoute component={SessionReportPage} />}
      </Route>
      <Route path="/complications">
        {() => <ProtectedRoute component={ComplicationProtocolPage} />}
      </Route>
      <Route path="/chairside">
        {() => <ProtectedRoute component={ChairsideEmergencyPage} />}
      </Route>
      <Route path="/daily-home">
        {() => <ProtectedRoute component={DailyClinicHomePage} />}
      </Route>
      <Route path="/hyaluronidase">
        {() => <ProtectedRoute component={HyaluronidaseCalcPage} />}
      </Route>
      <Route path="/case-log">
        {() => <ProtectedRoute component={CaseLogPage} />}
      </Route>
      <Route path="/network-safety-workspace">
        {() => <ProtectedRoute component={NetworkSafetyWorkspacePage} />}
      </Route>
      <Route path="/risk-intelligence">
        {() => <ProtectedRoute component={RiskIntelligencePage} />}
      </Route>
      <Route path="/complication-monitor">
        {() => <ProtectedRoute component={ComplicationMonitorPage} />}
      </Route>
      <Route path="/org-analytics">
        {() => <ProtectedRoute component={OrgAnalyticsPage} />}
      </Route>
      <Route path="/decide">
        {() => <ProtectedRoute component={ComplicationDecisionV2Page} />}
      </Route>
      <Route path="/workflow">
        {() => <ProtectedRoute component={WorkflowPage} />}
      </Route>
      <Route path="/admin/ingest">
        {() => <ProtectedRoute component={IngestPage} />}
      </Route>
      <Route component={NotFound} />
    </Switch>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <LocaleProvider>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
            <ClinicProvider>
              <Toaster />
              <Router />
            </ClinicProvider>
          </TooltipProvider>
        </QueryClientProvider>
      </LocaleProvider>
    </ThemeProvider>
  );
}
