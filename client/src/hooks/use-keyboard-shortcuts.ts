import { useEffect, useCallback } from "react";

interface ShortcutConfig {
  onNewChat?: () => void;
  onToggleSidebar?: () => void;
  onToggleEnhanced?: () => void;
  onFocusInput?: () => void;
  onToggleTools?: () => void;
  onShowShortcuts?: () => void;
}

export function useKeyboardShortcuts(config: ShortcutConfig) {
  const handler = useCallback(
    (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInput = target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable;

      if (e.key === "/" && !isInput) {
        e.preventDefault();
        config.onFocusInput?.();
        return;
      }

      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;

      switch (e.key.toLowerCase()) {
        case "k":
          e.preventDefault();
          config.onFocusInput?.();
          break;
        case "b":
          e.preventDefault();
          config.onToggleSidebar?.();
          break;
        case "e":
          if (e.shiftKey) {
            e.preventDefault();
            config.onToggleEnhanced?.();
          }
          break;
        case "j":
          e.preventDefault();
          config.onToggleTools?.();
          break;
        case "/":
          e.preventDefault();
          config.onShowShortcuts?.();
          break;
      }
    },
    [config]
  );

  useEffect(() => {
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [handler]);
}

export const SHORTCUTS = [
  { keys: ["/"], label: "Focus search input" },
  { keys: ["Ctrl", "K"], label: "Focus search" },
  { keys: ["Ctrl", "B"], label: "Toggle sidebar" },
  { keys: ["Ctrl", "Shift", "E"], label: "Toggle enhanced mode" },
  { keys: ["Ctrl", "J"], label: "Toggle clinical tools" },
  { keys: ["Ctrl", "/"], label: "Show keyboard shortcuts" },
];
