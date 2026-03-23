import { useState } from "react";
import { ExternalLink, FileText, Users, ChevronDown, ChevronUp, BookOpen } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Citation } from "@shared/schema";

interface CitationCardProps {
  citation: Citation;
  index: number;
}

const evidenceLevelColors: { [key: string]: string } = {
  "Level I": "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300 border-green-300 dark:border-green-700",
  "Level II": "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300 border-emerald-300 dark:border-emerald-700",
  "Level III": "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300 border-amber-300 dark:border-amber-700",
  "Level IV": "bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300 border-orange-300 dark:border-orange-700",
  "A": "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300 border-green-300 dark:border-green-700",
  "B": "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700",
  "C": "bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300 border-orange-300 dark:border-orange-700",
};

const evidenceTypeColors: { [key: string]: string } = {
  "Guideline/Consensus": "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300 border-green-300 dark:border-green-700",
  "Systematic Review": "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300 border-emerald-300 dark:border-emerald-700",
  "Randomized Trial": "bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300 border-blue-300 dark:border-blue-700",
  "Observational Study": "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300 border-amber-300 dark:border-amber-700",
  "Case Report/Series": "bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300 border-orange-300 dark:border-orange-700",
  "Narrative Review": "bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300 border-purple-300 dark:border-purple-700",
  "Journal Article": "bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-300 border-sky-300 dark:border-sky-700",
};

const evidenceLevelDescriptions: { [key: string]: string } = {
  "Level I": "Systematic reviews, meta-analyses of RCTs",
  "Level II": "Well-designed RCTs",
  "Level III": "Observational studies, cohort studies",
  "Level IV": "Expert opinion, case reports",
  "A": "High quality: RCT, Meta-analysis, Systematic Review",
  "B": "Moderate quality: Cohort study, Case-control",
  "C": "Limited quality: Case report, Expert opinion",
};

function getEvidenceLevel(citation: Citation): string | null {
  const c = citation as any;
  if (c.evidence_level) return c.evidence_level;
  if (c.tier) return c.tier;
  
  const title = citation.title?.toLowerCase() || "";
  const source = citation.source?.toLowerCase() || "";
  
  if (title.includes("meta-analysis") || title.includes("systematic review")) {
    return "Level I";
  }
  if (title.includes("randomized") || title.includes("rct") || title.includes("controlled trial")) {
    return "Level II";
  }
  if (title.includes("cohort") || title.includes("case-control") || title.includes("prospective")) {
    return "Level III";
  }
  if (source.includes("journal") || source.includes("nejm") || source.includes("jama") || source.includes("lancet")) {
    return "Level III";
  }
  
  return null;
}

export function CitationCard({ citation, index }: CitationCardProps) {
  const [expanded, setExpanded] = useState(false);
  const evidenceLevel = getEvidenceLevel(citation);
  const quote = (citation as any).quote;
  
  const getPubMedLink = () => {
    if (citation.url && (citation.url.includes("pubmed") || citation.url.includes("ncbi"))) {
      return citation.url;
    }
    return `https://pubmed.ncbi.nlm.nih.gov/?term=${encodeURIComponent(citation.title)}`;
  };

  return (
    <TooltipProvider>
      <Card className="p-4 hover-elevate transition-colors group" data-testid={`card-citation-${index}`}>
        <div className="flex items-start gap-3">
          <div className="flex items-center justify-center rounded-full bg-primary/10 text-primary font-semibold shrink-0 w-7 h-7 text-sm">
            {index + 1}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
              {(citation as any).evidence_type && (citation as any).evidence_type !== "Other" && (
                <Badge 
                  variant="outline" 
                  className={`text-[10px] px-1.5 py-0 h-5 ${evidenceTypeColors[(citation as any).evidence_type] || "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200"}`}
                >
                  {(citation as any).evidence_type}
                </Badge>
              )}
              {evidenceLevel && !(citation as any).evidence_type && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge 
                      variant="outline" 
                      className={`text-[10px] px-1.5 py-0 h-5 ${evidenceLevelColors[evidenceLevel] || "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200"}`}
                    >
                      {evidenceLevel.length === 1 ? `Tier ${evidenceLevel}` : evidenceLevel}
                    </Badge>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <p className="text-xs">{evidenceLevelDescriptions[evidenceLevel] || "Evidence quality indicator"}</p>
                  </TooltipContent>
                </Tooltip>
              )}
              {citation.year && (
                <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5">
                  {citation.year}
                </Badge>
              )}
            </div>
            
            <h4 className="font-medium text-foreground leading-snug mb-1.5 line-clamp-2 text-sm">
              {citation.title}
            </h4>
            
            <div className="flex flex-wrap items-center gap-2 text-muted-foreground text-xs">
              <div className="flex items-center gap-1">
                <BookOpen className="w-3 h-3" />
                <span className="truncate max-w-[150px]">{citation.source}</span>
              </div>
              {citation.authors && (
                <div className="flex items-center gap-1">
                  <Users className="w-3 h-3" />
                  <span className="truncate max-w-[120px]">{citation.authors}</span>
                </div>
              )}
            </div>

            {quote && (
              <div className="mt-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setExpanded(!expanded)}
                  data-testid={`button-expand-quote-${index}`}
                >
                  <FileText className="h-3 w-3 mr-1" />
                  Key excerpt
                  {expanded ? (
                    <ChevronUp className="h-3 w-3 ml-1" />
                  ) : (
                    <ChevronDown className="h-3 w-3 ml-1" />
                  )}
                </Button>
                {expanded && (
                  <div className="mt-2 p-2.5 bg-muted/50 rounded-md text-xs italic text-muted-foreground border-l-2 border-primary/30">
                    "{quote}"
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center gap-2 mt-2">
              {citation.url && (
                <Button variant="ghost" size="sm" asChild>
                  <a
                    href={citation.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid={`link-citation-${index}`}
                  >
                    <ExternalLink className="w-3 h-3 mr-1" />
                    {citation.url.includes("doi.org") ? "DOI" : citation.url.includes("pubmed") ? "PubMed" : "View source"}
                  </a>
                </Button>
              )}
              {(!citation.url || !citation.url.includes("pubmed")) && (
                <Button variant="ghost" size="sm" asChild>
                  <a
                    href={getPubMedLink()}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid={`link-pubmed-${index}`}
                  >
                    PubMed
                  </a>
                </Button>
              )}
            </div>
          </div>
        </div>
      </Card>
    </TooltipProvider>
  );
}
