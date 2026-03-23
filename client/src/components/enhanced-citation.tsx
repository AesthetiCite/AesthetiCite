import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ExternalLink, BookOpen, Calendar, User, FileText, ChevronDown, ChevronUp } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface EnhancedCitationProps {
  index: number;
  title: string;
  source?: string;
  url?: string;
  year?: number;
  authors?: string;
  tier?: string;
  studyType?: string;
  quote?: string;
  sourceLanguage?: string;
}

const tierColors: { [key: string]: string } = {
  A: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  B: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  C: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
  UNKNOWN: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200",
};

const tierDescriptions: { [key: string]: string } = {
  A: "High quality: RCT, Meta-analysis, Systematic Review",
  B: "Moderate quality: Cohort study, Case-control",
  C: "Limited quality: Case report, Expert opinion",
  UNKNOWN: "Evidence tier not determined",
};

export function EnhancedCitation({
  index,
  title,
  source,
  url,
  year,
  authors,
  tier,
  studyType,
  quote,
  sourceLanguage,
}: EnhancedCitationProps) {
  const [expanded, setExpanded] = useState(false);

  const getPubMedLink = () => {
    if (url && url.includes("pubmed")) return url;
    if (url && url.includes("ncbi.nlm.nih.gov")) return url;
    // Try to construct a search link
    return `https://pubmed.ncbi.nlm.nih.gov/?term=${encodeURIComponent(title)}`;
  };

  return (
    <TooltipProvider>
      <Card className="overflow-hidden hover-elevate" data-testid={`citation-card-${index}`}>
        <CardContent className="p-3">
          <div className="flex items-start gap-3">
            {/* Citation Number */}
            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center">
              <span className="text-xs font-medium text-primary">{index}</span>
            </div>

            <div className="flex-1 min-w-0">
              {/* Header with badges */}
              <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
                {tier && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge variant="outline" className={`text-xs ${tierColors[tier] || tierColors.UNKNOWN}`}>
                        Tier {tier}
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>{tierDescriptions[tier] || tierDescriptions.UNKNOWN}</p>
                    </TooltipContent>
                  </Tooltip>
                )}
                {studyType && (
                  <Badge variant="secondary" className="text-xs">
                    {studyType}
                  </Badge>
                )}
                {year && (
                  <Badge variant="outline" className="text-xs">
                    <Calendar className="h-3 w-3 mr-1" />
                    {year}
                  </Badge>
                )}
                {sourceLanguage && sourceLanguage !== "en" && (
                  <Badge variant="outline" className="text-xs uppercase">
                    {sourceLanguage}
                  </Badge>
                )}
              </div>

              {/* Title */}
              <h4 className="text-sm font-medium leading-tight line-clamp-2 mb-1">
                {title}
              </h4>

              {/* Source and Authors */}
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                {source && (
                  <span className="flex items-center gap-1">
                    <BookOpen className="h-3 w-3" />
                    {source}
                  </span>
                )}
                {authors && (
                  <span className="flex items-center gap-1">
                    <User className="h-3 w-3" />
                    {authors}
                  </span>
                )}
              </div>

              {/* Quote Preview (expandable) */}
              {quote && (
                <div className="mt-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs"
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
                    <div className="mt-2 p-2 bg-muted/50 rounded text-xs italic text-muted-foreground">
                      "{quote}"
                    </div>
                  )}
                </div>
              )}

              {/* Links */}
              <div className="flex items-center gap-2 mt-2">
                {url && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-6 px-2 text-xs"
                    asChild
                  >
                    <a href={url} target="_blank" rel="noopener noreferrer" data-testid={`link-source-${index}`}>
                      <ExternalLink className="h-3 w-3 mr-1" />
                      View Source
                    </a>
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs"
                  asChild
                >
                  <a href={getPubMedLink()} target="_blank" rel="noopener noreferrer" data-testid={`link-pubmed-${index}`}>
                    PubMed
                  </a>
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}
