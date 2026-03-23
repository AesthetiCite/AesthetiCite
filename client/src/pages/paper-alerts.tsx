import { useState, useEffect } from "react";
import { Link } from "wouter";
import { ArrowLeft, Bell, Plus, Loader2, RefreshCw, Mail, ExternalLink } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { getMe, getToken } from "@/lib/auth";

type Subscription = {
  id: string;
  user_id: string;
  topic: string;
  email: string | null;
  last_checked_utc: string | null;
  created_at_utc: string;
};

type DigestItem = {
  title: string;
  abstract?: string;
  url?: string;
  published_date?: string;
};

type DigestResult = {
  subscription_id: string;
  topic: string;
  new_items: DigestItem[];
};

const SUGGESTED_TOPICS = [
  "vascular occlusion filler",
  "botulinum toxin ptosis",
  "hyaluronidase dosing",
  "tear trough filler safety",
  "lip filler complications",
];

export default function PaperAlertsPage() {
  const [userId, setUserId] = useState<string>("");
  const [topic, setTopic] = useState("");
  const [email, setEmail] = useState("");
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [digests, setDigests] = useState<Record<string, DigestResult>>({});
  const [loading, setLoading] = useState(true);
  const [subscribing, setSubscribing] = useState(false);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) { setLoading(false); return; }
    getMe(token).then((u) => {
      if (u?.email) {
        setUserId(u.email);
        fetchSubscriptions(u.email);
      } else {
        setLoading(false);
      }
    });
  }, []);

  async function fetchSubscriptions(uid: string) {
    setLoading(true);
    try {
      const res = await fetch(`/api/growth/paper-alerts/${encodeURIComponent(uid)}`);
      if (res.ok) setSubscriptions(await res.json());
    } finally {
      setLoading(false);
    }
  }

  async function handleSubscribe() {
    if (!topic.trim()) { setError("Enter a topic."); return; }
    setSubscribing(true);
    setError(null);
    try {
      const res = await fetch("/api/growth/paper-alerts/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, topic: topic.trim(), email: email.trim() || undefined }),
      });
      if (!res.ok) throw new Error(await res.text());
      const sub: Subscription = await res.json();
      setSubscriptions((prev) => [sub, ...prev]);
      setTopic("");
      setEmail("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Subscription failed.");
    } finally {
      setSubscribing(false);
    }
  }

  async function runDigest(sub: Subscription) {
    setRunningId(sub.id);
    try {
      const res = await fetch(`/api/growth/paper-alerts/${sub.id}/run`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const digest: DigestResult = await res.json();
      setDigests((prev) => ({ ...prev, [sub.id]: digest }));
      setSubscriptions((prev) => prev.map((s) => s.id === sub.id ? { ...s, last_checked_utc: new Date().toISOString() } : s));
    } finally {
      setRunningId(null);
    }
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

        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">Paper Alerts</h1>
            <p className="mt-1 text-sm text-slate-500">Get notified when new publications match your clinical topics.</p>
          </div>
          <div className="flex items-center gap-2 rounded-2xl border bg-white dark:bg-slate-900 px-4 py-2 shadow-sm">
            <Bell className="h-4 w-4 text-slate-400" />
            <span className="text-sm text-slate-500">{subscriptions.length} topics</span>
          </div>
        </div>

        <Card className="rounded-2xl border shadow-sm bg-white dark:bg-slate-900 mb-8">
          <CardHeader><CardTitle className="text-lg">Subscribe to a Topic</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="topic">Clinical Topic</Label>
                <Input id="topic" data-testid="input-topic" placeholder="e.g. vascular occlusion filler" value={topic} onChange={(e) => setTopic(e.target.value)} className="rounded-xl" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email (optional)</Label>
                <Input id="email" data-testid="input-email" type="email" placeholder="your@email.com" value={email} onChange={(e) => setEmail(e.target.value)} className="rounded-xl" />
              </div>
            </div>

            <div className="flex flex-wrap gap-2 items-center">
              <span className="text-xs text-slate-400">Suggestions:</span>
              {SUGGESTED_TOPICS.map((t) => (
                <button key={t} onClick={() => setTopic(t)}
                  className="rounded-full border border-slate-200 dark:border-slate-700 px-3 py-1 text-xs text-slate-500 hover:border-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
                  {t}
                </button>
              ))}
            </div>

            <Button className="w-full rounded-xl" onClick={handleSubscribe} disabled={subscribing || !topic.trim() || !userId} data-testid="button-subscribe">
              {subscribing ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Subscribing...</> : <><Plus className="mr-2 h-4 w-4" />Subscribe</>}
            </Button>
            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
          </CardContent>
        </Card>

        {loading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
          </div>
        )}

        {!loading && subscriptions.length === 0 && (
          <Card className="rounded-2xl border shadow-sm bg-white dark:bg-slate-900">
            <CardContent className="flex min-h-[240px] items-center justify-center text-center p-10">
              <div>
                <Bell className="mx-auto mb-3 h-12 w-12 text-slate-200 dark:text-slate-700" />
                <p className="text-sm text-slate-400">No alert subscriptions yet. Subscribe to a clinical topic above to receive new publication digests.</p>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="space-y-6">
          {subscriptions.map((sub) => (
            <Card key={sub.id} className="rounded-2xl border shadow-sm bg-white dark:bg-slate-900" data-testid={`subscription-card-${sub.id}`}>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle className="text-base">{sub.topic}</CardTitle>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                      {sub.email && <span className="flex items-center gap-1"><Mail className="h-3 w-3" />{sub.email}</span>}
                      {sub.last_checked_utc && <span>Last checked: {new Date(sub.last_checked_utc).toLocaleDateString()}</span>}
                      {!sub.last_checked_utc && <Badge variant="secondary" className="text-xs">Never run</Badge>}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    className="rounded-xl shrink-0"
                    onClick={() => runDigest(sub)}
                    disabled={runningId === sub.id}
                    data-testid={`button-run-digest-${sub.id}`}
                  >
                    {runningId === sub.id
                      ? <><Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />Checking...</>
                      : <><RefreshCw className="mr-1.5 h-3.5 w-3.5" />Run Digest</>}
                  </Button>
                </div>
              </CardHeader>

              {digests[sub.id] && (
                <CardContent className="pt-0">
                  <div className="border-t pt-4 space-y-3">
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                      {digests[sub.id].new_items.length} new paper{digests[sub.id].new_items.length !== 1 ? "s" : ""} found
                    </p>
                    {digests[sub.id].new_items.map((item, idx) => (
                      <div key={idx} className="rounded-xl border bg-slate-50 dark:bg-slate-800/50 p-4 space-y-2">
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{item.title}</p>
                          {item.url && (
                            <a href={item.url} target="_blank" rel="noopener noreferrer" className="shrink-0 text-slate-400 hover:text-blue-500">
                              <ExternalLink className="h-4 w-4" />
                            </a>
                          )}
                        </div>
                        {item.abstract && <p className="text-xs text-slate-500 line-clamp-3">{item.abstract}</p>}
                        {item.published_date && <p className="text-xs text-slate-400">{item.published_date}</p>}
                      </div>
                    ))}
                  </div>
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
