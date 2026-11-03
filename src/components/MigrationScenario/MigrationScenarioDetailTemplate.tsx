
import { useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  Clipboard,
  ClipboardCheck,
  Download,
  ExternalLink,
  FileText,
  Github,
  HelpCircle,
  Layers3,
  PlayCircle,
  Sparkles,
  UserRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { trackClick } from "../../analytics";
import type { Lang } from "../../data/i18n";
import { textFor, type LocalizedPair } from "../../data/solutions";
import { AutoLinkText } from "../AutoLinkText";
import { serviceUrlMap } from "../SolutionDetailPage";
import type {
  MigrationResource,
  MigrationResourceType,
  MigrationScenarioTemplateConfig,
  SkillCloneCommand,
  SkillCloneInfo,
  SkillToolSection,
} from "./migrationScenarioTemplates";

type MigrationScenarioDetailTemplateProps = {
  lang: Lang;
  config: MigrationScenarioTemplateConfig;
};

const uiCopy: Record<Lang, {
  back: string;
  solution: string;
  skill: string;
  howToStart: string;
  resources: string;
  prerequisites: string;
  steps: string;
  tutorialSteps: string;
  configuration: string;
  apiAccess: string;
  needHelp: string;
  faq: string;
  question: string;
  result: string;
  relatedScenarios: string;
  backToMigration: string;
  available: string;
  comingSoon: string;
  browseAllScenarios: string;
  presentation: string;
  howToStartAnchor: string;
  goFurther: string;
  demoVideo: string;
  download: string;
  viewOnGithub: string;
  zipExtractsPrefix: string;
  zipExtractsSuffix: string;
  orUseGitClone: string;
  thenCopySkill: string;
  installToolsHintPrefix: string;
  installToolsHintLink: string;
  installToolsHintSuffix: string;
  wslSetup: string;
  installTool: string;
  quickInstall: string;
  quickInstallDesc: string;
}> = {
  en: {
    back: "Back to Migration Scenarios",
    solution: "Migration Solution",
    skill: "AI Migration Skill",
    howToStart: "How to start with AI",
    resources: "Resources",
    prerequisites: "Prerequisites",
    steps: "General suggested migration steps",
    tutorialSteps: "Tutorial main steps",
    configuration: "Configuration notes",
    apiAccess: "Try it with KooCLI",
    needHelp: "Need Help",
    faq: "FAQ",
    question: "Question",
    result: "Result",
    relatedScenarios: "Related Scenarios",
    backToMigration: "Back to Migration",
    available: "Available",
    comingSoon: "Coming Soon",
    browseAllScenarios: "Browse all scenarios",
    presentation: "Presentation",
    howToStartAnchor: "How to Start",
    goFurther: "Go Further",
    demoVideo: "Demo Video",
    download: "Download",
    viewOnGithub: "View on GitHub",
    zipExtractsPrefix: "The ZIP extracts to a folder named",
    zipExtractsSuffix: "Install it in:",
    orUseGitClone: "or use git clone",
    thenCopySkill: "Then copy the skill to your AI coding tool",
    installToolsHintPrefix: "if you need to install these tools, review",
    installToolsHintLink: "here",
    installToolsHintSuffix: "",
    wslSetup: "WSL Setup",
    installTool: "Install",
    quickInstall: "Quick Install (curl)",
    quickInstallDesc: "Download and extract the skill directly to your tool skill directory:",
  },
  es: {
    back: "Volver a escenarios de migración",
    solution: "Solución de migración",
    skill: "Skill de migración con IA",
    howToStart: "Cómo empezar con IA",
    resources: "Recursos",
    prerequisites: "Prerrequisitos",
    steps: "Pasos generales de migración sugeridos",
    tutorialSteps: "Pasos principales del tutorial",
    configuration: "Notas de configuración",
    apiAccess: "Pruébelo con KooCLI",
    needHelp: "¿Necesita ayuda?",
    faq: "Preguntas frecuentes",
    question: "Pregunta",
    result: "Resultado",
    relatedScenarios: "Escenarios relacionados",
    backToMigration: "Volver a migración",
    available: "Disponible",
    comingSoon: "Próximamente",
    browseAllScenarios: "Ver todos los escenarios",
    presentation: "Presentación",
    howToStartAnchor: "Cómo empezar",
    goFurther: "Ir más allá",
    demoVideo: "Video demo",
    download: "Descargar",
    viewOnGithub: "Ver en GitHub",
    zipExtractsPrefix: "El ZIP se extrae en una carpeta llamada",
    zipExtractsSuffix: "Instálelo en:",
    orUseGitClone: "o use git clone",
    thenCopySkill: "Luego copie el Skill a su herramienta de AI Coding",
    installToolsHintPrefix: "si necesita instalar estas herramientas, revise",
    installToolsHintLink: "aquí",
    installToolsHintSuffix: "",
    wslSetup: "Setup WSL",
    installTool: "Instalar",
    quickInstall: "Instalación Rápida (curl)",
    quickInstallDesc: "Descargue y extraiga el skill directamente al directorio de skills de su herramienta:",
  },
  zh: {
    back: "返回迁移场景",
    solution: "迁移解决方案",
    skill: "AI 迁移技能",
    howToStart: "如何开始",
    resources: "资源",
    prerequisites: "准备工作",
    steps: "通用建议迁移步骤",
    tutorialSteps: "教程主要步骤",
    configuration: "配置说明",
    apiAccess: "使用 KooCLI 试用",
    needHelp: "需要帮助",
    faq: "常见问题",
    question: "问题",
    result: "结果",
    relatedScenarios: "相关迁移场景",
    backToMigration: "返回迁移",
    available: "可用",
    comingSoon: "即将上线",
    browseAllScenarios: "浏览全部场景",
    presentation: "迁移方案",
    howToStartAnchor: "如何开始",
    goFurther: "Go Further",
    demoVideo: "Demo 视频",
    download: "下载",
    viewOnGithub: "在 GitHub 查看",
    zipExtractsPrefix: "ZIP 解压后会得到名为",
    zipExtractsSuffix: "的文件夹，请安装到：",
    orUseGitClone: "或使用 git clone",
    thenCopySkill: "然后将 Skill 复制到你的 AI Coding 工具",
    installToolsHintPrefix: "如果需要安装这些工具，请查看",
    installToolsHintLink: "这里",
    installToolsHintSuffix: "",
    wslSetup: "WSL 设置",
    installTool: "安装",
    quickInstall: "快速安装 (curl)",
    quickInstallDesc: "直接下载并解压技能到您的工具技能目录：",
  },
  pg: {
    back: "Back to Migration Scenarios",
    solution: "Migration Solution",
    skill: "AI Migration Skill",
    howToStart: "How to start with AI",
    resources: "Resources",
    prerequisites: "Prerequisites",
    steps: "General suggested migration steps",
    tutorialSteps: "Tutorial main steps",
    configuration: "Configuration notes",
    apiAccess: "Try it with KooCLI",
    needHelp: "Need Help",
    faq: "FAQ",
    question: "Question",
    result: "Result",
    relatedScenarios: "Related Scenarios",
    backToMigration: "Back to Migration",
    available: "Available",
    comingSoon: "Coming Soon",
    browseAllScenarios: "Browse all scenarios",
    presentation: "Presentation",
    howToStartAnchor: "How to Start",
    goFurther: "Go Further",
    demoVideo: "Demo Video",
    download: "Download",
    viewOnGithub: "View on GitHub",
    zipExtractsPrefix: "The ZIP extracts to a folder named",
    zipExtractsSuffix: "Install it in:",
    orUseGitClone: "or use git clone",
    thenCopySkill: "Then copy the skill to your AI coding tool",
    installToolsHintPrefix: "if you need to install these tools, review",
    installToolsHintLink: "here",
    installToolsHintSuffix: "",
    wslSetup: "WSL Setup",
    installTool: "Install",
    quickInstall: "Instalação Rápida (curl)",
    quickInstallDesc: "Baixe e extraia a skill diretamente para o diretório de skills da sua ferramenta:",
  },
};

const resourceIcons: Record<MigrationResourceType, LucideIcon> = {
  ppt: FileText,
  demo: PlayCircle,
  skill: Github,
  "lab-guide": Layers3,
  faq: HelpCircle,
  architecture: Sparkles,
  checklist: CheckCircle,
  video: PlayCircle,
};

function asText(lang: Lang, copy: LocalizedPair) {
  return textFor(lang, copy);
}

function ResourceCard({
  lang,
  resource,
  section,
}: {
  lang: Lang;
  resource: MigrationResource;
  section: string;
}) {
  const l = uiCopy[lang];
  const Icon = resourceIcons[resource.resourceType] ?? FileText;
  const resourceLink = resource.link ?? "";
  const isAvailable = resource.status === "available" && resourceLink.length > 0;
  const typeLabel = resource.resourceType.replace("-", " ").toUpperCase();

  return (
    <article className={`migration-resource-card ${isAvailable ? "" : "is-disabled"}`}>
      <div className="migration-resource-card-topline">
        <span className="migration-resource-icon" aria-hidden="true">
          <Icon size={22} />
        </span>
        <span className={`migration-resource-status ${isAvailable ? "available" : "soon"}`}>
          {isAvailable ? l.available : l.comingSoon}
        </span>
      </div>
      <p className="migration-resource-type">{typeLabel}</p>
      <h3>{asText(lang, resource.title)}</h3>
      <p>{asText(lang, resource.description)}</p>
      {isAvailable ? (
        <a
          className="migration-resource-action"
          href={resourceLink}
          target={resourceLink.startsWith("#/") ? undefined : "_blank"}
          rel={resourceLink.startsWith("#/") ? undefined : "noreferrer"}
          onClick={() =>
            trackClick({
              click_target: `migration_resource_${resource.resourceType}`,
              click_section: section,
              destination: resourceLink,
            })
          }
        >
          {asText(lang, resource.buttonText)}
          <ExternalLink size={17} />
        </a>
      ) : (
        <button className="migration-resource-action disabled" type="button" disabled>
          {l.comingSoon}
        </button>
      )}
    </article>
  );
}

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
  return <>{"\n"}{parts}</>;
}

