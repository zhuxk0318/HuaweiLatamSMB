import type { Lang } from "./i18n";
import {
  aiSkillCategoryProfiles,
  aiSkillDefinitions,
  type AiSkillCategoryProfile,
} from "./aiSkills";

export type SolutionEntryId = "ai-maas" | "on-prem-to-cloud" | "enterprise";

export type LocalizedPair = {
  en: string;
  es: string;
  zh?: string;
};

export type SkillLink = {
  label: string;
  url: string;
};

export type QuickIntegration = {
  prerequisites: (LocalizedPair & { link?: { label: string; url: string }; linkParts?: { label: string; url: string }[] })[];
  steps: LocalizedPair[];
  configuration: LocalizedPair[];
  apiAccess?: LocalizedPair[];
  requiredMcpServers?: {
    intro: LocalizedPair;
    servers: { mcp: string; purpose: LocalizedPair }[];
    note: LocalizedPair;
  };
  startingPrompt?: {
    intro: LocalizedPair;
    code: string;
  };
  whatSkillAsks?: LocalizedPair;
  whatScenarioDoesNotDo?: LocalizedPair;
};

export type SolutionScenario = {
  id: string;
  entryId: SolutionEntryId;
  categoryId?: string;
  categoryLabel?: LocalizedPair;
  title: LocalizedPair;
  oneLiner: LocalizedPair;
  targetCustomers: ({ icon: string; who: LocalizedPair; pain: LocalizedPair } | LocalizedPair)[];
  painPoints: LocalizedPair[];
  solutionApproach: (LocalizedPair & {
    referenceLinks?: { label: string; url: string }[];
    replaces?: LocalizedPair;
  })[];
  recommendedServices: string[];
  demoSkillLinks: SkillLink[];
  quickIntegration: QuickIntegration;
  salesTalkTrack: LocalizedPair[];
  expectedOutcomes: LocalizedPair[];
  heroImage: string;
  externalUrls?: { en: string; es: string };
  sourceCloudServices?: { cloud: string; services: string[] }[];
  detailVariant?: "default" | "healthcare";
  technicalReferences?: { label: string; url: string }[];
  migrationExamples?: {
    title: LocalizedPair;
    description: LocalizedPair;
    githubUrl: string;
  }[];
  migrationMainExample?: {
    title: LocalizedPair;
    description: LocalizedPair;
    githubUrl: string;
  };
  migrationRelatedTools?: {
    title: LocalizedPair;
    description: LocalizedPair;
    githubUrl: string;
    beta?: boolean;
  }[];
  hasPresentationPlaceholder?: boolean;
  presentationUrl?: string;
};

export type SolutionEntry = {
  id: SolutionEntryId;
  title: LocalizedPair;
  summary: LocalizedPair;
  tags: string[];
  heroImage: string;
  scenarioIds: string[];
};

export function textFor(lang: Lang, copy: LocalizedPair) {
  if (lang === "zh") {
    return copy.zh ?? copy.en;
  }
  if (lang === "es") {
    return copy.es;
  }
  return copy.en;
}

export type SolutionEntryCard =
  | { kind: "internal"; entry: SolutionEntry }
  | {
      kind: "external";
      id: string;
      title: LocalizedPair;
      summary: LocalizedPair;
      tags: string[];
      heroImage: string;
      externalUrls: { es: string; en: string };
    };

const link = (label: string, url: string): SkillLink => ({ label, url });

export const solutionEntries: SolutionEntry[] = [
  {
    id: "ai-maas",
    title: {
      en: "AI Cloud Adoption Skills",
      es: "Skills de adopción cloud para IA",
    },
    summary: {
      en: "Reusable Huawei Cloud patterns for agent platforms, AI applications, AI coding, governance, and migration.",
      es: "Patrones reutilizables de Huawei Cloud para agentes, aplicaciones de IA, AI Coding, gobierno y migración.",
    },
    tags: ["18 Skills", "MaaS", "Agent & App Patterns"],
    heroImage: "/assets/huawei/ai-skills/ai-connected-city.jpg",
    scenarioIds: aiSkillDefinitions.map((skill) => skill.id),
  },
  {
    id: "on-prem-to-cloud",
    title: {
      en: "Modernize IT Foundations",
      es: "Modernización on-prem to cloud",
    },
    summary: {
      en: "Strengthen core systems, backup, security, desktop, and business continuity with cloud-based services.",
      es: "Lleve VMware, SAP, backup, seguridad y escritorios desde el datacenter hacia un modelo cloud gobernado.",
    },
    tags: ["Resilience", "Security", "Simpler IT"],
    heroImage: "/assets/huawei/flexus.jpg",
    scenarioIds: ["sap-erp-on-cloud", "backup-dr-security", "workspace-migration", "cce-local-to-cloud", "cloud-to-cloud-migration", "database-migration", "container-migration", "ai-coding", "claude-code-litellm-maas", "cloud-foundation", "other-scenarios", "object-migration", "vmware-migration", "vm-migration", "codearts-deployment", "mrs-deployment", "mrs-migration"],
  },
  {
    id: "enterprise",
    title: {
      en: "Enterprise Infrastructure and Industry Solutions",
      es: "Infraestructura empresarial y soluciones sectoriales",
    },
    summary: {
      en: "Huawei Enterprise networking, connectivity, and industry-specific solutions for healthcare, public sector, and beyond.",
      es: "Redes empresariales Huawei, conectividad y soluciones sectoriales para salud, sector público y más.",
    },
    tags: ["WLAN", "Healthcare", "Enterprise Network"],
    heroImage: "/assets/huawei/official-cache/enterprise-wlan-banner.jpg",
    scenarioIds: ["enterprise-wlan", "ai-medical-imaging", "digital-pathology"],
  },
];

export const solutionEntryCards: SolutionEntryCard[] = [
  ...solutionEntries
    .map((entry) => ({ kind: "internal" as const, entry })),
];

const aiSkillCategoryMap = Object.fromEntries(
  aiSkillCategoryProfiles.map((profile) => [profile.id, profile]),
) as Record<string, AiSkillCategoryProfile>;

const aiSkillScenarios: SolutionScenario[] = aiSkillDefinitions.map((skill) => {
  const profile = aiSkillCategoryMap[skill.categoryId];

  return {
    id: skill.id,
    entryId: "ai-maas",
    categoryId: profile.id,
    categoryLabel: profile.label,
    title: skill.title,
    oneLiner: skill.summary,
    targetCustomers: profile.targetCustomers,
    painPoints: profile.painPoints,
    solutionApproach: [skill.focus, ...profile.solutionApproach],
    recommendedServices: skill.recommendedServices,
    demoSkillLinks: [link(skill.title.en, skill.githubPath)],
    quickIntegration: {
      prerequisites: profile.prerequisites,
      steps: [
        {
          en: `Review the ${skill.title.en} Skill, its prerequisites, reference assets, and validation path.`,
          es: `Revise el Skill ${skill.title.es}, sus prerequisitos, activos de referencia y ruta de validación.`,
        },
        ...profile.steps,
      ],
      configuration: profile.configuration,
      apiAccess: profile.apiAccess,
    },
    salesTalkTrack: profile.salesTalkTrack,
    expectedOutcomes: [skill.outcome, ...profile.expectedOutcomes],
    heroImage: skill.heroImage,
  };
});

export const solutionScenarios: SolutionScenario[] = [
  ...aiSkillScenarios,
  {
    id: "ai-coding-agent",
    entryId: "ai-maas",
    title: {
      en: "AI Coding and Agent Access",
      es: "AI Coding y acceso de agentes",
    },
    oneLiner: {
      en: "Connect Claude Code, OpenHands, Pi, LiteLLM, and related coding workflows to Huawei Cloud MaaS with a practical gateway pattern.",
      es: "Conecte Claude Code, OpenHands, Pi, LiteLLM y flujos de AI Coding a Huawei Cloud MaaS con un patrón práctico de gateway.",
    },
    targetCustomers: [
      { en: "Software development teams", es: "Equipos de desarrollo de software" },
      { en: "SaaS builders and ISVs", es: "Constructores SaaS e ISV" },
      { en: "Enterprise IT and DevOps teams", es: "Equipos de TI empresarial y DevOps" },
    ],
    painPoints: [
      { en: "Coding tools connect to multiple model APIs without a governed gateway.", es: "Las herramientas de coding se conectan a múltiples APIs de modelos sin un gateway gobernado." },
      { en: "Token usage, cost visibility, and team permissions are hard to control.", es: "Es difícil controlar el uso de tokens, la visibilidad de costos y los permisos por equipo." },
      { en: "Teams want a fast path from trial to internal rollout.", es: "Los equipos quieren una ruta rápida del piloto al despliegue interno." },
    ],
    solutionApproach: [
      { en: "Use Huawei Cloud MaaS as the model API layer.", es: "Use Huawei Cloud MaaS como capa de API de modelos." },
      { en: "Add LiteLLM or an internal gateway for routing, policies, and observability.", es: "Agregue LiteLLM o un gateway interno para ruteo, políticas y observabilidad." },
      { en: "Connect coding agents and optional search or MCP enhancements in a controlled runtime.", es: "Conecte agentes de coding y extensiones opcionales de búsqueda o MCP en un runtime controlado." },
    ],
    recommendedServices: ["ModelArts MaaS", "ECS", "OBS", "API Gateway", "Cloud Eye"],
    demoSkillLinks: [
      link("LiteLLM + SearXNG AI Coding Gateway", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI/AI-Coding/LiteLLM-SearXNG-AICoding-Gateway-Single-ECS"),
      link("Claude Code Huawei MaaS", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI/AI-Coding/claude-code-huawei-maas"),
      link("OpenHands Huawei MaaS", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI/AI-Coding/openhands-huawei-maas"),
    ],
    quickIntegration: {
      prerequisites: [
        { en: "MaaS API key, target model list, and a small pilot team.", es: "API key de MaaS, lista de modelos objetivo y un pequeño equipo piloto." },
        { en: "One ECS runtime for the gateway and basic outbound connectivity.", es: "Un runtime ECS para el gateway y conectividad saliente básica." },
      ],
      steps: [
        { en: "Deploy the gateway pattern and register Huawei MaaS as the model provider.", es: "Despliegue el patrón de gateway y registre Huawei MaaS como proveedor de modelos." },
        { en: "Connect the coding tool or agent to the gateway endpoint.", es: "Conecte la herramienta o agente de coding al endpoint del gateway." },
        { en: "Apply team policies, logging, and a simple cost dashboard before wider rollout.", es: "Aplique políticas por equipo, logging y un dashboard simple de costos antes de ampliar el despliegue." },
      ],
      configuration: [
        { en: "Standardize model aliases, token limits, and request logging.", es: "Estandarice alias de modelos, límites de tokens y logging de requests." },
        { en: "Use separate API keys or routing rules for different teams or environments.", es: "Use API keys separadas o reglas de ruteo por equipo o ambiente." },
      ],
      apiAccess: [
        { en: "Expose one internal endpoint for coding tools instead of multiple direct model endpoints.", es: "Exponga un único endpoint interno para herramientas de coding en lugar de múltiples endpoints directos de modelos." },
        { en: "Track prompt volume, output volume, and failed calls as launch criteria.", es: "Monitoree volumen de prompts, volumen de respuestas y fallas de llamada como criterio de salida." },
      ],
    },
    salesTalkTrack: [
      { en: "Which teams are already paying for AI coding or experimenting without governance?", es: "¿Qué equipos ya están pagando por AI coding o experimentando sin gobierno?" },
      { en: "Do you need one shared token gateway before scaling tool adoption?", es: "¿Necesita un gateway compartido de tokens antes de escalar la adopción?" },
    ],
    expectedOutcomes: [
      { en: "Faster coding pilots with visible token consumption.", es: "Pilotos de coding más rápidos con consumo de tokens visible." },
      { en: "A governed AI coding access model for multiple teams.", es: "Un modelo gobernado de acceso a AI coding para varios equipos." },
      { en: "A practical bridge from AI experimentation to broader cloud usage.", es: "Un puente práctico desde la experimentación AI hacia mayor uso cloud." },
    ],
    heroImage: "/assets/huawei/hero-maas.jpg",
  },
  {
    id: "customer-service-knowledge",
    entryId: "ai-maas",
    title: {
      en: "Customer Service and Knowledge Assistant",
      es: "Asistente de servicio y conocimiento",
    },
    oneLiner: {
      en: "Build customer support, internal knowledge, and industry assistants on Huawei MaaS with RAG-ready patterns.",
      es: "Construya asistentes de soporte al cliente, conocimiento interno y asistentes sectoriales sobre Huawei MaaS con patrones listos para RAG.",
    },
    targetCustomers: [
      { en: "Customer service and support teams", es: "Equipos de atención y soporte" },
      { en: "Operations managers with repetitive knowledge work", es: "Responsables operativos con trabajo repetitivo de conocimiento" },
      { en: "SMBs with growing product or policy documentation", es: "Pymes con documentación de producto o políticas en crecimiento" },
    ],
    painPoints: [
      { en: "Knowledge is spread across PDFs, tickets, and shared folders.", es: "El conocimiento está disperso en PDFs, tickets y carpetas compartidas." },
      { en: "Support quality depends too much on individual experts.", es: "La calidad del soporte depende demasiado de expertos individuales." },
      { en: "Response time and consistency are difficult to improve with small teams.", es: "Es difícil mejorar tiempo de respuesta y consistencia con equipos pequeños." },
    ],
    solutionApproach: [
      { en: "Use Huawei MaaS for model access and a RAG stack for trusted retrieval.", es: "Use Huawei MaaS para acceso a modelos y un stack RAG para recuperación confiable." },
      { en: "Start with one controlled document domain and a narrow FAQ scope.", es: "Comience con un dominio documental controlado y un alcance acotado de preguntas frecuentes." },
      { en: "Measure answer quality, fallback handling, and handoff to human teams.", es: "Mida calidad de respuesta, manejo de fallback y transferencia a equipos humanos." },
    ],
    recommendedServices: ["ModelArts MaaS", "ECS", "OBS", "RAGFlow", "FunctionGraph"],
    demoSkillLinks: [
      link("RAGFlow Huawei MaaS", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI/AI-Applications/ragflow-huawei-maas"),
      link("Telco Call Center AI", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI/AI-Applications/Telco-Call-Center-AI"),
      link("Enterprise RAG", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI/AI-Applications"),
    ],
    quickIntegration: {
      prerequisites: [
        { en: "Approved source documents, ownership, and target user group.", es: "Documentos fuente aprobados, responsables y grupo objetivo de usuarios." },
        { en: "One pilot support flow with measurable volume and escalation logic.", es: "Un flujo piloto de soporte con volumen medible y lógica de escalamiento." },
      ],
      steps: [
        { en: "Prepare document ingestion, chunking, and permissions for the first knowledge domain.", es: "Prepare ingestión documental, chunking y permisos para el primer dominio de conocimiento." },
        { en: "Connect the assistant UI or channel to the retrieval and MaaS layers.", es: "Conecte la interfaz o canal del asistente a las capas de retrieval y MaaS." },
        { en: "Validate quality with real questions before exposing the assistant widely.", es: "Valide la calidad con preguntas reales antes de exponer ampliamente el asistente." },
      ],
      configuration: [
        { en: "Define document freshness, answer guardrails, and escalation triggers.", es: "Defina frescura documental, guardrails de respuesta y disparadores de escalamiento." },
        { en: "Separate internal and external content scopes if both are needed.", es: "Separe los alcances de contenido interno y externo si ambos son necesarios." },
      ],
      apiAccess: [
        { en: "Expose the assistant through web chat, support portal, or internal knowledge search.", es: "Exponga el asistente por chat web, portal de soporte o búsqueda interna de conocimiento." },
        { en: "Log answer quality, fallback rate, and article coverage from day one.", es: "Registre desde el primer día calidad de respuesta, tasa de fallback y cobertura documental." },
      ],
    },
    salesTalkTrack: [
      { en: "Where do your support teams lose the most time searching or repeating answers?", es: "¿Dónde pierden más tiempo sus equipos de soporte buscando o repitiendo respuestas?" },
      { en: "Which knowledge domain is stable enough for a first assistant pilot?", es: "¿Qué dominio de conocimiento es lo bastante estable para un primer piloto de asistente?" },
    ],
    expectedOutcomes: [
      { en: "Faster answer retrieval and better support consistency.", es: "Recuperación de respuestas más rápida y mejor consistencia de soporte." },
      { en: "A measurable knowledge assistant ready for controlled expansion.", es: "Un asistente de conocimiento medible y listo para crecer de forma controlada." },
      { en: "Stronger reuse of enterprise documentation and support know-how.", es: "Mayor reutilización de documentación empresarial y know-how de soporte." },
    ],
    heroImage: "/assets/huawei/official-cache/nn2-a987783a7f08256c.jpg",
  },
  {
    id: "data-analytics-assistant",
    entryId: "ai-maas",
    title: {
      en: "Data Analytics and Operations Assistant",
      es: "Asistente de analítica y operaciones",
    },
    oneLiner: {
      en: "Enable natural-language access to business data, logs, and operational indicators for faster analysis and better decision support.",
      es: "Habilite acceso en lenguaje natural a datos de negocio, logs e indicadores operativos para acelerar el análisis y mejorar la toma de decisiones.",
    },
    targetCustomers: [
      { en: "Operations and finance teams", es: "Equipos de operaciones y finanzas" },
      { en: "Business analysts and reporting owners", es: "Analistas de negocio y responsables de reporting" },
      { en: "SMBs with fragmented data and heavy manual reporting", es: "Pymes con datos fragmentados y reporting manual intensivo" },
    ],
    painPoints: [
      { en: "Teams wait too long for reports or ad hoc data requests.", es: "Los equipos esperan demasiado por reportes o consultas ad hoc." },
      { en: "Database knowledge and log analysis are concentrated in a few people.", es: "El conocimiento de base de datos y análisis de logs está concentrado en pocas personas." },
      { en: "Managers need clearer operational insight without building a full BI program first.", es: "Los gerentes necesitan mejor visibilidad operativa sin construir primero un programa BI completo." },
    ],
    solutionApproach: [
      { en: "Connect a controlled NL2SQL or analytics assistant to governed data sources.", es: "Conecte un asistente controlado de NL2SQL o analítica a fuentes de datos gobernadas." },
      { en: "Use Huawei MaaS for language understanding and output summarization.", es: "Use Huawei MaaS para comprensión del lenguaje y resumen de resultados." },
      { en: "Start with a narrow metric set and expand after query quality is proven.", es: "Comience con un conjunto acotado de métricas y expanda cuando la calidad de consulta esté probada." },
    ],
    recommendedServices: ["ModelArts MaaS", "RDS", "DWS", "CSS", "OBS"],
    demoSkillLinks: [
      link("Dify NL2SQL", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI/AI-Applications/Dify-NL2SQL"),
      link("CSS Log Query Assistant", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI/AI-Applications/CSS-Log-Query-Assistant"),
      link("ChatBI and Intelligent Analytics", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/Big-Data"),
    ],
    quickIntegration: {
      prerequisites: [
        { en: "A defined source system, table scope, or log source for the first pilot.", es: "Un sistema fuente, alcance de tablas o fuente de logs definidos para el primer piloto." },
        { en: "A small approved KPI set and at least one business owner for validation.", es: "Un pequeño conjunto aprobado de KPI y al menos un responsable de negocio para validar." },
      ],
      steps: [
        { en: "Connect the assistant to one governed data source and define allowed query patterns.", es: "Conecte el asistente a una fuente de datos gobernada y defina patrones permitidos de consulta." },
        { en: "Validate query accuracy with real operational questions and sample outputs.", es: "Valide la exactitud de consulta con preguntas operativas reales y salidas de muestra." },
        { en: "Add dashboard links or exports only after answer reliability is stable.", es: "Agregue links a dashboards o exports solo cuando la confiabilidad de las respuestas sea estable." },
      ],
      configuration: [
        { en: "Whitelist schemas, metrics, and prompt templates for the first release.", es: "Haga whitelist de esquemas, métricas y plantillas de prompt para la primera liberación." },
        { en: "Apply row-level or role-based access when exposing data to different teams.", es: "Aplique acceso por fila o por rol al exponer datos a diferentes equipos." },
      ],
      apiAccess: [
        { en: "Offer the assistant through a portal, internal chat, or BI landing page.", es: "Ofrezca el asistente mediante portal, chat interno o página de entrada BI." },
        { en: "Track query success, escalation to analysts, and time saved by business users.", es: "Monitoree éxito de consultas, escalamiento a analistas y tiempo ahorrado por usuarios de negocio." },
      ],
    },
    salesTalkTrack: [
      { en: "Which recurring reports or log questions still depend on a specialist?", es: "¿Qué reportes o preguntas sobre logs siguen dependiendo de un especialista?" },
      { en: "Would a narrow analytics assistant create value before a larger data program?", es: "¿Un asistente analítico acotado generaría valor antes de un programa de datos más grande?" },
    ],
    expectedOutcomes: [
      { en: "Shorter time to answer business and operations questions.", es: "Menor tiempo para responder preguntas de negocio y operaciones." },
      { en: "Less dependency on scarce analytics specialists for routine requests.", es: "Menor dependencia de especialistas escasos para solicitudes rutinarias." },
      { en: "A clearer path from analytics assistant to broader data modernization.", es: "Una ruta más clara desde el asistente analítico hacia una modernización de datos más amplia." },
    ],
    heroImage: "/assets/huawei/official-cache/nn2-a987783a7f08256c.jpg",
  },
  {
    id: "cloud-to-cloud-migration",
    entryId: "on-prem-to-cloud",
    title: {
      en: "AWS to Huawei Cloud Migration",
      es: "Migración de AWS a Huawei Cloud",
      zh: "AWS到华为云迁移",
    },
      oneLiner: {
      en: "Move workloads from AWS to Huawei Cloud with AI-guided migration tools and automated service mapping.",
      es: "Mueva cargas de AWS a Huawei Cloud con herramientas de migración guiadas por IA y mapeo automático de servicios.",
      zh: "将AWS工作负载迁移到华为云，通过AI引导的迁移工具和自动服务映射完成搬迁。",
    },
    categoryLabel: { en: "Cloud to Cloud Migration", es: "Migración Cloud to Cloud" },
            targetCustomers: [
      { icon: "Cloud", who: { en: "Teams migrating from AWS, Azure, or GCP", es: "Equipos que migran desde AWS, Azure o GCP" }, pain: { en: "Manual migration is error-prone and hard to repeat across environments.", es: "La migracion manual es propensa a errores y dificil de repetir entre entornos." } },
      { icon: "GitBranch", who: { en: "Organizations wanting automated, repeatable migration", es: "Organizaciones que quieren migracion automatizada y repetible" }, pain: { en: "Without deep provider knowledge for resource mapping.", es: "Sin conocimiento profundo del provider para mapear recursos." } },
      { icon: "Building2", who: { en: "Enterprises consolidating multi-cloud estates", es: "Empresas consolidando estates multi-cloud" }, pain: { en: "Facing hidden complexity in networking and identity alignment.", es: "Enfrentando complejidad oculta en networking y alineamiento de identidad." } },
    ],
    painPoints: [
      { en: "Manual migration is error-prone and hard to repeat across environments.", es: "La migración manual es propensa a errores y difícil de repetir entre entornos." },
      { en: "Mapping source cloud resources to Huawei Cloud equivalents requires deep provider knowledge.", es: "Mapear recursos de la nube origen a equivalentes de Huawei Cloud requiere conocimiento profundo del provider." },
      { en: "Cross-cloud networking and identity alignment add hidden complexity to every migration.", es: "El alineamiento de red e identidad cross-cloud añade complejidad oculta a cada migración." },
    ],
    solutionApproach: [
      { en: "DRS — Migrate databases (MySQL, PostgreSQL, Oracle, SQL Server, and more) to Huawei Cloud with minimal downtime and automatic schema conversion.", es: "DRS — Migre bases de datos (MySQL, PostgreSQL, Oracle, SQL Server y más) a Huawei Cloud con mínimo downtime y conversión automática de schema.",
      replaces: { en: "Equivalent to AWS DMS, Azure Database Migration Service, and GCP Database Migration Service — adds automatic schema conversion and zero-downtime cutover with no separate tool.", es: "Equivalente a AWS DMS, Azure Database Migration Service y GCP Database Migration Service — añade conversión automática de schema y cutover sin downtime sin herramienta separada." },
      referenceLinks: [{ label: "DRS — Data Replication Service", url: "https://www.huaweicloud.com/intl/en-us/product/drs.html" }],},
      { en: "OMS — Move object storage data at any scale, with automatic verification that every file arrived intact.", es: "OMS — Mueva datos de object storage a cualquier escala, con verificación automática de que cada archivo llegó intacto.",
      replaces: { en: "Equivalent to AWS DataSync, Azure AzCopy, and GCP Storage Transfer Service — adds native multi-cloud source support (11+ clouds) and built-in ETag verification at petabyte scale.", es: "Equivalente a AWS DataSync, Azure AzCopy y GCP Storage Transfer Service — añade soporte nativo multi-cloud (11+ nubes) y verificación ETag integrada a escala petabyte." },
      referenceLinks: [{ label: "OMS — Object Migration Service", url: "https://www.huaweicloud.com/intl/en-us/product/oms.html" }],},
      { en: "SMS — Migrate servers from any Linux distribution or Windows, with automatic driver adaptation for Huawei Cloud.", es: "SMS — Migre servidores desde cualquier distribución Linux o Windows, con adaptación automática de drivers para Huawei Cloud.",
      replaces: { en: "Equivalent to AWS MGN, Azure Migrate, and GCP Migrate for Compute Engine — adds a single agent for all sources (VMware, AWS, Azure, GCP, on-prem) with automatic driver injection.", es: "Equivalente a AWS MGN, Azure Migrate y GCP Migrate for Compute Engine — añade un único agente para todos los orígenes (VMware, AWS, Azure, GCP, on-prem) con inyección automática de drivers." },
      referenceLinks: [{ label: "SMS — Server Migration Service", url: "https://www.huaweicloud.com/intl/en-us/product/sms.html" }],},
      { en: "MgC — Manage the entire migration from a single dashboard — track progress across servers, databases, and storage in one place.", es: "MgC — Gestione toda la migración desde un único dashboard — siga el progreso de servidores, bases de datos y storage en un solo lugar.",
      replaces: { en: "Equivalent to AWS Migration Hub and Azure Migrate hub — adds unified orchestration for servers, databases, and objects from a single dashboard, not just tracking.", es: "Equivalente a AWS Migration Hub y Azure Migrate hub — añade orquestación unificada de servidores, bases de datos y objetos desde un único dashboard, no solo tracking." },
      referenceLinks: [{ label: "MgC — Migration Center", url: "https://www.huaweicloud.com/intl/en-us/product/mgc.html" }],},
      { en: "AI assistance — Automatically discover what you have in your source cloud and generate the migration plan — no manual inventory needed.", es: "Asistencia IA — Descubra automáticamente qué tiene en su nube origen y genere el plan de migración — sin inventario manual." },
    ],
    recommendedServices: ["DRS", "OMS", "SMS", "MgC", "ECS", "RDS", "OBS", "GaussDB"],
    demoSkillLinks: [
      link("Cloud to Cloud Migration Examples", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-to-Cloud-Migration-Examples"),
    ],
    migrationMainExample: {
      title: { en: "AWS to Huawei Cloud Migration with AI Assistance", es: "Migración de AWS a Huawei Cloud con asistencia de IA" },
      description: { en: "Complete demo of migrating an AWS WordPress workload (EC2, RDS, S3) to Huawei Cloud using Terraform, DRS, OMS, and SMS. Includes AI conversation transcript and HTML documentation.", es: "Demo completa de migración de un workload WordPress de AWS (EC2, RDS, S3) a Huawei Cloud usando Terraform, DRS, OMS y SMS. Incluye transcripción de conversación IA y documentación HTML." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-to-Cloud-Migration-Examples/AWS-to-HCloud-Migration-Demo",
    },
    migrationRelatedTools: [
      {
        title: { en: "Database Migration", es: "Migración de Bases de Datos" },
        description: { en: "DRS, UGO, and Babelfish for migrating relational and big-data databases to Huawei Cloud.", es: "DRS, UGO y Babelfish para migrar bases de datos relacionales y big-data a Huawei Cloud." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration",
      },
      {
        title: { en: "Object Migration", es: "Migración de Object Storage" },
        description: { en: "OMS for migrating object storage data from source clouds to Huawei Cloud OBS.", es: "OMS para migrar datos de object storage desde nubes origen a Huawei Cloud OBS." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Object-Migration",
      },
      {
        title: { en: "Datacenter On-Premise Migration", es: "Migración Datacenter On-Premise" },
        description: { en: "VMware and on-premises server migration guidance for migrating datacenter workloads to Huawei Cloud ECS.", es: "Guía de migración VMware y servidores on-premises para migrar cargas de datacenter a Huawei Cloud ECS." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Datacenter-on-premise-migration/Vmware-Migration",
      },
      {
        title: { en: "VM Migration", es: "Migración de VM" },
        description: { en: "Server Migration Service (SMS) and cloud-to-cloud VM migration guidance for migrating virtual machines to Huawei Cloud ECS.", es: "Server Migration Service (SMS) y guía de migración VM cloud-to-cloud para migrar máquinas virtuales a Huawei Cloud ECS." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/VM-Migration",
      },
      {
        title: { en: "Automation and IaC", es: "Automatización e IaC" },
        description: { en: "Terraform planner and hcloud CLI for generating infrastructure-as-code from discovered source resources.", es: "Terraform planner y hcloud CLI para generar infrastructure-as-code desde recursos origen descubiertos." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Automation-and-IaC",
      },
    ],
    migrationExamples: [
      {
        title: { en: "huaweicloud-oms-migration", es: "huaweicloud-oms-migration" },
        description: { en: "OMS migration skill for migrating object storage from source clouds to Huawei Cloud OBS.", es: "Skill de migración OMS para migrar object storage desde nubes origen a Huawei Cloud OBS." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-to-Cloud-Migration-Examples/AWS-to-HCloud-Migration-Demo/skills/huaweicloud-oms-migration",
      },
      {
        title: { en: "huaweicloud-sms-migration", es: "huaweicloud-sms-migration" },
        description: { en: "SMS migration skill for migrating servers from source clouds to Huawei Cloud ECS.", es: "Skill de migración SMS para migrar servidores desde nubes origen a Huawei Cloud ECS." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-to-Cloud-Migration-Examples/AWS-to-HCloud-Migration-Demo/skills/huaweicloud-sms-migration",
      },
      {
        title: { en: "huaweicloud-terraform-planner", es: "huaweicloud-terraform-planner" },
        description: { en: "Terraform planner skill for generating Huawei Cloud Terraform code from discovered source resources.", es: "Skill planificador Terraform para generar código Terraform de Huawei Cloud desde recursos origen descubiertos." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-to-Cloud-Migration-Examples/AWS-to-HCloud-Migration-Demo/skills/huaweicloud-terraform-planner",
      },
    ],
            quickIntegration: {
      prerequisites: [
        { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
        { en: "Recommended skills installed in ~/.opencode/skills/ (or equivalent).", es: "Skills recomendados instalados en ~/.opencode/skills/ (o equivalente).", link: { label: "GitHub Skills", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-to-Cloud-Migration-Examples" } },
        { en: "Access to your source cloud.", es: "Acceso a su nube origen." },
      ],
      steps: [
        { en: "Discover with AI: Give AI read-only access to your source cloud. It scans everything — servers, databases, storage, networks — and builds a complete inventory with dependencies. Verify the results against your actual environment.", es: "Descubrir con IA: Dele a la IA acceso de solo lectura a su nube origen. Escanea todo — servidores, bases de datos, storage, redes — y construye un inventario completo con dependencias. Verifique los resultados contra su entorno real." },
        { en: "Plan with AI: AI maps each resource to its Huawei Cloud equivalent and generates Terraform code, a phased migration plan, and cost estimates. Review the plan before proceeding.", es: "Planificar con IA: La IA mapea cada recurso a su equivalente en Huawei Cloud y genera código Terraform, un plan de migración por fases y estimaciones de costo. Revise el plan antes de continuar." },
        { en: "Migrate databases with AI: DRS replicates your databases with minimal downtime. AI monitors the sync and alerts you when ready for cutover.", es: "Migrar bases de datos con IA: DRS replica sus bases de datos con mínimo downtime. La IA monitorea la sincronización y le avisa cuando está listo para el cutover." },
        { en: "Migrate storage with AI: OMS moves your object storage data and verifies every file arrived intact. AI tracks progress and handles retries.", es: "Migrar storage con IA: OMS mueve sus datos de object storage y verifica que cada archivo llegó intacto. La IA sigue el progreso y maneja reintentos." },
        { en: "Migrate servers with AI: SMS migrates your servers with disks and network config. AI handles driver adaptation and network settings automatically.", es: "Migrar servidores con IA: SMS migra sus servidores con discos y configuración de red. La IA maneja la adaptación de drivers y configuración de red automáticamente." },
        { en: "Validate with AI: AI verifies connectivity, data integrity, and application health for each migrated resource. Require specific evidence before approving cutover.", es: "Validar con IA: La IA verifica conectividad, integridad de datos y health de aplicación para cada recurso migrado. Exija evidencia específica antes de aprobar el cutover." },
      ],
      configuration: [
        { en: "No private line support: OMS uses Internet or intranet for cross-cloud transfer", es: "Sin líneas privadas: OMS usa Internet o intranet para transferencia cross-cloud" },
        { en: "Archived data costs extra: source cloud charges for restore before migration", es: "Datos archivados costan extra: la nube origen cobra por restore antes de migrar" },
        { en: "5 concurrent tasks per region: plan migration waves within concurrency limits", es: "5 tareas concurrentes por región: planifique olejas dentro de límites de concurrencia" },
        { en: "Symbolic links and ACLs not migrated: reconfigure permissions manually on destination", es: "Symlinks y ACLs no migrados: reconfigure permisos manualmente en destino" },
        { en: "Bandwidth-dependent speed: cross-region speed depends on Internet conditions", es: "Velocidad dependiente del ancho de banda: la velocidad cross-region depende de condiciones de Internet" },
        { en: "Source rate limiting: some source clouds throttle API calls, slowing migration", es: "Rate limiting del origen: algunas nubes origen limitan calls API, ralentizando la migración" },
      ],
      apiAccess: [
        { en: "Check supported cloud vendors: hcloud OMS ShowCloudType", es: "Verificar nubes soportadas: hcloud OMS ShowCloudType" },
        { en: "Check regions for a vendor: hcloud OMS ShowRegionInfo --cloud_type=AWS", es: "Ver regiones de un vendor: hcloud OMS ShowRegionInfo --cloud_type=AWS" },
        { en: "Create cross-cloud task: hcloud OMS CreateTask --src_cloud_type=AWS --src_bucket=xxx --dst_bucket=xxx", es: "Crear tarea cross-cloud: hcloud OMS CreateTask --src_cloud_type=AWS --src_bucket=xxx --dst_bucket=xxx" },
        { en: "Monitor progress: hcloud OMS ShowTask --task_id=xxx", es: "Monitorear progreso: hcloud OMS ShowTask --task_id=xxx" },
      ],
    },
      salesTalkTrack: [
      { en: "Do I need to know both clouds to use AI for migration?", es: "¿Necesito conocer ambas nubes para usar IA en la migración?" },
      { en: "Which cloud resources can AI migrate automatically?", es: "¿Qué recursos de la nube puede migrar la IA automáticamente?" },
      { en: "Will my applications be down during the migration?", es: "¿Mis aplicaciones estarán caídas durante la migración?" },
    ],
    expectedOutcomes: [
      { en: "No. AI handles the service mapping between clouds for you. It reads your source cloud, identifies each resource, and maps it to the Huawei Cloud equivalent. Your team reviews the mapping and makes adjustments, but you don't need deep expertise in both providers.", es: "No. La IA maneja el mapeo de servicios entre nubes por usted. Lee su nube origen, identifica cada recurso y lo mapea al equivalente en Huawei Cloud. Su equipo revisa el mapeo y realiza ajustes, pero no necesita conocimiento profundo de ambos proveedores." },
      { en: "AI can migrate servers (via SMS), databases (via DRS), and object storage (via OMS). It also generates Terraform code to recreate your network, security groups, and other infrastructure. Some resources like monitoring dashboards may need manual setup after migration.", es: "La IA puede migrar servidores (vía SMS), bases de datos (vía DRS) y object storage (vía OMS). También genera código Terraform para recrear su red, security groups y otra infraestructura. Algunos recursos como dashboards de monitoreo pueden requerir configuración manual después de la migración." },
      { en: "No. DRS replicates databases with incremental sync while your source database stays running. SMS migrates servers while they continue to operate. Only the final cutover requires a brief pause (typically minutes) to sync the last changes and switch traffic to Huawei Cloud.", es: "No. DRS replica bases de datos con sincronización incremental mientras su base de datos origen sigue ejecutándose. SMS migra servidores mientras continúan operando. Solo el cutover final requiere una pausa breve (típicamente minutos) para sincronizar los últimos cambios y cambiar el tráfico a Huawei Cloud." },
    ],
    presentationUrl: "/presentations/cloud-to-cloud-migration.pdf",
    heroImage: "/assets/huawei/ai-skills/ai-data-stream.jpg",
  },
  {
    id: "database-migration",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Database", es: "Database" },
    title: {
      en: "Database Migration",
      es: "Migración de Bases de Datos",
      zh: "数据库迁移",
    },
      oneLiner: {
      en: "Migrate transactional and analytical databases to Huawei Cloud with minimal downtime and guaranteed data integrity.",
      es: "Migre bases de datos transaccionales y analíticas a Huawei Cloud con mínima interrupción e integridad garantizada.",
      zh: "将事务型和分析型数据库迁移到华为云，尽量减少停机时间并保障数据完整性。",
    },
            targetCustomers: [
      { icon: "Database", who: { en: "Teams migrating from Snowflake, Databricks, or Teradata", es: "Equipos que migran desde Snowflake, Databricks o Teradata" }, pain: { en: "SQL dialects and UDFs don't map directly to target platforms.", es: "Dialectos SQL y UDFs no mapean directamente a las plataformas destino." } },
      { icon: "Server", who: { en: "Organizations migrating Oracle or SQL Server to GaussDB", es: "Organizaciones que migran Oracle o SQL Server a GaussDB" }, pain: { en: "Needing schema conversion and ETL rebuild without manual steps.", es: "Necesitando conversion de schema y reconstruccion de ETL sin pasos manuales." } },
      { icon: "BarChart3", who: { en: "Teams running warehouse workloads", es: "Equipos con cargas de warehouse" }, pain: { en: "DRS can't help and data consistency must be validated before cutover.", es: "DRS no puede ayudar y la consistencia de datos debe validarse antes del cutover." } },
    ],
    painPoints: [
      { en: "Source-specific SQL dialects and UDFs do not map directly to DWS or GaussDB.", es: "Los dialectos SQL y UDFs del origen no mapean directamente a DWS o GaussDB." },
      { en: "DRS handles transactional databases but does not replicate warehouse workloads (Snowflake, Databricks, Teradata).", es: "DRS maneja bases transaccionales pero no replica workloads de warehouse (Snowflake, Databricks, Teradata)." },
      { en: "ETL pipelines depend on source-specific orchestration and connectors.", es: "Los pipelines ETL dependen de orquestación y conectores específicos del origen." },
      { en: "Data consistency must be validated before cutover to avoid reporting gaps.", es: "La consistencia de datos debe validarse antes del cutover para evitar gaps en reporting." },
    ],
    solutionApproach: [
      { en: "Track A (Transactional): UGO converts Oracle/SQL Server schemas and PL/SQL/T-SQL to GaussDB-compatible syntax, then DRS replicates data with zero-downtime cutover.", es: "Track A (Transaccional): UGO convierte schemas de Oracle/SQL Server y PL/SQL/T-SQL a sintaxis compatible con GaussDB, luego DRS replica datos con cutover sin downtime.",
      replaces: { en: "Equivalent to AWS SCT + DMS and Azure DMS — UGO handles schema conversion and DRS handles replication in one integrated flow, no manual SCT step.", es: "Equivalente a AWS SCT + DMS y Azure DMS — UGO maneja conversión de schema y DRS maneja replicación en un flujo integrado, sin paso manual de SCT." },
      referenceLinks: [{ label: "UGO — Database Schema Migration", url: "https://www.huaweicloud.com/intl/en-us/product/ugo.html" }, { label: "DRS — Data Replication Service", url: "https://www.huaweicloud.com/intl/en-us/product/drs.html" }, { label: "GaussDB", url: "https://www.huaweicloud.com/intl/en-us/product/gaussdb.html" }],},
      { en: "Track B (Warehouse): UGO converts Teradata/Oracle SQL to DWS syntax (native compatibility modes), deploy DWS cluster, then rebuild ETL pipelines in DataArts Studio.", es: "Track B (Warehouse): UGO convierte SQL de Teradata/Oracle a sintaxis DWS (modos de compatibilidad nativa), despliegue cluster DWS, luego reconstruya pipelines ETL en DataArts Studio.",
      replaces: { en: "Equivalent to Snowflake, AWS Redshift, Azure Synapse, and GCP BigQuery — DWS offers native Teradata and Oracle SQL compatibility modes, eliminating SQL rewrite.", es: "Equivalente a Snowflake, AWS Redshift, Azure Synapse y GCP BigQuery — DWS ofrece modos de compatibilidad nativa con Teradata y Oracle, eliminando reescritura de SQL." },
      referenceLinks: [{ label: "DWS — Data Warehouse Service", url: "https://www.huaweicloud.com/intl/en-us/product/dws.html" }, { label: "DataArts Studio", url: "https://www.huaweicloud.com/intl/en-us/product/dayu.html" }],},
      { en: "For Databricks/Spark workloads: migrate to MRS (MapReduce Service) with Spark/Hive equivalence and notebook conversion.", es: "Para cargas Databricks/Spark: migre a MRS (MapReduce Service) con equivalencia Spark/Hive y conversión de notebooks.",
      replaces: { en: "Equivalent to Databricks, AWS EMR, and GCP Dataproc — MRS provides fully managed Spark/Hive with auto-scaling and OBS integration.", es: "Equivalente a Databricks, AWS EMR y GCP Dataproc — MRS provee Spark/Hive totalmente gestionado con auto-scaling e integración OBS." },
      referenceLinks: [{ label: "MRS — MapReduce Service", url: "https://www.huaweicloud.com/intl/en-us/product/mrs.html" }],},
      { en: "Validate report parity with business stakeholders before cutover.", es: "Valide paridad de reportes con stakeholders antes del cutover." },
    ],
    recommendedServices: ["DWS", "DataArts", "DRS", "UGO", "GaussDB", "MRS", "OBS", "VPC"],
    demoSkillLinks: [
      link("Database Migration", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration"),
    ],
    migrationMainExample: {
      title: { en: "AI-Assisted Database Migration Tool", es: "Herramienta de migración de bases de datos asistida con IA" },
      description: { en: "Migration and modernization paths for enterprise databases and data platforms, including relational databases, big data platforms, and data warehouses.", es: "Rutas de migración y modernización para bases de datos empresariales y plataformas de datos, incluyendo bases relacionales, big data y data warehouses." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration",
    },
    migrationRelatedTools: [
      {
        title: { en: "Relational Database Migration", es: "Migración de Bases de Datos Relacionales" },
        description: { en: "Migrate Oracle, SQL Server, PostgreSQL, MySQL to Huawei Cloud RDS/GaussDB using DRS, UGO, and Babelfish. Includes 4 sub-skills: DRS migration, GaussDB adaptation, Oracle→PostgreSQL 17, and SQL Server Babelfish finance demo.", es: "Migre Oracle, SQL Server, PostgreSQL, MySQL a Huawei Cloud RDS/GaussDB usando DRS, UGO y Babelfish. Incluye 4 sub-skills: migración DRS, adaptación GaussDB, Oracle→PostgreSQL 17 y demo financiera SQL Server Babelfish." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Relational-Database-Migration",
      },
      {
        title: { en: "Big Data Platform Migration", es: "Migración de Plataformas de Big Data" },
        description: { en: "Migrate Cloudera, Databricks, Teradata to Huawei Cloud MRS/DWS. Includes 4 sub-skills: Cloudera→MRS, Databricks→Huawei Cloud, Databricks→MRS Hudi, and Teradata→DWS.", es: "Migre Cloudera, Databricks, Teradata a Huawei Cloud MRS/DWS. Incluye 4 sub-skills: Cloudera→MRS, Databricks→Huawei Cloud, Databricks→MRS Hudi y Teradata→DWS." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration",
      },
      {
        title: { en: "AWS DocumentDB to Huawei DDS", es: "AWS DocumentDB a Huawei DDS" },
        description: { en: "Migrate Amazon DocumentDB (MongoDB-compatible) to Huawei Cloud DDS (Document Database Service). Includes schema mapping, index migration, and connection string updates.", es: "Migre Amazon DocumentDB (compatible con MongoDB) a Huawei Cloud DDS (Document Database Service). Incluye mapeo de schema, migración de índices y actualización de strings de conexión." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/AWS-DocumentDB-to-Huawei-DDS",
        beta: true,
      },
      {
        title: { en: "AWS DynamoDB to Huawei GeminiDB", es: "AWS DynamoDB a Huawei GeminiDB" },
        description: { en: "Migrate Amazon DynamoDB tables to Huawei Cloud GeminiDB (Cassandra-compatible). Covers table mapping, data export/import, and throughput sizing.", es: "Migre tablas de Amazon DynamoDB a Huawei Cloud GeminiDB (compatible con Cassandra). Cubre mapeo de tablas, export/import de datos y sizing de throughput." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/AWS-DynamoDB-to-Huawei-GeminiDB",
        beta: true,
      },
      {
        title: { en: "AWS ElastiCache to Huawei DCS", es: "AWS ElastiCache a Huawei DCS" },
        description: { en: "Migrate Amazon ElastiCache (Redis/Memcached) to Huawei Cloud DCS (Distributed Cache Service). Includes RDB backup/restore and cluster topology mapping.", es: "Migre Amazon ElastiCache (Redis/Memcached) a Huawei Cloud DCS (Distributed Cache Service). Incluye backup/restore RDB y mapeo de topología de cluster." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/AWS-ElastiCache-to-Huawei-DCS",
        beta: true,
      },
      {
        title: { en: "Azure CosmosDB to Huawei GeminiDB", es: "Azure CosmosDB a Huawei GeminiDB" },
        description: { en: "Migrate Azure Cosmos DB collections to Huawei Cloud GeminiDB. Covers API mapping, partition key strategy, and data migration tooling.", es: "Migre colecciones de Azure Cosmos DB a Huawei Cloud GeminiDB. Cubre mapeo de API, estrategia de partition key y tooling de migración de datos." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Azure-CosmosDB-to-Huawei-GeminiDB",
        beta: true,
      },
    ],
    migrationExamples: [
      {
        title: { en: "huaweicloud-drs-migration", es: "huaweicloud-drs-migration" },
        description: { en: "DRS migration skill for replicating relational databases to Huawei Cloud with minimal downtime.", es: "Skill de migración DRS para replicar bases de datos relacionales a Huawei Cloud con mínimo downtime." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Relational-Database-Migration/huaweicloud-drs-migration",
      },
      {
        title: { en: "huawei-postgresql-ecs-to-rds-drs-cross-region", es: "huawei-postgresql-ecs-to-rds-drs-cross-region" },
        description: { en: "Cross-region DRS migration of PostgreSQL from ECS to RDS.", es: "Migración DRS cross-region de PostgreSQL desde ECS a RDS." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Relational-Database-Migration/huawei-postgresql-ecs-to-rds-drs-cross-region",
      },
      {
        title: { en: "huawei-dws-cluster-deployment", es: "huawei-dws-cluster-deployment" },
        description: { en: "DWS cluster deployment skill for big data warehouse migration.", es: "Skill de despliegue de cluster DWS para migración de data warehouse." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/huawei-dws-cluster-deployment",
      },
      {
        title: { en: "huawei-snowflake-to-dataarts-migration", es: "huawei-snowflake-to-dataarts-migration" },
        description: { en: "Snowflake to Huawei Cloud DataArts migration skill.", es: "Skill de migración de Snowflake a Huawei Cloud DataArts." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/huawei-snowflake-to-dataarts-migration",
      },
    ],
    presentationUrl: "/presentations/database-migration.pdf",
            quickIntegration: {
    prerequisites: [
      { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
      { en: "Recommended skills installed in ~/.opencode/skills/ (or equivalent).", es: "Skills recomendados instalados en ~/.opencode/skills/ (o equivalente).", link: { label: "GitHub Skills", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration" } },
      { en: "Source database credentials.", es: "Credenciales de base de datos origen." },
    ],
    steps: [
      { en: "Discover with AI: Scan your source databases — schemas, stored procedures, functions, triggers, and dependencies. Verify the results against your actual database.", es: "Descubrir con IA: Escanee sus bases de datos origen — schemas, stored procedures, funciones, triggers y dependencias. Verifique los resultados contra su base de datos actual." },
      { en: "Plan with AI: AI maps each database to its Huawei Cloud equivalent (GaussDB, DWS, RDS) and generates a migration plan with cost estimates. Review the plan before proceeding.", es: "Planificar con IA: La IA mapea cada base de datos a su equivalente en Huawei Cloud (GaussDB, DWS, RDS) y genera un plan de migración con estimaciones de costo. Revise el plan antes de continuar." },
      { en: "Convert with AI: UGO converts SQL dialects automatically — stored procedures, functions, and triggers. AI highlights any items needing manual review.", es: "Convertir con IA: UGO convierte dialectos SQL automáticamente — stored procedures, funciones y triggers. La IA destaca los items que requieren revisión manual." },
      { en: "Replicate with AI: DRS replicates your data with incremental sync while the source database stays running. AI monitors the sync and alerts you when ready for cutover.", es: "Replicar con IA: DRS replica sus datos con sincronización incremental mientras la base de datos origen sigue ejecutándose. La IA monitorea la sincronización y le avisa cuando está listo para el cutover." },
      { en: "Validate with AI: AI checks report parity, query performance, and data integrity against the source. Business owners validate critical outputs.", es: "Validar con IA: La IA verifica paridad de reportes, rendimiento de consultas e integridad de datos contra el origen. Los responsables de negocio validan salidas críticas." },
      { en: "Cutover with AI: Switch application connections to Huawei Cloud. AI verifies application health and rollback readiness. Require specific evidence before approving cutover.", es: "Cutover con IA: Cambie las conexiones de aplicación a Huawei Cloud. La IA verifica health de aplicación y readiness de rollback. Exija evidencia específica antes de aprobar el cutover." },
    ],
      configuration: [
        { en: "UGO: no incremental schema — changes after assessment are not captured, sync manually", es: "UGO: sin schema incremental — cambios posteriores al assessment no se capturan, sincronice manualmente" },
        { en: "UGO: off-peak collection — assessment occupies source DB resources, run during low traffic", es: "UGO: recolección en horas valle — el assessment ocupa recursos de BD origen, ejecute en tráfico bajo" },
        { en: "UGO: strict testing required — migrated schemas need thorough validation before cutover", es: "UGO: testing estricto — schemas migrados necesitan validación exhaustiva antes del cutover" },
        { en: "DRS: source must enable binlog — MySQL sources require binlog for incremental sync", es: "DRS: origen debe habilitar binlog — orígenes MySQL requieren binlog para sync incremental" },
        { en: "DRS: per-path constraints — each DB engine pair has specific limitations, check compatibility", es: "DRS: restricciones por ruta — cada par de engines tiene limitaciones, verifique compatibilidad" },
        { en: "GaussDB limits: foreign keys and generated columns unsupported in distributed mode", es: "Límites GaussDB: foreign keys y generated columns no soportados en modo distributed" },
      ],
      apiAccess: [
        { en: "Evaluate source database: hcloud UGO CreateEvaluationProject --source_db_id=xxx", es: "Evaluar BD origen: hcloud UGO CreateEvaluationProject --source_db_id=xxx" },
        { en: "Check evaluation status: hcloud UGO ShowEvaluationProjectStatus --project_id=xxx", es: "Ver estado de evaluación: hcloud UGO ShowEvaluationProjectStatus --project_id=xxx" },
        { en: "Create DRS migration job: hcloud DRS CreateJob --job_type=migration --source_db.host=xxx --target_db.host=xxx", es: "Crear job de migración DRS: hcloud DRS CreateJob --job_type=migration --source_db.host=xxx --target_db.host=xxx" },
        { en: "Check migration progress: hcloud DRS ShowDataProgress --job_id=xxx", es: "Ver progreso de migración: hcloud DRS ShowDataProgress --job_id=xxx" },
      ],
    },
      salesTalkTrack: [
      { en: "Do I need to rewrite my SQL queries when migrating databases?", es: "¿Necesito reescribir mis consultas SQL al migrar bases de datos?" },
      { en: "Can AI migrate both transactional and analytical databases?", es: "¿Puede la IA migrar bases de datos transaccionales y analíticas?" },
      { en: "Will my applications lose data during the database migration?", es: "¿Mis aplicaciones perderán datos durante la migración de la base de datos?" },
    ],
    expectedOutcomes: [
      { en: "AI converts SQL dialects automatically using Huawei Cloud UGO. It reads your stored procedures, functions, and triggers, and generates compatible versions for the target database. Your team reviews the conversion and tests before cutover. Most Oracle and SQL Server migrations require minimal manual adjustment.", es: "La IA convierte dialectos SQL automáticamente usando UGO de Huawei Cloud. Lee sus stored procedures, funciones y triggers, y genera versiones compatibles para la base de datos destino. Su equipo revisa la conversión y prueba antes del cutover. La mayoría de migraciones de Oracle y SQL Server requieren ajuste manual mínimo." },
      { en: "Yes. AI handles transactional databases (MySQL, PostgreSQL, Oracle, SQL Server) via DRS with incremental replication, and analytical databases via DWS with DataArts Studio for ETL migration. It identifies the database type and recommends the right migration path.", es: "Sí. La IA maneja bases transaccionales (MySQL, PostgreSQL, Oracle, SQL Server) vía DRS con replicación incremental, y bases analíticas vía DWS con DataArts Studio para migración ETL. Identifica el tipo de base de datos y recomienda la ruta de migración correcta." },
      { en: "No. DRS performs incremental sync while your source database stays running. Applications continue to read and write to the source. Only the final cutover requires a brief pause to sync the last transactions and switch the connection string.", es: "No. DRS realiza sincronización incremental mientras su base de datos origen sigue ejecutándose. Las aplicaciones continúan leyendo y escribiendo al origen. Solo el cutover final requiere una pausa breve para sincronizar las últimas transacciones y cambiar el connection string." },
    ],
    heroImage: "/assets/huawei/official-cache/nn2-a987783a7f08256c.jpg",
  },
  {
    id: "sap-erp-on-cloud",
    entryId: "on-prem-to-cloud",
    title: {
      en: "Big Data Migration to Huawei Cloud",
      es: "Migracion de Big Data a Huawei Cloud",
    },
    oneLiner: {
      en: "Migrate big data workloads from on-premises Hadoop, Hive, and ClickHouse clusters to Huawei Cloud MRS and DWS. Skills cover cluster deployment, data migration, and query engine conversion.",
      es: "Migre cargas de big data desde clústers on-premise de Hadoop, Hive y ClickHouse hacia Huawei Cloud MRS y DWS. Los skills cubren despliegue de clústers, migración de datos y conversión de motores de consultas.",
      zh: "将大数据工作负载从本地 Hadoop、Hive 和 ClickHouse 集群迁移到华为云 MRS 和 DWS。技能涵盖集群部署、数据迁移和查询引擎转换。",
    },
    targetCustomers: [
      { en: "ERP-dependent SMBs and midmarket enterprises", es: "Pymes y empresas medianas dependientes de ERP" },
      { en: "SAP infrastructure owners", es: "Responsables de infraestructura SAP" },
      { en: "Teams planning modernization without replacing the ERP first", es: "Equipos que planifican modernización sin reemplazar primero el ERP" },
    ],
    painPoints: [
      { en: "Legacy ERP infrastructure is hard to scale, back up, or recover quickly.", es: "La infraestructura ERP legacy es difícil de escalar, respaldar o recuperar rápidamente." },
      { en: "Availability and performance concerns block migration decisions.", es: "Las preocupaciones de disponibilidad y rendimiento bloquean decisiones de migración." },
      { en: "Operations teams need a safer path than a full application redesign.", es: "Los equipos operativos necesitan una ruta más segura que rediseñar toda la aplicación." },
    ],
    solutionApproach: [
      { en: "Assess ERP sizing, business continuity, and surrounding system dependencies.", es: "Evalúe sizing ERP, continuidad de negocio y dependencias de sistemas circundantes." },
      { en: "Build a target cloud pattern with HA, backup, and performance monitoring from the start.", es: "Construya un patrón cloud objetivo con HA, backup y monitoreo de rendimiento desde el inicio." },
      { en: "Move in controlled waves with operations runbooks and validation checkpoints.", es: "Mueva en oleadas controladas con runbooks operativos y checkpoints de validación." },
    ],
    recommendedServices: ["DWS", "MRS", "GaussDB", "OBS", "ECS", "VPC"],
    demoSkillLinks: [
      link("Database Migration", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration"),
    ],
    quickIntegration: {
      prerequisites: [
        { en: "An ERP infrastructure inventory, HA requirement, and recovery targets.", es: "Un inventario de infraestructura ERP, requisito de HA y objetivos de recuperación." },
        { en: "Business sign-off on maintenance windows and validation owners.", es: "Aprobación de negocio sobre ventanas de mantenimiento y responsables de validación." },
      ],
      steps: [
        { en: "Assess current ERP landscape and define target cloud capacity and resilience.", es: "Evalúe el landscape ERP actual y defina capacidad y resiliencia cloud objetivo." },
        { en: "Prepare backup, network, and operations baselines before moving production workloads.", es: "Prepare baseline de backup, red y operaciones antes de mover cargas productivas." },
        { en: "Run migration rehearsal, cutover, and application validation with business teams.", es: "Ejecute ensayo de migración, cutover y validación de aplicación con equipos de negocio." },
      ],
      configuration: [
        { en: "Document target capacity, HA zones, storage tiers, and backup policy.", es: "Documente capacidad objetivo, zonas HA, tiers de almacenamiento y política de backup." },
        { en: "Align ERP operations, monitoring, and escalation ownership before go-live.", es: "Alinee operaciones ERP, monitoreo y ownership de escalamiento antes del go-live." },
      ],
      apiAccess: [
        { en: "Integrate ERP monitoring and backup status into the standard operations view.", es: "Integre monitoreo ERP y estado de backup en la vista estándar de operaciones." },
        { en: "Keep migration validation evidence and operational baselines as part of the project handover.", es: "Mantenga evidencia de validación de migración y baselines operativos como parte del handover del proyecto." },
      ],
    },
    salesTalkTrack: [
      { en: "Is the priority availability, infrastructure cost, DR readiness, or datacenter exit?", es: "¿La prioridad es disponibilidad, costo de infraestructura, readiness DR o salida del datacenter?" },
      { en: "What part of the ERP landscape must stay unchanged while infrastructure modernizes?", es: "¿Qué parte del landscape ERP debe permanecer sin cambios mientras se moderniza la infraestructura?" },
    ],
    expectedOutcomes: [
      { en: "A safer ERP infrastructure modernization path.", es: "Una ruta más segura de modernización de infraestructura ERP." },
      { en: "Better backup, HA, and operations visibility for critical business systems.", es: "Mejor backup, HA y visibilidad operativa para sistemas críticos de negocio." },
      { en: "A cloud foundation that supports later ERP-side optimization.", es: "Una base cloud que soporta optimización posterior del lado ERP." },
    ],
    heroImage: "/assets/huawei/flexus.jpg",
  },
  {
    id: "backup-dr-security",
    entryId: "on-prem-to-cloud",
    title: {
      en: "Backup, DR & Security",
      es: "Backup, disaster recovery y base de seguridad",
    },
    oneLiner: {
      en: "Establish backup, disaster recovery, and security baselines on Huawei Cloud. Skills cover CBR backup and restore, SDR cross-region replication, and security monitoring with Cloud Eye.",
      es: "Establezca bases de backup, disaster recovery y seguridad en Huawei Cloud. Los skills cubren backup y restore con CBR, replicación cross-region con SDR y monitoreo de seguridad con Cloud Eye.",
      zh: "在华为云上建立备份、灾难恢复和安全基线。技能涵盖 CBR 备份与恢复、SDR 跨区域复制和 Cloud Eye 安全监控。",
    },
    targetCustomers: [
      { en: "SMBs with critical files, systems, or databases", es: "Pymes con archivos, sistemas o bases de datos críticos" },
      { en: "Organizations without tested recovery procedures", es: "Organizaciones sin procedimientos de recuperación probados" },
      { en: "Customers asking for a first security baseline rather than a large program", es: "Clientes que piden una primera base de seguridad en lugar de un programa grande" },
    ],
    painPoints: [
      { en: "Backup exists but restoration confidence is low.", es: "Existe backup pero la confianza en la restauración es baja." },
      { en: "Security controls are fragmented and difficult to explain commercially.", es: "Los controles de seguridad están fragmentados y son difíciles de explicar comercialmente." },
      { en: "Teams need a simple package rather than an open-ended transformation project.", es: "Los equipos necesitan un paquete simple en lugar de un proyecto de transformación abierto." },
    ],
    solutionApproach: [
      { en: "Start from recovery objectives and the most business-critical assets.", es: "Comience desde objetivos de recuperación y los activos más críticos para el negocio." },
      { en: "Bundle backup policy, DR pattern, and baseline security controls into one plan.", es: "Agrupe política de backup, patrón DR y controles de seguridad básicos en un solo plan." },
      { en: "Validate restore drills and response ownership before expanding the scope.", es: "Valide drills de restauración y ownership de respuesta antes de ampliar el alcance." },
    ],
    recommendedServices: ["CBR", "SDR", "OBS", "EVS", "CES", "VPC"],
    demoSkillLinks: [
      link("CBR Backup and Restore", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/huawei-cbr-backup-restore"),
      link("SDR Cross-Region Replication", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/huawei-sdr-cross-region-replication"),
    ],
    quickIntegration: {
      prerequisites: [
        { en: "A list of critical systems, backup owners, and acceptable recovery windows.", es: "Una lista de sistemas críticos, responsables de backup y ventanas de recuperación aceptables." },
        { en: "Visibility into current backup tools and at least one recent restore test result.", es: "Visibilidad sobre las herramientas actuales de backup y al menos un resultado reciente de restore test." },
      ],
      steps: [
        { en: "Classify business-critical assets and define recovery tiers.", es: "Clasifique activos críticos y defina tiers de recuperación." },
        { en: "Set target backup and DR policies with matching security controls.", es: "Defina políticas objetivo de backup y DR junto con controles de seguridad asociados." },
        { en: "Run a restore drill and close operational gaps before go-live.", es: "Ejecute un drill de restauración y cierre brechas operativas antes del go-live." },
      ],
      configuration: [
        { en: "Document backup retention, restore ownership, alerting, and isolation requirements.", es: "Documente retención de backup, ownership de restore, alertamiento y requisitos de aislamiento." },
        { en: "Align DR scope with business impact rather than treating every system equally.", es: "Alinee el alcance DR con impacto de negocio en lugar de tratar todos los sistemas por igual." },
      ],
      apiAccess: [
        { en: "Expose backup status, restore logs, and security alerts to the operations team in one operating view.", es: "Exponga a operaciones el estado de backup, logs de restore y alertas de seguridad en una sola vista operativa." },
        { en: "Keep monthly recovery evidence and alert review as part of the service cadence.", es: "Mantenga evidencia mensual de recuperación y revisión de alertas como parte de la cadencia del servicio." },
      ],
    },
    salesTalkTrack: [
      { en: "What would hurt the business most: data loss, prolonged downtime, or weak security posture?", es: "¿Qué dañaría más al negocio: pérdida de datos, tiempo prolongado de caída o una postura débil de seguridad?" },
      { en: "Would a packaged backup and security baseline be easier to fund than a broad modernization program?", es: "¿Sería más fácil financiar una base empaquetada de backup y seguridad que un programa amplio de modernización?" },
    ],
    expectedOutcomes: [
      { en: "A practical SMB-friendly backup and DR offer.", es: "Una oferta práctica de backup y DR amigable para SMB." },
      { en: "Better restore confidence and clearer recovery ownership.", es: "Mayor confianza de restauración y ownership de recuperación más claro." },
      { en: "A first security baseline that supports later cloud growth.", es: "Una primera base de seguridad que soporte el crecimiento cloud posterior." },
    ],
    heroImage: "/assets/huawei/official-cache/enterprise-wlan-banner.jpg",
  },
  {
    id: "workspace-migration",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Workspace", es: "Workspace" },
    title: {
      en: "Workspace Migration",
      es: "Migración de Workspace",
      zh: "云桌面迁移",
    },
      oneLiner: {
      en: "Migrate virtual desktop infrastructure to Huawei Cloud Workspace with full user data and application compatibility.",
      es: "Migre infraestructura de escritorios virtuales a Huawei Cloud Workspace con datos de usuario completos y compatibilidad de aplicaciones.",
      zh: "将虚拟桌面基础设施迁移到华为云 Workspace，保留用户数据并兼顾应用兼容性。",
    },
            targetCustomers: [
      { icon: "Monitor", who: { en: "Organizations facing VMware Horizon licensing pressure", es: "Organizaciones facing presion de licenciamiento VMware Horizon" }, pain: { en: "Lift-and-shift image conversion is unreliable and carries legacy drivers.", es: "La conversion de imagenes lift-and-shift es poco confiable y arrastra drivers legacy." } },
      { icon: "Users", who: { en: "Teams supporting remote workers", es: "Equipos que soportan trabajadores remotos" }, pain: { en: "No automated inventory of installed software across 50+ desktops.", es: "Sin inventario automatizado de software instalado en 50+ desktops." } },
      { icon: "Building2", who: { en: "Enterprises wanting to exit VMware licensing", es: "Empresas que quieren salir de licenciamiento VMware" }, pain: { en: "Needing AD OU and GPO continuity preserved during migration.", es: "Necesitando continuidad de OU y GPO de AD preservada durante la migracion." } },
    ],
    painPoints: [
      { en: "VMware Horizon licensing costs and Broadcom renewal pressure.", es: "Costos de licenciamiento VMware Horizon y presión de renovación Broadcom." },
      { en: "Lift-and-shift image conversion is unreliable — source images carry legacy drivers, orphaned software, and config drift.", es: "La conversión de imágenes lift-and-shift es poco confiable — las imágenes origen arrastran drivers legacy, software huérfano y config drift." },
      { en: "No automated inventory of installed software across 50+ desktops to know what to reinstall.", es: "No hay inventario automatizado de software instalado across 50+ desktops para saber qué reinstalar." },
      { en: "AD OU and GPO continuity must be preserved for policy and access control.", es: "La continuidad de OU y GPO de AD debe preservarse para política y control de acceso." },
    ],
    solutionApproach: [
      { en: "Phase 1 — Inventory: Scan a representative VMware desktop to enumerate installed software, versions, and install paths (windows-software-inventory skill).", es: "Fase 1 — Inventario: Escanee un desktop VMware representativo para enumerar software instalado, versiones y paths de instalación (skill windows-software-inventory)." },
      { en: "Phase 2 — MSI Backup: Locate and copy all MSI installers from the source desktop to a shared location (windows-msi-inventory skill).", es: "Fase 2 — Backup MSI: Localice y copie todos los instaladores MSI desde el desktop origen a una ubicación compartida (skill windows-msi-inventory).",
      replaces: { en: "Equivalent to VMware App Volumes and FSLogix — MSI-based approach preserves exact software versions and install configurations.", es: "Equivalente a VMware App Volumes y FSLogix — el enfoque basado en MSI preserva versiones exactas de software y configuraciones de instalación." },
      referenceLinks: [{ label: "SFS Turbo", url: "https://www.huaweicloud.com/intl/en-us/product/sfsturbo.html" }],},
      { en: "Phase 3 — Clean Rebuild: Provision fresh Workspace desktops with clean OS images and join to existing AD domain.", es: "Fase 3 — Rebuild Limpio: Provisione desktops Workspace con imágenes de OS limpias y únalos al dominio AD existente.",
      replaces: { en: "Equivalent to VMware Horizon, AWS WorkSpaces, and Azure Virtual Desktop — Workspace is fully managed with no infrastructure to maintain and integrated AD support.", es: "Equivalente a VMware Horizon, AWS WorkSpaces y Azure Virtual Desktop — Workspace es totalmente gestionado sin infraestructura que mantener y con soporte AD integrado." },
      referenceLinks: [{ label: "Workspace", url: "https://www.huaweicloud.com/intl/en-us/product/workspace.html" }],},
      { en: "Phase 4 — Batch Reinstall: Use msiexec with sequential installation, logging, and exit-code decoding to reinstall all software (msi-batch-installer skill).", es: "Fase 4 — Reinstalación Batch: Use msiexec con instalación secuencial, logging y decodificación de exit-codes para reinstalar todo el software (skill msi-batch-installer).",
      referenceLinks: [{ label: "NAT Gateway", url: "https://www.huaweicloud.com/intl/en-us/product/natgateway.html" }],},
      { en: "Phase 5 — Parity Verify: Compare installed software lists between source and target, fix gaps, and validate user experience.", es: "Fase 5 — Verificación de Paridad: Compare listas de software instalado entre origen y destino, corrija gaps y valide experiencia de usuario.",
      referenceLinks: [{ label: "CBR — Cloud Backup and Recovery", url: "https://www.huaweicloud.com/intl/en-us/product/cbr.html" }],},
    ],
    recommendedServices: ["Workspace", "ECS", "EVS", "SFS Turbo", "VPC", "NAT Gateway", "HSS", "CBR"],
    demoSkillLinks: [
      link("Workspace Migration", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Workspace-Migration"),
    ],
    migrationMainExample: {
      title: { en: "AI-Assisted Workspace Migration Tool", es: "Herramienta de migración de workspace asistida con IA" },
      description: { en: "Complete toolkit for migrating VDI desktops to Huawei Cloud Workspace using the re-deploy strategy. Includes inventory, MSI backup, and batch installation skills.", es: "Toolkit completo para migrar desktops VDI a Huawei Cloud Workspace usando la estrategia de re-deploy. Incluye inventario, backup MSI y skills de instalación batch." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Workspace-Migration",
    },
    migrationRelatedTools: [
      {
        title: { en: "MSI Batch Installer", es: "Instalador Batch MSI" },
        description: { en: "Install .msi files silently in batch via msiexec with full logging, error code decoding, and pass/fail report. Includes structured 4-step workflow scripts.", es: "Instala archivos .msi silenciosamente en batch vía msiexec con logging completo, decodificación de códigos de error y reporte de éxito/fallo. Incluye scripts de workflow estructurado de 4 pasos." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Workspace-Migration/msi-batch-installer",
        beta: true,
      },
    ],
    migrationExamples: [
      {
        title: { en: "Windows Software Inventory", es: "Inventario de Software de Windows" },
        description: { en: "Scan all installed software on a Windows VDI via registry (4 keys: HKLM+HKCU, 64-bit+32-bit). Exports CSV/JSON. Faster and safer than Win32_Product WMI.", es: "Escanea todo el software instalado en un VDI de Windows vía registro (4 claves: HKLM+HKCU, 64-bit+32-bit). Exporta CSV/JSON. Más rápido y seguro que Win32_Product WMI." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Workspace-Migration/windows-software-inventory",
      },
      {
        title: { en: "Windows MSI Inventory", es: "Inventario MSI de Windows" },
        description: { en: "Extract cached .msi installers from C:\\Windows\\Installer\\, map to software via registry, back up with readable names and properties (ProductCode, UpgradeCode).", es: "Extrae instaladores .msi cacheados de C:\\Windows\\Installer\\, mapea a software vía registro, respalda con nombres legibles y propiedades (ProductCode, UpgradeCode)." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Workspace-Migration/windows-msi-inventory",
      },
      {
        title: { en: "MSI Batch Installer", es: "Instalador Batch MSI" },
        description: { en: "Install .msi files silently in batch via msiexec with full logging, error code decoding, and pass/fail report. Includes structured 4-step workflow scripts.", es: "Instala archivos .msi silenciosamente en batch vía msiexec con logging completo, decodificación de códigos de error y reporte de éxito/fallo. Incluye scripts de workflow estructurado de 4 pasos." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Workspace-Migration/msi-batch-installer",
      },
    ],
    presentationUrl: "/presentations/workspace-migration.pdf",
            quickIntegration: {
    prerequisites: [
      { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
      { en: "Recommended skills installed in ~/.opencode/skills/ (or equivalent).", es: "Skills recomendados instalados en ~/.opencode/skills/ (o equivalente).", link: { label: "GitHub Skills", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Workspace-Migration" } },
      { en: "VMware Horizon environment.", es: "Entorno VMware Horizon." },
    ],
    steps: [
      { en: "Discover with AI: Scan your source desktops — installed applications, user profiles, AD groups, and desktop assignments. Verify the results against your actual environment.", es: "Descubrir con IA: Escanee sus desktops origen — aplicaciones instaladas, perfiles de usuario, grupos de AD y asignaciones de desktop. Verifique los resultados contra su entorno actual." },
      { en: "Plan with AI: AI maps each desktop pool to its Huawei Cloud Workspace equivalent and generates a migration plan. Review the plan before proceeding.", es: "Planificar con IA: La IA mapea cada pool de desktops a su equivalente en Huawei Cloud Workspace y genera un plan de migración. Revise el plan antes de continuar." },
      { en: "Inventory with AI: AI scans each source desktop to find all installed applications, versions, and configurations automatically.", es: "Inventario con IA: La IA escanea cada desktop origen para encontrar todas las aplicaciones, versiones y configuraciones instaladas automáticamente." },
      { en: "Provision with AI: Clean Workspace desktops created and joined to AD domain. AI verifies OU structure and GPO policies are intact.", es: "Aprovisionar con IA: Desktops Workspace limpios se crean y se unen al dominio AD. La IA verifica que la estructura de OU y las políticas GPO estén intactas." },
      { en: "Install with AI: Applications reinstalled in batches with AI-driven logging and error detection. AI compares installed software against the source for parity.", es: "Instalar con IA: Aplicaciones reinstaladas en lotes con logging y detección de errores impulsada por IA. La IA compara el software instalado contra el origen para paridad." },
      { en: "Validate with AI: AI tests user login, application access, and desktop experience. Require specific evidence before approving cutover.", es: "Validar con IA: La IA prueba login de usuario, acceso a aplicaciones y experiencia de desktop. Exija evidencia específica antes de aprobar el cutover." },
    ],
      configuration: [
        { en: "User data migration: profiles and home directories need separate data migration", es: "Migración de datos de usuario: perfiles y home directories necesitan migración separada" },
        { en: "Application compatibility: some on-premises apps may not work with cloud workspace", es: "Compatibilidad de aplicaciones: algunas apps on-premises pueden no funcionar con workspace cloud" },
        { en: "AD integration: Active Directory must be accessible from Huawei Cloud VPC", es: "Integración AD: Active Directory debe ser accesible desde VPC de Huawei Cloud" },
        { en: "Profile persistence: user profiles require persistent storage configuration", es: "Persistencia de perfiles: los perfiles de usuario requieren configuración de storage persistente" },
        { en: "Network latency: user experience depends on latency to the workspace region", es: "Latencia de red: la experiencia de usuario depende de la latencia hacia la región del workspace" },
      ],
      apiAccess: [
        { en: "List desktops: hcloud Workspace ListDesktops", es: "Listar desktops: hcloud Workspace ListDesktops" },
        { en: "List available images: hcloud Workspace ListImages", es: "Listar imágenes disponibles: hcloud Workspace ListImages" },
        { en: "Create desktop pool: hcloud Workspace CreateDesktopPool --pool_name=xxx --image_id=xxx", es: "Crear pool de desktops: hcloud Workspace CreateDesktopPool --pool_name=xxx --image_id=xxx" },
        { en: "List users: hcloud Workspace ListUsers", es: "Listar usuarios: hcloud Workspace ListUsers" },
      ],
    },
      salesTalkTrack: [
      { en: "Do I need to rebuild my desktop images for Huawei Cloud Workspace?", es: "¿Necesito reconstruir mis imágenes de escritorio para Huawei Cloud Workspace?" },
      { en: "Can users keep their existing Active Directory accounts and permissions?", es: "¿Los usuarios pueden conservar sus cuentas y permisos de Active Directory?" },
      { en: "What happens to my VMware Horizon licensing if I migrate?", es: "¿Qué pasa con mi licenciamiento de VMware Horizon si migro?" },
    ],
    expectedOutcomes: [
      { en: "No. AI reads your existing desktop images and converts them to Huawei Cloud Workspace format. It verifies software parity — checking that all applications, settings, and licenses in the source image are present in the target. Your team reviews the comparison report before deploying.", es: "No. La IA lee sus imágenes de escritorio existentes y las convierte al formato de Huawei Cloud Workspace. Verifica la paridad de software — revisando que todas las aplicaciones, configuraciones y licencias de la imagen origen estén presentes en el destino. Su equipo revisa el reporte de comparación antes de desplegar." },
      { en: "Yes. AI preserves Active Directory integration with OU structure and GPO policies intact. Users log in with the same credentials and see the same desktop environment. No re-enrollment or profile rebuild is needed.", es: "Sí. La IA preserva la integración de Active Directory con estructura de OU y políticas GPO intactas. Los usuarios inician sesión con las mismas credenciales y ven el mismo entorno de escritorio. No se necesita re-enrollment ni reconstrucción de perfiles." },
      { en: "Migrating to Huawei Cloud Workspace replaces VMware Horizon licensing with a managed service. You avoid Broadcom renewal costs and get a cloud-native VDI without infrastructure management. AI helps calculate the TCO comparison and plan the migration timeline around your license expiry.", es: "Migrar a Huawei Cloud Workspace reemplaza el licenciamiento de VMware Horizon con un servicio gestionado. Evita costos de renovación con Broadcom y obtiene VDI cloud-native sin gestión de infraestructura. La IA ayuda a calcular la comparación TCO y planificar el timeline de migración alrededor del vencimiento de su licencia." },
    ],
    heroImage: "/assets/huawei/flexus.jpg",
  },
  {
    id: "enterprise-wlan",
    entryId: "enterprise",
    title: { en: "Enterprise WLAN", es: "WLAN Empresarial" },
    oneLiner: {
      en: "High-performance wireless LAN for campuses, hospitals, schools, and public-sector facilities.",
      es: "Red WLAN de alto rendimiento para campus, hospitales, escuelas e instalaciones del sector público.",
    },
    targetCustomers: [
      { en: "Campus and multi-building enterprises", es: "Empresas de campus y múltiples edificios" },
      { en: "Hospitals and healthcare facilities", es: "Hospitales y centros de salud" },
      { en: "Public-sector and education networks", es: "Redes de sector público y educación" },
    ],
    painPoints: [
      { en: "Wi-Fi coverage gaps in high-density areas.", es: "Brechas de cobertura Wi-Fi en zonas de alta densidad." },
      { en: "Manual AP management across large sites.", es: "Gestión manual de APs en sitios extensos." },
      { en: "Security and roaming issues for mission-critical devices.", es: "Problemas de seguridad y roaming para dispositivos misión-críticos." },
    ],
    solutionApproach: [
      { en: "Huawei AirEngine Wi-Fi 6/7 APs with intelligent roaming and AI-driven optimization.", es: "APs Huawei AirEngine Wi-Fi 6/7 con roaming inteligente y optimización impulsada por IA." },
      { en: "Unified management with iMaster NCE for policy, visibility, and automation.", es: "Gestión unificada con iMaster NCE para políticas, visibilidad y automatización." },
      { en: "CloudCampus architecture for centralized multi-site operations.", es: "Arquitectura CloudCampus para operaciones centralizadas multi-sitio." },
    ],
    recommendedServices: ["AirEngine Wi-Fi 6", "iMaster NCE", "CloudCampus"],
    demoSkillLinks: [],
    quickIntegration: {
      prerequisites: [
        { en: "Site survey and capacity planning for target areas.", es: "Levantamiento del sitio y planificación de capacidad para áreas objetivo." },
        { en: "Network architecture review and VLAN/policy design.", es: "Revisión de arquitectura de red y diseño de VLAN/políticas." },
      ],
      steps: [
        { en: "Deploy APs and configure SSID, security, and roaming policies.", es: "Despliegue APs y configure SSID, seguridad y políticas de roaming." },
        { en: "Integrate with iMaster NCE for centralized management.", es: "Integre con iMaster NCE para gestión centralizada." },
        { en: "Validate coverage, roaming, and performance with live traffic.", es: "Valide cobertura, roaming y rendimiento con tráfico real." },
      ],
      configuration: [
        { en: "Define RF profiles, QoS policies, and authentication methods.", es: "Defina perfiles RF, políticas QoS y métodos de autenticación." },
        { en: "Set up monitoring dashboards and alerting thresholds.", es: "Configure dashboards de monitoreo y umbrales de alertas." },
      ],
      apiAccess: [
        { en: "Use iMaster NCE REST API for automation and reporting.", es: "Use la API REST de iMaster NCE para automatización y reportes." },
        { en: "Integrate with existing NMS or ITSM for unified operations.", es: "Integre con NMS o ITSM existente para operaciones unificadas." },
      ],
    },
    salesTalkTrack: [
      { en: "How many APs are managed manually today?", es: "¿Cuántos APs se gestionan manualmente hoy?" },
      { en: "What is the cost of Wi-Fi-related support incidents?", es: "¿Cuál es el costo de incidentes de soporte relacionados con Wi-Fi?" },
    ],
    expectedOutcomes: [
      { en: "Reliable high-density Wi-Fi with AI-driven optimization.", es: "Wi-Fi confiable de alta densidad con optimización impulsada por IA." },
      { en: "Centralized management reducing operational overhead.", es: "Gestión centralizada que reduce la carga operativa." },
      { en: "Seamless roaming for critical medical and enterprise devices.", es: "Roaming sin interrupciones para dispositivos médicos y empresariales críticos." },
    ],
    heroImage: "/assets/huawei/official-cache/enterprise-wlan-banner.jpg",
    externalUrls: {
      en: "https://e.huawei.com/sg/products/wlan",
      es: "https://e.huawei.com/mx/products/wlan",
    },
  },
  {
    id: "ai-medical-imaging",
    entryId: "enterprise",
    title: { en: "AI-Assisted Medical Imaging", es: "Imágenes Médicas Asistidas por IA" },
    oneLiner: {
      en: "AI-powered screening, diagnosis, and collaboration for radiology departments — from chest X-ray and bone fracture detection to lung cancer screening.",
      es: "Cribado, diagnóstico y colaboración impulsados por IA para departamentos de radiología — desde radiografía de tórax y detección de fracturas hasta cribado de cáncer pulmonar.",
    },
    targetCustomers: [
      { en: "Hospitals with radiology and imaging departments", es: "Hospitales con departamentos de radiología e imágenes" },
      { en: "Public health networks centralizing diagnostic imaging", es: "Redes de salud pública que centralizan imágenes diagnósticas" },
      { en: "Health systems seeking AI-assisted screening at scale", es: "Sistemas de salud que buscan cribado asistido por IA a escala" },
    ],
    painPoints: [
      { en: "Radiologist workload is growing faster than staffing can support.", es: "La carga de trabajo radiológico crece más rápido que la capacidad de personal." },
      { en: "Diagnostic delays in high-volume screening programs.", es: "Retrasos diagnósticos en programas de cribado de alto volumen." },
      { en: "Image sharing and collaboration across departments is slow and fragmented.", es: "El intercambio de imágenes y la colaboración entre departamentos es lento y fragmentado." },
    ],
    solutionApproach: [
      { en: "AI-assisted screening and diagnosis for chest X-ray, bone fracture, and lung cancer detection.", es: "Cribado y diagnóstico asistidos por IA para radiografía de tórax, fracturas y detección de cáncer pulmonar." },
      { en: "Quality control, image sharing, and 3D imaging collaboration across the hospital network.", es: "Control de calidad, intercambio de imágenes y colaboración de imágenes 3D en la red hospitalaria." },
      { en: "Integrated PACS and AI inference pipeline on Huawei infrastructure.", es: "Pipeline integrado de PACS e inferencia de IA sobre infraestructura Huawei." },
    ],
    recommendedServices: ["Huawei AI Server", "Huawei All-Flash Storage", "Partner AI Application", "PACS Integration"],
    demoSkillLinks: [],
    quickIntegration: {
      prerequisites: [
        { en: "DICOM-compatible PACS system and radiology workflow.", es: "Sistema PACS compatible con DICOM y flujo radiológico." },
        { en: "Annotated training dataset for target AI models.", es: "Dataset de entrenamiento anotado para los modelos IA objetivo." },
      ],
      steps: [
        { en: "Deploy Huawei AI Server and partner AI application in the hospital data center.", es: "Despliegue Huawei AI Server y la aplicación IA partner en el datacenter del hospital." },
        { en: "Integrate AI inference with PACS image routing and radiologist review workflow.", es: "Integre la inferencia IA con el ruteo de imágenes PACS y el flujo de revisión radiológica." },
        { en: "Validate AI accuracy with retrospective cases before live deployment.", es: "Valide precisión de IA con casos retrospectivos antes del despliegue en vivo." },
      ],
      configuration: [
        { en: "Define AI model scope, inference latency targets, and GPU allocation on AI Server.", es: "Defina alcance de modelos IA, objetivos de latencia de inferencia y asignación de GPU en AI Server." },
        { en: "Set up image retention, backup, and cross-department sharing policies on All-Flash Storage.", es: "Configure retención de imágenes, backup y políticas de intercambio entre departamentos en All-Flash Storage." },
      ],
      apiAccess: [
        { en: "Connect AI inference service to PACS and radiology workstations via hospital network.", es: "Conecte el servicio de inferencia IA a PACS y estaciones radiológicas vía red hospitalaria." },
        { en: "Track screening volume, AI accuracy, and radiologist turnaround time.", es: "Monitoree volumen de cribado, precisión de IA y tiempo de respuesta radiológica." },
      ],
    },
    salesTalkTrack: [
      { en: "How long do radiologists wait for screening results today?", es: "¿Cuánto esperan los radiólogos por resultados de cribado hoy?" },
      { en: "Would AI-assisted triage reduce missed findings in high-volume programs?", es: "¿Reduciría el triaje asistido por IA los hallazgos omitidos en programas de alto volumen?" },
    ],
    expectedOutcomes: [
      { en: "AI-assisted diagnosis efficiency +50%.", es: "Eficiencia de diagnóstico asistido por IA +50%." },
      { en: "Diagnosis accuracy improvement +10%.", es: "Mejora de precisión diagnóstica +10%." },
      { en: "Faster image collaboration and reduced screening backlogs.", es: "Colaboración de imágenes más rápida y reducción de backlogs de cribado." },
    ],
    heroImage: "/assets/huawei/enterprise-healthcare/medical-imaging-banner.jpg",
    detailVariant: "healthcare",
  },
  {
    id: "digital-pathology",
    entryId: "enterprise",
    title: { en: "Digital Pathology", es: "Patología Digital" },
    oneLiner: {
      en: "Whole-slide imaging, pyramid-style storage, and sub-second retrieval for pathology departments — without upgrading network or client endpoints.",
      es: "Imágenes de laminillas completas, almacenamiento piramidal y recuperación sub-segundo para departamentos de patología — sin actualizar red ni endpoints.",
    },
    targetCustomers: [
      { en: "Hospital pathology labs transitioning to digital workflows", es: "Laboratorios de patología hospitalaria en transición a flujos digitales" },
      { en: "Reference labs and multi-site pathology networks", es: "Laboratorios de referencia y redes de patología multi-sitio" },
      { en: "Research institutions with large slide archives", es: "Instituciones de investigación con grandes archivos de laminillas" },
    ],
    painPoints: [
      { en: "Physical slide storage, retrieval, and sharing is slow and space-intensive.", es: "El almacenamiento, recuperación e intercambio de laminillas físicas es lento y consume mucho espacio." },
      { en: "High-resolution slide viewing requires expensive workstations and high-bandwidth network.", es: "La visualización de laminillas de alta resolución requiere estaciones costosas y red de alto ancho de banda." },
      { en: "Pathologist collaboration across sites is limited by physical slide logistics.", es: "La colaboración de patólogos entre sitios está limitada por la logística de laminillas físicas." },
    ],
    solutionApproach: [
      { en: "Whole-slide digitization with pyramid-style multi-resolution storage and retrieval.", es: "Digitalización de laminillas completas con almacenamiento y recuperación piramidal multi-resolución." },
      { en: "Sub-second image retrieval without upgrading existing network or client endpoints.", es: "Recuperación de imágenes sub-segundo sin actualizar la red existente ni los endpoints de cliente." },
      { en: "Hospital-wide data security with encrypted storage, access control, and audit logging.", es: "Seguridad de datos hospitalaria con almacenamiento cifrado, control de acceso y logging de auditoría." },
    ],
    recommendedServices: ["Huawei AI Server", "Huawei All-Flash Storage", "Digital Pathology Viewer", "LIS Integration"],
    demoSkillLinks: [],
    quickIntegration: {
      prerequisites: [
        { en: "Whole-slide scanner and DICOM-compatible LIS integration.", es: "Escáner de laminillas completas e integración LIS compatible con DICOM." },
        { en: "Storage capacity planning for slide volume and retention policy.", es: "Planificación de capacidad de almacenamiento para volumen de laminillas y política de retención." },
      ],
      steps: [
        { en: "Deploy Huawei AI Server and All-Flash Storage with pyramid-style storage configuration.", es: "Despliegue Huawei AI Server y All-Flash Storage con configuración de almacenamiento piramidal." },
        { en: "Integrate with LIS for slide metadata, ordering, and reporting workflow.", es: "Integre con LIS para metadatos de laminillas, órdenes y flujo de reportes." },
        { en: "Validate retrieval speed, image quality, and pathologist workflow before go-live.", es: "Valide velocidad de recuperación, calidad de imagen y flujo del patólogo antes del go-live." },
      ],
      configuration: [
        { en: "Define resolution tiers, compression policy, and storage lifecycle on All-Flash Storage.", es: "Defina tiers de resolución, política de compresión y ciclo de vida en All-Flash Storage." },
        { en: "Configure access control, encryption, and audit logging for compliance.", es: "Configure control de acceso, cifrado y logging de auditoría para cumplimiento." },
      ],
      apiAccess: [
        { en: "Connect slide viewer and retrieval service to pathologist workstations and LIS.", es: "Conecte el visor de laminillas y servicio de recuperación a estaciones de patología y LIS." },
        { en: "Track retrieval latency, storage utilization, and access patterns.", es: "Monitoree latencia de recuperación, utilización de almacenamiento y patrones de acceso." },
      ],
    },
    salesTalkTrack: [
      { en: "How many physical slides are stored and how long does retrieval take?", es: "¿Cuántas laminillas físicas se almacenan y cuánto tarda la recuperación?" },
      { en: "Would sub-second digital retrieval replace the need for slide courier logistics?", es: "¿Reemplazaría la recuperación digital sub-segundo la logística de mensajería de laminillas?" },
    ],
    expectedOutcomes: [
      { en: "Image retrieval within 1 second.", es: "Recuperación de imágenes en menos de 1 segundo." },
      { en: "30% storage space savings with pyramid-style compression.", es: "30% de ahorro de espacio de almacenamiento con compresión piramidal." },
      { en: "Elimination of physical slide courier and associated delays.", es: "Eliminación de mensajería de laminillas físicas y demoras asociadas." },
    ],
    heroImage: "/assets/huawei/enterprise-healthcare/digital-pathology-banner.jpg",
    detailVariant: "healthcare",
  },
  {
    id: "container-migration",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Containers", es: "Containers" },
    title: {
      en: "Container Migration",
      es: "Migración de Contenedores",
      zh: "容器迁移",
    },
      oneLiner: {
      en: "Migrate containerized workloads to Huawei Cloud CCE with image registry and persistent volume portability.",
      es: "Migre cargas en contenedores a Huawei Cloud CCE con registro de imágenes y portabilidad de volúmenes persistentes.",
      zh: "将容器化工作负载迁移到华为云 CCE，支持镜像仓库和持久卷的可迁移性。",
    },
            targetCustomers: [
      { icon: "Container", who: { en: "Organizations operating CCE clusters across regions", es: "Organizaciones que operan clusters CCE across regiones" }, pain: { en: "Hitting OBS S3 API incompatibility with Velero backups.", es: "Enfrentando incompatibilidad de API S3 de OBS con backups Velero." } },
      { icon: "Network", who: { en: "Teams needing cross-region DR", es: "Equipos que necesitan DR cross-region" }, pain: { en: "SWR has no replication and EIPs are mandatory for Velero.", es: "SWR no tiene replicacion y EIPs son obligatorios para Velero." } },
      { icon: "Terminal", who: { en: "DevOps teams", es: "Equipos DevOps" }, pain: { en: "Struggling with ELB ingress L4/L7 flavor configuration different from other clouds.", es: "Struggleando con configuracion de flavors L4/L7 de ELB ingress diferente de otras nubes." } },
    ],
    painPoints: [
      { en: "OBS S3 API incompatibility: OBS requires virtual-hosted-style addressing, but Velero's restic/kopia uses path-style — error: 'Virtual host domain is required'.", es: "Incompatibilidad API S3 de OBS: OBS requiere addressing virtual-hosted-style, pero restic/kopia de Velero usa path-style — error: 'Virtual host domain is required'." },
      { en: "SWR has no cross-region replication — container images must be re-pushed to the destination region SWR.", es: "SWR no tiene replicación cross-region — las imágenes de contenedores deben re-push al SWR de la región destino." },
      { en: "EIPs are mandatory for Velero on CCE — clusters need public OBS access for backup storage.", es: "EIPs son obligatorios para Velero en CCE — los clusters necesitan acceso público a OBS para almacenamiento de backup." },
      { en: "ELB ingress requires separate L4 and L7 flavors — different from typical cloud load balancer setups.", es: "ELB ingress requiere flavors L4 y L7 separados — diferente de setups típicos de cloud load balancer." },
    ],
    solutionApproach: [
      { en: "Phase 1 — Deploy Destination: Create target CCE cluster with matching node flavors, VPC, and security groups.", es: "Fase 1 — Deploy Destino: Cree cluster CCE destino con flavors de nodo matching, VPC y security groups.",
      replaces: { en: "Equivalent to AWS EKS, Azure AKS, and GCP GKE — CCE is fully managed Kubernetes with integrated observability and auto-scaling.", es: "Equivalente a AWS EKS, Azure AKS y GCP GKE — CCE es Kubernetes totalmente gestionado con observabilidad integrada y auto-scaling." },
      referenceLinks: [{ label: "CCE — Cloud Container Engine", url: "https://www.huaweicloud.com/intl/en-us/product/cce.html" }],},
      { en: "Phase 2 — Velero Metadata: Install Velero with OBS plugin on source cluster, create backup of all K8s objects (deployments, services, configmaps, secrets).", es: "Fase 2 — Metadatos Velero: Instale Velero con plugin OBS en cluster origen, cree backup de todos los objetos K8s (deployments, services, configmaps, secrets).",
      replaces: { en: "Equivalent to AWS S3 backup and Azure Blob backup — OBS provides multi-tier storage with 99.999999999% durability and lifecycle rules.", es: "Equivalente a AWS S3 backup y Azure Blob backup — OBS provee storage multi-tier con 99.999999999% de durabilidad y lifecycle rules." },
      referenceLinks: [{ label: "OBS — Object Storage Service", url: "https://www.huaweicloud.com/intl/en-us/product/obs.html" }],},
      { en: "Phase 3 — SWR Reconfig: Re-tag and push container images to destination region SWR, update image references in restored manifests.", es: "Fase 3 — Reconfig SWR: Re-tag y push imágenes de contenedores al SWR de la región destino, actualice referencias de imagen en manifests restaurados.",
      replaces: { en: "Equivalent to AWS ECR, Azure ACR, and GCP Artifact Registry — SWR integrates directly with CCE for seamless deployments.", es: "Equivalente a AWS ECR, Azure ACR y GCP Artifact Registry — SWR se integra directamente con CCE para deploys seamless." },
      referenceLinks: [{ label: "SWR — Software Repository", url: "https://www.huaweicloud.com/intl/en-us/product/swr.html" }],},
      { en: "Phase 4 — PV Data Transfer: Use obsutil (not Velero) to copy PersistentVolume data between OBS buckets — Velero handles metadata only.", es: "Fase 4 — Transfer PV: Use obsutil (no Velero) para copiar datos de PersistentVolume entre buckets OBS — Velero maneja solo metadatos." },
      { en: "Phase 5 — Validate: Restore on destination, verify pod status, ingress, and data parity.", es: "Fase 5 — Validar: Restore en destino, verifique status de pods, ingress y paridad de datos.",
      replaces: { en: "Equivalent to AWS ALB/NLB and Azure Load Balancer — ELB offers separate L4 and L7 flavors with CCE auto-discovery.", es: "Equivalente a AWS ALB/NLB y Azure Load Balancer — ELB ofrece flavors L4 y L7 separados con auto-discovery de CCE." },
      referenceLinks: [{ label: "ELB — Elastic Load Balance", url: "https://www.huaweicloud.com/intl/en-us/product/elb.html" }],},
    ],
    recommendedServices: ["CCE", "SWR", "OBS", "ELB", "VPC", "EIP"],
    demoSkillLinks: [
      link("Container Migration", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration"),
    ],
    migrationMainExample: {
      title: { en: "AI-Assisted Container Migration Tool", es: "Herramienta de migración de contenedores asistida con IA" },
      description: { en: "Complete toolkit for migrating containerized workloads to and between Huawei Cloud CCE. Covers local-to-CCE and cross-region migration with ready-to-use skills.", es: "Toolkit completo para migrar cargas en contenedores a y entre Huawei Cloud CCE. Cubre migración local-to-CCE y cross-region con skills listas para usar." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration",
    },
    migrationRelatedTools: [
      {
        title: { en: "Local to CCE Migration", es: "Migración de Local a CCE" },
        description: { en: "Set up a CCE-compatible local Kind cluster, then migrate containerized workloads to Huawei Cloud CCE in 10 steps. Includes NGINX Ingress, SWR image push, and ELB configuration.", es: "Configure un cluster Kind local compatible con CCE, luego migre cargas en contenedores a Huawei Cloud CCE en 10 pasos. Incluye NGINX Ingress, push de imágenes a SWR y configuración de ELB." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/Local-to-CCE",
      },
      {
        title: { en: "CCE Cross-Region Migration", es: "Migración CCE Cross-Region" },
        description: { en: "Migrate CCE workloads between Huawei Cloud regions using Velero backup/restore. Handles SWR reconfiguration and PVC data migration via obsutil.", es: "Migre cargas CCE entre regiones de Huawei Cloud usando Velero backup/restore. Maneja reconfiguración SWR y migración de datos PVC vía obsutil." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/CCE-Cross-Region",
      },
      {
        title: { en: "CCE Deployment", es: "Despliegue de CCE" },
        description: { en: "Shared deployment skills for creating CCE clusters and node pools. Two options: Terraform MCP (declarative) or KooCLI (imperative, discovery-first).", es: "Skills de despliegue compartidos para crear clusters CCE y node pools. Dos opciones: Terraform MCP (declarativo) o KooCLI (imperativo, discovery-first)." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/CCE-Deployment",
      },
      {
        title: { en: "AWS ECR to Huawei SWR", es: "AWS ECR a Huawei SWR" },
        description: { en: "Migrate Amazon ECR container images to Huawei Cloud SWR (Software Repository for Containers). Includes image retag, batch push, and lifecycle policy mapping.", es: "Migre imágenes de contenedor de Amazon ECR a Huawei Cloud SWR (Software Repository for Containers). Incluye retag de imágenes, push batch y mapeo de lifecycle policy." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/AWS-ECR-to-Huawei-SWR",
        beta: true,
      },
      {
        title: { en: "AWS ECS Fargate to CCE Volcano", es: "AWS ECS Fargate a CCE Volcano" },
        description: { en: "Migrate AWS ECS Fargate serverless containers to Huawei Cloud CCE with Volcano scheduler. Covers task definition mapping, auto-scaling config, and networking translation.", es: "Migre contenedores serverless de AWS ECS Fargate a Huawei Cloud CCE con scheduler Volcano. Cubre mapeo de task definitions, config de auto-scaling y traducción de networking." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/AWS-ECS-Fargate-to-CCE-Volcano",
        beta: true,
      },
    ],
    migrationExamples: [
      {
        title: { en: "cce-local-kind-setup", es: "cce-local-kind-setup" },
        description: { en: "Set up a local Kubernetes cluster using Kind that is compatible with Huawei Cloud CCE for development and migration exercises.", es: "Configure un cluster Kubernetes local usando Kind compatible con Huawei Cloud CCE para desarrollo y ejercicios de migración." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/Local-to-CCE/cce-local-kind-setup",
      },
      {
        title: { en: "kind-to-cce-migration", es: "kind-to-cce-migration" },
        description: { en: "Migrate a Kubernetes application from a local Kind cluster to Huawei Cloud CCE.", es: "Migre una aplicación Kubernetes desde un cluster Kind local a Huawei Cloud CCE." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/Local-to-CCE/kind-to-cce-migration",
      },
      {
        title: { en: "huaweicloud-velero-cce-migration-planner", es: "huaweicloud-velero-cce-migration-planner" },
        description: { en: "Migrate CCE workloads between clusters using Velero backup and restore.", es: "Migre cargas CCE entre clusters usando backup y restore de Velero." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/CCE-Cross-Region/huaweicloud-velero-cce-migration-planner",
      },
      {
        title: { en: "pv-migration-planner", es: "pv-migration-planner" },
        description: { en: "Migrate PersistentVolumeClaim data between CCE clusters using obsutil via OBS bucket as intermediary storage.", es: "Migre datos de PersistentVolumeClaim entre clusters CCE usando obsutil vía bucket OBS como almacenamiento intermedio." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/CCE-Cross-Region/pv-migration-planner",
      },
      {
        title: { en: "huaweicloud-cce-deploy-terraform", es: "huaweicloud-cce-deploy-terraform" },
        description: { en: "Deploy CCE clusters with node pools using Terraform MCP and Huawei Cloud MCP.", es: "Despliegue clusters CCE con node pools usando Terraform MCP y Huawei Cloud MCP." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/CCE-Deployment/huaweicloud-cce-deploy-terraform",
      },
      {
        title: { en: "huaweicloud-cce-deployment", es: "huaweicloud-cce-deployment" },
        description: { en: "Deploy CCE clusters with node pools using KooCLI and Huawei Cloud MCP.", es: "Despliegue clusters CCE con node pools usando KooCLI y Huawei Cloud MCP." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/CCE-Deployment/huaweicloud-cce-deployment",
      },
    ],
    presentationUrl: "/presentations/container-migration.pdf?v=2",
            quickIntegration: {
      prerequisites: [
        { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
        { en: "Recommended skills installed in ~/.opencode/skills/ (or equivalent).", es: "Skills recomendados instalados en ~/.opencode/skills/ (o equivalente).", link: { label: "GitHub Skills", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration" } },
        { en: "Source Kubernetes cluster.", es: "Cluster Kubernetes origen." },
      ],
      steps: [
        { en: "Discover with AI: Scan your source cluster — deployments, services, config maps, secrets, persistent volumes, and ingress. Map the dependencies between them. Verify the results against your actual cluster.", es: "Descubrir con IA: Escanee su cluster origen — deployments, services, config maps, secrets, persistent volumes e ingress. Mapee las dependencias entre ellos. Verifique los resultados contra su cluster real." },
        { en: "Plan with AI: Map each resource to its CCE equivalent and generate Helm charts and Terraform code. Review the plan before proceeding.", es: "Planificar con IA: Mapee cada recurso a su equivalente en CCE y genere Helm charts y código Terraform. Revise el plan antes de continuar." },
        { en: "Migrate images with AI: Re-tag and push container images to Huawei Cloud SWR. AI identifies all image references across your manifests.", es: "Migrar imágenes con IA: Re-tag y push de imágenes de contenedores a Huawei Cloud SWR. La IA identifica todas las referencias de imágenes en sus manifests." },
        { en: "Migrate data with AI: Back up persistent volumes and transfer them via OBS. AI tracks progress and verifies data integrity.", es: "Migrar datos con IA: Backup de persistent volumes y transferencia vía OBS. La IA sigue el progreso y verifica la integridad de datos." },
        { en: "Restore with AI: Restore all Kubernetes resources on the target CCE cluster with updated image references. AI validates pod status and ingress connectivity.", es: "Restaurar con IA: Restaurar todos los recursos de Kubernetes en el cluster CCE destino con referencias de imagen actualizadas. La IA valida el status de pods y conectividad ingress." },
        { en: "Validate with AI: Verify every migrated workload is healthy — pods running, ingress reachable, data intact. Require specific evidence before approving cutover.", es: "Validar con IA: Verificar que cada workload migrado esté healthy — pods ejecutándose, ingress alcanzable, datos intactos. Exija evidencia específica antes de aprobar el cutover." },
      ],
      configuration: [
        { en: "Image registry migration: container images must be pushed to SWR before CCE deployment", es: "Migración de registro: las imágenes deben subirse a SWR antes del despliegue CCE" },
        { en: "Storage class differences: Kubernetes storageClass names may differ between source and CCE", es: "Diferencias de storage class: los nombres de storageClass pueden diferir entre origen y CCE" },
        { en: "Ingress controller: CCE supports NGINX Ingress; other controllers need manual setup", es: "Controller de ingress: CCE soporta NGINX Ingress; otros controllers necesitan setup manual" },
        { en: "Helm chart compatibility: some charts reference source-cluster-specific values", es: "Compatibilidad de Helm charts: algunos charts referencian valores específicos del cluster origen" },
        { en: "Node architecture: ARM and x86 images are not interchangeable — match node pools to image arch", es: "Arquitectura de nodos: imágenes ARM y x86 no son intercambiables — matchee node pools a la arquitectura" },
        { en: "Persistent volumes: PVCs require OBS or EVS CSI drivers; local storage is not portable", es: "Volúmenes persistentes: PVCs requieren drivers CSI de OBS o EVS; local storage no es portable" },
      ],
      apiAccess: [
        { en: "List CCE clusters: hcloud CCE ListClusters", es: "Listar clusters CCE: hcloud CCE ListClusters" },
        { en: "Show cluster details: hcloud CCE ShowCluster --cluster_id=xxx", es: "Ver detalles del cluster: hcloud CCE ShowCluster --cluster_id=xxx" },
        { en: "List nodes: hcloud CCE ListNodes --cluster_id=xxx", es: "Listar nodos: hcloud CCE ListNodes --cluster_id=xxx" },
        { en: "Get kubeconfig: hcloud CCE ShowClusterConfig --cluster_id=xxx", es: "Obtener kubeconfig: hcloud CCE ShowClusterConfig --cluster_id=xxx" },
      ],
    },
      salesTalkTrack: [
      { en: "Do I need to be a Kubernetes expert to use AI for container migration?", es: "¿Necesito ser experto en Kubernetes para usar IA en la migración de contenedores?" },
      { en: "What happens to my container images and data during migration?", es: "¿Qué pasa con mis imágenes de contenedor y datos durante la migración?" },
      { en: "Can I migrate containers from any cloud to Huawei Cloud CCE?", es: "¿Puedo migrar contenedores desde cualquier nube a Huawei Cloud CCE?" },
    ],
    expectedOutcomes: [
      { en: "No. AI reads your Kubernetes manifests and generates CCE-compatible Helm charts. Your team reviews and deploys. AI handles the technical conversion; your team makes the decisions.", es: "No. La IA lee sus manifests de Kubernetes y genera Helm charts compatibles con CCE. Su equipo revisa y despliega. La IA maneja la conversión técnica; su equipo toma las decisiones." },
      { en: "Container images are copied to Huawei Cloud SWR (Software Repository) with all tags intact. Persistent volume data is backed up to OBS and restored on the destination cluster. Nothing is lost; the source cluster keeps running until you switch.", es: "Las imágenes de contenedor se copian a SWR (Software Repository) de Huawei Cloud con todas las etiquetas intactas. Los datos de persistent volumes se respaldan en OBS y se restauran en el cluster destino. Nada se pierde; el cluster origen sigue ejecutándose hasta el switch." },
      { en: "Yes. AI supports migration from EKS (AWS), AKS (Azure), GKE (GCP), and self-managed Kubernetes clusters. It also works with local clusters like kind for testing before production migration.", es: "Sí. La IA soporta migración desde EKS (AWS), AKS (Azure), GKE (GCP) y clusters Kubernetes autogestionados. También funciona con clusters locales como kind para pruebas antes de la migración a producción." },
    ],
    heroImage: "/assets/huawei/ecommerce.jpg",
  },
  {
    id: "cce-local-to-cloud",
    entryId: "on-prem-to-cloud",
    title: {
      en: "CCE Local to Cloud Migration",
      es: "Migracion CCE de local a cloud",
    },
    oneLiner: {
      en: "Migrate Kubernetes applications from a local Kind cluster to Huawei Cloud CCE, covering cluster creation, image push to SWR, and Helm deployment.",
      es: "Migre aplicaciones Kubernetes desde un cluster Kind local a Huawei Cloud CCE, cubriendo creacion de cluster, push de imagenes a SWR y despliegue Helm.",
    },
    targetCustomers: [
      { en: "Development teams using local Kubernetes for testing", es: "Equipos de desarrollo que usan Kubernetes local para pruebas" },
      { en: "Teams moving from local dev to managed cloud Kubernetes", es: "Equipos que migran de dev local a Kubernetes gestionado en cloud" },
    ],
    painPoints: [
      { en: "Local Kubernetes clusters cannot scale for production.", es: "Los clusters Kubernetes locales no pueden escalar para produccion." },
      { en: "Moving from local to cloud Kubernetes requires image, ingress, and storage adjustments.", es: "Mover de Kubernetes local a cloud requiere ajustes de imagen, ingress y almacenamiento." },
    ],
    solutionApproach: [
      { en: "Set up a local Kind cluster compatible with CCE for development.", es: "Configure un cluster Kind local compatible con CCE para desarrollo." },
      { en: "Push container images to Huawei Cloud SWR and deploy via Helm.", es: "Push imagenes de contenedores a SWR de Huawei Cloud y despliegue via Helm." },
      { en: "Configure ELB ingress and validate the application on CCE.", es: "Configure ingress ELB y valide la aplicacion en CCE." },
    ],
    recommendedServices: ["CCE", "SWR", "ELB", "VPC", "EIP"],
    demoSkillLinks: [
      link("CCE Local Kind Setup", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/Local-to-CCE/cce-local-kind-setup"),
      link("Kind to CCE Migration", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/Local-to-CCE/kind-to-cce-migration"),
    ],
    quickIntegration: {
      prerequisites: [
        { en: "Docker and Kind installed locally.", es: "Docker y Kind instalados localmente." },
        { en: "Huawei Cloud account with CCE and SWR access.", es: "Cuenta de Huawei Cloud con acceso a CCE y SWR." },
      ],
      steps: [
        { en: "Create local Kind cluster and deploy application with Helm.", es: "Cree cluster Kind local y despliegue aplicacion con Helm." },
        { en: "Push images to SWR, create CCE cluster, and deploy with CCE-specific values.", es: "Push imagenes a SWR, cree cluster CCE, y despliegue con valores especificos de CCE." },
        { en: "Configure ELB and validate the migrated application.", es: "Configure ELB y valide la aplicacion migrada." },
      ],
      configuration: [
        { en: "Adjust Helm values for CCE-specific storage, ingress, and image registry.", es: "Ajuste valores Helm para almacenamiento, ingress y registro de imagenes especificos de CCE." },
      ],
      apiAccess: [
        { en: "Use CCE API for cluster management and SWR API for image operations.", es: "Use CCE API para gestion de cluster y SWR API para operaciones de imagen." },
      ],
    },
    salesTalkTrack: [
      { en: "Are you running Kubernetes locally and need a path to managed cloud?", es: "Esta ejecutando Kubernetes localmente y necesita una ruta a cloud gestionado?" },
    ],
    expectedOutcomes: [
      { en: "A smooth path from local Kubernetes to managed CCE.", es: "Una ruta fluida de Kubernetes local a CCE gestionado." },
      { en: "Production-ready CCE deployment with proper ingress and scaling.", es: "Despliegue CCE listo para produccion con ingress y escalado adecuados." },
    ],
    heroImage: "/assets/huawei/flexus.jpg",
  },
  {
    id: "ai-coding-opencode",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "AI Tools", es: "AI Tools" },
    title: {
      en: "AI Coding with OpenCode",
      es: "AI Coding con OpenCode",
      zh: "AI Coding with OpenCode",
    },
      oneLiner: {
      en: "Set up OpenCode with Huawei Cloud MaaS and MCP servers for infrastructure-as-code generation.",
      es: "Configure OpenCode con Huawei Cloud MaaS y servidores MCP para generación de infrastructure-as-code.",
      zh: "Set up OpenCode with Huawei Cloud MaaS and MCP servers for infrastructure-as-code generation.",
    },
            targetCustomers: [
      { icon: "Code2", who: { en: "Developers using OpenCode for Huawei Cloud infrastructure code", es: "Desarrolladores que usan OpenCode para código de infraestructura de Huawei Cloud" }, pain: { en: "Need AI agent that discovers real cloud resources and writes valid Terraform.", es: "Necesitan agente IA que descubra recursos reales y escriba Terraform válido." } },
      { icon: "ShieldCheck", who: { en: "Teams wanting governed MaaS access with cost control", es: "Equipos que quieren acceso gobernado a MaaS con control de costos" }, pain: { en: "Direct model access lacks routing, fallback, and usage tracking.", es: "El acceso directo al modelo carece de ruteo, fallback y seguimiento de uso." } },
      { icon: "Zap", who: { en: "DevOps teams automating infrastructure with AI", es: "Equipos DevOps automatizando infraestructura con IA" }, pain: { en: "Manual Terraform authoring is slow and error-prone without cloud context.", es: "La creación manual de Terraform es lenta y propensa a errores sin contexto de la nube." } },
    ],
    painPoints: [
      { en: "Writing Terraform for Huawei Cloud requires knowing exact resource IDs, flavors, and images — AI without cloud context hallucinates values.", es: "Escribir Terraform para Huawei Cloud requiere conocer IDs exactos de recursos, flavors e imágenes — la IA sin contexto de nube alucina valores." },
      { en: "Direct MaaS access lacks fallback and latency optimization.", es: "El acceso directo a MaaS carece de fallback y optimización de latencia." },
      { en: "No single model fits all tasks — coding, reasoning, and quick edits need different models.", es: "Ningún modelo único sirve para todas las tareas — coding, reasoning y ediciones rápidas necesitan modelos diferentes." },
    ],
    solutionApproach: [
      { en: "Install OpenCode on WSL with Node.js and connect to Huawei Cloud MaaS for LLM inference.", es: "Instale OpenCode en WSL con Node.js y conéctelo a Huawei Cloud MaaS para inferencia LLM.",
      replaces: { en: "Equivalent to GitHub Copilot with AWS/Azure — OpenCode + MaaS provides AI coding with Huawei Cloud models.", es: "Equivalente a GitHub Copilot con AWS/Azure — OpenCode + MaaS proporciona AI coding con modelos de Huawei Cloud." },
      referenceLinks: [{ label: "ModelArts MaaS", url: "https://www.huaweicloud.com/intl/en-us/product/maas.html" }],},
      { en: "Configure HCloud MCP server (90+ read-only tools across 18 services) and Terraform MCP for provider schema discovery.", es: "Configure servidor HCloud MCP (90+ herramientas de lectura en 18 servicios) y Terraform MCP para descubrimiento de schema de providers.",
      replaces: { en: "Equivalent to AWS Toolkit MCP — HCloud MCP wraps KooCLI for real-time cloud discovery.", es: "Equivalente a AWS Toolkit MCP — HCloud MCP envuelve KooCLI para descubrimiento de nube en tiempo real." },
      referenceLinks: [{ label: "OpenCode Setup", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/OpenCode-Setup" }],},
      { en: "AI discovers real cloud resources, writes valid Terraform with correct IDs, and performs day-2 operations through natural conversation.", es: "La IA descubre recursos reales de la nube, escribe Terraform válido con IDs correctos y realiza operaciones day-2 mediante conversación natural." },
      { en: "To go further with a proxy layer for model routing, latency-based fallbacks, and multi-provider support, OpenCode can also be configured with LiteLLM. The LiteLLM + Claude Code demonstration serves as a complete setup guide — the same proxy configuration applies directly to OpenCode.", es: "Para ir más allá con una capa de proxy para enrutamiento de modelos, fallbacks basados en latencia y soporte multi-provider, OpenCode también puede configurarse con LiteLLM. La demostración de LiteLLM + Claude Code sirve como guía completa de configuración — la misma configuración de proxy aplica directamente a OpenCode.", referenceLinks: [{ label: "LiteLLM + Claude Code Guide", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/ClaudeCode-LiteLLM-MaaS" }] },
    ],
    recommendedServices: ["ModelArts MaaS", "ECS"],
    demoSkillLinks: [
      link("OpenCode Setup", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/OpenCode-Setup"),
    ],
    migrationMainExample: {
      title: { en: "OpenCode + MaaS + MCP Integration", es: "OpenCode + MaaS + Integración MCP" },
      description: { en: "Install OpenCode on WSL, configure with Huawei Cloud MaaS models, and set up HCloud + Terraform MCP servers for infrastructure code generation.", es: "Instale OpenCode en WSL, configure con modelos de Huawei Cloud MaaS y configure servidores HCloud + Terraform MCP para generación de código de infraestructura." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/OpenCode-Setup",
    },
    migrationRelatedTools: [
      {
        title: { en: "OpenCode Setup", es: "Setup de OpenCode" },
        description: { en: "Installation and configuration guides for OpenCode with MCP servers and Huawei Cloud tools.", es: "Guías de instalación y configuración para OpenCode con servidores MCP y herramientas de Huawei Cloud." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/OpenCode-Setup",
      },
      {
        title: { en: "OpenCode Setup", es: "Setup de OpenCode" },
        description: { en: "Installation and configuration guides for OpenCode with MaaS models and MCP servers.", es: "Guías de instalación y configuración para OpenCode con modelos MaaS y servidores MCP." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/OpenCode-Setup",
      },
    ],
    presentationUrl: "/presentations/ai-coding-opencode.pdf",
            quickIntegration: {
    prerequisites: [
      { en: "WSL (Windows Subsystem for Linux) or Linux/macOS terminal", es: "WSL (Windows Subsystem for Linux) o terminal Linux/macOS", link: { label: "WSL Install Guide", url: "https://learn.microsoft.com/en-us/windows/wsl/install" } },
      { en: "Node.js v18+ and npm", es: "Node.js v18+ y npm", link: { label: "Node.js Download", url: "https://nodejs.org/en/download/" } },
      { en: "Python 3.8+ (for HCloud MCP server)", es: "Python 3.8+ (para servidor HCloud MCP)", link: { label: "Python Download", url: "https://www.python.org/downloads/" } },
      { en: "Docker (for Terraform MCP server)", es: "Docker (para servidor Terraform MCP)", link: { label: "Docker Install", url: "https://docs.docker.com/engine/install/" } },
      { en: "Huawei Cloud MaaS API key (AK/SK)", es: "API key de Huawei Cloud MaaS (AK/SK)", link: { label: "ModelArts MaaS", url: "https://www.huaweicloud.com/intl/en-us/product/maas.html" } },
    ],
    steps: [
      { en: "Install OpenCode: curl -fsSL https://opencode.ai/install | bash", es: "Instalar OpenCode: curl -fsSL https://opencode.ai/install | bash" },
      { en: "Install KooCLI: download, extract, and move hcloud to /usr/local/bin/", es: "Instalar KooCLI: descargar, extraer y mover hcloud a /usr/local/bin/" },
      { en: "Configure KooCLI with AK/SK: hcloud configure init", es: "Configurar KooCLI con AK/SK: hcloud configure init" },
      { en: "Configure OpenCode with MaaS models and MCP servers (HCloud + Terraform)", es: "Configurar OpenCode con modelos MaaS y servidores MCP (HCloud + Terraform)" },
      { en: "Validate: ask OpenCode to discover cloud resources and generate Terraform", es: "Validar: pida a OpenCode descubrir recursos de la nube y generar Terraform" },
    ],
      configuration: [
        { en: "Model selection: choose MaaS models based on latency, cost, and capability", es: "Selección de modelo: elija modelos MaaS según latencia, costo y capacidad" },
        { en: "MCP servers: HCloud MCP for cloud discovery, Terraform MCP for schema lookup", es: "Servidores MCP: HCloud MCP para descubrimiento de nube, Terraform MCP para schema" },
        { en: "KooCLI region: select the closest Huawei Cloud region", es: "Región de KooCLI: seleccione la región de Huawei Cloud más cercana" },
        { en: "Cost monitoring: set billing alerts to track MaaS API usage", es: "Monitoreo de costos: configure alertas de billing para uso de API MaaS" },
      ],
      apiAccess: [
        { en: "Install OpenCode: curl -fsSL https://opencode.ai/install | bash", es: "Instalar OpenCode: curl -fsSL https://opencode.ai/install | bash" },
        { en: "Install KooCLI: curl -LO https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz", es: "Instalar KooCLI: curl -LO https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz" },
        { en: "Configure KooCLI: hcloud configure init", es: "Configurar KooCLI: hcloud configure init" },
      ],
    },
      salesTalkTrack: [
      { en: "How does OpenCode know about my existing Huawei Cloud resources?", es: "¿Cómo sabe OpenCode sobre mis recursos existentes de Huawei Cloud?" },
      { en: "Can OpenCode write valid Terraform without me looking up resource IDs?", es: "¿Puede OpenCode escribir Terraform válido sin que yo busque IDs de recursos?" },
      { en: "What models are available through MaaS for coding tasks?", es: "¿Qué modelos están disponibles через MaaS para tareas de coding?" },
    ],
    expectedOutcomes: [
      { en: "OpenCode uses the HCloud MCP server to call KooCLI discovery tools — it lists your VPCs, subnets, flavors, and images in real time. The AI sees your actual cloud state, not guesses.", es: "OpenCode usa el servidor HCloud MCP para llamar herramientas de descubrimiento de KooCLI — lista sus VPCs, subredes, flavors e imágenes en tiempo real. La IA ve su estado real de nube, no adivina." },
      { en: "Yes. The Terraform MCP server provides provider schemas and the HCloud MCP provides real resource IDs. OpenCode generates Terraform with valid references — no hallucinated IDs or invalid parameters.", es: "Sí. El servidor Terraform MCP proporciona schemas de providers y HCloud MCP proporciona IDs reales de recursos. OpenCode genera Terraform con referencias válidas — sin IDs alucinados o parámetros inválidos." },
      { en: "MaaS offers 5 models including DeepSeek V4-Flash/V4.1-Flash, GLM-5.1/5.2/5.3 — covering economy, fast, coding, and reasoning tiers. You select models per task type with cost control.", es: "MaaS ofrece 5 modelos incluyendo DeepSeek V4-Flash/V4.1-Flash, GLM-5.1/5.2/5.3 — cubriendo tiers de economía, rápido, coding y reasoning. Selecciona modelos por tipo de tarea con control de costos." },
    ],
    heroImage: "/assets/huawei/hero-maas.jpg",
  },
  {
    id: "ai-coding-hermes",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "AI Tools", es: "AI Tools" },
    title: {
      en: "AI Coding with Hermes",
      es: "AI Coding con Hermes",
      zh: "AI Coding with Hermes",
    },
      oneLiner: {
      en: "Set up Huawei Hermes AI assistant with MaaS models and MCP integration on WSL.",
      es: "Configure el asistente AI Hermes de Huawei con modelos MaaS e integración MCP en WSL.",
      zh: "Set up Huawei Hermes AI assistant with MaaS models and MCP integration on WSL.",
    },
            targetCustomers: [
      { icon: "Code2", who: { en: "Huawei Cloud customers adopting Hermes as AI assistant", es: "Clientes de Huawei Cloud adoptando Hermes como asistente AI" }, pain: { en: "Need guided setup with correct MaaS configuration and API keys.", es: "Necesitan setup guiado con configuración correcta de MaaS y API keys." } },
      { icon: "ShieldCheck", who: { en: "Teams wanting Huawei-native AI tooling", es: "Equipos que quieren tooling AI nativo de Huawei" }, pain: { en: "Third-party AI tools lack deep Huawei Cloud integration.", es: "Las herramientas de IA de terceros carecen de integración profunda con Huawei Cloud." } },
    ],
    painPoints: [
      { en: "Hermes setup requires correct API key placement and MaaS endpoint configuration.", es: "El setup de Hermes requiere correcta colocación de API keys y configuración de endpoint MaaS." },
      { en: "Placeholders in public repos must be replaced with real credentials before use.", es: "Los placeholders en repos públicos deben reemplazarse con credenciales reales antes de usar." },
    ],
    solutionApproach: [
      { en: "Install Hermes on WSL using the provided install.sh script (idempotent).", es: "Instale Hermes en WSL usando el script install.sh proporcionado (idempotente)." },
      { en: "Replace placeholder API keys with real Huawei Cloud MaaS credentials.", es: "Reemplace los placeholder de API keys con credenciales reales de Huawei Cloud MaaS." },
      { en: "Verify Hermes Agent is running and connected to MaaS models.", es: "Verifique que Hermes Agent esté corriendo y conectado a modelos MaaS." },
    ],
    recommendedServices: ["ModelArts MaaS"],
    demoSkillLinks: [
      link("Hermes Setup", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/Hermes-Setup"),
    ],
    migrationMainExample: {
      title: { en: "Hermes Agent Setup", es: "Setup de Hermes Agent" },
      description: { en: "Install and configure Huawei Hermes AI assistant with MaaS models, MCP integration, and OpenCode compatibility.", es: "Instale y configure el asistente AI Hermes de Huawei con modelos MaaS, integración MCP y compatibilidad con OpenCode." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/Hermes-Setup",
    },
    migrationRelatedTools: [
      {
        title: { en: "Hermes Setup", es: "Setup de Hermes" },
        description: { en: "Configuration and setup guides for Huawei Hermes AI assistant with OpenCode and MCP integration.", es: "Guías de configuración y setup para el asistente AI Hermes de Huawei con integración OpenCode y MCP." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/Hermes-Setup",
        beta: true,
      },
    ],
    presentationUrl: "/presentations/ai-coding.pdf",
            quickIntegration: {
    prerequisites: [
      { en: "WSL (Windows Subsystem for Linux) or Linux/macOS terminal", es: "WSL (Windows Subsystem for Linux) o terminal Linux/macOS", link: { label: "WSL Install Guide", url: "https://learn.microsoft.com/en-us/windows/wsl/install" } },
      { en: "hcloud CLI configured with AK/SK credentials", es: "hcloud CLI configurado con credenciales AK/SK", link: { label: "KooCLI Install", url: "https://www.huaweicloud.com/intl/en-us/product/hcli.html" } },
      { en: "Huawei Cloud MaaS API key (AK/SK)", es: "API key de Huawei Cloud MaaS (AK/SK)", link: { label: "ModelArts MaaS", url: "https://www.huaweicloud.com/intl/en-us/product/maas.html" } },
    ],
    steps: [
      { en: "Copy hermes-repro directory to target machine", es: "Copiar directorio hermes-repro a la máquina destino" },
      { en: "Run install.sh (idempotent): bash install.sh", es: "Ejecutar install.sh (idempotente): bash install.sh" },
      { en: "Replace PLACEHOLDER_* values with real MaaS API keys", es: "Reemplazar valores PLACEHOLDER_* con API keys reales de MaaS" },
      { en: "Verify Hermes Agent is running and responding", es: "Verificar que Hermes Agent esté corriendo y respondiendo" },
    ],
      configuration: [
        { en: "API keys: replace all PLACEHOLDER_* values with real Huawei Cloud credentials", es: "API keys: reemplace todos los valores PLACEHOLDER_* con credenciales reales de Huawei Cloud" },
        { en: "MaaS endpoint: configure the correct region endpoint for model inference", es: "Endpoint MaaS: configure el endpoint de región correcto para inferencia de modelo" },
        { en: "MCP servers: ensure hcloud CLI is configured before starting Hermes", es: "Servidores MCP: asegure que hcloud CLI esté configurado antes de iniciar Hermes" },
      ],
      apiAccess: [
        { en: "Install hcloud CLI: curl -LO https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz", es: "Instalar hcloud CLI: curl -LO https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz" },
        { en: "Configure: hcloud configure init", es: "Configurar: hcloud configure init" },
        { en: "Setup Hermes: cd ~/hermes-repro && bash install.sh", es: "Setup Hermes: cd ~/hermes-repro && bash install.sh" },
      ],
    },
      salesTalkTrack: [
      { en: "How is Hermes different from OpenCode or Claude Code?", es: "¿Cómo es Hermes diferente de OpenCode o Claude Code?" },
      { en: "Can I use Hermes with existing MCP servers?", es: "¿Puedo usar Hermes con servidores MCP existentes?" },
    ],
    expectedOutcomes: [
      { en: "Hermes is Huawei's native AI assistant — it has deep integration with Huawei Cloud APIs and MaaS models out of the box, without needing external MCP servers for basic cloud operations.", es: "Hermes es el asistente AI nativo de Huawei — tiene integración profunda con APIs de Huawei Cloud y modelos MaaS listos para usar, sin necesitar servidores MCP externos para operaciones básicas de nube." },
      { en: "Yes. Hermes supports the MCP protocol and can use the same HCloud MCP and Terraform MCP servers as OpenCode. The hermes-setup skill configures MCP integration automatically.", es: "Sí. Hermes soporta el protocolo MCP y puede usar los mismos servidores HCloud MCP y Terraform MCP que OpenCode. El skill hermes-setup configura la integración MCP automáticamente." },
    ],
    heroImage: "/assets/huawei/hero-maas.jpg",
  },
  {
    id: "ai-coding-claude-code",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "AI Tools", es: "AI Tools" },
    title: {
      en: "AI Coding with Claude Code + LiteLLM",
      es: "AI Coding con Claude Code + LiteLLM",
      zh: "AI Coding with Claude Code + LiteLLM",
    },
      oneLiner: {
      en: "Configure Claude Code with LiteLLM proxy and Huawei Cloud MaaS — model aliases, latency routing, and fallbacks.",
      es: "Configure Claude Code con proxy LiteLLM y Huawei Cloud MaaS — aliases de modelos, ruteo por latencia y fallbacks.",
      zh: "Configure Claude Code with LiteLLM proxy and Huawei Cloud MaaS — model aliases, latency routing, and fallbacks.",
    },
            targetCustomers: [
      { icon: "Code2", who: { en: "Developers using Claude Code with Huawei Cloud models", es: "Desarrolladores que usan Claude Code con modelos de Huawei Cloud" }, pain: { en: "Claude Code only recognizes Claude model names — need aliases for MaaS models.", es: "Claude Code solo reconoce nombres de modelos Claude — necesitan aliases para modelos MaaS." } },
      { icon: "ShieldCheck", who: { en: "Organizations needing governed model routing", es: "Organizaciones que necesitan ruteo de modelos gobernado" }, pain: { en: "Direct MaaS access lacks fallback and latency optimization.", es: "El acceso directo a MaaS carece de fallback y optimización de latencia." } },
      { icon: "Zap", who: { en: "Teams wanting latency-optimized routing with fallbacks", es: "Equipos que quieren ruteo optimizado por latencia con fallbacks" }, pain: { en: "No single model fits all tasks — coding, reasoning, and quick edits need different models.", es: "Ningún modelo único sirve para todas las tareas — coding, reasoning y ediciones rápidas necesitan modelos diferentes." } },
    ],
    painPoints: [
      { en: "Claude Code validates model names at startup and rejects non-Claude model names.", es: "Claude Code valida nombres de modelos al iniciar y rechaza nombres no-Claude." },
      { en: "Direct MaaS access lacks fallback and latency optimization.", es: "El acceso directo a MaaS carece de fallback y optimización de latencia." },
      { en: "No single model fits all tasks — coding, reasoning, and quick edits need different models.", es: "Ningún modelo único sirve para todas las tareas — coding, reasoning y ediciones rápidas necesitan modelos diferentes." },
    ],
    solutionApproach: [
      { en: "Deploy LiteLLM proxy locally in a Python 3.12 venv — no ECS or OBS needed for single-developer use.", es: "Despliegue proxy LiteLLM localmente en un venv Python 3.12 — no necesita ECS u OBS para uso single-developer.",
      replaces: { en: "Equivalent to AWS Bedrock, Azure OpenAI Service, and GCP Vertex AI — ModelArts MaaS offers an OpenAI-compatible API with 5 models including DeepSeek and GLM.", es: "Equivalente a AWS Bedrock, Azure OpenAI Service y GCP Vertex AI — ModelArts MaaS ofrece una API compatible con OpenAI con 5 modelos incluyendo DeepSeek y GLM." },
      referenceLinks: [{ label: "LiteLLM Docs", url: "https://docs.litellm.ai/" }],},
      { en: "Configure LiteLLM with MaaS model aliases (claude-haiku-4-20250514 → deepseek-v4.1-flash, claude-haiku-4-pro-20250514 → glm-5.3). Claude Code sends these model names; LiteLLM forwards to Huawei Cloud MaaS.", es: "Configure LiteLLM con aliases de modelos MaaS (claude-haiku-4-20250514 → deepseek-v4.1-flash, claude-haiku-4-pro-20250514 → glm-5.3). Claude Code envía estos nombres; LiteLLM los reenvía a Huawei Cloud MaaS.",
      replaces: { en: "Claude Code accepts arbitrary model names — no Claude-specific aliases needed.", es: "Claude Code acepta nombres arbitrarios de modelos — no se necesitan aliases específicos de Claude." },
      referenceLinks: [{ label: "ModelArts MaaS", url: "https://www.huaweicloud.com/intl/en-us/product/maas.html" }],},
      { en: "Configure 5 routing groups: economy (V4-Flash), fast (V4.1-Flash), coding (V4-Flash), coding-heavy (GLM-5.2), reasoning (GLM-5.3/GLM-5.1) with cross-group fallbacks.", es: "Configure 5 grupos de ruteo: economy (V4-Flash), fast (V4.1-Flash), coding (V4-Flash), coding-heavy (GLM-5.2), reasoning (GLM-5.3/GLM-5.1) con fallbacks cruzados." },
    ],
    recommendedServices: ["ModelArts MaaS", "ECS"],
    demoSkillLinks: [
      link("Claude Code + LiteLLM MaaS", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/ClaudeCode-LiteLLM-MaaS"),
    ],
    migrationMainExample: {
      title: { en: "Claude Code + LiteLLM Proxy + MaaS", es: "Claude Code + Proxy LiteLLM + MaaS" },
      description: { en: "Configure Claude Code with LiteLLM proxy as gateway to Huawei Cloud MaaS. Uses model-name aliases so Claude Code recognizes MaaS models as Claude models.", es: "Configure Claude Code con proxy LiteLLM como gateway a Huawei Cloud MaaS. Usa aliases de nombres de modelo para que Claude Code reconozca modelos MaaS como modelos Claude." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/ClaudeCode-LiteLLM-MaaS",
    },
    migrationRelatedTools: [
      {
        title: { en: "Claude Code + LiteLLM MaaS", es: "Claude Code + LiteLLM MaaS" },
        description: { en: "Configure Claude Code with Huawei Cloud MaaS models via LiteLLM proxy. Includes model aliases, latency-based routing, and fallbacks.", es: "Configure Claude Code con modelos de Huawei Cloud MaaS vía proxy LiteLLM. Incluye aliases de modelos, ruteo por latencia y fallbacks." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/ClaudeCode-LiteLLM-MaaS",
      },
    ],
    presentationUrl: "/presentations/ai-coding-claude-code.pdf",
            quickIntegration: {
    prerequisites: [
      { en: "WSL (Windows Subsystem for Linux) or Linux/macOS terminal", es: "WSL (Windows Subsystem for Linux) o terminal Linux/macOS", link: { label: "WSL Install Guide", url: "https://learn.microsoft.com/en-us/windows/wsl/install" } },
      { en: "Node.js v20+ and npm (for Claude Code)", es: "Node.js v20+ y npm (para Claude Code)", link: { label: "Node.js Download", url: "https://nodejs.org/en/download/" } },
      { en: "Python 3.12+ (for LiteLLM proxy)", es: "Python 3.12+ (para proxy LiteLLM)", link: { label: "Python Download", url: "https://www.python.org/downloads/" } },
      { en: "Huawei Cloud MaaS API key (AK/SK)", es: "API key de Huawei Cloud MaaS (AK/SK)", link: { label: "ModelArts MaaS", url: "https://www.huaweicloud.com/intl/en-us/product/maas.html" } },
    ],
    steps: [
      { en: "Install Claude Code: npm install -g @anthropic-ai/claude-code", es: "Instalar Claude Code: npm install -g @anthropic-ai/claude-code" },
      { en: "Create Python venv and install LiteLLM: python3 -m venv litellm-venv && source litellm-venv/bin/activate && pip install litellm", es: "Crear venv Python e instalar LiteLLM: python3 -m venv litellm-venv && source litellm-venv/bin/activate && pip install litellm" },
      { en: "Configure LiteLLM with MaaS model aliases (claude-haiku-4-20250514 → deepseek-v4.1-flash, claude-haiku-4-pro-20250514 → glm-5.3) so Claude Code routes requests through LiteLLM to MaaS", es: "Configurar LiteLLM con aliases de modelos MaaS (claude-haiku-4-20250514 → deepseek-v4.1-flash, claude-haiku-4-pro-20250514 → glm-5.3) para que Claude Code enrute peticiones a través de LiteLLM hacia MaaS" },
      { en: "Start LiteLLM proxy and point Claude Code to localhost:4000 as its model endpoint", es: "Iniciar proxy LiteLLM y apuntar Claude Code a localhost:4000 como su endpoint de modelo" },
      { en: "Validate: run coding tasks and verify Claude Code routes through LiteLLM to MaaS", es: "Validar: ejecute tareas de coding y verifique que Claude Code enrute a través de LiteLLM hacia MaaS" },
    ],
      configuration: [
        { en: "Models: claude-haiku-4-20250514 → deepseek-v4.1-flash (default, fast), claude-haiku-4-pro-20250514 → glm-5.3 (heavy coding/reasoning)", es: "Modelos: claude-haiku-4-20250514 → deepseek-v4.1-flash (default, rápido), claude-haiku-4-pro-20250514 → glm-5.3 (coding pesado/reasoning)" },
        { en: "Routing groups: economy (V4-Flash), fast (V4.1-Flash), coding (V4-Flash), coding-heavy (GLM-5.2), reasoning (GLM-5.3/GLM-5.1)", es: "Grupos de ruteo: economy (V4-Flash), fast (V4.1-Flash), coding (V4-Flash), coding-heavy (GLM-5.2), reasoning (GLM-5.3/GLM-5.1)" },
        { en: "Fallbacks: economy→fast→coding, coding→coding-heavy→reasoning for resilience", es: "Fallbacks: economy→fast→coding, coding→coding-heavy→reasoning para resiliencia" },
        { en: "Cost monitoring: set billing alerts to track MaaS API usage per developer", es: "Monitoreo de costos: configure alertas de billing para uso de API MaaS por desarrollador" },
      ],
      apiAccess: [
        { en: "Install Claude Code: npm install -g @anthropic-ai/claude-code", es: "Instalar Claude Code: npm install -g @anthropic-ai/claude-code" },
        { en: "Install LiteLLM: pip install litellm", es: "Instalar LiteLLM: pip install litellm" },
        { en: "Start proxy: litellm --model custom_openai/maas --api_base https://maas.huaweicloud.com/v1", es: "Iniciar proxy: litellm --model custom_openai/maas --api_base https://maas.huaweicloud.com/v1" },
      ],
    },
      salesTalkTrack: [
      { en: "How does Claude Code route to MaaS models via LiteLLM?", es: "¿Cómo enruta Claude Code a modelos MaaS vía LiteLLM?" },
      { en: "How does the LiteLLM proxy handle model outages or high-latency responses?", es: "¿Cómo maneja el proxy LiteLLM interrupciones de modelo o respuestas de alta latencia?" },
      { en: "Can I control which MaaS models my developers use and how much they cost?", es: "¿Puedo controlar qué modelos MaaS usan mis desarrolladores y cuánto cuestan?" },
    ],
    expectedOutcomes: [
      { en: "Use LiteLLM proxy with MaaS model aliases. LiteLLM registers claude-haiku-4-20250514 and claude-haiku-4-pro-20250514 as model names that map to Huawei Cloud MaaS (deepseek-v4.1-flash and glm-5.3). Claude Code sends requests with these model names; LiteLLM transparently routes to MaaS. This is the recommended approach for Claude Code + MaaS.", es: "Use proxy LiteLLM con aliases de modelos MaaS. LiteLLM registra claude-haiku-4-20250514 y claude-haiku-4-pro-20250514 como nombres de modelo que mapean a Huawei Cloud MaaS (deepseek-v4.1-flash y glm-5.3). Claude Code envía peticiones con estos nombres; LiteLLM enruta transparentemente a MaaS. Este es el enfoque recomendado para Claude Code + MaaS." },
      { en: "The LiteLLM proxy monitors model latency and availability in real time. If a MaaS model is slow or unavailable, it automatically falls back to an alternative per the configured fallback chains. Developers experience no interruptions.", es: "El proxy LiteLLM monitorea latencia y disponibilidad del modelo en tiempo real. Si un modelo MaaS es lento o no disponible, automáticamente usa un alternativo según las cadenas de fallback configuradas. Los desarrolladores no experimentan interrupciones." },
      { en: "Yes. LiteLLM sets up model tiering with per-developer and per-project budgets. You define which MaaS models are available, set spending limits, and get alerts when costs approach thresholds.", es: "Sí. LiteLLM configura tiering de modelos con presupuestos por desarrollador y por proyecto. Usted define qué modelos MaaS están disponibles, establece límites de gasto y recibe alertas cuando los costos se acercan a los umbrales." },
    ],
    heroImage: "/assets/huawei/hero-maas.jpg",
  },
  {
    id: "claude-code-litellm-maas",
    entryId: "on-prem-to-cloud",
    title: {
      en: "Claude Code + LiteLLM + MaaS",
      es: "Claude Code + LiteLLM + MaaS",
    },
    oneLiner: {
      en: "Connect Claude Code to Huawei Cloud MaaS via LiteLLM proxy for governed, cost-visible AI coding with model routing and fallbacks.",
      es: "Conecte Claude Code a MaaS de Huawei Cloud via proxy LiteLLM para AI Coding gobernado, con visibilidad de costos, ruteo de modelos y fallbacks.",
    },
    targetCustomers: [
      { en: "Teams using Claude Code for AI-assisted development", es: "Equipos que usan Claude Code para desarrollo asistido por IA" },
      { en: "Organizations needing cost control over AI coding tool usage", es: "Organizaciones que necesitan control de costos sobre uso de herramientas de AI Coding" },
    ],
    painPoints: [
      { en: "Claude Code direct API access lacks cost governance and fallback.", es: "El acceso directo de Claude Code a API carece de gobierno de costos y fallback." },
      { en: "Teams need a single gateway for multiple AI coding tools.", es: "Los equipos necesitan un unico gateway para multiples herramientas de AI Coding." },
    ],
    solutionApproach: [
      { en: "Deploy LiteLLM proxy with MaaS backend on ECS.", es: "Despliegue proxy LiteLLM con backend MaaS en ECS." },
      { en: "Configure Claude Code to route through the LiteLLM proxy.", es: "Configure Claude Code para rutear a traves del proxy LiteLLM." },
      { en: "Enable logging, cost tracking, and model fallbacks.", es: "Habilite logging, tracking de costos y fallbacks de modelos." },
    ],
    recommendedServices: ["ModelArts MaaS", "ECS", "OBS", "Cloud Eye"],
    demoSkillLinks: [
      link("Claude Code LiteLLM MaaS", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/ClaudeCode-LiteLLM-MaaS"),
    ],
    quickIntegration: {
      prerequisites: [
        { en: "MaaS API key and Claude Code installed.", es: "API key de MaaS y Claude Code instalado." },
        { en: "ECS instance for LiteLLM proxy deployment.", es: "Instancia ECS para despliegue del proxy LiteLLM." },
      ],
      steps: [
        { en: "Deploy LiteLLM proxy with MaaS model configuration.", es: "Despliegue proxy LiteLLM con configuracion de modelos MaaS." },
        { en: "Configure Claude Code environment to use the proxy endpoint.", es: "Configure entorno de Claude Code para usar el endpoint del proxy." },
        { en: "Validate coding workflows and monitor cost dashboards.", es: "Valide flujos de coding y monitoree dashboards de costos." },
      ],
      configuration: [
        { en: "Define model routing rules, token limits, and logging policies.", es: "Defina reglas de ruteo de modelos, limites de tokens y politicas de logging." },
      ],
      apiAccess: [
        { en: "Expose LiteLLM proxy as the single endpoint for Claude Code.", es: "Exponga proxy LiteLLM como el endpoint unico para Claude Code." },
      ],
    },
    salesTalkTrack: [
      { en: "How are you governing Claude Code API access and costs today?", es: "Como gobierna el acceso API y costos de Claude Code hoy?" },
    ],
    expectedOutcomes: [
      { en: "Governed Claude Code access with cost visibility.", es: "Acceso gobernado de Claude Code con visibilidad de costos." },
      { en: "Model fallback resilience for uninterrupted coding.", es: "Resiliencia de fallback de modelos para coding ininterrumpido." },
    ],
    heroImage: "/assets/huawei/hero-maas.jpg",
  },
  {
    id: "cloud-foundation",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Cloud Foundation", es: "Cloud Foundation" },
    title: {
      en: "Cloud Foundation",
      es: "Cloud Foundation",
      zh: "云基础底座",
    },
      oneLiner: {
      en: "Build cloud readiness with local migration rehearsal and service mapping before moving to Huawei Cloud.",
      es: "Construya readiness cloud con ensayo local de migración y mapeo de servicios antes de mover a Huawei Cloud.",
      zh: "在迁移到华为云之前，通过本地迁移演练和服务映射建立云上就绪能力。",
    },
            targetCustomers: [
      { icon: "FlaskConical", who: { en: "Migration architects rehearsing cloud-to-cloud migrations", es: "Arquitectos de migracion ensayando migraciones cloud-to-cloud" }, pain: { en: "Testing on real clouds is expensive and risky.", es: "Probar en nubes reales es costoso y riesgoso." } },
      { icon: "GraduationCap", who: { en: "Development teams building migration skills", es: "Equipos de desarrollo construyendo skills de migracion" }, pain: { en: "No safe sandbox to develop and validate.", es: "Sin sandbox seguro para desarrollar y validar." } },
      { icon: "BookOpen", who: { en: "Organizations training teams on Huawei Cloud", es: "Organizaciones entrenando equipos en Huawei Cloud" }, pain: { en: "Teams know AWS/Azure/GCP APIs but need to learn Huawei equivalents.", es: "Equipos conocen APIs de AWS/Azure/GCP pero necesitan aprender equivalentes de Huawei." } },
    ],
    painPoints: [
      { en: "Testing migration workflows on real clouds is expensive and risky.", es: "Probar flujos de migración en nubes reales es costoso y riesgoso." },
      { en: "No safe sandbox exists for developing and validating migration skills.", es: "No existe un sandbox seguro para desarrollar y validar skills de migración." },
      { en: "Teams know AWS/Azure/GCP APIs but need to learn Huawei Cloud equivalents.", es: "Los equipos conocen APIs de AWS/Azure/GCP pero necesitan aprender equivalentes de Huawei Cloud." },
    ],
    solutionApproach: [
      { en: "Install floci locally via Docker: AWS emulation on port 4566 (50+ services), Azure on port 4577 (20 services), GCP on port 4588 (21 services).", es: "Instale floci localmente via Docker: emulación AWS en puerto 4566 (50+ servicios), Azure en puerto 4577 (20 servicios), GCP en puerto 4588 (21 servicios).",
      replaces: { en: "Emulates AWS (50+ services), Azure (20), and GCP (21) locally — test migrations without cloud costs or risk.", es: "Emula AWS (50+ servicios), Azure (20) y GCP (21) localmente — pruebe migraciones sin costos de nube ni riesgo." },},
      { en: "Configure MCP servers: @yawlabs/aws-mcp for AWS, custom Node.js server for Azure (@azure/mcp is incompatible), gcp-mcp for GCP.", es: "Configure servidores MCP: @yawlabs/aws-mcp para AWS, servidor Node.js custom para Azure (@azure/mcp es incompatible), gcp-mcp para GCP." },
      { en: "Map source cloud services to Huawei Cloud equivalents: EC2→ECS, S3→OBS, RDS→RDS, Lambda→FunctionGraph, DynamoDB→GeminiDB, VPC→VPC, IAM→IAM.", es: "Mapee servicios de nube origen a equivalentes de Huawei Cloud: EC2→ECS, S3→OBS, RDS→RDS, Lambda→FunctionGraph, DynamoDB→GeminiDB, VPC→VPC, IAM→IAM.",
      replaces: { en: "Maps EC2→ECS, S3→OBS, Lambda→FunctionGraph, DynamoDB→GeminiDB, and 39 more — learn Huawei Cloud using familiar APIs.", es: "Mapea EC2→ECS, S3→OBS, Lambda→FunctionGraph, DynamoDB→GeminiDB y 39 más — aprenda Huawei Cloud usando APIs familiares." },
      referenceLinks: [{ label: "ECS — Elastic Cloud Server", url: "https://www.huaweicloud.com/intl/en-us/product/ecs.html" }, { label: "OBS — Object Storage Service", url: "https://www.huaweicloud.com/intl/en-us/product/obs.html" }, { label: "GeminiDB", url: "https://www.huaweicloud.com/intl/en-us/product/geminidb.html" }, { label: "FunctionGraph", url: "https://www.huaweicloud.com/intl/en-us/product/functiongraph.html" }],},
      { en: "Test workflows against local endpoints, then validate on real Huawei Cloud before cutover.", es: "Pruebe flujos contra endpoints locales, luego valide en Huawei Cloud real antes del cutover.",
      referenceLinks: [{ label: "CCE — Cloud Container Engine", url: "https://www.huaweicloud.com/intl/en-us/product/cce.html" }],},
    ],
    recommendedServices: ["ECS", "CCE", "OBS", "RDS", "VPC", "GeminiDB", "FunctionGraph", "DMS", "DEW", "SWR"],
    demoSkillLinks: [
      link("Cloud Foundation", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation"),
    ],
    migrationMainExample: {
      title: { en: "Cloud Foundation Setup Tools", es: "Herramientas de setup de Cloud Foundation" },
      description: { en: "Foundational cloud setup and operations: landing zones, IaC automation, local emulators, DR/backup, and AIOps tool interconnection.", es: "Setup fundamental de cloud y operaciones: landing zones, automatización IaC, emuladores locales, DR/backup e interconexión de herramientas AIOps." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation",
    },
    migrationRelatedTools: [
      {
        title: { en: "Automation and IaC", es: "Automatización e IaC" },
        description: { en: "Terraform IaC, CLI tooling, and automation scripts for standardized cloud operations.", es: "Terraform IaC, tooling de CLI y scripts de automatización para operaciones de nube estandarizadas." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Automation-and-IaC",
      },
      {
        title: { en: "Landing Zone and Organization Management", es: "Landing Zone y Gestión de Organización" },
        description: { en: "Multi-account landing zone design, organization governance, IAM, and Identity Center.", es: "Diseño de landing zone multi-cuenta, gobernanza de organización, IAM e Identity Center." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Landing-Zone-and-Organization-Management",
      },
      {
        title: { en: "Operations, AIOps and Tool Interconnection", es: "Operaciones, AIOps e Interconexión de Herramientas" },
        description: { en: "Operational excellence, AIOps, alert governance, and third-party tool integration.", es: "Excelencia operacional, AIOps, gobernanza de alertas e integración de herramientas de terceros." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Operations-AIOps-and-Tool-Interconnection",
      },
      {
        title: { en: "DR and Backup", es: "DR y Backup" },
        description: { en: "Backup strategy, disaster recovery design, failover planning, and continuity exercises.", es: "Estrategia de backup, diseño de disaster recovery, planificación de failover y ejercicios de continuidad." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup",
      },
      {
        title: { en: "Local Cloud Emulators", es: "Emuladores de Nube Locales" },
        description: { en: "Local AWS/Azure/GCP emulators (floci) for cost-free migration practice.", es: "Emuladores locales de AWS/Azure/GCP (floci) para práctica de migración sin costo." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Local-Cloud-Emulators",
      },
      {
        title: { en: "AWS CloudFormation to RFS", es: "AWS CloudFormation a RFS" },
        description: { en: "Migrate AWS CloudFormation templates to Huawei Cloud RFS (Resource Formation Service). Includes template translation, resource mapping, and stack deployment.", es: "Migre plantillas de AWS CloudFormation a Huawei Cloud RFS (Resource Formation Service). Incluye traducción de plantillas, mapeo de recursos y despliegue de stacks." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/AWS-CloudFormation-to-RFS",
        beta: true,
      },
      {
        title: { en: "AWS CloudWatch to Huawei CES", es: "AWS CloudWatch a Huawei CES" },
        description: { en: "Migrate AWS CloudWatch alarms, dashboards, and log groups to Huawei Cloud CES (Cloud Eye Service). Covers metric mapping, alarm translation, and log pipeline setup.", es: "Migre alarms, dashboards y log groups de AWS CloudWatch a Huawei Cloud CES (Cloud Eye Service). Cubre mapeo de métricas, traducción de alarms y setup de pipeline de logs." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/AWS-CloudWatch-to-Huawei-CES",
        beta: true,
      },
      {
        title: { en: "AWS IAM to Huawei IAM", es: "AWS IAM a Huawei IAM" },
        description: { en: "Migrate AWS IAM users, roles, policies, and groups to Huawei Cloud IAM. Covers policy translation, trust relationship mapping, and permission boundary conversion.", es: "Migre users, roles, policies y groups de AWS IAM a Huawei Cloud IAM. Cubre traducción de policies, mapeo de trust relationships y conversión de permission boundaries." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/AWS-IAM-to-Huawei-IAM",
        beta: true,
      },
      {
        title: { en: "AWS KMS to Huawei DEW", es: "AWS KMS a Huawei DEW" },
        description: { en: "Migrate AWS KMS keys and encryption policies to Huawei Cloud DEW (Data Encryption Workshop). Covers key material import, alias mapping, and envelope encryption compatibility.", es: "Migre keys y políticas de encriptación de AWS KMS a Huawei Cloud DEW (Data Encryption Workshop). Cubre import de key material, mapeo de aliases y compatibilidad de envelope encryption." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/AWS-KMS-to-Huawei-DEW",
        beta: true,
      },
      {
        title: { en: "AWS VPC to Huawei VPC", es: "AWS VPC a Huawei VPC" },
        description: { en: "Migrate AWS VPCs, subnets, route tables, security groups, and NAT gateways to Huawei Cloud VPC. Includes CIDR planning, firewall rule translation, and peering setup.", es: "Migre VPCs, subnets, route tables, security groups y NAT gateways de AWS a Huawei Cloud VPC. Incluye planning de CIDR, traducción de firewall rules y setup de peering." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/AWS-VPC-to-Huawei-VPC",
        beta: true,
      },
    ],
    migrationExamples: [
      {
        title: { en: "hcloud-cli", es: "hcloud-cli" },
        description: { en: "Huawei Cloud CLI (KooCLI) for command-line infrastructure management.", es: "CLI de Huawei Cloud (KooCLI) para gestión de infraestructura por línea de comandos." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Automation-and-IaC/hcloud-cli",
      },
      {
        title: { en: "huaweicloud-terraform-planner", es: "huaweicloud-terraform-planner" },
        description: { en: "Plan and write Terraform for Huawei Cloud by discovering real values from the live cloud.", es: "Planifique y escriba Terraform para Huawei Cloud descubriendo valores reales de la nube." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Automation-and-IaC/huaweicloud-terraform-planner",
      },
      {
        title: { en: "Landing-Zone-Demo", es: "Landing-Zone-Demo" },
        description: { en: "Demonstration of a multi-account landing zone setup on Huawei Cloud.", es: "Demostración de setup de landing zone multi-cuenta en Huawei Cloud." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Landing-Zone-and-Organization-Management/Landing-Zone-Demo",
      },
      {
        title: { en: "multi-account-landing-zone", es: "multi-account-landing-zone" },
        description: { en: "Multi-account landing zone design with IAM and Identity Center governance.", es: "Diseño de landing zone multi-cuenta con gobernanza IAM e Identity Center." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Landing-Zone-and-Organization-Management/multi-account-landing-zone",
      },
      {
        title: { en: "huawei-cbr-backup-restore", es: "huawei-cbr-backup-restore" },
        description: { en: "CBR backup and restore skill for Huawei Cloud resources.", es: "Skill de backup y restore con CBR para recursos de Huawei Cloud." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/huawei-cbr-backup-restore",
      },
      {
        title: { en: "huawei-sdr-cross-region-replication", es: "huawei-sdr-cross-region-replication" },
        description: { en: "SDR cross-region replication skill for disaster recovery.", es: "Skill de replicación cross-region con SDR para disaster recovery." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/huawei-sdr-cross-region-replication",
      },
      {
        title: { en: "floci-aws-mcp-setup", es: "floci-aws-mcp-setup" },
        description: { en: "Configure floci local AWS emulator with AWS MCP server.", es: "Configure el emulador local AWS floci con servidor AWS MCP." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Local-Cloud-Emulators/floci-aws-mcp-setup",
      },
      {
        title: { en: "floci-az-mcp-setup", es: "floci-az-mcp-setup" },
        description: { en: "Configure floci-az local Azure emulator with custom MCP server.", es: "Configure el emulador local Azure floci-az con servidor MCP custom." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Local-Cloud-Emulators/floci-az-mcp-setup",
      },
      {
        title: { en: "floci-gcp-mcp-setup", es: "floci-gcp-mcp-setup" },
        description: { en: "Configure floci-gcp local GCP emulator with GCP MCP server.", es: "Configure el emulador local GCP floci-gcp con servidor GCP MCP." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Local-Cloud-Emulators/floci-gcp-mcp-setup",
      },
    ],
    presentationUrl: "/presentations/cloud-foundation.pdf",
            quickIntegration: {
    prerequisites: [
      { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
      { en: "Recommended skills installed in ~/.opencode/skills/ (or equivalent).", es: "Skills recomendados instalados en ~/.opencode/skills/ (o equivalente).", link: { label: "GitHub Skills", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation" } },
      { en: "Docker installed locally.", es: "Docker instalado localmente." },
    ],
    steps: [
      { en: "Discover with AI: AI scans your existing infrastructure — VPCs, security groups, compute, and storage. Verify the results against your actual environment.", es: "Descubrir con IA: La IA escanea su infraestructura existente — VPCs, security groups, compute y storage. Verifique los resultados contra su entorno actual." },
      { en: "Plan with AI: AI generates Terraform code to recreate your infrastructure on Huawei Cloud. Review the plan before proceeding.", es: "Planificar con IA: La IA genera código Terraform para recrear su infraestructura en Huawei Cloud. Revise el plan antes de continuar." },
      { en: "Build with AI: AI deploys foundational infrastructure — VPC, NAT, security groups, IAM on Huawei Cloud using the generated Terraform.", es: "Construir con IA: La IA despliega infraestructura base — VPC, NAT, security groups, IAM en Huawei Cloud usando el Terraform generado." },
      { en: "Rehearse with AI: AI creates a local sandbox to test the migration workflow before running against real Huawei Cloud resources.", es: "Ensayar con IA: La IA crea un sandbox local para probar el flujo de migración antes de ejecutarlo contra recursos reales de Huawei Cloud." },
      { en: "Validate with AI: AI verifies network connectivity, security rules, and IAM permissions in both the sandbox and the real environment.", es: "Validar con IA: La IA verifica conectividad de red, reglas de seguridad y permisos IAM tanto en el sandbox como en el entorno real." },
      { en: "Apply with AI: Run the validated Terraform against Huawei Cloud. Require specific evidence that all resources are created correctly before proceeding.", es: "Aplicar con IA: Ejecute el Terraform validado contra Huawei Cloud. Exija evidencia específica de que todos los recursos se crean correctamente antes de continuar." },
    ],
      configuration: [
        { en: "IAM structure first: define org units, accounts, and permission boundaries before deploying", es: "Estructura IAM primero: defina org units, cuentas y permission boundaries antes de desplegar" },
        { en: "Network design: VPC peering, NAT gateways, and security groups must be planned upfront", es: "Diseño de red: VPC peering, NAT gateways y security groups deben planificarse upfront" },
        { en: "Region selection: choose regions based on latency, compliance, and service availability", es: "Selección de región: elija regiones según latencia, compliance y disponibilidad de servicios" },
        { en: "Resource quotas: default quotas may be too low for production — request increases early", es: "Quotas de recursos: las quotas por defecto pueden ser bajas para producción — solicite aumentos temprano" },
        { en: "Tagging strategy: define consistent tags for cost allocation and resource management", es: "Estrategia de tagging: defina tags consistentes para asignación de costos y gestión de recursos" },
      ],
      apiAccess: [
        { en: "Create VPC: hcloud VPC CreateVpc --name=prod-vpc --cidr=192.168.0.0/16", es: "Crear VPC: hcloud VPC CreateVpc --name=prod-vpc --cidr=192.168.0.0/16" },
        { en: "Create subnet: hcloud VPC CreateSubnet --vpc_id=xxx --name=prod-subnet --cidr=192.168.0.0/24", es: "Crear subnet: hcloud VPC CreateSubnet --vpc_id=xxx --name=prod-subnet --cidr=192.168.0.0/24" },
        { en: "Create IAM user: hcloud IAM CreateUserV5 --user_name=dev-team", es: "Crear usuario IAM: hcloud IAM CreateUserV5 --user_name=dev-team" },
        { en: "Create security group: hcloud VPC CreateSecurityGroup/v3 --name=prod-sg", es: "Crear security group: hcloud VPC CreateSecurityGroup/v3 --name=prod-sg" },
      ],
    },
      salesTalkTrack: [
      { en: "How can my team learn Huawei Cloud without paying for cloud resources?", es: "¿Cómo puede mi equipo aprender Huawei Cloud sin pagar por recursos de nube?" },
      { en: "Can we practice migrations before running them on real infrastructure?", es: "¿Podemos practicar migraciones antes de ejecutarlas en infraestructura real?" },
      { en: "Does AI help with infrastructure-as-code for Huawei Cloud?", es: "¿La IA ayuda con infrastructure-as-code para Huawei Cloud?" },
    ],
    expectedOutcomes: [
      { en: "AI generates Terraform code from your existing infrastructure — reading your current VPCs, security groups, and compute resources, then writing the Terraform to recreate them on Huawei Cloud. Your team learns by reviewing and applying the generated code without provisioning expensive cloud resources.", es: "La IA genera código Terraform desde su infraestructura existente — leyendo sus VPCs, security groups y recursos de compute actuales, luego escribiendo el Terraform para recrearlos en Huawei Cloud. Su equipo aprende revisando y aplicando el código generado sin provisionar recursos de nube costosos." },
      { en: "Yes. AI creates a local sandbox that emulates Huawei Cloud APIs, so your team can rehearse the full migration workflow — discover, plan, apply — in a safe environment. They practice without risk, then run the same code against Huawei Cloud when ready.", es: "Sí. La IA crea un sandbox local que emula las APIs de Huawei Cloud, para que su equipo pueda ensayar el flujo completo de migración — descubrir, planear, aplicar — en un entorno seguro. Practican sin riesgo y luego ejecutan el mismo código contra Huawei Cloud cuando estén listos." },
      { en: "Yes. AI generates Terraform modules for Huawei Cloud resources using the latest provider schema. It reads your existing infrastructure from AWS, Azure, or on-premises and produces Huawei Cloud equivalents. Your team reviews, adjusts, and deploys with confidence.", es: "Sí. La IA genera módulos de Terraform para recursos de Huawei Cloud usando el último schema del provider. Lee su infraestructura existente de AWS, Azure u on-premises y produce equivalentes en Huawei Cloud. Su equipo revisa, ajusta y despliega con confianza." },
    ],
    heroImage: "/assets/huawei/official-cache/nn3-1a641eacb42d393d.jpg",
  },
  {
    id: "vpn-connectivity",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Cloud Foundation", es: "Cloud Foundation" },
    title: {
      en: "VPN Connectivity",
      es: "Conectividad VPN",
      zh: "VPN 连接",
    },
    oneLiner: {
      en: "Create IPsec site-to-cloud VPN tunnels to Huawei Cloud with AI-assisted configuration, validation, and troubleshooting.",
      es: "Cree túneles VPN IPsec site-to-cloud hacia Huawei Cloud con configuración, validación y troubleshooting asistidos por IA.",
      zh: "通过 AI 辅助配置、验证和故障排除，创建到华为云的 IPsec 站点到云 VPN 隧道。",
    },
    targetCustomers: [
      { icon: "Shield", who: { en: "Network engineers connecting on-premises or other clouds to Huawei Cloud via VPN", es: "Ingenieros de red conectando on-premises u otras nubes a Huawei Cloud vía VPN" }, pain: { en: "Manual VPN configuration is error-prone with many incompatible IKE/IPsec parameters.", es: "La configuración manual de VPN es propensa a errores con muchos parámetros IKE/IPsec incompatibles." } },
      { icon: "Globe", who: { en: "Infrastructure teams establishing hybrid cloud connectivity", es: "Equipos de infraestructura estableciendo conectividad híbrida cloud" }, pain: { en: "Tunnel troubleshooting is difficult — status shows DOWN even when the tunnel is UP.", es: "El troubleshooting de túneles es difícil — el status muestra DOWN incluso cuando el túnel está UP." } },
      { icon: "BookOpen", who: { en: "Organizations migrating workloads that require secure network connectivity first", es: "Organizaciones migrando workloads que requieren conectividad de red segura primero" }, pain: { en: "VPN is a prerequisite for migration but teams lack Huawei Cloud VPN expertise.", es: "VPN es un prerequisito para la migración pero los equipos carecen de expertise en VPN de Huawei Cloud." } },
    ],
    painPoints: [
      { en: "Manual VPN configuration requires matching IKE/IPsec parameters exactly — a single mismatch (e.g. Group14 vs group14) breaks the tunnel.", es: "La configuración manual de VPN requiere parámetros IKE/IPsec exactos — un solo mismatch (ej. Group14 vs group14) rompe el túnel." },
      { en: "Huawei Cloud VPN status shows DOWN even when the tunnel is fully operational — confusing operators.", es: "El status de VPN de Huawei Cloud muestra DOWN incluso cuando el túnel está operativo — confundiendo a los operadores." },
      { en: "Creating a VPN peer (strongSwan) on another cloud requires NAT gateways, DNS fixes, and plugin configuration — many hidden steps.", es: "Crear un peer VPN (strongSwan) en otra nube requiere NAT gateways, fixes de DNS y configuración de plugins — muchos pasos ocultos." },
    ],
    solutionApproach: [
      { en: "AI gathers all VPN parameters interactively — region, VPC, IKE/IPsec policy, peer mode (cloud or on-premises), PSK — never assumes defaults.",
      es: "La IA recopila todos los parámetros de VPN de forma interactiva — región, VPC, política IKE/IPsec, modo del peer (nube u on-premises), PSK — nunca asume defaults.",
      replaces: { en: "AI asks for every parameter instead of guessing — prevents misconfiguration and ensures the tunnel matches on both sides.", es: "La IA pregunta cada parámetro en vez de adivinar — previene misconfiguration y asegura que el túnel coincida en ambos lados." },},
      { en: "AI creates all cloud-side resources: VPC, subnet, security group, NAT gateway, VPN gateway (with active-active HA), customer gateway, and VPN connections.",
      es: "La IA crea todos los recursos del lado de la nube: VPC, subnet, security group, NAT gateway, VPN gateway (con HA active-active), customer gateway y conexiones VPN.",
      referenceLinks: [{ label: "VPN Gateway", url: "https://www.huaweicloud.com/intl/en-us/product/vpn.html" }, { label: "VPC — Virtual Private Cloud", url: "https://www.huaweicloud.com/intl/en-us/product/vpc.html" }],},
      { en: "AI handles peer-side setup: creates an ECS with strongSwan in another Huawei region, or generates a strongSwan config file for on-premises deployment.",
      es: "La IA maneja el setup del lado del peer: crea un ECS con strongSwan en otra región de Huawei, o genera un archivo de config strongSwan para despliegue on-premises.",
      replaces: { en: "AI automates the peer side — either deploying strongSwan on a cloud ECS or generating the config for your on-premises device.", es: "La IA automatiza el lado del peer — ya sea desplegando strongSwan en un ECS de nube o generando la config para su dispositivo on-premises." },
      referenceLinks: [{ label: "ECS — Elastic Cloud Server", url: "https://www.huaweicloud.com/intl/en-us/product/ecs.html" }],},
      { en: "AI validates the tunnel by checking IKE/IPsec SA status and pinging through the tunnel — not relying on the cloud-side status field.",
      es: "La IA valida el túnel verificando el status del SA IKE/IPsec y haciendo ping a través del túnel — sin depender del campo de status del lado de la nube.",
      replaces: { en: "AI validates with SA + ping (the real test) instead of trusting the DOWN status that appears without health-check.", es: "La IA valida con SA + ping (la prueba real) en vez de confiar en el status DOWN que aparece sin health-check." },},
      { en: "AI handles 12 critical gotchas discovered during real testing: lowercase dh_group, mandatory gateway_ip, NAT for ECS, stroke plugin, ha_role rules, and more.",
      es: "La IA maneja 12 gotchas críticos descubiertos durante testing real: dh_group en minúsculas, gateway_ip obligatorio, NAT para ECS, plugin stroke, reglas de ha_role, y más.",
      referenceLinks: [{ label: "VPN Gateway Documentation", url: "https://support.huaweicloud.com/vpn/index.html" }],},
    ],
    recommendedServices: ["VPN", "VPC", "ECS", "EIP", "NAT Gateway", "KPS"],
    demoSkillLinks: [
      link("VPN Connectivity", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/VPN-Connectivity"),
    ],
    migrationMainExample: {
      title: { en: "IPsec Site-to-Cloud VPN Skill", es: "Skill de VPN IPsec Site-to-Cloud" },
      description: { en: "AI-assisted creation of IPsec VPN tunnels to Huawei Cloud. Supports cloud peer (ECS + strongSwan) and on-premises peer (generated config). Handles IKE/IPsec parameters, active-active HA, NAT traversal, and tunnel validation.", es: "Creación asistida por IA de túneles VPN IPsec hacia Huawei Cloud. Soporta peer de nube (ECS + strongSwan) y peer on-premises (config generada). Maneja parámetros IKE/IPsec, HA active-active, NAT traversal y validación de túnel." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/VPN-Connectivity/huaweicloud-vpn-s2c-create",
    },
    migrationRelatedTools: [
      {
        title: { en: "hcloud-cli (KooCLI)", es: "hcloud-cli (KooCLI)" },
        description: { en: "Huawei Cloud CLI for VPN gateway, connection, and customer gateway operations.", es: "CLI de Huawei Cloud para operaciones de VPN gateway, connection y customer gateway." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Automation-and-IaC/hcloud-cli",
      },
      {
        title: { en: "huaweicloud-terraform-planner", es: "huaweicloud-terraform-planner" },
        description: { en: "Plan and write Terraform for Huawei Cloud VPN resources by discovering real values from the live cloud.", es: "Planifique y escriba Terraform para recursos VPN de Huawei Cloud descubriendo valores reales de la nube." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Automation-and-IaC/huaweicloud-terraform-planner",
      },
      {
        title: { en: "Cloud Foundation", es: "Cloud Foundation" },
        description: { en: "Foundational cloud setup: landing zones, IaC, local emulators, DR/backup, and AIOps.", es: "Setup fundamental de cloud: landing zones, IaC, emuladores locales, DR/backup y AIOps." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation",
      },
    ],
    migrationExamples: [
      {
        title: { en: "huaweicloud-vpn-s2c-create", es: "huaweicloud-vpn-s2c-create" },
        description: { en: "AI-assisted IPsec site-to-cloud VPN creation runbook with strongSwan config templates and troubleshooting guide.", es: "Runbook de creación de VPN IPsec site-to-cloud asistido por IA con plantillas de config strongSwan y guía de troubleshooting." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/VPN-Connectivity/huaweicloud-vpn-s2c-create",
      },
    ],
    sourceCloudServices: [
      { cloud: "On-Premises", services: ["IPsec VPN", "strongSwan", "Cisco ISR", "FortiGate"] },
      { cloud: "AWS", services: ["VPN Gateway", "Site-to-Site VPN", "Transit Gateway"] },
      { cloud: "Azure", services: ["VPN Gateway", "ExpressRoute", "Virtual WAN"] },
      { cloud: "GCP", services: ["Cloud VPN", "Cloud Interconnect"] },
    ],
    quickIntegration: {
      prerequisites: [
        { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
        { en: "KooCLI (hcloud) installed and configured with AK/SK.", es: "KooCLI (hcloud) instalado y configurado con AK/SK.", link: { label: "KooCLI Docs", url: "https://support.huaweicloud.com/cli/index.html" } },
        { en: "hcloud MCP server configured (optional, for discovery).", es: "Servidor hcloud MCP configurado (opcional, para descubrimiento)." },
        { en: "VPN skill installed in ~/.opencode/skills/ (or equivalent).", es: "Skill de VPN instalado en ~/.opencode/skills/ (o equivalente).", link: { label: "GitHub Skill", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/VPN-Connectivity/huaweicloud-vpn-s2c-create" } },
      ],
      steps: [
        { en: "Gather parameters with AI: AI asks for region, VPC, IKE/IPsec policy, peer mode (cloud or on-premises), and PSK — never assumes defaults.", es: "Recopilar parámetros con IA: La IA pregunta por región, VPC, política IKE/IPsec, modo del peer (nube u on-premises) y PSK — nunca asume defaults." },
        { en: "Verify resources with AI: AI checks flavor and image availability in the chosen region before creating anything.", es: "Verificar recursos con IA: La IA verifica disponibilidad de flavors e imágenes en la región elegida antes de crear nada." },
        { en: "Create cloud-side resources with AI: AI creates VPC, subnet, security group, NAT gateway, VPN gateway, customer gateway, and VPN connections.", es: "Crear recursos del lado de la nube con IA: La IA crea VPC, subnet, security group, NAT gateway, VPN gateway, customer gateway y conexiones VPN." },
        { en: "Set up peer with AI: AI either deploys strongSwan on a cloud ECS or generates the config file for on-premises deployment.", es: "Configurar peer con IA: La IA despliega strongSwan en un ECS de nube o genera el archivo de config para despliegue on-premises." },
        { en: "Validate tunnel with AI: AI checks IKE/IPsec SA status and pings through the tunnel — the real validation, not the status field.", es: "Validar túnel con IA: La IA verifica el status del SA IKE/IPsec y hace ping a través del túnel — la validación real, no el campo de status." },
      ],
      configuration: [
        { en: "Use lowercase for dh_group and pfs: group14, not Group14 — the API rejects capitalized values", es: "Use minúsculas para dh_group y pfs: group14, no Group14 — la API rechaza valores capitalizados" },
        { en: "Always pass gateway_ip when creating subnets — it is mandatory despite the API help saying optional", es: "Siempre pase gateway_ip al crear subnets — es obligatorio pese a que la ayuda de la API dice opcional" },
        { en: "For active-active HA: use ha_role=master for connection 1, omit ha_role for connection 2 (slave is rejected)", es: "Para HA active-active: use ha_role=master para conexión 1, omita ha_role para conexión 2 (slave es rechazado)" },
        { en: "Create a NAT gateway + SNAT rule before relying on ECS cloud-init (apt-get needs internet)", es: "Cree un NAT gateway + regla SNAT antes de depender de cloud-init del ECS (apt-get necesita internet)" },
        { en: "Use a unique prefix for all resource names to avoid collisions with other projects", es: "Use un prefijo único para todos los nombres de recursos para evitar colisiones con otros proyectos" },
      ],
      apiAccess: [
        { en: "Create VPN gateway: hcloud VPN CreateVgw --vpn_gateway.name=vgw-prod --vpn_gateway.vpc_id=xxx --vpn_gateway.ha_mode=active-active", es: "Crear VPN gateway: hcloud VPN CreateVgw --vpn_gateway.name=vgw-prod --vpn_gateway.vpc_id=xxx --vpn_gateway.ha_mode=active-active" },
        { en: "Create customer gateway: hcloud VPN CreateCgw --customer_gateway.name=cgw-onprem --customer_gateway.id_type=ip --customer_gateway.id_value=203.0.113.5", es: "Crear customer gateway: hcloud VPN CreateCgw --customer_gateway.name=cgw-onprem --customer_gateway.id_type=ip --customer_gateway.id_value=203.0.113.5" },
        { en: "Create VPN connection: hcloud VPN CreateVpnConnection --vpn_connection.name=conn-prod --vpn_connection.vgw_id=xxx --vpn_connection.cgw_id=xxx --vpn_connection.psk=MyPSK", es: "Crear conexión VPN: hcloud VPN CreateVpnConnection --vpn_connection.name=conn-prod --vpn_connection.vgw_id=xxx --vpn_connection.cgw_id=xxx --vpn_connection.psk=MyPSK" },
        { en: "Check connection status: hcloud VPN ShowVpnConnection --vpn_connection_id=xxx", es: "Verificar status de conexión: hcloud VPN ShowVpnConnection --vpn_connection_id=xxx" },
      ],
      startingPrompt: {
        intro: { en: "Example starting prompt for the AI skill:", es: "Ejemplo de prompt inicial para el skill de IA:" },
        code: 'Create an IPsec site-to-cloud VPN in Huawei Cloud using the huaweicloud-vpn-s2c-create skill. Region: la-north-2. VPC: vpc-myvpn, CIDR 192.168.0.0/16. Peer mode: on-prem local, peer IP 203.0.113.5, peer subnet 10.0.0.0/24. PSK: MySecretPSK!',
      },
    },
    salesTalkTrack: [
      { en: "How do I connect my on-premises network to Huawei Cloud securely?", es: "¿Cómo conecto mi red on-premises a Huawei Cloud de forma segura?" },
      { en: "Can AI help configure IPsec VPN tunnels without manual parameter matching?", es: "¿Puede la IA ayudar a configurar túneles VPN IPsec sin matching manual de parámetros?" },
      { en: "My VPN tunnel shows DOWN but traffic passes — how do I validate properly?", es: "Mi túnel VPN muestra DOWN pero el tráfico pasa — ¿cómo valido correctamente?" },
    ],
    expectedOutcomes: [
      { en: "AI creates a fully functional IPsec VPN tunnel between your on-premises or cloud network and Huawei Cloud in minutes, handling all parameter matching, NAT traversal, and HA configuration automatically.", es: "La IA crea un túnel VPN IPsec completamente funcional entre su red on-premises o de nube y Huawei Cloud en minutos, manejando todo el matching de parámetros, NAT traversal y configuración de HA automáticamente." },
      { en: "AI validates the tunnel using IKE/IPsec SA status and ping through the tunnel — the authoritative test — instead of relying on the misleading cloud-side status field.", es: "La IA valida el túnel usando el status del SA IKE/IPsec y ping a través del túnel — la prueba autoritativa — en vez de confiar en el engañoso campo de status del lado de la nube." },
      { en: "AI handles 12 critical gotchas (lowercase dh_group, mandatory gateway_ip, NAT for ECS, stroke plugin, ha_role rules, etc.) that would otherwise cause silent failures or hours of troubleshooting.", es: "La IA maneja 12 gotchas críticos (dh_group en minúsculas, gateway_ip obligatorio, NAT para ECS, plugin stroke, reglas de ha_role, etc.) que de otro modo causarían fallos silenciosos u horas de troubleshooting." },
    ],
    heroImage: "/assets/huawei/migration-scenarios/cloud-foundation.jpg",
  },
  {
    id: "other-scenarios",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Other", es: "Other" },
    title: {
      en: "Other Scenarios",
      es: "Otros Escenarios",
      zh: "其他场景",
    },
      oneLiner: {
      en: "Hybrid, on-premise, and multi-cloud architectures with secure cross-boundary networking.",
      es: "Arquitecturas híbridas, on-premise y multi-nube con redes seguras entre entornos.",
      zh: "面向混合云、本地数据中心和多云架构，构建安全的跨边界网络连接。",
    },
            targetCustomers: [
      { icon: "GitMerge", who: { en: "Teams building hybrid cloud architectures", es: "Equipos que construyen arquitecturas hybrid cloud" }, pain: { en: "On-premises workloads lack managed APIs and cloud-native observability.", es: "Las cargas on-premises carecen de APIs gestionadas y observabilidad cloud-native." } },
      { icon: "Server", who: { en: "Organizations migrating from on-premises datacenters", es: "Organizaciones que migran desde datacenters on-premises" }, pain: { en: "Needing stable, low-latency cross-boundary network links.", es: "Necesitando links de red cross-boundary estables y de baja latencia." } },
      { icon: "Globe", who: { en: "Enterprises operating multi-cloud architectures", es: "Empresas que operan arquitecturas multi-cloud" }, pain: { en: "Facing federation complexity across identity, DNS, and service discovery.", es: "Enfrentando complejidad de federacion across identidad, DNS y service discovery." } },
    ],
    painPoints: [
      { en: "On-premises workloads lack managed APIs, auto-scaling, and cloud-native observability.", es: "Las cargas on-premises carecen de APIs gestionadas, auto-scaling y observabilidad cloud-native." },
      { en: "Hybrid architectures need stable, low-latency cross-boundary network links.", es: "Las arquitecturas híbridas necesitan links de red cross-boundary estables y de baja latencia." },
      { en: "Multi-cloud adds federation complexity — identity, DNS, and service discovery must span clouds.", es: "Multi-cloud añade complejidad de federación — identidad, DNS y service discovery deben span clouds." },
    ],
    solutionApproach: [
      { en: "Hybrid cloud: Use Direct Connect for dedicated, low-latency links between on-premises and Huawei Cloud VPC.", es: "Hybrid cloud: Use Direct Connect para links dedicados y de baja latencia entre on-premises y VPC de Huawei Cloud.",
      replaces: { en: "Equivalent to AWS Direct Connect, Azure ExpressRoute, and GCP Cloud Interconnect — Huawei Direct Connect offers dedicated low-latency links from 1G to 100G.", es: "Equivalente a AWS Direct Connect, Azure ExpressRoute y GCP Cloud Interconnect — Huawei Direct Connect ofrece links dedicados de baja latencia desde 1G hasta 100G." },
      referenceLinks: [{ label: "Direct Connect", url: "https://www.huaweicloud.com/intl/en-us/product/directconnect.html" }],},
      { en: "On-premises-to-cloud: Use SMS for VM migration and Cloud End Site to extend on-premises network into Huawei Cloud.", es: "On-premises-to-cloud: Use SMS para migración de VM y Cloud End Site para extender red on-premises hacia Huawei Cloud.",
      replaces: { en: "Equivalent to AWS MGN and Azure Migrate — SMS Agent handles all sources with Cloud End Site for network extension.", es: "Equivalente a AWS MGN y Azure Migrate — SMS Agent maneja todos los orígenes con Cloud End Site para extensión de red." },
      referenceLinks: [{ label: "SMS — Server Migration Service", url: "https://www.huaweicloud.com/intl/en-us/product/sms.html" }, { label: "Cloud End Site", url: "https://www.huaweicloud.com/intl/en-us/product/cloudendsite.html" }],},
      { en: "Multi-cloud: Use VPN for encrypted cross-cloud connectivity and VPC peering within Huawei Cloud regions.", es: "Multi-cloud: Use VPN para conectividad cross-cloud encriptada y VPC peering dentro de regiones de Huawei Cloud.",
      replaces: { en: "Equivalent to AWS VPN, Azure VPN Gateway, and GCP Cloud VPN — IKEv2/IPsec with multiple tunnels and VPC routing integration.", es: "Equivalente a AWS VPN, Azure VPN Gateway y GCP Cloud VPN — IKEv2/IPsec con múltiples túneles e integración con routing VPC." },
      referenceLinks: [{ label: "VPN", url: "https://www.huaweicloud.com/intl/en-us/product/vpn.html" }],},
      { en: "Compositional approach: combine patterns from other migration categories with cross-boundary networking.", es: "Enfoque composicional: combine patrones de otras categorías de migración con networking cross-boundary." },
    ],
    recommendedServices: ["Direct Connect", "VPN", "Cloud End Site", "SMS", "VPC", "EIP"],
    demoSkillLinks: [
      link("Other Scenarios Examples", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Other-Scenarios-Examples"),
    ],
            quickIntegration: {
    prerequisites: [
      { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
      { en: "Recommended skills installed in ~/.opencode/skills/ (or equivalent).", es: "Skills recomendados instalados en ~/.opencode/skills/ (o equivalente).", link: { label: "GitHub Skills", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration" } },
      { en: "A defined migration scenario.", es: "Un escenario de migración definido." },
    ],
    steps: [
      { en: "Discover with AI: AI scans your source environment and identifies the closest standard migration pattern. Verify the results against your actual environment.", es: "Descubrir con IA: La IA escanea su entorno origen e identifica el patrón de migración estándar más cercano. Verifique los resultados contra su entorno actual." },
      { en: "Plan with AI: AI generates a migration plan adapted to your specific requirements — hybrid, multi-cloud, or non-standard. Review the plan before proceeding.", es: "Planificar con IA: La IA genera un plan de migración adaptado a sus requisitos específicos — híbrido, multi-nube o no estándar. Revise el plan antes de continuar." },
      { en: "Connect with AI: Provision cross-boundary networking first — VPN, Direct Connect, or ExpressRoute as needed.", es: "Conectar con IA: Provisione networking cross-boundary primero — VPN, Direct Connect o ExpressRoute según sea necesario." },
      { en: "Migrate with AI: Combine relevant patterns (VM, database, container, storage) as needed for your scenario.", es: "Migrar con IA: Combine patrones relevantes (VM, base de datos, contenedor, storage) según sea necesario para su escenario." },
      { en: "Validate with AI: AI tests failover, latency, and application behavior across environments.", es: "Validar con IA: La IA prueba failover, latencia y comportamiento de aplicación entre entornos." },
      { en: "Document with AI: AI generates a migration runbook and verification checklist. Require specific evidence before signing off.", es: "Documentar con IA: La IA genera un runbook de migración y checklist de verificación. Exija evidencia específica antes de firmar." },
    ],
      configuration: [
        { en: "Assessment first: evaluate source environment before choosing a migration approach", es: "Assessment primero: evalúe el entorno origen antes de elegir un enfoque de migración" },
        { en: "Network connectivity: ensure stable network path between source and target", es: "Conectividad de red: asegure un path de red estable entre origen y destino" },
        { en: "Data consistency: plan for incremental sync or downtime window for final cutover", es: "Consistencia de datos: planee sync incremental o ventana de downtime para cutover final" },
        { en: "Rollback plan: always prepare a rollback strategy before executing migration", es: "Plan de rollback: siempre prepare una estrategia de rollback antes de ejecutar la migración" },
      ],
      apiAccess: [
        { en: "List ECS servers: hcloud ECS ListServersDetails", es: "Listar servidores ECS: hcloud ECS ListServersDetails" },
        { en: "List CCE clusters: hcloud CCE ListClusters", es: "Listar clusters CCE: hcloud CCE ListClusters" },
        { en: "List VPCs: hcloud VPC ListVpcs/v3", es: "Listar VPCs: hcloud VPC ListVpcs/v3" },
        { en: "List security groups: hcloud VPC ListSecurityGroups/v3", es: "Listar security groups: hcloud VPC ListSecurityGroups/v3" },
      ],
    },
      salesTalkTrack: [
      { en: "What if my migration scenario doesn't fit standard categories?", es: "¿Qué pasa si mi escenario de migración no encaja en categorías estándar?" },
      { en: "Can AI handle hybrid or multi-cloud migration requirements?", es: "¿Puede la IA manejar requisitos de migración híbrida o multi-nube?" },
      { en: "How do I get started with a non-standard migration?", es: "¿Cómo empiezo con una migración no estándar?" },
    ],
    expectedOutcomes: [
      { en: "AI analyzes your infrastructure and identifies the closest standard scenario, then adapts the migration plan for your specific requirements. It handles hybrid setups (on-prem + cloud), multi-cloud sources (AWS + Azure simultaneously), and special constraints like network latency or compliance.", es: "La IA analiza su infraestructura e identifica el escenario estándar más cercano, luego adapta el plan de migración para sus requisitos específicos. Maneja setups híbridos (on-prem + nube), orígenes multi-nube (AWS + Azure simultáneamente) y restricciones especiales como latencia de red o compliance." },
      { en: "Yes. AI maps dependencies across environments and generates a migration plan that respects cross-boundary constraints. It handles network connectivity (VPN, Direct Connect, ExpressRoute), data residency, and encryption requirements between environments.", es: "Sí. La IA mapea dependencias entre entornos y genera un plan de migración que respeta las restricciones entre límites. Maneja conectividad de red (VPN, Direct Connect, ExpressRoute), residencia de datos y requisitos de encriptación entre entornos." },
      { en: "Describe your scenario to the AI tool in plain language. AI asks clarifying questions about your source, target, constraints, and timeline. It then produces a migration plan with phases, risks, and verification checkpoints. Your team reviews and adjusts before execution.", es: "Describa su escenario a la herramienta de IA en lenguaje natural. La IA hace preguntas aclaratorias sobre su origen, destino, restricciones y timeline. Luego produce un plan de migración con fases, riesgos y puntos de verificación. Su equipo revisa y ajusta antes de la ejecución." },
    ],
    heroImage: "/assets/huawei/official-cache/nn8-e43be77fbfb95910.jpg",
  },
  {
    id: "object-migration",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Object Storage", es: "Object Storage" },
    title: {
      en: "Object Migration",
      es: "Migración de Objetos",
      zh: "对象存储迁移",
    },
      oneLiner: {
      en: "Migrate object storage data to Huawei Cloud OBS at any scale with verified integrity and continuous sync.",
      es: "Migre datos de object storage a Huawei Cloud OBS a cualquier escala con integridad verificada y sincronización continua.",
      zh: "将任意规模的对象存储数据迁移到华为云 OBS，支持完整性校验和持续同步。",
    },
            targetCustomers: [
      { icon: "HardDrive", who: { en: "Organizations with large object storage estates", es: "Organizaciones con grandes estates de object storage" }, pain: { en: "Migration is slow, bandwidth-intensive, and hard to verify at scale.", es: "La migracion es lenta, consume ancho de banda y es dificil de verificar a escala." } },
      { icon: "Database", who: { en: "Teams moving data lakes to OBS", es: "Equipos que mueven data lakes a OBS" }, pain: { en: "Data consistency challenges with different checksum algorithms across clouds.", es: "Desafios de consistencia con diferentes algoritmos de checksum entre nubes." } },
      { icon: "RefreshCw", who: { en: "Enterprises needing continuous sync during migration", es: "Empresas que necesitan sync continuo durante la migracion" }, pain: { en: "Per-cloud credential quirks (Azure, AWS, GCP).", es: "Quirks de credenciales por nube (Azure, AWS, GCP)." } },
    ],
    painPoints: [
      { en: "Object storage migration is slow, bandwidth-intensive, and hard to verify at scale.", es: "La migración de object storage es lenta, consume ancho de banda y es difícil de verificar a escala." },
      { en: "Data consistency and verification across clouds is challenging — different checksum algorithms and metadata handling.", es: "La consistencia y verificación de datos entre nubes es un desafío — diferentes algoritmos de checksum y manejo de metadata." },
      { en: "Per-cloud credential quirks: Azure needs account name + key, AWS needs AK/SK + region, GCP needs SA key + project ID.", es: "Quirks de credenciales por nube: Azure necesita account name + key, AWS necesita AK/SK + región, GCP necesita SA key + project ID." },
    ],
    solutionApproach: [
      { en: "Phase 1 — Discover: Inventory source buckets/containers and estimate total data volume and object count.", es: "Fase 1 — Descubrir: Inventario de buckets/contenedores origen y estimación de volumen total y conteo de objetos." },
      { en: "Phase 2 — Prepare: Create target OBS buckets with matching storage tiers (Standard, Infrequent Access, Archive).", es: "Fase 2 — Preparar: Cree buckets OBS destino con tiers de almacenamiento matching (Standard, Infrequent Access, Archive).",
      replaces: { en: "Equivalent to AWS S3, Azure Blob Storage, and GCP Cloud Storage as target — OBS offers multi-tier storage with automatic lifecycle rules.", es: "Equivalente a AWS S3, Azure Blob Storage y GCP Cloud Storage como destino — OBS ofrece storage multi-tier con lifecycle rules automáticas." },
      referenceLinks: [{ label: "OBS — Object Storage Service", url: "https://www.huaweicloud.com/intl/en-us/product/obs.html" }],},
      { en: "Phase 3 — Terraform: Define OMS migration tasks — choose from 3 types: one-time migration, continuous sync, or batch task group.", es: "Fase 3 — Terraform: Defina tasks de migración OMS — elija entre 3 tipos: one-time, sync continuo o batch task group.",
      replaces: { en: "Equivalent to AWS DataSync and GCP Storage Transfer Service — OMS supports 11+ source clouds with 3 task types (one-time, continuous sync, batch).", es: "Equivalente a AWS DataSync y GCP Storage Transfer Service — OMS soporta 11+ nubes origen con 3 tipos de task (one-time, sync continuo, batch)." },
      referenceLinks: [{ label: "OMS — Object Migration Service", url: "https://www.huaweicloud.com/intl/en-us/product/oms.html" }],},
      { en: "Phase 4 — Apply: Run migration tasks with consistency_check (size_last_modified, crc64, or no_check) and ETag verification.", es: "Fase 4 — Apply: Ejecute tasks de migración con consistency_check (size_last_modified, crc64 o no_check) y verificación ETag.",
      referenceLinks: [{ label: "SMN — Simple Message Notification", url: "https://www.huaweicloud.com/intl/en-us/product/smn.html" }],},
      { en: "Phase 5 — Verify: Compare object counts, total sizes, and sample checksums between source and target.", es: "Fase 5 — Verificar: Compare conteos de objetos, tamaños totales y checksums de muestra entre origen y destino." },
      { en: "Phase 6 — Clean up: Remove temporary OMS tasks and update application references to new OBS endpoints.", es: "Fase 6 — Cleanup: Elimine tasks OMS temporales y actualice referencias de aplicación a nuevos endpoints OBS." },
    ],
    recommendedServices: ["OBS", "OMS", "SMN", "VPC"],
    demoSkillLinks: [
      link("Object Migration", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Object-Migration"),
    ],
    migrationMainExample: {
      title: { en: "AI-Assisted Object Storage Migration Tool", es: "Herramienta de migración de object storage asistida con IA" },
      description: { en: "Skills and tools for migrating object storage data to Huawei Cloud OBS using the Object Storage Migration Service (OMS).", es: "Skills y herramientas para migrar datos de object storage a Huawei Cloud OBS usando el Object Storage Migration Service (OMS)." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Object-Migration",
    },
    migrationRelatedTools: [
      {
        title: { en: "Huawei Cloud OMS Migration", es: "Migración OMS de Huawei Cloud" },
        description: { en: "Object Storage Migration Service (OMS) for migrating data from source clouds or on-premises to Huawei Cloud OBS. Supports 11+ source clouds with 3 task types.", es: "Object Storage Migration Service (OMS) para migrar datos desde nubes origen o on-premises a Huawei Cloud OBS. Soporta 11+ nubes origen con 3 tipos de task." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Object-Migration/huaweicloud-oms-migration",
      },
      {
        title: { en: "AWS S3 to Huawei OBS", es: "AWS S3 a Huawei OBS" },
        description: { en: "Migrate Amazon S3 buckets and objects to Huawei Cloud OBS. Includes bucket policy translation, lifecycle rule mapping, and batch transfer via OMS or obsutil.", es: "Migre buckets y objetos de Amazon S3 a Huawei Cloud OBS. Incluye traducción de bucket policies, mapeo de lifecycle rules y transfer batch vía OMS u obsutil." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Object-Migration/AWS-S3-to-Huawei-OBS",
        beta: true,
      },
      {
        title: { en: "Azure Blob to Huawei OBS", es: "Azure Blob a Huawei OBS" },
        description: { en: "Migrate Azure Blob Storage containers to Huawei Cloud OBS. Covers SAS token mapping, tier translation (Hot/Cool/Archive), and bulk data sync.", es: "Migre contenedores de Azure Blob Storage a Huawei Cloud OBS. Cubre mapeo de SAS tokens, traducción de tiers (Hot/Cool/Archive) y sync bulk de datos." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Object-Migration/Azure-Blob-to-Huawei-OBS",
        beta: true,
      },
      {
        title: { en: "GCP GCS to Huawei OBS", es: "GCP GCS a Huawei OBS" },
        description: { en: "Migrate Google Cloud Storage buckets to Huawei Cloud OBS. Includes IAM policy translation, storage class mapping, and gsutil/obsutil data transfer.", es: "Migre buckets de Google Cloud Storage a Huawei Cloud OBS. Incluye traducción de IAM policies, mapeo de storage classes y transfer de datos gsutil/obsutil." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Object-Migration/GCP-GCS-to-Huawei-OBS",
        beta: true,
      },
    ],
    presentationUrl: "/presentations/object-migration.pdf",
            quickIntegration: {
    prerequisites: [
      { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
      { en: "Recommended skills installed in ~/.opencode/skills/ (or equivalent).", es: "Skills recomendados instalados en ~/.opencode/skills/ (o equivalente).", link: { label: "GitHub Skills", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Object-Migration" } },
      { en: "Source cloud credentials.", es: "Credenciales de nube origen." },
    ],
    steps: [
      { en: "Discover with AI: Scan your source object storage — buckets, objects, sizes, and storage classes. Verify the results against your actual cloud.", es: "Descubrir con IA: Escanee su object storage origen — buckets, objetos, tamaños y clases de almacenamiento. Verifique los resultados contra su nube actual." },
      { en: "Plan with AI: AI maps each source bucket to a Huawei Cloud OBS bucket and generates a migration plan with cost estimates. Review the plan before proceeding.", es: "Planificar con IA: La IA mapea cada bucket origen a un bucket de Huawei Cloud OBS y genera un plan de migración con estimaciones de costo. Revise el plan antes de continuar." },
      { en: "Configure with AI: OMS connects source and target. AI guides credential setup and recommends optimal parallelism settings.", es: "Configurar con IA: OMS conecta origen y destino. La IA guía el setup de credenciales y recomienda ajustes de paralelismo óptimos." },
      { en: "Migrate with AI: OMS transfers objects with ETag verification. AI tracks progress and handles retries automatically.", es: "Migrar con IA: OMS transfiere objetos con verificación ETag. La IA rastrea el progreso y maneja reintentos automáticamente." },
      { en: "Validate with AI: AI compares object counts, sizes, and checksums between source and target. Any mismatches are flagged for review.", es: "Validar con IA: La IA compara conteos de objetos, tamaños y checksums entre origen y destino. Cualquier discrepancia se marca para revisión." },
      { en: "Sync with AI: For ongoing replication, AI sets up continuous sync and monitors for new objects. Require specific evidence that all data is verified before cutover.", es: "Sincronizar con IA: Para replicación ongoing, la IA configura sync continuo y monitorea nuevos objetos. Exija evidencia específica de que todos los datos están verificados antes del cutover." },
    ],
      configuration: [
        { en: "No private line support: OMS uses Internet or intranet only, not dedicated connections", es: "Sin líneas privadas: OMS usa únicamente Internet o intranet, no conexiones dedicadas" },
        { en: "Symbolic links fail: symlinks are recorded as failed and must be handled manually", es: "Symlinks fallan: los symlinks se registran como fallidos y deben manejarse manualmente" },
        { en: "Object ACLs not migrated: bucket-level ACLs must be reconfigured on destination", es: "ACLs no migrados: los ACLs de bucket deben reconfigurarse en el destino" },
        { en: "Metadata limits: Chinese punctuation marks in metadata cause migration failures", es: "Límites de metadata: puntuación china en metadata causa fallos de migración" },
        { en: "Archived data needs restore: restore archived objects first and set a validity period", es: "Datos archivados necesitan restore: restaure objetos archivados primero y defina período de validez" },
        { en: "5 concurrent tasks per region: max 5 migration tasks run simultaneously", es: "5 tareas concurrentes por región: máx 5 tareas de migración simultáneas" },
        { en: "10–20 TB per day: typical throughput; use MgC for up to 20 Gbit/s bandwidth", es: "10–20 TB por día: throughput típico; use MgC para hasta 20 Gbit/s de ancho de banda" },
        { en: "One bucket per task: multiple source buckets require multiple migration tasks", es: "Un bucket por tarea: múltiples buckets origen requieren múltiples tareas" },
      ],
      apiAccess: [
        { en: "List migration tasks: hcloud OMS ListTasks", es: "Listar tareas de migración: hcloud OMS ListTasks" },
        { en: "Check task details: hcloud OMS ShowTask --task_id=xxx", es: "Ver detalles de tarea: hcloud OMS ShowTask --task_id=xxx" },
        { en: "Start a paused task: hcloud OMS StartTask --task_id=xxx", es: "Iniciar tarea pausada: hcloud OMS StartTask --task_id=xxx" },
        { en: "List source bucket objects: hcloud OMS ShowBucketObjects --bucket=xxx", es: "Listar objetos del bucket origen: hcloud OMS ShowBucketObjects --bucket=xxx" },
      ],
    },
      salesTalkTrack: [
      { en: "How does AI ensure my data is not corrupted during migration?", es: "¿Cómo asegura la IA que mis datos no se corrompan durante la migración?" },
      { en: "Can I keep syncing data after the initial migration?", es: "¿Puedo seguir sincronizando datos después de la migración inicial?" },
      { en: "How long does it take to migrate petabytes of object storage?", es: "¿Cuánto tiempo toma migrar petabytes de object storage?" },
    ],
    expectedOutcomes: [
      { en: "AI uses Huawei Cloud OMS (Object Migration Service) which verifies every transferred object with ETag checksum comparison. If any object fails verification, it is automatically re-transferred. Your team gets a report showing total objects, verified, and any exceptions before cutover.", es: "La IA usa OMS de Huawei Cloud que verifica cada objeto transferido con comparación de checksum ETag. Si algún objeto falla la verificación, se re-transfiere automáticamente. Su equipo obtiene un reporte con el total de objetos, verificados y cualquier excepción antes del cutover." },
      { en: "Yes. OMS supports continuous sync mode where new and modified objects are replicated to Huawei Cloud OBS while the source stays active. This lets you migrate gradually and switch over when ready, with no data gap between source and target.", es: "Sí. OMS soporta modo de sincronización continua donde los objetos nuevos y modificados se replican a Huawei Cloud OBS mientras el origen se mantiene activo. Esto permite migrar gradualmente y switchar cuando esté listo, sin brecha de datos entre origen y destino." },
      { en: "OMS is designed for large-scale migration. It uses parallel transfers and bandwidth optimization to move data efficiently. Real-world cases like Meitu have migrated petabytes in under a week. AI estimates the transfer time based on your data volume and available bandwidth, and recommends the optimal parallelism settings.", es: "OMS está diseñado para migración a gran escala. Usa transferencias paralelas y optimización de ancho de banda para mover datos eficientemente. Casos reales como Meitu han migrado petabytes en menos de una semana. La IA estima el tiempo de transferencia basado en su volumen de datos y ancho de banda disponible, y recomienda los ajustes de paralelismo óptimos." },
    ],
    heroImage: "/assets/huawei/cloud-dc.png",
  },
  {
    id: "landing-zone",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Cloud Foundation", es: "Cloud Foundation" },
    title: {
      en: "Multi-Account Landing Zone",
      es: "Landing Zone Multi-Cuenta",
      zh: "多账号着陆区",
    },
    oneLiner: {
      en: "Design and deploy a multi-account landing zone with organizational governance, OUs, SCPs, IAM agencies, and per-account infrastructure using Terraform.",
      es: "Diseñe y despliegue un landing zone multi-cuenta con gobernanza organizacional, OUs, SCPs, agencias IAM e infraestructura por cuenta usando Terraform.",
      zh: "使用Terraform设计并部署多账号着陆区，包含组织治理、OU、SCP、IAM代理和每账号基础设施。",
    },
    targetCustomers: [
      { icon: "Building2", who: { en: "Enterprise architects establishing cloud governance", es: "Arquitectos enterprise estableciendo gobernanza cloud" }, pain: { en: "No multi-account structure or governance framework.", es: "Sin estructura multi-cuenta ni framework de gobernanza." } },
      { icon: "ShieldCheck", who: { en: "Security teams needing centralized policy control", es: "Equipos de seguridad necesitando control centralizado de políticas" }, pain: { en: "Inconsistent IAM and SCP enforcement across accounts.", es: "Aplicación inconsistente de IAM y SCP entre cuentas." } },
      { icon: "Network", who: { en: "Platform teams building landing zone blueprints", es: "Equipos de plataforma construyendo blueprints de landing zone" }, pain: { en: "Manual account setup is slow and error-prone.", es: "Setup manual de cuentas es lento y propenso a errores." } },
    ],
    painPoints: [
      { en: "No multi-account organizational structure or governance framework exists.", es: "No existe estructura organizacional multi-cuenta ni framework de gobernanza." },
      { en: "IAM and Service Control Policies are inconsistent across accounts.", es: "IAM y Service Control Policies son inconsistentes entre cuentas." },
      { en: "Manual account setup is slow, error-prone, and not repeatable.", es: "Setup manual de cuentas es lento, propenso a errores y no repetible." },
    ],
    solutionApproach: [
      { en: "Design the organizational structure: OUs hierarchy (max 2 levels), account placement, and governance model.", es: "Diseñe la estructura organizacional: jerarquía de OUs (máx 2 niveles), ubicación de cuentas y modelo de gobernanza." },
      { en: "Define Service Control Policies (SCPs) baseline: IAM guard policies, tag governance, and security baselines.", es: "Defina baseline de Service Control Policies (SCPs): políticas de guardia IAM, gobernanza de tags y baselines de seguridad." },
      { en: "Set up Identity Center with permission sets and group assignments for cross-account access.", es: "Configure Identity Center con permission sets y asignaciones de grupos para acceso cross-account." },
      { en: "Deploy per-account infrastructure: VPC, subnets, security groups, compute, and tagging using modular Terraform.", es: "Despliegue infraestructura por cuenta: VPC, subnets, security groups, compute y tagging usando Terraform modular." },
    ],
    recommendedServices: ["Organizations", "IAM", "Identity Center", "VPC", "ECS", "RGC", "TMS"],
    demoSkillLinks: [
      link("Landing Zone and Organization Management", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Landing-Zone-and-Organization-Management"),
    ],
    migrationMainExample: {
      title: { en: "Multi-Account Landing Zone", es: "Landing Zone Multi-Cuenta" },
      description: { en: "Multi-account landing zone design with OUs, accounts, SCPs, IAM agencies, Identity Center, and per-account infrastructure.", es: "Diseño de landing zone multi-cuenta con OUs, cuentas, SCPs, agencias IAM, Identity Center e infraestructura por cuenta." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Landing-Zone-and-Organization-Management",
    },
    migrationRelatedTools: [
      {
        title: { en: "multi-account-landing-zone", es: "multi-account-landing-zone" },
        description: { en: "Build modular HuaweiCloud multi-account landing zone Terraform code with governance and per-account infrastructure.", es: "Construya código Terraform modular para landing zone multi-cuenta en HuaweiCloud con gobernanza e infraestructura por cuenta." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Landing-Zone-and-Organization-Management/multi-account-landing-zone",
      },
      {
        title: { en: "Landing-Zone-Demo", es: "Landing-Zone-Demo" },
        description: { en: "End-to-end demonstration of multi-account landing zone setup on Huawei Cloud.", es: "Demostración end-to-end de setup de landing zone multi-cuenta en Huawei Cloud." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Landing-Zone-and-Organization-Management/Landing-Zone-Demo",
      },
    ],
    migrationExamples: [
      {
        title: { en: "multi-account-landing-zone", es: "multi-account-landing-zone" },
        description: { en: "Build modular HuaweiCloud multi-account landing zone Terraform code.", es: "Construya código Terraform modular para landing zone multi-cuenta en HuaweiCloud." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Landing-Zone-and-Organization-Management/multi-account-landing-zone",
      },
    ],
    quickIntegration: {
      prerequisites: [
        { en: "Huawei Cloud account with Organizations enabled.", es: "Cuenta de Huawei Cloud con Organizations habilitado." },
        { en: "AI coding tool installed.", es: "Herramienta de coding con IA instalada.", linkParts: [
          { label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" },
          { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" },
          { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" },
          
        ] },
      ],
      steps: [
        { en: "Install the multi-account-landing-zone skill in your AI coding tool.", es: "Instale el skill multi-account-landing-zone en su herramienta de coding con IA." },
        { en: "Ask the AI to design your organizational structure: OUs, accounts, and governance model.", es: "Pida a la IA diseñar su estructura organizacional: OUs, cuentas y modelo de gobernanza." },
        { en: "Generate and validate Terraform code with terraform init and terraform validate.", es: "Genere y valide código Terraform con terraform init y terraform validate." },
      ],
      configuration: [
        { en: "Define OU hierarchy (max 2 levels), account placement, and SCP baseline.", es: "Defina jerarquía de OU (máx 2 niveles), ubicación de cuentas y baseline de SCP." },
      ],
    },
    salesTalkTrack: [
      { en: "How does the landing zone enforce security across all accounts?", es: "¿Cómo enforce el landing zone la seguridad en todas las cuentas?" },
      { en: "Can I customize the SCP baseline for my organization?", es: "¿Puedo customizar el baseline de SCP para mi organización?" },
      { en: "How long does it take to set up a multi-account structure?", es: "¿Cuánto tiempo toma setup una estructura multi-cuenta?" },
    ],
    expectedOutcomes: [
      { en: "The landing zone uses Service Control Policies (SCPs) with IAM guard policies applied at the organization level. Every account inherits the baseline, ensuring consistent security enforcement. The AI generates SCPs with policy_attach statements so they are always effective.", es: "El landing zone usa Service Control Policies (SCPs) con políticas de guardia IAM aplicadas a nivel de organización. Cada cuenta hereda el baseline, asegurando enforcement consistente de seguridad. La IA genera SCPs con policy_attach para que siempre sean efectivas." },
      { en: "Yes. The skill supports custom SCP definitions. You provide your policy requirements and the AI generates the corresponding Terraform modules with proper policy_attach statements.", es: "Sí. El skill soporta definiciones custom de SCP. Usted provee sus requisitos de políticas y la IA genera los módulos Terraform correspondientes con policy_attach apropiados." },
      { en: "With the AI-assisted workflow, a complete multi-account structure with OUs, accounts, SCPs, IAM agencies, and Identity Center can be designed and deployed in under an hour. The AI generates all Terraform code, validates it, and provides a deployment plan.", es: "Con el workflow asistido por IA, una estructura multi-cuenta completa con OUs, cuentas, SCPs, agencias IAM e Identity Center puede diseñarse y desplegarse en menos de una hora. La IA genera todo el código Terraform, lo valida y provee un plan de despliegue." },
    ],
    heroImage: "/assets/huawei/cloud-dc.png",
  },
  {
    id: "image-discovery",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Cloud Foundation", es: "Cloud Foundation" },
    title: {
      en: "AI-Assisted Image Discovery",
      es: "Descubrimiento de Imágenes con IA",
      zh: "AI辅助镜像发现",
    },
    oneLiner: {
      en: "Use AI to discover available OS images on Huawei Cloud and generate correct Terraform code for ECS deployment through natural conversation.",
      es: "Use IA para descubrir imágenes de SO disponibles en Huawei Cloud y generar código Terraform correcto para despliegue de ECS mediante conversación natural.",
      zh: "使用AI通过自然对话发现华为云上可用的OS镜像，并生成正确的Terraform代码用于ECS部署。",
    },
    targetCustomers: [
      { icon: "Server", who: { en: "Developers deploying ECS instances", es: "Desarrolladores desplegando instancias ECS" }, pain: { en: "Don't know which image IDs or flavors to use.", es: "No saben qué image IDs o flavors usar." } },
      { icon: "Wrench", who: { en: "Platform engineers writing Terraform", es: "Ingenieros de plataforma escribiendo Terraform" }, pain: { en: "Manual image lookup is tedious and error-prone.", es: "Búsqueda manual de imágenes es tediosa y propensa a errores." } },
      { icon: "BookOpen", who: { en: "Teams learning Huawei Cloud APIs", es: "Equipos aprendiendo APIs de Huawei Cloud" }, pain: { en: "Image IDs change across regions and accounts.", es: "Image IDs cambian entre regiones y cuentas." } },
    ],
    painPoints: [
      { en: "Developers don't know which OS image IDs or flavors are available in their region.", es: "Los desarrolladores no saben qué image IDs o flavors están disponibles en su región." },
      { en: "Manual image lookup via console or CLI is tedious and error-prone.", es: "Búsqueda manual de imágenes vía consola o CLI es tediosa y propensa a errores." },
      { en: "Hardcoded image IDs break when deploying to different regions or accounts.", es: "Image IDs hardcodeados se rompen al desplegar en diferentes regiones o cuentas." },
    ],
    solutionApproach: [
      { en: "AI gets the ECS schema from Terraform MCP to understand required parameters: image_id, flavor_id, availability_zone, network.uuid.", es: "La IA obtiene el schema de ECS desde Terraform MCP para entender los parámetros requeridos: image_id, flavor_id, availability_zone, network.uuid." },
      { en: "AI discovers available images via HCloud MCP: hcloud_list_images(imagetype='gold', os_type='Linux') returns real image IDs.", es: "La IA descubre imágenes disponibles vía HCloud MCP: hcloud_list_images(imagetype='gold', os_type='Linux') retorna image IDs reales." },
      { en: "AI asks the user which OS image to use, then writes Terraform with the correct image_id verified against the live cloud.", es: "La IA pregunta al usuario qué imagen de SO usar, luego escribe Terraform con el image_id correcto verificado contra la nube real." },
      { en: "AI validates the generated code with terraform init and terraform validate before deployment.", es: "La IA valida el código generado con terraform init y terraform validate antes del despliegue." },
    ],
    recommendedServices: ["ECS", "IMS", "VPC", "Terraform", "HCloud CLI"],
    demoSkillLinks: [
      link("Image Import Demo", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/Image-Import-Demo"),
    ],
    migrationMainExample: {
      title: { en: "AI-Assisted Image Discovery", es: "Descubrimiento de Imágenes con IA" },
      description: { en: "Discover available OS images on Huawei Cloud and generate correct Terraform code for ECS deployment using AI.", es: "Descubra imágenes de SO disponibles en Huawei Cloud y genere código Terraform correcto para despliegue de ECS usando IA." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/Image-Import-Demo",
    },
    migrationRelatedTools: [
      {
        title: { en: "huaweicloud-terraform-planner", es: "huaweicloud-terraform-planner" },
        description: { en: "Plan and write Terraform for Huawei Cloud by discovering real values from the live cloud.", es: "Planifique y escriba Terraform para Huawei Cloud descubriendo valores reales de la nube." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Automation-and-IaC/huaweicloud-terraform-planner",
      },
    ],
    migrationExamples: [
      {
        title: { en: "Image-Import-Demo", es: "Image-Import-Demo" },
        description: { en: "AI-assisted workflow: discover OS images and generate Terraform for ECS deployment.", es: "Workflow asistido por IA: descubrir imágenes de SO y generar Terraform para despliegue de ECS." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/Image-Import-Demo",
      },
    ],
    quickIntegration: {
      prerequisites: [
        { en: "Huawei Cloud account with ECS and IMS access.", es: "Cuenta de Huawei Cloud con acceso a ECS e IMS." },
        { en: "AI coding tool installed.", es: "Herramienta de coding con IA instalada.", linkParts: [
          { label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" },
          { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" },
          { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" },
        ] },
        { en: "huaweicloud-terraform-planner skill installed in ~/.opencode/skills/ (or equivalent).", es: "Skill huaweicloud-terraform-planner instalado en ~/.opencode/skills/ (o equivalente).", link: { label: "GitHub Skill", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/Image-Import-Demo/skills/huaweicloud-terraform-planner" } },
      ],
      steps: [
        { en: "Install the huaweicloud-terraform-planner skill in your AI coding tool (~/.opencode/skills/ or equivalent).", es: "Instale el skill huaweicloud-terraform-planner en su herramienta de coding con IA (~/.opencode/skills/ o equivalente)." },
        { en: "Start a conversation: \"Deploy a web server to my existing VPC in la-north-2\" — the AI parses your intent and identifies gaps (image, flavor, AZ, subnet).", es: "Inicie una conversación: \"Deploy a web server to my existing VPC in la-north-2\" — la IA analiza su intención e identifica los gaps (imagen, flavor, AZ, subnet)." },
        { en: "AI discovers OS images via HCloud MCP (hcloud_list_images) and asks you to choose, recommending the latest LTS.", es: "La IA descubre imágenes de SO vía HCloud MCP (hcloud_list_images) y le pide elegir, recomendando el último LTS." },
        { en: "AI discovers flavors, AZs, VPCs, and subnets in parallel, then writes Terraform with data blocks — no hardcoded IDs.", es: "La IA descubre flavors, AZs, VPCs y subnets en paralelo, luego escribe Terraform con data blocks — sin IDs hardcodeados." },
        { en: "Review the generated code and deploy with terraform init && terraform apply.", es: "Revise el código generado y despliegue con terraform init && terraform apply." },
      ],
      configuration: [
        { en: "Specify region, VPC, and desired OS for image discovery.", es: "Especifique región, VPC y SO deseado para descubrimiento de imágenes." },
      ],
    },
    salesTalkTrack: [
      { en: "How does the AI know which images are available in my region?", es: "¿Cómo sabe la IA qué imágenes están disponibles en mi región?" },
      { en: "Can I use this for flavors and availability zones too?", es: "¿Puedo usar esto para flavors y availability zones también?" },
      { en: "What happens if an image ID changes after deployment?", es: "¿Qué pasa si un image ID cambia después del despliegue?" },
    ],
    expectedOutcomes: [
      { en: "The AI calls HCloud MCP to list real images available in your account and region. It calls hcloud_list_images with your credentials, so it always returns current, valid image IDs — never hardcoded or guessed values.", es: "La IA llama a HCloud MCP para listar imágenes reales disponibles en su cuenta y región. Llama a hcloud_list_images con sus credenciales, por lo que siempre retorna image IDs actuales y válidos — nunca valores hardcodeados o adivinados." },
      { en: "Yes. The same workflow works for flavors (hcloud_list_flavors), availability zones (hcloud_list_availability_zones), and volume types (hcloud_list_volume_types). The AI discovers all required parameters from the live cloud.", es: "Sí. El mismo workflow funciona para flavors (hcloud_list_flavors), availability zones (hcloud_list_availability_zones) y volume types (hcloud_list_volume_types). La IA descubre todos los parámetros requeridos de la nube real." },
      { en: "The generated Terraform uses the image_id that was valid at generation time. If images change, you simply ask the AI to rediscover and update the code. The AI handles the lookup, validation, and code update automatically.", es: "El Terraform generado usa el image_id que era válido al momento de generación. Si las imágenes cambian, simplemente pida a la IA redescubrir y actualizar el código. La IA maneja la búsqueda, validación y actualización de código automáticamente." },
    ],
    heroImage: "/assets/huawei/cloud-dc.png",
  },
  {
    id: "vmware-migration",
    entryId: "on-prem-to-cloud",
    title: {
      en: "VMware Migration",
      es: "Migración VMware",
      zh: "VMware迁移",
    },
    categoryLabel: { en: "Datacenter On-Premise", es: "Datacenter On-Premise" },
      oneLiner: {
      en: "Migrate VMware, OpenStack, and on-prem VM workloads to Huawei Cloud ECS with SMS agent and MgC batch orchestration.",
      es: "Migre cargas de VM de VMware, OpenStack y on-prem a Huawei Cloud ECS con agente SMS y orquestación batch MgC.",
      zh: "将 VMware、OpenStack 和本地虚拟机工作负载迁移到华为云 ECS。",
    },
            targetCustomers: [
      { icon: "Server", who: { en: "Organizations with VMware or OpenStack VM estates", es: "Organizaciones con estates de VM en VMware u OpenStack" }, pain: { en: "UEFI/BIOS firmware mismatch is the #1 failure cause.", es: "Mismatch de firmware UEFI/BIOS es la causa #1 de fallo." } },
      { icon: "Cloud", who: { en: "Teams exiting datacenter to cloud", es: "Equipos saliendo del datacenter hacia la nube" }, pain: { en: "Needing phased migration with minimal downtime and dependency ordering.", es: "Necesitando migracion por fases con minimo downtime y ordering de dependencias." } },
      { icon: "Layers3", who: { en: "Enterprises needing batch migration of hundreds of VMs", es: "Empresas que necesitan migracion batch de cientos de VMs" }, pain: { en: "OS compatibility and driver injection must be validated for each VM.", es: "Compatibilidad de OS e inyeccion de drivers debe validarse para cada VM." } },
    ],
    painPoints: [
      { en: "UEFI/BIOS firmware mismatch is the #1 failure cause — source firmware must match the ECS ServerTemplate firmware type.", es: "Mismatch de firmware UEFI/BIOS es la causa #1 de fallo — el firmware origen debe matching el tipo de firmware del ServerTemplate ECS." },
      { en: "SMS API region is not the same as target ECS region — API calls go to the SMS service region, but ECS is created in the target region.", es: "La región de la API SMS no es la misma que la región ECS destino — las calls de API van a la región del servicio SMS, pero ECS se crea en la región destino." },
      { en: "Large VM estates need phased migration with minimal downtime and dependency ordering.", es: "Grandes estates de VM necesitan migración por fases con mínimo downtime y ordering de dependencias." },
      { en: "OS compatibility and driver injection (virtio) must be validated for each VM.", es: "La compatibilidad de OS e inyección de drivers (virtio) debe validarse para cada VM." },
    ],
    solutionApproach: [
      { en: "Phase 1 — Discover: Inventory VMs, OS versions, firmware type (UEFI/BIOS), and application dependencies.", es: "Fase 1 — Descubrir: Inventario de VMs, versiones de OS, tipo de firmware (UEFI/BIOS) y dependencias de aplicaciones." },
      { en: "Phase 2 — Agent: Install SMS Agent on source VMs — supports VMware, AWS, Azure, GCP, and on-prem (KVM/physical).", es: "Fase 2 — Agent: Instale SMS Agent en VMs origen — soporta VMware, AWS, Azure, GCP y on-prem (KVM/physical).",
      replaces: { en: "Equivalent to AWS MGN, Azure Migrate, and GCP Migrate for Compute Engine — single SMS Agent supports all sources with automatic driver injection.", es: "Equivalente a AWS MGN, Azure Migrate y GCP Migrate for Compute Engine — un único SMS Agent soporta todos los orígenes con inyección automática de drivers." },
      referenceLinks: [{ label: "SMS — Server Migration Service", url: "https://www.huaweicloud.com/intl/en-us/product/sms.html" }],},
      { en: "Phase 3 — Network: Configure target VPC, subnets, and security groups to match source networking.", es: "Fase 3 — Red: Configure VPC destino, subnets y security groups para matching el networking origen." },
      { en: "Phase 4 — Terraform: Generate migration code with correct ServerTemplate firmware type (UEFI or BIOS) matching source.", es: "Fase 4 — Terraform: Genere código de migración con tipo de firmware ServerTemplate correcto (UEFI o BIOS) matching el origen.",
      replaces: { en: "Equivalent to AWS EC2 launch templates and Azure VM images — ECS ServerTemplate handles firmware matching (UEFI/BIOS) automatically.", es: "Equivalente a AWS EC2 launch templates y Azure VM images — ECS ServerTemplate maneja matching de firmware (UEFI/BIOS) automáticamente." },
      referenceLinks: [{ label: "ECS — Elastic Cloud Server", url: "https://www.huaweicloud.com/intl/en-us/product/ecs.html" }],},
      { en: "Phase 5 — Apply: Run migration via SMS or MgC for batch — choose MIGRATE_FILE (file-level, faster) or MIGRATE_BLOCK (block-level, more reliable).", es: "Fase 5 — Apply: Ejecute migración via SMS o MgC para batch — elija MIGRATE_FILE (file-level, más rápido) o MIGRATE_BLOCK (block-level, más confiable).",
      replaces: { en: "Equivalent to AWS Migration Hub and Azure Migrate orchestration — MgC provides batch migration with progress tracking across hundreds of VMs.", es: "Equivalente a AWS Migration Hub y Azure Migrate orchestration — MgC provee migración batch con seguimiento de progreso across cientos de VMs." },
      referenceLinks: [{ label: "MgC — Migration Center", url: "https://www.huaweicloud.com/intl/en-us/product/mgc.html" }],},
      { en: "Phase 6 — Verify: Validate each VM post-migration — OS boot, network, application, and driver injection.", es: "Fase 6 — Verificar: Valide cada VM post-migración — boot de OS, red, aplicación e inyección de drivers.",
      referenceLinks: [{ label: "CBR — Cloud Backup and Recovery", url: "https://www.huaweicloud.com/intl/en-us/product/cbr.html" }],},
      { en: "Phase 7 — Clean up: Remove SMS Agent and decommission source VMs after validation.", es: "Fase 7 — Cleanup: Elimine SMS Agent y descomisione VMs origen después de validación." },
    ],
    recommendedServices: ["ECS", "SMS", "MgC", "VPC", "EIP", "CBR"],
    demoSkillLinks: [
      link("Datacenter Migration", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Datacenter-on-premise-migration/Vmware-Migration"),
    ],
    migrationMainExample: {
      title: { en: "AI-Assisted Datacenter Migration Tool", es: "Herramienta de migración de datacenter asistida con IA" },
      description: { en: "Skills and tools for migrating VMware and on-prem server workloads to Huawei Cloud ECS using SMS and MgC batch orchestration.", es: "Skills y herramientas para migrar cargas de VMware y on-prem a Huawei Cloud ECS usando SMS y orquestación batch MgC." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Datacenter-on-premise-migration/Vmware-Migration",
    },
    migrationRelatedTools: [
      {
        title: { en: "VMware Migration", es: "Migración de VMware" },
        description: { en: "Guidance and references for migrating VMware VMs to Huawei Cloud ECS.", es: "Guías y referencias para migrar VMs de VMware a Huawei Cloud ECS." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Datacenter-on-premise-migration/Vmware-Migration",
      },
      {
        title: { en: "AWS EC2 to Huawei ECS", es: "AWS EC2 a Huawei ECS" },
        description: { en: "Migrate Amazon EC2 instances to Huawei Cloud ECS. Covers instance type mapping, AMI conversion, EBS→EVS disk migration, and security group translation.", es: "Migre instancias de Amazon EC2 a Huawei Cloud ECS. Cubre mapeo de tipos de instancia, conversión de AMI, migración de discos EBS→EVS y traducción de security groups." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/VM-Migration",
        beta: true,
      },
      {
        title: { en: "Azure VM to Huawei ECS", es: "Azure VM a Huawei ECS" },
        description: { en: "Migrate Azure Virtual Machines to Huawei Cloud ECS. Includes VM size mapping, managed disk conversion, NIC rule translation, and boot diagnostics setup.", es: "Migre Azure Virtual Machines a Huawei Cloud ECS. Incluye mapeo de VM sizes, conversión de managed disks, traducción de NIC rules y setup de boot diagnostics." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/VM-Migration",
        beta: true,
      },
      {
        title: { en: "GCP GCE to Huawei ECS", es: "GCP GCE a Huawei ECS" },
        description: { en: "Migrate Google Compute Engine instances to Huawei Cloud ECS. Covers machine type mapping, persistent disk conversion, firewall rule translation, and metadata script migration.", es: "Migre instancias de Google Compute Engine a Huawei Cloud ECS. Cubre mapeo de machine types, conversión de persistent disks, traducción de firewall rules y migración de metadata scripts." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/VM-Migration",
        beta: true,
      },
    ],
    migrationExamples: [
      {
        title: { en: "Huawei Cloud SMS Migration", es: "Migración SMS de Huawei Cloud" },
        description: { en: "Server Migration Service (SMS) for migrating on-premises or cloud VMs to Huawei Cloud ECS with automatic driver adaptation.", es: "Server Migration Service (SMS) para migrar VMs on-premises o de nube a Huawei Cloud ECS con adaptación automática de drivers." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/VM-Migration/huaweicloud-sms-migration",
      },
    ],
    presentationUrl: "/presentations/vmware-migration.pdf",
            quickIntegration: {
      prerequisites: [
        { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
        { en: "Recommended skills installed in ~/.opencode/skills/ (or equivalent).", es: "Skills recomendados instalados en ~/.opencode/skills/ (o equivalente).", link: { label: "GitHub Skills", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Datacenter-on-premise-migration/Vmware-Migration" } },
        { en: "Target VPC.", es: "VPC objetivo." },
      ],
      steps: [
        { en: "Discover with AI: Scan your source environment and generate a complete inventory — servers, databases, applications, network, and dependencies. Verify the results against your actual environment.", es: "Discover con IA: Escanee su entorno origen y genere un inventario completo — servidores, bases de datos, aplicaciones, red y dependencias. Verifique los resultados contra su entorno real." },
        { en: "Plan with AI: Generate the target architecture on Huawei Cloud, including a migration plan and cost estimates. Review the plan before proceeding.", es: "Plan con IA: Genere la arquitectura objetivo en Huawei Cloud, incluyendo un plan de migración y estimaciones de costo. Revise el plan antes de continuar." },
        { en: "Agent with AI: Install the migration agent on each source VM. The agent syncs data to Huawei Cloud while your VMs keep running.", es: "Agent con IA: Instale el agente de migración en cada VM origen. El agente sincroniza datos con Huawei Cloud mientras sus VMs siguen ejecutándose." },
        { en: "Template with AI: Prepare migration templates for each VM group — matching or exceeding your current server sizes, storage, and network configuration.", es: "Template con IA: Prepare plantillas de migración para cada grupo de VMs — igualando o superando sus tamaños de servidor, almacenamiento y configuración de red actuales." },
        { en: "Migrate with AI: Start migration in batches, grouped by application. Begin with 2-3 non-critical VMs as a pilot, then scale up.", es: "Migrate con IA: Inicie la migración en lotes, agrupados por aplicación. Comience con 2-3 VMs no críticas como piloto, luego escale." },
        { en: "Validate with AI: Verify each migrated VM — boot, network, data integrity, and application health. Require specific evidence before approving cutover.", es: "Validate con IA: Verifique cada VM migrada — boot, red, integridad de datos y health de aplicación. Exija evidencia específica antes de aprobar el cutover." },
      ],
      configuration: [
        { en: "Max 23 disks per server: ECS supports 24 disks but SMS reserves one for its agent", es: "Máx 23 discos por servidor: ECS soporta 24 discos pero SMS reserva uno para su agente" },
        { en: "16 TB per disk on Linux: larger disks need manual image export/import", es: "16 TB por disco en Linux: discos mayores necesitan export/import manual de imagen" },
        { en: "No RAID or encrypted volumes: RAID arrays, BitLocker, and nested LVM cannot be migrated", es: "No RAID ni volúmenes encriptados: arrays RAID, BitLocker y LVM anidado no se pueden migrar" },
        { en: "Dynamic disks become basic: Windows dynamic disks convert to basic after migration", es: "Discos dinámicos vuelven básicos: los discos dinámicos de Windows se convierten en básicos tras la migración" },
        { en: "Source health check: CPU must be below 80% and available memory above 256 MB", es: "Health del origen: CPU debe estar bajo 80% y memoria disponible sobre 256 MB" },
        { en: "Limited file systems: Linux ext2/3/4, VFAT, XFS only; Windows NTFS (non-boot)", es: "File systems limitados: Linux ext2/3/4, VFAT, XFS únicamente; Windows NTFS (non-boot)" },
        { en: "Max 200 concurrent migrations: plan migration waves accordingly", es: "Máx 200 migraciones concurrentes: planifique olejas de migración en consecuencia" },
        { en: "No shared file systems: NFS, CIFS, and NAS mounts are not migrated", es: "No file systems compartidos: mounts NFS, CIFS y NAS no se migran" },
      ],
      apiAccess: [
        { en: "List source servers: hcloud SMS ListServers", es: "Listar servidores origen: hcloud SMS ListServers" },
        { en: "Get agent install command: hcloud SMS ShowCommand --server_id=xxx", es: "Obtener comando de agente: hcloud SMS ShowCommand --server_id=xxx" },
        { en: "Check task progress: hcloud SMS ShowTask --task_id=xxx", es: "Verificar progreso: hcloud SMS ShowTask --task_id=xxx" },
        { en: "List all migration tasks: hcloud SMS ListTasks", es: "Listar todas las tareas: hcloud SMS ListTasks" },
      ],
    },
      salesTalkTrack: [
      { en: "Is there a difference between VMware migration and server migration?", es: "¿Hay diferencia entre migración de VMware y migración de servidores?" },
      { en: "What operating systems do Huawei Cloud migration tools support?", es: "¿Qué sistemas operativos soportan las herramientas de migración de Huawei Cloud?" },
      { en: "Do I need to stop my applications during migration?", es: "¿Necesito detener mis aplicaciones durante la migración?" },
    ],
      expectedOutcomes: [
      { en: "Server migration is a general term for moving any server to Huawei Cloud. VMware migration is a specific type where VMs are moved from a VMware environment (vCenter/ESXi) to Huawei Cloud ECS. Huawei Cloud SMS and MgC support both, plus migration from AWS, Azure, GCP, and on-premises servers.", es: "La migración de servidores es un término general para mover cualquier servidor a Huawei Cloud. La migración de VMware es un tipo específico donde las VMs se mueven desde un entorno VMware (vCenter/ESXi) a Huawei Cloud ECS. SMS y MgC soportan ambos, además de migración desde AWS, Azure, GCP y servidores on-premises." },
      { en: "Huawei Cloud SMS supports 40+ operating systems including Linux distributions (CentOS, Ubuntu, Debian, Red Hat, SUSE, Oracle Linux) and Windows Server (2012, 2016, 2019, 2022).", es: "Huawei Cloud SMS soporta más de 40 sistemas operativos incluyendo distribuciones Linux (CentOS, Ubuntu, Debian, Red Hat, SUSE, Oracle Linux) y Windows Server (2012, 2016, 2019, 2022)." },
      { en: "No. SMS Agent performs incremental sync while your VM stays running. Only the final cutover requires a brief pause (typically minutes) to sync the last changes and switch DNS to the new ECS instance. Most migrations are non-disruptive until cutover.", es: "No. El SMS Agent realiza sincronización incremental mientras la VM sigue ejecutándose. Solo el cutover final requiere una pausa breve (típicamente minutos) para sincronizar los últimos cambios y cambiar el DNS a la nueva instancia ECS. La mayoría de las migraciones son no disruptivas hasta el cutover." },
    ],
    heroImage: "/assets/huawei/flexus.jpg",
  },
  {
    id: "vm-migration",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Virtual Machine", es: "Virtual Machine" },
    title: {
      en: "Virtual Machine Migration",
      es: "Migración de Máquinas Virtuales",
      zh: "虚拟机迁移",
    },
      oneLiner: {
      en: "Migrate virtual machines from any source to Huawei Cloud ECS with automated batch processing and validation.",
      es: "Migre máquinas virtuales desde cualquier origen a Huawei Cloud ECS con procesamiento batch automatizado y validación.",
      zh: "将任意来源的虚拟机迁移到华为云 ECS，支持自动化批量处理和迁移校验。",
    },
            targetCustomers: [
      { icon: "Server", who: { en: "Organizations with VM estates on any platform", es: "Organizaciones con estates de VM en cualquier plataforma" }, pain: { en: "UEFI/BIOS firmware mismatch is the #1 failure cause.", es: "Mismatch de firmware UEFI/BIOS es la causa #1 de fallo." } },
      { icon: "Cloud", who: { en: "Teams migrating VMs from AWS/Azure/GCP", es: "Equipos que migran VMs desde AWS/Azure/GCP" }, pain: { en: "Needing phased migration with minimal downtime and dependency ordering.", es: "Necesitando migracion por fases con minimo downtime y ordering de dependencias." } },
      { icon: "Layers3", who: { en: "Enterprises needing batch migration of hundreds of VMs", es: "Empresas que necesitan migracion batch de cientos de VMs" }, pain: { en: "OS compatibility and driver injection must be validated for each VM.", es: "Compatibilidad de OS e inyeccion de drivers debe validarse para cada VM." } },
    ],
    painPoints: [
      { en: "UEFI/BIOS firmware mismatch is the #1 failure cause — source firmware must match the ECS ServerTemplate firmware type.", es: "Mismatch de firmware UEFI/BIOS es la causa #1 de fallo — el firmware origen debe matching el tipo de firmware del ServerTemplate ECS." },
      { en: "SMS API region is not the same as target ECS region — API calls go to the SMS service region, but ECS is created in the target region.", es: "La región de la API SMS no es la misma que la región ECS destino — las calls de API van a la región del servicio SMS, pero ECS se crea en la región destino." },
      { en: "Large VM estates need phased migration with minimal downtime and dependency ordering.", es: "Grandes estates de VM necesitan migración por fases con mínimo downtime y ordering de dependencias." },
      { en: "OS compatibility and driver injection (virtio) must be validated for each VM.", es: "La compatibilidad de OS e inyección de drivers (virtio) debe validarse para cada VM." },
    ],
    solutionApproach: [
      { en: "Phase 1 — Discover: Inventory VMs, OS versions, firmware type (UEFI/BIOS), and application dependencies.", es: "Fase 1 — Descubrir: Inventario de VMs, versiones de OS, tipo de firmware (UEFI/BIOS) y dependencias de aplicaciones." },
      { en: "Phase 2 — Agent: Install SMS Agent on source VMs — supports VMware, AWS, Azure, GCP, and on-prem (KVM/physical).", es: "Fase 2 — Agent: Instale SMS Agent en VMs origen — soporta VMware, AWS, Azure, GCP y on-prem (KVM/physical).",
      replaces: { en: "Equivalent to AWS MGN, Azure Migrate, and GCP Migrate for Compute Engine — single SMS Agent supports all sources with automatic driver injection.", es: "Equivalente a AWS MGN, Azure Migrate y GCP Migrate for Compute Engine — un único SMS Agent soporta todos los orígenes con inyección automática de drivers." },
      referenceLinks: [{ label: "SMS — Server Migration Service", url: "https://www.huaweicloud.com/intl/en-us/product/sms.html" }],},
      { en: "Phase 3 — Network: Configure target VPC, subnets, and security groups to match source networking.", es: "Fase 3 — Red: Configure VPC destino, subnets y security groups para matching el networking origen." },
      { en: "Phase 4 — Terraform: Generate migration code with correct ServerTemplate firmware type (UEFI or BIOS) matching source.", es: "Fase 4 — Terraform: Genere código de migración con tipo de firmware ServerTemplate correcto (UEFI o BIOS) matching el origen.",
      replaces: { en: "Equivalent to AWS EC2 launch templates and Azure VM images — ECS ServerTemplate handles firmware matching (UEFI/BIOS) automatically.", es: "Equivalente a AWS EC2 launch templates y Azure VM images — ECS ServerTemplate maneja matching de firmware (UEFI/BIOS) automáticamente." },
      referenceLinks: [{ label: "ECS — Elastic Cloud Server", url: "https://www.huaweicloud.com/intl/en-us/product/ecs.html" }],},
      { en: "Phase 5 — Apply: Run migration via SMS or MgC for batch — choose MIGRATE_FILE (file-level, faster) or MIGRATE_BLOCK (block-level, more reliable).", es: "Fase 5 — Apply: Ejecute migración via SMS o MgC para batch — elija MIGRATE_FILE (file-level, más rápido) o MIGRATE_BLOCK (block-level, más confiable).",
      replaces: { en: "Equivalent to AWS Migration Hub and Azure Migrate orchestration — MgC provides batch migration with progress tracking across hundreds of VMs.", es: "Equivalente a AWS Migration Hub y Azure Migrate orchestration — MgC provee migración batch con seguimiento de progreso across cientos de VMs." },
      referenceLinks: [{ label: "MgC — Migration Center", url: "https://www.huaweicloud.com/intl/en-us/product/mgc.html" }],},
      { en: "Phase 6 — Verify: Validate each VM post-migration — OS boot, network, application, and driver injection.", es: "Fase 6 — Verificar: Valide cada VM post-migración — boot de OS, red, aplicación e inyección de drivers.",
      referenceLinks: [{ label: "CBR — Cloud Backup and Recovery", url: "https://www.huaweicloud.com/intl/en-us/product/cbr.html" }],},
      { en: "Phase 7 — Clean up: Remove SMS Agent and decommission source VMs after validation.", es: "Fase 7 — Cleanup: Elimine SMS Agent y descomisione VMs origen después de validación." },
    ],
    recommendedServices: ["ECS", "SMS", "MgC", "VPC", "EIP", "CBR"],
    demoSkillLinks: [
      link("Virtual Machine Migration", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/VM-Migration"),
    ],
    migrationMainExample: {
      title: { en: "AI-Assisted Virtual Machine Migration Tool", es: "Herramienta de migración de máquinas virtuales asistida con IA" },
      description: { en: "Skills and tools for migrating virtual machines and server workloads to Huawei Cloud ECS using SMS and VMware migration guidance.", es: "Skills y herramientas para migrar máquinas virtuales y cargas de servidores a Huawei Cloud ECS usando SMS y guía de migración VMware." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/VM-Migration",
    },
    migrationRelatedTools: [
      {
        title: { en: "VMware Migration", es: "Migración de VMware" },
        description: { en: "Guidance and references for migrating VMware VMs to Huawei Cloud ECS.", es: "Guías y referencias para migrar VMs de VMware a Huawei Cloud ECS." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Datacenter-on-premise-migration/Vmware-Migration",
      },
      {
        title: { en: "AWS EC2 to Huawei ECS", es: "AWS EC2 a Huawei ECS" },
        description: { en: "Migrate Amazon EC2 instances to Huawei Cloud ECS. Covers instance type mapping, AMI conversion, EBS→EVS disk migration, and security group translation.", es: "Migre instancias de Amazon EC2 a Huawei Cloud ECS. Cubre mapeo de tipos de instancia, conversión de AMI, migración de discos EBS→EVS y traducción de security groups." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/VM-Migration",
        beta: true,
      },
      {
        title: { en: "Azure VM to Huawei ECS", es: "Azure VM a Huawei ECS" },
        description: { en: "Migrate Azure Virtual Machines to Huawei Cloud ECS. Includes VM size mapping, managed disk conversion, NIC rule translation, and boot diagnostics setup.", es: "Migre Azure Virtual Machines a Huawei Cloud ECS. Incluye mapeo de VM sizes, conversión de managed disks, traducción de NIC rules y setup de boot diagnostics." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/VM-Migration",
        beta: true,
      },
      {
        title: { en: "GCP GCE to Huawei ECS", es: "GCP GCE a Huawei ECS" },
        description: { en: "Migrate Google Compute Engine instances to Huawei Cloud ECS. Covers machine type mapping, persistent disk conversion, firewall rule translation, and metadata script migration.", es: "Migre instancias de Google Compute Engine a Huawei Cloud ECS. Cubre mapeo de machine types, conversión de persistent disks, traducción de firewall rules y migración de metadata scripts." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/VM-Migration",
        beta: true,
      },
    ],
    migrationExamples: [
      {
        title: { en: "Huawei Cloud SMS Migration", es: "Migración SMS de Huawei Cloud" },
        description: { en: "Server Migration Service (SMS) for migrating on-premises or cloud VMs to Huawei Cloud ECS with automatic driver adaptation.", es: "Server Migration Service (SMS) para migrar VMs on-premises o de nube a Huawei Cloud ECS con adaptación automática de drivers." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/VM-Migration/huaweicloud-sms-migration",
      },
    ],
    presentationUrl: "/presentations/vm-migration.pdf",
            quickIntegration: {
    prerequisites: [
      { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
      { en: "Recommended skills installed in ~/.opencode/skills/ (or equivalent).", es: "Skills recomendados instalados en ~/.opencode/skills/ (o equivalente).", link: { label: "GitHub Skills", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/VM-Migration" } },
      { en: "Target VPC.", es: "VPC objetivo." },
    ],
    steps: [
      { en: "Discover with AI: Scan your source VMs — OS, firmware type, disks, network, and dependencies. Verify the results against your actual environment.", es: "Descubrir con IA: Escanee sus VMs origen — OS, tipo de firmware, discos, red y dependencias. Verifique los resultados contra su entorno actual." },
      { en: "Plan with AI: AI maps each VM to a matching ECS flavor on Huawei Cloud and generates a phased migration plan. Review the plan before proceeding.", es: "Planificar con IA: La IA mapea cada VM a un flavor de ECS compatible en Huawei Cloud y genera un plan de migración por fases. Revise el plan antes de continuar." },
      { en: "Agent with AI: Install the SMS Agent on each source VM. The agent syncs data to Huawei Cloud while your VMs keep running.", es: "Agente con IA: Instale el SMS Agent en cada VM origen. El agente sincroniza datos a Huawei Cloud mientras sus VMs siguen ejecutándose." },
      { en: "Template with AI: AI prepares migration templates with matching firmware and sizing for each VM group.", es: "Plantilla con IA: La IA prepara plantillas de migración con firmware y sizing compatible para cada grupo de VMs." },
      { en: "Migrate with AI: Start migration in batches via MgC. Begin with 2-3 non-critical VMs as a pilot, then scale up.", es: "Migrar con IA: Inicie la migración en lotes vía MgC. Comience con 2-3 VMs no críticas como piloto, luego escale." },
      { en: "Validate with AI: AI checks each VM — OS boot, network, drivers, and application health. Require specific evidence before approving cutover.", es: "Validar con IA: La IA verifica cada VM — boot de OS, red, drivers y health de aplicación. Exija evidencia específica antes de aprobar el cutover." },
    ],
      configuration: [
        { en: "Max 23 disks per server: ECS supports 24 disks but SMS reserves one for its agent", es: "Máx 23 discos por servidor: ECS soporta 24 discos pero SMS reserva uno para su agente" },
        { en: "16 TB per disk on Linux: larger disks need manual image export/import", es: "16 TB por disco en Linux: discos mayores necesitan export/import manual de imagen" },
        { en: "No RAID or encrypted volumes: RAID arrays, BitLocker, and nested LVM cannot be migrated", es: "No RAID ni volúmenes encriptados: arrays RAID, BitLocker y LVM anidado no se pueden migrar" },
        { en: "Dynamic disks become basic: Windows dynamic disks convert to basic after migration", es: "Discos dinámicos vuelven básicos: los discos dinámicos de Windows se convierten en básicos tras la migración" },
        { en: "Source health check: CPU must be below 80% and available memory above 256 MB", es: "Health del origen: CPU debe estar bajo 80% y memoria disponible sobre 256 MB" },
        { en: "Limited file systems: Linux ext2/3/4, VFAT, XFS only; Windows NTFS (non-boot)", es: "File systems limitados: Linux ext2/3/4, VFAT, XFS únicamente; Windows NTFS (non-boot)" },
        { en: "Max 200 concurrent migrations: plan migration waves accordingly", es: "Máx 200 migraciones concurrentes: planifique olejas de migración en consecuencia" },
        { en: "No shared file systems: NFS, CIFS, and NAS mounts are not migrated", es: "No file systems compartidos: mounts NFS, CIFS y NAS no se migran" },
      ],
      apiAccess: [
        { en: "List source servers: hcloud SMS ListServers", es: "Listar servidores origen: hcloud SMS ListServers" },
        { en: "Get agent install command: hcloud SMS ShowCommand --server_id=xxx", es: "Obtener comando de agente: hcloud SMS ShowCommand --server_id=xxx" },
        { en: "Check task progress: hcloud SMS ShowTask --task_id=xxx", es: "Verificar progreso: hcloud SMS ShowTask --task_id=xxx" },
        { en: "List all migration tasks: hcloud SMS ListTasks", es: "Listar todas las tareas: hcloud SMS ListTasks" },
      ],
    },
      salesTalkTrack: [
      { en: "Can AI migrate VMs from any source platform?", es: "¿Puede la IA migrar VMs desde cualquier plataforma de origen?" },
      { en: "Do I need to match firmware types between source and target?", es: "¿Necesito coincidir tipos de firmware entre origen y destino?" },
      { en: "How does AI handle batch migration of hundreds of VMs?", es: "¿Cómo maneja la IA la migración por lotes de cientos de VMs?" },
    ],
    expectedOutcomes: [
      { en: "Yes. AI uses Huawei Cloud SMS (Server Migration Service) which supports VMware, AWS EC2, Azure VM, GCP GCE, and on-premises servers. The SMS Agent installs on the source VM and performs incremental disk sync to Huawei Cloud ECS. Your team selects the source platform and AI handles the rest.", es: "Sí. La IA usa SMS de Huawei Cloud que soporta VMware, AWS EC2, Azure VM, GCP GCE y servidores on-premises. El SMS Agent se instala en la VM origen y realiza sincronización incremental de disco a Huawei Cloud ECS. Su equipo selecciona la plataforma origen y la IA maneja el resto." },
      { en: "AI checks firmware compatibility automatically. It detects whether each source VM uses UEFI or BIOS and selects a matching ECS flavor on Huawei Cloud. If a mismatch is found, AI flags it and recommends a compatible target before migration starts. Your team reviews and approves the mapping.", es: "La IA verifica la compatibilidad de firmware automáticamente. Detecta si cada VM origen usa UEFI o BIOS y selecciona un flavor de ECS compatible en Huawei Cloud. Si encuentra una incompatibilidad, la IA la marca y recomienda un destino compatible antes de que comience la migración. Su equipo revisa y aprueba el mapeo." },
      { en: "AI uses MgC (Migration Center) to orchestrate batch migrations with progress tracking. It groups VMs by priority, dependency, and maintenance window. Each VM migrates independently with incremental sync, so failures don't block others. Your team monitors progress on a dashboard and can pause, retry, or reorder as needed.", es: "La IA usa MgC (Migration Center) para orquestar migraciones por lotes con seguimiento de progreso. Agrupa las VMs por prioridad, dependencia y ventana de mantenimiento. Cada VM migra independientemente con sincronización incremental, por lo que los fallos no bloquean a otras. Su equipo monitorea el progreso en un dashboard y puede pausar, reintentar o reordenar según sea necesario." },
    ],
    heroImage: "/assets/huawei/flexus.jpg",
  },

  {
    id: "codearts-deployment",
    entryId: "on-prem-to-cloud",
    title: {
      en: "CodeArts with AI",
      es: "CodeArts con IA",
      zh: "CodeArts与AI",
    },
    categoryLabel: { en: "Cloud Foundation", es: "Cloud Foundation" },
    oneLiner: {
      en: "Deploy applications with AI-guided CodeArts pipelines and KooCLI orchestration.",
      es: "Despliegue aplicaciones con pipelines de CodeArts guiados por IA y orquestación con KooCLI.",
      zh: "使用AI引导的CodeArts流水线和KooCLI编排部署应用程序。",
    },
    targetCustomers: [
      { icon: "Cloud", who: { en: "DevOps teams adopting CI/CD", es: "Equipos DevOps adoptando CI/CD" }, pain: { en: "Manual builds and deployments are slow and error-prone.", es: "Builds y despliegues manuales son lentos y propensos a errores." } },
      { icon: "Server", who: { en: "Teams with growing application portfolios", es: "Equipos con portafolios de aplicaciones crecientes" }, pain: { en: "Inconsistent environments and no automated pipeline.", es: "Entornos inconsistentes y sin pipeline automatizado." } },
      { icon: "Cloud", who: { en: "Organizations standardizing CI/CD on Huawei Cloud", es: "Organizaciones estandarizando CI/CD en Huawei Cloud" }, pain: { en: "No unified DevOps platform — tools scattered across providers.", es: "Sin plataforma DevOps unificada — herramientas dispersas entre proveedores." } },
    ],
    painPoints: [
      { en: "Manual deployment processes slow down release cycles.", es: "Procesos de despliegue manual ralentizan los ciclos de release." },
      { en: "Inconsistent builds across environments cause production issues.", es: "Builds inconsistentes entre entornos causan problemas en producción." },
      { en: "No AI-guided discovery of pipeline dependencies or build artifacts.", es: "Sin descubrimiento guiado por IA de dependencias de pipeline o build artifacts." },
    ],
    solutionApproach: [
      { en: "AI discovers your CodeArts project structure, repositories, and pipeline dependencies in minutes.", es: "La IA descubre la estructura de tu proyecto CodeArts, repositorios y dependencias de pipeline en minutos.", referenceLinks: [{ label: "CodeArts — Huawei Cloud", url: "https://www.huaweicloud.com/intl/en-us/product/codearts.html" }] },
      { en: "AI prepares deployment pipelines with properly sized CCE workloads and network configuration.", es: "La IA prepara pipelines de despliegue con workloads CCE correctamente dimensionados y configuración de red.", referenceLinks: [{ label: "CCE — Cloud Container Engine", url: "https://www.huaweicloud.com/intl/en-us/product/cce.html" }] },
      { en: "AI executes deployment in batches, handles errors, and validates every service.", es: "La IA ejecuta el despliegue en lotes, maneja errores y valida cada servicio." },
    ],
    recommendedServices: ["CodeArts", "CCE", "ECS", "VPC"],
    demoSkillLinks: [
      link("CodeArts Deployment", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/CodeArts-Overview"),
    ],
    migrationMainExample: {
      title: { en: "AI-Guided CodeArts Deployment", es: "Despliegue de CodeArts Guiado por IA" },
      description: { en: "Skills and tools for deploying applications with CodeArts pipelines and KooCLI orchestration.", es: "Skills y herramientas para desplegar aplicaciones con pipelines de CodeArts y orquestación KooCLI." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/CodeArts-Overview",
    },
    migrationRelatedTools: [
      {
        title: { en: "CodeArts DevOps Operations Skill", es: "Skill de Operaciones DevOps con CodeArts" },
        description: { en: "AI-guided CodeArts pipeline operations: repo, check, build, artifact, test plan, deploy via KooCLI.", es: "Operaciones de pipeline CodeArts guiadas por IA: repo, check, build, artifact, test plan, deploy via KooCLI." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/CodeArts-Overview/huawei-codearts-devops-operations",
      },
      {
        title: { en: "CodeArts Project Design Skill", es: "Skill de Diseño de Proyectos CodeArts" },
        description: { en: "AI-guided CodeArts project design and creation: repositories, pipelines, and team configuration via KooCLI.", es: "Diseño y creación de proyectos CodeArts guiados por IA: repositorios, pipelines y configuración de equipo via KooCLI." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/CodeArts-Overview/huawei-codearts-project-design",
      },
    ],
    presentationUrl: "/presentations/codearts-kocli-deployment.pdf",
    quickIntegration: {
      prerequisites: [
        { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
        { en: "Recommended skills installed in ~/.opencode/skills/ (or equivalent).", es: "Skills recomendados instalados en ~/.opencode/skills/ (o equivalente).", link: { label: "GitHub Skills", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/CodeArts-Overview" } },
        { en: "CodeArts project with repositories.", es: "Proyecto CodeArts con repositorios." },
      ],
      steps: [
        { en: "Discover: AI scans your CodeArts project, repositories, and pipeline dependencies.", es: "Descubrir: La IA escanea tu proyecto CodeArts, repositorios y dependencias de pipeline." },
        { en: "Plan: AI prepares deployment pipelines with properly sized workloads.", es: "Planificar: La IA prepara pipelines de despliegue con workloads correctamente dimensionados." },
        { en: "Execute: AI deploys in batches grouped by dependency.", es: "Ejecutar: La IA despliega en lotes agrupados por dependencia." },
        { en: "Validate: AI checks every deployed service and reports results.", es: "Validar: La IA verifica cada servicio desplegado y reporta resultados." },
      ],
      configuration: [
        { en: "CodeArts project ID and region.", es: "ID del proyecto CodeArts y región." },
        { en: "Target CCE cluster and node flavors.", es: "Cluster CCE objetivo y flavors de nodo." },
      ],
    },
    salesTalkTrack: [
      { en: "How does AI accelerate CodeArts deployment?", es: "¿Cómo acelera la IA el despliegue con CodeArts?" },
      { en: "Can AI handle multi-service deployments with dependencies?", es: "¿Puede la IA manejar despliegues multi-servicio con dependencias?" },
      { en: "How does KooCLI integrate with CodeArts pipelines?", es: "¿Cómo integra KooCLI los pipelines de CodeArts?" },
    ],
    expectedOutcomes: [
      { en: "AI discovers 100+ repositories and pipelines in minutes. 40% faster releases with automated orchestration.", es: "La IA descubre 100+ repositorios y pipelines en minutos. 40% releases más rápidos con orquestación automatizada." },
      { en: "AI spots configuration issues and dependencies early. Over 95% succeed on the first try.", es: "La IA detecta problemas de configuración y dependencias temprano. Más de 95% exito en el primer intento." },
      { en: "KooCLI enables repeatable, scriptable deployments. Zero manual console clicks for routine operations.", es: "KooCLI habilita despliegues repetibles y scriptables. Cero clicks manuales en consola para operaciones rutinarias." },
    ],
    heroImage: "/assets/huawei/ai-skills/ai-data-stream.jpg",
  },

  {
    id: "mrs-deployment",
    entryId: "on-prem-to-cloud",
    title: {
      en: "MRS Deployment",
      es: "Despliegue MRS",
      zh: "MRS部署",
    },
    categoryLabel: { en: "Big Data", es: "Big Data" },
    oneLiner: {
      en: "Deploy big data clusters with AI-guided MRS and KooCLI orchestration.",
      es: "Despliegue clusters de big data con MRS guiado por IA y orquestación con KooCLI.",
      zh: "使用AI引导的MRS和KooCLI编排部署大数据集群。",
    },
    targetCustomers: [
      { icon: "Cloud", who: { en: "Data teams needing managed Hadoop/Spark", es: "Equipos de datos que necesitan Hadoop/Spark gestionado" }, pain: { en: "Running Hadoop and Spark manually means heavy setup and patching.", es: "Ejecutar Hadoop y Spark manualmente implica setup y parches pesados." } },
      { icon: "Server", who: { en: "Organizations processing large data volumes", es: "Organizaciones que procesan grandes volúmenes de datos" }, pain: { en: "No elastic scaling for batch workloads.", es: "Sin escalado elástico para workloads batch." } },
      { icon: "Cloud", who: { en: "Teams migrating from on-prem Hadoop", es: "Equipos migrando desde Hadoop on-prem" }, pain: { en: "Manual Hadoop setup and patching is unsustainable.", es: "Setup y parches manuales de Hadoop son insostenibles." } },
    ],
    painPoints: [
      { en: "Manual cluster setup is slow and error-prone.", es: "Setup manual de cluster es lento y propenso a errores." },
      { en: "Sizing nodes correctly requires deep expertise.", es: "Dimensionar nodos correctamente requiere expertise profundo." },
      { en: "Component selection (Hive, Spark, HBase, Flink) is complex and interdependent.", es: "Selección de componentes (Hive, Spark, HBase, Flink) es compleja e interdependiente." },
    ],
    solutionApproach: [
      { en: "AI recommends cluster topology and component sets in minutes based on your workload.", es: "La IA recomienda topología de cluster y conjuntos de componentes en minutos basado en tu workload.", referenceLinks: [{ label: "MRS — MapReduce Service", url: "https://www.huaweicloud.com/intl/en-us/product/mrs.html" }] },
      { en: "AI generates KooCLI commands to provision and scale the MRS cluster.", es: "La IA genera comandos KooCLI para provisionar y escalar el cluster MRS." },
      { en: "AI validates cluster health, HDFS balance, and job completion.", es: "La IA valida salud del cluster, balance HDFS y completitud de jobs.", referenceLinks: [{ label: "OBS — Object Storage", url: "https://www.huaweicloud.com/intl/en-us/product/obs.html" }] },
    ],
    recommendedServices: ["MRS", "OBS", "VPC", "EIP"],
    demoSkillLinks: [
      link("MRS Deployment", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Deployment"),
    ],
    migrationMainExample: {
      title: { en: "AI-Guided MRS Deployment", es: "Despliegue de MRS Guiado por IA" },
      description: { en: "Skills and tools for deploying MRS big data clusters with KooCLI orchestration.", es: "Skills y herramientas para desplegar clusters de big data MRS con orquestación KooCLI." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Deployment",
    },
    migrationRelatedTools: [
      {
        title: { en: "MRS Deploy Operations Skill", es: "Skill de Operaciones de Despliegue MRS" },
        description: { en: "AI-guided MRS cluster deployment: custom cluster creation, component selection, and scaling via KooCLI.", es: "Despliegue de cluster MRS guiado por IA: creación de cluster personalizado, selección de componentes y escalado via KooCLI." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Deployment/huawei-mrs-deploy-operations",
      },
    ],
    presentationUrl: "/presentations/mrs-kocli-deployment.pdf",
    quickIntegration: {
      prerequisites: [
        { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
        { en: "Recommended skills installed in ~/.opencode/skills/ (or equivalent).", es: "Skills recomendados instalados en ~/.opencode/skills/ (o equivalente).", link: { label: "GitHub Skills", url: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Deployment" } },
        { en: "Target VPC and OBS bucket.", es: "VPC objetivo y bucket OBS." },
      ],
      steps: [
        { en: "Discover: AI analyzes your data sources and workload to recommend cluster topology.", es: "Descubrir: La IA analiza tus fuentes de datos y workload para recomendar topología de cluster." },
        { en: "Plan: AI prepares MRS cluster templates with sized nodes and components.", es: "Planificar: La IA prepara templates de cluster MRS con nodos dimensionados y componentes." },
        { en: "Execute: AI provisions the cluster and bootstraps components.", es: "Ejecutar: La IA provisiona el cluster y bootstrap de componentes." },
        { en: "Validate: AI checks cluster health, HDFS balance, and job success.", es: "Validar: La IA verifica salud del cluster, balance HDFS y exito de jobs." },
      ],
      configuration: [
        { en: "MRS cluster type and component set (Hive, Spark, HBase, Flink).", es: "Tipo de cluster MRS y conjunto de componentes (Hive, Spark, HBase, Flink)." },
        { en: "Node flavors for Master, Core, and Task nodes.", es: "Flavors de nodo para Master, Core y Task." },
      ],
    },
    salesTalkTrack: [
      { en: "How does AI size MRS clusters correctly?", es: "¿Cómo dimensiona la IA los clusters MRS correctamente?" },
      { en: "Can AI handle elastic scaling for batch workloads?", es: "¿Puede la IA manejar escalado elástico para workloads batch?" },
      { en: "How does AI select the right component set (Hive, Spark, HBase, Flink)?", es: "¿Cómo selecciona la IA el conjunto correcto de componentes (Hive, Spark, HBase, Flink)?" },
    ],
    expectedOutcomes: [
      { en: "AI sizes clusters and recommends components in minutes. 40% faster provisioning.", es: "La IA dimensiona clusters y recomienda componentes en minutos. 40% provisionamiento más rápido." },
      { en: "AI spots undersized nodes and missing components early. Over 95% succeed on first try.", es: "La IA detecta nodos subdimensionados y componentes faltantes temprano. Más de 95% exito en el primer intento." },
      { en: "KooCLI enables repeatable cluster provisioning. Zero manual console clicks for routine operations.", es: "KooCLI habilita provisionamiento repetible de clusters. Cero clicks manuales en consola para operaciones rutinarias." },
    ],
    heroImage: "/assets/huawei/ai-skills/ai-data-stream.jpg",
  },

  {
    id: "mrs-migration",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Big Data", es: "Big Data" },
    title: {
      en: "MRS Migration",
      es: "Migración MRS",
      zh: "MRS迁移",
    },
    oneLiner: {
      en: "Migrate complete big-data systems — components and data — from on-prem Hadoop, AWS EMR, Azure HDInsight, or GCP Dataproc to Huawei Cloud MRS with KooCLI.",
      es: "Migre sistemas big-data completos — componentes y datos — desde Hadoop on-prem, AWS EMR, Azure HDInsight o GCP Dataproc a Huawei Cloud MRS con KooCLI.",
      zh: "将完整的大数据系统（组件和数据）从本地Hadoop、AWS EMR、Azure HDInsight或GCP Dataproc迁移到华为云MRS。",
    },
    targetCustomers: [
      { icon: "Cloud", who: { en: "Organizations running on-prem Hadoop (CDH, Hortonworks, FusionInsight)", es: "Organizaciones con Hadoop on-prem (CDH, Hortonworks, FusionInsight)" }, pain: { en: "Unsustainable manual patching and hardware maintenance.", es: "Parches manuales y mantenimiento de hardware insostenibles." } },
      { icon: "Cloud", who: { en: "Teams migrating from AWS EMR, Azure HDInsight, or GCP Dataproc", es: "Equipos migrando desde AWS EMR, Azure HDInsight o GCP Dataproc" }, pain: { en: "Cloud lock-in with expensive egress for large datasets.", es: "Cloud lock-in con egress costoso para datasets grandes." } },
      { icon: "Server", who: { en: "Data teams with Hive, HBase, Spark, Flink workloads", es: "Equipos de datos con workloads de Hive, HBase, Spark, Flink" }, pain: { en: "Component interdependencies make migration complex.", es: "Interdependencias de componentes hacen la migración compleja." } },
    ],
    painPoints: [
      { en: "Source inventory is manual — no API reads a source cluster. Components, versions, and data sizes must be collected before migration.", es: "El inventario source es manual — ninguna API lee un cluster source. Componentes, versiones y tamaños de datos deben recolectarse antes de migrar." },
      { en: "OMS requires destination OBS bucket in the same region as the OMS endpoint — cross-region destination is rejected.", es: "OMS requiere bucket OBS destino en la misma región que el endpoint OMS — destino cross-region es rechazado." },
      { en: "MRS 3.x has no V2 list/show/delete-cluster operation — no automated rollback for the target cluster.", es: "MRS 3.x no tiene operación V2 de list/show/delete-cluster — sin rollback automatizado para el cluster target." },
      { en: "DistCp job state COMPLETE means submitted, not finished — polling ShowSingleJob is required.", es: "State COMPLETE de DistCp significa submitted, no finished — polling de ShowSingleJob es requerido." },
    ],
    solutionApproach: [
      { en: "Phase 1 — Inventory: Collect source cluster inventory (components, versions, data footprint, table counts) via MgC Agent or source tooling.", es: "Fase 1 — Inventario: Recolectar inventario del cluster source (componentes, versiones, footprint de datos, conteo de tablas) vía MgC Agent o tooling del source.",
      referenceLinks: [{ label: "MgC — Migration Center", url: "https://www.huaweicloud.com/intl/en-us/product/mgc.html" }] },
      { en: "Phase 2 — Land Target: Create MRS CUSTOM cluster whose component set reproduces the source inventory. Validate with ListNodes.", es: "Fase 2 — Land Target: Crear cluster MRS CUSTOM cuyo set de componentes reproduce el inventario source. Validar con ListNodes.",
      referenceLinks: [{ label: "MRS — MapReduce Service", url: "https://www.huaweicloud.com/intl/en-us/product/mrs.html" }] },
      { en: "Phase 3 — Migrate Data: OMS CreateTask moves bulk objects from S3/Blob/GCS to OBS. MRS DistCp loads from OBS to target HDFS.", es: "Fase 3 — Migrar Datos: OMS CreateTask mueve objetos bulk desde S3/Blob/GCS a OBS. MRS DistCp carga desde OBS a HDFS target.",
      referenceLinks: [{ label: "OMS — Object Storage Migration", url: "https://www.huaweicloud.com/intl/en-us/product/oms.html" }, { label: "OBS — Object Storage", url: "https://www.huaweicloud.com/intl/en-us/product/obs.html" }] },
      { en: "Phase 4 — Rebuild Metadata: HiveSql/HiveScript jobs recreate table definitions. Register partitions for partitioned tables.", es: "Fase 4 — Reconstruir Metadata: Jobs de HiveSql/HiveScript recrean definiciones de tablas. Registrar particiones para tablas particionadas." },
      { en: "Phase 5 — Verify: Compare row counts and checksums per table. Run critical jobs against target and diff output. MgC consistency verification.", es: "Fase 5 — Verificar: Comparar conteos de filas y checksums por tabla. Ejecutar jobs críticos contra target y diff del output. Verificación de consistencia MgC." },
    ],
    recommendedServices: ["MRS", "OMS", "OBS", "VPC", "EIP"],
    demoSkillLinks: [
      link("MRS Migration", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Migration"),
    ],
    migrationMainExample: {
      title: { en: "AI-Guided MRS Migration", es: "Migración MRS Guiada por IA" },
      description: { en: "Complete toolkit for migrating big-data systems to Huawei Cloud MRS. Three migration planes: OMS bulk object transfer, MRS DistCp data load, Hive metadata rebuild.", es: "Toolkit completo para migrar sistemas big-data a Huawei Cloud MRS. Tres planos de migración: transferencia bulk OMS, carga de datos DistCp MRS, reconstrucción de metadata Hive." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Migration",
    },
    migrationRelatedTools: [
      {
        title: { en: "MRS Migration Operations Skill", es: "Skill de Operaciones de Migración MRS" },
        description: { en: "Migrate big-data systems to MRS using KooCLI. Covers OMS bulk object migration, DistCp data load, Hive metadata rebuild, and MgC consistency verification.", es: "Migre sistemas big-data a MRS usando KooCLI. Cubre migración bulk OMS, carga DistCp, reconstrucción metadata Hive y verificación de consistencia MgC." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Migration/huawei-mrs-migration-operations",
      },
      {
        title: { en: "MRS Deployment Skill", es: "Skill de Despliegue MRS" },
        description: { en: "Deploy new MRS clusters with KooCLI. Use this first if you need a fresh cluster before migrating data.", es: "Despliegue clusters MRS nuevos con KooCLI. Use esto primero si necesita un cluster fresco antes de migrar datos." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Deployment/huawei-mrs-deploy-operations",
      },
    ],
    presentationUrl: "/presentations/mrs-kocli-migration.pdf",
    quickIntegration: {
      prerequisites: [
        { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
        { en: "hcloud CLI (KooCLI) installed and configured.", es: "hcloud CLI (KooCLI) instalado y configurado.", link: { label: "KooCLI Setup", url: "https://support.huaweicloud.com/intl/en-us/cli/index.html" } },
        { en: "Source cluster inventory collected (components, versions, data sizes).", es: "Inventario del cluster source recolectado (componentes, versiones, tamaños de datos)." },
        { en: "Target VPC, subnet, and OBS staging bucket in the same region.", es: "VPC target, subnet y bucket OBS staging en la misma región." },
      ],
      steps: [
        { en: "Inventory: AI helps collect and validate the source cluster inventory — components, versions, data footprint, table/partition counts.", es: "Inventario: La IA ayuda a recolectar y validar el inventario del cluster source — componentes, versiones, footprint de datos, conteos de tablas/particiones." },
        { en: "Land: AI generates the MRS CreateCluster command with the right component set and node sizing. Explicit approval required.", es: "Land: La IA genera el comando MRS CreateCluster con el set correcto de componentes y sizing de nodos. Aprobación explícita requerida." },
        { en: "Migrate Data: AI creates OMS tasks for bulk object migration and DistCp jobs for HDFS loading. Tracks completion and failed objects.", es: "Migrar Datos: La IA crea tareas OMS para migración bulk de objetos y jobs DistCp para carga HDFS. Rastrea completitud y objetos fallidos." },
        { en: "Rebuild Metadata: AI generates HiveSql/HiveScript jobs to recreate table definitions and register partitions.", es: "Reconstruir Metadata: La IA genera jobs HiveSql/HiveScript para recrear definiciones de tablas y registrar particiones." },
        { en: "Verify: AI compares row counts, checksums, and critical job output between source and target. Reports cutover readiness.", es: "Verificar: La IA compara conteos de filas, checksums y output de jobs críticos entre source y target. Reporta readiness de cutover." },
      ],
      configuration: [
        { en: "Source platform (onprem, aws, azure, gcp) and read-only credentials.", es: "Plataforma source (onprem, aws, azure, gcp) y credenciales read-only." },
        { en: "MRS cluster version (e.g., MRS 3.3.0-LTS) and component list.", es: "Versión de cluster MRS (ej., MRS 3.3.0-LTS) y lista de componentes." },
        { en: "Node groups sized against source data footprint.", es: "Node groups dimensionados contra el footprint de datos source." },
      ],
    },
    salesTalkTrack: [
      { en: "How does AI handle the source inventory gap?", es: "¿Cómo maneja la IA el gap de inventario source?" },
      { en: "Can AI migrate data from AWS EMR / Azure HDInsight to MRS?", es: "¿Puede la IA migrar datos desde AWS EMR / Azure HDInsight a MRS?" },
      { en: "What happens when a source component has no MRS equivalent?", es: "¿Qué pasa cuando un componente source no tiene equivalente en MRS?" },
    ],
    expectedOutcomes: [
      { en: "AI derives the target component set from the source inventory — no guessing. Unmappable components are flagged, not silently dropped.", es: "La IA deriva el set de componentes target del inventario source — sin adivinar. Componentes no mapeables se marcan, no se descartan silenciosamente." },
      { en: "Three-plane migration (OMS + DistCp + Hive) handles both data and metadata. Partitions are registered so tables read correctly.", es: "Migración de tres planos (OMS + DistCp + Hive) maneja datos y metadata. Particiones se registran para que las tablas lean correctamente." },
      { en: "Verification compares row counts and checksums per table. Cutover readiness is evidence-backed, not assumed.", es: "Verificación compara conteos de filas y checksums por tabla. Readiness de cutover está respaldado por evidencia, no asumido." },
    ],
    heroImage: "/assets/huawei/ai-skills/ai-data-stream.jpg",
  },

  {
    id: "cbr-backup-restore",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Cloud Foundation", es: "Cloud Foundation" },
    title: {
      en: "CBR Backup and Restore",
      es: "CBR Backup y Restore",
    },
    oneLiner: {
      en: "Discover, configure, execute, validate, and restore Huawei Cloud CBR backups for ECS, EVS, and CCE nodes.",
      es: "Descubra, configure, ejecute, valide y restaure backups de CBR en Huawei Cloud para ECS, EVS y nodos CCE.",
    },
    targetCustomers: [
      { icon: "Shield", who: { en: "Organizations needing reliable backup for ECS instances", es: "Organizaciones que necesitan backup confiable para instancias ECS" }, pain: { en: "Manual backup is error-prone and hard to validate.", es: "El backup manual es propenso a errores y difícil de validar." } },
      { icon: "Database", who: { en: "Teams protecting EVS volumes and CCE nodes", es: "Equipos que protegen volúmenes EVS y nodos CCE" }, pain: { en: "No systematic recovery testing or validation.", es: "Sin testing o validación sistemática de recuperación." } },
    ],
    painPoints: [
      { en: "Manual CBR backup configuration is slow and inconsistent across resources.", es: "La configuración manual de CBR es lenta e inconsistente entre recursos." },
      { en: "Restore validation is often skipped, leading to surprises during actual recovery.", es: "La validación de restore se omite, causando sorpresas durante recuperación real." },
      { en: "No AI-guided discovery of unprotected resources.", es: "Sin descubrimiento guiado por IA de recursos desprotegidos." },
    ],
    solutionApproach: [
      { en: "AI discovers all ECS instances, EVS volumes, and CCE nodes — identifies which lack CBR protection.", es: "La IA descubre todas las instancias ECS, volúmenes EVS y nodos CCE — identifica cuáles carecen de protección CBR.",
      referenceLinks: [{ label: "CBR — Cloud Backup and Recovery", url: "https://www.huaweicloud.com/intl/en-us/product/cbr.html" }],},
      { en: "AI generates hcloud CLI commands to create backup policies, execute backups, and validate restore points.", es: "La IA genera comandos hcloud CLI para crear políticas de backup, ejecutar backups y validar puntos de restore." },
      { en: "AI performs test restores to a new resource and validates data integrity before approving the backup.", es: "La IA realiza restores de prueba a un recurso nuevo y valida integridad de datos antes de aprobar el backup." },
    ],
    recommendedServices: ["CBR", "ECS", "EVS", "CCE", "VPC"],
    demoSkillLinks: [
      link("CBR Backup Restore", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/cbr-backup-restore"),
    ],
    migrationMainExample: {
      title: { en: "AI-Assisted CBR Backup & Restore", es: "Backup & Restore CBR Asistido por IA" },
      description: { en: "Complete toolkit for CBR backup discovery, configuration, execution, validation, and restore using hcloud CLI.", es: "Toolkit completo para descubrimiento, configuración, ejecución, validación y restore de backups CBR usando hcloud CLI." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/cbr-backup-restore",
    },
    migrationRelatedTools: [
      {
        title: { en: "CBR Backup Restore Skill", es: "Skill de CBR Backup Restore" },
        description: { en: "AI-guided CBR backup and restore for ECS, EVS, and CCE nodes using hcloud CLI. Includes discovery, policy creation, backup execution, validation, and cross-region restore.", es: "Backup y restore CBR guiado por IA para ECS, EVS y nodos CCE usando hcloud CLI. Incluye descubrimiento, creación de políticas, ejecución, validación y restore cross-region." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/cbr-backup-restore",
      },
    ],
    quickIntegration: {
      prerequisites: [
        { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
        { en: "hcloud CLI configured with credentials.", es: "hcloud CLI configurado con credenciales." },
        { en: "ECS instances, EVS volumes, or CCE nodes to protect.", es: "Instancias ECS, volúmenes EVS o nodos CCE a proteger." },
      ],
      steps: [
        { en: "Discover: AI finds all resources and identifies unprotected ones.", es: "Descubrir: La IA encuentra todos los recursos e identifica los desprotegidos." },
        { en: "Configure: AI creates CBR backup policies and vaults.", es: "Configurar: La IA crea políticas de backup CBR y vaults." },
        { en: "Execute: AI runs backups and monitors completion.", es: "Ejecutar: La IA ejecuta backups y monitorea completitud." },
        { en: "Validate: AI performs test restore and verifies data integrity.", es: "Validar: La IA realiza restore de prueba y verifica integridad de datos." },
      ],
      configuration: [
        { en: "CBR vault and backup policy name.", es: "Nombre de vault y política de backup CBR." },
        { en: "Backup type (full/incremental) and schedule.", es: "Tipo de backup (full/incremental) y schedule." },
      ],
    },
    salesTalkTrack: [
      { en: "How does AI discover unprotected resources?", es: "¿Cómo descubre la IA recursos desprotegidos?" },
      { en: "Can AI validate restores without impacting production?", es: "¿Puede la IA validar restores sin impactar producción?" },
    ],
    expectedOutcomes: [
      { en: "AI discovers all unprotected resources in minutes. 100% coverage with automated policies.", es: "La IA descubre todos los recursos desprotegidos en minutos. 100% cobertura con políticas automatizadas." },
      { en: "AI validates restores automatically. Zero surprises during actual recovery.", es: "La IA valida restores automáticamente. Cero sorpresas durante recuperación real." },
    ],
    heroImage: "/assets/huawei/ai-skills/ai-data-stream.jpg",
    presentationUrl: "/presentations/cbr-backup-restore.pdf",
  },

  {
    id: "sdrs-cross-region-dr",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Cloud Foundation", es: "Cloud Foundation" },
    title: {
      en: "SDRS Cross-Region DR",
      es: "SDRS DR Cross-Region",
    },
    oneLiner: {
      en: "Establish cross-region disaster recovery with SDRS: protection setup, DR drill, and failover/failback.",
      es: "Establezca disaster recovery cross-region con SDRS: setup de protección, drill de DR y failover/failback.",
    },
    targetCustomers: [
      { icon: "Shield", who: { en: "Organizations requiring cross-region DR for ECS workloads", es: "Organizaciones que requieren DR cross-region para workloads ECS" }, pain: { en: "Manual DR setup is complex and untested.", es: "Setup manual de DR es complejo y sin testear." } },
      { icon: "Server", who: { en: "Teams needing automated failover and failback", es: "Equipos que necesitan failover y failback automatizado" }, pain: { en: "Failover procedures are documented but never practiced.", es: "Procedimientos de failover están documentados pero nunca practicados." } },
    ],
    painPoints: [
      { en: "SDRS has no CLI or MCP — all operations are manual via console.", es: "SDRS no tiene CLI ni MCP — todas las operaciones son manuales via consola." },
      { en: "Cross-region replication setup requires careful network and disk configuration.", es: "Setup de replicación cross-region requiere configuración cuidadosa de red y discos." },
      { en: "DR drills are rare, leaving teams unprepared for actual failover.", es: "Drills de DR son raros, dejando equipos sin preparación para failover real." },
    ],
    solutionApproach: [
      { en: "Phase 1 — Protection Setup: AI guides SDRS protection group creation, replication pair setup, and network configuration across regions.", es: "Fase 1 — Setup de Protección: La IA guía la creación de protection groups SDRS, setup de replication pairs y configuración de red cross-region.",
      referenceLinks: [{ label: "SDRS — Storage Disaster Recovery Service", url: "https://www.huaweicloud.com/intl/en-us/product/sdrs.html" }],},
      { en: "Phase 2 — DR Drill: AI orchestrates a non-disruptive DR drill to validate replication status and recovery time objectives.", es: "Fase 2 — DR Drill: La IA orquesta un drill de DR no-disruptivo para validar status de replicación y objetivos de tiempo de recuperación." },
      { en: "Phase 3 — Failover/Failback: AI guides the failover process to the DR region and subsequent failback when primary is restored.", es: "Fase 3 — Failover/Failback: La IA guía el proceso de failover a la región DR y el failback subsiguiente cuando el primario se restaura." },
    ],
    recommendedServices: ["SDRS", "ECS", "EVS", "VPC", "EIP"],
    demoSkillLinks: [
      link("SDRS Cross-Region DR", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/sdrs-cross-region-dr"),
    ],
    migrationMainExample: {
      title: { en: "AI-Assisted SDRS Cross-Region DR", es: "DR Cross-Region SDRS Asistido por IA" },
      description: { en: "Three-skill toolkit for SDRS cross-region DR: protection setup, DR drill, and failover/failback with AI-guided console operations.", es: "Toolkit de 3 skills para DR cross-region SDRS: setup de protección, drill de DR y failover/failback con operaciones de consola guiadas por IA." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/sdrs-cross-region-dr",
    },
    migrationRelatedTools: [
      {
        title: { en: "SDRS Protection Setup", es: "Setup de Protección SDRS" },
        description: { en: "AI-guided SDRS protection group creation, replication pair setup, and network configuration for cross-region DR.", es: "Creación de protection groups SDRS, setup de replication pairs y configuración de red guiado por IA para DR cross-region." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/sdrs-cross-region-dr/huawei-sdrs-protection-setup",
      },
      {
        title: { en: "SDRS DR Drill", es: "DR Drill SDRS" },
        description: { en: "AI-orchestrated non-disruptive DR drill to validate replication status and recovery objectives.", es: "Drill de DR no-disruptivo orquestado por IA para validar status de replicación y objetivos de recuperación." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/sdrs-cross-region-dr/huawei-sdrs-dr-drill",
      },
      {
        title: { en: "SDRS Failover/Failback", es: "SDRS Failover/Failback" },
        description: { en: "AI-guided failover to DR region and failback to primary with full validation.", es: "Failover guiado por IA a región DR y failback a primario con validación completa." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/sdrs-cross-region-dr/huawei-sdrs-failover-failback",
      },
    ],
    quickIntegration: {
      prerequisites: [
        { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
        { en: "ECS instances with EVS disks in production region.", es: "Instancias ECS con discos EVS en región de producción." },
        { en: "DR region VPC and network configured.", es: "VPC y red de región DR configurados." },
      ],
      steps: [
        { en: "Protect: AI guides SDRS protection group and replication pair setup.", es: "Proteger: La IA guía setup de protection group y replication pairs SDRS." },
        { en: "Drill: AI orchestrates a DR drill to validate recovery.", es: "Drill: La IA orquesta un drill de DR para validar recuperación." },
        { en: "Failover: AI guides failover to DR region when needed.", es: "Failover: La IA guía failover a región DR cuando sea necesario." },
        { en: "Failback: AI guides failback to primary after resolution.", es: "Failback: La IA guía failback a primario tras resolución." },
      ],
      configuration: [
        { en: "Primary and DR region selection.", es: "Selección de región primaria y DR." },
        { en: "Protection group name and replication mode.", es: "Nombre de protection group y modo de replicación." },
      ],
    },
    salesTalkTrack: [
      { en: "How does AI handle SDRS without CLI or MCP?", es: "¿Cómo maneja la IA SDRS sin CLI ni MCP?" },
      { en: "Can AI automate DR drills without disruption?", es: "¿Puede la IA automatizar drills de DR sin disrupción?" },
    ],
    expectedOutcomes: [
      { en: "AI guides complete SDRS setup in hours vs days. Validated DR with documented RTO/RPO.", es: "La IA guía setup completo de SDRS en horas vs días. DR validado con RTO/RPO documentado." },
      { en: "AI-orchestrated drills ensure teams are prepared. Zero failed failovers.", es: "Drills orquestados por IA aseguran equipos preparados. Cero failovers fallidos." },
    ],
    heroImage: "/assets/huawei/ai-skills/ai-data-stream.jpg",
    presentationUrl: "/presentations/sdrs-cross-region-dr.pdf",
  },

  {
    id: "dws-cluster-deployment",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Big Data", es: "Big Data" },
    title: {
      en: "DWS Cluster Deployment",
      es: "Despliegue de Cluster DWS",
    },
    oneLiner: {
      en: "Deploy and validate Huawei Cloud DWS data warehouse clusters with AI-guided hcloud CLI orchestration.",
      es: "Despliegue y validación de clusters DWS en Huawei Cloud con orquestación hcloud CLI guiada por IA.",
    },
    targetCustomers: [
      { icon: "Database", who: { en: "Data teams needing a managed data warehouse", es: "Equipos de datos que necesitan un data warehouse gestionado" }, pain: { en: "Manual DWS setup is slow and sizing is guesswork.", es: "Setup manual de DWS es lento y el sizing es adivinanza." } },
      { icon: "BarChart3", who: { en: "Organizations migrating from Teradata or Snowflake", es: "Organizaciones que migran desde Teradata o Snowflake" }, pain: { en: "Need PostgreSQL-compatible warehouse with validation.", es: "Necesitan warehouse compatible con PostgreSQL y validación." } },
    ],
    painPoints: [
      { en: "DWS cluster sizing requires deep expertise — too many node flavors and configuration options.", es: "Sizing de cluster DWS requiere expertise profundo — demasiados flavors de nodo y opciones de configuración." },
      { en: "Connectivity validation (private network, JDBC) is often incomplete.", es: "Validación de conectividad (red privada, JDBC) es frecuentemente incompleta." },
      { en: "No AI-guided discovery of optimal cluster topology for specific workloads.", es: "Sin descubrimiento guiado por IA de topología óptima para workloads específicos." },
    ],
    solutionApproach: [
      { en: "AI analyzes workload requirements and recommends DWS cluster topology, node flavors, and cluster type.", es: "La IA analiza requisitos de workload y recomienda topología de cluster DWS, flavors de nodo y tipo de cluster.",
      referenceLinks: [{ label: "DWS — Data Warehouse Service", url: "https://www.huaweicloud.com/intl/en-us/product/dws.html" }],},
      { en: "AI generates hcloud CLI commands to provision the DWS cluster with correct security and network settings.", es: "La IA genera comandos hcloud CLI para provisionar el cluster DWS con settings correctos de seguridad y red." },
      { en: "AI validates cluster health, JDBC connectivity, and query execution with test workloads.", es: "La IA valida salud del cluster, conectividad JDBC y ejecución de queries con workloads de prueba." },
    ],
    recommendedServices: ["DWS", "VPC", "EIP", "OBS"],
    demoSkillLinks: [
      link("DWS Cluster Deployment", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/dws-cluster-deployment"),
    ],
    migrationMainExample: {
      title: { en: "AI-Guided DWS Deployment", es: "Despliegue de DWS Guiado por IA" },
      description: { en: "Skills and tools for deploying DWS data warehouse clusters with hcloud CLI orchestration and validation.", es: "Skills y herramientas para desplegar clusters de data warehouse DWS con orquestación hcloud CLI y validación." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/dws-cluster-deployment",
    },
    migrationRelatedTools: [
      {
        title: { en: "DWS Cluster Deployment Skill", es: "Skill de Despliegue de Cluster DWS" },
        description: { en: "AI-guided DWS cluster deployment using hcloud CLI. Includes sizing, provisioning, connectivity validation, and query testing.", es: "Despliegue de cluster DWS guiado por IA usando hcloud CLI. Incluye sizing, provisionamiento, validación de conectividad y testing de queries." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/dws-cluster-deployment",
      },
    ],
    quickIntegration: {
      prerequisites: [
        { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
        { en: "hcloud CLI configured with credentials.", es: "hcloud CLI configurado con credenciales." },
        { en: "Target VPC and subnet for DWS cluster.", es: "VPC y subnet objetivo para cluster DWS." },
      ],
      steps: [
        { en: "Discover: AI analyzes workload and recommends cluster topology.", es: "Descubrir: La IA analiza workload y recomienda topología de cluster." },
        { en: "Plan: AI prepares DWS cluster configuration with sized nodes.", es: "Planificar: La IA prepara configuración de cluster DWS con nodos dimensionados." },
        { en: "Execute: AI provisions the DWS cluster via hcloud CLI.", es: "Ejecutar: La IA provisiona el cluster DWS via hcloud CLI." },
        { en: "Validate: AI checks cluster health, JDBC connectivity, and query execution.", es: "Validar: La IA verifica salud del cluster, conectividad JDBC y ejecución de queries." },
      ],
      configuration: [
        { en: "DWS cluster type and node flavors.", es: "Tipo de cluster DWS y flavors de nodo." },
        { en: "Number of nodes and storage configuration.", es: "Número de nodos y configuración de storage." },
      ],
    },
    salesTalkTrack: [
      { en: "How does AI size DWS clusters for specific workloads?", es: "¿Cómo dimensiona la IA clusters DWS para workloads específicos?" },
      { en: "Can AI validate JDBC connectivity automatically?", es: "¿Puede la IA validar conectividad JDBC automáticamente?" },
    ],
    expectedOutcomes: [
      { en: "AI sizes DWS clusters and recommends topology in minutes. 50% faster provisioning.", es: "La IA dimensiona clusters DWS y recomienda topología en minutos. 50% provisionamiento más rápido." },
      { en: "AI validates connectivity and query execution. Over 95% succeed on first deployment.", es: "La IA valida conectividad y ejecución de queries. Más de 95% exito en primer despliegue." },
    ],
    heroImage: "/assets/huawei/ai-skills/ai-data-stream.jpg",
    presentationUrl: "/presentations/dws-cluster-deployment.pdf",
  },

  {
    id: "postgresql-ecs-to-rds-drs",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Database", es: "Database" },
    title: {
      en: "PostgreSQL ECS to RDS Migration",
      es: "Migración PostgreSQL ECS a RDS",
    },
    oneLiner: {
      en: "Migrate self-managed PostgreSQL on ECS to Huawei Cloud RDS using DRS Full+Incremental across regions. The target instance is created for you.",
      es: "Migre PostgreSQL autogestionado en ECS a Huawei Cloud RDS usando DRS Full+Incremental entre regiones. La instancia destino es creada por usted.",
    },
    targetCustomers: [
      { icon: "Database", who: { en: "Teams running PostgreSQL on ECS needing managed RDS", es: "Equipos con PostgreSQL en ECS que necesitan RDS gestionado" }, pain: { en: "Self-managed PostgreSQL means patching, backups, and no HA.", es: "PostgreSQL autogestionado implica parches, backups y sin HA." } },
      { icon: "Server", who: { en: "Organizations migrating databases across regions", es: "Organizaciones que migran bases de datos entre regiones" }, pain: { en: "Cross-region migration requires careful network and DRS configuration.", es: "Migración cross-region requiere configuración cuidadosa de red y DRS." } },
    ],
    painPoints: [
      { en: "Cross-region DRS requires public EIP with /32 CIDR restrictions — complex network setup.", es: "DRS cross-region requiere EIP público con restricciones /32 CIDR — setup de red complejo." },
      { en: "DRS Full+Incremental configuration has many parameters that are easy to misconfigure.", es: "Configuración DRS Full+Incremental tiene muchos parámetros fáciles de mal configurar." },
      { en: "Data consistency validation before cutover is manual and error-prone.", es: "Validación de consistencia de datos antes del cutover es manual y propensa a errores." },
    ],
    solutionApproach: [
      { en: "AI configures source ECS EIP and target RDS security group with /32 CIDR restrictions for cross-region DRS.", es: "La IA configura EIP del ECS origen y security group del RDS destino con restricciones /32 CIDR para DRS cross-region.",
      referenceLinks: [{ label: "DRS — Data Replication Service", url: "https://www.huaweicloud.com/intl/en-us/product/drs.html" }, { label: "RDS for PostgreSQL", url: "https://www.huaweicloud.com/intl/en-us/product/rds.html" }],},
      { en: "AI creates and monitors DRS Full+Incremental job, tracking progress and alerting on anomalies.", es: "La IA crea y monitorea el job DRS Full+Incremental, trackeando progreso y alertando sobre anomalías." },
      { en: "AI validates data consistency between source and target, then guides cutover with minimal downtime.", es: "La IA valida consistencia de datos entre origen y destino, luego guía el cutover con mínimo downtime." },
    ],
    recommendedServices: ["DRS", "RDS", "ECS", "EIP", "VPC", "Terraform"],
    demoSkillLinks: [
      link("PostgreSQL ECS to RDS DRS", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Relational-Database-Migration/postgresql-ecs-to-rds-drs"),
    ],
    migrationMainExample: {
      title: { en: "AI-Assisted PostgreSQL ECS to RDS Migration", es: "Migración PostgreSQL ECS a RDS Asistida por IA" },
      description: { en: "Complete toolkit for migrating PostgreSQL from ECS to RDS using DRS Full+Incremental across regions with AI-guided network and job configuration.", es: "Toolkit completo para migrar PostgreSQL de ECS a RDS usando DRS Full+Incremental entre regiones con configuración de red y job guiada por IA." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Relational-Database-Migration/postgresql-ecs-to-rds-drs",
    },
    migrationRelatedTools: [
      {
        title: { en: "PostgreSQL ECS to RDS DRS Skill", es: "Skill de PostgreSQL ECS a RDS DRS" },
        description: { en: "AI-guided cross-region migration from PostgreSQL on ECS to RDS using DRS Full+Incremental. Includes network setup, DRS job creation, monitoring, validation, and cutover.", es: "Migración cross-region guiada por IA de PostgreSQL en ECS a RDS usando DRS Full+Incremental. Incluye setup de red, creación de job DRS, monitoreo, validación y cutover." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Relational-Database-Migration/postgresql-ecs-to-rds-drs",
      },
    ],
    quickIntegration: {
      prerequisites: [
        { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
        { en: "PostgreSQL running on ECS in source region.", es: "PostgreSQL ejecutándose en ECS en región origen." },
        { en: "Target region selected. The RDS instance is created by the skill — it does not need to exist beforehand.", es: "Región destino seleccionada. La instancia RDS la crea el skill — no necesita existir de antemano." },
        { en: "Source PostgreSQL configured for logical replication (wal_level = logical) with a replication user. The skill verifies this and tells you what to change if not.", es: "PostgreSQL origen configurado para replicación lógica (wal_level = logical) con usuario de replicación. El skill lo verifica e indica qué cambiar si no." },
        { en: "Two MCP servers connected to your AI tool: hcloud and terraform.", es: "Dos servidores MCP conectados a su herramienta de IA: hcloud y terraform." },
        { en: "Huawei Cloud Access Key and Secret Key, used by Terraform.", es: "Access Key y Secret Key de Huawei Cloud, usados por Terraform." },
        { en: "SSH access to the source ECS. A few commands must be run by you — the skill never connects to your database.", es: "Acceso SSH al ECS origen. Algunos comandos debe ejecutarlos usted — el skill nunca se conecta a su base de datos." },
      ],
      steps: [
        { en: "Check: AI verifies your source database meets the DRS requirements and records a row-count baseline.", es: "Verificar: La IA comprueba que su base de datos origen cumple los requisitos DRS y registra una línea base de conteo de filas." },
        { en: "Provision: AI creates the target RDS instance and its network with Terraform, after showing you the plan.", es: "Aprovisionar: La IA crea la instancia RDS destino y su red con Terraform, tras mostrarle el plan." },
        { en: "Connect: AI creates the DRS task and opens temporary access between the two databases.", es: "Conectar: La IA crea la tarea DRS y abre acceso temporal entre las dos bases de datos." },
        { en: "Migrate: AI runs the DRS Full+Incremental job and monitors progress.", es: "Migrar: La IA ejecuta el job DRS Full+Incremental y monitorea el progreso." },
        { en: "Validate: AI compares structure and row counts against the baseline, and verifies that live changes replicate.", es: "Validar: La IA compara estructura y conteo de filas contra la línea base, y verifica que cambios en vivo repliquen." },
        { en: "Cutover and clean up: AI guides the switch with minimal downtime, then removes the temporary access.", es: "Cutover y limpieza: La IA guía el switch con mínimo downtime, luego elimina el acceso temporal." },
      ],
      configuration: [
        { en: "Source ECS EIP and target RDS security group CIDR.", es: "EIP del ECS origen y CIDR del security group del RDS destino." },
        { en: "DRS job type (Full+Incremental) and migration objects.", es: "Tipo de job DRS (Full+Incremental) y objetos de migración." },
      ],
      requiredMcpServers: {
        intro: {
          en: "This scenario needs two MCP servers connected to your AI coding tool. Both are general-purpose and are configured once per environment.",
          es: "Este escenario necesita dos servidores MCP conectados a su herramienta de IA. Ambos son de propósito general y se configuran una vez por entorno.",
        },
        servers: [
          { mcp: "hcloud", purpose: { en: "Huawei Cloud operations: resource discovery, DRS task lifecycle, security group rules. Based on KooCLI.", es: "Operaciones de Huawei Cloud: descubrimiento de recursos, ciclo de vida de tareas DRS, reglas de security group. Basado en KooCLI." } },
          { mcp: "terraform", purpose: { en: "Provisioning the target VPC, subnet, security group and RDS instance.", es: "Aprovisionamiento del VPC destino, subred, security group e instancia RDS." } },
        ],
        note: {
          en: "No scenario-specific MCP is required, and no browser automation is involved.",
          es: "No se requiere ningún MCP específico del escenario, ni se usa automatización de navegador.",
        },
      },
      startingPrompt: {
        intro: {
          en: "Copy this prompt, replace the values in angle brackets, and send it to your AI tool. Everything else is asked along the way.",
          es: "Copie este prompt, reemplace los valores entre corchetes angulares, y envíelo a su herramienta de IA. Todo lo demás se pregunta durante el proceso.",
        },
        code: `/postgresql-ecs-to-rds-drs\nUsing this skill and the "hcloud" and "terraform" MCPs, migrate my\nPostgreSQL database. Go step by step and stop at every approval gate.\n\nSOURCE (already exists - do not modify it, do not connect via SSH):\n- Region: <source region>\n- Public IP (EIP): <source EIP>\n- Port: <port, usually 5432>\n- Database name: <database to migrate>\n- Replication user: <user with REPLICATION>\n- Security group ID: <source security group ID>\n\nTARGET (does not exist yet - create it):\n- Region: <target region, must differ from the source>\n\nStart at Step 0 and wait for my confirmation at each gate. When you\nneed me to run something on the source, give me the complete command\nand wait.`,
      },
      whatSkillAsks: {
        en: "An administrator password for the new RDS instance. The format rules are explained before the request.\nYour Access Key and Secret Key, if not already set in the environment. Terraform authenticates separately from the CLI.\nThe replication user password, when the DRS task is created.\nTo run three or four commands yourself on the source server. The skill never connects to your database; it gives you each command with an explanation of what it does.",
        es: "Una contraseña de administrador para la nueva instancia RDS. Las reglas de formato se explican antes de la solicitud.\nSu Access Key y Secret Key, si no están en el entorno. Terraform se autentica separadamente del CLI.\nLa contraseña del usuario de replicación, cuando se crea la tarea DRS.\nEjecutar tres o cuatro comandos usted mismo en el servidor origen. El skill nunca se conecta a su base de datos; le da cada comando con una explicación de lo que hace.",
      },
      whatScenarioDoesNotDo: {
        en: "It does not modify your source database. Changes it needs are given to you as commands to run yourself.\nIt does not shut anything down. Cutover redirects your application; your original database keeps running as your rollback path.\nIt does not use VPN or VPC peering. Connectivity is over the public network, with the database port restricted to a single IP address and closed again at the end.\nIt does not migrate across PostgreSQL major versions. Source and target must be the same major version.",
        es: "No modifica su base de datos origen. Los cambios necesarios se le entregan como comandos para ejecutarlos usted mismo.\nNo apaga nada. El cutover redirige su aplicación; su base de datos original sigue corriendo como ruta de rollback.\nNo usa VPN ni VPC peering. La conectividad es por red pública, con el puerto de base de datos restringido a una sola dirección IP y cerrado nuevamente al final.\nNo migra entre versiones maje de PostgreSQL. Origen y destino deben ser la misma versión maje.",
      },
    },
    salesTalkTrack: [
      { en: "How does AI handle cross-region DRS network configuration?", es: "¿Cómo maneja la IA configuración de red DRS cross-region?" },
      { en: "Can AI validate data consistency automatically before cutover?", es: "¿Puede la IA validar consistencia de datos automáticamente antes del cutover?" },
    ],
    expectedOutcomes: [
      { en: "AI configures cross-region DRS in minutes vs hours. Zero network misconfigurations.", es: "La IA configura DRS cross-region en minutos vs horas. Cero misconfiguraciones de red." },
      { en: "AI validates data consistency automatically. Over 99% successful cutovers.", es: "La IA valida consistencia de datos automáticamente. Más de 99% cutovers exitosos." },
    ],
    heroImage: "/assets/huawei/ai-skills/ai-data-stream.jpg",
    presentationUrl: "/presentations/postgresql-ecs-to-rds-drs.pdf",
  },

  {
    id: "snowflake-to-dataarts",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Big Data", es: "Big Data" },
    title: {
      en: "Snowflake to DataArts Migration",
      es: "Migración Snowflake a DataArts",
    },
    oneLiner: {
      en: "Migrate data pipelines and SQL workloads from Snowflake to Huawei Cloud DataArts (Factory + DLI).",
      es: "Migre pipelines de datos y workloads SQL de Snowflake a Huawei Cloud DataArts (Factory + DLI).",
    },
    targetCustomers: [
      { icon: "Database", who: { en: "Teams migrating from Snowflake to Huawei Cloud", es: "Equipos que migran desde Snowflake a Huawei Cloud" }, pain: { en: "SQL dialects and UDFs don't map directly to DataArts DLI.", es: "Dialectos SQL y UDFs no mapean directamente a DataArts DLI." } },
      { icon: "BarChart3", who: { en: "Organizations needing managed data pipeline orchestration", es: "Organizaciones que necesitan orquestación gestionada de pipelines" }, pain: { en: "Snowflake task graphs and schedules need translation.", es: "Task graphs y schedules de Snowflake necesitan traducción." } },
    ],
    painPoints: [
      { en: "Snowflake SQL dialect differs from DataArts DLI SQL — manual translation is error-prone.", es: "Dialecto SQL de Snowflake difiere de DataArts DLI SQL — traducción manual es propensa a errores." },
      { en: "Task graphs and DAGs in Snowflake have no direct equivalent in DataArts Factory.", es: "Task graphs y DAGs en Snowflake no tienen equivalente directo en DataArts Factory." },
      { en: "Schema and UDF migration requires manual extraction and adaptation.", es: "Migración de schema y UDFs requiere extracción y adaptación manual." },
    ],
    solutionApproach: [
      { en: "AI extracts SQL tasks, task graphs, and schemas from Snowflake (manual extraction with AI guidance).", es: "La IA extrae SQL tasks, task graphs y schemas de Snowflake (extracción manual con guía de IA).",
      referenceLinks: [{ label: "DataArts Studio", url: "https://www.huaweicloud.com/intl/en-us/product/dayu.html" }],},
      { en: "AI adapts Snowflake SQL to DataArts DLI SQL, handling dialect differences and UDF translation.", es: "La IA adapta SQL de Snowflake a DataArts DLI SQL, manejando diferencias de dialecto y traducción de UDFs." },
      { en: "AI creates DataArts Factory jobs and DLI tables, then validates query results against expected outputs.", es: "La IA crea jobs de DataArts Factory y tablas DLI, luego valida resultados de queries contra outputs esperados." },
    ],
    recommendedServices: ["DataArts", "DLI", "OBS", "VPC"],
    demoSkillLinks: [
      link("Snowflake to DataArts", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/snowflake-to-dataarts"),
    ],
    migrationMainExample: {
      title: { en: "AI-Assisted Snowflake to DataArts Migration", es: "Migración Snowflake a DataArts Asistida por IA" },
      description: { en: "Toolkit for migrating data pipelines and SQL workloads from Snowflake to Huawei Cloud DataArts with AI-guided SQL adaptation and pipeline conversion.", es: "Toolkit para migrar pipelines de datos y workloads SQL de Snowflake a Huawei Cloud DataArts con adaptación SQL y conversión de pipelines guiada por IA." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/snowflake-to-dataarts",
    },
    migrationRelatedTools: [
      {
        title: { en: "Snowflake to DataArts Migration Skill", es: "Skill de Migración Snowflake a DataArts" },
        description: { en: "AI-guided migration from Snowflake to DataArts (Factory + DLI). Includes SQL adaptation, task graph conversion, schema mapping, and result validation.", es: "Migración guiada por IA de Snowflake a DataArts (Factory + DLI). Incluye adaptación SQL, conversión de task graphs, mapeo de schema y validación de resultados." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/snowflake-to-dataarts",
      },
    ],
    quickIntegration: {
      prerequisites: [
        { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
        { en: "Snowflake account with SQL tasks and schemas accessible.", es: "Cuenta de Snowflake con SQL tasks y schemas accesibles." },
        { en: "Huawei Cloud DataArts Studio provisioned.", es: "Huawei Cloud DataArts Studio provisionado." },
      ],
      steps: [
        { en: "Extract: AI guides extraction of SQL tasks, task graphs, and schemas from Snowflake.", es: "Extraer: La IA guía extracción de SQL tasks, task graphs y schemas de Snowflake." },
        { en: "Adapt: AI translates Snowflake SQL to DataArts DLI SQL and converts UDFs.", es: "Adaptar: La IA traduce SQL de Snowflake a DataArts DLI SQL y convierte UDFs." },
        { en: "Deploy: AI creates DataArts Factory jobs and DLI tables.", es: "Desplegar: La IA crea jobs de DataArts Factory y tablas DLI." },
        { en: "Validate: AI compares query results against expected outputs.", es: "Validar: La IA compara resultados de queries contra outputs esperados." },
      ],
      configuration: [
        { en: "Snowflake source connection details.", es: "Detalles de conexión de Snowflake origen." },
        { en: "DataArts DLI database and Factory workspace.", es: "Base de datos DataArts DLI y workspace de Factory." },
      ],
    },
    salesTalkTrack: [
      { en: "How does AI handle Snowflake SQL dialect differences?", es: "¿Cómo maneja la IA diferencias de dialecto SQL de Snowflake?" },
      { en: "Can AI convert Snowflake task graphs to DataArts Factory jobs?", es: "¿Puede la IA convertir task graphs de Snowflake a jobs de DataArts Factory?" },
    ],
    expectedOutcomes: [
      { en: "AI adapts SQL and converts pipelines in hours vs weeks. 70% faster migration.", es: "La IA adapta SQL y convierte pipelines en horas vs semanas. 70% migración más rápida." },
      { en: "AI validates results against expected outputs. Over 95% query parity achieved.", es: "La IA valida resultados contra outputs esperados. Más de 95% paridad de queries lograda." },
    ],
    heroImage: "/assets/huawei/ai-skills/ai-data-stream.jpg",
    presentationUrl: "/presentations/snowflake-to-dataarts.pdf",
  },

  {
    id: "database-usage-operations",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Database", es: "Database" },
    title: {
      en: "AI-Guided Database Operations",
      es: "Operaciones de Base de Datos Guiadas por IA",
    },
    oneLiner: {
      en: "Use existing Huawei Cloud database instances (RDS, DDS, GeminiDB, TaurusDB, GaussDB) via KooCLI: find, connect, and bind EIP.",
      es: "Use instancias de base de datos existentes en Huawei Cloud (RDS, DDS, GeminiDB, TaurusDB, GaussDB) via KooCLI: encontrar, conectar y bind EIP.",
    },
    targetCustomers: [
      { icon: "Database", who: { en: "Teams managing existing database instances", es: "Equipos que gestionan instancias de base de datos existentes" }, pain: { en: "No CLI guidance for finding, connecting, or exposing databases.", es: "Sin guía CLI para encontrar, conectar o exponer bases de datos." } },
      { icon: "Server", who: { en: "Organizations needing public access to databases via EIP", es: "Organizaciones que necesitan acceso público a bases de datos via EIP" }, pain: { en: "EIP binding varies per service — RDS, DDS, GeminiDB, TaurusDB, GaussDB each have different mechanisms.", es: "EIP binding varía por servicio — RDS, DDS, GeminiDB, TaurusDB, GaussDB cada uno tiene mecanismos diferentes." } },
    ],
    painPoints: [
      { en: "Each database service has its own hcloud service name and EIP-bind mechanism — no generic Database CLI.", es: "Cada servicio de base de datos tiene su propio nombre de servicio hcloud y mecanismo de EIP-bind — no hay CLI genérico de Database." },
      { en: "RDS has no dedicated EIP-bind operation — requires generic EIP-to-port association via VPC.", es: "RDS no tiene operación dedicada de EIP-bind — requiere asociación genérica EIP-to-port via VPC." },
      { en: "GaussDB EIP-bind capability is unconfirmed at public-cloud CLI level — critical gap.", es: "La capacidad de EIP-bind para GaussDB no está confirmada a nivel CLI en nube pública — gap crítico." },
    ],
    solutionApproach: [
      { en: "AI discovers database instances across RDS, DDS, GeminiDB, TaurusDB, and GaussDB using hcloud CLI.", es: "La IA descubre instancias de base de datos en RDS, DDS, GeminiDB, TaurusDB y GaussDB usando hcloud CLI.",
      referenceLinks: [{ label: "RDS — Relational Database Service", url: "https://www.huaweicloud.com/intl/en-us/product/rds.html" }, { label: "DDS — Document Database Service", url: "https://www.huaweicloud.com/intl/en-us/product/dds.html" }, { label: "GeminiDB", url: "https://www.huaweicloud.com/intl/en-us/product/geminidb.html" }],},
      { en: "AI surfaces connection details (private IP, port, database client) for the target instance.", es: "La IA muestra detalles de conexión (IP privada, puerto, cliente de base de datos) para la instancia objetivo." },
      { en: "AI guides EIP deployment and binding using each service's confirmed mechanism — with explicit approval gates for every bind action.", es: "La IA guía el despliegue de EIP y binding usando el mecanismo confirmado de cada servicio — con gates de aprobación explícitos para cada acción de bind." },
    ],
    recommendedServices: ["RDS", "DDS", "GeminiDB", "GaussDB", "EIP", "VPC"],
    demoSkillLinks: [
      link("Database Usage Operations", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/database-usage-operations"),
    ],
    migrationMainExample: {
      title: { en: "AI-Guided Database Operations with KooCLI", es: "Operaciones de Base de Datos Guiadas por IA con KooCLI" },
      description: { en: "Skills for using existing Huawei Cloud database instances via hcloud CLI: find, connect, and bind EIP across RDS, DDS, GeminiDB, TaurusDB, and GaussDB.", es: "Skills para usar instancias de base de datos existentes en Huawei Cloud via hcloud CLI: encontrar, conectar y bind EIP en RDS, DDS, GeminiDB, TaurusDB y GaussDB." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/database-usage-operations",
    },
    migrationRelatedTools: [
      {
        title: { en: "Database Usage Operations Skill", es: "Skill de Operaciones de Base de Datos" },
        description: { en: "AI-guided database operations via hcloud CLI for RDS, DDS, GeminiDB, TaurusDB, and GaussDB. Includes instance discovery, connection details, EIP deployment and binding with per-service mechanisms, and verification.", es: "Operaciones de base de datos guiadas por IA via hcloud CLI para RDS, DDS, GeminiDB, TaurusDB y GaussDB. Incluye descubrimiento de instancias, detalles de conexión, despliegue y binding de EIP con mecanismos por servicio, y verificación." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/database-usage-operations",
      },
    ],
    presentationUrl: "/presentations/database-usage-operations.pdf",
    quickIntegration: {
      prerequisites: [
        { en: "AI coding tool installed.", es: "Herramienta de AI Coding instalada.", linkParts: [{ label: "OpenCode", url: "#/solutions/ai-coding-opencode?from=migration" }, { label: "Claude Code", url: "#/solutions/ai-coding-claude-code?from=migration" }, { label: "Hermes", url: "#/solutions/ai-coding-hermes?from=migration" }] },
        { en: "hcloud CLI (KooCLI) installed and configured with AK/SK.", es: "hcloud CLI (KooCLI) instalado y configurado con AK/SK." },
        { en: "An already-existing, running database instance.", es: "Una instancia de base de datos ya existente y en ejecución." },
      ],
      steps: [
        { en: "Find: AI discovers the target instance across RDS, DDS, GeminiDB, TaurusDB, or GaussDB.", es: "Encontrar: La IA descubre la instancia objetivo en RDS, DDS, GeminiDB, TaurusDB o GaussDB." },
        { en: "Connect: AI surfaces connection details — private IP, port, and database client.", es: "Conectar: La IA muestra detalles de conexión — IP privada, puerto y cliente de base de datos." },
        { en: "Bind EIP: AI deploys/reuses an EIP and binds it using the service's confirmed mechanism.", es: "Bind EIP: La IA despliega/reusa un EIP y lo bind usando el mecanismo confirmado del servicio." },
        { en: "Verify: AI confirms the EIP appears against the instance and reminds about security group rules.", es: "Validar: La IA confirma que el EIP aparece en la instancia y recuerda sobre reglas de security group." },
      ],
      configuration: [
        { en: "Target service (rds, dds, geminidb, taurusdb, gaussdb).", es: "Servicio objetivo (rds, dds, geminidb, taurusdb, gaussdb)." },
        { en: "Instance name or ID, and action (find, connect, bind-eip).", es: "Nombre o ID de instancia, y acción (find, connect, bind-eip)." },
      ],
    },
    salesTalkTrack: [
      { en: "How does AI handle different EIP-bind mechanisms per database service?", es: "¿Cómo maneja la IA diferentes mecanismos de EIP-bind por servicio de base de datos?" },
      { en: "What happens when GaussDB EIP-bind is not available via CLI?", es: "¿Qué pasa cuando EIP-bind de GaussDB no está disponible via CLI?" },
    ],
    expectedOutcomes: [
      { en: "AI discovers and connects to any database instance in minutes. Zero manual CLI lookups.", es: "La IA descubre y se conecta a cualquier instancia en minutos. Cero lookups manuales de CLI." },
      { en: "AI guides EIP binding with per-service mechanisms. Over 95% successful binds on first attempt.", es: "La IA guía EIP binding con mecanismos por servicio. Más de 95% binds exitosos al primer intento." },
    ],
    heroImage: "/assets/huawei/ai-skills/ai-data-stream.jpg",
  },

  {
    id: "docker-compose-to-cci",
    entryId: "on-prem-to-cloud",
    categoryLabel: { en: "Containers", es: "Containers" },
    title: {
      en: "Docker Compose to CCI Migration",
      es: "Migración Docker Compose a CCI",
    },
    oneLiner: {
      en: "Migrate local Docker Compose applications to Huawei Cloud CCI serverless containers using the v2 API — no cluster management required.",
      es: "Migre aplicaciones locales Docker Compose a contenedores serverless CCI de Huawei Cloud usando la v2 API — sin gestión de clusters.",
    },
    targetCustomers: [
      { icon: "Container", who: { en: "Teams running Docker Compose on local servers or VMs", es: "Equipos ejecutando Docker Compose en servidores locales o VMs" }, pain: { en: "Servers run 24/7 even when apps are idle, wasting compute budget.", es: "Servidores corren 24/7 incluso cuando apps están idle, desperdiciando presupuesto de compute." } },
      { icon: "Terminal", who: { en: "DevOps engineers wanting serverless containers", es: "Ingenieros DevOps que quieren contenedores serverless" }, pain: { en: "Don't want to manage Kubernetes clusters but need container orchestration.", es: "No quieren gestionar clusters Kubernetes pero necesitan orquestación de contenedores." } },
      { icon: "Network", who: { en: "Cost-conscious teams", es: "Equipos conscientes del costo" }, pain: { en: "Pay-per-second billing vs always-on VMs for intermittent workloads.", es: "Facturación por-segundo vs VMs always-on para cargas intermitentes." } },
    ],
    painPoints: [
      { en: "Docker Compose requires a always-on host server — no scale-to-zero, no per-second billing.", es: "Docker Compose requiere un servidor host always-on — sin scale-to-zero, sin facturación por-segundo." },
      { en: "CCI v1beta1 API strips securityGroups from Network spec, causing 400 errors. Must use v2 API (cci/v2 + yangtse/v2).", es: "La API v1beta1 de CCI elimina securityGroups del spec de Network, causando errores 400. Debe usar la v2 API (cci/v2 + yangtse/v2)." },
      { en: "CCI requires resource limits on all containers (minimum 250m CPU, 512Mi memory) — Compose files often omit these.", es: "CCI requiere resource limits en todos los contenedores (mínimo 250m CPU, 512Mi memory) — archivos Compose suelen omitirlos." },
      { en: "CCI does not support ClusterIP or NodePort services — only LoadBalancer with ELB ID annotation.", es: "CCI no soporta servicios ClusterIP o NodePort — solo LoadBalancer con anotación ELB ID." },
    ],
    solutionApproach: [
      { en: "Phase 1 — Parse: Read docker-compose.yaml and extract all services, ports, volumes, environment, and dependencies.", es: "Fase 1 — Parse: Lea docker-compose.yaml y extraiga todos los servicios, puertos, volúmenes, variables de entorno y dependencias.",
      referenceLinks: [{ label: "CCI — Cloud Container Instance", url: "https://www.huaweicloud.com/intl/en-us/product/cci.html" }],},
      { en: "Phase 2 — Setup CCI: Create namespace via cci/v2 API, network via yangtse/v2 with securityGroups, NAT gateway + EIP for internet access.", es: "Fase 2 — Setup CCI: Cree namespace via API cci/v2, network via yangtse/v2 con securityGroups, NAT gateway + EIP para acceso a internet.",
      replaces: { en: "Equivalent to AWS Fargate and Azure Container Instances — CCI provides serverless containers with per-second billing and scale-to-zero.", es: "Equivalente a AWS Fargate y Azure Container Instances — CCI provee contenedores serverless con facturación por-segundo y scale-to-zero." },},
      { en: "Phase 3 — Translate: Map each Compose service to a CCI Deployment with mandatory resource limits. Map volumes to SFS Turbo PVCs, env vars to ConfigMaps, secrets to Secrets.", es: "Fase 3 — Translate: Mapee cada servicio Compose a un Deployment CCI con resource limits obligatorios. Mapee volúmenes a PVCs SFS Turbo, env vars a ConfigMaps, secrets a Secrets." },
      { en: "Phase 4 — Deploy: Create all resources via cci/v2 API with AK/SK signing. Wait for pods to reach Running state.", es: "Fase 4 — Deploy: Cree todos los recursos via API cci/v2 con signing AK/SK. Espere a que los pods alcancen estado Running." },
      { en: "Phase 5 — Validate: Verify pod status, podIPs, and deployment readiness. Clean up source Docker Compose if desired.", es: "Fase 5 — Validate: Verifique status de pods, podIPs y readiness del deployment. Limpie Docker Compose origen si lo desea." },
    ],
    recommendedServices: ["CCI", "SWR", "VPC", "NAT Gateway", "EIP", "SFS Turbo"],
    demoSkillLinks: [
      link("CCI CLI Deploy", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/cci/cci-cli-deploy"),
      link("Docker Compose to CCI", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/cci/docker-compose-to-cci"),
    ],
    migrationMainExample: {
      title: { en: "Docker Compose to CCI Migration Toolkit", es: "Toolkit de Migración Docker Compose a CCI" },
      description: { en: "Complete toolkit for translating Docker Compose applications to Huawei Cloud CCI serverless containers. Includes Python translation script, CCI v2 API helper, and worked examples.", es: "Toolkit completo para traducir aplicaciones Docker Compose a contenedores serverless CCI de Huawei Cloud. Incluye script de traducción Python, helper de API CCI v2 y ejemplos." },
      githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/cci/docker-compose-to-cci",
    },
    migrationRelatedTools: [
      {
        title: { en: "CCI CLI Deploy", es: "Despliegue CCI desde CLI" },
        description: { en: "Deploy CCI workloads entirely from the terminal using the v2 API with AK/SK signing. Covers namespace, network, NAT gateway, deployments, and services.", es: "Despliegue cargas CCI completamente desde la terminal usando la v2 API con signing AK/SK. Cubre namespace, network, NAT gateway, deployments y services." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/cci/cci-cli-deploy",
      },
    ],
    migrationExamples: [
      {
        title: { en: "cci-cli-deploy", es: "cci-cli-deploy" },
        description: { en: "Deploy CCI serverless containers from the CLI using v2 API with AK/SK signing. No console access needed.", es: "Despliegue contenedores serverless CCI desde la CLI usando v2 API con signing AK/SK. Sin acceso a consola." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/cci/cci-cli-deploy",
      },
      {
        title: { en: "docker-compose-to-cci", es: "docker-compose-to-cci" },
        description: { en: "Translate Docker Compose services to CCI v2 API Deployments with automated Python script. Handles images, volumes, env vars, and health checks.", es: "Traduzca servicios Docker Compose a Deployments CCI v2 API con script Python automatizado. Maneja imágenes, volúmenes, env vars y health checks." },
        githubUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/cci/docker-compose-to-cci",
      },
    ],
    quickIntegration: {
      prerequisites: [
        { en: "Huawei Cloud AK/SK with CCI permissions.", es: "AK/SK de Huawei Cloud con permisos CCI." },
        { en: "CCI agency authorized for the target region (one-time console step).", es: "Agencia CCI autorizada para la región destino (paso de consola único)." },
        { en: "Docker Compose file (v2 or v3 format).", es: "Archivo Docker Compose (formato v2 o v3)." },
        { en: "Python 3.6+ with PyYAML installed.", es: "Python 3.6+ con PyYAML instalado." },
      ],
      steps: [
        { en: "Parse docker-compose.yaml to extract services, ports, volumes, and environment.", es: "Parse docker-compose.yaml para extraer servicios, puertos, volúmenes y variables de entorno." },
        { en: "Create CCI namespace via cci/v2 API and network via yangtse/v2 with securityGroups.", es: "Cree namespace CCI via API cci/v2 y network via yangtse/v2 con securityGroups." },
        { en: "Create NAT gateway + EIP for internet access (if using Docker Hub images).", es: "Cree NAT gateway + EIP para acceso a internet (si usa imágenes Docker Hub)." },
        { en: "Run compose-to-cci.py migrate to deploy all services to CCI.", es: "Ejecute compose-to-cci.py migrate para desplegar todos los servicios a CCI." },
        { en: "Verify all pods are Running and validate pod IPs.", es: "Verifique que todos los pods estén Running y valide pod IPs." },
      ],
      configuration: [
        { en: "All resources use pay-per-use billing (CCI pods per-second, NAT per-hour, EIP per-bandwidth).", es: "Todos los recursos usan facturación pay-per-use (pods CCI por-segundo, NAT por-hora, EIP por-bandwidth)." },
        { en: "CCI requires resource limits: minimum 250m CPU, 512Mi memory per container.", es: "CCI requiere resource limits: mínimo 250m CPU, 512Mi memory por contenedor." },
        { en: "Only SFS Turbo available for persistent storage (no EVS, no OBS).", es: "Solo SFS Turbo disponible para storage persistente (no EVS, no OBS)." },
      ],
      apiAccess: [
        { en: "CCI v2 API: https://cci.<region>.myhuaweicloud.com/apis/cci/v2/", es: "CCI v2 API: https://cci.<region>.myhuaweicloud.com/apis/cci/v2/" },
        { en: "Network API: https://cci.<region>.myhuaweicloud.com/apis/yangtse/v2/", es: "Network API: https://cci.<region>.myhuaweicloud.com/apis/yangtse/v2/" },
      ],
    },
    salesTalkTrack: [
      { en: "How does this compare to AWS Fargate?", es: "¿Cómo se compara con AWS Fargate?" },
      { en: "CCI offers per-second billing and scale-to-zero, similar to Fargate. But CCI uses the Kubernetes API (v2), so existing K8s tooling works.", es: "CCI ofrece facturación por-segundo y scale-to-zero, similar a Fargate. Pero CCI usa la API Kubernetes (v2), por lo que tooling K8s existente funciona." },
      { en: "What about persistent storage?", es: "¿Qué hay de storage persistente?" },
      { en: "CCI supports SFS Turbo (Scalable File Service) with ReadWriteMany access. No block storage (EVS) or object storage (OBS) as PVCs.", es: "CCI soporta SFS Turbo (Scalable File Service) con acceso ReadWriteMany. No block storage (EVS) ni object storage (OBS) como PVCs." },
      { en: "Can I use my existing Docker Compose files?", es: "¿Puedo usar mis archivos Docker Compose existentes?" },
      { en: "Yes — the compose-to-cci.py script parses standard docker-compose.yaml and translates all services to CCI Deployments automatically.", es: "Sí — el script compose-to-cci.py parsea docker-compose.yaml estándar y traduce todos los servicios a Deployments CCI automáticamente." },
    ],
    expectedOutcomes: [
      { en: "Docker Compose applications running as serverless containers on CCI with per-second billing.", es: "Aplicaciones Docker Compose corriendo como contenedores serverless en CCI con facturación por-segundo." },
      { en: "Zero infrastructure management — no cluster nodes to maintain or scale.", es: "Cero gestión de infraestructura — sin nodos de cluster que mantener o escalar." },
      { en: "Automatic scale-to-zero when idle, eliminating idle compute costs.", es: "Scale-to-zero automático cuando idle, eliminando costos de compute idle." },
      { en: "Complete migration in under 5 minutes for typical 2-3 service applications.", es: "Migración completa en menos de 5 minutos para aplicaciones típicas de 2-3 servicios." },
    ],
    heroImage: "/assets/huawei/migration-scenarios/container-migration.jpg",
    presentationUrl: "/presentations/container-migration.pdf?v=2",
  },

];

const migrationScenarioHeroImages: Partial<Record<string, string>> = {
  "cloud-to-cloud-migration": "/assets/huawei/migration-scenarios/cloud-to-cloud-migration.jpg",
  "database-migration": "/assets/huawei/migration-scenarios/database-migration.jpg",
  "container-migration": "/assets/huawei/migration-scenarios/container-migration.jpg",
  "workspace-migration": "/assets/huawei/migration-scenarios/workspace-migration.jpg",
  "ai-coding": "/assets/huawei/migration-scenarios/ai-coding.jpg",
  "cloud-foundation": "/assets/huawei/migration-scenarios/cloud-foundation.jpg",
  "other-scenarios": "/assets/huawei/migration-scenarios/other-scenarios.jpg",
  "object-migration": "/assets/huawei/migration-scenarios/object-migration.jpg",
  "virtual-machine-migration": "/assets/huawei/migration-scenarios/virtual-machine-migration.jpg",
  "vm-migration": "/assets/huawei/migration-scenarios/virtual-machine-migration.jpg",
  "vmware-migration": "/assets/huawei/migration-scenarios/virtual-machine-migration.jpg",
  "codearts-deployment": "/assets/huawei/ai-skills/ai-data-stream.jpg",
  "mrs-deployment": "/assets/huawei/ai-skills/ai-data-stream.jpg",
  "cbr-backup-restore": "/assets/huawei/ai-skills/ai-data-stream.jpg",
  "sdrs-cross-region-dr": "/assets/huawei/ai-skills/ai-data-stream.jpg",
  "dws-cluster-deployment": "/assets/huawei/ai-skills/ai-data-stream.jpg",
  "postgresql-ecs-to-rds-drs": "/assets/huawei/ai-skills/ai-data-stream.jpg",
  "snowflake-to-dataarts": "/assets/huawei/ai-skills/ai-data-stream.jpg",
  "database-usage-operations": "/assets/huawei/ai-skills/ai-data-stream.jpg",
  "vpn-connectivity": "/assets/huawei/migration-scenarios/cloud-foundation.jpg",
};

solutionScenarios.forEach((scenario) => {
  const heroImage = migrationScenarioHeroImages[scenario.id];
  if (heroImage) {
    scenario.heroImage = heroImage;
  }
});

export const solutionScenarioMap = Object.fromEntries(
  solutionScenarios.map((scenario) => [scenario.id, scenario]),
) as Record<string, SolutionScenario>;
