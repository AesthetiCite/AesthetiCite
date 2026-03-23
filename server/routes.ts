import type { Express, Request, Response } from "express";
import path from "path";
import fs from "fs";
import rateLimit from "express-rate-limit";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import OpenAI from "openai";
import { searchQuerySchema, type Citation } from "@shared/schema";
import { ZodError } from "zod";
import multer from "multer";
import FormData from "form-data";

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
  return {
    id,
    title: item.title || item.source || `Source ${index + 1}`,
    source: item.source,
    locator,
    snippet: item.snippet || item.quote,
    url: item.url,
  };
}

function stripInvalidInlineCitations(answer: string, validIds: Set<string>): string {
  if (!answer) return answer;
  return answer
    .replace(/\[([^\[\]]+)\]/g, (full, rawId) =>
      validIds.has(String(rawId).trim()) ? full : "")
    .replace(/【([^】]+)】/g, (full, rawId) =>
      validIds.has(String(rawId).trim()) ? full : "")
    .replace(/\[\^([^\]]+)\]/g, (full, rawId) =>
      validIds.has(String(rawId).trim()) ? full : "")
    .replace(/[ \t]+(\n|$)/g, "$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
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

  return {
    ...payload,
    answer: stripInvalidInlineCitations(answer, validIds),
    citations,
    evidence: rawEvidence,
    citation_mode: "server-validated",
    citations_grounded: citations.length > 0,
  };
}

function sanitizeGroundedResponseStrict(payload: any) {
  const sanitized = sanitizeGroundedResponse(payload);
  if (!sanitized.citations || sanitized.citations.length === 0) {
    return {
      ...sanitized,
      citations: [],
      citations_grounded: false,
      evidence_warning: "No grounded evidence retrieved. Citations suppressed.",
    };
  }
  return sanitized;
}

const PYTHON_API_BASE = "http://localhost:8000";

const openai = new OpenAI({
  apiKey: process.env.AI_INTEGRATIONS_OPENAI_API_KEY,
  baseURL: process.env.AI_INTEGRATIONS_OPENAI_BASE_URL,
});

const SYSTEM_PROMPT = `You are AesthetiCite, an AI research assistant that provides evidence-based answers with citations. Your responses should be:

1. COMPREHENSIVE: Provide thorough, well-structured answers that address all aspects of the question
2. EVIDENCE-BASED: Include citations in [1], [2], [3] format throughout your response
3. WELL-ORGANIZED: Use clear paragraphs, bullet points, or numbered lists when appropriate
4. ACCESSIBLE: Explain complex concepts in clear, understandable language
5. BALANCED: Present multiple perspectives when relevant

Format your response as follows:
- Write your main answer with inline citations like [1], [2], etc.
- Use markdown formatting (headers, lists, bold) to structure your response
- Be thorough but concise - aim for 300-500 words for most queries
- End with key takeaways when appropriate

Remember: Every claim should be supported by a citation. Use citation numbers sequentially.`;

// generateCitations() removed — grounded citations only via sanitizeGroundedResponseStrict

function generateRelatedQuestions(query: string): string[] {
  const baseQuestions = [
    `What are the latest research findings on ${query.toLowerCase().replace(/\?/g, '')}?`,
    `What are the risk factors and prevention strategies?`,
    `How do different treatment approaches compare in effectiveness?`,
    `What do clinical guidelines recommend?`,
  ];
  
  return baseQuestions.slice(0, 3);
}

interface EvidenceBadge {
  score: number;
  badge: "High" | "Moderate" | "Low";
  badge_color: "green" | "yellow" | "red";
  types: Record<string, number>;
  why: string;
  unique_sources: number;
}

function computeEvidenceBadge(citations: Citation[]): EvidenceBadge {
  if (!citations || citations.length === 0) {
    return {
      score: 0.1,
      badge: "Low",
      badge_color: "red",
      types: {},
      why: "No sources available",
      unique_sources: 0
    };
  }
  
  const typeWeights: Record<string, number> = {
    "Medical Journal": 0.85,
    "Research Journal": 0.80,
    "Systematic Reviews": 0.95,
    "Database": 0.70,
  };
  
  const typeCounts: Record<string, number> = {};
  let totalWeight = 0;
  let strongest = 0;
  
  for (const citation of citations) {
    const source = citation.source || "Other";
    const weight = typeWeights[source] || 0.50;
    totalWeight += weight;
    strongest = Math.max(strongest, weight);
    typeCounts[source] = (typeCounts[source] || 0) + 1;
  }
  
  const avgWeight = totalWeight / citations.length;
  const breadthBonus = Math.min(1.0, citations.length / 6.0) * 0.05;
  let score = Math.min(0.99, 0.55 * strongest + 0.45 * avgWeight + breadthBonus);
  score = Math.max(0.10, score);
  
  let badge: "High" | "Moderate" | "Low";
  let badge_color: "green" | "yellow" | "red";
  
  if (score >= 0.85) {
    badge = "High";
    badge_color = "green";
  } else if (score >= 0.65) {
    badge = "Moderate";
    badge_color = "yellow";
  } else {
    badge = "Low";
    badge_color = "red";
  }
  
  const whyParts: string[] = [];
  if (typeCounts["Systematic Reviews"]) {
    whyParts.push("Systematic review evidence");
  }
  if (typeCounts["Medical Journal"]) {
    whyParts.push("Peer-reviewed medical journals");
  }
  if (typeCounts["Research Journal"]) {
    whyParts.push("Research journal sources");
  }
  if (whyParts.length === 0) {
    whyParts.push(`Based on ${citations.length} sources`);
  }
  
  return {
    score: Math.round(score * 100) / 100,
    badge,
    badge_color,
    types: typeCounts,
    why: whyParts.join("; "),
    unique_sources: citations.length
  };
}

// ─── Rate limiters ────────────────────────────────────────────────────────────

