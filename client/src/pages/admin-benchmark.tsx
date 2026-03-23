import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
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
  Syringe,
  Zap,
  Pill,
  Dna,
  ClipboardList
} from "lucide-react";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { Link } from "wouter";

interface BenchmarkSummary {
  version: string;
  name: string;
  description: string;
  total_questions: number;
  categories: Array<{ id: string; name: string; weight: number }>;
  category_counts: Record<string, number>;
  difficulty_distribution: Record<string, number>;
  scoring_weights: Record<string, { weight: number; description: string }>;
}

interface BenchmarkResult {
  version: string;
  run_id: string;
  run_date: string;
  total_questions: number;
  questions_answered: number;
  questions_refused: number;
  correct_refusals: number;
  incorrect_refusals: number;
  category_scores: Record<string, number>;
  overall_score: number;
  average_latency_ms: number;
  grade: string;
  question_results: Array<{
    question_id: string;
    category: string;
    difficulty: string;
    question: string;
    answer: string;
    citations_count: number;
    expected_citations_min: number;
    evidence_level: string | null;
    evidence_level_expected: string | null;
    keywords_found: string[];
    keywords_expected: string[];
    was_refused: boolean;
    should_refuse: boolean;
    latency_ms: number;
    scores: Record<string, number>;
    total_score: number;
  }>;
}

function getGradeColor(grade: string): string {
  if (grade.startsWith("A")) return "text-green-600 dark:text-green-400";
  if (grade.startsWith("B")) return "text-blue-600 dark:text-blue-400";
  if (grade.startsWith("C")) return "text-yellow-600 dark:text-yellow-400";
  if (grade.startsWith("D")) return "text-orange-600 dark:text-orange-400";
  return "text-red-600 dark:text-red-400";
}

function getDifficultyColor(difficulty: string): string {
  switch (difficulty) {
    case "critical": return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
    case "hard": return "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200";
    default: return "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200";
  }
}

function getCategoryIcon(category: string) {
  const iconClass = "w-4 h-4";
  switch (category) {
    case "injectables": return <Syringe className={iconClass} />;
    case "energy_devices": return <Zap className={iconClass} />;
    case "complications": return <AlertTriangle className={iconClass} />;
    case "dosing": return <Pill className={iconClass} />;
    case "anatomy": return <Dna className={iconClass} />;
    default: return <ClipboardList className={iconClass} />;
  }
}

