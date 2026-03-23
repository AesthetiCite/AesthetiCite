import { useState, useMemo } from "react";
import { BookOpen, HelpCircle, ChevronDown, ChevronUp } from "lucide-react";
import { Card } from "@/components/ui/card";
import { CitationCard } from "./citation-card";
import { EvidenceBadge } from "./evidence-badge";
import { ACIScoreDisplay } from "./aci-score-display";
import { ComplicationProtocolAlert } from "./complication-protocol-alert";
import { InlineToolsDisplay } from "./inline-tools-display";
import { useDeviceType } from "@/hooks/use-mobile";
import type { Citation } from "@shared/schema";
import type { QueryMeta, ComplicationProtocol, InlineTool } from "@/lib/auth";

interface EvidenceBadgeData {
  score: number;
  badge: "High" | "Moderate" | "Low";
  badge_color: "green" | "yellow" | "red";
  types: Record<string, number>;
  why: string;
  unique_sources: number;
}

interface StreamingResultsProps {
  content: string;
  citations: Citation[];
  relatedQuestions: string[];
  isStreaming: boolean;
  onRelatedQuestionClick: (question: string) => void;
  evidenceBadge?: EvidenceBadgeData;
  aciScore?: number;
  queryMeta?: QueryMeta;
  complicationProtocol?: ComplicationProtocol;
  inlineTools?: InlineTool[];
}

function parseContentWithCitations(content: string): React.ReactNode[] {
  const parts = content.split(/(\[\d+\])/g);
  return parts.map((part, index) => {
    const match = part.match(/\[(\d+)\]/);
    if (match) {
      const citationNum = parseInt(match[1]);
      return (
        <span
          key={index}
          className="citation-link"
          title={`Citation ${citationNum}`}
        >
          {citationNum}
        </span>
      );
    }
    return <span key={index}>{part}</span>;
  });
}

function StreamingContent({ content, isStreaming }: { content: string; isStreaming: boolean }) {
  const paragraphs = content.split("\n\n").filter(Boolean);
  
  return (
    <div className="prose-evidence">
      {paragraphs.map((paragraph, index) => {
        if (paragraph.startsWith("# ")) {
          return <h1 key={index} className="text-xl font-semibold mt-6 mb-3">{parseContentWithCitations(paragraph.slice(2))}</h1>;
        }
        if (paragraph.startsWith("## ")) {
          return <h2 key={index} className="text-lg font-semibold mt-5 mb-2">{parseContentWithCitations(paragraph.slice(3))}</h2>;
        }
        if (paragraph.startsWith("### ")) {
          return <h3 key={index} className="text-base font-semibold mt-4 mb-2">{parseContentWithCitations(paragraph.slice(4))}</h3>;
        }
        if (paragraph.startsWith("- ") || paragraph.startsWith("* ")) {
          const items = paragraph.split("\n").filter(line => line.startsWith("- ") || line.startsWith("* "));
          return (
            <ul key={index} className="list-disc pl-6 my-3 space-y-1.5">
              {items.map((item, i) => (
                <li key={i} className="text-foreground/90">{parseContentWithCitations(item.slice(2))}</li>
              ))}
            </ul>
          );
        }
        if (paragraph.match(/^\d+\. /)) {
          const items = paragraph.split("\n").filter(line => line.match(/^\d+\. /));
          return (
            <ol key={index} className="list-decimal pl-6 my-3 space-y-1.5">
              {items.map((item, i) => (
                <li key={i} className="text-foreground/90">{parseContentWithCitations(item.replace(/^\d+\. /, ""))}</li>
              ))}
            </ol>
          );
        }
        return <p key={index} className="mb-4 leading-relaxed text-foreground/90">{parseContentWithCitations(paragraph)}</p>;
      })}
      {isStreaming && (
        <span className="inline-block w-2 h-5 bg-primary animate-pulse-subtle ml-0.5 align-middle" />
      )}
    </div>
  );
}

