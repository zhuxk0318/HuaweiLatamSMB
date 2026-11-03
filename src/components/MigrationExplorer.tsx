import { useState } from "react";
import { ArrowRight, ExternalLink } from "lucide-react";
import { trackClick } from "../analytics";
import type { Lang } from "../data/i18n";
import {
  solutionEntries,
  solutionScenarioMap,
  textFor,
  type SolutionEntry,
  type SolutionScenario,
} from "../data/solutions";
import { AutoLinkText } from "./AutoLinkText";
import { serviceUrlMap } from "./SolutionDetailPage";
import { MigrationHeroBanner } from "./Hero/MigrationHeroBanner";

const MIGRATION_SCENARIO_IDS = [
  "cloud-to-cloud-migration",
  "vmware-migration",
  "container-migration",
  "workspace-migration",
  "ai-coding-opencode",
  "ai-coding-hermes",
  "ai-coding-claude-code",
  "vm-migration",
  "database-migration",
  "codearts-deployment",
  "mrs-deployment",
  "mrs-migration",
  "dws-cluster-deployment",
  "snowflake-to-dataarts",
  "postgresql-ecs-to-rds-drs",
  "database-usage-operations",
  "object-migration",
  "cloud-foundation",
  "landing-zone",
  "image-discovery",
  "cbr-backup-restore",
  "sdrs-cross-region-dr",
  "other-scenarios",
  "docker-compose-to-cci",
  "vpn-connectivity",
];

const CATEGORY_ORDER = [
  "All",
  "Cloud to Cloud Migration",
  "Containers",
  "Workspace",
  "AI Tools",
  "Datacenter On-Premise",
  "Virtual Machine",
  "Database",
  "Big Data",
  "Object Storage",
  "Cloud Foundation",
  "Other",
] as const;

const categoryLabels: Record<Lang, Record<string, string>> = {
  es: {
    "All": "Todos",
    "Cloud to Cloud Migration": "Cloud to Cloud",
    "Containers": "Contenedores",
    "Workspace": "Workspace",
    "AI Tools": "AI Tools",
    "Datacenter On-Premise": "Datacenter",
    "Virtual Machine": "Virtual Machine",
    "Database": "Database",
    "Big Data": "Big Data",
    "Object Storage": "Object Storage",
    "Cloud Foundation": "Cloud Foundation",
    "Other": "Otros",
  },
  en: {
    "All": "All",
    "Cloud to Cloud Migration": "Cloud to Cloud",
    "Containers": "Containers",
    "Workspace": "Workspace",
    "AI Tools": "AI Tools",
    "Datacenter On-Premise": "Datacenter",
    "Virtual Machine": "Virtual Machine",
    "Database": "Database",
    "Big Data": "Big Data",
    "Object Storage": "Object Storage",
    "Cloud Foundation": "Cloud Foundation",
    "Other": "Other",
  },
  zh: {
    "All": "\u5168\u90e8",
    "Cloud to Cloud Migration": "Cloud to Cloud",
    "Containers": "\u5bb9\u5668",
    "Workspace": "Workspace",
    "AI Tools": "AI Tools",
    "Datacenter On-Premise": "Datacenter",
    "Virtual Machine": "\u865a\u62df\u673a",
    "Database": "Database",
    "Big Data": "Big Data",
    "Object Storage": "Object Storage",
    "Cloud Foundation": "Cloud Foundation",
    "Other": "\u5176\u4ed6",
  },
  pg: {
    "All": "Todos",
    "Cloud to Cloud Migration": "Cloud to Cloud",
    "Containers": "Cont\u00eaineres",
    "Workspace": "Workspace",
    "AI Tools": "AI Tools",
    "Datacenter On-Premise": "Datacenter",
    "Virtual Machine": "Virtual Machine",
    "Database": "Database",
    "Big Data": "Big Data",
    "Object Storage": "Object Storage",
    "Cloud Foundation": "Cloud Foundation",
    "Other": "Outros",
  },
};

