import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Play,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  BarChart3,
  FileText,
  AlertTriangle,
  Trophy,
  Shield,
  Sparkles,
  Globe,
  Wrench,
  ArrowLeft,
  TrendingUp,
} from "lucide-react";
import { Link } from "wouter";

interface ReportSummary {
  total_questions: number;
  questions_en: number;
  questions_fr: number;
  overall_score: number;
  grade: string;
  citation_rate: number;
  avg_aci: number;
  median_aci: number;
  aci_std: number;
  tool_triggering_rate: number;
  protocol_activation_rate_safety: number;
  error_rate: number;
  avg_latency_s: number;
  p95_latency_s: number;
}

interface ACIDistribution {
  high_confidence: { count: number; range: string };
  moderate_confidence: { count: number; range: string };
  low_confidence: { count: number; range: string };
  no_score: { count: number };
}

interface LanguagePerformance {
  english: { questions: number; citation_rate: number; avg_aci: number };
  french: { questions: number; citation_rate: number; avg_aci: number };
}

interface CategoryBreakdown {
  [key: string]: {
    label: string;
    questions: number;
    citation_rate: number;
    avg_aci: number;
    tools_triggered: number;
    protocols_triggered: number;
  };
}

interface PilotKPI {
  metric: string;
  value: string;
  assessment: string;
}

interface QuestionResult {
  index: number;
  query: string;
  language: string;
  category: string;
  aci: number;
  has_citations: boolean;
  n_refs: number;
  n_tools: number;
  tool_names?: string[];
  has_protocol: boolean;
  evidence_grade: string;
  latency_s: number;
  status: string;
  answer_preview?: string;
  error?: string;
}

interface UnilabsReport {
  report_title: string;
  report_subtitle: string;
  generated_at: string;
  engine_version: string;
  mode: string;
  total_wall_time_s: number;
  summary: ReportSummary;
  aci_distribution: ACIDistribution;
  language_performance: LanguagePerformance;
  category_breakdown: CategoryBreakdown;
  differentiators_vs_generic_ai: {
    aestheticite: Record<string, any>;
    generic_medical_ai: Record<string, any>;
  };
  pilot_kpi_mapping: Record<string, PilotKPI>;
  results_en: QuestionResult[];
  results_fr: QuestionResult[];
}

function GradeDisplay({ grade, score }: { grade: string; score: number }) {
  const colorMap: Record<string, string> = {
    "A": "text-emerald-600 dark:text-emerald-400",
    "B+": "text-blue-600 dark:text-blue-400",
    "B": "text-blue-500 dark:text-blue-300",
    "C": "text-amber-600 dark:text-amber-400",
    "D": "text-red-600 dark:text-red-400",
  };
  return (
    <div className="text-center" data-testid="text-report-grade">
      <div className={`text-6xl font-bold ${colorMap[grade] || "text-muted-foreground"}`}>{grade}</div>
      <div className="text-lg text-muted-foreground mt-1">{score}%</div>
    </div>
  );
}