function SimpleList({
  items,
  lang,
}: {
  items: LocalizedPair[];
  lang: Lang;
}) {
  if (!items.length) {
    return null;
  }

  return (
    <ul className="migration-howto-list">
      {items.map((item, index) => {
        const link = (item as any).link;
        return (
          <li key={`${asText(lang, item)}-${index}`}>
            <CheckCircle size={17} />
            <span>
              <AutoLinkText text={asText(lang, item)} />
              {link ? (
                <>
                  {" "}
                  <a href={link.url} target="_blank" rel="noreferrer" className="prereq-inline-link">
                    {link.label}
                  </a>
                </>
              ) : null}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function StepList({
  items,
  lang,
}: {
  items: LocalizedPair[];
  lang: Lang;
}) {
  if (!items.length) {
    return null;
  }

  return (
    <div className="migration-howto-steps">
      {items.map((item, index) => (
        <div className="migration-howto-step" key={`${asText(lang, item)}-${index}`}>
          <span>{index + 1}</span>
          <p>
            <AutoLinkText text={asText(lang, item)} />
          </p>
        </div>
      ))}
    </div>
  );
}

function ScenarioFAQ({
  lang,
  config,
  scenarioId,
}: {
  lang: Lang;
  config: NonNullable<MigrationScenarioTemplateConfig["faq"]>;
  scenarioId: string;
}) {
  const l = uiCopy[lang];
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  return (
    <section className="migration-template-faq-card">
      <div className="migration-faq-intro">
        <span className="section-kicker">{l.faq}</span>
        <h2>{asText(lang, config.title)}</h2>
        <p>{asText(lang, config.subtitle)}</p>
      </div>

      <div className="migration-faq-accordion">
        {config.items.slice(0, 6).map((item, index) => {
          const isOpen = openIndex === index;
          const panelId = `migration-faq-answer-${scenarioId}-${index}`;
          const buttonId = `migration-faq-question-${scenarioId}-${index}`;

          return (
            <article
              className={`migration-faq-item ${isOpen ? "is-open" : ""}`}
              key={`${asText(lang, item.question)}-${index}`}
            >
              <button
                id={buttonId}
                className="migration-faq-question-button"
                type="button"
                aria-expanded={isOpen}
                aria-controls={panelId}
                onClick={() => setOpenIndex(isOpen ? null : index)}
              >
                <span className="migration-faq-question-copy">
                  <span className="migration-faq-index">{`Q${index + 1}`}</span>
                  <span>{asText(lang, item.question)}</span>
                </span>
                <span className="migration-faq-toggle" aria-hidden="true">
                  {isOpen ? "—" : "-"}
                </span>
              </button>
              <div
                id={panelId}
                className="migration-faq-answer-shell"
                role="region"
                aria-labelledby={buttonId}
              >
                <div className="migration-faq-answer-inner">
                  <span className="migration-faq-answer-index">{`A${index + 1}`}</span>
                  <p>{item.result ? asText(lang, item.result) : ""}</p>
                </div>
              </div>
            </article>
          );
        })}

      </div>
    </section>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="migration-copy-btn"
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        });
      }}
      aria-label="Copy to clipboard"
    >
      {copied ? <ClipboardCheck size={15} /> : <Clipboard size={15} />}
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function DemoVideoEmbed({ url, title }: { url: string; title: string }) {
  return (
    <div className="migration-demo-embed">
      <iframe
        src={url}
        title={title}
        width="100%"
        height="100%"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
        loading="lazy"
      />
    </div>
  );
}

const toolNameUrls: Record<string, string> = {
  "OpenCode": "#/solutions/ai-coding-opencode?from=migration",
  "Hermes": "#/solutions/ai-coding-hermes?from=migration",
  "Claude Code": "#/solutions/ai-coding-claude-code?from=migration",
};

function SkillInstallSection({
  lang,
  zipUrl,
  zipLabel,
  repoUrl,
  cloneInfo,
  guideUrl,
  guideLabel,
  labelType,
}: {
  lang: Lang;
  zipUrl: string;
  zipLabel: string;
  repoUrl?: string;
  cloneInfo: SkillCloneInfo;
  guideUrl?: string;
  guideLabel?: string;
  labelType?: "skill" | "wsl-install";
}) {
  const l = uiCopy[lang];
  const isWslInstall = labelType === "wsl-install";

  return (
    <div className="migration-skill-install">
      <div className="migration-skill-install-buttons">
        <a
          className="migration-zip-btn"
          href={zipUrl}
          download
          onClick={() =>
            trackClick({
              click_target: "skill_zip_download",
              click_section: "ai_migration_skill",
              destination: zipUrl,
            })
          }
        >
          <Download size={18} />
          {l.download} {zipLabel} (ZIP)
        </a>

        {guideUrl ? (
          <a
            className="migration-guide-btn"
            href={guideUrl}
            download
            onClick={() =>
              trackClick({
                click_target: "skill_guide_download",
                click_section: "ai_migration_skill",
                destination: guideUrl,
              })
            }
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.6rem 1.2rem",
              borderRadius: "0.5rem",
              background: "#f0f5ff",
              border: "1px solid #d4e0ff",
              color: "#2966ff",
              fontWeight: 600,
              fontSize: "0.9rem",
              textDecoration: "none",
            }}
          >
            <Download size={18} />
            {guideLabel ?? "Download Guide"}
          </a>
        ) : null}

        {repoUrl ? (
          <a
            className="migration-repo-btn"
            href={repoUrl}
            target="_blank"
            rel="noreferrer"
            onClick={() =>
              trackClick({
                click_target: "skill_repo_view",
                click_section: "ai_migration_skill",
                destination: repoUrl,
              })
            }
          >
            <Github size={18} />
            {l.viewOnGithub}
          </a>
        ) : null}
      </div>

      {!isWslInstall && (
        <div className="migration-skill-install-info">
          <p>
            {l.zipExtractsPrefix} <code>{cloneInfo.folderName}</code>
            {lang === "zh" ? l.zipExtractsSuffix : `. ${l.zipExtractsSuffix}`}
          </p>
          <ul>
            {cloneInfo.toolSections.map((section) => (
              <li key={section.toolName}>
                <strong>{section.toolName}:</strong>{" "}
                <code>{section.installPath}</code>
              </li>
            ))}
          </ul>
        </div>
      )}


      {!isWslInstall && zipUrl && (
        <div className="migration-quick-install">
          <p className="migration-quick-install-heading">{l.quickInstall}</p>
          <p className="migration-quick-install-desc">{l.quickInstallDesc}</p>
          {cloneInfo.toolSections.map((section) => {
            const fullUrl = `https://www.huaweilatam.com${zipUrl}`;
            const zipFileName = zipUrl.split("/").pop() ?? "";
            const curlCmd = `curl -LO ${fullUrl} && unzip -o ${zipFileName} -d ${section.installPath}`;
            return (
              <div className="migration-tool-section" key={`quick-${section.toolName}`}>
                <div className="migration-tool-label">
                  {toolNameUrls[section.toolName] ? (
                    <a href={toolNameUrls[section.toolName]} className="prereq-inline-link">{section.toolName}</a>
                  ) : (
                    section.toolName
                  )}
                </div>
                <div className="migration-code-block">
                  <div className="migration-code-line">
                    <div className="migration-code-cmd-row">
                      <code className="migration-code-cmd">{curlCmd}</code>
                      <CopyButton text={curlCmd} />
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="migration-skill-install-divider">
        <span>{isWslInstall ? l.wslSetup : l.orUseGitClone}</span>
      </div>

      <div className="migration-code-block">
        {cloneInfo.generalCommands.map((cmd, i) => (
          <div className="migration-code-line" key={i}>
            <span className="migration-code-comment"># {cmd.comment}</span>
            <div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{cmd.command}</code>
              <CopyButton text={cmd.command} />
            </div>
          </div>
        ))}
      </div>

      <p className="migration-code-section-label">
        {isWslInstall ? `${l.installTool} ${cloneInfo.toolSections[0]?.toolName ?? ""}` : l.thenCopySkill}
      </p>

      {cloneInfo.toolSections.map((section) => (
        <div className="migration-tool-section" key={section.toolName}>
          <div className="migration-tool-label">
              {toolNameUrls[section.toolName] ? (
                <a href={toolNameUrls[section.toolName]} className="prereq-inline-link">{section.toolName}</a>
              ) : (
                section.toolName
              )}
            </div>
          <div className="migration-code-block">
            {section.commands.map((cmd, j) => (
              <div className="migration-code-line" key={j}>
                <span className="migration-code-comment">
                  # {cmd.comment}
                </span>
                <div className="migration-code-cmd-row">
                  <code className="migration-code-cmd">{cmd.command}</code>
                  <CopyButton text={cmd.command} />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

const customStepsLabels: Record<string, Partial<Record<Lang, string>>> = {
  "image-discovery": {
    en: "General Image Discovery Steps",
    es: "Pasos Generales de Descubrimiento de Imágenes",
    zh: "通用镜像发现步骤",
    pg: "General Image Discovery Steps",
  },
  "codearts-deployment": {
    en: "General suggested deployment steps",
    es: "Pasos generales de despliegue sugeridos",
    zh: "通用建议部署步骤",
    pg: "General suggested deployment steps",
  },
  "mrs-deployment": {
    en: "General suggested deployment steps",
    es: "Pasos generales de despliegue sugeridos",
    zh: "通用建议部署步骤",
    pg: "General suggested deployment steps",
  },
  "dws-cluster-deployment": {
    en: "General suggested deployment steps",
    es: "Pasos generales de despliegue sugeridos",
    zh: "通用建议部署步骤",
    pg: "General suggested deployment steps",
  },
  "cbr-backup-restore": {
    en: "General suggested steps for this scenario",
    es: "Pasos generales sugeridos para este escenario",
    zh: "本场景通用建议步骤",
    pg: "General suggested steps for this scenario",
  },
  "sdrs-cross-region-dr": {
    en: "General suggested steps for this scenario",
    es: "Pasos generales sugeridos para este escenario",
    zh: "本场景通用建议步骤",
    pg: "General suggested steps for this scenario",
  },
  "database-usage-operations": {
    en: "General suggested steps for this scenario",
    es: "Pasos generales sugeridos para este escenario",
    zh: "本场景通用建议步骤",
    pg: "General suggested steps for this scenario",
  },
  "ai-coding-opencode": {
    en: "General suggested steps for this scenario",
    es: "Pasos generales sugeridos para este escenario",
    zh: "本场景通用建议步骤",
    pg: "General suggested steps for this scenario",
  },
  "ai-coding-hermes": {
    en: "General suggested steps for this scenario",
    es: "Pasos generales sugeridos para este escenario",
    zh: "本场景通用建议步骤",
    pg: "General suggested steps for this scenario",
  },
  "ai-coding-claude-code": {
    en: "General suggested steps for this scenario",
    es: "Pasos generales sugeridos para este escenario",
    zh: "本场景通用建议步骤",
    pg: "General suggested steps for this scenario",
  },
  "claude-code-litellm-maas": {
    en: "General suggested steps for this scenario",
    es: "Pasos generales sugeridos para este escenario",
    zh: "本场景通用建议步骤",
    pg: "General suggested steps for this scenario",
  },
  "landing-zone": {
    en: "General suggested steps for this scenario",
    es: "Pasos generales sugeridos para este escenario",
    zh: "本场景通用建议步骤",
    pg: "General suggested steps for this scenario",
  },
  "other-scenarios": {
    en: "General suggested steps for this scenario",
    es: "Pasos generales sugeridos para este escenario",
    zh: "本场景通用建议步骤",
    pg: "General suggested steps for this scenario",
  },
};

export function MigrationScenarioDetailTemplate({
  lang,
  config,
}: MigrationScenarioDetailTemplateProps) {
  const l = uiCopy[lang];
  const quick = config.howToStart;
  const stepsLabel = customStepsLabels[config.scenarioId]?.[lang] ?? l.steps;
  const heroCta = config.hero.cta;
  const heroCtaLink = heroCta.link;
  const hasSkillInstall = Boolean(config.skillCloneInfo && config.skillZipUrl);
  const hasVerticalLayout = Boolean(
    config.demoVideoEmbedUrl || hasSkillInstall || config.detailedLayout,
  );

  const toolPrereq = config.skillCloneInfo ? quick.prerequisites[0] : undefined;
  const regularPrereqs = config.skillCloneInfo
    ? quick.prerequisites.slice(1)
    : quick.prerequisites;

  return (
    <main className={`solution-detail-page migration-scenario-template-page migration-scenario-${config.scenarioId}`}>
      <a
        className="back-link migration-template-back"
        href="#/migration"
        onClick={() =>
          trackClick({
            click_target: "migration_template_back",
            click_section: "migration_scenario_detail",
            destination: "#/migration",
            scenario_id: config.scenarioId,
          })
        }
      >
        <ArrowLeft size={17} />
        {l.back}
      </a>

      <section className="migration-template-hero">
        <div className="migration-template-hero-copy">
          <span className="section-kicker">{l.solution}</span>
          <h1>{asText(lang, config.hero.title)}</h1>
          <p>{asText(lang, config.hero.description)}</p>
          {config.recommendedServices?.length ? (
            <div className="tag-row">
              {config.recommendedServices.map((service) => {
                const url = serviceUrlMap[service];
                return url ? (
                  <a
                    className="service-tag strong service-tag-link"
                    key={service}
                    href={url}
                    target="_blank"
                    rel="noreferrer"
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
          ) : null}
          <div className="migration-template-hero-actions">
            {heroCta.status === "available" && heroCtaLink ? (
              <a
                className="migration-template-primary-cta"
                href={hasSkillInstall ? "#migration-ai-skill" : heroCtaLink}
                target={hasSkillInstall ? undefined : "_blank"}
                rel={hasSkillInstall ? undefined : "noreferrer"}
                onClick={(e) => {
                  if (hasSkillInstall) {
                    e.preventDefault();
                    document
                      .getElementById("migration-ai-skill")
                      ?.scrollIntoView({ behavior: "smooth" });
                  }
                  trackClick({
                    click_target: "migration_template_hero_cta",
                    click_section: "migration_scenario_hero",
                    destination: hasSkillInstall
                      ? "#migration-ai-skill"
                      : heroCtaLink,
                    scenario_id: config.scenarioId,
                  });
                }}
              >
                {asText(lang, heroCta.buttonText)}
                <ArrowRight size={18} />
              </a>
            ) : null}
            <div className="migration-template-secondary-actions">
              {hasVerticalLayout ? (
                <>
                  <a
                    className="migration-template-scroll-cta"
                    href="#migration-presentation"
                    onClick={(e) => {
                      e.preventDefault();
                      document
                        .getElementById("migration-presentation")
                        ?.scrollIntoView({ behavior: "smooth" });
                    }}
                  >
                    <FileText size={16} />
                    {l.presentation}
                  </a>
                  <a
                    className="migration-template-scroll-cta"
                    href="#migration-howto-start"
                    onClick={(e) => {
                      e.preventDefault();
                      document
                        .getElementById("migration-howto-start")
                        ?.scrollIntoView({ behavior: "smooth" });
                    }}
                  >
                    <Sparkles size={16} />
                    {l.howToStartAnchor}
                  </a>
                  {config.faq ? (
                    <a
                      className="migration-template-scroll-cta"
                      href="#migration-faq"
                      onClick={(e) => {
                        e.preventDefault();
                        document
                          .getElementById("migration-faq")
                          ?.scrollIntoView({ behavior: "smooth" });
                      }}
                    >
                      <HelpCircle size={16} />
                      {l.faq}
                    </a>
                  ) : null}
                  {(config.scenarioId === "ai-coding-opencode" || config.scenarioId === "ai-coding-claude-code") && (
                    <a
                      className="migration-template-scroll-cta"
                      href="#migration-go-further"
                      onClick={(e) => {
                        e.preventDefault();
                        document
                          .getElementById("migration-go-further")
                          ?.scrollIntoView({ behavior: "smooth" });
                      }}
                    >
                      <Layers3 size={16} />
                      {l.goFurther}
                    </a>
                  )}
                </>
              ) : null}
              <a
                className="migration-template-secondary-cta"
                href="#/migration"
                onClick={() =>
                  trackClick({
                    click_target: "migration_template_browse_all_scenarios",
                    click_section: "migration_scenario_hero",
                    destination: "#/migration",
                    scenario_id: config.scenarioId,
                  })
                }
              >
                {l.browseAllScenarios}
                <ArrowRight size={18} />
              </a>
            </div>
          </div>
        </div>
        <div
          className="migration-template-hero-media"
          style={{ backgroundImage: `url(${config.hero.image})` }}
          role="img"
          aria-label={asText(lang, config.hero.title)}
        />
      </section>

      <section className="migration-template-section" id="migration-presentation">
        <div className="migration-template-section-heading">
          <span className="section-kicker">{l.solution}</span>
          <h2>{l.solution}</h2>
        </div>
        <div className="migration-resource-grid single">
          {config.solutionResources.map((resource) => {
            const resourceLink = resource.link ?? "";
            const canPreviewPpt = resource.resourceType === "ppt"
              && resource.status === "available"
              && resourceLink.length > 0;

            return (
              <div
                className="migration-solution-resource"
                key={`${resource.resourceType}-${asText(lang, resource.title)}`}
              >
                <ResourceCard
                  lang={lang}
                  resource={resource}
                  section="migration_solution"
                />
                {canPreviewPpt ? (
                  <div className="migration-ppt-preview">
                    <iframe
                      src={`${resourceLink}#toolbar=0&navpanes=0&scrollbar=0&zoom=page-fit`}
                      title={asText(lang, resource.title)}
                      loading="lazy"
                    />
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </section>

      <section className="migration-template-section migration-template-skill-section">
        <div className="migration-template-section-heading">
          <span className="section-kicker">{l.resources}</span>
          <h2>{l.skill}</h2>
        </div>

        {hasVerticalLayout ? (
          <div className="migration-template-skill-grid vertical">
            <article className="migration-howto-panel" id="migration-howto-start">
              <div className="migration-howto-heading">
                <Sparkles size={22} />
                <div>
                  <h3>{l.howToStart}</h3>
                </div>
              </div>

              <div className="migration-howto-block">
                <h4>{l.prerequisites}</h4>
                <SimpleList items={regularPrereqs} lang={lang} />
                {toolPrereq ? (
                  <ul className="migration-howto-list">
                    <li>
                      <CheckCircle size={17} />
                      <span>
                        {asText(lang, toolPrereq)}
                        {(toolPrereq as any).link ? (
                          <>
                            {" "}
                            <a href={(toolPrereq as any).link.url} target="_blank" rel="noreferrer" className="prereq-inline-link">
                              {(toolPrereq as any).link.label}
                            </a>
                          </>
                        ) : null}
                      </span>
                      {(toolPrereq as any).linkParts && (toolPrereq as any).linkParts.some((lp: any) => lp.url) ? (
                        <ul className="migration-prereq-sublist">
                          {(toolPrereq as any).linkParts.filter((lp: any) => lp.url).map((lp: any, i: number) => (
                            <li key={`prereq-sub-${i}`}>
                              <a href={lp.url} className="prereq-sublist-link">
                                {lang === "es"
                                  ? `Aprenda a configurar ${lp.label} y skills para migración`
                                  : lang === "zh"
                                  ? `了解如何配置 ${lp.label} 和迁移技能`
                                  : lang === "pg"
                                  ? `Aprenda a configurar ${lp.label} e skills para migração`
                                  : `Learn how to configure ${lp.label} and skills for migration`}
                              </a>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </li>
                  </ul>
                ) : null}
              </div>

              {(quick as any).requiredMcpServers ? (
                <div className="migration-howto-block">
                  <h4>{lang === "es" ? "Servidores MCP requeridos" : "Required MCP servers"}</h4>
                  <p style={{ marginBottom: "12px", color: "#4b5563", fontSize: "0.92rem" }}>
                    {asText(lang, (quick as any).requiredMcpServers.intro)}
                  </p>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
                    <thead>
                      <tr style={{ borderBottom: "2px solid rgba(17,24,39,0.1)" }}>
                        <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 700 }}>MCP</th>
                        <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 700 }}>{lang === "es" ? "Propósito" : "Purpose"}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(quick as any).requiredMcpServers.servers.map((srv: any, i: number) => (
                        <tr key={`mcp-${i}`} style={{ borderBottom: "1px solid rgba(17,24,39,0.06)" }}>
                          <td style={{ padding: "8px 12px", fontWeight: 600, fontFamily: "monospace" }}>{srv.mcp}</td>
                          <td style={{ padding: "8px 12px", color: "#374151" }}>{asText(lang, srv.purpose)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p style={{ marginTop: "10px", fontSize: "0.82rem", color: "#6b7280", fontStyle: "italic" }}>
                    {asText(lang, (quick as any).requiredMcpServers.note)}
                  </p>
                </div>
              ) : null}

              {config.demoVideoEmbedUrl ? (
                <div className="migration-howto-block">
                  <h4>{l.demoVideo}</h4>
                  <DemoVideoEmbed
                    url={config.demoVideoEmbedUrl}
                    title={l.demoVideo}
                  />
                </div>
              ) : null}

              <div className="migration-howto-block">
                <h4>{config.skillCloneInfoLabelType === "wsl-install" ? l.tutorialSteps : stepsLabel}</h4>
                <StepList items={quick.steps} lang={lang} />
              </div>

              {(quick as any).whatScenarioDoesNotDo ? (
                <div className="migration-howto-block">
                  <h4>{lang === "es" ? "Lo que este escenario no hace" : "What this scenario does not do"}</h4>
                  <p style={{ whiteSpace: "pre-line", color: "#374151", fontSize: "0.9rem", lineHeight: 1.6 }}>
                    {asText(lang, (quick as any).whatScenarioDoesNotDo)}
                  </p>
                </div>
              ) : null}
            </article>

            {config.skillCloneInfo && config.skillZipUrl ? (
              <div className="migration-skill-install-wrapper" id="migration-ai-skill">
                <div className="migration-howto-heading">
                  <Github size={22} />
                  <div>
                    <h3>AI Skill</h3>
                  </div>
                </div>
                <SkillInstallSection
                  lang={lang}
                  zipUrl={config.skillZipUrl}
                  zipLabel={config.skillZipLabel ?? "AI Skill"}
                  repoUrl={config.skillRepoUrl}
                  cloneInfo={config.skillCloneInfo}
                  guideUrl={config.skillGuideUrl}
                  guideLabel={config.skillGuideLabel}
                  labelType={config.skillCloneInfoLabelType}
                />

                {(quick as any).startingPrompt ? (
                  <div className="migration-howto-block" style={{ marginTop: "20px" }}>
                    <h4>{lang === "es" ? "Iniciando la migración" : "Starting the migration"}</h4>
                    <p style={{ marginBottom: "12px", color: "#4b5563", fontSize: "0.92rem" }}>
                      {asText(lang, (quick as any).startingPrompt.intro)}
                    </p>
                    <pre style={{
                      background: "#0d1117", color: "#c9d1d9", padding: "16px",
                      borderRadius: "8px", fontSize: "0.82rem", lineHeight: 1.5,
                      overflowX: "auto", whiteSpace: "pre-wrap", fontFamily: "monospace"
                    }}>
                      {(quick as any).startingPrompt.code}
                    </pre>
                  </div>
                ) : null}

                {(quick as any).whatSkillAsks ? (
                  <div className="migration-howto-block" style={{ marginTop: "16px" }}>
                    <h4>{lang === "es" ? "Lo que el skill le pedirá" : "What the skill will ask you for"}</h4>
                    <p style={{ whiteSpace: "pre-line", color: "#374151", fontSize: "0.9rem", lineHeight: 1.6 }}>
                      {asText(lang, (quick as any).whatSkillAsks)}
                    </p>
                  </div>
                ) : null}
              </div>
            ) : null}

          </div>
        ) : (
        <div className="migration-template-skill-grid">
          <article className="migration-howto-panel">
            <div className="migration-howto-heading">
              <Sparkles size={22} />
              <div>
                <h3>{l.howToStart}</h3>
              </div>
            </div>

            <div className="migration-howto-block">
              <h4>{l.prerequisites}</h4>
              <SimpleList items={quick.prerequisites} lang={lang} />
            </div>

            <div className="migration-howto-block">
              <h4>{config.skillCloneInfoLabelType === "wsl-install" ? l.tutorialSteps : stepsLabel}</h4>
              <StepList items={quick.steps} lang={lang} />
            </div>

          </article>
        </div>
        )}
      </section>

      {config.scenarioId === "ai-coding-opencode" && (
        <section className="migration-template-section" id="migration-go-further">
          <div className="migration-template-section-heading">
            <span className="section-kicker">{l.resources}</span>
            <h2>Going Further</h2>
          </div>
          <div className="migration-howto-panel">

            {/* ── Docker Demo ── */}
            <h3 style={{ marginTop: 0, marginBottom: "8px" }}>Docker Demo: OpenCode + MaaS + CCI Migration</h3>
            <p style={{ fontSize: "15px", lineHeight: "1.7", color: "#444", marginBottom: "16px" }}>
              Run a complete AI-assisted migration demo inside a Docker container.
              The container starts clean — you install everything step by step,
              then use OpenCode to migrate a Docker Compose app to Huawei Cloud CCI.
            </p>

            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "20px" }}>
              <a href="/downloads/Dockerfile" download className="presentation-github-link" style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                <Download size={15} /> Dockerfile
              </a>
              <a href="/downloads/sample-compose.yaml" download className="presentation-github-link" style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                <Download size={15} /> sample-compose.yaml
              </a>
            </div>

            <p className="migration-code-section-label">1. Get your Huawei Cloud MaaS API Key</p>
            <p style={{ fontSize: "13px", color: "#444", margin: "0 0 12px", lineHeight: "1.7" }}>
              The MaaS API key authenticates OpenCode with Huawei Cloud ModelArts MaaS models (DeepSeek, GLM, etc.).
            </p>
            <div style={{ fontSize: "13px", color: "#444", lineHeight: "1.8", margin: "0 0 8px", paddingLeft: "16px" }}>
              <strong>a.</strong> Go to the <a href="https://console-intl.huaweicloud.com/modelarts/?region=ap-southeast-1#/model-studio/square" target="_blank" rel="noopener noreferrer" style={{ color: "#c7000b", textDecoration: "underline" }}>ModelArts MaaS console</a>.<br/>
              <strong>b.</strong> If you have not subscribed to any models yet, click <strong>Subscribe</strong> on at least one model
              (recommended: <code>DeepSeek-V4.1-Flash</code> or <code>GLM-5.3</code>).<br/>
              <strong>c.</strong> Go to <strong>API Keys</strong> in the left navigation panel and click <strong>Create API Key</strong>.<br/>
              <strong>d.</strong>               Copy the generated key (format <code>sk-...</code>) — you will pass it as <code>MAAS_API_KEY</code> in step 4.<br/>
              <strong>e.</strong> The API base URL is <code>https://api-ap-southeast-1.modelarts-maas.com/openai/v1</code> (region <code>ap-southeast-1</code>).
            </div>

            <p className="migration-code-section-label">2. Get your Huawei Cloud AK/SK</p>
            <p style={{ fontSize: "13px", color: "#444", margin: "0 0 12px", lineHeight: "1.7" }}>
              The Access Key (AK) and Secret Key (SK) authenticate KooCLI and the hcloud MCP server with your Huawei Cloud account.
            </p>
            <div style={{ fontSize: "13px", color: "#444", lineHeight: "1.8", margin: "0 0 8px", paddingLeft: "16px" }}>
              <strong>a.</strong>               Go to <a href="https://console.huaweicloud.com/iam/#/accessEcsAccessKey" target="_blank" rel="noopener noreferrer" style={{ color: "#c7000b", textDecoration: "underline" }}>IAM → My Credentials → Access Keys</a>.<br/>
              <strong>b.</strong>               Click <strong>Create Access Key</strong>. Download the CSV file — the <strong>Secret Key</strong> is shown only once.<br/>
              <strong>c.</strong> You will use these in step 4 below.
            </div>

            <p className="migration-code-section-label">3. Build the Docker image</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`cat > Dockerfile << 'EOF'
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl lsof ca-certificates git python3 python3-venv unzip
ENTRYPOINT ["/bin/bash"]
EOF`}</code>
              <CopyButton text={"cat > Dockerfile << 'EOF'\nFROM ubuntu:24.04\nRUN apt-get update && apt-get install -y --no-install-recommends \\\n    curl lsof ca-certificates git python3 python3-venv unzip\nENTRYPOINT [\"/bin/bash\"]\nEOF"} />
            </div></div></div>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">docker build -t opencode-demo .</code>
              <CopyButton text="docker build -t opencode-demo ." />
            </div></div></div>

            <p className="migration-code-section-label">4. Run a fresh container</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`docker run -it --name demo \
  -e MAAS_API_KEY="YOUR_MAAS_API_KEY" \
  -e HCLOUD_AK="YOUR_AK" \
  -e HCLOUD_SK="YOUR_SK" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --tmpfs /workspace -w /workspace \
  opencode-demo`}</code>
              <CopyButton text={`docker run -it --name demo \
  -e MAAS_API_KEY="YOUR_MAAS_API_KEY" \
  -e HCLOUD_AK="YOUR_AK" \
  -e HCLOUD_SK="YOUR_SK" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --tmpfs /workspace -w /workspace \
  opencode-demo`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              Replace <code>YOUR_MAAS_API_KEY</code>, <code>YOUR_AK</code>, and <code>YOUR_SK</code> with your credentials (from steps 1-2).
              The <code>-e</code> flags pass them as environment variables inside the container.
            </p>

            <p className="migration-code-section-label">5. Inside the container — Install Node.js 24</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`curl -fsSL https://deb.nodesource.com/setup_24.x | bash -\napt-get install -y nodejs`}</code>
              <CopyButton text={`curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
apt-get install -y nodejs`} />
            </div></div></div>

            <p className="migration-code-section-label">6. Install OpenCode</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`curl -fsSL https://opencode.ai/install | bash\nexport PATH="$HOME/.opencode/bin:\${PATH}"`}</code>
              <CopyButton text={`curl -fsSL https://opencode.ai/install | bash\nexport PATH="$HOME/.opencode/bin:\${PATH}"`} />
            </div></div></div>

            <p className="migration-code-section-label">7. Install KooCLI (hcloud)</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`curl -LO "https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz"\ntar -zxvf huaweicloud-cli-linux-amd64.tar.gz\nmkdir -p ~/.local/bin\nmv hcloud /usr/local/bin/hcloud\nexport PATH="$HOME/.local/bin:\${PATH}"`}</code>
              <CopyButton text={`curl -LO "https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz"\ntar -zxvf huaweicloud-cli-linux-amd64.tar.gz\nmkdir -p ~/.local/bin\nmv hcloud /usr/local/bin/hcloud\nexport PATH="$HOME/.local/bin:\${PATH}"`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              The privacy notice and timeouts are configured automatically in the next step.
            </p>

            <p className="migration-code-section-label">8. Configure KooCLI with your AK/SK</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`hcloud configure set \
  --cli-access-key=$HCLOUD_AK \
  --cli-secret-key=$HCLOUD_SK \
  --cli-region=la-north-2 \
  --cli-agree-privacy-statement=true \
  --cli-read-timeout=30 \
  --cli-connect-timeout=10`}</code>
              <CopyButton text={`hcloud configure set \
  --cli-access-key=$HCLOUD_AK \
  --cli-secret-key=$HCLOUD_SK \
  --cli-region=la-north-2 \
  --cli-agree-privacy-statement=true \
  --cli-read-timeout=30 \
  --cli-connect-timeout=10`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              The <code>$HCLOUD_AK</code> and <code>$HCLOUD_SK</code> variables were passed via <code>-e</code> flags in step 4.
            </p>

            <p className="migration-code-section-label">9. Install hcloud-mcp-server (Python)</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`curl -LsSf https://astral.sh/uv/install.sh | sh\nexport PATH="$HOME/.local/bin:\${PATH}"\necho \'export PATH="$HOME/.local/bin:\${PATH}"\' >> ~/.bashrc\nuv venv ~/.venv --python 3.12\ncurl -LO https://www.huaweilatam.com/downloads/hcloud-mcp-server.tar.gz\ntar xzf hcloud-mcp-server.tar.gz\ncd hcloud-mcp-server\nuv pip install . --python ~/.venv/bin/python\ncd ..\nuv pip install --python ~/.venv/bin/python 'mcp<2'\nln -s ~/.venv/bin/hcloud-mcp /usr/local/bin/hcloud-mcp`}</code>
              <CopyButton text={`curl -LsSf https://astral.sh/uv/install.sh | sh\nexport PATH="$HOME/.local/bin:\${PATH}"\necho \'export PATH="$HOME/.local/bin:\${PATH}"\' >> ~/.bashrc\nuv venv ~/.venv --python 3.12\ncurl -LO https://www.huaweilatam.com/downloads/hcloud-mcp-server.tar.gz\ntar xzf hcloud-mcp-server.tar.gz\ncd hcloud-mcp-server\nuv pip install . --python ~/.venv/bin/python\ncd ..\nuv pip install --python ~/.venv/bin/python 'mcp<2'\nln -s ~/.venv/bin/hcloud-mcp /usr/local/bin/hcloud-mcp`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              The <code>curl -LO</code> downloads the hcloud-mcp-server source from this site, then <code>uv pip install .</code> builds and installs it
              (the <code>hcloud-mcp</code> binary is auto-created by <code>pyproject.toml</code>). The <code>mcp&lt;2</code> downgrade is required — hcloud-mcp-server uses the mcp 1.x API.
            </p>

            <p className="migration-code-section-label">10. Create OpenCode config (MaaS + hcloud MCP)</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`mkdir -p ~/.config/opencode
cat > ~/.config/opencode/opencode.json << EOF
{
  "\$schema": "https://opencode.ai/config.json",
  "model": "maas/deepseek-v4.1-flash",
  "small_model": "maas/deepseek-v4-flash",
  "mcp": {
    "hcloud": { "type": "local", "command": ["hcloud-mcp"], "enabled": true }
  },
  "provider": {
    "maas": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Huawei Cloud MaaS",
      "options": {
        "baseURL": "https://api-ap-southeast-1.modelarts-maas.com/openai/v1",
        "apiKey": "$MAAS_API_KEY"
      },
      "models": {
        "deepseek-v4-flash": { "name": "DeepSeek V4 Flash" },
        "deepseek-v4.1-flash": { "name": "DeepSeek V4.1 Flash" },
        "glm-5.1": { "name": "GLM 5.1" },
        "glm-5.2": { "name": "GLM 5.2" },
        "glm-5.3": { "name": "GLM 5.3" }
      }
    }
  }
}
EOF`}</code>
              <CopyButton text={`mkdir -p ~/.config/opencode\ncat > ~/.config/opencode/opencode.json << EOF\n{\n  "$schema": "https://opencode.ai/config.json",\n  "model": "maas/deepseek-v4.1-flash",\n  "small_model": "maas/deepseek-v4-flash",\n  "mcp": {\n    "hcloud": { "type": "local", "command": ["hcloud-mcp"], "enabled": true }\n  },\n  "provider": {\n    "maas": {\n      "npm": "@ai-sdk/openai-compatible",\n      "name": "Huawei Cloud MaaS",\n      "options": {\n        "baseURL": "https://api-ap-southeast-1.modelarts-maas.com/openai/v1",\n        "apiKey": "$MAAS_API_KEY"\n      },\n      "models": {\n        "deepseek-v4-flash": { "name": "DeepSeek V4 Flash" },\n        "deepseek-v4.1-flash": { "name": "DeepSeek V4.1 Flash" },\n        "glm-5.1": { "name": "GLM 5.1" },\n        "glm-5.2": { "name": "GLM 5.2" },\n        "glm-5.3": { "name": "GLM 5.3" }\n      }\n    }\n  }\n}\nEOF`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              The <code>$MAAS_API_KEY</code> variable is substituted from the <code>-e</code> flag in step 4.
              The <code>"model"</code> field is critical — without it, OpenCode defaults to its built-in model.
            </p>

            <p className="migration-code-section-label">11. Run the migration demo</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">opencode</code>
              <CopyButton text="opencode" />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              Inside OpenCode, first verify: ask <em>"What is 2+2?"</em> (tests MaaS) and
              <em>"List the VPCs in my Huawei Cloud account"</em> (tests hcloud MCP).
              Then run the migration with: <em>"I have a docker-compose.yaml — migrate it to CCI"</em>.
            </p>

            <p className="migration-code-section-label">12. Cleanup</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`exit                    # leave the container\ndocker rm -f demo       # remove container`}</code>
              <CopyButton text={`exit
docker rm -f demo`} />
            </div></div></div>

            {/* ── LiteLLM ── */}
            <hr style={{ border: "none", borderTop: "1px solid #e0e0e0", margin: "32px 0 20px" }} />
            <h3 style={{ marginBottom: "8px" }}>LiteLLM Proxy</h3>
            <p style={{ fontSize: "15px", lineHeight: "1.7", color: "#444" }}>
              To go further with a proxy layer for model routing, latency-based fallbacks, and multi-provider support, OpenCode can also be configured with LiteLLM. The LiteLLM + Claude Code demonstration serves as a complete setup guide — the same proxy configuration applies directly to OpenCode.
            </p>
            <a
              href="#/solutions/ai-coding-claude-code?from=migration"
              className="presentation-github-link"
              style={{ display: "inline-flex", alignItems: "center", gap: "6px", marginTop: "12px" }}
              onClick={(e) => {
                e.preventDefault();
                window.location.hash = "/solutions/ai-coding-claude-code?from=migration";
                setTimeout(() => {
                  document.getElementById("migration-go-further")
                    ?.scrollIntoView({ behavior: "smooth" });
                }, 500);
              }}
            >
              <ExternalLink size={16} />
              LiteLLM + Claude Code Guide
            </a>
          </div>
        </section>
      )}
      {config.scenarioId === "ai-coding-hermes" && (
        <section className="migration-template-section" id="migration-go-further">
          <div className="migration-template-section-heading">
            <span className="section-kicker">{l.resources}</span>
            <h2>Going Further</h2>
          </div>
          <div className="migration-howto-panel">

            {/* ── Docker Demo ── */}
            <h3 style={{ marginTop: 0, marginBottom: "8px" }}>Docker Demo: Hermes Agent + MaaS</h3>
            <p style={{ fontSize: "15px", lineHeight: "1.7", color: "#444", marginBottom: "16px" }}>
              Install Hermes Agent from NousResearch inside a Docker container and configure it
              with Huawei Cloud MaaS as the LLM backend. Hermes uses a custom OpenAI-compatible
              provider to route requests to MaaS models like GLM-5.2 and DeepSeek-V4.
            </p>

            <p className="migration-code-section-label">1. Get your Huawei Cloud MaaS API Key</p>
            <p style={{ fontSize: "13px", color: "#444", margin: "0 0 12px", lineHeight: "1.7" }}>
              The MaaS API key authenticates Hermes with Huawei Cloud ModelArts MaaS models.
            </p>
            <div style={{ fontSize: "13px", color: "#444", lineHeight: "1.8", margin: "0 0 8px", paddingLeft: "16px" }}>
              <strong>a.</strong> Go to the <a href="https://console-intl.huaweicloud.com/modelarts/?region=ap-southeast-1#/model-studio/square" target="_blank" rel="noopener noreferrer" style={{ color: "#c7000b", textDecoration: "underline" }}>ModelArts MaaS console</a>.<br/>
              <strong>b.</strong> If you have not subscribed to any models yet, click <strong>Subscribe</strong> on at least one model
              (recommended: <code>GLM-5.3</code> or <code>DeepSeek-V4.1-Flash</code>).<br/>
              <strong>c.</strong> Go to <strong>API Keys</strong> in the left navigation panel and click <strong>Create API Key</strong>.<br/>
              <strong>d.</strong> Copy the generated key (format <code>sk-...</code>) — you will pass it as <code>MAAS_API_KEY</code> in step 4.<br/>
              <strong>e.</strong> The API base URL is <code>https://api-ap-southeast-1.modelarts-maas.com/openai/v1</code> (region <code>ap-southeast-1</code>).
            </div>

            <p className="migration-code-section-label">2. Get your Huawei Cloud AK/SK</p>
            <p style={{ fontSize: "13px", color: "#444", margin: "0 0 12px", lineHeight: "1.7" }}>
              The Access Key (AK) and Secret Key (SK) authenticate KooCLI with your Huawei Cloud account.
            </p>
            <div style={{ fontSize: "13px", color: "#444", lineHeight: "1.8", margin: "0 0 8px", paddingLeft: "16px" }}>
              <strong>a.</strong> Go to <a href="https://console.huaweicloud.com/iam/#/accessEcsAccessKey" target="_blank" rel="noopener noreferrer" style={{ color: "#c7000b", textDecoration: "underline" }}>IAM &rarr; My Credentials &rarr; Access Keys</a>.<br/>
              <strong>b.</strong> Click <strong>Create Access Key</strong>. Download the CSV file — the <strong>Secret Key</strong> is shown only once.<br/>
              <strong>c.</strong> You will use these in step 4 below.
            </div>

            <p className="migration-code-section-label">3. Build the Docker image</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`cat > Dockerfile << 'EOF'
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git python3 python3-venv
ENTRYPOINT ["/bin/bash"]
EOF`}</code>
              <CopyButton text={"cat > Dockerfile << 'EOF'\nFROM ubuntu:24.04\nRUN apt-get update && apt-get install -y --no-install-recommends \\\n    curl ca-certificates git python3 python3-venv\nENTRYPOINT [\"/bin/bash\"]\nEOF"} />
            </div></div></div>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">docker build -t hermes-demo .</code>
              <CopyButton text="docker build -t hermes-demo ." />
            </div></div></div>

            <p className="migration-code-section-label">4. Run a fresh container</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`docker run -it --name demo \
  -e MAAS_API_KEY="YOUR_MAAS_API_KEY" \
  -e HCLOUD_AK="YOUR_AK" \
  -e HCLOUD_SK="YOUR_SK" \
  hermes-demo`}</code>
              <CopyButton text={`docker run -it --name demo \
  -e MAAS_API_KEY="YOUR_MAAS_API_KEY" \
  -e HCLOUD_AK="YOUR_AK" \
  -e HCLOUD_SK="YOUR_SK" \
  hermes-demo`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              Replace <code>YOUR_MAAS_API_KEY</code>, <code>YOUR_AK</code>, and <code>YOUR_SK</code> with your credentials (from steps 1-2).
            </p>

            <p className="migration-code-section-label">5. Install KooCLI (hcloud)</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`curl -LO "https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz"\ntar -zxvf huaweicloud-cli-linux-amd64.tar.gz\nmkdir -p ~/.local/bin\nmv hcloud ~/.local/bin/hcloud\nexport PATH="$HOME/.local/bin:\${PATH}"`}</code>
              <CopyButton text={`curl -LO "https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz"\ntar -zxvf huaweicloud-cli-linux-amd64.tar.gz\nmkdir -p ~/.local/bin\nmv hcloud ~/.local/bin/hcloud\nexport PATH="$HOME/.local/bin:\${PATH}"`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              The privacy notice and timeouts are configured automatically in the next step.
            </p>

            <p className="migration-code-section-label">6. Configure KooCLI with your AK/SK</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`hcloud configure set \
  --cli-access-key=$HCLOUD_AK \
  --cli-secret-key=$HCLOUD_SK \
  --cli-region=la-north-2 \
  --cli-agree-privacy-statement=true \
  --cli-read-timeout=30 \
  --cli-connect-timeout=10`}</code>
              <CopyButton text={`hcloud configure set \
  --cli-access-key=$HCLOUD_AK \
  --cli-secret-key=$HCLOUD_SK \
  --cli-region=la-north-2 \
  --cli-agree-privacy-statement=true \
  --cli-read-timeout=30 \
  --cli-connect-timeout=10`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              Verify with <code>hcloud IAM ListUsersV5</code> — it should return your IAM user list.
            </p>

            <p className="migration-code-section-label">7. Install Hermes Agent</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`git clone --depth 1 https://github.com/NousResearch/hermes-agent.git /usr/local/lib/hermes-agent\ncd /usr/local/lib/hermes-agent\n./setup-hermes.sh\nln -sf ~/.hermes/installs/*/environments/*/venv/bin/hermes ~/.local/bin/hermes`}</code>
              <CopyButton text={`git clone --depth 1 https://github.com/NousResearch/hermes-agent.git /usr/local/lib/hermes-agent\ncd /usr/local/lib/hermes-agent\n./setup-hermes.sh\nln -sf ~/.hermes/installs/*/environments/*/venv/bin/hermes ~/.local/bin/hermes`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              The setup script auto-installs <code>uv</code>, Python 3.11, a virtual environment, and all dependencies.
              It also symlinks the <code>hermes</code> CLI to <code>~/.local/bin/hermes</code>.
              Ensure <code>~/.local/bin</code> is in your <code>PATH</code>.
            </p>

            <p className="migration-code-section-label">8. Install hcloud-mcp-server</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`curl -LsSf https://astral.sh/uv/install.sh | sh\nexport PATH="$HOME/.local/bin:\${PATH}"\nuv venv ~/.venv --python 3.12\ncurl -LO https://www.huaweilatam.com/downloads/hcloud-mcp-server.tar.gz\ntar xzf hcloud-mcp-server.tar.gz\ncd hcloud-mcp-server\nuv pip install . --python ~/.venv/bin/python\ncd ..\nuv pip install --python ~/.venv/bin/python 'mcp<2'\nln -s ~/.venv/bin/hcloud-mcp /usr/local/bin/hcloud-mcp`}</code>
              <CopyButton text={`curl -LsSf https://astral.sh/uv/install.sh | sh\nexport PATH="$HOME/.local/bin:\${PATH}"\nuv venv ~/.venv --python 3.12\ncurl -LO https://www.huaweilatam.com/downloads/hcloud-mcp-server.tar.gz\ntar xzf hcloud-mcp-server.tar.gz\ncd hcloud-mcp-server\nuv pip install . --python ~/.venv/bin/python\ncd ..\nuv pip install --python ~/.venv/bin/python 'mcp<2'\nln -s ~/.venv/bin/hcloud-mcp /usr/local/bin/hcloud-mcp`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              The MCP server exposes hcloud commands as native Hermes tools (<code>mcp_hcloud_list_vpcs</code>, <code>mcp_hcloud_list_servers</code>, etc.).
              The <code>mcp&lt;2</code> downgrade is required — hcloud-mcp-server uses the mcp 1.x API.
            </p>

            <p className="migration-code-section-label">9. Configure Hermes with MaaS + MCP</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`mkdir -p ~/.hermes\ncat > ~/.hermes/config.yaml << 'EOF'\nmodel:\n  default: glm-5.3\n  provider: custom\n  base_url: https://api-ap-southeast-1.modelarts-maas.com/openai/v1\n  api_key: \${HERMES_CUSTOM_API_KEY}\n  api_mode: chat_completions\ndatabase:\n  journal_mode: wal\nagent:\n  max_turns: 500\n  verbose: false\nmcp_servers:\n  hcloud:\n    command: hcloud-mcp\n    transport: stdio\n    timeout: 120\n    connect_timeout: 60\nEOF`}</code>
              <CopyButton text={"mkdir -p ~/.hermes\ncat > ~/.hermes/config.yaml << 'EOF'\nmodel:\n  default: glm-5.3\n  provider: custom\n  base_url: https://api-ap-southeast-1.modelarts-maas.com/openai/v1\n  api_key: ${HERMES_CUSTOM_API_KEY}\n  api_mode: chat_completions\ndatabase:\n  journal_mode: wal\nagent:\n  max_turns: 500\n  verbose: false\nmcp_servers:\n  hcloud:\n    command: hcloud-mcp\n    transport: stdio\n    timeout: 120\n    connect_timeout: 60\nEOF"} />
            </div></div></div>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`echo "HERMES_CUSTOM_API_KEY=\${MAAS_API_KEY}" > ~/.hermes/.env\nchmod 600 ~/.hermes/.env`}</code>
              <CopyButton text={`echo "HERMES_CUSTOM_API_KEY=\${MAAS_API_KEY}" > ~/.hermes/.env\nchmod 600 ~/.hermes/.env`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              The <code>config.yaml</code> sets the model to <code>glm-5.3</code> with a custom provider pointing to MaaS,
              and registers the Huawei Cloud MCP server under <code>mcp_servers.hcloud</code>.
              The <code>.env</code> file maps <code>HERMES_CUSTOM_API_KEY</code> to your <code>MAAS_API_KEY</code> environment variable.
            </p>

            <p className="migration-code-section-label">10. Verify + Launch Hermes</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`export PATH="$HOME/.local/bin:\${PATH}"\nhermes --version\nhermes -z "Hello, list the ECS instances in sa-brazil-1"`}</code>
              <CopyButton text={`export PATH="$HOME/.local/bin:\${PATH}"\nhermes --version\nhermes -z "Hello, list the ECS instances in sa-brazil-1"`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              <code>hermes --version</code> confirms the install. <code>hermes -z "..."</code> tests MaaS connectivity, MCP tool discovery,
              and hcloud command execution in one shot. Hermes automatically discovers the <code>mcp_hcloud_*</code> tools from the MCP server
              registered in step 9.
            </p>

            <p className="migration-code-section-label">11. Cleanup</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`exit\ndocker rm -f demo`}</code>
              <CopyButton text={`exit\ndocker rm -f demo`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              Type <code>exit</code> to leave the container, then remove it with <code>docker rm -f demo</code>.
            </p>

          </div>
        </section>
      )}
      {config.scenarioId === "ai-coding-claude-code" && (
        <section className="migration-template-section" id="migration-go-further">
          <div className="migration-template-section-heading">
            <span className="section-kicker">{l.resources}</span>
            <h2>Going Further</h2>
          </div>
          <div className="migration-howto-panel">

            {/* ── Docker Demo ── */}
            <h3 style={{ marginTop: 0, marginBottom: "8px" }}>Docker Demo: Claude Code + LiteLLM + MaaS</h3>
            <p style={{ fontSize: "15px", lineHeight: "1.7", color: "#444", marginBottom: "16px" }}>
              Install Claude Code inside a Docker container with a LiteLLM proxy that routes
              requests to Huawei Cloud MaaS models. LiteLLM registers Claude-recognized model names
              as aliases mapped to MaaS models — Claude Code thinks it is using Claude models while
              LiteLLM transparently routes to DeepSeek and GLM.
            </p>
            <p style={{ fontSize: "13px", color: "#666", margin: "0 0 20px", lineHeight: "1.7" }}>
              Architecture: <code>Claude Code &rarr; LiteLLM (localhost:4000) &rarr; Huawei Cloud MaaS &rarr; DeepSeek/GLM</code>
            </p>

            <p className="migration-code-section-label">1. Get your Huawei Cloud MaaS API Key</p>
            <p style={{ fontSize: "13px", color: "#444", margin: "0 0 12px", lineHeight: "1.7" }}>
              The MaaS API key authenticates LiteLLM with Huawei Cloud ModelArts MaaS models.
            </p>
            <div style={{ fontSize: "13px", color: "#444", lineHeight: "1.8", margin: "0 0 8px", paddingLeft: "16px" }}>
              <strong>a.</strong> Go to the <a href="https://console-intl.huaweicloud.com/modelarts/?region=ap-southeast-1#/model-studio/square" target="_blank" rel="noopener noreferrer" style={{ color: "#c7000b", textDecoration: "underline" }}>ModelArts MaaS console</a>.<br/>
              <strong>b.</strong> If you have not subscribed to any models yet, click <strong>Subscribe</strong> on at least one model
              (recommended: <code>DeepSeek-V4.1-Flash</code> or <code>GLM-5.3</code>).<br/>
              <strong>c.</strong> Go to <strong>API Keys</strong> in the left navigation panel and click <strong>Create API Key</strong>.<br/>
              <strong>d.</strong> Copy the generated key (format <code>sk-...</code>) — you will pass it as <code>MAAS_API_KEY</code> in step 4.<br/>
              <strong>e.</strong> The API base URL is <code>https://api-ap-southeast-1.modelarts-maas.com/openai/v1</code> (region <code>ap-southeast-1</code>).
            </div>

            <p className="migration-code-section-label">2. Get your Huawei Cloud AK/SK</p>
            <p style={{ fontSize: "13px", color: "#444", margin: "0 0 12px", lineHeight: "1.7" }}>
              The Access Key (AK) and Secret Key (SK) authenticate KooCLI with your Huawei Cloud account.
            </p>
            <div style={{ fontSize: "13px", color: "#444", lineHeight: "1.8", margin: "0 0 8px", paddingLeft: "16px" }}>
              <strong>a.</strong> Go to <a href="https://console.huaweicloud.com/iam/#/accessEcsAccessKey" target="_blank" rel="noopener noreferrer" style={{ color: "#c7000b", textDecoration: "underline" }}>IAM &rarr; My Credentials &rarr; Access Keys</a>.<br/>
              <strong>b.</strong> Click <strong>Create Access Key</strong>. Download the CSV file — the <strong>Secret Key</strong> is shown only once.<br/>
              <strong>c.</strong> You will use these in step 4 below.
            </div>

            <p className="migration-code-section-label">3. Build the Docker image</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`cat > Dockerfile << 'EOF'
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl lsof ca-certificates git python3 python3-venv unzip
ENTRYPOINT ["/bin/bash"]
EOF`}</code>
              <CopyButton text={"cat > Dockerfile << 'EOF'\nFROM ubuntu:24.04\nRUN apt-get update && apt-get install -y --no-install-recommends \\\n    curl lsof ca-certificates git python3 python3-venv unzip\nENTRYPOINT [\"/bin/bash\"]\nEOF"} />
            </div></div></div>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">docker build -t claude-demo .</code>
              <CopyButton text="docker build -t claude-demo ." />
            </div></div></div>

            <p className="migration-code-section-label">4. Run a fresh container</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`docker run -it --name demo \
  -e MAAS_API_KEY="YOUR_MAAS_API_KEY" \
  -e HCLOUD_AK="YOUR_AK" \
  -e HCLOUD_SK="YOUR_SK" \
  claude-demo`}</code>
              <CopyButton text={`docker run -it --name demo \
  -e MAAS_API_KEY="YOUR_MAAS_API_KEY" \
  -e HCLOUD_AK="YOUR_AK" \
  -e HCLOUD_SK="YOUR_SK" \
  claude-demo`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              Replace <code>YOUR_MAAS_API_KEY</code>, <code>YOUR_AK</code>, and <code>YOUR_SK</code> with your credentials (from steps 1-2).
            </p>

            <p className="migration-code-section-label">5. Install Node.js 24</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`curl -fsSL https://deb.nodesource.com/setup_24.x | bash -\napt-get install -y nodejs\nnode --version`}</code>
              <CopyButton text={`curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
apt-get install -y nodejs
node --version`} />
            </div></div></div>

            <p className="migration-code-section-label">6. Install Claude Code</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`npm install -g @anthropic-ai/claude-code\nclaude --version`}</code>
              <CopyButton text={`npm install -g @anthropic-ai/claude-code\nclaude --version`} />
            </div></div></div>

            <p className="migration-code-section-label">7. Install uv + LiteLLM</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`curl -LsSf https://astral.sh/uv/install.sh | sh\nexport PATH="$HOME/.local/bin:\${PATH}"\n~/.local/bin/uv venv ~/litellm-env --python 3.12\n~/.local/bin/uv pip install 'litellm[proxy]' --python ~/litellm-env/bin/python`}</code>
              <CopyButton text={`curl -LsSf https://astral.sh/uv/install.sh | sh\nexport PATH="$HOME/.local/bin:\${PATH}"\n~/.local/bin/uv venv ~/litellm-env --python 3.12\n~/.local/bin/uv pip install 'litellm[proxy]' --python ~/litellm-env/bin/python`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              <code>uv</code> auto-downloads Python 3.12 if needed. The venv at <code>~/litellm-env</code> isolates LiteLLM dependencies.
            </p>

            <p className="migration-code-section-label">8. Create LiteLLM config</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`mkdir -p ~/litellm\ncat > ~/litellm/config.yaml << 'EOF'\nmodel_list:\n  # Claude model aliases -> MaaS models\n  - model_name: claude-haiku-4-20250514\n    litellm_params:\n      model: custom_openai/deepseek-v4.1-flash\n      api_base: https://api-ap-southeast-1.modelarts-maas.com/openai/v1\n      api_key: os.environ/MAAS_API_KEY\n  - model_name: claude-haiku-4-pro-20250514\n    litellm_params:\n      model: custom_openai/glm-5.3\n      api_base: https://api-ap-southeast-1.modelarts-maas.com/openai/v1\n      api_key: os.environ/MAAS_API_KEY\n\nlitellm_settings:\n  master_key: sk-litellm-master\nEOF`}</code>
              <CopyButton text={"mkdir -p ~/litellm\ncat > ~/litellm/config.yaml << 'EOF'\nmodel_list:\n  # Claude model aliases -> MaaS models\n  - model_name: claude-haiku-4-20250514\n    litellm_params:\n      model: custom_openai/deepseek-v4.1-flash\n      api_base: https://api-ap-southeast-1.modelarts-maas.com/openai/v1\n      api_key: os.environ/MAAS_API_KEY\n  - model_name: claude-haiku-4-pro-20250514\n    litellm_params:\n      model: custom_openai/glm-5.3\n      api_base: https://api-ap-southeast-1.modelarts-maas.com/openai/v1\n      api_key: os.environ/MAAS_API_KEY\n\nlitellm_settings:\n  master_key: sk-litellm-master\nEOF"} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              MaaS model aliases (<code>claude-haiku-4-20250514</code> → deepseek-v4.1-flash, <code>claude-haiku-4-pro-20250514</code> → glm-5.3).
              LiteLLM forwards to Huawei Cloud MaaS. The <code>master_key</code> authenticates proxy requests.
            </p>

            <p className="migration-code-section-label">9. Create environment scripts</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`cat > ~/litellm/init_claude_env.sh << 'EOF'\n#!/bin/bash\nexport ANTHROPIC_BASE_URL="http://127.0.0.1:4000"\nexport ANTHROPIC_AUTH_TOKEN="sk-litellm-master"\nexport ANTHROPIC_MODEL="claude-haiku-4-20250514"\nexport ANTHROPIC_SMALL_FAST_MODEL="claude-haiku-4-20250514"\nexport ANTHROPIC_DEFAULT_HAIKU_MODEL="claude-haiku-4-20250514"\nexport ANTHROPIC_DEFAULT_SONNET_MODEL="claude-haiku-4-pro-20250514"\nexport ANTHROPIC_DEFAULT_OPUS_MODEL="claude-haiku-4-pro-20250514"\nexport CLAUDE_CODE_SUBAGENT_MODEL="claude-haiku-4-20250514"\nunset ANTHROPIC_API_KEY\nexport API_TIMEOUT_MS=600000\nEOF\nchmod +x ~/litellm/init_claude_env.sh`}</code>
              <CopyButton text={"cat > ~/litellm/init_claude_env.sh << 'EOF'\n#!/bin/bash\nexport ANTHROPIC_BASE_URL=\"http://127.0.0.1:4000\"\nexport ANTHROPIC_AUTH_TOKEN=\"sk-litellm-master\"\nexport ANTHROPIC_MODEL=\"claude-haiku-4-20250514\"\nexport ANTHROPIC_SMALL_FAST_MODEL=\"claude-haiku-4-20250514\"\nexport ANTHROPIC_DEFAULT_HAIKU_MODEL=\"claude-haiku-4-20250514\"\nexport ANTHROPIC_DEFAULT_SONNET_MODEL=\"claude-haiku-4-pro-20250514\"\nexport ANTHROPIC_DEFAULT_OPUS_MODEL=\"claude-haiku-4-pro-20250514\"\nexport CLAUDE_CODE_SUBAGENT_MODEL=\"claude-haiku-4-20250514\"\nunset ANTHROPIC_API_KEY\nexport API_TIMEOUT_MS=600000\nEOF\nchmod +x ~/litellm/init_claude_env.sh"} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              <strong>Critical:</strong> <code>unset ANTHROPIC_API_KEY</code> prevents Claude Code from trying official Anthropic auth.
              The <code>ANTHROPIC_AUTH_TOKEN</code> must match the <code>master_key</code> in config.yaml.
            </p>

            <p className="migration-code-section-label">10. Start LiteLLM + Claude Code</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`export LITELLM_MASTER_KEY="sk-litellm-master"\nsource ~/litellm-env/bin/activate\nlitellm --config ~/litellm/config.yaml --port 4000 &\nsleep 3\ncurl -s http://127.0.0.1:4000/v1/models -H "Authorization: Bearer sk-litellm-master" | head -5`}</code>
              <CopyButton text={`export LITELLM_MASTER_KEY="sk-litellm-master"\nsource ~/litellm-env/bin/activate\nlitellm --config ~/litellm/config.yaml --port 4000 &\nsleep 3\ncurl -s http://127.0.0.1:4000/v1/models -H "Authorization: Bearer sk-litellm-master" | head -5`} />
            </div></div></div>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`source ~/litellm/init_claude_env.sh\nclaude`}</code>
              <CopyButton text={`source ~/litellm/init_claude_env.sh\nclaude`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              The health check should return a JSON list of models. Then Claude Code launches with all
              requests routed through LiteLLM to MaaS.
            </p>

            <p className="migration-code-section-label">11. Install KooCLI (hcloud)</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`curl -LO "https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz"\ntar -zxvf huaweicloud-cli-linux-amd64.tar.gz\nmkdir -p ~/.local/bin\nmv hcloud ~/.local/bin/hcloud\nexport PATH="$HOME/.local/bin:\${PATH}"\nhcloud configure set \\\n  --cli-access-key=$HCLOUD_AK \\\n  --cli-secret-key=$HCLOUD_SK \\\n  --cli-region=la-north-2 \\\n  --cli-agree-privacy-statement=true \\\n  --cli-read-timeout=30 \\\n  --cli-connect-timeout=10`}</code>
              <CopyButton text={`curl -LO "https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz"\ntar -zxvf huaweicloud-cli-linux-amd64.tar.gz\nmkdir -p ~/.local/bin\nmv hcloud ~/.local/bin/hcloud\nexport PATH="$HOME/.local/bin:\${PATH}"\nhcloud configure set \\\n  --cli-access-key=$HCLOUD_AK \\\n  --cli-secret-key=$HCLOUD_SK \\\n  --cli-region=la-north-2 \\\n  --cli-agree-privacy-statement=true \\\n  --cli-read-timeout=30 \\\n  --cli-connect-timeout=10`} />
            </div></div></div>

            <p className="migration-code-section-label">12. Verify</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`claude --version\nhcloud IAM ListUsersV5`}</code>
              <CopyButton text={`claude --version\nhcloud IAM ListUsersV5`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              <code>claude --version</code> confirms Claude Code is installed. <code>hcloud IAM ListUsersV5</code> confirms KooCLI is configured.
              Claude Code is now running with MaaS models via LiteLLM proxy.
            </p>

            <p className="migration-code-section-label">13. Cleanup</p>
            <div className="migration-code-block"><div className="migration-code-line"><div className="migration-code-cmd-row">
              <code className="migration-code-cmd">{`exit\ndocker rm -f demo`}</code>
              <CopyButton text={`exit\ndocker rm -f demo`} />
            </div></div></div>
            <p style={{ fontSize: "13px", color: "#666", margin: "4px 0 16px" }}>
              Type <code>exit</code> to leave the container, then remove it with <code>docker rm -f demo</code>.
            </p>

          </div>
        </section>
      )}

      {config.faq ? (
        <div id="migration-faq">
          <ScenarioFAQ lang={lang} config={config.faq} scenarioId={config.scenarioId} />
        </div>
      ) : null}

      <section className="migration-template-help">
        <div className="migration-help-copy">
          <span className="section-kicker">{l.needHelp}</span>
          <h2>{asText(lang, config.contactInfo.title)}</h2>
          <p>{asText(lang, config.contactInfo.description)}</p>
        </div>
        <div className="migration-help-actions">
          <a
            className="migration-help-contact"
            href={config.contactInfo.link}
            target="_blank"
            rel="noreferrer"
            onClick={() =>
              trackClick({
                click_target: "migration_template_contact_expert",
                click_section: "migration_need_help",
                destination: config.contactInfo.link,
                scenario_id: config.scenarioId,
              })
            }
          >
            <UserRound size={18} />
            {asText(lang, config.contactInfo.buttonText)}
          </a>
          <a
            className="migration-help-back"
            href="#/migration"
            onClick={() =>
              trackClick({
                click_target: "migration_template_back_to_migration",
                click_section: "migration_need_help",
                destination: "#/migration",
                scenario_id: config.scenarioId,
              })
            }
          >
            {l.backToMigration}
            <ArrowRight size={17} />
          </a>
        </div>
        <div className="migration-related-panel">
          <h3>{l.relatedScenarios}</h3>
          <div className="migration-related-links">
            {config.relatedScenarios.map((scenario) => (
              <a
                key={scenario.scenarioId}
                href={scenario.href}
                onClick={() =>
                  trackClick({
                    click_target: "migration_template_related_scenario",
                    click_section: "migration_need_help",
                    destination: scenario.href,
                    scenario_id: scenario.scenarioId,
                  })
                }
              >
                {asText(lang, scenario.title)}
                <ArrowRight size={15} />
              </a>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
