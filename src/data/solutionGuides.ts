import type { Lang } from "./i18n";

type Localized = Record<Lang, string>;

export type SolutionGuide = {
  overview: Localized;
  businessChallenge: Localized;
  bestFitScenarios: Localized[];
  businessOutcomes: Localized[];
  recommendedCapabilities: Localized[];
  adoptionPath: Array<{ title: Localized; body: Localized }>;
  beforeYouStart: Localized[];
  successMeasures: Localized[];
  faq: Array<{ question: Localized; answer: Localized }>;
  nextSteps: Localized[];
  technicalReferences?: Array<{ label: string; href: string }>;
};

const t = (es: string, en: string, zh: string): Localized => ({ es, en, zh });

const standardPath: SolutionGuide["adoptionPath"] = [
  {
    title: t("Evaluar", "Assess", "评估"),
    body: t(
      "Defina el objetivo de negocio, los sistemas involucrados y el resultado esperado antes de invertir en implementación.",
      "Define the business objective, systems in scope, and expected outcome before investing in implementation.",
      "先明确业务目标、涉及系统和预期结果，再进入实施投入。",
    ),
  },
  {
    title: t("Probar", "Pilot", "试点"),
    body: t(
      "Ejecute un piloto acotado con datos, usuarios o cargas reales para validar valor, costo, seguridad y operación.",
      "Run a focused pilot with real data, users, or workloads to validate value, cost, security, and operations.",
      "使用真实数据、用户或负载做小范围试点，验证价值、成本、安全和运维。",
    ),
  },
  {
    title: t("Lanzar", "Launch", "上线"),
    body: t(
      "Prepare el plan de transición, responsables, soporte y métricas para pasar del piloto al uso productivo.",
      "Prepare the transition plan, owners, support model, and metrics to move from pilot to production use.",
      "准备切换计划、责任人、支持模式和指标，从试点进入生产使用。",
    ),
  },
  {
    title: t("Optimizar", "Optimize", "优化"),
    body: t(
      "Revise adopción, disponibilidad, costo y experiencia para mejorar el caso y ampliarlo a más áreas.",
      "Review adoption, availability, cost, and experience to improve the use case and scale it to more teams.",
      "持续复盘采用率、可用性、成本和体验，优化后扩展到更多团队。",
    ),
  },
];

