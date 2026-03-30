import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertTriangle, Zap, Shield, Activity,
  Search, Clock, ChevronRight, Syringe,
  Eye, Microscope, HelpCircle,
} from "lucide-react";

interface QuickOption {
  id: string;
  label: string;
  query: string;
  icon: React.ElementType;
  urgent: boolean;
  shortcut?: string;
}

const QUICK_OPTIONS: QuickOption[] = [
  {
    id: "vascular",
    label: "Vascular Occlusion",
    query: "vascular occlusion management hyaluronidase treatment protocol",
    icon: AlertTriangle,
    urgent: true,
    shortcut: "V",
  },
  {
    id: "anaphylaxis",
    label: "Anaphylaxis",
    query: "anaphylaxis emergency management aesthetic injectable",
    icon: Zap,
    urgent: true,
    shortcut: "A",
  },
  {
    id: "nodules",
    label: "Nodules",
    query: "filler nodule granuloma treatment management",
    icon: Activity,
    urgent: false,
    shortcut: "N",
  },
  {
    id: "infection",
    label: "Infection / Biofilm",
    query: "post-filler infection biofilm treatment antibiotics",
    icon: Microscope,
    urgent: false,
    shortcut: "I",
  },
  {
    id: "ptosis",
    label: "Ptosis",
    query: "botulinum toxin induced ptosis management apraclonidine",
    icon: Eye,
    urgent: false,
    shortcut: "P",
  },
  {
    id: "tyndall",
    label: "Tyndall Effect",
    query: "tyndall effect filler hyaluronidase treatment",
    icon: Shield,
    urgent: false,
  },
  {
    id: "dir",
    label: "Delayed Inflammatory",
    query: "delayed inflammatory reaction filler management treatment",
    icon: Clock,
    urgent: false,
  },
  {
    id: "other",
    label: "Other",
    query: "",
    icon: HelpCircle,
    urgent: false,
  },
];

const SUGGESTED_QUERIES = [
  "Hyaluronidase dose for vascular occlusion",
  "Pre-procedure safety check lip filler",
  "Botox dose glabellar lines",
  "Tear trough filler danger zones",
  "Drug interactions warfarin and fillers",
];

interface ComplicationQuickStartProps {
  onQuery: (q: string) => void;
  isLoading: boolean;
  recentSearches?: string[];
  className?: string;
}

