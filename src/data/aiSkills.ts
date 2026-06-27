export type AiSkillCategoryId =
  | "agent-platform"
  | "ai-applications"
  | "ai-coding"
  | "responsible-ai"
  | "host-migration";

export type AiLocalizedText = {
  en: string;
  es: string;
};

export type AiSkillDefinition = {
  id: string;
  categoryId: AiSkillCategoryId;
  title: AiLocalizedText;
  summary: AiLocalizedText;
  focus: AiLocalizedText;
  outcome: AiLocalizedText;
  recommendedServices: string[];
  githubPath: string;
  heroImage: string;
};

export type AiSkillCategoryProfile = {
  id: AiSkillCategoryId;
  label: AiLocalizedText;
  description: AiLocalizedText;
  targetCustomers: AiLocalizedText[];
  painPoints: AiLocalizedText[];
  solutionApproach: AiLocalizedText[];
  prerequisites: AiLocalizedText[];
  steps: AiLocalizedText[];
  configuration: AiLocalizedText[];
  apiAccess: AiLocalizedText[];
  salesTalkTrack: AiLocalizedText[];
  expectedOutcomes: AiLocalizedText[];
};

const githubRoot =
  "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI";

export const aiSkillSourceCommit = "9de0ff622e6c5a965a75b2bb51dbdda7ea6fa8d2";

