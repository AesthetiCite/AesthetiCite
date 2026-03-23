/**
 * AesthetiCite — Medico-Legal Report Generator UI
 *
 * The money feature. Every complication must be documented.
 * This makes it ONE TAP.
 *
 * Features:
 *   - Pre-filled from complication session context
 *   - 12-section structured form (all optional except complication)
 *   - Live preview of sections as filled
 *   - Export PDF button → triggers download
 *   - Copy button → plain text to clipboard
 *   - Share button → Web Share API or copy link
 *   - Stores report_id for retrieval
 *
 * Can be used as:
 *   1. Modal triggered from complication-decision.tsx
 *   2. Standalone page at /report?complication=...
 *   3. Post-workflow completion screen
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Accordion, AccordionContent, AccordionItem, AccordionTrigger,
} from "@/components/ui/accordion";
import {
  FileText, Download, Copy, Share2, CheckCircle2,
  RefreshCw, ChevronRight, AlertTriangle, Shield, Printer,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { getToken } from "@/lib/auth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ReportSections {
  report_id: string;
  report_date: string;
  incident: Record<string, string>;
  clinician: Record<string, string>;
  patient: Record<string, string>;
  procedure: Record<string, string>;
  complication: Record<string, string>;
  timeline: string;
  treatment: { summary: string; first_intervention: string; hyaluronidase_dose: string };
  patient_response: string;
  outcome: string;
  time_to_resolution: string;
  escalation: Record<string, string>;
  follow_up: Record<string, string>;
  evidence: { protocol_used: string; references: any[] };
  clinician_notes: string;
  declaration: string;
  disclaimer: string;
}

interface ReportResponse {
  report_id: string;
  generated_at: string;
  sections: ReportSections;
  status: string;
}

// Report input form state
interface ReportForm {
  complication: string;
  clinic_name: string;
  practitioner_name: string;
  practitioner_role: string;
  practitioner_registration: string;
  patient_reference: string;
  procedure: string;
  region: string;
  product_name: string;
  product_batch: string;
  volume_ml: string;
  technique: string;
  incident_date: string;
  incident_time: string;
  onset_time: string;
  symptoms: string;
  suspected_diagnosis: string;
  timeline: string;
  treatment_given: string;
  hyaluronidase_dose: string;
  time_of_first_intervention: string;
  patient_response: string;
  outcome: string;
  time_to_resolution: string;
  escalation_actions: string;
  referrals_made: string;
  emergency_services_called: boolean;
  follow_up_plan: string;
  review_date: string;
  protocol_used: string;
  clinician_notes: string;
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const token = getToken();
  const res = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json();
}

async function downloadPdf(form: ReportForm): Promise<void> {
  const token = getToken();
  const res = await fetch("/api/generate-report/pdf", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(form),
  });
  if (!res.ok) throw new Error("PDF generation failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `aestheticite-incident-report.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Sections text builder (for copy/share)
// ---------------------------------------------------------------------------

function sectionsToText(s: ReportSections): string {
  const sep = "─".repeat(50);
  const lines = [
    "AESTHETICITE CLINICAL INCIDENT REPORT",
    `Report ID: ${s.report_id.slice(0, 8).toUpperCase()}`,
    `Generated: ${s.report_date}`,
    sep,
    "",
    "1. INCIDENT",
    `Clinic: ${s.incident.clinic_name}`,
    `Date: ${s.incident.incident_date}  Time: ${s.incident.incident_time}`,
    "",
    "2. CLINICIAN",
    `${s.clinician.name} — ${s.clinician.role}`,
    `Reg: ${s.clinician.registration}`,
    "",
    "3. PATIENT",
    `Reference: ${s.patient.reference}`,
    "",
    "4. PROCEDURE",
    `Procedure: ${s.procedure.procedure}  Region: ${s.procedure.region}`,
    `Product: ${s.procedure.product}  Batch: ${s.procedure.batch_number}`,
    "",
    "5. COMPLICATION",
    `Type: ${s.complication.type}`,
    `Onset: ${s.complication.onset}`,
    `Symptoms: ${s.complication.symptoms}`,
    "",
    "6. TIMELINE",
    s.timeline,
    "",
    "7. TREATMENT",
    s.treatment.summary,
    "",
    "8. OUTCOME",
    `Response: ${s.patient_response}`,
    `Outcome: ${s.outcome}`,
    `Resolution time: ${s.time_to_resolution}`,
    "",
    "9. ESCALATION",
    s.escalation.actions,
    s.escalation.referrals,
    "",
    "10. FOLLOW-UP",
    s.follow_up.plan,
    `Review: ${s.follow_up.review_date}`,
    "",
    sep,
    s.declaration,
    sep,
    s.disclaimer,
  ];
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Form field component
// ---------------------------------------------------------------------------

function Field({
  label, value, onChange, placeholder, multiline = false, required = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  multiline?: boolean;
  required?: boolean;
}) {
  return (
    <div>
      <Label className="text-xs">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </Label>
      {multiline ? (
        <Textarea
          className="mt-1 text-sm resize-none"
          rows={2}
          placeholder={placeholder ?? label}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <Input
          className="mt-1 h-8 text-sm"
          placeholder={placeholder ?? label}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live preview panel
// ---------------------------------------------------------------------------

function ReportPreview({ sections }: { sections: ReportSections }) {
  const sectionData = [
    { title: "Incident",      data: sections.incident },
    { title: "Clinician",     data: sections.clinician },
    { title: "Patient",       data: sections.patient },
    { title: "Procedure",     data: sections.procedure },
    { title: "Complication",  data: sections.complication },
  ];

  return (
    <div className="font-mono text-xs space-y-3 bg-slate-950 text-slate-200 rounded-xl p-4 max-h-[400px] overflow-y-auto">
      <div className="text-center border-b border-slate-700 pb-2">
        <p className="text-sm font-bold text-white">CLINICAL INCIDENT REPORT</p>
        <p className="text-slate-400">ID: {sections.report_id.slice(0, 8).toUpperCase()}</p>
      </div>

      {sectionData.map(({ title, data }) => (
        <div key={title}>
          <p className="text-slate-400 uppercase text-[10px] tracking-widest mb-1">{title}</p>
          {Object.entries(data).filter(([k]) => k !== "privacy_note").map(([k, v]) => (
            v && v !== "Not recorded" ? (
              <div key={k} className="flex gap-2 text-[11px]">
                <span className="text-slate-500 flex-shrink-0 w-24">{k.replace(/_/g, " ")}:</span>
                <span className="text-slate-200">{String(v)}</span>
              </div>
            ) : null
          ))}
        </div>
      ))}

      {sections.timeline && sections.timeline !== "Timeline not recorded." && (
        <div>
          <p className="text-slate-400 uppercase text-[10px] tracking-widest mb-1">Timeline</p>
          <p className="text-slate-200 whitespace-pre-line text-[11px]">{sections.timeline}</p>
        </div>
      )}

      <div>
        <p className="text-slate-400 uppercase text-[10px] tracking-widest mb-1">Treatment</p>
        <p className="text-slate-200 whitespace-pre-line text-[11px]">{sections.treatment.summary}</p>
      </div>

      <div>
        <p className="text-slate-400 uppercase text-[10px] tracking-widest mb-1">Outcome</p>
        <p className="text-slate-200 text-[11px]">{sections.outcome}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface MedicoLegalReportProps {
  // Pre-fill from session context
  complication?: string;
  procedure?: string;
  region?: string;
  product?: string;
  treatment?: string;
  outcome?: string;
  symptoms?: string;
  hyaluronidase?: string;
  evidenceRefs?: any[];
  protocolUsed?: string;
  // Display
  trigger?: React.ReactNode;
  defaultOpen?: boolean;
  onReportGenerated?: (reportId: string) => void;
}

export function MedicoLegalReport({
  complication = "",
  procedure = "",
  region = "",
  product = "",
  treatment = "",
  outcome = "",
  symptoms = "",
  hyaluronidase = "",
  evidenceRefs = [],
  protocolUsed = "AesthetiCite Clinical Protocol",
  trigger,
  defaultOpen = false,
  onReportGenerated,
}: MedicoLegalReportProps) {
  const { toast } = useToast();
  const [open, setOpen] = useState(defaultOpen);
  const [step, setStep] = useState<"form" | "preview" | "done">("form");
  const [reportData, setReportData] = useState<ReportResponse | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  const [form, setForm] = useState<ReportForm>({
    complication,
    clinic_name: "",
    practitioner_name: "",
    practitioner_role: "",
    practitioner_registration: "",
    patient_reference: "",
    procedure,
    region,
    product_name: product,
    product_batch: "",
    volume_ml: "",
    technique: "",
    incident_date: new Date().toLocaleDateString("en-GB"),
    incident_time: new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }),
    onset_time: "Immediate post-injection",
    symptoms,
    suspected_diagnosis: complication,
    timeline: "",
    treatment_given: treatment,
    hyaluronidase_dose: hyaluronidase,
    time_of_first_intervention: "",
    patient_response: "",
    outcome,
    time_to_resolution: "",
    escalation_actions: "",
    referrals_made: "",
    emergency_services_called: false,
    follow_up_plan: "",
    review_date: "",
    protocol_used: protocolUsed,
    clinician_notes: "",
  });

  const set = (key: keyof ReportForm) => (val: string) =>
    setForm((p) => ({ ...p, [key]: val }));

  const generateMutation = useMutation({
    mutationFn: () =>
      apiPost<ReportResponse>("/api/generate-report", {
        ...form,
        evidence_refs: evidenceRefs,
      }),
    onSuccess: (data) => {
      setReportData(data);
      setStep("preview");
      onReportGenerated?.(data.report_id);
    },
    onError: (e: Error) =>
      toast({ title: "Error generating report", description: e.message, variant: "destructive" }),
  });

  const handleDownloadPdf = async () => {
    setPdfLoading(true);
    try {
      await downloadPdf({ ...form, evidence_refs: evidenceRefs } as any);
      toast({ title: "PDF downloaded" });
    } catch (e: any) {
      toast({ title: "PDF error", description: e.message, variant: "destructive" });
    } finally {
      setPdfLoading(false);
    }
  };

  const handleCopy = () => {
    if (!reportData) return;
    const text = sectionsToText(reportData.sections);
    navigator.clipboard.writeText(text);
    toast({ title: "Copied to clipboard" });
  };

  const handleShare = async () => {
    if (!reportData) return;
    const text = sectionsToText(reportData.sections);
    if (navigator.share) {
      try {
        await navigator.share({
          title: `AesthetiCite Incident Report — ${form.complication}`,
          text,
        });
      } catch { /* user cancelled */ }
    } else {
      navigator.clipboard.writeText(text);
      toast({ title: "Copied for sharing" });
    }
  };

  const formContent = (
    <div className="space-y-1">
      <Accordion type="multiple" defaultValue={["incident", "complication", "treatment"]}>

        {/* COMPLICATION — always open */}
        <AccordionItem value="complication">
          <AccordionTrigger className="text-sm font-semibold py-2">
            <span className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-500" />
              Complication *
            </span>
          </AccordionTrigger>
          <AccordionContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
              <Field label="Complication type" value={form.complication} onChange={set("complication")} required />
              <Field label="Onset" value={form.onset_time} onChange={set("onset_time")} placeholder="e.g. Immediate, 2 min post-injection" />
              <Field label="Symptoms" value={form.symptoms} onChange={set("symptoms")} multiline />
              <Field label="Suspected diagnosis" value={form.suspected_diagnosis} onChange={set("suspected_diagnosis")} />
            </div>
          </AccordionContent>
        </AccordionItem>

        {/* TREATMENT */}
        <AccordionItem value="treatment">
          <AccordionTrigger className="text-sm font-semibold py-2">
            <span className="flex items-center gap-2">
              <Shield className="h-4 w-4 text-blue-500" />
              Treatment & Outcome
            </span>
          </AccordionTrigger>
          <AccordionContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
              <Field label="Treatment given" value={form.treatment_given} onChange={set("treatment_given")} multiline />
              <Field label="Hyaluronidase dose" value={form.hyaluronidase_dose} onChange={set("hyaluronidase_dose")} placeholder="e.g. 1500 IU" />
              <Field label="First intervention time" value={form.time_of_first_intervention} onChange={set("time_of_first_intervention")} placeholder="e.g. 14:32" />
              <Field label="Patient response" value={form.patient_response} onChange={set("patient_response")} placeholder="e.g. Blanching resolving at 30 min" />
              <Field label="Outcome" value={form.outcome} onChange={set("outcome")} placeholder="e.g. Resolved at 90 min" />
              <Field label="Time to resolution" value={form.time_to_resolution} onChange={set("time_to_resolution")} placeholder="e.g. 90 min" />
            </div>
          </AccordionContent>
        </AccordionItem>

        {/* INCIDENT */}
        <AccordionItem value="incident">
          <AccordionTrigger className="text-sm font-semibold py-2">Incident Details</AccordionTrigger>
          <AccordionContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
              <Field label="Clinic name" value={form.clinic_name} onChange={set("clinic_name")} />
              <Field label="Date" value={form.incident_date} onChange={set("incident_date")} />
              <Field label="Time" value={form.incident_time} onChange={set("incident_time")} />
              <Field label="Practitioner name" value={form.practitioner_name} onChange={set("practitioner_name")} />
              <Field label="Role" value={form.practitioner_role} onChange={set("practitioner_role")} placeholder="e.g. Aesthetic Nurse, Doctor" />
              <Field label="Registration number" value={form.practitioner_registration} onChange={set("practitioner_registration")} />
              <Field label="Patient reference (non-identifiable)" value={form.patient_reference} onChange={set("patient_reference")} placeholder="e.g. REF-2024-042" />
            </div>
          </AccordionContent>
        </AccordionItem>

        {/* PROCEDURE */}
        <AccordionItem value="procedure">
          <AccordionTrigger className="text-sm font-semibold py-2">Procedure</AccordionTrigger>
          <AccordionContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
              <Field label="Procedure" value={form.procedure} onChange={set("procedure")} />
              <Field label="Region" value={form.region} onChange={set("region")} />
              <Field label="Product" value={form.product_name} onChange={set("product_name")} />
              <Field label="Batch number" value={form.product_batch} onChange={set("product_batch")} />
              <Field label="Volume (ml)" value={form.volume_ml} onChange={set("volume_ml")} />
              <Field label="Technique" value={form.technique} onChange={set("technique")} placeholder="e.g. Cannula, needle" />
            </div>
          </AccordionContent>
        </AccordionItem>

        {/* ESCALATION */}
        <AccordionItem value="escalation">
          <AccordionTrigger className="text-sm font-semibold py-2">Escalation & Follow-up</AccordionTrigger>
          <AccordionContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
              <Field label="Escalation actions" value={form.escalation_actions} onChange={set("escalation_actions")} multiline placeholder="e.g. No escalation required" />
              <Field label="Referrals made" value={form.referrals_made} onChange={set("referrals_made")} placeholder="e.g. None / Ophthalmology" />
              <Field label="Follow-up plan" value={form.follow_up_plan} onChange={set("follow_up_plan")} multiline />
              <Field label="Review date" value={form.review_date} onChange={set("review_date")} />
              <Field label="Timeline (optional)" value={form.timeline} onChange={set("timeline")} multiline placeholder="Chronological sequence of events" />
              <Field label="Clinician notes" value={form.clinician_notes} onChange={set("clinician_notes")} multiline />
            </div>
          </AccordionContent>
        </AccordionItem>

      </Accordion>
    </div>
  );

  const content = (
    <div className="space-y-4">
      {step === "form" && (
        <>
          {formContent}
          <Button
            className="w-full gap-1.5"
            onClick={() => generateMutation.mutate()}
            disabled={!form.complication || generateMutation.isPending}
          >
            {generateMutation.isPending ? (
              <><RefreshCw className="h-3.5 w-3.5 animate-spin" /> Generating…</>
            ) : (
              <><FileText className="h-3.5 w-3.5" /> Generate Report</>
            )}
          </Button>
        </>
      )}

      {step === "preview" && reportData && (
        <div className="space-y-4">
          {/* Action buttons */}
          <div className="grid grid-cols-3 gap-2">
            <Button
              onClick={handleDownloadPdf}
              disabled={pdfLoading}
              className="gap-1.5"
            >
              {pdfLoading ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              <span className="hidden sm:inline">Export</span> PDF
            </Button>
            <Button variant="outline" onClick={handleCopy} className="gap-1.5">
              <Copy className="h-3.5 w-3.5" />
              Copy
            </Button>
            <Button variant="outline" onClick={handleShare} className="gap-1.5">
              <Share2 className="h-3.5 w-3.5" />
              Share
            </Button>
          </div>

          {/* Live preview */}
          <ReportPreview sections={reportData.sections} />

          {/* Report ID */}
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
            Report ID: {reportData.report_id.slice(0, 8).toUpperCase()} · Saved
          </div>

          <Button
            size="sm"
            variant="ghost"
            onClick={() => setStep("form")}
            className="w-full text-xs"
          >
            ← Edit report
          </Button>

          <p className="text-[10px] text-muted-foreground/60 text-center">
            Retain with patient records per your clinic's data retention policy.
            Consult your MDO for specific documentation requirements.
          </p>
        </div>
      )}
    </div>
  );

  if (!trigger) {
    // Inline version — no dialog wrapper
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 mb-2">
          <FileText className="h-4 w-4 text-blue-500" />
          <h3 className="font-semibold text-sm">Medico-Legal Incident Report</h3>
          <Badge variant="outline" className="text-[10px]">MDO-ready</Badge>
        </div>
        {content}
      </div>
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-sm flex items-center gap-2">
            <FileText className="h-4 w-4 text-blue-500" />
            Medico-Legal Incident Report
            <Badge variant="outline" className="text-[10px]">MDO-ready</Badge>
          </DialogTitle>
          <p className="text-xs text-muted-foreground">
            All fields are optional except complication type. Pre-filled from your session.
          </p>
        </DialogHeader>
        {content}
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Convenience export button — drop-in for any page
// ---------------------------------------------------------------------------

export function ReportExportButton({
  complication,
  treatment,
  outcome,
  procedure,
  region,
  product,
  symptoms,
  hyaluronidase,
  evidenceRefs,
  size = "sm",
}: {
  complication: string;
  treatment?: string;
  outcome?: string;
  procedure?: string;
  region?: string;
  product?: string;
  symptoms?: string;
  hyaluronidase?: string;
  evidenceRefs?: any[];
  size?: "sm" | "default";
}) {
  return (
    <MedicoLegalReport
      complication={complication}
      treatment={treatment}
      outcome={outcome}
      procedure={procedure}
      region={region}
      product={product}
      symptoms={symptoms}
      hyaluronidase={hyaluronidase}
      evidenceRefs={evidenceRefs}
      trigger={
        <Button size={size} className="gap-1.5">
          <FileText className="h-3.5 w-3.5" />
          Generate Report
        </Button>
      }
    />
  );
}
