import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ThemeToggle } from "@/components/theme-toggle";
import { LanguageSelector } from "@/components/language-selector";
import { BRAND } from "@/config";
import {
  Check,
  X,
  Minus,
  Shield,
  BookOpen,
  Globe,
  Zap,
  Brain,
  FileText,
  Stethoscope,
  Search,
  Lock,
  Database,
  FlaskConical,
  GraduationCap,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";

type CompareStatus = "yes" | "no" | "partial" | "superior";

function StatusIcon({ status }: { status: CompareStatus }) {
  switch (status) {
    case "yes":
    case "superior":
      return <Check className="w-4 h-4 text-[hsl(var(--chart-2))]" />;
    case "no":
      return <X className="w-4 h-4 text-destructive" />;
    case "partial":
      return <Minus className="w-4 h-4 text-[hsl(var(--chart-4))]" />;
  }
}

function StatusCell({
  status,
  label,
  highlight,
  testId,
}: {
  status: CompareStatus;
  label: string;
  highlight?: boolean;
  testId: string;
}) {
  return (
    <div
      className={`flex items-start gap-2 ${highlight ? "font-medium" : ""}`}
      data-testid={testId}
    >
      <span className="mt-0.5 shrink-0">
        <StatusIcon status={status} />
      </span>
      <span className="text-sm">{label}</span>
    </div>
  );
}

type FeatureRow = {
  id: string;
  feature: string;
  icon: React.ReactNode;
  aestheticite: { status: CompareStatus; label: string };
  openevidence: { status: CompareStatus; label: string };
  category: string;
};

const features: FeatureRow[] = [
  {
    id: "kb-size",
    feature: "Knowledge Base Size",
    icon: <Database className="w-4 h-4" />,
    aestheticite: { status: "superior", label: "217K+ papers across 25+ specialties" },
    openevidence: { status: "yes", label: "Large general medicine corpus" },
    category: "Evidence",
  },
  {
    id: "aesthetic-focus",
    feature: "Aesthetic Medicine Focus",
    icon: <Stethoscope className="w-4 h-4" />,
    aestheticite: { status: "superior", label: "Deep: injectables, devices, complications, off-label" },
    openevidence: { status: "partial", label: "General medicine, limited aesthetic coverage" },
    category: "Evidence",
  },
  {
    id: "evidence-grading",
    feature: "Evidence Grading",
    icon: <Shield className="w-4 h-4" />,
    aestheticite: { status: "superior", label: "4-tier (I-IV) + A/B/C source tiers with color badges" },
    openevidence: { status: "yes", label: "Evidence quality indicators" },
    category: "Evidence",
  },
  {
    id: "inline-citations",
    feature: "Inline Citations",
    icon: <BookOpen className="w-4 h-4" />,
    aestheticite: { status: "yes", label: "Expandable citations with key excerpts" },
    openevidence: { status: "yes", label: "Inline citations with source links" },
    category: "Evidence",
  },
  {
    id: "anti-hallucination",
    feature: "Anti-Hallucination Guards",
    icon: <AlertTriangle className="w-4 h-4" />,
    aestheticite: { status: "superior", label: "Claim grounding, numeric guards, conflict detection, selective refusal" },
    openevidence: { status: "partial", label: "Standard citation enforcement" },
    category: "Safety",
  },
  {
    id: "claim-verification",
    feature: "Claim Verification",
    icon: <FlaskConical className="w-4 h-4" />,
    aestheticite: { status: "superior", label: "Per-claim grounding with SUPPORTED/WEAK/UNSUPPORTED status" },
    openevidence: { status: "no", label: "No per-claim verification" },
    category: "Safety",
  },
  {
    id: "numeric-guard",
    feature: "Numeric Consistency Guard",
    icon: <Shield className="w-4 h-4" />,
    aestheticite: { status: "yes", label: "Rejects claims with unsourced dosages or quantities" },
    openevidence: { status: "no", label: "Not available" },
    category: "Safety",
  },
  {
    id: "conflict-detection",
    feature: "Conflict Detection",
    icon: <AlertTriangle className="w-4 h-4" />,
    aestheticite: { status: "yes", label: "Pairwise negation/polarity analysis between claims" },
    openevidence: { status: "no", label: "Not available" },
    category: "Safety",
  },
  {
    id: "languages",
    feature: "Languages Supported",
    icon: <Globe className="w-4 h-4" />,
    aestheticite: { status: "superior", label: "25 languages with automatic script detection" },
    openevidence: { status: "partial", label: "English primary" },
    category: "Access",
  },
  {
    id: "deepconsult",
    feature: "DeepConsult PhD Agent",
    icon: <GraduationCap className="w-4 h-4" />,
    aestheticite: { status: "yes", label: "Multi-study synthesis, literature disagreement detection" },
    openevidence: { status: "no", label: "Not available" },
    category: "AI",
  },
  {
    id: "mcq",
    feature: "MCQ Exam Mode",
    icon: <Brain className="w-4 h-4" />,
    aestheticite: { status: "yes", label: "USMLE-style answering with evidence-backed reasoning" },
    openevidence: { status: "no", label: "Not available" },
    category: "AI",
  },
  {
    id: "clinical-tools",
    feature: "Clinical Tools",
    icon: <Stethoscope className="w-4 h-4" />,
    aestheticite: { status: "yes", label: "BMI, BSA, eGFR, unit converter, drug interactions" },
    openevidence: { status: "no", label: "Not available" },
    category: "Tools",
  },
  {
    id: "dosing-rules",
    feature: "Evidence-Locked Dosing",
    icon: <Lock className="w-4 h-4" />,
    aestheticite: { status: "yes", label: "Evidence-based max dosing rules enforcement" },
    openevidence: { status: "no", label: "Not available" },
    category: "Safety",
  },
  {
    id: "voice",
    feature: "Voice Input",
    icon: <Search className="w-4 h-4" />,
    aestheticite: { status: "yes", label: "Speech-to-text for hands-free queries" },
    openevidence: { status: "no", label: "Not available" },
    category: "Access",
  },
  {
    id: "pdf-export",
    feature: "PDF Export",
    icon: <FileText className="w-4 h-4" />,
    aestheticite: { status: "yes", label: "Citation-grade PDF reports" },
    openevidence: { status: "partial", label: "Copy/share only" },
    category: "Tools",
  },
  {
    id: "speed",
    feature: "Response Speed",
    icon: <Zap className="w-4 h-4" />,
    aestheticite: { status: "yes", label: "Two speed modes, cached repeats instant" },
    openevidence: { status: "yes", label: "Fast streaming responses" },
    category: "Performance",
  },
  {
    id: "updates",
    feature: "Automatic Knowledge Updates",
    icon: <Database className="w-4 h-4" />,
    aestheticite: { status: "yes", label: "Daily automated PubMed Central sync" },
    openevidence: { status: "partial", label: "Periodic updates" },
    category: "Evidence",
  },
  {
    id: "ifu-priority",
    feature: "IFU/Consensus Priority",
    icon: <FileText className="w-4 h-4" />,
    aestheticite: { status: "yes", label: "IFU, consensus statements, guidelines prioritized" },
    openevidence: { status: "partial", label: "General evidence ranking" },
    category: "Evidence",
  },
];

const categories = ["Evidence", "Safety", "AI", "Tools", "Access", "Performance"];

const categoryIcons: Record<string, React.ReactNode> = {
  Evidence: <BookOpen className="w-4 h-4" />,
  Safety: <Shield className="w-4 h-4" />,
  AI: <Brain className="w-4 h-4" />,
  Tools: <Stethoscope className="w-4 h-4" />,
  Access: <Globe className="w-4 h-4" />,
  Performance: <Zap className="w-4 h-4" />,
};

function StatCard({ value, label, testId }: { value: string; label: string; testId: string }) {
  return (
    <div className="text-center" data-testid={testId}>
      <div className="text-2xl font-semibold tracking-tight" data-testid={`${testId}-value`}>{value}</div>
      <div className="text-sm text-muted-foreground" data-testid={`${testId}-label`}>{label}</div>
    </div>
  );
}

export default function ComparePage() {
  const aestheticiteWins = features.filter(
    (f) => f.aestheticite.status === "superior" || (f.aestheticite.status === "yes" && f.openevidence.status !== "yes")
  ).length;

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60" data-testid="header-compare">
        <div className="container mx-auto flex h-14 items-center justify-between gap-4 px-4">
          <Link href="/welcome">
            <div className="flex items-center gap-2.5 cursor-pointer" data-testid="link-home-logo">
              <img
                src="/aestheticite-logo.png"
                alt="AesthetiCite"
                className="w-8 h-8 object-contain rounded-lg"
                data-testid="img-compare-logo"
              />
              <span className="text-xl font-semibold tracking-tight">{BRAND.name}</span>
            </div>
          </Link>
          <div className="flex items-center gap-2" data-testid="header-actions">
            <LanguageSelector />
            <ThemeToggle />
            <Link href="/login">
              <Button data-testid="link-login">Sign In</Button>
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8">
        <div className="mb-8" data-testid="section-hero">
          <Badge variant="secondary" data-testid="badge-comparison">
            Feature Comparison
          </Badge>
          <h1
            className="mt-3 text-3xl font-semibold tracking-tight"
            data-testid="text-compare-headline"
          >
            AesthetiCite vs OpenEvidence
          </h1>
          <p className="mt-2 max-w-2xl text-muted-foreground" data-testid="text-compare-subtitle">
            A detailed comparison of evidence search capabilities, safety features, and clinical tools
            for aesthetic medicine professionals.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8" data-testid="section-stats">
          <Card className="p-6">
            <StatCard value={`${aestheticiteWins}`} label="Features where AesthetiCite leads" testId="stat-wins" />
          </Card>
          <Card className="p-6">
            <StatCard value="217K+" label="Publications indexed" testId="stat-publications" />
          </Card>
          <Card className="p-6">
            <StatCard value="25" label="Languages supported" testId="stat-languages" />
          </Card>
        </div>

        {categories.map((cat) => {
          const catFeatures = features.filter((f) => f.category === cat);
          if (catFeatures.length === 0) return null;

          return (
            <div key={cat} className="mb-6" data-testid={`section-${cat.toLowerCase()}`}>
              <div className="flex flex-wrap items-center gap-2 mb-3" data-testid={`title-${cat.toLowerCase()}`}>
                <span className="text-muted-foreground">{categoryIcons[cat]}</span>
                <h2 className="text-lg font-medium">{cat}</h2>
              </div>

              <Card>
                <div className="divide-y">
                  <div
                    className="hidden md:grid grid-cols-[1fr_1fr_1fr] gap-4 px-4 py-2.5 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wide"
                    data-testid={`header-${cat.toLowerCase()}`}
                  >
                    <div data-testid="col-feature">Feature</div>
                    <div data-testid="col-aestheticite">AesthetiCite</div>
                    <div data-testid="col-openevidence">OpenEvidence</div>
                  </div>

                  {catFeatures.map((row) => (
                    <div
                      key={row.id}
                      className="flex flex-col md:grid md:grid-cols-[1fr_1fr_1fr] gap-2 md:gap-4 px-4 py-3 items-start"
                      data-testid={`row-${row.id}`}
                    >
                      <div className="flex flex-wrap items-center gap-2" data-testid={`feature-${row.id}`}>
                        <span className="text-muted-foreground shrink-0">{row.icon}</span>
                        <span className="text-sm font-medium">{row.feature}</span>
                      </div>
                      <div className="md:hidden text-xs font-medium text-muted-foreground uppercase mt-1">AesthetiCite</div>
                      <StatusCell
                        status={row.aestheticite.status}
                        label={row.aestheticite.label}
                        highlight={row.aestheticite.status === "superior"}
                        testId={`cell-ac-${row.id}`}
                      />
                      <div className="md:hidden text-xs font-medium text-muted-foreground uppercase mt-1">OpenEvidence</div>
                      <StatusCell
                        status={row.openevidence.status}
                        label={row.openevidence.label}
                        testId={`cell-oe-${row.id}`}
                      />
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          );
        })}

        <Card className="p-6 mt-8 mb-4" data-testid="section-confidence">
          <h2 className="text-lg font-semibold mb-4" data-testid="text-confidence-title">
            ACI Confidence Index
          </h2>
          <p className="text-sm text-muted-foreground mb-4" data-testid="text-confidence-desc">
            AesthetiCite computes an Aesthetic Confidence Index (0-10) for every answer, using evidence
            weighting, recency modifiers, and risk penalties. This helps clinicians instantly gauge how
            much trust to place in each response.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="rounded-lg border p-4 text-center" data-testid="aci-high">
              <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">8-10</div>
              <div className="text-xs text-muted-foreground mt-1">Strong evidence</div>
              <div className="text-[10px] text-muted-foreground">Multiple guidelines + RCTs</div>
            </div>
            <div className="rounded-lg border p-4 text-center" data-testid="aci-medium">
              <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">4-7</div>
              <div className="text-xs text-muted-foreground mt-1">Moderate evidence</div>
              <div className="text-[10px] text-muted-foreground">Case series + reviews</div>
            </div>
            <div className="rounded-lg border p-4 text-center" data-testid="aci-low">
              <div className="text-2xl font-bold text-red-600 dark:text-red-400">0-3</div>
              <div className="text-xs text-muted-foreground mt-1">Limited evidence</div>
              <div className="text-[10px] text-muted-foreground">Expert opinion / insufficient</div>
            </div>
          </div>
        </Card>

        <Card className="p-6 mt-4 mb-8" data-testid="section-summary">
          <h2 className="text-lg font-semibold mb-4" data-testid="text-summary-title">
            Summary
          </h2>
          <div className="space-y-3 text-sm text-muted-foreground">
            <p data-testid="text-summary-depth">
              <strong className="text-foreground">Depth in Aesthetic Medicine:</strong>{" "}
              AesthetiCite is purpose-built for aesthetic medicine with specialized indexing across
              injectables, energy devices, complications, and off-label use. OpenEvidence covers general medicine broadly
              but lacks deep aesthetic specialty coverage.
            </p>
            <p data-testid="text-summary-safety">
              <strong className="text-foreground">Safety-First Architecture:</strong>{" "}
              AesthetiCite employs per-claim grounding with explicit SUPPORTED/WEAK/UNSUPPORTED status,
              numeric consistency guards that reject unsourced dosages, and pairwise conflict detection.
              These anti-hallucination safeguards go beyond standard citation enforcement.
            </p>
            <p data-testid="text-summary-tools">
              <strong className="text-foreground">Clinical Workflow Integration:</strong>{" "}
              Built-in clinical calculators (BMI, BSA, eGFR), drug interaction checking,
              evidence-locked dosing rules, voice input, and citation-grade PDF exports make AesthetiCite
              a complete clinical decision support tool.
            </p>
            <p data-testid="text-summary-access">
              <strong className="text-foreground">Global Accessibility:</strong>{" "}
              With 25 languages and automatic script-based detection,
              AesthetiCite serves practitioners worldwide. OpenEvidence is primarily English-focused.
            </p>
          </div>

          <div className="mt-6 flex flex-wrap gap-3" data-testid="summary-actions">
            <Link href="/login" data-testid="link-try-aestheticite">
              <Button data-testid="button-try-aestheticite">
                Try AesthetiCite
                <ArrowRight className="w-4 h-4 ml-1" />
              </Button>
            </Link>
            <Link href="/hardest-10" data-testid="link-hardest10">
              <Button variant="outline" data-testid="button-hardest10">
                See Live: 10 Hardest Questions
                <ArrowRight className="w-4 h-4 ml-1" />
              </Button>
            </Link>
            <Link href="/welcome" data-testid="link-back-home">
              <Button variant="ghost" data-testid="button-back-home">
                Back to Home
              </Button>
            </Link>
          </div>
        </Card>
      </main>
    </div>
  );
}
