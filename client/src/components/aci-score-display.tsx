import { Shield, AlertTriangle, TrendingUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { QueryMeta } from "@/lib/auth";

interface ACIScoreDisplayProps {
  score: number;
  queryMeta?: QueryMeta;
}

function getACIColor(score: number): string {
  if (score >= 7) return "text-green-600 dark:text-green-400";
  if (score >= 4) return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

function getACIBgColor(score: number): string {
  if (score >= 7) return "bg-green-50/50 dark:bg-green-950/20";
  if (score >= 4) return "bg-yellow-50/50 dark:bg-yellow-950/20";
  return "bg-destructive/5";
}

function getACILabel(score: number): string {
  if (score >= 8) return "Strong Evidence";
  if (score >= 6) return "Good Evidence";
  if (score >= 4) return "Moderate Evidence";
  if (score >= 2) return "Limited Evidence";
  return "Insufficient Evidence";
}

function getACIRingColor(score: number): string {
  if (score >= 7) return "stroke-green-500";
  if (score >= 4) return "stroke-yellow-500";
  return "stroke-red-500";
}

function ACIRing({ score }: { score: number }) {
  const radius = 18;
  const circumference = 2 * Math.PI * radius;
  const normalizedScore = Math.min(Math.max(score, 0), 10);
  const offset = circumference - (normalizedScore / 10) * circumference;

  return (
    <div className="relative w-12 h-12 flex-shrink-0">
      <svg className="w-12 h-12 -rotate-90" viewBox="0 0 44 44">
        <circle
          cx="22"
          cy="22"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          className="text-muted-foreground/20"
        />
        <circle
          cx="22"
          cy="22"
          r={radius}
          fill="none"
          strokeWidth="3"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className={`${getACIRingColor(score)} transition-all duration-700`}
        />
      </svg>
      <span className={`absolute inset-0 flex items-center justify-center text-xs font-bold ${getACIColor(score)}`}>
        {normalizedScore.toFixed(1)}
      </span>
    </div>
  );
}

export function ACIScoreDisplay({ score, queryMeta }: ACIScoreDisplayProps) {
  return (
    <Card className={`p-3 ${getACIBgColor(score)} border-0`} data-testid="card-aci-score">
      <div className="flex items-center gap-3">
        <ACIRing score={score} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold" data-testid="text-aci-label">
              ACI Score
            </span>
            <Badge variant="outline" className="text-xs" data-testid="badge-aci-level">
              {getACILabel(score)}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5" data-testid="text-aci-description">
            Aesthetic Confidence Index
          </p>
        </div>
        {queryMeta && (
          <div className="flex items-center gap-1.5 flex-shrink-0 flex-wrap">
            {queryMeta.risk_level === "high" && (
              <Badge variant="destructive" className="text-xs" data-testid="badge-risk-high">
                <AlertTriangle className="w-3 h-3 mr-1" />
                High Risk
              </Badge>
            )}
            {queryMeta.risk_level === "medium" && (
              <Badge variant="secondary" className="text-xs" data-testid="badge-risk-medium">
                <Shield className="w-3 h-3 mr-1" />
                Medium Risk
              </Badge>
            )}
            {queryMeta.is_injectable && (
              <Badge variant="outline" className="text-xs" data-testid="badge-injectable">
                Injectable
              </Badge>
            )}
            {queryMeta.is_device && (
              <Badge variant="outline" className="text-xs" data-testid="badge-device">
                Device
              </Badge>
            )}
          </div>
        )}
      </div>
      {queryMeta?.high_risk_zones && queryMeta.high_risk_zones.length > 0 && (
        <div className="mt-2 flex items-center gap-1.5 flex-wrap" data-testid="section-risk-zones">
          <span className="text-xs text-muted-foreground">Risk zones:</span>
          {queryMeta.high_risk_zones.map((zone, i) => (
            <Badge key={i} variant="outline" className="text-xs capitalize" data-testid={`badge-zone-${i}`}>
              {zone}
            </Badge>
          ))}
        </div>
      )}
    </Card>
  );
}