export const solutionGuides: Record<string, SolutionGuide> = {
  "ai-ai-applications": {
    overview: t(
      "Cree aplicaciones inteligentes para automatizar atención, soporte, ventas y operaciones sin rediseñar todo el negocio desde cero.",
      "Create intelligent applications that automate support, service, sales, and operations without redesigning the whole business from scratch.",
      "构建智能应用，自动化客服、支持、销售和运营流程，无需从零重构整个业务。",
    ),
    businessChallenge: t(
      "Muchas pymes dependen de procesos manuales, información dispersa y equipos pequeños. Esto limita la velocidad de respuesta y dificulta mantener una experiencia consistente.",
      "Many SMBs rely on manual processes, scattered information, and small teams. This limits response speed and makes consistent customer experience hard to maintain.",
      "许多中小企业依赖人工流程、分散信息和小团队运作，响应速度受限，也难以保持一致的客户体验。",
    ),
    bestFitScenarios: [
      t("Atención al cliente con alto volumen de preguntas repetidas.", "Customer service with high volumes of repeated questions.", "客户服务中存在大量重复问题。"),
      t("Equipos de ventas u operaciones que necesitan asistentes internos.", "Sales or operations teams that need internal assistants.", "销售或运营团队需要内部助手。"),
      t("Procesos donde la respuesta rápida mejora ingresos o satisfacción.", "Processes where faster response improves revenue or satisfaction.", "响应速度会影响收入或满意度的流程。"),
    ],
    businessOutcomes: [
      t("Reducir tiempo de respuesta y carga operativa.", "Reduce response time and operational workload.", "降低响应时间和运营负担。"),
      t("Mejorar consistencia en respuestas y procesos.", "Improve consistency across answers and workflows.", "提升回答和流程的一致性。"),
      t("Crear una base medible para nuevos casos de IA.", "Create a measurable foundation for new AI use cases.", "为更多 AI 场景建立可衡量基础。"),
    ],
    recommendedCapabilities: [
      t("Modelos como servicio para acelerar el primer caso.", "Model-as-a-service to accelerate the first use case.", "通过 MaaS 加速首个场景。"),
      t("Base de conocimiento y almacenamiento para contenido empresarial.", "Knowledge base and storage for enterprise content.", "用于企业内容的知识库和存储。"),
      t("Aplicación web o API integrada con sistemas existentes.", "Web app or API integrated with existing systems.", "与现有系统集成的 Web 应用或 API。"),
    ],
    adoptionPath: standardPath,
    beforeYouStart: [
      t("Lista de procesos candidatos y volumen mensual aproximado.", "List of candidate processes and approximate monthly volume.", "候选流程清单及月度大致量级。"),
      t("Fuentes de conocimiento, documentos o sistemas que la IA debe consultar.", "Knowledge sources, documents, or systems the AI should use.", "AI 需要使用的知识来源、文档或系统。"),
      t("Criterios de seguridad, privacidad y revisión humana.", "Security, privacy, and human-review requirements.", "安全、隐私和人工审核要求。"),
    ],
    successMeasures: [
      t("Tiempo promedio de respuesta.", "Average response time.", "平均响应时间。"),
      t("Tasa de resolución o automatización.", "Resolution or automation rate.", "解决率或自动化率。"),
      t("Satisfacción de usuarios y costo por interacción.", "User satisfaction and cost per interaction.", "用户满意度和单次交互成本。"),
    ],
    faq: [
      {
        question: t("¿Necesito un equipo grande de desarrollo?", "Do I need a large development team?", "是否需要大型开发团队？"),
        answer: t(
          "No para iniciar. Un piloto puede comenzar con un alcance pequeño, datos controlados y una integración simple.",
          "Not to start. A pilot can begin with a small scope, controlled data, and simple integration.",
          "启动阶段不需要。试点可以从小范围、受控数据和简单集成开始。",
        ),
      },
      {
        question: t("¿Cómo controlo respuestas incorrectas?", "How do I control incorrect answers?", "如何控制错误回答？"),
        answer: t(
          "Defina fuentes autorizadas, límites de uso, revisión humana y métricas de calidad antes de producción.",
          "Define trusted sources, usage boundaries, human review, and quality metrics before production.",
          "生产前定义可信来源、使用边界、人工审核和质量指标。",
        ),
      },
    ],
    nextSteps: [
      t("Seleccione un proceso de alto valor y bajo riesgo para el piloto.", "Select a high-value, low-risk process for the pilot.", "选择一个高价值、低风险流程做试点。"),
      t("Prepare una muestra de documentos o conversaciones reales.", "Prepare a sample of real documents or conversations.", "准备真实文档或对话样本。"),
      t("Defina quién aprobará calidad, seguridad y salida a producción.", "Define who approves quality, security, and production release.", "明确质量、安全和上线审批人。"),
    ],
  },
  "ai-ai-applications-ragflow-huawei-maas": {
    overview: t(
      "Convierta documentos empresariales en una base de conocimiento consultable con IA para ventas, soporte, operación o capacitación.",
      "Turn enterprise documents into an AI-searchable knowledge base for sales, support, operations, or training.",
      "将企业文档转化为可被 AI 查询的知识库，服务销售、支持、运营或培训场景。",
    ),
    businessChallenge: t(
      "El conocimiento de una pyme suele estar en PDFs, manuales, tickets y carpetas. Los equipos pierden tiempo buscando respuestas y la calidad depende de expertos individuales.",
      "SMB knowledge often lives in PDFs, manuals, tickets, and folders. Teams lose time searching, and answer quality depends on individual experts.",
      "中小企业知识常散落在 PDF、手册、工单和文件夹中，团队查找耗时，回答质量依赖个别专家。",
    ),
    bestFitScenarios: [
      t("Soporte interno o externo basado en manuales y políticas.", "Internal or external support based on manuals and policies.", "基于手册和政策的内部或外部支持。"),
      t("Ventas que necesitan consultar catálogos, contratos o FAQs.", "Sales teams that need to query catalogs, contracts, or FAQs.", "销售团队需要查询目录、合同或 FAQ。"),
      t("Capacitación de nuevos equipos con conocimiento documentado.", "Training new teams with documented knowledge.", "基于文档知识培训新团队。"),
    ],
    businessOutcomes: [
      t("Reducir tiempo de búsqueda de información.", "Reduce information search time.", "减少信息查找时间。"),
      t("Mejorar consistencia de respuestas basadas en documentos aprobados.", "Improve answer consistency based on approved documents.", "基于已批准文档提升回答一致性。"),
      t("Medir calidad, uso y brechas de conocimiento.", "Measure quality, usage, and knowledge gaps.", "衡量质量、使用情况和知识缺口。"),
    ],
    recommendedCapabilities: [
      t("RAGFlow para ingestión y recuperación de conocimiento.", "RAGFlow for knowledge ingestion and retrieval.", "使用 RAGFlow 做知识摄取和检索。"),
      t("Huawei MaaS para acceso API a modelos.", "Huawei MaaS for API-based model access.", "通过 Huawei MaaS 以 API 方式访问模型。"),
      t("OBS/ECS para almacenamiento y ejecución del servicio.", "OBS/ECS for storage and service runtime.", "使用 OBS/ECS 承载存储和服务运行。"),
    ],
    adoptionPath: standardPath,
    beforeYouStart: [
      t("Documentos fuente y responsables de aprobar contenido.", "Source documents and content owners.", "源文档及内容负责人。"),
      t("Usuarios objetivo y preguntas frecuentes.", "Target users and frequent questions.", "目标用户和高频问题。"),
      t("Reglas de acceso, datos sensibles y retención.", "Access rules, sensitive data, and retention requirements.", "访问规则、敏感数据和保留要求。"),
    ],
    successMeasures: [
      t("Precisión de respuestas en preguntas de prueba.", "Answer accuracy on test questions.", "测试问题回答准确率。"),
      t("Reducción del tiempo de búsqueda.", "Reduction in search time.", "查询时间下降。"),
      t("Uso activo por equipos objetivo.", "Active usage by target teams.", "目标团队活跃使用。"),
    ],
    faq: [
      {
        question: t("¿Puedo empezar con pocos documentos?", "Can I start with a small document set?", "可以从少量文档开始吗？"),
        answer: t(
          "Sí. Es mejor iniciar con un conjunto pequeño, autorizado y de alto valor para medir calidad rápidamente.",
          "Yes. It is better to start with a small, approved, high-value set to measure quality quickly.",
          "可以。建议从小规模、已授权且高价值的文档集开始，快速衡量质量。",
        ),
      },
      {
        question: t("¿El sistema reemplaza a mis expertos?", "Does it replace my experts?", "系统会替代专家吗？"),
        answer: t(
          "No. Ayuda a escalar su conocimiento y reduce preguntas repetidas; los expertos siguen validando contenido y excepciones.",
          "No. It scales their knowledge and reduces repeated questions; experts still validate content and exceptions.",
          "不会。它用于扩展专家知识并减少重复问题，专家仍负责内容和例外情况审核。",
        ),
      },
    ],
    nextSteps: [
      t("Seleccione un dominio de conocimiento para el primer piloto.", "Select one knowledge domain for the first pilot.", "选择一个知识领域作为首个试点。"),
      t("Prepare 20-50 preguntas reales para evaluación.", "Prepare 20-50 real questions for evaluation.", "准备 20-50 个真实问题用于评估。"),
      t("Defina usuarios piloto y criterios de aprobación.", "Define pilot users and approval criteria.", "确定试点用户和验收标准。"),
    ],
    technicalReferences: [
      {
        label: "RAGFlow Huawei MaaS implementation skill",
        href: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/blob/docs/general-skill-framework/AI/AI-Applications/ragflow-huawei-maas/SKILL.md",
      },
    ],
  },
  "cloud-foundation-security-foundation": {
    overview: t(
      "Establezca una base de seguridad para proteger identidades, redes, datos y operaciones críticas.",
      "Establish a security foundation to protect identities, networks, data, and critical operations.",
      "建立安全基础，保护身份、网络、数据和关键运营。",
    ),
    businessChallenge: t(
      "A medida que una pyme digitaliza operaciones, aumenta la exposición a accesos no autorizados, pérdida de datos y errores de configuración.",
      "As an SMB digitizes operations, exposure to unauthorized access, data loss, and misconfiguration increases.",
      "随着中小企业数字化运营推进，未授权访问、数据丢失和配置错误风险会增加。",
    ),
    bestFitScenarios: [
      t("Empresas que manejan datos de clientes o pagos.", "Businesses handling customer or payment data.", "处理客户或支付数据的企业。"),
      t("Ambientes híbridos con usuarios, sucursales y aplicaciones críticas.", "Hybrid environments with users, branches, and critical apps.", "存在用户、分支和关键应用的混合环境。"),
      t("Equipos que necesitan controles básicos antes de crecer.", "Teams needing baseline controls before scaling.", "扩展前需要基础控制的团队。"),
    ],
    businessOutcomes: [
      t("Reducir riesgos operativos y de acceso.", "Reduce operational and access risks.", "降低运营和访问风险。"),
      t("Mejorar visibilidad de eventos y responsabilidades.", "Improve visibility into events and responsibilities.", "提升事件和责任可见性。"),
      t("Preparar una base para auditorías y cumplimiento.", "Prepare a foundation for audits and compliance.", "为审计和合规建立基础。"),
    ],
    recommendedCapabilities: [
      t("Gestión de identidad y permisos.", "Identity and permission management.", "身份和权限管理。"),
      t("Segmentación de red y controles perimetrales.", "Network segmentation and perimeter controls.", "网络分段和边界控制。"),
      t("Monitoreo, logs, respaldo y respuesta.", "Monitoring, logs, backup, and response.", "监控、日志、备份和响应。"),
    ],
    adoptionPath: standardPath,
    beforeYouStart: [
      t("Inventario de usuarios, sistemas y datos sensibles.", "Inventory of users, systems, and sensitive data.", "用户、系统和敏感数据清单。"),
      t("Políticas de acceso actuales y responsables.", "Current access policies and owners.", "现有访问策略和负责人。"),
      t("Requisitos regulatorios o contractuales relevantes.", "Relevant regulatory or contractual requirements.", "相关监管或合同要求。"),
    ],
    successMeasures: [
      t("Cuentas privilegiadas controladas.", "Privileged accounts controlled.", "特权账号受控。"),
      t("Alertas y logs disponibles para revisión.", "Alerts and logs available for review.", "告警和日志可审查。"),
      t("Plan de recuperación y respuesta documentado.", "Recovery and response plan documented.", "恢复和响应计划已文档化。"),
    ],
    faq: [
      {
        question: t("¿Debo hacerlo antes de migrar más cargas?", "Should I do this before moving more workloads?", "是否应在迁移更多负载前做？"),
        answer: t(
          "Sí. Una base mínima de identidad, red, monitoreo y respaldo reduce riesgo al escalar.",
          "Yes. A minimum baseline for identity, network, monitoring, and backup reduces risk when scaling.",
          "是。身份、网络、监控和备份的最低基线能降低扩展风险。",
        ),
      },
    ],
    nextSteps: [
      t("Ejecute una revisión rápida de identidad, red y datos.", "Run a quick review of identity, network, and data.", "快速评估身份、网络和数据。"),
      t("Priorice los tres controles con mayor reducción de riesgo.", "Prioritize the three controls with the highest risk reduction.", "优先处理最能降低风险的三个控制项。"),
      t("Defina responsables de operación y revisión periódica.", "Define owners for operations and periodic review.", "明确运营和定期复查责任人。"),
    ],
  },
  "cloud-foundation-dr-and-backup": {
    overview: t(
      "Proteja aplicaciones y datos críticos con respaldo, recuperación y continuidad diseñados para SMB.",
      "Protect critical applications and data with backup, recovery, and continuity designed for SMBs.",
      "通过面向 SMB 的备份、恢复和连续性能力保护关键应用和数据。",
    ),
    businessChallenge: t(
      "La pérdida de datos o una interrupción puede detener ventas, atención y operación. Muchas pymes no prueban recuperación hasta que ocurre un incidente.",
      "Data loss or downtime can stop sales, service, and operations. Many SMBs do not test recovery until an incident happens.",
      "数据丢失或中断会影响销售、服务和运营。许多中小企业直到事故发生才发现恢复不可用。",
    ),
    bestFitScenarios: [
      t("ERP, bases de datos, sitios web o archivos críticos.", "ERP, databases, websites, or critical files.", "ERP、数据库、网站或关键文件。"),
      t("Empresas sin pruebas regulares de recuperación.", "Businesses without regular recovery tests.", "缺少定期恢复演练的企业。"),
      t("Operaciones con ventanas limitadas de interrupción.", "Operations with limited downtime windows.", "中断窗口有限的运营场景。"),
    ],
    businessOutcomes: [
      t("Reducir impacto de errores, ransomware o fallas.", "Reduce impact from errors, ransomware, or failures.", "降低误操作、勒索或故障影响。"),
      t("Definir tiempos de recuperación realistas.", "Define realistic recovery times.", "定义现实可达的恢复时间。"),
      t("Aumentar confianza en continuidad operativa.", "Increase confidence in operational continuity.", "提升业务连续性信心。"),
    ],
    recommendedCapabilities: [
      t("Respaldo automatizado y políticas de retención.", "Automated backup and retention policies.", "自动备份和保留策略。"),
      t("Restauración validada con ejercicios prácticos.", "Validated restoration through practical drills.", "通过演练验证恢复。"),
      t("Monitoreo de cumplimiento de respaldos.", "Monitoring of backup compliance.", "备份合规状态监控。"),
    ],
    adoptionPath: standardPath,
    beforeYouStart: [
      t("Lista de sistemas críticos y prioridad de recuperación.", "List of critical systems and recovery priority.", "关键系统清单和恢复优先级。"),
      t("Objetivos RPO/RTO aproximados.", "Approximate RPO/RTO targets.", "大致 RPO/RTO 目标。"),
      t("Ventanas de mantenimiento y contactos de aprobación.", "Maintenance windows and approval contacts.", "维护窗口和审批联系人。"),
    ],
    successMeasures: [
      t("Respaldos completados según política.", "Backups completed according to policy.", "备份按策略完成。"),
      t("Restauración probada con evidencia.", "Restoration tested with evidence.", "恢复已测试并有证据。"),
      t("RTO/RPO medidos y aceptados por negocio.", "RTO/RPO measured and accepted by the business.", "RTO/RPO 已测量并被业务接受。"),
    ],
    faq: [
      {
        question: t("¿Backup es lo mismo que continuidad?", "Is backup the same as continuity?", "备份等于连续性吗？"),
        answer: t(
          "No. Backup guarda datos; continuidad exige saber qué restaurar, en qué orden, cuánto tarda y quién decide.",
          "No. Backup stores data; continuity requires knowing what to restore, in what order, how long it takes, and who decides.",
          "不是。备份保存数据；连续性还要求知道恢复什么、顺序、耗时和决策人。",
        ),
      },
    ],
    nextSteps: [
      t("Clasifique aplicaciones por criticidad.", "Classify applications by criticality.", "按关键性分类应用。"),
      t("Defina objetivos de recuperación con el negocio.", "Define recovery targets with the business.", "与业务定义恢复目标。"),
      t("Ejecute una primera prueba de restauración.", "Run a first restoration test.", "执行首次恢复测试。"),
    ],
  },
  "application-modernization-datacenter-migration-into-cloud": {
    overview: t(
      "Planifique la migración de servidores y aplicaciones a cloud con menor interrupción y una ruta clara por oleadas.",
      "Plan the migration of servers and applications to cloud with lower disruption and a clear wave-based path.",
      "以分批迁移方式规划服务器和应用上云，降低中断并明确路径。",
    ),
    businessChallenge: t(
      "Migrar sin inventario, dependencias y criterios de éxito claros puede generar interrupciones, costos inesperados y baja aceptación.",
      "Migrating without clear inventory, dependencies, and success criteria can create downtime, unexpected cost, and low adoption.",
      "缺少清单、依赖关系和成功标准的迁移，容易造成中断、意外成本和低接受度。",
    ),
    bestFitScenarios: [
      t("Renovación de infraestructura o salida de datacenter.", "Infrastructure refresh or datacenter exit.", "基础设施更新或退出数据中心。"),
      t("Aplicaciones que requieren elasticidad o mejor continuidad.", "Applications needing elasticity or better continuity.", "需要弹性或更好连续性的应用。"),
      t("Empresas que quieren ordenar costos y operación.", "Businesses that want clearer cost and operations.", "希望理清成本和运维的企业。"),
    ],
    businessOutcomes: [
      t("Reducir riesgo de migración con oleadas controladas.", "Reduce migration risk with controlled waves.", "通过受控批次降低迁移风险。"),
      t("Mejorar escalabilidad y visibilidad operativa.", "Improve scalability and operational visibility.", "提升扩展性和运维可见性。"),
      t("Construir una base para modernización posterior.", "Build a foundation for later modernization.", "为后续现代化建立基础。"),
    ],
    recommendedCapabilities: [
      t("Evaluación de cargas y dependencias.", "Workload and dependency assessment.", "负载和依赖评估。"),
      t("ECS, EVS, red, seguridad y respaldo.", "ECS, EVS, networking, security, and backup.", "ECS、EVS、网络、安全和备份。"),
      t("Plan de pruebas, cutover y rollback.", "Testing, cutover, and rollback plan.", "测试、割接和回退计划。"),
    ],
    adoptionPath: standardPath,
    beforeYouStart: [
      t("Inventario de servidores, aplicaciones y dependencias.", "Inventory of servers, applications, and dependencies.", "服务器、应用和依赖清单。"),
      t("Ventanas de cambio y criticidad por aplicación.", "Change windows and criticality by application.", "各应用变更窗口和关键性。"),
      t("Costos actuales y restricciones técnicas.", "Current costs and technical constraints.", "当前成本和技术约束。"),
    ],
    successMeasures: [
      t("Migración piloto sin impacto crítico.", "Pilot migration without critical impact.", "试点迁移无关键影响。"),
      t("Rendimiento y disponibilidad validados.", "Performance and availability validated.", "性能和可用性已验证。"),
      t("Costo mensual estimado comparado con línea base.", "Monthly estimated cost compared with baseline.", "月度估算成本与基线对比。"),
    ],
    faq: [
      {
        question: t("¿Tengo que migrar todo al mismo tiempo?", "Do I have to migrate everything at once?", "是否必须一次迁移全部？"),
        answer: t(
          "No. Para SMB es más seguro empezar con una ola piloto y avanzar por prioridad y dependencia.",
          "No. For SMBs it is safer to start with a pilot wave and move by priority and dependency.",
          "不需要。对 SMB 更安全的方式是先做试点批次，再按优先级和依赖推进。",
        ),
      },
    ],
    nextSteps: [
      t("Use el cotizador RVTools para una primera estimación.", "Use the RVTools estimator for an initial estimate.", "使用 RVTools 报价器做初步估算。"),
      t("Seleccione una aplicación piloto.", "Select one pilot application.", "选择一个试点应用。"),
      t("Defina criterios de cutover y rollback.", "Define cutover and rollback criteria.", "定义割接和回退标准。"),
    ],
  },
  "application-modernization-sap-on-cloud": {
    overview: t(
      "Ejecute SAP sobre una base cloud preparada para disponibilidad, respaldo, rendimiento y crecimiento.",
      "Run SAP on a cloud foundation prepared for availability, backup, performance, and growth.",
      "在具备可用性、备份、性能和增长能力的云基础上运行 SAP。",
    ),
    businessChallenge: t(
      "SAP suele ser crítico para finanzas, inventario y operación. Cambios de infraestructura requieren evaluación cuidadosa para evitar impacto al negocio.",
      "SAP is often critical for finance, inventory, and operations. Infrastructure changes require careful assessment to avoid business impact.",
      "SAP 通常支撑财务、库存和运营，基础设施变化需要谨慎评估以避免业务影响。",
    ),
    bestFitScenarios: [
      t("Renovación de hardware o crecimiento de capacidad SAP.", "Hardware refresh or SAP capacity growth.", "SAP 硬件更新或容量增长。"),
      t("Necesidad de mejor respaldo y continuidad.", "Need for better backup and continuity.", "需要更好的备份和连续性。"),
      t("Preparación para modernizar datos y analítica alrededor de SAP.", "Preparing to modernize data and analytics around SAP.", "准备围绕 SAP 做数据和分析现代化。"),
    ],
    businessOutcomes: [
      t("Mayor flexibilidad para capacidad y ambientes.", "More flexibility for capacity and environments.", "容量和环境更灵活。"),
      t("Mejor recuperación y operación controlada.", "Better recovery and controlled operations.", "更好的恢复和受控运维。"),
      t("Base para integración con datos e IA.", "Foundation for data and AI integration.", "为数据和 AI 集成奠定基础。"),
    ],
    recommendedCapabilities: [
      t("Arquitectura SAP dimensionada por carga.", "SAP architecture sized by workload.", "按负载规划 SAP 架构。"),
      t("Computación, almacenamiento y red para sistemas críticos.", "Compute, storage, and networking for critical systems.", "面向关键系统的计算、存储和网络。"),
      t("Respaldo, monitoreo y plan de recuperación.", "Backup, monitoring, and recovery plan.", "备份、监控和恢复计划。"),
    ],
    adoptionPath: standardPath,
    beforeYouStart: [
      t("Versiones SAP, base de datos, tamaño y uso actual.", "SAP versions, database, size, and current usage.", "SAP 版本、数据库、规模和当前使用情况。"),
      t("Ventanas permitidas y procesos críticos.", "Allowed windows and critical processes.", "允许窗口和关键流程。"),
      t("Requisitos de disponibilidad, respaldo y cumplimiento.", "Availability, backup, and compliance requirements.", "可用性、备份和合规要求。"),
    ],
    successMeasures: [
      t("Rendimiento validado para procesos críticos.", "Performance validated for critical processes.", "关键流程性能已验证。"),
      t("Plan de respaldo y recuperación probado.", "Backup and recovery plan tested.", "备份和恢复计划已测试。"),
      t("Operación y responsabilidades claras.", "Clear operations and responsibilities.", "运维和责任清晰。"),
    ],
    faq: [
      {
        question: t("¿Es un cambio solo técnico?", "Is this only a technical change?", "这只是技术变更吗？"),
        answer: t(
          "No. SAP impacta procesos clave; negocio e IT deben validar ventanas, rendimiento y continuidad.",
          "No. SAP impacts key processes; business and IT must validate windows, performance, and continuity.",
          "不是。SAP 影响关键流程，业务和 IT 都需要验证窗口、性能和连续性。",
        ),
      },
    ],
    nextSteps: [
      t("Reúna información de sizing y dependencias SAP.", "Gather SAP sizing and dependency information.", "收集 SAP sizing 和依赖信息。"),
      t("Defina un escenario piloto o ambiente no productivo.", "Define a pilot scenario or non-production environment.", "定义试点场景或非生产环境。"),
      t("Alinee criterios de rendimiento y continuidad.", "Align performance and continuity criteria.", "对齐性能和连续性标准。"),
    ],
  },
};
