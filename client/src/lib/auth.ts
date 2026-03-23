export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("aestheticite_token");
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("aestheticite_token", token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("aestheticite_token");
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

interface LoginResponse {
  access_token: string;
  token_type: string;
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

export async function login(email: string, password: string): Promise<string> {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail || "Login failed");
  }
  return (data as LoginResponse).access_token;
}

export async function getMe(token: string): Promise<UserInfo> {
  const res = await fetch("/api/auth/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail || "Auth check failed");
  }
  return data as UserInfo;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  related_questions: string[];
  refusal: boolean;
  refusal_reason?: string;
  request_id: string;
  latency_ms: number;
}

export interface Citation {
  source_id: string;
  title: string;
  year?: number;
  organization_or_journal?: string;
  page_or_section?: string;
  evidence_level?: string;
  snippet?: string;
  tier?: string;
  study_type?: string;
  score?: number;
  quote?: string;
}

export interface AskOEResponse {
  status: "ok" | "refuse";
  answer?: string;
  clinical_summary?: string;
  citations: Citation[];
  related_questions?: string[];
  evidence_strength?: string;
  refusal_code?: string;
  refusal_reason?: string;
  aci_score?: number;
  query_meta?: QueryMeta;
  complication_protocol?: ComplicationProtocol;
}

export async function askQuestionOE(
  token: string,
  query: string,
  domain: string = "aesthetic_medicine",
  lang: string = "en",
  includeRelated: boolean = true,
  conversationId: string = ""
): Promise<AskOEResponse> {
  const body: Record<string, unknown> = {
    query,
    domain,
    lang,
    include_related_questions: includeRelated,
  };
  if (conversationId) body.conversation_id = conversationId;
  const res = await fetch("/api/ask_oe", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail || "Enhanced query failed");
  }
  return data as AskOEResponse;
}

export async function askQuestion(
  token: string,
  question: string,
  domain: string = "aesthetic_medicine",
  mode: string = "clinic"
): Promise<AskResponse> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ question, domain, mode }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail || "Ask failed");
  }
  return data as AskResponse;
}

export interface QueryMeta {
  is_injectable: boolean;
  is_device: boolean;
  risk_level: "low" | "medium" | "high";
  high_risk_zones: string[];
  category: string;
}

export interface ComplicationProtocol {
  triggered: boolean;
  red_flags: string[];
  immediate_actions: string[];
  triggers_matched: string[];
}

export interface InlineTool {
  tool: string;
  input?: Record<string, unknown>;
  output: Record<string, unknown>;
}

export interface ACIDetails {
  overall_confidence_0_10: number;
  highest_level: string;
  supporting_count: number;
  gaps: string[];
  mix: Record<string, number>;
}

export interface StreamMetaData {
  citations: Citation[];
  requestId: string;
  aciScore?: number;
  aciDetails?: ACIDetails;
  queryMeta?: QueryMeta;
  complicationProtocol?: ComplicationProtocol;
  inlineTools?: InlineTool[];
  evidenceBadge?: { level: string; label: string; color: string; best_type?: string; emoji?: string };
  mode?: string;
}

export interface StreamCallbacks {
  onToken: (token: string) => void;
  onMeta: (citations: Citation[], requestId: string, extra?: StreamMetaData) => void;
  onRelated: (questions: string[]) => void;
  onDone: (fullAnswer: string) => void;
  onError: (error: string) => void;
  onProtocolCard?: (data: any) => void;
}

