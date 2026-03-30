/**
 * pages/vision-analysis.tsx
 * ==========================
 * AesthetiCite Vision — unified page replacing both:
 *   /vision-analysis  (structured complication assessment)
 *   /visual-counsel   (streaming evidence Q&A with photo)
 *
 * Three tabs, one upload:
 *   1. Analyse      — structured complication assessment (Vision Engine)
 *   2. Ask          — open-ended streaming Q&A about the photo (Visual Counsel)
 *   3. Healing      — before/after serial comparison
 *
 * The uploaded image persists across Analyse and Ask tabs within the session.
 * Clinician uploads once and can switch freely between modes.
 *
 * INTEGRATION (App.tsx):
 *   import VisionPage from "@/pages/vision-analysis";
 *   <Route path="/vision-analysis">{() => <ProtectedRoute component={VisionPage} />}</Route>
 *   <Route path="/visual-counsel">{() => <Redirect to="/vision-analysis" />}</Route>
 */

import { useRef, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import {
  Upload, Activity, MessageSquare, ArrowLeftRight,
  Loader2, AlertTriangle, CheckCircle, ShieldCheck,
  RefreshCw, Clock, Trash2, Send, StopCircle, X,
} from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import {
  VisionAnalysisResult,
  type VisionAnalysisResponse,
} from "@/components/VisionAnalysisResult";
import { askVisualStream, type StreamCallbacks } from "@/lib/auth";

// ─── API ─────────────────────────────────────────────────────────

async function uploadPhoto(file: File, token: string): Promise<{ visual_id: string }> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("conversation_id", crypto.randomUUID());
  fd.append("kind", "vision_analysis");
  const res = await fetch("/api/visual/upload", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e?.detail || "Upload failed"); }
  return res.json();
}

async function runAnalysis(visualId: string, ctx: Record<string, any>, token: string): Promise<VisionAnalysisResponse> {
  const res = await fetch("/api/vision/analyse", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ visual_id: visualId, ...ctx }),
  });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e?.detail || "Analysis failed"); }
  return res.json();
}

async function runSerial(beforeId: string, afterId: string, ctx: Record<string, any>, token: string): Promise<any> {
  const res = await fetch("/api/vision/serial-compare", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ visual_id_before: beforeId, visual_id_after: afterId, ...ctx }),
  });
  if (!res.ok) throw new Error("Comparison failed");
  return res.json();
}

