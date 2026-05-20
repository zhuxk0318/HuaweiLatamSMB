import { ArrowRight, ExternalLink } from "lucide-react";
import { trackClick } from "../analytics";
import type { Lang } from "../data/i18n";
import {
  solutionEntries,
  solutionEntryCards,
  solutionScenarioMap,
  textFor,
  type SolutionEntry,
  type SolutionEntryId,
  type SolutionScenario,
} from "../data/solutions";

type SolutionExplorerProps = {
  lang: Lang;
  initialEntryId?: SolutionEntryId;
};

const labels = {
  es: {
    kicker: "Solution Playbook",
    title: "Start from business needs. Deliver with ready-to-use scenarios.",
    body:
      "Explore practical AI and cloud solutions for SMBs, with scenario guidance, GitHub skills, and quick integration paths.",
    allScenarios: "Escenarios de esta solución",
    viewSolution: "Ver solución",
    viewSkill: "Ver demo / skill",
    quickIntegration: "Integración rápida",
    openOfficial: "Abrir solución oficial",
    externalBadge: "Enlace externo",
  },
  en: {
    kicker: "Solution Playbook",
    title: "Start from business needs. Deliver with ready-to-use scenarios.",
    body:
      "Explore practical AI and cloud solutions for SMBs, with scenario guidance, GitHub skills, and quick integration paths.",
    allScenarios: "Scenarios in this solution area",
    viewSolution: "View solution",
    viewSkill: "View demo / skill",
    quickIntegration: "Quick integration",
    openOfficial: "Open official solution",
    externalBadge: "External link",
  },
  zh: {
    kicker: "方案手册",
    title: "从业务需求出发，用可直接落地的场景推进交付。",
    body:
      "浏览适合 SMB 的 AI 与云方案，结合场景说明、GitHub 技能和快速集成路径。",
    allScenarios: "该方案域中的场景",
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
    allScenarios: string;
    viewSolution: string;
    viewSkill: string;
    quickIntegration: string;
    openOfficial: string;
    externalBadge: string;
  }
>;

function isValidEntry(entryId?: string): entryId is SolutionEntryId {
  return solutionEntries.some((entry) => entry.id === entryId);
}

function entryScenarios(activeEntry: SolutionEntry) {
  return activeEntry.scenarioIds
    .map((scenarioId) => solutionScenarioMap[scenarioId])
    .filter((scenario): scenario is SolutionScenario => Boolean(scenario));
}

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
                  click_target: "scenario_open_official",
                  click_section: "solutions_scenarios",
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
                  click_target: "scenario_view_solution",
                  click_section: "solutions_scenarios",
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
                  click_target: "scenario_view_skill",
                  click_section: "solutions_scenarios",
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
                  click_target: "scenario_quick_integration",
                  click_section: "solutions_scenarios",
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

export function SolutionExplorer({ lang, initialEntryId }: SolutionExplorerProps) {
  const l = labels[lang];
  const activeEntry = solutionEntries.find((entry) => entry.id === initialEntryId) ?? solutionEntries[0];
  const orderedScenarios = entryScenarios(activeEntry);

  return (
    <div className="solution-playbook">
      <section className="solution-playbook-hero">
        <div>
          <span className="section-kicker">{l.kicker}</span>
          <h2>{l.title}</h2>
          <p>{l.body}</p>
        </div>
      </section>

      <section className="playbook-entry-grid">
        {solutionEntryCards.map((card) => {
          if (card.kind === "internal") {
            const entry = card.entry;
            const active = entry.id === activeEntry.id;
            return (
              <a
                className={active ? "playbook-entry-card active" : "playbook-entry-card"}
                href={`#/solutions?entry=${entry.id}`}
                key={entry.id}
                onClick={() =>
                  trackClick({
                    click_target: "solution_entry_card",
                    click_section: "solutions_entries",
                    destination: `#/solutions?entry=${entry.id}`,
                    entry_id: entry.id,
                  })
                }
              >
                <img src={entry.heroImage} alt="" loading="lazy" />
                <span className="playbook-entry-overlay" />
                <span className="playbook-entry-content">
                  <strong>{textFor(lang, entry.title)}</strong>
                  <small>{textFor(lang, entry.summary)}</small>
                  <span className="tag-row playbook-entry-tags">
                    {entry.tags.map((tag) => (
                      <span className="service-tag strong on-dark" key={tag}>
                        {tag}
                      </span>
                    ))}
                  </span>
                </span>
              </a>
            );
          }
          const url = lang === "es" ? card.externalUrls.es : card.externalUrls.en;
          return (
            <a
              className="playbook-entry-card playbook-entry-card-external"
              href={url}
              key={card.id}
              target="_blank"
              rel="noreferrer"
              onClick={() =>
                trackClick({
                  click_target: "solution_entry_card_external",
                  click_section: "solutions_entries",
                  destination: url,
                  entry_id: card.id,
                })
              }
            >
              <img src={card.heroImage} alt="" loading="lazy" />
              <span className="playbook-entry-overlay" />
              <span className="playbook-entry-content">
                <span className="external-link-badge"><ExternalLink size={12} /> {l.externalBadge}</span>
                <strong>{textFor(lang, card.title)}</strong>
                <small>{textFor(lang, card.summary)}</small>
                <span className="tag-row playbook-entry-tags">
                  {card.tags.map((tag) => (
                    <span className="service-tag strong on-dark" key={tag}>
                      {tag}
                    </span>
                  ))}
                </span>
                <span className="solution-domain-entry-action">
                  {l.openOfficial}
                  <ExternalLink size={16} />
                </span>
              </span>
            </a>
          );
        })}
      </section>

      <section className="scenario-section">
        <div className="section-heading">
          <span className="section-kicker">
            {orderedScenarios.length} {lang === "es" ? "escenarios" : lang === "zh" ? "个场景" : "scenarios"}
          </span>
          <h3>{textFor(lang, activeEntry.title)}</h3>
          <p>{l.allScenarios}</p>
        </div>
        <div className="scenario-grid">
          {orderedScenarios.map((scenario) => (
            <ScenarioCard lang={lang} scenario={scenario} activeEntry={activeEntry} key={scenario.id} />
          ))}
        </div>
      </section>
    </div>
  );
}

export function getValidSolutionEntry(entryId?: string): SolutionEntryId | undefined {
  return isValidEntry(entryId) ? entryId : undefined;
}
