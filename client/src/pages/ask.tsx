import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "wouter";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Search, LogOut, Loader2, AlertTriangle, FileText, Sparkles, ExternalLink, ChevronRight, ChevronDown, ChevronUp, BookOpen, Shield, User, Calculator, PanelLeftClose, PanelLeft, Plus, MessageCircle, Send, Pin, PinOff, Tag, Eye, Copy, ClipboardCheck, BarChart3, AlertCircle, Info, StopCircle, Clock, Syringe, Zap, ShieldAlert, Microscope, Bookmark, Pill, FileUser, Key, LayoutDashboard, Bell, ClipboardCheck as SessionIcon, MoreHorizontal, Menu, Database } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Link } from "wouter";
import { ThemeToggle } from "@/components/theme-toggle";
import { LanguageSelector } from "@/components/language-selector";
import { EvidencePanel, TopEvidenceBadge, type Citation as EHCitation } from "@/components/evidence-hierarchy-badge";
import { useLocale } from "@/hooks/use-locale";
import { BRAND } from "@/config";
import { getToken, clearToken, getMe, askQuestionStream, askQuestionStreamV2, askQuestionOE, getUserDisplayName, createConversation, listConversations, deleteConversation, getConversationMessages, type AskOEResponse, type Citation, type QueryMeta, type ComplicationProtocol, type InlineTool, type ConversationItem } from "@/lib/auth";
import { ACIScoreDisplay } from "@/components/aci-score-display";
import { ComplicationProtocolAlert } from "@/components/complication-protocol-alert";
import { SimilarCasesPanel, LogCaseButton, NetworkStatsBar } from "@/components/similar-cases";
import { InlineToolsDisplay } from "@/components/inline-tools-display";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { X } from "lucide-react";
import { VoiceInput } from "@/components/voice-input";
import { ExportShare } from "@/components/export-share";
import { FavoritesButton } from "@/components/favorites-button";
import { ClinicalToolsPanel } from "@/components/clinical-tools-panel";
import { ClinicalReasoningSection } from "@/components/clinical-reasoning";
import { AnswerFeedback } from "@/components/answer-feedback";
import { OnboardingDialog } from "@/components/onboarding-dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";
import { KeyboardShortcutsDialog } from "@/components/keyboard-shortcuts-dialog";
import { UsageIndicator, recordQuery } from "@/components/usage-indicator";
import { SidebarSafetyNav } from "@/components/sidebar-safety-nav";
import { ProtocolCard, type ProtocolCardData } from "@/components/protocol-card";
import { SafetyEscalationBlock, type SafetyAssessment } from "@/components/safety-escalation-block";
import { ComplicationQuickStart } from "@/components/complication-quick-start";

interface ParsedSections {
  evidenceSummary?: string;
  clinicalSummary?: string;
  keyPoints?: string[];
  safety?: string;
  limitations?: string;
  followups?: string[];
}

function parseSections(raw: string): ParsedSections {
  const s: ParsedSections = {};
  const t = raw || "";

  const grabBlock = (start: RegExp, end: RegExp) => {
    const m = t.match(new RegExp(`${start.source}([\\s\\S]*?)${end.source}`, "i"));
    return m ? m[1].trim() : "";
  };

  const ev = grabBlock(/Evidence Strength Summary\s*/i, /(Clinical Summary|Counseling Summary|Key Evidence-Based Points)\s*/i);
  if (ev) s.evidenceSummary = ev;

  const cs = grabBlock(/Clinical Summary\s*/i, /(Key Evidence-Based Points|Safety Considerations|Limitations \/ Uncertainty|Suggested Follow-up Questions)\s*/i);
  if (cs) s.clinicalSummary = cs;

  const kpBlock = grabBlock(/Key Evidence-Based Points\s*/i, /(Safety Considerations|Limitations \/ Uncertainty|Suggested Follow-up Questions)\s*/i);
  if (kpBlock) {
    const bullets = kpBlock.split("\n").map((l) => l.trim()).filter((l) => l.startsWith("-")).map((l) => l.replace(/^-+\s*/, "").trim()).filter(Boolean);
    if (bullets.length) s.keyPoints = bullets;
  }

  const sf = grabBlock(/Safety Considerations\s*/i, /(Limitations \/ Uncertainty|Suggested Follow-up Questions)\s*/i);
  if (sf) s.safety = sf;

  const lim = grabBlock(/Limitations \/ Uncertainty\s*/i, /(Suggested Follow-up Questions)\s*/i);
  if (lim) s.limitations = lim;

  const fuBlock = grabBlock(/Suggested Follow-up Questions\s*/i, /$/i);
  if (fuBlock) {
    const lines = fuBlock.split("\n").map((l) => l.trim()).filter((l) => l.startsWith("-")).map((l) => l.replace(/^-+\s*/, "").trim()).filter(Boolean);
    if (lines.length) s.followups = lines;
  }

  return s;
}

function stripCitations(text: string) {
  return text.replace(/\s*\[S?\d+\]/g, "").replace(/\s+/g, " ").trim();
}

function citationDensityFromText(raw: string): number {
  const cites = (raw.match(/\[S?\d+\]/g) || []).length;
  const bullets = (raw.match(/^\s*-\s+/gm) || []).length;
  if (!bullets) return 0;
  return Math.round((cites / bullets) * 100) / 100;
}

function citedClaimsPct(raw: string): number {
  const bullets = (raw.match(/^\s*-\s+.*$/gm) || []).map((b) => b.trim());
  if (!bullets.length) return 0;
  const cited = bullets.filter((b) => /\[S?\d+\]/.test(b)).length;
  return Math.round((cited / bullets.length) * 100);
}

function buildCitationLine(c: Citation): string {
  const parts: string[] = [];
  if (c.title) parts.push(c.title);
  if (c.organization_or_journal) parts.push(c.organization_or_journal);
  if (c.year) parts.push(String(c.year));
  if (c.source_id) parts.push(c.source_id);
  return parts.join(" — ");
}

interface UserInfo {
  id: string;
  email: string;
  is_active: boolean;
  role: string;
  created_at: string;
  full_name?: string;
  practitioner_id?: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  isStreaming?: boolean;
  citations?: Citation[];
  relatedQuestions?: string[];
  oeResponse?: AskOEResponse;
  aciScore?: number | null;
  queryMeta?: QueryMeta | null;
  complicationProtocol?: ComplicationProtocol | null;
  inlineTools?: InlineTool[];
  evidenceStrength?: string;
  evidenceBadge?: { level: string; label: string; color: string; best_type?: string; emoji?: string };
  clinicalSummary?: string;
  isRefusal?: boolean;
  refusalReason?: string;
  refusalCode?: string;
  protocolCard?: ProtocolCardData | null;
  safety?: SafetyAssessment | null;
}

let msgCounter = 0;
function nextMsgId() {
  return `msg_${Date.now()}_${++msgCounter}`;
}

const ROTATING_PLACEHOLDERS = [
  "What is the recommended hyaluronidase dose for vascular occlusion?",
  "Evidence for PRP in hair restoration — what do RCTs show?",
  "Botulinum toxin dosing for masseter reduction?",
  "Safest filler choice for tear trough in thin-skinned patients?",
  "Laser settings for melasma in Fitzpatrick IV skin?",
  "Long-term safety of poly-L-lactic acid vs HA fillers?",
  "Management of nodules after hyaluronic acid injection?",
  "What evidence supports LED light therapy for skin rejuvenation?",
  "Contraindications for thread lifts — systematic review evidence?",
  "Optimal interval for repeat botulinum toxin treatment?",
];

function buildStreamingPhases(corpusLabel: string) {
  return [
    `Searching ${corpusLabel} papers…`,
    "Reading top evidence…",
    "Verifying citations…",
    "Synthesizing answer…",
  ];
}

function getReadingTime(text: string): string {
  if (!text) return "";
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  if (words < 50) return "";
  const mins = Math.max(1, Math.round(words / 200));
  return `${mins} min read`;
}

