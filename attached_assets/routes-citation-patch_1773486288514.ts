/**
 * ROUTES.TS — CITATION SAFETY PATCH
 * ─────────────────────────────────────────────────────────────────────
 * File: server/routes.ts
 *
 * Four surgical changes. Apply in order.
 * Each block is labelled FIND → REPLACE.
 * No other changes needed.
 */

// ═══════════════════════════════════════════════════════════════════════
// CHANGE 1 — Add sanitizer utility
// WHERE: Paste immediately after imports, before PYTHON_API_BASE const
// ═══════════════════════════════════════════════════════════════════════

/*
// ─── Citation Sanitizer ────────────────────────────────────────────────────

type EvidenceItem = {
  id?: string; source_id?: string; chunk_id?: string; doc_id?: string;
  title?: string; source?: string; locator?: string;
  page?: number | string; section?: string;
  snippet?: string; quote?: string; url?: string;
}
type CitationItem = {
  id: string; title?: string; source?: string;
  locator?: string; snippet?: string; url?: string;
}

function normalizeCitationId(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const s = v.trim();
  return s.length ? s : null;
}
function getEvidenceId(item: EvidenceItem, index: number): string {
  return (normalizeCitationId(item.id) || normalizeCitationId(item.source_id) ||
    normalizeCitationId(item.chunk_id) || normalizeCitationId(item.doc_id) ||
    `src_${index + 1}`)!;
}
function evidenceToCitation(item: EvidenceItem, index: number): CitationItem {
  const id = getEvidenceId(item, index);
  const locator = item.locator ||
    (item.page !== undefined ? `Page ${item.page}` : undefined) || item.section;
  return { id, title: item.title || item.source || `Source ${index + 1}`,
    source: item.source, locator, snippet: item.snippet || item.quote, url: item.url };
}
function stripInvalidInlineCitations(answer: string, validIds: Set<string>): string {
  if (!answer) return answer;
  return answer
    .replace(/\[([^\[\]]+)\]/g, (full, rawId) => validIds.has(String(rawId).trim()) ? full : "")
    .replace(/【([^】]+)】/g, (full, rawId) => validIds.has(String(rawId).trim()) ? full : "")
    .replace(/\[\^([^\]]+)\]/g, (full, rawId) => validIds.has(String(rawId).trim()) ? full : "")
    .replace(/[ \t]+(\n|$)/g, "$1").replace(/\n{3,}/g, "\n\n").trim();
}
function sanitizeGroundedResponse(payload: any) {
  const rawEvidence: EvidenceItem[] =
    Array.isArray(payload?.evidence) ? payload.evidence :
    Array.isArray(payload?.sources) ? payload.sources :
    Array.isArray(payload?.retrieved_chunks) ? payload.retrieved_chunks : [];
  const citations = rawEvidence.map(evidenceToCitation);
  const validIds = new Set(citations.map((c) => c.id));
  const answer = typeof payload?.answer === "string" ? payload.answer :
    typeof payload?.response === "string" ? payload.response :
    typeof payload?.text === "string" ? payload.text : "";
  return { ...payload,
    answer: stripInvalidInlineCitations(answer, validIds),
    citations, evidence: rawEvidence,
    citation_mode: "server-validated", citations_grounded: citations.length > 0 };
}
function sanitizeGroundedResponseStrict(payload: any) {
  const s = sanitizeGroundedResponse(payload);
  if (!s.citations || s.citations.length === 0) {
    return { ...s, citations: [], citations_grounded: false,
      evidence_warning: "No grounded evidence retrieved. Citations suppressed." };
  }
  return s;
}

// ─── Stream-safe proxy ─────────────────────────────────────────────────────

async function proxyStreamSafe(fastApiUrl: string, req: Request, res: Response) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (req.headers.authorization)        headers["Authorization"]      = req.headers.authorization as string;
  if (req.headers["x-api-key"])         headers["X-API-Key"]          = req.headers["x-api-key"] as string;
  if (req.headers["x-admin-api-key"])   headers["x-admin-api-key"]    = req.headers["x-admin-api-key"] as string;
  if (req.headers["x-partner-session"]) headers["X-Partner-Session"]  = req.headers["x-partner-session"] as string;

  const upstream = await fetch(fastApiUrl, {
    method: req.method, headers,
    body: req.method !== "GET" && req.body ? JSON.stringify(req.body) : undefined,
  });

  if (!upstream.body) { res.status(502).json({ error: "No stream body" }); return; }

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");

  const reader = (upstream.body as any).getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) { res.write(line + "\n"); continue; }
      const raw = line.slice(6).trim();
      if (raw === "[DONE]") { res.write("data: [DONE]\n\n"); res.end(); return; }
      try {
        const parsed = JSON.parse(raw);
        // Intercept citation/meta events — rebuild from evidence only
        if (parsed?.type === "citations" || parsed?.type === "meta" ||
            parsed?.answer || parsed?.response || parsed?.text) {
          res.write(`data: ${JSON.stringify(sanitizeGroundedResponse(parsed))}\n\n`);
        } else {
          res.write(`data: ${JSON.stringify(parsed)}\n\n`);
        }
      } catch { res.write(line + "\n"); }
    }
  }
  res.end();
}
*/


