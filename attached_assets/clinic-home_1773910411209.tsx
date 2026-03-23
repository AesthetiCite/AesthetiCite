/**
 * AesthetiCite — Clinic Home
 * ===========================
 * Drop into: client/src/pages/clinic-home.tsx
 * Route: "/" and "/home" — becomes the default landing after login
 *
 * What it does:
 *   - Clean "What do you want to do?" screen for doctors
 *   - 4 primary action cards: Search, Safety Check, Emergency Protocol, Session Report
 *   - Quick-access secondary tools row
 *   - No clutter — doctors see exactly what they need immediately
 */

import { Link } from "wouter";
import {
  Search, ShieldAlert, Zap, ClipboardList,
  Pill, Database, Microscope, LayoutDashboard,
  BookOpen, Bell, ChevronRight, Activity,
  FileText, Waves
} from "lucide-react";

// ─── Primary action cards ─────────────────────────────────────────────────────

const PRIMARY_ACTIONS = [
  {
    id: "search",
    href: "/ask",
    icon: Search,
    label: "Evidence Search",
    description: "Ask any clinical question. Get cited, evidence-graded answers from 206,000+ peer-reviewed papers.",
    tag: "Core",
    tagColor: "bg-slate-100 text-slate-600",
    cardBg: "bg-white",
    iconBg: "bg-slate-800",
    iconColor: "text-white",
    border: "border-slate-200",
    hoverBorder: "hover:border-slate-400",
    cta: "Ask a question",
  },
  {
    id: "safety",
    href: "/safety-check",
    icon: ShieldAlert,
    label: "Pre-Procedure Safety",
    description: "Enter procedure, region, product, and patient factors. Get a Go/Caution/High Risk decision before you inject.",
    tag: "Before treatment",
    tagColor: "bg-blue-100 text-blue-700",
    cardBg: "bg-white",
    iconBg: "bg-blue-600",
    iconColor: "text-white",
    border: "border-blue-100",
    hoverBorder: "hover:border-blue-300",
    cta: "Run safety check",
  },
  {
    id: "emergency",
    href: "/emergency",
    icon: Zap,
    label: "Emergency Protocol",
    description: "Vascular occlusion, anaphylaxis, necrosis. Immediate structured steps when every second counts.",
    tag: "Emergency",
    tagColor: "bg-red-100 text-red-700",
    cardBg: "bg-white",
    iconBg: "bg-red-600",
    iconColor: "text-white",
    border: "border-red-200",
    hoverBorder: "hover:border-red-400",
    cta: "Open protocol",
    urgent: true,
  },
  {
    id: "session",
    href: "/session-report",
    icon: ClipboardList,
    label: "Session Safety Report",
    description: "Queue today's procedures. Run safety checks for each patient. Export one consolidated PDF for your records.",
    tag: "Clinic workflow",
    tagColor: "bg-emerald-100 text-emerald-700",
    cardBg: "bg-white",
    iconBg: "bg-emerald-600",
    iconColor: "text-white",
    border: "border-emerald-100",
    hoverBorder: "hover:border-emerald-300",
    cta: "Start session",
  },
];

// ─── Secondary tools ──────────────────────────────────────────────────────────

const SECONDARY_TOOLS = [
  { href: "/drug-interactions", icon: Pill, label: "Drug Interactions" },
  { href: "/safety-check#differential", icon: Microscope, label: "Complication Differential" },
  { href: "/safety-check#prescan", icon: Waves, label: "Pre-Scan Briefing" },
  { href: "/case-log", icon: Database, label: "Case Log" },
  { href: "/clinic-dashboard", icon: LayoutDashboard, label: "Clinic Dashboard" },
  { href: "/bookmarks", icon: BookOpen, label: "Saved Answers" },
  { href: "/paper-alerts", icon: Bell, label: "Paper Alerts" },
  { href: "/patient-export", icon: FileText, label: "Patient Export" },
];

// ─── Quick emergency protocols ────────────────────────────────────────────────

const EMERGENCY_SHORTCUTS = [
  { label: "Vascular Occlusion", query: "vascular_occlusion", color: "text-red-600 bg-red-50 border-red-200" },
  { label: "Anaphylaxis", query: "anaphylaxis", color: "text-red-600 bg-red-50 border-red-200" },
  { label: "Tyndall Effect", query: "tyndall_effect", color: "text-sky-600 bg-sky-50 border-sky-200" },
  { label: "Ptosis", query: "ptosis", color: "text-amber-600 bg-amber-50 border-amber-200" },
  { label: "Nodules", query: "filler_nodules", color: "text-slate-600 bg-slate-50 border-slate-200" },
  { label: "Toxin Resistance", query: "neuromodulator_resistance", color: "text-violet-600 bg-violet-50 border-violet-200" },
];