const labels = {
  es: {
    kicker: "Migration & Modernization",
    title: "Escenarios de Migraci\u00f3n y Modernizaci\u00f3n",
    body: "Rutas pr\u00e1cticas para mover cargas, bases de datos, escritorios virtuales y contenedores desde cualquier nube o datacenter hacia Huawei Cloud.",
    viewSolution: "Ver soluci\u00f3n/demo",
    viewSkill: "Ver skills y tools",
    quickIntegration: "Integraci\u00f3n r\u00e1pida",
    openOfficial: "Abrir soluci\u00f3n oficial",
    externalBadge: "Enlace externo",
  },
  en: {
    kicker: "Migration & Modernization",
    title: "Migration and Modernization Scenarios",
    body: "Practical paths for moving workloads, databases, virtual desktops, and containers from any cloud or datacenter into Huawei Cloud.",
    viewSolution: "View Solution/Demo",
    viewSkill: "View Skills and tools",
    quickIntegration: "Quick integration",
    openOfficial: "Open official solution",
    externalBadge: "External link",
  },
  zh: {
    kicker: "\u8fc1\u79fb\u4e0e\u73b0\u4ee3\u5316",
    title: "\u8fc1\u79fb\u4e0e\u73b0\u4ee3\u5316\u573a\u666f",
    body: "\u4ece\u4efb\u4f55\u4e91\u6216\u6570\u636e\u4e2d\u5fc3\u8fc1\u79fb\u8d1f\u8f7d\u3001\u6570\u636e\u5e93\u3001\u865a\u62df\u684c\u9762\u548c\u5bb9\u5668\u5230\u534e\u4e3a\u4e91\u7684\u5b9e\u7528\u8def\u5f84\u3002",
    viewSolution: "\u67e5\u770b\u65b9\u6848/Demo",
    viewSkill: "\u67e5\u770b Skills and tools",
    quickIntegration: "\u5feb\u901f\u96c6\u6210",
    openOfficial: "\u6253\u5f00\u5b98\u65b9\u65b9\u6848",
    externalBadge: "\u5916\u90e8\u94fe\u63a5",
  },
  pg: {
    kicker: "Migration & Modernization",
    title: "Migration and Modernization Scenarios",
    body: "Practical paths for moving workloads, databases, virtual desktops, and containers from any cloud or datacenter into Huawei Cloud.",
    viewSolution: "View Solution/Demo",
    viewSkill: "View Skills and tools",
    quickIntegration: "Quick integration",
    openOfficial: "Open official solution",
    externalBadge: "External link",
  },
} satisfies Record<
  Lang,
  {
    kicker: string;
    title: string;
    body: string;
    viewSolution: string;
    viewSkill: string;
    quickIntegration: string;
    openOfficial: string;
    externalBadge: string;
  }
>;

function ScenarioCard({
  lang,
  scenario,
  activeEntry,
}: {
  lang: Lang;
  scenario: SolutionScenario;
  activeEntry: SolutionEntry;
}) {
  const l = labels[lang];
  const primarySkill = scenario.demoSkillLinks[0];
  const scenarioEntry = solutionEntries.find((entry) => entry.id === scenario.entryId) ?? activeEntry;
  const isExternal = Boolean(scenario.externalUrls);

  return (
    <article className="scenario-card">
      <div className="scenario-card-media">
        <img src={scenario.heroImage} alt="" loading="lazy" />
        {scenario.categoryLabel && (
          <span className="scenario-category-tag">{textFor(lang, scenario.categoryLabel)}</span>
        )}
      </div>
      <div className="scenario-card-body">
        <div className="scenario-card-heading">
          {isExternal && <span className="external-link-badge"><ExternalLink size={12} /> {l.externalBadge}</span>}
        </div>
        <h3>{textFor(lang, scenario.title)}</h3>
        <p><AutoLinkText text={textFor(lang, scenario.oneLiner)} /></p>
        <div className="tag-row">
          {scenario.recommendedServices.slice(0, 4).map((service) => {
            const url = serviceUrlMap[service];
            return url ? (
              <a
                className="service-tag service-tag-link"
                key={service}
                href={url}
                target="_blank"
                rel="noreferrer"
              >
                {service}
              </a>
            ) : (
              <span className="service-tag" key={service}>
                {service}
              </span>
            );
          })}
        </div>
        <div className="scenario-actions">
          {isExternal ? (
            <a
              className="primary-action"
              href={lang === "es" ? scenario.externalUrls!.es : scenario.externalUrls!.en}
              target="_blank"
              rel="noreferrer"
              onClick={() =>
                trackClick({
                  click_target: "migration_scenario_open_official",
                  click_section: "migration_scenarios",
                  destination: lang === "es" ? scenario.externalUrls!.es : scenario.externalUrls!.en,
                  entry_id: activeEntry.id,
                  scenario_id: scenario.id,
                })
              }
            >
              {l.openOfficial}
              <ExternalLink size={16} />
            </a>
          ) : (
            <a
              className="primary-action"
              href={`#/solutions/${scenario.id}?from=migration`}
              onClick={() =>
                trackClick({
                  click_target: "migration_scenario_view_solution",
                  click_section: "migration_scenarios",
                  destination: `#/solutions/${scenario.id}?from=migration`,
                  entry_id: activeEntry.id,
                  scenario_id: scenario.id,
                })
              }
            >
              {l.viewSolution}
              <ArrowRight size={16} />
            </a>
          )}
          {!isExternal && primarySkill && (
            <a
              className="secondary-action light"
              href={primarySkill.url}
              target="_blank"
              rel="noreferrer"
              onClick={() =>
                trackClick({
                  click_target: "migration_scenario_view_skill",
                  click_section: "migration_scenarios",
                  destination: primarySkill.url,
                  entry_id: activeEntry.id,
                  scenario_id: scenario.id,
                })
              }
            >
              {l.viewSkill}
              <ExternalLink size={16} />
            </a>
          )}
        </div>
      </div>
    </article>
  );
}

