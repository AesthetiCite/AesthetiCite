/**
 * AesthetiCite — Safety & Escalation Block
 * UpToDate-inspired safety layer that appears in every response.
 *
 * Renders:
 *   - Risk level badge (critical/high/moderate/low) with colour coding
 *   - Risk warning summary
 *   - Immediate actions list with priority badges
 *   - When to STOP section
 *   - When to REFER section
 *   - Escalation criteria
 *   - Monitoring instructions
 *   - Medico-legal documentation checklist
 *
 * Usage:
 *   <SafetyEscalationBlock safety={meta.safety} />
 *
 * The component is always rendered when safety data is present.
 * For critical/high risk it renders expanded by default.
 * For low risk it renders collapsed with a subtle indicator.
 */

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AlertTriangle, AlertCircle, XCircle, CheckCircle2,
  ChevronDown, ChevronUp, ChevronRight, Phone,
  StopCircle, UserCheck, Activity, FileText, Info,
  Clock, Shield,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types — mirrors SafetyAssessment from safety_layer.py
// ---------------------------------------------------------------------------

export type RiskLevel = "critical" | "high" | "moderate" | "low";

export interface SafetyAction {
  action: string;
  priority: "immediate" | "urgent" | "routine";
}

export interface MedicoLegal {
  document: string[];
  disclaimer: string;
}

export interface SafetyAssessment {
  risk_level: RiskLevel;
  risk_warning: string;
  call_emergency: boolean;
  actions: SafetyAction[];
  when_to_stop: string[];
  when_to_refer: string[];
  escalation: string;
  escalation_criteria: string[];
  monitoring: string[];
  medico_legal: MedicoLegal;
  query_type: string;
  risk_score: number;
}

// ---------------------------------------------------------------------------
// Risk level config
// ---------------------------------------------------------------------------

interface RiskConfig {
  label: string;
  icon: React.ElementType;
  cardBorder: string;
  headerBg: string;
  headerText: string;
  badgeCls: string;
  defaultExpanded: boolean;
}

const RISK_CONFIG: Record<RiskLevel, RiskConfig> = {
  critical: {
    label: "Critical Risk",
    icon: XCircle,
    cardBorder: "border-red-500 dark:border-red-600",
    headerBg: "bg-red-600 dark:bg-red-800",
    headerText: "text-white",
    badgeCls: "bg-red-100 text-red-800 border-red-300 dark:bg-red-900/50 dark:text-red-200",
    defaultExpanded: true,
  },
  high: {
    label: "High Risk",
    icon: AlertTriangle,
    cardBorder: "border-orange-400 dark:border-orange-600",
    headerBg: "bg-orange-500 dark:bg-orange-700",
    headerText: "text-white",
    badgeCls: "bg-orange-100 text-orange-800 border-orange-300 dark:bg-orange-900/30 dark:text-orange-200",
    defaultExpanded: true,
  },
  moderate: {
    label: "Moderate Risk",
    icon: AlertCircle,
    cardBorder: "border-amber-300 dark:border-amber-700",
    headerBg: "bg-amber-500 dark:bg-amber-700",
    headerText: "text-white",
    badgeCls: "bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/30 dark:text-amber-200",
    defaultExpanded: false,
  },
  low: {
    label: "Low Risk",
    icon: CheckCircle2,
    cardBorder: "border-slate-200 dark:border-slate-700",
    headerBg: "bg-slate-100 dark:bg-slate-800",
    headerText: "text-slate-700 dark:text-slate-300",
    badgeCls: "bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-400",
    defaultExpanded: false,
  },
};

