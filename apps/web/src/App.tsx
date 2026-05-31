import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  Bot,
  Building2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  ExternalLink,
  FileSearch,
  Filter,
  Landmark,
  Loader2,
  Plus,
  Search,
  Send,
} from "lucide-react";
import {
  AuthSession,
  ChatProcedureContext,
  ChatSourceChunk,
  ChatSessionListItem,
  FilterOptions,
  ProcedureGroup,
  ProcedureListItem,
  ProcedureListResponse,
  ProcedureRecord,
  StatsOverview,
  UserType,
  getFilters,
  getProcedure,
  getStatsOverview,
  getChatSession,
  consumeSupabaseAuthRedirect,
  listChatSessions,
  listProcedures,
  sendChatMessage,
  sendLocalChatMessage,
  signInWithGoogle,
  startChat,
  summarizeContextProcedure,
  updateSavedChatContext,
  vectorSearch,
} from "./api";

type Tab = "search" | "dashboard" | "chat";
type GroupFilter = ProcedureGroup | "all";

const groupLabels: Record<ProcedureGroup, string> = {
  administrative: "Thường",
  interlinked: "Liên thông",
};

const CHAT_STATE_KEY = "hcm_govbot_chat_state";
const RETURN_TAB_KEY = "hcm_govbot_return_tab";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  inferenceSeconds?: number | null;
  sources?: ChatSourceChunk[];
};

type StoredChatState = {
  userType: UserType;
  question: string;
  sessionId: string;
  messages: ChatMessage[];
  procedures: ChatProcedureContext[];
  sources: ChatSourceChunk[];
  expiresAt: string | null;
};