function KPICard({ label, kpi }: { label: string; kpi: PilotKPI }) {
  const assessColor = kpi.assessment === "Strong" || kpi.assessment === "Ready" || kpi.assessment === "Active"
    ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
    : kpi.assessment === "Moderate"
    ? "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
    : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300";

  return (
    <div className="p-4 rounded-lg border bg-card" data-testid={`kpi-${label}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium capitalize">{label.replace(/_/g, " ")}</span>
        <Badge className={assessColor}>{kpi.assessment}</Badge>
      </div>
      <p className="text-xs text-muted-foreground mb-1">{kpi.metric}</p>
      <p className="text-sm font-medium">{kpi.value}</p>
    </div>
  );
}

function ComparisonRow({ feature, ours, theirs }: { feature: string; ours: any; theirs: any }) {
  const oursDisplay = typeof ours === "boolean" ? (ours ? <CheckCircle className="w-4 h-4 text-emerald-500" /> : <XCircle className="w-4 h-4 text-red-400" />) : <span className="text-sm">{String(ours)}</span>;
  const theirsDisplay = typeof theirs === "boolean" ? (theirs ? <CheckCircle className="w-4 h-4 text-emerald-500" /> : <XCircle className="w-4 h-4 text-red-400" />) : <span className="text-sm text-muted-foreground">{String(theirs)}</span>;

  return (
    <div className="grid grid-cols-3 gap-4 py-3 border-b last:border-b-0 items-center" data-testid={`compare-${feature}`}>
      <span className="text-sm capitalize">{feature.replace(/_/g, " ")}</span>
      <div className="flex justify-center">{oursDisplay}</div>
      <div className="flex justify-center">{theirsDisplay}</div>
    </div>
  );
}

function QuestionResultRow({ r }: { r: QuestionResult }) {
  return (
    <div className="p-3 rounded-lg border bg-card" data-testid={`question-result-${r.index}`}>
      <div className="flex items-start justify-between gap-2 mb-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="outline">{r.language.toUpperCase()}</Badge>
          <Badge variant="secondary">{r.category}</Badge>
          {r.has_protocol && <Badge className="bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300">Protocol</Badge>}
          {r.n_tools > 0 && <Badge className="bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300">Tools: {r.tool_names?.join(", ") || r.n_tools}</Badge>}
        </div>
        <div className="flex items-center gap-2">
          {r.has_citations ? <CheckCircle className="w-4 h-4 text-emerald-500" /> : <XCircle className="w-4 h-4 text-red-400" />}
          <span className="text-sm font-mono">ACI {r.aci}</span>
          <span className="text-xs text-muted-foreground">{r.latency_s}s</span>
        </div>
      </div>
      <p className="text-sm">{r.query}</p>
      {r.error && <p className="text-xs text-red-500 mt-1">{r.error}</p>}
      {r.answer_preview && !r.error && (
        <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{r.answer_preview}</p>
      )}
    </div>
  );
}

export default function BenchmarkReportPage() {
  const [report, setReport] = useState<UnilabsReport | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const adminApiKey = localStorage.getItem("admin_api_key") || "";

  const runReport = async () => {
    setIsRunning(true);
    setError(null);
    try {
      const res = await fetch("/api/admin/benchmark/gold/report", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Admin-Key": adminApiKey,
        },
        body: JSON.stringify({ mode: "fast" }),
      });
      if (!res.ok) throw new Error(`Benchmark failed: ${res.status}`);
      const data = await res.json();
      setReport(data);
    } catch (e: any) {
      setError(e.message || "Benchmark failed");
    } finally {
      setIsRunning(false);
    }
  };

  if (!adminApiKey) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle>Admin Access Required</CardTitle>
            <CardDescription>Log in to the admin panel first.</CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/admin">
              <Button className="w-full" data-testid="button-go-admin">Go to Admin Login</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-card/50 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-3">
            <Trophy className="w-6 h-6 text-primary" />
            <div>
              <h1 className="font-bold text-lg" data-testid="text-report-title">Unilabs Pilot Report</h1>
              <p className="text-xs text-muted-foreground">AesthetiCite Gold Benchmark</p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Link href="/admin/benchmark">
              <Button variant="ghost" size="sm" data-testid="button-back-benchmark">
                <ArrowLeft className="w-4 h-4 mr-1" /> Benchmark
              </Button>
            </Link>
            <Link href="/admin">
              <Button variant="ghost" size="sm" data-testid="button-back-admin">Admin</Button>
            </Link>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {!report && !isRunning && (
          <Card data-testid="card-run-report">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="w-5 h-5" />
                Unilabs France Pilot Benchmark
              </CardTitle>
              <CardDescription>
                Run 40 curated clinical questions (30 English + 10 French) through the VeriDoc v2 engine.
                Produces a professional report with KPIs mapped to the Unilabs pilot proposal.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="text-center p-4 rounded-lg bg-muted/50">
                  <div className="text-2xl font-bold text-primary">40</div>
                  <div className="text-xs text-muted-foreground">Questions</div>
                </div>
                <div className="text-center p-4 rounded-lg bg-muted/50">
                  <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">2</div>
                  <div className="text-xs text-muted-foreground">Languages</div>
                </div>
                <div className="text-center p-4 rounded-lg bg-muted/50">
                  <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">7</div>
                  <div className="text-xs text-muted-foreground">Categories</div>
                </div>
                <div className="text-center p-4 rounded-lg bg-muted/50">
                  <div className="text-2xl font-bold text-purple-600 dark:text-purple-400">5</div>
                  <div className="text-xs text-muted-foreground">KPI Dimensions</div>
                </div>
              </div>

              <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                  <div className="text-sm">
                    <p className="font-medium text-amber-800 dark:text-amber-200">This will take several minutes</p>
                    <p className="text-amber-700 dark:text-amber-300">
                      Each question runs through the full VeriDoc v2 pipeline with evidence retrieval, claim verification, ACI scoring, and tool execution. Expect 10-20 minutes total.
                    </p>
                  </div>
                </div>
              </div>

              {error && (
                <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg p-4">
                  <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
                </div>
              )}

              <Button onClick={runReport} disabled={isRunning} className="w-full" data-testid="button-run-report">
                <Play className="w-4 h-4 mr-2" />
                Generate Unilabs Report
              </Button>
            </CardContent>
          </Card>
        )}

        {isRunning && (
          <Card>
            <CardContent className="py-16">
              <div className="flex flex-col items-center gap-4">
                <Loader2 className="w-12 h-12 animate-spin text-primary" />
                <div className="text-center">
                  <p className="font-medium text-lg">Running Benchmark...</p>
                  <p className="text-sm text-muted-foreground mt-1">Processing 40 questions through VeriDoc v2 engine</p>
                  <p className="text-xs text-muted-foreground mt-2">This may take 10-20 minutes. Do not close this page.</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {report && !isRunning && (
          <Tabs defaultValue="executive" className="w-full">
            <TabsList data-testid="tabs-report" className="flex flex-wrap">
              <TabsTrigger value="executive" data-testid="tab-executive">Executive Summary</TabsTrigger>
              <TabsTrigger value="kpis" data-testid="tab-kpis">Pilot KPIs</TabsTrigger>
              <TabsTrigger value="comparison" data-testid="tab-comparison">vs Generic AI</TabsTrigger>
              <TabsTrigger value="categories" data-testid="tab-categories">Categories</TabsTrigger>
              <TabsTrigger value="questions" data-testid="tab-questions">Question Details</TabsTrigger>
            </TabsList>

            <TabsContent value="executive" className="space-y-6 mt-6">
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <div>
                  <h2 className="text-2xl font-bold" data-testid="text-report-heading">{report.report_title}</h2>
                  <p className="text-muted-foreground">{report.report_subtitle}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Generated {new Date(report.generated_at).toLocaleString()} | {report.engine_version} | Mode: {report.mode} | Wall time: {report.total_wall_time_s}s
                  </p>
                </div>
                <GradeDisplay grade={report.summary.grade} score={report.summary.overall_score} />
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                <Card data-testid="stat-citation-rate">
                  <CardContent className="pt-4 pb-4 text-center">
                    <div className="text-3xl font-bold text-primary">{report.summary.citation_rate}%</div>
                    <div className="text-xs text-muted-foreground mt-1">Citation Rate</div>
                  </CardContent>
                </Card>
                <Card data-testid="stat-avg-aci">
                  <CardContent className="pt-4 pb-4 text-center">
                    <div className="text-3xl font-bold text-emerald-600 dark:text-emerald-400">{report.summary.avg_aci}</div>
                    <div className="text-xs text-muted-foreground mt-1">Avg ACI (0-10)</div>
                  </CardContent>
                </Card>
                <Card data-testid="stat-tool-rate">
                  <CardContent className="pt-4 pb-4 text-center">
                    <div className="text-3xl font-bold text-purple-600 dark:text-purple-400">{report.summary.tool_triggering_rate}%</div>
                    <div className="text-xs text-muted-foreground mt-1">Tool Triggering</div>
                  </CardContent>
                </Card>
                <Card data-testid="stat-protocol-rate">
                  <CardContent className="pt-4 pb-4 text-center">
                    <div className="text-3xl font-bold text-red-600 dark:text-red-400">{report.summary.protocol_activation_rate_safety}%</div>
                    <div className="text-xs text-muted-foreground mt-1">Safety Protocol</div>
                  </CardContent>
                </Card>
                <Card data-testid="stat-latency">
                  <CardContent className="pt-4 pb-4 text-center">
                    <div className="text-3xl font-bold text-blue-600 dark:text-blue-400">{report.summary.avg_latency_s}s</div>
                    <div className="text-xs text-muted-foreground mt-1">Avg Latency</div>
                  </CardContent>
                </Card>
                <Card data-testid="stat-error-rate">
                  <CardContent className="pt-4 pb-4 text-center">
                    <div className="text-3xl font-bold text-muted-foreground">{report.summary.error_rate}%</div>
                    <div className="text-xs text-muted-foreground mt-1">Error Rate</div>
                  </CardContent>
                </Card>
              </div>

              <div className="grid md:grid-cols-2 gap-6">
                <Card data-testid="card-aci-distribution">
                  <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                      <TrendingUp className="w-4 h-4" />
                      ACI Score Distribution
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {[
                      { label: "High Confidence", data: report.aci_distribution.high_confidence, color: "bg-emerald-500" },
                      { label: "Moderate Confidence", data: report.aci_distribution.moderate_confidence, color: "bg-amber-500" },
                      { label: "Low Confidence", data: report.aci_distribution.low_confidence, color: "bg-red-500" },
                    ].map(({ label, data, color }) => (
                      <div key={label} className="space-y-1">
                        <div className="flex justify-between text-sm">
                          <span>{label} ({data.range})</span>
                          <span className="font-medium">{data.count}</span>
                        </div>
                        <div className="h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className={`h-full ${color} rounded-full transition-all`}
                            style={{ width: `${(data.count / report.summary.total_questions) * 100}%` }}
                          />
                        </div>
                      </div>
                    ))}
                    <div className="flex justify-between text-sm text-muted-foreground pt-2 border-t">
                      <span>No Score / Error</span>
                      <span>{report.aci_distribution.no_score.count}</span>
                    </div>
                  </CardContent>
                </Card>

                <Card data-testid="card-language-performance">
                  <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                      <Globe className="w-4 h-4" />
                      Language Performance
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {Object.entries(report.language_performance).map(([lang, perf]) => (
                      <div key={lang} className="p-3 rounded-lg bg-muted/30 space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Badge variant="outline">{lang === "english" ? "EN" : "FR"}</Badge>
                            <span className="font-medium capitalize text-sm">{lang}</span>
                          </div>
                          <span className="text-sm text-muted-foreground">{perf.questions} questions</span>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-sm">
                          <div>
                            <span className="text-muted-foreground">Citation Rate: </span>
                            <span className="font-medium">{perf.citation_rate}%</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Avg ACI: </span>
                            <span className="font-medium">{perf.avg_aci}/10</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </div>

              <div className="flex justify-end">
                <Button variant="outline" onClick={runReport} disabled={isRunning} data-testid="button-rerun">
                  <Play className="w-4 h-4 mr-2" /> Re-run Benchmark
                </Button>
              </div>
            </TabsContent>

            <TabsContent value="kpis" className="space-y-6 mt-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Sparkles className="w-5 h-5" />
                    Pilot KPI Mapping
                  </CardTitle>
                  <CardDescription>
                    How benchmark results map to the success metrics defined in the Unilabs France pilot proposal.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid md:grid-cols-2 gap-4">
                    {Object.entries(report.pilot_kpi_mapping).map(([key, kpi]) => (
                      <KPICard key={key} label={key} kpi={kpi} />
                    ))}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="comparison" className="space-y-6 mt-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Shield className="w-5 h-5" />
                    AesthetiCite vs Generic Medical AI
                  </CardTitle>
                  <CardDescription>
                    Feature comparison highlighting AesthetiCite's differentiation for aesthetic medicine.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="border rounded-lg overflow-hidden">
                    <div className="grid grid-cols-3 gap-4 py-3 px-4 bg-muted/50 font-medium text-sm border-b">
                      <span>Feature</span>
                      <span className="text-center">AesthetiCite</span>
                      <span className="text-center">Generic AI</span>
                    </div>
                    <div className="px-4">
                      {Object.keys(report.differentiators_vs_generic_ai.aestheticite).map((feature) => (
                        <ComparisonRow
                          key={feature}
                          feature={feature}
                          ours={report.differentiators_vs_generic_ai.aestheticite[feature]}
                          theirs={report.differentiators_vs_generic_ai.generic_medical_ai[feature]}
                        />
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="categories" className="space-y-6 mt-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="w-5 h-5" />
                    Category Breakdown
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {Object.entries(report.category_breakdown).map(([key, cat]) => (
                      <div key={key} className="p-4 rounded-lg border bg-card" data-testid={`category-${key}`}>
                        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{cat.label}</span>
                            <Badge variant="secondary">{cat.questions} questions</Badge>
                          </div>
                          <span className="text-sm font-mono">ACI {cat.avg_aci}/10</span>
                        </div>
                        <div className="space-y-2">
                          <div className="space-y-1">
                            <div className="flex justify-between text-xs">
                              <span>Citation Rate</span>
                              <span>{cat.citation_rate}%</span>
                            </div>
                            <Progress value={cat.citation_rate} className="h-1.5" />
                          </div>
                        </div>
                        <div className="flex gap-4 mt-3 text-xs text-muted-foreground flex-wrap">
                          {cat.tools_triggered > 0 && (
                            <span className="flex items-center gap-1">
                              <Wrench className="w-3 h-3" /> {cat.tools_triggered} tools triggered
                            </span>
                          )}
                          {cat.protocols_triggered > 0 && (
                            <span className="flex items-center gap-1">
                              <AlertTriangle className="w-3 h-3" /> {cat.protocols_triggered} protocols activated
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="questions" className="space-y-6 mt-6">
              <Tabs defaultValue="all">
                <TabsList>
                  <TabsTrigger value="all">All ({report.results_en.length + report.results_fr.length})</TabsTrigger>
                  <TabsTrigger value="en">English ({report.results_en.length})</TabsTrigger>
                  <TabsTrigger value="fr">French ({report.results_fr.length})</TabsTrigger>
                </TabsList>

                <TabsContent value="all" className="mt-4">
                  <ScrollArea className="h-[600px]">
                    <div className="space-y-3">
                      {[...report.results_en, ...report.results_fr].map((r) => (
                        <QuestionResultRow key={`${r.language}-${r.index}`} r={r} />
                      ))}
                    </div>
                  </ScrollArea>
                </TabsContent>

                <TabsContent value="en" className="mt-4">
                  <ScrollArea className="h-[600px]">
                    <div className="space-y-3">
                      {report.results_en.map((r) => (
                        <QuestionResultRow key={`en-${r.index}`} r={r} />
                      ))}
                    </div>
                  </ScrollArea>
                </TabsContent>

                <TabsContent value="fr" className="mt-4">
                  <ScrollArea className="h-[600px]">
                    <div className="space-y-3">
                      {report.results_fr.map((r) => (
                        <QuestionResultRow key={`fr-${r.index}`} r={r} />
                      ))}
                    </div>
                  </ScrollArea>
                </TabsContent>
              </Tabs>
            </TabsContent>
          </Tabs>
        )}
      </main>
    </div>
  );
}
