/**
 * AesthetiCite — server/routes_additions.ts
 * ==========================================
 * Add this entire block to server/routes.ts, inside registerRoutes(),
 * just before the final  return httpServer;  line.
 *
 * Also add at the top of routes.ts:
 *   import rateLimit from "express-rate-limit";
 *
 * And add to package.json dependencies:
 *   "express-rate-limit": "^7.0.0"
 *   "@types/express-rate-limit": "^6.0.0"  (devDependencies)
 *
 * Run:  npm install express-rate-limit
 */

import type { Express, Request, Response, NextFunction } from "express";
import rateLimit from "express-rate-limit";

// ─── Per-user rate limiting ───────────────────────────────────────────────────
// Limits each authenticated user (by JWT sub) or IP to 60 req/min on search
// and 30 req/min on safety checks. Prevents single-user OpenAI budget exhaustion.

const extractUserId = (req: Request): string => {
  const auth = req.headers.authorization || "";
  if (auth.startsWith("Bearer ")) {
    try {
      // Decode JWT payload without verifying (verification happens in Python)
      const payload = JSON.parse(
        Buffer.from(auth.slice(7).split(".")[1], "base64url").toString("utf8")
      );
      return payload.sub || req.ip || "anon";
    } catch {
      return req.ip || "anon";
    }
  }
  return req.ip || "anon";
};

const searchLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 60,
  keyGenerator: extractUserId,
  standardHeaders: true,
  legacyHeaders: false,
  message: { detail: "Too many requests. Please wait a moment before searching again." },
  skip: (req) => req.method === "OPTIONS",
});

const safetyLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 30,
  keyGenerator: extractUserId,
  standardHeaders: true,
  legacyHeaders: false,
  message: { detail: "Safety check rate limit reached. Please wait before running another check." },
  skip: (req) => req.method === "OPTIONS",
});

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,  // 15 minutes
  max: 10,
  keyGenerator: (req) => req.ip || "anon",
  standardHeaders: true,
  legacyHeaders: false,
  message: { detail: "Too many authentication attempts. Please try again in 15 minutes." },
});

// ─── Apply rate limiters to existing routes ───────────────────────────────────
// Add these lines inside registerRoutes(), before the existing route declarations:
//
//   app.use("/api/search", searchLimiter);
//   app.use("/api/ask", searchLimiter);
//   app.use("/api/v2/stream", searchLimiter);
//   app.use("/api/safety", safetyLimiter);
//   app.use("/api/auth/login", authLimiter);
//   app.use("/api/auth/register", authLimiter);
//   app.use("/api/ops/auth/forgot-password", authLimiter);
//   app.use("/api/ops/auth/reset-password", authLimiter);

// ─── Operational routes ───────────────────────────────────────────────────────