export default function AdminBenchmark() {
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [benchmarkResult, setBenchmarkResult] = useState<BenchmarkResult | null>(null);
  
  const adminApiKey = localStorage.getItem("admin_api_key") || "";
  
  const fetchWithAdminKey = async (url: string, options?: RequestInit) => {
    const res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-Admin-Key": adminApiKey,
        ...options?.headers,
      },
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status}`);
    return res.json();
  };

  const { data: summary, isLoading: summaryLoading } = useQuery<BenchmarkSummary>({
    queryKey: ["/api/admin/benchmark/summary", adminApiKey],
    queryFn: () => fetchWithAdminKey("/api/admin/benchmark/summary"),
    enabled: !!adminApiKey
  });
  
  const runBenchmark = useMutation({
    mutationFn: async () => {
      return fetchWithAdminKey("/api/admin/benchmark/run", {
        method: "POST",
        body: JSON.stringify({
          categories: selectedCategory === "all" ? null : [selectedCategory],
          max_questions: 20,
          mode: "clinic"
        })
      });
    },
    onSuccess: (data) => {
      setBenchmarkResult(data);
      queryClient.invalidateQueries({ queryKey: ["/api/admin/benchmark/summary"] });
    }
  });
  
  if (!adminApiKey) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle>Admin Access Required</CardTitle>
            <CardDescription>
              Please log in to the admin panel first to access the benchmark.
            </CardDescription>
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
      <header className="border-b bg-card/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Trophy className="w-6 h-6 text-primary" />
            <div>
              <h1 className="font-bold text-lg" data-testid="text-benchmark-title">AAMB Benchmark</h1>
              <p className="text-xs text-muted-foreground">AesthetiCite Aesthetic Medicine Benchmark</p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Link href="/admin/benchmark/report">
              <Button variant="default" size="sm" data-testid="button-unilabs-report">Unilabs Report</Button>
            </Link>
            <Link href="/admin">
              <Button variant="ghost" size="sm" data-testid="button-back-admin">Back to Admin</Button>
            </Link>
          </div>
        </div>
      </header>
      
      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <Tabs defaultValue="overview" className="w-full">
          <TabsList data-testid="tabs-benchmark">
            <TabsTrigger value="overview" data-testid="tab-overview">Overview</TabsTrigger>
            <TabsTrigger value="run" data-testid="tab-run">Run Benchmark</TabsTrigger>
            <TabsTrigger value="results" data-testid="tab-results" disabled={!benchmarkResult}>Results</TabsTrigger>
          </TabsList>
          
          <TabsContent value="overview" className="space-y-6 mt-6">
            {summaryLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
              </div>
            ) : summary ? (
              <>
                <Card data-testid="card-benchmark-info">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <BarChart3 className="w-5 h-5" />
                      {summary.name}
                    </CardTitle>
                    <CardDescription>{summary.description}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="text-center p-4 rounded-lg bg-muted/50" data-testid="stat-total-questions">
                        <div className="text-3xl font-bold text-primary">{summary.total_questions}</div>
                        <div className="text-sm text-muted-foreground">Total Questions</div>
                      </div>
                      <div className="text-center p-4 rounded-lg bg-muted/50" data-testid="stat-categories">
                        <div className="text-3xl font-bold text-blue-600 dark:text-blue-400">{summary.categories.length}</div>
                        <div className="text-sm text-muted-foreground">Categories</div>
                      </div>
                      <div className="text-center p-4 rounded-lg bg-muted/50" data-testid="stat-version">
                        <div className="text-3xl font-bold text-emerald-600 dark:text-emerald-400">v{summary.version}</div>
                        <div className="text-sm text-muted-foreground">Version</div>
                      </div>
                      <div className="text-center p-4 rounded-lg bg-muted/50" data-testid="stat-scoring">
                        <div className="text-3xl font-bold text-purple-600 dark:text-purple-400">5</div>
                        <div className="text-sm text-muted-foreground">Scoring Dimensions</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                
                <div className="grid md:grid-cols-2 gap-6">
                  <Card data-testid="card-categories">
                    <CardHeader>
                      <CardTitle className="text-base">Categories</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {summary.categories.map((cat) => (
                        <div key={cat.id} className="flex items-center justify-between p-3 rounded-lg bg-muted/30" data-testid={`category-${cat.id}`}>
                          <div className="flex items-center gap-3">
                            <span className="text-lg text-primary">{getCategoryIcon(cat.id)}</span>
                            <div>
                              <div className="font-medium text-sm">{cat.name}</div>
                              <div className="text-xs text-muted-foreground">
                                {summary.category_counts[cat.id] || 0} questions
                              </div>
                            </div>
                          </div>
                          <Badge variant="secondary">{Math.round(cat.weight * 100)}%</Badge>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                  
                  <Card data-testid="card-scoring">
                    <CardHeader>
                      <CardTitle className="text-base">Scoring Dimensions</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {Object.entries(summary.scoring_weights).map(([key, value]) => (
                        <div key={key} className="space-y-1" data-testid={`scoring-${key}`}>
                          <div className="flex justify-between text-sm">
                            <span className="capitalize">{key.replace(/_/g, " ")}</span>
                            <span className="text-muted-foreground">{Math.round(value.weight * 100)}%</span>
                          </div>
                          <Progress value={value.weight * 100} className="h-2" />
                          <p className="text-xs text-muted-foreground">{value.description}</p>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                </div>
              </>
            ) : null}
          </TabsContent>
          
          <TabsContent value="run" className="space-y-6 mt-6">
            <Card data-testid="card-run-benchmark">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Play className="w-5 h-5" />
                  Run Benchmark
                </CardTitle>
                <CardDescription>
                  Execute the AAMB benchmark to evaluate AesthetiCite's aesthetic medicine knowledge quality.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Category Filter</label>
                  <Select value={selectedCategory} onValueChange={setSelectedCategory}>
                    <SelectTrigger data-testid="select-category">
                      <SelectValue placeholder="Select category" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Categories</SelectItem>
                      <SelectItem value="injectables">Injectables</SelectItem>
                      <SelectItem value="energy_devices">Energy Devices</SelectItem>
                      <SelectItem value="complications">Complications & Safety</SelectItem>
                      <SelectItem value="dosing">Dosing & Protocols</SelectItem>
                      <SelectItem value="anatomy">Anatomy & Techniques</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 mt-0.5" />
                    <div className="text-sm">
                      <p className="font-medium text-amber-800 dark:text-amber-200">Note</p>
                      <p className="text-amber-700 dark:text-amber-300">
                        Running the benchmark will make API calls to the LLM for each question. 
                        This may take several minutes and incur API costs.
                      </p>
                    </div>
                  </div>
                </div>
                
                <Button 
                  onClick={() => runBenchmark.mutate()}
                  disabled={runBenchmark.isPending}
                  className="w-full"
                  data-testid="button-run-benchmark"
                >
                  {runBenchmark.isPending ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Running Benchmark...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 mr-2" />
                      Run Benchmark
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>
          </TabsContent>
          
          <TabsContent value="results" className="space-y-6 mt-6">
            {benchmarkResult && (
              <>
                <Card data-testid="card-results-summary">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle>Benchmark Results</CardTitle>
                        <CardDescription>Run ID: {benchmarkResult.run_id}</CardDescription>
                      </div>
                      <div className={`text-5xl font-bold ${getGradeColor(benchmarkResult.grade)}`} data-testid="text-grade">
                        {benchmarkResult.grade}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
                      <div className="text-center p-3 rounded-lg bg-muted/50" data-testid="result-score">
                        <div className="text-2xl font-bold text-primary">{benchmarkResult.overall_score}%</div>
                        <div className="text-xs text-muted-foreground">Overall Score</div>
                      </div>
                      <div className="text-center p-3 rounded-lg bg-muted/50" data-testid="result-answered">
                        <div className="text-2xl font-bold text-emerald-600">{benchmarkResult.questions_answered}</div>
                        <div className="text-xs text-muted-foreground">Answered</div>
                      </div>
                      <div className="text-center p-3 rounded-lg bg-muted/50" data-testid="result-refused">
                        <div className="text-2xl font-bold text-amber-600">{benchmarkResult.questions_refused}</div>
                        <div className="text-xs text-muted-foreground">Refused</div>
                      </div>
                      <div className="text-center p-3 rounded-lg bg-muted/50" data-testid="result-correct-refusals">
                        <div className="text-2xl font-bold text-green-600">{benchmarkResult.correct_refusals}</div>
                        <div className="text-xs text-muted-foreground">Correct Refusals</div>
                      </div>
                      <div className="text-center p-3 rounded-lg bg-muted/50" data-testid="result-latency">
                        <div className="text-2xl font-bold text-blue-600">{Math.round(benchmarkResult.average_latency_ms)}ms</div>
                        <div className="text-xs text-muted-foreground">Avg Latency</div>
                      </div>
                    </div>
                    
                    <div className="space-y-2">
                      <h4 className="text-sm font-medium">Category Scores</h4>
                      {Object.entries(benchmarkResult.category_scores).map(([cat, score]) => (
                        <div key={cat} className="space-y-1" data-testid={`result-category-${cat}`}>
                          <div className="flex justify-between text-sm">
                            <span className="capitalize">{cat.replace(/_/g, " ")}</span>
                            <span>{Math.round(score * 100)}%</span>
                          </div>
                          <Progress value={score * 100} className="h-2" />
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
                
                <Card data-testid="card-question-results">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="w-5 h-5" />
                      Question Details
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ScrollArea className="h-[600px]">
                      <div className="space-y-4">
                        {benchmarkResult.question_results.map((q, idx) => (
                          <div 
                            key={q.question_id} 
                            className="p-4 rounded-lg border bg-card"
                            data-testid={`question-result-${q.question_id}`}
                          >
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-mono text-muted-foreground">{q.question_id}</span>
                                <Badge className={getDifficultyColor(q.difficulty)}>{q.difficulty}</Badge>
                                <Badge variant="outline">{q.category}</Badge>
                              </div>
                              <div className="flex items-center gap-2">
                                {q.was_refused ? (
                                  q.should_refuse ? (
                                    <CheckCircle className="w-5 h-5 text-green-500" />
                                  ) : (
                                    <XCircle className="w-5 h-5 text-red-500" />
                                  )
                                ) : (
                                  <span className="text-lg font-bold">{Math.round(q.total_score * 100)}%</span>
                                )}
                              </div>
                            </div>
                            
                            <p className="text-sm font-medium mb-2">{q.question}</p>
                            
                            {!q.was_refused && (
                              <>
                                <div className="text-xs text-muted-foreground mb-2 line-clamp-3">
                                  {q.answer}
                                </div>
                                
                                <div className="flex flex-wrap gap-2 text-xs">
                                  <span className="flex items-center gap-1">
                                    <Clock className="w-3 h-3" />
                                    {q.latency_ms}ms
                                  </span>
                                  <span>Citations: {q.citations_count}/{q.expected_citations_min}</span>
                                  <span>Keywords: {q.keywords_found.length}/{q.keywords_expected.length}</span>
                                  {q.evidence_level && (
                                    <Badge variant="secondary" className="text-xs">
                                      Level {q.evidence_level}
                                    </Badge>
                                  )}
                                </div>
                              </>
                            )}
                            
                            {q.was_refused && (
                              <div className="text-xs">
                                <Badge variant={q.should_refuse ? "default" : "destructive"}>
                                  {q.should_refuse ? "Correctly Refused" : "Incorrectly Refused"}
                                </Badge>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </ScrollArea>
                  </CardContent>
                </Card>
              </>
            )}
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
