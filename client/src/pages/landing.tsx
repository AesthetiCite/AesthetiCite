import { useLocation } from "wouter";
import { Link } from "wouter";
import { useEffect, useState } from "react";
import {
  Shield, AlertTriangle, ClipboardList, Activity,
  BookOpen, CheckCircle2, ArrowRight, Camera,
  Syringe, BarChart3, Globe, Lock, FileDown, TrendingUp
} from "lucide-react";
import { Button } from "@/components/ui/button";

function useCorpusCount() {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    fetch("/api/corpus/stats", { signal: controller.signal })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        const n = d?.state?.papers_inserted ?? d?.papers_inserted;
        if (typeof n === "number" && n > 0) setCount(n);
      })
      .catch(() => {})
      .finally(() => clearTimeout(timer));
  }, []);
  return count;
}

function formatCorpusCount(n: number | null): string {
  if (!n) return "1,900,000+";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M+`;
  const rounded = Math.floor(n / 1000) * 1000;
  return `${rounded.toLocaleString()}+`;
}

export default function LandingPage() {
  const [, setLocation] = useLocation();
  const corpusCount = useCorpusCount();
  const displayCount = formatCorpusCount(corpusCount);

  return (
    <div className="min-h-screen bg-background text-foreground">

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
            and {displayCount} peer-reviewed documents — built for injectors, not researchers.
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

          <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-xs text-muted-foreground">
            {[
              { icon: BookOpen, label: `${displayCount} peer-reviewed documents` },
              { icon: CheckCircle2, label: "Server-validated citations only" },
              { icon: Lock, label: "GDPR compliant by design" },
              { icon: Globe, label: "22+ languages supported" },
              { icon: TrendingUp, label: "Corpus growing daily" },
            ].map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-1.5">
                <Icon className="w-3.5 h-3.5 text-primary/60" />
                <span>{label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

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
              <div
                key={feature.title}
                className={`rounded-2xl border p-6 space-y-4 transition-all hover:shadow-md ${colorMap[feature.color]}`}
              >
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

      <section className="border-t bg-muted/20">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-16">
          <h2 className="text-xl font-bold mb-8 text-center">Everything a clinical team needs</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            {[
              { icon: BookOpen,  label: `${displayCount} documents` },
              { icon: Syringe,   label: "Drug interactions" },
              { icon: Camera,    label: "Vision follow-up" },
              { icon: Activity,  label: "Evidence search" },
              { icon: BarChart3, label: "Clinic dashboard" },
              { icon: FileDown,  label: "PDF export" },
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