export function registerOperationalRoutes(app: Express) {
  // Rate limiters
  app.use("/api/search", searchLimiter);
  app.use("/api/ask", searchLimiter);
  app.use("/api/v2/stream", searchLimiter);
  app.use("/api/safety", safetyLimiter);
  app.use("/api/auth/login", authLimiter);
  app.use("/api/auth/register", authLimiter);
  app.use("/api/ops/auth/forgot-password", authLimiter);
  app.use("/api/ops/auth/reset-password", authLimiter);

  // ─── Module 6: full health check ─────────────────────────────────────────
  app.get("/api/ops/health/full",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/health/full"));

  // ─── Module 7: complete auth flow ────────────────────────────────────────
  app.post("/api/ops/auth/forgot-password",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/auth/forgot-password"));
  app.post("/api/ops/auth/reset-password",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/auth/reset-password"));
  app.post("/api/ops/auth/send-verification",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/auth/send-verification"));
  app.post("/api/ops/auth/verify-email",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/auth/verify-email"));
  app.get("/api/ops/auth/verification-status",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/auth/verification-status"));

  // ─── Module 3: PostgreSQL case logging ───────────────────────────────────
  app.post("/api/ops/cases/log",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/cases/log"));
  app.get("/api/ops/cases",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/cases"));

  // ─── Module 4: PDF storage ────────────────────────────────────────────────
  app.get("/api/ops/exports/url/:filename",
    (req, res) => proxyToFastAPI(req, res, `/api/ops/exports/url/${req.params.filename}`));

  // ─── Module 5: dashboard logging ─────────────────────────────────────────
  app.post("/api/ops/dashboard/log-query",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/dashboard/log-query"));
  app.get("/api/ops/dashboard/clinic",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/dashboard/clinic"));

  // ─── Module 1: ingestion pipeline ────────────────────────────────────────
  app.post("/api/ops/ingest/start",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/ingest/start"));
  app.get("/api/ops/ingest/status",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/ingest/status"));
  app.post("/api/ops/ingest/stop",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/ingest/stop"));

  // ─── Module 2: evidence retrieval test ───────────────────────────────────
  app.get("/api/ops/evidence/test",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/evidence/test"));

  // ─── Safety engine v2 ────────────────────────────────────────────────────
  app.post("/api/safety/v2/preprocedure-check",
    safetyLimiter,
    (req, res) => proxyToFastAPI(req, res, "/api/safety/v2/preprocedure-check"));
  app.post("/api/safety/v2/preprocedure-check/export-pdf",
    (req, res) => proxyToFastAPI(req, res, "/api/safety/v2/preprocedure-check/export-pdf"));
  app.post("/api/safety/v2/complications/protocol",
    (req, res) => proxyToFastAPI(req, res, "/api/safety/v2/complications/protocol"));
  app.get("/api/safety/v2/complications/protocols",
    (req, res) => proxyToFastAPI(req, res, "/api/safety/v2/complications/protocols"));
  app.post("/api/safety/v2/complications/export-pdf",
    (req, res) => proxyToFastAPI(req, res, "/api/safety/v2/complications/export-pdf"));
  app.post("/api/safety/v2/drug-check",
    (req, res) => proxyToFastAPI(req, res, "/api/safety/v2/drug-check"));
  app.post("/api/safety/v2/log-case",
    (req, res) => proxyToFastAPI(req, res, "/api/safety/v2/log-case"));
  app.get("/api/safety/v2/case-log",
    (req, res) => proxyToFastAPI(req, res, "/api/safety/v2/case-log"));
  app.get("/api/safety/v2/onboarding-hint",
    (req, res) => proxyToFastAPI(req, res, "/api/safety/v2/onboarding-hint"));
  app.get("/api/safety/v2/paper-digest/:topic",
    (req, res) => proxyToFastAPI(req, res, `/api/safety/v2/paper-digest/${req.params.topic}`));
  app.post("/api/safety/v2/seed-journals",
    (req, res) => proxyToFastAPI(req, res, "/api/safety/v2/seed-journals"));

  // ─── PWA: real service worker served from public/sw.js ───────────────────
  // The sw_production.js file must be placed at:  client/public/sw.js
  // This route serves it with the correct headers for PWA registration.
  app.get("/sw.js", (req: Request, res: Response) => {
    res.setHeader("Content-Type", "application/javascript; charset=utf-8");
    res.setHeader("Service-Worker-Allowed", "/");
    res.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");
    const swPath = require("path").join(process.cwd(), "client", "public", "sw.js");
    if (require("fs").existsSync(swPath)) {
      res.sendFile(swPath);
    } else {
      // Minimal fallback if sw.js not found
      res.send(`
self.addEventListener('install', e => { self.skipWaiting(); });
self.addEventListener('activate', e => { e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', e => {});
      `.trim());
    }
  });

  // ─── Manifest with correct theme colour ──────────────────────────────────
  app.get("/manifest.json", (_req: Request, res: Response) => {
    res.json({
      name: "AesthetiCite",
      short_name: "AesthetiCite",
      start_url: "/",
      display: "standalone",
      background_color: "#0f172a",
      theme_color: "#6366f1",
      description: "Clinical safety and evidence engine for aesthetic injectables.",
      icons: [
        { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any maskable" },
        { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any maskable" },
      ],
      categories: ["medical", "health"],
      shortcuts: [
        { name: "Safety Check", url: "/safety-workspace", description: "Run pre-procedure safety check" },
        { name: "Complications", url: "/clinical-tools", description: "Complication protocols" },
      ],
    });
  });
}

// ─── Fixed logQueryToClinic for ask.tsx ───────────────────────────────────────
//
// Replace the existing logQueryToClinic function in client/src/pages/ask.tsx
// with this version. Uses JWT token for auth so clinic_id is
// derived server-side from the user's profile — not from localStorage.
//
// FIND this in ask.tsx:
//   function logQueryToClinic(question: string, answerPreview: string, aci: number | null, durationMs: number) {
//     const clinicId = localStorage.getItem("aestheticite_clinic_id") || "";
//     fetch("/api/growth/query-logs", {
//       ...
//     }).catch(() => {});
//   }
//
// REPLACE WITH:
//
// function logQueryToClinic(question: string, aci: number | null, durationMs: number) {
//   const token = getToken();
//   if (!token) return;
//   fetch("/api/ops/dashboard/log-query", {
//     method: "POST",
//     headers: {
//       "Content-Type": "application/json",
//       Authorization: `Bearer ${token}`,
//     },
//     body: JSON.stringify({
//       query_text: question,
//       answer_type: "evidence_search",
//       aci_score: aci ?? undefined,
//       response_time_ms: Math.round(durationMs),
//       domain: "aesthetic_medicine",
//     }),
//   }).catch(() => {});
// }
//
// Also update the two call sites in handleAsk() / handleDone() to match
// the new 3-argument signature:
//   logQueryToClinic(question, aciScore, Date.now() - queryStartTimeRef.current);

// ─── PWA registration for client/src/main.tsx ─────────────────────────────
//
// Add this to client/src/main.tsx (after ReactDOM.createRoot):
//
// if ('serviceWorker' in navigator) {
//   window.addEventListener('load', () => {
//     navigator.serviceWorker.register('/sw.js', { scope: '/' })
//       .then(reg => console.log('[PWA] Service worker registered', reg.scope))
//       .catch(err => console.warn('[PWA] Service worker registration failed', err));
//   });
// }
