import { AlertTriangle, ShieldAlert, CircleAlert } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { ComplicationProtocol } from "@/lib/auth";

interface ComplicationProtocolAlertProps {
  protocol: ComplicationProtocol;
}

export function ComplicationProtocolAlert({ protocol }: ComplicationProtocolAlertProps) {
  if (!protocol.triggered) return null;

  return (
    <Card className="p-4 border-destructive/30 bg-destructive/5" data-testid="card-complication-protocol">
      <div className="flex items-start gap-3">
        <ShieldAlert className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0 space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-destructive" data-testid="text-protocol-title">
              Complication Protocol Active
            </span>
            <Badge variant="destructive" className="text-xs" data-testid="badge-protocol-active">
              Safety Alert
            </Badge>
          </div>

          {protocol.red_flags.length > 0 && (
            <div data-testid="section-red-flags">
              <div className="flex items-center gap-1.5 mb-1.5">
                <AlertTriangle className="w-3.5 h-3.5 text-destructive" />
                <span className="text-xs font-medium text-destructive">Red Flags to Monitor</span>
              </div>
              <ul className="space-y-1">
                {protocol.red_flags.map((flag, i) => (
                  <li key={i} className="text-xs text-foreground/80 flex items-start gap-1.5" data-testid={`text-red-flag-${i}`}>
                    <span className="text-destructive mt-0.5 flex-shrink-0">-</span>
                    <span>{flag}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {protocol.immediate_actions.length > 0 && (
            <div data-testid="section-immediate-actions">
              <div className="flex items-center gap-1.5 mb-1.5">
                <CircleAlert className="w-3.5 h-3.5 text-orange-600 dark:text-orange-400" />
                <span className="text-xs font-medium text-orange-700 dark:text-orange-300">Immediate Actions</span>
              </div>
              <ul className="space-y-1">
                {protocol.immediate_actions.map((action, i) => (
                  <li key={i} className="text-xs text-foreground/80 flex items-start gap-1.5" data-testid={`text-action-${i}`}>
                    <span className="text-orange-600 dark:text-orange-400 mt-0.5 flex-shrink-0 font-bold">{i + 1}.</span>
                    <span>{action}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