export async function askQuestionStream(
  token: string,
  question: string,
  domain: string = "aesthetic_medicine",
  mode: string = "clinic",
  callbacks: StreamCallbacks,
  conversationId: string = ""
): Promise<void> {
  const body: Record<string, unknown> = { question, domain, mode };
  if (conversationId) body.conversation_id = conversationId;
  const res = await fetch("/api/ask/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.detail || "Stream request failed");
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const data = JSON.parse(line.slice(6));
          switch (data.type) {
            case "token":
              callbacks.onToken(data.content);
              break;
            case "meta":
              const rawAci = data.aci_score;
              const normalizedAci = rawAci && typeof rawAci === 'object'
                ? rawAci.overall_confidence_0_10
                : rawAci;
              callbacks.onMeta(data.citations, data.request_id, {
                citations: data.citations,
                requestId: data.request_id,
                aciScore: normalizedAci,
                aciDetails: rawAci && typeof rawAci === 'object' ? rawAci : undefined,
                queryMeta: data.query_meta,
                complicationProtocol: data.complication_protocol,
                inlineTools: data.inline_tools,
                evidenceBadge: data.evidence_badge,
                mode: data.mode,
              });
              break;
            case "related":
              callbacks.onRelated(data.questions);
              break;
            case "done":
              callbacks.onDone(data.full_answer);
              break;
            case "error":
              callbacks.onError(data.message);
              break;
            case "refusal":
              callbacks.onError(data.reason);
              break;
            case "protocol_card":
              if (callbacks.onProtocolCard) callbacks.onProtocolCard(data);
              break;
          }
        } catch {
          // Ignore parse errors
        }
      }
    }
  }
}

export async function askQuestionStreamV2(
  token: string,
  question: string,
  domain: string = "aesthetic_medicine",
  callbacks: StreamCallbacks,
  conversationId: string = "",
  signal?: AbortSignal
): Promise<void> {
  const body: Record<string, unknown> = { question, domain, mode: "standard" };
  if (conversationId) body.conversation_id = conversationId;
  const res = await fetch("/api/v2/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.detail || "Stream request failed");
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let fullAnswer = "";

  try {
    while (true) {
      if (signal?.aborted) {
        reader.cancel();
        callbacks.onDone(fullAnswer);
        break;
      }

      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            switch (data.type) {
              case "content":
                if (typeof data.data === "string") {
                  callbacks.onToken(data.data);
                  fullAnswer += data.data;
                }
                break;
              case "citations":
                {
                  const rawAci = data.aci_score;
                  const normalizedAci = rawAci && typeof rawAci === 'object'
                    ? rawAci.overall_confidence_0_10
                    : rawAci;
                  const cits = data.citations || [];
                  callbacks.onMeta(cits, "", {
                    citations: cits,
                    requestId: "",
                    aciScore: normalizedAci,
                    queryMeta: data.query_meta,
                    complicationProtocol: data.complication_protocol,
                    inlineTools: data.inline_tools,
                    evidenceBadge: data.evidence_badge,
                  });
                }
                break;
              case "badge":
                break;
              case "protocol_card":
                if (callbacks.onProtocolCard) callbacks.onProtocolCard(data);
                break;
              case "related":
                callbacks.onRelated(data.data || []);
                break;
              case "done":
                callbacks.onDone(fullAnswer);
                break;
              case "replace":
                fullAnswer = "";
                callbacks.onToken("");
                break;
              case "error":
                callbacks.onError(data.message || data.data || "Error");
                break;
            }
          } catch {
            // Ignore parse errors
          }
        }
      }
    }
  } catch (err: any) {
    if (err?.name === "AbortError") {
      callbacks.onDone(fullAnswer);
    } else {
      throw err;
    }
  }
}

export type UserRole = "clinician" | "student";

export async function requestAccess(
  fullName: string,
  email: string,
  practitionerId: string,
  role: UserRole = "clinician"
): Promise<{ ok: boolean; message: string }> {
  const res = await fetch("/api/auth/request-access", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      full_name: fullName,
      email,
      practitioner_id: practitionerId,
      role,
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail || "Request failed");
  }
  return data;
}

export async function setPasswordWithToken(
  token: string,
  password: string
): Promise<{ ok: boolean; message: string }> {
  const res = await fetch("/api/auth/set-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail || "Set password failed");
  }
  return data;
}

export function getUserDisplayName(user: UserInfo | null): string {
  if (!user) return "";
  if (user.full_name) {
    const parts = user.full_name.trim().split(" ");
    const lastName = parts.length > 1 ? parts[parts.length - 1] : user.full_name;
    const prefix = user.role === "student" ? "" : "Dr. ";
    return `${prefix}${lastName}`;
  }
  return user.email.split("@")[0];
}

