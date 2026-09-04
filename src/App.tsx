import {
  Activity,
  ArrowRight,
  BrainCircuit,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  CloudUpload,
  Download,
  ExternalLink,
  FileSpreadsheet,
  Filter,
  FlaskConical,
  KeyRound,
  Library as LibraryIcon,
  LoaderCircle,
  LogOut,
  Menu,
  Play,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  UserRound,
  Video as VideoIcon,
  WandSparkles,
  X,
  XCircle,
} from "lucide-react";
import {
  startTransition,
  useDeferredValue,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { ApiError, backend, downloadExport } from "./api";
import type {
  AnalysisSettings,
  AuthSession,
  ImportResult,
  Job,
  JWStatus,
  Library,
  ServiceStatus,
  Video,
  ViewName,
} from "./types";

const LIBRARIES: Record<string, Library> = {
  DEV: {
    name: "DEV",
    propertyId: "FvJr6FNj",
    url: "https://dashboard.jwplayer.com/p/FvJr6FNj/media",
  },
  EBSERH: {
    name: "EBSERH",
    propertyId: "UBP82vRQ",
    url: "https://dashboard.jwplayer.com/p/UBP82vRQ/media",
  },
  SANARFLIX: {
    name: "SANARFLIX",
    propertyId: "XK8A5jD7",
    url: "https://dashboard.jwplayer.com/p/XK8A5jD7/media",
  },
  VIDEOSSANAR: {
    name: "VIDEOS SANAR",
    propertyId: "XdfUPSCL",
    url: "https://dashboard.jwplayer.com/p/XdfUPSCL/media",
  },
};

const PROVIDER_MODELS = {
  Gemini: "gemini-flash-latest",
  Claude: "claude-sonnet-4-5",
  Ollama: "llava:7b",
} as const;

const CATEGORIES = [
  "Teórica core",
  "Teórica apenas slide",
  "Demonstrativo",
  "Teórica core + demonstrativo",
];

const NAV_ITEMS: Array<{
  id: ViewName;
  label: string;
  description: string;
  icon: typeof Server;
}> = [
  { id: "connection", label: "Conectar", description: "Sessão JW", icon: Server },
  { id: "import", label: "Enviar planilha", description: "Preparar lote", icon: CloudUpload },
  { id: "processing", label: "Processamento", description: "Acompanhar fila", icon: Activity },
  { id: "results", label: "Resultados", description: "Revisar acervo", icon: FileSpreadsheet },
];

const TERMINAL_JOB_STATES = new Set(["completed", "error", "cancelled"]);

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Ocorreu um erro inesperado.";
}

