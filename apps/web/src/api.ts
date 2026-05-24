const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
let supabaseUrl = import.meta.env.VITE_SUPABASE_URL ?? "";
let supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY ?? "";
let supabaseConfigPromise: Promise<SupabaseAuthConfig> | null = null;

export type ProcedureGroup = "administrative" | "interlinked";
export type UserType = "individual" | "business";

export interface ProcedureListItem {
  id: string;
  source_id: string;
  procedure_code: string;
  procedure_group: ProcedureGroup;
  name: string;
  target_audience?: string | null;
  field_name?: string | null;
  published_agency?: string | null;
  implementation_agency?: string | null;
  implementation_level?: string | null;
  processing_time?: string | null;
  fees?: string | null;
  source_url: string;
  updated_at?: string | null;
}

export interface ProcedureRecord extends ProcedureListItem {
  execution_methods: Array<Record<string, unknown>>;
  execution_steps?: string | null;
  required_documents?: string | null;
  requirements?: string | null;
  legal_basis?: string | null;
  attachments: Array<Record<string, unknown>>;
  related_procedures: Array<Record<string, unknown>>;
  last_seen_at?: string | null;
  source_updated_at?: string | null;
}

export interface ProcedureListResponse {
  items: ProcedureListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface FilterOptions {
  fields: string[];
  agencies: string[];
  levels: string[];
}

export interface StatsBucket {
  name: string;
  count: number;
}

export interface StatsOverview {
  total: number;
  administrative: number;
  interlinked: number;
  individual: number;
  business: number;
  both_or_unknown: number;
  by_field: StatsBucket[];
  by_agency: StatsBucket[];
  recently_updated: ProcedureListItem[];
}

export interface VectorSearchResult {
  procedure_id: string;
  procedure_code: string;
  procedure_group: ProcedureGroup;
  name: string;
  field_name?: string | null;
  target_audience?: string | null;
  source_url: string;
  similarity: number;
}

export interface ChatProcedureContext {
  procedure_id: string;
  procedure_code: string;
  procedure_group: ProcedureGroup;
  name: string;
  source_url: string;
  field_name?: string | null;
  target_audience?: string | null;
  summary: string;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  procedures: ChatProcedureContext[];
  inference_seconds?: number | null;
  expires_at?: string | null;
}

export interface AuthSession {
  access_token: string;
  refresh_token?: string;
  user: {
    id: string;
    email?: string;
  };
}

interface SupabaseAuthConfig {
  supabase_url: string;
  supabase_anon_key: string;
}

export interface ChatSessionListItem {
  id: string;
  user_type?: UserType | null;
  initial_question?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  expires_at?: string | null;
}

export interface ChatMessageRecord {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  metadata: Record<string, unknown>;
  created_at?: string | null;
}

export interface ChatSessionDetail extends ChatSessionListItem {
  procedure_context: ChatProcedureContext[];
  messages: ChatMessageRecord[];
}

export interface ListProcedureParams {
  page?: number;
  pageSize?: number;
  q?: string;
  group?: ProcedureGroup | "all";
  field?: string;
  agency?: string;
  audience?: UserType | "all";
}

export async function listProcedures(params: ListProcedureParams): Promise<ProcedureListResponse> {
  const url = new URL("/api/procedures", API_BASE_URL);
  url.searchParams.set("page", String(params.page ?? 1));
  url.searchParams.set("page_size", String(params.pageSize ?? 20));
  appendParam(url, "q", params.q);
  appendParam(url, "group", params.group === "all" ? "" : params.group);
  appendParam(url, "field", params.field);
  appendParam(url, "agency", params.agency);
  appendParam(url, "audience", params.audience === "all" ? "" : params.audience);
  return request(url);
}

export async function getProcedure(id: string): Promise<ProcedureRecord> {
  return request(new URL(`/api/procedures/${id}`, API_BASE_URL));
}

export async function getFilters(): Promise<FilterOptions> {
  return request(new URL("/api/filters", API_BASE_URL));
}

export async function getStatsOverview(): Promise<StatsOverview> {
  return request(new URL("/api/stats/overview", API_BASE_URL));
}

export async function vectorSearch(query: string, audience: UserType | "all", limit = 9): Promise<VectorSearchResult[]> {
  const response = await request<{ items: VectorSearchResult[] }>(new URL("/api/search/vector", API_BASE_URL), {
    method: "POST",
    body: JSON.stringify({
      query,
      target_audience: audience === "all" ? null : audience === "individual" ? "cá nhân" : "doanh nghiệp",
      limit,
    }),
  });
  return response.items;
}

export async function signInWithGoogle() {
  const config = await getSupabaseAuthConfig();
  const url = new URL("/auth/v1/authorize", config.supabase_url);
  url.searchParams.set("provider", "google");
  url.searchParams.set("redirect_to", window.location.origin + window.location.pathname);
  window.location.href = url.toString();
}

export async function consumeSupabaseAuthRedirect(): Promise<AuthSession | null> {
  if (!window.location.hash) {
    return null;
  }

  const params = new URLSearchParams(window.location.hash.slice(1));
  const error = params.get("error_description") || params.get("error");
  if (error) {
    clearUrlHash();
    throw new Error(error);
  }

  const accessToken = params.get("access_token");
  if (!accessToken) {
    return null;
  }

  const refreshToken = params.get("refresh_token") ?? undefined;
  const user = await getSupabaseUser(accessToken);
  clearUrlHash();
  return {
    access_token: accessToken,
    refresh_token: refreshToken,
    user,
  };
}

async function getSupabaseUser(accessToken: string): Promise<AuthSession["user"]> {
  const config = await getSupabaseAuthConfig();
  const url = new URL("/auth/v1/user", config.supabase_url);
  const response = await fetch(url, {
    headers: {
      apikey: config.supabase_anon_key,
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const payload = await response.json();
  return {
    id: payload.id,
    email: payload.email,
  };
}

async function getSupabaseAuthConfig(): Promise<SupabaseAuthConfig> {
  if (supabaseUrl && supabaseAnonKey) {
    return {
      supabase_url: supabaseUrl,
      supabase_anon_key: supabaseAnonKey,
    };
  }

  if (!supabaseConfigPromise) {
    supabaseConfigPromise = request<SupabaseAuthConfig>(new URL("/api/auth/supabase-config", API_BASE_URL)).then((config) => {
      supabaseUrl = config.supabase_url;
      supabaseAnonKey = config.supabase_anon_key;
      return config;
    });
  }
  return supabaseConfigPromise;
}

function clearUrlHash() {
  window.history.replaceState(null, document.title, window.location.pathname + window.location.search);
}

export async function startChat(userType: UserType, question: string, token?: string): Promise<ChatResponse> {
  return request(new URL("/api/chat/sessions", API_BASE_URL), {
    method: "POST",
    body: JSON.stringify({ user_type: userType, question }),
    token,
  });
}

export async function listChatSessions(limit = 30, token?: string): Promise<ChatSessionListItem[]> {
  const url = new URL("/api/chat/sessions", API_BASE_URL);
  url.searchParams.set("limit", String(limit));
  return request(url, { token });
}

export async function getChatSession(sessionId: string, token?: string): Promise<ChatSessionDetail> {
  return request(new URL(`/api/chat/sessions/${sessionId}`, API_BASE_URL), { token });
}

export async function sendChatMessage(sessionId: string, message: string, token?: string): Promise<ChatResponse> {
  return request(new URL(`/api/chat/sessions/${sessionId}/messages`, API_BASE_URL), {
    method: "POST",
    body: JSON.stringify({ message }),
    token,
  });
}

export async function sendLocalChatMessage(
  userType: UserType,
  initialQuestion: string,
  message: string,
  procedureContext: ChatProcedureContext[],
): Promise<ChatResponse> {
  return request(new URL("/api/chat/local/messages", API_BASE_URL), {
    method: "POST",
    body: JSON.stringify({
      user_type: userType,
      initial_question: initialQuestion,
      message,
      procedure_context: procedureContext,
    }),
  });
}

export async function summarizeContextProcedure(
  procedureId: string,
  userType: UserType,
  question: string,
): Promise<ChatProcedureContext> {
  return request(new URL("/api/chat/context/summarize", API_BASE_URL), {
    method: "POST",
    body: JSON.stringify({
      procedure_id: procedureId,
      user_type: userType,
      question,
    }),
  });
}

export async function updateSavedChatContext(
  sessionId: string,
  procedureContext: ChatProcedureContext[],
  token?: string,
): Promise<ChatProcedureContext[]> {
  return request(new URL(`/api/chat/sessions/${sessionId}/context`, API_BASE_URL), {
    method: "PATCH",
    body: JSON.stringify({ procedure_context: procedureContext }),
    token,
  });
}

function appendParam(url: URL, key: string, value?: string | null) {
  if (value && value.trim()) {
    url.searchParams.set(key, value.trim());
  }
}

async function request<T>(url: URL, init?: RequestInit & { token?: string }): Promise<T> {
  const { token, ...fetchInit } = init ?? {};
  const response = await fetch(url, {
    ...fetchInit,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(fetchInit.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}