export function MigrationExplorer({ lang }: { lang: Lang }) {
  const [activeCategory, setActiveCategory] = useState<string>("All");

  const allScenarios = MIGRATION_SCENARIO_IDS
    .map((id) => solutionScenarioMap[id])
    .filter((s): s is SolutionScenario => Boolean(s));

  const categoryCounts = CATEGORY_ORDER.reduce((acc, cat) => {
    if (cat === "All") {
      acc[cat] = allScenarios.length;
    } else {
      acc[cat] = allScenarios.filter(
        (s) => s.categoryLabel?.en === cat
      ).length;
    }
    return acc;
  }, {} as Record<string, number>);

  const visibleCategories = CATEGORY_ORDER.filter(
    (cat) => cat === "All" || categoryCounts[cat] > 0
  );

  const scenarios =
    activeCategory === "All"
      ? allScenarios
      : allScenarios.filter((s) => s.categoryLabel?.en === activeCategory);

  const fallbackEntry = solutionEntries.find((e) => e.id === "on-prem-to-cloud") ?? solutionEntries[0];
  const catL = categoryLabels[lang];

  return (
    <div className="migration-explorer">
      <MigrationHeroBanner lang={lang} />

      <section id="migration-scenarios" className="scenario-section migration-scenario-section">
        <div className="section-heading">
          <span className="section-kicker">
            {scenarios.length} {lang === "es" ? "escenarios" : lang === "zh" ? "\u4e2a\u573a\u666f" : "scenarios"}
          </span>
        </div>
        <div className="category-filter-row">
          {visibleCategories.map((cat) => (
            <button
              key={cat}
              className={`category-pill${activeCategory === cat ? " active" : ""}`}
              onClick={() => setActiveCategory(cat)}
            >
              {catL[cat] ?? cat}
              <span className="category-pill-count">{categoryCounts[cat]}</span>
            </button>
          ))}
        </div>
        <div className="scenario-grid">
          {scenarios.map((scenario) => (
            <ScenarioCard
              lang={lang}
              scenario={scenario}
              activeEntry={fallbackEntry}
              key={scenario.id}
            />
          ))}
        </div>
      </section>

      <section className="mcp-cta-banner">
        <div className="mcp-cta-content">
          <span className="section-kicker">AI Infrastructure Tools</span>
          <h2>{lang === "es" ? "Servidor MCP de Huawei Cloud" : lang === "zh" ? "华为云 MCP 服务器" : "Huawei Cloud MCP Server"}</h2>
          <p>
            {lang === "es"
              ? "150 tools MCP para 34 servicios de Huawei Cloud. Instala el servidor en tu cliente de IA y gestiona infraestructura con type safety."
              : lang === "zh"
                ? "150 个 MCP 工具覆盖 34 个华为云服务。在您的 AI 客户端中安装服务器，以类型安全管理基础设施。"
                : "150 MCP tools for 34 Huawei Cloud services. Install the server in your AI client and manage infrastructure with type safety."}
          </p>
          <a
            className="primary-action"
            href="#/mcp"
            onClick={() =>
              trackClick({
                click_target: "migration_mcp_cta",
                click_section: "migration_mcp_banner",
                destination: "#/mcp",
              })
            }
          >
            {lang === "es" ? "Ver MCP Server" : lang === "zh" ? "查看 MCP 服务器" : "View MCP Server"}
            <ArrowRight size={18} />
          </a>
        </div>
      </section>
    </div>
  );
}
