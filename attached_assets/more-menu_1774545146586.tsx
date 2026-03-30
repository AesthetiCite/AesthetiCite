/**
 * MoreMenu.tsx
 * ============
 * Replaces the invisible MoreHorizontal (···) dropdown in ask.tsx
 * with a rich app-drawer panel that shows every hidden feature
 * as a labelled, described card — impossible to miss.
 *
 * INTEGRATION — in ask.tsx:
 *
 * 1. Add import:
 *    import { MoreMenu } from "@/components/more-menu";
 *
 * 2. Find the existing DropdownMenu block (search for data-testid="button-more-menu")
 *    and replace the entire <DropdownMenu>...</DropdownMenu> block with:
 *    <MoreMenu />
 *
 * That's it. Nothing else changes.
 */

import { useState, useRef, useEffect } from "react";
import { Link } from "wouter";
import {
  Pill, ClipboardCheck, FileUser, Bookmark, Bell,
  LayoutDashboard, Key, FileText, BarChart3,
  ChevronRight, Grid3X3,
} from "lucide-react";
import { Button } from "@/components/ui/button";

// ─────────────────────────────────────────────────────────────────
// Feature registry — everything that was hidden in the ··· menu
// ─────────────────────────────────────────────────────────────────

interface FeatureItem {
  href: string;
  icon: React.ReactNode;
  label: string;
  description: string;
  accent: string;   // Tailwind bg class for icon background
  textAccent: string; // Tailwind text class for icon
}

const FEATURES: FeatureItem[] = [
  {
    href: "/drug-interactions",
    icon: <Pill className="w-4 h-4" />,
    label: "Drug interactions",
    description: "Check medications before injecting — anticoagulants, GLP-1, SSRIs",
    accent: "bg-red-50",
    textAccent: "text-red-700",
  },
  {
    href: "/session-report",
    icon: <ClipboardCheck className="w-4 h-4" />,
    label: "Session report",
    description: "End-of-session safety summary + PDF export for records",
    accent: "bg-teal-50",
    textAccent: "text-teal-700",
  },
  {
    href: "/patient-export",
    icon: <FileUser className="w-4 h-4" />,
    label: "Patient export",
    description: "Convert any answer into plain-language patient handout",
    accent: "bg-blue-50",
    textAccent: "text-blue-700",
  },
  {
    href: "/bookmarks",
    icon: <Bookmark className="w-4 h-4" />,
    label: "Saved answers",
    description: "Your bookmarked clinical answers, searchable",
    accent: "bg-amber-50",
    textAccent: "text-amber-700",
  },
  {
    href: "/ask-oe",
    icon: <FileText className="w-4 h-4" />,
    label: "Structured evidence",
    description: "Formal PICO-style evidence table view",
    accent: "bg-purple-50",
    textAccent: "text-purple-700",
  },
  {
    href: "/paper-alerts",
    icon: <Bell className="w-4 h-4" />,
    label: "Paper alerts",
    description: "Get notified when new papers match your topics",
    accent: "bg-orange-50",
    textAccent: "text-orange-700",
  },
  {
    href: "/clinic-dashboard",
    icon: <LayoutDashboard className="w-4 h-4" />,
    label: "Clinic dashboard",
    description: "Query volume, ACI scores, and usage analytics",
    accent: "bg-teal-50",
    textAccent: "text-teal-700",
  },
  {
    href: "/hardest-10",
    icon: <BarChart3 className="w-4 h-4" />,
    label: "Challenge mode",
    description: "10 hardest aesthetic questions — AesthetiCite vs general AI",
    accent: "bg-gray-50",
    textAccent: "text-gray-600",
  },
  {
    href: "/api-keys",
    icon: <Key className="w-4 h-4" />,
    label: "API keys",
    description: "Integrate AesthetiCite into your clinic system",
    accent: "bg-gray-50",
    textAccent: "text-gray-600",
  },
];

// Top 3 featured prominently — rest in grid
const FEATURED = FEATURES.slice(0, 3);
const GRID     = FEATURES.slice(3);

// ─────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────

export function MoreMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  return (
    <div className="relative hidden md:block" ref={ref}>
      {/* ── Trigger button — visible, labelled, with indicator dot ── */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen(o => !o)}
        data-testid="button-more-menu"
        className={`
          flex items-center gap-1.5 text-xs h-8 relative
          ${open
            ? "bg-muted text-foreground"
            : "text-muted-foreground hover:text-foreground"
          }
        `}
      >
        <Grid3X3 className="w-3.5 h-3.5" />
        <span className="font-medium">All tools</span>
        {/* Notification dot — draws attention on first load */}
        <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-teal-500 border-2 border-background" />
      </Button>

      {/* ── Panel ── */}
      {open && (
        <div
          className="
            absolute right-0 top-full mt-2 z-50
            w-[400px] rounded-xl border border-border
            bg-background shadow-lg overflow-hidden
          "
        >
          {/* Panel header */}
          <div className="px-4 py-3 border-b border-border bg-muted/40 flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground uppercase tracking-wide">
              All tools
            </span>
            <span className="text-xs text-muted-foreground">
              {FEATURES.length} features
            </span>
          </div>

          <div className="p-3">
            {/* ── Featured row — 3 large cards ── */}
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider px-1 mb-2">
              Most used
            </p>
            <div className="grid grid-cols-3 gap-2 mb-3">
              {FEATURED.map((f) => (
                <Link
                  key={f.href}
                  href={f.href}
                  onClick={() => setOpen(false)}
                >
                  <div className="
                    flex flex-col gap-2 p-3 rounded-lg border border-border
                    hover:border-teal-200 hover:bg-teal-50/50
                    transition-all cursor-pointer group
                    bg-background
                  ">
                    <div className={`
                      w-8 h-8 rounded-lg flex items-center justify-center
                      ${f.accent} ${f.textAccent}
                      group-hover:scale-105 transition-transform
                    `}>
                      {f.icon}
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-foreground leading-tight">
                        {f.label}
                      </p>
                      <p className="text-[10px] text-muted-foreground leading-tight mt-0.5">
                        {f.description}
                      </p>
                    </div>
                  </div>
                </Link>
              ))}
            </div>

            {/* ── Divider ── */}
            <div className="border-t border-border mb-3" />

            {/* ── Grid — remaining features as compact rows ── */}
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider px-1 mb-2">
              More
            </p>
            <div className="grid grid-cols-2 gap-1">
              {GRID.map((f) => (
                <Link
                  key={f.href}
                  href={f.href}
                  onClick={() => setOpen(false)}
                >
                  <div className="
                    flex items-center gap-2.5 px-2.5 py-2 rounded-lg
                    hover:bg-muted transition-colors cursor-pointer group
                  ">
                    <div className={`
                      w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0
                      ${f.accent} ${f.textAccent}
                    `}>
                      {f.icon}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-foreground truncate">
                        {f.label}
                      </p>
                      <p className="text-[10px] text-muted-foreground truncate">
                        {f.description}
                      </p>
                    </div>
                    <ChevronRight className="w-3 h-3 text-muted-foreground ml-auto flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </Link>
              ))}
            </div>
          </div>

          {/* Panel footer */}
          <div className="px-4 py-2.5 border-t border-border bg-muted/30">
            <p className="text-[10px] text-muted-foreground text-center">
              AesthetiCite  ·  Clinical Safety Decision Support
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