export const aiSkillCategoryProfiles: AiSkillCategoryProfile[] = [
  {
    id: "agent-platform",
    label: { en: "Agent Platform", es: "Plataforma de agentes" },
    description: {
      en: "Persistent memory, context efficiency, and governed enterprise knowledge for production agents.",
      es: "Memoria persistente, eficiencia de contexto y conocimiento empresarial gobernado para agentes productivos.",
    },
    targetCustomers: [
      { en: "Teams operating enterprise AI agents", es: "Equipos que operan agentes de IA empresariales" },
      { en: "Knowledge-intensive delivery and support organizations", es: "Organizaciones de entrega y soporte intensivas en conocimiento" },
      { en: "Platform teams standardizing reusable agent capabilities", es: "Equipos de plataforma que estandarizan capacidades reutilizables de agentes" },
    ],
    painPoints: [
      { en: "Agents lose context between sessions or repeatedly reload the same knowledge.", es: "Los agentes pierden contexto entre sesiones o recargan repetidamente el mismo conocimiento." },
      { en: "Long prompts increase token cost, latency, and operational uncertainty.", es: "Los prompts extensos aumentan costo de tokens, latencia e incertidumbre operativa." },
      { en: "Memory, privacy, and audit controls are implemented inconsistently.", es: "La memoria, privacidad y auditoría se implementan de forma inconsistente." },
    ],
    solutionApproach: [
      { en: "Separate working, episodic, procedural, and semantic memory into governed tiers.", es: "Separe memoria de trabajo, episódica, procedimental y semántica en capas gobernadas." },
      { en: "Use hybrid retrieval and progressive disclosure to load only relevant context.", es: "Use recuperación híbrida y divulgación progresiva para cargar solo el contexto relevante." },
    ],
    prerequisites: [
      { en: "A defined agent use case, data classification, and retention policy.", es: "Un caso de uso de agente, clasificación de datos y política de retención definidos." },
      { en: "A representative set of sessions, documents, and recall questions.", es: "Un conjunto representativo de sesiones, documentos y preguntas de recuperación." },
    ],
    steps: [
      { en: "Deploy the smallest memory or retrieval pack described by the Skill.", es: "Despliegue el paquete mínimo de memoria o recuperación descrito por el Skill." },
      { en: "Validate recall quality, token cost, latency, and sensitive-data handling.", es: "Valide calidad de recuperación, costo de tokens, latencia y tratamiento de datos sensibles." },
      { en: "Add audit, lifecycle, and access policies before scaling to more agents.", es: "Agregue auditoría, ciclo de vida y políticas de acceso antes de escalar a más agentes." },
    ],
    configuration: [
      { en: "Keep model credentials outside source control and separate environments.", es: "Mantenga credenciales de modelos fuera del código y separe ambientes." },
      { en: "Define memory TTL, deletion, redaction, and retrieval thresholds explicitly.", es: "Defina explícitamente TTL, eliminación, redacción y umbrales de recuperación." },
    ],
    apiAccess: [
      { en: "Expose memory and retrieval through internal APIs or controlled MCP tools.", es: "Exponga memoria y recuperación mediante APIs internas o herramientas MCP controladas." },
      { en: "Capture recall accuracy, context size, latency, and access events.", es: "Registre precisión de recuperación, tamaño de contexto, latencia y eventos de acceso." },
    ],
    salesTalkTrack: [
      { en: "How often do agents repeat discovery or lose approved context between sessions?", es: "¿Con qué frecuencia los agentes repiten descubrimiento o pierden contexto aprobado entre sesiones?" },
      { en: "Which knowledge must remain private, attributable, and removable?", es: "¿Qué conocimiento debe permanecer privado, atribuible y eliminable?" },
    ],
    expectedOutcomes: [
      { en: "Lower token consumption and more consistent agent responses.", es: "Menor consumo de tokens y respuestas de agentes más consistentes." },
      { en: "A reusable memory foundation with privacy and audit controls.", es: "Una base reutilizable de memoria con controles de privacidad y auditoría." },
    ],
  },
  {
    id: "ai-applications",
    label: { en: "AI Applications", es: "Aplicaciones de IA" },
    description: {
      en: "Business applications for knowledge, analytics, documents, and customer operations.",
      es: "Aplicaciones de negocio para conocimiento, analítica, documentos y operaciones de clientes.",
    },
    targetCustomers: [
      { en: "Customer service, operations, legal, and analytics teams", es: "Equipos de servicio, operaciones, legal y analítica" },
      { en: "Organizations with document-heavy or repetitive workflows", es: "Organizaciones con flujos documentales o repetitivos" },
      { en: "Teams seeking a measurable AI proof of concept", es: "Equipos que buscan una prueba de concepto de IA medible" },
    ],
    painPoints: [
      { en: "Business knowledge is fragmented across documents, databases, and specialists.", es: "El conocimiento está fragmentado entre documentos, bases de datos y especialistas." },
      { en: "Manual review and information retrieval slow down customer and internal processes.", es: "La revisión manual y la búsqueda de información ralentizan procesos internos y de clientes." },
      { en: "AI pilots lack clear safeguards, fallback behavior, and success metrics.", es: "Los pilotos de IA carecen de controles, fallback y métricas de éxito claras." },
    ],
    solutionApproach: [
      { en: "Start with a narrow workflow, approved data, and measurable business questions.", es: "Comience con un flujo acotado, datos aprobados y preguntas de negocio medibles." },
      { en: "Combine Huawei Cloud MaaS with retrieval, data, OCR, or application services as required.", es: "Combine Huawei Cloud MaaS con recuperación, datos, OCR o servicios de aplicación según sea necesario." },
    ],
    prerequisites: [
      { en: "An accountable business owner and a bounded pilot workflow.", es: "Un responsable de negocio y un flujo piloto delimitado." },
      { en: "Approved sample data plus quality, privacy, and escalation criteria.", es: "Datos de muestra aprobados y criterios de calidad, privacidad y escalamiento." },
    ],
    steps: [
      { en: "Prepare a controlled dataset and deploy the reference workflow.", es: "Prepare un conjunto de datos controlado y despliegue el flujo de referencia." },
      { en: "Test with real business questions, edge cases, and deterministic fallbacks.", es: "Pruebe con preguntas reales, casos límite y fallbacks determinísticos." },
      { en: "Measure value and operational readiness before expanding scope.", es: "Mida valor y preparación operativa antes de ampliar el alcance." },
    ],
    configuration: [
      { en: "Restrict source systems, schemas, documents, and model permissions.", es: "Restrinja sistemas fuente, esquemas, documentos y permisos del modelo." },
      { en: "Log evidence, model decisions, failures, and human overrides.", es: "Registre evidencia, decisiones del modelo, fallas y correcciones humanas." },
    ],
    apiAccess: [
      { en: "Expose the capability through an internal portal, workflow, or governed API.", es: "Exponga la capacidad mediante portal interno, workflow o API gobernada." },
      { en: "Use read-only access and explicit allowlists for data-oriented pilots.", es: "Use acceso de solo lectura y listas permitidas explícitas para pilotos de datos." },
    ],
    salesTalkTrack: [
      { en: "Which repetitive workflow has clear volume, cost, and quality baselines?", es: "¿Qué flujo repetitivo tiene líneas base claras de volumen, costo y calidad?" },
      { en: "What evidence must the AI show before a user can trust or approve its answer?", es: "¿Qué evidencia debe mostrar la IA antes de que un usuario confíe o apruebe su respuesta?" },
    ],
    expectedOutcomes: [
      { en: "Faster decisions and lower manual workload in the selected process.", es: "Decisiones más rápidas y menor carga manual en el proceso seleccionado." },
      { en: "A governed pilot with evidence for scale, redesign, or stop decisions.", es: "Un piloto gobernado con evidencia para decidir escalar, rediseñar o detener." },
    ],
  },
  {
    id: "ai-coding",
    label: { en: "AI Coding", es: "AI Coding" },
    description: {
      en: "Connect developer tools to Huawei Cloud MaaS with shared routing, search, quality, and operations.",
      es: "Conecte herramientas de desarrollo a Huawei Cloud MaaS con ruteo, búsqueda, calidad y operación compartidos.",
    },
    targetCustomers: [
      { en: "Software engineering and DevOps teams", es: "Equipos de desarrollo de software y DevOps" },
      { en: "Enterprise platform and developer-experience owners", es: "Responsables de plataforma y experiencia del desarrollador" },
      { en: "Organizations standardizing AI coding access", es: "Organizaciones que estandarizan el acceso a AI Coding" },
    ],
    painPoints: [
      { en: "Coding tools require different adapters, endpoints, and compatibility workarounds.", es: "Las herramientas de coding requieren distintos adaptadores, endpoints y ajustes de compatibilidad." },
      { en: "Teams lack centralized model routing, budgets, search, and observability.", es: "Los equipos carecen de ruteo, presupuestos, búsqueda y observabilidad centralizados." },
      { en: "Uncontrolled agent changes create quality and security risk.", es: "Los cambios no controlados de agentes generan riesgos de calidad y seguridad." },
    ],
    solutionApproach: [
      { en: "Use Huawei Cloud MaaS behind a compatible gateway or purpose-built adapter.", es: "Use Huawei Cloud MaaS detrás de un gateway compatible o adaptador específico." },
      { en: "Add code search, memory hygiene, quality gates, and usage visibility around the coding agent.", es: "Agregue búsqueda de código, higiene de memoria, controles de calidad y visibilidad de uso alrededor del agente." },
    ],
    prerequisites: [
      { en: "A MaaS endpoint, approved model, pilot repository, and developer group.", es: "Un endpoint MaaS, modelo aprobado, repositorio piloto y grupo de desarrolladores." },
      { en: "Defined security, cost, source-control, and review boundaries.", es: "Límites definidos de seguridad, costo, control de código y revisión." },
    ],
    steps: [
      { en: "Deploy the Skill adapter or gateway without replacing the existing developer path.", es: "Despliegue el adaptador o gateway del Skill sin reemplazar la ruta actual del desarrollador." },
      { en: "Validate chat, tool calls, file edits, search, and failure recovery.", es: "Valide chat, llamadas de herramientas, edición de archivos, búsqueda y recuperación de fallas." },
      { en: "Introduce team policies, budgets, telemetry, and review gates.", es: "Introduzca políticas de equipo, presupuestos, telemetría y controles de revisión." },
    ],
    configuration: [
      { en: "Use side-by-side commands and isolated configuration for pilots.", es: "Use comandos paralelos y configuración aislada para pilotos." },
      { en: "Store API keys in environment or secret services and redact logs.", es: "Guarde API keys en variables o servicios de secretos y redacte logs." },
    ],
    apiAccess: [
      { en: "Provide one governed OpenAI- or Anthropic-compatible endpoint per team policy.", es: "Proporcione un endpoint compatible con OpenAI o Anthropic según la política del equipo." },
      { en: "Track token usage, latency, errors, tool calls, and model routing.", es: "Monitoree tokens, latencia, errores, llamadas de herramientas y ruteo de modelos." },
    ],
    salesTalkTrack: [
      { en: "Which coding tools and repositories should join the first controlled pilot?", es: "¿Qué herramientas y repositorios deben entrar al primer piloto controlado?" },
      { en: "Do teams need shared model access, code search, or both?", es: "¿Los equipos necesitan acceso compartido a modelos, búsqueda de código o ambos?" },
    ],
    expectedOutcomes: [
      { en: "Faster developer onboarding to Huawei Cloud MaaS.", es: "Incorporación más rápida de desarrolladores a Huawei Cloud MaaS." },
      { en: "Consistent routing, security, cost visibility, and quality controls.", es: "Ruteo, seguridad, visibilidad de costos y controles de calidad consistentes." },
    ],
  },
  {
    id: "responsible-ai",
    label: { en: "Responsible AI & Governance", es: "IA responsable y gobierno" },
    description: {
      en: "Tracing, evaluation, cost, privacy, and operational evidence for MaaS-backed systems.",
      es: "Trazas, evaluación, costo, privacidad y evidencia operativa para sistemas respaldados por MaaS.",
    },
    targetCustomers: [
      { en: "AI platform, security, SRE, and compliance teams", es: "Equipos de plataforma de IA, seguridad, SRE y cumplimiento" },
      { en: "Application owners moving AI pilots into production", es: "Responsables que llevan pilotos de IA a producción" },
      { en: "Organizations requiring auditable model operations", es: "Organizaciones que requieren operaciones de modelos auditables" },
    ],
    painPoints: [
      { en: "AI behavior, latency, errors, and cost are difficult to diagnose end to end.", es: "El comportamiento, latencia, errores y costo de IA son difíciles de diagnosticar de extremo a extremo." },
      { en: "Telemetry may expose prompts, credentials, or sensitive business data.", es: "La telemetría puede exponer prompts, credenciales o datos sensibles." },
      { en: "Teams lack shared evaluation and release evidence.", es: "Los equipos carecen de evidencia compartida de evaluación y liberación." },
    ],
    solutionApproach: [
      { en: "Instrument applications at model, agent, retrieval, and workflow boundaries.", es: "Instrumente aplicaciones en los límites de modelo, agente, recuperación y workflow." },
      { en: "Apply explicit redaction, sampling, retention, and access policies to telemetry.", es: "Aplique políticas explícitas de redacción, muestreo, retención y acceso a la telemetría." },
    ],
    prerequisites: [
      { en: "One representative MaaS application and an approved telemetry destination.", es: "Una aplicación MaaS representativa y un destino de telemetría aprobado." },
      { en: "Privacy classification plus latency, cost, and quality targets.", es: "Clasificación de privacidad y objetivos de latencia, costo y calidad." },
    ],
    steps: [
      { en: "Instrument a non-production workflow and validate trace completeness.", es: "Instrumente un flujo no productivo y valide la integridad de las trazas." },
      { en: "Verify redaction, access, retention, and failure behavior.", es: "Verifique redacción, acceso, retención y comportamiento ante fallas." },
      { en: "Create operational dashboards and evaluation gates before production rollout.", es: "Cree dashboards operativos y controles de evaluación antes del despliegue productivo." },
    ],
    configuration: [
      { en: "Disable prompt or response capture unless explicitly approved.", es: "Desactive captura de prompts o respuestas salvo aprobación explícita." },
      { en: "Separate development and production projects, credentials, and retention.", es: "Separe proyectos, credenciales y retención de desarrollo y producción." },
    ],
    apiAccess: [
      { en: "Export traces through controlled SDK, OTLP, or gateway integrations.", es: "Exporte trazas mediante SDK, OTLP o integraciones de gateway controladas." },
      { en: "Correlate request, model, retrieval, error, latency, and cost signals.", es: "Correlacione señales de solicitud, modelo, recuperación, error, latencia y costo." },
    ],
    salesTalkTrack: [
      { en: "Can the team explain why an AI request failed, slowed down, or became expensive?", es: "¿Puede el equipo explicar por qué una solicitud de IA falló, se ralentizó o encareció?" },
      { en: "Which prompt and user data must never leave the application boundary?", es: "¿Qué datos de prompts y usuarios nunca deben salir del límite de la aplicación?" },
    ],
    expectedOutcomes: [
      { en: "Faster incident diagnosis and clearer AI service-level evidence.", es: "Diagnóstico de incidentes más rápido y evidencia más clara de niveles de servicio de IA." },
      { en: "Safer telemetry with explicit privacy and access controls.", es: "Telemetría más segura con controles explícitos de privacidad y acceso." },
    ],
  },
  {
    id: "host-migration",
    label: { en: "AI-Guided Migration", es: "Migración guiada por IA" },
    description: {
      en: "Repeatable cross-region migration with prechecks, evidence, and controlled fallback paths.",
      es: "Migración repetible entre regiones con prechecks, evidencia y rutas de fallback controladas.",
    },
    targetCustomers: [
      { en: "Cloud operations and migration teams", es: "Equipos de operaciones cloud y migración" },
      { en: "Customers moving ECS or VMware workloads between regions", es: "Clientes que mueven cargas ECS o VMware entre regiones" },
      { en: "Delivery teams requiring repeatable migration evidence", es: "Equipos de entrega que requieren evidencia repetible de migración" },
    ],
    painPoints: [
      { en: "Migration prerequisites and source compatibility are discovered too late.", es: "Los prerequisitos y la compatibilidad de origen se descubren demasiado tarde." },
      { en: "Fallback decisions and cutover evidence are handled manually.", es: "Las decisiones de fallback y la evidencia de cutover se manejan manualmente." },
      { en: "Cross-region execution varies between delivery teams.", es: "La ejecución entre regiones varía entre equipos de entrega." },
    ],
    solutionApproach: [
      { en: "Use deterministic prechecks and SMS-first execution with staged rsync fallback.", es: "Use prechecks determinísticos y ejecución SMS-first con fallback rsync por etapas." },
      { en: "Package configuration, outputs, validation, and troubleshooting evidence.", es: "Empaquete configuración, resultados, validación y evidencia de troubleshooting." },
    ],
    prerequisites: [
      { en: "Approved source and target inventory, network path, and migration window.", es: "Inventario de origen y destino, red y ventana de migración aprobados." },
      { en: "Access to MGC/SMS, Terraform variables, and source-host credentials.", es: "Acceso a MGC/SMS, variables Terraform y credenciales del host origen." },
    ],
    steps: [
      { en: "Run compatibility, capacity, network, and permission prechecks.", es: "Ejecute prechecks de compatibilidad, capacidad, red y permisos." },
      { en: "Start SMS migration or select the documented staged rsync fallback.", es: "Inicie migración SMS o seleccione el fallback rsync documentado por etapas." },
      { en: "Validate incremental sync, cutover, application health, and rollback evidence.", es: "Valide sincronización incremental, cutover, salud de aplicación y evidencia de rollback." },
    ],
    configuration: [
      { en: "Keep secrets outside Terraform state and generated evidence packages.", es: "Mantenga secretos fuera del estado Terraform y paquetes de evidencia." },
      { en: "Pin regions, resource mappings, bandwidth limits, and cutover criteria.", es: "Fije regiones, mapeos de recursos, límites de ancho de banda y criterios de cutover." },
    ],
    apiAccess: [
      { en: "Use MGC/SMS and cloud APIs through least-privilege credentials.", es: "Use APIs MGC/SMS y cloud mediante credenciales de mínimo privilegio." },
      { en: "Record task IDs, statuses, timestamps, validation results, and exceptions.", es: "Registre IDs de tareas, estados, tiempos, validaciones y excepciones." },
    ],
    salesTalkTrack: [
      { en: "Which workloads, dependencies, and downtime constraints define the migration wave?", es: "¿Qué cargas, dependencias y restricciones de downtime definen la ola de migración?" },
      { en: "What fallback is approved if SMS cannot support the source host?", es: "¿Qué fallback está aprobado si SMS no soporta el host origen?" },
    ],
    expectedOutcomes: [
      { en: "Repeatable migration execution with explicit fallback and rollback paths.", es: "Ejecución de migración repetible con rutas explícitas de fallback y rollback." },
      { en: "Consistent technical evidence for delivery review and handover.", es: "Evidencia técnica consistente para revisión y transferencia." },
    ],
  },
];

