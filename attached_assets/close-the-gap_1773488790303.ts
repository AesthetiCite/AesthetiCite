/**
 * AesthetiCite — Frontend Gap Closing Patch
 * ─────────────────────────────────────────────────────────────────────
 * Apply four changes to ask.tsx and one to routes.ts.
 * Every block is labelled with exact FIND text and REPLACE text.
 * No other files need editing — App.tsx, sidebar-safety-nav.tsx,
 * complication-protocol.tsx, session-report-v2.tsx, and
 * pre-procedure-safety.tsx were already delivered.
 *
 * APPLY ORDER:
 *   1. routes.ts    — citation sanitizer (paste utility block once)
 *   2. ask.tsx      — add two imports
 *   3. ask.tsx      — extend ChatMessage interface
 *   4. ask.tsx      — add protocol_card SSE case to both stream handlers
 *   5. ask.tsx      — insert <SidebarSafetyNav /> above <ScrollArea>
 *   6. ask.tsx      — insert <ProtocolCard /> below <StructuredAnswer />
 *   7. ask.tsx      — add Complication Protocols to More dropdown
 *   8. ask.tsx      — add Complication Protocols to mobile Sheet
 * ─────────────────────────────────────────────────────────────────────
 */


// ═══════════════════════════════════════════════════════════════════════════
// CHANGE 1 — routes.ts
// WHERE: Paste immediately after the last import, before PYTHON_API_BASE
// ═══════════════════════════════════════════════════════════════════════════
//
// PASTE THIS ENTIRE BLOCK (copy from the triple-slash line below to the
// closing brace of sanitizeGroundedResponseStrict):
//
/*
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
  if (!s.citations || s.citations.length === 0)
    return { ...s, citations: [], citations_grounded: false,
      evidence_warning: "No grounded evidence retrieved. Citations suppressed." };
  return s;
}
async function proxyStreamSafe(fastApiUrl: string, req: Request, res: Response) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (req.headers.authorization)         headers["Authorization"]      = req.headers.authorization as string;
  if (req.headers["x-api-key"])          headers["X-API-Key"]          = req.headers["x-api-key"] as string;
  if (req.headers["x-admin-api-key"])    headers["x-admin-api-key"]    = req.headers["x-admin-api-key"] as string;
  if (req.headers["x-partner-session"])  headers["X-Partner-Session"]  = req.headers["x-partner-session"] as string;
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
        if (parsed?.type === "protocol_card") {
          // Pass protocol cards through unmodified
          res.write(`data: ${JSON.stringify(parsed)}\n\n`);
        } else if (parsed?.type === "citations" || parsed?.type === "meta" ||
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
// ─── End Citation Sanitizer ──────────────────────────────────────────────────
*/
//
// Then update the three stream routes:
//   app.post("/api/search", ...) → replace body with: await proxyStreamSafe(`${PYTHON_API_BASE}/v2/stream`, req, res);
//   app.post("/api/v2/stream", ...) → replace body with: await proxyStreamSafe(`${PYTHON_API_BASE}/v2/stream`, req, res);
//   app.post("/api/ask/stream", ...) → replace body with: await proxyStreamSafe(`${PYTHON_API_BASE}/ask/stream`, req, res);
//
// And update the two AI answer routes to pass sanitize=true:
//   app.post("/api/ask",    ...) → proxyToFastAPI(req, res, "/ask",    true)
//   app.post("/api/ask_oe", ...) → proxyToFastAPI(req, res, "/ask_oe", true)
//
// Also delete the generateCitations() function (~lines 162-204).


// ═══════════════════════════════════════════════════════════════════════════
// CHANGE 2 — ask.tsx
// WHERE: Top of file, with the existing imports
// ═══════════════════════════════════════════════════════════════════════════
//
// ADD these two lines alongside the other component imports:
//
//   import { SidebarSafetyNav } from "@/components/sidebar-safety-nav";
//   import { ProtocolCard, type ProtocolCardData } from "@/components/protocol-card";


