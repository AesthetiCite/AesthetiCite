import { useState, useRef, useEffect } from "react";
import { Search, ArrowRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useIsMobile } from "@/hooks/use-mobile";

interface SearchBarProps {
  onSearch: (query: string) => void;
  isLoading?: boolean;
  size?: "default" | "large";
  placeholder?: string;
  initialValue?: string;
  autoFocus?: boolean;
}

export function SearchBar({
  onSearch,
  isLoading = false,
  size = "default",
  placeholder = "Ask any research question...",
  initialValue = "",
  autoFocus = false,
}: SearchBarProps) {
  const [query, setQuery] = useState(initialValue);
  const inputRef = useRef<HTMLInputElement>(null);
  const isMobile = useIsMobile();

  useEffect(() => {
    if (autoFocus && inputRef.current && !isMobile) {
      inputRef.current.focus();
    }
  }, [autoFocus, isMobile]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim() && !isLoading) {
      onSearch(query.trim());
      if (inputRef.current) {
        inputRef.current.blur();
      }
    }
  };

  const inputSizeClasses = size === "large" 
    ? "text-lg py-4 pl-12 pr-14"
    : "text-base py-2.5 pl-10 pr-12";

  const iconClasses = size === "large" 
    ? "left-4 w-5 h-5" 
    : "left-3 w-4 h-4";

  return (
    <form onSubmit={handleSubmit} className="relative w-full" data-testid="form-search">
      <div className="relative">
        <Search className={`absolute top-1/2 -translate-y-1/2 text-muted-foreground ${iconClasses}`} />
        <input
          ref={inputRef}
          type="text"
          enterKeyHint="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          disabled={isLoading}
          data-testid="input-search"
          className={`w-full rounded-lg border border-input bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all ${inputSizeClasses}`}
        />
        <Button
          type="submit"
          size="icon"
          disabled={!query.trim() || isLoading}
          className="absolute top-1/2 -translate-y-1/2 right-1.5"
          data-testid="button-search-submit"
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ArrowRight className="h-4 w-4" />
          )}
        </Button>
      </div>
    </form>
  );
}