// ─── Component ────────────────────────────────────────────────────────────────

export default function ClinicHomePage() {
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
    <div className="min-h-screen bg-slate-50">

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <header className="border-b border-slate-200 bg-white sticky top-0 z-20">
        <div className="mx-auto max-w-5xl px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-slate-800 flex items-center justify-center">
              <Activity className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-slate-800 text-sm">AesthetiCite</span>
            <span className="text-xs text-slate-400 hidden sm:block">
              Clinical safety &amp; evidence platform
            </span>
          </div>
          <div className="flex items-center gap-2">
            {/* Emergency — always visible in header */}
            <Link href="/emergency">
              <button className="flex items-center gap-1.5 bg-red-600 hover:bg-red-700 text-white text-xs font-bold rounded-lg px-3 py-1.5 transition-colors shadow-sm">
                <Zap className="w-3.5 h-3.5" />
                Emergency
              </button>
            </Link>
            <Link href="/ask">
              <button className="text-xs text-slate-500 hover:text-slate-700 font-medium px-3 py-1.5 transition-colors">
                Search →
              </button>
            </Link>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-8 space-y-8">

        {/* ── Greeting ─────────────────────────────────────────────────────── */}
        <div>
          <h1 className="text-2xl font-black text-slate-800 tracking-tight">{greeting}.</h1>
          <p className="text-sm text-slate-500 mt-1">What do you need today?</p>
        </div>

        {/* ── Primary 4-card grid ───────────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {PRIMARY_ACTIONS.map((action) => {
            const Icon = action.icon;
            return (
              <Link key={action.id} href={action.href}>
                <div
                  className={`
                    group relative ${action.cardBg} rounded-2xl border-2 ${action.border} ${action.hoverBorder}
                    p-5 cursor-pointer transition-all duration-200
                    hover:shadow-md active:scale-[0.99]
                    ${action.urgent ? "ring-1 ring-red-200" : ""}
                  `}
                >
                  {/* Urgent pulse */}
                  {action.urgent && (
                    <span className="absolute top-4 right-4 flex h-2.5 w-2.5">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500" />
                    </span>
                  )}

                  <div className="flex items-start gap-4">
                    <div className={`w-10 h-10 rounded-xl ${action.iconBg} flex items-center justify-center flex-shrink-0`}>
                      <Icon className={`w-5 h-5 ${action.iconColor}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h2 className="text-sm font-bold text-slate-800">{action.label}</h2>
                        <span className={`text-[10px] font-semibold rounded-full px-2 py-0.5 ${action.tagColor}`}>
                          {action.tag}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 leading-relaxed">
                        {action.description}
                      </p>
                    </div>
                  </div>

                  <div className={`
                    mt-4 flex items-center gap-1 text-xs font-semibold
                    ${action.urgent ? "text-red-600" : "text-slate-600"}
                    group-hover:gap-2 transition-all
                  `}>
                    {action.cta}
                    <ChevronRight className="w-3.5 h-3.5" />
                  </div>
                </div>
              </Link>
            );
          })}
        </div>

        {/* ── Quick emergency protocol access ──────────────────────────────── */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4 text-red-500" />
            <h2 className="text-sm font-bold text-slate-800">Quick Protocol Access</h2>
            <span className="text-xs text-slate-400">— tap to open immediately</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {EMERGENCY_SHORTCUTS.map((s) => (
              <Link
                key={s.query}
                href={`/emergency?protocol=${s.query}`}
              >
                <button className={`text-xs font-semibold border rounded-lg px-3 py-2 transition-all hover:opacity-80 ${s.color}`}>
                  {s.label}
                </button>
              </Link>
            ))}
          </div>
        </div>

        {/* ── Secondary tools ───────────────────────────────────────────────── */}
        <div>
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">All tools</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {SECONDARY_TOOLS.map((tool) => {
              const Icon = tool.icon;
              return (
                <Link key={tool.href} href={tool.href}>
                  <div className="bg-white rounded-xl border border-slate-200 p-3 flex items-center gap-2.5 cursor-pointer hover:border-slate-400 hover:shadow-sm transition-all group">
                    <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0 group-hover:bg-slate-200 transition-colors">
                      <Icon className="w-3.5 h-3.5 text-slate-600" />
                    </div>
                    <span className="text-xs font-medium text-slate-700 leading-tight">{tool.label}</span>
                  </div>
                </Link>
              );
            })}
          </div>
        </div>

        {/* ── Footer positioning note ───────────────────────────────────────── */}
        <p className="text-[10px] text-slate-400 text-center pb-4">
          AesthetiCite — Clinical safety &amp; evidence engine for aesthetic injectables.
          All content is decision support only — not a substitute for clinical judgment.
        </p>
      </div>
    </div>
  );
}
