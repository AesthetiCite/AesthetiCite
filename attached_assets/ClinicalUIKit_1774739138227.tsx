/**
 * EmergencyDropdown.tsx
 * ─────────────────────
 * Improvement #12 — 3-tap emergency protocol access
 * Replace the current Emergency button in the header with this component.
 * Top 3 emergency protocols are directly accessible without any query.
 *
 * Usage: replace EmergencyButton in ask.tsx header with:
 *   import { EmergencyDropdown } from "@/components/EmergencyDropdown";
 *   <EmergencyDropdown />
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * ClinicalTooltip.tsx (also in this file)
 * ─────────────────────
 * Improvement #8 — MHRA SaMD regulatory badge
 * Improvement #9 — Role-specific interface switch
 * Improvement #11 — Dark mode intelligent default
 * Improvement #13 — OpenMed NER tags display
 *
 * Usage:
 *   import { ClinicalTooltip, MHRABadge, RoleSwitch, useAutoDarkMode } from "@/components/ClinicalUIKit";
 */

// ═══════════════════════════════════════════════════════════════════════════
// PART 1: EmergencyDropdown (Improvement #12)
// ═══════════════════════════════════════════════════════════════════════════

import { useState, useRef, useEffect } from "react";
import { useLocation } from "wouter";
import { AlertTriangle, Eye, Heart, ChevronDown, X, Shield, Info, Sun, Moon, User, BarChart2 } from "lucide-react";

// ── Emergency protocols (direct access, no search required) ────────────────

const EMERGENCY_PROTOCOLS = [
  {
    key: "vascular_occlusion",
    label: "Vascular Occlusion",
    description: "Blanching, mottling, skin ischaemia post-filler",
    urgency: "critical" as const,
    icon: <Heart className="h-4 w-4" />,
    path: "/clinical-tools?protocol=vascular_occlusion",
    shortcut: "1",
  },
  {
    key: "anaphylaxis",
    label: "Anaphylaxis",
    description: "Systemic allergic reaction, angioedema, airway compromise",
    urgency: "critical" as const,
    icon: <AlertTriangle className="h-4 w-4" />,
    path: "/clinical-tools?protocol=anaphylaxis",
    shortcut: "2",
  },
  {
    key: "vision_loss",
    label: "Vision Loss / Ocular",
    description: "Any visual disturbance, diplopia, or vision change post-injection",
    urgency: "critical" as const,
    icon: <Eye className="h-4 w-4" />,
    path: "/clinical-tools?protocol=vascular_occlusion&context=ocular",
    shortcut: "3",
  },
];

