import type { Lang } from "./i18n";
import {
  aiSkillCategoryProfiles,
  aiSkillDefinitions,
  type AiSkillCategoryProfile,
} from "./aiSkills";

export type SolutionEntryId = "ai-maas" | "cloud-to-cloud" | "on-prem-to-cloud" | "enterprise";

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
  prerequisites: LocalizedPair[];
  steps: LocalizedPair[];
  configuration: LocalizedPair[];
  apiAccess: LocalizedPair[];
};

export type SolutionScenario = {
  id: string;
  entryId: SolutionEntryId;
  categoryId?: string;
  categoryLabel?: LocalizedPair;
  title: LocalizedPair;
  oneLiner: LocalizedPair;
  targetCustomers: LocalizedPair[];
  painPoints: LocalizedPair[];
  solutionApproach: LocalizedPair[];
  recommendedServices: string[];
  demoSkillLinks: SkillLink[];
  quickIntegration: QuickIntegration;
  salesTalkTrack: LocalizedPair[];
  expectedOutcomes: LocalizedPair[];
  heroImage: string;
  externalUrls?: { en: string; es: string };
  detailVariant?: "default" | "healthcare";
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
    id: "cloud-to-cloud",
    title: {
      en: "Get More Value from Cloud Workloads",
      es: "Migración cloud-to-cloud",
    },
    summary: {
      en: "Improve cloud applications, databases, and analytics with better efficiency, performance, and local support.",
      es: "Mueva cargas y plataformas de datos desde otras nubes públicas hacia Huawei Cloud con una ruta más clara de costos y landing zone.",
    },
    tags: ["Cost Control", "Performance", "Operations"],
    heroImage: "/assets/huawei/ecommerce.jpg",
    scenarioIds: ["cloud-database-migration", "bi-data-platform-migration"],
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
    scenarioIds: ["sap-erp-on-cloud", "backup-dr-security", "workspace-vmware-migration"],
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
    .filter((entry) => entry.id !== "cloud-to-cloud")
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
    id: "cloud-database-migration",
    entryId: "cloud-to-cloud",
    title: {
      en: "Cloud and Database Migration",
      es: "Migración cloud y de bases de datos",
    },
    oneLiner: {
      en: "Move servers, applications, and databases from other clouds into Huawei Cloud with a migration wave and validation model built for SMB programs.",
      es: "Mueva servidores, aplicaciones y bases de datos desde otras nubes hacia Huawei Cloud con un modelo de oleadas y validación diseñado para programas SMB.",
    },
    targetCustomers: [
      { en: "SMBs already running on another public cloud", es: "Pymes que ya operan en otra nube pública" },
      { en: "SaaS providers looking for cost or region alternatives", es: "Proveedores SaaS que buscan alternativas de costo o región" },
      { en: "Teams consolidating cloud estates after fast growth", es: "Equipos que consolidan estates cloud tras un crecimiento rápido" },
    ],
    painPoints: [
      { en: "Cloud spend is rising but migration priorities are unclear.", es: "El gasto cloud sube pero las prioridades de migración no están claras." },
      { en: "Dependencies between applications and databases are not well documented.", es: "Las dependencias entre aplicaciones y bases de datos no están bien documentadas." },
      { en: "Teams need a migration narrative that includes landing zone, validation, and rollback.", es: "Los equipos necesitan una narrativa de migración que incluya landing zone, validación y rollback." },
    ],
    solutionApproach: [
      { en: "Start from workload and dependency discovery, then group migration waves by business priority.", es: "Comience con descubrimiento de cargas y dependencias, y luego agrupe oleadas por prioridad de negocio." },
      { en: "Use a cloud landing zone with security and operations controls before cutover.", es: "Use una landing zone cloud con controles de seguridad y operaciones antes del cutover." },
      { en: "Validate application behavior, database consistency, and rollback criteria in each wave.", es: "Valide comportamiento de aplicaciones, consistencia de base de datos y criterios de rollback en cada oleada." },
    ],
    recommendedServices: ["ECS", "EVS", "VPC", "DDS", "DRS", "CBR"],
    demoSkillLinks: [
      link("Datacenter Migration into Cloud", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/Application-Modernization/Datacenter-Migration-into-Cloud"),
      link("Database Migration", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/Application-Modernization/Database-Migration"),
    ],
    quickIntegration: {
      prerequisites: [
        { en: "An inventory of in-scope workloads and a nominated migration owner.", es: "Un inventario de cargas en alcance y un responsable de migración." },
        { en: "A target region and baseline networking and identity model.", es: "Una región objetivo y un modelo base de red e identidad." },
      ],
      steps: [
        { en: "Assess current workloads, map dependencies, and split pilot and production waves.", es: "Evalúe las cargas actuales, mapee dependencias y separe oleadas piloto y productivas." },
        { en: "Build the target landing zone and prepare data migration or replication paths.", es: "Construya la landing zone objetivo y prepare rutas de migración o replicación de datos." },
        { en: "Run cutover rehearsals and post-migration validation before the final switch.", es: "Ejecute ensayos de cutover y validación post-migración antes del cambio final." },
      ],
      configuration: [
        { en: "Document target sizing, security groups, backup, and rollback conditions per wave.", es: "Documente sizing objetivo, security groups, backup y condiciones de rollback por oleada." },
        { en: "Separate application migration assumptions from database migration assumptions.", es: "Separe los supuestos de migración de aplicaciones de los supuestos de bases de datos." },
      ],
      apiAccess: [
        { en: "Use migration tooling and replication APIs behind a project-level runbook.", es: "Use herramientas de migración y APIs de replicación detrás de un runbook por proyecto." },
        { en: "Track cutover readiness, validation status, and post-wave issues centrally.", es: "Monitoree centralmente readiness de cutover, estado de validación e incidencias post-oleada." },
      ],
    },
    salesTalkTrack: [
      { en: "Is the main driver cost, regional service quality, or simplification of your cloud estate?", es: "¿El driver principal es costo, calidad de servicio regional o simplificación del estate cloud?" },
      { en: "Which workloads can move first with low dependency risk?", es: "¿Qué cargas pueden moverse primero con bajo riesgo de dependencia?" },
    ],
    expectedOutcomes: [
      { en: "A wave-based migration plan with clearer commercial and technical boundaries.", es: "Un plan de migración por oleadas con límites comerciales y técnicos más claros." },
      { en: "Lower migration uncertainty for both workloads and databases.", es: "Menor incertidumbre de migración tanto para cargas como para bases de datos." },
      { en: "A stronger path from public-cloud migration to platform standardization.", es: "Una ruta más sólida desde la migración cloud hacia la estandarización de plataforma." },
    ],
    heroImage: "/assets/huawei/ecommerce.jpg",
  },
  {
    id: "bi-data-platform-migration",
    entryId: "cloud-to-cloud",
    title: {
      en: "BI and Data Platform Migration",
      es: "Migración de BI y plataforma de datos",
    },
    oneLiner: {
      en: "Move reporting, data warehouse, and big data workloads to Huawei Cloud data services with a practical migration and governance path.",
      es: "Mueva reporting, data warehouse y cargas de big data a servicios de datos de Huawei Cloud con una ruta práctica de migración y gobierno.",
    },
    targetCustomers: [
      { en: "Organizations modernizing reporting or analytics estates", es: "Organizaciones que modernizan entornos de reporting o analítica" },
      { en: "Teams moving from Databricks, Teradata, or legacy big data stacks", es: "Equipos que migran desde Databricks, Teradata o stacks legacy de big data" },
      { en: "SMBs that need BI growth without rebuilding the entire data team", es: "Pymes que necesitan crecer en BI sin reconstruir todo el equipo de datos" },
    ],
    painPoints: [
      { en: "Analytics platforms are fragmented across tools and cloud providers.", es: "Las plataformas analíticas están fragmentadas entre herramientas y nubes." },
      { en: "Reporting consistency and data governance are hard to maintain.", es: "La consistencia del reporting y el gobierno de datos son difíciles de mantener." },
      { en: "Migration plans often ignore business users and focus only on technical pipelines.", es: "Los planes de migración suelen ignorar a los usuarios de negocio y enfocarse solo en pipelines técnicos." },
    ],
    solutionApproach: [
      { en: "Prioritize the data products, reports, and pipelines that matter most to the business.", es: "Priorice los productos de datos, reportes y pipelines que más importan al negocio." },
      { en: "Rebuild or migrate the target landing patterns on OBS, DWS, MRS, or related services.", es: "Reconstruya o migre los patrones objetivo sobre OBS, DWS, MRS o servicios relacionados." },
      { en: "Validate parity with business stakeholders before shutting down the previous platform.", es: "Valide la paridad con stakeholders de negocio antes de apagar la plataforma anterior." },
    ],
    recommendedServices: ["OBS", "DWS", "MRS", "DLI", "DataArts", "GaussDB"],
    demoSkillLinks: [
      link("Big Data Skill Library", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/Big-Data"),
      link("Data Warehouse Migration", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/Big-Data"),
      link("Databricks to Huawei Cloud", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/Big-Data"),
    ],
    quickIntegration: {
      prerequisites: [
        { en: "A list of critical reports, pipelines, and platform dependencies.", es: "Una lista de reportes críticos, pipelines y dependencias de plataforma." },
        { en: "Business owners who can validate migrated outputs.", es: "Responsables de negocio que puedan validar salidas migradas." },
      ],
      steps: [
        { en: "Catalog source datasets, pipeline schedules, and downstream consumers.", es: "Catalogue datasets origen, agendas de pipelines y consumidores downstream." },
        { en: "Build the target data landing and transformation path on Huawei Cloud.", es: "Construya la ruta objetivo de landing y transformación de datos en Huawei Cloud." },
        { en: "Validate report parity, refresh cycles, and governance controls before cutover.", es: "Valide paridad de reportes, ciclos de refresco y controles de gobierno antes del cutover." },
      ],
      configuration: [
        { en: "Define storage classes, workload separation, and governance ownership up front.", es: "Defina desde el inicio clases de almacenamiento, separación de cargas y ownership de gobierno." },
        { en: "Document data quality checks and sign-off criteria per migrated domain.", es: "Documente checks de calidad y criterios de aprobación por dominio migrado." },
      ],
      apiAccess: [
        { en: "Integrate BI tools, pipelines, and data access controls through standard service endpoints.", es: "Integre herramientas BI, pipelines y controles de acceso mediante endpoints estándar del servicio." },
        { en: "Track refresh reliability, query latency, and user validation status after each migration wave.", es: "Monitoree confiabilidad de refresco, latencia de consulta y validación de usuarios tras cada oleada." },
      ],
    },
    salesTalkTrack: [
      { en: "Which reports or dashboards would create immediate value if they were more stable or cheaper to run?", es: "¿Qué reportes o dashboards crearían valor inmediato si fueran más estables o más baratos de operar?" },
      { en: "Do business users trust the current analytics platform enough to support migration sign-off?", es: "¿Los usuarios de negocio confían lo suficiente en la plataforma analítica actual como para apoyar el sign-off de migración?" },
    ],
    expectedOutcomes: [
      { en: "A migration path that includes both data engineering and business validation.", es: "Una ruta de migración que incluye ingeniería de datos y validación de negocio." },
      { en: "More consistent reporting and governance on Huawei Cloud data services.", es: "Reporting y gobierno más consistentes sobre servicios de datos Huawei Cloud." },
      { en: "A stronger base for analytics assistants and AI-ready data use cases.", es: "Una base más sólida para asistentes analíticos y casos de datos listos para IA." },
    ],
    heroImage: "/assets/huawei/official-cache/nn2-a987783a7f08256c.jpg",
  },
  {
    id: "sap-erp-on-cloud",
    entryId: "on-prem-to-cloud",
    title: {
      en: "SAP and ERP on Cloud",
      es: "SAP y ERP en cloud",
    },
    oneLiner: {
      en: "Move SAP or ERP foundations to Huawei Cloud with a focus on availability, backup, capacity planning, and operations readiness.",
      es: "Lleve bases SAP o ERP a Huawei Cloud con foco en disponibilidad, backup, capacity planning y readiness operativo.",
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
    recommendedServices: ["ECS", "EVS", "CBR", "Cloud Eye", "VPC", "OBS"],
    demoSkillLinks: [
      link("SAP on Cloud", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/Application-Modernization/SAP-on-Cloud"),
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
      en: "Backup, Disaster Recovery, and Security Foundation",
      es: "Backup, disaster recovery y base de seguridad",
    },
    oneLiner: {
      en: "Package backup, disaster recovery, and baseline security controls into one practical offer that is easy for SMBs to understand and buy.",
      es: "Empaquete backup, disaster recovery y controles básicos de seguridad en una oferta práctica que las pymes puedan entender y comprar fácilmente.",
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
    recommendedServices: ["CBR", "OBS", "HSS", "WAF", "Cloud Eye", "VPC"],
    demoSkillLinks: [
      link("DR and Backup", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/Cloud-Foundation/DR-and-Backup"),
      link("Security Foundation", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/Cloud-Foundation/Security-Foundation"),
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
    heroImage: "/assets/huawei/official-cache/nn2-a987783a7f08256c.jpg",
  },
  {
    id: "workspace-vmware-migration",
    entryId: "on-prem-to-cloud",
    title: {
      en: "Workspace and VMware Migration",
      es: "Workspace y migración VMware",
    },
    oneLiner: {
      en: "Replace traditional desktop delivery or migrate VMware-based workloads to a managed cloud model with better visibility and control.",
      es: "Sustituya la entrega tradicional de escritorios o migre cargas basadas en VMware hacia un modelo cloud gestionado con mejor visibilidad y control.",
    },
    targetCustomers: [
      { en: "Organizations running VMware-heavy virtual environments", es: "Organizaciones con entornos virtuales fuertemente basados en VMware" },
      { en: "Teams supporting remote or distributed workers", es: "Equipos que soportan trabajadores remotos o distribuidos" },
      { en: "Customers planning datacenter footprint reduction", es: "Clientes que planifican reducir su huella de datacenter" },
    ],
    painPoints: [
      { en: "Desktop and VM operations are difficult to scale or secure consistently.", es: "Las operaciones de escritorios y VM son difíciles de escalar o asegurar de forma consistente." },
      { en: "VMware estates often lack a clear migration sequence and compatibility narrative.", es: "Los estates VMware suelen carecer de una secuencia clara de migración y narrativa de compatibilidad." },
      { en: "Remote access requirements are growing faster than infrastructure teams can respond.", es: "Los requisitos de acceso remoto crecen más rápido de lo que las infraestructuras pueden responder." },
    ],
    solutionApproach: [
      { en: "Assess VMware inventory, user groups, and application dependencies before migration or workspace rollout.", es: "Evalúe inventario VMware, grupos de usuarios y dependencias de aplicaciones antes de la migración o despliegue Workspace." },
      { en: "Use a managed desktop or migration path that reduces operational variance.", es: "Use una ruta de escritorio gestionado o migración que reduzca la variabilidad operativa." },
      { en: "Pilot with one user group or workload wave, then expand with cutover and support procedures.", es: "Haga piloto con un grupo de usuarios u oleada de cargas, y luego expanda con procedimientos de cutover y soporte." },
    ],
    recommendedServices: ["Workspace", "ECS", "EVS", "VPC", "HSS", "CBR"],
    demoSkillLinks: [
      link("Workspace and Virtual Desktop", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/Application-Modernization/Workspace-and-Virtual-Desktop"),
      link("VMware Migration", "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/Application-Modernization/VMware-Migration"),
    ],
    quickIntegration: {
      prerequisites: [
        { en: "A VMware or user inventory, target access policy, and pilot group.", es: "Un inventario VMware o de usuarios, política objetivo de acceso y grupo piloto." },
        { en: "Known application compatibility and connectivity requirements.", es: "Requisitos conocidos de compatibilidad de aplicaciones y conectividad." },
      ],
      steps: [
        { en: "Assess desktop or VM groups and map the first migration or virtual desktop wave.", es: "Evalúe grupos de escritorios o VM y mapee la primera oleada de migración o escritorio virtual." },
        { en: "Prepare secure access, image standards, and operations support model.", es: "Prepare acceso seguro, estándares de imagen y modelo de soporte operativo." },
        { en: "Run pilot onboarding and validate user experience before expansion.", es: "Ejecute onboarding piloto y valide experiencia de usuario antes de ampliar." },
      ],
      configuration: [
        { en: "Document identity integration, endpoint posture, and backup responsibilities.", es: "Documente integración de identidad, postura de endpoint y responsabilidades de backup." },
        { en: "Separate user-experience KPIs from infrastructure KPIs for the pilot.", es: "Separe KPI de experiencia de usuario de KPI de infraestructura en el piloto." },
      ],
      apiAccess: [
        { en: "Surface provisioning, session health, and migration progress in one support view.", es: "Exponga aprovisionamiento, salud de sesiones y progreso de migración en una sola vista de soporte." },
        { en: "Track adoption, login success, and support incidents to justify scale-up.", es: "Monitoree adopción, éxito de login e incidencias de soporte para justificar el escalado." },
      ],
    },
    salesTalkTrack: [
      { en: "Is the main need remote productivity, VMware exit, or tighter desktop security?", es: "¿La necesidad principal es productividad remota, salida de VMware o mayor seguridad de escritorios?" },
      { en: "Which user group or VM set can validate the model first with low disruption risk?", es: "¿Qué grupo de usuarios o conjunto de VM puede validar primero el modelo con bajo riesgo de disrupción?" },
    ],
    expectedOutcomes: [
      { en: "A clearer path for VMware or desktop modernization.", es: "Una ruta más clara para la modernización de VMware o escritorios." },
      { en: "Better remote access control and desktop operations visibility.", es: "Mayor control de acceso remoto y visibilidad operativa de escritorios." },
      { en: "A practical on-prem to cloud story that does not depend on a full application rewrite.", es: "Una narrativa práctica de on-prem a cloud que no depende de rehacer todas las aplicaciones." },
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
];

export const solutionScenarioMap = Object.fromEntries(
  solutionScenarios.map((scenario) => [scenario.id, scenario]),
) as Record<string, SolutionScenario>;
