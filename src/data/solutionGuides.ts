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

const t = (es: string, en: string, zh?: string): Localized => ({ es, en, zh: zh ?? en });

const standardPath: SolutionGuide["adoptionPath"] = [
  {
    title: t("Evaluar", "Assess"),
    body: t("Defina el objetivo de negocio, los sistemas involucrados y el resultado esperado antes de invertir en implementación.", "Define the business objective, systems in scope, and expected outcome before investing in implementation."),
  },
  {
    title: t("Probar", "Pilot"),
    body: t("Ejecute un piloto acotado con datos, usuarios o cargas reales para validar valor, costo, seguridad y operación.", "Run a focused pilot with real data, users, or workloads to validate value, cost, security, and operations."),
  },
  {
    title: t("Lanzar", "Launch"),
    body: t("Prepare el plan de transición, responsables, soporte y métricas para pasar del piloto al uso productivo.", "Prepare the transition plan, owners, support model, and metrics to move from pilot to production use."),
  },
  {
    title: t("Optimizar", "Optimize"),
    body: t("Revise adopción, disponibilidad, costo y experiencia para mejorar el caso y ampliarlo a más áreas.", "Review adoption, availability, cost, and experience to improve the use case and scale it to more teams."),
  },
];

export const solutionGuides: Record<string, SolutionGuide> = {
  "ai-ai-applications": {
    overview: t("Cree aplicaciones inteligentes para automatizar atención, soporte, ventas y operaciones sin rediseñar todo el negocio desde cero.", "Create intelligent applications that automate support, service, sales, and operations without redesigning the whole business from scratch."),
    businessChallenge: t("Muchas pymes dependen de procesos manuales, información dispersa y equipos pequeños. Esto limita la velocidad de respuesta y dificulta mantener una experiencia consistente.", "Many SMBs rely on manual processes, scattered information, and small teams. This limits response speed and makes consistent customer experience hard to maintain."),
    bestFitScenarios: [
      t("Atención al cliente con alto volumen de preguntas repetidas.", "Customer service with high volumes of repeated questions."),
      t("Equipos de ventas u operaciones que necesitan asistentes internos.", "Sales or operations teams that need internal assistants."),
      t("Procesos donde la respuesta rápida mejora ingresos o satisfacción.", "Processes where faster response improves revenue or satisfaction."),
    ],
    businessOutcomes: [
      t("Reducir tiempo de respuesta y carga operativa.", "Reduce response time and operational workload."),
      t("Mejorar consistencia en respuestas y procesos.", "Improve consistency across answers and workflows."),
      t("Crear una base medible para nuevos casos de IA.", "Create a measurable foundation for new AI use cases."),
    ],
    recommendedCapabilities: [
      t("Modelos como servicio para acelerar el primer caso.", "Model-as-a-service to accelerate the first use case."),
      t("Base de conocimiento y almacenamiento para contenido empresarial.", "Knowledge base and storage for enterprise content."),
      t("Aplicación web o API integrada con sistemas existentes.", "Web app or API integrated with existing systems."),
    ],
    adoptionPath: standardPath,
    beforeYouStart: [
      t("Lista de procesos candidatos y volumen mensual aproximado.", "List of candidate processes and approximate monthly volume."),
      t("Fuentes de conocimiento, documentos o sistemas que la IA debe consultar.", "Knowledge sources, documents, or systems the AI should use."),
      t("Criterios de seguridad, privacidad y revisión humana.", "Security, privacy, and human-review requirements."),
    ],
    successMeasures: [
      t("Tiempo promedio de respuesta.", "Average response time."),
      t("Tasa de resolución o automatización.", "Resolution or automation rate."),
      t("Satisfacción de usuarios y costo por interacción.", "User satisfaction and cost per interaction."),
    ],
    faq: [
      {
        question: t("¿Necesito un equipo grande de desarrollo?", "Do I need a large development team?"),
        answer: t("No para iniciar. Un piloto puede comenzar con un alcance pequeño, datos controlados y una integración simple.", "Not to start. A pilot can begin with a small scope, controlled data, and simple integration."),
      },
      {
        question: t("¿Cómo controlo respuestas incorrectas?", "How do I control incorrect answers?"),
        answer: t("Defina fuentes autorizadas, límites de uso, revisión humana y métricas de calidad antes de producción.", "Define trusted sources, usage boundaries, human review, and quality metrics before production."),
      },
    ],
    nextSteps: [
      t("Seleccione un proceso de alto valor y bajo riesgo para el piloto.", "Select a high-value, low-risk process for the pilot."),
      t("Prepare una muestra de documentos o conversaciones reales.", "Prepare a sample of real documents or conversations."),
      t("Defina quién aprobará calidad, seguridad y salida a producción.", "Define who approves quality, security, and production release."),
    ],
  },
  "ai-ai-applications-ragflow-huawei-maas": {
    overview: t("Convierta documentos empresariales en una base de conocimiento consultable con IA para ventas, soporte, operación o capacitación.", "Turn enterprise documents into an AI-searchable knowledge base for sales, support, operations, or training."),
    businessChallenge: t("El conocimiento de una pyme suele estar en PDFs, manuales, tickets y carpetas. Los equipos pierden tiempo buscando respuestas y la calidad depende de expertos individuales.", "SMB knowledge often lives in PDFs, manuals, tickets, and folders. Teams lose time searching, and answer quality depends on individual experts."),
    bestFitScenarios: [
      t("Soporte interno o externo basado en manuales y políticas.", "Internal or external support based on manuals and policies."),
      t("Ventas que necesitan consultar catálogos, contratos o FAQs.", "Sales teams that need to query catalogs, contracts, or FAQs."),
      t("Capacitación de nuevos equipos con conocimiento documentado.", "Training new teams with documented knowledge."),
    ],
    businessOutcomes: [
      t("Reducir tiempo de búsqueda de información.", "Reduce information search time."),
      t("Mejorar consistencia de respuestas basadas en documentos aprobados.", "Improve answer consistency based on approved documents."),
      t("Medir calidad, uso y brechas de conocimiento.", "Measure quality, usage, and knowledge gaps."),
    ],
    recommendedCapabilities: [
      t("RAGFlow para ingestión y recuperación de conocimiento.", "RAGFlow for knowledge ingestion and retrieval."),
      t("Huawei MaaS para acceso API a modelos.", "Huawei MaaS for API-based model access."),
      t("OBS/ECS para almacenamiento y ejecución del servicio.", "OBS/ECS for storage and service runtime."),
    ],
    adoptionPath: standardPath,
    beforeYouStart: [
      t("Documentos fuente y responsables de aprobar contenido.", "Source documents and content owners."),
      t("Usuarios objetivo y preguntas frecuentes.", "Target users and frequent questions."),
      t("Reglas de acceso, datos sensibles y retención.", "Access rules, sensitive data, and retention requirements."),
    ],
    successMeasures: [
      t("Precisión de respuestas en preguntas de prueba.", "Answer accuracy on test questions."),
      t("Reducción del tiempo de búsqueda.", "Reduction in search time."),
      t("Uso activo por equipos objetivo.", "Active usage by target teams."),
    ],
    faq: [
      {
        question: t("¿Puedo empezar con pocos documentos?", "Can I start with a small document set?"),
        answer: t("Sí. Es mejor iniciar con un conjunto pequeño, autorizado y de alto valor para medir calidad rápidamente.", "Yes. It is better to start with a small, approved, high-value set to measure quality quickly."),
      },
      {
        question: t("¿El sistema reemplaza a mis expertos?", "Does it replace my experts?"),
        answer: t("No. Ayuda a escalar su conocimiento y reduce preguntas repetidas; los expertos siguen validando contenido y excepciones.", "No. It scales their knowledge and reduces repeated questions; experts still validate content and exceptions."),
      },
    ],
    nextSteps: [
      t("Seleccione un dominio de conocimiento para el primer piloto.", "Select one knowledge domain for the first pilot."),
      t("Prepare 20-50 preguntas reales para evaluación.", "Prepare 20-50 real questions for evaluation."),
      t("Defina usuarios piloto y criterios de aprobación.", "Define pilot users and approval criteria."),
    ],
    technicalReferences: [
      {
        label: "RAGFlow Huawei MaaS implementation skill",
        href: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/blob/docs/general-skill-framework/AI/AI-Applications/ragflow-huawei-maas/SKILL.md",
      },
    ],
  },
  "cloud-foundation-security-foundation": {
    overview: t("Establezca una base de seguridad para proteger identidades, redes, datos y operaciones críticas.", "Establish a security foundation to protect identities, networks, data, and critical operations."),
    businessChallenge: t("A medida que una pyme digitaliza operaciones, aumenta la exposición a accesos no autorizados, pérdida de datos y errores de configuración.", "As an SMB digitizes operations, exposure to unauthorized access, data loss, and misconfiguration increases."),
    bestFitScenarios: [
      t("Empresas que manejan datos de clientes o pagos.", "Businesses handling customer or payment data."),
      t("Ambientes híbridos con usuarios, sucursales y aplicaciones críticas.", "Hybrid environments with users, branches, and critical apps."),
      t("Equipos que necesitan controles básicos antes de crecer.", "Teams needing baseline controls before scaling."),
    ],
    businessOutcomes: [
      t("Reducir riesgos operativos y de acceso.", "Reduce operational and access risks."),
      t("Mejorar visibilidad de eventos y responsabilidades.", "Improve visibility into events and responsibilities."),
      t("Preparar una base para auditorías y cumplimiento.", "Prepare a foundation for audits and compliance."),
    ],
    recommendedCapabilities: [
      t("Gestión de identidad y permisos.", "Identity and permission management."),
      t("Segmentación de red y controles perimetrales.", "Network segmentation and perimeter controls."),
      t("Monitoreo, logs, respaldo y respuesta.", "Monitoring, logs, backup, and response."),
    ],
    adoptionPath: standardPath,
    beforeYouStart: [
      t("Inventario de usuarios, sistemas y datos sensibles.", "Inventory of users, systems, and sensitive data."),
      t("Políticas de acceso actuales y responsables.", "Current access policies and owners."),
      t("Requisitos regulatorios o contractuales relevantes.", "Relevant regulatory or contractual requirements."),
    ],
    successMeasures: [
      t("Cuentas privilegiadas controladas.", "Privileged accounts controlled."),
      t("Alertas y logs disponibles para revisión.", "Alerts and logs available for review."),
      t("Plan de recuperación y respuesta documentado.", "Recovery and response plan documented."),
    ],
    faq: [
      {
        question: t("¿Debo hacerlo antes de migrar más cargas?", "Should I do this before moving more workloads?"),
        answer: t("Sí. Una base mínima de identidad, red, monitoreo y respaldo reduce riesgo al escalar.", "Yes. A minimum baseline for identity, network, monitoring, and backup reduces risk when scaling."),
      },
    ],
    nextSteps: [
      t("Ejecute una revisión rápida de identidad, red y datos.", "Run a quick review of identity, network, and data."),
      t("Priorice los tres controles con mayor reducción de riesgo.", "Prioritize the three controls with the highest risk reduction."),
      t("Defina responsables de operación y revisión periódica.", "Define owners for operations and periodic review."),
    ],
  },
  "cloud-foundation-dr-and-backup": {
    overview: t("Proteja aplicaciones y datos críticos con respaldo, recuperación y continuidad diseñados para SMB.", "Protect critical applications and data with backup, recovery, and continuity designed for SMBs."),
    businessChallenge: t("La pérdida de datos o una interrupción puede detener ventas, atención y operación. Muchas pymes no prueban recuperación hasta que ocurre un incidente.", "Data loss or downtime can stop sales, service, and operations. Many SMBs do not test recovery until an incident happens."),
    bestFitScenarios: [
      t("ERP, bases de datos, sitios web o archivos críticos.", "ERP, databases, websites, or critical files."),
      t("Empresas sin pruebas regulares de recuperación.", "Businesses without regular recovery tests."),
      t("Operaciones con ventanas limitadas de interrupción.", "Operations with limited downtime windows."),
    ],
    businessOutcomes: [
      t("Reducir impacto de errores, ransomware o fallas.", "Reduce impact from errors, ransomware, or failures."),
      t("Definir tiempos de recuperación realistas.", "Define realistic recovery times."),
      t("Aumentar confianza en continuidad operativa.", "Increase confidence in operational continuity."),
    ],
    recommendedCapabilities: [
      t("Respaldo automatizado y políticas de retención.", "Automated backup and retention policies."),
      t("Restauración validada con ejercicios prácticos.", "Validated restoration through practical drills."),
      t("Monitoreo de cumplimiento de respaldos.", "Monitoring of backup compliance."),
    ],
    adoptionPath: standardPath,
    beforeYouStart: [
      t("Lista de sistemas críticos y prioridad de recuperación.", "List of critical systems and recovery priority."),
      t("Objetivos RPO/RTO aproximados.", "Approximate RPO/RTO targets."),
      t("Ventanas de mantenimiento y contactos de aprobación.", "Maintenance windows and approval contacts."),
    ],
    successMeasures: [
      t("Respaldos completados según política.", "Backups completed according to policy."),
      t("Restauración probada con evidencia.", "Restoration tested with evidence."),
      t("RTO/RPO medidos y aceptados por negocio.", "RTO/RPO measured and accepted by the business."),
    ],
    faq: [
      {
        question: t("¿Backup es lo mismo que continuidad?", "Is backup the same as continuity?"),
        answer: t("No. Backup guarda datos; continuidad exige saber qué restaurar, en qué orden, cuánto tarda y quién decide.", "No. Backup stores data; continuity requires knowing what to restore, in what order, how long it takes, and who decides."),
      },
    ],
    nextSteps: [
      t("Clasifique aplicaciones por criticidad.", "Classify applications by criticality."),
      t("Defina objetivos de recuperación con el negocio.", "Define recovery targets with the business."),
      t("Ejecute una primera prueba de restauración.", "Run a first restoration test."),
    ],
  },
  "application-modernization-datacenter-migration-into-cloud": {
    overview: t("Planifique la migración de servidores y aplicaciones a cloud con menor interrupción y una ruta clara por oleadas.", "Plan the migration of servers and applications to cloud with lower disruption and a clear wave-based path."),
    businessChallenge: t("Migrar sin inventario, dependencias y criterios de éxito claros puede generar interrupciones, costos inesperados y baja aceptación.", "Migrating without clear inventory, dependencies, and success criteria can create downtime, unexpected cost, and low adoption."),
    bestFitScenarios: [
      t("Renovación de infraestructura o salida de datacenter.", "Infrastructure refresh or datacenter exit."),
      t("Aplicaciones que requieren elasticidad o mejor continuidad.", "Applications needing elasticity or better continuity."),
      t("Empresas que quieren ordenar costos y operación.", "Businesses that want clearer cost and operations."),
    ],
    businessOutcomes: [
      t("Reducir riesgo de migración con oleadas controladas.", "Reduce migration risk with controlled waves."),
      t("Mejorar escalabilidad y visibilidad operativa.", "Improve scalability and operational visibility."),
      t("Construir una base para modernización posterior.", "Build a foundation for later modernization."),
    ],
    recommendedCapabilities: [
      t("Evaluación de cargas y dependencias.", "Workload and dependency assessment."),
      t("ECS, EVS, red, seguridad y respaldo.", "ECS, EVS, networking, security, and backup."),
      t("Plan de pruebas, cutover y rollback.", "Testing, cutover, and rollback plan."),
    ],
    adoptionPath: standardPath,
    beforeYouStart: [
      t("Inventario de servidores, aplicaciones y dependencias.", "Inventory of servers, applications, and dependencies."),
      t("Ventanas de cambio y criticidad por aplicación.", "Change windows and criticality by application."),
      t("Costos actuales y restricciones técnicas.", "Current costs and technical constraints."),
    ],
    successMeasures: [
      t("Migración piloto sin impacto crítico.", "Pilot migration without critical impact."),
      t("Rendimiento y disponibilidad validados.", "Performance and availability validated."),
      t("Costo mensual estimado comparado con línea base.", "Monthly estimated cost compared with baseline."),
    ],
    faq: [
      {
        question: t("¿Tengo que migrar todo al mismo tiempo?", "Do I have to migrate everything at once?"),
        answer: t("No. Para SMB es más seguro empezar con una ola piloto y avanzar por prioridad y dependencia.", "No. For SMBs it is safer to start with a pilot wave and move by priority and dependency."),
      },
    ],
    nextSteps: [
      t("Use el cotizador RVTools para una primera estimación.", "Use the RVTools estimator for an initial estimate."),
      t("Seleccione una aplicación piloto.", "Select one pilot application."),
      t("Defina criterios de cutover y rollback.", "Define cutover and rollback criteria."),
    ],
  },
  "application-modernization-sap-on-cloud": {
    overview: t("Ejecute SAP sobre una base cloud preparada para disponibilidad, respaldo, rendimiento y crecimiento.", "Run SAP on a cloud foundation prepared for availability, backup, performance, and growth."),
    businessChallenge: t("SAP suele ser crítico para finanzas, inventario y operación. Cambios de infraestructura requieren evaluación cuidadosa para evitar impacto al negocio.", "SAP is often critical for finance, inventory, and operations. Infrastructure changes require careful assessment to avoid business impact."),
    bestFitScenarios: [
      t("Renovación de hardware o crecimiento de capacidad SAP.", "Hardware refresh or SAP capacity growth."),
      t("Necesidad de mejor respaldo y continuidad.", "Need for better backup and continuity."),
      t("Preparación para modernizar datos y analítica alrededor de SAP.", "Preparing to modernize data and analytics around SAP."),
    ],
    businessOutcomes: [
      t("Mayor flexibilidad para capacidad y ambientes.", "More flexibility for capacity and environments."),
      t("Mejor recuperación y operación controlada.", "Better recovery and controlled operations."),
      t("Base para integración con datos e IA.", "Foundation for data and AI integration."),
    ],
    recommendedCapabilities: [
      t("Arquitectura SAP dimensionada por carga.", "SAP architecture sized by workload."),
      t("Computación, almacenamiento y red para sistemas críticos.", "Compute, storage, and networking for critical systems."),
      t("Respaldo, monitoreo y plan de recuperación.", "Backup, monitoring, and recovery plan."),
    ],
    adoptionPath: standardPath,
    beforeYouStart: [
      t("Versiones SAP, base de datos, tamaño y uso actual.", "SAP versions, database, size, and current usage."),
      t("Ventanas permitidas y procesos críticos.", "Allowed windows and critical processes."),
      t("Requisitos de disponibilidad, respaldo y cumplimiento.", "Availability, backup, and compliance requirements."),
    ],
    successMeasures: [
      t("Rendimiento validado para procesos críticos.", "Performance validated for critical processes."),
      t("Plan de respaldo y recuperación probado.", "Backup and recovery plan tested."),
      t("Operación y responsabilidades claras.", "Clear operations and responsibilities."),
    ],
    faq: [
      {
        question: t("¿Es un cambio solo técnico?", "Is this only a technical change?"),
        answer: t("No. SAP impacta procesos clave; negocio e IT deben validar ventanas, rendimiento y continuidad.", "No. SAP impacts key processes; business and IT must validate windows, performance, and continuity."),
      },
    ],
    nextSteps: [
      t("Reúna información de sizing y dependencias SAP.", "Gather SAP sizing and dependency information."),
      t("Defina un escenario piloto o ambiente no productivo.", "Define a pilot scenario or non-production environment."),
      t("Alinee criterios de rendimiento y continuidad.", "Align performance and continuity criteria."),
    ],
  },
};
