import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Upload, FileText, Link, CheckCircle2, XCircle, Clock,
  RefreshCw, ChevronRight, BookOpen, Loader2, AlertCircle,
  Database, Plus, Trash2, Play
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const API_KEY_STORE = "aestheticite_admin_key";

function getAdminKey(): string {
  return localStorage.getItem(API_KEY_STORE) ?? "";
}

function setAdminKey(k: string) {
  localStorage.setItem(API_KEY_STORE, k);
}

async function adminFetch(path: string, opts: RequestInit = {}): Promise<Response> {
  const key = getAdminKey();
  const headers: Record<string, string> = {
    ...(opts.headers as Record<string, string> | undefined ?? {}),
    "x-api-key": key,
  };
  return fetch(path, { ...opts, headers });
}

async function adminJson<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await adminFetch(path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? "Request failed");
  return data as T;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface IngestResult {
  ok: boolean;
  record_id: string;
  doi: string;
  title?: string;
  journal?: string;
  year?: number;
  abstract?: string;
  oa_pdf_downloaded: boolean;
  oa_pdf_url?: string;
  publisher_url?: string;
  notes?: string;
}

interface StudyRecord {
  record_id: string;
  doi: string;
  title?: string;
  journal?: string;
  year?: number;
  has_pdf: boolean;
  pdf_file?: string;
  meta_file?: string;
}

// ---------------------------------------------------------------------------
// Status pill
// ---------------------------------------------------------------------------

