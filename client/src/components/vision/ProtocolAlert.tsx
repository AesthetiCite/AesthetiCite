import { AlertTriangle, ShieldAlert, Info, ExternalLink, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

export interface TriggeredProtocol {
  protocol_key: string;
  protocol_name: string;
  urgency: "critical" | "high" | "moderate";
  confidence: number;
  detected_signals: string[];
  headline: string;
  immediate_action: string;
  view_protocol_url: string;
  disclaimer: string;
}

interface ProtocolAlertProps {
  protocols: TriggeredProtocol[];
}

const URGENCY_CONFIG = {
  critical: {
    border: "border-red-500",
    bg: "bg-red-50 dark:bg-red-950/30",
    badge: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
    icon: <ShieldAlert className="h-5 w-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />,
    label: "CRITICAL",
    labelColor: "text-red-700 dark:text-red-400",
  },
  high: {
    border: "border-orange-400",
    bg: "bg-orange-50 dark:bg-orange-950/30",
    badge: "bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300",
    icon: <AlertTriangle className="h-5 w-5 text-orange-500 dark:text-orange-400 flex-shrink-0 mt-0.5" />,
    label: "HIGH",
    labelColor: "text-orange-700 dark:text-orange-400",
  },
  moderate: {
    border: "border-yellow-400",
    bg: "bg-yellow-50 dark:bg-yellow-950/30",
    badge: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300",
    icon: <Info className="h-5 w-5 text-yellow-600 dark:text-yellow-400 flex-shrink-0 mt-0.5" />,
    label: "MODERATE",
    labelColor: "text-yellow-700 dark:text-yellow-400",
  },
} as const;

function formatSignal(signal: string): string {
  return signal.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.7 ? "bg-red-500" : value >= 0.5 ? "bg-orange-400" : "bg-yellow-400";
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="h-1.5 flex-1 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted-foreground w-10 text-right">{pct}%</span>
    </div>
  );
}

function SingleProtocolCard({ protocol }: { protocol: TriggeredProtocol }) {
  const [expanded, setExpanded] = useState(protocol.urgency === "critical");
  const cfg = URGENCY_CONFIG[protocol.urgency];

  return (
    <div className={`rounded-lg border-l-4 ${cfg.border} ${cfg.bg} p-4 space-y-2`} data-testid={`card-protocol-${protocol.protocol_key}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 min-w-0">
          {cfg.icon}
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-xs font-bold uppercase tracking-wide ${cfg.labelColor}`}>
                {cfg.label}
              </span>
              <span className={`text-xs rounded-full px-2 py-0.5 font-medium ${cfg.badge}`}>
                {protocol.protocol_name}
              </span>
            </div>
            <p className="text-sm font-semibold text-foreground mt-0.5">{protocol.headline}</p>
          </div>
        </div>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex-shrink-0 text-muted-foreground hover:text-foreground transition-colors"
          aria-label={expanded ? "Collapse" : "Expand"}
          data-testid={`button-protocol-expand-${protocol.protocol_key}`}
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      <div>
        <p className="text-xs text-muted-foreground">Signal confidence</p>
        <ConfidenceBar value={protocol.confidence} />
      </div>

      {protocol.detected_signals.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {protocol.detected_signals.map((s) => (
            <span
              key={s}
              className="text-xs bg-white/70 dark:bg-white/10 border border-gray-200 dark:border-gray-700 rounded px-1.5 py-0.5 text-muted-foreground"
            >
              {formatSignal(s)}
            </span>
          ))}
        </div>
      )}

      {expanded && (
        <div className="space-y-3 pt-1 border-t border-black/10 dark:border-white/10">
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
              Immediate action
            </p>
            <p className="text-sm text-foreground leading-relaxed">{protocol.immediate_action}</p>
          </div>
          <a
            href={protocol.view_protocol_url}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline"
            data-testid={`link-protocol-full-${protocol.protocol_key}`}
          >
            Open full protocol
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
          <p className="text-xs text-muted-foreground italic">{protocol.disclaimer}</p>
        </div>
      )}
    </div>
  );
}

export function ProtocolAlert({ protocols }: ProtocolAlertProps) {
  if (!protocols || protocols.length === 0) return null;

  const hasCritical = protocols.some((p) => p.urgency === "critical");

  return (
    <div className="space-y-3 mt-4" data-testid="section-protocol-alerts">
      <div className="flex items-center gap-2">
        <div className={`h-2 w-2 rounded-full ${hasCritical ? "bg-red-500 animate-pulse" : "bg-orange-400"}`} />
        <h3 className="text-sm font-semibold text-foreground">
          {hasCritical
            ? "⚠ Complication protocol triggered"
            : "Potential complication signals detected"}
        </h3>
        <span className="ml-auto text-xs text-muted-foreground">
          {protocols.length} protocol{protocols.length > 1 ? "s" : ""}
        </span>
      </div>
      <div className="space-y-2">
        {protocols.map((p) => (
          <SingleProtocolCard key={p.protocol_key} protocol={p} />
        ))}
      </div>
    </div>
  );
}