function formatDuration(value?: number | null) {
  if (!value) return "—";
  const totalSeconds = Math.round(value);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function publishYear(value?: string | null) {
  if (!value) return "";
  const match = value.match(/^\d{4}/);
  return match?.[0] ?? "";
}

function jobTone(state: Job["state"]) {
  if (state === "completed") return "success";
  if (state === "error" || state === "cancelled") return "danger";
  if (state === "paused") return "warning";
  return "active";
}

function videoTone(status?: string) {
  const normalized = (status ?? "Pendente").toLocaleLowerCase("pt-BR");
  if (normalized.includes("conclu")) return "success";
  if (normalized.includes("erro")) return "danger";
  if (normalized.includes("process")) return "active";
  return "neutral";
}

function Panel({
  title,
  eyebrow,
  action,
  children,
  className = "",
}: {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          {eyebrow && <span className="eyebrow">{eyebrow}</span>}
          <h2>{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function EmptyState({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  );
}

function LoginScreen({
  session,
  loading,
  connectionError,
  onLogin,
  onRetry,
}: {
  session: AuthSession | null;
  loading: boolean;
  connectionError: string;
  onLogin: (username: string, password: string) => Promise<void>;
  onRetry: () => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await onLogin(username, password);
      setPassword("");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-shell">
      <div className="login-grid" aria-hidden="true" />
      <section className="login-story">
        <div className="brand brand-light">
          <span className="brand-mark"><FlaskConical size={22} /></span>
          <span><strong>CetrusLab</strong><b>IA</b></span>
        </div>
        <div className="story-copy">
          <span className="eyebrow light">INTELIGÊNCIA DE CONTEÚDO</span>
          <h1>Do vídeo bruto ao acervo organizado.</h1>
          <p>
            Classifique, resuma e revise o portfólio Cetrus em um fluxo único,
            com rastreabilidade em cada etapa.
          </p>
        </div>
        <div className="story-metrics">
          <div><BrainCircuit /><span><strong>IA multimodal</strong><small>Frames e transcrição</small></span></div>
          <div><ShieldCheck /><span><strong>Acesso protegido</strong><small>Sessão segura e privada</small></span></div>
        </div>
      </section>

      <section className="login-card-wrap">
        <div className="login-card">
          <span className="login-symbol"><KeyRound /></span>
          <span className="eyebrow">ACESSO OPERACIONAL</span>
          <h2>Entrar no CetrusLabIA</h2>
          <p>Use as credenciais configuradas no ambiente da aplicação.</p>

          {connectionError ? (
            <div className="alert danger">
              <XCircle size={18} />
              <span>{connectionError}</span>
              <button type="button" className="text-button" onClick={onRetry}>Tentar novamente</button>
            </div>
          ) : loading || !session ? (
            <div className="login-loading"><LoaderCircle className="spin" /> Verificando sessão segura...</div>
          ) : (
            <form onSubmit={submit} className="form-stack">
              <label>
                Usuário
                <span className="input-with-icon"><UserRound size={17} /><input autoFocus autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></span>
              </label>
              <label>
                Senha
                <span className="input-with-icon"><KeyRound size={17} /><input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></span>
              </label>
              {error && <div className="field-error"><TriangleAlert size={16} />{error}</div>}
              <button className="button primary button-wide" disabled={submitting}>
                {submitting ? <LoaderCircle className="spin" size={18} /> : <ShieldCheck size={18} />}
                {submitting ? "Autenticando..." : "Acessar plataforma"}
              </button>
            </form>
          )}
          <small className="security-note"><CircleDot size={12} /> A senha não é armazenada no navegador.</small>
        </div>
      </section>
    </main>
  );
}

export default function App() {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [connectionError, setConnectionError] = useState("");
  const [view, setView] = useState<ViewName>("connection");
  const [mobileNav, setMobileNav] = useState(false);
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus | null>(null);
  const [libraryKey, setLibraryKey] = useState("VIDEOSSANAR");
  const [jwStatus, setJwStatus] = useState<JWStatus>({ state: "disconnected" });
  const [jwEmail, setJwEmail] = useState("");
  const [jwPassword, setJwPassword] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [filterEnabled, setFilterEnabled] = useState(false);
  const [minPublishDate, setMinPublishDate] = useState("");
  const [includeMissingDate, setIncludeMissingDate] = useState(false);
  const [settings, setSettings] = useState<AnalysisSettings>({
    provider: "Gemini",
    model: PROVIDER_MODELS.Gemini,
    analysisMode: "frames",
    frameCount: 8,
    whisperModel: "small",
  });
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [singleId, setSingleId] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [videos, setVideos] = useState<Video[]>([]);
  const [busy, setBusy] = useState("");
  const [toast, setToast] = useState<{ tone: string; message: string } | null>(null);
  const [search, setSearch] = useState("");
  const [yearFilter, setYearFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [validationVideo, setValidationVideo] = useState<Video | null>(null);
  const [validationCategory, setValidationCategory] = useState("");
  const [validationSummary, setValidationSummary] = useState("");
  const workspaceRequestId = useRef(0);
  const validationDialog = useRef<HTMLElement>(null);
  const validationTrigger = useRef<HTMLButtonElement | null>(null);
  const deferredSearch = useDeferredValue(search);

  const library = LIBRARIES[libraryKey];
  const jwConnected =
    (jwStatus.state === "connected" || jwStatus.connected === true) &&
    (!jwStatus.property_id || jwStatus.property_id === library.propertyId);

  function notify(message: string, tone = "success") {
    setToast({ message, tone });
    window.setTimeout(() => setToast(null), 4500);
  }

  async function checkSession() {
    setSessionLoading(true);
    setConnectionError("");
    try {
      setSession(await backend.session());
    } catch (error) {
      setConnectionError(
        error instanceof ApiError && error.status === 404
          ? "O backend conectado ainda não oferece autenticação."
          : `Não foi possível acessar o backend: ${errorMessage(error)}`,
      );
    } finally {
      setSessionLoading(false);
    }
  }

  useEffect(() => {
    void checkSession();
    function unauthorized() {
      setSession((current) => current ? { ...current, authenticated: false } : null);
      notify("Sua sessão expirou. Entre novamente.", "danger");
    }
    window.addEventListener("cetrus:unauthorized", unauthorized);
    return () => window.removeEventListener("cetrus:unauthorized", unauthorized);
  }, []);

  async function refreshWorkspace(showFeedback = false) {
    const requestId = ++workspaceRequestId.current;
    const selected = LIBRARIES[libraryKey];
    const results = await Promise.allSettled([
      backend.status(),
      backend.jwStatus(libraryKey, selected.propertyId),
      backend.jobs(),
      backend.videos(),
    ]);

    if (requestId !== workspaceRequestId.current) return;
    if (results[0].status === "fulfilled") setServiceStatus(results[0].value);
    if (results[1].status === "fulfilled") setJwStatus(results[1].value);
    if (results[2].status === "fulfilled") setJobs(results[2].value.items);
    if (results[3].status === "fulfilled") setVideos(results[3].value.items);
    if (showFeedback) {
      const failed = results.filter((result) => result.status === "rejected").length;
      notify(
        failed === 0
          ? "Dados atualizados."
          : `${failed} consulta(s) não puderam ser atualizadas.`,
        failed === 0 ? "success" : "danger",
      );
    }
  }

  useEffect(() => {
    if (!session?.authenticated) return;
    void refreshWorkspace();
  }, [session?.authenticated, libraryKey]);

  useEffect(() => {
    if (!session?.authenticated) return;
    const interval = window.setInterval(async () => {
      try {
        const [jobData, videoData] = await Promise.all([backend.jobs(), backend.videos()]);
        startTransition(() => {
          setJobs(jobData.items);
          setVideos(videoData.items);
        });
      } catch {
        // The API client handles expired sessions globally.
      }
    }, 5000);
    return () => window.clearInterval(interval);
  }, [session?.authenticated]);

  useEffect(() => {
    if (!validationVideo) return;
    function handleDialogKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setValidationVideo(null);
        return;
      }
      if (event.key !== "Tab") return;

      const controls = validationDialog.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), select:not(:disabled), textarea:not(:disabled), input:not(:disabled), [tabindex]:not([tabindex="-1"])',
      );
      if (!controls?.length) {
        event.preventDefault();
        validationDialog.current?.focus();
        return;
      }

      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    window.addEventListener("keydown", handleDialogKey);
    return () => {
      window.removeEventListener("keydown", handleDialogKey);
      validationTrigger.current?.focus();
      validationTrigger.current = null;
    };
  }, [validationVideo]);

  async function login(username: string, password: string) {
    const authenticated = await backend.login(username, password);
    setSession(authenticated);
  }

  async function logout() {
    setBusy("logout");
    try {
      setSession(await backend.logout());
    } catch (error) {
      notify(errorMessage(error), "danger");
    } finally {
      setBusy("");
    }
  }

  async function connectJW(event: FormEvent) {
    event.preventDefault();
    setBusy("jw-login");
    try {
      const result = await backend.jwLogin({
        library: libraryKey,
        property_id: library.propertyId,
        email: jwEmail,
        password: jwPassword,
      });
      setJwStatus(result);
      setJwPassword("");
      notify("Biblioteca JW Player conectada.");
    } catch (error) {
      notify(errorMessage(error), "danger");
    } finally {
      setBusy("");
    }
  }

  async function selectLibrary(nextKey: string) {
    if (nextKey === libraryKey) return;
    workspaceRequestId.current += 1;
    const next = LIBRARIES[nextKey];
    setBusy("library");
    setImportResult(null);
    try {
      const result = jwConnected
        ? await backend.switchLibrary(nextKey, next.propertyId)
        : await backend.jwStatus(nextKey, next.propertyId);
      setLibraryKey(nextKey);
      setJwStatus(result);
      if (result.state === "connected") notify(`Biblioteca alterada para ${next.name}.`);
    } catch (error) {
      setLibraryKey(nextKey);
      setJwStatus({ state: "error", message: errorMessage(error) });
    } finally {
      setBusy("");
    }
  }

  function processingPayload() {
    return {
      provider: settings.provider,
      model: settings.model,
      analysis_mode: settings.analysisMode,
      frame_count: settings.frameCount,
      whisper_model: settings.whisperModel,
    };
  }

  async function importSpreadsheet(event: FormEvent) {
    event.preventDefault();
    if (!file) return notify("Selecione uma planilha para continuar.", "danger");
    setBusy("import");
    setImportResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("library", libraryKey);
      formData.append("property_id", library.propertyId);
      formData.append("provider", settings.provider);
      formData.append("model", settings.model);
      formData.append("analysis_mode", settings.analysisMode);
      formData.append("frame_count", String(settings.frameCount));
      formData.append("whisper_model", settings.whisperModel);
      formData.append("min_publish_date", filterEnabled ? minPublishDate : "");
      formData.append("include_missing_date", String(includeMissingDate));
      const result = await backend.importSpreadsheet(formData);
      setImportResult(result);
      setView("import");
      await refreshWorkspace();
      notify("Planilha importada e filtro aplicado.");
    } catch (error) {
      notify(errorMessage(error), "danger");
    } finally {
      setBusy("");
    }
  }

  async function startEligible() {
    if (!importResult) return;
    setBusy("start");
    try {
      const result = await backend.startEligible({
        ...processingPayload(),
        run_id: importResult.run_id,
      });
      setJobs(result.jobs);
      setView("processing");
      notify(result.message ?? `${result.media_count} vídeo(s) enviado(s) para análise.`);
    } catch (error) {
      notify(errorMessage(error), "danger");
    } finally {
      setBusy("");
    }
  }

  async function analyzeOne(event: FormEvent) {
    event.preventDefault();
    setBusy("single");
    try {
      const result = await backend.analyzeOne({
        jwplayer_id: singleId.trim(),
        library: libraryKey,
        property_id: library.propertyId,
        min_publish_date: filterEnabled ? minPublishDate : "",
        include_missing_date: includeMissingDate,
        ...processingPayload(),
      });
      setJobs((current) => [...current, ...result.jobs]);
      setSingleId("");
      setView("processing");
      notify(result.message);
    } catch (error) {
      notify(errorMessage(error), "danger");
    } finally {
      setBusy("");
    }
  }

  function openValidation(video: Video, trigger: HTMLButtonElement) {
    validationTrigger.current = trigger;
    setValidationVideo(video);
    setValidationCategory(video.final_category ?? video.ai_category ?? CATEGORIES[0]);
    setValidationSummary(video.summary ?? "");
  }

  function closeValidation() {
    setValidationVideo(null);
  }

  async function saveValidation(event: FormEvent) {
    event.preventDefault();
    if (!validationVideo) return;
    setBusy("validation");
    try {
      await backend.validate({
        jwplayer_id: validationVideo.jwplayer_id,
        final_category: validationCategory,
        summary: validationSummary,
        validated: true,
      });
      closeValidation();
      const data = await backend.videos();
      setVideos(data.items);
      notify("Revisão salva como validada.");
    } catch (error) {
      notify(errorMessage(error), "danger");
    } finally {
      setBusy("");
    }
  }

  async function exportResults(format: "csv" | "xlsx") {
    setBusy(`export-${format}`);
    try {
      await downloadExport(format, yearFilter);
      notify(`Exportação ${format.toUpperCase()} gerada.`);
    } catch (error) {
      notify(errorMessage(error), "danger");
    } finally {
      setBusy("");
    }
  }

  if (!session?.authenticated) {
    return (
      <LoginScreen
        session={session}
        loading={sessionLoading}
        connectionError={connectionError}
        onLogin={login}
        onRetry={() => void checkSession()}
      />
    );
  }

  const years = Array.from(new Set(videos.map((video) => publishYear(video.publish_date)).filter(Boolean))).sort().reverse();
  const normalizedSearch = deferredSearch.trim().toLocaleLowerCase("pt-BR");
  const filteredVideos = videos.filter((video) => {
    const text = [video.lesson_name, video.professor_name, video.jwplayer_id, video.macrotema, video.microtema, video.nanotema]
      .filter(Boolean).join(" ").toLocaleLowerCase("pt-BR");
    return (!normalizedSearch || text.includes(normalizedSearch))
      && (!yearFilter || publishYear(video.publish_date) === yearFilter)
      && (!statusFilter || (video.status ?? "Pendente") === statusFilter)
      && (!categoryFilter || video.final_category === categoryFilter);
  });
  const activeJobs = jobs.filter((job) => !TERMINAL_JOB_STATES.has(job.state));
  const completed = videos.filter((video) => video.status === "Concluído").length;
  const validated = videos.filter((video) => video.validation_status === "Validado").length;
  const errors = videos.filter((video) => video.status === "Erro").length;

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? "mobile-open" : ""}`}>
        <div className="brand">
          <span className="brand-mark"><FlaskConical size={21} /></span>
          <span><strong>CetrusLab</strong><b>IA</b><small>Content intelligence</small></span>
        </div>
        <div className="flow-label">FLUXO DE TRABALHO</div>
        <nav aria-label="Etapas da aplicação">
          {NAV_ITEMS.map((item, index) => {
            const Icon = item.icon;
            return (
              <button key={item.id} className={`nav-item ${view === item.id ? "active" : ""}`} onClick={() => { setView(item.id); setMobileNav(false); }} aria-current={view === item.id ? "step" : undefined}>
                <span className="nav-index">{index + 1}</span>
                <Icon className="nav-icon" size={18} />
                <span><strong>{item.label}</strong><small>{item.description}</small></span>
                <ChevronRight className="nav-chevron" size={16} />
              </button>
            );
          })}
        </nav>
        <div className="sidebar-status">
          <span className={`status-light ${jwConnected ? "online" : ""}`} />
          <div><small>JW PLAYER</small><strong>{jwConnected ? library.name : "Desconectado"}</strong></div>
        </div>
      </aside>

      <div className="mobile-scrim" onClick={() => setMobileNav(false)} />

      <main className="workspace">
        <header className="topbar">
          <button className="icon-button menu-button" aria-label="Abrir navegação" onClick={() => setMobileNav(true)}><Menu /></button>
          <div>
            <span className="eyebrow">LABORATÓRIO DE CONTEÚDO</span>
            <h1>{NAV_ITEMS.find((item) => item.id === view)?.label}</h1>
          </div>
          <div className="topbar-actions">
            <span className="operator"><span>{session.username.slice(0, 1).toUpperCase()}</span><small>{session.username}</small></span>
            <button className="button secondary compact" onClick={() => void refreshWorkspace(true)}><RefreshCw size={16} />Atualizar</button>
            {session.auth_enabled && <button className="icon-button" aria-label="Sair" title="Sair" onClick={() => void logout()} disabled={busy === "logout"}><LogOut size={18} /></button>}
          </div>
        </header>

        <div className="workspace-content">
          {view === "connection" && (
            <div className="view-grid connection-grid">
              <Panel eyebrow="ETAPA 01" title="Biblioteca de mídia">
                <p className="panel-intro">Escolha o acervo que será consultado nesta sessão.</p>
                <div className="library-list">
                  {Object.entries(LIBRARIES).map(([key, item]) => (
                    <button className={`library-option ${libraryKey === key ? "selected" : ""}`} key={key} onClick={() => void selectLibrary(key)} disabled={busy === "library" || busy === "import"}>
                      <span className="library-glyph"><LibraryIcon size={18} /></span>
                      <span><strong>{item.name}</strong><small>{item.propertyId}</small></span>
                      {libraryKey === key && <Check size={17} />}
                    </button>
                  ))}
                </div>
                <a className="inline-link" href={library.url} target="_blank" rel="noreferrer">Abrir biblioteca no JW Player <ExternalLink size={14} /></a>
              </Panel>

              <Panel eyebrow="SESSÃO DO NAVEGADOR" title="Conexão JW Player" className="connection-panel">
                <div className={`connection-state ${jwConnected ? "connected" : jwStatus.state}`}>
                  <span>{jwConnected ? <CheckCircle2 /> : jwStatus.state === "connecting" ? <LoaderCircle className="spin" /> : <Server />}</span>
                  <div><strong>{jwConnected ? "Sessão conectada" : "Aguardando conexão"}</strong><p>{jwStatus.message ?? (jwConnected ? `Acesso ativo em ${library.name}.` : "Informe as credenciais da conta JW Player.")}</p></div>
                </div>
                {!jwConnected && (
                  <form className="form-stack" onSubmit={connectJW}>
                    <label>E-mail JW Player<input type="email" autoComplete="username" value={jwEmail} onChange={(event) => setJwEmail(event.target.value)} placeholder="nome@empresa.com" required /></label>
                    <label>Senha<input type="password" autoComplete="current-password" value={jwPassword} onChange={(event) => setJwPassword(event.target.value)} required /></label>
                    <button className="button primary" disabled={busy === "jw-login"}>{busy === "jw-login" ? <LoaderCircle className="spin" size={18} /> : <Play size={18} />}{busy === "jw-login" ? "Conectando..." : "Conectar biblioteca"}</button>
                  </form>
                )}
                {jwConnected && (
                  <div className="connected-actions">
                    <button className="button secondary" onClick={async () => { setBusy("verify"); try { setJwStatus(await backend.jwStatus(libraryKey, library.propertyId, true)); notify("Sessão verificada."); } catch (error) { notify(errorMessage(error), "danger"); } finally { setBusy(""); } }}><RefreshCw size={16} />Verificar sessão</button>
                    <button className="button primary" onClick={() => setView("import")}>Continuar<ArrowRight size={17} /></button>
                  </div>
                )}
                <div className="security-strip"><ShieldCheck size={18} /><span><strong>Credenciais efêmeras</strong><small>A senha JW é usada apenas durante a autenticação e não é persistida.</small></span></div>
              </Panel>
            </div>
          )}

          {view === "import" && (
            <div className="import-layout">
              {!jwConnected && <div className="alert warning"><TriangleAlert /><span><strong>Conecte o JW Player antes de preparar um lote.</strong> Volte à primeira etapa para autenticar a biblioteca.</span><button className="text-button" onClick={() => setView("connection")}>Ir para conexão</button></div>}
              <div className="view-grid import-grid">
                <Panel eyebrow="LOTE DE ENTRADA" title="Planilha e recorte">
                  <form className="form-stack" onSubmit={importSpreadsheet}>
                    <label className={`dropzone ${file ? "has-file" : ""}`}>
                      <input type="file" accept=".csv,.xls,.xlsx" disabled={busy === "import"} onChange={(event) => { setFile(event.target.files?.[0] ?? null); setImportResult(null); }} />
                      <span className="drop-icon">{file ? <FileSpreadsheet /> : <CloudUpload />}</span>
                      <span><strong>{file ? file.name : "Selecione ou arraste a planilha"}</strong><small>{file ? `${(file.size / 1024).toFixed(1)} KB` : "CSV, XLS ou XLSX"}</small></span>
                      {file && <CheckCircle2 className="file-check" />}
                    </label>
                    <div className="divider-label"><span>FILTRO DE PUBLICAÇÃO</span></div>
                    <label className="switch-row"><span><strong>Aplicar data mínima</strong><small>Ignora vídeos publicados antes do recorte.</small></span><input type="checkbox" checked={filterEnabled} disabled={busy === "import"} onChange={(event) => { setFilterEnabled(event.target.checked); setImportResult(null); }} /><i /></label>
                    {filterEnabled && <label>Publicados a partir de<input type="date" value={minPublishDate} disabled={busy === "import"} onChange={(event) => { setMinPublishDate(event.target.value); setImportResult(null); }} required /></label>}
                    <label className="check-row"><input type="checkbox" checked={includeMissingDate} disabled={busy === "import"} onChange={(event) => { setIncludeMissingDate(event.target.checked); setImportResult(null); }} /><span><strong>Incluir vídeos sem data</strong><small>Use quando o metadado não estiver disponível no JW Player.</small></span></label>
                    <button className="button primary" disabled={!jwConnected || !file || busy === "import"}>{busy === "import" ? <LoaderCircle className="spin" size={18} /> : <CloudUpload size={18} />}{busy === "import" ? "Consultando publicações..." : "Importar e aplicar filtro"}</button>
                  </form>
                </Panel>

                <Panel eyebrow="MOTOR DE ANÁLISE" title="Inteligência artificial">
                  <div className="form-stack">
                    <label>Provedor<select value={settings.provider} onChange={(event) => { const provider = event.target.value as AnalysisSettings["provider"]; setSettings((current) => ({ ...current, provider, model: PROVIDER_MODELS[provider] })); }}>
                      <option value="Gemini" disabled={serviceStatus ? !serviceStatus.gemini : false}>Gemini{serviceStatus && !serviceStatus.gemini ? " — indisponível" : ""}</option>
                      <option value="Claude" disabled={serviceStatus ? !serviceStatus.claude : false}>Claude{serviceStatus && !serviceStatus.claude ? " — indisponível" : ""}</option>
                      {serviceStatus?.ollama_enabled && <option value="Ollama">Ollama</option>}
                    </select></label>
                    <label>Modelo<input value={settings.model} onChange={(event) => setSettings((current) => ({ ...current, model: event.target.value }))} /></label>
                    <label>Estratégia<select value={settings.analysisMode} onChange={(event) => setSettings((current) => ({ ...current, analysisMode: event.target.value as AnalysisSettings["analysisMode"] }))}><option value="frames">Frames — rápido</option><option value="hybrid">Híbrido — frames + transcrição</option></select></label>
                    <div className="two-fields">
                      <label>Quantidade de frames<select value={settings.frameCount} onChange={(event) => setSettings((current) => ({ ...current, frameCount: Number(event.target.value) }))}><option value={6}>6 — rápido</option><option value={8}>8 — equilibrado</option><option value={12}>12 — detalhado</option></select></label>
                      {settings.analysisMode === "hybrid" && <label>Modelo Whisper<select value={settings.whisperModel} onChange={(event) => setSettings((current) => ({ ...current, whisperModel: event.target.value as AnalysisSettings["whisperModel"] }))}><option value="base">base</option><option value="small">small</option><option value="medium">medium</option></select></label>}
                    </div>
                    <div className="insight-card"><Sparkles size={19} /><span><strong>Análise visual acelerada</strong><small>Os frames são distribuídos ao longo do vídeo e enviados em uma única chamada multimodal.</small></span></div>
                  </div>
                </Panel>
              </div>

              {importResult && (
                <Panel eyebrow="PRÉVIA DO LOTE" title="Recorte pronto para análise" className="batch-summary">
                  <div className="summary-stats">
                    <div><small>LINHAS</small><strong>{importResult.rows}</strong></div>
                    <div><small>VÍDEOS ÚNICOS</small><strong>{importResult.unique_media}</strong></div>
                    <div className="positive"><small>ELEGÍVEIS</small><strong>{importResult.filter.will_be_analyzed}</strong></div>
                    <div><small>FORA DO RECORTE</small><strong>{importResult.filter.filtered}</strong></div>
                    <div><small>SEM DATA</small><strong>{importResult.filter.no_date}</strong></div>
                  </div>
                  <div className="batch-action"><p>A importação não inicia IA automaticamente. Confira o recorte e libere o processamento.</p><button className="button primary" onClick={() => void startEligible()} disabled={busy === "start" || importResult.filter.will_be_analyzed === 0}>{busy === "start" ? <LoaderCircle className="spin" size={18} /> : <Play size={18} />}Iniciar análise</button></div>
                </Panel>
              )}

              <Panel eyebrow="AÇÃO RÁPIDA" title="Analisar um único vídeo">
                <form className="single-analysis" onSubmit={analyzeOne}>
                  <label>JWPlayer ID<input value={singleId} onChange={(event) => setSingleId(event.target.value)} placeholder="Ex.: Ab12Cd34" minLength={8} required /></label>
                  <button className="button secondary" disabled={!jwConnected || busy === "single"}>{busy === "single" ? <LoaderCircle className="spin" size={18} /> : <WandSparkles size={18} />}Analisar ID</button>
                </form>
              </Panel>
            </div>
          )}

          {view === "processing" && (
            <div className="processing-layout">
              <div className="metric-strip">
                <div><span className="metric-icon active"><Activity /></span><small>EM ANDAMENTO</small><strong>{activeJobs.length}</strong></div>
                <div><span className="metric-icon"><FileSpreadsheet /></span><small>TOTAL NA FILA</small><strong>{jobs.length}</strong></div>
                <div><span className="metric-icon success"><CheckCircle2 /></span><small>CONCLUÍDOS</small><strong>{jobs.filter((job) => job.state === "completed").length}</strong></div>
              </div>
              <Panel eyebrow="EXECUÇÃO SEQUENCIAL" title="Fila de processamento" action={<button className="button secondary compact" onClick={() => void refreshWorkspace(true)}><RefreshCw size={15} />Sincronizar</button>}>
                {jobs.length === 0 ? <EmptyState icon={<Activity />} title="Nenhum trabalho iniciado" text="Prepare um lote ou envie um JWPlayer ID na etapa anterior." /> : (
                  <div className="job-list">
                    {[...jobs].reverse().map((job, index) => (
                      <article className="job-card" key={job.id}>
                        <div className={`job-state ${jobTone(job.state)}`}>{job.state === "completed" ? <CheckCircle2 /> : job.state === "error" ? <XCircle /> : <LoaderCircle className={TERMINAL_JOB_STATES.has(job.state) ? "" : "spin"} />}</div>
                        <div className="job-main"><div><span className="job-order">#{String(jobs.length - index).padStart(2, "0")}</span><strong>{job.jwplayer_id ?? job.media_id}</strong><span className={`badge ${jobTone(job.state)}`}>{job.state}</span></div><p>{job.stage}<span>·</span>{job.message}</p><div className="job-track"><i className={job.state} /></div></div>
                        <div className="job-meta"><small>{job.provider}</small><span>{job.model}</span></div>
                      </article>
                    ))}
                  </div>
                )}
              </Panel>
            </div>
          )}

          {view === "results" && (
            <div className="results-layout">
              <div className="metric-strip results-metrics">
                <div><span className="metric-icon"><VideoIcon /></span><small>NO ACERVO</small><strong>{videos.length}</strong></div>
                <div><span className="metric-icon success"><CheckCircle2 /></span><small>CONCLUÍDOS</small><strong>{completed}</strong></div>
                <div><span className="metric-icon active"><ShieldCheck /></span><small>VALIDADOS</small><strong>{validated}</strong></div>
                <div><span className="metric-icon danger"><TriangleAlert /></span><small>COM ERRO</small><strong>{errors}</strong></div>
              </div>
              <Panel eyebrow="PORTFÓLIO CLASSIFICADO" title="Resultados" action={<div className="export-actions"><button className="button secondary compact" onClick={() => void exportResults("csv")} disabled={busy.startsWith("export")}><Download size={15} />CSV</button><button className="button primary compact" onClick={() => void exportResults("xlsx")} disabled={busy.startsWith("export")}><Download size={15} />Excel</button></div>}>
                <div className="filters-bar">
                  <label className="search-field"><Search size={17} /><input aria-label="Buscar resultados" placeholder="Aula, professor, tema ou ID" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
                  <label><span>Ano</span><select aria-label="Filtrar por ano" value={yearFilter} onChange={(event) => setYearFilter(event.target.value)}><option value="">Todos</option>{years.map((year) => <option key={year}>{year}</option>)}</select></label>
                  <label><span>Status</span><select aria-label="Filtrar por status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">Todos</option><option>Pendente</option><option>Processando</option><option>Concluído</option><option>Erro</option></select></label>
                  <label><span>Modelo</span><select aria-label="Filtrar por modelo" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}><option value="">Todos</option>{CATEGORIES.map((category) => <option key={category}>{category}</option>)}</select></label>
                  <span className="filter-count"><Filter size={14} />{filteredVideos.length} resultado(s)</span>
                </div>
                {filteredVideos.length === 0 ? <EmptyState icon={<Search />} title="Nenhum resultado encontrado" text="Altere os filtros ou processe novos vídeos." /> : (
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>Aula</th><th>Modelo</th><th>Resumo</th><th>Tema</th><th>Status</th><th>Publicação</th><th /></tr></thead>
                      <tbody>{filteredVideos.map((video) => (
                        <tr key={video.jwplayer_id}>
                          <td><div className="lesson-cell"><strong>{video.lesson_name || video.jwplayer_id}</strong><span>{video.professor_name || "Professor não identificado"}</span><code>{video.jwplayer_id}</code></div></td>
                          <td><span className="category-label">{video.final_category || "Não classificado"}</span><small className="confidence">{video.confidence != null ? `${Math.round(video.confidence * 100)}% confiança` : "—"}</small></td>
                          <td><p className="summary-cell">{video.summary || video.error_message || "Aguardando análise."}</p></td>
                          <td><div className="topic-cell"><strong>{video.macrotema || "Não identificado"}</strong><span>{video.microtema || "—"}</span><small>{video.nanotema || "—"}</small></div></td>
                          <td><span className={`badge ${videoTone(video.status)}`}>{video.status || "Pendente"}</span><small className="validation-state">{video.validation_status || "Pendente"}</small></td>
                          <td><span>{publishYear(video.publish_date) || "—"}</span><small>{formatDuration(video.duration)}</small></td>
                          <td><button className="icon-button table-action" aria-label={`Revisar ${video.lesson_name ?? video.jwplayer_id}`} title="Revisar resultado" onClick={(event) => openValidation(video, event.currentTarget)} disabled={video.status !== "Concluído"}><ChevronRight size={18} /></button></td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
              </Panel>
            </div>
          )}
        </div>
      </main>

      <nav className="mobile-tabs" aria-label="Etapas da aplicação">
        {NAV_ITEMS.map((item, index) => { const Icon = item.icon; return <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}><Icon size={19} /><span>{index + 1}. {item.label}</span></button>; })}
      </nav>

      {validationVideo && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeValidation(); }}>
          <section ref={validationDialog} className="modal" role="dialog" aria-modal="true" aria-labelledby="validation-title" tabIndex={-1}>
            <div className="modal-head"><div><span className="eyebrow">REVISÃO HUMANA</span><h2 id="validation-title">Validar classificação</h2></div><button className="icon-button" aria-label="Fechar" onClick={closeValidation}><X /></button></div>
            <div className="video-reference"><span><VideoIcon /></span><div><strong>{validationVideo.lesson_name}</strong><small>{validationVideo.jwplayer_id} · {validationVideo.professor_name || "Professor não identificado"}</small></div></div>
            <form className="form-stack" onSubmit={saveValidation}>
              <label>Modelo de aula<select autoFocus value={validationCategory} onChange={(event) => setValidationCategory(event.target.value)}>{CATEGORIES.map((category) => <option key={category}>{category}</option>)}</select></label>
              <label>Resumo<textarea rows={7} maxLength={500} value={validationSummary} onChange={(event) => setValidationSummary(event.target.value)} required /><small className="character-count">{validationSummary.length}/500</small></label>
              <div className="modal-actions"><button type="button" className="button secondary" onClick={closeValidation}>Cancelar</button><button className="button primary" disabled={busy === "validation"}>{busy === "validation" ? <LoaderCircle className="spin" size={18} /> : <Check size={18} />}Salvar validação</button></div>
            </form>
          </section>
        </div>
      )}

      {toast && <div className={`toast ${toast.tone}`} role="status">{toast.tone === "danger" ? <XCircle /> : <CheckCircle2 />}<span>{toast.message}</span><button aria-label="Fechar aviso" onClick={() => setToast(null)}><X /></button></div>}
    </div>
  );
}
