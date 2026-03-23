import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Shield, ShieldCheck, ShieldAlert } from "lucide-react";

interface EvidenceBadgeData {
  score: number;
  badge: "High" | "Moderate" | "Low";
  badge_color: "green" | "yellow" | "red";
  types: Record<string, number>;
  why: string;
  unique_sources: number;
}

interface EvidenceBadgeProps {
  data: EvidenceBadgeData;
  size?: "sm" | "md" | "lg";
}

export function EvidenceBadge({ data, size = "md" }: EvidenceBadgeProps) {
  const getIcon = () => {
    switch (data.badge) {
      case "High":
        return <ShieldCheck className={size === "sm" ? "h-3 w-3" : "h-4 w-4"} />;
      case "Moderate":
        return <Shield className={size === "sm" ? "h-3 w-3" : "h-4 w-4"} />;
      default:
        return <ShieldAlert className={size === "sm" ? "h-3 w-3" : "h-4 w-4"} />;
    }
  };

  const getVariant = () => {
    switch (data.badge) {
      case "High":
        return "default";
      case "Moderate":
        return "secondary";
      default:
        return "outline";
    }
  };

  const getBadgeClass = () => {
    switch (data.badge) {
      case "High":
        return "bg-green-600 hover:bg-green-700 text-white";
      case "Moderate":
        return "bg-yellow-500 hover:bg-yellow-600 text-white";
      default:
        return "bg-red-500 hover:bg-red-600 text-white";
    }
  };

  const sourceTypes = Object.entries(data.types)
    .map(([type, count]) => `${type}: ${count}`)
    .join(", ");

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge 
          className={`${getBadgeClass()} gap-1 cursor-help ${size === "sm" ? "text-xs py-0" : ""}`}
          data-testid="badge-evidence-strength"
        >
          {getIcon()}
          <span>{data.badge} Evidence</span>
          <span className="opacity-75">({Math.round(data.score * 100)}%)</span>
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs" data-testid="tooltip-evidence-details">
        <div className="space-y-1">
          <p className="font-medium">{data.why}</p>
          {sourceTypes && (
            <p className="text-xs text-muted-foreground">Sources: {sourceTypes}</p>
          )}
          <p className="text-xs text-muted-foreground">
            {data.unique_sources} unique source{data.unique_sources !== 1 ? "s" : ""} analyzed
          </p>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

export function EvidenceConfidenceIndicator({ score }: { score: number }) {
  const percentage = Math.round(score * 100);
  
  const getColor = () => {
    if (score >= 0.85) return "bg-green-500";
    if (score >= 0.65) return "bg-yellow-500";
    return "bg-red-500";
  };
  
  return (
    <div className="flex items-center gap-2" data-testid="indicator-confidence">
      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
        <div 
          className={`h-full ${getColor()} transition-all duration-500`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground w-10 text-right">{percentage}%</span>
    </div>
  );
}
