import { ArrowLeft, ArrowRight, ExternalLink, Layers3 } from "lucide-react";
import { trackClick } from "../analytics";
import type { Lang } from "../data/i18n";
import { solutionEntries, solutionScenarioMap, textFor, type LocalizedPair } from "../data/solutions";
import { HealthcareSolutionPage } from "./HealthcareSolutionPage";

type SolutionDetailPageProps = {
  lang: Lang;
  solutionId: string | null;
};

const labels = {
  es: {
    back: "Volver al playbook",
    missing: "Escenario no encontrado",
    missingBody: "Revise el playbook y seleccione uno de los escenarios disponibles.",
    targetCustomers: "Clientes objetivo",
    painPoints: "Dolores del cliente",
    solutionApproach: "Enfoque Huawei Cloud",
    services: "Servicios recomendados",
    demoSkills: "Demo y skills de GitHub",
    quickIntegration: "Integración rápida",
    prerequisites: "Prerequisitos",
    steps: "Pasos de integración",
    configuration: "Notas de configuración",
    apiAccess: "Patrón de API y acceso",
    salesTalkTrack: "Preguntas de venta",
    expectedOutcomes: "Resultados esperados",
    estimator: "Abrir cotizador cloud",
    overview: "Ver todos los escenarios",
  },
  en: {
    back: "Back to playbook",
    missing: "Scenario not found",
    missingBody: "Review the playbook and select one of the available scenarios.",
    targetCustomers: "Target customers",
    painPoints: "Customer pain points",
    solutionApproach: "Huawei Cloud approach",
    services: "Recommended services",
    demoSkills: "Demo and GitHub skills",
    quickIntegration: "Quick integration",
    prerequisites: "Prerequisites",
    steps: "Integration steps",
    configuration: "Configuration notes",
    apiAccess: "API and access pattern",
    salesTalkTrack: "Sales talk track",
    expectedOutcomes: "Expected outcomes",
    estimator: "Open cloud estimator",
    overview: "Browse all scenarios",
  },
} satisfies Record<Lang, Record<string, string>>;

function textList(lang: Lang, items: LocalizedPair[]) {
  return items.map((item) => textFor(lang, item));
}

function BulletSection({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="solution-detail-card">
      <h2>{title}</h2>
      <ul className="detail-bullet-list">
        {items.map((item) => (
          <li key={item}>
            <span className="detail-bullet-dot" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function SolutionDetailPage({ lang, solutionId }: SolutionDetailPageProps) {
  const l = labels[lang];
  const scenario = solutionId ? solutionScenarioMap[solutionId] : undefined;

  if (scenario?.detailVariant === "healthcare" && solutionId) {
    return <HealthcareSolutionPage lang={lang} scenarioId={solutionId} />;
  }

  if (!scenario) {
    return (
      <main className="solution-detail-page">
        <a className="back-link" href="#/solutions">
          <ArrowLeft size={17} />
          {l.back}
        </a>
        <section className="solution-detail-hero">
          <span className="section-kicker">{l.missing}</span>
          <h1>{l.missing}</h1>
          <p>{l.missingBody}</p>
        </section>
      </main>
    );
  }

  const entry = solutionEntries.find((item) => item.id === scenario.entryId) ?? solutionEntries[0];

  return (
    <main className="solution-detail-page">
      <a
        className="back-link"
        href={`#/solutions?entry=${entry.id}`}
        onClick={() =>
          trackClick({
            click_target: "solution_detail_back",
            click_section: "solution_detail",
            destination: `#/solutions?entry=${entry.id}`,
            entry_id: entry.id,
            scenario_id: scenario.id,
          })
        }
      >
        <ArrowLeft size={17} />
        {l.back}
      </a>

      <section
        className="solution-detail-hero scenario-detail-hero"
        style={{
          backgroundImage: `linear-gradient(120deg, rgba(255, 255, 255, 0.96), rgba(255, 255, 255, 0.82)), url("${scenario.heroImage}")`,
        }}
      >
        <span className="section-kicker">{textFor(lang, entry.title)}</span>
        <h1>{textFor(lang, scenario.title)}</h1>
        <p>{textFor(lang, scenario.oneLiner)}</p>
        <div className="tag-row">
          {scenario.recommendedServices.map((service) => (
            <span className="service-tag strong" key={service}>
              {service}
            </span>
          ))}
        </div>
        <div className="hero-actions">
          <a
            className="primary-action"
            href="#/estimator"
            onClick={() =>
              trackClick({
                click_target: "solution_detail_estimator",
                click_section: "solution_detail_hero",
                destination: "#/estimator",
                entry_id: entry.id,
                scenario_id: scenario.id,
              })
            }
          >
            {l.estimator}
            <ArrowRight size={18} />
          </a>
          <a
            className="secondary-action light"
            href="#/solutions"
            onClick={() =>
              trackClick({
                click_target: "solution_detail_overview_cta",
                click_section: "solution_detail_hero",
                destination: "#/solutions",
                entry_id: entry.id,
                scenario_id: scenario.id,
              })
            }
          >
            {l.overview}
          </a>
        </div>
      </section>

      <div className="solution-detail-grid">
        <BulletSection title={l.targetCustomers} items={textList(lang, scenario.targetCustomers)} />
        <BulletSection title={l.painPoints} items={textList(lang, scenario.painPoints)} />
      </div>

      <section className="solution-detail-card">
        <h2>{l.solutionApproach}</h2>
        <ul className="detail-bullet-list">
          {textList(lang, scenario.solutionApproach).map((item) => (
            <li key={item}>
              <span className="detail-bullet-dot" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </section>

      <div className="solution-detail-grid">
        <section className="solution-detail-card">
          <h2>{l.services}</h2>
          <div className="tag-row detail-tag-row">
            {scenario.recommendedServices.map((service) => (
              <span className="service-tag strong" key={service}>
                {service}
              </span>
            ))}
          </div>
        </section>

        <section className="solution-detail-card">
          <h2>{l.demoSkills}</h2>
          <div className="resource-grid single scenario-resource-grid">
            {scenario.demoSkillLinks.map((reference) => (
              <a
                className="resource-card"
                href={reference.url}
                target="_blank"
                rel="noreferrer"
                key={reference.url}
                onClick={() =>
                  trackClick({
                    click_target: "solution_detail_skill",
                    click_section: "solution_detail_resources",
                    destination: reference.url,
                    entry_id: entry.id,
                    scenario_id: scenario.id,
                  })
                }
              >
                <ExternalLink size={18} />
                <span>
                  <strong>{reference.label}</strong>
                  <small>{reference.url}</small>
                </span>
              </a>
            ))}
          </div>
        </section>
      </div>

      <section id="integration" className="solution-detail-card">
        <div className="panel-title">
          <Layers3 size={20} />
          <h2>{l.quickIntegration}</h2>
        </div>
        <div className="solution-detail-grid integration-grid">
          <BulletSection title={l.prerequisites} items={textList(lang, scenario.quickIntegration.prerequisites)} />
          <BulletSection title={l.steps} items={textList(lang, scenario.quickIntegration.steps)} />
          <BulletSection title={l.configuration} items={textList(lang, scenario.quickIntegration.configuration)} />
          <BulletSection title={l.apiAccess} items={textList(lang, scenario.quickIntegration.apiAccess)} />
        </div>
      </section>

      <div className="solution-detail-grid">
        <BulletSection title={l.salesTalkTrack} items={textList(lang, scenario.salesTalkTrack)} />
        <BulletSection title={l.expectedOutcomes} items={textList(lang, scenario.expectedOutcomes)} />
      </div>
    </main>
  );
}
