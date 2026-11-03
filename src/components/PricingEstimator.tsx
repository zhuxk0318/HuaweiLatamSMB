import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { Calculator, Database, Download, FileSpreadsheet, Server, UploadCloud } from "lucide-react";
import { trackClick } from "../analytics";
import {
  pricingCatalog,
  pricingMetadata,
  type EvsTypeKey,
  type PricingRegionKey,
} from "../data/pricingCatalog";
import type { Lang } from "../data/i18n";

const QUOTE_API_BASE_URL = (import.meta.env.VITE_QUOTE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ??
  "/quote-api";

const regionOrder: PricingRegionKey[] = ["mexico", "chile", "brazil"];

type QuoteLine = {
  action: "quote" | "manual_review" | "exclude_powered_off";
  review_reason: string | null;
  vm_name: string;
  power_state: string;
  os: string;
  vcpu: number;
  memory_gib: number;
  disk_gib: number;
  region: PricingRegionKey;
  evs_type: EvsTypeKey;
  ecs_family_label: string | null;
  ecs_spec: string | null;
  ecs_ondemand_monthly_usd: number;
  ecs_ri_1y_monthly_usd: number;
  evs_monthly_usd: number;
  total_ondemand_monthly_usd: number;
  total_ri_1y_monthly_usd: number;
};

type QuoteSummary = {
  total_vms: number;
  excluded_vms: number;
  manual_review_vms: number;
  quoted_vms: number;
  total_disk_gib: number;
  total_ondemand_monthly_usd: number;
  total_ri_1y_monthly_usd: number;
  summary: string;
  assumptions: string[];
  risks: string[];
};

type QuotePreviewResponse = {
  source_filename: string;
  region: PricingRegionKey;
  evs_type: EvsTypeKey;
  lang: Lang;
  summary: QuoteSummary;
  quote_lines: QuoteLine[];
  manual_review_lines: QuoteLine[];
  excluded_lines: QuoteLine[];
  task_id: string | null;
};

const uiCopy = {
  es: {
    kicker: "Cotizador cloud",
    title: "Cotización Cloud para Infraestructura",
    body:
      "Cargue exportaciones de RVTools o inventarios de máquinas virtuales con información de CPU, memoria, almacenamiento y sistema operativo. Seleccione una región y el backend calcula primero la vista previa completa y después puede exportar el Excel oficial con el mismo motor de precios.",
    upload: "Cargar RVTools .xlsx",
    export: "Exportar cotización Excel",
    region: "Region",
    evs: "EVS para discos",
    priceSource: "Precios cacheados",
    estimate: "Vista previa oficial",
    noFile: "Aun no se ha cargado un archivo de inventario.",
    fileReady: "Archivo listo para vista previa",
    previewing: "Generando vista previa de cotización...",
    previewSuccess: "Vista previa lista. Revise el resultado antes de exportar.",
    exporting: "Generando Excel oficial...",
    exportSuccess: "Excel descargado.",
    official: "La vista previa y el Excel usan la misma lógica de precios del backend.",
    invalidFile: "V1 solo admite inventarios RVTools .xlsx.",
    previewErrorFallback: "No se pudo generar la vista previa.",
    downloadError: "No se pudo exportar la cotización.",
    selectedFile: "Archivo cargado",
    lastDownload: "Ultimo archivo",
    summaryText: "Resumen ejecutivo",
    assumptions: "Supuestos",
    risks: "Riesgos",
    totalVms: "VM totales",
    quotedVms: "VM cotizadas",
    manualReviewVms: "Revision manual",
    excludedVms: "Excluidas",
    totalDisk: "Disco total GiB",
    ondemand: "Mensual on-demand",
    ri: "Mensual RI",
    quotedTable: "VM cotizadas",
    manualTable: "Revision manual",
    excludedTable: "Excluidas",
    emptyPreview: "Cargue un inventario RVTools .xlsx para ver la cotizacion antes de exportarla.",
    ecsTable: "ECS pricing",
    evsTable: "EVS",
    sheetSelection: "Hojas a procesar",
    sheetFirst: "Solo la primera hoja",
    sheetAll: "Todas las hojas",
    sheetSpecify: "Especificar hojas",
    sheetSpecifyPlaceholder: "p.ej. vInfo, Compute, 1,3",
    sheetSpecifyEmpty: "Ingrese los nombres o índices de hoja.",
  },
  en: {
    kicker: "Cloud quote exporter",
    title: "Infrastructure Cloud Quote",
    body:
      "Upload RVTools exports or VM inventory files with CPU, memory, storage, and operating system details. Choose a region and the backend renders a full quote preview, then exports the official Excel with the same pricing logic.",
    upload: "Upload RVTools .xlsx",
    export: "Export quote Excel",
    region: "Region",
    evs: "EVS for disks",
    priceSource: "Cached pricing",
    estimate: "Official preview",
    noFile: "No inventory file has been uploaded yet.",
    fileReady: "File ready for preview",
    previewing: "Generating quote preview...",
    previewSuccess: "Preview ready. Review the result before exporting.",
    exporting: "Generating official quote workbook...",
    exportSuccess: "Excel downloaded.",
    official: "The preview and Excel export use the same backend pricing logic.",
    invalidFile: "V1 only supports RVTools .xlsx inventory files.",
    previewErrorFallback: "Unable to generate the quote preview.",
    downloadError: "Unable to export the quote workbook.",
    selectedFile: "Uploaded file",
    lastDownload: "Last file",
    summaryText: "Executive summary",
    assumptions: "Assumptions",
    risks: "Risks",
    totalVms: "Total VMs",
    quotedVms: "Quoted VMs",
    manualReviewVms: "Manual review",
    excludedVms: "Excluded",
    totalDisk: "Total disk GiB",
    ondemand: "On-demand monthly",
    ri: "RI monthly",
    quotedTable: "Quoted VMs",
    manualTable: "Manual review",
    excludedTable: "Excluded",
    emptyPreview: "Upload an RVTools .xlsx inventory to review the quote before exporting.",
    ecsTable: "ECS pricing",
    evsTable: "EVS",
    sheetSelection: "Sheets to process",
    sheetFirst: "First sheet only",
    sheetAll: "All sheets",
    sheetSpecify: "Specify sheets",
    sheetSpecifyPlaceholder: "e.g. vInfo, Compute, 1,3",
    sheetSpecifyEmpty: "Enter sheet names or indexes.",
  },
  zh: {
    kicker: "云报价导出",
    title: "基础架构云报价",
    body:
      "上传 RVTools 导出文件或包含 CPU、内存、存储和操作系统信息的虚拟机清单。选择区域，后端会先生成完整预览，再用同一套价格逻辑导出正式 Excel。",
    upload: "上传 RVTools .xlsx",
    export: "导出报价 Excel",
    region: "区域",
    evs: "磁盘 EVS 类型",
    priceSource: "本地缓存价格",
    estimate: "官方预览",
    noFile: "尚未上传清单文件。",
    fileReady: "文件已准备好，可生成预览",
    previewing: "正在生成报价预览...",
    previewSuccess: "预览已生成，请确认后再导出。",
    exporting: "正在生成正式报价工作簿...",
    exportSuccess: "Excel 已下载。",
    official: "预览与 Excel 导出使用同一套后端价格逻辑。",
    invalidFile: "V1 仅支持 RVTools .xlsx 清单文件。",
    previewErrorFallback: "无法生成报价预览。",
    downloadError: "无法导出报价工作簿。",
    selectedFile: "已上传文件",
    lastDownload: "最近导出",
    summaryText: "执行摘要",
    assumptions: "假设",
    risks: "风险",
    totalVms: "总 VM 数",
    quotedVms: "已报价 VM",
    manualReviewVms: "人工审核",
    excludedVms: "已排除",
    totalDisk: "总磁盘 GiB",
    ondemand: "按需月价",
    ri: "RI 月价",
    quotedTable: "已报价 VM",
    manualTable: "人工审核",
    excludedTable: "已排除",
    emptyPreview: "上传 RVTools .xlsx 清单后，可先查看报价预览再导出。",
    ecsTable: "ECS 价格",
    evsTable: "EVS",
    sheetSelection: "处理工作表",
    sheetFirst: "仅第一个工作表",
    sheetAll: "所有工作表",
    sheetSpecify: "指定工作表",
    sheetSpecifyPlaceholder: "例如 vInfo, Compute, 1,3",
    sheetSpecifyEmpty: "请输入工作表名称或索引。",
  },
  pg: {
    kicker: "Cloud quote exporter",
    title: "RVTools cloud quote preview",
    body:
      "Choose a region and upload an RVTools .xlsx. The backend first renders a full quote preview, then exports the official Excel with the same pricing logic.",
    upload: "Upload RVTools .xlsx",
    export: "Export quote Excel",
    region: "Region",
    evs: "EVS for disks",
    priceSource: "Cached pricing",
    estimate: "Official preview",
    noFile: "No RVTools file has been uploaded yet.",
    fileReady: "File ready for preview",
    previewing: "Generating quote preview...",
    previewSuccess: "Preview ready. Review the result before exporting.",
    exporting: "Generating official quote workbook...",
    exportSuccess: "Excel downloaded.",
    official: "The preview and Excel export use the same backend pricing logic.",
    invalidFile: "V1 only supports RVTools .xlsx files.",
    previewErrorFallback: "Unable to generate the quote preview.",
    downloadError: "Unable to export the quote workbook.",
    selectedFile: "Uploaded file",
    lastDownload: "Last file",
    summaryText: "Executive summary",
    assumptions: "Assumptions",
    risks: "Risks",
    totalVms: "Total VMs",
    quotedVms: "Quoted VMs",
    manualReviewVms: "Manual review",
    excludedVms: "Excluded",
    totalDisk: "Total disk GiB",
    ondemand: "On-demand monthly",
    ri: "RI monthly",
    quotedTable: "Quoted VMs",
    manualTable: "Manual review",
    excludedTable: "Excluded",
    emptyPreview: "Upload an RVTools .xlsx to review the quote before exporting.",
    ecsTable: "ECS pricing",
    evsTable: "EVS",
    sheetSelection: "Sheets to process",
    sheetFirst: "First sheet only",
    sheetAll: "All sheets",
    sheetSpecify: "Specify sheets",
    sheetSpecifyPlaceholder: "e.g. vInfo, Compute, 1,3",
    sheetSpecifyEmpty: "Enter sheet names or indexes.",
  },
} satisfies Record<Lang, Record<string, string>>;

function money(value?: number | null, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return `$${value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

function number(value?: number | null, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function price(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return `$${value.toLocaleString("en-US", {
    minimumFractionDigits: 6,
    maximumFractionDigits: 8,
  })}`;
}

function getDownloadFilename(header: string | null, fallbackRegion: PricingRegionKey) {
  const matched = header?.match(/filename="?([^"]+)"?/i)?.[1]?.trim();
  if (matched) {
    return matched;
  }
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  return `quote-${fallbackRegion}-${stamp}.xlsx`;
}

function triggerDownload(blob: Blob, filename: string) {
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(objectUrl);
}

async function getErrorDetail(response: Response, fallback: string) {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const payload = await response.json().catch(() => null);
    return payload?.detail || fallback;
  }

  const text = (await response.text().catch(() => "")).trim();
  if (text) {
    return text.length > 600 ? `${text.slice(0, 600)}...` : text;
  }
  return fallback;
}

type SheetSelectionMode = "first" | "all" | "selected";

export function PricingEstimator({ lang }: { lang: Lang }) {
  const t = uiCopy[lang];
  const [regionKey, setRegionKey] = useState<PricingRegionKey>("mexico");
  const [evsKey, setEvsKey] = useState<EvsTypeKey>("gpssd");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [previewResult, setPreviewResult] = useState<QuotePreviewResponse | null>(null);
  const [status, setStatus] = useState(t.noFile);
  const [previewError, setPreviewError] = useState("");
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [lastDownload, setLastDownload] = useState("");
  const [sheetMode, setSheetMode] = useState<SheetSelectionMode>("first");
  const [sheetInput, setSheetInput] = useState("");
  const region = pricingCatalog[regionKey];
  const familyCounts = useMemo(
    () =>
      region.ecs.reduce<Record<string, number>>((acc, item) => {
        acc[item.familyLabel] = (acc[item.familyLabel] ?? 0) + 1;
        return acc;
      }, {}),
    [region.ecs],
  );

  useEffect(() => {
    if (!selectedFiles.length) {
      setPreviewResult(null);
      setPreviewError("");
      setStatus(t.noFile);
      return;
    }

    const files = selectedFiles;
    const controller = new AbortController();
    let cancelled = false;

    async function runPreview() {
      setIsPreviewing(true);
      setPreviewError("");
      setPreviewResult(null);
      setStatus(t.previewing);

      if (sheetMode === "selected" && !sheetInput.trim()) {
        setIsPreviewing(false);
        setPreviewError(t.sheetSpecifyEmpty);
        setStatus(t.fileReady);
        return;
      }

      try {
        const formData = new FormData();
        for (const file of files) {
          formData.append("files", file);
        }
        formData.append("region", regionKey);
        formData.append("evs_type", evsKey);
        formData.append("lang", lang);
        formData.append("sheet_selection_mode", sheetMode);
        if (sheetMode === "selected") {
          formData.append("sheet_selection_input", sheetInput);
        }

        const endpoint = files.length === 1
          ? `${QUOTE_API_BASE_URL}/api/quotes/preview`
          : `${QUOTE_API_BASE_URL}/api/quotes/multi/preview`;

        // For single file, use the legacy endpoint with "rvtools_file" field name
        if (files.length === 1) {
          const singleFormData = new FormData();
          singleFormData.append("rvtools_file", files[0]);
          singleFormData.append("region", regionKey);
          singleFormData.append("evs_type", evsKey);
          singleFormData.append("lang", lang);
          singleFormData.append("sheet_selection_mode", sheetMode);
          if (sheetMode === "selected") {
            singleFormData.append("sheet_selection_input", sheetInput);
          }

          const response = await fetch(`${QUOTE_API_BASE_URL}/api/quotes/preview`, {
            method: "POST",
            body: singleFormData,
            signal: controller.signal,
          });

          if (!response.ok) {
            throw new Error(await getErrorDetail(response, t.previewErrorFallback));
          }

          const payload = (await response.json()) as QuotePreviewResponse;
          if (cancelled) {
            return;
          }
          setPreviewResult(payload);
          setStatus(t.previewSuccess);
        } else {
          const response = await fetch(endpoint, {
            method: "POST",
            body: formData,
            signal: controller.signal,
          });

          if (!response.ok) {
            throw new Error(await getErrorDetail(response, t.previewErrorFallback));
          }

          const payload = (await response.json()) as QuotePreviewResponse;
          if (cancelled) {
            return;
          }
          setPreviewResult(payload);
          setStatus(t.previewSuccess);
        }
      } catch (err) {
        if (controller.signal.aborted || cancelled) {
          return;
        }
        setPreviewResult(null);
        setStatus(t.fileReady);
        setPreviewError(err instanceof Error ? err.message : t.previewErrorFallback);
      } finally {
        if (!cancelled) {
          setIsPreviewing(false);
        }
      }
    }

    void runPreview();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [
    selectedFiles,
    regionKey,
    evsKey,
    lang,
    sheetMode,
    sheetInput,
    t.noFile,
    t.previewErrorFallback,
    t.previewSuccess,
    t.previewing,
    t.fileReady,
    t.sheetSpecifyEmpty,
  ]);

  async function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) {
      return;
    }
    event.target.value = "";

    const validFiles: File[] = [];
    for (const file of files) {
      if (!file.name.toLowerCase().endsWith(".xlsx")) {
        setSelectedFiles([]);
        setPreviewResult(null);
        setLastDownload("");
        setStatus(t.noFile);
        setPreviewError(t.invalidFile);
        return;
      }
      validFiles.push(file);
    }

    trackClick({
      click_target: "estimator_upload_rvtools",
      click_section: "estimator",
      destination: "quote_preview_api",
      region_key: regionKey,
      evs_key: evsKey,
    });

    setSelectedFiles(validFiles);
    setLastDownload("");
    setStatus(t.fileReady);
    setPreviewError("");
  }

  async function onExportClick() {
    if (!previewResult) {
      return;
    }

    trackClick({
      click_target: "estimator_export_quote",
      click_section: "estimator",
      destination: "quote_export_api",
      region_key: regionKey,
      evs_key: evsKey,
    });

    setIsExporting(true);
    setPreviewError("");
    setStatus(t.exporting);

    try {
      let response: Response;

      if (previewResult.task_id) {
        response = await fetch(`${QUOTE_API_BASE_URL}/api/quotes/tasks/${previewResult.task_id}/export`);
      } else {
        const formData = new FormData();
        for (const file of selectedFiles) {
          formData.append("files", file);
        }
        formData.append("region", regionKey);
        formData.append("evs_type", evsKey);
        formData.append("lang", lang);
        formData.append("sheet_selection_mode", sheetMode);
        if (sheetMode === "selected") {
          formData.append("sheet_selection_input", sheetInput);
        }
        const exportEndpoint = selectedFiles.length === 1
          ? `${QUOTE_API_BASE_URL}/api/quotes/export`
          : `${QUOTE_API_BASE_URL}/api/quotes/multi/export`;
        // For single file fallback, use legacy field name
        if (selectedFiles.length === 1) {
          const singleFormData = new FormData();
          singleFormData.append("rvtools_file", selectedFiles[0]);
          singleFormData.append("region", regionKey);
          singleFormData.append("evs_type", evsKey);
          singleFormData.append("lang", lang);
          singleFormData.append("sheet_selection_mode", sheetMode);
          if (sheetMode === "selected") {
            singleFormData.append("sheet_selection_input", sheetInput);
          }
          response = await fetch(`${QUOTE_API_BASE_URL}/api/quotes/export`, {
            method: "POST",
            body: singleFormData,
          });
        } else {
          response = await fetch(exportEndpoint, {
            method: "POST",
            body: formData,
          });
        }
      }

      if (!response.ok) {
        throw new Error(await getErrorDetail(response, t.downloadError));
      }

      const blob = await response.blob();
      const filename = getDownloadFilename(response.headers.get("content-disposition"), regionKey);
      triggerDownload(blob, filename);
      setLastDownload(filename);
      setStatus(t.exportSuccess);
    } catch (err) {
      setStatus(previewResult ? t.previewSuccess : t.fileReady);
      setPreviewError(err instanceof Error ? err.message : t.downloadError);
    } finally {
      setIsExporting(false);
    }
  }

  const canExport = Boolean(previewResult && !isPreviewing && !isExporting);

  return (
    <section id="quote" className="pricing-section">
      <div className="section-heading split-heading">
        <div>
          <span className="section-kicker">{t.kicker}</span>
          <h2>{t.title}</h2>
          <p>{t.body}</p>
        </div>
        <div className="quote-actions">
          <label className="upload-button">
            <UploadCloud size={18} />
            {t.upload}
            <input type="file" accept=".xlsx" multiple onChange={onFileChange} disabled={isPreviewing || isExporting} />
          </label>
          <button type="button" className="upload-button secondary" onClick={onExportClick} disabled={!canExport}>
            <Download size={18} />
            {t.export}
          </button>
        </div>
      </div>

      <div className="pricing-controls">
        <div>
          <strong>{t.region}</strong>
          <div className="segmented-control">
            {regionOrder.map((key) => (
              <button
                key={key}
                type="button"
                className={regionKey === key ? "active" : ""}
                onClick={() => {
                  if (regionKey !== key) {
                    trackClick({
                      click_target: "estimator_region_change",
                      click_section: "estimator",
                      destination: key,
                      region_key: key,
                      evs_key: evsKey,
                    });
                  }
                  setRegionKey(key);
                }}
              >
                {pricingCatalog[key].country}
                <span>{pricingCatalog[key].huaweiRegionName}</span>
              </button>
            ))}
          </div>
        </div>
        <div>
          <strong>{t.evs}</strong>
          <div className="segmented-control compact">
            {region.evs.map((item) => (
              <button
                key={item.key}
                type="button"
                className={evsKey === item.key ? "active" : ""}
                onClick={() => {
                  if (evsKey !== item.key) {
                    trackClick({
                      click_target: "estimator_evs_change",
                      click_section: "estimator",
                      destination: item.key,
                      region_key: regionKey,
                      evs_key: item.key,
                    });
                  }
                  setEvsKey(item.key);
                }}
              >
                {item.label}
                <span>{price(item.hourlyUsdPerGb)}/GBh</span>
              </button>
            ))}
          </div>
        </div>
        <div>
          <strong>{t.sheetSelection}</strong>
          <div className="segmented-control compact">
            <button type="button" className={sheetMode === "first" ? "active" : ""} onClick={() => setSheetMode("first")}>{t.sheetFirst}</button>
            <button type="button" className={sheetMode === "all" ? "active" : ""} onClick={() => setSheetMode("all")}>{t.sheetAll}</button>
            <button type="button" className={sheetMode === "selected" ? "active" : ""} onClick={() => setSheetMode("selected")}>{t.sheetSpecify}</button>
          </div>
          {sheetMode === "selected" && (
            <input
              type="text"
              className="sheet-selection-input"
              placeholder={t.sheetSpecifyPlaceholder}
              value={sheetInput}
              onChange={(e) => setSheetInput(e.target.value)}
              disabled={isPreviewing || isExporting}
            />
          )}
        </div>
      </div>

      <div className="pricing-dashboard">
        <article className="quote-panel">
          <div className="panel-title">
            <Calculator size={20} />
            <h3>{t.estimate}</h3>
          </div>
          {previewError ? <p className="form-error">{previewError}</p> : null}
          <div className="quote-metrics quote-metrics-extended">
            <span>
              <small>{t.selectedFile}</small>
              <strong>{selectedFiles.length === 0 ? "-" : selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} files: ${selectedFiles.map(f => f.name).join(", ")}`}</strong>
            </span>
            <span>
              <small>{t.lastDownload}</small>
              <strong>{lastDownload || "-"}</strong>
            </span>
          </div>
          <p className="empty-state">
            {isPreviewing || isExporting ? <Download size={20} /> : <FileSpreadsheet size={20} />}
            {status}
          </p>
          <p className="source-note">{t.official}</p>
        </article>

        <article className="quote-panel">
          <div className="panel-title">
            <Server size={20} />
            <h3>{t.priceSource}</h3>
          </div>
          <div className="source-facts">
            <span>{region.huaweiRegionName}</span>
            <span>{region.regionCode}</span>
            <span>{pricingMetadata.fetchedAt}</span>
          </div>
          <p className="source-note">
            {pricingMetadata.ecsPricingScope}
          </p>
          <div className="family-summary">
            {Object.entries(familyCounts).map(([family, count]) => (
              <span key={family}>
                {family}
                <strong>{count}</strong>
              </span>
            ))}
          </div>
        </article>
      </div>

      {previewResult ? (
        <div className="pricing-tables preview-results">
          <article className="quote-panel">
            <div className="panel-title">
              <FileSpreadsheet size={20} />
              <h3>{t.summaryText}</h3>
            </div>
            <div className="quote-summary-grid">
              <span>
                <small>{t.totalVms}</small>
                <strong>{number(previewResult.summary.total_vms)}</strong>
              </span>
              <span>
                <small>{t.quotedVms}</small>
                <strong>{number(previewResult.summary.quoted_vms)}</strong>
              </span>
              <span>
                <small>{t.manualReviewVms}</small>
                <strong>{number(previewResult.summary.manual_review_vms)}</strong>
              </span>
              <span>
                <small>{t.excludedVms}</small>
                <strong>{number(previewResult.summary.excluded_vms)}</strong>
              </span>
              <span>
                <small>{t.totalDisk}</small>
                <strong>{number(previewResult.summary.total_disk_gib, 2)}</strong>
              </span>
              <span>
                <small>{t.ondemand}</small>
                <strong>{money(previewResult.summary.total_ondemand_monthly_usd)}</strong>
              </span>
              <span>
                <small>{t.ri}</small>
                <strong>{money(previewResult.summary.total_ri_1y_monthly_usd)}</strong>
              </span>
            </div>
            <p className="preview-summary-copy">{previewResult.summary.summary}</p>
            <div className="preview-notes">
              <section>
                <strong>{t.assumptions}</strong>
                <ul>
                  {previewResult.summary.assumptions.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
              <section>
                <strong>{t.risks}</strong>
                <ul>
                  {previewResult.summary.risks.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
            </div>
          </article>

          <article className="price-table-card">
            <div className="panel-title">
              <Calculator size={20} />
              <h3>{t.quotedTable}</h3>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>VM</th>
                    <th>OS</th>
                    <th>vCPU</th>
                    <th>Memory GiB</th>
                    <th>Disk GiB</th>
                    <th>ECS Spec</th>
                    <th>Family</th>
                    <th>ECS On-demand</th>
                    <th>ECS RI</th>
                    <th>EVS</th>
                    <th>Total On-demand</th>
                    <th>Total RI</th>
                  </tr>
                </thead>
                <tbody>
                  {previewResult.quote_lines.map((item) => (
                    <tr key={`${item.vm_name}-${item.ecs_spec}`}>
                      <td>{item.vm_name}</td>
                      <td>{item.os || "-"}</td>
                      <td>{item.vcpu}</td>
                      <td>{number(item.memory_gib, 2)}</td>
                      <td>{number(item.disk_gib, 2)}</td>
                      <td>{item.ecs_spec || "-"}</td>
                      <td>{item.ecs_family_label || "-"}</td>
                      <td>{money(item.ecs_ondemand_monthly_usd)}</td>
                      <td>{money(item.ecs_ri_1y_monthly_usd)}</td>
                      <td>{money(item.evs_monthly_usd)}</td>
                      <td>{money(item.total_ondemand_monthly_usd)}</td>
                      <td>{money(item.total_ri_1y_monthly_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          <article className="price-table-card">
            <div className="panel-title">
              <Server size={20} />
              <h3>{t.manualTable}</h3>
            </div>
            <div className="table-wrap compact-table">
              <table>
                <thead>
                  <tr>
                    <th>VM</th>
                    <th>OS</th>
                    <th>vCPU</th>
                    <th>Memory GiB</th>
                    <th>Disk GiB</th>
                    <th>Review reason</th>
                  </tr>
                </thead>
                <tbody>
                  {previewResult.manual_review_lines.map((item) => (
                    <tr key={`${item.vm_name}-${item.review_reason}`}>
                      <td>{item.vm_name}</td>
                      <td>{item.os || "-"}</td>
                      <td>{item.vcpu}</td>
                      <td>{number(item.memory_gib, 2)}</td>
                      <td>{number(item.disk_gib, 2)}</td>
                      <td>{item.review_reason || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          <article className="price-table-card">
            <div className="panel-title">
              <Database size={20} />
              <h3>{t.excludedTable}</h3>
            </div>
            <div className="table-wrap compact-table">
              <table>
                <thead>
                  <tr>
                    <th>VM</th>
                    <th>Power state</th>
                    <th>Review reason</th>
                  </tr>
                </thead>
                <tbody>
                  {previewResult.excluded_lines.map((item) => (
                    <tr key={`${item.vm_name}-${item.power_state}`}>
                      <td>{item.vm_name}</td>
                      <td>{item.power_state || "-"}</td>
                      <td>{item.review_reason || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </div>
      ) : (
        <article className="quote-panel preview-empty-state">
          <p className="empty-state">
            <FileSpreadsheet size={20} />
            {t.emptyPreview}
          </p>
        </article>
      )}

      <div className="pricing-tables">
        <article className="price-table-card">
          <div className="panel-title">
            <Server size={20} />
            <h3>{t.ecsTable}</h3>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Family</th>
                  <th>Image</th>
                  <th>Spec</th>
                  <th>vCPU</th>
                  <th>Memory</th>
                  <th>Hourly</th>
                  <th>RI 1-year monthly</th>
                  <th>Product ID</th>
                </tr>
              </thead>
              <tbody>
                {region.ecs.map((item) => (
                  <tr key={item.resourceSpecCode}>
                    <td>{item.familyLabel}</td>
                    <td>{item.image}</td>
                    <td>{item.spec}</td>
                    <td>{item.vcpu}</td>
                    <td>{item.memoryGiB} GiB</td>
                    <td>{price(item.hourlyUsd)}</td>
                    <td>{money(item.ri1YearMonthlyUsd)}</td>
                    <td>{item.ondemandProductId}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="price-table-card">
          <div className="panel-title">
            <Database size={20} />
            <h3>{t.evsTable}</h3>
          </div>
          <div className="table-wrap evs-table">
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Code</th>
                  <th>Hourly / GB</th>
                  <th>Monthly equivalent / GB</th>
                  <th>Product ID</th>
                </tr>
              </thead>
              <tbody>
                {region.evs.map((item) => (
                  <tr key={item.key}>
                    <td>{item.label}</td>
                    <td>{item.resourceSpecCode}</td>
                    <td>{price(item.hourlyUsdPerGb)}</td>
                    <td>{money(item.monthlyEquivalentUsdPerGb, 4)}</td>
                    <td>{item.ondemandProductId}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="source-note">{pricingMetadata.evsPricingScope}</p>
        </article>
      </div>
    </section>
  );
}
