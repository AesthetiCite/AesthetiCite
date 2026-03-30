import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { useLocation } from "wouter";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Upload,
  Send,
  Loader2,
  ArrowLeft,
  Shield,
  AlertTriangle,
  FileText,
  Eye,
  ExternalLink,
  Camera,
} from "lucide-react";
import { Link } from "wouter";
import { ThemeToggle } from "@/components/theme-toggle";
import { VisualDifferential } from "@/components/VisualDifferential";
import {
  getToken,
  getMe,
  uploadVisual,
  getVisualPreview,
  askVisualStream,
  createConversation,
  type Citation,
} from "@/lib/auth";
import { ACIScoreDisplay } from "@/components/aci-score-display";
import { useToast } from "@/hooks/use-toast";
import { VisionDiagnoseButton } from "@/components/vision-diagnosis-result";

type Lang = "en" | "fr" | "es" | "ar";
const LANG_LABEL: Record<Lang, string> = { en: "English", fr: "Français", es: "Español", ar: "العربية" };
const isRTL = (l: Lang) => l === "ar";

const PLACEHOLDERS: Record<Lang, string> = {
  en: "e.g., After breast augmentation, what are common 10-year trajectories and complications?",
  fr: "Ex: À quoi ressemble l'évolution à 10 ans après augmentation mammaire ? Complications ?",
  es: "Ej: ¿Cómo evoluciona a 10 años tras aumento mamario? ¿Complicaciones?",
  ar: "مثال: كيف يمكن أن تتغير النتيجة بعد 10 سنوات من تكبير الثدي؟ ما المضاعفات؟",
};

const STATUS_DONE: Record<Lang, string> = { en: "Done.", fr: "Terminé.", es: "Listo.", ar: "تم." };
const STATUS_STARTING: Record<Lang, string> = { en: "Starting...", fr: "Démarrage…", es: "Iniciando…", ar: "بدء…" };
const STATUS_UPLOADED: Record<Lang, string> = { en: "Photo uploaded.", fr: "Photo importée.", es: "Foto subida.", ar: "تم رفع الصورة." };

interface SourceItem {
  sid?: string;
  title?: string;
  year?: number;
  url?: string;
  evidence_type?: string;
}

