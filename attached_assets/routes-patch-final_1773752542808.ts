/**
 * AesthetiCite — routes.ts Citation Sanitizer Patch
 * server/routes-patch.ts
 *
 * HOW TO APPLY:
 *
 * STEP A — Paste the SANITIZER BLOCK (below) into routes.ts
 *          immediately after the last import line, before:
 *          const PYTHON_API_BASE = "http://localhost:8000"
 *
 * STEP B — Replace the three stream routes with STREAM ROUTES (below)
 *
 * STEP C — Update the two AI answer proxy lines with ANSWER ROUTES (below)
 *
 * STEP D — Delete the generateCitations() function (~lines 162-204)
 *          Replace any call to it with: const citations: CitationItem[] = []
 */


// ═══════════════════════════════════════════════════════════════════════════
// STEP A — SANITIZER BLOCK
// Paste this entire block after imports, before PYTHON_API_BASE
// ═══════════════════════════════════════════════════════════════════════════

export const SANITIZER_BLOCK = `
// ─── Citation Sanitizer ──────────────────────────────────────────────────────

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
  const s = v.trim(); return s.length ? s : null;
}
function getEvidenceId(item: EvidenceItem, index: number): string {
  return (normalizeCitationId(item.id) || normalizeCitationId(item.source_id) ||
    normalizeCitationId(item.chunk_id) || normalizeCitationId(item.doc_id) ||
    \`src_\${index + 1}\`)!;
}
function evidenceToCitation(item: EvidenceItem, index: number): CitationItem {
  const id = getEvidenceId(item, index);
  const locator = item.locator ||
    (item.page !== undefined ? \`Page \${item.page}\` : undefined) || item.section;
  return { id, title: item.title || item.source || \`Source \${index + 1}\`,
    source: item.source, locator, snippet: item.snippet || item.quote, url: item.url };
}
function stripInvalidInlineCitations(answer: string, validIds: Set<string>): string {
  if (!answer) return answer;
  return answer
    .replace(/\\[([^\\[\\]]+)\\]/g, (full: string, rawId: string) =>
      validIds.has(String(rawId).trim()) ? full : "")
    .replace(/【([^】]+)】/g, (full: string, rawId: string) =>
      validIds.has(String(rawId).trim()) ? full : "")
    .replace(/\\[\\^([^\\]]+)\\]/g, (full: string, rawId: string) =>
      validIds.has(String(rawId).trim()) ? full : "")
    .replace(/[ \\t]+(\\n|$)/g, "$1").replace(/\\n{3,}/g, "\\n\\n").trim();
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
  if (!s.citations || s.citations.length === 0)
    return { ...s, citations: [], citations_grounded: false,
      evidence_warning: "No grounded evidence retrieved. Citations suppressed." };
  return s;
}
async function proxyStreamSafe(fastApiUrl: string, req: Request, res: Response) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (req.headers.authorization)
    headers["Authorization"] = req.headers.authorization as string;
  if (req.headers["x-api-key"])
    headers["X-API-Key"] = req.headers["x-api-key"] as string;
  if (req.headers["x-admin-api-key"])
    headers["x-admin-api-key"] = req.headers["x-admin-api-key"] as string;
  if (req.headers["x-partner-session"])
    headers["X-Partner-Session"] = req.headers["x-partner-session"] as string;

  let upstream: globalThis.Response;
  try {
    upstream = await fetch(fastApiUrl, {
      method: req.method,
      headers,
      body: req.method !== "GET" && req.body ? JSON.stringify(req.body) : undefined,
    });
  } catch (err) {
    res.status(502).json({ error: "Backend unreachable", detail: String(err) });
    return;
  }

  if (!upstream.body) {
    res.status(502).json({ error: "No stream body from backend" });
    return;
  }

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");

  const reader = (upstream.body as any).getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) { res.write(line + "\\n"); continue; }
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") { res.write("data: [DONE]\\n\\n"); res.end(); return; }
        try {
          const parsed = JSON.parse(raw);
          // Protocol cards pass through unmodified — they use structured EvidenceItem
          // objects already, not inline citation markers
          if (parsed?.type === "protocol_card") {
            res.write(\`data: \${JSON.stringify(parsed)}\\n\\n\`);
          } else if (
            parsed?.type === "citations" ||
            parsed?.type === "meta" ||
            parsed?.answer ||
            parsed?.response ||
            parsed?.text
          ) {
            res.write(\`data: \${JSON.stringify(sanitizeGroundedResponse(parsed))}\\n\\n\`);
          } else {
            res.write(\`data: \${JSON.stringify(parsed)}\\n\\n\`);
          }
        } catch { res.write(line + "\\n"); }
      }
    }
  } catch (err) {
    if (!res.writableEnded) {
      res.write(\`data: \${JSON.stringify({ type: "error", message: "Stream interrupted" })}\\n\\n\`);
    }
  }
  if (!res.writableEnded) res.end();
}
// ─── End Citation Sanitizer ──────────────────────────────────────────────────
`;


// ═══════════════════════════════════════════════════════════════════════════
// STEP B — STREAM ROUTES
// Replace the three stream route handlers in routes.ts with these exact lines
// ═══════════════════════════════════════════════════════════════════════════

export const STREAM_ROUTES = `
  // /api/search — safe stream
  app.post("/api/search", async (req: Request, res: Response) => {
    try {
      const { query } = searchQuerySchema.parse(req.body);
      await storage.addSearchHistory(query);
    } catch { /* non-fatal — history logging failure must not block search */ }
    await proxyStreamSafe(\`\${PYTHON_API_BASE}/v2/stream\`, req, res);
  });

  // /api/v2/stream — safe stream
  app.post("/api/v2/stream", async (req: Request, res: Response) => {
    await proxyStreamSafe(\`\${PYTHON_API_BASE}/v2/stream\`, req, res);
  });

  // /api/ask/stream — safe stream
  app.post("/api/ask/stream", async (req: Request, res: Response) => {
    await proxyStreamSafe(\`\${PYTHON_API_BASE}/ask/stream\`, req, res);
  });

  // /api/ask/visual/stream — NOT sanitized (visual counseling, different event format)
  // Leave this one exactly as it was.
`;


// ═══════════════════════════════════════════════════════════════════════════
// STEP C — ANSWER ROUTES
// Replace the two AI answer proxy lines (non-streaming) with these
// ═══════════════════════════════════════════════════════════════════════════

export const ANSWER_ROUTES = `
  // REPLACE these two lines:
  //   app.post("/api/ask",    (req, res) => proxyToFastAPI(req, res, "/ask"));
  //   app.post("/api/ask_oe", (req, res) => proxyToFastAPI(req, res, "/ask_oe"));
  //
  // WITH:
  app.post("/api/ask",    (req: Request, res: Response) => proxyToFastAPI(req, res, "/ask",    true));
  app.post("/api/ask_oe", (req: Request, res: Response) => proxyToFastAPI(req, res, "/ask_oe", true));

  // Also update proxyToFastAPI signature to accept sanitize param:
  //
  // async function proxyToFastAPI(
  //   req: Request,
  //   res: Response,
  //   path: string,
  //   sanitize = false,   ← add this
  // ) {
  //
  // And inside the function, replace:
  //   const data = await response.json();
  //   res.status(response.status).json(data);
  //
  // WITH:
  //   const text = await response.text();
  //   let data: any;
  //   try { data = JSON.parse(text); }
  //   catch { data = { detail: text.slice(0, 400) }; }
  //   const output = sanitize ? sanitizeGroundedResponseStrict(data) : data;
  //   res.status(response.status).json(output);
`;

export {};
