// client/src/App.tsx
// ── CHANGE: added ComplicationProtocolPage import and /complications route

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
import AdminBenchmarkPage from "@/pages/admin-benchmark";
import BenchmarkReportPage from "@/pages/benchmark-report";
import ClinicalToolsPage from "@/pages/clinical-tools";
import ResearchToolsPage from "@/pages/research-tools";
import ToolsPage from "@/pages/tools";
import ComparePage from "@/pages/compare";
import GovernancePage from "@/pages/governance";
import AdminAnalyticsPage from "@/pages/admin-analytics";
import VisualCounselingPage from "@/pages/visual-counseling";
import AskOEPage from "@/pages/ask-oe";
import Hardest10Page from "@/pages/hardest10";
import PreProcedureSafetyPage from "@/pages/pre-procedure-safety";
import BookmarksPage from "@/pages/bookmarks";
import DrugInteractionsPage from "@/pages/drug-interactions";
import PatientExportPage from "@/pages/patient-export";
import APIKeysPage from "@/pages/api-keys";
import ClinicDashboardPage from "@/pages/clinic-dashboard";
import PaperAlertsPage from "@/pages/paper-alerts";
import SessionReportPage from "@/pages/session-report";
import ComplicationProtocolPage from "@/pages/complication-protocol"; // ← NEW
import NotFound from "@/pages/not-found";
import { isAuthenticated } from "@/lib/auth";

function ProtectedRoute({ component: Component }: { component: React.ComponentType }) {
  if (!isAuthenticated()) {
    return <Redirect to="/login" />;
  }
  return <Component />;
}

function Router() {
  return (
    <Switch>
      <Route path="/governance" component={GovernancePage} />
      <Route path="/welcome" component={LandingPage} />
      <Route path="/login" component={LoginPage} />
      <Route path="/tools" component={ToolsPage} />
      <Route path="/compare" component={ComparePage} />
      <Route path="/request-access" component={RequestAccessPage} />
      <Route path="/set-password" component={SetPasswordPage} />
      <Route path="/">
        {() => <ProtectedRoute component={AskPage} />}
      </Route>
      <Route path="/ask">
        {() => <ProtectedRoute component={AskPage} />}
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
      <Route path="/clinical-tools">
        {() => <ProtectedRoute component={ClinicalToolsPage} />}
      </Route>
      <Route path="/research-tools">
        {() => <ProtectedRoute component={ResearchToolsPage} />}
      </Route>
      <Route path="/visual-counsel">
        {() => <ProtectedRoute component={VisualCounselingPage} />}
      </Route>
      <Route path="/ask-oe">
        {() => <ProtectedRoute component={AskOEPage} />}
      </Route>
      <Route path="/hardest-10">
        {() => <ProtectedRoute component={Hardest10Page} />}
      </Route>
      {/* ── SAFETY CLUSTER ── */}
      <Route path="/safety-check">
        {() => <ProtectedRoute component={PreProcedureSafetyPage} />}
      </Route>
      <Route path="/complications">                                    {/* ← NEW */}
        {() => <ProtectedRoute component={ComplicationProtocolPage} />}
      </Route>
      <Route path="/session-report">
        {() => <ProtectedRoute component={SessionReportPage} />}
      </Route>
      {/* ── OTHER ── */}
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
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <ThemeProvider>
      <LocaleProvider>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
            <Toaster />
            <Router />
          </TooltipProvider>
        </QueryClientProvider>
      </LocaleProvider>
    </ThemeProvider>
  );
}

export default App;