const imageRoot = "/assets/huawei/ai-skills";
const aiImages = {
  digitalTunnel: `${imageRoot}/ai-digital-tunnel.jpg`,
  glassOrbit: `${imageRoot}/ai-glass-orbit.jpg`,
  blueprintCity: `${imageRoot}/ai-blueprint-city.jpg`,
  dataStream: `${imageRoot}/ai-data-stream.jpg`,
  digitalHorizon: `${imageRoot}/ai-digital-horizon.jpg`,
  mountain: `${imageRoot}/ai-mountain.jpg`,
  connectedCity: `${imageRoot}/ai-connected-city.jpg`,
  blueGreenOrbs: `${imageRoot}/ai-blue-green-orbs.jpg`,
  mintOrbs: `${imageRoot}/ai-mint-orbs.jpg`,
  yellowOrbs: `${imageRoot}/ai-yellow-orbs.jpg`,
  cityNetwork: `${imageRoot}/ai-city-network.jpg`,
  businessGovernance: `${imageRoot}/ai-business-governance.jpg`,
  fiveGCity: `${imageRoot}/ai-5g-city.jpg`,
} as const;

export const aiSkillDefinitions: AiSkillDefinition[] = [
  {
    id: "ai-agent-context-compression",
    categoryId: "agent-platform",
    title: { en: "Agent Context Compression & Tiered Recall", es: "Compresión de contexto y recuperación por capas" },
    summary: {
      en: "Reduce agent token consumption while preserving critical facts through compaction, progressive disclosure, and recall verification.",
      es: "Reduzca el consumo de tokens preservando hechos críticos mediante compactación, divulgación progresiva y verificación de recuperación.",
    },
    focus: {
      en: "Introduce recall probes, artifact extraction, and just-in-time context loading around long-running agents.",
      es: "Incorpore pruebas de recuperación, extracción de artefactos y carga de contexto justo a tiempo para agentes de larga duración.",
    },
    outcome: { en: "Smaller context windows with measurable recall fidelity.", es: "Ventanas de contexto menores con fidelidad de recuperación medible." },
    recommendedServices: ["ModelArts MaaS", "ECS", "CSS", "OBS", "Cloud Eye"],
    githubPath: `${githubRoot}/Agent-Platform/agent-context-compression-and-retrieval-skill`,
    heroImage: aiImages.glassOrbit,
  },
  {
    id: "ai-enterprise-agent-memory",
    categoryId: "agent-platform",
    title: { en: "Enterprise Agent Memory", es: "Memoria empresarial para agentes" },
    summary: {
      en: "Persist useful agent knowledge across sessions with layered retrieval, privacy controls, and auditable capture.",
      es: "Conserve conocimiento útil entre sesiones con recuperación por capas, privacidad y captura auditable.",
    },
    focus: {
      en: "Combine working, episodic, procedural, semantic, and configuration memory with sensitive-content exclusion.",
      es: "Combine memoria de trabajo, episódica, procedimental, semántica y de configuración excluyendo contenido sensible.",
    },
    outcome: { en: "Agents reuse approved experience without rebuilding context every session.", es: "Los agentes reutilizan experiencia aprobada sin reconstruir contexto en cada sesión." },
    recommendedServices: ["ModelArts MaaS", "CSS", "RDS", "OBS", "IAM"],
    githubPath: `${githubRoot}/Agent-Platform/enterprise-agent-memory-skill`,
    heroImage: aiImages.digitalTunnel,
  },
  {
    id: "ai-project-memory-rag",
    categoryId: "agent-platform",
    title: { en: "Project Memory RAG", es: "RAG de memoria de proyecto" },
    summary: {
      en: "Unify learned project memory, document RAG, GraphRAG, and MCP access into a persistent knowledge layer.",
      es: "Unifique memoria aprendida, RAG documental, GraphRAG y acceso MCP en una capa persistente de conocimiento.",
    },
    focus: {
      en: "Use hybrid retrieval for documents, relationships, reusable procedures, and previously validated project findings.",
      es: "Use recuperación híbrida para documentos, relaciones, procedimientos reutilizables y hallazgos ya validados.",
    },
    outcome: { en: "Faster project recall with evidence and relationship-aware retrieval.", es: "Recuperación de proyecto más rápida con evidencia y relaciones." },
    recommendedServices: ["ModelArts MaaS", "CSS", "OBS", "RDS", "MCP"],
    githubPath: `${githubRoot}/Agent-Platform/project-memory-rag-skill`,
    heroImage: aiImages.connectedCity,
  },
  {
    id: "ai-contract-risk-analysis",
    categoryId: "ai-applications",
    title: { en: "Contract Risk Analysis", es: "Análisis de riesgo contractual" },
    summary: {
      en: "Extract contract text, score risks with an LLM, and store structured evidence for legal and compliance review.",
      es: "Extraiga texto contractual, evalúe riesgos con un LLM y almacene evidencia estructurada para revisión legal y de cumplimiento.",
    },
    focus: {
      en: "Connect OCR, FunctionGraph, model scoring, deterministic fallback, and DWS or GaussDB result layers.",
      es: "Conecte OCR, FunctionGraph, evaluación del modelo, fallback determinístico y capas de resultados DWS o GaussDB.",
    },
    outcome: { en: "Faster document triage with traceable risk findings.", es: "Clasificación documental más rápida con hallazgos de riesgo trazables." },
    recommendedServices: ["Huawei Cloud OCR", "FunctionGraph", "ModelArts MaaS", "DWS", "GaussDB", "OBS"],
    githubPath: `${githubRoot}/AI-Applications/Contract-Risk-Analysis-AI-Skill`,
    heroImage: aiImages.businessGovernance,
  },
  {
    id: "ai-dify-nl2sql",
    categoryId: "ai-applications",
    title: { en: "Dify NL2SQL", es: "Dify NL2SQL" },
    summary: {
      en: "Turn natural-language business questions into validated, read-only PostgreSQL queries through a controlled gateway.",
      es: "Convierta preguntas de negocio en consultas PostgreSQL validadas y de solo lectura mediante un gateway controlado.",
    },
    focus: {
      en: "Separate SQL generation from execution and enforce allowlists, read-only access, and query validation.",
      es: "Separe generación y ejecución SQL aplicando listas permitidas, acceso de solo lectura y validación de consultas.",
    },
    outcome: { en: "Self-service data questions without exposing unrestricted database access.", es: "Consultas de datos autoservicio sin exponer acceso irrestricto a la base." },
    recommendedServices: ["ModelArts MaaS", "ECS", "RDS for PostgreSQL", "Dify", "LiteLLM"],
    githubPath: `${githubRoot}/AI-Applications/dify-nl2sql-docker`,
    heroImage: aiImages.blueprintCity,
  },
  {
    id: "ai-enterprise-rag-agent",
    categoryId: "ai-applications",
    title: { en: "Enterprise RAG Agent", es: "Agente RAG empresarial" },
    summary: {
      en: "Build multilingual, cited knowledge agents for regulated document collections with ACL-aware retrieval.",
      es: "Construya agentes multilingües con citas para documentos regulados y recuperación consciente de permisos.",
    },
    focus: {
      en: "Combine document parsing, OCR, hybrid search, metadata, evidence chains, evaluation, and anti-hallucination controls.",
      es: "Combine parsing, OCR, búsqueda híbrida, metadatos, cadenas de evidencia, evaluación y controles contra alucinaciones.",
    },
    outcome: { en: "Permission-aware answers grounded in approved enterprise evidence.", es: "Respuestas con permisos basadas en evidencia empresarial aprobada." },
    recommendedServices: ["ModelArts MaaS", "CSS", "OBS", "RDS", "ECS", "RAGFlow"],
    githubPath: `${githubRoot}/AI-Applications/enterprise-rag-agent`,
    heroImage: aiImages.connectedCity,
  },
  {
    id: "ai-ragflow-huawei-maas",
    categoryId: "ai-applications",
    title: { en: "RAGFlow with Huawei MaaS", es: "RAGFlow con Huawei MaaS" },
    summary: {
      en: "Deploy RAGFlow and connect its OpenAI-compatible model provider safely to Huawei Cloud MaaS.",
      es: "Despliegue RAGFlow y conecte de forma segura su proveedor compatible con OpenAI a Huawei Cloud MaaS.",
    },
    focus: {
      en: "Validate Docker deployment, model registration, UI and API behavior, LLM calls, and secret protection.",
      es: "Valide Docker, registro de modelos, UI, API, llamadas LLM y protección de secretos.",
    },
    outcome: { en: "A validated document assistant foundation backed by Huawei MaaS.", es: "Una base validada para asistentes documentales respaldada por Huawei MaaS." },
    recommendedServices: ["ModelArts MaaS", "ECS", "OBS", "RAGFlow", "Docker"],
    githubPath: `${githubRoot}/AI-Applications/ragflow-huawei-maas`,
    heroImage: aiImages.blueGreenOrbs,
  },
  {
    id: "ai-telco-call-center",
    categoryId: "ai-applications",
    title: { en: "Telco Call Center AI", es: "IA para contact center de telecomunicaciones" },
    summary: {
      en: "Demonstrate customer intelligence, call analytics, churn insight, and agent assistance for telecom operators.",
      es: "Demuestre inteligencia de clientes, analítica de llamadas, churn y asistencia a agentes para operadores telco.",
    },
    focus: {
      en: "Combine ASR, LLM analysis, ECS GPU runtime, deterministic demo fallback, and Mexico compliance guidance.",
      es: "Combine ASR, análisis LLM, ECS GPU, fallback determinístico y orientación de cumplimiento para México.",
    },
    outcome: { en: "An executive-ready proof of concept with credible operational and regulatory controls.", es: "Una prueba ejecutiva con controles operativos y regulatorios creíbles." },
    recommendedServices: ["ECS GPU", "ModelArts MaaS", "ASR", "OBS", "Cloud Eye"],
    githubPath: `${githubRoot}/AI-Applications/Telco-Call-Center-AI-Skill`,
    heroImage: aiImages.fiveGCity,
  },
  {
    id: "ai-code-dreaming",
    categoryId: "ai-coding",
    title: { en: "Code Dreaming & Memory Hygiene", es: "Code Dreaming e higiene de memoria" },
    summary: {
      en: "Consolidate AI coding memory, remove stale references, detect rule conflicts, and produce reviewable updates.",
      es: "Consolide memoria de AI Coding, elimine referencias obsoletas, detecte conflictos y produzca cambios revisables.",
    },
    focus: {
      en: "Run an on-demand or scheduled dream pass that validates paths, deduplicates findings, and never auto-applies governance changes.",
      es: "Ejecute una pasada programada que valide rutas, elimine duplicados y nunca aplique automáticamente cambios de gobierno.",
    },
    outcome: { en: "Cleaner project memory with fewer stale or confidently wrong agent assumptions.", es: "Memoria de proyecto más limpia con menos supuestos obsoletos del agente." },
    recommendedServices: ["ModelArts MaaS", "ECS", "OBS", "CodeArts Repo"],
    githubPath: `${githubRoot}/AI-Coding/AI-Coding-Best-Practice/code-dreaming`,
    heroImage: aiImages.digitalHorizon,
  },
  {
    id: "ai-claude-code-huawei-maas",
    categoryId: "ai-coding",
    title: { en: "Claude Code with Huawei MaaS", es: "Claude Code con Huawei MaaS" },
    summary: {
      en: "Route Claude Code and the Claude Agent SDK to Huawei Cloud MaaS through compatible, isolated adapters.",
      es: "Conecte Claude Code y Claude Agent SDK a Huawei Cloud MaaS mediante adaptadores compatibles y aislados.",
    },
    focus: {
      en: "Provide side-by-side commands, CCR or Anthropic adapters, tool-call compatibility, search options, and safe logging.",
      es: "Proporcione comandos paralelos, adaptadores CCR o Anthropic, compatibilidad de herramientas, búsqueda y logging seguro.",
    },
    outcome: { en: "A reproducible MaaS-backed Claude workflow without disrupting the original client.", es: "Un flujo Claude reproducible sobre MaaS sin alterar el cliente original." },
    recommendedServices: ["ModelArts MaaS", "ECS", "LiteLLM", "Claude Code Router", "MCP"],
    githubPath: `${githubRoot}/AI-Coding/Enterprise-MaaS-Foundation/claude-code-huawei-maas`,
    heroImage: aiImages.dataStream,
  },
  {
    id: "ai-codearts-huawei-maas",
    categoryId: "ai-coding",
    title: { en: "CodeArts CLI with Huawei MaaS", es: "CodeArts CLI con Huawei MaaS" },
    summary: {
      en: "Install CodeArts CLI with a LiteLLM-backed wrapper, model configuration, local auth, and controlled autonomous mode.",
      es: "Instale CodeArts CLI con wrapper LiteLLM, configuración de modelo, autenticación local y modo autónomo controlado.",
    },
    focus: {
      en: "Standardize a repeatable macOS setup and validate language, session, model, and wrapper behavior.",
      es: "Estandarice una instalación repetible en macOS y valide idioma, sesión, modelo y comportamiento del wrapper.",
    },
    outcome: { en: "A supported CodeArts developer path using the shared MaaS gateway.", es: "Una ruta soportada de CodeArts usando el gateway MaaS compartido." },
    recommendedServices: ["CodeArts", "ModelArts MaaS", "LiteLLM", "ECS"],
    githubPath: `${githubRoot}/AI-Coding/Enterprise-MaaS-Foundation/codearts-huawei-maas`,
    heroImage: aiImages.mintOrbs,
  },
  {
    id: "ai-codex-huawei-maas",
    categoryId: "ai-coding",
    title: { en: "Codex CLI with Huawei MaaS", es: "Codex CLI con Huawei MaaS" },
    summary: {
      en: "Add a side-by-side Codex command routed to Huawei MaaS through a compatible Responses API shim.",
      es: "Agregue un comando Codex paralelo conectado a Huawei MaaS mediante un shim compatible con Responses API.",
    },
    focus: {
      en: "Preserve the original Codex command while validating model routing, streaming, tool use, and isolation.",
      es: "Conserve el comando Codex original validando ruteo, streaming, herramientas y aislamiento.",
    },
    outcome: { en: "Controlled Codex access to MaaS with a reversible client setup.", es: "Acceso controlado de Codex a MaaS con configuración reversible." },
    recommendedServices: ["ModelArts MaaS", "ECS", "LiteLLM", "CCR"],
    githubPath: `${githubRoot}/AI-Coding/Enterprise-MaaS-Foundation/codex-huawei-maas`,
    heroImage: aiImages.blueprintCity,
  },
  {
    id: "ai-copilot-huawei-maas",
    categoryId: "ai-coding",
    title: { en: "Copilot Chat with Huawei MaaS", es: "Copilot Chat con Huawei MaaS" },
    summary: {
      en: "Configure and harden VS Code Copilot Chat against an OpenAI-compatible Huawei MaaS model endpoint.",
      es: "Configure y fortalezca Copilot Chat en VS Code con un endpoint Huawei MaaS compatible con OpenAI.",
    },
    focus: {
      en: "Diagnose stalled responses, malformed tool calls, partial writes, path drift, and extension compatibility.",
      es: "Diagnostique bloqueos, tool calls malformadas, escrituras parciales, cambios de ruta y compatibilidad de extensión.",
    },
    outcome: { en: "A validated VS Code assistant setup with portable diagnostics.", es: "Una configuración validada del asistente VS Code con diagnóstico portable." },
    recommendedServices: ["ModelArts MaaS", "VS Code", "LiteLLM", "ECS"],
    githubPath: `${githubRoot}/AI-Coding/Enterprise-MaaS-Foundation/copilot-huawei-maas`,
    heroImage: aiImages.yellowOrbs,
  },
  {
    id: "ai-css-code-search-mcp",
    categoryId: "ai-coding",
    title: { en: "CSS Code Search MCP", es: "Búsqueda de código CSS mediante MCP" },
    summary: {
      en: "Index repositories in Huawei Cloud CSS and expose code and documentation search as native MCP tools.",
      es: "Indexe repositorios en Huawei Cloud CSS y exponga búsqueda de código y documentación como herramientas MCP.",
    },
    focus: {
      en: "Provision ECS and CSS, ingest repository metadata, and expose search_code, list_skills, and get_file safely.",
      es: "Provisione ECS y CSS, ingiera metadatos y exponga de forma segura search_code, list_skills y get_file.",
    },
    outcome: { en: "Fast server-side code retrieval without loading the entire repository into agent context.", es: "Recuperación rápida de código sin cargar todo el repositorio en el contexto del agente." },
    recommendedServices: ["Cloud Search Service", "ECS", "MCP", "OBS", "IAM"],
    githubPath: `${githubRoot}/AI-Coding/Enterprise-MaaS-Foundation/CSS-Code-Search-MCP`,
    heroImage: aiImages.digitalTunnel,
  },
  {
    id: "ai-litellm-huawei-maas-proxy",
    categoryId: "ai-coding",
    title: { en: "LiteLLM Huawei MaaS Proxy", es: "Proxy LiteLLM para Huawei MaaS" },
    summary: {
      en: "Operate a shared OpenAI-compatible MaaS gateway with virtual keys, budgets, load balancing, and metrics.",
      es: "Opere un gateway MaaS compatible con OpenAI con claves virtuales, presupuestos, balanceo y métricas.",
    },
    focus: {
      en: "Deploy LiteLLM, PostgreSQL, Prometheus, and Grafana with optional search MCP and coding-agent integrations.",
      es: "Despliegue LiteLLM, PostgreSQL, Prometheus y Grafana con MCP de búsqueda e integraciones de coding opcionales.",
    },
    outcome: { en: "Governed multi-team model access with cost and performance visibility.", es: "Acceso gobernado multi-equipo con visibilidad de costo y rendimiento." },
    recommendedServices: ["ModelArts MaaS", "ECS", "RDS", "LiteLLM", "Prometheus", "Grafana"],
    githubPath: `${githubRoot}/AI-Coding/Enterprise-MaaS-Foundation/LiteLLM-Huawei-MaaS-Proxy`,
    heroImage: aiImages.cityNetwork,
  },
  {
    id: "ai-mgc-cross-region-migration",
    categoryId: "host-migration",
    title: { en: "MGC Cross-Region Migration", es: "Migración MGC entre regiones" },
    summary: {
      en: "Execute repeatable ECS or VMware migration with SMS-first automation and a documented rsync fallback.",
      es: "Ejecute migraciones repetibles de ECS o VMware con automatización SMS-first y fallback rsync documentado.",
    },
    focus: {
      en: "Automate Terraform setup, compatibility prechecks, task execution, error diagnosis, validation, and evidence packaging.",
      es: "Automatice Terraform, prechecks, ejecución, diagnóstico de errores, validación y empaquetado de evidencia.",
    },
    outcome: { en: "A controlled migration runbook with explicit fallback and cutover evidence.", es: "Un runbook controlado con fallback explícito y evidencia de cutover." },
    recommendedServices: ["Migration Center", "Server Migration Service", "ECS", "OBS", "Terraform"],
    githubPath: `${githubRoot}/host_migration/skill`,
    heroImage: aiImages.mountain,
  },
  {
    id: "ai-langfuse-observability",
    categoryId: "responsible-ai",
    title: { en: "Langfuse LLM Observability", es: "Observabilidad LLM con Langfuse" },
    summary: {
      en: "Add tracing, prompt management, evaluation, usage, latency, cost, and error visibility to LLM applications.",
      es: "Agregue trazas, gestión de prompts, evaluación, uso, latencia, costo y errores a aplicaciones LLM.",
    },
    focus: {
      en: "Instrument applications or LiteLLM while keeping MaaS credentials and provider responsibilities separate.",
      es: "Instrumente aplicaciones o LiteLLM manteniendo separadas las credenciales MaaS y responsabilidades del proveedor.",
    },
    outcome: { en: "Comparable traces and evaluations for safer production decisions.", es: "Trazas y evaluaciones comparables para decisiones productivas más seguras." },
    recommendedServices: ["ModelArts MaaS", "ECS", "RDS", "Langfuse", "Prometheus"],
    githubPath: `${githubRoot}/Responsible-AI-and-Governance/langfuse-llm-observability`,
    heroImage: aiImages.businessGovernance,
  },
  {
    id: "ai-openllmetry-maas-agent",
    categoryId: "responsible-ai",
    title: { en: "OpenLLMetry for MaaS Agents", es: "OpenLLMetry para agentes MaaS" },
    summary: {
      en: "Instrument MaaS-backed agents with OpenLLMetry and OpenTelemetry while protecting prompts and credentials.",
      es: "Instrumente agentes MaaS con OpenLLMetry y OpenTelemetry protegiendo prompts y credenciales.",
    },
    focus: {
      en: "Capture model, tool, retrieval, latency, and error spans through safe OTLP or Traceloop export.",
      es: "Capture spans de modelo, herramientas, recuperación, latencia y errores mediante exportación OTLP o Traceloop segura.",
    },
    outcome: { en: "End-to-end agent telemetry with explicit privacy boundaries.", es: "Telemetría de extremo a extremo con límites explícitos de privacidad." },
    recommendedServices: ["ModelArts MaaS", "ECS", "OpenTelemetry", "Cloud Eye", "Traceloop"],
    githubPath: `${githubRoot}/Responsible-AI-and-Governance/openllmetry-huawei-maas-agent`,
    heroImage: aiImages.cityNetwork,
  },
];
