import { Wrench, Syringe, Droplets, Sun } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { InlineTool } from "@/lib/auth";

const TOOL_META: Record<string, { label: string; icon: typeof Wrench; color: string }> = {
  hyaluronidase_helper: {
    label: "Hyaluronidase Protocol",
    icon: Syringe,
    color: "text-destructive",
  },
  botox_dilution_helper: {
    label: "Botox Dilution Calculator",
    icon: Droplets,
    color: "text-primary",
  },
  fitzpatrick_laser_adjustment: {
    label: "Fitzpatrick Laser Adjustment",
    icon: Sun,
    color: "text-amber-600 dark:text-amber-400",
  },
};

function ToolResultItem({ tool }: { tool: InlineTool }) {
  const meta = TOOL_META[tool.tool] || {
    label: tool.tool.replace(/_/g, " "),
    icon: Wrench,
    color: "text-muted-foreground",
  };
  const Icon = meta.icon;
  const output = tool.output || {};

  return (
    <div className="border rounded-md p-3 space-y-2" data-testid={`tool-result-${tool.tool}`}>
      <div className="flex items-center gap-2 flex-wrap">
        <Icon className={`w-4 h-4 ${meta.color}`} />
        <span className="font-medium text-sm">{meta.label}</span>
        <Badge variant="outline" className="text-xs">Auto</Badge>
      </div>

      {tool.input && Object.keys(tool.input).length > 0 && (
        <div className="text-xs text-muted-foreground">
          {Object.entries(tool.input).map(([k, v]) => (
            <span key={k} className="mr-3">{k}: <strong>{String(v)}</strong></span>
          ))}
        </div>
      )}

      <div className="text-sm space-y-1">
        {typeof output.note === "string" && (
          <p className="text-muted-foreground italic">{output.note}</p>
        )}
        {typeof output.purpose === "string" && (
          <p className="text-foreground/90">{output.purpose}</p>
        )}
        {typeof output.risk === "string" && (
          <p className="text-foreground/90">{output.risk}</p>
        )}
        {Array.isArray(output.notes) && (
          <ul className="list-disc pl-4 space-y-0.5">
            {(output.notes as string[]).map((n: string, i: number) => (
              <li key={i} className="text-foreground/80 text-xs">{n}</li>
            ))}
          </ul>
        )}
        {Array.isArray(output.mitigation) && (
          <ul className="list-disc pl-4 space-y-0.5">
            {(output.mitigation as string[]).map((m: string, i: number) => (
              <li key={i} className="text-foreground/80 text-xs">{m}</li>
            ))}
          </ul>
        )}
        {typeof output.units_per_ml === "number" && (
          <div className="flex gap-4 text-xs">
            <span>Units/mL: <strong>{output.units_per_ml}</strong></span>
            {typeof output.units_per_0_1ml === "number" && (
              <span>Units/0.1mL: <strong>{output.units_per_0_1ml}</strong></span>
            )}
          </div>
        )}
        {typeof output.evidence_needed === "string" && (
          <p className="text-xs text-muted-foreground mt-1">Evidence needed: {output.evidence_needed}</p>
        )}
      </div>
    </div>
  );
}

interface InlineToolsDisplayProps {
  tools: InlineTool[];
}

export function InlineToolsDisplay({ tools }: InlineToolsDisplayProps) {
  if (!tools || tools.length === 0) return null;

  return (
    <Card className="p-4 space-y-3" data-testid="card-inline-tools">
      <div className="flex items-center gap-2">
        <Wrench className="w-4 h-4 text-primary" />
        <h4 className="font-semibold text-sm">Clinical Tools (auto-triggered)</h4>
      </div>
      <div className="space-y-2">
        {tools.map((tool, i) => (
          <ToolResultItem key={`${tool.tool}-${i}`} tool={tool} />
        ))}
      </div>
    </Card>
  );
}
