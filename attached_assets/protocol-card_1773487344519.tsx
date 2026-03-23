/**
 * AesthetiCite — Protocol Card Renderer
 * client/src/components/protocol-card.tsx
 *
 * Renders the protocol_card SSE event emitted by the protocol bridge.
 * Drop into ask.tsx message rendering alongside StructuredAnswer.
 *
 * Usage in ask.tsx:
 *
 *   // 1. Add to ChatMessage interface:
 *   protocolCard?: ProtocolCardData | null;
 *
 *   // 2. In onMeta / SSE handler, capture the event:
 *   case "protocol_card":
 *     setMessages(prev => prev.map(m =>
 *       m.id === assistantMsgId ? { ...m, protocolCard: data } : m
 *     ));
 *     break;
 *
 *   // 3. In message render, after <StructuredAnswer>:
 *   {msg.protocolCard && !msg.isStreaming && (
 *     <ProtocolCard data={msg.protocolCard} />
 *   )}
 *
 * The card is only shown after streaming is complete (isStreaming = false)
 * so it doesn't interrupt the answer flow.
 */

import { useState } from "react";
import {
  AlertTriangle, Syringe, Activity, Eye,
  ChevronDown, ChevronUp, BookOpen, Shield,
  Clock, TriangleAlert, Brain, FileDown, Loader2
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { getToken } from "@/lib/auth";

// ─── Types (mirrors ProtocolResponse from complication_protocol_engine.py) ──

export interface ProtocolStep {
  step_number: number;
  action: string;
  rationale: string;
  priority: "primary" | "secondary";
}

export interface DoseItem {
  substance: string;
  recommendation: string;
  notes: string;
}

export interface EvidenceRef {
  source_id: string;
  title: string;
  note: string;
  citation_text?: string;
  url?: string;
  source_type?: string;
}

export interface ProtocolCardData {
  // Standard ProtocolResponse fields
  request_id: string;
  engine_version: string;
  matched_protocol_key: string;
  matched_protocol_name: string;
  confidence: number;
  risk_assessment: {
    risk_score: number;
    severity: string;
    urgency: string;
    likely_time_critical: boolean;
    evidence_strength: string;
  };
  clinical_summary: string;
  immediate_actions: ProtocolStep[];
  dose_guidance: DoseItem[];
  red_flags: string[];
  escalation: string[];
  monitoring: string[];
  limitations: string[];
  follow_up_questions: string[];
  evidence: EvidenceRef[];
  disclaimer: string;
  // Bridge metadata
  _card_type: "complication_protocol";
  _triggered_by: string;
  _query: string;
}

// ─── Severity helpers ────────────────────────────────────────────────────────

function getSeverityStyle(severity: string) {
  switch (severity) {
    case "critical": return { border: "border-red-500/50", bg: "bg-red-500/8", badge: "bg-red-500 text-white", text: "text-red-600 dark:text-red-400" };
    case "high":     return { border: "border-orange-500/40", bg: "bg-orange-500/6", badge: "bg-orange-500 text-white", text: "text-orange-600 dark:text-orange-400" };
    case "moderate": return { border: "border-amber-500/40", bg: "bg-amber-500/6", badge: "bg-amber-500 text-white", text: "text-amber-600 dark:text-amber-400" };
    default:         return { border: "border-emerald-500/30", bg: "bg-emerald-500/5", badge: "bg-emerald-500 text-white", text: "text-emerald-600 dark:text-emerald-400" };
  }
}

function getUrgencyLabel(urgency: string) {
  switch (urgency) {
    case "immediate":  return { label: "Act immediately",   color: "text-red-600 dark:text-red-400" };
    case "urgent":     return { label: "Urgent",            color: "text-orange-600 dark:text-orange-400" };
    case "same_day":   return { label: "Same-day review",   color: "text-amber-600 dark:text-amber-400" };
    default:           return { label: "Routine",           color: "text-emerald-600 dark:text-emerald-400" };
  }
}

// ─── Collapsible section ─────────────────────────────────────────────────────

function ProtocolSection({
  icon, title, children, defaultOpen = true, accent = "default"
}: {
  icon: React.ReactNode; title: string; children: React.ReactNode;
  defaultOpen?: boolean; accent?: "red" | "amber" | "emerald" | "blue" | "default";
}) {
  const [open, setOpen] = useState(defaultOpen);
  const textColors = {
    red: "text-red-600 dark:text-red-400",
    amber: "text-amber-600 dark:text-amber-400",
    emerald: "text-emerald-600 dark:text-emerald-400",
    blue: "text-blue-600 dark:text-blue-400",
    default: "text-foreground",
  };
  return (
    <div className="border-t border-border/40 pt-3">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between gap-2 mb-2">
        <div className={`flex items-center gap-2 text-xs font-semibold uppercase tracking-wider ${textColors[accent]}`}>
          {icon}{title}
        </div>
        {open ? <ChevronUp className="w-3 h-3 text-muted-foreground/50" /> : <ChevronDown className="w-3 h-3 text-muted-foreground/50" />}
      </button>
      {open && children}
    </div>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────

export function ProtocolCard({ data }: { data: ProtocolCardData }) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);

  const style = getSeverityStyle(data.risk_assessment.severity);
  const urgency = getUrgencyLabel(data.risk_assessment.urgency);

  async function exportPDF() {
    setPdfLoading(true);
    try {
      const token = getToken();
      const res = await fetch("/api/complications/export-pdf", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          query: data._query,
          mode: "decision_support",
        }),
      });
      const d = await res.json();
      if (d.filename) window.open(`/exports/${d.filename}`, "_blank");
    } catch { /* non-fatal */ }
    finally { setPdfLoading(false); }
  }

  return (
    <Card className={`border-2 ${style.border} ${style.bg} mt-4`}>
      <CardContent className="p-4 space-y-3">

        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold ${style.badge}`}>
                <AlertTriangle className="w-3 h-3" />
                PROTOCOL
              </span>
              <span className={`text-xs font-semibold uppercase ${style.text}`}>
                {data.risk_assessment.severity}
              </span>
              <span className={`text-xs ${urgency.color} flex items-center gap-1`}>
                <Clock className="w-3 h-3" />
                {urgency.label}
              </span>
              {data.risk_assessment.likely_time_critical && (
                <span className="text-xs font-bold text-red-500 animate-pulse">⏱ TIME CRITICAL</span>
              )}
            </div>
            <h3 className={`text-sm font-bold ${style.text}`}>{data.matched_protocol_name}</h3>
            <p className="text-xs text-foreground/75 leading-relaxed">{data.clinical_summary}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={exportPDF} disabled={pdfLoading}
            className="flex-shrink-0 gap-1 text-xs h-7 text-muted-foreground hover:text-foreground">
            {pdfLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <FileDown className="w-3 h-3" />}
            PDF
          </Button>
        </div>

        {/* Red flags — always visible */}
        {data.red_flags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {data.red_flags.map((flag, i) => (
              <span key={i} className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-red-500/15 border border-red-500/25 text-xs text-red-700 dark:text-red-300 font-medium">
                <TriangleAlert className="w-2.5 h-2.5" /> {flag}
              </span>
            ))}
          </div>
        )}

        {/* Immediate actions */}
        {data.immediate_actions.length > 0 && (
          <ProtocolSection icon={<Syringe className="w-3 h-3" />} title="Immediate Actions" accent="red" defaultOpen>
            <ol className="space-y-2">
              {data.immediate_actions.map((step) => (
                <li key={step.step_number} className="flex gap-2.5">
                  <span className={`flex-shrink-0 w-5 h-5 rounded-full text-xs font-bold flex items-center justify-center ${
                    step.priority === "primary" ? "bg-red-500 text-white" : "bg-muted text-muted-foreground"
                  }`}>{step.step_number}</span>
                  <div>
                    <p className="text-xs font-medium text-foreground">{step.action}</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">{step.rationale}</p>
                  </div>
                </li>
              ))}
            </ol>
          </ProtocolSection>
        )}

        {/* Dose guidance */}
        {data.dose_guidance.length > 0 && (
          <ProtocolSection icon={<Activity className="w-3 h-3" />} title="Dose Guidance" accent="amber" defaultOpen>
            <div className="space-y-2">
              {data.dose_guidance.map((d, i) => (
                <div key={i} className="p-2 rounded bg-background/60 border border-border/50">
                  <p className="text-xs font-semibold">{d.substance}</p>
                  <p className="text-xs text-foreground/80 mt-0.5">{d.recommendation}</p>
                  {d.notes && <p className="text-[11px] text-muted-foreground mt-0.5 italic">{d.notes}</p>}
                </div>
              ))}
            </div>
          </ProtocolSection>
        )}

        {/* Escalation */}
        {data.escalation.length > 0 && (
          <ProtocolSection icon={<AlertTriangle className="w-3 h-3" />} title="Escalation" accent="amber" defaultOpen>
            <ul className="space-y-1">
              {data.escalation.map((e, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-foreground/80">
                  <span className="w-1 h-1 rounded-full bg-amber-500 mt-1.5 flex-shrink-0" />{e}
                </li>
              ))}
            </ul>
          </ProtocolSection>
        )}

        {/* Monitoring */}
        {data.monitoring.length > 0 && (
          <ProtocolSection icon={<Eye className="w-3 h-3" />} title="Monitoring" accent="blue" defaultOpen={false}>
            <ul className="space-y-1">
              {data.monitoring.map((m, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-foreground/80">
                  <span className="w-1 h-1 rounded-full bg-blue-500 mt-1.5 flex-shrink-0" />{m}
                </li>
              ))}
            </ul>
          </ProtocolSection>
        )}

        {/* Procedure insight */}
        {data.follow_up_questions.length > 0 && (
          <ProtocolSection icon={<Brain className="w-3 h-3" />} title="Follow-up Questions" accent="default" defaultOpen={false}>
            <ol className="space-y-1">
              {data.follow_up_questions.map((q, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                  <span className="flex-shrink-0 w-4 h-4 rounded-full bg-muted text-[10px] font-bold flex items-center justify-center">{i + 1}</span>
                  {q}
                </li>
              ))}
            </ol>
          </ProtocolSection>
        )}

        {/* Evidence */}
        {data.evidence.length > 0 && (
          <div className="border-t border-border/40 pt-3">
            <button onClick={() => setEvidenceOpen(!evidenceOpen)}
              className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors w-full">
              <BookOpen className="w-3 h-3" />
              Evidence ({data.evidence.length} sources)
              {evidenceOpen ? <ChevronUp className="w-3 h-3 ml-auto" /> : <ChevronDown className="w-3 h-3 ml-auto" />}
            </button>
            {evidenceOpen && (
              <div className="mt-2 space-y-2">
                {data.evidence.map((ev, i) => (
                  <div key={i} className="p-2 rounded bg-muted/30 border border-border/40 space-y-0.5">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-[10px] font-bold text-primary">[{ev.source_id}]</span>
                      {ev.url && <a href={ev.url} target="_blank" rel="noreferrer" className="text-[10px] text-primary hover:underline">↗</a>}
                    </div>
                    <p className="text-[11px] font-medium text-foreground/90">{ev.title}</p>
                    <p className="text-[11px] text-muted-foreground">{ev.note}</p>
                    {ev.citation_text && (
                      <p className="text-[11px] italic text-muted-foreground border-l border-primary/30 pl-2">"{ev.citation_text}"</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Confidence + disclaimer */}
        <div className="flex items-center justify-between gap-2 border-t border-border/40 pt-2">
          <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
            <span>Confidence: {Math.round(data.confidence * 100)}%</span>
            <span>Evidence: {data.risk_assessment.evidence_strength}</span>
            <span>Engine v{data.engine_version}</span>
          </div>
          <Shield className="w-3 h-3 text-muted-foreground/40" />
        </div>
        <p className="text-[10px] text-muted-foreground/50 leading-relaxed">{data.disclaimer}</p>
      </CardContent>
    </Card>
  );
}