const extractUserId = (req: Request): string => {
  const auth = req.headers.authorization || "";
  if (auth.startsWith("Bearer ")) {
    try {
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
  validate: { keyGeneratorIpFallback: false },
  message: { detail: "Too many requests. Please wait a moment before searching again." },
  skip: (req) => req.method === "OPTIONS",
});

const safetyLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 30,
  keyGenerator: extractUserId,
  standardHeaders: true,
  legacyHeaders: false,
  validate: { keyGeneratorIpFallback: false },
  message: { detail: "Safety check rate limit reached. Please wait before running another check." },
  skip: (req) => req.method === "OPTIONS",
});

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 10,
  keyGenerator: (req) => req.ip || "anon",
  standardHeaders: true,
  legacyHeaders: false,
  validate: { keyGeneratorIpFallback: false },
  message: { detail: "Too many authentication attempts. Please try again in 15 minutes." },
});

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {
  // Apply rate limiting to sensitive routes
  app.use("/api/ask", searchLimiter);
  app.use("/api/v2/stream", searchLimiter);
  app.use("/api/safety", safetyLimiter);
  app.use("/api/auth/login", authLimiter);
  app.use("/api/auth/register", authLimiter);

  app.post("/api/search", async (req, res) => {
    try {
      const { query } = searchQuerySchema.parse(req.body);
      await storage.addSearchHistory(query);
      req.body = { question: query, domain: "aesthetic_medicine", k: 12,
        conversation_id: req.body.conversation_id || "",
        lang: req.body.lang || null };
    } catch (error) {
      if (error instanceof ZodError) {
        res.status(400).json({ error: "Invalid query" });
        return;
      }
    }
    await proxyStreamSafe(`${PYTHON_API_BASE}/v2/stream`, req, res);
  });

  app.post("/api/conversations/new", async (req, res) => {
    try {
      const convRes = await fetch(`${PYTHON_API_BASE}/v2/conversations/new`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req.body || {}),
      });
      if (convRes.ok) {
        const data = await convRes.json();
        res.json(data);
      } else {
        res.status(500).json({ error: "Failed to create conversation" });
      }
    } catch (error) {
      console.error("Conversation creation error:", error);
      res.status(500).json({ error: "Failed to create conversation" });
    }
  });

  app.get("/api/conversations/:id/messages", async (req, res) => {
    try {
      const convRes = await fetch(`${PYTHON_API_BASE}/v2/conversations/${req.params.id}/messages`);
      if (convRes.ok) {
        const data = await convRes.json();
        res.json(data);
      } else {
        res.status(500).json({ error: "Failed to fetch messages" });
      }
    } catch (error) {
      console.error("Conversation fetch error:", error);
      res.status(500).json({ error: "Failed to fetch messages" });
    }
  });

  app.get("/api/conversations/user/:userId", async (req, res) => {
    try {
      const convRes = await fetch(`${PYTHON_API_BASE}/v2/conversations/user/${req.params.userId}`);
      if (convRes.ok) {
        const data = await convRes.json();
        res.json(data);
      } else {
        res.status(500).json({ error: "Failed to list conversations" });
      }
    } catch (error) {
      console.error("Conversation list error:", error);
      res.status(500).json({ error: "Failed to list conversations" });
    }
  });

  app.delete("/api/conversations/:id", async (req, res) => {
    try {
      const convRes = await fetch(`${PYTHON_API_BASE}/v2/conversations/${req.params.id}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req.body || {}),
      });
      if (convRes.ok) {
        const data = await convRes.json();
        res.json(data);
      } else {
        res.status(500).json({ error: "Failed to delete conversation" });
      }
    } catch (error) {
      console.error("Conversation delete error:", error);
      res.status(500).json({ error: "Failed to delete conversation" });
    }
  });

  app.get("/api/search/history", async (req, res) => {
    try {
      const history = await storage.getSearchHistory();
      res.json(history);
    } catch (error) {
      console.error("Error fetching search history:", error);
      res.status(500).json({ error: "Failed to fetch search history" });
    }
  });

  // Proxy routes to Python FastAPI backend
  async function proxyToFastAPI(
    req: Request,
    res: Response,
    path: string,
    sanitize = false
  ) {
    const maxRetries = 3;
    const retryDelay = 2000;

    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };
        if (req.headers.authorization) {
          headers["Authorization"] = req.headers.authorization as string;
        }
        if (req.headers["x-api-key"]) {
          headers["X-API-Key"] = req.headers["x-api-key"] as string;
        }
        if (req.headers["x-admin-api-key"]) {
          headers["x-admin-api-key"] = req.headers["x-admin-api-key"] as string;
        }
        if (req.headers["x-partner-session"]) {
          headers["X-Partner-Session"] = req.headers["x-partner-session"] as string;
        }

        const fetchOptions: RequestInit = {
          method: req.method,
          headers,
        };

        if (req.method !== "GET" && req.body) {
          fetchOptions.body = JSON.stringify(req.body);
        }

        const queryString = new URLSearchParams(req.query as Record<string, string>).toString();
        const fullPath = queryString ? `${path}?${queryString}` : path;

        const response = await fetch(`${PYTHON_API_BASE}${fullPath}`, fetchOptions);
        const text = await response.text();
        let data: any;
        try { data = JSON.parse(text); }
        catch { data = { detail: text.slice(0, 400) || "Non-JSON response from backend" }; }
        const output = sanitize ? sanitizeGroundedResponseStrict(data) : data;
        res.status(response.status).json(output);
        return;
      } catch (error) {
        if (attempt < maxRetries - 1) {
          console.log(`Proxy attempt ${attempt + 1} failed for ${path}, retrying in ${retryDelay}ms...`);
          await new Promise((r) => setTimeout(r, retryDelay));
        } else {
          console.error(`Proxy error for ${path} after ${maxRetries} attempts:`, error);
          res.status(502).json({ detail: "Backend service is starting up, please try again in a moment" });
        }
      }
    }
  }

  // ─── Sanitizing SSE stream proxy ────────────────────────────────────────────
  async function proxyStreamSafe(upstreamUrl: string, req: Request, res: Response) {
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no");

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (req.headers.authorization)       headers["Authorization"]      = req.headers.authorization as string;
      if (req.headers["x-api-key"])        headers["X-API-Key"]          = req.headers["x-api-key"] as string;
      if (req.headers["x-admin-api-key"])  headers["x-admin-api-key"]    = req.headers["x-admin-api-key"] as string;
      if (req.headers["x-partner-session"])headers["X-Partner-Session"]  = req.headers["x-partner-session"] as string;

      const upstream = await fetch(upstreamUrl, {
        method: "POST",
        headers,
        body: JSON.stringify(req.body),
      });

      if (!upstream.ok || !upstream.body) {
        res.write(`data: ${JSON.stringify({ type: "error", message: "Backend unavailable" })}\n\n`);
        res.end();
        return;
      }

      const reader = (upstream.body as any).getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) {
            res.write(line + "\n");
            continue;
          }
          let payload: any;
          try { payload = JSON.parse(line.slice(6)); } catch {
            res.write(line + "\n");
            continue;
          }
          // Intercept typed citation/meta events
          if (payload?.type === "citations" || payload?.type === "meta") {
            res.write(`data: ${JSON.stringify(sanitizeGroundedResponse(payload))}\n\n`);
          // Intercept flat JSON with untyped citations array
          } else if (payload?.citations && !payload?.type) {
            res.write(`data: ${JSON.stringify(sanitizeGroundedResponse(payload))}\n\n`);
          // Flat answer/response/text fallback (e.g. /ask/stream)
          } else if (payload?.answer || payload?.response || payload?.text) {
            res.write(`data: ${JSON.stringify(sanitizeGroundedResponse(payload))}\n\n`);
          } else if (payload?.type === "protocol_card") {
            // Pass protocol cards through unmodified — structured evidence objects, no inline markers
            res.write(`data: ${JSON.stringify(payload)}\n\n`);
          } else {
            res.write(line + "\n");
          }
        }
      }

      res.end();
    } catch (err) {
      console.error("proxyStreamSafe error:", err);
      if (res.headersSent) {
        res.write(`data: ${JSON.stringify({ type: "error", message: "Stream failed" })}\n\n`);
        res.end();
      } else {
        res.status(502).json({ detail: "Stream proxy failed" });
      }
    }
  }

  app.post("/api/auth/login", (req, res) => proxyToFastAPI(req, res, "/auth/login"));
  app.post("/api/auth/register", (req, res) => proxyToFastAPI(req, res, "/auth/register"));
  app.get("/api/auth/me", (req, res) => proxyToFastAPI(req, res, "/auth/me"));
  app.post("/api/auth/request-access", (req, res) => proxyToFastAPI(req, res, "/auth/request-access"));
  app.post("/api/auth/set-password", (req, res) => proxyToFastAPI(req, res, "/auth/set-password"));
  app.post("/api/ask", (req, res) => proxyToFastAPI(req, res, "/ask", true));
  app.post("/api/ask/stream", async (req, res) => {
    await proxyStreamSafe(`${PYTHON_API_BASE}/ask/stream`, req, res);
  });
  app.get("/api/complications/protocols", (req, res) => proxyToFastAPI(req, res, "/api/complications/protocols"));
  app.post("/api/complications/protocol", (req, res) => proxyToFastAPI(req, res, "/api/complications/protocol"));
  app.post("/api/complications/print-view", (req, res) => proxyToFastAPI(req, res, "/api/complications/print-view"));
  app.post("/api/complications/export-pdf", (req, res) => proxyToFastAPI(req, res, "/api/complications/export-pdf"));
  app.post("/api/complications/feedback", (req, res) => proxyToFastAPI(req, res, "/api/complications/feedback"));
  app.post("/api/complications/log-case", (req, res) => proxyToFastAPI(req, res, "/api/complications/log-case"));
  app.get("/api/complications/stats", (req, res) => proxyToFastAPI(req, res, "/api/complications/stats"));
  app.post("/api/complications/prescan-briefing", (req, res) => proxyToFastAPI(req, res, "/api/complications/prescan-briefing"));

  // ── Cases Network (Doximity-inspired outcome data) ───────────────────────
  // Order: specific paths before parameterised ones
  // ── Workflow Engine ───────────────────────────────────────────────────
  app.get("/api/workflow/list",  (req, res) => proxyToFastAPI(req, res, "/api/workflow/list"));
  app.get("/api/workflow",       (req, res) => proxyToFastAPI(req, res, "/api/workflow"));

  // ── Medico-Legal Report Generator ────────────────────────────────────
  // Order: specific GET /:id before bare POST to avoid Express ambiguity
  app.get("/api/generate-report/:id",  (req, res) => proxyToFastAPI(req, res, `/api/generate-report/${req.params.id}`));
  app.post("/api/generate-report",     (req, res) => proxyToFastAPI(req, res, "/api/generate-report"));
  app.post("/api/generate-report/pdf", async (req, res) => {
    try {
      const PYTHON_BASE = process.env.PYTHON_API_BASE || "http://localhost:8000";
      const response = await fetch(`${PYTHON_BASE}/api/generate-report/pdf`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(req.headers.authorization ? { Authorization: req.headers.authorization as string } : {}),
        },
        body: JSON.stringify(req.body),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        return res.status(response.status).json(err);
      }
      const disposition = response.headers.get("content-disposition") || "attachment";
      res.setHeader("Content-Type", "application/pdf");
      res.setHeader("Content-Disposition", disposition);
      const buf = await response.arrayBuffer();
      res.send(Buffer.from(buf));
    } catch {
      res.status(502).json({ detail: "PDF generation failed" });
    }
  });

  app.get("/api/cases/stats",                (req, res) => proxyToFastAPI(req, res, "/api/cases/stats"));
  app.get("/api/speed/stats",               (req, res) => proxyToFastAPI(req, res, "/api/speed/stats"));
  app.get("/api/corpus/stats",              (req, res) => proxyToFastAPI(req, res, "/api/ops/corpus/count"));
  app.get("/api/cases/outcomes/:comp",       (req, res) => proxyToFastAPI(req, res, `/api/cases/outcomes/${req.params.comp}`));
  app.post("/api/cases/:id/outcome",         (req, res) => proxyToFastAPI(req, res, `/api/cases/${req.params.id}/outcome`));
  app.post("/api/cases",                     (req, res) => proxyToFastAPI(req, res, "/api/cases"));
  app.get("/api/cases",                      (req, res) => proxyToFastAPI(req, res, "/api/cases"));

  app.post("/api/safety/preprocedure-check", (req, res) => proxyToFastAPI(req, res, "/api/safety/preprocedure-check"));
  app.post("/api/safety/preprocedure-check/export-pdf", (req, res) => proxyToFastAPI(req, res, "/api/safety/preprocedure-check/export-pdf"));

  app.all(["/api/growth", "/api/growth/*splat"], (req: Request, res: Response) => {
    proxyToFastAPI(req, res, req.path);
  });

  app.get("/manifest.json", (_req: Request, res: Response) => {
    res.json({
      name: "AesthetiCite",
      short_name: "AesthetiCite",
      start_url: "/",
      display: "standalone",
      background_color: "#0f172a",
      theme_color: "#0f172a",
      description: "Clinical safety and evidence platform for aesthetic medicine.",
      icons: [
        { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
        { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      ],
    });
  });

  app.get("/sw.js", (_req: Request, res: Response) => {
    res.setHeader("Content-Type", "application/javascript");
    res.send(
      "self.addEventListener('install',(e)=>{self.skipWaiting();});\n" +
      "self.addEventListener('activate',(e)=>{e.waitUntil(self.clients.claim());});\n" +
      "self.addEventListener('fetch',(e)=>{ /* pass-through */ });"
    );
  });

  app.get("/exports/:filename", (req: Request, res: Response) => {
    const raw = Array.isArray(req.params.filename) ? req.params.filename[0] : req.params.filename;
    const filename = path.basename(raw);
    if (!/^[\w\-]+\.pdf$/i.test(filename)) {
      res.status(400).send("Invalid filename");
      return;
    }
    const exportsDir = path.resolve(process.cwd(), "exports");
    const filePath = path.resolve(exportsDir, filename);
    if (!filePath.startsWith(exportsDir + path.sep) && filePath !== exportsDir) {
      res.status(400).send("Invalid filename");
      return;
    }
    if (!fs.existsSync(filePath)) {
      res.status(404).send("File not found");
      return;
    }
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", `attachment; filename="${filename}"`);
    fs.createReadStream(filePath).pipe(res);
  });

  app.post("/api/v2/stream", async (req, res) => {
    await proxyStreamSafe(`${PYTHON_API_BASE}/v2/stream`, req, res);
  });
  app.post("/api/ask_oe", (req, res) => proxyToFastAPI(req, res, "/ask_oe", true));
  app.get("/api/ask_oe/health", (req, res) => proxyToFastAPI(req, res, "/ask_oe/health"));
  app.get("/api/health", (req, res) => proxyToFastAPI(req, res, "/health"));
  app.get("/api/health/deep", (req, res) => proxyToFastAPI(req, res, "/health/deep"));
  app.get("/api/ready", (req, res) => proxyToFastAPI(req, res, "/ready"));
  app.get("/api/admin/metrics", (req, res) => proxyToFastAPI(req, res, "/admin/metrics"));
  app.get("/api/admin/metrics/summary", (req, res) => proxyToFastAPI(req, res, "/admin/metrics/summary"));
  app.get("/api/admin/benchmark/summary", (req, res) => proxyToFastAPI(req, res, "/admin/benchmark/summary"));
  app.get("/api/admin/benchmark/questions", (req, res) => proxyToFastAPI(req, res, "/admin/benchmark/questions"));
  app.post("/api/admin/benchmark/run", (req, res) => proxyToFastAPI(req, res, "/admin/benchmark/run"));
  app.post("/api/admin/benchmark/run-single", (req, res) => proxyToFastAPI(req, res, "/admin/benchmark/run-single"));
  app.post("/api/admin/benchmark/gold", (req, res) => proxyToFastAPI(req, res, "/admin/benchmark/gold"));
  app.get("/api/admin/benchmark/gold/questions", (req, res) => proxyToFastAPI(req, res, "/admin/benchmark/gold/questions"));
  app.post("/api/admin/benchmark/gold/report", (req, res) => proxyToFastAPI(req, res, "/admin/benchmark/gold/report"));
  app.get("/api/admin/stats/enterprise", (req, res) => proxyToFastAPI(req, res, "/admin/stats/enterprise"));
  app.get("/api/admin/export/pilot.csv", (req, res) => proxyToFastAPI(req, res, "/admin/export/pilot.csv"));
  app.get("/api/languages", (req, res) => proxyToFastAPI(req, res, "/languages"));
  app.post("/api/languages/detect", (req, res) => proxyToFastAPI(req, res, "/languages/detect"));
  
  // Partner preview routes
  app.get("/partner/preview", (req, res) => proxyToFastAPI(req, res, "/partner/preview"));
  app.get("/partner/login", (req, res) => proxyToFastAPI(req, res, "/partner/login"));
  app.get("/partner/app", (req, res) => proxyToFastAPI(req, res, "/partner/app"));
  app.get("/partner/status", (req, res) => proxyToFastAPI(req, res, "/partner/status"));
  app.post("/partner/deepconsult", (req, res) => proxyToFastAPI(req, res, "/partner/deepconsult"));
  app.post("/partner/logout", (req, res) => proxyToFastAPI(req, res, "/partner/logout"));
  app.get("/partner/analytics", (req, res) => proxyToFastAPI(req, res, "/partner/analytics"));
  
  // Clinical document generators
  app.post("/api/clinical-docs/prior-auth", (req, res) => proxyToFastAPI(req, res, "/clinical-docs/prior-auth"));
  app.post("/api/clinical-docs/patient-instructions", (req, res) => proxyToFastAPI(req, res, "/clinical-docs/patient-instructions"));
  app.post("/api/clinical-docs/icd10-codes", (req, res) => proxyToFastAPI(req, res, "/clinical-docs/icd10-codes"));
  app.post("/api/clinical-docs/discharge-summary", (req, res) => proxyToFastAPI(req, res, "/clinical-docs/discharge-summary"));

  // Clinical calculators (Epocrates-grade tools)
  app.post("/api/tools/calc/dilution",          (req, res) => proxyToFastAPI(req, res, "/tools/calc/dilution"));
  app.post("/api/tools/aesthetic/toxin/dilution",(req, res) => proxyToFastAPI(req, res, "/tools/aesthetic/toxin/dilution"));
  app.post("/api/tools/aesthetic/risk-flags/check",(req,res) => proxyToFastAPI(req, res, "/tools/aesthetic/risk-flags/check"));

  // Voice transcription with file upload
  const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 50 * 1024 * 1024 } });
  
  app.post("/api/voice/transcribe", upload.single("file"), async (req, res) => {
    try {
      if (!req.file) {
        return res.status(400).json({ detail: "No audio file provided" });
      }
      
      const formData = new FormData();
      formData.append("file", req.file.buffer, {
        filename: req.file.originalname || "audio.webm",
        contentType: req.file.mimetype,
      });
      
      if (req.body.language) {
        formData.append("language", req.body.language);
      }
      
      const response = await fetch(`${PYTHON_API_BASE}/voice/transcribe`, {
        method: "POST",
        headers: {
          ...formData.getHeaders(),
          ...(req.headers.authorization ? { Authorization: req.headers.authorization as string } : {}),
        },
        body: formData as unknown as BodyInit,
      });
      
      const data = await response.json();
      res.status(response.status).json(data);
    } catch (error) {
      console.error("Voice transcription error:", error);
      res.status(502).json({ detail: "Voice transcription service unavailable" });
    }
  });
  
  app.post("/api/voice/clinical-note", upload.single("file"), async (req, res) => {
    try {
      if (!req.file) {
        return res.status(400).json({ detail: "No audio file provided" });
      }
      
      const formData = new FormData();
      formData.append("file", req.file.buffer, {
        filename: req.file.originalname || "audio.webm",
        contentType: req.file.mimetype,
      });
      
      if (req.body.specialty) {
        formData.append("specialty", req.body.specialty);
      }
      
      const response = await fetch(`${PYTHON_API_BASE}/voice/clinical-note`, {
        method: "POST",
        headers: {
          ...formData.getHeaders(),
          ...(req.headers.authorization ? { Authorization: req.headers.authorization as string } : {}),
        },
        body: formData as unknown as BodyInit,
      });
      
      const data = await response.json();
      res.status(response.status).json(data);
    } catch (error) {
      console.error("Clinical note error:", error);
      res.status(502).json({ detail: "Clinical note service unavailable" });
    }
  });

  // Visual Counseling routes
  app.post("/api/visual/upload", upload.single("file"), async (req, res) => {
    try {
      if (!req.file) {
        return res.status(400).json({ detail: "No image file provided" });
      }

      const formData = new FormData();
      formData.append("file", req.file.buffer, {
        filename: req.file.originalname || "photo.jpg",
        contentType: req.file.mimetype,
      });
      formData.append("conversation_id", req.body.conversation_id || "");
      formData.append("kind", req.body.kind || "photo");

      const response = await fetch(`${PYTHON_API_BASE}/visual/upload`, {
        method: "POST",
        headers: {
          ...formData.getHeaders(),
          ...(req.headers.authorization ? { Authorization: req.headers.authorization as string } : {}),
        },
        body: formData as unknown as BodyInit,
      });

      const data = await response.json();
      res.status(response.status).json(data);
    } catch (error) {
      console.error("Visual upload error:", error);
      res.status(502).json({ detail: "Visual upload service unavailable" });
    }
  });

  app.post("/api/visual/preview", async (req, res) => {
    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (req.headers.authorization) {
        headers["Authorization"] = req.headers.authorization as string;
      }
      const response = await fetch(`${PYTHON_API_BASE}/visual/preview`, {
        method: "POST",
        headers,
        body: JSON.stringify(req.body),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        return res.status(response.status).json(err);
      }
      res.setHeader("Content-Type", "image/png");
      const buf = await response.arrayBuffer();
      res.send(Buffer.from(buf));
    } catch (error) {
      console.error("Visual preview error:", error);
      res.status(502).json({ detail: "Preview service unavailable" });
    }
  });

  // ── AesthetiCite Vision routes ────────────────────────────────────────────
  app.post("/api/vision/analyze", upload.array("files", 10), async (req: Request, res: Response) => {
    try {
      const files = req.files as Express.Multer.File[];
      if (!files || files.length < 2) {
        return res.status(400).json({ detail: "At least 2 image files are required." });
      }
      const formData = new FormData();
      formData.append("procedure", (req.body as any).procedure_type || (req.body as any).procedure || "injectables");
      formData.append("notes", (req.body as any).notes || "");
      for (const f of files) {
        formData.append("files", f.buffer, {
          filename: f.originalname || "image.jpg",
          contentType: f.mimetype,
        });
      }
      // node-form-data objects can't be passed directly to Node 20's native fetch;
      // serialise to Buffer and set Content-Type manually so FastAPI's multipart
      // parser receives a correct boundary-delimited body.
      const buf = formData.getBuffer();
      const response = await fetch(`${PYTHON_API_BASE}/api/vision/analyze`, {
        method: "POST",
        headers: {
          "Content-Type": `multipart/form-data; boundary=${formData.getBoundary()}`,
          ...(req.headers.authorization ? { Authorization: req.headers.authorization as string } : {}),
        },
        body: buf,
      });
      const data = await response.json();
      res.status(response.status).json(data);
    } catch (error) {
      console.error("Vision analyze error:", error);
      res.status(502).json({ detail: "Vision analysis service unavailable" });
    }
  });

  app.post("/api/vision/analyze/export", upload.array("files", 10), async (req: Request, res: Response) => {
    try {
      const files = req.files as Express.Multer.File[];
      if (!files || files.length < 2) {
        return res.status(400).json({ detail: "At least 2 image files are required." });
      }
      const formData = new FormData();
      formData.append("procedure", (req.body as any).procedure_type || (req.body as any).procedure || "injectables");
      formData.append("notes", (req.body as any).notes || "");
      for (const f of files) {
        formData.append("files", f.buffer, {
          filename: f.originalname || "image.jpg",
          contentType: f.mimetype,
        });
      }
      const buf = formData.getBuffer();
      const response = await fetch(`${PYTHON_API_BASE}/api/vision/analyze/export`, {
        method: "POST",
        headers: {
          "Content-Type": `multipart/form-data; boundary=${formData.getBoundary()}`,
          ...(req.headers.authorization ? { Authorization: req.headers.authorization as string } : {}),
        },
        body: buf,
      });
      const data = await response.json();
      res.status(response.status).json(data);
    } catch (error) {
      console.error("Vision PDF export error:", error);
      res.status(502).json({ detail: "Vision PDF export service unavailable" });
    }
  });

  app.get("/api/vision/procedures", async (req: Request, res: Response) => {
    try {
      const response = await fetch(`${PYTHON_API_BASE}/api/vision/procedures`);
      const data = await response.json();
      res.status(response.status).json(data);
    } catch (error) {
      res.status(502).json({ detail: "Vision procedures service unavailable" });
    }
  });

  // Vision Diagnosis Engine — complication differential (VisualDX-inspired)
  app.post("/api/vision/diagnose", upload.single("file"), async (req: Request, res: Response) => {
    try {
      const formData = new FormData();
      if (req.file) formData.append("file", req.file.buffer, { filename: req.file.originalname, contentType: req.file.mimetype });
      if (req.body.procedure)  formData.append("procedure",  req.body.procedure);
      if (req.body.region)     formData.append("region",     req.body.region);
      if (req.body.time_since) formData.append("time_since", req.body.time_since);
      if (req.body.product)    formData.append("product",    req.body.product);
      const headers: Record<string, string> = { "Content-Type": `multipart/form-data; boundary=${formData.getBoundary()}` };
      if (req.headers.authorization) headers["Authorization"] = req.headers.authorization as string;
      const response = await fetch(`${PYTHON_API_BASE}/api/vision/diagnose`, { method: "POST", headers, body: formData.getBuffer() });
      const data = await response.json();
      res.status(response.status).json(data);
    } catch (error) {
      res.status(502).json({ detail: "Vision diagnosis service unavailable" });
    }
  });

  app.post("/api/vision/diagnose-compare", upload.fields([{ name: "baseline", maxCount: 1 }, { name: "followup", maxCount: 1 }]), async (req: Request, res: Response) => {
    try {
      const files = req.files as { [fieldname: string]: Express.Multer.File[] };
      const formData = new FormData();
      if (files?.baseline?.[0]) { const f = files.baseline[0]; formData.append("baseline", f.buffer, { filename: f.originalname, contentType: f.mimetype }); }
      if (files?.followup?.[0])  { const f = files.followup[0];  formData.append("followup",  f.buffer, { filename: f.originalname, contentType: f.mimetype }); }
      if (req.body.procedure)          formData.append("procedure",          req.body.procedure);
      if (req.body.region)             formData.append("region",             req.body.region);
      if (req.body.days_since_baseline) formData.append("days_since_baseline", req.body.days_since_baseline);
      const headers: Record<string, string> = { "Content-Type": `multipart/form-data; boundary=${formData.getBoundary()}` };
      if (req.headers.authorization) headers["Authorization"] = req.headers.authorization as string;
      const response = await fetch(`${PYTHON_API_BASE}/api/vision/diagnose-compare`, { method: "POST", headers, body: formData.getBuffer() });
      const data = await response.json();
      res.status(response.status).json(data);
    } catch (error) {
      res.status(502).json({ detail: "Vision compare service unavailable" });
    }
  });

  app.get("/api/vision/complication-signs", async (req: Request, res: Response) => {
    try {
      const headers: Record<string, string> = {};
      if (req.headers.authorization) headers["Authorization"] = req.headers.authorization as string;
      const response = await fetch(`${PYTHON_API_BASE}/api/vision/complication-signs`, { headers });
      const data = await response.json();
      res.status(response.status).json(data);
    } catch (error) {
      res.status(502).json({ detail: "Vision complication signs service unavailable" });
    }
  });

  app.post("/api/ask/visual/stream", async (req, res) => {
    try {
      res.setHeader("Content-Type", "text/event-stream");
      res.setHeader("Cache-Control", "no-cache");
      res.setHeader("Connection", "keep-alive");
      res.setHeader("X-Accel-Buffering", "no");

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (req.headers.authorization) {
        headers["Authorization"] = req.headers.authorization as string;
      }

      const fastApiRes = await fetch(`${PYTHON_API_BASE}/ask/visual/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify(req.body),
      });

      if (!fastApiRes.ok || !fastApiRes.body) {
        res.write(`data: ${JSON.stringify({ type: "error", message: "Backend unavailable" })}\n\n`);
        res.end();
        return;
      }

      const reader = (fastApiRes.body as any).getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        res.write(chunk);
      }

      res.end();
    } catch (error) {
      console.error("Visual counsel stream error:", error);
      if (res.headersSent) {
        res.write(`data: ${JSON.stringify({ type: "error", message: "Visual counseling failed" })}\n\n`);
        res.end();
      } else {
        res.status(502).json({ detail: "Visual counseling service unavailable" });
      }
    }
  });

  // Voice transcription endpoint
  app.post("/api/transcribe", upload.single("audio"), async (req, res) => {
    try {
      if (!req.file) {
        return res.status(400).json({ error: "No audio file provided" });
      }

      // Use OpenAI's toFile helper for Node.js compatibility
      const { toFile } = await import("openai/uploads");
      const audioFile = await toFile(req.file.buffer, "audio.webm", { type: req.file.mimetype });
      
      const transcription = await openai.audio.transcriptions.create({
        file: audioFile,
        model: "gpt-4o-mini-transcribe",
        response_format: "json",
      });

      res.json({ text: transcription.text });
    } catch (error) {
      console.error("Transcription error:", error);
      res.status(500).json({ error: "Transcription failed" });
    }
  });

  // Text Export endpoint (changed to .txt for correctness)
  app.post("/api/export/pdf", async (req, res) => {
    try {
      const { question, answer, citations, clinicalSummary } = req.body;
      
      // Generate formatted text report
      let content = `VERIDOC EVIDENCE REPORT\n${"=".repeat(50)}\n\n`;
      content += `Date: ${new Date().toLocaleDateString()}\n\n`;
      content += `QUESTION:\n${question}\n\n`;
      if (clinicalSummary) {
        content += `CLINICAL SUMMARY:\n${clinicalSummary}\n\n`;
      }
      content += `${"=".repeat(50)}\n\nANSWER:\n${answer}\n\n`;
      content += `${"=".repeat(50)}\nREFERENCES:\n`;
      
      (citations || []).forEach((c: { title: string; source?: string; year?: number; url?: string }, i: number) => {
        content += `\n[${i + 1}] ${c.title}`;
        if (c.source) content += `\n    Source: ${c.source}`;
        if (c.year) content += ` (${c.year})`;
        if (c.url) content += `\n    URL: ${c.url}`;
        content += "\n";
      });
      
      content += `\n${"=".repeat(50)}\nGenerated by AesthetiCite - AI Evidence Search\n`;
      
      // Return as text file
      res.setHeader("Content-Type", "text/plain; charset=utf-8");
      res.setHeader("Content-Disposition", "attachment; filename=aestheticite-report.txt");
      res.send(Buffer.from(content, "utf-8"));
    } catch (error) {
      console.error("Export error:", error);
      res.status(500).json({ error: "Export failed" });
    }
  });

  // Favorites endpoints
  app.post("/api/favorites", async (req, res) => {
    try {
      const { query_id, question, answer_preview } = req.body;
      // Store in memory for now (would normally go to database)
      res.json({ success: true, id: query_id || Date.now().toString() });
    } catch (error) {
      res.status(500).json({ error: "Failed to save favorite" });
    }
  });

  app.delete("/api/favorites/:id", async (req, res) => {
    try {
      res.json({ success: true });
    } catch (error) {
      res.status(500).json({ error: "Failed to remove favorite" });
    }
  });

  // Feedback endpoints
  app.post("/api/feedback", async (req, res) => {
    try {
      const { query_id, question, rating } = req.body;
      console.log(`Feedback received: ${rating} for query "${question?.substring(0, 50)}..."`);
      res.json({ success: true });
    } catch (error) {
      res.status(500).json({ error: "Failed to submit feedback" });
    }
  });

  app.post("/api/feedback/report", async (req, res) => {
    try {
      const { query_id, question, report } = req.body;
      console.log(`Issue reported for query "${question?.substring(0, 50)}...": ${report?.substring(0, 100)}`);
      res.json({ success: true });
    } catch (error) {
      res.status(500).json({ error: "Failed to submit report" });
    }
  });

  // ─── Safety Engine v2 proxy routes ──────────────────────────────────────────
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

  // ─── Operational routes ──────────────────────────────────────────────────────
  app.get("/api/ops/health/full",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/health/full"));
  app.post("/api/ops/dashboard/log-query",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/dashboard/log-query"));
  app.get("/api/ops/dashboard/clinic",
    (req, res) => proxyToFastAPI(req, res, "/api/ops/dashboard/clinic"));

  // ─── PWA: service worker with correct headers ────────────────────────────────
  app.get("/sw.js", (req: Request, res: Response) => {
    res.setHeader("Content-Type", "application/javascript; charset=utf-8");
    res.setHeader("Service-Worker-Allowed", "/");
    res.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");
    const swPath = path.join(process.cwd(), "client", "public", "sw.js");
    if (fs.existsSync(swPath)) {
      res.sendFile(swPath);
    } else {
      res.send(`self.addEventListener('install',e=>{self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil(self.clients.claim());});
self.addEventListener('fetch',e=>{});`);
    }
  });

  // ─── PWA manifest ────────────────────────────────────────────────────────────
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

  app.get("/api/ops/readiness",         (req, res) => proxyToFastAPI(req, res, "/api/ops/readiness"));
  app.post("/api/ops/readiness/fix",    (req, res) => proxyToFastAPI(req, res, "/api/ops/readiness/fix"));
  app.get("/api/ops/readiness/history", (req, res) => proxyToFastAPI(req, res, "/api/ops/readiness/history"));
  app.get("/api/ops/readiness/quick",   (req, res) => proxyToFastAPI(req, res, "/api/ops/readiness/quick"));

  app.get("/api/ops/ingest/status",     (req, res) => proxyToFastAPI(req, res, "/api/ops/ingest/status"));
  app.post("/api/ops/ingest/start",     (req, res) => proxyToFastAPI(req, res, "/api/ops/ingest/start"));
  app.get("/api/ops/evidence/test",     (req, res) => proxyToFastAPI(req, res, "/api/ops/evidence/test"));
  app.post("/api/ops/auth/forgot-password", (req, res) => proxyToFastAPI(req, res, "/api/ops/auth/forgot-password"));
  app.post("/api/ops/auth/verify-email",    (req, res) => proxyToFastAPI(req, res, "/api/ops/auth/verify-email"));

  // ── Clinic Network Safety Workspace ──────────────────────────────────
  app.get("/api/workspace/orgs/me",        (req, res) => proxyToFastAPI(req, res, "/api/workspace/orgs/me"));
  app.get("/api/workspace/clinics/me",     (req, res) => proxyToFastAPI(req, res, "/api/workspace/clinics/me"));
  app.post("/api/workspace/clinics/select",(req, res) => proxyToFastAPI(req, res, "/api/workspace/clinics/select"));

  app.post("/api/workspace/network-guidance/query",
      (req, res) => proxyToFastAPI(req, res, "/api/workspace/network-guidance/query"));

  app.post("/api/workspace/case-logs",     (req, res) => proxyToFastAPI(req, res, "/api/workspace/case-logs"));
  app.get("/api/workspace/case-logs",      (req, res) => proxyToFastAPI(req, res, "/api/workspace/case-logs"));
  app.get("/api/workspace/case-logs/export/csv",
      (req, res) => proxyToFastAPI(req, res, "/api/workspace/case-logs/export/csv"));
  app.get("/api/workspace/case-logs/:id",  (req, res) => proxyToFastAPI(req, res, `/api/workspace/case-logs/${req.params.id}`));
  app.patch("/api/workspace/case-logs/:id",(req, res) => proxyToFastAPI(req, res, `/api/workspace/case-logs/${req.params.id}`));

  app.post("/api/workspace/protocols",     (req, res) => proxyToFastAPI(req, res, "/api/workspace/protocols"));
  app.get("/api/workspace/protocols",      (req, res) => proxyToFastAPI(req, res, "/api/workspace/protocols"));
  app.patch("/api/workspace/protocols/:id",(req, res) => proxyToFastAPI(req, res, `/api/workspace/protocols/${req.params.id}`));

  app.post("/api/workspace/reports/from-case/:id",
      (req, res) => proxyToFastAPI(req, res, `/api/workspace/reports/from-case/${req.params.id}`));
  app.post("/api/workspace/reports/from-guidance",
      (req, res) => proxyToFastAPI(req, res, "/api/workspace/reports/from-guidance"));
  app.get("/api/workspace/reports/:id",    (req, res) => proxyToFastAPI(req, res, `/api/workspace/reports/${req.params.id}`));

  app.get("/api/workspace/admin/analytics/overview",
      (req, res) => proxyToFastAPI(req, res, "/api/workspace/admin/analytics/overview"));
  app.get("/api/workspace/admin/analytics/trends",
      (req, res) => proxyToFastAPI(req, res, "/api/workspace/admin/analytics/trends"));

  // ── Risk Intelligence ──────────────────────────────────────────────────────
  app.post("/api/risk/scores/compute",      (req, res) => proxyToFastAPI(req, res, "/api/risk/scores/compute"));
  app.get("/api/risk/scores",               (req, res) => proxyToFastAPI(req, res, "/api/risk/scores"));
  app.get("/api/risk/scores/:name",         (req, res) => proxyToFastAPI(req, res, `/api/risk/scores/${encodeURIComponent(req.params.name)}`));
  app.get("/api/risk/alerts",               (req, res) => proxyToFastAPI(req, res, "/api/risk/alerts"));
  app.post("/api/risk/alerts/:id/dismiss",  (req, res) => proxyToFastAPI(req, res, `/api/risk/alerts/${req.params.id}/dismiss`));
  app.post("/api/risk/detect-patterns",     (req, res) => proxyToFastAPI(req, res, "/api/risk/detect-patterns"));
  app.get("/api/risk/heatmap",              (req, res) => proxyToFastAPI(req, res, "/api/risk/heatmap"));

  // ── Complication Monitor ───────────────────────────────────────────────────
  app.post("/api/monitor/cases",                    (req, res) => proxyToFastAPI(req, res, "/api/monitor/cases"));
  app.get("/api/monitor/cases",                     (req, res) => proxyToFastAPI(req, res, "/api/monitor/cases"));
  app.get("/api/monitor/cases/:id",                 (req, res) => proxyToFastAPI(req, res, `/api/monitor/cases/${req.params.id}`));
  app.post("/api/monitor/cases/:id/submit",
    upload.single("file"),
    (req, res) => {
      const formData = new FormData();
      if (req.file) {
        formData.append("file", new Blob([req.file.buffer], { type: req.file.mimetype }), req.file.originalname);
      }
      if (req.body?.clinic_id) formData.append("clinic_id", req.body.clinic_id);
      if (req.body?.notes)     formData.append("notes",     req.body.notes);
      const PYTHON_API_BASE = process.env.PYTHON_API_BASE || "http://localhost:8000";
      const token = (req.headers["authorization"] as string) || "";
      fetch(`${PYTHON_API_BASE}/api/monitor/cases/${req.params.id}/submit`, {
        method: "POST",
        headers: { ...(token ? { authorization: token } : {}) },
        body: formData as any,
      })
        .then(async (r) => {
          const body = await r.text();
          res.status(r.status).set("Content-Type", "application/json").send(body);
        })
        .catch((err) => res.status(502).json({ detail: "Monitor submit proxy error", error: String(err) }));
    });
  app.patch("/api/monitor/cases/:id/status",        (req, res) => proxyToFastAPI(req, res, `/api/monitor/cases/${req.params.id}/status`));

  // ── Org Analytics ──────────────────────────────────────────────────────────
  app.post("/api/analytics/events",                 (req, res) => proxyToFastAPI(req, res, "/api/analytics/events"));
  app.get("/api/analytics/session-heatmap",         (req, res) => proxyToFastAPI(req, res, "/api/analytics/session-heatmap"));
  app.get("/api/analytics/answer-quality",          (req, res) => proxyToFastAPI(req, res, "/api/analytics/answer-quality"));
  app.get("/api/analytics/org-overview/:org_id",    (req, res) => proxyToFastAPI(req, res, `/api/analytics/org-overview/${req.params.org_id}`));
  app.get("/api/analytics/clinic-benchmark",        (req, res) => proxyToFastAPI(req, res, "/api/analytics/clinic-benchmark"));

  // ── LLM Provider ───────────────────────────────────────────────────────────
  app.get("/api/llm/providers",                     (req, res) => proxyToFastAPI(req, res, "/api/llm/providers"));
  app.get("/api/llm/config/:org_id",                (req, res) => proxyToFastAPI(req, res, `/api/llm/config/${req.params.org_id}`));
  app.post("/api/llm/config/:org_id",               (req, res) => proxyToFastAPI(req, res, `/api/llm/config/${req.params.org_id}`));
  app.post("/api/llm/test",                         (req, res) => proxyToFastAPI(req, res, "/api/llm/test"));

  // ── Study Ingest ──────────────────────────────────────────────────────────
  app.post("/ingest/doi",             (req, res) => proxyToFastAPI(req, res, "/ingest/doi"));
  app.get("/ingest/records",          (req, res) => proxyToFastAPI(req, res, "/ingest/records"));
  app.post("/ingest/extract/:id",     (req, res) => proxyToFastAPI(req, res, `/ingest/extract/${req.params.id}`));
  app.post("/ingest/process/:id",     (req, res) => proxyToFastAPI(req, res, `/ingest/process/${req.params.id}`));
  app.post("/ingest/embed/:id",       (req, res) => proxyToFastAPI(req, res, `/ingest/embed/${req.params.id}`));

  // PDF upload — multipart pass-through
  app.post("/ingest/upload/pdf/:id", async (req: Request, res: Response) => {
    try {
      const upstream = await fetch(`${PYTHON_API_BASE}/ingest/upload/pdf/${req.params.id}`, {
        method: "POST",
        headers: {
          ...(req.headers["x-api-key"] ? { "x-api-key": req.headers["x-api-key"] as string } : {}),
          ...(req.headers["content-type"] ? { "content-type": req.headers["content-type"] as string } : {}),
        },
        body: req as any,
        // @ts-ignore
        duplex: "half",
      });
      const data = await upstream.json().catch(() => ({}));
      res.status(upstream.status).json(data);
    } catch (err) {
      res.status(502).json({ detail: "PDF upload proxy failed" });
    }
  });

  // ── Clinical Decision Engine (Master Build) ───────────────────────────────
  app.post("/api/decide",               (req, res) => proxyToFastAPI(req, res, "/api/decide"));
  app.post("/api/decide/reasoning",     (req, res) => proxyToFastAPI(req, res, "/api/decide/reasoning"));
  app.post("/api/decide/workflow",      (req, res) => proxyToFastAPI(req, res, "/api/decide/workflow"));
  app.post("/api/decide/hyaluronidase", (req, res) => proxyToFastAPI(req, res, "/api/decide/hyaluronidase"));
  app.get("/api/decide/protocols",      (req, res) => proxyToFastAPI(req, res, "/api/decide/protocols"));
  app.get("/api/decide/similar-cases",  (req, res) => proxyToFastAPI(req, res, "/api/decide/similar-cases"));

  // ── Clinical Reasoning (Glass Health-inspired) ──────────────────────────
  app.post("/api/reasoning/stream", async (req: Request, res: Response) => {
    try {
      res.setHeader("Content-Type", "text/event-stream");
      res.setHeader("Cache-Control", "no-cache");
      res.setHeader("Connection", "keep-alive");
      res.setHeader("X-Accel-Buffering", "no");

      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (req.headers.authorization) {
        headers["Authorization"] = req.headers.authorization as string;
      }
      const fastApiRes = await fetch(`${PYTHON_API_BASE}/api/reasoning/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify(req.body),
      });
      if (!fastApiRes.ok || !fastApiRes.body) {
        res.write(`data: ${JSON.stringify({ type: "error", message: "Reasoning unavailable" })}\n\n`);
        res.end();
        return;
      }
      const reader = (fastApiRes.body as any).getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        res.write(decoder.decode(value, { stream: true }));
      }
      res.end();
    } catch (error) {
      res.write(`data: ${JSON.stringify({ type: "error", message: "Stream failed" })}\n\n`);
      res.end();
    }
  });

  app.post("/api/reasoning",      (req: Request, res: Response) => proxyToFastAPI(req, res, "/api/reasoning"));
  app.get("/api/reasoning/cache", (req: Request, res: Response) => proxyToFastAPI(req, res, "/api/reasoning/cache"));

  // ─── Backup (admin-only) ────────────────────────────────────────────────────
  app.post("/api/backup/start",  (req, res) => proxyToFastAPI(req, res, "/api/backup/start"));
  app.get("/api/backup/status",  (req, res) => proxyToFastAPI(req, res, "/api/backup/status"));
  app.get("/api/backup/files",   (req, res) => proxyToFastAPI(req, res, "/api/backup/files"));

  app.post("/api/decide/report", async (req: Request, res: Response) => {
    try {
      const response = await fetch(`${PYTHON_API_BASE}/api/decide/report`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(req.headers.authorization ? { Authorization: req.headers.authorization as string } : {}),
        },
        body: JSON.stringify(req.body),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        return res.status(response.status).json(err);
      }
      const contentType = response.headers.get("content-type") || "application/octet-stream";
      const disposition = response.headers.get("content-disposition") || "attachment";
      res.setHeader("Content-Type", contentType);
      res.setHeader("Content-Disposition", disposition);
      const buf = await response.arrayBuffer();
      res.send(Buffer.from(buf));
    } catch (error) {
      res.status(502).json({ detail: "Report generation failed" });
    }
  });

  return httpServer;
}
