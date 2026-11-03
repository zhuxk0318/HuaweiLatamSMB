import { useMemo, useState } from "react";
import { ArrowRight, Download, Github, Search, Shield, Terminal, Wrench, Zap } from "lucide-react";
import { trackClick } from "../analytics";
import type { Lang } from "../data/i18n";
import {
  mcpServerVersion,
  mcpProtocolVersion,
  mcpTotalTools,
  mcpStructuredTools,
  mcpServicesCovered,
  mcpDownloadUrl,
  mcpDownloadSize,
  mcpGitHubRepo,
  mcpServices,
  mcpCategoryOrder,
  mcpTools,
  mcpInstallSnippets,
  mcpInstallSteps,
  mcpExamples,
  type McpServiceCategory,
} from "../data/mcpServer";

const pageCopy = {
  es: {
    kicker: "AI Infrastructure Tools",
    title: "Huawei Cloud MCP Server",
    subtitle: "150 tools. 34 servicios. Un servidor MCP para infraestructura asistida por IA.",
    download: "Descargar",
    downloadSize: mcpDownloadSize,
    version: "Versión",
    statsTitle: "De un vistazo",
    servicesTitle: "Servicios cubiertos",
    servicesBody: "34 servicios de Huawei Cloud expuestos como tools MCP con type safety, JSON schema y annotations readOnlyHint.",
    installTitle: "Instalación",
    installBody: "Configura el servidor MCP en tu cliente de IA preferido. Requiere hcloud CLI (KooCLI) instalado y autenticado.",
    toolsTitle: "Referencia de tools",
    toolsBody: "149 tools estructuradas read-only + 1 hcloud_cli catch-all para operaciones de escritura.",
    searchPlaceholder: "Buscar tools...",
    allServices: "Todos los servicios",
    examplesTitle: "Ejemplos de uso",
    cliNote: "hcloud_cli — catch-all genérico",
    cliNoteBody: "Para operaciones de escritura (Create/Update/Delete) y cualquier operación no cubierta por las tools estructuradas. Safety gate: dry-run por defecto, confirm=true para ejecutar.",
    readOnly: "read-only",
    destructive: "destructive",
    toolCol: "Tool",
    serviceCol: "Servicio",
    descCol: "Descripción",
    typeCol: "Tipo",
    protocolLabel: "Protocolo MCP",
    annotationsLabel: "Annotations",
    toolsLabel: "Tools",
    servicesLabel: "Servicios",
    backToMigration: "Volver a Migración",
  },
  en: {
    kicker: "AI Infrastructure Tools",
    title: "Huawei Cloud MCP Server",
    subtitle: "150 tools. 34 services. One MCP server for AI-assisted infrastructure.",
    download: "Download",
    downloadSize: mcpDownloadSize,
    version: "Version",
    statsTitle: "At a glance",
    servicesTitle: "Services covered",
    servicesBody: "34 Huawei Cloud services exposed as MCP tools with type safety, JSON schema, and readOnlyHint annotations.",
    installTitle: "Installation",
    installBody: "Configure the MCP server in your preferred AI client. Requires hcloud CLI (KooCLI) installed and authenticated.",
    toolsTitle: "Tool reference",
    toolsBody: "149 structured read-only tools + 1 hcloud_cli catch-all for write operations.",
    searchPlaceholder: "Search tools...",
    allServices: "All services",
    examplesTitle: "Usage examples",
    cliNote: "hcloud_cli — generic catch-all",
    cliNoteBody: "For write operations (Create/Update/Delete) and any operation not covered by structured tools. Safety gate: dry-run by default, confirm=true to execute.",
    readOnly: "read-only",
    destructive: "destructive",
    toolCol: "Tool",
    serviceCol: "Service",
    descCol: "Description",
    typeCol: "Type",
    protocolLabel: "MCP Protocol",
    annotationsLabel: "Annotations",
    toolsLabel: "Tools",
    servicesLabel: "Services",
    backToMigration: "Back to Migration",
  },
  zh: {
    kicker: "AI 基础设施工具",
    title: "Huawei Cloud MCP Server",
    subtitle: "150 个工具。34 个服务。一个面向 AI 辅助基础设施的 MCP 服务器。",
    download: "下载",
    downloadSize: mcpDownloadSize,
    version: "版本",
    statsTitle: "概览",
    servicesTitle: "覆盖服务",
    servicesBody: "34 个华为云服务以 MCP 工具形式暴露，具备类型安全、JSON schema 和 readOnlyHint 注解。",
    installTitle: "安装",
    installBody: "在您首选的 AI 客户端中配置 MCP 服务器。需要已安装并认证的 hcloud CLI (KooCLI)。",
    toolsTitle: "工具参考",
    toolsBody: "149 个结构化只读工具 + 1 个 hcloud_cli 通用工具用于写操作。",
    searchPlaceholder: "搜索工具...",
    allServices: "所有服务",
    examplesTitle: "使用示例",
    cliNote: "hcloud_cli — 通用工具",
    cliNoteBody: "用于写操作 (Create/Update/Delete) 及结构化工具未覆盖的任何操作。安全门：默认 dry-run，confirm=true 才执行。",
    readOnly: "只读",
    destructive: "破坏性",
    toolCol: "工具",
    serviceCol: "服务",
    descCol: "描述",
    typeCol: "类型",
    protocolLabel: "MCP 协议",
    annotationsLabel: "注解",
    toolsLabel: "工具",
    servicesLabel: "服务",
    backToMigration: "返回迁移",
  },
  pg: {
    kicker: "Ferramentas de Infra AI",
    title: "Huawei Cloud MCP Server",
    subtitle: "150 ferramentas. 34 serviços. Um servidor MCP para infraestrutura assistida por IA.",
    download: "Baixar",
    downloadSize: mcpDownloadSize,
    version: "Versão",
    statsTitle: "Visão geral",
    servicesTitle: "Serviços cobertos",
    servicesBody: "34 serviços Huawei Cloud expostos como tools MCP com type safety, JSON schema e annotations readOnlyHint.",
    installTitle: "Instalação",
    installBody: "Configure o servidor MCP no seu cliente de IA preferido. Requer hcloud CLI (KooCLI) instalado e autenticado.",
    toolsTitle: "Referência de tools",
    toolsBody: "149 tools estruturadas read-only + 1 hcloud_cli catch-all para operações de escrita.",
    searchPlaceholder: "Buscar tools...",
    allServices: "Todos os serviços",
    examplesTitle: "Exemplos de uso",
    cliNote: "hcloud_cli — catch-all genérico",
    cliNoteBody: "Para operações de escrita (Create/Update/Delete) e qualquer operação não coberta pelas tools estruturadas. Safety gate: dry-run por padrão, confirm=true para executar.",
    readOnly: "read-only",
    destructive: "destructive",
    toolCol: "Tool",
    serviceCol: "Serviço",
    descCol: "Descrição",
    typeCol: "Tipo",
    protocolLabel: "Protocolo MCP",
    annotationsLabel: "Annotations",
    toolsLabel: "Tools",
    servicesLabel: "Serviços",
    backToMigration: "Voltar para Migração",
  },
} satisfies Record<Lang, Record<string, string>>;

