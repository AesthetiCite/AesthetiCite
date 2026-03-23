import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getToken } from "@/lib/auth";
import { Link } from "wouter";
import { ArrowLeft, Copy, Check, ExternalLink, ChevronDown, ChevronUp, Square } from "lucide-react";

type Lang = "auto" | "en" | "fr" | "es" | "ar";
const LANG_LABEL: Record<Lang, string> = { auto: "Auto", en: "English", fr: "Français", es: "Español", ar: "العربية" };
const isRTL = (l: Lang) => l === "ar";

type Source = {
  sid?: string;
  source_id?: string;
  id?: number;
  title?: string;
  year?: number;
  url?: string;
  doi?: string;
  doi_url?: string;
  pmid?: string;
  pubmed_url?: string;
  evidence_type?: string;
  evidence_tier?: string;
  evidence_grade?: string;
  evidence_rank?: number;
  source_tier?: "A" | "B" | "C";
  organization_or_journal?: string;
  journal?: string;
  publication_type?: string;
};

type ACIMeta = {
  aci_score?: number;
  aci_badge?: string;
  aci_components?: Record<string, number>;
  aci_rationale?: string;
};

type Sections = {
  evidenceSummary?: string;
  clinicalSummary?: string;
  keyPoints?: string[];
  safety?: string;
  limitations?: string;
  followups?: string[];
};

const EVIDENCE_TYPE_RANK: Record<string, number> = {
  "Guideline/Consensus": 1,
  "Systematic Review": 2,
  "Randomized Trial": 3,
  "Observational Study": 4,
  "Narrative Review": 5,
  "Case Report/Series": 6,
  "Other": 7,
};

const TIER_RANK: Record<string, number> = { A: 0, B: 1, C: 2 };

function getTier(s: Source): string {
  return s.source_tier || s.evidence_tier || "C";
}

function rankSources(sources: Source[]): Source[] {
  return [...sources].sort((a, b) => {
    const ta = TIER_RANK[getTier(a)] ?? 2;
    const tb = TIER_RANK[getTier(b)] ?? 2;
    if (ta !== tb) return ta - tb;
    if (a.evidence_rank != null && b.evidence_rank != null && a.evidence_rank !== b.evidence_rank)
      return a.evidence_rank - b.evidence_rank;
    const ra = EVIDENCE_TYPE_RANK[a.evidence_type || ""] ?? 7;
    const rb = EVIDENCE_TYPE_RANK[b.evidence_type || ""] ?? 7;
    if (ra !== rb) return ra - rb;
    return (b.year ?? 0) - (a.year ?? 0);
  });
}

async function ensureConversationId(): Promise<string> {
  const token = getToken();
  const r = await fetch("/api/conversations/new", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  const j = await r.json();
  if (!j?.conversation_id) throw new Error("Failed to create conversation");
  return j.conversation_id as string;
}

function parseSections(raw: string): Sections {
  const s: Sections = {};
  const t = raw || "";
  const grab = (start: RegExp, end: RegExp) => {
    const m = t.match(new RegExp(`${start.source}([\\s\\S]*?)${end.source}`, "i"));
    return m ? m[1].trim() : "";
  };

  const ev = grab(
    /\*?\*?Evidence Strength Summary\*?\*?\s*/i,
    /(Clinical Summary|Counseling Summary|Protocol-Oriented Guidance|Key Evidence-Based Points)\s*/i
  );
  if (ev) s.evidenceSummary = ev.replace(/^\*\*|\*\*$/g, "").replace(/^---+$/gm, "").trim();

  const cs = grab(
    /\*?\*?Clinical Summary\*?\*?\s*/i,
    /(Protocol-Oriented Guidance|Key Evidence-Based Points|Safety Considerations|Limitations \/ Uncertainty|Suggested Follow-up Questions)\s*/i
  );
  if (cs) s.clinicalSummary = cs;

  const kpBlock = grab(
    /\*?\*?Key Evidence-Based Points\*?\*?\s*/i,
    /(Safety Considerations|Limitations \/ Uncertainty|Suggested Follow-up Questions)\s*/i
  );
  if (kpBlock) {
    const bullets = kpBlock
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.startsWith("-"))
      .map((l) => l.replace(/^-+\s*/, "").trim())
      .filter(Boolean);
    if (bullets.length) s.keyPoints = bullets;
  }

  const sf = grab(
    /\*?\*?Safety Considerations\*?\*?\s*/i,
    /(Limitations \/ Uncertainty|Suggested Follow-up Questions)\s*/i
  );
  if (sf) s.safety = sf;

  const lim = grab(
    /\*?\*?Limitations \/ Uncertainty\*?\*?\s*/i,
    /(Suggested Follow-up Questions)\s*/i
  );
  if (lim) s.limitations = lim;

  const fu = grab(/\*?\*?Suggested Follow-up Questions\*?\*?\s*/i, /$/i);
  if (fu) {
    const lines = fu
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.startsWith("-"))
      .map((l) => l.replace(/^-+\s*/, "").trim())
      .filter(Boolean);
    if (lines.length) s.followups = lines;
  }

  return s;
}