export function StreamingResults({ 
  content, 
  citations, 
  relatedQuestions,
  isStreaming,
  onRelatedQuestionClick,
  evidenceBadge,
  aciScore,
  queryMeta,
  complicationProtocol,
  inlineTools,
}: StreamingResultsProps) {
  const { isMobileOrTablet } = useDeviceType();
  
  return (
    <div className={`w-full max-w-4xl mx-auto space-y-4 ${isMobileOrTablet ? "pb-20" : ""}`}>
      {complicationProtocol?.triggered && (
        <ComplicationProtocolAlert protocol={complicationProtocol} />
      )}

      {aciScore !== undefined && aciScore !== null && (
        <ACIScoreDisplay score={aciScore} queryMeta={queryMeta} />
      )}

      {inlineTools && inlineTools.length > 0 && !isStreaming && (
        <InlineToolsDisplay tools={inlineTools} />
      )}

      <Card className="p-6 md:p-8" data-testid="card-streaming-answer">
        {evidenceBadge && !isStreaming && (
          <div className="mb-4 flex items-center gap-2">
            <EvidenceBadge data={evidenceBadge} />
          </div>
        )}
        <StreamingContent content={content} isStreaming={isStreaming} />
      </Card>

      {citations.length > 0 && !isStreaming && (
        <RankedCitationsSection citations={citations} />
      )}

      {!isStreaming && (
        <p className="text-[11px] text-muted-foreground/70 text-center leading-relaxed" data-testid="text-disclaimer">
          AI-generated summary for informational purposes only. Not a substitute for professional medical judgment. Always verify against primary sources and consult relevant clinical guidelines. Generated {new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}.
        </p>
      )}

      {relatedQuestions.length > 0 && !isStreaming && (
        <div className="space-y-4" data-testid="section-related">
          <div className="flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-primary" />
            <h3 className="font-semibold text-lg" data-testid="text-related-title">Related questions</h3>
          </div>
          
          <div className="grid grid-cols-1 gap-2" data-testid="list-related">
            {relatedQuestions.map((question, index) => (
              <button
                key={index}
                onClick={() => onRelatedQuestionClick(question)}
                className="text-left p-4 rounded-lg border bg-card hover-elevate active-elevate-2 transition-colors"
                data-testid={`button-related-${index}`}
              >
                <span className="text-sm text-foreground">{question}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const EVIDENCE_TYPE_RANK: Record<string, number> = {
  "Guideline/Consensus": 1,
  "Systematic Review": 2,
  "Randomized Trial": 3,
  "Observational Study": 4,
  "Narrative Review": 5,
  "Case Report/Series": 6,
  "Other": 7,
};

const TOP_SOURCES = 8;

function RankedCitationsSection({ citations }: { citations: Citation[] }) {
  const [expanded, setExpanded] = useState(false);
  const ranked = useMemo(() =>
    [...citations].sort((a, b) => {
      const ra = EVIDENCE_TYPE_RANK[(a as any).evidence_type] ?? 7;
      const rb = EVIDENCE_TYPE_RANK[(b as any).evidence_type] ?? 7;
      if (ra !== rb) return ra - rb;
      const ta = ((a as any).tier ?? "Z").toUpperCase();
      const tb = ((b as any).tier ?? "Z").toUpperCase();
      if (ta !== tb) return ta < tb ? -1 : 1;
      return (b.year ?? 0) - (a.year ?? 0);
    }),
    [citations]
  );
  const showToggle = ranked.length > TOP_SOURCES;
  const visible = expanded ? ranked : ranked.slice(0, TOP_SOURCES);

  return (
    <div className="space-y-4" data-testid="section-sources">
      <div className="flex items-center gap-2">
        <BookOpen className="w-5 h-5 text-primary" />
        <h3 className="font-semibold text-lg" data-testid="text-sources-title">Top Sources</h3>
        <span className="text-sm text-muted-foreground" data-testid="text-sources-count">
          ({citations.length} references)
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="list-citations">
        {visible.map((citation, index) => (
          <CitationCard key={`${citation.id}-${index}`} citation={citation} index={index} />
        ))}
      </div>

      {showToggle && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 text-sm text-primary hover:text-primary/80 transition-colors font-medium"
          data-testid="button-toggle-all-citations"
        >
          {expanded ? (
            <>
              <ChevronUp className="w-4 h-4" />
              Show top sources only
            </>
          ) : (
            <>
              <ChevronDown className="w-4 h-4" />
              Show all {ranked.length} sources
            </>
          )}
        </button>
      )}
    </div>
  );
}
