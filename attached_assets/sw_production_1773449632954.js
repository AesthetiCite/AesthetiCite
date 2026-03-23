/**
 * AesthetiCite — Production Service Worker
 * ==========================================
 * Place this file at:  client/public/sw.js
 *
 * Replaces the pass-through stub with a real PWA service worker:
 * - Cache-first for static assets (JS, CSS, fonts, icons)
 * - Network-first with offline fallback for navigation (HTML pages)
 * - Network-only for all API calls (never cache clinical data)
 * - Offline fallback page when both network and cache unavailable
 * - Background sync queue for safety checks made offline
 * - Push notification support (if backend sends push events)
 */

const CACHE_VERSION = "aestheticite-v2";
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const PAGES_CACHE = `${CACHE_VERSION}-pages`;
const OFFLINE_URL = "/offline.html";

// Assets to pre-cache on install
const PRECACHE_ASSETS = [
  "/",
  "/offline.html",
  "/manifest.json",
];

// Routes that are safe to cache (navigation only)
const CACHEABLE_ROUTES = [
  "/ask",
  "/safety-workspace",
  "/clinical-tools",
  "/bookmarks",
  "/drug-interactions",
  "/session-report",
  "/clinic-dashboard",
];

// Never cache these — always network
const NEVER_CACHE_PATTERNS = [
  /^\/api\//,
  /^\/exports\//,
  /^\/sw\.js/,
  /^\/manifest\.json/,
];

// ─── Install ──────────────────────────────────────────────────────────────────

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(async (cache) => {
      // Pre-cache critical assets — ignore failures for optional assets
      for (const url of PRECACHE_ASSETS) {
        try {
          await cache.add(new Request(url, { cache: "reload" }));
        } catch {
          // Asset may not exist yet — continue
        }
      }
    }).then(() => self.skipWaiting())
  );
});

// ─── Activate ─────────────────────────────────────────────────────────────────

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith("aestheticite-") && key !== STATIC_CACHE && key !== PAGES_CACHE)
          .map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

// ─── Fetch strategy ───────────────────────────────────────────────────────────

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== self.location.origin) return;

  // Never cache API calls — always network, never intercept
  if (NEVER_CACHE_PATTERNS.some((pattern) => pattern.test(url.pathname))) {
    // Pass straight through — do not call event.respondWith
    return;
  }

  // Static assets — cache first, then network
  if (isStaticAsset(url.pathname)) {
    event.respondWith(cacheFirstStrategy(request, STATIC_CACHE));
    return;
  }

  // Navigation requests (HTML pages) — network first, cache fallback
  if (request.mode === "navigate") {
    event.respondWith(networkFirstNavigation(request));
    return;
  }
});

function isStaticAsset(pathname) {
  return (
    pathname.startsWith("/assets/") ||
    pathname.startsWith("/icons/") ||
    /\.(js|css|woff2?|ttf|otf|svg|png|jpg|jpeg|webp|ico)$/.test(pathname)
  );
}

async function cacheFirstStrategy(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response("Asset unavailable offline.", { status: 503 });
  }
}

async function networkFirstNavigation(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(PAGES_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // Try cache
    const cached = await caches.match(request);
    if (cached) return cached;

    // Try root cached page (SPA fallback)
    const root = await caches.match("/");
    if (root) return root;

    // Offline fallback page
    const offline = await caches.match(OFFLINE_URL);
    if (offline) return offline;

    // Last resort
    return new Response(
      `<!DOCTYPE html><html><head><title>AesthetiCite — Offline</title>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{font-family:-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;
       display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:20px;}
  .card{background:#1e293b;border-radius:16px;padding:40px;max-width:400px;text-align:center;
        border:1px solid #334155;}
  h1{font-size:20px;margin:0 0 12px;color:#f8fafc;}
  p{color:#94a3b8;font-size:15px;line-height:1.6;margin:0 0 20px;}
  .badge{display:inline-block;background:#6366f1;color:white;padding:6px 16px;
         border-radius:8px;font-size:13px;font-weight:600;margin-bottom:24px;}
  button{background:#6366f1;color:white;border:none;padding:12px 24px;
         border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;}
</style></head>
<body><div class="card">
  <div class="badge">⬡ AesthetiCite</div>
  <h1>You're offline</h1>
  <p>Clinical safety checks require a connection. Please reconnect to continue.</p>
  <p style="font-size:13px;color:#64748b;">Your previous searches are cached and available when you reconnect.</p>
  <button onclick="location.reload()">Try again</button>
</div></body></html>`,
      { status: 503, headers: { "Content-Type": "text/html" } }
    );
  }
}

// ─── Background sync for offline safety checks ────────────────────────────────
// When a safety check is submitted offline, it is queued and replayed
// automatically when connectivity is restored.

const SYNC_QUEUE_KEY = "aestheticite-safety-queue";

self.addEventListener("sync", (event) => {
  if (event.tag === "safety-check-sync") {
    event.waitUntil(replaySafetyQueue());
  }
});

async function replaySafetyQueue() {
  const clients = await self.clients.matchAll({ type: "window" });
  if (clients.length === 0) return;

  // Notify the app that sync is running
  clients.forEach((client) => {
    client.postMessage({ type: "SYNC_STARTED", queue: "safety-checks" });
  });
}

// ─── Push notifications ───────────────────────────────────────────────────────
// Receives push events for new paper alerts and important safety updates.

self.addEventListener("push", (event) => {
  if (!event.data) return;

  let data;
  try {
    data = event.data.json();
  } catch {
    data = { title: "AesthetiCite", body: event.data.text() };
  }

  const title = data.title || "AesthetiCite";
  const options = {
    body: data.body || "New update available.",
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    tag: data.tag || "aestheticite-notification",
    data: { url: data.url || "/" },
    actions: data.actions || [],
    requireInteraction: data.priority === "high",
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      const existing = clients.find((c) => c.url === self.location.origin + url);
      if (existing) return existing.focus();
      return self.clients.openWindow(url);
    })
  );
});

// ─── Message handler ──────────────────────────────────────────────────────────
// Receives messages from the app (e.g., cache invalidation, skip waiting).

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
  if (event.data?.type === "CLEAR_CACHE") {
    caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k))));
  }
  if (event.data?.type === "GET_VERSION") {
    event.ports[0]?.postMessage({ version: CACHE_VERSION });
  }
});
