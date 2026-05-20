export type Lang = "es" | "en" | "zh";

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
  zh: {
    nav: {
      home: "首页",
      highlights: "亮点",
      solutions: "方案",
      quote: "报价器",
      journey: "路线图",
      resources: "资源",
    },
    hero: {
      eyebrow: "Huawei LATAM SMB Solutions",
      title: "面向拉美中小企业的数字化方案",
      body:
        "通过云、AI、数据、安全、连接和企业应用能力，支持拉美地区中小企业的数字化升级。",
      primary: "查看亮点",
      secondary: "浏览方案",
    },
    stats: [
      { label: "全球覆盖", value: "170+", note: "华为业务覆盖的国家和地区" },
      { label: "服务人群", value: "3B+", note: "华为方案服务的用户规模" },
      { label: "拉美能力", value: "5", note: "适用于本地场景的云区域数量" },
      { label: "方案模块", value: "48", note: "按业务需求组织的方案能力" },
    ],
    sections: {
      latam: "支撑拉美 SMB 增长的数字底座",
      latamBody:
        "方案组合覆盖云、AI、数据、安全、连接和业务应用，面向网站与应用、ERP/SAP、备份、分支、自动化和分析等常见场景。",
      highlights: "SMB 最关心的能力",
      highlightsBody:
        "面向拉美中小企业的数字化重点能力摘要。",
      solutions: "SMB 方案手册",
      solutionsBody:
        "从商业入口出发，将沟通转化为可落地的客户场景、业务价值和快速集成路径。",
      journey: "推荐的 SMB 数字化路线图",
      journeyBody:
        "中小企业不需要一次性采用全部能力，应优先建设安全底座、关键流程、数据，再逐步落地可衡量的 AI 场景。",
      resources: "公开资源",
    },
    solutions: {
      cards: "模块",
      services: "建议能力",
      detail: "查看详情",
      guidance: "如何开始",
      outcomes: "成功指标",
      close: "关闭",
    },
    journey: [
      {
        title: "1. 评估机会",
        body: "识别最能带来业务价值的流程、系统、成本、风险与数据场景。",
      },
      {
        title: "2. 建设底座",
        body: "在关键流程现代化之前，先明确连接、身份、安全、备份与监控。",
      },
      {
        title: "3. 迁移与现代化",
        body: "按优先级推进网站、应用、ERP/SAP、数据库和容器等能力升级。",
      },
      {
        title: "4. 激活数据与 AI",
        body: "集中数据、建设知识库，并启动可衡量的 AI 用例。",
      },
      {
        title: "5. 优化与扩展",
        body: "持续衡量可用性、成本和效率，扩大最有价值的方案。",
      },
    ],
    resources: [
      {
        label: "Huawei Cloud International",
        href: "https://www.huaweicloud.com/intl/en-us/",
        description: "国际站公开产品、方案与客户案例。",
      },
      {
        label: "Global Infrastructure",
        href: "https://www.huaweicloud.com/intl/en-us/about/global-infrastructure.html",
        description: "全球区域、AZ、POP 与网络覆盖。",
      },
      {
        label: "LATAM Regions",
        href: "https://support.huaweicloud.com/intl/en-us/productdesc-cc/cc_01_0003.html",
        description: "包含拉美在内的华为云区域信息。",
      },
    ],
  },
};