async function deletePhoto(visualId: string, token: string) {
  await fetch(`/api/visual/delete/${visualId}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
}

// ─── Shared helpers ───────────────────────────────────────────────

const inputCls = "w-full text-sm rounded-lg border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400 bg-background text-foreground";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className="text-xs font-medium text-gray-500 block mb-1">{label}</label>{children}</div>;
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 flex gap-2 items-start">
      <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />{message}
    </div>
  );
}

interface UploadedPhoto { visualId: string; previewUrl: string; }

// ─── Shared PhotoPanel ────────────────────────────────────────────

function PhotoPanel({ photo, onUpload, onClear, uploading, children }: {
  photo: UploadedPhoto | null; onUpload: (f: File) => void;
  onClear: () => void; uploading: boolean; children?: React.ReactNode;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="space-y-3">
      <div
        onClick={() => !photo && ref.current?.click()}
        className={`relative border-2 border-dashed rounded-xl transition-all overflow-hidden
          ${photo ? "border-teal-400 cursor-default" : "border-gray-300 hover:border-teal-400 hover:bg-teal-50/40 cursor-pointer min-h-[130px] flex flex-col items-center justify-center gap-2"}`}
      >
        {uploading ? (
          <div className="flex flex-col items-center justify-center min-h-[130px]">
            <Loader2 className="w-6 h-6 animate-spin text-teal-600" />
            <p className="text-xs text-gray-500 mt-2">Uploading…</p>
          </div>
        ) : photo ? (
          <div className="relative group">
            <img src={photo.previewUrl} alt="Uploaded" className="w-full max-h-[200px] object-cover" />
            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100">
              <button onClick={e => { e.stopPropagation(); ref.current?.click(); }} className="text-xs bg-white text-gray-800 px-3 py-1.5 rounded-lg font-medium shadow">Replace</button>
              <button onClick={e => { e.stopPropagation(); onClear(); }} className="text-xs bg-red-50 text-red-700 px-3 py-1.5 rounded-lg font-medium shadow">Remove</button>
            </div>
          </div>
        ) : (
          <>
            <div className="w-10 h-10 rounded-full bg-teal-100 flex items-center justify-center"><Upload className="w-5 h-5 text-teal-600" /></div>
            <p className="text-xs font-medium text-gray-600">Upload clinical photo</p>
            <p className="text-xs text-gray-400">JPEG · PNG · WEBP · max 20 MB</p>
          </>
        )}
      </div>
      <input ref={ref} type="file" accept="image/*" className="hidden"
        onChange={e => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = ""; }} />
      {photo && children}
    </div>
  );
}

// ─── TAB 1: Analyse ───────────────────────────────────────────────

function AnalyseTab({ photo, uploading, onUpload, onClear, token }: {
  photo: UploadedPhoto | null; uploading: boolean; onUpload: (f: File) => void; onClear: () => void; token: string;
}) {
  const [procedure, setProcedure] = useState("");
  const [region, setRegion] = useState("");
  const [product, setProduct] = useState("");
  const [daysPP, setDaysPP] = useState<number | "">("");
  const [symptoms, setSymptoms] = useState("");
  const [notes, setNotes] = useState("");
  const [ephemeral, setEphemeral] = useState(false);
  const [result, setResult] = useState<VisionAnalysisResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleted, setDeleted] = useState(false);

  const analyse = async () => {
    if (!photo) return;
    setAnalyzing(true); setError(null);
    try {
      const data = await runAnalysis(photo.visualId, {
        procedure_type: procedure || undefined,
        days_post_procedure: daysPP !== "" ? Number(daysPP) : undefined,
        injected_region: region || undefined,
        product_type: product || undefined,
        patient_symptoms: symptoms ? symptoms.split(",").map(s => s.trim()).filter(Boolean) : [],
        clinical_notes: notes || undefined,
      }, token);
      setResult(data);
      if (ephemeral) { await deletePhoto(photo.visualId, token); onClear(); setDeleted(true); }
    } catch (err: any) { setError(err.message); }
    finally { setAnalyzing(false); }
  };

  const reset = () => {
    setResult(null); setError(null);
    setProcedure(""); setRegion(""); setProduct(""); setDaysPP(""); setSymptoms(""); setNotes(""); setDeleted(false);
  };

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} />}
      {!result ? (
        <PhotoPanel photo={photo} onUpload={onUpload} onClear={onClear} uploading={uploading}>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Procedure type"><input type="text" value={procedure} onChange={e => setProcedure(e.target.value)} placeholder="e.g. lip filler" className={inputCls} /></Field>
            <Field label="Injected region"><input type="text" value={region} onChange={e => setRegion(e.target.value)} placeholder="e.g. upper lip" className={inputCls} /></Field>
            <Field label="Product"><input type="text" value={product} onChange={e => setProduct(e.target.value)} placeholder="e.g. Juvederm" className={inputCls} /></Field>
            <Field label="Days post-procedure"><input type="number" min={0} value={daysPP} onChange={e => setDaysPP(e.target.value === "" ? "" : Number(e.target.value))} placeholder="e.g. 3" className={inputCls} /></Field>
          </div>
          <Field label="Patient symptoms (comma-separated)"><input type="text" value={symptoms} onChange={e => setSymptoms(e.target.value)} placeholder="e.g. pain, swelling, discolouration" className={inputCls} /></Field>
          <Field label="Clinical notes"><textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} placeholder="Any additional context…" className={`${inputCls} resize-none`} /></Field>
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => setEphemeral(e => !e)} className={`relative w-9 h-5 rounded-full transition-colors ${ephemeral ? "bg-teal-600" : "bg-gray-300"}`}>
              <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${ephemeral ? "translate-x-4" : "translate-x-0.5"}`} />
            </button>
            <span className="text-xs text-muted-foreground">Delete image after analysis</span>
            {ephemeral && <ShieldCheck className="w-3.5 h-3.5 text-teal-600" />}
          </div>
          <Button onClick={analyse} disabled={analyzing || !photo} className="w-full bg-teal-700 hover:bg-teal-800 text-white gap-2">
            {analyzing ? <><Loader2 className="w-4 h-4 animate-spin" />Analysing…</> : <><Activity className="w-4 h-4" />Run complication analysis</>}
          </Button>
        </PhotoPanel>
      ) : (
        <>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              {photo && !deleted && <img src={photo.previewUrl} alt="" className="w-10 h-10 rounded-lg object-cover border border-border" />}
              <div>
                <p className="text-sm font-semibold text-foreground">Analysis complete</p>
                <p className="text-xs text-muted-foreground">{new Date(result.generated_at_utc).toLocaleString()}</p>
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={reset} className="text-xs gap-1 shrink-0"><RefreshCw className="w-3.5 h-3.5" /> New</Button>
          </div>
          <VisionAnalysisResult result={result} onRerun={analyse} />
          {photo && !deleted && (
            <Button variant="outline" size="sm" onClick={async () => { await deletePhoto(photo.visualId, token); onClear(); setDeleted(true); }} className="w-full text-xs gap-1.5 text-red-600 border-red-200 hover:bg-red-50">
              <Trash2 className="w-3.5 h-3.5" /> Delete image from server
            </Button>
          )}
        </>
      )}
    </div>
  );
}

