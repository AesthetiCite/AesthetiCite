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
