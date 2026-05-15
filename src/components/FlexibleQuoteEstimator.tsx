import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { AlertCircle, Calculator, Download, FileSpreadsheet, LoaderCircle, UploadCloud } from "lucide-react";
import { trackClick } from "../analytics";
import { pricingCatalog, type PricingRegionKey } from "../data/pricingCatalog";
import type { Lang } from "../data/i18n";

const QUOTE_API_BASE_URL = (import.meta.env.VITE_QUOTE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ??
  "/quote-api";

type RowQuoteSummary = {
  total_rows: number;
  quoted_rows: number;
  unmatched_rows: number;
  manual_review_rows: number;
  missing_price_rows: number;
  non_quote_rows: number;
  total_ondemand_monthly: number;
  total_monthly: number;
  total_ri_1y_monthly: number;
  currency: string;
};

type RowQuoteProgress = {
  total_rows: number;
  processed_rows: number;
  quoted_rows: number;
  manual_review_rows: number;
  missing_price_rows: number;
  unmatched_rows: number;
  non_quote_rows: number;
  mapped_rows: number;
  priced_rows: number;
  stage_processed_rows: number;
  stage_total_rows: number;
};

type RowQuoteTaskResponse = {
  task_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  current_stage?: string | null;
  summary?: RowQuoteSummary | null;
  progress?: RowQuoteProgress | null;
  error?: {
    message: string;
    detail?: string | null;
    last_stage?: string | null;
  } | null;
  created_at: string;
  updated_at: string;
  finished_at?: string | null;
};

type PreviewViewState = "idle" | "ready" | "queued" | "running" | "succeeded" | "failed";

const regionOrder: PricingRegionKey[] = ["mexico", "chile", "brazil"];

const uiCopy = {
  es: {
    title: "Flexible Quote",
    body: "Cargue un Excel de cliente. El resultado conserva el libro original y agrega columnas de cotización Huawei Cloud al final de cada hoja.",
    upload: "Cargar Excel",
    preview: "Analizar filas",
    export: "Exportar Excel",
    context: "Contexto",
    region: "Región",
    language: "Idioma",
    notes: "Notas del cliente",
    summary: "Resumen de filas",
    progress: "Progreso",
    file: "Archivo",
    taskStatus: "Estado",
    currentStage: "Etapa actual",
    previewFailed: "Falló el análisis",
    taskMissing: "La tarea ya no existe o el servicio se reinició.",
    idle: "Cargue un archivo .xlsx para iniciar.",
    ready: "Archivo listo para analizar.",
    previewQueued: "Tarea en cola...",
    previewRunning: "Analizando filas...",
    exporting: "Generando Excel anotado...",
    success: "Excel anotado listo para exportar.",
    invalidFile: "Flexible Quote en modo fila solo admite .xlsx.",
    summaryWaiting: "El resumen aparecerá cuando termine el análisis.",
    totalRows: "Total filas",
    quotedRows: "Cotizadas",
    unmatchedRows: "Sin precio",
    missingPriceRows: "Sin precio",
    manualRows: "Confirmación",
    nonQuoteRows: "No cotización",
    ondemand: "On-demand",
    monthly: "Mensual",
    ri: "RI 1Y",
    progressLabelMapRows: "Mapeadas/Total",
    progressLabelPriceRows: "Cotizadas/Total",
  },
  en: {
    title: "Flexible Quote",
    body: "Upload a customer Excel workbook. The result preserves the original workbook and appends Huawei Cloud quote columns to every sheet.",
    upload: "Upload Excel",
    preview: "Analyze rows",
    export: "Export Excel",
    context: "Context",
    region: "Region",
    language: "Language",
    notes: "Customer notes",
    summary: "Row summary",
    progress: "Progress",
    file: "File",
    taskStatus: "Status",
    currentStage: "Current stage",
    previewFailed: "Analysis failed",
    taskMissing: "The task no longer exists or the service restarted.",
    idle: "Upload one .xlsx file to start.",
    ready: "File is ready for row analysis.",
    previewQueued: "Task queued...",
    previewRunning: "Analyzing rows...",
    exporting: "Generating annotated workbook...",
    success: "Annotated workbook is ready to export.",
    invalidFile: "Row-level Flexible Quote only supports .xlsx.",
    summaryWaiting: "Summary will appear when analysis completes.",
    totalRows: "Total rows",
    quotedRows: "Quoted",
    unmatchedRows: "Unmatched",
    missingPriceRows: "Missing price",
    manualRows: "Manual confirm",
    nonQuoteRows: "Non-quote",
    ondemand: "On-demand",
    monthly: "Monthly",
    ri: "RI 1Y",
    progressLabelMapRows: "Mapped/Total",
    progressLabelPriceRows: "Priced/Total",
  },
} satisfies Record<string, Record<string, string>>;

function money(value?: number | null, currency = "USD") {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(value);
}

async function getErrorDetail(response: Response, fallback: string) {
  const payload = await response.json().catch(() => null);
  return payload?.detail || fallback;
}

function triggerDownload(blob: Blob, filename: string) {
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(objectUrl);
}

function getDownloadFilename(header: string | null) {
  const matched = header?.match(/filename="?([^"]+)"?/i)?.[1]?.trim();
  return matched || "huawei-row-quote.xlsx";
}