export function App() {
  const [tab, setTab] = useState<Tab>(() => (sessionStorage.getItem(RETURN_TAB_KEY) === "chat" ? "chat" : "search"));
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState<GroupFilter>("all");
  const [field, setField] = useState("");
  const [agency, setAgency] = useState("");
  const [page, setPage] = useState(1);
  const [list, setList] = useState<ProcedureListResponse | null>(null);
  const [filters, setFilters] = useState<FilterOptions>({ fields: [], agencies: [], levels: [] });
  const [selected, setSelected] = useState<ProcedureRecord | null>(null);
  const [stats, setStats] = useState<StatsOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const totalPages = useMemo(() => Math.max(1, Math.ceil((list?.total ?? 0) / (list?.page_size ?? 20))), [list]);

  useEffect(() => {
    getFilters().then(setFilters).catch(() => undefined);
    getStatsOverview().then(setStats).catch(() => undefined);
    sessionStorage.removeItem(RETURN_TAB_KEY);
  }, []);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError("");
    listProcedures({ page, pageSize: 20, q: query, group, field, agency })
      .then((data) => {
        if (!mounted) return;
        setList(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Không tải được danh sách thủ tục.");
        setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [agency, field, group, page, query]);

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    setPage(1);
  };

  const openDetail = async (item: ProcedureListItem | { procedure_id: string }) => {
    setDetailLoading(true);
    setError("");
    try {
      const detail = await getProcedure("id" in item ? item.id : item.procedure_id);
      setSelected(detail);
      setTab("search");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được chi tiết thủ tục.");
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <main className={`${tab === "chat" ? "flex h-screen flex-col overflow-hidden" : "min-h-screen"} bg-civic-paper text-civic-ink`}>
      <header className="shrink-0 border-b border-civic-line bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-semibold text-civic-red">Thành phố Hồ Chí Minh</p>
            <h1 className="text-2xl font-semibold">Tra cứu thủ tục hành chính công</h1>
          </div>
          <nav className="grid grid-cols-3 gap-2 md:flex">
            <NavButton icon={<FileSearch size={18} />} label="Tra cứu" active={tab === "search"} onClick={() => setTab("search")} />
            <NavButton icon={<BarChart3 size={18} />} label="Thống kê" active={tab === "dashboard"} onClick={() => setTab("dashboard")} />
            <NavButton icon={<Bot size={18} />} label="Hỏi AI" active={tab === "chat"} onClick={() => setTab("chat")} />
          </nav>
        </div>
      </header>

      <section className={`mx-auto w-full max-w-7xl px-4 py-6 ${tab === "chat" ? "min-h-0 flex-1 overflow-hidden" : ""}`}>
        {error && <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
        <div className={tab === "search" ? "block" : "hidden"}>
          <SearchView
            query={query}
            setQuery={setQuery}
            group={group}
            setGroup={setGroup}
            field={field}
            setField={setField}
            agency={agency}
            setAgency={setAgency}
            filters={filters}
            list={list}
            loading={loading}
            detailLoading={detailLoading}
            selected={selected}
            setSelected={setSelected}
            submitSearch={submitSearch}
            openDetail={openDetail}
            page={page}
            totalPages={totalPages}
            setPage={setPage}
          />
        </div>
        <div className={tab === "dashboard" ? "block" : "hidden"}>
          <DashboardView stats={stats} openDetail={openDetail} />
        </div>
        <div className={tab === "chat" ? "block h-full min-h-0" : "hidden"}>
          <ChatView />
        </div>
      </section>
    </main>
  );
}

function SearchView(props: {
  query: string;
  setQuery: (value: string) => void;
  group: GroupFilter;
  setGroup: (value: GroupFilter) => void;
  field: string;
  setField: (value: string) => void;
  agency: string;
  setAgency: (value: string) => void;
  filters: FilterOptions;
  list: ProcedureListResponse | null;
  loading: boolean;
  detailLoading: boolean;
  selected: ProcedureRecord | null;
  setSelected: (value: ProcedureRecord | null) => void;
  submitSearch: (event: FormEvent) => void;
  openDetail: (item: ProcedureListItem) => void;
  page: number;
  totalPages: number;
  setPage: (value: number) => void;
}) {
  return (
    <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
      <aside className="space-y-4">
        <form className="rounded-lg border border-civic-line bg-white p-4 shadow-soft" onSubmit={props.submitSearch}>
          <label className="text-sm font-semibold">Tìm kiếm</label>
          <div className="relative mt-2">
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-civic-muted" size={18} />
            <input
              className="h-11 w-full rounded-md border border-civic-line pl-10 pr-3 outline-none focus:border-civic-teal focus:ring-2 focus:ring-civic-teal/20"
              value={props.query}
              onChange={(event) => props.setQuery(event.target.value)}
              placeholder="Tên hoặc mã thủ tục"
            />
          </div>
          <button className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-civic-ink text-sm font-semibold text-white">
            <Search size={17} />
            Tìm kiếm
          </button>
        </form>

        <section className="rounded-lg border border-civic-line bg-white p-4 shadow-soft">
          <div className="mb-3 flex items-center gap-2 font-semibold">
            <Filter size={18} />
            Bộ lọc
          </div>
          <Select label="Loại thủ tục" value={props.group} onChange={(value) => props.setGroup(value as GroupFilter)}>
            <option value="all">Tất cả</option>
            <option value="administrative">Thủ tục thường</option>
            <option value="interlinked">Liên thông</option>
          </Select>
          <Select label="Lĩnh vực" value={props.field} onChange={props.setField}>
            <option value="">Tất cả lĩnh vực</option>
            {props.filters.fields.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </Select>
          <Select label="Cơ quan" value={props.agency} onChange={props.setAgency}>
            <option value="">Tất cả cơ quan</option>
            {props.filters.agencies.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </Select>
        </section>
      </aside>

      <div className="space-y-4">
        {props.selected ? (
          <ProcedureDetail detail={props.selected} onBack={() => props.setSelected(null)} />
        ) : (
          <section className="rounded-lg border border-civic-line bg-white shadow-soft">
            <div className="flex flex-col gap-2 border-b border-civic-line p-4 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="text-lg font-semibold">Danh sách thủ tục</h2>
                <p className="text-sm text-civic-muted">{props.list ? `${props.list.total.toLocaleString("vi-VN")} kết quả` : "Đang tải dữ liệu"}</p>
              </div>
              {props.loading && <Loader2 className="animate-spin text-civic-muted" size={20} />}
            </div>
            <div className="divide-y divide-civic-line">
              {props.list?.items.map((item) => (
                <ProcedureRow key={item.id} item={item} onOpen={() => props.openDetail(item)} />
              ))}
              {props.list?.items.length === 0 && <div className="p-6 text-civic-muted">Không tìm thấy thủ tục phù hợp.</div>}
            </div>
            <div className="flex items-center justify-between border-t border-civic-line p-4">
              <button
                className="inline-flex h-9 items-center gap-1 rounded-md border border-civic-line px-3 text-sm disabled:opacity-40"
                disabled={props.page <= 1}
                onClick={() => props.setPage(props.page - 1)}
              >
                <ChevronLeft size={16} />
                Trước
              </button>
              <span className="text-sm text-civic-muted">
                Trang {props.page}/{props.totalPages}
              </span>
              <button
                className="inline-flex h-9 items-center gap-1 rounded-md border border-civic-line px-3 text-sm disabled:opacity-40"
                disabled={props.page >= props.totalPages}
                onClick={() => props.setPage(props.page + 1)}
              >
                Sau
                <ChevronRight size={16} />
              </button>
            </div>
          </section>
        )}
        {props.detailLoading && <div className="text-sm text-civic-muted">Đang tải chi tiết...</div>}
      </div>
    </div>
  );
}

function ProcedureRow({ item, onOpen }: { item: ProcedureListItem; onOpen: () => void }) {
  return (
    <button className="block w-full p-4 text-left transition hover:bg-slate-50" onClick={onOpen}>
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="text-sm font-semibold text-civic-red">{item.procedure_code}</div>
          <div className="mt-1 font-semibold">{item.name}</div>
        </div>
        <span className="w-fit rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-civic-muted">{groupLabels[item.procedure_group]}</span>
      </div>
      <div className="mt-3 grid gap-2 text-sm text-civic-muted md:grid-cols-3">
        <Meta icon={<Landmark size={15} />} text={item.field_name || "Chưa rõ lĩnh vực"} />
        <Meta icon={<Building2 size={15} />} text={item.implementation_agency || "Chưa rõ cơ quan"} />
        <Meta icon={<Clock3 size={15} />} text={item.processing_time || "Chưa rõ thời hạn"} />
      </div>
    </button>
  );
}

function ProcedureDetail({ detail, onBack }: { detail: ProcedureRecord; onBack: () => void }) {
  return (
    <section className="rounded-lg border border-civic-line bg-white shadow-soft">
      <div className="border-b border-civic-line p-4">
        <button className="mb-3 inline-flex h-9 items-center gap-1 rounded-md border border-civic-line px-3 text-sm" onClick={onBack}>
          <ChevronLeft size={16} />
          Danh sách
        </button>
        <div className="text-sm font-semibold text-civic-red">{detail.procedure_code}</div>
        <h2 className="mt-1 text-2xl font-semibold leading-tight">{detail.name}</h2>
        <a className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-civic-teal" href={detail.source_url} target="_blank" rel="noreferrer">
          Link nguồn
          <ExternalLink size={15} />
        </a>
      </div>
      <div className="grid gap-4 p-4 md:grid-cols-2">
        <Info label="Cơ quan thực hiện" value={detail.implementation_agency} />
        <Info label="Đối tượng" value={detail.target_audience} />
        <Info label="Thời hạn" value={detail.processing_time} />
        <Info label="Phí/lệ phí" value={detail.fees} />
      </div>
      <div className="space-y-5 border-t border-civic-line p-4">
        <LongText title="Hồ sơ cần chuẩn bị" value={detail.required_documents} />
        <LongText title="Trình tự thực hiện" value={detail.execution_steps} />
        <LongText title="Yêu cầu, điều kiện" value={detail.requirements} />
        <LongText title="Căn cứ pháp lý" value={detail.legal_basis} />
      </div>
    </section>
  );
}

function DashboardView({ stats, openDetail }: { stats: StatsOverview | null; openDetail: (item: ProcedureListItem) => void }) {
  if (!stats) {
    return <LoadingBlock label="Đang tải dashboard..." />;
  }
  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-3">
        <Metric label="Tổng thủ tục" value={stats.total} />
        <Metric label="Thường" value={stats.administrative} />
        <Metric label="Liên thông" value={stats.interlinked} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <BucketPanel title="Theo lĩnh vực" items={stats.by_field} />
        <BucketPanel title="Theo cơ quan" items={stats.by_agency} />
      </div>
      <section className="rounded-lg border border-civic-line bg-white shadow-soft">
        <h2 className="border-b border-civic-line p-4 text-lg font-semibold">Mới cập nhật gần đây</h2>
        <div className="divide-y divide-civic-line">
          {stats.recently_updated.map((item) => (
            <ProcedureRow key={item.id} item={item} onOpen={() => openDetail(item)} />
          ))}
        </div>
      </section>
    </div>
  );
}

function ChatView() {
  const [userType, setUserType] = useState<UserType>("individual");
  const [question, setQuestion] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [procedures, setProcedures] = useState<ChatProcedureContext[]>([]);
  const [sources, setSources] = useState<ChatSourceChunk[]>([]);
  const [sessions, setSessions] = useState<ChatSessionListItem[]>([]);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [authSession, setAuthSession] = useState<AuthSession | null>(() => {
    const raw = localStorage.getItem("hcm_govbot_auth");
    return raw ? (JSON.parse(raw) as AuthSession) : null;
  });
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [chatError, setChatError] = useState("");
  const [contextQuery, setContextQuery] = useState("");
  const [contextSearchResults, setContextSearchResults] = useState<Array<{ procedure_id: string; procedure_code: string; name: string; field_name?: string | null; similarity: number }>>([]);
  const [contextBusyId, setContextBusyId] = useState("");
  const latestMessageRef = useRef<HTMLDivElement | null>(null);
  const inputBarRef = useRef<HTMLFormElement | null>(null);

  useEffect(() => {
    const raw = sessionStorage.getItem(CHAT_STATE_KEY);
    if (!raw) return;

    try {
      const state = JSON.parse(raw) as StoredChatState;
      setUserType(state.userType === "business" ? "business" : "individual");
      setQuestion(state.question || "");
      setSessionId(state.sessionId || "");
      setMessages(Array.isArray(state.messages) ? state.messages : []);
      setProcedures(Array.isArray(state.procedures) ? state.procedures : []);
      setSources(Array.isArray(state.sources) ? state.sources : []);
      setExpiresAt(state.expiresAt ?? null);
    } catch {
      // Ignore invalid stored state.
    } finally {
      sessionStorage.removeItem(CHAT_STATE_KEY);
    }
  }, []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      inputBarRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    latestMessageRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [messages.length, loading, searching]);

  useEffect(() => {
    if (!loading && !contextBusyId) {
      setElapsedSeconds(0);
      return;
    }
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 250);
    return () => window.clearInterval(timer);
  }, [loading, contextBusyId]);

  const syncSavedContext = async (nextContext: ChatProcedureContext[], nextSources: ChatSourceChunk[] = sources) => {
    if (!authSession?.access_token || !sessionId || sessionId.startsWith("local:")) {
      return;
    }
    await updateSavedChatContext(sessionId, nextContext, nextSources, authSession.access_token);
  };

  const refreshSessions = useCallback(async () => {
    if (!authSession?.access_token) {
      setSessions([]);
      return;
    }
    try {
      setSessions(await listChatSessions(30, authSession.access_token));
    } catch {
      setSessions([]);
    }
  }, [authSession?.access_token]);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    consumeSupabaseAuthRedirect()
      .then((session) => {
        if (!session) return;
        setAuthSession(session);
        localStorage.setItem("hcm_govbot_auth", JSON.stringify(session));
      })
      .catch((err: unknown) => {
        setChatError(err instanceof Error ? err.message : "Không đăng nhập được bằng Google.");
      });
  }, []);

  const loginWithGoogle = async () => {
    setChatError("");
    try {
      sessionStorage.setItem(RETURN_TAB_KEY, "chat");
      sessionStorage.setItem(
        CHAT_STATE_KEY,
        JSON.stringify({
          userType,
          question,
          sessionId,
          messages,
          procedures,
          sources,
          expiresAt,
        } satisfies StoredChatState),
      );
      await signInWithGoogle();
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "Không đăng nhập được.");
    }
  };

  const logout = () => {
    localStorage.removeItem("hcm_govbot_auth");
    setAuthSession(null);
    setSessions([]);
    newSession();
  };

  const openSession = async (id: string) => {
    setChatError("");
    setLoading(true);
    try {
      const session = await getChatSession(id, authSession?.access_token);
      setSessionId(session.id);
      setUserType(session.user_type === "business" ? "business" : "individual");
      setExpiresAt(session.expires_at ?? null);
      setProcedures(session.procedure_context ?? []);
      setSources(session.source_context ?? []);
      setMessages(
        session.messages
          .filter((message) => message.role === "user" || message.role === "assistant")
          .map((message) => ({
            role: message.role as "user" | "assistant",
            content: message.content,
            inferenceSeconds: typeof message.metadata?.inference_seconds === "number" ? message.metadata.inference_seconds : null,
            sources: Array.isArray(message.metadata?.sources) ? (message.metadata.sources as ChatSourceChunk[]) : [],
          })),
      );
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "Không tải được phiên chat.");
    } finally {
      setLoading(false);
    }
  };

  const newSession = () => {
    setSessionId("");
    setMessages([]);
    setProcedures([]);
    setSources([]);
    setExpiresAt(null);
    setChatError("");
    setQuestion("");
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (question.trim().length < 3) return;
    const text = question.trim();
    setQuestion("");
    setChatError("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);
    try {
      const isSavedSession = authSession?.access_token && sessionId && !sessionId.startsWith("local:");
      const response = isSavedSession
          ? await sendChatMessage(sessionId, text, authSession.access_token)
        : sessionId.startsWith("local:")
          ? await sendLocalChatMessage(
              userType,
              messages[0]?.content || text,
              text,
              procedures,
              sources,
              messages.map((message) => ({ role: message.role, content: message.content })),
            )
          : await startChat(userType, text, authSession?.access_token);
      setSessionId(response.session_id);
      setExpiresAt(response.expires_at ?? null);
      setProcedures(response.procedures);
      setSources(response.sources ?? []);
      setMessages((prev) => [...prev, { role: "assistant", content: response.answer, inferenceSeconds: response.inference_seconds, sources: response.sources ?? [] }]);
      if (authSession?.access_token) {
        refreshSessions();
      }
    } catch (err) {
      const message = normalizeErrorMessage(err, "Không gọi được AI.");
      setChatError(message);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Mình chưa xử lý được câu hỏi này. Vui lòng kiểm tra backend, Gemini API key/model hoặc thử lại với mô tả cụ thể hơn.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const searchContextProcedures = async () => {
    if (!contextQuery.trim()) return;
    setSearching(true);
    setChatError("");
    try {
      const results = await vectorSearch(contextQuery, "all", 6);
      setContextSearchResults(
        results.map((item) => ({
          procedure_id: item.procedure_id,
          procedure_code: item.procedure_code,
          name: item.name,
          field_name: item.field_name,
          similarity: item.similarity,
        })),
      );
    } catch (err) {
      setChatError(normalizeErrorMessage(err, "Không tìm được thủ tục để thêm."));
    } finally {
      setSearching(false);
    }
  };

  const removeProcedureFromContext = async (procedureId: string) => {
    const nextContext = procedures.filter((item) => item.procedure_id !== procedureId);
    const nextSources = sources.filter((item) => item.procedure_id !== procedureId);
    setSources(nextSources);
    setProcedures(nextContext);
    await syncSavedContext(nextContext, nextSources);
  };

  const addProcedureToContext = async (procedureId: string) => {
    if (procedures.some((item) => item.procedure_id === procedureId)) {
      setChatError("Thủ tục này đã có trong context.");
      return;
    }
    setContextBusyId(procedureId);
    setChatError("");
    try {
      const contextItem = await summarizeContextProcedure(procedureId, userType, messages[0]?.content || contextQuery || "Người dùng thêm thủ tục vào context");
      const nextContext = [...procedures, contextItem];
      setProcedures(nextContext);
      await syncSavedContext(nextContext);
      setContextSearchResults((prev) => prev.filter((item) => item.procedure_id !== procedureId));
    } catch (err) {
      setChatError(normalizeErrorMessage(err, "Không thêm được thủ tục vào context."));
    } finally {
      setContextBusyId("");
    }
  };

  return (
    <div className="grid h-full min-h-0 gap-5 lg:grid-cols-[260px_minmax(0,1fr)_300px]">
      <aside className="flex min-h-0 flex-col rounded-lg border border-civic-line bg-white shadow-soft">
        <div className="border-b border-civic-line p-3">
          <h3 className="font-semibold">Chat trước đó</h3>
        </div>
        <div className="border-b border-civic-line p-3">
          {authSession ? (
            <div className="space-y-2">
              <div className="truncate text-sm font-semibold">{authSession.user.email || "Đã đăng nhập"}</div>
              <button className="h-8 rounded-md border border-civic-line px-3 text-xs font-semibold" onClick={logout}>
                Đăng xuất
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="text-xs text-civic-muted">Đăng nhập nếu muốn lưu lịch sử chat.</div>
              <button className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-civic-ink text-sm font-semibold text-white" onClick={loginWithGoogle}>
                <GoogleIcon />
                Tiếp tục với Google
              </button>
            </div>
          )}
          <button
            className="mt-3 inline-flex h-10 w-full items-center justify-center gap-2 rounded-md border border-civic-line bg-white text-sm font-semibold text-civic-ink hover:bg-slate-50 disabled:opacity-50"
            onClick={newSession}
            disabled={loading || searching}
          >
            <Plus size={16} />
            Đoạn hội thoại mới
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          {sessions.map((item) => (
            <button
              key={item.id}
              className={`block w-full border-b border-civic-line p-3 text-left text-sm hover:bg-slate-50 ${sessionId === item.id ? "bg-slate-50" : ""}`}
              onClick={() => openSession(item.id)}
            >
              <div className="line-clamp-2 font-semibold">{item.initial_question || "Phiên chat chưa có câu hỏi"}</div>
            </button>
          ))}
          {sessions.length === 0 && <div className="p-3 text-sm text-civic-muted">{authSession ? "Chưa có lịch sử chat." : "Chat không đăng nhập sẽ không được lưu."}</div>}
        </div>
      </aside>

      <section className="flex min-h-0 flex-col rounded-lg border border-civic-line bg-white shadow-soft">
        <div className="border-b border-civic-line p-4">
          <h2 className="text-lg font-semibold">Hỏi AI về thủ tục hành chính</h2>
          {!authSession && <div className="mt-1 text-xs text-civic-muted">Chat không đăng nhập sẽ không lưu lịch sử.</div>}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="space-y-3">
            {messages.length === 0 && <div className="rounded-md bg-slate-50 p-4 text-sm text-civic-muted">Hãy mô tả chi tiết nhu cầu để chúng tôi có thể trả lời bạn tốt hơn.</div>}
            {messages.map((message, index) => (
              <div
                key={index}
                ref={index === messages.length - 1 ? latestMessageRef : undefined}
                className={`max-w-[92%] rounded-lg p-3 text-sm leading-6 ${message.role === "user" ? "ml-auto bg-civic-ink text-white" : "bg-slate-50 text-civic-ink"}`}
              >
                {message.role === "assistant" ? <FormattedAnswer content={message.content} /> : message.content}
                {message.role === "assistant" && typeof message.inferenceSeconds === "number" && (
                  <div className="mt-2 text-xs text-civic-muted">Thời gian suy luận: {formatSeconds(message.inferenceSeconds)}</div>
                )}
                {message.role === "assistant" && message.sources && message.sources.length > 0 && <SourceList sources={message.sources} />}
              </div>
            ))}
            {chatError && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{chatError}</div>}
            {loading && <LoadingBlock label={`AI đang đọc thủ tục liên quan, có thể mất khoảng 15s... ${elapsedSeconds}s`} />}
            {searching && <LoadingBlock label="Đang tìm bằng hybrid retrieval..." />}
          </div>
        </div>
        <form ref={inputBarRef} className="shrink-0 flex gap-2 border-t border-civic-line p-4" onSubmit={submit}>
          <input
            className="h-11 flex-1 rounded-md border border-civic-line px-3 outline-none focus:border-civic-teal focus:ring-2 focus:ring-civic-teal/20"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ví dụ: tôi muốn xin giấy phép kinh doanh karaoke"
          />
          <button className="inline-flex h-11 items-center gap-2 rounded-md bg-civic-ink px-4 text-sm font-semibold text-white disabled:opacity-50" disabled={loading || searching || question.trim().length < 3}>
            <Send size={17} />
            Gửi
          </button>
        </form>
      </section>

      <aside className="flex min-h-0 flex-col rounded-lg border border-civic-line bg-white shadow-soft">
        <div className="border-b border-civic-line p-3">
          <h3 className="text-sm font-semibold">Thủ tục dùng để trả lời</h3>
          <div className="mt-1 text-xs text-civic-muted">{sources.length} chunk nguồn.</div>
        </div>
        <div className="border-b border-civic-line p-3">
          <div className="flex gap-2">
            <input
              className="h-9 min-w-0 flex-1 rounded-md border border-civic-line px-2 text-sm outline-none focus:border-civic-teal"
              value={contextQuery}
              onChange={(event) => setContextQuery(event.target.value)}
              placeholder="Tìm thủ tục để thêm"
            />
            <button className="h-9 rounded-md border border-civic-line px-2 text-xs font-semibold disabled:opacity-50" onClick={searchContextProcedures} disabled={searching}>
              Tìm
            </button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          {sources.length > 0 && (
            <div>
              <div className="p-3 text-xs font-semibold text-civic-muted">Chunk nguồn gần nhất</div>
              <div className="divide-y divide-civic-line">
                {sources.map((source) => (
                  <div key={source.chunk_id} className="p-3">
                    <div className="text-xs font-semibold text-civic-teal">[{source.citation}] {source.section_name}</div>
                    <div className="mt-1 line-clamp-2 text-sm font-semibold">{source.name}</div>
                    <div className="mt-1 line-clamp-3 text-xs text-civic-muted">{source.text}</div>
                    <div className="mt-2 flex items-center gap-2">
                      <a className="inline-flex text-xs font-semibold text-civic-teal underline" href={source.source_url} target="_blank" rel="noreferrer">
                        Nguồn
                      </a>
                      <button className="rounded-md border border-red-200 px-2 py-1 text-xs font-semibold text-red-700" onClick={() => removeProcedureFromContext(source.procedure_id)}>
                        Xóa thủ tục này
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {sources.length === 0 && <div className="p-3 text-sm text-civic-muted">Chưa có chunk nguồn nào.</div>}
          {contextSearchResults.length > 0 && (
            <div className="border-t border-civic-line">
              <div className="p-3 text-xs font-semibold text-civic-muted">Kết quả tìm thêm</div>
              <div className="divide-y divide-civic-line">
                {contextSearchResults.map((item) => {
                  const exists = procedures.some((procedure) => procedure.procedure_id === item.procedure_id);
                  const busy = contextBusyId === item.procedure_id;
                  return (
                    <div key={item.procedure_id} className="p-3">
                      <div className="text-xs font-semibold text-civic-red">{item.procedure_code}</div>
                      <div className="mt-1 line-clamp-3 text-sm font-semibold">{item.name}</div>
                      <div className="mt-1 text-xs text-civic-muted">
                        {item.field_name || "Chưa rõ lĩnh vực"} · {(item.similarity * 100).toFixed(1)}%
                      </div>
                      <button
                        className="mt-2 rounded-md bg-civic-ink px-2 py-1 text-xs font-semibold text-white disabled:opacity-50"
                        onClick={() => addProcedureToContext(item.procedure_id)}
                        disabled={exists || Boolean(contextBusyId)}
                      >
                        {busy ? `Đang đọc... ${elapsedSeconds}s` : exists ? "Đã có" : "Thêm"}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function NavButton({ icon, label, active, onClick }: { icon: ReactNode; label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className={`inline-flex h-10 items-center justify-center gap-2 rounded-md px-3 text-sm font-semibold ${active ? "bg-civic-ink text-white" : "text-civic-muted hover:bg-slate-100"}`}>
      {icon}
      {label}
    </button>
  );
}

function GoogleIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4">
      <path fill="#4285F4" d="M22.6 12.2c0-.8-.1-1.5-.2-2.2H12v4.2h6c-.3 1.4-1 2.5-2.1 3.3v2.7h3.4c2-1.8 3.3-4.5 3.3-8z" />
      <path fill="#34A853" d="M12 23c3 0 5.5-1 7.3-2.7l-3.4-2.7c-1 .6-2.2 1-3.9 1-3 0-5.5-2-6.4-4.7H2.1v2.8C3.9 20.4 7.6 23 12 23z" />
      <path fill="#FBBC05" d="M5.6 13.9c-.2-.6-.4-1.3-.4-1.9s.1-1.3.4-1.9V7.3H2.1C1.4 8.7 1 10.3 1 12s.4 3.3 1.1 4.7l3.5-2.8z" />
      <path fill="#EA4335" d="M12 5.4c1.6 0 3.1.6 4.2 1.7l3.1-3.1C17.5 2.1 15 1 12 1 7.6 1 3.9 3.6 2.1 7.3l3.5 2.8C6.5 7.4 9 5.4 12 5.4z" />
    </svg>
  );
}

function SourceList({ sources }: { sources: ChatSourceChunk[] }) {
  return (
    <div className="mt-3 rounded-md border border-civic-line bg-white/80 p-2 text-xs text-civic-ink">
      <div className="mb-2 font-semibold">Nguồn đã dùng</div>
      <div className="space-y-2">
        {sources.map((source) => (
          <a key={source.chunk_id} className="block rounded border border-civic-line p-2 hover:bg-slate-50" href={source.source_url} target="_blank" rel="noreferrer">
            <span className="font-semibold text-civic-teal">[{source.citation}] {source.procedure_code}</span>
            <span className="ml-1">{source.section_name}</span>
            <div className="mt-1 line-clamp-2 text-civic-muted">{source.name}</div>
          </a>
        ))}
      </div>
    </div>
  );
}

function FormattedAnswer({ content }: { content: string }) {
  const blocks = content.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
  if (blocks.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {blocks.map((block, index) => {
        const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
        if (isMarkdownTable(lines)) {
          return <MarkdownTable key={index} lines={lines} />;
        }
        if (lines.length === 1 && !isListLine(lines[0])) {
          return <p key={index}>{renderInline(lines[0])}</p>;
        }

        return (
          <div key={index} className="space-y-1">
            {lines.map((line, lineIndex) => (
              <div key={lineIndex} className={lineIndex > 0 || isListLine(line) ? "pl-3" : "font-semibold"}>
                {renderInline(cleanListMarker(line))}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function isMarkdownTable(lines: string[]) {
  return lines.length >= 2 && lines[0].includes("|") && /^[:\-\s|]+$/.test(lines[1]);
}

function MarkdownTable({ lines }: { lines: string[] }) {
  const rows = lines
    .filter((line, index) => index !== 1)
    .map((line) =>
      line
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((cell) => cell.trim()),
    );
  const [header, ...body] = rows;
  return (
    <div className="overflow-x-auto rounded-md border border-civic-line bg-white">
      <table className="min-w-full border-collapse text-left text-xs">
        <thead className="bg-slate-50">
          <tr>
            {header.map((cell, index) => (
              <th key={index} className="border-b border-civic-line px-2 py-2 font-semibold">
                {renderInline(cell)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="border-t border-civic-line px-2 py-2 align-top">
                  {renderInline(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function isListLine(line: string) {
  return /^(\d+\.|-|\*)\s+/.test(line);
}

function cleanListMarker(line: string) {
  return line.replace(/^###\s*/, "").replace(/^[-*]\s+/, "• ").replace(/^(\d+\.)\s+/, "$1 ");
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|https?:\/\/[^\s)]+|\[[^\]]+\]\((https?:\/\/[^)]+)\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={nodes.length}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("[")) {
      const label = token.match(/^\[([^\]]+)\]/)?.[1] ?? "Link nguồn";
      const href = match[2];
      nodes.push(
        <a key={nodes.length} className="font-semibold text-civic-teal underline underline-offset-2" href={href} target="_blank" rel="noreferrer">
          {label}
        </a>,
      );
    } else {
      nodes.push(
        <a key={nodes.length} className="font-semibold text-civic-teal underline underline-offset-2" href={token} target="_blank" rel="noreferrer">
          {token}
        </a>,
      );
    }
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

function Select({ label, value, onChange, children }: { label: string; value: string; onChange: (value: string) => void; children: ReactNode }) {
  return (
    <label className="mt-3 block">
      <span className="text-sm font-medium text-civic-muted">{label}</span>
      <select className="mt-1 h-10 w-full rounded-md border border-civic-line bg-white px-3 text-sm outline-none focus:border-civic-teal" value={value} onChange={(event) => onChange(event.target.value)}>
        {children}
      </select>
    </label>
  );
}

function Meta({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <div className="flex min-w-0 items-start gap-2">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span className="min-w-0 break-words">{text}</span>
    </div>
  );
}

function Info({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="rounded-md border border-civic-line p-3">
      <div className="text-sm text-civic-muted">{label}</div>
      <div className="mt-1 whitespace-pre-wrap text-sm font-medium">{value || "Chưa có dữ liệu"}</div>
    </div>
  );
}

function LongText({ title, value }: { title: string; value?: string | null }) {
  return (
    <section>
      <h3 className="mb-2 font-semibold">{title}</h3>
      <div className="whitespace-pre-wrap rounded-md bg-slate-50 p-3 text-sm leading-6">{value || "Chưa có dữ liệu"}</div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <section className="rounded-lg border border-civic-line bg-white p-4 shadow-soft">
      <div className="text-sm text-civic-muted">{label}</div>
      <div className="mt-2 text-3xl font-semibold">{value.toLocaleString("vi-VN")}</div>
    </section>
  );
}

function BucketPanel({ title, items }: { title: string; items: Array<{ name: string; count: number }> }) {
  const max = Math.max(...items.map((item) => item.count), 1);
  return (
    <section className="rounded-lg border border-civic-line bg-white p-4 shadow-soft">
      <h2 className="mb-4 text-lg font-semibold">{title}</h2>
      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.name}>
            <div className="mb-1 flex items-center justify-between gap-3 text-sm">
              <span className="min-w-0 truncate">{item.name}</span>
              <span className="font-semibold">{item.count}</span>
            </div>
            <div className="h-2 rounded-full bg-slate-100">
              <div className="h-2 rounded-full bg-civic-teal" style={{ width: `${Math.max(4, (item.count / max) * 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 rounded-md bg-slate-50 p-4 text-sm text-civic-muted">
      <Loader2 className="animate-spin" size={18} />
      {label}
    </div>
  );
}

function formatSeconds(value: number) {
  return `${value.toLocaleString("vi-VN", { maximumFractionDigits: 1 })} giây`;
}

function normalizeErrorMessage(err: unknown, fallback: string) {
  const raw = err instanceof Error ? err.message : "";
  if (!raw) {
    return fallback;
  }

  try {
    const parsed = JSON.parse(raw);
    const detail = parsed?.detail;
    if (Array.isArray(detail)) {
      const first = detail[0];
      if (first?.type === "string_too_short" && Array.isArray(first.loc) && first.loc.includes("question")) {
        return "Câu hỏi cần có ít nhất 3 ký tự.";
      }
      if (typeof first?.msg === "string") {
        return first.msg;
      }
    }
    if (typeof detail === "string") {
      return detail;
    }
  } catch {
    // Keep the original message below if it is already readable.
  }

  return raw.startsWith("{") ? fallback : raw;
}