function StatusPill({ hasPdf }: { hasPdf: boolean }) {
  return hasPdf ? (
    <Badge className="text-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 border-emerald-300">
      PDF ready
    </Badge>
  ) : (
    <Badge variant="outline" className="text-[10px] text-amber-600 border-amber-300 dark:border-amber-700">
      No PDF
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Embed progress component
// ---------------------------------------------------------------------------

function EmbedRunner({ recordId, apiKey }: { recordId: string; apiKey: string }) {
  const { toast } = useToast();
  const [state, setState] = useState<{ running: boolean; done: boolean; remaining: number | null }>({
    running: false, done: false, remaining: null,
  });
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = null;
    setState((s) => ({ ...s, running: false }));
  };

  const runOne = async () => {
    try {
      const res = await fetch(`/ingest/embed/${recordId}`, {
        method: "POST",
        headers: { "x-api-key": apiKey },
      });
      const data = await res.json();
      if (!res.ok) { stop(); toast({ title: "Embed error", description: data.detail, variant: "destructive" }); return; }
      setState({ running: !data.done, done: data.done, remaining: data.remaining ?? null });
      if (data.done) {
        stop();
        toast({ title: "Embedding complete", description: `All chunks embedded.` });
      }
    } catch (e: any) {
      stop();
      toast({ title: "Network error", description: e.message, variant: "destructive" });
    }
  };

  const start = () => {
    if (state.running) return;
    setState((s) => ({ ...s, running: true, done: false }));
    intervalRef.current = setInterval(runOne, 400);
  };

  useEffect(() => () => { if (intervalRef.current) clearInterval(intervalRef.current); }, []);

  if (state.done) return (
    <span className="flex items-center gap-1 text-xs text-emerald-600">
      <CheckCircle2 className="h-3.5 w-3.5" /> Embedded
    </span>
  );

  return (
    <Button
      size="sm"
      variant="outline"
      className="h-6 text-[11px] px-2"
      onClick={state.running ? stop : start}
      disabled={!apiKey}
    >
      {state.running ? (
        <>
          <Loader2 className="h-3 w-3 mr-1 animate-spin" />
          {state.remaining != null ? `${state.remaining} left` : "Embedding…"}
        </>
      ) : (
        <>
          <Play className="h-3 w-3 mr-1" /> Embed
        </>
      )}
    </Button>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function IngestPage() {
  const { toast } = useToast();
  const qc = useQueryClient();

  const [apiKey, setApiKeyState] = useState<string>(() => getAdminKey());
  const [doi, setDoi] = useState("");
  const [batchText, setBatchText] = useState("");
  const [mode, setMode] = useState<"single" | "batch">("single");
  const [uploadRecordId, setUploadRecordId] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);

  const saveKey = (k: string) => { setAdminKey(k); setApiKeyState(k); };

  // ── Fetch records ───────────────────────────────────────────────────────────
  const { data: records = [], isLoading: recordsLoading, refetch } = useQuery<StudyRecord[]>({
    queryKey: ["/ingest/records"],
    queryFn: () => adminJson<StudyRecord[]>("/ingest/records"),
    enabled: !!apiKey,
    refetchInterval: 30000,
  });

  // ── DOI ingest mutation ─────────────────────────────────────────────────────
  const ingestDoi = useMutation({
    mutationFn: (d: string) => adminJson<IngestResult>("/ingest/doi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doi: d.trim(), allow_oa_pdf_download: true }),
    }),
    onSuccess: (r) => {
      toast({
        title: r.oa_pdf_downloaded ? `✓ Ingested — OA PDF downloaded` : `✓ Ingested — no OA PDF`,
        description: r.title ?? r.doi,
      });
      qc.invalidateQueries({ queryKey: ["/ingest/records"] });
      setDoi("");
    },
    onError: (e: Error) => toast({ title: "Ingest failed", description: e.message, variant: "destructive" }),
  });

  // ── Batch DOI ingest ────────────────────────────────────────────────────────
  const [batchResults, setBatchResults] = useState<{ doi: string; status: string; title?: string }[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);

  const runBatch = async () => {
    const dois = batchText.split(/[\n,]+/).map((d) => d.trim()).filter(Boolean);
    if (!dois.length) return;
    setBatchRunning(true);
    setBatchResults(dois.map((d) => ({ doi: d, status: "pending" })));
    for (let i = 0; i < dois.length; i++) {
      const d = dois[i];
      setBatchResults((prev) => prev.map((r) => r.doi === d ? { ...r, status: "running" } : r));
      try {
        const result = await adminJson<IngestResult>("/ingest/doi", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ doi: d, allow_oa_pdf_download: true }),
        });
        setBatchResults((prev) => prev.map((r) =>
          r.doi === d ? { doi: d, status: result.oa_pdf_downloaded ? "✓ + PDF" : "✓ no PDF", title: result.title ?? undefined } : r
        ));
      } catch (e: any) {
        setBatchResults((prev) => prev.map((r) =>
          r.doi === d ? { doi: d, status: `✗ ${e.message?.slice(0, 40)}` } : r
        ));
      }
      await new Promise((res) => setTimeout(res, 300));
    }
    setBatchRunning(false);
    qc.invalidateQueries({ queryKey: ["/ingest/records"] });
  };

  // ── PDF upload ───────────────────────────────────────────────────────────────
  const uploadPdf = async (recordId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`/ingest/upload/pdf/${recordId}`, {
      method: "POST",
      headers: { "x-api-key": apiKey },
      body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail ?? "Upload failed");
    return data;
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !uploadRecordId.trim()) {
      toast({ title: "Select a record ID first", variant: "destructive" }); return;
    }
    try {
      await uploadPdf(uploadRecordId.trim(), file);
      toast({ title: "PDF uploaded" });
      qc.invalidateQueries({ queryKey: ["/ingest/records"] });
      setUploadRecordId("");
      if (fileRef.current) fileRef.current.value = "";
    } catch (e: any) {
      toast({ title: "Upload failed", description: e.message, variant: "destructive" });
    }
  };

  // ── Process (chunk) ──────────────────────────────────────────────────────────
  const processRecord = useMutation({
    mutationFn: (id: string) => adminJson(`/ingest/process/${id}`, {
      method: "POST",
      headers: { "x-api-key": apiKey },
    }),
    onSuccess: (data: any) => {
      toast({ title: `Chunked: ${data.chunks_created} chunks`, description: data.title ?? "" });
      setProcessingId(null);
    },
    onError: (e: Error) => { toast({ title: "Process failed", description: e.message, variant: "destructive" }); setProcessingId(null); },
  });

  return (
    <div className="min-h-screen bg-background">
      <div className="border-b bg-background/95 sticky top-0 z-30">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-3">
          <Database className="h-5 w-5 text-blue-500" />
          <span className="font-semibold text-sm">Study Upload</span>
          <span className="text-xs text-muted-foreground hidden sm:inline">· Ingest research into the RAG database</span>
          <div className="ml-auto flex items-center gap-2">
            <Badge variant="outline" className="text-xs">{records.length} records</Badge>
            <Button size="sm" variant="ghost" className="h-7" onClick={() => refetch()}>
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">

        {/* API KEY */}
        <Card>
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-sm flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-amber-500" /> Admin Key
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <div className="flex gap-2">
              <input
                type="password"
                data-testid="input-admin-key"
                className="flex-1 h-8 px-3 text-sm border rounded-md bg-background focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="Enter admin API key"
                value={apiKey}
                onChange={(e) => saveKey(e.target.value)}
              />
              {apiKey && <CheckCircle2 className="h-5 w-5 text-emerald-500 self-center flex-shrink-0" />}
            </div>
          </CardContent>
        </Card>

        {/* DOI INGEST */}
        <Card>
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-sm flex items-center gap-2">
              <Link className="h-4 w-4" /> Add Study by DOI
              <div className="ml-auto flex gap-1">
                {(["single", "batch"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={`text-[11px] px-2 py-0.5 rounded border transition-colors ${
                      mode === m ? "bg-blue-600 text-white border-blue-600" : "border-border text-muted-foreground hover:border-blue-400"
                    }`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-3">
            {mode === "single" ? (
              <div className="flex gap-2">
                <input
                  data-testid="input-doi"
                  className="flex-1 h-9 px-3 text-sm border rounded-md bg-background focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
                  placeholder="10.1056/NEJMoa2034577"
                  value={doi}
                  onChange={(e) => setDoi(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && doi.trim() && ingestDoi.mutate(doi)}
                />
                <Button
                  data-testid="button-ingest-doi"
                  onClick={() => ingestDoi.mutate(doi)}
                  disabled={!doi.trim() || !apiKey || ingestDoi.isPending}
                  className="h-9"
                >
                  {ingestDoi.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ChevronRight className="h-4 w-4" />}
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                <textarea
                  data-testid="textarea-batch-dois"
                  className="w-full h-28 px-3 py-2 text-sm border rounded-md bg-background focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono resize-none"
                  placeholder={"One DOI per line:\n10.1016/j.jaad.2022.01.001\n10.1001/jamadermatol.2021.4567"}
                  value={batchText}
                  onChange={(e) => setBatchText(e.target.value)}
                />
                <Button
                  data-testid="button-batch-ingest"
                  onClick={runBatch}
                  disabled={!batchText.trim() || !apiKey || batchRunning}
                  size="sm"
                >
                  {batchRunning ? <><Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> Running…</> : <><Plus className="h-3.5 w-3.5 mr-1.5" /> Run Batch</>}
                </Button>

                {batchResults.length > 0 && (
                  <div className="border rounded-lg overflow-hidden text-xs">
                    {batchResults.map((r, i) => (
                      <div key={i} className="flex items-start gap-3 px-3 py-2 border-b last:border-0 bg-muted/20">
                        <span className="font-mono text-muted-foreground flex-shrink-0 w-48 truncate">{r.doi}</span>
                        <span className={r.status.startsWith("✓") ? "text-emerald-600" : r.status.startsWith("✗") ? "text-red-500" : "text-amber-500"}>
                          {r.status === "running" ? <Loader2 className="h-3 w-3 animate-spin inline" /> : r.status}
                        </span>
                        {r.title && <span className="text-muted-foreground truncate">{r.title}</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {ingestDoi.data && (
              <div className="mt-2 p-3 rounded-lg border bg-muted/30 text-xs space-y-1">
                <p className="font-medium">{ingestDoi.data.title ?? ingestDoi.data.doi}</p>
                <p className="text-muted-foreground">{ingestDoi.data.journal} · {ingestDoi.data.year}</p>
                <div className="flex flex-wrap gap-2 mt-1">
                  <StatusPill hasPdf={ingestDoi.data.oa_pdf_downloaded} />
                  <code className="text-muted-foreground font-mono">{ingestDoi.data.record_id}</code>
                </div>
                {ingestDoi.data.notes && (
                  <p className="text-amber-600 dark:text-amber-400">{ingestDoi.data.notes}</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* PDF UPLOAD */}
        <Card>
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-sm flex items-center gap-2">
              <Upload className="h-4 w-4" /> Upload PDF
              <span className="text-muted-foreground font-normal text-xs ml-1">— for records without an OA PDF</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-3">
            <div className="flex gap-2">
              <input
                data-testid="input-upload-record-id"
                className="flex-1 h-8 px-3 text-sm border rounded-md bg-background focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
                placeholder="record_id (UUID)"
                value={uploadRecordId}
                onChange={(e) => setUploadRecordId(e.target.value)}
              />
            </div>
            <div>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,application/pdf"
                className="hidden"
                onChange={handleFileChange}
                data-testid="input-pdf-file"
              />
              <Button
                size="sm"
                variant="outline"
                onClick={() => fileRef.current?.click()}
                disabled={!uploadRecordId.trim() || !apiKey}
                data-testid="button-choose-pdf"
              >
                <FileText className="h-3.5 w-3.5 mr-1.5" /> Choose PDF
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">Max 50 MB. Paste the record_id from the table below.</p>
          </CardContent>
        </Card>

        {/* RECORDS TABLE */}
        <Card>
          <CardHeader className="pb-2 pt-3 px-4">
            <CardTitle className="text-sm flex items-center gap-2">
              <BookOpen className="h-4 w-4" /> Records
              <span className="text-xs font-normal text-muted-foreground ml-1">
                Process → chunk, Embed → semantic search ready
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            {!apiKey ? (
              <p className="text-sm text-muted-foreground">Enter admin key to view records.</p>
            ) : recordsLoading ? (
              <div className="space-y-2">{[1,2,3].map((i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
            ) : records.length === 0 ? (
              <p className="text-sm text-muted-foreground">No records yet. Add a DOI above.</p>
            ) : (
              <div className="border rounded-lg overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b bg-muted/40">
                        <th className="text-left px-3 py-2 font-medium text-muted-foreground">Title / DOI</th>
                        <th className="text-left px-3 py-2 font-medium text-muted-foreground">Year</th>
                        <th className="text-left px-3 py-2 font-medium text-muted-foreground">PDF</th>
                        <th className="text-left px-3 py-2 font-medium text-muted-foreground">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {records.map((r) => (
                        <tr key={r.record_id} className="border-b last:border-0 hover:bg-muted/20 transition-colors">
                          <td className="px-3 py-2">
                            <p className="font-medium truncate max-w-[280px]">{r.title ?? r.doi}</p>
                            <div className="flex items-center gap-2 mt-0.5">
                              <code
                                className="text-muted-foreground font-mono text-[10px] cursor-pointer hover:text-foreground"
                                onClick={() => { navigator.clipboard.writeText(r.record_id); setUploadRecordId(r.record_id); }}
                                title="Click to copy & paste as upload target"
                              >
                                {r.record_id.slice(0, 8)}…
                              </code>
                              {r.journal && <span className="text-muted-foreground">{r.journal}</span>}
                            </div>
                          </td>
                          <td className="px-3 py-2 text-muted-foreground">{r.year ?? "—"}</td>
                          <td className="px-3 py-2"><StatusPill hasPdf={r.has_pdf} /></td>
                          <td className="px-3 py-2">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              {r.has_pdf && (
                                <>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="h-6 text-[11px] px-2"
                                    disabled={!apiKey || processRecord.isPending}
                                    onClick={() => { setProcessingId(r.record_id); processRecord.mutate(r.record_id); }}
                                    data-testid={`button-process-${r.record_id.slice(0,8)}`}
                                  >
                                    {processRecord.isPending && processingId === r.record_id
                                      ? <Loader2 className="h-3 w-3 animate-spin mr-1" />
                                      : <Play className="h-3 w-3 mr-1" />
                                    }
                                    Process
                                  </Button>
                                  <EmbedRunner recordId={r.record_id} apiKey={apiKey} />
                                </>
                              )}
                              {!r.has_pdf && (
                                <button
                                  className="text-[11px] text-blue-500 hover:underline"
                                  onClick={() => setUploadRecordId(r.record_id)}
                                >
                                  + Upload PDF
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* PIPELINE GUIDE */}
        <div className="flex items-start gap-3 p-4 rounded-xl border bg-muted/30 text-xs text-muted-foreground">
          <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-medium text-foreground">Pipeline steps</p>
            <p><span className="font-medium text-foreground">1. Add DOI</span> — fetches metadata from Crossref/PubMed. Downloads open-access PDF automatically.</p>
            <p><span className="font-medium text-foreground">2. Upload PDF</span> — if no OA PDF was found, paste the record ID and upload your copy (max 50 MB).</p>
            <p><span className="font-medium text-foreground">3. Process</span> — chunks the PDF text and stores it in the database.</p>
            <p><span className="font-medium text-foreground">4. Embed</span> — generates vector embeddings for semantic search. Click and wait until complete.</p>
          </div>
        </div>

      </div>
    </div>
  );
}
