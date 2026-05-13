import { ArrowRight, ExternalLink, Sparkles } from "lucide-react";
import { trackClick } from "../analytics";
import type { Lang } from "../data/i18n";
import {
  solutionEntries,
  solutionScenarios,
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
    recommended: "Recommended from this entry",
    allScenarios: "Ocho escenarios SMB",
    viewSolution: "Ver solución",
    viewSkill: "Ver demo / skill",
    quickIntegration: "Integración rápida",
    estimator: "Abrir cotizador cloud",
  },
  en: {
    kicker: "Solution Playbook",
    title: "Start from business needs. Deliver with ready-to-use scenarios.",
    body:
      "Explore practical AI and cloud solutions for SMBs, with scenario guidance, GitHub skills, and quick integration paths.",
    recommended: "Recommended from this entry",
    allScenarios: "Eight SMB scenarios",
    viewSolution: "View solution",
    viewSkill: "View demo / skill",
    quickIntegration: "Quick integration",
    estimator: "Open cloud estimator",
  },
  zh: {
    kicker: "Solution Playbook",
    title: "Start from business needs. Deliver with ready-to-use scenarios.",
    body:
      "Explore practical AI and cloud solutions for SMBs, with scenario guidance, GitHub skills, and quick integration paths.",
    recommended: "Recommended from this entry",
    allScenarios: "Eight SMB scenarios",
    viewSolution: "View solution",
    viewSkill: "View demo / skill",
    quickIntegration: "Quick integration",
    estimator: "Open cloud estimator",
  },
} satisfies Record<
  Lang,
  {
    kicker: string;
    title: string;
    body: string;
    recommended: string;
    allScenarios: string;
    viewSolution: string;
    viewSkill: string;
    quickIntegration: string;
    estimator: string;
  }
>;

function isValidEntry(entryId?: string): entryId is SolutionEntryId {
  return solutionEntries.some((entry) => entry.id === entryId);
}

function sortScenarios(activeEntry: SolutionEntry) {
  const recommendedIds = new Set(activeEntry.scenarioIds);
  return [...solutionScenarios].sort((left, right) => {
    const leftRecommended = recommendedIds.has(left.id);
    const rightRecommended = recommendedIds.has(right.id);
    if (leftRecommended !== rightRecommended) {
      return leftRecommended ? -1 : 1;
    }
    return solutionScenarios.findIndex((item) => item.id === left.id) - solutionScenarios.findIndex((item) => item.id === right.id);
  });
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
  const recommended = activeEntry.scenarioIds.includes(scenario.id);
  const scenarioEntry = solutionEntries.find((entry) => entry.id === scenario.entryId) ?? activeEntry;

  return (
    <article className={recommended ? "scenario-card recommended" : "scenario-card"}>
      <img src={scenario.heroImage} alt="" loading="lazy" />
      <div className="scenario-card-body">
        <div className="scenario-card-heading">
          <span className="scenario-entry-badge">{textFor(lang, scenarioEntry.title)}</span>
          {recommended ? (
            <span className="scenario-recommended-badge">
              <Sparkles size={14} />
              {l.recommended}
            </span>
          ) : null}
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
        </div>
      </div>
    </article>
  );
}

export function SolutionExplorer({ lang, initialEntryId }: SolutionExplorerProps) {
  const l = labels[lang];
  const activeEntry = solutionEntries.find((entry) => entry.id === initialEntryId) ?? solutionEntries[0];
  const orderedScenarios = sortScenarios(activeEntry);

  return (
    <div className="solution-playbook">
      <section className="solution-playbook-hero">
        <div>
          <span className="section-kicker">{l.kicker}</span>
          <h2>{l.title}</h2>
          <p>{l.body}</p>
        </div>
        <a
          className="secondary-action light"
          href="#/estimator"
          onClick={() =>
            trackClick({
              click_target: "solutions_estimator_cta",
              click_section: "solutions_playbook_hero",
              destination: "#/estimator",
            })
          }
        >
          {l.estimator}
        </a>
      </section>

      <section className="playbook-entry-grid">
        {solutionEntries.map((entry) => {
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
        })}
      </section>

      <section className="scenario-section">
        <div className="section-heading">
          <span className="section-kicker">{l.allScenarios}</span>
          <h3>{textFor(lang, activeEntry.title)}</h3>
          <p>{textFor(lang, activeEntry.summary)}</p>
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
