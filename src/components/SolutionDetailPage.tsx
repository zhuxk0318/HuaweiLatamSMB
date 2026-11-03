import {
  ArrowLeft, ArrowRight, ExternalLink, Layers3,
  Cloud, GitBranch, Building2, Database, Server, BarChart3,
  Monitor, Users, Container, Network, Terminal,
  Code2, ShieldCheck, Zap, FlaskConical, GraduationCap, BookOpen,
  GitMerge, Globe, HardDrive, RefreshCw,
  CheckCircle, Settings, HelpCircle,
} from "lucide-react";
import { trackClick } from "../analytics";
import type { Lang } from "../data/i18n";
import { solutionEntries, solutionScenarioMap, textFor, type LocalizedPair } from "../data/solutions";
import { HealthcareSolutionPage } from "./HealthcareSolutionPage";
import { AutoLinkText } from "./AutoLinkText";
import { MigrationScenarioDetailTemplate } from "./MigrationScenario/MigrationScenarioDetailTemplate";
import { getMigrationScenarioTemplateConfig } from "./MigrationScenario/migrationScenarioTemplates";


function renderTextWithLinks(text: string, linkParts?: { label: string; url: string }[]): React.ReactNode {
  if (!linkParts || linkParts.length === 0) return text;
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;
  for (const lp of linkParts) {
    const idx = remaining.indexOf(lp.label);
    if (idx >= 0) {
      if (idx > 0) parts.push(remaining.slice(0, idx));
      parts.push(
        <a key={key++} href={lp.url} className="prereq-inline-link">
          {lp.label}
        </a>
      );
      remaining = remaining.slice(idx + lp.label.length);
    }
  }
  if (remaining) parts.push(remaining);
  return <>{parts}</>;
}

const iconMap: Record<string, React.ComponentType<any>> = {
  Cloud, GitBranch, Building2, Database, Server, BarChart3,
  Monitor, Users, Container, Network, Terminal,
  Code2, ShieldCheck, Zap, FlaskConical, GraduationCap, BookOpen,
  GitMerge, Globe, HardDrive, RefreshCw, Layers3,
};

export const serviceUrlMap: Record<string, string> = {
  CBR: "https://support.huaweicloud.com/intl/en-us/cbr/",
  CCE: "https://support.huaweicloud.com/intl/en-us/cce/",
  CES: "https://support.huaweicloud.com/intl/en-us/ces/",
  "Cloud End Site": "https://support.huaweicloud.com/intl/en-us/cloudend/",
  DEW: "https://support.huaweicloud.com/intl/en-us/dew/",
  DMS: "https://support.huaweicloud.com/intl/en-us/dms/",
  DRS: "https://support.huaweicloud.com/intl/en-us/drs/",
  DWS: "https://support.huaweicloud.com/intl/en-us/dws/",
  DataArts: "https://support.huaweicloud.com/intl/en-us/dataarts/",
  "Direct Connect": "https://support.huaweicloud.com/intl/en-us/dc/",
  ECS: "https://support.huaweicloud.com/intl/en-us/ecs/",
  EIP: "https://support.huaweicloud.com/intl/en-us/eip/",
  ELB: "https://support.huaweicloud.com/intl/en-us/elb/",
  EVS: "https://support.huaweicloud.com/intl/en-us/evs/",
  FunctionGraph: "https://support.huaweicloud.com/intl/en-us/functiongraph/",
  GaussDB: "https://support.huaweicloud.com/intl/en-us/gaussdb/",
  GeminiDB: "https://support.huaweicloud.com/intl/en-us/geminidb/",
  HSS: "https://support.huaweicloud.com/intl/en-us/hss/",
  "Identity Center": "https://support.huaweicloud.com/intl/en-us/identitycenter/",
  MRS: "https://support.huaweicloud.com/intl/en-us/mrs/",
  MgC: "https://support.huaweicloud.com/intl/en-us/mgc/",
  "ModelArts MaaS": "https://support.huaweicloud.com/intl/en-us/modelarts/",
  "NAT Gateway": "https://support.huaweicloud.com/intl/en-us/natgateway/",
  OBS: "https://support.huaweicloud.com/intl/en-us/obs/",
  OMS: "https://support.huaweicloud.com/intl/en-us/oms/",
  RDS: "https://support.huaweicloud.com/intl/en-us/rds/",
  "SFS Turbo": "https://support.huaweicloud.com/intl/en-us/sfsturbo/",
  SMN: "https://support.huaweicloud.com/intl/en-us/smn/",
  SMS: "https://support.huaweicloud.com/intl/en-us/sms/",
  SDR: "https://support.huaweicloud.com/intl/en-us/sdr/",
  SWR: "https://support.huaweicloud.com/intl/en-us/swr/",
  UGO: "https://support.huaweicloud.com/intl/en-us/ugo/",
  VPC: "https://support.huaweicloud.com/intl/en-us/vpc/",
  VPN: "https://support.huaweicloud.com/intl/en-us/vpn/",
  Workspace: "https://support.huaweicloud.com/intl/en-us/workspace/",
};