function statusText(state: PreviewViewState, t: Record<string, string>) {
  if (state === "ready") {
    return t.ready;
  }
  if (state === "queued") {
    return t.previewQueued;
  }
  if (state === "running") {
    return t.previewRunning;
  }
  if (state === "succeeded") {
    return t.success;
  }
  if (state === "failed") {
    return t.previewFailed;
  }
  return t.idle;
}

function stageLabel(stage?: string | null) {
  if (!stage) {
    return "-";
  }
  if (stage === "collect_rows") {
    return "Collect Rows";
  }
  if (stage === "map_rows") {
    return "Map Rows";
  }
  if (stage === "price_rows") {
    return "Price Rows";
  }
  if (stage === "annotate_workbook") {
    return "Annotate Workbook";
  }
  if (stage === "completed") {
    return "Completed";
  }
  return stage;
}

function progressLabel(stage: string | null | undefined, t: Record<string, string>) {
  if (stage === "map_rows") {
    return t.progressLabelMapRows;
  }
  return t.progressLabelPriceRows;
}

export function FlexibleQuoteEstimator({ lang }: { lang: Lang }) {
  const t = uiCopy[lang] ?? uiCopy.en;
  const [file, setFile] = useState<File | null>(null);
  const [quoteContext, setQuoteContext] = useState({
    region: "mexico" as PricingRegionKey,
    language: lang,
    customer_notes: "",
  });
  const [previewState, setPreviewState] = useState<PreviewViewState>("idle");
  const [taskId, setTaskId] = useState("");
  const [task, setTask] = useState<RowQuoteTaskResponse | null>(null);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const pollTokenRef = useRef(0);

  useEffect(() => {
    setQuoteContext((current) => ({ ...current, language: lang }));
  }, [lang]);

  useEffect(() => {
    return () => {
      pollTokenRef.current += 1;
    };
  }, []);

  const progressBusy = previewState === "queued" || previewState === "running";
  const canExport = Boolean(taskId && previewState === "succeeded" && !exporting);
  const summary = task?.summary || null;

  function resetTracking(nextState: PreviewViewState) {
    pollTokenRef.current += 1;
    setPreviewState(nextState);
    setTaskId("");
    setTask(null);
    setError("");
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] || null;
    event.target.value = "";
    if (!selected) {
      return;
    }
    if (!/\.xlsx$/i.test(selected.name)) {
      setError(t.invalidFile);
      setPreviewState("failed");
      return;
    }
    trackClick({
      click_target: "flexible_row_quote_upload",
      click_section: "estimator",
      destination: "flexible_annotate_api",
    });
    setFile(selected);
    resetTracking("ready");
  }

  async function pollTask(nextTaskId: string, token: number) {
    try {
      const response = await fetch(`${QUOTE_API_BASE_URL}/api/quotes/flexible/annotate/tasks/${nextTaskId}`);
      if (token !== pollTokenRef.current) {
        return;
      }
      if (response.status === 404) {
        setPreviewState("failed");
        setError(t.taskMissing);
        return;
      }
      if (!response.ok) {
        throw new Error(await getErrorDetail(response, t.previewFailed));
      }
      const payload = (await response.json()) as RowQuoteTaskResponse;
      setTask(payload);
      if (payload.status === "queued" || payload.status === "running") {
        setPreviewState(payload.status);
        window.setTimeout(() => {
          if (token === pollTokenRef.current) {
            void pollTask(nextTaskId, token);
          }
        }, 1000);
        return;
      }
      if (payload.status === "failed") {
        setPreviewState("failed");
        setError(payload.error?.detail || payload.error?.message || t.previewFailed);
        return;
      }
      setPreviewState("succeeded");
      setError("");
    } catch (err) {
      if (token !== pollTokenRef.current) {
        return;
      }
      setPreviewState("failed");
      setError(err instanceof Error ? err.message : t.previewFailed);
    }
  }

  async function runPreview() {
    if (!file) {
      return;
    }
    pollTokenRef.current += 1;
    const token = pollTokenRef.current;
    setPreviewState("queued");
    setTaskId("");
    setTask(null);
    setError("");
    try {
      const formData = new FormData();
      formData.append("flexible_file", file);
      formData.append("region", quoteContext.region);
      formData.append("lang", quoteContext.language);
      formData.append("customer_notes", quoteContext.customer_notes);
      const response = await fetch(`${QUOTE_API_BASE_URL}/api/quotes/flexible/annotate/tasks`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        throw new Error(await getErrorDetail(response, t.previewFailed));
      }
      const payload = (await response.json()) as { task_id: string; status: "queued" | "running" };
      if (token !== pollTokenRef.current) {
        return;
      }
      setTaskId(payload.task_id);
      setPreviewState(payload.status);
      void pollTask(payload.task_id, token);
    } catch (err) {
      if (token !== pollTokenRef.current) {
        return;
      }
      setPreviewState("failed");
      setError(err instanceof Error ? err.message : t.previewFailed);
    }
  }

  async function runExport() {
    if (!taskId) {
      return;
    }
    setExporting(true);
    setError("");
    try {
      const response = await fetch(`${QUOTE_API_BASE_URL}/api/quotes/flexible/annotate/tasks/${taskId}/export`);
      if (!response.ok) {
        throw new Error(await getErrorDetail(response, t.exporting));
      }
      triggerDownload(await response.blob(), getDownloadFilename(response.headers.get("content-disposition")));
    } catch (err) {
      setError(err instanceof Error ? err.message : t.exporting);
    } finally {
      setExporting(false);
    }
  }

  const currentStage = task?.current_stage || (progressBusy ? "collect_rows" : null);
  const prog = task?.progress;
  const stageProcessed = prog?.stage_processed_rows ?? 0;
  const stageTotal = prog?.stage_total_rows ?? 0;

  return (
    <section className="pricing-section">
      <div className="section-heading split-heading">
        <div>
          <span className="section-kicker">Flexible Quote</span>
          <h2>{t.title}</h2>
          <p>{t.body}</p>
        </div>
        <div className="quote-actions">
          <label className="upload-button">
            <UploadCloud size={18} />
            {t.upload}
            <input type="file" accept=".xlsx" onChange={onFileChange} disabled={progressBusy || exporting} />
          </label>
          <button type="button" className="upload-button secondary" onClick={runPreview} disabled={!file || progressBusy || exporting}>
            <Calculator size={18} />
            {t.preview}
          </button>
          <button type="button" className="upload-button secondary" onClick={runExport} disabled={!canExport}>
            <Download size={18} />
            {t.export}
          </button>
        </div>
      </div>

      <div className="pricing-controls">
        <div>
          <strong>{t.context}</strong>
          <div className="flexible-form-grid">
            <label>
              <span>{t.region}</span>
              <select
                value={quoteContext.region}
                onChange={(event) => setQuoteContext((current) => ({ ...current, region: event.target.value as PricingRegionKey }))}
                disabled={progressBusy}
              >
                {regionOrder.map((key) => (
                  <option key={key} value={key}>{pricingCatalog[key].country}</option>
                ))}
              </select>
            </label>
            <label>
              <span>{t.language}</span>
              <input value={quoteContext.language} readOnly />
            </label>
            <label className="flexible-notes-field">
              <span>{t.notes}</span>
              <textarea
                rows={4}
                value={quoteContext.customer_notes}
                onChange={(event) => setQuoteContext((current) => ({ ...current, customer_notes: event.target.value }))}
                disabled={progressBusy}
              />
            </label>
          </div>
        </div>

        <article className="quote-panel">
          <div className="panel-title">
            {previewState === "failed" ? <AlertCircle size={20} /> : progressBusy ? <LoaderCircle size={20} className="spin-icon" /> : <FileSpreadsheet size={20} />}
            <h3>{t.summary}</h3>
          </div>
          {error ? <p className="form-error">{error}</p> : null}
          <div className="quote-metrics quote-metrics-extended">
            <span>
              <small>{t.file}</small>
              <strong>{file?.name || "-"}</strong>
            </span>
            <span>
              <small>{t.taskStatus}</small>
              <strong>{statusText(previewState, t)}</strong>
            </span>
          </div>
          {summary ? (
            <>
              <div className="quote-summary-grid">
                <span><small>{t.totalRows}</small><strong>{summary.total_rows}</strong></span>
                <span><small>{t.quotedRows}</small><strong>{summary.quoted_rows}</strong></span>
                <span><small>{t.unmatchedRows}</small><strong>{summary.unmatched_rows}</strong></span>
                <span><small>{t.missingPriceRows}</small><strong>{summary.missing_price_rows}</strong></span>
                <span><small>{t.manualRows}</small><strong>{summary.manual_review_rows}</strong></span>
                <span><small>{t.nonQuoteRows}</small><strong>{summary.non_quote_rows}</strong></span>
                <span><small>{t.monthly}</small><strong>{money(summary.total_monthly, summary.currency)}</strong></span>
              </div>
              <div className="quote-summary-grid">
                <span><small>{t.ondemand}</small><strong>{money(summary.total_ondemand_monthly, summary.currency)}</strong></span>
                <span><small>{t.ri}</small><strong>{money(summary.total_ri_1y_monthly, summary.currency)}</strong></span>
              </div>
            </>
          ) : (
            <p className="empty-state">{t.summaryWaiting}</p>
          )}
        </article>
      </div>

      <div className="pricing-dashboard">
        <article className="quote-panel">
          <div className="panel-title">
            {progressBusy ? <LoaderCircle size={20} className="spin-icon" /> : previewState === "failed" ? <AlertCircle size={20} /> : <Calculator size={20} />}
            <h3>{t.progress}</h3>
          </div>
          <div className="quote-metrics quote-metrics-extended">
            <span>
              <small>Task ID</small>
              <strong>{taskId || "-"}</strong>
            </span>
            <span>
              <small>{t.currentStage}</small>
              <strong>{stageLabel(currentStage)}</strong>
            </span>
            <span>
              <small>{t.taskStatus}</small>
              <strong>{task?.status || previewState}</strong>
            </span>
            <span>
              <small>{t.file}</small>
              <strong>{file?.name || "-"}</strong>
            </span>
            <span>
              <small>{progressLabel(currentStage, t)}</small>
              <strong>
                {prog
                  ? stageTotal > 0
                    ? `${stageProcessed}/${stageTotal}`
                    : "0/—"
                  : "-"}
              </strong>
            </span>
          </div>
          {prog ? (
            stageTotal > 0 ? (
              <div className="row-quote-progress-bar-wrap">
                <div className="row-quote-progress-bar">
                  <div
                    className="row-quote-progress-fill"
                    style={{ width: `${Math.round((stageProcessed / stageTotal) * 100)}%` }}
                  />
                </div>
                <span className="row-quote-progress-label">
                  {stageProcessed}/{stageTotal} ({Math.round((stageProcessed / stageTotal) * 100)}%)
                </span>
              </div>
            ) : (
              <div className="row-quote-progress-bar-wrap">
                <div className="row-quote-progress-bar">
                  <div className="row-quote-progress-fill" style={{ width: "0%" }} />
                </div>
                <span className="row-quote-progress-label">0/—</span>
              </div>
            )
          ) : null}
          <div className="flexible-progress-list">
            <div className={`flexible-progress-step status-${previewState === "failed" ? "failed" : previewState === "succeeded" ? "completed" : progressBusy ? "running" : "skipped"}`}>
              <strong>{stageLabel(currentStage)}</strong>
              <span>{task?.status || previewState}</span>
              <small>{statusText(previewState, t)}</small>
            </div>
          </div>
          {task?.error?.detail ? (
            <p className="form-error">
              {task.error.detail}
              {task.error.last_stage ? ` (${stageLabel(task.error.last_stage)})` : ""}
            </p>
          ) : null}
        </article>
      </div>
    </section>
  );
}