const categoryColors: Record<McpServiceCategory, string> = {
  "Compute": "#2563eb",
  "Network": "#059669",
  "Storage": "#d97706",
  "Database": "#dc2626",
  "Security & Identity": "#7c3aed",
  "Monitoring & Logs": "#0891b2",
  "Migration & Backup": "#ea580c",
  "Big Data & Analytics": "#4f46e5",
  "DevOps": "#be185d",
  "Messaging": "#65a30d",
  "Governance & Billing": "#475569",
};

function McpHero({ lang }: { lang: Lang }) {
  const t = pageCopy[lang];
  return (
    <section className="mcp-hero">
      <div className="mcp-hero-content">
        <span className="section-kicker">{t.kicker}</span>
        <h1>{t.title}</h1>
        <p className="mcp-hero-subtitle">{t.subtitle}</p>
        <div className="mcp-hero-badges">
          <span className="mcp-badge mcp-badge-version">{t.version} {mcpServerVersion}</span>
          <span className="mcp-badge mcp-badge-protocol">{t.protocolLabel} {mcpProtocolVersion}</span>
        </div>
        <div className="mcp-hero-actions">
          <a
            className="primary-action"
            href={mcpGitHubRepo}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => trackClick({ click_target: "mcp_github", click_section: "mcp_hero", destination: mcpGitHubRepo })}
          >
            <Github size={18} />
            GitHub
          </a>
          <a
            className="secondary-action"
            href={mcpDownloadUrl}
            onClick={() => trackClick({ click_target: "mcp_download", click_section: "mcp_hero", destination: mcpDownloadUrl })}
          >
            <Download size={18} />
            {t.download} ({t.downloadSize})
          </a>
          <a
            className="secondary-action"
            href="#/migration"
            onClick={() => trackClick({ click_target: "mcp_back_migration", click_section: "mcp_hero", destination: "#/migration" })}
          >
            <ArrowRight size={18} />
            {t.backToMigration}
          </a>
        </div>
      </div>
    </section>
  );
}