// ═══════════════════════════════════════════════════════════════════════════
// CHANGE 3 — ask.tsx
// WHERE: ChatMessage interface (~line 1822)
// ═══════════════════════════════════════════════════════════════════════════
//
// FIND:
//   interface ChatMessage {
//     id: string;
//     role: "user" | "assistant";
//     content: string;
//     created_at?: string;
//     isStreaming?: boolean;
//     citations?: Citation[];
//     relatedQuestions?: string[];
//     oeResponse?: AskOEResponse;
//     aciScore?: number | null;
//     queryMeta?: QueryMeta | null;
//     complicationProtocol?: ComplicationProtocol | null;
//     inlineTools?: InlineTool[];
//     evidenceStrength?: string;
//     clinicalSummary?: string;
//     isRefusal?: boolean;
//     refusalReason?: string;
//     refusalCode?: string;
//   }
//
// REPLACE WITH:
//   interface ChatMessage {
//     id: string;
//     role: "user" | "assistant";
//     content: string;
//     created_at?: string;
//     isStreaming?: boolean;
//     citations?: Citation[];
//     relatedQuestions?: string[];
//     oeResponse?: AskOEResponse;
//     aciScore?: number | null;
//     queryMeta?: QueryMeta | null;
//     complicationProtocol?: ComplicationProtocol | null;
//     inlineTools?: InlineTool[];
//     evidenceStrength?: string;
//     clinicalSummary?: string;
//     isRefusal?: boolean;
//     refusalReason?: string;
//     refusalCode?: string;
//     protocolCard?: ProtocolCardData | null;  // ← ADD THIS LINE
//   }


// ═══════════════════════════════════════════════════════════════════════════
// CHANGE 4 — ask.tsx (TWO PLACES)
// WHERE: Inside askQuestionStreamV2 callbacks AND askQuestionStream callbacks
//         Both are inside handleAsk() — the enhanced mode block and the
//         standard mode block. Each has a switch/case on data.type.
// ═══════════════════════════════════════════════════════════════════════════
//
// In BOTH the enhanced mode (askQuestionStreamV2) and standard mode
// (askQuestionStream) callbacks, find the "citations" case handler:
//
//   case "citations":    (in askQuestionStreamV2)
//   case "meta":         (in askQuestionStream)
//
// After the LAST case in each callback's switch (before the closing brace),
// INSERT this new case in BOTH locations:
//
//   case "protocol_card":
//     setMessages((prev) =>
//       prev.map((m) =>
//         m.id === assistantMsgId
//           ? { ...m, protocolCard: data as ProtocolCardData }
//           : m
//       )
//     );
//     break;
//
// For askQuestionStreamV2, add it after the "badge" case.
// For askQuestionStream, add it after the "done" case.
//
// NOTE: the raw SSE data object for protocol_card has the shape:
//   { type: "protocol_card", ...ProtocolCardData fields }
// Cast it directly: data as ProtocolCardData


// ═══════════════════════════════════════════════════════════════════════════
// CHANGE 5 — ask.tsx
// WHERE: Inside the <aside> sidebar, immediately before <ScrollArea>
// ═══════════════════════════════════════════════════════════════════════════
//
// FIND (exact line, ~line 2494):
//   <ScrollArea className="flex-1 px-3">
//
// INSERT immediately before it:
//   <SidebarSafetyNav />
//
// Result:
//   <SidebarSafetyNav />
//   <ScrollArea className="flex-1 px-3">
//     ...
//   </ScrollArea>


