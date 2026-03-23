import { useState, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { useLocation, Link } from "wouter";
import {
  Zap, ArrowLeft, AlertTriangle, ChevronRight,
  Download, Clock, CheckCircle2, XCircle
} from "lucide-react";

interface ProtocolStep {
  step_number: number;
  action: string;
  rationale: string;
  priority: "primary" | "secondary";
}

interface DoseGuidance {
  substance: string;
  recommendation: string;
  notes: string;
}

interface ProtocolResponse {
  request_id: string;
  matched_protocol_name: string;
  matched_protocol_key: string;
  risk_assessment: {
    severity: string;
    urgency: string;
    likely_time_critical: boolean;
  };
  clinical_summary: string;
  immediate_actions: ProtocolStep[];
  dose_guidance: DoseGuidance[];
  red_flags: string[];
  escalation: string[];
  monitoring: string[];
  limitations: string[];
  follow_up_questions: string[];
  disclaimer: string;
}

const PROTOCOLS = [
  {
    key: "vascular_occlusion_ha_filler",
    label: "Vascular Occlusion",
    subtitle: "Blanching · pain · mottling after filler",
    severity: "critical",
    bg: "bg-red-600 hover:bg-red-700",
    ringColor: "ring-red-300",
  },
  {
    key: "anaphylaxis_allergic_reaction",
    label: "Anaphylaxis",
    subtitle: "Urticaria · hypotension · throat tightness",
    severity: "critical",
    bg: "bg-red-600 hover:bg-red-700",
    ringColor: "ring-red-300",
  },
  {
    key: "infection_or_biofilm_after_filler",
    label: "Infection / Biofilm",
    subtitle: "Warmth · erythema · fluctuance · fever",
    severity: "high",
    bg: "bg-orange-500 hover:bg-orange-600",
    ringColor: "ring-orange-300",
  },
  {
    key: "botulinum_toxin_ptosis",
    label: "Ptosis",
    subtitle: "Eyelid droop after botulinum toxin",
    severity: "high",
    bg: "bg-amber-500 hover:bg-amber-600",
    ringColor: "ring-amber-300",
  },
  {
    key: "tyndall_effect_ha_filler",
    label: "Tyndall Effect",
    subtitle: "Blue-grey discolouration · superficial HA",
    severity: "moderate",
    bg: "bg-sky-500 hover:bg-sky-600",
    ringColor: "ring-sky-300",
  },
  {
    key: "filler_nodules_inflammatory_or_noninflammatory",
    label: "Filler Nodules",
    subtitle: "Palpable lumps · weeks to months post-treatment",
    severity: "moderate",
    bg: "bg-slate-600 hover:bg-slate-700",
    ringColor: "ring-slate-300",
  },
  {
    key: "neuromodulator_resistance",
    label: "Toxin Resistance",
    subtitle: "No response · shortened duration · pseudo-resistance",
    severity: "routine",
    bg: "bg-violet-600 hover:bg-violet-700",
    ringColor: "ring-violet-300",
  },
  {
    key: "skin_necrosis_after_filler",
    label: "Skin Necrosis",
    subtitle: "Dusky/grey skin · livedo · post-filler ischaemia",
    severity: "critical",
    bg: "bg-red-700 hover:bg-red-800",
    ringColor: "ring-red-400",
  },
  {
    key: "vision_change_after_filler",
    label: "Vision Change",
    subtitle: "Visual loss · blurring · diplopia after filler",
    severity: "critical",
    bg: "bg-red-600 hover:bg-red-700",
    ringColor: "ring-red-300",
  },
];

async function fetchProtocol(query: string): Promise<ProtocolResponse> {
  const res = await fetch("/api/complications/protocol", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, mode: "emergency" }),
  });
  if (!res.ok) throw new Error("Protocol fetch failed");
  return res.json();
}

async function exportPDF(query: string): Promise<void> {
  const res = await fetch("/api/complications/export-pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, mode: "emergency" }),
  });
  if (res.ok) {
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `AesthetiCite_Protocol_${query}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  }
}

function SeverityBadge({ severity, urgency }: { severity: string; urgency: string }) {
  const isCritical = severity === "critical" || urgency === "immediate";
  const isHigh = severity === "high" || urgency === "urgent";
  const bg = isCritical ? "bg-red-600 text-white" : isHigh ? "bg-orange-500 text-white" : "bg-amber-400 text-white";
  return (
    <div className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${bg}`}>
      {isCritical && <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />}
      {urgency.replace(/_/g, " ").toUpperCase()}
    </div>
  );
}

