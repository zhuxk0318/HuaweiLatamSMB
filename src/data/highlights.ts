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
    },
    body: {
      es: "Modelos como servicio, asistentes, agentes y análisis inteligente ayudan a automatizar atención, operaciones, ventas y toma de decisiones.",
      en: "Model-as-a-service, assistants, agents, and intelligent analytics help automate support, operations, sales, and decision-making.",
    },
  },
  {
    icon: "security",
    title: {
      es: "Seguridad y continuidad desde el diseño",
      en: "Security and continuity by design",
    },
    body: {
      es: "Controles de identidad, red, respaldo, recuperación y cumplimiento permiten operar cargas críticas con mayor confianza.",
      en: "Identity, networking, backup, recovery, and compliance controls help run critical workloads with greater confidence.",
    },
  },
  {
    icon: "migration",
    title: {
      es: "Migración y modernización de extremo a extremo",
      en: "End-to-end migration and modernization",
    },
    body: {
      es: "Herramientas y servicios para servidores, bases de datos, almacenamiento, contenedores y datos reducen la complejidad de la modernización.",
      en: "Tools and services for servers, databases, storage, containers, and data reduce modernization complexity.",
    },
  },
  {
    icon: "local",
    title: {
      es: "Cobertura local para experiencias regionales",
      en: "Local coverage for regional experiences",
    },
    body: {
      es: "Regiones y servicios en Latinoamérica acercan aplicaciones, datos y soporte a clientes y usuarios locales.",
      en: "Regions and services in Latin America bring applications, data, and support closer to local customers and users.",
    },
  },
  {
    icon: "cost",
    title: {
      es: "Escalamiento flexible y control de costos",
      en: "Flexible scaling and cost control",
    },
    body: {
      es: "Recursos flexibles, pago por crecimiento y servicios administrados ayudan a alinear capacidad digital con necesidades reales del negocio.",
      en: "Flexible resources, pay-as-you-grow models, and managed services help align digital capacity with real business needs.",
    },
  },
  {
    icon: "smb",
    title: {
      es: "Escenarios listos para pymes",
      en: "Ready scenarios for SMBs",
    },
    body: {
      es: "Websites, aplicaciones, ERP/SAP, respaldo, seguridad, datos e IA se presentan como rutas de adopción claras y accionables.",
      en: "Websites, applications, ERP/SAP, backup, security, data, and AI are organized into clear, actionable adoption paths.",
    },
  },
];
