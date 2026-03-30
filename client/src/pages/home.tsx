import { useState, useCallback, useEffect } from "react";
import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StreamingResults } from "@/components/streaming-results";
import { LoadingSkeleton } from "@/components/loading-skeleton";
import { ClinicalToolsPanel, ClinicalToolsTrigger } from "@/components/clinical-tools-panel";
import { MobileBottomNav } from "@/components/mobile-bottom-nav";
import { ThemeToggle } from "@/components/theme-toggle";
import { LanguageSelector } from "@/components/language-selector";
import { useLocale } from "@/hooks/use-locale";
import { useDeviceType } from "@/hooks/use-mobile";
import { Search, ArrowRight, Loader2, BookOpen, Languages, ShieldCheck, Zap } from "lucide-react";
import type { Citation } from "@shared/schema";
import type { QueryMeta, ComplicationProtocol, InlineTool } from "@/lib/auth";

function useCorpusLabel() {
  const [label, setLabel] = useState("1.9M+ publications");
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    fetch("/api/corpus/stats", { signal: controller.signal })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        const n = d?.state?.papers_inserted ?? d?.papers_inserted;
        if (typeof n === "number" && n > 0) {
          const formatted = n >= 1_000_000
            ? `${(n / 1_000_000).toFixed(2)}M+ publications`
            : `${(Math.floor(n / 1000) * 1000).toLocaleString()}+ publications`;
          setLabel(formatted);
        }
      })
      .catch(() => {})
      .finally(() => clearTimeout(timer));
  }, []);
  return label;
}

const SUGGESTED = [
  "Hyaluronic acid vascular occlusion: management protocol and hyaluronidase dosing",
  "Botulinum toxin resistance: causes, assessment, and management strategies",
  "GLP-1 agonists and facial volume loss: aesthetic implications of semaglutide",
  "Delayed inflammatory reactions after dermal filler: diagnosis and treatment",
  "Skin booster vs dermal filler: evidence for biostimulator mechanisms",
];