export function ComplicationQuickStart({
  onQuery,
  isLoading,
  recentSearches = [],
  className = "",
}: ComplicationQuickStartProps) {
  const [input, setInput] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (document.activeElement?.tagName === "TEXTAREA" ||
          document.activeElement?.tagName === "INPUT") return;

      const opt = QUICK_OPTIONS.find(
        (o) => o.shortcut && e.key.toUpperCase() === o.shortcut
      );
      if (opt && opt.query) {
        e.preventDefault();
        handleSelect(opt);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const handleSelect = (opt: QuickOption) => {
    if (opt.id === "other" || !opt.query) {
      setInput("");
      setTimeout(() => textRef.current?.focus(), 50);
      return;
    }
    setActiveId(opt.id);
    onQuery(opt.query);
  };

  const handleSubmit = () => {
    const q = input.trim();
    if (!q || isLoading) return;
    onQuery(q);
    setInput("");
  };

  return (
    <div className={`flex flex-col items-center w-full max-w-2xl mx-auto ${className}`}>
      <div className="text-center mb-7">
        <div className="flex justify-center mb-5">
          <img
            src="/aestheticite-logo.png"
            alt="AesthetiCite"
            className="h-24 sm:h-28 w-auto object-contain drop-shadow-md"
          />
        </div>
        <h2 className="text-2xl sm:text-3xl font-bold tracking-tight mb-2">
          What complication are you facing?
        </h2>
        <p className="text-muted-foreground text-sm max-w-md mx-auto">
          Evidence-based protocols, ranked by clinical hierarchy.
          Select a complication or type below.
        </p>
      </div>

      <div className="w-full relative mb-4">
        <Textarea
          ref={textRef}
          rows={2}
          placeholder="Describe your clinical question…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          disabled={isLoading}
          className="resize-none text-sm rounded-xl border-2 border-muted-foreground/20
                     focus:border-blue-400 bg-background shadow-sm
                     px-4 pt-3 pb-3 pr-24 min-h-[64px] transition-all"
          data-testid="input-question-quick"
        />
        <Button
          onClick={handleSubmit}
          disabled={isLoading || !input.trim()}
          size="sm"
          className="absolute right-2.5 bottom-2.5 rounded-lg h-9 px-3 gap-1.5"
          data-testid="button-ask-quick"
        >
          {isLoading ? (
            <span className="flex items-center gap-1.5">
              <span className="h-3.5 w-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Searching…
            </span>
          ) : (
            <>
              <Search className="h-3.5 w-3.5" />
              Ask
            </>
          )}
        </Button>
      </div>

      <div className="w-full grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-4">
        {QUICK_OPTIONS.map((opt) => {
          const Icon = opt.icon;
          const isActive = activeId === opt.id && isLoading;
          return (
            <button
              key={opt.id}
              type="button"
              disabled={isLoading}
              onClick={() => handleSelect(opt)}
              className={`
                relative flex flex-col items-center justify-center gap-2
                px-3 py-4 rounded-xl border-2 text-sm font-medium
                transition-all duration-150 text-left
                focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                ${opt.urgent
                  ? "border-red-200 dark:border-red-900 hover:border-red-400 hover:bg-red-50 dark:hover:bg-red-950/20"
                  : "border-border hover:border-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/20"
                }
                ${isActive ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30 shadow-sm" : ""}
                ${isLoading && !isActive ? "opacity-60 cursor-not-allowed" : "cursor-pointer"}
              `}
              data-testid={`quick-${opt.id}`}
            >
              <Icon
                className={`h-5 w-5 ${
                  opt.urgent
                    ? "text-red-500"
                    : "text-blue-500 dark:text-blue-400"
                } ${isActive ? "animate-pulse" : ""}`}
              />
              <span className="leading-tight text-center text-xs sm:text-sm">
                {opt.label}
              </span>
              {opt.urgent && (
                <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-red-500" />
              )}
              {opt.shortcut && !isLoading && (
                <span className="absolute bottom-1.5 right-2 text-[9px] text-muted-foreground/50 font-mono">
                  {opt.shortcut}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="w-full mb-4">
        <p className="text-[11px] text-muted-foreground uppercase tracking-wide font-medium mb-2">
          Quick searches
        </p>
        <div className="flex flex-wrap gap-1.5">
          {SUGGESTED_QUERIES.map((q) => (
            <button
              key={q}
              type="button"
              disabled={isLoading}
              onClick={() => onQuery(q)}
              className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-full
                         border border-border hover:border-blue-400 hover:text-blue-600
                         dark:hover:text-blue-400 transition-colors disabled:opacity-50"
            >
              <ChevronRight className="h-3 w-3 opacity-50" />
              {q}
            </button>
          ))}
        </div>
      </div>

      {recentSearches.length > 0 && (
        <div className="w-full">
          <p className="text-[11px] text-muted-foreground uppercase tracking-wide font-medium mb-2">
            Recent
          </p>
          <div className="space-y-1">
            {recentSearches.slice(0, 4).map((q) => (
              <button
                key={q}
                type="button"
                disabled={isLoading}
                onClick={() => onQuery(q)}
                className="w-full text-left flex items-center gap-2 px-3 py-1.5 rounded-lg
                           hover:bg-muted transition-colors text-sm text-muted-foreground
                           hover:text-foreground disabled:opacity-50"
              >
                <Clock className="h-3.5 w-3.5 flex-shrink-0 opacity-50" />
                <span className="truncate">{q}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6 flex items-center gap-2 text-xs text-muted-foreground">
        <Badge variant="outline" className="text-[10px] bg-emerald-50 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-400 border-emerald-300">
          🟢 Guideline-first
        </Badge>
        <span>772,000+ papers · Evidence ranked by clinical hierarchy</span>
      </div>
    </div>
  );
}