// Priority badge for actions
const PRIORITY_CONFIG = {
  immediate: {
    label: "NOW",
    cls: "bg-red-600 text-white text-[10px] px-1.5 py-0",
  },
  urgent: {
    label: "URGENT",
    cls: "bg-orange-500 text-white text-[10px] px-1.5 py-0",
  },
  routine: {
    label: "ROUTINE",
    cls: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300 text-[10px] px-1.5 py-0",
  },
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SectionLabel({
  icon: Icon,
  label,
  className = "",
}: {
  icon: React.ElementType;
  label: string;
  className?: string;
}) {
  return (
    <p className={`text-xs font-semibold uppercase tracking-wide flex items-center gap-1.5 mb-2 ${className}`}>
      <Icon className="h-3.5 w-3.5" />
      {label}
    </p>
  );
}

function ActionRow({ action }: { action: SafetyAction }) {
  const pCfg = PRIORITY_CONFIG[action.priority];
  return (
    <div className="flex items-start gap-2.5 py-1.5 border-b last:border-0 last:pb-0">
      <Badge className={`${pCfg.cls} flex-shrink-0 mt-0.5 rounded font-bold`}>
        {pCfg.label}
      </Badge>
      <p className="text-sm leading-snug">{action.action}</p>
    </div>
  );
}

function BulletList({
  items,
  icon: Icon = ChevronRight,
  itemClassName = "",
}: {
  items: string[];
  icon?: React.ElementType;
  itemClassName?: string;
}) {
  if (!items.length) return null;
  return (
    <ul className="space-y-1">
      {items.map((item, i) => (
        <li key={i} className={`flex items-start gap-1.5 text-sm ${itemClassName}`}>
          <Icon className="h-3.5 w-3.5 flex-shrink-0 mt-0.5 text-current opacity-60" />
          {item}
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Emergency banner — shown at top when call_emergency is true
// ---------------------------------------------------------------------------

function EmergencyBanner() {
  return (
    <div className="flex items-center gap-3 bg-red-600 text-white rounded-lg p-3 mb-3 animate-pulse">
      <Phone className="h-5 w-5 flex-shrink-0" />
      <div>
        <p className="font-bold text-sm">CALL 999 / EMERGENCY SERVICES NOW</p>
        <p className="text-xs opacity-90">Do not wait. This is a life-threatening emergency.</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface SafetyEscalationBlockProps {
  safety: SafetyAssessment;
  /** Section number for display, e.g. "4" */
  sectionNumber?: string;
  className?: string;
}

export function SafetyEscalationBlock({
  safety,
  sectionNumber,
  className = "",
}: SafetyEscalationBlockProps) {
  const cfg = RISK_CONFIG[safety.risk_level] ?? RISK_CONFIG.low;
  const [expanded, setExpanded] = useState(cfg.defaultExpanded);
  const [medicoLegalOpen, setMedicoLegalOpen] = useState(false);
  const RiskIcon = cfg.icon;

  return (
    <Card className={`${cfg.cardBorder} border-2 ${className}`} role="region" aria-label="Safety and escalation">
      {/* Header */}
      <CardHeader
        className={`${cfg.headerBg} ${cfg.headerText} py-3 px-4 rounded-t-lg cursor-pointer`}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            {sectionNumber && (
              <span className="text-xs opacity-70 font-normal">{sectionNumber}</span>
            )}
            <RiskIcon className="h-4 w-4 flex-shrink-0" />
            <CardTitle className={`text-sm ${cfg.headerText}`}>
              ⚠️ Safety &amp; Escalation
            </CardTitle>
            <Badge
              variant="outline"
              className={`text-xs border ${cfg.badgeCls} ${
                safety.risk_level === "critical" || safety.risk_level === "high"
                  ? "bg-white/20 border-white/40 text-white"
                  : ""
              }`}
            >
              {cfg.label}
            </Badge>
          </div>
          <button
            type="button"
            className={`${cfg.headerText} opacity-70 hover:opacity-100`}
            aria-label={expanded ? "Collapse" : "Expand"}
          >
            {expanded ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </button>
        </div>

        {/* Risk warning — always visible even when collapsed */}
        <p className={`text-xs mt-1 ${cfg.headerText} opacity-90 leading-snug`}>
          {safety.risk_warning}
        </p>
      </CardHeader>

      {/* Body — shown/hidden based on expanded state */}
      {expanded && (
        <CardContent className="px-4 pb-4 pt-3 space-y-4">

          {/* Emergency banner */}
          {safety.call_emergency && <EmergencyBanner />}

          {/* ESCALATION — most important, always at the top */}
          {safety.escalation && (
            <div className={`p-3 rounded-lg border-l-4 ${
              safety.risk_level === "critical" ? "bg-red-50 dark:bg-red-950/20 border-l-red-500" :
              safety.risk_level === "high"     ? "bg-orange-50 dark:bg-orange-950/20 border-l-orange-500" :
              safety.risk_level === "moderate" ? "bg-amber-50 dark:bg-amber-950/20 border-l-amber-500" :
              "bg-slate-50 dark:bg-slate-900/50 border-l-slate-400"
            }`}>
              <p className="text-xs font-semibold mb-0.5 flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" />
                Key Escalation Threshold
              </p>
              <p className="text-sm font-medium">{safety.escalation}</p>
            </div>
          )}

          {/* IMMEDIATE ACTIONS */}
          {safety.actions?.length > 0 && (
            <div>
              <SectionLabel icon={Activity} label="Actions" />
              <div className="space-y-0 rounded-lg border overflow-hidden">
                {safety.actions.map((action, i) => (
                  <div key={i} className="px-3">
                    <ActionRow action={action} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* WHEN TO STOP + WHEN TO REFER — grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {safety.when_to_stop?.length > 0 && (
              <div className="bg-red-50 dark:bg-red-950/20 rounded-lg p-3">
                <SectionLabel
                  icon={StopCircle}
                  label="When to Stop"
                  className="text-red-700 dark:text-red-400"
                />
                <BulletList
                  items={safety.when_to_stop}
                  itemClassName="text-red-800 dark:text-red-300"
                />
              </div>
            )}

            {safety.when_to_refer?.length > 0 && (
              <div className="bg-blue-50 dark:bg-blue-950/20 rounded-lg p-3">
                <SectionLabel
                  icon={UserCheck}
                  label="When to Refer"
                  className="text-blue-700 dark:text-blue-400"
                />
                <BulletList
                  items={safety.when_to_refer}
                  itemClassName="text-blue-800 dark:text-blue-300"
                />
              </div>
            )}
          </div>

          {/* ESCALATION CRITERIA */}
          {safety.escalation_criteria?.length > 0 &&
            safety.escalation_criteria.length > 1 && (
            <div>
              <SectionLabel icon={AlertTriangle} label="Full Escalation Criteria" />
              <BulletList
                items={safety.escalation_criteria}
                icon={ChevronRight}
              />
            </div>
          )}

          {/* MONITORING */}
          {safety.monitoring?.length > 0 && (
            <div>
              <SectionLabel icon={Activity} label="Monitoring" />
              <BulletList items={safety.monitoring} />
            </div>
          )}

          {/* MEDICO-LEGAL SECTION — collapsible */}
          {safety.medico_legal && (
            <div className="border-t pt-3">
              <button
                type="button"
                onClick={() => setMedicoLegalOpen(!medicoLegalOpen)}
                className="flex items-center gap-2 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors w-full text-left"
              >
                <FileText className="h-3.5 w-3.5" />
                Medico-Legal Documentation
                {medicoLegalOpen ? (
                  <ChevronUp className="h-3.5 w-3.5 ml-auto" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5 ml-auto" />
                )}
              </button>

              {medicoLegalOpen && (
                <div className="mt-2 space-y-3">
                  {safety.medico_legal.document?.length > 0 && (
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Document the following:</p>
                      <ul className="space-y-1">
                        {safety.medico_legal.document.map((item, i) => (
                          <li key={i} className="flex items-start gap-1.5 text-xs">
                            <span className="text-muted-foreground/60 flex-shrink-0 font-mono">
                              {i + 1}.
                            </span>
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {safety.medico_legal.disclaimer && (
                    <div className="flex items-start gap-2 p-2.5 bg-muted/50 rounded-lg">
                      <Shield className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0 mt-0.5" />
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        {safety.medico_legal.disclaimer}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

        </CardContent>
      )}

      {/* Collapsed summary — shows key escalation even when collapsed */}
      {!expanded && safety.escalation && (
        <CardContent className="px-4 py-2">
          <p className="text-xs text-muted-foreground flex items-center gap-1.5">
            <Clock className="h-3 w-3 flex-shrink-0" />
            {safety.escalation}
          </p>
        </CardContent>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Compact inline version — for use in list views, answer previews
// ---------------------------------------------------------------------------

interface SafetyInlineBadgeProps {
  riskLevel: RiskLevel;
  escalation?: string;
  className?: string;
}

export function SafetyInlineBadge({
  riskLevel,
  escalation,
  className = "",
}: SafetyInlineBadgeProps) {
  const cfg = RISK_CONFIG[riskLevel] ?? RISK_CONFIG.low;
  const Icon = cfg.icon;
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <Badge variant="outline" className={`text-xs ${cfg.badgeCls} flex items-center gap-1`}>
        <Icon className="h-3 w-3" />
        {cfg.label}
      </Badge>
      {escalation && (
        <p className="text-xs text-muted-foreground truncate">{escalation}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hook — derive safety from meta payload
// ---------------------------------------------------------------------------

export function useSafety(meta: Record<string, any> | null): SafetyAssessment | null {
  if (!meta?.safety) return null;
  return meta.safety as SafetyAssessment;
}