export default function Home() {
  const { locale, direction, t } = useLocale();
  const corpusLabel = useCorpusLabel();
  const STATS = [
    { icon: BookOpen, label: corpusLabel },
    { icon: Languages, label: "22+ languages" },
    { icon: ShieldCheck, label: "Evidence graded" },
    { icon: Zap, label: "Real-time citations" },
  ];
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [streamContent, setStreamContent] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [relatedQuestions, setRelatedQuestions] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showTools, setShowTools] = useState(false);
  const [evidenceBadge, setEvidenceBadge] = useState<{
    score: number;
    badge: "High" | "Moderate" | "Low";
    badge_color: "green" | "yellow" | "red";
    types: Record<string, number>;
    why: string;
    unique_sources: number;
  } | null>(null);
  const [aciScore, setAciScore] = useState<number | null>(null);
  const [queryMeta, setQueryMeta] = useState<QueryMeta | null>(null);
  const [complicationProtocol, setComplicationProtocol] = useState<ComplicationProtocol | null>(null);
  const [inlineTools, setInlineTools] = useState<InlineTool[]>([]);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string>("");
  const { isMobileOrTablet, isTouch } = useDeviceType();

  const resetSearch = useCallback(() => {
    setQuery("");
    setIsLoading(false);
    setIsStreaming(false);
    setHasSearched(false);
    setStreamContent("");
    setCitations([]);
    setRelatedQuestions([]);
    setError(null);
    setEvidenceBadge(null);
    setAciScore(null);
    setQueryMeta(null);
    setComplicationProtocol(null);
    setInlineTools([]);
    setStatusMessage(null);
    setConversationId("");
  }, []);

  const handleSearch = useCallback(async (searchQuery: string) => {
    setQuery(searchQuery);
    setIsLoading(true);
    setIsStreaming(true);
    setHasSearched(true);
    setStreamContent("");
    setCitations([]);
    setRelatedQuestions([]);
    setError(null);
    setEvidenceBadge(null);
    setAciScore(null);
    setQueryMeta(null);
    setComplicationProtocol(null);
    setInlineTools([]);
    setStatusMessage(null);

    try {
      let activeConvId = conversationId;
      if (!activeConvId) {
        try {
          const convRes = await fetch("/api/conversations/new", { method: "POST" });
          if (convRes.ok) {
            const convData = await convRes.json();
            activeConvId = convData.conversation_id || "";
            setConversationId(activeConvId);
          }
        } catch {
          activeConvId = "";
        }
      }

      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery, conversation_id: activeConvId, lang: locale }),
      });

      if (!response.ok) {
        throw new Error("Search failed");
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      let previewContent = "";
      let replaced = false;

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
                if (!replaced) {
                  setStatusMessage(event.message || event.data?.message || null);
                }
                break;
              case "preview":
                if (replaced) break;
                previewContent = typeof event.data === "string" ? event.data : previewContent + (event.data || "");
                setStreamContent(previewContent);
                setIsLoading(false);
                break;
              case "replace":
                replaced = true;
                fullContent = "";
                previewContent = "";
                setStreamContent("");
                setStatusMessage(null);
                break;
              case "content":
                fullContent += event.data;
                setStreamContent(fullContent);
                setIsLoading(false);
                setStatusMessage(null);
                break;
              case "citations":
                setCitations(event.data);
                break;
              case "related":
                setRelatedQuestions(event.data);
                break;
              case "evidence_badge":
                setEvidenceBadge(event.data);
                break;
              case "meta":
                if (event.aci_score !== undefined) {
                  const raw = event.aci_score;
                  setAciScore(raw && typeof raw === 'object' ? raw.overall_confidence_0_10 : raw);
                }
                if (event.query_meta) setQueryMeta(event.query_meta);
                if (event.complication_protocol) setComplicationProtocol(event.complication_protocol);
                if (event.inline_tools) setInlineTools(event.inline_tools);
                break;
              case "done":
                setIsStreaming(false);
                setStatusMessage(null);
                break;
              case "error":
                throw new Error(event.message || event.data?.message || "Search failed");
            }
          } catch (e) {
            if (!(e instanceof SyntaxError)) {
              console.error("Stream error:", e);
            }
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
      setIsLoading(false);
      setIsStreaming(false);
    }
  }, [conversationId, locale]);

  const handleRelatedQuestionClick = (question: string) => {
    handleSearch(question);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim() && !isLoading) {
      handleSearch(query.trim());
    }
  };

  return (
    <div className={`min-h-screen bg-background ${isMobileOrTablet ? "pb-16" : ""}`} dir={direction} lang={locale}>
      <header className="sticky top-0 z-50 border-b bg-background/90 backdrop-blur" data-testid="header">
        <div className="mx-auto max-w-4xl px-4 py-3 flex items-center justify-between gap-4">
          <button onClick={resetSearch} className="flex items-center gap-3 cursor-pointer" data-testid="button-home">
            <img
              src="/aestheticite-logo.png"
              alt="AesthetiCite"
              className="h-10 w-10 rounded-lg object-contain flex-shrink-0"
              data-testid="img-logo"
            />
            <div className="leading-tight text-left">
              <div className="text-sm font-semibold" data-testid="text-brand">AesthetiCite</div>
              <div className="text-xs text-muted-foreground hidden sm:block">Evidence-first AI for aesthetic medicine</div>
            </div>
          </button>

          <div className="flex items-center gap-2">
            <LanguageSelector />
            <ThemeToggle />
            <Link href="/login">
              <Button variant="outline" size="sm" data-testid="button-sign-in">
                {t('search.signIn')}
              </Button>
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-10">
        {!hasSearched ? (
          <div className={`flex flex-col items-center ${isMobileOrTablet ? "pt-4" : "pt-10"}`}>
            <img
              src="/aestheticite-logo.png"
              alt="AesthetiCite"
              className={`object-contain mb-4 ${isMobileOrTablet ? "h-20" : "h-28"}`}
              data-testid="img-hero-logo"
            />
            <h1 className={`font-semibold tracking-tight text-center ${isMobileOrTablet ? "text-2xl mb-2" : "text-3xl md:text-4xl mb-3"}`} data-testid="text-hero-title">
              {t('home.title')}
            </h1>
            <p className="text-muted-foreground text-center max-w-xl mb-6" data-testid="text-hero-subtitle">
              {t('home.tagline')}
            </p>

            {/* Stats strip */}
            <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 mb-8">
              {STATS.map(({ icon: Icon, label }) => (
                <div key={label} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Icon className="h-3.5 w-3.5 text-primary/70" />
                  <span>{label}</span>
                </div>
              ))}
            </div>

            {/* Search form — always LTR layout so button stays on the right */}
            <form onSubmit={handleSubmit} className="w-full max-w-2xl mb-2" data-testid="form-search">
              <div className="relative flex items-center">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none z-10" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={t('search.placeholder')}
                  className="w-full rounded-xl border border-input bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring pl-10 pr-36 py-3.5 text-sm"
                  autoFocus={!isMobileOrTablet}
                  data-testid="input-search"
                  dir="auto"
                />
                <Button
                  type="submit"
                  disabled={!query.trim() || isLoading}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-1.5 px-4 h-8 text-sm rounded-lg"
                  data-testid="button-search-submit"
                >
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <span>Search</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </Button>
              </div>
            </form>
            <p className="w-full max-w-2xl text-xs text-muted-foreground mb-8" data-testid="text-cite-rule">
              {t('home.citeRule')}
            </p>

            <div className="w-full max-w-2xl">
              <div className="text-xs text-muted-foreground mb-3 font-medium uppercase tracking-wide">{t('search.suggested')}</div>
              <div className="flex flex-col gap-2" data-testid="section-suggested">
                {SUGGESTED.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => { setQuery(q); handleSearch(q); }}
                    className="text-left text-sm text-foreground hover-elevate rounded-xl border px-4 py-3 flex items-center justify-between gap-2 transition-colors hover:bg-muted/50"
                    data-testid={`button-suggested-${i}`}
                  >
                    <span>{q}</span>
                    <ArrowRight className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground/50" />
                  </button>
                ))}
              </div>
            </div>

            {/* Clinical tools callout — visible on desktop below suggestions */}
            {!isMobileOrTablet && (
              <div className="w-full max-w-2xl mt-8 rounded-xl border bg-muted/30 px-4 py-3 flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm font-medium mb-0.5">Clinical Calculators</div>
                  <div className="text-xs text-muted-foreground">BMI · BSA · eGFR · Unit Converter — available bottom right</div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowTools(true)}
                  data-testid="button-open-tools-callout"
                >
                  Open tools
                </Button>
              </div>
            )}

            <p className="mt-8 text-xs text-muted-foreground text-center max-w-md" data-testid="text-disclaimer">
              {t('home.disclaimer')}
            </p>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto">
            {/* Results search bar — button always on the right */}
            <form onSubmit={handleSubmit} className="mb-8" data-testid="form-search-results">
              <div className="relative flex items-center">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none z-10" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={t('search.followUp')}
                  className="w-full rounded-xl border border-input bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring pl-10 pr-36 py-3.5 text-sm"
                  data-testid="input-search-again"
                  dir="auto"
                />
                <Button
                  type="submit"
                  disabled={!query.trim() || isLoading || isStreaming}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-1.5 px-4 h-8 text-sm rounded-lg"
                  data-testid="button-search-again"
                >
                  {isLoading || isStreaming ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <span>Search</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </Button>
              </div>
            </form>

            {error ? (
              <Card className="p-6 text-center" data-testid="card-error">
                <p className="text-destructive mb-4" data-testid="text-error">{error}</p>
                <Button variant="outline" onClick={() => handleSearch(query)} data-testid="button-retry">
                  {t('search.tryAgain')}
                </Button>
              </Card>
            ) : isLoading && !streamContent ? (
              <div>
                {statusMessage ? (
                  <div className="flex items-center gap-2 mb-4 text-muted-foreground" data-testid="text-status-message">
                    <span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse" />
                    <span className="text-sm">{statusMessage}</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 mb-4 text-muted-foreground" data-testid="text-loading">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="text-sm">{t('search.retrieving')}</span>
                  </div>
                )}
                <LoadingSkeleton />
              </div>
            ) : streamContent ? (
              <StreamingResults
                content={streamContent}
                citations={citations}
                relatedQuestions={relatedQuestions}
                isStreaming={isStreaming}
                onRelatedQuestionClick={handleRelatedQuestionClick}
                evidenceBadge={evidenceBadge || undefined}
                aciScore={aciScore ?? undefined}
                queryMeta={queryMeta ?? undefined}
                complicationProtocol={complicationProtocol ?? undefined}
                inlineTools={inlineTools}
              />
            ) : null}
          </div>
        )}
      </main>

      {!hasSearched && !isMobileOrTablet && (
        <footer className="border-t mt-8" data-testid="footer">
          <div className="mx-auto max-w-4xl px-4 py-6">
            <div className="text-xs text-muted-foreground">
              {t('home.disclaimer')}
            </div>
          </div>
        </footer>
      )}

      <ClinicalToolsPanel isOpen={showTools} onClose={() => setShowTools(false)} />
      {!showTools && !isMobileOrTablet && (
        <ClinicalToolsTrigger onClick={() => setShowTools(true)} />
      )}

      <MobileBottomNav
        onHomeClick={resetSearch}
        onSearchClick={() => {
          if (hasSearched) {
            window.scrollTo({ top: 0, behavior: "smooth" });
          }
        }}
        onToolsClick={() => setShowTools(true)}
        onFavoritesClick={() => {}}
        activeTab={hasSearched ? "search" : "home"}
      />
    </div>
  );
}