export function EmergencyDropdown() {
  const [open, setOpen] = useState(false);
  const [, navigate] = useLocation();
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Keyboard shortcut: Alt+E to open, 1/2/3 to select protocol
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.altKey && e.key === "e") {
        setOpen(v => !v);
        return;
      }
      if (open && ["1", "2", "3"].includes(e.key)) {
        const proto = EMERGENCY_PROTOCOLS[parseInt(e.key) - 1];
        if (proto) {
          navigate(proto.path);
          setOpen(false);
        }
      }
      if (open && e.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, navigate]);

  return (
    <div ref={ref} className="relative">
      {/* Trigger button */}
      <button
        onClick={() => setOpen(v => !v)}
        className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-semibold transition-all
          ${open
            ? "bg-red-600 text-white shadow-lg shadow-red-500/30"
            : "bg-red-500 hover:bg-red-600 text-white shadow-sm hover:shadow-red-500/20"
          }`}
        aria-label="Emergency protocols (Alt+E)"
        title="Emergency protocols — Alt+E"
      >
        <AlertTriangle className="h-4 w-4" />
        <span className="hidden sm:block">Emergency</span>
        <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 rounded-xl border border-red-200 dark:border-red-800 bg-white dark:bg-gray-900 shadow-2xl shadow-red-500/10 z-50">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-red-100 dark:border-red-900">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
              <span className="text-sm font-bold text-red-700 dark:text-red-400 uppercase tracking-wide">
                Emergency Protocols
              </span>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Protocol cards */}
          <div className="p-2 space-y-1">
            {EMERGENCY_PROTOCOLS.map((proto) => (
              <button
                key={proto.key}
                onClick={() => { navigate(proto.path); setOpen(false); }}
                className="w-full flex items-start gap-3 rounded-lg px-3 py-2.5 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors text-left group"
              >
                <div className="flex-shrink-0 mt-0.5 text-red-500 dark:text-red-400">
                  {proto.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-foreground">{proto.label}</span>
                    <kbd className="text-xs bg-gray-100 dark:bg-gray-800 text-muted-foreground px-1.5 py-0.5 rounded font-mono opacity-70 group-hover:opacity-100">
                      {proto.shortcut}
                    </kbd>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed mt-0.5">
                    {proto.description}
                  </p>
                </div>
              </button>
            ))}
          </div>

          {/* Footer */}
          <div className="px-4 py-2 border-t border-gray-100 dark:border-gray-800">
            <p className="text-xs text-muted-foreground">
              Press <kbd className="font-mono text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">Alt+E</kbd> to open,{" "}
              <kbd className="font-mono text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">1–3</kbd> to select
            </p>
          </div>
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// PART 2: ClinicalTooltip (Improvement #8)
// ═══════════════════════════════════════════════════════════════════════════

interface TooltipProps {
  content: string;
  children: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  maxWidth?: number;
}

export function ClinicalTooltip({ content, children, side = "top", maxWidth = 280 }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const ref = useRef<HTMLSpanElement>(null);

  const handleEnter = () => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const offset = 8;
    let top = 0, left = 0;

    switch (side) {
      case "top":
        top  = rect.top - offset;
        left = rect.left + rect.width / 2;
        break;
      case "bottom":
        top  = rect.bottom + offset;
        left = rect.left + rect.width / 2;
        break;
      case "left":
        top  = rect.top + rect.height / 2;
        left = rect.left - offset;
        break;
      case "right":
        top  = rect.top + rect.height / 2;
        left = rect.right + offset;
        break;
    }
    setPos({ top, left });
    setVisible(true);
  };

  return (
    <span
      ref={ref}
      className="inline-flex items-center gap-0.5 cursor-help"
      onMouseEnter={handleEnter}
      onMouseLeave={() => setVisible(false)}
      onFocus={handleEnter}
      onBlur={() => setVisible(false)}
    >
      {children}
      <Info className="h-3 w-3 text-muted-foreground opacity-60 hover:opacity-100 transition-opacity" />

      {visible && (
        <div
          className="fixed z-[9999] pointer-events-none"
          style={{
            top:      `${pos.top}px`,
            left:     `${pos.left}px`,
            maxWidth: `${maxWidth}px`,
            transform: side === "top" ? "translate(-50%, -100%)"
              : side === "bottom" ? "translate(-50%, 0)"
              : side === "left"   ? "translate(-100%, -50%)"
              : "translate(0, -50%)",
          }}
        >
          <div className="bg-gray-900 dark:bg-gray-800 text-white text-xs rounded-lg px-3 py-2 shadow-xl leading-relaxed">
            {content}
          </div>
        </div>
      )}
    </span>
  );
}

// Pre-built clinical tooltips for AesthetiCite-specific terms
export const CLINICAL_TOOLTIPS: Record<string, string> = {
  aci_score:
    "Aesthetic Confidence Index (0–10): measures how well this answer is grounded in evidence. " +
    "7+ = strong (guideline/RCT level). Below 5 = limited evidence — use with caution.",
  evidence_badge:
    "Evidence level based on the quality of sources retrieved. High = systematic review or RCT. " +
    "Moderate = observational studies. Low = case reports or expert opinion only.",
  vascular_occlusion:
    "Blockage of a blood vessel by filler material. Time-critical emergency. " +
    "Stop treatment immediately on any blanching and initiate protocol.",
  tyndall_effect:
    "Blue-grey skin discolouration from superficially placed HA filler. " +
    "Managed with hyaluronidase dissolution.",
  fitzpatrick_type:
    "Skin phototype I–VI. Higher types (IV–VI) have greater risk of post-inflammatory " +
    "hyperpigmentation with laser and energy devices.",
  hyaluronidase:
    "Enzyme that dissolves hyaluronic acid filler. First-line emergency treatment for HA-related " +
    "vascular occlusion. Must be immediately available in all HA filler clinics.",
};


// ═══════════════════════════════════════════════════════════════════════════
// PART 3: MHRABadge (Improvement #11 — regulatory display)
// ═══════════════════════════════════════════════════════════════════════════

export function MHRABadge({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <ClinicalTooltip
        content="AesthetiCite is clinical decision support software. It is not a medical device for diagnosis. Always apply clinical judgement. MHRA SaMD classification review in progress."
        side="bottom"
        maxWidth={320}
      >
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground border border-gray-200 dark:border-gray-700 rounded px-1.5 py-0.5">
          <Shield className="h-3 w-3" />
          CDS Software
        </span>
      </ClinicalTooltip>
    );
  }

  return (
    <div className="rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 p-4 space-y-2">
      <div className="flex items-center gap-2">
        <Shield className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0" />
        <h3 className="text-sm font-bold text-blue-700 dark:text-blue-400">Regulatory Status</h3>
      </div>
      <div className="space-y-1 text-xs text-foreground">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Classification</span>
          <span className="font-medium">Clinical Decision Support Software</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Framework</span>
          <span className="font-medium">MHRA SaMD (under review)</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Data standard</span>
          <span className="font-medium">UK GDPR / UKDPA 2018</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Intended use</span>
          <span className="font-medium">Clinical decision support — not diagnostic</span>
        </div>
      </div>
      <p className="text-xs text-muted-foreground italic pt-1">
        AesthetiCite is decision support software and does not replace clinical training,
        examination, or professional judgement. All outputs require clinician verification.
      </p>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// PART 4: RoleSwitch (Improvement #9 — role-specific interfaces)
// ═══════════════════════════════════════════════════════════════════════════

type Role = "clinician" | "clinic_owner";

const ROLE_CONFIG: Record<Role, {
  label: string;
  description: string;
  icon: React.ReactNode;
  primaryNav: Array<{ path: string; label: string }>;
}> = {
  clinician: {
    label: "Clinician",
    description: "Evidence search, safety checks, protocols",
    icon: <User className="h-4 w-4" />,
    primaryNav: [
      { path: "/ask",           label: "Evidence Search" },
      { path: "/safety-check",  label: "Pre-Procedure Safety" },
      { path: "/session-report",label: "Session Report" },
      { path: "/visual-counsel",label: "Vision" },
      { path: "/clinical-tools",label: "Protocols" },
    ],
  },
  clinic_owner: {
    label: "Clinic Owner",
    description: "Analytics, team management, API keys",
    icon: <BarChart2 className="h-4 w-4" />,
    primaryNav: [
      { path: "/clinic-dashboard", label: "Dashboard" },
      { path: "/api-keys",         label: "API Keys" },
      { path: "/paper-alerts",     label: "Paper Alerts" },
      { path: "/bookmarks",        label: "Saved Answers" },
    ],
  },
};

interface RoleSwitchProps {
  currentRole: Role;
  onRoleChange: (role: Role) => void;
}

export function RoleSwitch({ currentRole, onRoleChange }: RoleSwitchProps) {
  return (
    <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5">
      {(Object.keys(ROLE_CONFIG) as Role[]).map(role => {
        const cfg = ROLE_CONFIG[role];
        const active = role === currentRole;
        return (
          <button
            key={role}
            onClick={() => onRoleChange(role)}
            title={cfg.description}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all
              ${active
                ? "bg-white dark:bg-gray-700 text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
              }`}
          >
            {cfg.icon}
            <span className="hidden sm:block">{cfg.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function getRoleNavItems(role: Role) {
  return ROLE_CONFIG[role].primaryNav;
}


// ═══════════════════════════════════════════════════════════════════════════
// PART 5: useAutoDarkMode hook (Improvement #13 — intelligent dark default)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Improvement #13: Auto-enable dark mode in clinical contexts.
 * Dark mode is automatically applied when:
 *   - OS-level dark mode preference is set
 *   - Time is after 19:00 local (clinical shift hours)
 *   - User is on a clinical page (safety-check, visual-counsel, clinical-tools)
 *
 * Usage in theme-provider or App.tsx:
 *   import { useAutoDarkMode } from "@/components/ClinicalUIKit";
 *   const { shouldUseDark, reason } = useAutoDarkMode();
 *   // apply shouldUseDark to your ThemeProvider
 */
export function useAutoDarkMode(): { shouldUseDark: boolean; reason: string } {
  const [, setLocation] = useLocation();

  // OS preference
  const osPrefersDark =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;

  // Time-based: after 19:00 local
  const hour = new Date().getHours();
  const isEveningOrNight = hour >= 19 || hour < 7;

  // Page-based: clinical tool pages benefit from dark mode
  const clinicalPages = [
    "/safety-check", "/visual-counsel", "/clinical-tools",
    "/session-report", "/drug-interactions",
  ];
  const currentPath =
    typeof window !== "undefined" ? window.location.pathname : "/";
  const isClinicalPage = clinicalPages.some(p => currentPath.startsWith(p));

  if (osPrefersDark) {
    return { shouldUseDark: true, reason: "OS dark mode preference" };
  }
  if (isEveningOrNight) {
    return { shouldUseDark: true, reason: "Evening/night clinical hours" };
  }
  if (isClinicalPage) {
    return { shouldUseDark: true, reason: "Clinical tool page" };
  }

  return { shouldUseDark: false, reason: "Light mode conditions" };
}


// ═══════════════════════════════════════════════════════════════════════════
// PART 6: NERTagsDisplay (Improvement #13 — OpenMed NER tags)
// Shows chunk tags in citation cards / evidence sources
// ═══════════════════════════════════════════════════════════════════════════

interface NERTagsProps {
  nerTags?: Record<string, string[]>;
  evidenceStrength?: "strong" | "moderate" | "weak";
  compact?: boolean;
}

const TAG_COLORS: Record<string, string> = {
  product:      "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  complication: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  procedure:    "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  anatomical:   "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  drug_class:   "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300",
  evidence_type:"bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
};

export function NERTagsDisplay({ nerTags, evidenceStrength, compact = false }: NERTagsProps) {
  if (!nerTags || Object.keys(nerTags).length === 0) return null;

  // In compact mode, show at most 3 tags total
  const allTags: Array<{ category: string; value: string }> = [];
  for (const [cat, values] of Object.entries(nerTags)) {
    for (const v of values.slice(0, 2)) {
      allTags.push({ category: cat, value: v });
    }
  }
  const displayTags = compact ? allTags.slice(0, 3) : allTags.slice(0, 8);

  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {displayTags.map((tag, i) => (
        <span
          key={`${tag.category}-${i}`}
          className={`text-xs rounded-full px-1.5 py-0.5 font-medium
            ${TAG_COLORS[tag.category] ?? "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"}`}
          title={`${tag.category}: ${tag.value}`}
        >
          {tag.value}
        </span>
      ))}
      {evidenceStrength && !compact && (
        <span className={`text-xs rounded-full px-1.5 py-0.5 font-medium
          ${evidenceStrength === "strong" ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300"
            : evidenceStrength === "moderate" ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300"
            : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"}`}>
          {evidenceStrength} evidence
        </span>
      )}
    </div>
  );
}
