import { Link, useLocation } from "wouter";
import { useQuery } from "@tanstack/react-query";
import {
  Zap, ShieldAlert, MessageCircle, ChevronRight, Activity,
  Pill, ClipboardList, BookOpen, Bell, Waves,
  Camera, AlertTriangle, TrendingUp, FileText, BarChart2,
  Download, LayoutDashboard, GitBranch, Eye, FlaskConical,
  Stethoscope, Search, FolderOpen, Microscope, Network, Layers,
} from "lucide-react";
import { clearToken } from "@/lib/auth";

// ─── Category definitions ────────────────────────────────────────────────────

const CATEGORIES = [
  {
    id: "complications",
    label: "Complications & Safety",
    accent: "rose",
    bar: "bg-rose-500",
    tools: [
      { href: "/decide",               icon: Microscope,     label: "Complication Decision", desc: "AI-guided decision tree for active complications" },
      { href: "/complications",        icon: AlertTriangle,  label: "Protocol Library",       desc: "Evidence-based management by complication type" },
      { href: "/complication-monitor", icon: TrendingUp,     label: "Complication Monitor",   desc: "Track, trend, and review complication cases" },
      { href: "/chairside",            icon: Stethoscope,    label: "Chairside Reference",    desc: "Acute event handbook for chair-side use" },
      { href: "/drug-interactions",    icon: Pill,           label: "Drug Interactions",      desc: "Check anaesthetic and concurrent drug risks" },
      { href: "/hyaluronidase",        icon: Waves,          label: "Hyaluronidase Calc",     desc: "HA dissolution dosing by product and volume" },
    ],
  },
  {
    id: "vision",
    label: "Vision & Injectables",
    accent: "sky",
    bar: "bg-sky-500",
    tools: [
      { href: "/vision-analysis",  icon: Camera,      label: "Vision Analysis",     desc: "AI photo assessment of post-procedure findings" },
      { href: "/vision-followup",  icon: Eye,         label: "Vision Follow-up",    desc: "Serial comparison and healing progression tracker" },
      { href: "/clinical-tools",   icon: FlaskConical,label: "Clinical Tools Suite", desc: "24 tools — vascular risk, consent, dosing & more" },
      { href: "/workflow",         icon: GitBranch,   label: "Clinical Workflow",   desc: "Step-by-step guided procedure workflow engine" },
    ],
  },
  {
    id: "research",
    label: "Research & Evidence",
    accent: "violet",
    bar: "bg-violet-500",
    tools: [
      { href: "/research-tools", icon: Search,    label: "Research Tools", desc: "Advanced evidence search across 1.9M+ papers" },
      { href: "/bookmarks",      icon: BookOpen,  label: "Saved Answers",  desc: "Your bookmarked clinical references" },
      { href: "/paper-alerts",   icon: Bell,      label: "Paper Alerts",   desc: "Monitor newly published research topics" },
      { href: "/ask-oe",         icon: Layers,    label: "Deep Search",    desc: "Extended evidence retrieval with open evidence" },
    ],
  },
  {
    id: "clinic",
    label: "Clinic Operations",
    accent: "emerald",
    bar: "bg-emerald-500",
    tools: [
      { href: "/session-report",   icon: ClipboardList,    label: "Session Report",   desc: "Auto-generate post-session clinical summaries" },
      { href: "/case-log",         icon: FolderOpen,       label: "Case Log",         desc: "Log, tag, and review patient cases" },
      { href: "/patient-export",   icon: Download,         label: "Patient Export",   desc: "Generate structured patient-facing documents" },
      { href: "/clinic-dashboard", icon: LayoutDashboard,  label: "Clinic Dashboard", desc: "Performance metrics and clinic overview" },
      { href: "/risk-intelligence",icon: BarChart2,        label: "Risk Intelligence",desc: "Predictive analytics and safety trend reports" },
      { href: "/network-safety-workspace", icon: Network,  label: "Network Safety",   desc: "Cross-clinic safety workspace and benchmarking" },
    ],
  },
];