export default function VisualCounselingPage() {
  const [, navigate] = useLocation();
  const { toast } = useToast();

  const [user, setUser] = useState<{ id: string; email: string; full_name?: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [lang, setLang] = useState<Lang>("en");
  const dir = useMemo(() => (isRTL(lang) ? "rtl" : "ltr"), [lang]);

  const [conversationId, setConversationId] = useState("");
  const [visualId, setVisualId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [localPreviewUrl, setLocalPreviewUrl] = useState("");
  const [serverPreviewUrl, setServerPreviewUrl] = useState("");
  const [intensity, setIntensity] = useState(0.5);
  const [uploading, setUploading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [statusText, setStatusText] = useState("");

  const [question, setQuestion] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [finalText, setFinalText] = useState("");
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [aciScore, setAciScore] = useState<number | null>(null);

  const fileRef = useRef<HTMLInputElement>(null);
  const answerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) { navigate("/login"); return; }
    getMe(token).then((u) => {
      setUser(u);
      createConversation(u.id, "Visual Counseling")
        .then(setConversationId)
        .catch(() => {});
    }).catch(() => navigate("/login")).finally(() => setLoading(false));
  }, [navigate]);

  useEffect(() => {
    if (!file) return;
    if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
    const url = URL.createObjectURL(file);
    setLocalPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    return () => {
      if (serverPreviewUrl) URL.revokeObjectURL(serverPreviewUrl);
    };
  }, [serverPreviewUrl]);

  const handleUpload = useCallback(async () => {
    if (!file || !user) return;
    const token = getToken();
    if (!token) return;

    let cid = conversationId;
    if (!cid) {
      cid = await createConversation(user.id, "Visual Counseling");
      setConversationId(cid);
    }

    setUploading(true);
    setStatusText("");
    try {
      const result = await uploadVisual(token, cid, file, "photo");
      setVisualId(result.visual_id);
      setStatusText(STATUS_UPLOADED[lang]);
      setPreviewLoading(true);
      try {
        const prevUrl = await getVisualPreview(token, result.visual_id, intensity);
        setServerPreviewUrl(prevUrl);
      } catch {} finally {
        setPreviewLoading(false);
      }
    } catch (e: any) {
      toast({ title: "Upload failed", description: e.message, variant: "destructive" });
      setStatusText(e.message || "Upload error");
    } finally {
      setUploading(false);
    }
  }, [file, user, conversationId, lang, toast]);

  const intensityRef = useRef(intensity);
  useEffect(() => { intensityRef.current = intensity; }, [intensity]);

  useEffect(() => {
    if (!visualId) return;
    const t = setTimeout(() => {
      const token = getToken();
      if (!token) return;
      setPreviewLoading(true);
      getVisualPreview(token, visualId, intensityRef.current).then((url) => {
        setServerPreviewUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return url; });
      }).catch(() => {}).finally(() => setPreviewLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [intensity, visualId]);

  const handleStream = useCallback(async () => {
    const q = question.trim();
    if (!q || streaming || !conversationId) return;

    const token = getToken();
    if (!token) return;

    setStreaming(true);
    setFinalText("");
    setSources([]);
    setAciScore(null);
    setStatusText(STATUS_STARTING[lang]);

    let accumulated = "";

    try {
      await askVisualStream(token, q, conversationId, {
        onToken: (tok) => {
          accumulated += tok;
          setFinalText(accumulated);
          answerRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
        },
        onMeta: (cits, _, extra) => {
          const mapped: SourceItem[] = cits.map((c, i) => ({
            sid: `S${(c as any).id || i + 1}`,
            title: c.title,
            year: c.year,
            url: (c as any).url || "",
            evidence_type: (c as any).evidence_type || "",
          }));
          setSources(mapped);
          if (extra?.aciScore != null) setAciScore(extra.aciScore);
        },
        onRelated: () => {},
        onDone: () => {
          setStreaming(false);
          setStatusText(STATUS_DONE[lang]);
        },
        onError: (err) => {
          setFinalText(err);
          setStreaming(false);
          setStatusText("");
        },
      }, visualId, lang);
    } catch (e: any) {
      setFinalText(e.message || "Stream error");
    } finally {
      setStreaming(false);
    }
  }, [question, streaming, conversationId, visualId, lang]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleStream();
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen" data-testid="loading-visual">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen" dir={dir} lang={lang}>
      <header className="flex items-center justify-between gap-2 p-3 border-b flex-wrap sticky top-0 z-50 bg-background">
        <div className="flex items-center gap-2">
          <Link href="/ask">
            <Button variant="ghost" size="icon" data-testid="button-back-ask">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <Eye className="h-5 w-5 text-primary" />
          <span className="font-semibold text-sm">Visual Counseling</span>
          <Badge variant="outline" className="text-xs hidden sm:inline-flex">Beta</Badge>
        </div>
        <div className="flex items-center gap-2">
          <Select value={lang} onValueChange={(v) => setLang(v as Lang)}>
            <SelectTrigger className="w-[120px] text-xs" data-testid="select-lang">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(LANG_LABEL) as Lang[]).map((k) => (
                <SelectItem key={k} value={k}>{LANG_LABEL[k]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <ThemeToggle />
        </div>
      </header>

      <main className="flex-1 overflow-auto p-4 md:p-6">
        <div className="mx-auto max-w-5xl grid gap-6 lg:grid-cols-2">
          <Card>
            <CardContent className="p-5 flex flex-col gap-4">
              <div className="text-sm font-semibold">1) Upload a photo (front view)</div>
              <p className="text-sm text-muted-foreground leading-relaxed">
                This preview is illustrative for counseling only. It is not a guaranteed outcome and is not a 3D simulation.
              </p>

              <div className="flex flex-col gap-3">
                <div
                  className="border-2 border-dashed rounded-md p-6 flex flex-col items-center gap-2 cursor-pointer hover-elevate transition-colors"
                  onClick={() => fileRef.current?.click()}
                  data-testid="dropzone-upload"
                >
                  <Upload className="h-8 w-8 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground text-center">
                    {file ? file.name : "Click to select a photo"}
                  </p>
                  <p className="text-xs text-muted-foreground">JPEG, PNG up to 7MB</p>
                </div>

                <input
                  ref={fileRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  data-testid="input-file-upload"
                />

                <div className="flex items-center gap-2">
                  <Button
                    onClick={handleUpload}
                    disabled={!file || uploading}
                    data-testid="button-upload"
                  >
                    {uploading ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Uploading...
                      </>
                    ) : (
                      "Upload"
                    )}
                  </Button>
                  <span className="text-xs text-muted-foreground">
                    {visualId ? `ID: ${visualId.slice(0, 12)}...` : "No upload yet"}
                  </span>
                </div>
              </div>

              <div className="text-sm font-semibold mt-2">2) Preview (illustrative)</div>

              <div className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground whitespace-nowrap">Subtle</span>
                <Slider
                  value={[intensity]}
                  onValueChange={(val) => setIntensity(val[0])}
                  min={0}
                  max={1}
                  step={0.01}
                  disabled={!visualId}
                  className="flex-1"
                  data-testid="slider-intensity"
                />
                <span className="text-xs text-muted-foreground whitespace-nowrap">Larger</span>
              </div>

              <div className="grid gap-4 grid-cols-2">
                <div>
                  <p className="text-xs text-muted-foreground mb-2">Original</p>
                  <div className="aspect-[3/4] w-full overflow-hidden rounded-md border bg-muted flex items-center justify-center">
                    {localPreviewUrl ? (
                      <img src={localPreviewUrl} alt="Local preview" className="h-full w-full object-contain" data-testid="img-original" />
                    ) : (
                      <span className="text-xs text-muted-foreground">No image</span>
                    )}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-2">Illustrative preview</p>
                  <div className="aspect-[3/4] w-full overflow-hidden rounded-md border bg-muted flex items-center justify-center relative">
                    {serverPreviewUrl ? (
                      <img src={serverPreviewUrl} alt="Server preview" className="h-full w-full object-contain" data-testid="img-preview" />
                    ) : (
                      <span className="text-xs text-muted-foreground">{visualId ? "Generating..." : "Upload first"}</span>
                    )}
                    {previewLoading && (
                      <div className="absolute inset-0 flex items-center justify-center bg-background/50">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {visualId && (
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
                    <Camera className="h-3.5 w-3.5 text-blue-500" />
                    Complication Screening
                  </p>
                  <VisionDiagnoseButton
                    label="Analyse Image for Complications"
                    variant="outline"
                    size="sm"
                  />
                </div>
              )}

              {visualId && (
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
                    <FileText className="h-3.5 w-3.5 text-teal-600" />
                    Differential Diagnosis
                  </p>
                  <VisualDifferential
                    visualId={visualId}
                    token={getToken() || ""}
                    clinicalContext={question || undefined}
                  />
                </div>
              )}

              <div className="flex items-start gap-2 p-3 rounded-md bg-muted/50 text-xs text-muted-foreground">
                <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>Keep lighting consistent and use a neutral background for clearer counseling visuals.</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5 flex flex-col gap-4">
              <div className="text-sm font-semibold">3) Ask for long-term counseling + complications</div>
              <p className="text-sm text-muted-foreground leading-relaxed">
                AesthetiCite will respond with evidence-grounded, scenario-based long-term trajectories and complication/revision considerations, with strict inline citations.
              </p>

              <div className="flex gap-2">
                <Input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={PLACEHOLDERS[lang]}
                  disabled={streaming}
                  className="flex-1 text-sm"
                  data-testid="input-visual-question"
                />
                <Button
                  onClick={handleStream}
                  disabled={streaming || !question.trim() || !conversationId}
                  data-testid="button-send-visual"
                >
                  {streaming ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Streaming...
                    </>
                  ) : (
                    <>
                      <Send className="h-4 w-4 mr-2" />
                      Ask
                    </>
                  )}
                </Button>
              </div>

              <div className="text-xs text-muted-foreground">
                {statusText || "Structured output with citations. No cite = no claim."}
              </div>

              {sources.length > 0 && (
                <div className="rounded-md border p-4">
                  <div className="text-xs font-semibold mb-3">Sources</div>
                  <div className="flex flex-wrap gap-2">
                    {sources.slice(0, 10).map((s, i) => (
                      <a
                        key={`${s.sid || i}-${s.url || ""}`}
                        href={s.url || "#"}
                        target="_blank"
                        rel="noreferrer"
                        title={`${s.title || ""}${s.year ? ` (${s.year})` : ""}`}
                        data-testid={`source-link-${i}`}
                      >
                        <Badge variant="outline" className="gap-1.5 text-xs font-normal">
                          <span className="font-mono">{s.sid || `S${i + 1}`}</span>
                          <span className="truncate max-w-[180px]">{s.title || "Untitled"}</span>
                          {s.url && <ExternalLink className="h-3 w-3 shrink-0" />}
                        </Badge>
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {aciScore != null && (
                <ACIScoreDisplay score={aciScore} />
              )}

              {finalText && (
                <div className="rounded-md border p-5" ref={answerRef}>
                  <div className="whitespace-pre-wrap text-sm leading-relaxed" data-testid="text-answer">
                    {finalText}
                  </div>
                  {streaming && (
                    <Loader2 className="h-4 w-4 animate-spin mt-2 inline-block text-muted-foreground" />
                  )}
                </div>
              )}

              <div className="flex items-start gap-2 p-3 rounded-md bg-muted/50 text-xs text-muted-foreground border-t mt-2">
                <Shield className="h-4 w-4 mt-0.5 shrink-0" />
                <span>Educational decision support. Illustrative preview only. Not a substitute for clinical judgment.</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
