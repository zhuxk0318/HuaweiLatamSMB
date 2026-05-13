import type { Lang } from "./i18n";

export type Highlight = {
  icon: "ai" | "security" | "migration" | "local" | "cost" | "smb";
  title: Record<Lang, string>;
  body: Record<Lang, string>;
};

export const highlights: Highlight[] = [
  {
    icon: "ai",
    title: {
      es: "IA práctica para la próxima etapa digital",
      en: "Practical AI for the next digital phase",
      zh: "面向下一阶段数字化的实用 AI",
    },
    body: {
      es: "Modelos como servicio, asistentes, agentes y análisis inteligente ayudan a automatizar atención, operaciones, ventas y toma de decisiones.",
      en: "Model-as-a-service, assistants, agents, and intelligent analytics help automate support, operations, sales, and decision-making.",
      zh: "通过 MaaS、智能助手、智能体和智能分析，帮助企业自动化客服、运营、销售和决策流程。",
    },
  },
  {
    icon: "security",
    title: {
      es: "Seguridad y continuidad desde el diseño",
      en: "Security and continuity by design",
      zh: "以安全与连续性为设计基础",
    },
    body: {
      es: "Controles de identidad, red, respaldo, recuperación y cumplimiento permiten operar cargas críticas con mayor confianza.",
      en: "Identity, networking, backup, recovery, and compliance controls help run critical workloads with greater confidence.",
      zh: "通过身份、网络、备份、恢复和合规控制，让关键业务负载运行得更稳健可信。",
    },
  },
  {
    icon: "migration",
    title: {
      es: "Migración y modernización de extremo a extremo",
      en: "End-to-end migration and modernization",
      zh: "端到端迁移与现代化",
    },
    body: {
      es: "Herramientas y servicios para servidores, bases de datos, almacenamiento, contenedores y datos reducen la complejidad de la modernización.",
      en: "Tools and services for servers, databases, storage, containers, and data reduce modernization complexity.",
      zh: "面向服务器、数据库、存储、容器和数据的工具与服务，降低迁移和现代化复杂度。",
    },
  },
  {
    icon: "local",
    title: {
      es: "Cobertura local para experiencias regionales",
      en: "Local coverage for regional experiences",
      zh: "本地覆盖支撑区域体验",
    },
    body: {
      es: "Regiones y servicios en Latinoamérica acercan aplicaciones, datos y soporte a clientes y usuarios locales.",
      en: "Regions and services in Latin America bring applications, data, and support closer to local customers and users.",
      zh: "拉美区域内的 Region 和服务能力，让应用、数据和支持更贴近本地客户与用户。",
    },
  },
  {
    icon: "cost",
    title: {
      es: "Escalamiento flexible y control de costos",
      en: "Flexible scaling and cost control",
      zh: "弹性扩展与成本控制",
    },
    body: {
      es: "Recursos flexibles, pago por crecimiento y servicios administrados ayudan a alinear capacidad digital con necesidades reales del negocio.",
      en: "Flexible resources, pay-as-you-grow models, and managed services help align digital capacity with real business needs.",
      zh: "通过弹性资源、按增长付费和托管服务，让数字化能力更贴合真实业务需求。",
    },
  },
  {
    icon: "smb",
    title: {
      es: "Escenarios listos para pymes",
      en: "Ready scenarios for SMBs",
      zh: "面向 SMB 的高频场景",
    },
    body: {
      es: "Websites, aplicaciones, ERP/SAP, respaldo, seguridad, datos e IA se presentan como rutas de adopción claras y accionables.",
      en: "Websites, applications, ERP/SAP, backup, security, data, and AI are organized into clear, actionable adoption paths.",
      zh: "围绕网站、应用、ERP/SAP、备份、安全、数据和 AI，形成清晰可执行的采用路径。",
    },
  },
];