// ─── Accent colour maps ───────────────────────────────────────────────────────

const ICON_BG: Record<string, string> = {
  rose:    "bg-rose-100    dark:bg-rose-900/40",
  sky:     "bg-sky-100     dark:bg-sky-900/40",
  violet:  "bg-violet-100  dark:bg-violet-900/40",
  emerald: "bg-emerald-100 dark:bg-emerald-900/40",
};

const ICON_COLOR: Record<string, string> = {
  rose:    "text-rose-600    dark:text-rose-400",
  sky:     "text-sky-600     dark:text-sky-400",
  violet:  "text-violet-600  dark:text-violet-400",
  emerald: "text-emerald-600 dark:text-emerald-400",
};

const BORDER_HOVER: Record<string, string> = {
  rose:    "hover:border-rose-300    dark:hover:border-rose-700",
  sky:     "hover:border-sky-300     dark:hover:border-sky-700",
  violet:  "hover:border-violet-300  dark:hover:border-violet-700",
  emerald: "hover:border-emerald-300 dark:hover:border-emerald-700",
};

// ─── Component ───────────────────────────────────────────────────────────────

export default function ClinicHomePage() {
  const [, setLocation] = useLocation();

  const { data: corpusStats } = useQuery<{ papers_inserted: number }>({
    queryKey: ["/api/corpus/stats"],
    staleTime: 5 * 60 * 1000,
  });
  const corpusLabel = corpusStats?.papers_inserted
    ? corpusStats.papers_inserted >= 1_000_000
      ? `${(corpusStats.papers_inserted / 1_000_000).toFixed(1)}M+`
      : `${Math.floor(corpusStats.papers_inserted / 1000).toLocaleString()}K+`
    : "1.9M+";

  function handleLogout() {
    clearToken();
    setLocation("/login");
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex flex-col pb-28">

      {/* ── EMERGENCY banner ── */}
      <Link href="/emergency">
        <div
          data-testid="banner-emergency"
          className="group w-full flex items-center justify-between gap-3 bg-red-600 hover:bg-red-700 active:bg-red-800 text-white px-5 py-3 cursor-pointer transition-all"
        >
          <div className="flex items-center gap-3">
            <span className="relative flex h-2.5 w-2.5 flex-shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-300 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-200" />
            </span>
            <Zap className="w-4 h-4 flex-shrink-0" />
            <span className="font-bold text-sm tracking-wide uppercase">EMERGENCY</span>
            <span className="text-red-100 text-sm hidden sm:inline">
              — Vascular occlusion · Anaphylaxis · Necrosis
            </span>
          </div>
          <ChevronRight className="w-4 h-4 text-red-200 group-hover:translate-x-1 transition-transform flex-shrink-0" />
        </div>
      </Link>

      {/* ── Header ── */}
      <header className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 sticky top-0 z-20">
        <div className="mx-auto max-w-lg px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-slate-800 dark:bg-slate-200 flex items-center justify-center">
              <Activity className="w-3.5 h-3.5 text-white dark:text-slate-800" />
            </div>
            <span className="font-bold text-slate-800 dark:text-slate-100 text-sm">AesthetiCite</span>
          </div>
          <button
            onClick={handleLogout}
            className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
            data-testid="button-logout-home"
          >
            Sign out
          </button>
        </div>
      </header>

      {/* ── Main content ── */}
      <div className="flex-1 mx-auto w-full max-w-lg px-4 py-8 space-y-8">

        {/* Corpus label + title */}
        <div className="text-center space-y-1.5">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
            AesthetiCite · {corpusLabel} papers
          </p>
          <h1 className="text-2xl font-black text-slate-800 dark:text-slate-100 tracking-tight">
            What are you dealing with?
          </h1>
        </div>

        {/* ── Primary scenario cards ── */}
        <div className="space-y-3">
          <Link href="/safety-check">
            <div
              data-testid="card-scenario-safety"
              className="group flex items-center gap-5 bg-white dark:bg-slate-900 hover:bg-blue-50 dark:hover:bg-blue-950/30 border-2 border-blue-200 dark:border-blue-900 hover:border-blue-400 dark:hover:border-blue-700 rounded-2xl p-5 cursor-pointer transition-all"
            >
              <div className="w-11 h-11 rounded-xl bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center flex-shrink-0">
                <ShieldAlert className="w-5 h-5 text-blue-600 dark:text-blue-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-base font-bold text-slate-800 dark:text-slate-100">Before a procedure</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Risk score, contraindications &amp; safety check</p>
              </div>
              <ChevronRight className="w-5 h-5 text-slate-300 group-hover:text-blue-400 group-hover:translate-x-1 transition-all flex-shrink-0" />
            </div>
          </Link>

          <Link href="/complications">
            <div
              data-testid="card-scenario-complication"
              className="group flex items-center gap-5 bg-white dark:bg-slate-900 hover:bg-rose-50 dark:hover:bg-rose-950/30 border-2 border-rose-200 dark:border-rose-900 hover:border-rose-400 dark:hover:border-rose-700 rounded-2xl p-5 cursor-pointer transition-all"
            >
              <div className="w-11 h-11 rounded-xl bg-rose-100 dark:bg-rose-900/50 flex items-center justify-center flex-shrink-0">
                <AlertTriangle className="w-5 h-5 text-rose-600 dark:text-rose-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-base font-bold text-slate-800 dark:text-slate-100">Active complication</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Evidence-based protocols for any complication type</p>
              </div>
              <ChevronRight className="w-5 h-5 text-slate-300 group-hover:text-rose-400 group-hover:translate-x-1 transition-all flex-shrink-0" />
            </div>
          </Link>
        </div>

        {/* ── All tools — category sections ── */}
        <div className="space-y-7">

          {CATEGORIES.map((cat) => (
            <section key={cat.id} data-testid={`section-${cat.id}`}>

              {/* Section header */}
              <div className="flex items-center gap-2.5 mb-3">
                <div className={`w-1 h-4 rounded-full flex-shrink-0 ${cat.bar}`} />
                <span className="text-[11px] font-bold uppercase tracking-widest text-slate-400 dark:text-slate-500">
                  {cat.label}
                </span>
                <div className="flex-1 h-px bg-slate-200 dark:bg-slate-800" />
              </div>

              {/* Tool card grid */}
              <div className="grid grid-cols-2 gap-2.5">
                {cat.tools.map((tool) => {
                  const Icon = tool.icon;
                  return (
                    <Link key={tool.href} href={tool.href}>
                      <div
                        data-testid={`card-tool-${tool.href.replace(/\//g, "")}`}
                        className={`flex flex-col gap-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-3.5 cursor-pointer transition-all hover:shadow-sm ${BORDER_HOVER[cat.accent]}`}
                      >
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${ICON_BG[cat.accent]}`}>
                          <Icon className={`w-4 h-4 ${ICON_COLOR[cat.accent]}`} />
                        </div>
                        <div>
                          <p className="text-[13px] font-semibold text-slate-800 dark:text-slate-100 leading-snug">{tool.label}</p>
                          <p className="text-[11px] text-slate-400 dark:text-slate-500 leading-snug mt-0.5">{tool.desc}</p>
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </section>
          ))}

        </div>

        <p className="text-[10px] text-slate-400 text-center pt-2">
          Decision support only — not a substitute for clinical judgment.
        </p>
      </div>

      {/* ── Ask FAB — fixed bottom-center ── */}
      <Link href="/ask">
        <div
          data-testid="fab-ask"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-30 flex items-center gap-3 bg-slate-800 dark:bg-slate-100 hover:bg-slate-700 dark:hover:bg-white active:scale-95 text-white dark:text-slate-900 rounded-full px-7 py-4 shadow-2xl shadow-slate-900/30 cursor-pointer transition-all"
        >
          <MessageCircle className="w-5 h-5 flex-shrink-0" />
          <span className="font-bold text-sm tracking-wide">Ask a clinical question</span>
        </div>
      </Link>
    </div>
  );
}