export default function EmergencyPage() {
  const [location] = useLocation();
  const urlProtocol = new URLSearchParams(location.split("?")[1] || "").get("protocol") || "";

  const [activeKey, setActiveKey] = useState(urlProtocol);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [timerActive, setTimerActive] = useState(false);

  const protocolMutation = useMutation({
    mutationFn: fetchProtocol,
  });

  useEffect(() => {
    if (urlProtocol) {
      setActiveKey(urlProtocol);
      protocolMutation.mutate(urlProtocol);
      setTimerActive(true);
      setElapsedSeconds(0);
    }
  }, [urlProtocol]);

  useEffect(() => {
    if (!timerActive) return;
    const id = setInterval(() => setElapsedSeconds(s => s + 1), 1000);
    return () => clearInterval(id);
  }, [timerActive]);

  function handleSelectProtocol(key: string) {
    setActiveKey(key);
    protocolMutation.mutate(key);
    setTimerActive(true);
    setElapsedSeconds(0);
  }

  const protocol = protocolMutation.data;
  const isCritical = protocol?.risk_assessment?.urgency === "immediate"
    || protocol?.risk_assessment?.severity === "critical";

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  return (
    <div className="min-h-screen bg-slate-900">
      <header className="border-b border-red-900/50 bg-red-950/80 backdrop-blur-sm sticky top-0 z-20">
        <div className="mx-auto max-w-5xl px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/">
              <button className="text-red-400 hover:text-red-200 transition-colors" data-testid="button-emergency-back">
                <ArrowLeft className="w-4 h-4" />
              </button>
            </Link>
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-red-600 flex items-center justify-center">
                <Zap className="w-4 h-4 text-white" />
              </div>
              <div>
                <h1 className="text-sm font-black text-white leading-none">Emergency Protocols</h1>
                <p className="text-[10px] text-red-400 leading-none mt-0.5">AesthetiCite Clinical Safety Engine</p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {timerActive && (
              <div className="flex items-center gap-1.5 bg-red-900/60 rounded-lg px-3 py-1.5">
                <Clock className="w-3.5 h-3.5 text-red-400" />
                <span className="text-sm font-mono font-bold text-red-300" data-testid="text-elapsed-timer">{formatTime(elapsedSeconds)}</span>
              </div>
            )}
            {protocol && (
              <button
                onClick={() => exportPDF(activeKey)}
                data-testid="button-export-pdf"
                className="flex items-center gap-1.5 bg-white/10 hover:bg-white/20 text-white text-xs font-semibold rounded-lg px-3 py-1.5 transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                Print
              </button>
            )}
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-6 grid grid-cols-1 lg:grid-cols-4 gap-5">
        <div className="lg:col-span-1 space-y-2">
          <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Select Protocol</p>
          {PROTOCOLS.map((p) => (
            <button
              key={p.key}
              data-testid={`button-protocol-${p.key}`}
              onClick={() => handleSelectProtocol(p.key)}
              className={`
                w-full text-left rounded-xl p-3 transition-all border
                ${activeKey === p.key
                  ? `${p.bg} text-white border-transparent shadow-lg ring-2 ${p.ringColor}`
                  : "bg-white/5 hover:bg-white/10 text-slate-300 border-white/10"
                }
              `}
            >
              <p className="text-xs font-bold leading-none">{p.label}</p>
              <p className={`text-[10px] mt-1 leading-tight ${activeKey === p.key ? "text-white/80" : "text-slate-500"}`}>
                {p.subtitle}
              </p>
            </button>
          ))}
        </div>

        <div className="lg:col-span-3 space-y-4">
          {protocolMutation.isPending && (
            <div className="bg-white/5 rounded-2xl border border-white/10 p-12 flex flex-col items-center gap-4">
              <div className="w-8 h-8 border-2 border-red-500/30 border-t-red-500 rounded-full animate-spin" />
              <p className="text-sm text-slate-400">Loading protocol…</p>
            </div>
          )}

          {!activeKey && !protocolMutation.isPending && (
            <div className="bg-white/5 rounded-2xl border border-white/10 p-12 flex flex-col items-center text-center gap-4">
              <div className="w-14 h-14 rounded-full bg-red-900/50 flex items-center justify-center">
                <Zap className="w-7 h-7 text-red-500" />
              </div>
              <div>
                <p className="text-base font-bold text-white">Select a protocol</p>
                <p className="text-sm text-slate-400 mt-1">Choose the complication from the list</p>
              </div>
              <div className="flex flex-wrap gap-2 justify-center mt-2">
                {PROTOCOLS.filter(p => p.severity === "critical").map(p => (
                  <button
                    key={p.key}
                    onClick={() => handleSelectProtocol(p.key)}
                    className={`${p.bg} text-white text-xs font-bold rounded-lg px-4 py-2 transition-all`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {protocol && !protocolMutation.isPending && (
            <>
              <div className={`rounded-2xl p-5 ${isCritical ? "bg-red-900/40 border border-red-700/50" : "bg-white/5 border border-white/10"}`}>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-lg font-black text-white">{protocol.matched_protocol_name}</h2>
                    <p className="text-xs text-slate-400 mt-1 leading-relaxed max-w-lg">
                      {protocol.clinical_summary}
                    </p>
                  </div>
                  <SeverityBadge
                    severity={protocol.risk_assessment.severity}
                    urgency={protocol.risk_assessment.urgency}
                  />
                </div>
                {protocol.risk_assessment.likely_time_critical && (
                  <div className="flex items-center gap-2 mt-3 bg-red-800/40 rounded-lg px-3 py-2">
                    <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                    <p className="text-xs text-red-300 font-semibold">Time-critical — act immediately. Do not delay treatment while gathering more information.</p>
                  </div>
                )}
              </div>

              <div className="bg-white/5 rounded-2xl border border-white/10 p-5">
                <h3 className="text-xs font-bold text-red-400 uppercase tracking-wider mb-4">
                  Immediate Actions
                </h3>
                <div className="space-y-3">
                  {protocol.immediate_actions.map((step) => (
                    <div key={step.step_number} className="flex items-start gap-3">
                      <div className={`
                        w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-black flex-shrink-0 mt-0.5
                        ${step.priority === "primary" ? "bg-red-600 text-white" : "bg-white/10 text-slate-400"}
                      `}>
                        {step.step_number}
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-white">{step.action}</p>
                        <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{step.rationale}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {protocol.dose_guidance.length > 0 && (
                <div className="bg-white/5 rounded-2xl border border-white/10 p-5">
                  <h3 className="text-xs font-bold text-amber-400 uppercase tracking-wider mb-4">Dose Guidance</h3>
                  <div className="space-y-3">
                    {protocol.dose_guidance.map((d, i) => (
                      <div key={i} className="bg-white/5 rounded-xl p-3">
                        <p className="text-sm font-bold text-white">{d.substance}</p>
                        <p className="text-xs text-amber-300 mt-0.5 font-medium">{d.recommendation}</p>
                        <p className="text-xs text-slate-400 mt-1">{d.notes}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {protocol.red_flags.length > 0 && (
                  <div className="bg-red-950/40 border border-red-800/40 rounded-2xl p-4">
                    <h3 className="text-xs font-bold text-red-400 uppercase tracking-wider mb-3">Red Flags</h3>
                    <ul className="space-y-1.5">
                      {protocol.red_flags.map((flag, i) => (
                        <li key={i} className="flex items-start gap-2 text-xs text-red-300">
                          <XCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-red-500" />
                          {flag}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {protocol.escalation.length > 0 && (
                  <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
                    <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-3">Escalation</h3>
                    <ul className="space-y-1.5">
                      {protocol.escalation.map((step, i) => (
                        <li key={i} className="flex items-start gap-2 text-xs text-slate-300">
                          <ChevronRight className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-slate-500" />
                          {step}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {protocol.monitoring.length > 0 && (
                <div className="bg-white/5 rounded-2xl border border-white/10 p-4">
                  <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Monitoring</h3>
                  <ul className="space-y-1.5 grid grid-cols-1 sm:grid-cols-2 gap-1">
                    {protocol.monitoring.map((m, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-slate-400">
                        <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-slate-500" />
                        {m}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-[10px] text-slate-600 leading-relaxed px-1">
                {protocol.disclaimer}
              </p>
            </>
          )}

          {protocolMutation.isError && !protocolMutation.isPending && (
            <div className="bg-red-950/40 border border-red-800/40 rounded-2xl p-6 text-center">
              <AlertTriangle className="w-8 h-8 text-red-500 mx-auto mb-2" />
              <p className="text-sm text-red-300 font-semibold">Failed to load protocol</p>
              <p className="text-xs text-slate-400 mt-1">Check your connection and try again</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