// ─── TAB 2: Ask ───────────────────────────────────────────────────

interface ChatMsg { role: "user" | "assistant"; content: string; streaming?: boolean; }

const SUGGESTED = [
  "What complications could explain these visual findings?",
  "Is there any sign of vascular compromise?",
  "What should I do next based on what you see?",
  "Are there any reassuring signs in this image?",
];

function AskTab({ photo, uploading, onUpload, onClear, token }: {
  photo: UploadedPhoto | null; uploading: boolean; onUpload: (f: File) => void; onClear: () => void; token: string;
}) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [convId] = useState(() => crypto.randomUUID());
  const bottomRef = useRef<HTMLDivElement>(null);

  const scrollDown = () => bottomRef.current?.scrollIntoView({ behavior: "smooth" });

  const send = useCallback(async (question: string) => {
    if (!photo || !question.trim() || streaming) return;
    const q = question.trim(); setInput("");
    setMessages(m => [...m, { role: "user", content: q }, { role: "assistant", content: "", streaming: true }]);
    setStreaming(true);
    let content = "";
    const cb: StreamCallbacks = {
      onToken: (tok: string) => {
        content += tok;
        setMessages(m => { const c = [...m]; c[c.length-1] = { ...c[c.length-1], content }; return c; });
        scrollDown();
      },
      onDone: () => { setMessages(m => { const c = [...m]; c[c.length-1] = { ...c[c.length-1], streaming: false }; return c; }); setStreaming(false); },
      onError: (msg: string) => { setMessages(m => { const c = [...m]; c[c.length-1] = { ...c[c.length-1], content: `Error: ${msg}`, streaming: false }; return c; }); setStreaming(false); },
      onMeta: () => {}, onRelated: () => {},
    };
    try { await askVisualStream(token, q, convId, cb, photo.visualId); }
    catch (e: any) { if (streaming) cb.onError(e.message); }
  }, [photo, streaming, token, convId]);

  return (
    <div className="space-y-4">
      <PhotoPanel photo={photo} onUpload={onUpload} onClear={onClear} uploading={uploading}>
        {messages.length === 0 && (
          <div className="space-y-1.5 pt-1">
            <p className="text-xs text-muted-foreground">Suggested questions:</p>
            {SUGGESTED.map((q, i) => (
              <button key={i} onClick={() => send(q)} className="w-full text-left text-xs text-teal-700 bg-teal-50 hover:bg-teal-100 border border-teal-200 rounded-lg px-3 py-2 transition-colors">
                {q}
              </button>
            ))}
          </div>
        )}
      </PhotoPanel>

      {messages.length > 0 && (
        <div className="space-y-3 max-h-[380px] overflow-y-auto pr-1">
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${msg.role === "user" ? "bg-teal-700 text-white" : "bg-muted/60 text-foreground border border-border"}`}>
                {msg.content || (msg.streaming ? <Loader2 className="w-3.5 h-3.5 animate-spin inline" /> : "")}
                {msg.streaming && msg.content && <span className="inline-block w-1.5 h-3.5 bg-teal-500 animate-pulse ml-0.5 rounded-sm" />}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}

      {photo && (
        <div className="flex gap-2">
          <input type="text" value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
            placeholder="Ask about this photo…" disabled={streaming} className={`${inputCls} flex-1`} />
          {streaming
            ? <Button variant="outline" size="sm" onClick={() => setStreaming(false)} className="shrink-0 gap-1.5"><StopCircle className="w-4 h-4" />Stop</Button>
            : <Button onClick={() => send(input)} disabled={!input.trim()} size="sm" className="shrink-0 bg-teal-700 hover:bg-teal-800 text-white"><Send className="w-3.5 h-3.5" /></Button>}
        </div>
      )}
      {messages.length > 0 && (
        <Button variant="ghost" size="sm" onClick={() => setMessages([])} className="w-full text-xs gap-1.5 text-muted-foreground">
          <X className="w-3 h-3" /> Clear conversation
        </Button>
      )}
    </div>
  );
}

// ─── TAB 3: Healing tracker ───────────────────────────────────────

const TRAJ: Record<string, { wrap: string; text: string; icon: React.ReactNode }> = {
  improving: { wrap: "bg-green-50 border-green-300", text: "text-green-800", icon: <CheckCircle className="w-4 h-4" /> },
  stable:    { wrap: "bg-blue-50 border-blue-300",   text: "text-blue-800",  icon: <Clock className="w-4 h-4" />       },
  worsening: { wrap: "bg-red-50 border-red-400",     text: "text-red-800",   icon: <AlertTriangle className="w-4 h-4" /> },
  mixed:     { wrap: "bg-amber-50 border-amber-300", text: "text-amber-800", icon: <Activity className="w-4 h-4" />    },
};

function HealingTab({ token }: { token: string }) {
  const bRef = useRef<HTMLInputElement>(null), aRef = useRef<HTMLInputElement>(null);
  const [bp, setBp] = useState<string|null>(null), [ap, setAp] = useState<string|null>(null);
  const [bid, setBid] = useState<string|null>(null), [aid, setAid] = useState<string|null>(null);
  const [lB, setLB] = useState(false), [lA, setLA] = useState(false);
  const [days, setDays] = useState<number|"">("");
  const [proc, setProc] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string|null>(null);

  const handleUp = async (file: File, setP: (u:string)=>void, setId: (id:string)=>void, setLd: (b:boolean)=>void) => {
    setP(URL.createObjectURL(file)); setLd(true);
    try { const { visual_id } = await uploadPhoto(file, token); setId(visual_id); }
    catch(e:any) { setError(e.message); } finally { setLd(false); }
  };

  const compare = async () => {
    if (!bid || !aid) return;
    setLoading(true); setError(null);
    try { setResult(await runSerial(bid, aid, { days_between: days !== "" ? Number(days) : undefined, procedure_type: proc || undefined }, token)); }
    catch(e:any) { setError(e.message); } finally { setLoading(false); }
  };

  const t = result ? (TRAJ[result.overall_trajectory] ?? TRAJ.stable) : null;

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} />}
      <div className="grid grid-cols-2 gap-3">
        {[
          { label:"Before", p:bp, ld:lB, ref:bRef, setP:setBp, setId:setBid, setLd:setLB },
          { label:"After",  p:ap, ld:lA, ref:aRef, setP:setAp, setId:setAid, setLd:setLA },
        ].map(({ label, p, ld, ref, setP, setId, setLd }) => (
          <div key={label}>
            <p className="text-xs font-medium text-muted-foreground mb-1.5">{label}</p>
            <div onClick={() => ref.current?.click()}
              className={`border-2 border-dashed rounded-xl cursor-pointer transition-all overflow-hidden min-h-[120px] flex flex-col items-center justify-center gap-1.5 ${p ? "border-teal-400" : "border-gray-300 hover:border-teal-400 hover:bg-teal-50/40"}`}>
              {ld ? <Loader2 className="w-5 h-5 animate-spin text-teal-600" />
                : p ? <img src={p} alt={label} className="w-full max-h-[150px] object-cover" />
                : <><Upload className="w-4 h-4 text-gray-400" /><p className="text-xs text-gray-500">{label} photo</p></>}
            </div>
            <input ref={ref} type="file" accept="image/*" className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if(f) handleUp(f, setP, setId, setLd); }} />
          </div>
        ))}
      </div>

      {bid && aid && !result && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Days between"><input type="number" min={0} value={days} onChange={e => setDays(e.target.value===""?"":Number(e.target.value))} placeholder="e.g. 7" className={inputCls} /></Field>
            <Field label="Procedure"><input type="text" value={proc} onChange={e => setProc(e.target.value)} placeholder="e.g. lip filler" className={inputCls} /></Field>
          </div>
          <Button onClick={compare} disabled={loading} className="w-full bg-teal-700 hover:bg-teal-800 text-white gap-2">
            {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Comparing…</> : <><ArrowLeftRight className="w-4 h-4" />Compare healing progress</>}
          </Button>
        </>
      )}

      {result && t && (
        <div className="space-y-3">
          <div className={`rounded-xl border-2 px-4 py-3 ${t.wrap}`}>
            <div className="flex items-center gap-2 mb-1"><span className={t.text}>{t.icon}</span><span className={`font-bold text-sm capitalize ${t.text}`}>{result.overall_trajectory}</span></div>
            <p className={`text-sm ${t.text} opacity-80 leading-relaxed`}>{result.change_summary}</p>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {[
              { label:"Improving", items:result.improving_features, tw:"bg-green-50 border-green-200 text-green-700" },
              { label:"Stable",    items:result.stable_features,    tw:"bg-blue-50 border-blue-200 text-blue-700" },
              { label:"Worsening", items:result.worsening_features,  tw:"bg-red-50 border-red-200 text-red-700" },
            ].map(({ label, items, tw }) => (
              <div key={label} className={`rounded-lg border p-2.5 ${tw}`}>
                <p className="text-xs font-bold mb-1.5">{label}</p>
                {items?.length ? items.map((f:string,i:number) => <p key={i} className="text-xs opacity-80">{f}</p>) : <p className="text-xs italic opacity-50">None</p>}
              </div>
            ))}
          </div>
          <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Clinical interpretation</p>
            <p className="text-sm text-foreground leading-relaxed">{result.clinical_interpretation}</p>
          </div>
          <div className="rounded-lg border border-teal-200 bg-teal-50 px-4 py-3">
            <p className="text-xs font-semibold text-teal-600 uppercase tracking-wide mb-1">Recommended action</p>
            <p className="text-sm text-teal-800 font-medium">{result.recommended_action}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => setResult(null)} className="w-full text-xs gap-1.5">
            <RefreshCw className="w-3.5 h-3.5" /> New comparison
          </Button>
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────

export default function VisionPage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<"analyse"|"ask"|"healing">("analyse");
  const [photo, setPhoto] = useState<UploadedPhoto|null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState<string|null>(null);

  const handleUpload = async (file: File) => {
    if (!token) return;
    setUploading(true); setUploadErr(null);
    try { const { visual_id } = await uploadPhoto(file, token); setPhoto({ visualId: visual_id, previewUrl: URL.createObjectURL(file) }); }
    catch(e:any) { setUploadErr(e.message); } finally { setUploading(false); }
  };

  return (
    <div className="max-w-xl mx-auto px-4 py-6">
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-1">
          <Activity className="w-5 h-5 text-teal-600" />
          <h1 className="text-lg font-bold text-foreground">AesthetiCite Vision</h1>
          <span className="text-xs bg-teal-100 text-teal-700 px-2 py-0.5 rounded-full font-medium">Beta</span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          AI highlights visual patterns that may indicate complications and guides next steps. Not a diagnosis.
        </p>
      </div>

      {uploadErr && <ErrorBanner message={uploadErr} />}

      <div className="flex gap-1 bg-muted rounded-lg p-1 mb-5">
        {[
          { id:"analyse", label:"Analyse",         icon:<Activity className="w-3.5 h-3.5" />,      sub:"Complication assessment" },
          { id:"ask",     label:"Ask",             icon:<MessageSquare className="w-3.5 h-3.5" />,  sub:"Q&A about this photo"    },
          { id:"healing", label:"Healing tracker", icon:<ArrowLeftRight className="w-3.5 h-3.5" />, sub:"Before vs after"         },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id as any)}
            className={`flex-1 flex flex-col items-center py-2 px-1 rounded-md transition-all ${tab===t.id ? "bg-background text-teal-700 shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
            <span className="flex items-center gap-1 text-xs font-medium">{t.icon}{t.label}</span>
            <span className="text-[10px] opacity-60">{t.sub}</span>
          </button>
        ))}
      </div>

      {tab==="analyse" && <AnalyseTab photo={photo} uploading={uploading} onUpload={handleUpload} onClear={() => setPhoto(null)} token={token!} />}
      {tab==="ask"     && <AskTab     photo={photo} uploading={uploading} onUpload={handleUpload} onClear={() => setPhoto(null)} token={token!} />}
      {tab==="healing" && <HealingTab token={token!} />}
    </div>
  );
}