export default function AskPage() {
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const { t } = useLocale();
  const { data: corpusStats } = useQuery<{ papers_inserted: number }>({
    queryKey: ["/api/corpus/stats"],
    staleTime: 10 * 60 * 1000,
  });
  const corpusLabel = corpusStats?.papers_inserted
    ? `${Math.floor(corpusStats.papers_inserted / 1000)}K+`
    : "825K+";
  const STREAMING_PHASES = buildStreamingPhases(corpusLabel);
  const [token, setTokenState] = useState<string | null>(null);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [input, setInput] = useState("");
  const [domain, setDomain] = useState("aesthetic_medicine");
  const [mode, setMode] = useState("clinic");
  const [isLoading, setIsLoading] = useState(false);
  const [enhancedMode, setEnhancedMode] = useState(true);
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string>("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showClinicalTools, setShowClinicalTools] = useState(false);
  const [sidebarFilter, setSidebarFilter] = useState("");
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(() => {
    try {
      const saved = localStorage.getItem("aestheticite_pinned");
      return saved ? new Set(JSON.parse(saved)) : new Set();
    } catch { return new Set(); }
  });
  const [convTags, setConvTags] = useState<Record<string, string>>(() => {
    try {
      const saved = localStorage.getItem("aestheticite_tags");
      return saved ? JSON.parse(saved) : {};
    } catch { return {}; }
  });
  const [activeTag, setActiveTag] = useState<string>("");
  const [showTagInput, setShowTagInput] = useState<string>("");
  const [tagInputValue, setTagInputValue] = useState("");
  const [showShortcuts, setShowShortcuts] = useState(false);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeSources, setActiveSources] = useState<Citation[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [copiedNote, setCopiedNote] = useState<string>("");

  const [recentSearches, setRecentSearches] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem("aestheticite_recent");
      return saved ? JSON.parse(saved) : [];
    } catch { return []; }
  });

  const [placeholderIdx, setPlaceholderIdx] = useState(0);
  const [streamingPhase, setStreamingPhase] = useState(0);

  const bottomRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const scrollBoxRef = useRef<HTMLDivElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const queryStartTimeRef = useRef<number>(0);
  const pendingAciRef = useRef<number | null>(null);

  function logQueryToClinic(question: string, aci: number | null, durationMs: number) {
    const token = getToken();
    if (!token) return;
    fetch("/api/ops/dashboard/log-query", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        query_text: question,
        answer_type: "evidence_search",
        aci_score: aci ?? undefined,
        response_time_ms: Math.round(durationMs),
        domain: "aesthetic_medicine",
      }),
    }).catch(() => {});
  }

  useKeyboardShortcuts({
    onNewChat: handleNewChat,
    onToggleSidebar: () => setSidebarOpen((v) => !v),
    onToggleEnhanced: () => setEnhancedMode((v) => !v),
    onFocusInput: () => inputRef.current?.focus(),
    onToggleTools: () => setShowClinicalTools((v) => !v),
    onShowShortcuts: () => setShowShortcuts((v) => !v),
  });

  useEffect(() => {
    if (input) return;
    const id = setInterval(() => setPlaceholderIdx((i) => (i + 1) % ROTATING_PLACEHOLDERS.length), 3500);
    return () => clearInterval(id);
  }, [input]);

  useEffect(() => {
    if (!isLoading) { setStreamingPhase(0); return; }
    const id = setInterval(() => setStreamingPhase((i) => Math.min(i + 1, STREAMING_PHASES.length - 1)), 2500);
    return () => clearInterval(id);
  }, [isLoading]);

  useEffect(() => {
    const t = getToken();
    if (!t) {
      setLocation("/login");
      return;
    }
    setTokenState(t);
    getMe(t)
      .then((userData) => {
        setUser(userData as UserInfo);
        loadConversations((userData as UserInfo).id);
      })
      .catch(() => {
        clearToken();
        setLocation("/login");
      });
  }, [setLocation]);

  useEffect(() => {
    const el = scrollBoxRef.current;
    if (!el) return;
    const onScroll = () => {
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      setAutoScroll(nearBottom);
    };
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!autoScroll) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, autoScroll]);

  function loadConversations(userId?: string) {
    const uid = userId || user?.id;
    if (!uid) return;
    listConversations(uid)
      .then((convs) => setConversations(convs))
      .catch(() => {});
  }

  function togglePin(convId: string, e: React.MouseEvent) {
    e.stopPropagation();
    setPinnedIds((prev) => {
      const next = new Set(prev);
      if (next.has(convId)) next.delete(convId);
      else next.add(convId);
      localStorage.setItem("aestheticite_pinned", JSON.stringify(Array.from(next)));
      return next;
    });
  }

  function saveTag(convId: string) {
    const tag = tagInputValue.trim();
    setConvTags((prev) => {
      const next = { ...prev };
      if (tag) next[convId] = tag;
      else delete next[convId];
      localStorage.setItem("aestheticite_tags", JSON.stringify(next));
      return next;
    });
    setShowTagInput("");
    setTagInputValue("");
  }

  function removeTag(convId: string, e: React.MouseEvent) {
    e.stopPropagation();
    setConvTags((prev) => {
      const next = { ...prev };
      delete next[convId];
      localStorage.setItem("aestheticite_tags", JSON.stringify(next));
      return next;
    });
  }

  const allTags = useMemo(() => {
    return Array.from(new Set(Object.values(convTags))).sort();
  }, [convTags]);

  async function handleOpenConversation(conv: ConversationItem) {
    setActiveConversationId(conv.id);
    setInput("");
    setIsLoading(false);
    setActiveSources([]);

    try {
      const msgs = await getConversationMessages(conv.id);
      const chatMsgs: ChatMessage[] = msgs.map((m) => ({
        id: nextMsgId(),
        role: m.role as "user" | "assistant",
        content: m.content,
        created_at: m.created_at,
      }));
      setMessages(chatMsgs);
    } catch {
      setMessages([]);
    }
  }

  function handleNewChat() {
    abortControllerRef.current?.abort();
    setInput("");
    setMessages([]);
    setActiveConversationId("");
    setActiveSources([]);
    setIsLoading(false);
    inputRef.current?.focus();
  }

  function handleStop() {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setIsLoading(false);
    setMessages((prev) =>
      prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m))
    );
  }

  function saveRecentSearch(q: string) {
    setRecentSearches((prev) => {
      const next = [q, ...prev.filter((r) => r !== q)].slice(0, 6);
      try { localStorage.setItem("aestheticite_recent", JSON.stringify(next)); } catch {}
      return next;
    });
  }

  async function handleDeleteConversation(convId: string, e: React.MouseEvent) {
    e.stopPropagation();
    if (!user?.id) return;
    const ok = await deleteConversation(convId, user.id);
    if (ok) {
      setConversations((prev) => prev.filter((c) => c.id !== convId));
      if (activeConversationId === convId) {
        handleNewChat();
      }
    }
  }

  async function handleAsk(q?: string) {
    const questionToAsk = q || input.trim();
    if (!token || !questionToAsk) return;

    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setInput("");
    setIsLoading(true);
    setActiveSources([]);
    recordQuery();
    saveRecentSearch(questionToAsk);

    let convId = activeConversationId;
    if (!convId && user?.id) {
      try {
        convId = await createConversation(user.id, questionToAsk.slice(0, 60));
        setActiveConversationId(convId);
      } catch {
        convId = "";
      }
    }

    const userMsgId = nextMsgId();
    const assistantMsgId = nextMsgId();
    queryStartTimeRef.current = Date.now();
    pendingAciRef.current = null;

    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: questionToAsk, created_at: new Date().toISOString() },
      { id: assistantMsgId, role: "assistant", content: "", isStreaming: true, created_at: new Date().toISOString() },
    ]);

    if (enhancedMode) {
      try {
        let finalCitations: Citation[] = [];

        await askQuestionStreamV2(token, questionToAsk, domain, {
          onToken: (text) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, content: m.content + text } : m
              )
            );
          },
          onMeta: (citations, _rid, extra) => {
            finalCitations = citations;
            pendingAciRef.current = extra?.aciScore ?? null;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? {
                      ...m,
                      citations,
                      aciScore: extra?.aciScore ?? null,
                      queryMeta: extra?.queryMeta ?? null,
                      complicationProtocol: extra?.complicationProtocol ?? null,
                      inlineTools: extra?.inlineTools ?? [],
                      evidenceBadge: extra?.evidenceBadge ?? undefined,
                      evidenceStrength: extra?.evidenceBadge?.level ?? undefined,
                      safety: (extra as any)?.safety ?? null,
                    }
                  : m
              )
            );
            setActiveSources(citations);
          },
          onRelated: (questions) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, relatedQuestions: questions } : m
              )
            );
          },
          onDone: (_fullAnswer) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, isStreaming: false, citations: finalCitations } : m
              )
            );
            logQueryToClinic(questionToAsk, pendingAciRef.current, Date.now() - queryStartTimeRef.current);
            setIsLoading(false);
            loadConversations();
          },
          onError: (error) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, content: `Error: ${error}`, isStreaming: false } : m
              )
            );
            toast({ variant: "destructive", title: "Query failed", description: error });
            setIsLoading(false);
          },
          onProtocolCard: (card) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, protocolCard: card } : m
              )
            );
          },
        }, convId, controller.signal);
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, content: "Failed to get answer. Please try again.", isStreaming: false }
              : m
          )
        );
        toast({
          variant: "destructive",
          title: "Query failed",
          description: err instanceof Error ? err.message : "Failed to get answer",
        });
        setIsLoading(false);
      }
    } else {
      try {
        let finalCitations: Citation[] = [];

        await askQuestionStream(token, questionToAsk, domain, mode, {
          onToken: (text) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, content: m.content + text } : m
              )
            );
          },
          onMeta: (citations, _rid, extra) => {
            finalCitations = citations;
            pendingAciRef.current = extra?.aciScore ?? null;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? {
                      ...m,
                      citations,
                      aciScore: extra?.aciScore ?? null,
                      queryMeta: extra?.queryMeta ?? null,
                      complicationProtocol: extra?.complicationProtocol ?? null,
                      inlineTools: extra?.inlineTools ?? [],
                      evidenceBadge: extra?.evidenceBadge ?? undefined,
                      evidenceStrength: extra?.evidenceBadge?.level ?? undefined,
                      safety: (extra as any)?.safety ?? null,
                    }
                  : m
              )
            );
            setActiveSources(citations);
          },
          onRelated: (questions) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, relatedQuestions: questions } : m
              )
            );
          },
          onDone: (_fullAnswer) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, isStreaming: false, citations: finalCitations } : m
              )
            );
            logQueryToClinic(questionToAsk, pendingAciRef.current, Date.now() - queryStartTimeRef.current);
            setIsLoading(false);
            loadConversations();
          },
          onError: (error) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, content: `Error: ${error}`, isStreaming: false } : m
              )
            );
            toast({ variant: "destructive", title: "Query failed", description: error });
            setIsLoading(false);
          },
          onProtocolCard: (card) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, protocolCard: card } : m
              )
            );
          },
        }, convId);
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, content: "Failed to get answer.", isStreaming: false }
              : m
          )
        );
        toast({
          variant: "destructive",
          title: "Query failed",
          description: err instanceof Error ? err.message : "Failed",
        });
        setIsLoading(false);
      }
    }
  }

  function handleLogout() {
    clearToken();
    setLocation("/login");
  }

  function handleRelatedQuestion(q: string) {
    handleAsk(q);
  }

  async function copyNote(text: string, withCitations: boolean) {
    const content = withCitations ? text : stripCitations(text);
    await navigator.clipboard.writeText(content);
    setCopiedNote(withCitations ? "with" : "without");
    setTimeout(() => setCopiedNote(""), 2000);
  }

  function fmtTime(iso: string | null): string {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      const now = new Date();
      const diffMs = now.getTime() - d.getTime();
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
      if (diffDays === 0) return "Today";
      if (diffDays === 1) return "Yesterday";
      if (diffDays < 7) return `${diffDays}d ago`;
      return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    } catch {
      return "";
    }
  }

  const filteredConversations = useMemo(() => {
    let items = conversations;
    const f = sidebarFilter.trim().toLowerCase();
    if (f) items = items.filter((c) => (c.title || "").toLowerCase().includes(f));
    if (activeTag) items = items.filter((c) => convTags[c.id] === activeTag);
    return items;
  }, [conversations, sidebarFilter, activeTag, convTags]);

  const pinnedConversations = useMemo(() => {
    return filteredConversations.filter((c) => pinnedIds.has(c.id));
  }, [filteredConversations, pinnedIds]);

  const unpinnedConversations = useMemo(() => {
    return filteredConversations.filter((c) => !pinnedIds.has(c.id));
  }, [filteredConversations, pinnedIds]);

  const hasMessages = messages.length > 0;
  const lastQuestion = messages.filter((m) => m.role === "user").at(-1)?.content || "";
  const lastAssistantMsg = messages.filter((m) => m.role === "assistant").at(-1);

  function renderConversationItem(conv: ConversationItem, isPinned: boolean) {
    const tag = convTags[conv.id];
    return (
      <div
        key={conv.id}
        className={`group relative w-full text-left rounded-lg mb-0.5 cursor-pointer transition-colors ${
          conv.id === activeConversationId ? "bg-primary/10" : "hover-elevate"
        }`}
        onClick={() => handleOpenConversation(conv)}
        data-testid={`conversation-item-${conv.id}`}
      >
        <div className="flex items-start gap-2 px-3 py-2.5">
          <MessageCircle
            className={`w-4 h-4 mt-0.5 flex-shrink-0 ${
              conv.id === activeConversationId ? "text-primary" : "text-muted-foreground"
            }`}
          />
          <div className="flex-1 min-w-0">
            <p className={`text-sm line-clamp-2 ${conv.id === activeConversationId ? "font-semibold" : "font-medium"}`}>
              {conv.title || "New conversation"}
            </p>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="text-[10px] text-muted-foreground">{fmtTime(conv.created_at)}</span>
              {tag && (
                <Badge variant="secondary" className="text-[9px] px-1.5 py-0 h-4 cursor-pointer" onClick={(e: React.MouseEvent) => removeTag(conv.id, e)} data-testid={`badge-tag-${conv.id}`}>
                  {tag} <X className="w-2.5 h-2.5 ml-0.5" />
                </Badge>
              )}
            </div>
          </div>
          <div className="flex items-center gap-0.5 flex-shrink-0">
            <button
              className={`p-1 rounded-md text-muted-foreground hover:text-foreground ${isPinned ? "visible" : "invisible group-hover:visible"}`}
              onClick={(e) => togglePin(conv.id, e)}
              data-testid={`button-pin-${conv.id}`}
            >
              {isPinned ? <PinOff className="w-3 h-3" /> : <Pin className="w-3 h-3" />}
            </button>
            <button
              className="invisible group-hover:visible p-1 rounded-md text-muted-foreground hover:text-foreground"
              onClick={(e) => { e.stopPropagation(); setShowTagInput(conv.id); setTagInputValue(convTags[conv.id] || ""); }}
              data-testid={`button-tag-${conv.id}`}
            >
              <Tag className="w-3 h-3" />
            </button>
            <button
              className="invisible group-hover:visible p-1 rounded-md text-muted-foreground hover:text-foreground"
              onClick={(e) => handleDeleteConversation(conv.id, e)}
              data-testid={`button-delete-conv-${conv.id}`}
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        </div>
        {showTagInput === conv.id && (
          <div className="px-3 pb-2 flex gap-1" onClick={(e) => e.stopPropagation()}>
            <Input
              value={tagInputValue}
              onChange={(e) => setTagInputValue(e.target.value)}
              placeholder="e.g. Botox, Fillers..."
              className="text-xs h-7"
              onKeyDown={(e) => { if (e.key === "Enter") saveTag(conv.id); if (e.key === "Escape") setShowTagInput(""); }}
              autoFocus
              data-testid={`input-tag-${conv.id}`}
            />
            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => saveTag(conv.id)} data-testid={`button-save-tag-${conv.id}`}>
              Save
            </Button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="h-screen flex bg-gradient-to-b from-background to-muted/20">
      <OnboardingDialog />
      <KeyboardShortcutsDialog open={showShortcuts} onClose={() => setShowShortcuts(false)} />
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30 md:hidden"
          onClick={() => setSidebarOpen(false)}
          data-testid="sidebar-backdrop"
        />
      )}
      <aside
        className={`${sidebarOpen ? "w-72" : "w-0"} transition-all duration-300 ease-in-out border-r bg-muted/30 flex-shrink-0 overflow-hidden fixed md:relative z-50 md:z-auto h-full bg-background md:bg-muted/30`}
        data-testid="sidebar-history"
      >
        <div className="w-72 h-full flex flex-col">
          <div className="p-4 border-b flex items-center justify-between gap-2">
            <div className="flex items-center gap-2" data-testid="sidebar-logo">
              <img
                src="/aestheticite-logo.png"
                alt="AesthetiCite"
                className="w-8 h-8 object-contain rounded-lg"
                data-testid="img-sidebar-logo"
              />
              <span className="font-bold text-sm" data-testid="text-sidebar-title">AesthetiCite</span>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(false)}
              data-testid="button-close-sidebar"
            >
              <PanelLeftClose className="w-4 h-4" />
            </Button>
          </div>

          <div className="p-3 space-y-2">
            <Button
              className="w-full justify-start gap-2"
              variant="outline"
              onClick={handleNewChat}
              data-testid="button-new-chat"
            >
              <Plus className="w-4 h-4" />
              New Search
            </Button>
            <Input
              value={sidebarFilter}
              onChange={(e) => setSidebarFilter(e.target.value)}
              placeholder="Search conversations..."
              className="text-sm"
              data-testid="input-sidebar-filter"
            />
          </div>

          {allTags.length > 0 && (
            <div className="px-3 pt-1 pb-2 flex flex-wrap gap-1" data-testid="tag-filter-bar">
              <Badge
                variant={activeTag === "" ? "default" : "secondary"}
                className="text-[10px] cursor-pointer px-2 py-0.5"
                onClick={() => setActiveTag("")}
                data-testid="tag-filter-all"
              >
                All
              </Badge>
              {allTags.map((tag) => (
                <Badge
                  key={tag}
                  variant={activeTag === tag ? "default" : "secondary"}
                  className="text-[10px] cursor-pointer px-2 py-0.5"
                  onClick={() => setActiveTag(activeTag === tag ? "" : tag)}
                  data-testid={`tag-filter-${tag}`}
                >
                  {tag}
                </Badge>
              ))}
            </div>
          )}

          <SidebarSafetyNav />

          <ScrollArea className="flex-1 px-3">
            <div className="space-y-1 pb-4">
              {filteredConversations.length === 0 ? (
                <p className="text-xs text-muted-foreground px-2 py-4">
                  {sidebarFilter || activeTag ? "No matches found." : "No conversations yet. Ask a question to get started!"}
                </p>
              ) : (
                <>
                  {pinnedConversations.length > 0 && (
                    <>
                      <div className="px-2 pt-1 pb-1">
                        <h4 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1" data-testid="text-pinned-heading">
                          <Pin className="w-3 h-3" /> Pinned
                        </h4>
                      </div>
                      {pinnedConversations.map((conv) => renderConversationItem(conv, true))}
                      <div className="my-2 h-px bg-border" />
                    </>
                  )}
                  {unpinnedConversations.length > 0 && (
                    <>
                      <div className="px-2 pt-1 pb-1">
                        <h4 className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider" data-testid="text-conversations-heading">
                          Conversations
                        </h4>
                      </div>
                      {unpinnedConversations.map((conv) => renderConversationItem(conv, false))}
                    </>
                  )}
                </>
              )}
            </div>
          </ScrollArea>

          <div className="p-3 border-t mt-auto" data-testid="sidebar-user-section">
            {user && (
              <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-muted/50" data-testid="user-info-card">
                <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                  <User className="w-4 h-4 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" data-testid="text-user-name">
                    {getUserDisplayName(user)}
                  </p>
                  <p className="text-[10px] text-muted-foreground truncate" data-testid="text-user-email">
                    {user.email}
                  </p>
                </div>
                <Button variant="ghost" size="icon" onClick={handleLogout} data-testid="button-logout">
                  <LogOut className="w-4 h-4" />
                </Button>
              </div>
            )}
          </div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="border-b glass-panel sticky top-0 z-50 flex-shrink-0">
          <div className="px-4 sm:px-6 py-3 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              {!sidebarOpen && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setSidebarOpen(true)}
                  data-testid="button-open-sidebar"
                >
                  <PanelLeft className="w-4 h-4" />
                </Button>
              )}
              <div className="hidden sm:flex items-center gap-2.5">
                <img
                  src="/aestheticite-logo.png"
                  alt="AesthetiCite"
                  className="w-8 h-8 object-contain rounded-lg"
                  data-testid="img-header-logo"
                />
                <span className="text-lg font-semibold tracking-tight">{BRAND.name}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {activeSources.length > 0 && (
                <Badge variant="secondary" className="hidden md:flex items-center gap-1.5 text-xs" data-testid="badge-active-sources">
                  <BookOpen className="w-3 h-3" />
                  {activeSources.length} sources
                </Badge>
              )}
              <Badge variant="secondary" className="hidden md:flex items-center gap-1.5 text-xs">
                <BookOpen className="w-3 h-3" />
                {BRAND.publicationsLabel}
              </Badge>
              <Link href="/ask-oe">
                <Button variant="ghost" size="sm" className="hidden md:flex items-center gap-1.5 text-xs h-8" data-testid="button-ask-oe" title="Structured Evidence View">
                  <FileText className="w-3.5 h-3.5" />
                  <span>Evidence</span>
                </Button>
              </Link>
              <Link href="/hardest-10">
                <Button variant="ghost" size="sm" className="hidden md:flex items-center gap-1.5 text-xs h-8" data-testid="button-hardest10" title="10 Hardest Questions vs General AI">
                  <BarChart3 className="w-3.5 h-3.5" />
                  <span>Challenge</span>
                </Button>
              </Link>
              <Link href="/safety-check">
                <Button
                  variant="outline"
                  size="sm"
                  className="hidden md:flex items-center gap-1.5 text-xs h-8 border-blue-200 text-blue-700 hover:bg-blue-50 hover:border-blue-400 dark:border-blue-800 dark:text-blue-400"
                  data-testid="button-safety-check"
                  title="Pre-Procedure Safety Check"
                >
                  <ShieldAlert className="w-3.5 h-3.5" />
                  <span>Safety</span>
                </Button>
              </Link>
              <Link href="/decide">
                <Button
                  variant="ghost"
                  size="sm"
                  className="hidden md:flex items-center gap-1.5 text-xs h-8 text-orange-600 hover:bg-orange-50 hover:text-orange-700 dark:text-orange-400 dark:hover:bg-orange-950/30"
                  data-testid="button-decide"
                  title="Complication Clinical Decision"
                >
                  <Shield className="w-3.5 h-3.5" />
                  <span>Decide</span>
                </Button>
              </Link>
              <Link href="/emergency">
                <Button
                  variant="ghost"
                  size="sm"
                  className="hidden md:flex items-center gap-1.5 text-xs h-8 bg-red-600 hover:bg-red-700 text-white border-0"
                  data-testid="button-emergency"
                  title="Emergency Complication Protocols"
                >
                  <Zap className="w-3.5 h-3.5" />
                  <span>Emergency</span>
                </Button>
              </Link>
              <Link href="/visual-counsel">
                <Button variant="ghost" size="sm" className="hidden md:flex items-center gap-1.5 text-xs h-8" data-testid="button-visual-counsel" title="Visual Counseling">
                  <Eye className="w-3.5 h-3.5" />
                  <span>Visuals</span>
                </Button>
              </Link>
              <Button
                variant="ghost"
                size="sm"
                className="hidden sm:flex items-center gap-1.5 text-xs h-8"
                onClick={() => setShowClinicalTools(true)}
                data-testid="button-clinical-tools-header"
                title="Clinical Tools — BMI, BSA, eGFR, Unit Converter"
              >
                <Calculator className="w-3.5 h-3.5" />
                <span>Tools</span>
              </Button>
              {/* Mobile full-nav sheet — visible only below md breakpoint */}
              <Sheet>
                <SheetTrigger asChild>
                  <Button variant="ghost" size="icon" className="flex md:hidden h-8 w-8" data-testid="button-mobile-menu">
                    <Menu className="w-4 h-4" />
                  </Button>
                </SheetTrigger>
                <SheetContent side="right" className="w-72 overflow-y-auto">
                  <SheetHeader className="mb-4">
                    <SheetTitle className="text-left">Navigation</SheetTitle>
                  </SheetHeader>
                  <div className="space-y-6 text-sm">
                    <Link href="/emergency" className="flex items-center gap-3 rounded-lg px-3 py-3 bg-red-600 text-white font-bold hover:bg-red-700 transition-colors">
                      <Zap className="h-4 w-4" />Emergency Protocols
                    </Link>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Search</p>
                      <div className="space-y-1">
                        <Link href="/ask" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Search className="h-4 w-4" />AesthetiCite Search</Link>
                        <Link href="/ask-oe" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><FileText className="h-4 w-4" />Structured Evidence</Link>
                        <Link href="/hardest-10" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><BarChart3 className="h-4 w-4" />Challenge Mode</Link>
                      </div>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Safety &amp; Tools</p>
                      <div className="space-y-1">
                        <Link href="/safety-check" className="flex items-center gap-3 rounded-lg px-3 py-2 bg-blue-50 text-blue-700 font-semibold hover:bg-blue-100 transition-colors">
                          <ShieldAlert className="h-4 w-4" />Pre-Procedure Safety
                        </Link>
                        <Link href="/session-report" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><SessionIcon className="h-4 w-4" />Session Safety Report</Link>
                        <Link href="/drug-interactions" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Pill className="h-4 w-4" />Drug Interactions</Link>
                        <Link href="/patient-export" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><FileUser className="h-4 w-4" />Patient Export</Link>
                        <Link href="/case-log" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Database className="h-4 w-4" />Case Log</Link>
                        <Link href="/visual-counsel" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Eye className="h-4 w-4" />Visual Counseling</Link>
                      </div>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">My Account</p>
                      <div className="space-y-1">
                        <Link href="/bookmarks" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Bookmark className="h-4 w-4" />Saved Answers</Link>
                        <Link href="/paper-alerts" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Bell className="h-4 w-4" />Paper Alerts</Link>
                      </div>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Clinic</p>
                      <div className="space-y-1">
                        <Link href="/clinic-dashboard" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><LayoutDashboard className="h-4 w-4" />Clinic Dashboard</Link>
                        <Link href="/api-keys" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Key className="h-4 w-4" />API Keys</Link>
                      </div>
                    </div>
                  </div>
                </SheetContent>
              </Sheet>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" className="hidden md:flex items-center gap-1 text-xs h-8" data-testid="button-more-menu">
                    <MoreHorizontal className="w-3.5 h-3.5" />
                    <span>More</span>
                    <ChevronDown className="w-3 h-3 opacity-50" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel>Clinical</DropdownMenuLabel>
                  <DropdownMenuItem asChild>
                    <Link href="/emergency" className="flex items-center gap-2 cursor-pointer text-red-600">
                      <Zap className="h-4 w-4" />Emergency Protocols
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link href="/drug-interactions" className="flex items-center gap-2 cursor-pointer">
                      <Pill className="h-4 w-4 text-muted-foreground" />Drug Interaction Checker
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link href="/session-report" className="flex items-center gap-2 cursor-pointer">
                      <SessionIcon className="h-4 w-4 text-muted-foreground" />Session Safety Report
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link href="/patient-export" className="flex items-center gap-2 cursor-pointer">
                      <FileUser className="h-4 w-4 text-muted-foreground" />Patient-Readable Export
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link href="/case-log" className="flex items-center gap-2 cursor-pointer">
                      <Database className="h-4 w-4 text-muted-foreground" />Case Log
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuLabel>My Account</DropdownMenuLabel>
                  <DropdownMenuItem asChild>
                    <Link href="/bookmarks" className="flex items-center gap-2 cursor-pointer">
                      <Bookmark className="h-4 w-4 text-muted-foreground" />Saved Answers
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link href="/paper-alerts" className="flex items-center gap-2 cursor-pointer">
                      <Bell className="h-4 w-4 text-muted-foreground" />Paper Alerts
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuLabel>Clinic</DropdownMenuLabel>
                  <DropdownMenuItem asChild>
                    <Link href="/clinic-dashboard" className="flex items-center gap-2 cursor-pointer">
                      <LayoutDashboard className="h-4 w-4 text-muted-foreground" />Clinic Dashboard
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link href="/api-keys" className="flex items-center gap-2 cursor-pointer">
                      <Key className="h-4 w-4 text-muted-foreground" />API Keys
                    </Link>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              <UsageIndicator />
              <LanguageSelector />
              <ThemeToggle />
            </div>
          </div>

          {activeSources.length > 0 && (
            <div className="border-t px-4 py-2 flex gap-2 overflow-x-auto" data-testid="sources-ribbon">
              {activeSources.slice(0, 14).map((s, i) => {
                const link = s.source_id?.includes("pmc_")
                  ? `https://pmc.ncbi.nlm.nih.gov/articles/PMC${s.source_id.replace("pmc_", "")}/`
                  : s.source_id?.startsWith("PMID_")
                  ? `https://pubmed.ncbi.nlm.nih.gov/${s.source_id.replace("PMID_", "")}/`
                  : null;
                const tierInfo = getTierInfo(s.tier);
                return (
                  <a
                    key={`src-${i}`}
                    href={link || "#"}
                    target={link ? "_blank" : undefined}
                    rel="noreferrer"
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs whitespace-nowrap transition-colors ${
                      link ? "bg-muted hover-elevate cursor-pointer" : "bg-muted/50 text-muted-foreground"
                    }`}
                    title={`${s.title || "Source"}${s.year ? ` (${s.year})` : ""}\n${s.organization_or_journal || ""}`}
                    data-testid={`source-ribbon-${i}`}
                  >
                    {tierInfo && (
                      <span className={`w-1.5 h-1.5 rounded-full ${tierInfo.dotColor}`} />
                    )}
                    <span className="font-medium">[{i + 1}]</span>
                    <span className="truncate max-w-[120px]">{s.title?.slice(0, 30) || `Source ${i + 1}`}</span>
                    {s.year && <span className="text-muted-foreground">{s.year}</span>}
                    {link && <ExternalLink className="w-3 h-3 text-muted-foreground flex-shrink-0" />}
                  </a>
                );
              })}
            </div>
          )}
        </header>

        <div className="flex-1 overflow-auto" ref={scrollBoxRef}>
          <div className={`mx-auto px-4 sm:px-6 py-6 ${!hasMessages ? "max-w-3xl" : "max-w-6xl"}`}>
            {!hasMessages && (
              <div className="flex flex-col items-center justify-center min-h-[calc(100vh-180px)] px-4" data-testid="empty-state">
                <ComplicationQuickStart
                  onQuery={(q) => {
                    setInput(q);
                    if (q.trim()) {
                      setTimeout(() => handleAsk(q), 0);
                    }
                  }}
                  isLoading={isLoading}
                  recentSearches={recentSearches}
                />
                <NetworkStatsBar className="mt-3" />
                {/* Domain + enhanced mode controls preserved below the quick-start */}
                <div className="flex items-center justify-center gap-3 mt-4 flex-wrap">
                  <Select value={domain} onValueChange={setDomain}>
                    <SelectTrigger className="bg-muted/50 border-0 w-auto min-w-[140px] h-8 text-xs" data-testid="select-domain-hero">
                      <SelectValue placeholder="Specialty" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="aesthetic_medicine">Aesthetic Medicine</SelectItem>
                      <SelectItem value="dental_medicine">Dental Medicine</SelectItem>
                      <SelectItem value="general_medicine">General Medicine</SelectItem>
                    </SelectContent>
                  </Select>

                  <div className="flex items-center gap-1.5">
                    <Switch
                      id="enhanced-mode-hero"
                      checked={enhancedMode}
                      onCheckedChange={setEnhancedMode}
                      data-testid="switch-enhanced-mode-hero"
                      className="scale-90"
                    />
                    <Label htmlFor="enhanced-mode-hero" className="text-xs cursor-pointer flex items-center gap-1">
                      <Shield className="w-3 h-3 text-emerald-500" />
                      Enhanced
                    </Label>
                  </div>

                  <VoiceInput
                    onTranscript={(text) => setInput((prev) => (prev ? `${prev} ${text}` : text))}
                    disabled={isLoading}
                  />
                </div>
              </div>
            )}

            {messages.map((msg, idx) => (
              <div key={msg.id} className="mb-6" data-testid={`chat-message-${msg.id}`}>
                {msg.role === "user" ? (
                  <div className="flex justify-end mb-2">
                    <div className="max-w-2xl rounded-2xl px-5 py-3 bg-primary text-primary-foreground">
                      <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {msg.isRefusal ? (
                      <Card className="border-destructive/30 bg-destructive/5" data-testid="section-refusal">
                        <CardContent className="p-6">
                          <div className="flex items-start gap-4">
                            <div className="w-10 h-10 rounded-full bg-destructive/10 flex items-center justify-center flex-shrink-0">
                              <AlertTriangle className="w-5 h-5 text-destructive" />
                            </div>
                            <div>
                              <h3 className="font-semibold text-destructive mb-1">Unable to Answer</h3>
                              <p className="text-muted-foreground">
                                {msg.refusalReason || "Insufficient evidence to provide a reliable answer."}
                              </p>
                              {msg.refusalCode && (
                                <Badge variant="secondary" className="mt-2 text-xs" data-testid="badge-refusal-code">
                                  {msg.refusalCode}
                                </Badge>
                              )}
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ) : (
                      <>
                        {msg.complicationProtocol?.triggered && (
                          <ComplicationProtocolAlert protocol={msg.complicationProtocol} />
                        )}

                        {msg.complicationProtocol?.triggered && !msg.isStreaming && (
                          <ClinicalReasoningSection
                            complication={msg.complicationProtocol?.triggers_matched?.[0] ?? "aesthetic complication"}
                            symptoms={msg.complicationProtocol?.triggers_matched?.slice(1) ?? []}
                            autoFetch={true}
                            className="my-4"
                          />
                        )}

                        {msg.complicationProtocol?.triggered && !msg.isStreaming && (
                          <div className="space-y-2 my-4">
                            <SimilarCasesPanel
                              complication={msg.complicationProtocol?.triggers_matched?.[0] ?? "aesthetic complication"}
                            />
                            <div className="flex gap-2 flex-wrap">
                              <LogCaseButton
                                complication={msg.complicationProtocol?.triggers_matched?.[0] ?? "aesthetic complication"}
                                size="sm"
                                variant="outline"
                                label="Log This Case"
                              />
                              <Link href={`/decide?complication=${encodeURIComponent(
                                msg.complicationProtocol?.triggers_matched?.[0] ?? ""
                              )}`}>
                                <Button size="sm" variant="default" className="gap-1.5" data-testid="button-run-protocol">
                                  <Shield className="h-3.5 w-3.5" />
                                  Run Protocol
                                </Button>
                              </Link>
                            </div>
                          </div>
                        )}

                        {msg.safety && !msg.isStreaming && (
                          <SafetyEscalationBlock
                            safety={msg.safety}
                            className="my-4"
                          />
                        )}

                        {msg.aciScore !== undefined && msg.aciScore !== null && (
                          <ACIScoreDisplay score={msg.aciScore} queryMeta={msg.queryMeta ?? undefined} />
                        )}

                        {msg.inlineTools && msg.inlineTools.length > 0 && (
                          <InlineToolsDisplay tools={msg.inlineTools} />
                        )}

                        {!msg.isStreaming && msg.citations && msg.citations.length > 0 && (
                          <div className="flex items-center gap-3 flex-wrap">
                            <Badge variant="secondary" className="gap-1" data-testid="badge-sources">
                              <BookOpen className="w-3 h-3" />
                              {msg.citations.length} sources
                            </Badge>
                            {(msg.evidenceBadge || msg.evidenceStrength) && (
                              <TopEvidenceBadge
                                badge={msg.evidenceBadge}
                                citations={(msg.citations ?? []) as unknown as EHCitation[]}
                                size="md"
                                className="gap-1"
                              />
                            )}
                            {enhancedMode && (
                              <Badge variant="outline" className="gap-1 text-emerald-600 dark:text-emerald-400" data-testid="badge-enhanced-mode">
                                <Shield className="w-3 h-3" />
                                Enhanced
                              </Badge>
                            )}
                            {getReadingTime(msg.content) && (
                              <Badge variant="outline" className="gap-1 text-muted-foreground" data-testid="badge-reading-time">
                                <Clock className="w-3 h-3" />
                                {getReadingTime(msg.content)}
                              </Badge>
                            )}
                          </div>
                        )}

                        {msg.clinicalSummary && (
                          <Card className="border-emerald-500/30 bg-emerald-500/5" data-testid="section-clinical-summary">
                            <CardContent className="p-4">
                              <div className="flex items-start gap-3">
                                <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center flex-shrink-0">
                                  <Shield className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                                </div>
                                <div>
                                  <h3 className="font-semibold text-sm text-emerald-700 dark:text-emerald-300 mb-1">
                                    Clinical Summary
                                  </h3>
                                  <p className="text-sm text-muted-foreground">{msg.clinicalSummary}</p>
                                </div>
                              </div>
                            </CardContent>
                          </Card>
                        )}

                        <StructuredAnswer
                          msg={msg}
                          lastQuestion={lastQuestion}
                          onRelatedQuestion={handleRelatedQuestion}
                          onCopyNote={copyNote}
                          copiedNote={copiedNote}
                          streamingPhaseText={STREAMING_PHASES[streamingPhase]}
                          onStop={handleStop}
                        />
                        {msg.protocolCard && !msg.isStreaming && (
                          <ProtocolCard data={msg.protocolCard} />
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}


            <div ref={bottomRef} />
          </div>
        </div>

        {hasMessages && (
          <div className="border-t glass-panel flex-shrink-0 p-4" data-testid="composer">
            <div className="max-w-4xl mx-auto">
              <div className="flex items-end gap-3">
                <div className="flex-1 relative">
                  <Textarea
                    ref={inputRef}
                    rows={1}
                    placeholder="Ask a follow-up question..."
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        if (!isLoading && input.trim()) handleAsk();
                      }
                    }}
                    className="resize-none text-base bg-muted/50 rounded-xl pr-24 transition-colors focus:bg-background"
                    disabled={isLoading}
                    data-testid="input-question-chat"
                  />
                  <div className="absolute right-2 bottom-2 flex items-center gap-1">
                    <VoiceInput
                      onTranscript={(text) => setInput((prev) => (prev ? `${prev} ${text}` : text))}
                      disabled={isLoading}
                    />
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <Select value={domain} onValueChange={setDomain}>
                    <SelectTrigger className="bg-muted/50 border-0 w-auto min-w-[140px] hidden sm:flex" data-testid="select-domain">
                      <SelectValue placeholder="Specialty" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="aesthetic_medicine">Aesthetic Medicine</SelectItem>
                      <SelectItem value="dental_medicine">Dental Medicine</SelectItem>
                      <SelectItem value="general_medicine">General Medicine</SelectItem>
                    </SelectContent>
                  </Select>

                  <div className="hidden md:flex items-center gap-2">
                    <Switch
                      id="enhanced-mode"
                      checked={enhancedMode}
                      onCheckedChange={setEnhancedMode}
                      data-testid="switch-enhanced-mode"
                    />
                    <Label htmlFor="enhanced-mode" className="text-sm cursor-pointer flex items-center gap-1.5">
                      <Shield className="w-3.5 h-3.5 text-emerald-500" />
                      Enhanced
                    </Label>
                  </div>

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowClinicalTools(!showClinicalTools)}
                    title="Clinical Tools — BMI, BSA, eGFR, Unit Converter"
                    data-testid="button-tools-toggle"
                    className="hidden sm:flex items-center gap-1.5 h-9"
                  >
                    <Calculator className="h-3.5 w-3.5" />
                    <span className="hidden md:inline text-xs">Tools</span>
                  </Button>

                  {isLoading ? (
                    <Button
                      onClick={handleStop}
                      variant="destructive"
                      className="flex items-center gap-2"
                      data-testid="button-stop-chat"
                    >
                      <StopCircle className="h-4 w-4" />
                      <span className="hidden sm:inline">Stop</span>
                    </Button>
                  ) : (
                    <Button
                      onClick={() => handleAsk()}
                      disabled={!input.trim()}
                      className="shadow-lg shadow-primary/25 flex items-center gap-2 btn-press"
                      data-testid="button-ask-chat"
                    >
                      <Send className="h-4 w-4" />
                      <span className="hidden sm:inline">Ask</span>
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <ClinicalToolsPanel isOpen={showClinicalTools} onClose={() => setShowClinicalTools(false)} />
    </div>
  );
}

function renderWithCitations(text: string) {
  const parts = text.split(/(\[S?\d+\])/g);
  return parts.map((part, i) => {
    if (/^\[S?\d+\]$/.test(part)) {
      return (
        <span key={i} className="citation-link mx-0.5">
          {part.slice(1, -1)}
        </span>
      );
    }
    return part;
  });
}

function SectionCard({ title, children, right, icon, accent = "primary" }: { title: string; children: React.ReactNode; right?: React.ReactNode; icon?: React.ReactNode; accent?: "emerald" | "primary" | "amber" | "muted" | "purple" }) {
  const accentClass = {
    emerald: "section-accent-emerald",
    primary: "section-accent-primary",
    amber: "section-accent-amber",
    muted: "section-accent-muted",
    purple: "section-accent-purple",
  }[accent];
  return (
    <Card className={`section-card-accent ${accentClass}`} data-testid={`section-${title.toLowerCase().replace(/\s+/g, "-")}`}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-4 pb-3 border-b border-border/50">
          <div className="flex items-center gap-2 text-sm font-semibold tracking-tight">
            {icon}
            {title}
          </div>
          {right}
        </div>
        <div className="mt-3 text-sm leading-relaxed text-muted-foreground">{children}</div>
      </CardContent>
    </Card>
  );
}

function SourcePillWithHover({ citation, index }: { citation: Citation; index: number }) {
  const pubmedUrl = citation.source_id?.includes("pmc_")
    ? `https://pmc.ncbi.nlm.nih.gov/articles/PMC${citation.source_id.replace("pmc_", "")}/`
    : citation.source_id?.startsWith("PMID_")
    ? `https://pubmed.ncbi.nlm.nih.gov/${citation.source_id.replace("PMID_", "")}/`
    : null;
  const href = pubmedUrl || "#";
  const tierInfo = getTierInfo(citation.tier);
  const evidenceInfo = getEvidenceLevelInfo(citation.evidence_level);
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    await navigator.clipboard.writeText(buildCitationLine(citation));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <HoverCard openDelay={200} closeDelay={100}>
      <HoverCardTrigger asChild>
        <a
          href={href}
          target={pubmedUrl ? "_blank" : undefined}
          rel="noreferrer"
          className={`source-pill ${
            tierInfo?.label === "Tier A" ? "source-pill-a" :
            tierInfo?.label === "Tier B" ? "source-pill-b" :
            tierInfo?.label === "Tier C" ? "source-pill-c" :
            "source-pill-default"
          }`}
          data-testid={`source-pill-${index}`}
        >
          <span className={`font-semibold text-[11px] tabular-nums ${tierInfo ? tierInfo.color.split(" ")[1] : "text-muted-foreground"}`}>[{index}]</span>
          <span className="truncate max-w-[140px] font-medium">{citation.title?.slice(0, 38) || `Source ${index}`}</span>
          {citation.year && <span className="text-muted-foreground/70 text-[10px] flex-shrink-0">{citation.year}</span>}
          {pubmedUrl && <ExternalLink className="w-2.5 h-2.5 text-muted-foreground/60 flex-shrink-0" />}
        </a>
      </HoverCardTrigger>
      <HoverCardContent side="bottom" align="start" className="w-[360px] p-3">
        <div className="font-semibold text-sm mb-1">{citation.title || "Untitled"}</div>
        <div className="text-xs text-muted-foreground">
          {citation.year ? `${citation.year}` : "Year N/A"}
          {citation.study_type ? ` \u2022 ${citation.study_type}` : ""}
        </div>
        <div className="text-xs text-muted-foreground">{citation.organization_or_journal || ""}</div>
        {(tierInfo || evidenceInfo) && (
          <div className="mt-1.5 flex gap-1.5">
            {tierInfo && <Badge variant="outline" className={`text-[10px] ${tierInfo.color}`}>{tierInfo.label}</Badge>}
            {!tierInfo && evidenceInfo && <Badge variant="outline" className={`text-[10px] ${evidenceInfo.color}`}>{evidenceInfo.label}</Badge>}
          </div>
        )}
        {citation.quote && (
          <div className="mt-1.5 text-xs italic text-muted-foreground line-clamp-2">"{citation.quote}"</div>
        )}
        <div className="mt-2 flex gap-2">
          <Button variant="outline" size="sm" onClick={handleCopy} className="text-xs h-6 px-2" data-testid={`copy-citation-${index}`}>
            {copied ? <ClipboardCheck className="w-3 h-3 mr-1" /> : <Copy className="w-3 h-3 mr-1" />}
            {copied ? "Copied" : "Copy citation"}
          </Button>
          {pubmedUrl && (
            <Button variant="outline" size="sm" asChild className="text-xs h-6 px-2">
              <a href={pubmedUrl} target="_blank" rel="noreferrer">
                <ExternalLink className="w-3 h-3 mr-1" />
                Open
              </a>
            </Button>
          )}
        </div>
        <div className="mt-1.5 text-[10px] text-muted-foreground">
          {citation.source_id || ""}
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}

function SkeletonLine({ width = "100%" }: { width?: string }) {
  return <div className="h-3 rounded skeleton-shimmer" style={{ width }} />;
}

function AnswerSkeleton({ phase, onStop }: { phase: string; onStop: () => void }) {
  return (
    <div className="space-y-4 animate-float-in" data-testid="answer-skeleton">
      <div className="flex items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-2">
          <div className="w-3.5 h-3.5 rounded-full border-2 border-primary border-t-transparent animate-spin flex-shrink-0" />
          <span className="text-sm font-medium text-muted-foreground">
            {phase}<span className="thinking-dots" />
          </span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onStop}
          className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive gap-1"
          data-testid="button-stop-skeleton"
        >
          <StopCircle className="w-3.5 h-3.5" />
          Stop
        </Button>
      </div>

      <Card className="section-card-accent section-accent-emerald">
        <CardContent className="p-5">
          <div className="flex items-center gap-2 pb-3 border-b border-border/50">
            <div className="w-4 h-4 rounded skeleton-shimmer flex-shrink-0" />
            <div className="h-3.5 w-36 rounded skeleton-shimmer" />
          </div>
          <div className="mt-4 space-y-2.5">
            <SkeletonLine width="100%" />
            <SkeletonLine width="88%" />
            <SkeletonLine width="72%" />
          </div>
        </CardContent>
      </Card>

      <Card className="section-card-accent section-accent-primary">
        <CardContent className="p-5">
          <div className="flex items-center gap-2 pb-3 border-b border-border/50">
            <div className="w-4 h-4 rounded skeleton-shimmer flex-shrink-0" />
            <div className="h-3.5 w-52 rounded skeleton-shimmer" />
          </div>
          <div className="mt-4 space-y-3.5">
            {[["100%", "65%"], ["91%", "55%"], ["83%", "48%"]].map(([a, b], i) => (
              <div key={i} className="flex gap-3 items-start">
                <div className="w-5 h-5 rounded-full skeleton-shimmer flex-shrink-0 mt-0.5" />
                <div className="flex-1 space-y-1.5">
                  <SkeletonLine width={a} />
                  <SkeletonLine width={b} />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-1.5 px-1">
        {[80, 118, 96, 105, 88, 72].map((w, i) => (
          <div
            key={i}
            className="h-6 rounded-md skeleton-shimmer border-l-[3px] border-l-border/40"
            style={{ width: w, animationDelay: `${i * 0.12}s` }}
          />
        ))}
      </div>
    </div>
  );
}

function StructuredAnswer({ msg, lastQuestion, onRelatedQuestion, onCopyNote, copiedNote, streamingPhaseText, onStop }: {
  msg: ChatMessage;
  lastQuestion: string;
  onRelatedQuestion: (q: string) => void;
  onCopyNote: (text: string, withCitations: boolean) => void;
  copiedNote: string;
  streamingPhaseText: string;
  onStop: () => void;
}) {
  const sections = useMemo(() => parseSections(msg.content), [msg.content]);
  const cd = useMemo(() => citationDensityFromText(msg.content), [msg.content]);
  const pct = useMemo(() => citedClaimsPct(msg.content), [msg.content]);
  const hasSections = !!(sections.clinicalSummary || sections.keyPoints || sections.safety || sections.limitations);
  const followups = sections.followups || [];
  const relatedQuestions = msg.relatedQuestions || [];
  const allFollowups = Array.from(new Set([...followups, ...relatedQuestions])).slice(0, 8);

  return (
    <>
      <div className="grid gap-5 lg:grid-cols-[1fr_280px]">
        <div className="space-y-4">
          {msg.content ? (
            hasSections ? (
              <>
                {sections.clinicalSummary && (
                  <div className="animate-float-in">
                    <SectionCard title="Clinical Summary" accent="emerald" icon={<Shield className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />}>
                      <div className="whitespace-pre-wrap leading-7">{renderWithCitations(sections.clinicalSummary)}</div>
                    </SectionCard>
                  </div>
                )}

                {sections.keyPoints && sections.keyPoints.length > 0 && (
                  <div className="animate-float-in animate-float-in-delay-1">
                    <SectionCard
                      title="Key Evidence-Based Points"
                      accent="primary"
                      icon={<FileText className="w-4 h-4 text-primary" />}
                      right={
                        <div className="flex items-center gap-1 text-xs text-muted-foreground bg-muted/60 px-2 py-0.5 rounded-full">
                          <span className="font-semibold text-foreground">{pct}%</span> cited
                        </div>
                      }
                    >
                      <ul className="space-y-3 mt-1">
                        {sections.keyPoints.map((p, i) => (
                          <li key={i} className="flex gap-3 items-start">
                            <div className="flex-shrink-0 w-5 h-5 rounded-full bg-primary/10 text-primary text-[10px] font-bold flex items-center justify-center mt-0.5 ring-1 ring-primary/20">
                              {i + 1}
                            </div>
                            <span className="leading-relaxed flex-1">{renderWithCitations(p)}</span>
                          </li>
                        ))}
                      </ul>
                    </SectionCard>
                  </div>
                )}

                {sections.safety && (
                  <div className="animate-float-in animate-float-in-delay-2">
                    <SectionCard title="Safety Considerations" accent="amber" icon={<AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />}>
                      <div className="whitespace-pre-wrap leading-7">{renderWithCitations(sections.safety)}</div>
                    </SectionCard>
                  </div>
                )}

                {sections.limitations && (
                  <div className="animate-float-in animate-float-in-delay-3">
                    <SectionCard title="Limitations / Uncertainty" accent="muted" icon={<AlertCircle className="w-4 h-4 text-muted-foreground" />}>
                      <div className="whitespace-pre-wrap leading-7">{renderWithCitations(sections.limitations)}</div>
                    </SectionCard>
                  </div>
                )}
              </>
            ) : (
              <Card data-testid="section-answer">
                <CardContent className="p-6 sm:p-8">
                  <AnswerContent answer={msg.content} />
                  {msg.isStreaming && msg.content && (
                    <span className="inline-block w-2 h-5 bg-primary animate-pulse ml-0.5" />
                  )}
                </CardContent>
              </Card>
            )
          ) : msg.isStreaming ? (
            <AnswerSkeleton phase={streamingPhaseText} onStop={onStop} />
          ) : null}

          {hasSections && msg.isStreaming && msg.content && (
            <span className="inline-block w-2 h-5 bg-primary animate-pulse ml-0.5" />
          )}

          {!msg.isStreaming && msg.citations && msg.citations.length > 0 && (
            <RankedSourcesSection citations={msg.citations} />
          )}

          {!msg.isStreaming && msg.citations && msg.citations.length > 0 && (
            <EvidencePanel
              citations={(msg.citations) as unknown as EHCitation[]}
              topBadge={msg.evidenceBadge}
              className="mt-2"
            />
          )}

          {allFollowups.length > 0 && !msg.isStreaming && (
            <SectionCard title="Follow-up Questions" accent="purple" icon={<Sparkles className="w-4 h-4 text-violet-500" />}>
              <div className="flex flex-wrap gap-2 mt-1">
                {allFollowups.map((f, i) => (
                  <button
                    key={i}
                    className="followup-chip"
                    onClick={() => onRelatedQuestion(f)}
                    data-testid={`followup-chip-${i}`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </SectionCard>
          )}

          {!msg.isStreaming && msg.content && (
            <div className="space-y-3">
            <p className="text-[11px] text-muted-foreground/60 leading-relaxed" data-testid="text-disclaimer">
              AI-generated summary for informational purposes only. Not a substitute for professional medical judgment.
              Always verify against primary sources. Generated {new Date(msg.created_at || Date.now()).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}.
            </p>
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-2">
                <AnswerFeedback question={lastQuestion} />
                {cd > 0 && (
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <BarChart3 className="w-3 h-3" />
                    Density: {cd}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onCopyNote(msg.content, true)}
                  data-testid="button-copy-with-citations"
                >
                  {copiedNote === "with" ? <ClipboardCheck className="w-3 h-3 mr-1.5" /> : <Copy className="w-3 h-3 mr-1.5" />}
                  {copiedNote === "with" ? "Copied" : "Copy as note"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onCopyNote(msg.content, false)}
                  data-testid="button-copy-without-citations"
                >
                  {copiedNote === "without" ? <ClipboardCheck className="w-3 h-3 mr-1.5" /> : <Copy className="w-3 h-3 mr-1.5" />}
                  {copiedNote === "without" ? "Copied" : "Copy plain"}
                </Button>
                <FavoritesButton question={lastQuestion} answer={msg.content} />
                <ExportShare
                  question={lastQuestion}
                  answer={msg.content}
                  citations={(msg.citations || []).map((c) => ({
                    title: c.title,
                    source: c.organization_or_journal,
                    year: c.year,
                  }))}
                  clinicalSummary={msg.clinicalSummary}
                />
              </div>
            </div>
            </div>
          )}
        </div>

        <div className="hidden lg:block">
          <div className="sticky top-24 space-y-4">
            <Card data-testid="section-evidence-summary">
              <CardContent className="p-4">
                <div className="flex items-center justify-between gap-2 mb-3">
                  <div className="text-xs font-semibold flex items-center gap-1.5">
                    <Shield className="w-3.5 h-3.5 text-primary" />
                    Evidence Strength
                  </div>
                  {msg.content && cd > 0 && (
                    <span className="text-[10px] text-muted-foreground">
                      Density: <span className="font-semibold">{cd}</span>
                    </span>
                  )}
                </div>
                {sections.evidenceSummary ? (
                  <div className="text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap">{renderWithCitations(sections.evidenceSummary)}</div>
                ) : (
                  <div className="text-xs text-muted-foreground">
                    {msg.content ? "Evidence summary will appear when the answer includes structured sections." : "Ask a question to see confidence score, evidence level, and gaps."}
                  </div>
                )}
                {msg.aciScore !== undefined && msg.aciScore !== null && (
                  <div className="mt-3">
                    <ACIScoreDisplay score={msg.aciScore} />
                  </div>
                )}
              </CardContent>
            </Card>

            <Card data-testid="section-governance">
              <CardContent className="p-4">
                <div className="text-xs font-semibold mb-2 flex items-center gap-1.5">
                  <Info className="w-3.5 h-3.5" />
                  Governance
                </div>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li className="flex items-start gap-1.5"><div className="w-1 h-1 rounded-full bg-muted-foreground mt-1.5 flex-shrink-0" />No cite = no claim</li>
                  <li className="flex items-start gap-1.5"><div className="w-1 h-1 rounded-full bg-muted-foreground mt-1.5 flex-shrink-0" />Explicit limitations</li>
                  <li className="flex items-start gap-1.5"><div className="w-1 h-1 rounded-full bg-muted-foreground mt-1.5 flex-shrink-0" />Evidence gaps shown</li>
                  <li className="flex items-start gap-1.5"><div className="w-1 h-1 rounded-full bg-muted-foreground mt-1.5 flex-shrink-0" />Conservative language</li>
                </ul>
              </CardContent>
            </Card>

            <p className="text-[10px] text-muted-foreground">
              Educational decision support. Not a substitute for clinical judgment.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}

function AnswerContent({ answer }: { answer: string }) {
  const lines = answer.split("\n");

  return (
    <div className="prose prose-neutral dark:prose-invert max-w-none">
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return null;

        if (trimmed.startsWith("**") && trimmed.endsWith("**")) {
          const text = trimmed.slice(2, -2);
          const isMainHeader = text === "Clinical Summary" || text === "Evidence Summary";

          if (isMainHeader) {
            return (
              <div key={i} className="flex items-center gap-3 mb-6 pb-4 border-b not-prose">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-primary/70 flex items-center justify-center">
                  <FileText className="w-5 h-5 text-primary-foreground" />
                </div>
                <h2 className="text-xl font-bold tracking-tight">{text}</h2>
              </div>
            );
          }

          return (
            <h3 key={i} className="text-base font-semibold mt-6 mb-3 text-foreground flex items-center gap-2 not-prose">
              <div className="w-1.5 h-1.5 rounded-full bg-primary" />
              {text}
            </h3>
          );
        }

        if (trimmed.startsWith("- ")) {
          const content = trimmed.slice(2);
          return (
            <div key={i} className="flex gap-3 py-2.5 not-prose border-b border-border/30 last:border-0">
              <div className="w-1.5 h-5 rounded-full bg-primary/40 flex-shrink-0 mt-0.5" />
              <p className="text-[15px] leading-[1.75] text-foreground/85">{renderWithCitations(content)}</p>
            </div>
          );
        }

        return (
          <p key={i} className="text-[15px] leading-[1.8] text-foreground/80 mb-3 not-prose">
            {renderWithCitations(trimmed)}
          </p>
        );
      })}
    </div>
  );
}

function getEvidenceLevelInfo(level: string | undefined) {
  switch (level?.toUpperCase()) {
    case "I":
      return { label: "Level I", color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20", description: "High-quality RCT/Meta-analysis" };
    case "II":
      return { label: "Level II", color: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20", description: "Moderate quality" };
    case "III":
      return { label: "Level III", color: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20", description: "Case-control study" };
    case "IV":
      return { label: "Level IV", color: "bg-gray-500/10 text-gray-600 dark:text-gray-400 border-gray-500/20", description: "Case report/Expert opinion" };
    default:
      return null;
  }
}

const EVIDENCE_TYPE_RANK: Record<string, number> = {
  "Guideline/Consensus": 1,
  "Systematic Review": 2,
  "Randomized Trial": 3,
  "Observational Study": 4,
  "Narrative Review": 5,
  "Case Report/Series": 6,
  "Other": 7,
};

function rankCitations(citations: Citation[]): Citation[] {
  return [...citations].sort((a, b) => {
    const ra = EVIDENCE_TYPE_RANK[(a as any).evidence_type] ?? 7;
    const rb = EVIDENCE_TYPE_RANK[(b as any).evidence_type] ?? 7;
    if (ra !== rb) return ra - rb;
    const ta = a.tier?.toUpperCase() ?? "Z";
    const tb = b.tier?.toUpperCase() ?? "Z";
    if (ta !== tb) return ta < tb ? -1 : 1;
    return (b.year ?? 0) - (a.year ?? 0);
  });
}

const TOP_SOURCES_COUNT = 8;

function RankedSourcesSection({ citations }: { citations: Citation[] }) {
  const [expanded, setExpanded] = useState(false);
  const ranked = useMemo(() => rankCitations(citations), [citations]);
  const showToggle = ranked.length > TOP_SOURCES_COUNT;
  const visible = expanded ? ranked : ranked.slice(0, TOP_SOURCES_COUNT);

  return (
    <div className="animate-float-in animate-float-in-delay-4" data-testid="section-citations-pills">
      <div className="flex items-center justify-between gap-4 mb-3">
        <h3 className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-widest">
          <BookOpen className="w-3.5 h-3.5" />
          Sources
        </h3>
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground/60">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-3 rounded-full bg-emerald-500 inline-block" /> Tier A
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-3 rounded-full bg-blue-500 inline-block" /> Tier B
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-3 rounded-full bg-amber-500 inline-block" /> Tier C
          </span>
          <span className="text-muted-foreground/40">· {ranked.length} refs · hover for details</span>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {visible.map((c, i) => (
          <SourcePillWithHover key={`src-${c.source_id}-${i}`} citation={c} index={i + 1} />
        ))}
      </div>
      {showToggle && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-3 flex items-center gap-1.5 text-xs text-primary hover:text-primary/80 transition-colors font-medium btn-press"
          data-testid="button-toggle-all-sources"
        >
          {expanded ? (
            <>
              <ChevronUp className="w-3 h-3" />
              Show fewer sources
            </>
          ) : (
            <>
              <ChevronDown className="w-3 h-3" />
              Show all {ranked.length} sources
            </>
          )}
        </button>
      )}
    </div>
  );
}

function getTierInfo(tier: string | undefined) {
  switch (tier?.toUpperCase()) {
    case "A":
      return { label: "Tier A", color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20", description: "High-quality primary evidence", dotColor: "bg-emerald-500" };
    case "B":
      return { label: "Tier B", color: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20", description: "Moderate quality evidence", dotColor: "bg-blue-500" };
    case "C":
      return { label: "Tier C", color: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20", description: "Lower quality evidence", dotColor: "bg-amber-500" };
    default:
      return null;
  }
}

function getStrengthInfo(strength: string | undefined) {
  switch (strength?.toLowerCase()) {
    case "high":
      return { label: "High", color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20", icon: Shield };
    case "moderate":
      return { label: "Moderate", color: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20", icon: Shield };
    case "limited":
      return { label: "Limited", color: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20", icon: AlertTriangle };
    default:
      return null;
  }
}