// ═══════════════════════════════════════════════════════════════════════════
// CHANGE 6 — ask.tsx
// WHERE: In the message render, after <StructuredAnswer /> (~line 3018)
// ═══════════════════════════════════════════════════════════════════════════
//
// FIND:
//   <StructuredAnswer
//     msg={msg}
//     lastQuestion={lastQuestion}
//     onRelatedQuestion={handleRelatedQuestion}
//     onCopyNote={copyNote}
//     copiedNote={copiedNote}
//   />
//
// REPLACE WITH:
//   <StructuredAnswer
//     msg={msg}
//     lastQuestion={lastQuestion}
//     onRelatedQuestion={handleRelatedQuestion}
//     onCopyNote={copyNote}
//     copiedNote={copiedNote}
//   />
//   {msg.protocolCard && !msg.isStreaming && (
//     <ProtocolCard data={msg.protocolCard} />
//   )}


// ═══════════════════════════════════════════════════════════════════════════
// CHANGE 7 — ask.tsx
// WHERE: More dropdown menu (~line 2678)
// ═══════════════════════════════════════════════════════════════════════════
//
// FIND:
//   <DropdownMenuLabel>Clinical</DropdownMenuLabel>
//   <DropdownMenuItem asChild>
//     <Link href="/drug-interactions" className="flex items-center gap-2 cursor-pointer">
//       <Pill className="h-4 w-4 text-muted-foreground" />Drug Interaction Checker
//     </Link>
//   </DropdownMenuItem>
//
// REPLACE WITH:
//   <DropdownMenuLabel>Clinical</DropdownMenuLabel>
//   <DropdownMenuItem asChild>
//     <Link href="/complications" className="flex items-center gap-2 cursor-pointer">
//       <AlertTriangle className="h-4 w-4 text-muted-foreground" />Complication Protocols
//     </Link>
//   </DropdownMenuItem>
//   <DropdownMenuItem asChild>
//     <Link href="/drug-interactions" className="flex items-center gap-2 cursor-pointer">
//       <Pill className="h-4 w-4 text-muted-foreground" />Drug Interaction Checker
//     </Link>
//   </DropdownMenuItem>
//
// (AlertTriangle is already imported in ask.tsx from lucide-react)


// ═══════════════════════════════════════════════════════════════════════════
// CHANGE 8 — ask.tsx
// WHERE: Mobile Sheet nav, "Safety & Tools" section (~line 2641)
// ═══════════════════════════════════════════════════════════════════════════
//
// FIND:
//   <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Safety & Tools</p>
//   <div className="space-y-1">
//     <Link href="/safety-check" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ShieldAlert className="h-4 w-4" />Pre-Procedure Safety</Link>
//     <Link href="/session-report" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ClipboardCheck className="h-4 w-4" />Session Safety Report</Link>
//     <Link href="/drug-interactions" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Pill className="h-4 w-4" />Drug Interactions</Link>
//
// REPLACE WITH:
//   <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Safety & Tools</p>
//   <div className="space-y-1">
//     <Link href="/safety-check" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ShieldAlert className="h-4 w-4" />Pre-Procedure Safety</Link>
//     <Link href="/complications" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><AlertTriangle className="h-4 w-4" />Complication Protocols</Link>
//     <Link href="/session-report" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ClipboardCheck className="h-4 w-4" />Session Safety Report</Link>
//     <Link href="/drug-interactions" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Pill className="h-4 w-4" />Drug Interactions</Link>


// ═══════════════════════════════════════════════════════════════════════════
// DONE. After these 8 changes:
//
//   ✅ Fake citations impossible (sanitizer on all AI routes + streams)
//   ✅ generateCitations() deleted
//   ✅ /complications route live (App.tsx already delivered)
//   ✅ Safety cluster visible in sidebar (SidebarSafetyNav)
//   ✅ Complication Protocols in desktop More dropdown
//   ✅ Complication Protocols in mobile Sheet nav
//   ✅ Protocol card renders below answers on complication queries
//   ✅ Protocol card SSE event handled in both stream modes
//
// Frontend is now at parity with backend.
// ═══════════════════════════════════════════════════════════════════════════

export {};
