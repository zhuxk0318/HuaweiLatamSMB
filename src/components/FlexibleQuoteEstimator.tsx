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
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
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
type SheetSelectionMode = "first" | "all" | "selected";

const regionOrder: PricingRegionKey[] = ["mexico", "chile", "brazil"];

const regionNames: Record<PricingRegionKey, string> = {
  mexico: "LA Mexico City 2",
  chile: "LA Santiago",
  brazil: "LA Sao Paulo 1",
};

const defaultNotes: Record<string, string> = {
  es: "Genere una cotización de Huawei Cloud para una pyme. Priorice opciones simples y costo-efectivas para LATAM, mantenga el mapeo práctico y marque las filas ambiguas para revisión manual.",
  en: "Please generate a Huawei Cloud quote for SMB use. Prefer simple, cost-effective options for LATAM, keep the mapping practical, and mark unclear rows for manual review.",
  zh: "请为 SMB 场景生成华为云报价，优先选择适合拉美区域的简单、成本友好方案，映射尽量务实，不明确的行标记为人工确认。",
  pg: "Please generate a Huawei Cloud quote for SMB use. Prefer simple, cost-effective options for LATAM, keep the mapping practical, and mark unclear rows for manual review.",
};

const uiCopy = {
  es: {
    title: "Flexible Quote",
    body: "Cargue un Excel de cliente. El resultado conserva el libro original y agrega columnas de cotización Huawei Cloud al final de cada hoja.",
    upload: "Cargar Excel",
    preview: "Analizar filas",
    export: "Exportar Excel",
    context: "Contexto",
    region: "Región",
    notesLabel: "Guía para la cotización con AI",
    notesHint: "Edite el siguiente texto para guiar la cotización con AI.",
    notesRequired: "Ingrese una guía para la cotización con AI antes de iniciar el análisis.",
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
    cancel: "Cancelar",
    cancelFailed: "No se pudo cancelar la tarea.",
    sheetSelection: "Hojas a procesar",
    sheetFirst: "Solo la primera hoja",
    sheetAll: "Todas las hojas",
    sheetSpecify: "Especificar hojas",
    sheetSpecifyPlaceholder: "p.ej. Compute, Storage, 1,3",
    sheetSpecifyEmpty: "Ingrese los nombres o índices de hoja.",
  },
  en: {
    title: "Flexible Quote",
    body: "Upload a customer Excel workbook. The result preserves the original workbook and appends Huawei Cloud quote columns to every sheet.",
    upload: "Upload Excel",
    preview: "Analyze rows",
    export: "Export Excel",
    context: "Context",
    region: "Region",
    notesLabel: "AI Quote Guidance",
    notesHint: "Edit the prompt below to guide the AI quote.",
    notesRequired: "Please enter AI quote guidance before starting the analysis.",
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
    cancel: "Cancel",
    cancelFailed: "Failed to cancel the task.",
    sheetSelection: "Sheets to process",
    sheetFirst: "First sheet only",
    sheetAll: "All sheets",
    sheetSpecify: "Specify sheets",
    sheetSpecifyPlaceholder: "e.g. Compute, Storage, 1,3",
    sheetSpecifyEmpty: "Enter sheet names or indexes.",
  },
  zh: {
    title: "Flexible 报价",
    body: "上传客户 Excel 工作簿。结果会保留原始工作簿，并在每个工作表末尾追加华为云报价列。",
    upload: "上传 Excel",
    preview: "分析行内容",
    export: "导出 Excel",
    context: "上下文",
    region: "区域",
    notesLabel: "AI 报价辅助提示",
    notesHint: "请修改下面的提示，指导 AI 进行报价。",
    notesRequired: "请先输入 AI 报价辅助提示，再开始分析。",
    summary: "行汇总",
    progress: "进度",
    file: "文件",
    taskStatus: "状态",
    currentStage: "当前阶段",
    previewFailed: "分析失败",
    taskMissing: "任务不存在，或服务已经重启。",
    idle: "请上传一个 .xlsx 文件开始。",
    ready: "文件已准备好，可开始分析。",
    previewQueued: "任务排队中...",
    previewRunning: "正在分析行内容...",
    exporting: "正在生成标注后的工作簿...",
    success: "标注工作簿已可导出。",
    invalidFile: "行级 Flexible 报价仅支持 .xlsx 文件。",
    summaryWaiting: "分析完成后会显示汇总。",
    totalRows: "总行数",
    quotedRows: "已报价",
    unmatchedRows: "未匹配",
    missingPriceRows: "缺少价格",
    manualRows: "人工确认",
    nonQuoteRows: "非报价行",
    ondemand: "按需",
    monthly: "包月",
    ri: "RI 1Y",
    progressLabelMapRows: "已映射/总计",
    progressLabelPriceRows: "已报价/总计",
    cancel: "取消",
    cancelFailed: "取消任务失败。",
    sheetSelection: "处理工作表",
    sheetFirst: "仅第一个工作表",
    sheetAll: "所有工作表",
    sheetSpecify: "指定工作表",
    sheetSpecifyPlaceholder: "例如 Compute, Storage, 1,3",
    sheetSpecifyEmpty: "请输入工作表名称或索引。",
  },
  pg: {
    title: "Flexible Quote",
    body: "Upload a customer Excel workbook. The result preserves the original workbook and appends Huawei Cloud quote columns to every sheet.",
    upload: "Upload Excel",
    preview: "Analyze rows",
    export: "Export Excel",
    context: "Context",
    region: "Region",
    notesLabel: "AI Quote Guidance",
    notesHint: "Edit the prompt below to guide the AI quote.",
    notesRequired: "Please enter AI quote guidance before starting the analysis.",
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
    cancel: "Cancel",
    cancelFailed: "Failed to cancel the task.",
    sheetSelection: "Sheets to process",
    sheetFirst: "First sheet only",
    sheetAll: "All sheets",
    sheetSpecify: "Specify sheets",
    sheetSpecifyPlaceholder: "e.g. Compute, Storage, 1,3",
    sheetSpecifyEmpty: "Enter sheet names or indexes.",
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
  if (state === "ready") return t.ready;
  if (state === "queued") return t.previewQueued;
  if (state === "running") return t.previewRunning;
  if (state === "succeeded") return t.success;
  if (state === "failed") return t.previewFailed;
  return t.idle;
}

function stageLabel(stage?: string | null) {
  if (!stage) return "-";
  if (stage === "queued") return "Queued";
  if (stage === "collect_rows") return "Collect Rows";
  if (stage === "pipeline_rows") return "Pipeline";
  if (stage === "map_rows") return "Map Rows";
  if (stage === "price_rows") return "Price Rows";
  if (stage === "annotate_workbook") return "Annotate Workbook";
  if (stage === "completed") return "Completed";
  return stage;
}

export function FlexibleQuoteEstimator({ lang }: { lang: Lang }) {
  const t = uiCopy[lang] ?? uiCopy.en;
  const [file, setFile] = useState<File | null>(null);
  const [quoteContext, setQuoteContext] = useState({
    region: "mexico" as PricingRegionKey,
    language: lang,
    customer_notes: defaultNotes[lang] ?? defaultNotes.en,
  });
  const [notesIsCustom, setNotesIsCustom] = useState(false);
  const [previewState, setPreviewState] = useState<PreviewViewState>("idle");
  const [taskId, setTaskId] = useState("");
  const [task, setTask] = useState<RowQuoteTaskResponse | null>(null);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [sheetMode, setSheetMode] = useState<SheetSelectionMode>("first");
  const [sheetInput, setSheetInput] = useState("");
  const pollTokenRef = useRef(0);

  useEffect(() => {
    setQuoteContext((current) => {
      const newLang = lang;
      if (!notesIsCustom) {
        return { ...current, language: newLang, customer_notes: defaultNotes[newLang] ?? defaultNotes.en };
      }
      return { ...current, language: newLang };
    });
  }, [lang, notesIsCustom]);

  useEffect(() => {
    return () => { pollTokenRef.current += 1; };
  }, []);

  const progressBusy = previewState === "queued" || previewState === "running";
  const canExport = Boolean(taskId && previewState === "succeeded" && !exporting);
  const notesEmpty = quoteContext.customer_notes.trim().length === 0;
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
    if (!selected) return;
    if (!/\.xlsx$/i.test(selected.name)) {
      setError(t.invalidFile);
      setPreviewState("failed");
      return;
    }
    trackClick({ click_target: "flexible_row_quote_upload", click_section: "estimator", destination: "flexible_annotate_api" });
    setFile(selected);
    resetTracking("ready");
  }

  async function pollTask(nextTaskId: string, token: number) {
    try {
      const response = await fetch(`${QUOTE_API_BASE_URL}/api/quotes/flexible/annotate/tasks/${nextTaskId}`);
      if (token !== pollTokenRef.current) return;
      if (response.status === 404) { setPreviewState("failed"); setError(t.taskMissing); return; }
      if (!response.ok) throw new Error(await getErrorDetail(response, t.previewFailed));
      const payload = (await response.json()) as RowQuoteTaskResponse;
      setTask(payload);
      if (payload.status === "queued" || payload.status === "running") {
        setPreviewState(payload.status);
        window.setTimeout(() => { if (token === pollTokenRef.current) void pollTask(nextTaskId, token); }, 1000);
        return;
      }
      if (payload.status === "failed") { setPreviewState("failed"); setError(payload.error?.detail || payload.error?.message || t.previewFailed); return; }
      if (payload.status === "cancelled") { pollTokenRef.current += 1; setTask(null); setTaskId(""); setError(""); setPreviewState(file ? "ready" : "idle"); return; }
      setPreviewState("succeeded");
      setError("");
    } catch (err) {
      if (token !== pollTokenRef.current) return;
      setPreviewState("failed");
      setError(err instanceof Error ? err.message : t.previewFailed);
    }
  }

  async function runPreview() {
    if (!file) return;
    if (notesEmpty) { setError(t.notesRequired); return; }
    if (sheetMode === "selected" && !sheetInput.trim()) { setError(t.sheetSpecifyEmpty); return; }
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
      formData.append("sheet_selection_mode", sheetMode);
      if (sheetMode === "selected") {
        formData.append("sheet_selection_input", sheetInput);
      }
      const response = await fetch(`${QUOTE_API_BASE_URL}/api/quotes/flexible/annotate/tasks`, { method: "POST", body: formData });
      if (!response.ok) throw new Error(await getErrorDetail(response, t.previewFailed));
      const payload = (await response.json()) as { task_id: string; status: "queued" | "running" };
      if (token !== pollTokenRef.current) return;
      setTaskId(payload.task_id);
      setPreviewState(payload.status);
      void pollTask(payload.task_id, token);
    } catch (err) {
      if (token !== pollTokenRef.current) return;
      setPreviewState("failed");
      setError(err instanceof Error ? err.message : t.previewFailed);
    }
  }

  async function runExport() {
    if (!taskId) return;
    setExporting(true);
    setError("");
    try {
      const response = await fetch(`${QUOTE_API_BASE_URL}/api/quotes/flexible/annotate/tasks/${taskId}/export`);
      if (!response.ok) throw new Error(await getErrorDetail(response, t.exporting));
      triggerDownload(await response.blob(), getDownloadFilename(response.headers.get("content-disposition")));
    } catch (err) { setError(err instanceof Error ? err.message : t.exporting); }
    finally { setExporting(false); }
  }

  async function runCancel() {
    if (!taskId) return;
    setCancelling(true);
    try {
      const response = await fetch(`${QUOTE_API_BASE_URL}/api/quotes/flexible/annotate/tasks/${taskId}/cancel`, { method: "POST" });
      if (!response.ok) throw new Error(await getErrorDetail(response, t.cancelFailed));
      pollTokenRef.current += 1;
      setTask(null);
      setTaskId("");
      setError("");
      setPreviewState(file ? "ready" : "idle");
    } catch (err) { setError(err instanceof Error ? err.message : t.cancelFailed); }
    finally { setCancelling(false); }
  }

  const currentStage = task?.current_stage || (progressBusy ? "collect_rows" : null);
  const prog = task?.progress;

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
          <button type="button" className="upload-button secondary" onClick={runPreview} disabled={!file || progressBusy || exporting || notesEmpty}>
            <Calculator size={18} />
            {t.preview}
          </button>
          <button type="button" className="upload-button secondary" onClick={runExport} disabled={!canExport}>
            <Download size={18} />
            {t.export}
          </button>
          {progressBusy && (
            <button type="button" className="upload-button secondary" onClick={runCancel} disabled={cancelling}>
              {t.cancel}
            </button>
          )}
        </div>
      </div>

      <div className="pricing-controls">
        <div>
          <strong>{t.context}</strong>
          <div className="region-card-grid">
            {regionOrder.map((key) => {
              const selected = quoteContext.region === key;
              return (
                <button
                  type="button"
                  key={key}
                  className={`region-card${selected ? " selected" : ""}`}
                  disabled={progressBusy}
                  onClick={() => setQuoteContext((current) => ({ ...current, region: key }))}
                >
                  <span className="region-card-country">{pricingCatalog[key].country}</span>
                  <span className="region-card-name">{regionNames[key]}</span>
                </button>
              );
            })}
          </div>
          <div className="ai-guidance-field">
            <label>
              <span>{t.notesLabel}</span>
            </label>
            <p className="ai-guidance-hint">{t.notesHint}</p>
            <textarea
              rows={4}
              value={quoteContext.customer_notes}
              onChange={(event) => {
                const value = event.target.value;
                setQuoteContext((current) => ({ ...current, customer_notes: value }));
                setNotesIsCustom(value.trim() !== (defaultNotes[lang] ?? defaultNotes.en).trim());
              }}
              disabled={progressBusy}
            />
            {notesEmpty && <p className="form-error">{t.notesRequired}</p>}
          </div>
          <div>
            <strong>{t.sheetSelection}</strong>
            <div className="segmented-control compact">
              <button type="button" className={sheetMode === "first" ? "active" : ""} onClick={() => setSheetMode("first")} disabled={progressBusy}>{t.sheetFirst}</button>
              <button type="button" className={sheetMode === "all" ? "active" : ""} onClick={() => setSheetMode("all")} disabled={progressBusy}>{t.sheetAll}</button>
              <button type="button" className={sheetMode === "selected" ? "active" : ""} onClick={() => setSheetMode("selected")} disabled={progressBusy}>{t.sheetSpecify}</button>
            </div>
            {sheetMode === "selected" && (
              <input
                type="text"
                className="sheet-selection-input"
                placeholder={t.sheetSpecifyPlaceholder}
                value={sheetInput}
                onChange={(e) => setSheetInput(e.target.value)}
                disabled={progressBusy}
              />
            )}
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
          </div>
          {prog ? (
            <div className="dual-progress-bars">
              <div className="dual-progress-row">
                <small>{t.progressLabelMapRows}</small>
                <span>{prog.total_rows > 0 ? `${prog.mapped_rows}/${prog.total_rows}` : "0/—"}</span>
              </div>
              <div className="row-quote-progress-bar-wrap">
                <div className="row-quote-progress-bar">
                  <div className="row-quote-progress-fill" style={{ width: prog.total_rows > 0 ? `${Math.round((prog.mapped_rows / prog.total_rows) * 100)}%` : "0%" }} />
                </div>
                <span className="row-quote-progress-label">
                  {prog.total_rows > 0 ? `${prog.mapped_rows}/${prog.total_rows} (${Math.round((prog.mapped_rows / prog.total_rows) * 100)}%)` : "0/—"}
                </span>
              </div>
              <div className="dual-progress-row">
                <small>{t.progressLabelPriceRows}</small>
                <span>{prog.total_rows > 0 ? `${prog.priced_rows}/${prog.total_rows}` : "0/—"}</span>
              </div>
              <div className="row-quote-progress-bar-wrap">
                <div className="row-quote-progress-bar">
                  <div className="row-quote-progress-fill" style={{ width: prog.total_rows > 0 ? `${Math.round((prog.priced_rows / prog.total_rows) * 100)}%` : "0%" }} />
                </div>
                <span className="row-quote-progress-label">
                  {prog.total_rows > 0 ? `${prog.priced_rows}/${prog.total_rows} (${Math.round((prog.priced_rows / prog.total_rows) * 100)}%)` : "0/—"}
                </span>
              </div>
            </div>
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
