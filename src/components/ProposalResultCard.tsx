import { useState } from "react";
import { Download, FileJson, Image, FileCode, Plus, Pencil, LoaderCircle, LayoutDashboard, Calculator } from "lucide-react";

type Lang = "es" | "en" | "zh" | "pg";

type ProposalTaskResult = {
  task_id: string;
  status: string;
  current_stage?: string | null;
  error?: { message?: string; detail?: string; last_stage?: string } | null;
  artifacts?: {
    json_info?: { filename: string; size_bytes: number } | null;
    pptx_info?: { filename: string; size_bytes: number } | null;
    hld_png?: { filename: string; size_bytes: number } | null;
    hld_drawio?: { filename: string; size_bytes: number } | null;
  } | null;
  hld_design_id?: string | null;
  created_at: string;
  updated_at: string;
  finished_at?: string | null;
};

const copy: Record<Lang, {
  title: string;
  generated: string;
  downloadPptx: string;
  downloadJson: string;
  downloadHldPng: string;
  downloadHldDrawio: string;
  createAnother: string;
  modifyAnswers: string;
  statusContent: string;
  statusQuote: string;
  statusHld: string;
  generatedLabel: string;
  fallbackLabel: string;
  skippedLabel: string;
  succeededLabel: string;
  failedLabel: string;
  notImplLabel: string;
  pendingLabel: string;
}> = {
  en: {
    title: "Proposal Generated",
    generated: "Generated",
    downloadPptx: "Download PPTX",
    downloadJson: "Download JSON",
    downloadHldPng: "Download Architecture PNG",
    downloadHldDrawio: "Download Architecture .drawio",
    createAnother: "Create another proposal",
    modifyAnswers: "Edit inputs",
    statusContent: "Content",
    statusQuote: "Pricing",
    statusHld: "Architecture",
    generatedLabel: "AI",
    fallbackLabel: "Template",
    skippedLabel: "Skipped",
    succeededLabel: "Done",
    failedLabel: "Failed",
    notImplLabel: "N/A",
    pendingLabel: "Pending",
  },
  es: {
    title: "Propuesta Generada",
    generated: "Generada",
    downloadPptx: "Descargar PPTX",
    downloadJson: "Descargar JSON",
    downloadHldPng: "Descargar PNG Arquitectura",
    downloadHldDrawio: "Descargar .drawio Arquitectura",
    createAnother: "Crear otra propuesta",
    modifyAnswers: "Editar entradas",
    statusContent: "Contenido",
    statusQuote: "Precios",
    statusHld: "Arquitectura",
    generatedLabel: "IA",
    fallbackLabel: "Plantilla",
    skippedLabel: "Omitido",
    succeededLabel: "Listo",
    failedLabel: "Falló",
    notImplLabel: "N/D",
    pendingLabel: "Pendiente",
  },
  zh: {
    title: "提案已生成",
    generated: "生成时间",
    downloadPptx: "下载 PPTX",
    downloadJson: "下载 JSON",
    downloadHldPng: "下载架构 PNG",
    downloadHldDrawio: "下载架构 .drawio",
    createAnother: "创建新提案",
    modifyAnswers: "修改输入",
    statusContent: "内容",
    statusQuote: "报价",
    statusHld: "架构",
    generatedLabel: "AI",
    fallbackLabel: "模板",
    skippedLabel: "跳过",
    succeededLabel: "完成",
    failedLabel: "失败",
    notImplLabel: "不可用",
    pendingLabel: "待处理",
  },
  pg: {
    title: "Proposta Gerada",
    generated: "Gerada",
    downloadPptx: "Baixar PPTX",
    downloadJson: "Baixar JSON",
    downloadHldPng: "Baixar PNG Arquitetura",
    downloadHldDrawio: "Baixar .drawio Arquitetura",
    createAnother: "Criar outra proposta",
    modifyAnswers: "Editar entradas",
    statusContent: "Conteúdo",
    statusQuote: "Preços",
    statusHld: "Arquitetura",
    generatedLabel: "IA",
    fallbackLabel: "Template",
    skippedLabel: "Pulado",
    succeededLabel: "Pronto",
    failedLabel: "Falhou",
    notImplLabel: "N/D",
    pendingLabel: "Pendente",
  },
};

