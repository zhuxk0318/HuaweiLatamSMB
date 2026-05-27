import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, KeyboardEvent } from "react";
import {
  ArrowUp,
  Calculator,
  FileText,
  FileUp,
  Layers3,
  LayoutDashboard,
  LoaderCircle,
  MessageSquarePlus,
  Paperclip,
  SquareArrowOutUpRight,
  X,
} from "lucide-react";
import { trackClick } from "../analytics";
import type { Lang } from "../data/i18n";
import { copy as i18nCopy } from "../data/i18n";
import { HldDesignWizard } from "./HldDesignWizard";
import type { HldRequirements } from "./HldDesignWizard";
import { HldDesignResultCard } from "./HldDesignResultCard";
import { ProposalWizard } from "./ProposalWizard";
import type { ProposalRequest } from "./ProposalWizard";
import { ProposalResultCard } from "./ProposalResultCard";
import type { ProposalTaskResult } from "./ProposalResultCard";

const API_BASE_URL = (import.meta.env.VITE_QUOTE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "/quote-api";

type UploadedFile = {
  file_id: string;
  filename: string;
  size_bytes: number;
  media_type?: string | null;
  created_at: string;
};

type ChatCardAction = {
  label: string;
  action_type: "open_route" | "open_upload" | "suggest_prompt";
  target: string;
};

type ChatMessageBlock = {
  block_type: "text" | "solution_card" | "pricing_card" | "source_link";
  title?: string | null;
  body?: string | null;
  route?: string | null;
  image_url?: string | null;
  tags: string[];
  action?: ChatCardAction | null;
};

type ChatMessage = {
  message_id: string;
  role: "user" | "assistant";
  text: string;
  blocks: ChatMessageBlock[];
  created_at: string;
};

type ChatSessionCreatedResponse = {
  session_id: string;
  status: "active";
  created_at: string;
};

type ChatSessionResponse = {
  session_id: string;
  status: "active";
  messages: ChatMessage[];
  created_at: string;
  updated_at: string;
};

type ChatUploadResponse = {
  files: UploadedFile[];
};

type ChatStreamEvent = {
  event: "message_start" | "message_delta" | "message_block" | "message_end" | "error";
  session_id: string;
  message_id?: string | null;
  delta?: string | null;
  block?: ChatMessageBlock | null;
  error?: string | null;
};

const copy = {
  en: {
    productName: "Huawei LATAM SMB Advisor",
    welcomePrompt: "Where shall we start?",
    capabilityChips: ["Solutions", "Pricing", "Cloud Adoption"],
    placeholder: "Ask about SMB solutions, pricing, migration, healthcare, or upload a file for quotation guidance...",
    send: "Send",
    newChat: "New conversation",
    upload: "Upload files",
    uploading: "Uploading...",
    uploads: "Attached files",
    removeFile: "Remove file",
    errorSession: "Unable to initialize the conversation.",
    errorStream: "Unable to get a response from the assistant.",
    assistant: "Assistant",
    user: "You",
    open: "Open",
    askThis: "Ask this",
    fileReceived: "File uploaded and ready to reference in the conversation.",
    streaming: "Responding...",
    webSearch: "Web Search",
  },
  es: {
    productName: "Huawei LATAM SMB Advisor",
    welcomePrompt: "¿Por dónde empezamos?",
    capabilityChips: ["Soluciones", "Cotización", "Cloud Adoption"],
    placeholder: "Pregunte por soluciones SMB, precios, migración, salud o cargue un archivo para guía de cotización...",
    send: "Enviar",
    newChat: "Nueva conversación",
    upload: "Cargar archivos",
    uploading: "Cargando...",
    uploads: "Archivos adjuntos",
    removeFile: "Quitar archivo",
    errorSession: "No fue posible inicializar la conversación.",
    errorStream: "No fue posible obtener respuesta del asistente.",
    assistant: "Asistente",
    user: "Usted",
    open: "Abrir",
    askThis: "Preguntar esto",
    fileReceived: "Archivo cargado y listo para referenciar en la conversación.",
    streaming: "Respondiendo...",
    webSearch: "Búsqueda web",
  },
  zh: {
    productName: "Huawei LATAM SMB Advisor",
    welcomePrompt: "我们先从哪里开始？",
    capabilityChips: ["解决方案", "报价", "Cloud Adoption"],
    placeholder: "请输入 SMB 方案、报价、迁移、医疗或上传文件后的咨询内容...",
    send: "发送",
    newChat: "新对话",
    upload: "上传文件",
    uploading: "上传中...",
    uploads: "已附加文件",
    removeFile: "移除文件",
    errorSession: "初始化对话失败。",
    errorStream: "暂时无法获取助手回复。",
    assistant: "助手",
    user: "你",
    open: "打开",
    askThis: "继续追问",
    fileReceived: "文件已上传，可在当前对话中引用。",
    streaming: "正在回复...",
    webSearch: "联网搜索",
  },
  pg: {
    productName: "Huawei LATAM SMB Advisor",
    welcomePrompt: "Por onde começamos?",
    capabilityChips: ["Soluções", "Cotação", "Adoção Cloud"],
    placeholder: "Pergunte sobre soluções PME, preços, migração, saúde ou carregue um arquivo para orientação de cotação...",
    send: "Enviar",
    newChat: "Nova conversa",
    upload: "Carregar arquivos",
    uploading: "Carregando...",
    uploads: "Arquivos anexados",
    removeFile: "Remover arquivo",
    errorSession: "Não foi possível inicializar a conversa.",
    errorStream: "Não foi possível obter resposta do assistente.",
    assistant: "Assistente",
    user: "Você",
    open: "Abrir",
    askThis: "Perguntar isso",
    fileReceived: "Arquivo carregado e pronto para referência na conversa.",
    streaming: "Respondendo...",
    webSearch: "Busca na web",
  },
} satisfies Record<Lang, {
  productName: string;
  welcomePrompt: string;
  capabilityChips: string[];
  placeholder: string;
  send: string;
  newChat: string;
  upload: string;
  uploading: string;
  uploads: string;
  removeFile: string;
  errorSession: string;
  errorStream: string;
  assistant: string;
  user: string;
  open: string;
  askThis: string;
  fileReceived: string;
  streaming: string;
  webSearch: string;
}>;

type PortalMessage = ChatMessage & {
  pending?: boolean;
};

const hldCopy: Record<Lang, { generating: string; back: string; retry: string; editAnswers: string }> = {
  en: { generating: "Generating HLD diagram…", back: "Back", retry: "Retry generation", editAnswers: "Edit answers" },
  es: { generating: "Generando diagrama HLD…", back: "Volver", retry: "Reintentar generación", editAnswers: "Editar respuestas" },
  zh: { generating: "正在生成 HLD 图…", back: "返回", retry: "重试生成", editAnswers: "修改答案" },
  pg: { generating: "Gerando diagrama HLD…", back: "Voltar", retry: "Tentar novamente", editAnswers: "Editar respostas" },
};

const capabilityEntries = [
  {
    key: "pricing",
    label: "Pricing",
    description: { en: "Estimate cloud costs from RVTools or requirements", es: "Estime costos cloud desde RVTools o requerimientos", zh: "基于 RVTools 或需求估算云成本", pg: "Estime custos cloud desde RVTools ou requisitos" },
    href: "#/estimator",
    icon: Calculator,
  },
  {
    key: "hld",
    label: "HLD Design",
    description: { en: "Generate high-level architecture diagrams", es: "Genere diagramas de arquitectura de alto nivel", zh: "生成高层架构设计图", pg: "Gere diagramas de arquitetura de alto nível" },
    href: "#/hld",
    icon: LayoutDashboard,
  },
  {
    key: "proposal",
    label: "Proposal",
    description: { en: "Generate a full technical proposal with PPTX", es: "Genere una propuesta técnica completa con PPTX", zh: "生成包含 PPTX 的完整技术提案", pg: "Gere uma proposta técnica completa com PPTX" },
    href: "#/proposal",
    icon: FileText,
  },
] as const;

function getHeaderNavItems(lang: Lang) {
  const t = i18nCopy[lang];
  return [
    { label: t.nav.home, href: "#/", route: "home" },
    { label: t.nav.solutions, href: "#/solutions", route: "solutions" },
    { label: t.nav.migration, href: "#/migration", route: "migration" },
    { label: t.nav.pricing, href: "#/estimator", route: "pricing" },
    { label: t.nav.hld, href: "#/hld", route: "hld" },
    { label: t.nav.proposal, href: "#/proposal", route: "proposal" },
  ] as const;
}

function createLocalMessageId(prefix: string) {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return `${prefix}-${globalThis.crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function ChatPortal({ lang, setLang }: { lang: Lang; setLang: (lang: Lang) => void }) {
  const t = copy[lang];
  const currentHash = typeof window !== "undefined" ? window.location.hash : "";
  const currentRoute =
    currentHash.startsWith("#/solutions") ? "solutions" :
    currentHash.startsWith("#/migration") ? "migration" :
    currentHash.startsWith("#/estimator") ? "pricing" :
    currentHash.startsWith("#/hld") ? "hld" :
    currentHash.startsWith("#/proposal") ? "proposal" :
    "home";
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<PortalMessage[]>([]);
  const [composer, setComposer] = useState("");
  const [uploads, setUploads] = useState<UploadedFile[]>([]);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [bootstrapping, setBootstrapping] = useState(true);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const messageListRef = useRef<HTMLDivElement | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);
  const assistantMessageIdRef = useRef<string | null>(null);
  const shouldAutoScrollRef = useRef(true);

  // HLD mode state
  const [hldMode, setHldMode] = useState(false);
  const [hldDesignId, setHldDesignId] = useState("");
  const [hldPolling, setHldPolling] = useState(false);
  const [hldPngUrl, setHldPngUrl] = useState("");
  const [hldFilename, setHldFilename] = useState("");
  const [hldError, setHldError] = useState("");
  const [hldGeneratedAt, setHldGeneratedAt] = useState("");
  const [hldLastRequirements, setHldLastRequirements] = useState<HldRequirements | null>(null);
  const [hldReturnToReview, setHldReturnToReview] = useState(false);
  const hldPollTokenRef = useRef(0);

  // Proposal mode state
  const [proposalMode, setProposalMode] = useState(false);
  const [proposalTaskId, setProposalTaskId] = useState("");
  const [proposalPolling, setProposalPolling] = useState(false);
  const [proposalError, setProposalError] = useState("");
  const [proposalResult, setProposalResult] = useState<ProposalTaskResult | null>(null);
  const [proposalLastRequest, setProposalLastRequest] = useState<ProposalRequest | null>(null);
  const [proposalReturnToReview, setProposalReturnToReview] = useState(false);
  const proposalPollTokenRef = useRef(0);

  const proposalCopy: Record<Lang, { generating: string; back: string; retry: string; editAnswers: string }> = {
    en: { generating: "Generating proposal…", back: "Back", retry: "Retry", editAnswers: "Edit inputs" },
    es: { generating: "Generando propuesta…", back: "Volver", retry: "Reintentar", editAnswers: "Editar entradas" },
    zh: { generating: "正在生成提案…", back: "返回", retry: "重试", editAnswers: "修改输入" },
    pg: { generating: "Gerando proposta…", back: "Voltar", retry: "Tentar novamente", editAnswers: "Editar entradas" },
  };

  useEffect(() => {
    void startNewConversation();
  }, []);

  useLayoutEffect(() => {
    const container = messageListRef.current;
    if (!container || !shouldAutoScrollRef.current) return;
    window.requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
    });
  }, [messages, streaming]);

  // Sync hldMode/proposalMode from hash on every hash change
  useEffect(() => {
    const syncModes = () => {
      const hash = window.location.hash;
      if (hash === "#/hld") {
        setHldMode(true);
        setProposalMode(false);
      } else if (hash === "#/proposal") {
        setProposalMode(true);
        setHldMode(false);
      } else {
        setHldMode(false);
        setProposalMode(false);
      }
    };
    syncModes();
    window.addEventListener("hashchange", syncModes);
    return () => window.removeEventListener("hashchange", syncModes);
  }, []);

  // HLD submit handler
  async function handleHldSubmit(requirements: HldRequirements) {
    setHldLastRequirements(requirements);
    setHldReturnToReview(false);
    setHldPolling(true);
    setHldError("");
    const token = ++hldPollTokenRef.current;
    try {
      const resp = await fetch(`${API_BASE_URL}/api/hld/designs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requirements),
      });
      if (!resp.ok) throw new Error("Failed to create HLD design task");
      const payload = (await resp.json()) as { design_id: string; status: string };
      setHldDesignId(payload.design_id);
      pollHldDesign(payload.design_id, token);
    } catch (err) {
      setHldError(err instanceof Error ? err.message : "HLD submission failed");
      setHldPolling(false);
    }
  }

  function pollHldDesign(designId: string, token: number) {
    if (token !== hldPollTokenRef.current) return;
    fetch(`${API_BASE_URL}/api/hld/designs/${designId}`)
      .then((resp) => {
        if (!resp.ok) throw new Error("Poll failed");
        return resp.json();
      })
      .then((data: { status: string; output_basename?: string; finished_at?: string; error?: { message?: string; last_stage?: string } }) => {
        if (token !== hldPollTokenRef.current) return;
        if (data.status === "queued" || data.status === "running") {
          setTimeout(() => pollHldDesign(designId, token), 1000);
          return;
        }
        if (data.status === "failed") {
          const stage = data.error?.last_stage || "";
          const detail = data.error?.message || "HLD generation failed.";
          setHldError(stage ? `${detail} (stage: ${stage})` : detail);
          setHldPolling(false);
          return;
        }
        // succeeded — fetch PNG as blob URL for preview
        setHldFilename(data.output_basename || "hld-design");
        setHldGeneratedAt(data.finished_at || new Date().toISOString());
        fetch(`${API_BASE_URL}/api/hld/designs/${designId}/artifacts/png`)
          .then((r) => r.blob())
          .then((blob) => {
            if (token !== hldPollTokenRef.current) return;
            setHldPngUrl(URL.createObjectURL(blob));
            setHldPolling(false);
          })
          .catch(() => {
            setHldError("Failed to load PNG preview");
            setHldPolling(false);
          });
      })
      .catch(() => {
        if (token !== hldPollTokenRef.current) return;
        setHldError("Polling failed");
        setHldPolling(false);
      });
  }

  function resetHldMode() {
    ++hldPollTokenRef.current;
    setHldMode(false);
    setHldDesignId("");
    setHldPolling(false);
    setHldPngUrl("");
    setHldFilename("");
    setHldError("");
    setHldGeneratedAt("");
    setHldLastRequirements(null);
    window.location.hash = "#/";
  }

  function startAnotherHld() {
    ++hldPollTokenRef.current;
    setHldDesignId("");
    setHldPolling(false);
    setHldPngUrl("");
    setHldFilename("");
    setHldError("");
    setHldGeneratedAt("");
    setHldLastRequirements(null);
    setHldReturnToReview(false);
  }

  function handleModifyRequirements() {
    // Return to wizard at review step, preserving last requirements
    ++hldPollTokenRef.current;
    setHldDesignId("");
    setHldPolling(false);
    setHldPngUrl("");
    setHldFilename("");
    setHldError("");
    setHldGeneratedAt("");
    setHldReturnToReview(true);
    // hldLastRequirements is intentionally kept
  }

  // Proposal submit handler
  async function handleProposalSubmit(request: ProposalRequest) {
    setProposalLastRequest(request);
    setProposalReturnToReview(false);
    setProposalPolling(true);
    setProposalError("");
    setProposalResult(null);
    const token = ++proposalPollTokenRef.current;
    try {
      const resp = await fetch(`${API_BASE_URL}/api/proposals/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      if (!resp.ok) throw new Error("Failed to create proposal task");
      const payload = (await resp.json()) as { task_id: string; status: string };
      setProposalTaskId(payload.task_id);
      pollProposalTask(payload.task_id, token);
    } catch (err) {
      setProposalError(err instanceof Error ? err.message : "Proposal submission failed");
      setProposalPolling(false);
    }
  }

  function pollProposalTask(taskId: string, token: number) {
    if (token !== proposalPollTokenRef.current) return;
    fetch(`${API_BASE_URL}/api/proposals/tasks/${taskId}`)
      .then((resp) => {
        if (!resp.ok) throw new Error("Poll failed");
        return resp.json();
      })
      .then((data: ProposalTaskResult) => {
        if (token !== proposalPollTokenRef.current) return;
        if (data.status === "queued" || data.status === "running") {
          setTimeout(() => pollProposalTask(taskId, token), 1500);
          return;
        }
        if (data.status === "failed") {
          const stage = data.error?.last_stage || "";
          const detail = data.error?.message || "Proposal generation failed.";
          setProposalError(stage ? `${detail} (stage: ${stage})` : detail);
          setProposalPolling(false);
          return;
        }
        setProposalResult(data);
        setProposalPolling(false);
      })
      .catch(() => {
        if (token !== proposalPollTokenRef.current) return;
        setProposalError("Polling failed");
        setProposalPolling(false);
      });
  }

  function resetProposalMode() {
    ++proposalPollTokenRef.current;
    setProposalMode(false);
    setProposalTaskId("");
    setProposalPolling(false);
    setProposalError("");
    setProposalResult(null);
    setProposalLastRequest(null);
    window.location.hash = "#/";
  }

  function startAnotherProposal() {
    ++proposalPollTokenRef.current;
    setProposalTaskId("");
    setProposalPolling(false);
    setProposalError("");
    setProposalResult(null);
    setProposalLastRequest(null);
    setProposalReturnToReview(false);
  }

  function handleProposalModifyAnswers() {
    ++proposalPollTokenRef.current;
    setProposalTaskId("");
    setProposalPolling(false);
    setProposalError("");
    setProposalResult(null);
    setProposalReturnToReview(true);
  }

  function handleTranscriptScroll() {
    const container = messageListRef.current;
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < 80;
  }

  async function startNewConversation() {
    setBootstrapping(true);
    setError("");
    setMessages([]);
    setUploads([]);
    setComposer("");
    assistantMessageIdRef.current = null;
    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/sessions`, { method: "POST" });
      if (!response.ok) throw new Error(t.errorSession);
      const payload = (await response.json()) as ChatSessionCreatedResponse;
      setSessionId(payload.session_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.errorSession);
    } finally {
      setBootstrapping(false);
    }
  }

  async function ensureSession() {
    if (sessionId) return sessionId;
    const response = await fetch(`${API_BASE_URL}/api/chat/sessions`, { method: "POST" });
    if (!response.ok) throw new Error(t.errorSession);
    const payload = (await response.json()) as ChatSessionCreatedResponse;
    setSessionId(payload.session_id);
    return payload.session_id;
  }

  async function onUploadChange(event: ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files || []);
    event.target.value = "";
    if (selectedFiles.length === 0) return;
    setUploading(true);
    setError("");
    try {
      const formData = new FormData();
      for (const file of selectedFiles) {
        formData.append("files", file);
      }
      const response = await fetch(`${API_BASE_URL}/api/chat/uploads`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) throw new Error(t.errorStream);
      const payload = (await response.json()) as ChatUploadResponse;
      setUploads((current) => [...current, ...payload.files]);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.errorStream);
    } finally {
      setUploading(false);
    }
  }

  function removeUpload(fileId: string) {
    setUploads((current) => current.filter((item) => item.file_id !== fileId));
  }

  async function sendMessage(promptOverride?: string) {
    const text = (promptOverride ?? composer).trim();
    if (!text || streaming || bootstrapping) return;

    try {
      const nextUserMessage: PortalMessage = {
        message_id: createLocalMessageId("user"),
        role: "user",
        text,
        blocks: [],
        created_at: new Date().toISOString(),
      };
      setMessages((current) => [...current, nextUserMessage]);
      setComposer("");
      setError("");
      setStreaming(true);

      const activeSessionId = await ensureSession();
      const response = await fetch(`${API_BASE_URL}/api/chat/sessions/${activeSessionId}/messages/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          language: lang,
          file_ids: uploads.map((item) => item.file_id),
          web_search_enabled: webSearchEnabled,
        }),
      });
      if (!response.ok || !response.body) throw new Error(t.errorStream);
      await consumeEventStream(response.body);
      setUploads([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.errorStream);
    } finally {
      setStreaming(false);
      assistantMessageIdRef.current = null;
    }
  }

  async function consumeEventStream(stream: ReadableStream<Uint8Array>) {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        handleEventFrame(frame);
      }
    }
    if (buffer.trim()) {
      handleEventFrame(buffer);
    }
  }

  function handleEventFrame(frame: string) {
    const lines = frame.split("\n");
    let dataPayload = "";
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        dataPayload += line.slice(6);
      }
    }
    if (!dataPayload) return;
    const payload = JSON.parse(dataPayload) as ChatStreamEvent;

    if (payload.event === "message_start" && payload.message_id) {
      assistantMessageIdRef.current = payload.message_id;
      setMessages((current) => [
        ...current,
        {
          message_id: payload.message_id!,
          role: "assistant",
          text: "",
          blocks: [],
          created_at: new Date().toISOString(),
          pending: true,
        },
      ]);
      return;
    }

    if (payload.event === "message_delta" && payload.message_id && payload.delta) {
      setMessages((current) =>
        current.map((message) =>
          message.message_id === payload.message_id
            ? { ...message, text: `${message.text}${payload.delta}` }
            : message,
        ),
      );
      return;
    }

    if (payload.event === "message_block" && payload.message_id && payload.block) {
      setMessages((current) =>
        current.map((message) =>
          message.message_id === payload.message_id
            ? { ...message, blocks: [...message.blocks, payload.block!] }
            : message,
        ),
      );
      return;
    }

    if (payload.event === "message_end" && payload.message_id) {
      setMessages((current) =>
        current.map((message) =>
          message.message_id === payload.message_id ? { ...message, pending: false } : message,
        ),
      );
      return;
    }

    if (payload.event === "error" && payload.error) {
      setError(payload.error);
    }
  }

  function onComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  }

  function handleCardAction(block: ChatMessageBlock) {
    const action = block.action;
    if (!action) return;
    if (action.action_type === "open_route") {
      window.location.hash = action.target;
      return;
    }
    if (action.action_type === "open_upload") {
      fileInputRef.current?.click();
      return;
    }
    if (action.action_type === "suggest_prompt") {
      setComposer(action.target);
    }
  }

  const welcomeVisible = useMemo(() => !hldMode && !proposalMode && messages.length === 0, [hldMode, proposalMode, messages.length]);
  const isWorkflowMode = hldMode || proposalMode;

  return (
    <main className="chat-portal-page">
      <header className="site-header chat-portal-site-header">
        <a
          className="brand"
          href="#/"
          aria-label="Huawei LATAM SMB Solutions"
          onClick={() =>
            trackClick({
              click_target: "nav_logo",
              click_section: "header",
              destination: "#/",
            })
          }
        >
          <img src="/assets/huawei/huawei-logo.png" alt="Huawei" />
          <span>LATAM SMB Solutions</span>
        </a>
        <nav className="main-nav" aria-label="Primary">
          {getHeaderNavItems(lang).map((item) => (
            <a
              key={item.label}
              className={currentRoute === item.route ? "nav-active" : ""}
              href={item.href}
              onClick={() =>
                trackClick({ click_target: `chat_nav_${item.route}`, click_section: "chat_header", destination: item.href })
              }
            >
              {item.label}
            </a>
          ))}
        </nav>
        <div className="chat-portal-actions chat-portal-site-actions">
          <div className="language-toggle chat-language-toggle" aria-label="Language">
            {/* <button type="button" className={lang === "pg" ? "active" : ""} onClick={() => setLang("pg")}>
              PG
            </button> */}
            <button type="button" className={lang === "es" ? "active" : ""} onClick={() => setLang("es")}>
              ES
            </button>
            <button type="button" className={lang === "en" ? "active" : ""} onClick={() => setLang("en")}>
              EN
            </button>
            <button type="button" className={lang === "zh" ? "active" : ""} onClick={() => setLang("zh")}>
              中
            </button>
          </div>
          {!isWorkflowMode ? (
            <button
              type="button"
              className="chat-secondary-button"
              onClick={() => {
                trackClick({ click_target: "chat_new_conversation", click_section: "chat_header", destination: "new_chat" });
                void startNewConversation();
              }}
            >
              <MessageSquarePlus size={16} />
              {t.newChat}
            </button>
          ) : null}
        </div>
      </header>

      <section className={welcomeVisible ? "chat-portal-shell is-empty" : "chat-portal-shell"}>
        <div
          className={welcomeVisible ? "chat-portal-transcript is-empty" : "chat-portal-transcript"}
          ref={messageListRef}
          onScroll={handleTranscriptScroll}
        >
          {welcomeVisible ? (
            <div className="chat-portal-welcome">
              <p>{t.welcomePrompt}</p>
              <div className="chat-capability-entries">
                {capabilityEntries.map((entry) => {
                  const Icon = entry.icon;
                  return (
                    <a
                      className="chat-capability-entry"
                      href={entry.href}
                      key={entry.key}
                      onClick={(event) => {
                        if (entry.key === "hld") {
                          event.preventDefault();
                          window.location.hash = "#/hld";
                          trackClick({ click_target: "chat_entry_hld", click_section: "chat_capability_entries", destination: "hld_wizard" });
                          return;
                        }
                        if (entry.key === "proposal") {
                          event.preventDefault();
                          window.location.hash = "#/proposal";
                          trackClick({ click_target: "chat_entry_proposal", click_section: "chat_capability_entries", destination: "proposal_wizard" });
                          return;
                        }
                        trackClick({ click_target: `chat_entry_${entry.key}`, click_section: "chat_capability_entries", destination: entry.href });
                      }}
                    >
                      <span className="chat-capability-entry-icon"><Icon size={22} /></span>
                      <strong>{entry.label}</strong>
                      <small>{entry.description[lang]}</small>
                    </a>
                  );
                })}
              </div>
            </div>
          ) : hldMode ? (
            <div className="chat-message-list">
              {hldPngUrl ? (
                <HldDesignResultCard
                  designId={hldDesignId}
                  pngUrl={hldPngUrl}
                  filename={hldFilename}
                  generatedAt={hldGeneratedAt}
                  lang={lang}
                  onCreateAnother={startAnotherHld}
                  onModifyRequirements={handleModifyRequirements}
                />
              ) : hldPolling ? (
                <div className="hld-generating">
                  <LoaderCircle size={24} className="spin-icon" />
                  <p>{hldCopy[lang].generating}</p>
                </div>
              ) : hldError ? (
                <div className="hld-generating">
                  <p className="form-error">{hldError}</p>
                  <div className="hld-error-actions">
                    {hldLastRequirements ? (
                      <button type="button" className="hld-result-another" onClick={() => handleHldSubmit(hldLastRequirements)}>
                        {hldCopy[lang].retry}
                      </button>
                    ) : null}
                    <button type="button" className="chat-secondary-button" onClick={handleModifyRequirements}>
                      {hldCopy[lang].editAnswers}
                    </button>
                    <button type="button" className="chat-secondary-button" onClick={resetHldMode}>
                      {hldCopy[lang].back}
                    </button>
                  </div>
                </div>
              ) : (
                <HldDesignWizard
                  lang={lang}
                  onSubmit={handleHldSubmit}
                  onCancel={resetHldMode}
                  initialRequirements={hldReturnToReview ? hldLastRequirements : null}
                  initialStep={hldReturnToReview ? "summary" : undefined}
                />
              )}
            </div>
          ) : proposalMode ? (
            <div className="chat-message-list">
              {proposalResult ? (
                <ProposalResultCard
                  taskId={proposalTaskId}
                  result={proposalResult}
                  lang={lang}
                  onCreateAnother={startAnotherProposal}
                  onModifyAnswers={handleProposalModifyAnswers}
                  followUpActions={{
                    hldMode: proposalLastRequest?.hld_mode,
                    priceMode: proposalLastRequest?.price_mode,
                  }}
                />
              ) : proposalPolling ? (
                <div className="hld-generating">
                  <LoaderCircle size={24} className="spin-icon" />
                  <p>{proposalCopy[lang].generating}</p>
                </div>
              ) : proposalError ? (
                <div className="hld-generating">
                  <p className="form-error">{proposalError}</p>
                  <div className="hld-error-actions">
                    {proposalLastRequest ? (
                      <button type="button" className="hld-result-another" onClick={() => handleProposalSubmit(proposalLastRequest)}>
                        {proposalCopy[lang].retry}
                      </button>
                    ) : null}
                    <button type="button" className="chat-secondary-button" onClick={handleProposalModifyAnswers}>
                      {proposalCopy[lang].editAnswers}
                    </button>
                    <button type="button" className="chat-secondary-button" onClick={resetProposalMode}>
                      {proposalCopy[lang].back}
                    </button>
                  </div>
                </div>
              ) : (
                <ProposalWizard
                  lang={lang}
                  onSubmit={handleProposalSubmit}
                  onCancel={resetProposalMode}
                />
              )}
            </div>
          ) : (
            <div className="chat-message-list">
              {messages.map((message) => (
                <article key={message.message_id} className={message.role === "assistant" ? "chat-message assistant" : "chat-message user"}>
                  <div className="chat-message-label">{message.role === "assistant" ? t.assistant : t.user}</div>
                  <div className="chat-message-body">
                    <p>{message.text}</p>
                    {message.blocks.length > 0 ? (
                      <div className="chat-block-grid">
                        {message.blocks.map((block, index) => (
                          <div
                            className={block.block_type === "pricing_card" ? "chat-structured-card pricing" : "chat-structured-card"}
                            key={`${message.message_id}-${block.block_type}-${index}`}
                          >
                            {block.image_url ? <img src={block.image_url} alt="" loading="lazy" /> : null}
                            <div className="chat-structured-card-body">
                              {block.title ? <strong>{block.title}</strong> : null}
                              {block.body ? <p>{block.body}</p> : null}
                              {block.tags.length > 0 ? (
                                <div className="tag-row">
                                  {block.tags.map((tag) => (
                                    <span className="service-tag" key={tag}>
                                      {tag}
                                    </span>
                                  ))}
                                </div>
                              ) : null}
                              {block.action ? (
                                <button type="button" className="chat-card-action" onClick={() => handleCardAction(block)}>
                                  {block.action.action_type === "suggest_prompt" ? t.askThis : t.open}
                                  <SquareArrowOutUpRight size={15} />
                                </button>
                              ) : null}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                    {message.pending ? (
                      <span className="chat-streaming-indicator">
                        <LoaderCircle size={16} className="spin-icon" />
                        {t.streaming}
                      </span>
                    ) : null}
                  </div>
                </article>
              ))}
              <div ref={transcriptEndRef} aria-hidden="true" />
            </div>
          )}
        </div>

        {!isWorkflowMode ? (
          <div className={welcomeVisible ? "chat-composer-shell is-empty" : "chat-composer-shell"}>
            {uploads.length > 0 ? (
              <div className="chat-upload-list">
                <strong>{t.uploads}</strong>
                <div className="chat-upload-pills">
                  {uploads.map((upload) => (
                    <span className="chat-upload-pill" key={upload.file_id}>
                      <FileUp size={14} />
                      <span>{upload.filename}</span>
                      <button type="button" aria-label={t.removeFile} onClick={() => removeUpload(upload.file_id)}>
                        <X size={14} />
                      </button>
                    </span>
                  ))}
                </div>
                <small>{t.fileReceived}</small>
              </div>
            ) : null}

            <div className="chat-composer">
              <label className={webSearchEnabled ? "chat-search-toggle is-active" : "chat-search-toggle"}>
                <input
                  type="checkbox"
                  checked={webSearchEnabled}
                  onChange={(event) => setWebSearchEnabled(event.target.checked)}
                  disabled={bootstrapping || streaming}
                />
                <span>{t.webSearch}</span>
              </label>
              <button
                type="button"
                className="chat-icon-button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading || streaming}
                aria-label={t.upload}
              >
                {uploading ? <LoaderCircle size={18} className="spin-icon" /> : <Paperclip size={18} />}
              </button>
              <textarea
                value={composer}
                onChange={(event) => setComposer(event.target.value)}
                onKeyDown={onComposerKeyDown}
                placeholder={t.placeholder}
                rows={1}
                disabled={bootstrapping || streaming}
              />
              <button
                type="button"
                className="chat-send-button"
                onClick={() => void sendMessage()}
                disabled={!composer.trim() || bootstrapping || streaming}
              >
                <ArrowUp size={18} />
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".xlsx,.csv,.pdf,.doc,.docx,.txt"
                hidden
                onChange={onUploadChange}
              />
            </div>
            {error ? <p className="form-error chat-form-error">{error}</p> : null}
          </div>
        ) : null}
      </section>
    </main>
  );
}
