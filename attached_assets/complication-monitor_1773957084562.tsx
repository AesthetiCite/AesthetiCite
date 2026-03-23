import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Camera, Plus, AlertTriangle, CheckCircle2, Eye, Clock,
  XCircle, Upload, Activity, Shield,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useClinicContext } from "@/hooks/use-clinic-context";
import { ClinicSwitcher } from "@/components/clinic-switcher";
import { getToken } from "@/lib/auth";

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

async function api<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(path, {
    ...opts,
    headers: {
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
// Risk level styling
// ---------------------------------------------------------------------------

const RISK_COLORS: Record<string, string> = {
  normal:   "text-emerald-600 dark:text-emerald-400",
  low:      "text-blue-600 dark:text-blue-400",
  moderate: "text-amber-600 dark:text-amber-400",
  high:     "text-orange-600 dark:text-orange-400",
  critical: "text-red-600 dark:text-red-400",
  unknown:  "text-muted-foreground",
};

const RISK_BADGE: Record<string, string> = {
  normal:   "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  low:      "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  moderate: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  high:     "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  critical: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  unknown:  "bg-muted text-muted-foreground",
};

const STATUS_BADGE: Record<string, string> = {
  active:    "bg-blue-100 text-blue-700",
  resolved:  "bg-emerald-100 text-emerald-700",
  escalated: "bg-red-100 text-red-700",
  closed:    "bg-muted text-muted-foreground",
};

// ---------------------------------------------------------------------------
// Monitor detail dialog
// ---------------------------------------------------------------------------

function MonitorDetail({ monitorId, clinicId }: { monitorId: string; clinicId: string }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [notes, setNotes] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const { toast } = useToast();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["monitor-detail", monitorId],
    queryFn: () => api<any>(`/api/monitor/cases/${monitorId}`),
  });

  const submitMutation = useMutation({
    mutationFn: async () => {
      if (!selectedFile) throw new Error("No photo selected");
      const token = getToken();
      const fd = new FormData();
      fd.append("file", selectedFile);
      fd.append("clinic_id", clinicId);
      fd.append("notes", notes);
      const res = await fetch(`/api/monitor/cases/${monitorId}/submit`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? "Upload failed");
      }
      return res.json();
    },
    onSuccess: (result: any) => {
      qc.invalidateQueries({ queryKey: ["monitor-detail", monitorId] });
      qc.invalidateQueries({ queryKey: ["monitors", clinicId] });
      setNotes("");
      setSelectedFile(null);
      setPreview(null);

      if (result.alert_triggered) {
        toast({
          title: "⚠️ Alert triggered",
          description: result.assessment?.recommended_action ?? "Review required.",
          variant: "destructive",
        });
      } else {
        toast({ title: "Submission recorded", description: result.message });
      }
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    const reader = new FileReader();
    reader.onload = () => setPreview(reader.result as string);
    reader.readAsDataURL(file);
  };

  if (isLoading) return <div className="space-y-3 py-4">{[1,2,3].map(i => <Skeleton key={i} className="h-16 w-full" />)}</div>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      {/* Monitor info */}
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <p className="text-xs text-muted-foreground">Patient Reference</p>
          <p className="font-mono text-xs font-medium">{data.patient_reference}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Status</p>
          <Badge variant="outline" className={`text-xs ${STATUS_BADGE[data.monitor_status] ?? ""}`}>
            {data.monitor_status}
          </Badge>
        </div>
        {data.procedure && (
          <div>
            <p className="text-xs text-muted-foreground">Procedure</p>
            <p className="text-xs">{data.procedure}</p>
          </div>
        )}
        {data.region && (
          <div>
            <p className="text-xs text-muted-foreground">Region</p>
            <p className="text-xs">{data.region}</p>
          </div>
        )}
      </div>

      {/* Past submissions */}
      {data.submissions?.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">Previous Submissions ({data.submissions.length})</p>
          <div className="space-y-3">
            {data.submissions.map((sub: any) => {
              const assess = sub.ai_assessment ?? {};
              const risk = assess.risk_level ?? "unknown";
              return (
                <Card key={sub.id} className={sub.alert_triggered ? "border-red-300 dark:border-red-800" : ""}>
                  <CardContent className="p-3">
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <p className="text-xs text-muted-foreground">
                        {new Date(sub.submitted_at).toLocaleString()}
                      </p>
                      <Badge variant="outline" className={`text-xs ${RISK_BADGE[risk] ?? RISK_BADGE.unknown}`}>
                        {risk}
                      </Badge>
                    </div>
                    {sub.notes && (
                      <p className="text-xs text-muted-foreground mb-2">Notes: {sub.notes}</p>
                    )}
                    {assess.findings?.length > 0 && (
                      <div className="mb-1">
                        <p className="text-xs font-medium">Findings:</p>
                        <ul className="text-xs text-muted-foreground list-disc list-inside">
                          {assess.findings.map((f: string, i: number) => <li key={i}>{f}</li>)}
                        </ul>
                      </div>
                    )}
                    {assess.recommended_action && (
                      <p className="text-xs mt-1">
                        <span className="font-medium">Action: </span>
                        {assess.recommended_action}
                      </p>
                    )}
                    {assess.red_flags?.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {assess.red_flags.map((f: string, i: number) => (
                          <Badge key={i} className="text-xs bg-red-100 text-red-700">⚠ {f}</Badge>
                        ))}
                      </div>
                    )}
                    {assess.disclaimer && (
                      <p className="text-[10px] text-muted-foreground/60 mt-2 italic">{assess.disclaimer}</p>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {/* New submission form */}
      {data.monitor_status === "active" && (
        <div className="border-t pt-4">
          <p className="text-sm font-medium mb-3">Submit New Photo</p>

          <div className="space-y-3">
            <div>
              <Label className="text-xs">Photo</Label>
              <input
                type="file"
                accept="image/*"
                ref={fileRef}
                className="hidden"
                onChange={handleFileSelect}
              />
              <div
                className="mt-1 border-2 border-dashed rounded-lg p-4 text-center cursor-pointer hover:border-blue-400 transition-colors"
                onClick={() => fileRef.current?.click()}
              >
                {preview ? (
                  <img src={preview} alt="Preview" className="max-h-40 mx-auto rounded object-contain" />
                ) : (
                  <div className="text-muted-foreground">
                    <Camera className="h-8 w-8 mx-auto mb-2 opacity-40" />
                    <p className="text-xs">Click to select photo</p>
                  </div>
                )}
              </div>
            </div>

            <div>
              <Label className="text-xs">Clinical Notes</Label>
              <Textarea
                className="mt-1 text-sm resize-none"
                rows={2}
                placeholder="e.g. Moderate swelling, no blanching, patient reports mild discomfort…"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>

            <Button
              className="w-full"
              onClick={() => submitMutation.mutate()}
              disabled={!selectedFile || submitMutation.isPending}
            >
              <Upload className="h-3.5 w-3.5 mr-1.5" />
              {submitMutation.isPending ? "Screening…" : "Submit & Screen with AI"}
            </Button>
            <p className="text-[10px] text-muted-foreground text-center">
              AI screening is decision support only. Clinical judgement takes precedence.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Monitor list card
// ---------------------------------------------------------------------------

function MonitorCard({ monitor, clinicId }: { monitor: any; clinicId: string }) {
  const [open, setOpen] = useState(false);
  const status = monitor.monitor_status;

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <p className="font-mono text-xs font-medium">{monitor.patient_reference}</p>
              <Badge variant="outline" className={`text-xs ${STATUS_BADGE[status] ?? ""}`}>
                {status}
              </Badge>
              {status === "escalated" && (
                <Badge className="text-xs bg-red-100 text-red-700">⚠ Escalated</Badge>
              )}
            </div>
            {monitor.procedure && (
              <p className="text-xs text-muted-foreground">
                {monitor.procedure} · {monitor.region ?? "—"}
              </p>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              {monitor.submission_count ?? 0} submission{monitor.submission_count !== 1 ? "s" : ""}
              {monitor.last_submission && (
                <> · Last: {new Date(monitor.last_submission).toLocaleDateString()}</>
              )}
            </p>
          </div>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline" className="h-7 flex-shrink-0">
                <Eye className="h-3.5 w-3.5 mr-1.5" /> View
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle className="text-sm">
                  Monitor — {monitor.patient_reference}
                </DialogTitle>
              </DialogHeader>
              <MonitorDetail monitorId={monitor.id} clinicId={clinicId} />
            </DialogContent>
          </Dialog>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const PROCEDURES = [
  "Lip filler", "Cheek filler", "Tear trough filler", "Jawline filler",
  "Nasolabial fold filler", "Chin filler", "Botulinum toxin",
];

const REGIONS = [
  "Lips", "Periorbital", "Midface", "Jawline", "Chin", "Temple", "Glabella",
];

export default function ComplicationMonitorPage() {
  const { selectedClinic, isReady } = useClinicContext();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [statusFilter, setStatusFilter] = useState("active");
  const [form, setForm] = useState({
    patient_reference: "",
    procedure: "",
    region: "",
  });

  const clinicId = selectedClinic?.clinic_id ?? "";

  const { data: monitors = [], isLoading } = useQuery({
    queryKey: ["monitors", clinicId, statusFilter],
    queryFn: () =>
      api<any[]>(`/api/monitor/cases?clinic_id=${clinicId}${statusFilter !== "all" ? `&status=${statusFilter}` : ""}`),
    enabled: !!clinicId,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api("/api/monitor/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, clinic_id: clinicId }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["monitors"] });
      setShowForm(false);
      setForm({ patient_reference: "", procedure: "", region: "" });
      toast({ title: "Monitor created" });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const stats = {
    active: monitors.filter((m) => m.monitor_status === "active").length,
    escalated: monitors.filter((m) => m.monitor_status === "escalated").length,
    resolved: monitors.filter((m) => m.monitor_status === "resolved").length,
  };

  if (!isReady) return <div className="min-h-screen flex items-center justify-center"><Skeleton className="h-12 w-64" /></div>;

  return (
    <div className="min-h-screen bg-background">
      <div className="border-b bg-background/95 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Camera className="h-5 w-5 text-blue-500 flex-shrink-0" />
            <div>
              <h1 className="font-semibold text-sm">Complication Monitor</h1>
              <p className="text-xs text-muted-foreground hidden sm:block">
                Async photo-based post-procedure monitoring · AI screening
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ClinicSwitcher />
            <Button size="sm" onClick={() => setShowForm(true)}>
              <Plus className="h-3.5 w-3.5 mr-1.5" /> New Monitor
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-6 space-y-5">
        {/* Stats */}
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Active", count: stats.active, icon: Clock, color: "text-blue-500" },
            { label: "Escalated", count: stats.escalated, icon: AlertTriangle, color: "text-red-500" },
            { label: "Resolved", count: stats.resolved, icon: CheckCircle2, color: "text-emerald-500" },
          ].map(({ label, count, icon: Icon, color }) => (
            <Card key={label}>
              <CardContent className="p-3 flex items-center gap-2">
                <Icon className={`h-5 w-5 ${color}`} />
                <div>
                  <p className="text-lg font-semibold">{count}</p>
                  <p className="text-xs text-muted-foreground">{label}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* New monitor form */}
        {showForm && (
          <Card className="border-blue-200 dark:border-blue-800">
            <CardHeader className="pb-3 pt-3 px-4">
              <CardTitle className="text-sm">New Complication Monitor</CardTitle>
              <CardDescription className="text-xs">
                Create a monitoring case. Patient reference must be non-identifiable.
              </CardDescription>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                <div>
                  <Label className="text-xs">Patient Reference *</Label>
                  <Input
                    className="mt-1 h-8 text-sm"
                    placeholder="e.g. REF-2024-042"
                    value={form.patient_reference}
                    onChange={(e) => setForm((p) => ({ ...p, patient_reference: e.target.value }))}
                  />
                </div>
                <div>
                  <Label className="text-xs">Procedure</Label>
                  <Select onValueChange={(v) => setForm((p) => ({ ...p, procedure: v }))}>
                    <SelectTrigger className="mt-1 h-8 text-sm"><SelectValue placeholder="Select…" /></SelectTrigger>
                    <SelectContent>{PROCEDURES.map(p => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Region</Label>
                  <Select onValueChange={(v) => setForm((p) => ({ ...p, region: v }))}>
                    <SelectTrigger className="mt-1 h-8 text-sm"><SelectValue placeholder="Select…" /></SelectTrigger>
                    <SelectContent>{REGIONS.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => createMutation.mutate()} disabled={!form.patient_reference || createMutation.isPending}>
                  {createMutation.isPending ? "Creating…" : "Create Monitor"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Filters */}
        <div className="flex gap-2">
          {["active", "escalated", "resolved", "all"].map((s) => (
            <Button
              key={s}
              size="sm"
              variant={statusFilter === s ? "default" : "outline"}
              className="h-7 px-3 text-xs capitalize"
              onClick={() => setStatusFilter(s)}
            >
              {s}
            </Button>
          ))}
        </div>

        {/* Monitor list */}
        {isLoading ? (
          <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} className="h-20 w-full" />)}</div>
        ) : !monitors.length ? (
          <div className="py-16 text-center">
            <Camera className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
            <p className="text-sm font-medium text-muted-foreground">No monitors yet</p>
            <p className="text-xs text-muted-foreground/60 mt-1">
              Create a monitor after a procedure to track post-procedure healing.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {monitors.map((m) => (
              <MonitorCard key={m.id} monitor={m} clinicId={clinicId} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
