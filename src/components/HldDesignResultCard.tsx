import { useState } from "react";
import { Download, FileCode, Plus, LoaderCircle } from "lucide-react";

type Lang = "es" | "en" | "zh";

const copy: Record<Lang, {
  preview: string;
  downloadPng: string;
  downloadDrawio: string;
  createAnother: string;
  file: string;
  generated: string;
}> = {
  en: {
    preview: "Architecture Diagram Preview",
    downloadPng: "Download PNG",
    downloadDrawio: "Download .drawio",
    createAnother: "Create another HLD",
    file: "File",
    generated: "Generated",
  },
  es: {
    preview: "Vista previa del diagrama de arquitectura",
    downloadPng: "Descargar PNG",
    downloadDrawio: "Descargar .drawio",
    createAnother: "Crear otro HLD",
    file: "Archivo",
    generated: "Generado",
  },
  zh: {
    preview: "架构图预览",
    downloadPng: "下载 PNG",
    downloadDrawio: "下载 .drawio",
    createAnother: "创建新 HLD",
    file: "文件",
    generated: "生成时间",
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

interface HldDesignResultCardProps {
  designId: string;
  pngUrl: string;
  filename: string;
  generatedAt: string;
  lang: Lang;
  onCreateAnother: () => void;
}

export function HldDesignResultCard({ designId, pngUrl, filename, generatedAt, lang, onCreateAnother }: HldDesignResultCardProps) {
  const t = copy[lang];
  const [downloadingPng, setDownloadingPng] = useState(false);
  const [downloadingDrawio, setDownloadingDrawio] = useState(false);

  async function downloadPng() {
    setDownloadingPng(true);
    try {
      const resp = await fetch(`${API_BASE_URL}/api/hld/designs/${designId}/artifacts/png`);
      if (!resp.ok) throw new Error("Download failed");
      const blob = await resp.blob();
      triggerDownload(blob, `${filename}.png`);
    } finally {
      setDownloadingPng(false);
    }
  }

  async function downloadDrawio() {
    setDownloadingDrawio(true);
    try {
      const resp = await fetch(`${API_BASE_URL}/api/hld/designs/${designId}/artifacts/drawio`);
      if (!resp.ok) throw new Error("Download failed");
      const blob = await resp.blob();
      triggerDownload(blob, `${filename}.drawio`);
    } finally {
      setDownloadingDrawio(false);
    }
  }

  return (
    <div className="hld-result-card">
      <h3>{t.preview}</h3>
      <div className="hld-result-meta">
        <span><strong>{t.file}:</strong> {filename}.drawio / {filename}.png</span>
        {generatedAt ? <span><strong>{t.generated}:</strong> {generatedAt}</span> : null}
      </div>
      <div className="hld-result-preview">
        <img src={pngUrl} alt={t.preview} />
      </div>
      <div className="hld-result-actions">
        <button type="button" className="hld-result-download" onClick={downloadPng} disabled={downloadingPng}>
          {downloadingPng ? <LoaderCircle size={16} className="spin-icon" /> : <Download size={16} />}
          {t.downloadPng}
        </button>
        <button type="button" className="hld-result-download" onClick={downloadDrawio} disabled={downloadingDrawio}>
          {downloadingDrawio ? <LoaderCircle size={16} className="spin-icon" /> : <FileCode size={16} />}
          {t.downloadDrawio}
        </button>
      </div>
      <button type="button" className="hld-result-another" onClick={onCreateAnother}>
        <Plus size={16} />
        {t.createAnother}
      </button>
    </div>
  );
}