type SolutionDetailPageProps = {
  lang: Lang;
  solutionId: string | null;
};

const labels = {
  es: {
    back: "Volver al playbook",
    missing: "Escenario no encontrado",
    missingBody: "Revise el playbook y seleccione uno de los escenarios disponibles.",
    targetCustomers: "Perfiles de cliente",
    painPoints: "Dolores del cliente",
    solutionApproach: "Enfoque Huawei Cloud",
    services: "Servicios recomendados",
    demoSkills: "Demo y skills de GitHub",
    quickIntegration: "Cómo empezar",
    prerequisites: "Lo que necesitarás",
    steps: "Cómo funciona",
    configuration: "Tus opciones",
    apiAccess: "Pruébalo con KooCLI",
    salesTalkTrack: "Preguntas de venta",
    expectedOutcomes: "Resultados esperados",
    conversationGuide: "Preguntas y Resultados",
    qualifyingQuestions: "Preguntas para hacer",
    whatYoullAchieve: "Lo que lograrás",
    migrationExamples: "Ejemplos de Migración",
    introToSolutions: "Introducción a las Soluciones de Huawei",
    awsMigrationTitle: "1. Migración de AWS a Huawei Cloud con asistencia de IA",
    awsMigrationDesc: "Demuestra la migración de infraestructura AWS a Huawei Cloud usando herramientas con IA. Cubre replicación de bases de datos (DRS), migración de object storage (OMS) y migración de servidores (SMS).",
    estimator: "Abrir cotizador cloud",
    sourceSkill: "Abrir Skill en GitHub",
    overview: "Ver todos los escenarios",
    presentation: "Demostracion interactiva",
    sourceMapping: "Mapeo de servicios",
    technicalReferences: "Referencias técnicas",
    viewOnGitHub: "Ver en GitHub",
    presentationComingSoon: "Presentación próximamente",
    relatedSkills: "Skills relacionados",
    relatedTools: "Tools relacionados",
    tools: "Tools",
    skills: "Skills",
  },
  en: {
    back: "Back to playbook",
    missing: "Scenario not found",
    missingBody: "Review the playbook and select one of the available scenarios.",
    painPoints: "Customer pain points",
    solutionApproach: "Huawei Cloud approach",
    services: "Recommended services",
    demoSkills: "Demo and GitHub skills",
    quickIntegration: "How to start with AI",
    prerequisites: "Prerequisites",
    steps: "Integration steps",
    configuration: "Configuration notes",
    apiAccess: "Try it with KooCLI",
    salesTalkTrack: "Sales talk track",
    expectedOutcomes: "Expected outcomes",
    conversationGuide: "Questions & Results",
    qualifyingQuestions: "Questions to ask",
    whatYoullAchieve: "What you'll achieve",
    migrationExamples: "Migration Examples",
    introToSolutions: "Introduction to Huawei Solutions",
    awsMigrationTitle: "1. AWS to Huawei Cloud Migration with AI Assistance",
    awsMigrationDesc: "Demonstrates migrating AWS infrastructure to Huawei Cloud using AI-assisted tools. Covers database replication (DRS), object storage migration (OMS), and server migration (SMS).",
    targetCustomers: "Customer Profiles",
    estimator: "Open cloud estimator",
    sourceSkill: "Open GitHub Skill",
    overview: "Browse all scenarios",
    presentation: "Interactive Demo",
    sourceMapping: "Service Mapping",
    technicalReferences: "Technical References",
    viewOnGitHub: "View on GitHub",
    presentationComingSoon: "Presentation coming soon",
    relatedSkills: "Related Skills",
    relatedTools: "Related Tools",
    tools: "Tools",
    skills: "Skills",
  },
  zh: {
    back: "返回方案手册",
    missing: "未找到方案场景",
    missingBody: "请返回方案手册并选择可用场景。",
    targetCustomers: "客户画像",
    painPoints: "客户痛点",
    solutionApproach: "方案路径",
    services: "推荐能力",
    demoSkills: "Demo 与 GitHub Skill",
    quickIntegration: "如何开始",
    prerequisites: "你需要什么",
    steps: "如何运作",
    configuration: "你的选择",
    apiAccess: "使用 KooCLI 体验",
    salesTalkTrack: "销售沟通问题",
    expectedOutcomes: "预期结果",
    conversationGuide: "问题与结果",
    qualifyingQuestions: "提问",
    whatYoullAchieve: "成果",
    migrationExamples: "迁移示例",
    introToSolutions: "华为解决方案介绍",
    awsMigrationTitle: "1. 使用AI辅助从AWS迁移到华为云",
    awsMigrationDesc: "演示使用AI辅助工具将AWS基础设施迁移到华为云。涵盖数据库复制（DRS）、对象存储迁移（OMS）和服务器迁移（SMS）。",
    estimator: "打开云报价器",
    sourceSkill: "打开 GitHub Skill",
    overview: "浏览全部场景",
    presentation: "交互式演示",
    sourceMapping: "服务映射",
    technicalReferences: "技术参考",
    viewOnGitHub: "在 GitHub 上查看",
    presentationComingSoon: "演示即将推出",
    relatedSkills: "相关技能",
    relatedTools: "相关工具",
    tools: "工具",
    skills: "技能",
  },
  pg: {
    back: "Back to playbook",
    missing: "Scenario not found",
    missingBody: "Review the playbook and select one of the available scenarios.",
    targetCustomers: "Perfis de Cliente",
    painPoints: "Customer pain points",
    solutionApproach: "Huawei Cloud approach",
    services: "Recommended services",
    demoSkills: "Demo and GitHub skills",
    quickIntegration: "How to get started",
    prerequisites: "What you'll need",
    steps: "How it works",
    configuration: "Your options",
    apiAccess: "Experimente com KooCLI",
    salesTalkTrack: "Sales talk track",
    expectedOutcomes: "Expected outcomes",
    conversationGuide: "Perguntas e Resultados",
    qualifyingQuestions: "Perguntas a fazer",
    whatYoullAchieve: "O que você alcançará",
    migrationExamples: "Exemplos de Migração",
    introToSolutions: "Introdução às Soluções da Huawei",
    awsMigrationTitle: "1. Migração de AWS para Huawei Cloud com assistência de IA",
    awsMigrationDesc: "Demonstra a migração de infraestrutura AWS para Huawei Cloud usando ferramentas com IA. Cobre replicação de banco de dados (DRS), migração de object storage (OMS) e migração de servidores (SMS).",
    estimator: "Open cloud estimator",
    sourceSkill: "Open GitHub Skill",
    overview: "Browse all scenarios",
    presentation: "Interactive Demo",
    sourceMapping: "Service Mapping",
    technicalReferences: "Technical References",
    viewOnGitHub: "Ver no GitHub",
    presentationComingSoon: "Apresentação em breve",
    relatedSkills: "Skills relacionados",
    relatedTools: "Ferramentas relacionadas",
    tools: "Ferramentas",
    skills: "Skills",
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
  const primarySkill = scenario.demoSkillLinks[0];
  const isAiSkill = scenario.entryId === "ai-maas" && Boolean(scenario.categoryId && primarySkill);
  const migrationScenarioTemplateConfig = window.location.hash.includes("from=migration")
    ? getMigrationScenarioTemplateConfig(scenario)
    : undefined;

  if (migrationScenarioTemplateConfig) {
    return (
      <MigrationScenarioDetailTemplate
        lang={lang}
        config={migrationScenarioTemplateConfig}
      />
    );
  }

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
          {scenario.recommendedServices.map((service) => {
            const url = serviceUrlMap[service];
            return url ? (
              <a className="service-tag strong service-tag-link" key={service}
                href={url} target="_blank" rel="noreferrer"
                onClick={() => trackClick({ click_target: "service_tag", click_section: "solution_detail", destination: url, entry_id: entry.id, scenario_id: scenario.id })}
              >
                {service}
              </a>
            ) : (
              <span className="service-tag strong" key={service}>
                {service}
              </span>
            );
          })}
        </div>
        <div className="hero-actions">
          {isAiSkill && primarySkill ? (
            <a
              className="primary-action"
              href={primarySkill.url}
              target="_blank"
              rel="noreferrer"
              onClick={() =>
                trackClick({
                  click_target: "solution_detail_skill_primary",
                  click_section: "solution_detail_hero",
                  destination: primarySkill.url,
                  entry_id: entry.id,
                  scenario_id: scenario.id,
                })
              }
            >
              {l.sourceSkill}
              <ExternalLink size={18} />
            </a>
          ) : (
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
          )}
          <a
            className="secondary-action light"
            href={`#/solutions?entry=${entry.id}`}
            onClick={() =>
              trackClick({
                click_target: "solution_detail_overview_cta",
                click_section: "solution_detail_hero",
                destination: `#/solutions?entry=${entry.id}`,
                entry_id: entry.id,
                scenario_id: scenario.id,
              })
            }
          >
            {l.overview}
          </a>
        </div>
      </section>

{((scenario.migrationExamples && scenario.migrationExamples.length > 0) || (scenario.migrationRelatedTools && scenario.migrationRelatedTools.length > 0) || scenario.migrationMainExample) && (
        <section className="solution-detail-card presentation-embed-section">
          <h2>{solutionId === "cloud-to-cloud-migration" ? l.migrationExamples : l.introToSolutions}</h2>

          {solutionId === "cloud-to-cloud-migration" && (
            <div className="presentation-example">
              <h3>{l.awsMigrationTitle}</h3>
              <p className="presentation-example-desc">{l.awsMigrationDesc}</p>
              <div className="presentation-embed-wrap">
                <iframe
                  src="/presentations/demo-migration.pdf"
                  className="presentation-iframe"
                  title="Migration Demo Presentation"
                  loading="lazy"
                />
              </div>
            </div>
          )}

          {scenario.presentationUrl && (
            <div className="presentation-example">
              <div className="presentation-embed-wrap">
                <iframe
                  src={scenario.presentationUrl}
                  className="presentation-iframe"
                  title="Migration Presentation"
                  loading="lazy"
                />
              </div>
            </div>
          )}

          {scenario.migrationMainExample && (
            <div className="presentation-main-card">
              <h3>{textFor(lang, scenario.migrationMainExample.title)}</h3>
              <p className="presentation-main-card-desc">{textFor(lang, scenario.migrationMainExample.description)}</p>
              <a
                href={scenario.migrationMainExample.githubUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="presentation-github-link"
              >
                <ExternalLink size={16} />
                {l.viewOnGitHub}
              </a>
            </div>
          )}

          {scenario.migrationRelatedTools && scenario.migrationRelatedTools.length > 0 && (
            <>
              <h3 className="presentation-related-skills-title">{solutionId === "cloud-to-cloud-migration" ? l.relatedTools : l.tools}</h3>
              <div className="presentation-link-cards">
                {scenario.migrationRelatedTools.map((tool, i) => (
                  <div className="presentation-link-card" key={i}>
                    <h3>{textFor(lang, tool.title)}{tool.beta && <span className="beta-badge">Beta</span>}</h3>
                    <p className="presentation-link-card-desc">{textFor(lang, tool.description)}</p>
                    <a
                      href={tool.githubUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="presentation-github-link"
                    >
                      <ExternalLink size={16} />
                      {l.viewOnGitHub}
                    </a>
                  </div>
                ))}
              </div>
            </>
          )}

          {scenario.migrationExamples && scenario.migrationExamples.length > 0 && (
            <>
              <h3 className="presentation-related-skills-title">{solutionId === "cloud-to-cloud-migration" ? l.relatedSkills : l.skills}</h3>
              <div className="presentation-link-cards">
                {scenario.migrationExamples.map((ex, i) => (
                  <div className="presentation-link-card" key={i}>
                    <h3>{textFor(lang, ex.title)}</h3>
                    <p className="presentation-link-card-desc">{textFor(lang, ex.description)}</p>
                    <a
                      href={ex.githubUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="presentation-github-link"
                    >
                      <ExternalLink size={16} />
                      {l.viewOnGitHub}
                    </a>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      )}

      <section className="solution-detail-card">
        <h2>{l.targetCustomers}</h2>
        {"icon" in scenario.targetCustomers[0] ? (
          <div className="who-needs-grid">
            {scenario.targetCustomers.map((c, i) => {
              if (!("icon" in c)) return null;
              const Icon = iconMap[c.icon] ?? Users;
              return (
                <div className="who-needs-card" key={i}>
                  <Icon size={28} className="who-needs-icon" />
                  <p className="who-needs-who">{textFor(lang, c.who)}</p>
                  <p className="who-needs-pain">{textFor(lang, c.pain)}</p>
                </div>
              );
            })}
          </div>
        ) : (
          <ul className="detail-bullet-list">
            {scenario.targetCustomers.map((c, i) => (
              <li key={i}>
                <span className="detail-bullet-dot" />
                <span>{textFor(lang, c as LocalizedPair)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="solution-detail-card">
        <h2>{l.solutionApproach}</h2>
        <ul className="detail-bullet-list">
          {scenario.solutionApproach.map((item, idx) => (
            <li key={idx}>
              <span className="detail-bullet-dot" />
              <div className="approach-bullet-content">
                <span>{textFor(lang, item)}</span>
                {item.replaces && (
                  <p className="approach-replaces">{textFor(lang, item.replaces)}</p>
                )}
                {item.referenceLinks && item.referenceLinks.length > 0 && (
                  <div className="approach-refs">
                    {item.referenceLinks.map((ref) => (
                      <a
                        className="approach-ref-link"
                        href={ref.url}
                        target="_blank"
                        rel="noreferrer"
                        key={ref.url}
                        onClick={() =>
                          trackClick({
                            click_target: "solution_detail_approach_ref",
                            click_section: "solution_detail_approach",
                            destination: ref.url,
                            entry_id: entry.id,
                            scenario_id: scenario.id,
                          })
                        }
                      >
                        <ExternalLink size={14} />
                        {ref.label}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
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

      <section id="integration" className="solution-detail-card">
        <div className="panel-title">
          <Layers3 size={20} />
          <h2>{l.quickIntegration}</h2>
        </div>

        <div className="qi-prereqs">
          <h3>{l.prerequisites}</h3>
          {scenario.quickIntegration.prerequisites.map((p, idx) => (
            <div className="qi-prereq-item" key={idx}>
              <CheckCircle size={18} className="qi-check" />
              <span>
                {p.linkParts ? renderTextWithLinks(textFor(lang, p), p.linkParts) : textFor(lang, p)}
                {p.link && (
                  <a className="prereq-link" href={p.link.url} target="_blank" rel="noreferrer">
                    <ExternalLink size={12} />
                    {p.link.label}
                  </a>
                )}
              </span>
            </div>
          ))}
        </div>

        <h3 className="qi-section-label">{l.steps}</h3>
        <div className="qi-timeline">
          {scenario.quickIntegration.steps.map((s, idx) => {
            const text = textFor(lang, s);
            const colonIdx = text.indexOf(":");
            const hasTitle = colonIdx > 0 && colonIdx < 40;
            const title = hasTitle ? text.slice(0, colonIdx).trim() : "";
            const desc = hasTitle ? text.slice(colonIdx + 1).trim() : text;
            return (
              <div className="qi-step" key={idx}>
                <div className="qi-step-num">{idx + 1}</div>
                <div className="qi-step-body">
                  {hasTitle && <p className="qi-step-title">{title}</p>}
                  <p className="qi-step-desc"><AutoLinkText text={desc} /></p>
                </div>
              </div>
            );
          })}
        </div>

        <h3 className="qi-section-label">{l.configuration}</h3>
        <div className="qi-options-grid">
          {scenario.quickIntegration.configuration.map((c, idx) => (
            <div className="qi-option" key={idx}>
              <Settings size={16} className="qi-option-icon" />
              <AutoLinkText text={textFor(lang, c)} />
            </div>
          ))}
        </div>

        {scenario.quickIntegration.apiAccess && scenario.quickIntegration.apiAccess.length > 0 && (
          <div className="qi-terminal">
            <h3 className="qi-section-label">{l.apiAccess}</h3>
            {scenario.quickIntegration.apiAccess.map((a, idx) => {
              const full = textFor(lang, a);
              const colonIdx = full.indexOf(": ");
              const desc = colonIdx > 0 ? full.slice(0, colonIdx) : full;
              const cmd = colonIdx > 0 ? full.slice(colonIdx + 2) : "";
              return (
                <div key={idx} className="qi-terminal-line">
                  <AutoLinkText text={desc} className="qi-terminal-desc" />
                  {cmd && <code className="qi-terminal-cmd">$ {cmd}</code>}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="solution-detail-card conversation-guide">
        <h2>{l.conversationGuide}</h2>

        <h3 className="cg-subsection-label">{l.qualifyingQuestions}</h3>
        <div className="cg-questions-grid">
          {scenario.salesTalkTrack.map((q, idx) => (
            <div className="cg-question-card" key={idx}>
              <div className="cg-card-header">
                <span className="cg-num-badge">{idx + 1}</span>
                <HelpCircle size={18} className="cg-question-icon" />
              </div>
              <p><AutoLinkText text={textFor(lang, q)} /></p>
            </div>
          ))}
        </div>

        <div className="cg-divider" />

        <h3 className="cg-subsection-label">{l.whatYoullAchieve}</h3>
        <div className="cg-outcomes-grid">
          {scenario.expectedOutcomes.map((o, idx) => (
            <div className="cg-outcome-card" key={idx}>
              <div className="cg-card-header">
                <span className="cg-num-badge cg-num-badge-green">{idx + 1}</span>
                <CheckCircle size={18} className="cg-outcome-icon" />
              </div>
              <p><AutoLinkText text={textFor(lang, o)} /></p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
