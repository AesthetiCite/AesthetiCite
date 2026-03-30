/**
 * vision-sw.js  →  public/vision-sw.js
 * ──────────────────────────────────────
 * Improvement 6: Offline PWA mode for Vision.
 *
 * Service worker that:
 *   1. Caches the Vision capture flow for offline use
 *   2. Queues analysis requests in IndexedDB when offline
 *   3. Replays queued requests when connectivity is restored
 *   4. Shows a "queued — will analyse when online" notification
 *
 * Register in client/src/main.tsx or index.html:
 *   if ('serviceWorker' in navigator) {
 *     navigator.serviceWorker.register('/vision-sw.js');
 *   }
 */

const CACHE_NAME   = 'aestheticite-vision-v2';
const QUEUE_STORE  = 'vision-queue';
const QUEUE_DB     = 'aestheticite-queue-db';
const QUEUE_DB_VER = 1;

// Pages and assets to cache for offline Vision capture
const VISION_CACHE_URLS = [
  '/visual-counsel',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
];

// API routes that should be queued when offline
const QUEUE_PATTERNS = [
  /\/api\/visual\/v2\/stream/,
  /\/api\/visual\/v2\/analyse/,
  /\/api\/visual\/upload/,
  /\/api\/visual\/landmark-analyse/,
];

// API routes to always network-first (safety-critical)
const NETWORK_FIRST_PATTERNS = [
  /\/api\/complications\//,
  /\/api\/safety\//,
  /\/api\/ask\//,
];

// ─── IndexedDB helpers ────────────────────────────────────────────────────────

function openQueueDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(QUEUE_DB, QUEUE_DB_VER);
    req.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(QUEUE_STORE)) {
        db.createObjectStore(QUEUE_STORE, { keyPath: 'id', autoIncrement: true });
      }
    };
    req.onsuccess = e => resolve(e.target.result);
    req.onerror   = e => reject(e.target.error);
  });
}

async function enqueueRequest(request) {
  const db = await openQueueDB();
  const body = await request.clone().arrayBuffer();
  const headers = {};
  request.headers.forEach((val, key) => { headers[key] = val; });

  return new Promise((resolve, reject) => {
    const tx    = db.transaction(QUEUE_STORE, 'readwrite');
    const store = tx.objectStore(QUEUE_STORE);
    const item  = {
      url:       request.url,
      method:    request.method,
      headers,
      body:      Array.from(new Uint8Array(body)),
      queued_at: new Date().toISOString(),
      retries:   0,
    };
    const req = store.add(item);
    req.onsuccess = () => resolve(req.result);
    req.onerror   = e => reject(e.target.error);
  });
}

async function getQueuedRequests() {
  const db = await openQueueDB();
  return new Promise((resolve, reject) => {
    const tx    = db.transaction(QUEUE_STORE, 'readonly');
    const store = tx.objectStore(QUEUE_STORE);
    const req   = store.getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror   = e => reject(e.target.error);
  });
}

async function removeQueuedRequest(id) {
  const db = await openQueueDB();
  return new Promise((resolve, reject) => {
    const tx    = db.transaction(QUEUE_STORE, 'readwrite');
    const store = tx.objectStore(QUEUE_STORE);
    const req   = store.delete(id);
    req.onsuccess = () => resolve();
    req.onerror   = e => reject(e.target.error);
  });
}

// ─── Install: cache Vision pages ─────────────────────────────────────────────

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(VISION_CACHE_URLS))
  );
  self.skipWaiting();
});

// ─── Activate: clean old caches ──────────────────────────────────────────────

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ─── Fetch: strategy by URL pattern ──────────────────────────────────────────

self.addEventListener('fetch', event => {
  const { request } = event;
  const url = request.url;

  // Safety-critical: always network, never cache or queue
  if (NETWORK_FIRST_PATTERNS.some(p => p.test(url))) {
    event.respondWith(fetch(request));
    return;
  }

  // Vision analysis endpoints: queue offline, replay online
  if (QUEUE_PATTERNS.some(p => p.test(url)) && request.method === 'POST') {
    event.respondWith(
      fetch(request.clone()).catch(async () => {
        // Offline — enqueue
        try {
          const queueId = await enqueueRequest(request);
          return new Response(
            JSON.stringify({
              queued:   true,
              queue_id: queueId,
              message:  'Analysis queued — will run automatically when connectivity is restored.',
              offline:  true,
            }),
            {
              status:  202,
              headers: { 'Content-Type': 'application/json' },
            }
          );
        } catch (err) {
          return new Response(
            JSON.stringify({ error: 'Offline and queue failed', detail: String(err) }),
            { status: 503, headers: { 'Content-Type': 'application/json' } }
          );
        }
      })
    );
    return;
  }

  // Static assets: cache-first
  if (request.method === 'GET') {
    event.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(resp => {
        if (resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
        }
        return resp;
      }))
    );
    return;
  }

  // Everything else: network
  event.respondWith(fetch(request));
});

