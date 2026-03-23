import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Star } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { getToken, getMe } from "@/lib/auth";

interface FavoritesButtonProps {
  queryId?: string;
  question: string;
  answer: string;
  initialFavorited?: boolean;
}

export function FavoritesButton({ queryId, question, answer, initialFavorited = false }: FavoritesButtonProps) {
  const { toast } = useToast();
  const [isFavorited, setIsFavorited] = useState(initialFavorited);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const favorites = JSON.parse(localStorage.getItem("aestheticite_favorites") || "[]");
    const found = favorites.some((f: { question: string }) => f.question === question);
    setIsFavorited(found);
  }, [question]);

  const toggleFavorite = async () => {
    setIsLoading(true);
    try {
      const token = getToken();
      const favorites = JSON.parse(localStorage.getItem("aestheticite_favorites") || "[]");

      if (isFavorited) {
        const updated = favorites.filter((f: { question: string }) => f.question !== question);
        localStorage.setItem("aestheticite_favorites", JSON.stringify(updated));
        setIsFavorited(false);
        toast({ title: "Removed from saved answers" });

        if (token && queryId) {
          await fetch(`/api/favorites/${queryId}`, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` },
          }).catch(() => {});
        }
      } else {
        const newFavorite = {
          id: queryId || Date.now().toString(),
          question,
          answer: answer.substring(0, 500),
          savedAt: new Date().toISOString(),
        };
        favorites.unshift(newFavorite);
        localStorage.setItem("aestheticite_favorites", JSON.stringify(favorites.slice(0, 50)));
        setIsFavorited(true);
        toast({ title: "Saved to bookmarks", description: "View all saved answers in More → Saved Answers" });

        if (token) {
          const me = token ? await getMe(token).catch(() => null) : null;
          const userId = me?.email || me?.id || "anonymous";

          const titleWords = question.split(" ").slice(0, 8).join(" ");
          const title = titleWords.length < question.length ? titleWords + "..." : question;

          await fetch("/api/growth/bookmarks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              user_id: userId,
              title,
              question,
              answer_json: { answer: answer.substring(0, 2000) },
              tags: [],
            }),
          }).catch(() => {});

          await fetch("/api/favorites", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ query_id: queryId, question, answer_preview: answer.substring(0, 500) }),
          }).catch(() => {});
        }
      }
    } catch (err) {
      console.error("Favorites error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggleFavorite}
      disabled={isLoading}
      data-testid="button-favorite"
      title={isFavorited ? "Remove from saved answers" : "Save this answer"}
    >
      <Star
        className={`h-4 w-4 ${isFavorited ? "fill-yellow-400 text-yellow-400" : ""}`}
      />
    </Button>
  );
}
