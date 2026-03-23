import { useLocation, Link } from "wouter";
import {
  Shield, AlertTriangle, ClipboardList, ShieldAlert, Zap,
  ChevronDown, ChevronUp, Camera
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
    href: "/vision-followup",
    label: "Vision Follow-up",
    icon: Camera,
    description: "Serial photo healing analysis",
    accent: "blue" as const,
  },
];

const ACCENT_CLASSES = {
  emerald: {
    active: "bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-300",
    icon: "text-emerald-500",
    dot: "bg-emerald-500",
  },
  red: {
    active: "bg-red-500/10 border-red-500/30 text-red-700 dark:text-red-300",
    icon: "text-red-500",
    dot: "bg-red-500",
  },
  blue: {
    active: "bg-blue-500/10 border-blue-500/30 text-blue-700 dark:text-blue-300",
    icon: "text-blue-500",
    dot: "bg-blue-500",
  },
};

export function SidebarSafetyNav() {
  const [location] = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  const isOnSafetyPage = SAFETY_LINKS.some((l) => location === l.href);

  return (
    <div className="px-3 pb-2">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-2 py-1.5 mb-1 group"
      >
        <div className="flex items-center gap-1.5">
          <span
            className={`w-1.5 h-1.5 rounded-full transition-colors ${
              isOnSafetyPage ? "bg-red-500" : "bg-muted-foreground/40"
            }`}
          />
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
            Safety Engine
          </span>
        </div>
        {collapsed
          ? <ChevronDown className="w-3 h-3 text-muted-foreground/50" />
          : <ChevronUp className="w-3 h-3 text-muted-foreground/50" />
        }
      </button>

      {!collapsed && (
        <div className="space-y-0.5">
          {SAFETY_LINKS.map((link) => {
            const isActive = location === link.href;
            const accent = ACCENT_CLASSES[link.accent];
            return (
              <Link key={link.href} href={link.href}>
                <div
                  className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg border transition-all cursor-pointer ${
                    isActive
                      ? `${accent.active} border`
                      : "border-transparent hover:bg-muted/50 hover:border-border/50"
                  }`}
                >
                  <span className={`flex-shrink-0 w-5 h-5 rounded-md flex items-center justify-center ${
                    isActive ? "" : "bg-muted/60"
                  }`}>
                    <link.icon className={`w-3 h-3 ${isActive ? accent.icon : "text-muted-foreground"}`} />
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className={`text-xs font-medium leading-tight truncate ${
                      isActive ? "" : "text-foreground/80"
                    }`}>
                      {link.label}
                    </p>
                    {!isActive && (
                      <p className="text-[10px] text-muted-foreground/60 truncate leading-tight mt-0.5">
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

      <div className="mt-2 mb-1 h-px bg-border/50" />
    </div>
  );
}
