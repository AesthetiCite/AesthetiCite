import { useState } from "react";
import { ChevronDown, ChevronUp, BookOpen, HelpCircle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CitationCard } from "./citation-card";
import type { SearchResponse, Citation } from "@shared/schema";

interface ResultsDisplayProps {
  response: SearchResponse;
  onRelatedQuestionClick: (question: string) => void;
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
          data-testid={`citation-ref-${citationNum}`}
        >
          {citationNum}
        </span>
      );
    }
    return <span key={index}>{part}</span>;
  });
}

function AnswerContent({ content }: { content: string }) {
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
    </div>
  );
}

export function ResultsDisplay({ response, onRelatedQuestionClick }: ResultsDisplayProps) {
  const [showAllCitations, setShowAllCitations] = useState(false);
  
  const displayedCitations = showAllCitations 
    ? response.citations 
    : response.citations.slice(0, 4);

  return (
    <div className="w-full max-w-4xl mx-auto space-y-6">
      <Card className="p-6 md:p-8" data-testid="card-answer">
        <AnswerContent content={response.answer} />
      </Card>

      {response.citations.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-primary" />
              <h3 className="font-semibold text-lg">Sources</h3>
              <span className="text-sm text-muted-foreground">
                ({response.citations.length} references)
              </span>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {displayedCitations.map((citation, index) => (
              <CitationCard key={citation.id} citation={citation} index={index} />
            ))}
          </div>
          
          {response.citations.length > 4 && (
            <Button
              variant="ghost"
              onClick={() => setShowAllCitations(!showAllCitations)}
              className="w-full"
              data-testid="button-toggle-citations"
            >
              {showAllCitations ? (
                <>
                  <ChevronUp className="w-4 h-4 mr-2" />
                  Show fewer sources
                </>
              ) : (
                <>
                  <ChevronDown className="w-4 h-4 mr-2" />
                  Show all {response.citations.length} sources
                </>
              )}
            </Button>
          )}
        </div>
      )}

      {response.relatedQuestions.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-primary" />
            <h3 className="font-semibold text-lg">Related questions</h3>
          </div>
          
          <div className="grid grid-cols-1 gap-2">
            {response.relatedQuestions.map((question, index) => (
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
