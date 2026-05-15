export type Lang = "es" | "en";

type Copy = {
  nav: {
    home: string;
    highlights: string;
    solutions: string;
    quote: string;
    journey: string;
    resources: string;
  };
  hero: {
    eyebrow: string;
    title: string;
    body: string;
    primary: string;
    secondary: string;
  };
  stats: Array<{ label: string; value: string; note: string }>;
  sections: {
    latam: string;
    latamBody: string;
    highlights: string;
    highlightsBody: string;
    solutions: string;
    solutionsBody: string;
    journey: string;
    journeyBody: string;
    resources: string;
  };
  solutions: {
    cards: string;
    services: string;
    detail: string;
    guidance: string;
    outcomes: string;
    close: string;
  };
  journey: Array<{ title: string; body: string }>;
  resources: Array<{ label: string; href: string; description: string }>;
};

export const copy: Record<Lang, Copy> = {
  es: {
    nav: {
      home: "Inicio",
      highlights: "Highlights",
      solutions: "Soluciones",
      quote: "Cotizador cloud",
      journey: "Roadmap",
      resources: "Recursos",
    },
    hero: {
      eyebrow: "Huawei LATAM SMB Solutions",
      title: "Soluciones digitales para pymes en Latinoamérica",
      body:
        "Impulsa la digitalización con capacidades de cloud, IA, datos, seguridad, conectividad y aplicaciones empresariales diseñadas para empresas pequeñas y medianas en la región.",
      primary: "Ver highlights",
      secondary: "Explorar soluciones",
    },
    stats: [
      { label: "Presencia global", value: "170+", note: "Países y regiones donde opera Huawei" },
      { label: "Personas atendidas", value: "3B+", note: "Usuarios servidos por soluciones Huawei" },
      { label: "Capacidad LATAM", value: "5", note: "Regiones cloud listadas para escenarios locales" },
      { label: "Módulos", value: "48", note: "Portafolio organizado por necesidad de negocio" },
    ],
    sections: {
      latam: "Base digital para el crecimiento SMB en LATAM",
      latamBody:
        "La propuesta combina capacidades de cloud, IA, datos, seguridad, conectividad y aplicaciones para escenarios frecuentes: sitios y apps, ERP/SAP, respaldo, sucursales, automatización y analítica.",
      highlights: "Lo más relevante para pymes",
      highlightsBody:
        "Resumen ejecutivo de prioridades digitales para empresas pequeñas y medianas en Latinoamérica.",
      solutions: "Solution Playbook para SMB",
      solutionsBody:
        "Empiece por tres puertas de entrada comerciales y convierta la conversación en ocho escenarios concretos con skill de GitHub, propuesta de valor y pasos rápidos de integración.",
      journey: "Roadmap digital recomendado para SMB",
      journeyBody:
        "Una pyme no necesita adoptar todo a la vez. La ruta prioriza una base segura, procesos críticos, datos y después IA con medición.",
      resources: "Recursos públicos",
    },
    solutions: {
      cards: "módulos",
      services: "Servicios sugeridos",
      detail: "Ver detalles",
      guidance: "Cómo empezar",
      outcomes: "Indicadores de éxito",
      close: "Cerrar",
    },
    journey: [
      {
        title: "1. Evaluar la oportunidad",
        body: "Identificar procesos, sedes, cargas, riesgos, costos y datos donde una solución digital aporta valor inmediato.",
      },
      {
        title: "2. Construir la base",
        body: "Definir conectividad, identidad, seguridad, respaldo y monitoreo antes de modernizar procesos críticos.",
      },
      {
        title: "3. Migrar y modernizar",
        body: "Ejecutar oleadas por prioridad: websites, apps, ERP/SAP, bases de datos y contenedores.",
      },
      {
        title: "4. Activar datos e IA",
        body: "Centralizar datos, crear bases de conocimiento empresariales y lanzar casos de IA medibles.",
      },
      {
        title: "5. Optimizar y escalar",
        body: "Medir disponibilidad, costo y productividad para ampliar las soluciones que generan más valor.",
      },
    ],
    resources: [
      {
        label: "Huawei Cloud International",
        href: "https://www.huaweicloud.com/intl/en-us/",
        description: "Productos, soluciones y casos publicados en el portal internacional.",
      },
      {
        label: "Global Infrastructure",
        href: "https://www.huaweicloud.com/intl/en-us/about/global-infrastructure.html",
        description: "Cobertura global, regiones, AZ, POP y red.",
      },
      {
        label: "LATAM Regions",
        href: "https://support.huaweicloud.com/intl/en-us/productdesc-cc/cc_01_0003.html",
        description: "Regiones de Huawei Cloud por geografía, incluyendo LATAM.",
      },
    ],
  },
  en: {
    nav: {
      home: "Home",
      highlights: "Highlights",
      solutions: "Solutions",
      quote: "Cloud Estimator",
      journey: "Roadmap",
      resources: "Resources",
    },
    hero: {
      eyebrow: "Huawei LATAM SMB Solutions",
      title: "Digital solutions for SMBs in Latin America",
      body:
        "Advance digital transformation with cloud, AI, data, security, connectivity, and business application capabilities designed for small and medium-sized businesses across the region.",
      primary: "View highlights",
      secondary: "Explore solutions",
    },
    stats: [
      { label: "Global presence", value: "170+", note: "Countries and regions where Huawei operates" },
      { label: "People served", value: "3B+", note: "Users served by Huawei solutions" },
      { label: "LATAM capability", value: "5", note: "Cloud regions listed for local scenarios" },
      { label: "Modules", value: "48", note: "Portfolio organized by business need" },
    ],
    sections: {
      latam: "Digital foundation for SMB growth in LATAM",
      latamBody:
        "The solution set combines cloud, AI, data, security, connectivity, and business application capabilities for common SMB scenarios: websites and apps, ERP/SAP, backup, branches, automation, and analytics.",
      highlights: "What matters most for SMBs",
      highlightsBody:
        "An executive summary of digital priorities for small and medium-sized businesses in Latin America.",
      solutions: "SMB Solution Playbook",
      solutionsBody:
        "Start from three commercial entry points and move the conversation into eight concrete scenarios with GitHub skills, customer-facing value, and quick integration guidance.",
      journey: "Recommended SMB digital roadmap",
      journeyBody:
        "SMBs do not need to adopt every capability at once. The path prioritizes a secure foundation, critical processes, data, and then measurable AI use cases.",
      resources: "Public resources",
    },
    solutions: {
      cards: "modules",
      services: "Suggested services",
      detail: "View details",
      guidance: "How to start",
      outcomes: "Success indicators",
      close: "Close",
    },
    journey: [
      {
        title: "1. Assess the opportunity",
        body: "Identify processes, branches, workloads, risks, costs, and data where a digital solution can create immediate value.",
      },
      {
        title: "2. Build the foundation",
        body: "Define connectivity, identity, security, backup, and monitoring before modernizing critical processes.",
      },
      {
        title: "3. Migrate and modernize",
        body: "Execute waves by priority: websites, applications, ERP/SAP, databases, and containers.",
      },
      {
        title: "4. Activate data and AI",
        body: "Centralize data, build enterprise knowledge bases, and launch measurable AI use cases.",
      },
      {
        title: "5. Optimize and scale",
        body: "Measure availability, cost, and productivity to scale the solutions that create the most value.",
      },
    ],
    resources: [
      {
        label: "Huawei Cloud International",
        href: "https://www.huaweicloud.com/intl/en-us/",
        description: "Published products, solutions, and customer stories on the international portal.",
      },
      {
        label: "Global Infrastructure",
        href: "https://www.huaweicloud.com/intl/en-us/about/global-infrastructure.html",
        description: "Global regions, AZs, POPs, and network coverage.",
      },
      {
        label: "LATAM Regions",
        href: "https://support.huaweicloud.com/intl/en-us/productdesc-cc/cc_01_0003.html",
        description: "Huawei Cloud regions listed by geography, including LATAM.",
      },
    ],
  },
};
