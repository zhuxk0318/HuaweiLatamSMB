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
};

const uiCopy = {
  es: {
    kicker: "Cotizador cloud",
    title: "Vista previa de cotización cloud para RVTools",
    body:
      "Seleccione una región y cargue un RVTools .xlsx. El backend calcula primero la vista previa completa y después puede exportar el Excel oficial con el mismo motor de precios.",
    upload: "Cargar RVTools .xlsx",
    export: "Exportar cotización Excel",
    region: "Region",
    evs: "EVS para discos",
    priceSource: "Precios cacheados",
    estimate: "Vista previa oficial",
    noFile: "Aun no se ha cargado un archivo RVTools.",
    fileReady: "Archivo listo para vista previa",
    previewing: "Generando vista previa de cotización...",
    previewSuccess: "Vista previa lista. Revise el resultado antes de exportar.",
    exporting: "Generando Excel oficial...",
    exportSuccess: "Excel descargado.",
    official: "La vista previa y el Excel usan la misma lógica de precios del backend.",
    invalidFile: "Solo se admite RVTools .xlsx en V1.",
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
    emptyPreview: "Cargue un RVTools .xlsx para ver la cotizacion antes de exportarla.",
    ecsTable: "ECS pricing",
    evsTable: "EVS",
  },
  en: {
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
  const payload = await response.json().catch(() => null);
  return payload?.detail || fallback;
}

export function PricingEstimator({ lang }: { lang: Lang }) {
  const t = uiCopy[lang];
  const [regionKey, setRegionKey] = useState<PricingRegionKey>("mexico");
  const [evsKey, setEvsKey] = useState<EvsTypeKey>("gpssd");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewResult, setPreviewResult] = useState<QuotePreviewResponse | null>(null);
  const [status, setStatus] = useState(t.noFile);
  const [previewError, setPreviewError] = useState("");
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [lastDownload, setLastDownload] = useState("");
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
    if (!selectedFile) {
      setPreviewResult(null);
      setPreviewError("");
      setStatus(t.noFile);
      return;
    }

    const file = selectedFile;
    const controller = new AbortController();
    let cancelled = false;

    async function runPreview() {
      setIsPreviewing(true);
      setPreviewError("");
      setPreviewResult(null);
      setStatus(t.previewing);

      try {
        const formData = new FormData();
        formData.append("rvtools_file", file);
        formData.append("region", regionKey);
        formData.append("evs_type", evsKey);
        formData.append("lang", lang);

        const response = await fetch(`${QUOTE_API_BASE_URL}/api/quotes/preview`, {
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
  }, [selectedFile, regionKey, evsKey, lang, t.noFile, t.previewErrorFallback, t.previewSuccess, t.previewing, t.fileReady]);

  async function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    event.target.value = "";

    if (!file.name.toLowerCase().endsWith(".xlsx")) {
      setSelectedFile(null);
      setPreviewResult(null);
      setLastDownload("");
      setStatus(t.noFile);
      setPreviewError(t.invalidFile);
      return;
    }

    trackClick({
      click_target: "estimator_upload_rvtools",
      click_section: "estimator",
      destination: "quote_preview_api",
      region_key: regionKey,
      evs_key: evsKey,
    });

    setSelectedFile(file);
    setLastDownload("");
    setStatus(t.fileReady);
    setPreviewError("");
  }

  async function onExportClick() {
    if (!selectedFile || !previewResult) {
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
      const formData = new FormData();
      formData.append("rvtools_file", selectedFile);
      formData.append("region", regionKey);
      formData.append("evs_type", evsKey);
      formData.append("lang", lang);

      const response = await fetch(`${QUOTE_API_BASE_URL}/api/quotes/export`, {
        method: "POST",
        body: formData,
      });

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

  const canExport = Boolean(selectedFile && previewResult && !isPreviewing && !isExporting);

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
            <input type="file" accept=".xlsx" onChange={onFileChange} disabled={isPreviewing || isExporting} />
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
              <strong>{selectedFile?.name || "-"}</strong>
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