// ═══════════════════════════════════════════════════════════════════════
// CHANGE 2 — Delete generateCitations() and generateRelatedQuestions()
// WHERE: Lines ~162–215 in routes.ts
//
// FIND and DELETE this entire function:
//
//   function generateCitations(content: string): Citation[] {
//     ...
//   }
//
// REPLACE WITH:
//
//   // generateCitations() removed — citations must come from retrieved evidence only
//
// Also find any calls to generateCitations() in route handlers:
//
//   FIND:   const citations = generateCitations(content)
//   REPLACE: const citations: CitationItem[] = []
//
// ═══════════════════════════════════════════════════════════════════════


// ═══════════════════════════════════════════════════════════════════════
// CHANGE 3 — Apply sanitizer to non-stream AI answer routes
// WHERE: The proxyToFastAPI function signature (~line 368)
//
// FIND:
//   async function proxyToFastAPI(
//     req: Request,
//     res: Response,
//     path: string,
//   ) {
//
// REPLACE WITH:
//   async function proxyToFastAPI(
//     req: Request,
//     res: Response,
//     path: string,
//     sanitize = false,   // ← add this
//   ) {
//
// Then inside the function, find:
//   const data = await response.json();
//   res.status(response.status).json(data);
//
// REPLACE WITH:
//   const data = await response.json();
//   const output = sanitize ? sanitizeGroundedResponseStrict(data) : data;
//   res.status(response.status).json(output);
//
// Then update the two AI answer routes:
//   FIND:   app.post("/api/ask",    (req, res) => proxyToFastAPI(req, res, "/ask"));
//   REPLACE: app.post("/api/ask",    (req, res) => proxyToFastAPI(req, res, "/ask",    true));
//
//   FIND:   app.post("/api/ask_oe", (req, res) => proxyToFastAPI(req, res, "/ask_oe"));
//   REPLACE: app.post("/api/ask_oe", (req, res) => proxyToFastAPI(req, res, "/ask_oe", true));
//
// ═══════════════════════════════════════════════════════════════════════


// ═══════════════════════════════════════════════════════════════════════
// CHANGE 4 — Replace stream routes with proxyStreamSafe
// WHERE: The three stream route handlers
//
// FIND:
//   app.post("/api/search", async (req, res) => {
//     try {
//       const { query } = searchQuerySchema.parse(req.body);
//       await storage.addSearchHistory(query);
//       res.setHeader("Content-Type", "text/event-stream");
//       ...
//       while (true) {
//         const { done, value } = await reader.read();
//         if (done) break;
//         const chunk = decoder.decode(value, { stream: true });
//         res.write(chunk);   ← unsafe passthrough
//       }
//       res.end();
//
// REPLACE WITH:
//   app.post("/api/search", async (req, res) => {
//     try {
//       const { query } = searchQuerySchema.parse(req.body);
//       await storage.addSearchHistory(query);
//     } catch { /* non-fatal */ }
//     await proxyStreamSafe(`${PYTHON_API_BASE}/v2/stream`, req, res);
//   });
//
// ─────────────────────────────────────────────────────────────────────
//
// FIND:
//   app.post("/api/v2/stream", async (req, res) => {
//     try {
//       res.setHeader("Content-Type", "text/event-stream");
//       ...
//       while (true) {
//         const { done, value } = await reader.read();
//         if (done) break;
//         const chunk = decoder.decode(value, { stream: true });
//         res.write(chunk);   ← unsafe passthrough
//       }
//       res.end();
//
// REPLACE WITH:
//   app.post("/api/v2/stream", async (req, res) => {
//     await proxyStreamSafe(`${PYTHON_API_BASE}/v2/stream`, req, res);
//   });
//
// ─────────────────────────────────────────────────────────────────────
//
// FIND:
//   app.post("/api/ask/stream", (req, res) => proxyToFastAPI(req, res, "/ask/stream"));
//
// REPLACE WITH:
//   app.post("/api/ask/stream", async (req, res) => {
//     await proxyStreamSafe(`${PYTHON_API_BASE}/ask/stream`, req, res);
//   });
//
// NOTE: Do NOT apply proxyStreamSafe to:
//   /api/ask/visual/stream  ← visual counseling — different event format
//   /api/safety/*           ← structured safety JSON — not citation-bearing
//   /api/growth/*           ← growth engine — not citation-bearing
//   /api/complications/*    ← complication engine — not citation-bearing
//
// ═══════════════════════════════════════════════════════════════════════


// ═══════════════════════════════════════════════════════════════════════
// SUMMARY — After all 4 changes your trust chain is:
//
//   FastAPI (retrieves evidence, generates tokens)
//         ↓
//   proxyStreamSafe (intercepts citation/meta events on streams)
//         ↓
//   sanitizeGroundedResponse (strips inline markers with no backing source)
//         ↓
//   sanitizeGroundedResponseStrict (non-stream: empty evidence = empty citations)
//         ↓
//   Client (only grounded citations reach the browser)
//
// generateCitations() is gone.
// Fake [1], [2] markers cannot reach the client.
// Demo-safe.
// ═══════════════════════════════════════════════════════════════════════

export {}; // keep TypeScript happy if imported as a module