export interface HistoryItem {
  id: string;
  question: string;
  domain: string;
  mode: string;
  created_at: string;
  citations_count: number;
  refusal: boolean;
}

export interface HistoryResponse {
  items: HistoryItem[];
  total: number;
}

export async function getQueryHistory(
  token: string,
  limit: number = 20,
  offset: number = 0
): Promise<HistoryResponse> {
  const res = await fetch(`/api/history?limit=${limit}&offset=${offset}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail || "Failed to fetch history");
  }
  return data as HistoryResponse;
}

export async function deleteHistoryItem(token: string, queryId: string): Promise<void> {
  const res = await fetch(`/api/history/${queryId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const data = await res.json();
    throw new Error(data?.detail || "Failed to delete");
  }
}

export interface ConversationItem {
  id: string;
  title: string;
  created_at: string | null;
}

export interface ConversationMessage {
  role: string;
  content: string;
  created_at: string;
}

export async function createConversation(userId: string = "", title: string = ""): Promise<string> {
  const res = await fetch("/api/conversations/new", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, title }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error("Failed to create conversation");
  return data.conversation_id;
}

export async function listConversations(userId: string): Promise<ConversationItem[]> {
  const res = await fetch(`/api/conversations/user/${userId}`);
  const data = await res.json();
  if (!res.ok) return [];
  return data.conversations || [];
}

export async function getConversationMessages(conversationId: string): Promise<ConversationMessage[]> {
  const res = await fetch(`/api/conversations/${conversationId}/messages`);
  const data = await res.json();
  if (!res.ok) return [];
  return data.messages || [];
}

export async function uploadVisual(
  token: string,
  conversationId: string,
  file: File,
  kind: string = "photo"
): Promise<{ ok: boolean; visual_id: string; kind: string }> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("conversation_id", conversationId);
  fd.append("kind", kind);
  const res = await fetch("/api/visual/upload", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || "Upload failed");
  return data;
}

export async function getVisualPreview(
  token: string,
  visualId: string,
  intensity: number = 0.5
): Promise<string> {
  const res = await fetch("/api/visual/preview", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ visual_id: visualId, intensity_0_1: intensity }),
  });
  if (!res.ok) throw new Error("Preview failed");
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export async function askVisualStream(
  token: string,
  question: string,
  conversationId: string,
  callbacks: StreamCallbacks,
  visualId?: string,
  lang?: string
): Promise<void> {
  const body: Record<string, unknown> = {
    q: question,
    conversation_id: conversationId,
    k: 14,
  };
  if (visualId) body.visual_id = visualId;
  if (lang) body.lang = lang;

  const res = await fetch("/api/ask/visual/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.detail || "Visual counseling request failed");
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let fullAnswer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const data = JSON.parse(line.slice(6));
          switch (data.type) {
            case "content":
              if (typeof data.data === "string") {
                callbacks.onToken(data.data);
                fullAnswer += data.data;
              }
              break;
            case "citations": {
              const cits = data.citations || [];
              const rawAci = data.aci_score;
              const normalizedAci = rawAci && typeof rawAci === "object"
                ? rawAci.overall_confidence_0_10
                : rawAci;
              callbacks.onMeta(cits, "", {
                citations: cits,
                requestId: "",
                aciScore: normalizedAci,
              });
              break;
            }
            case "protocol_card":
              if (callbacks.onProtocolCard) callbacks.onProtocolCard(data);
              break;
            case "related":
              callbacks.onRelated(data.data || []);
              break;
            case "done":
              callbacks.onDone(fullAnswer);
              break;
            case "replace":
              fullAnswer = "";
              callbacks.onToken("");
              break;
            case "error":
              callbacks.onError(data.message || data.data || "Error");
              break;
          }
        } catch {
          // ignore
        }
      }
    }
  }
}

export async function deleteConversation(conversationId: string, userId: string = ""): Promise<boolean> {
  const res = await fetch(`/api/conversations/${conversationId}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });
  const data = await res.json();
  return data.ok === true;
}