// ─── Background sync: replay queued requests when online ─────────────────────

self.addEventListener('online', replayQueue);

async function replayQueue() {
  const items = await getQueuedRequests();
  if (!items.length) return;

  const clients = await self.clients.matchAll();

  for (const item of items) {
    try {
      const body = new Uint8Array(item.body);
      const resp = await fetch(item.url, {
        method:  item.method,
        headers: item.headers,
        body:    body.buffer,
      });

      if (resp.ok) {
        await removeQueuedRequest(item.id);

        // Notify all open tabs
        clients.forEach(client => client.postMessage({
          type:     'QUEUE_REPLAYED',
          queue_id: item.id,
          url:      item.url,
          status:   resp.status,
          queued_at:item.queued_at,
        }));
      }
    } catch (err) {
      // Still offline — leave in queue
      console.warn('[vision-sw] Replay failed for', item.id, err);
    }
  }
}

// Periodic replay check (every 30s)
self.addEventListener('periodicsync', event => {
  if (event.tag === 'vision-queue-replay') {
    event.waitUntil(replayQueue());
  }
});

// Manual trigger from app
self.addEventListener('message', event => {
  if (event.data?.type === 'REPLAY_QUEUE') {
    replayQueue();
  }
});


/* ═══════════════════════════════════════════════════════════════════════════
   STREAMING VISION UI COMPONENT
   VisionStreamingAnalysis.tsx  →  client/src/components/vision/VisionStreamingAnalysis.tsx

   Uses the /api/visual/v2/stream SSE endpoint for real-time token display.
   Improvement 2 frontend counterpart.
   ═══════════════════════════════════════════════════════════════════════════ */

