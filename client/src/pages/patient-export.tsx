import { useState } from "react";
import { Link } from "wouter";
import { ArrowLeft, FileText, Loader2, Copy, CheckCheck, User } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

type PatientReadableResponse = { id: string; patient_text: string; created_at_utc: string };

const EXAMPLES = [
  {
    label: "Hyaluronidase",
    title: "Hyaluronidase for vascular occlusion",
    text: "High-dose pulsed hyaluronidase is the primary intervention for HA filler-related vascular occlusion. Early recognition and rapid administration improve outcomes. The dose ranges from 200 to 1500 units depending on territory and clinical response. Reassessment should occur within 60 minutes of initial treatment.",
  },
  {
    label: "Botox Ptosis",
    title: "Ptosis after botulinum toxin",
    text: "Ptosis following botulinum toxin injection is caused by diffusion of the toxin to the levator palpebrae superioris muscle. It typically resolves within 4 to 8 weeks as the toxin effect wanes. Apraclonidine eye drops may be used to temporarily elevate the upper eyelid.",
  },
];

export default function PatientExportPage() {
  const [title, setTitle] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [clinicId, setClinicId] = useState("");
  const [result, setResult] = useState<PatientReadableResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleSimplify() {
    if (!title.trim() || !sourceText.trim()) { setError("Fill in both title and clinical text."); return; }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/growth/patient-readable-export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_title: title.trim(), source_text: sourceText.trim(), clinic_id: clinicId.trim() || undefined }),
      });
      if (!res.ok) throw new Error(await res.text());
      setResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Simplification failed.");
    } finally {
      setLoading(false);
    }
  }

  async function copyResult() {
    if (!result) return;
    await navigator.clipboard.writeText(result.patient_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function applyExample(ex: typeof EXAMPLES[0]) {
    setTitle(ex.title);
    setSourceText(ex.text);
    setResult(null);
    setError(null);
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 p-4 md:p-8">
      <div className="mx-auto max-w-4xl">
        <div className="mb-6">
          <Link href="/ask">
            <Button variant="ghost" size="sm" className="gap-1.5 text-slate-500 -ml-2">
              <ArrowLeft className="h-4 w-4" /> Back to Search
            </Button>
          </Link>
        </div>

        <div className="mb-8">
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">Patient-Readable Export</h1>
          <p className="mt-1 text-sm text-slate-500">Convert clinical evidence text into plain language a patient can understand.</p>
        </div>

        <div className="mb-5 flex flex-wrap gap-2 items-center">
          <span className="text-xs text-slate-400">Try an example:</span>
          {EXAMPLES.map((ex) => (
            <button key={ex.label} onClick={() => applyExample(ex)}
              className="rounded-full border border-slate-200 dark:border-slate-700 px-3 py-1 text-xs text-slate-500 hover:border-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
              {ex.label}
            </button>
          ))}
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="rounded-2xl border shadow-sm bg-white dark:bg-slate-900 self-start">
            <CardHeader><CardTitle className="text-lg">Clinical Input</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="title">Source Title</Label>
                <Input id="title" data-testid="input-source-title" placeholder="e.g. Hyaluronidase for vascular occlusion" value={title} onChange={(e) => setTitle(e.target.value)} className="rounded-xl" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="source">Clinical Text</Label>
                <Textarea
                  id="source"
                  data-testid="input-source-text"
                  placeholder="Paste the clinical summary, evidence note, or guideline excerpt here..."
                  value={sourceText}
                  onChange={(e) => setSourceText(e.target.value)}
                  className="min-h-[200px] resize-none rounded-xl"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="clinic">Clinic ID (optional)</Label>
                <Input id="clinic" data-testid="input-clinic-id" placeholder="e.g. clinic_001" value={clinicId} onChange={(e) => setClinicId(e.target.value)} className="rounded-xl" />
              </div>
              <Button className="w-full rounded-xl" onClick={handleSimplify} disabled={loading || !title.trim() || !sourceText.trim()} data-testid="button-simplify">
                {loading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Simplifying...</> : <><User className="mr-2 h-4 w-4" />Generate Patient Version</>}
              </Button>
              {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
            </CardContent>
          </Card>

          <Card className="rounded-2xl border shadow-sm bg-white dark:bg-slate-900 self-start">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-lg">Patient Version</CardTitle>
              {result && (
                <Button variant="ghost" size="sm" onClick={copyResult} className="gap-1.5 text-xs" data-testid="button-copy-patient-text">
                  {copied ? <><CheckCheck className="h-3.5 w-3.5 text-green-500" />Copied</> : <><Copy className="h-3.5 w-3.5" />Copy</>}
                </Button>
              )}
            </CardHeader>
            <CardContent>
              {!result ? (
                <div className="flex min-h-[280px] flex-col items-center justify-center text-center">
                  <FileText className="mb-3 h-10 w-10 text-slate-200 dark:text-slate-700" />
                  <p className="text-sm text-slate-400">The plain-language version will appear here.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="rounded-xl border bg-slate-50 dark:bg-slate-800/50 p-4">
                    <pre className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap font-sans leading-relaxed">{result.patient_text}</pre>
                  </div>
                  <p className="text-xs text-slate-400">Export ID: {result.id.slice(0, 8)}... · {new Date(result.created_at_utc).toLocaleString()}</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
