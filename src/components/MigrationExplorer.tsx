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

const MIGRATION_SCENARIO_IDS = [
  "cloud-database-migration",
  "bi-data-platform-migration",
  "sap-erp-on-cloud",
  "backup-dr-security",
  "workspace-vmware-migration",
];

const labels = {
  es: {
    kicker: "Migration & Modernization",
    title: "Escenarios de migración y modernización",
    body: "Rutas prácticas para mover cargas, bases de datos, VMware y ERP desde otras nubes o datacenters hacia Huawei Cloud.",
    viewSolution: "Ver solución",
    viewSkill: "Ver demo / skill",
    quickIntegration: "Integración rápida",
    openOfficial: "Abrir solución oficial",
    externalBadge: "Enlace externo",
  },
  en: {
    kicker: "Migration & Modernization",
    title: "Migration and modernization scenarios",
    body: "Practical paths for moving workloads, databases, VMware, and ERP from other clouds or datacenters into Huawei Cloud.",
    viewSolution: "View solution",
    viewSkill: "View demo / skill",
    quickIntegration: "Quick integration",
    openOfficial: "Open official solution",
    externalBadge: "External link",
  },
  zh: {
    kicker: "迁移与现代化",
    title: "迁移与现代化场景",
    body: "从其他云或数据中心迁移负载、数据库、VMware 和 ERP 到华为云的实用路径。",
    viewSolution: "查看方案",
    viewSkill: "查看 demo / skill",
    quickIntegration: "快速集成",
    openOfficial: "打开官方方案",
    externalBadge: "外部链接",
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
      <img src={scenario.heroImage} alt="" loading="lazy" />
      <div className="scenario-card-body">
        <div className="scenario-card-heading">
          <span className="scenario-entry-badge">{textFor(lang, scenarioEntry.title)}</span>
          {isExternal && <span className="external-link-badge"><ExternalLink size={12} /> {l.externalBadge}</span>}
        </div>
        <h3>{textFor(lang, scenario.title)}</h3>
        <p>{textFor(lang, scenario.oneLiner)}</p>
        <div className="tag-row">
          {scenario.recommendedServices.slice(0, 4).map((service) => (
            <span className="service-tag" key={service}>
              {service}
            </span>
          ))}
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
              href={`#/solutions/${scenario.id}`}
              onClick={() =>
                trackClick({
                  click_target: "migration_scenario_view_solution",
                  click_section: "migration_scenarios",
                  destination: `#/solutions/${scenario.id}`,
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
          {!isExternal && (
            <a
              className="text-action"
              href={`#/solutions/${scenario.id}#integration`}
              onClick={() =>
                trackClick({
                  click_target: "migration_scenario_quick_integration",
                  click_section: "migration_scenarios",
                  destination: `#/solutions/${scenario.id}#integration`,
                  entry_id: activeEntry.id,
                  scenario_id: scenario.id,
                })
              }
            >
              {l.quickIntegration}
              <ArrowRight size={15} />
            </a>
          )}
        </div>
      </div>
    </article>
  );
}

export function MigrationExplorer({ lang }: { lang: Lang }) {
  const l = labels[lang];
  const scenarios = MIGRATION_SCENARIO_IDS
    .map((id) => solutionScenarioMap[id])
    .filter((s): s is SolutionScenario => Boolean(s));
  const fallbackEntry = solutionEntries.find((e) => e.id === "cloud-to-cloud") ?? solutionEntries[0];

  return (
    <div className="migration-explorer">
      <section className="migration-explorer-hero">
        <div>
          <span className="section-kicker">{l.kicker}</span>
          <h2>{l.title}</h2>
          <p>{l.body}</p>
        </div>
      </section>

      <section className="scenario-section">
        <div className="section-heading">
          <span className="section-kicker">
            {scenarios.length} {lang === "es" ? "escenarios" : lang === "zh" ? "个场景" : "scenarios"}
          </span>
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
    </div>
  );
}