/*
// PASTE BELOW INTO: client/src/components/vision/VisionStreamingAnalysis.tsx

import { useState, useRef, useCallback, useEffect } from "react";
import {
  Loader2, CheckCircle2, AlertTriangle, Cpu,
  ShieldAlert, Wifi, WifiOff, Database
} from "lucide-react";

interface VisualScores {
  skin_colour_change: number | null;
  swelling_severity:  number | null;
  asymmetry_flag:     boolean | null;
  infection_signal:   number | null;
  ptosis_flag:        boolean | null;
  tyndall_flag:       boolean | null;
  overall_concern_level: string;
}

interface TriggeredProtocol {
  protocol_key:    string;
  protocol_name:   string;
  urgency:         string;
  headline:        string;
  immediate_action:string;
}

interface StreamPhase {
  phase:   "idle" | "preprocessing" | "analysing" | "scoring" | "done" | "error";
  message: string;
}

interface VisionStreamingAnalysisProps {
  file:           File;
  token:          string;
  question?:      string;
  context?:       string;
  onDone?:        (result: {
    fullText:  string;
    scores:    VisualScores;
    protocols: TriggeredProtocol[];
  }) => void;
}

const PHASE_LABELS: Record<string, string> = {
  preprocessing: "Enhancing image…",
  analysing:     "Running analysis…",
  scoring:       "Extracting clinical scores…",
  done:          "Analysis complete",
  error:         "Analysis failed",
};

const CONCERN_COLORS: Record<string, string> = {
  none:     "text-green-600 dark:text-green-400",
  low:      "text-blue-600 dark:text-blue-400",
  moderate: "text-yellow-600 dark:text-yellow-400",
  high:     "text-orange-600 dark:text-orange-400",
  critical: "text-red-600 dark:text-red-400",
};

export function VisionStreamingAnalysis({
  file, token, question, context, onDone
}: VisionStreamingAnalysisProps) {
  const [phase, setPhase]         = useState<StreamPhase>({ phase: "idle", message: "" });
  const [streamText, setStreamText] = useState("");
  const [scores, setScores]       = useState<VisualScores | null>(null);
  const [protocols, setProtocols] = useState<TriggeredProtocol[]>([]);
  const [isOffline, setIsOffline] = useState(!navigator.onLine);
  const [queued, setQueued]       = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const textRef  = useRef<HTMLDivElement>(null);

  // Track online/offline state
  useEffect(() => {
    const onOnline  = () => setIsOffline(false);
    const onOffline = () => setIsOffline(true);
    window.addEventListener("online",  onOnline);
    window.addEventListener("offline", onOffline);

    // Listen for service worker replay notifications
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.addEventListener("message", (e) => {
        if (e.data?.type === "QUEUE_REPLAYED") {
          setQueued(false);
          // Auto-restart analysis when connectivity restored
          startAnalysis();
        }
      });
    }

    return () => {
      window.removeEventListener("online",  onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  // Auto-scroll text
  useEffect(() => {
    if (textRef.current) {
      textRef.current.scrollTop = textRef.current.scrollHeight;
    }
  }, [streamText]);

  const startAnalysis = useCallback(async () => {
    setStreamText("");
    setScores(null);
    setProtocols([]);
    setQueued(false);

    const controller  = new AbortController();
    abortRef.current  = controller;

    const fd = new FormData();
    fd.append("file",     file);
    fd.append("question", question || "Assess this image for post-injectable complication signals.");
    fd.append("context",  context  || "");

    setPhase({ phase: "preprocessing", message: "Enhancing image…" });

    let resp: Response;
    try {
      resp = await fetch("/api/visual/v2/stream", {
        method:  "POST",
        headers: { Authorization: `Bearer ${token}` },
        body:    fd,
        signal:  controller.signal,
      });
    } catch (err: any) {
      if (err.name === "AbortError") return;
      setPhase({ phase: "error", message: "Network error — check connection" });
      return;
    }

    // Offline queued response
    if (resp.status === 202) {
      const data = await resp.json();
      if (data.queued) {
        setQueued(true);
        setPhase({ phase: "idle", message: "Analysis queued for when you're back online" });
        return;
      }
    }

    if (!resp.ok) {
      setPhase({ phase: "error", message: `Analysis failed (${resp.status})` });
      return;
    }

    // Read SSE stream
    const reader  = resp.body?.getReader();
    if (!reader) { setPhase({ phase: "error", message: "No stream" }); return; }

    const decoder = new TextDecoder();
    let buffer    = "";
    let fullText  = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const event = JSON.parse(line.slice(6));

          switch (event.type) {
            case "status":
              setPhase({ phase: event.phase || "analysing", message: event.message || "" });
              break;

            case "content":
              fullText += event.data || event.content || "";
              setStreamText(fullText);
              break;

            case "visual_scores":
              setScores(event.scores);
              setPhase({ phase: "scoring", message: "Extracting clinical scores…" });
              break;

            case "protocol_alert":
              if (event.triggered_protocols) {
                setProtocols(event.triggered_protocols);
              }
              break;

            case "done":
              setPhase({ phase: "done", message: "Analysis complete" });
              onDone?.({
                fullText,
                scores: event.scores || scores,
                protocols: event.triggered_protocols || protocols,
              });
              break;

            case "error":
              setPhase({ phase: "error", message: event.message || "Analysis error" });
              break;
          }
        } catch {}
      }
    }
  }, [file, token, question, context]);

  // Auto-start when file is provided
  useEffect(() => {
    if (file) startAnalysis();
    return () => abortRef.current?.abort();
  }, [file]);

  const concernLevel = scores?.overall_concern_level || "none";
  const concernColor = CONCERN_COLORS[concernLevel] || "";

  return (
    <div className="space-y-4">

      {/* Offline / queued banner */}
      {isOffline && (
        <div className="flex items-center gap-2 rounded-lg border border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-900/20 px-3 py-2">
          <WifiOff className="h-4 w-4 text-orange-500 flex-shrink-0" />
          <p className="text-sm text-orange-700 dark:text-orange-300">
            You're offline. Analysis will be queued and run automatically when connectivity is restored.
          </p>
        </div>
      )}

      {queued && (
        <div className="flex items-center gap-2 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 px-3 py-2">
          <Database className="h-4 w-4 text-blue-500 flex-shrink-0" />
          <p className="text-sm text-blue-700 dark:text-blue-300">
            Analysis queued — will run automatically when you're back online.
          </p>
        </div>
      )}

      {/* Phase indicator */}
      {phase.phase !== "idle" && !queued && (
        <div className="flex items-center gap-2.5">
          {phase.phase === "done"
            ? <CheckCircle2 className="h-5 w-5 text-green-500 flex-shrink-0" />
            : phase.phase === "error"
              ? <AlertTriangle className="h-5 w-5 text-red-500 flex-shrink-0" />
              : <Loader2 className="h-5 w-5 text-blue-500 animate-spin flex-shrink-0" />
          }
          <div>
            <p className="text-sm font-medium text-foreground">
              {PHASE_LABELS[phase.phase] || phase.message}
            </p>
            {phase.phase !== "done" && phase.phase !== "error" && (
              <p className="text-xs text-muted-foreground">{phase.message}</p>
            )}
          </div>
          {phase.phase === "done" && scores && (
            <span className={`ml-auto text-sm font-semibold capitalize ${concernColor}`}>
              {concernLevel} concern
            </span>
          )}
        </div>
      )}

      {/* Streaming text */}
      {streamText && (
        <div
          ref={textRef}
          className="rounded-xl border border-border bg-gray-50 dark:bg-gray-900 p-4 max-h-72 overflow-y-auto"
        >
          <div className="flex items-center gap-2 mb-2">
            <Cpu className="h-4 w-4 text-blue-500" />
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Live analysis
            </p>
          </div>
          <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap font-mono text-xs">
            {streamText}
            {phase.phase === "analysing" && (
              <span className="inline-block w-2 h-4 bg-blue-500 animate-pulse ml-0.5 align-text-bottom" />
            )}
          </p>
        </div>
      )}

      {/* Protocol alerts — surface immediately as detected */}
      {protocols.length > 0 && (
        <div className="space-y-2">
          {protocols.map(p => (
            <div
              key={p.protocol_key}
              className={`rounded-lg border-l-4 p-3 space-y-1
                ${p.urgency === "critical"
                  ? "border-red-500 bg-red-50 dark:bg-red-950/20"
                  : p.urgency === "high"
                    ? "border-orange-400 bg-orange-50 dark:bg-orange-950/20"
                    : "border-yellow-400 bg-yellow-50 dark:bg-yellow-950/20"
                }`}
            >
              <div className="flex items-center gap-2">
                <ShieldAlert className={`h-4 w-4 flex-shrink-0 ${
                  p.urgency === "critical" ? "text-red-500"
                    : p.urgency === "high" ? "text-orange-400" : "text-yellow-500"
                }`} />
                <span className="text-sm font-bold text-foreground">{p.protocol_name}</span>
                <span className={`ml-auto text-xs font-semibold uppercase rounded px-1.5 py-0.5
                  ${p.urgency === "critical"
                    ? "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300"
                    : p.urgency === "high"
                      ? "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300"
                      : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300"
                  }`}>
                  {p.urgency}
                </span>
              </div>
              <p className="text-xs text-foreground pl-6">{p.headline}</p>
              {p.immediate_action && (
                <p className="text-xs font-semibold text-foreground pl-6">
                  → {p.immediate_action}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Scores summary on completion */}
      {scores && phase.phase === "done" && (
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: "Perfusion",  value: scores.skin_colour_change, max: 3, urgent: true },
            { label: "Swelling",   value: scores.swelling_severity,  max: 3, urgent: false },
            { label: "Infection",  value: scores.infection_signal,   max: 3, urgent: true },
          ].map(({ label, value, max, urgent }) => (
            <div key={label} className="rounded-lg border border-border p-2.5 text-center">
              <p className="text-xs text-muted-foreground mb-1">{label}</p>
              <p className={`text-lg font-bold ${
                value === null ? "text-muted-foreground"
                  : urgent && (value ?? 0) >= 2 ? "text-red-500"
                  : (value ?? 0) >= 2 ? "text-orange-400"
                  : (value ?? 0) === 1 ? "text-yellow-500"
                  : "text-green-500"
              }`}>
                {value ?? "–"}<span className="text-xs text-muted-foreground font-normal">/{max}</span>
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
*/