function McpStats({ lang }: { lang: Lang }) {
  const t = pageCopy[lang];
  const stats = [
    { icon: Wrench, label: t.toolsLabel, value: String(mcpTotalTools), note: `${mcpStructuredTools} structured + 1 CLI` },
    { icon: Zap, label: t.servicesLabel, value: String(mcpServicesCovered), note: "Huawei Cloud services" },
    { icon: Terminal, label: t.protocolLabel, value: mcpProtocolVersion, note: "MCP 2.0 compatible" },
    { icon: Shield, label: t.annotationsLabel, value: "readOnly + destructive", note: "MCP ToolAnnotations on all tools" },
  ];
  return (
    <section className="content-section mcp-stats-section">
      <div className="section-heading">
        <span className="section-kicker">{t.statsTitle}</span>
      </div>
      <div className="mcp-stats-grid">
        {stats.map(({ icon: Icon, label, value, note }) => (
          <div className="mcp-stat-card" key={label}>
            <Icon size={28} className="mcp-stat-icon" />
            <div className="mcp-stat-value">{value}</div>
            <div className="mcp-stat-label">{label}</div>
            <div className="mcp-stat-note">{note}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function McpServices({ lang }: { lang: Lang }) {
  const t = pageCopy[lang];
  return (
    <section className="content-section mcp-services-section">
      <div className="section-heading">
        <span className="section-kicker">{t.servicesTitle}</span>
        <h2>{t.servicesTitle}</h2>
        <p>{t.servicesBody}</p>
      </div>
      {mcpCategoryOrder.map((category) => {
        const services = mcpServices.filter((s) => s.category === category);
        if (services.length === 0) return null;
        const color = categoryColors[category];
        return (
          <div className="mcp-category-group" key={category}>
            <h3 className="mcp-category-title" style={{ borderLeftColor: color }}>
              <span className="mcp-category-dot" style={{ backgroundColor: color }} />
              {category}
              <span className="mcp-category-count">{services.length}</span>
            </h3>
            <div className="mcp-service-grid">
              {services.map((svc) => (
                <div className="mcp-service-card" key={svc.id} style={{ borderTopColor: color }}>
                  <div className="mcp-service-header">
                    <strong>{svc.name}</strong>
                    <span className="mcp-service-count">{svc.toolCount}</span>
                  </div>
                  <div className="mcp-service-fullname">{svc.fullName}</div>
                  <div className="mcp-service-desc">{svc.description}</div>
                  <div className="mcp-service-cli">CLI: {svc.cliService}</div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </section>
  );
}

function McpInstallSteps({ lang }: { lang: Lang }) {
  const t = pageCopy[lang];
  return (
    <section className="content-section mcp-install-steps-section">
      <div className="section-heading">
        <span className="section-kicker">{lang === "es" ? "Guía de instalación" : "Installation guide"}</span>
        <h2>{lang === "es" ? "Paso a paso" : "Step by step"}</h2>
      </div>
      <div className="mcp-steps-list">
        {mcpInstallSteps.map(({ step, title, commands, note }) => (
          <div className="mcp-step" key={step}>
            <div className="mcp-step-header">
              <span className="mcp-step-number">{step}</span>
              <strong>{title}</strong>
            </div>
            <pre className="mcp-code-block mcp-code-block-sm">
              <code>{commands.join("\n")}</code>
            </pre>
            {note && <p className="mcp-step-note">{note}</p>}
          </div>
        ))}
      </div>
    </section>
  );
}

function McpInstall({ lang }: { lang: Lang }) {
  const t = pageCopy[lang];
  const tabs = Object.entries(mcpInstallSnippets);
  const [active, setActive] = useState(tabs[0][0]);
  const activeSnippet = mcpInstallSnippets[active];
  return (
    <section className="content-section mcp-install-section">
      <div className="section-heading">
        <span className="section-kicker">{t.installTitle}</span>
        <h2>{t.installTitle}</h2>
        <p>{t.installBody}</p>
      </div>
      <div className="mcp-install-tabs">
        {tabs.map(([key, snip]) => (
          <button
            type="button"
            key={key}
            className={active === key ? "mcp-install-tab active" : "mcp-install-tab"}
            onClick={() => setActive(key)}
          >
            {snip.label}
          </button>
        ))}
      </div>
      <div className="mcp-config-path">
        <strong>{lang === "es" ? "Archivo de config:" : "Config file:"}</strong>
        <code>{activeSnippet.configPath}</code>
      </div>
      <pre className="mcp-code-block">
        <code>{activeSnippet.code}</code>
      </pre>
    </section>
  );
}

function McpToolTable({ lang }: { lang: Lang }) {
  const t = pageCopy[lang];
  const [query, setQuery] = useState("");
  const [serviceFilter, setServiceFilter] = useState("");

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    return mcpTools.filter((tool) => {
      const matchesQuery = !q || tool.name.toLowerCase().includes(q) || tool.description.toLowerCase().includes(q);
      const matchesService = !serviceFilter || tool.service === serviceFilter;
      return matchesQuery && matchesService;
    });
  }, [query, serviceFilter]);

  const serviceOptions = useMemo(
    () => [...mcpServices].sort((a, b) => a.name.localeCompare(b.name)),
    [],
  );

  return (
    <section className="content-section mcp-tools-section">
      <div className="section-heading">
        <span className="section-kicker">{t.toolsTitle}</span>
        <h2>{t.toolsTitle}</h2>
        <p>{t.toolsBody}</p>
      </div>
      <div className="mcp-tools-controls">
        <div className="mcp-search-box">
          <Search size={16} />
          <input
            type="text"
            placeholder={t.searchPlaceholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <select value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)}>
          <option value="">{t.allServices}</option>
          {serviceOptions.map((svc) => (
            <option key={svc.id} value={svc.id}>{svc.name} ({svc.toolCount})</option>
          ))}
        </select>
        <span className="mcp-tools-count">{filtered.length} / {mcpTools.length}</span>
      </div>
      <div className="mcp-tools-table-wrapper">
        <table className="mcp-tools-table">
          <thead>
            <tr>
              <th>{t.toolCol}</th>
              <th>{t.serviceCol}</th>
              <th>{t.descCol}</th>
              <th>{t.typeCol}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((tool) => {
              const svc = mcpServices.find((s) => s.id === tool.service);
              return (
                <tr key={tool.name}>
                  <td className="mcp-tool-name">{tool.name}</td>
                  <td className="mcp-tool-service">{svc?.name ?? tool.service}</td>
                  <td className="mcp-tool-desc">{tool.description}</td>
                  <td className="mcp-tool-type">
                    <span className={tool.readOnly ? "mcp-tag mcp-tag-ro" : "mcp-tag mcp-tag-de"}>
                      {tool.readOnly ? t.readOnly : t.destructive}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {/* hcloud_cli catch-all note */}
      <div className="mcp-cli-note">
        <Terminal size={20} />
        <div>
          <strong>{t.cliNote}</strong>
          <p>{t.cliNoteBody}</p>
        </div>
      </div>
    </section>
  );
}

function McpExamples({ lang }: { lang: Lang }) {
  const t = pageCopy[lang];
  return (
    <section className="content-section mcp-examples-section">
      <div className="section-heading">
        <span className="section-kicker">{t.examplesTitle}</span>
        <h2>{t.examplesTitle}</h2>
      </div>
      <div className="mcp-examples-grid">
        {mcpExamples.map((ex) => (
          <div className="mcp-example-card" key={ex.title}>
            <strong>{ex.title}</strong>
            <p className="mcp-example-desc">{ex.description}</p>
            <pre className="mcp-code-block mcp-code-block-sm">
              <code>{ex.code}</code>
            </pre>
          </div>
        ))}
      </div>
    </section>
  );
}

export function McpServerPage({ lang }: { lang: Lang }) {
  return (
    <main id="top" className="mcp-page">
      <McpHero lang={lang} />
      <McpStats lang={lang} />
      <McpServices lang={lang} />
      <McpInstallSteps lang={lang} />
      <McpInstall lang={lang} />
      <McpToolTable lang={lang} />
      <McpExamples lang={lang} />
    </main>
  );
}
