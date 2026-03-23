import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  AlertTriangle, Shield, ClipboardList, BookOpen, BarChart3,
  Zap, CheckCircle2, AlertCircle, XCircle, Plus, Download, Copy,
  Printer, Pin, Archive, Star, FileText, ChevronRight, Info,
  Building2, Stethoscope, Activity,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useClinicContext } from "@/hooks/use-clinic-context";
import { ClinicSwitcher } from "@/components/clinic-switcher";
import { getToken } from "@/lib/auth";

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------

async function api<T>(
  path: string,
  opts: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const res = await fetch(path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Evidence hierarchy badge
// ---------------------------------------------------------------------------

const EVIDENCE_LEVEL_STYLES: Record<string, string> = {
  Guideline:   "bg-violet-100 text-violet-800 dark:bg-violet-900/30 dark:text-violet-300",
  Consensus:   "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
  Review:      "bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300",
  RCT:         "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
  "Case Series":"bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
};

function EvidenceBadge({ level }: { level: string }) {
  const cls = EVIDENCE_LEVEL_STYLES[level] ?? "bg-muted text-muted-foreground";
  return (
    <Badge variant="outline" className={`text-xs px-2 py-0 ${cls}`}>
      {level}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Outcome badge
// ---------------------------------------------------------------------------

function OutcomeBadge({ outcome }: { outcome: string | null }) {
  if (!outcome) return null;
  const o = outcome.toLowerCase();
  if (o.includes("resolved")) return <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 text-xs">{outcome}</Badge>;
  if (o.includes("urgent") || o.includes("referral")) return <Badge className="bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-xs">{outcome}</Badge>;
  if (o.includes("ongoing") || o.includes("partial")) return <Badge className="bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 text-xs">{outcome}</Badge>;
  return <Badge variant="outline" className="text-xs">{outcome}</Badge>;
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState({ icon: Icon, title, description }: {
  icon: React.ElementType; title: string; description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <Icon className="h-12 w-12 text-muted-foreground/40 mb-4" />
      <p className="text-sm font-medium text-muted-foreground">{title}</p>
      <p className="text-xs text-muted-foreground/60 mt-1 max-w-sm">{description}</p>
    </div>
  );
}

// ===========================================================================
// TAB 1 — Live Guidance
// ===========================================================================

const COMPLICATION_TYPES = [
  "Vascular occlusion",
  "Anaphylaxis / severe allergic reaction",
  "Ptosis",
  "Tyndall effect",
  "Inflammatory nodule / granuloma",
  "Infection / biofilm",
  "Skin necrosis",
  "Vision change / visual disturbance",
  "Bruising / haematoma",
  "Oedema / swelling",
  "Delayed inflammatory reaction (DIR)",
  "Asymmetry",
  "Filler migration",
  "Other",
];

const REGIONS = [
  "Lips", "Periorbital / tear trough", "Nasolabial folds", "Cheeks / midface",
  "Jawline", "Chin", "Temple", "Nose", "Forehead", "Glabella", "Neck", "Hands",
];

const PROCEDURES = [
  "Lip filler", "Cheek filler", "Tear trough filler", "Jawline filler",
  "Nasolabial fold filler", "Chin filler", "Temple filler",
  "Botulinum toxin (Botox)", "Biostimulator (Sculptra / Radiesse)",
  "Skin booster", "PRP", "Thread lift",
];

function LiveGuidanceTab({ clinicId }: { clinicId: string }) {
  const { toast } = useToast();
  const [form, setForm] = useState({
    complication_type: "",
    procedure: "",
    region: "",
    product_type: "",
    symptom_onset: "",
    pain: "",
    clinical_signs: [] as string[],
    injector_experience: "",
  });
  const [result, setResult] = useState<any>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api("/api/workspace/network-guidance/query", {
        method: "POST",
        body: JSON.stringify({ ...form, clinic_id: clinicId }),
      }),
    onSuccess: (data) => setResult(data),
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const saveProtocolMutation = useMutation({
    mutationFn: () =>
      api("/api/workspace/protocols", {
        method: "POST",
        body: JSON.stringify({
          clinic_id: clinicId,
          title: `${form.complication_type} — ${form.procedure || "General"}`,
          source_query: result?.query ?? "",
          answer_json: result?.structured_workflow ?? {},
          citations_json: result?.evidence_items ?? [],
          tags: [form.complication_type?.toLowerCase().replace(/\s+/g, "-")],
        }),
      }),
    onSuccess: () => toast({ title: "Protocol saved", description: "Added to Saved Protocols." }),
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const toggleSign = (sign: string) =>
    setForm((prev) => ({
      ...prev,
      clinical_signs: prev.clinical_signs.includes(sign)
        ? prev.clinical_signs.filter((s) => s !== sign)
        : [...prev.clinical_signs, sign],
    }));

  const SIGNS = [
    "Blanching", "Livedo reticularis", "Pain", "Oedema", "Nodule",
    "Visual disturbance", "Ptosis", "Skin discolouration", "Erythema",
  ];

  const workflowIcons: Record<string, React.ElementType> = {
    "1. Identify": AlertTriangle,
    "2. Immediate Action": Zap,
    "3. Treatment": Stethoscope,
    "4. Escalation": AlertCircle,
    "5. Follow-Up": Activity,
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6">
      {/* Intake form */}
      <div className="space-y-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <Shield className="h-4 w-4 text-blue-500" />
              Clinical Intake
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label className="text-xs">Complication Type *</Label>
              <Select onValueChange={(v) => setForm((p) => ({ ...p, complication_type: v }))}>
                <SelectTrigger className="mt-1 h-8 text-sm">
                  <SelectValue placeholder="Select complication…" />
                </SelectTrigger>
                <SelectContent>
                  {COMPLICATION_TYPES.map((c) => (
                    <SelectItem key={c} value={c} className="text-sm">{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Procedure</Label>
                <Select onValueChange={(v) => setForm((p) => ({ ...p, procedure: v }))}>
                  <SelectTrigger className="mt-1 h-8 text-sm">
                    <SelectValue placeholder="Select…" />
                  </SelectTrigger>
                  <SelectContent>
                    {PROCEDURES.map((p) => (
                      <SelectItem key={p} value={p} className="text-sm">{p}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Region</Label>
                <Select onValueChange={(v) => setForm((p) => ({ ...p, region: v }))}>
                  <SelectTrigger className="mt-1 h-8 text-sm">
                    <SelectValue placeholder="Select…" />
                  </SelectTrigger>
                  <SelectContent>
                    {REGIONS.map((r) => (
                      <SelectItem key={r} value={r} className="text-sm">{r}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label className="text-xs">Product / Brand</Label>
              <Input
                className="mt-1 h-8 text-sm"
                placeholder="e.g. Juvederm Ultra, Botox…"
                onChange={(e) => setForm((p) => ({ ...p, product_type: e.target.value }))}
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Symptom Onset</Label>
                <Input
                  className="mt-1 h-8 text-sm"
                  placeholder="e.g. Immediate, 2h"
                  onChange={(e) => setForm((p) => ({ ...p, symptom_onset: e.target.value }))}
                />
              </div>
              <div>
                <Label className="text-xs">Pain Level</Label>
                <Input
                  className="mt-1 h-8 text-sm"
                  placeholder="e.g. Severe, mild"
                  onChange={(e) => setForm((p) => ({ ...p, pain: e.target.value }))}
                />
              </div>
            </div>

            <div>
              <Label className="text-xs mb-2 block">Clinical Signs (select all that apply)</Label>
              <div className="flex flex-wrap gap-1.5">
                {SIGNS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => toggleSign(s)}
                    className={`text-xs px-2 py-1 rounded-full border transition-colors ${
                      form.clinical_signs.includes(s)
                        ? "bg-blue-600 border-blue-600 text-white"
                        : "border-border text-muted-foreground hover:border-blue-400"
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <Label className="text-xs">Injector Experience</Label>
              <Select onValueChange={(v) => setForm((p) => ({ ...p, injector_experience: v }))}>
                <SelectTrigger className="mt-1 h-8 text-sm">
                  <SelectValue placeholder="Select…" />
                </SelectTrigger>
                <SelectContent>
                  {["Trainee (<1 yr)", "Junior (1–3 yr)", "Intermediate (3–5 yr)", "Senior (5+ yr)"].map((l) => (
                    <SelectItem key={l} value={l} className="text-sm">{l}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <Button
              className="w-full"
              disabled={!form.complication_type || mutation.isPending}
              onClick={() => mutation.mutate()}
            >
              {mutation.isPending ? "Running…" : "Get Clinical Guidance"}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Results panel */}
      <div className="space-y-4">
        {!result && !mutation.isPending && (
          <EmptyState
            icon={Shield}
            title="Enter complication details to get guidance"
            description="Evidence ranked by clinical hierarchy: guidelines first, then consensus, reviews, and RCTs."
          />
        )}

        {mutation.isPending && (
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-24 w-full rounded-lg" />
            ))}
          </div>
        )}

        {result && (
          <div className="space-y-4">
            {/* Workflow steps */}
            {Object.entries(result.structured_workflow ?? {}).map(([key, step]: [string, any]) => {
              const Icon = workflowIcons[step.label] ?? Shield;
              const isEscalation = step.label === "4. Escalation";
              return (
                <Card
                  key={key}
                  className={isEscalation ? "border-red-300 dark:border-red-800" : ""}
                >
                  <CardHeader className="pb-2 pt-3 px-4">
                    <CardTitle className={`text-sm flex items-center gap-2 ${isEscalation ? "text-red-600 dark:text-red-400" : ""}`}>
                      <Icon className="h-4 w-4" />
                      {step.label}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-3">
                    {Array.isArray(step.content) ? (
                      <ul className="space-y-1">
                        {step.content.map((item: string, i: number) => (
                          <li key={i} className="flex items-start gap-2 text-sm">
                            <ChevronRight className="h-3.5 w-3.5 mt-0.5 flex-shrink-0 text-muted-foreground" />
                            {item}
                          </li>
                        ))}
                      </ul>
                    ) : typeof step.content === "object" && step.content !== null ? (
                      <dl className="space-y-1">
                        {Object.entries(step.content).map(([k, v]) => (
                          <div key={k} className="text-sm">
                            <span className="font-medium capitalize">{k.replace(/_/g, " ")}: </span>
                            <span className="text-muted-foreground">{String(v)}</span>
                          </div>
                        ))}
                      </dl>
                    ) : (
                      <p className="text-sm text-muted-foreground">{String(step.content)}</p>
                    )}
                  </CardContent>
                </Card>
              );
            })}

            {/* Evidence items */}
            {result.evidence_items && result.evidence_items.length > 0 && (
              <Card>
                <CardHeader className="pb-2 pt-3 px-4">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <BookOpen className="h-4 w-4" />
                    Evidence ({result.evidence_items.length})
                    <span className="text-xs text-muted-foreground font-normal ml-1">
                      {result.rerank_note}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-3 space-y-2">
                  {result.evidence_items.map((ev: any, i: number) => (
                    <div key={i} className="flex items-start justify-between gap-3 text-sm border-b pb-2 last:border-0 last:pb-0">
                      <div>
                        <p className="font-medium text-xs">{ev.title}</p>
                        <p className="text-xs text-muted-foreground">{ev.source} {ev.year}</p>
                      </div>
                      {ev.level && <EvidenceBadge level={ev.level} />}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Action buttons */}
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => saveProtocolMutation.mutate()}
                disabled={saveProtocolMutation.isPending}
              >
                <Pin className="h-3.5 w-3.5 mr-1.5" />
                Save Protocol
              </Button>
              <Button size="sm" variant="outline">
                <ClipboardList className="h-3.5 w-3.5 mr-1.5" />
                Start Case Log
              </Button>
              <Button size="sm" variant="outline">
                <FileText className="h-3.5 w-3.5 mr-1.5" />
                Generate Report
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ===========================================================================
// TAB 2 — Case Log
// ===========================================================================

const OUTCOMES = ["Resolved", "Partial resolution", "Ongoing", "Urgent referral", "Lost to follow-up"];

function CaseLogTab({ clinicId }: { clinicId: string }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [showForm, setShowForm] = useState(false);
  const [filters, setFilters] = useState({ complication_type: "", outcome: "" });
  const [form, setForm] = useState({
    patient_reference: "",
    event_date: "",
    practitioner_name: "",
    procedure: "",
    region: "",
    product_used: "",
    complication_type: "",
    symptoms: "",
    suspected_diagnosis: "",
    treatment_given: "",
    hyaluronidase_dose: "",
    follow_up_plan: "",
    outcome: "",
    notes: "",
  });

  const params = new URLSearchParams({
    clinic_id: clinicId,
    ...(filters.complication_type ? { complication_type: filters.complication_type } : {}),
    ...(filters.outcome ? { outcome: filters.outcome } : {}),
  });

  const { data, isLoading } = useQuery({
    queryKey: ["case-logs", clinicId, filters],
    queryFn: () => api<{ total: number; items: any[] }>(`/api/workspace/case-logs?${params}`),
    enabled: !!clinicId,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api("/api/workspace/case-logs", {
        method: "POST",
        body: JSON.stringify({ ...form, clinic_id: clinicId }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["case-logs"] });
      setShowForm(false);
      toast({ title: "Case log created" });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const exportCSV = () => {
    const token = getToken();
    window.open(`/api/workspace/case-logs/export/csv?clinic_id=${clinicId}`, "_blank");
  };

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-2 flex-1 min-w-0">
          <Input
            className="h-8 text-sm max-w-48"
            placeholder="Filter by complication…"
            value={filters.complication_type}
            onChange={(e) => setFilters((p) => ({ ...p, complication_type: e.target.value }))}
          />
          <Select onValueChange={(v) => setFilters((p) => ({ ...p, outcome: v === "all" ? "" : v }))}>
            <SelectTrigger className="h-8 text-sm w-40">
              <SelectValue placeholder="Outcome…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All outcomes</SelectItem>
              {OUTCOMES.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <Button size="sm" variant="outline" onClick={exportCSV}>
          <Download className="h-3.5 w-3.5 mr-1.5" /> Export CSV
        </Button>
        <Button size="sm" onClick={() => setShowForm(true)}>
          <Plus className="h-3.5 w-3.5 mr-1.5" /> New Case Log
        </Button>
      </div>

      {/* New case log form */}
      {showForm && (
        <Card className="border-blue-200 dark:border-blue-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <Plus className="h-4 w-4" /> New Complication Case Log
            </CardTitle>
            <CardDescription className="text-xs">
              Patient reference must be non-identifiable (e.g. REF-2024-001, initials + DOB year).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {[
                { key: "patient_reference", label: "Patient Reference *", placeholder: "e.g. REF-2024-001" },
                { key: "event_date", label: "Date / Time", placeholder: "YYYY-MM-DD HH:MM", type: "datetime-local" },
                { key: "practitioner_name", label: "Practitioner", placeholder: "Dr. Name" },
                { key: "product_used", label: "Product Used", placeholder: "e.g. Juvederm Ultra 1ml" },
                { key: "treatment_given", label: "Treatment Given", placeholder: "e.g. Hyaluronidase 1500IU" },
                { key: "hyaluronidase_dose", label: "Hyaluronidase Dose", placeholder: "e.g. 1500IU" },
              ].map(({ key, label, placeholder, type }) => (
                <div key={key}>
                  <Label className="text-xs">{label}</Label>
                  <Input
                    className="mt-1 h-8 text-sm"
                    placeholder={placeholder}
                    type={type ?? "text"}
                    value={(form as any)[key]}
                    onChange={(e) => setForm((p) => ({ ...p, [key]: e.target.value }))}
                  />
                </div>
              ))}

              <div>
                <Label className="text-xs">Procedure</Label>
                <Select onValueChange={(v) => setForm((p) => ({ ...p, procedure: v }))}>
                  <SelectTrigger className="mt-1 h-8 text-sm">
                    <SelectValue placeholder="Select…" />
                  </SelectTrigger>
                  <SelectContent>
                    {PROCEDURES.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label className="text-xs">Region</Label>
                <Select onValueChange={(v) => setForm((p) => ({ ...p, region: v }))}>
                  <SelectTrigger className="mt-1 h-8 text-sm">
                    <SelectValue placeholder="Select…" />
                  </SelectTrigger>
                  <SelectContent>
                    {REGIONS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label className="text-xs">Complication Type</Label>
                <Select onValueChange={(v) => setForm((p) => ({ ...p, complication_type: v }))}>
                  <SelectTrigger className="mt-1 h-8 text-sm">
                    <SelectValue placeholder="Select…" />
                  </SelectTrigger>
                  <SelectContent>
                    {COMPLICATION_TYPES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label className="text-xs">Outcome</Label>
                <Select onValueChange={(v) => setForm((p) => ({ ...p, outcome: v }))}>
                  <SelectTrigger className="mt-1 h-8 text-sm">
                    <SelectValue placeholder="Select…" />
                  </SelectTrigger>
                  <SelectContent>
                    {OUTCOMES.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              {[
                { key: "symptoms", label: "Symptoms", rows: 2 },
                { key: "suspected_diagnosis", label: "Suspected Diagnosis", rows: 2 },
                { key: "follow_up_plan", label: "Follow-Up Plan", rows: 2 },
                { key: "notes", label: "Notes", rows: 2 },
              ].map(({ key, label, rows }) => (
                <div key={key}>
                  <Label className="text-xs">{label}</Label>
                  <Textarea
                    className="mt-1 text-sm resize-none"
                    rows={rows}
                    placeholder={label + "…"}
                    value={(form as any)[key]}
                    onChange={(e) => setForm((p) => ({ ...p, [key]: e.target.value }))}
                  />
                </div>
              ))}
            </div>

            <div className="flex gap-2 mt-4">
              <Button
                size="sm"
                onClick={() => createMutation.mutate()}
                disabled={!form.patient_reference || createMutation.isPending}
              >
                {createMutation.isPending ? "Saving…" : "Save Case Log"}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setShowForm(false)}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Case log table */}
      {isLoading ? (
        <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} className="h-12 w-full" />)}</div>
      ) : !data?.items.length ? (
        <EmptyState icon={ClipboardList} title="No case logs yet" description="Start logging complications to build your clinic dataset." />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Reference</TableHead>
                <TableHead className="text-xs">Date</TableHead>
                <TableHead className="text-xs">Practitioner</TableHead>
                <TableHead className="text-xs">Procedure</TableHead>
                <TableHead className="text-xs">Complication</TableHead>
                <TableHead className="text-xs">Outcome</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((row) => (
                <TableRow key={row.id} className="text-sm">
                  <TableCell className="font-mono text-xs">{row.patient_reference}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {row.event_date ? new Date(row.event_date).toLocaleDateString() : "—"}
                  </TableCell>
                  <TableCell className="text-xs">{row.practitioner_name ?? "—"}</TableCell>
                  <TableCell className="text-xs">{row.procedure ?? "—"}</TableCell>
                  <TableCell className="text-xs">
                    <Badge variant="outline" className="text-xs">{row.complication_type ?? "—"}</Badge>
                  </TableCell>
                  <TableCell><OutcomeBadge outcome={row.outcome} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="px-4 py-2 text-xs text-muted-foreground border-t">
            {data.total} total records
          </div>
        </Card>
      )}
    </div>
  );
}

// ===========================================================================
// TAB 3 — Saved Protocols
// ===========================================================================

function SavedProtocolsTab({ clinicId, canAdmin }: { clinicId: string; canAdmin: boolean }) {
  const qc = useQueryClient();
  const { toast } = useToast();

  const { data: protocols = [], isLoading } = useQuery({
    queryKey: ["protocols", clinicId],
    queryFn: () => api<any[]>(`/api/workspace/protocols?clinic_id=${clinicId}`),
    enabled: !!clinicId,
  });

  const patchMutation = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Record<string, any> }) =>
      api(`/api/workspace/protocols/${id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["protocols"] });
      toast({ title: "Protocol updated" });
    },
  });

  return (
    <div className="space-y-3">
      {isLoading ? (
        <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} className="h-28 w-full" />)}</div>
      ) : !protocols.length ? (
        <EmptyState icon={BookOpen} title="No saved protocols" description="Save protocols from Live Guidance to build your clinic library." />
      ) : (
        protocols.map((p) => (
          <Card key={p.id} className={p.is_pinned ? "border-blue-300 dark:border-blue-700" : ""}>
            <CardHeader className="pb-2 pt-3 px-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <CardTitle className="text-sm">{p.title}</CardTitle>
                    {p.clinic_approved && (
                      <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 text-xs">
                        <CheckCircle2 className="h-3 w-3 mr-1" /> Clinic Approved
                      </Badge>
                    )}
                    {p.is_pinned && (
                      <Badge variant="outline" className="text-xs"><Pin className="h-3 w-3 mr-1" /> Pinned</Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5 truncate">
                    Query: {p.source_query}
                  </p>
                </div>
                <div className="flex gap-1 flex-shrink-0">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2"
                    onClick={() => patchMutation.mutate({ id: p.id, patch: { is_pinned: !p.is_pinned } })}
                    title={p.is_pinned ? "Unpin" : "Pin"}
                  >
                    <Pin className={`h-3.5 w-3.5 ${p.is_pinned ? "text-blue-500" : ""}`} />
                  </Button>
                  {canAdmin && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2"
                      onClick={() => patchMutation.mutate({ id: p.id, patch: { clinic_approved: !p.clinic_approved } })}
                      title="Toggle clinic approval"
                    >
                      <CheckCircle2 className={`h-3.5 w-3.5 ${p.clinic_approved ? "text-emerald-500" : ""}`} />
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2"
                    onClick={() => patchMutation.mutate({ id: p.id, patch: { is_archived: true } })}
                    title="Archive"
                  >
                    <Archive className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-3">
              <div className="flex flex-wrap gap-1.5">
                {(p.tags ?? []).map((tag: string) => (
                  <Badge key={tag} variant="secondary" className="text-xs">{tag}</Badge>
                ))}
              </div>
              {p.citations_json?.length > 0 && (
                <p className="text-xs text-muted-foreground mt-2">
                  {p.citations_json.length} citation{p.citations_json.length !== 1 ? "s" : ""}
                </p>
              )}
              <p className="text-xs text-muted-foreground mt-1">
                {new Date(p.created_at).toLocaleDateString()}
              </p>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}

// ===========================================================================
// TAB 4 — Reports
// ===========================================================================

function ReportsTab({ clinicId }: { clinicId: string }) {
  const { toast } = useToast();
  const [reportData, setReportData] = useState<any>(null);
  const [patientMode, setPatientMode] = useState(false);
  const printRef = useRef<HTMLDivElement>(null);

  const copyReport = () => {
    if (!reportData) return;
    const text = [
      reportData.title,
      "",
      "SUMMARY",
      reportData.summary,
      "",
      "PRESENTING PROBLEM",
      reportData.presenting_problem,
      "",
      "IMMEDIATE ACTIONS",
      reportData.immediate_actions,
      "",
      "TREATMENT USED",
      reportData.treatment_used,
      "",
      "ESCALATION",
      reportData.escalation_triggers,
      "",
      "FOLLOW-UP",
      reportData.follow_up,
      "",
      "CLINICIAN NOTES",
      reportData.clinician_notes,
    ].join("\n");
    navigator.clipboard.writeText(text);
    toast({ title: "Copied to clipboard" });
  };

  const sections = reportData ? [
    { label: "Summary", key: "summary", icon: FileText },
    { label: "Presenting Problem", key: "presenting_problem", icon: AlertTriangle },
    { label: "Immediate Actions", key: "immediate_actions", icon: Zap },
    { label: "Treatment Used", key: "treatment_used", icon: Stethoscope },
    { label: "Escalation Triggers", key: "escalation_triggers", icon: AlertCircle },
    { label: "Follow-Up", key: "follow_up", icon: Activity },
    { label: "Clinician Notes", key: "clinician_notes", icon: Info },
  ] : [];

  return (
    <div className="space-y-4">
      {!reportData ? (
        <EmptyState
          icon={FileText}
          title="No report loaded"
          description="Generate a report from the Case Log tab or from a Live Guidance session."
        />
      ) : (
        <div className="space-y-4">
          {/* Report header */}
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <h2 className="font-semibold text-base">{reportData.title}</h2>
              <p className="text-xs text-muted-foreground">
                Generated {new Date().toLocaleDateString()}
              </p>
            </div>
            <div className="flex gap-2 flex-wrap">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setPatientMode(!patientMode)}
              >
                {patientMode ? "Clinical View" : "Patient View"}
              </Button>
              <Button size="sm" variant="outline" onClick={copyReport}>
                <Copy className="h-3.5 w-3.5 mr-1.5" /> Copy
              </Button>
              <Button size="sm" variant="outline" onClick={() => window.print()}>
                <Printer className="h-3.5 w-3.5 mr-1.5" /> Print
              </Button>
            </div>
          </div>

          {patientMode ? (
            /* Patient-readable mode */
            <Card className="border-emerald-200 dark:border-emerald-800">
              <CardHeader className="pb-2 pt-3 px-4">
                <CardTitle className="text-sm text-emerald-700 dark:text-emerald-400">
                  Patient Information Summary
                </CardTitle>
                <CardDescription className="text-xs">Plain language for patient counselling</CardDescription>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                <p className="text-sm leading-relaxed">{reportData.patient_summary}</p>
              </CardContent>
            </Card>
          ) : (
            /* Clinical report sections */
            <div ref={printRef} className="space-y-3">
              {sections.map(({ label, key, icon: Icon }) => {
                const content = reportData[key];
                if (!content) return null;
                return (
                  <Card key={key}>
                    <CardHeader className="pb-1.5 pt-3 px-4">
                      <CardTitle className="text-xs text-muted-foreground flex items-center gap-1.5">
                        <Icon className="h-3.5 w-3.5" />
                        {label}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="px-4 pb-3">
                      <p className="text-sm leading-relaxed whitespace-pre-line">{content}</p>
                    </CardContent>
                  </Card>
                );
              })}

              {/* Evidence references */}
              {reportData.evidence_refs?.length > 0 && (
                <Card>
                  <CardHeader className="pb-1.5 pt-3 px-4">
                    <CardTitle className="text-xs text-muted-foreground flex items-center gap-1.5">
                      <BookOpen className="h-3.5 w-3.5" />
                      Evidence References
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-3 space-y-2">
                    {reportData.evidence_refs.map((ref: any, i: number) => (
                      <div key={i} className="flex items-start justify-between gap-2 text-sm">
                        <span className="text-xs">{ref.title} ({ref.year})</span>
                        {ref.level && <EvidenceBadge level={ref.level} />}
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ===========================================================================
// TAB 5 — Admin Dashboard
// ===========================================================================

function AdminDashboardTab({ clinicId }: { clinicId: string }) {
  const [period, setPeriod] = useState<"7d" | "30d" | "90d">("30d");

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ["analytics-overview", clinicId, period],
    queryFn: () => api<any>(`/api/workspace/admin/analytics/overview?clinic_id=${clinicId}&period=${period}`),
    enabled: !!clinicId,
  });

  const { data: trends, isLoading: trendsLoading } = useQuery({
    queryKey: ["analytics-trends", clinicId, period],
    queryFn: () => api<any>(`/api/workspace/admin/analytics/trends?clinic_id=${clinicId}&period=${period}`),
    enabled: !!clinicId,
  });

  const statCards = overview
    ? [
        { label: "Guidance Queries", value: overview.total_queries, icon: Zap, color: "text-blue-500" },
        { label: "Case Logs", value: overview.total_case_logs, icon: ClipboardList, color: "text-amber-500" },
        { label: "Saved Protocols", value: overview.total_protocols, icon: BookOpen, color: "text-emerald-500" },
        { label: "Safety Reports", value: overview.total_reports, icon: FileText, color: "text-violet-500" },
      ]
    : [];

  return (
    <div className="space-y-5">
      {/* Period filter */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Period:</span>
        {(["7d", "30d", "90d"] as const).map((p) => (
          <Button
            key={p}
            size="sm"
            variant={period === p ? "default" : "outline"}
            className="h-7 px-3 text-xs"
            onClick={() => setPeriod(p)}
          >
            {p}
          </Button>
        ))}
      </div>

      {/* Stat cards */}
      {overviewLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[1,2,3,4].map(i => <Skeleton key={i} className="h-24 w-full" />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {statCards.map(({ label, value, icon: Icon, color }) => (
            <Card key={label}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="text-2xl font-semibold mt-1">{value ?? 0}</p>
                  </div>
                  <Icon className={`h-5 w-5 ${color}`} />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Top complications */}
        <Card>
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-sm">Top Complication Categories</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3">
            {overviewLoading ? (
              <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} className="h-6 w-full" />)}</div>
            ) : !overview?.top_complications?.length ? (
              <p className="text-xs text-muted-foreground">No data for this period.</p>
            ) : (
              <div className="space-y-2">
                {overview.top_complications.map((c: any, i: number) => {
                  const max = overview.top_complications[0]?.cnt ?? 1;
                  const pct = Math.round((c.cnt / max) * 100);
                  return (
                    <div key={i}>
                      <div className="flex justify-between text-xs mb-0.5">
                        <span className="truncate">{c.complication_type}</span>
                        <span className="text-muted-foreground flex-shrink-0 ml-2">{c.cnt}</span>
                      </div>
                      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* High risk topics */}
        <Card className="border-red-200 dark:border-red-900">
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-sm flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-500" />
              High-Risk Topics
            </CardTitle>
            <CardDescription className="text-xs">
              Vascular, necrosis, visual, inflammatory
            </CardDescription>
          </CardHeader>
          <CardContent className="px-4 pb-3">
            {overviewLoading ? (
              <div className="space-y-2">{[1,2].map(i => <Skeleton key={i} className="h-6 w-full" />)}</div>
            ) : !overview?.high_risk_topics?.length ? (
              <p className="text-xs text-muted-foreground">No high-risk cases logged in this period.</p>
            ) : (
              <div className="space-y-1">
                {overview.high_risk_topics.map((t: any, i: number) => (
                  <div key={i} className="flex justify-between text-xs py-1 border-b last:border-0">
                    <span>{t.complication_type}</span>
                    <Badge variant="destructive" className="text-xs h-5">{t.cnt}</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Trend charts — lightweight bar representation */}
      <Card>
        <CardHeader className="pb-2 pt-3 px-4">
          <CardTitle className="text-sm">Queries Over Time</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-3">
          {trendsLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : !trends?.queries_over_time?.length ? (
            <p className="text-xs text-muted-foreground">No query data for this period.</p>
          ) : (
            <div className="flex items-end gap-1 h-28">
              {trends.queries_over_time.map((d: any, i: number) => {
                const max = Math.max(...trends.queries_over_time.map((x: any) => x.count), 1);
                const h = Math.max(4, Math.round((d.count / max) * 100));
                return (
                  <div key={i} className="flex-1 flex flex-col items-center gap-1">
                    <div
                      className="w-full bg-blue-500 rounded-t-sm"
                      style={{ height: `${h}%` }}
                      title={`${d.day}: ${d.count}`}
                    />
                    {i % Math.ceil(trends.queries_over_time.length / 6) === 0 && (
                      <span className="text-[9px] text-muted-foreground rotate-45 origin-left truncate w-6">
                        {d.day.slice(5)}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ===========================================================================
// ROOT PAGE
// ===========================================================================

export default function NetworkSafetyWorkspacePage() {
  const { selectedClinic, isReady, canAdmin } = useClinicContext();
  const [activeTab, setActiveTab] = useState("guidance");

  if (!isReady) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-3">
          <Skeleton className="h-8 w-64 mx-auto" />
          <Skeleton className="h-4 w-48 mx-auto" />
        </div>
      </div>
    );
  }

  if (!selectedClinic) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Card className="max-w-sm w-full mx-4">
          <CardContent className="p-6 text-center">
            <Building2 className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
            <p className="font-medium text-sm">No clinic access</p>
            <p className="text-xs text-muted-foreground mt-1">
              You are not a member of any clinic. Contact your administrator.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Page header */}
      <div className="border-b bg-background/95 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <Shield className="h-5 w-5 text-blue-500 flex-shrink-0" />
            <div className="min-w-0">
              <h1 className="font-semibold text-sm leading-tight">Safety Workspace</h1>
              <p className="text-xs text-muted-foreground hidden sm:block">
                Clinical safety and evidence infrastructure
              </p>
            </div>
          </div>
          <ClinicSwitcher />
        </div>
      </div>

      {/* Main content */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-6 flex-wrap h-auto gap-1">
            <TabsTrigger value="guidance" className="text-xs gap-1.5">
              <Zap className="h-3.5 w-3.5" /> Live Guidance
            </TabsTrigger>
            <TabsTrigger value="caselog" className="text-xs gap-1.5">
              <ClipboardList className="h-3.5 w-3.5" /> Case Log
            </TabsTrigger>
            <TabsTrigger value="protocols" className="text-xs gap-1.5">
              <BookOpen className="h-3.5 w-3.5" /> Saved Protocols
            </TabsTrigger>
            <TabsTrigger value="reports" className="text-xs gap-1.5">
              <FileText className="h-3.5 w-3.5" /> Reports
            </TabsTrigger>
            {canAdmin && (
              <TabsTrigger value="admin" className="text-xs gap-1.5">
                <BarChart3 className="h-3.5 w-3.5" /> Admin Dashboard
              </TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="guidance">
            <LiveGuidanceTab clinicId={selectedClinic.clinic_id} />
          </TabsContent>

          <TabsContent value="caselog">
            <CaseLogTab clinicId={selectedClinic.clinic_id} />
          </TabsContent>

          <TabsContent value="protocols">
            <SavedProtocolsTab
              clinicId={selectedClinic.clinic_id}
              canAdmin={canAdmin}
            />
          </TabsContent>

          <TabsContent value="reports">
            <ReportsTab clinicId={selectedClinic.clinic_id} />
          </TabsContent>

          {canAdmin && (
            <TabsContent value="admin">
              <AdminDashboardTab clinicId={selectedClinic.clinic_id} />
            </TabsContent>
          )}
        </Tabs>
      </div>
    </div>
  );
}
