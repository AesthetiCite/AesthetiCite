import { useState, useEffect } from "react";
import { Link } from "wouter";
import { ArrowLeft, Bookmark, Tag, Trash2, Loader2, BookOpen, Search } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { getMe, getToken } from "@/lib/auth";

type BookmarkItem = {
  id: string;
  user_id: string;
  title: string;
  question: string;
  answer_json: Record<string, unknown>;
  tags: string[];
  created_at_utc: string;
};

export default function BookmarksPage() {
  const [bookmarks, setBookmarks] = useState<BookmarkItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [userId, setUserId] = useState<string>("");
  const [search, setSearch] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) { setLoading(false); setError("Not logged in."); return; }
    getMe(token).then((u) => {
      if (u?.email) {
        setUserId(u.email);
        fetchBookmarks(u.email);
      } else {
        setLoading(false);
        setError("Could not identify current user.");
      }
    });
  }, []);

  async function fetchBookmarks(uid: string) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/growth/bookmarks/${encodeURIComponent(uid)}`);
      if (!res.ok) throw new Error(await res.text());
      setBookmarks(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load bookmarks.");
    } finally {
      setLoading(false);
    }
  }

  async function deleteBookmark(id: string) {
    setDeleting(id);
    try {
      await fetch(`/api/growth/bookmarks/${id}`, { method: "DELETE" });
      setBookmarks((prev) => prev.filter((b) => b.id !== id));
    } finally {
      setDeleting(null);
    }
  }

  const filtered = bookmarks.filter(
    (b) =>
      b.title.toLowerCase().includes(search.toLowerCase()) ||
      b.question.toLowerCase().includes(search.toLowerCase()) ||
      b.tags.some((t) => t.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 p-4 md:p-8">
      <div className="mx-auto max-w-4xl">
        <div className="mb-6">
          <Link href="/ask">
            <Button variant="ghost" size="sm" className="gap-1.5 text-slate-500 -ml-2">
              <ArrowLeft className="h-4 w-4" /> Back to Search
            </Button>
          </Link>
        </div>

        <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
              Saved Answers
            </h1>
            <p className="mt-1 text-sm text-slate-500">Your bookmarked clinical answers.</p>
          </div>
          <div className="flex items-center gap-2 rounded-2xl border bg-white dark:bg-slate-900 px-4 py-2 shadow-sm">
            <Bookmark className="h-4 w-4 text-slate-400" />
            <span className="text-sm text-slate-500">{bookmarks.length} saved</span>
          </div>
        </div>

        {bookmarks.length > 3 && (
          <div className="mb-6 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              placeholder="Search bookmarks..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 rounded-xl"
              data-testid="input-bookmark-search"
            />
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 dark:bg-red-950 p-4 text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        {!loading && !error && filtered.length === 0 && (
          <Card className="rounded-2xl border shadow-sm bg-white dark:bg-slate-900">
            <CardContent className="flex min-h-[360px] flex-col items-center justify-center text-center p-12">
              <BookOpen className="mb-4 h-14 w-14 text-slate-200 dark:text-slate-700" />
              <h2 className="text-xl font-medium text-slate-700 dark:text-slate-300">
                {search ? "No matching bookmarks" : "No saved answers yet"}
              </h2>
              <p className="mt-2 max-w-sm text-sm text-slate-400">
                {search
                  ? "Try a different search term."
                  : "When you find a useful answer in AesthetiCite Search, save it here for quick reference."}
              </p>
            </CardContent>
          </Card>
        )}

        <div className="space-y-4">
          {filtered.map((bm) => (
            <Card key={bm.id} className="rounded-2xl border shadow-sm bg-white dark:bg-slate-900" data-testid={`bookmark-card-${bm.id}`}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-slate-900 dark:text-slate-100 truncate">{bm.title}</p>
                    <p className="mt-1 text-sm text-slate-500 line-clamp-2">{bm.question}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {bm.tags.map((tag) => (
                        <Badge key={tag} variant="secondary" className="text-xs gap-1">
                          <Tag className="h-3 w-3" />{tag}
                        </Badge>
                      ))}
                      <span className="text-xs text-slate-400 ml-1">
                        {new Date(bm.created_at_utc).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="shrink-0 text-slate-400 hover:text-red-500"
                    onClick={() => deleteBookmark(bm.id)}
                    disabled={deleting === bm.id}
                    data-testid={`button-delete-bookmark-${bm.id}`}
                  >
                    {deleting === bm.id
                      ? <Loader2 className="h-4 w-4 animate-spin" />
                      : <Trash2 className="h-4 w-4" />}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