const API_BASE_URL = (import.meta.env.VITE_QUOTE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "/quote-api";

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function statusPill(status: string, t: typeof copy.en) {
  const map: Record<string, string> = {
    generated: t.generatedLabel,
    fallback: t.fallbackLabel,
    skipped: t.skippedLabel,
    succeeded: t.succeededLabel,
    failed: t.failedLabel,
    not_implemented: t.notImplLabel,
    pending_external_workflow: t.pendingLabel,
  };
  return map[status] || status;
}

interface ProposalResultCardProps {
  taskId: string;
  result: ProposalTaskResult;
  lang: Lang;
  onCreateAnother: () => void;
  onModifyAnswers?: () => void;
  followUpActions?: { hldMode?: string; priceMode?: string };
}

export function ProposalResultCard({ taskId, result, lang, onCreateAnother, onModifyAnswers, followUpActions }: ProposalResultCardProps) {
  const t = copy[lang];
  const [downloading, setDownloading] = useState<string | null>(null);

  async function downloadArtifact(type: string, filename: string) {
    setDownloading(type);
    try {
      const resp = await fetch(`${API_BASE_URL}/api/proposals/tasks/${taskId}/artifacts/${type}`);
      if (!resp.ok) throw new Error("Download failed");
      const blob = await resp.blob();
      triggerDownload(blob, filename);
    } finally {
      setDownloading(null);
    }
  }

  // Read status fields from the JSON artifact
  const [jsonMeta, setJsonMeta] = useState<Record<string, unknown> | null>(null);
  useState(() => {
    fetch(`${API_BASE_URL}/api/proposals/tasks/${taskId}/artifacts/json`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setJsonMeta(d as Record<string, unknown>))
      .catch(() => {});
  });

  const contentStatus = (jsonMeta?.content_status as string) || "fallback";
  const quoteStatus = (jsonMeta?.quote_status as string) || "skipped";
  const hldStatus = (jsonMeta?.hld_status as string) || "skipped";
  const hasHld = result.hld_design_id && result.artifacts?.hld_png;

  return (
    <div className="proposal-result-card">
      <h3>{t.title}</h3>
      <div className="proposal-result-meta">
        {result.finished_at ? <span><strong>{t.generated}:</strong> {new Date(result.finished_at).toLocaleString()}</span> : null}
      </div>
      <div className="proposal-status-pills">
        <span className="proposal-status-pill">
          {t.statusContent}: <strong className={`pill-${contentStatus}`}>{statusPill(contentStatus, t)}</strong>
        </span>
        <span className="proposal-status-pill">
          {t.statusQuote}: <strong className={`pill-${quoteStatus}`}>{statusPill(quoteStatus, t)}</strong>
        </span>
        <span className="proposal-status-pill">
          {t.statusHld}: <strong className={`pill-${hldStatus}`}>{statusPill(hldStatus, t)}</strong>
        </span>
      </div>
      <div className="proposal-download">
        <button type="button" className="proposal-download-btn" onClick={() => downloadArtifact("pptx", "proposal.pptx")} disabled={downloading === "pptx"}>
          {downloading === "pptx" ? <LoaderCircle size={16} className="spin-icon" /> : <Download size={16} />}
          {t.downloadPptx}
        </button>
        <button type="button" className="proposal-download-btn" onClick={() => downloadArtifact("json", "proposal.json")} disabled={downloading === "json"}>
          {downloading === "json" ? <LoaderCircle size={16} className="spin-icon" /> : <FileJson size={16} />}
          {t.downloadJson}
        </button>
        {hasHld ? (
          <>
            <button type="button" className="proposal-download-btn" onClick={() => downloadArtifact("hld/png", "architecture.png")} disabled={downloading === "hld/png"}>
              {downloading === "hld/png" ? <LoaderCircle size={16} className="spin-icon" /> : <Image size={16} />}
              {t.downloadHldPng}
            </button>
            <button type="button" className="proposal-download-btn" onClick={() => downloadArtifact("hld/drawio", "architecture.drawio")} disabled={downloading === "hld/drawio"}>
              {downloading === "hld/drawio" ? <LoaderCircle size={16} className="spin-icon" /> : <FileCode size={16} />}
              {t.downloadHldDrawio}
            </button>
          </>
        ) : null}
      </div>
      <div className="proposal-result-bottom-actions">
        {followUpActions?.hldMode === "create_new" && (
          <a className="proposal-followup-link" href="#/hld">
            <LayoutDashboard size={16} />
            {lang === "zh" ? "前往 HLD 工作流" : lang === "es" ? "Ir al flujo HLD" : "Go to HLD workflow"}
          </a>
        )}
        {followUpActions?.priceMode === "create_new" && (
          <a className="proposal-followup-link" href="#/estimator">
            <Calculator size={16} />
            {lang === "zh" ? "前往定价工作流" : lang === "es" ? "Ir al flujo de Precios" : "Go to Pricing workflow"}
          </a>
        )}
        {onModifyAnswers ? (
          <button type="button" className="proposal-result-modify" onClick={onModifyAnswers}>
            <Pencil size={16} />
            {t.modifyAnswers}
          </button>
        ) : null}
        <button type="button" className="proposal-result-another" onClick={onCreateAnother}>
          <Plus size={16} />
          {t.createAnother}
        </button>
      </div>
    </div>
  );
}

export type { ProposalTaskResult };