function buildCitationLine(src: Source): string {
  const parts: string[] = [];
  if (src.title) parts.push(src.title);
  if (src.journal || src.organization_or_journal)
    parts.push((src.journal || src.organization_or_journal) as string);
  if (src.year) parts.push(String(src.year));
  if (src.doi) parts.push(`DOI:${src.doi}`);
  if (src.pmid) parts.push(`PMID:${src.pmid}`);
  return parts.join(" — ");
}

function getSourceLink(s: Source): string | null {
  if (s.url) return s.url;
  if (s.doi_url) return s.doi_url;
  if (s.pubmed_url) return s.pubmed_url;
  if (s.source_id?.includes("pmc_"))
    return `https://pmc.ncbi.nlm.nih.gov/articles/PMC${s.source_id.replace("pmc_", "")}/`;
  if (s.source_id?.startsWith("PMID_"))
    return `https://pubmed.ncbi.nlm.nih.gov/${s.source_id.replace("PMID_", "")}/`;
  return null;
}

function SourcePill({ s }: { s: Source }) {
  const href = getSourceLink(s) || "#";
  const hasLink = href !== "#";
  const title = s.title || "Untitled";
  const label = s.sid || "S?";
  const [copied, setCopied] = useState(false);

  const onCopy = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    await navigator.clipboard.writeText(buildCitationLine(s));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const tier = getTier(s);
  const tierColor = (() => {
    switch (tier) {
      case "A": return "bg-emerald-500 text-white";
      case "B": return "bg-amber-500 text-white";
      default: return "bg-slate-400 text-white";
    }
  })();

  const etColor = (() => {
    switch (s.evidence_type) {
      case "Guideline/Consensus": return "border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-950";
      case "Systematic Review": return "border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-950";
      case "Randomized Trial": return "border-violet-300 dark:border-violet-700 bg-violet-50 dark:bg-violet-950";
      case "Observational Study": return "border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950";
      case "Case Report/Series": return "border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-950";
      default: return "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800";
    }
  })();

  return (
    <div className="relative group" data-testid={`source-pill-${label}`}>
      <a
        href={href}
        target={hasLink ? "_blank" : undefined}
        rel="noreferrer"
        className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs text-slate-700 dark:text-slate-300 hover:opacity-80 transition-opacity ${etColor}`}
        title={`${title}${s.year ? ` (${s.year})` : ""}${s.evidence_type ? ` • ${s.evidence_type}` : ""} • Tier ${tier}`}
      >
        <span className="font-mono font-semibold text-slate-500 dark:text-slate-400">[{label}]</span>
        <span className={`inline-flex items-center justify-center rounded px-1 py-0 text-[9px] font-bold leading-tight ${tierColor}`}>
          {tier}
        </span>
        <span className="truncate max-w-[200px]">{title}</span>
        {s.year && <span className="text-slate-400 dark:text-slate-500">{s.year}</span>}
        {hasLink && <ExternalLink className="w-3 h-3 text-slate-400 flex-shrink-0" />}
      </a>

      <div className="pointer-events-none absolute left-0 top-8 z-30 hidden w-[360px] rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 text-xs text-slate-700 dark:text-slate-300 shadow-lg group-hover:block">
        <div className="font-semibold">{title}</div>
        <div className="mt-1 flex items-center gap-2 text-slate-500 dark:text-slate-400">
          {s.year ? `${s.year}` : "Year N/A"}
          {s.evidence_type ? ` • ${s.evidence_type}` : ""}
          <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[9px] font-bold ${tierColor}`}>
            Tier {tier}
          </span>
          {s.evidence_grade && (
            <span className="text-slate-400 dark:text-slate-500">Grade {s.evidence_grade}</span>
          )}
        </div>
        <div className="mt-1 text-slate-500 dark:text-slate-400">{s.journal || s.organization_or_journal || ""}</div>
        {s.publication_type && <div className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">Pub type: {s.publication_type}</div>}
        <div className="mt-2 flex gap-2">
          <button
            onClick={onCopy}
            className="pointer-events-auto rounded-lg border border-slate-200 dark:border-slate-600 px-2 py-1 text-xs hover:bg-slate-50 dark:hover:bg-slate-700 flex items-center gap-1"
          >
            {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
            {copied ? "Copied" : "Copy citation"}
          </button>
          {hasLink && (
            <a href={href} target="_blank" rel="noreferrer" className="pointer-events-auto rounded-lg border border-slate-200 dark:border-slate-600 px-2 py-1 text-xs hover:bg-slate-50 dark:hover:bg-slate-700 flex items-center gap-1">
              <ExternalLink className="w-3 h-3" /> Open
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function Card({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</div>
        {right}
      </div>
      <div className="mt-3 text-sm leading-6 text-slate-700 dark:text-slate-300">{children}</div>
    </div>
  );
}

function InlineCitation({ text }: { text: string }) {
  const parts = text.split(/(\[S?\d+\])/g);
  return (
    <>
      {parts.map((part, i) => {
        const m = part.match(/\[S?(\d+)\]/);
        if (m) {
          return (
            <span key={i} className="inline-flex items-center justify-center ml-0.5 px-1 py-0 rounded text-[10px] font-mono font-bold bg-primary/10 text-primary">
              S{m[1]}
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

const TOP_SOURCES = 12;

export default function AskOEStyle() {
  const [lang, setLang] = useState<Lang>("auto");
  const dir = useMemo(() => (isRTL(lang) ? "rtl" : "ltr"), [lang]);

  const [conversationId, setConversationId] = useState<string>("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [answeredAt, setAnsweredAt] = useState<Date | null>(null);

  const [raw, setRaw] = useState("");
  const [sections, setSections] = useState<Sections>({});

  const [sources, setSources] = useState<Source[]>([]);
  const [showAllSources, setShowAllSources] = useState(false);

  const [intent, setIntent] = useState<string>("general");
  const [aciMeta, setAciMeta] = useState<ACIMeta>({});

  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const cid = await ensureConversationId();
        setConversationId(cid);
      } catch {}
    })();
  }, []);

  useEffect(() => {
    setSections(parseSections(raw));
  }, [raw]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
    setStatus("Stopped.");
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (e.key === "Escape") stop();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [stop]);

  const ask = useCallback(async () => {
    const qq = q.trim();
    if (!qq || !conversationId) return;

    setStreaming(true);
    setStatus("Searching evidence…");
    setRaw("");
    setSources([]);
    setShowAllSources(false);
    setIntent("general");
    setAciMeta({});
    setAnsweredAt(null);

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    const token = getToken();
    const body: Record<string, unknown> = {
      question: qq,
      domain: "aesthetic_medicine",
      mode: "standard",
      conversation_id: conversationId,
    };
    if (lang !== "auto") body.lang = lang;

    try {
      const resp = await fetch("/api/v2/stream", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
        signal: ac.signal,
      });

      if (!resp.ok || !resp.body) {
        setStreaming(false);
        const j = await resp.json().catch(() => null);
        setRaw(j?.detail || "Failed to start stream.");
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const dataStr = line.slice(6).trim();
          if (!dataStr) continue;

          try {
            const payload = JSON.parse(dataStr);
            const t = payload.type;

            if (t === "status") {
              setStatus(payload.message || "");
            } else if (t === "content") {
              setRaw((prev) => prev + (payload.data || ""));
            } else if (t === "citations") {
              const citList = (payload.data || []).map((c: any, i: number) => ({
                ...c,
                sid: `S${i + 1}`,
                source_tier: c.source_tier || c.evidence_tier || undefined,
                evidence_tier: c.evidence_tier || undefined,
                evidence_grade: c.evidence_grade || undefined,
                evidence_rank: c.evidence_rank ?? undefined,
                publication_type: c.publication_type || undefined,
              }));
              setSources(citList);
            } else if (t === "replace") {
              if (payload.message === "Verified answer:") {
                setRaw("");
              }
            } else if (t === "meta") {
              const d = payload.data || payload;
              const intentVal = d.intent;
              if (intentVal) setIntent(intentVal);
              if (d.aci_score !== undefined) {
                setAciMeta({
                  aci_score: d.aci_score,
                  aci_badge: d.aci_badge,
                  aci_components: d.aci_components,
                  aci_rationale: d.aci_rationale,
                });
              }
            } else if (t === "error") {
              setStatus(payload.message || "Error");
              setStreaming(false);
              abortRef.current = null;
              return;
            } else if (t === "done") {
              setStreaming(false);
              setStatus("");
              setAnsweredAt(new Date());
              abortRef.current = null;
              return;
            }
          } catch {}
        }
      }

      setStreaming(false);
      setAnsweredAt(new Date());
      abortRef.current = null;
    } catch (e: any) {
      if (e?.name === "AbortError") return;
      setStreaming(false);
      setStatus(e?.message || "Stream error");
    }
  }, [conversationId, lang, q]);

  const onTextareaKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask();
    }
  };

  const rankedSources = useMemo(() => rankSources(sources), [sources]);
  const shownSources = useMemo(() => {
    if (showAllSources) return rankedSources;
    return rankedSources.slice(0, TOP_SOURCES);
  }, [rankedSources, showAllSources]);
  const hiddenCount = rankedSources.length - TOP_SOURCES;

  const hasAnswer = sections.clinicalSummary || sections.keyPoints || sections.safety || sections.limitations;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100" dir={dir} lang={lang === "auto" ? undefined : lang}>
      <header className="border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
        <div className="mx-auto max-w-6xl px-4 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link href="/ask">
              <button className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors" title="Back to main view" data-testid="button-back-main">
                <ArrowLeft className="w-4 h-4" />
              </button>
            </Link>
            <div className="text-lg font-semibold">AesthetiCite</div>
            <div className="text-sm text-slate-500 dark:text-slate-400 hidden sm:block">Structured Evidence View</div>
          </div>

          <div className="flex items-center gap-2">
            <div className="hidden sm:block text-xs text-slate-500 dark:text-slate-400">Language</div>
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value as Lang)}
              className="rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-slate-400 dark:text-slate-100"
              data-testid="select-language"
            >
              {Object.entries(LANG_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
            {streaming && (
              <button onClick={stop} className="rounded-xl border border-slate-300 dark:border-slate-600 px-4 py-2 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 flex items-center gap-1.5" data-testid="button-stop">
                <Square className="w-3 h-3" /> Stop
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-sm font-semibold">Ask a clinical question</div>
              <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">Enter submit · Shift+Enter newline · Ctrl/Cmd+K focus · Esc stop</div>
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400">{conversationId ? "Session ready" : "Connecting…"}</div>
          </div>

          <div className="mt-4">
            <textarea
              ref={inputRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={onTextareaKeyDown}
              rows={3}
              placeholder="e.g., Recommended hyaluronidase dosing approach for suspected HA vascular occlusion"
              className="w-full resize-y rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-slate-400 dark:text-slate-100 dark:placeholder-slate-400"
              data-testid="input-question"
            />
          </div>

          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-xs text-slate-500 dark:text-slate-400">
              {status || "Structured output with inline citations. No cite → no claim."}
              {streaming && <span className="ml-2 inline-block w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />}
            </div>
            <div className="flex gap-2">
              <button
                onClick={ask}
                disabled={streaming || !q.trim() || !conversationId}
                className="rounded-xl bg-slate-900 dark:bg-slate-100 px-5 py-2 text-sm text-white dark:text-slate-900 disabled:opacity-50 hover:bg-slate-800 dark:hover:bg-slate-200 transition-colors"
                data-testid="button-ask"
              >
                Ask
              </button>
              <button
                onClick={() => {
                  setQ("");
                  setRaw("");
                  setSources([]);
                  setStatus("");
                  setIntent("general");
                  setAnsweredAt(null);
                }}
                className="rounded-xl border border-slate-300 dark:border-slate-600 px-4 py-2 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                data-testid="button-clear"
              >
                Clear
              </button>
            </div>
          </div>

          {intent === "complication" && (
            <div className="mt-4 rounded-2xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950 p-4 text-sm text-amber-900 dark:text-amber-200" data-testid="banner-complication">
              <div className="font-semibold">Complication Mode</div>
              <div className="mt-1 text-amber-800 dark:text-amber-300">
                Output prioritizes conservative, protocol-oriented guidance with explicit uncertainty and strict citations.
              </div>
            </div>
          )}
        </div>

        {sources.length > 0 && (
          <div className="mt-5 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4 shadow-sm" data-testid="section-sources-oe">
            <div className="flex items-center justify-between gap-4">
              <div className="text-xs font-semibold text-slate-700 dark:text-slate-300">Sources</div>
              <div className="text-xs text-slate-500 dark:text-slate-400">
                Used: <span className="font-semibold text-slate-700 dark:text-slate-300">{sources.length}</span>
                {hiddenCount > 0 && !showAllSources ? ` · ${hiddenCount} more` : ""}
              </div>
            </div>

            {(() => {
              const tierCounts = { A: 0, B: 0, C: 0 };
              const typeCounts: Record<string, number> = {};
              sources.forEach((s: any) => {
                const tier = s.evidence_tier || s.tier || "C";
                if (tier === "A") tierCounts.A++;
                else if (tier === "B") tierCounts.B++;
                else tierCounts.C++;
                const et = s.evidence_type || s.publication_type || "Other";
                typeCounts[et] = (typeCounts[et] || 0) + 1;
              });
              const typeEntries = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]);
              return (
                <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="tier-distribution-summary">
                  {tierCounts.A > 0 && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-300">
                      Tier A: {tierCounts.A}
                    </span>
                  )}
                  {tierCounts.B > 0 && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 px-2 py-0.5 text-[10px] font-semibold text-blue-700 dark:text-blue-300">
                      Tier B: {tierCounts.B}
                    </span>
                  )}
                  {tierCounts.C > 0 && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
                      Tier C: {tierCounts.C}
                    </span>
                  )}
                  <span className="text-slate-300 dark:text-slate-600">|</span>
                  {typeEntries.slice(0, 4).map(([type, count]) => (
                    <span key={type} className="inline-flex items-center gap-1 rounded-full bg-slate-100 dark:bg-slate-700 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:text-slate-300" data-testid={`evidence-type-chip-${type}`}>
                      {type} ({count})
                    </span>
                  ))}
                </div>
              );
            })()}

            <div className="mt-3 flex flex-wrap gap-2">
              {shownSources.map((s, i) => (
                <SourcePill key={`${s.source_id || s.sid || ""}-${i}`} s={s} />
              ))}
            </div>

            {hiddenCount > 0 && (
              <div className="mt-3">
                <button
                  onClick={() => setShowAllSources((v) => !v)}
                  className="flex items-center gap-1.5 text-xs text-primary hover:text-primary/80 font-medium transition-colors"
                  data-testid="button-toggle-sources"
                >
                  {showAllSources ? (
                    <><ChevronUp className="w-3.5 h-3.5" /> Show top {TOP_SOURCES} only</>
                  ) : (
                    <><ChevronDown className="w-3.5 h-3.5" /> Show {hiddenCount} more sources used</>
                  )}
                </button>
              </div>
            )}
          </div>
        )}

        <div className="mt-5 grid gap-5 lg:grid-cols-[1.4fr_0.6fr]">
          <div className="space-y-5">
            {sections.clinicalSummary && (
              <Card title="Clinical Summary">
                <div className="whitespace-pre-wrap"><InlineCitation text={sections.clinicalSummary} /></div>
              </Card>
            )}

            {sections.keyPoints?.length ? (
              <Card title="Key Evidence-Based Points">
                <ul className="space-y-2">
                  {sections.keyPoints.map((p, i) => (
                    <li key={i} className="leading-6 flex gap-2">
                      <span className="text-slate-400 dark:text-slate-500 select-none">•</span>
                      <span><InlineCitation text={p} /></span>
                    </li>
                  ))}
                </ul>
              </Card>
            ) : null}

            {sections.safety && (
              <Card title="Safety Considerations">
                <div className="whitespace-pre-wrap"><InlineCitation text={sections.safety} /></div>
              </Card>
            )}

            {sections.limitations && (
              <Card title="Limitations / Uncertainty">
                <div className="whitespace-pre-wrap"><InlineCitation text={sections.limitations} /></div>
              </Card>
            )}

            {sections.followups?.length ? (
              <Card title="Suggested Follow-up Questions">
                <div className="flex flex-wrap gap-2">
                  {sections.followups.slice(0, 6).map((f, i) => (
                    <button
                      key={i}
                      onClick={() => setQ(f)}
                      className="rounded-full border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-1 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-600 transition-colors"
                      data-testid={`button-followup-${i}`}
                    >
                      {f}
                    </button>
                  ))}
                </div>
              </Card>
            ) : null}

            {raw && !hasAnswer && !streaming && (
              <Card title="Answer">
                <div className="whitespace-pre-wrap"><InlineCitation text={raw} /></div>
              </Card>
            )}

            {streaming && !hasAnswer && (
              <Card title="Answer">
                <div className="whitespace-pre-wrap">
                  <InlineCitation text={raw} />
                  <span className="inline-block w-2 h-5 bg-primary animate-pulse ml-0.5 align-middle" />
                </div>
              </Card>
            )}
          </div>

          <div className="lg:sticky lg:top-24 h-fit space-y-4">
            <Card title="Evidence Strength Summary">
              {aciMeta.aci_score !== undefined ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">{aciMeta.aci_score}/10</div>
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                      aciMeta.aci_badge === "High" ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200" :
                      aciMeta.aci_badge === "Moderate" ? "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200" :
                      "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                    }`}>
                      {aciMeta.aci_badge}
                    </span>
                  </div>
                  {aciMeta.aci_components && (
                    <div className="space-y-1.5 text-xs text-slate-600 dark:text-slate-400">
                      {Object.entries(aciMeta.aci_components).map(([key, val]) => (
                        <div key={key} className="flex items-center gap-2">
                          <div className="w-24 truncate capitalize">{key.replace(/_/g, " ")}</div>
                          <div className="flex-1 bg-slate-100 dark:bg-slate-700 rounded-full h-1.5 overflow-hidden">
                            <div className="bg-primary h-full rounded-full" style={{ width: `${Math.round((val as number) * 100)}%` }} />
                          </div>
                          <div className="w-8 text-right font-mono">{typeof val === "number" ? val.toFixed(2) : val}</div>
                        </div>
                      ))}
                    </div>
                  )}
                  {aciMeta.aci_rationale && (
                    <div className="text-xs text-slate-500 dark:text-slate-400 italic">{aciMeta.aci_rationale}</div>
                  )}
                </div>
              ) : sections.evidenceSummary ? (
                <div className="whitespace-pre-wrap text-slate-700 dark:text-slate-300">
                  {sections.evidenceSummary.split("\n").map((line, i) => {
                    const cleaned = line.replace(/^[-*]\s*/, "").trim();
                    if (!cleaned) return null;
                    return <div key={i} className="py-0.5">{line.startsWith("-") ? `• ${cleaned}` : cleaned}</div>;
                  })}
                </div>
              ) : (
                <div className="text-sm text-slate-500 dark:text-slate-400">Ask a question to see confidence, highest evidence, mix, and gaps.</div>
              )}
            </Card>

            <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4 shadow-sm">
              <div className="text-xs font-semibold text-slate-700 dark:text-slate-300">Governance cues</div>
              <ul className="mt-2 space-y-1 text-xs text-slate-600 dark:text-slate-400">
                <li>• No cite → no claim</li>
                <li>• Explicit uncertainty</li>
                <li>• Evidence gaps shown</li>
                <li>• Conservative language</li>
              </ul>
            </div>

            {answeredAt && (
              <div className="text-[11px] text-slate-400 dark:text-slate-500" data-testid="text-generated-date">
                Generated {answeredAt.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
              </div>
            )}

            <div className="text-[11px] text-slate-400 dark:text-slate-500" data-testid="text-disclaimer-oe">
              AI-generated summary for informational purposes only. Not a substitute for professional medical judgment. Always verify against primary sources.
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
