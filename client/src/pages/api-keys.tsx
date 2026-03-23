import { useState } from "react";
import { Link } from "wouter";
import { ArrowLeft, Key, Plus, Copy, CheckCheck, Loader2, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

type APIKeyCreateResponse = { id: string; clinic_id: string; label: string; api_key: string; created_at_utc: string };

export default function APIKeysPage() {
  const [clinicId, setClinicId] = useState("");
  const [label, setLabel] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [keys, setKeys] = useState<APIKeyCreateResponse[]>([]);
  const [visibleKey, setVisibleKey] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  async function handleCreate() {
    if (!clinicId.trim() || !label.trim()) { setError("Clinic ID and label are required."); return; }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/growth/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clinic_id: clinicId.trim(), label: label.trim() }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data: APIKeyCreateResponse = await res.json();
      setKeys((prev) => [data, ...prev]);
      setLabel("");
      setVisibleKey(data.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create key.");
    } finally {
      setLoading(false);
    }
  }

  async function copyKey(key: string, id: string) {
    await navigator.clipboard.writeText(key);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 p-4 md:p-8">
      <div className="mx-auto max-w-3xl">
        <div className="mb-6">
          <Link href="/ask">
            <Button variant="ghost" size="sm" className="gap-1.5 text-slate-500 -ml-2">
              <ArrowLeft className="h-4 w-4" /> Back to Search
            </Button>
          </Link>
        </div>

        <div className="mb-8">
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">Clinic API Keys</h1>
          <p className="mt-1 text-sm text-slate-500">Generate API keys to integrate AesthetiCite into your clinic systems.</p>
        </div>

        <div className="mb-8 rounded-2xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950 p-4 text-sm text-amber-700 dark:text-amber-300">
          <strong>Security:</strong> Each key is shown once at the time of creation. Copy and store it securely — it cannot be retrieved again.
        </div>

        <Card className="rounded-2xl border shadow-sm bg-white dark:bg-slate-900 mb-8">
          <CardHeader><CardTitle className="text-lg">Generate New Key</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="clinic-id">Clinic ID</Label>
                <Input id="clinic-id" data-testid="input-clinic-id" placeholder="e.g. clinic_london_001" value={clinicId} onChange={(e) => setClinicId(e.target.value)} className="rounded-xl" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="key-label">Label</Label>
                <Input id="key-label" data-testid="input-key-label" placeholder="e.g. EMR integration" value={label} onChange={(e) => setLabel(e.target.value)} className="rounded-xl" onKeyDown={(e) => e.key === "Enter" && handleCreate()} />
              </div>
            </div>
            <Button className="w-full rounded-xl" onClick={handleCreate} disabled={loading || !clinicId.trim() || !label.trim()} data-testid="button-create-key">
              {loading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Generating...</> : <><Plus className="mr-2 h-4 w-4" />Generate Key</>}
            </Button>
            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
          </CardContent>
        </Card>

        {keys.length > 0 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-200">Keys generated this session</h2>
            {keys.map((k) => (
              <Card key={k.id} className="rounded-2xl border shadow-sm bg-white dark:bg-slate-900" data-testid={`key-card-${k.id}`}>
                <CardContent className="p-5 space-y-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <ShieldCheck className="h-4 w-4 text-green-500" />
                        <p className="font-medium text-slate-900 dark:text-slate-100">{k.label}</p>
                        <Badge variant="secondary" className="text-xs">{k.clinic_id}</Badge>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5">{new Date(k.created_at_utc).toLocaleString()}</p>
                    </div>
                  </div>

                  {visibleKey === k.id ? (
                    <div className="rounded-xl border bg-slate-900 dark:bg-slate-950 p-3 flex items-center justify-between gap-3">
                      <code className="text-sm text-green-400 font-mono break-all">{k.api_key}</code>
                      <div className="flex gap-2 shrink-0">
                        <Button variant="ghost" size="sm" onClick={() => copyKey(k.api_key, k.id)} className="text-slate-400 hover:text-white" data-testid={`button-copy-key-${k.id}`}>
                          {copied === k.id ? <CheckCheck className="h-4 w-4 text-green-400" /> : <Copy className="h-4 w-4" />}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setVisibleKey(null)} className="text-slate-400 hover:text-white">
                          <EyeOff className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-xl border bg-slate-100 dark:bg-slate-800 p-3 flex items-center justify-between gap-3">
                      <code className="text-sm text-slate-400 font-mono">ac_••••••••••••••••••••••</code>
                      <Button variant="ghost" size="sm" onClick={() => setVisibleKey(k.id)} className="text-slate-400" data-testid={`button-show-key-${k.id}`}>
                        <Eye className="h-4 w-4" />
                      </Button>
                    </div>
                  )}

                  <div className="rounded-xl border bg-slate-50 dark:bg-slate-800/50 p-3 text-xs text-slate-500">
                    <p className="font-medium mb-1">Usage:</p>
                    <code className="text-xs">POST /api/growth/clinic-api/search</code>
                    <p className="mt-1">Include header: <code>X-API-Key: {visibleKey === k.id ? k.api_key : "ac_..."}</code></p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {keys.length === 0 && (
          <Card className="rounded-2xl border shadow-sm bg-white dark:bg-slate-900">
            <CardContent className="flex min-h-[240px] flex-col items-center justify-center text-center p-10">
              <Key className="mb-4 h-12 w-12 text-slate-200 dark:text-slate-700" />
              <p className="text-slate-500 text-sm">No keys generated yet. Create one above to integrate AesthetiCite into your clinic systems.</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
