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
      zh: "模型即服务、助手、代理和智能分析有助于自动化客服、运营、销售与决策。",
    },
  },
  {
    icon: "security",
    title: {
      es: "Seguridad y continuidad desde el diseño",
      en: "Security and continuity by design",
      zh: "从设计之初兼顾安全与连续性",
    },
    body: {
      es: "Controles de identidad, red, respaldo, recuperación y cumplimiento permiten operar cargas críticas con mayor confianza.",
      en: "Identity, networking, backup, recovery, and compliance controls help run critical workloads with greater confidence.",
      zh: "身份、网络、备份、恢复和合规控制帮助关键业务更稳健运行。",
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
      zh: "围绕服务器、数据库、存储、容器和数据的能力可以降低现代化复杂度。",
    },
  },
  {
    icon: "local",
    title: {
      es: "Cobertura local para experiencias regionales",
      en: "Local coverage for regional experiences",
      zh: "本地覆盖支撑区域化体验",
    },
    body: {
      es: "Regiones y servicios en Latinoamérica acercan aplicaciones, datos y soporte a clientes y usuarios locales.",
      en: "Regions and services in Latin America bring applications, data, and support closer to local customers and users.",
      zh: "拉美本地区域和服务让应用、数据与支持更贴近本地客户和用户。",
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
      zh: "弹性资源、按需增长和托管服务帮助企业让数字能力与真实业务需求匹配。",
    },
  },
  {
    icon: "smb",
    title: {
      es: "Escenarios listos para pymes",
      en: "Ready scenarios for SMBs",
      zh: "面向 SMB 的现成场景",
    },
    body: {
      es: "Websites, aplicaciones, ERP/SAP, respaldo, seguridad, datos e IA se presentan como rutas de adopción claras y accionables.",
      en: "Websites, applications, ERP/SAP, backup, security, data, and AI are organized into clear, actionable adoption paths.",
      zh: "网站、应用、ERP/SAP、备份、安全、数据和 AI 能力被整理成清晰可执行的采用路径。",
    },
  },
];
