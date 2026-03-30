import { useLocation, Link } from "wouter";
import {
  Shield, AlertTriangle, ClipboardList, ShieldAlert, Zap, Eye,
  ChevronDown, ChevronUp
} from "lucide-react";
import { useState } from "react";

const SAFETY_LINKS = [
  {
    href: "/daily-home",
    label: "Quick Clinical Home",
    icon: Zap,
    description: "One-tap daily actions",
    accent: "blue" as const,
  },
  {
    href: "/safety-check",
    label: "Pre-Procedure Safety",
    icon: Shield,
    description: "Risk score before treatment",
    accent: "emerald" as const,
  },
  {
    href: "/chairside",
    label: "Chairside Emergency",
    icon: ShieldAlert,
    description: "Triage — open during injections",
    accent: "red" as const,
  },
  {
    href: "/complications",
    label: "Complication Protocols",
    icon: AlertTriangle,
    description: "Structured emergency protocols",
    accent: "red" as const,
  },
  {
    href: "/session-report",
    label: "Session Safety Report",
    icon: ClipboardList,
    description: "Multi-patient session summary",
    accent: "blue" as const,
  },
  {
    href: "/vision-analysis",
    label: "Vision",
    icon: Eye,
    description: "Photo analysis & healing follow-up",
    accent: "blue" as const,
  },
];

const ACCENT_CLASSES = {
  emerald: {
    active: "bg-emerald-500/15 border-emerald-500/40 text-emerald-700 dark:text-emerald-300",
    icon: "text-emerald-500",
    iconBg: "bg-emerald-500/15",
    dot: "bg-emerald-500",
  },
  red: {
    active: "bg-red-500/15 border-red-500/40 text-red-700 dark:text-red-300",
    icon: "text-red-500",
    iconBg: "bg-red-500/15",
    dot: "bg-red-500",
  },
  blue: {
    active: "bg-sidebar-primary/15 border-sidebar-primary/40 text-sidebar-primary dark:text-sidebar-accent-foreground",
    icon: "text-sidebar-primary",
    iconBg: "bg-sidebar-primary/15",
    dot: "bg-sidebar-primary",
  },
};

export function SidebarSafetyNav() {
  const [location] = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  const isOnSafetyPage = SAFETY_LINKS.some((l) => location === l.href);

  return (
    <div className="px-2 pb-2">
      <div className="rounded-xl border border-sidebar-border bg-sidebar-accent/40 overflow-hidden">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-sidebar-accent/60 transition-colors"
        >
          <div className="flex items-center gap-1.5">
            <span
              className={`w-1.5 h-1.5 rounded-full transition-colors ${
                isOnSafetyPage ? "bg-red-500" : "bg-sidebar-primary/50"
              }`}
            />
            <span className="text-[10px] font-bold text-sidebar-accent-foreground uppercase tracking-widest">
              Safety Engine
            </span>
          </div>
          {collapsed
            ? <ChevronDown className="w-3 h-3 text-sidebar-accent-foreground/60" />
            : <ChevronUp className="w-3 h-3 text-sidebar-accent-foreground/60" />
          }
        </button>

        {!collapsed && (
          <div className="px-1.5 pb-1.5 space-y-0.5">
            {SAFETY_LINKS.map((link) => {
              const isActive = location === link.href;
              const accent = ACCENT_CLASSES[link.accent];
              return (
                <Link key={link.href} href={link.href}>
                  <div
                    className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg border transition-all cursor-pointer ${
                      isActive
                        ? `${accent.active} border`
                        : "border-sidebar-border/50 bg-sidebar/60 hover:bg-sidebar-accent/60 hover:border-sidebar-border"
                    }`}
                  >
                    <span className={`flex-shrink-0 w-5 h-5 rounded-md flex items-center justify-center ${
                      isActive ? accent.iconBg : "bg-sidebar-accent/80"
                    }`}>
                      <link.icon className={`w-3 h-3 ${isActive ? accent.icon : "text-sidebar-accent-foreground/70"}`} />
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className={`text-xs font-medium leading-tight truncate ${
                        isActive ? "" : "text-sidebar-foreground/80"
                      }`}>
                        {link.label}
                      </p>
                      {!isActive && (
                        <p className="text-[10px] text-sidebar-accent-foreground/60 truncate leading-tight mt-0.5">
                          {link.description}
                        </p>
                      )}
                    </div>
                    {isActive && (
                      <span className={`flex-shrink-0 w-1.5 h-1.5 rounded-full ${accent.dot}`} />
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>

      <div className="mt-2 mb-1 h-px bg-sidebar-border/60" />
    </div>
  );
}
