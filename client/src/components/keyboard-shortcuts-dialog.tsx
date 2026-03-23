import { useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { X, Keyboard } from "lucide-react";
import { SHORTCUTS } from "@/hooks/use-keyboard-shortcuts";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function KeyboardShortcutsDialog({ open, onClose }: Props) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose} data-testid="shortcuts-overlay">
      <Card className="relative w-full max-w-sm mx-4 p-5 shadow-lg" onClick={(e) => e.stopPropagation()} data-testid="shortcuts-dialog">
        <button onClick={onClose} className="absolute top-3 right-3 text-muted-foreground hover-elevate rounded-md p-1" data-testid="button-close-shortcuts">
          <X className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-2 mb-4">
          <Keyboard className="w-4 h-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Keyboard Shortcuts</h3>
        </div>

        <div className="space-y-2">
          {SHORTCUTS.map((shortcut) => (
            <div key={shortcut.label} className="flex items-center justify-between gap-4 py-1.5" data-testid={`shortcut-${shortcut.label.toLowerCase().replace(/\s/g, '-')}`}>
              <span className="text-sm text-muted-foreground">{shortcut.label}</span>
              <div className="flex items-center gap-1">
                {shortcut.keys.map((key) => (
                  <Badge key={key} variant="secondary" className="font-mono text-[10px] px-1.5 py-0 h-5 min-w-[24px] justify-center">
                    {key}
                  </Badge>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
