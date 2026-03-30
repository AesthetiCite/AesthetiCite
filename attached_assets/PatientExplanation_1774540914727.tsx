/**
 * PatientExplanation.tsx — Improvement 5
 *
 * One-tap button that converts the top differential diagnosis into
 * plain-language patient counselling text.
 *
 * Calls POST /api/visual/patient-explanation with the differential data.
 * Returns plain English the clinician can read directly to the patient
 * or print as a patient handout.
 *
 * Usage:
 *   <PatientExplanation
 *     differential={result.differential}
 *     visualSummary={result.visual_summary}
 *     token={token}
 *   />
 */

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { FileText, Loader2, Copy, Check, Printer } from "lucide-react";

interface DiagnosisItem {
  rank: number;
  diagnosis: string;
  tier: string;
  confidence: number;
  confidence_label: string;
  urgency: string;
  key_visual_findings: string[];
}

interface PatientExplanationResponse {
  headline: string;
  what_we_see: string;
  what_it_means: string;
  what_happens_next: string;
  reassurance: string;
  when_to_seek_help: string;
  disclaimer: string;
}

interface Props {
  differential: DiagnosisItem[];
  visualSummary: string;
  token: string;
  clinicName?: string;
}

async function fetchPatientExplanation(
  differential: DiagnosisItem[],
  visualSummary: string,
  token: string
): Promise<PatientExplanationResponse> {
  const res = await fetch("/api/visual/patient-explanation", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      differential: differential.slice(0, 3),
      visual_summary: visualSummary,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || `Error ${res.status}`);
  }
  return res.json();
}

function PrintableHandout({
  content,
  clinicName,
  onClose,
}: {
  content: PatientExplanationResponse;
  clinicName: string;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4 print:p-0 print:bg-white print:fixed print:inset-0">
      <div className="bg-white rounded-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto shadow-2xl print:shadow-none print:rounded-none print:max-h-none">
        {/* Print header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between print:hidden">
          <span className="font-semibold text-gray-900">Patient explanation</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => window.print()} className="gap-1.5 text-xs">
              <Printer className="w-3.5 h-3.5" /> Print
            </Button>
            <Button variant="ghost" size="sm" onClick={onClose} className="text-xs">
              Close
            </Button>
          </div>
        </div>

        <div className="px-6 py-5 space-y-4">
          {/* Clinic header (print) */}
          <div className="hidden print:block border-b border-gray-200 pb-3 mb-4">
            <p className="text-lg font-bold text-gray-900">{clinicName}</p>
            <p className="text-xs text-gray-500">Patient Information Sheet · {new Date().toLocaleDateString("en-GB")}</p>
          </div>

          {/* Headline */}
          <div className="rounded-lg bg-teal-50 border border-teal-200 px-4 py-3">
            <p className="text-base font-bold text-teal-900">{content.headline}</p>
          </div>

          {/* Sections */}
          {[
            { title: "What we saw",         text: content.what_we_see        },
            { title: "What this means",      text: content.what_it_means      },
            { title: "What happens next",    text: content.what_happens_next  },
            { title: "Reassurance",          text: content.reassurance        },
            { title: "When to seek help",    text: content.when_to_seek_help, urgent: true },
          ].map(({ title, text, urgent }) => (
            <div key={title}>
              <p className={`text-xs font-bold uppercase tracking-wide mb-1 ${urgent ? "text-red-600" : "text-gray-500"}`}>
                {title}
              </p>
              <p className="text-sm text-gray-700 leading-relaxed">{text}</p>
            </div>
          ))}

          {/* Disclaimer */}
          <div className="rounded-lg bg-gray-50 border border-gray-200 px-4 py-3 mt-4">
            <p className="text-xs text-gray-400 italic">{content.disclaimer}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export function PatientExplanation({ differential, visualSummary, token, clinicName = "AesthetiCite" }: Props) {
  const [content, setContent]   = useState<PatientExplanationResponse | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [copied, setCopied]     = useState(false);
  const [showPrint, setShowPrint] = useState(false);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchPatientExplanation(differential, visualSummary, token);
      setContent(result);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const copyText = () => {
    if (!content) return;
    const text = [
      content.headline,
      "",
      "What we saw:",     content.what_we_see,
      "",
      "What this means:", content.what_it_means,
      "",
      "What happens next:", content.what_happens_next,
      "",
      content.when_to_seek_help,
    ].join("\n");
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (!content && !loading) {
    return (
      <div>
        <Button
          variant="outline"
          onClick={generate}
          className="w-full gap-2 text-sm border-teal-200 text-teal-700 hover:bg-teal-50"
        >
          <FileText className="w-4 h-4" />
          Generate patient explanation
        </Button>
        {error && (
          <p className="text-xs text-red-600 mt-2">{error}</p>
        )}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 py-3 justify-center">
        <Loader2 className="w-4 h-4 animate-spin text-teal-500" />
        Generating patient explanation…
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-teal-200 bg-teal-50 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-teal-200 bg-teal-100 flex items-center justify-between">
        <span className="text-xs font-semibold text-teal-800 uppercase tracking-wide">
          Patient explanation
        </span>
        <div className="flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="sm"
            className="text-xs gap-1 text-teal-700 h-7"
            onClick={copyText}
          >
            {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
            {copied ? "Copied" : "Copy"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-xs gap-1 text-teal-700 h-7"
            onClick={() => setShowPrint(true)}
          >
            <Printer className="w-3 h-3" /> Print
          </Button>
        </div>
      </div>

      {content && (
        <div className="px-4 py-4 space-y-3">
          {/* Headline */}
          <p className="text-sm font-bold text-teal-900">{content.headline}</p>

          {/* Preview of main sections */}
          <div className="space-y-2">
            {[
              { label: "What we saw",      text: content.what_we_see      },
              { label: "What this means",  text: content.what_it_means    },
              { label: "What happens next",text: content.what_happens_next },
            ].map(({ label, text }) => (
              <div key={label}>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-0.5">{label}</p>
                <p className="text-sm text-gray-700 leading-relaxed">{text}</p>
              </div>
            ))}
          </div>

          {/* When to seek help */}
          <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2.5">
            <p className="text-xs font-bold text-red-600 uppercase tracking-wide mb-0.5">When to seek help</p>
            <p className="text-sm text-red-800">{content.when_to_seek_help}</p>
          </div>

          {/* Re-generate */}
          <Button
            variant="ghost"
            size="sm"
            onClick={generate}
            className="text-xs text-teal-600 gap-1"
          >
            <Loader2 className="w-3 h-3" /> Regenerate
          </Button>
        </div>
      )}

      {/* Printable overlay */}
      {showPrint && content && (
        <PrintableHandout
          content={content}
          clinicName={clinicName}
          onClose={() => setShowPrint(false)}
        />
      )}
    </div>
  );
}
