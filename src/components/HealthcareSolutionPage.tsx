import { ArrowLeft, ArrowRight, CheckCircle2 } from "lucide-react";
import { trackClick } from "../analytics";
import type { Lang } from "../data/i18n";
import { solutionEntries, solutionScenarioMap, textFor, type LocalizedPair, type SolutionScenario } from "../data/solutions";

type HealthcareSolutionPageProps = {
  lang: Lang;
  scenarioId: string;
};

const labels = {
  es: {
    back: "Volver al playbook",
    overview: "Descripción de la solución",
    keyValue: "Valor y mejoras medibles",
    modules: "Módulos y flujos clínicos",
    architecture: "Arquitectura e infraestructura",
    products: "Base de productos Huawei",
    outcomes: "Resultados para el cliente",
    cta: "Solicitar consulta de solución",
    browseAll: "Ver todas las soluciones",
    metricImprovement: "Mejora",
    metricValue: "Valor",
  },
  en: {
    back: "Back to playbook",
    overview: "Solution overview",
    keyValue: "Key value and measurable improvements",
    modules: "Solution modules and clinical workflows",
    architecture: "Architecture and infrastructure",
    products: "Huawei product foundation",
    outcomes: "Customer outcomes",
    cta: "Request Solution Consultation",
    browseAll: "Browse all solutions",
    metricImprovement: "Improvement",
    metricValue: "Value",
  },
  zh: {
    back: "返回方案手册",
    overview: "方案概览",
    keyValue: "关键价值与可衡量提升",
    modules: "方案模块与临床流程",
    architecture: "架构与基础设施",
    products: "华为产品基础",
    outcomes: "客户结果",
    cta: "申请方案咨询",
    browseAll: "浏览全部方案",
    metricImprovement: "提升项",
    metricValue: "结果",
  },
  pg: {
    back: "Voltar ao playbook",
    overview: "Visão geral da solução",
    keyValue: "Valor principal e melhorias mensuráveis",
    modules: "Módulos da solução e fluxos clínicos",
    architecture: "Arquitetura e infraestrutura",
    products: "Base de produtos Huawei",
    outcomes: "Resultados para o cliente",
    cta: "Solicitar consulta de solução",
    browseAll: "Ver todas as soluções",
    metricImprovement: "Melhoria",
    metricValue: "Valor",
  },
} satisfies Record<Lang, Record<string, string>>;

interface HealthcareContent {
  overview: LocalizedPair[];
  keyMetrics: { metric: LocalizedPair; value: LocalizedPair }[];
  modules: { title: LocalizedPair; description: LocalizedPair; image?: string }[];
  architecturePoints: LocalizedPair[];
  products: { name: string; role: LocalizedPair }[];
  outcomes: LocalizedPair[];
}

const healthcareContent: Record<string, HealthcareContent> = {
  "ai-medical-imaging": {
    overview: [
      {
        en: "AI-Assisted Medical Imaging deploys within the hospital data center to bring artificial intelligence directly into the radiology workflow — supporting screening, diagnosis, quality control, and multi-site image collaboration.",
        es: "Imágenes Médicas Asistidas por IA se despliega en el datacenter del hospital para incorporar inteligencia artificial directamente en el flujo radiológico — apoyando cribado, diagnóstico, control de calidad y colaboración de imágenes multi-sitio.",
      },
      {
        en: "Built on Huawei AI Server and Huawei All-Flash Storage with partner AI applications, the solution integrates with existing PACS infrastructure to deliver AI inference results alongside the radiologist's standard reading workflow, reducing turnaround time and improving diagnostic consistency.",
        es: "Construida sobre Huawei AI Server y Huawei All-Flash Storage con aplicaciones IA de partner, la solución se integra con la infraestructura PACS existente para entregar resultados de inferencia IA junto al flujo de lectura estándar del radiólogo, reduciendo tiempos de respuesta y mejorando la consistencia diagnóstica.",
      },
    ],
    keyMetrics: [
      { metric: { en: "AI-assisted diagnosis efficiency", es: "Eficiencia de diagnóstico asistido por IA" }, value: { en: "+50%", es: "+50%" } },
      { metric: { en: "Diagnosis accuracy improvement", es: "Mejora de precisión diagnóstica" }, value: { en: "+10%", es: "+10%" } },
      { metric: { en: "Screening turnaround reduction", es: "Reducción de tiempo de cribado" }, value: { en: "Significant", es: "Significativa" } },
    ],
    modules: [
      {
        title: { en: "AI-Assisted Screening and Diagnosis", es: "Cribado y Diagnóstico Asistidos por IA" },
        description: { en: "Automated detection of abnormalities in chest X-ray, bone fracture, and lung cancer screening with configurable confidence thresholds and radiologist review workflow.", es: "Detección automática de anomalías en radiografía de tórax, fracturas y cribado de cáncer pulmonar con umbrales de confianza configurables y flujo de revisión radiológica." },
        image: "/assets/huawei/enterprise-healthcare/medical-imaging-chest-xray.png",
      },
      {
        title: { en: "Image Quality Control", es: "Control de Calidad de Imágenes" },
        description: { en: "Automated quality assessment of incoming DICOM images to reject or flag sub-standard acquisitions before they reach the radiologist worklist.", es: "Evaluación automática de calidad de imágenes DICOM entrantes para rechazar o marcar adquisiciones deficientes antes de llegar a la lista de trabajo del radiólogo." },
      },
      {
        title: { en: "Image Sharing and Collaboration", es: "Intercambio y Colaboración de Imágenes" },
        description: { en: "Secure cross-department and cross-site image sharing with real-time annotation, 3D reconstruction, and collaborative viewing for multidisciplinary tumor boards.", es: "Intercambio seguro de imágenes entre departamentos y sitios con anotación en tiempo real, reconstrucción 3D y visualización colaborativa para comités de tumores multidisciplinarios." },
        image: "/assets/huawei/enterprise-healthcare/medical-imaging-storage.png",
      },
      {
        title: { en: "3D Imaging and Advanced Visualization", es: "Imágenes 3D y Visualización Avanzada" },
        description: { en: "3D volume rendering and multi-planar reconstruction from standard CT/MRI datasets, accessible from clinical workstations on the hospital network.", es: "Renderizado volumétrico 3D y reconstrucción multi-planar desde datasets CT/RMI estándar, accesible desde estaciones clínicas en la red hospitalaria." },
      },
    ],
    architecturePoints: [
      { en: "Hospital imaging systems and PACS feed DICOM images into the AI inference pipeline.", es: "Sistemas de imágenes hospitalarias y PACS alimentan imágenes DICOM al pipeline de inferencia IA." },
      { en: "Huawei AI Server runs partner AI applications for chest X-ray, bone fracture, and lung cancer diagnosis.", es: "Huawei AI Server ejecuta aplicaciones IA de partner para diagnóstico de radiografía de tórax, fracturas y cáncer pulmonar." },
      { en: "Huawei All-Flash Storage provides high-performance medical image storage with low-latency access for active datasets.", es: "Huawei All-Flash Storage provee almacenamiento de imágenes médicas de alto rendimiento con acceso de baja latencia para datasets activos." },
      { en: "Radiologist workstations and image collaboration tools connect via hospital network for real-time review and 3D imaging.", es: "Estaciones radiológicas y herramientas de colaboración de imágenes se conectan vía red hospitalaria para revisión en tiempo real e imágenes 3D." },
    ],
    products: [
      { name: "Huawei AI Server", role: { en: "AI-assisted screening and diagnosis compute", es: "Compute para cribado y diagnóstico asistidos por IA" } },
      { name: "Huawei All-Flash Storage", role: { en: "High-performance medical image storage", es: "Almacenamiento de imágenes médicas de alto rendimiento" } },
      { name: "Partner AI Application", role: { en: "Chest X-ray, bone fracture, and lung cancer diagnosis", es: "Diagnóstico de radiografía de tórax, fracturas y cáncer pulmonar" } },
      { name: "PACS Integration", role: { en: "DICOM gateway and radiology workflow", es: "Gateway DICOM y flujo radiológico" } },
      { name: "Clinical Workstation", role: { en: "Image viewing, collaboration, and 3D visualization", es: "Visualización de imágenes, colaboración y visualización 3D" } },
    ],
    outcomes: [
      { en: "Radiologists focus on complex cases while AI handles routine screening triage.", es: "Los radiólogos se enfocan en casos complejos mientras la IA maneja el triaje rutinario de cribado." },
      { en: "Diagnostic consistency improves across shifts, sites, and experience levels.", es: "La consistencia diagnóstica mejora entre turnos, sitios y niveles de experiencia." },
      { en: "Multi-site image collaboration eliminates physical media and courier delays.", es: "La colaboración de imágenes multi-sitio elimina medios físicos y demoras de mensajería." },
    ],
  },
  "digital-pathology": {
    overview: [
      {
        en: "Digital Pathology transforms physical slide workflows into a fully digital pipeline deployed on-premises in the hospital — from whole-slide scanning and pyramid-structured storage to sub-second retrieval and collaborative viewing.",
        es: "Patología Digital transforma los flujos de laminillas físicas en un pipeline completamente digital desplegado on-premise en el hospital — desde escaneo de laminillas completas y almacenamiento piramidal hasta recuperación sub-segundo y visualización colaborativa.",
      },
      {
        en: "Built on Huawei AI Server and Huawei All-Flash Storage, pathologists access full-resolution slides from standard PC workstations or mobile devices without upgrading hospital network infrastructure or client endpoints, enabling immediate cross-site consultation and second opinions.",
        es: "Construida sobre Huawei AI Server y Huawei All-Flash Storage, los patólogos acceden a laminillas de resolución completa desde estaciones PC estándar o dispositivos móviles sin actualizar la infraestructura de red hospitalaria ni los endpoints, habilitando consulta inmediata entre sitios y segundas opiniones.",
      },
    ],
    keyMetrics: [
      { metric: { en: "Image retrieval time", es: "Tiempo de recuperación de imágenes" }, value: { en: "< 1 second", es: "< 1 segundo" } },
      { metric: { en: "Storage space savings", es: "Ahorro de espacio de almacenamiento" }, value: { en: "30%", es: "30%" } },
      { metric: { en: "Network/client upgrade needed", es: "Actualización de red/cliente necesaria" }, value: { en: "None", es: "Ninguna" } },
    ],
    modules: [
      {
        title: { en: "Whole-Slide Digitization", es: "Digitalización de Laminillas Completas" },
        description: { en: "High-throughput whole-slide scanning with automated quality control, barcode tracking, and direct ingestion into the digital storage pipeline.", es: "Escaneo de alto rendimiento de laminillas completas con control de calidad automático, seguimiento por código de barras e ingestión directa al pipeline de almacenamiento digital." },
        image: "/assets/huawei/enterprise-healthcare/digital-pathology-detail.png",
      },
      {
        title: { en: "Pyramid-Structured Storage and Retrieval", es: "Almacenamiento y Recuperación Piramidal" },
        description: { en: "Multi-resolution pyramid encoding stores each slide at multiple zoom levels, enabling sub-second retrieval at any magnification without transferring the full dataset.", es: "Codificación piramidal multi-resolución almacena cada laminilla en múltiples niveles de zoom, permitiendo recuperación sub-segundo a cualquier magnificación sin transferir el dataset completo." },
        image: "/assets/huawei/enterprise-healthcare/digital-pathology-layers.png",
      },
      {
        title: { en: "PC and Mobile Slide Viewing", es: "Visualización de Laminillas en PC y Móvil" },
        description: { en: "Real-time shared viewing with synchronized panning, zooming, and annotation from standard PCs and mobile devices — no special hardware or software installation required.", es: "Visualización compartida en tiempo real con paneo, zoom y anotación sincronizados desde PCs estándar y dispositivos móviles — sin requerir hardware especial ni instalación de software." },
      },
      {
        title: { en: "Hospital-Wide Data Security", es: "Seguridad de Datos Hospitalaria" },
        description: { en: "End-to-end encryption at rest and in transit, role-based access control, full audit logging, and compliance-ready retention policies for patient image data.", es: "Cifrado extremo a extremo en reposo y tránsito, control de acceso por roles, logging de auditoría completo y políticas de retención listas para cumplimiento de datos de imágenes de pacientes." },
      },
    ],
    architecturePoints: [
      { en: "Whole-slide scanner outputs DICOM files ingested via secure gateway into pyramid encoder on Huawei AI Server.", es: "El escáner de laminillas produce archivos DICOM ingestados vía gateway seguro al codificador piramidal en Huawei AI Server." },
      { en: "Pyramid encoder generates multi-resolution tiers stored on Huawei All-Flash Storage for high-throughput active access and long-term archive.", es: "El codificador piramidal genera tiers multi-resolución almacenados en Huawei All-Flash Storage para acceso activo de alto rendimiento y archivo a largo plazo." },
      { en: "Retrieval service serves requested tile/zoom level directly from All-Flash Storage cache, avoiding full-slide transfer and enabling sub-second response.", es: "El servicio de recuperación sirve el tile/nivel de zoom solicitado directamente desde caché de All-Flash Storage, evitando transferencia completa y permitiendo respuesta sub-segundo." },
      { en: "PC and mobile slide viewers connect via hospital network without requiring endpoint upgrades or special client software.", es: "Visores de laminillas en PC y móvil se conectan vía red hospitalaria sin requerir actualización de endpoints ni software cliente especial." },
    ],
    products: [
      { name: "Huawei AI Server", role: { en: "AI computing node and pyramid encoder", es: "Nodo de cómputo IA y codificador piramidal" } },
      { name: "Huawei All-Flash Storage", role: { en: "High-performance pyramid-structured slide storage", es: "Almacenamiento piramidal de laminillas de alto rendimiento" } },
      { name: "Digital Pathology Viewer", role: { en: "PC and mobile slide viewing and annotation", es: "Visualización y anotación de laminillas en PC y móvil" } },
      { name: "LIS Integration", role: { en: "Slide metadata, ordering, and reporting", es: "Metadatos de laminillas, órdenes y reportes" } },
      { name: "Hospital Integration Layer", role: { en: "Security, access control, and audit logging", es: "Seguridad, control de acceso y logging de auditoría" } },
    ],
    outcomes: [
      { en: "Pathologists retrieve any slide at any magnification in under one second.", es: "Los patólogos recuperan cualquier laminilla a cualquier magnificación en menos de un segundo." },
      { en: "Physical slide storage and courier logistics are eliminated.", es: "El almacenamiento de laminillas físicas y la logística de mensajería se eliminan." },
      { en: "Cross-site consultation and second opinions happen in real time.", es: "La consulta entre sitios y segundas opiniones ocurren en tiempo real." },
    ],
  },
};

function MetricCard({ metric, value, lang }: { metric: LocalizedPair; value: LocalizedPair; lang: Lang }) {
  return (
    <div className="healthcare-metric-card">
      <span className="healthcare-metric-value">{textFor(lang, value)}</span>
      <span className="healthcare-metric-label">{textFor(lang, metric)}</span>
    </div>
  );
}

function ModuleCard({ title, description, image, lang }: { title: LocalizedPair; description: LocalizedPair; image?: string; lang: Lang }) {
  return (
    <div className="healthcare-module-card">
      {image && <img src={image} alt="" loading="lazy" />}
      <div className="healthcare-module-card-body">
        <h4>{textFor(lang, title)}</h4>
        <p>{textFor(lang, description)}</p>
      </div>
    </div>
  );
}

export function HealthcareSolutionPage({ lang, scenarioId }: HealthcareSolutionPageProps) {
  const l = labels[lang];
  const scenario = solutionScenarioMap[scenarioId] as SolutionScenario | undefined;
  const content = healthcareContent[scenarioId];

  if (!scenario || !content) {
    return (
      <main className="healthcare-solution-page">
        <a className="back-link" href="#/solutions">
          <ArrowLeft size={17} />
          {l.back}
        </a>
      </main>
    );
  }

  const entry = solutionEntries.find((item) => item.id === scenario.entryId) ?? solutionEntries[0];

  return (
    <main className="healthcare-solution-page">
      <a
        className="back-link"
        href={`#/solutions?entry=${entry.id}`}
        onClick={() =>
          trackClick({
            click_target: "healthcare_back",
            click_section: "healthcare_detail",
            destination: `#/solutions?entry=${entry.id}`,
            entry_id: entry.id,
            scenario_id: scenario.id,
          })
        }
      >
        <ArrowLeft size={17} />
        {l.back}
      </a>

      {/* Hero */}
      <section
        className="healthcare-hero"
        style={{ backgroundImage: `url("${scenario.heroImage}")` }}
      >
        <div className="healthcare-hero-overlay" />
        <div className="healthcare-hero-content">
          <span className="section-kicker">{textFor(lang, entry.title)}</span>
          <h1>{textFor(lang, scenario.title)}</h1>
          <p>{textFor(lang, scenario.oneLiner)}</p>
          <div className="tag-row">
            {scenario.recommendedServices.map((service) => (
              <span className="service-tag strong on-dark" key={service}>{service}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Solution Overview */}
      <section className="healthcare-section">
        <div className="healthcare-section-inner">
          <h2>{l.overview}</h2>
          {content.overview.map((para, i) => (
            <p key={i}>{textFor(lang, para)}</p>
          ))}
        </div>
      </section>

      {/* Key Value / Measurable Improvements */}
      <section className="healthcare-section healthcare-section-alt">
        <div className="healthcare-section-inner">
          <h2>{l.keyValue}</h2>
          <div className="healthcare-metrics-grid">
            {content.keyMetrics.map((km) => (
              <MetricCard key={textFor("en", km.metric)} metric={km.metric} value={km.value} lang={lang} />
            ))}
          </div>
        </div>
      </section>

      {/* Solution Modules / Clinical Workflows */}
      <section className="healthcare-section">
        <div className="healthcare-section-inner">
          <h2>{l.modules}</h2>
          <div className="healthcare-modules-grid">
            {content.modules.map((mod) => (
              <ModuleCard
                key={textFor("en", mod.title)}
                title={mod.title}
                description={mod.description}
                image={mod.image}
                lang={lang}
              />
            ))}
          </div>
        </div>
      </section>

      {/* Architecture / Infrastructure */}
      <section className="healthcare-section healthcare-section-alt">
        <div className="healthcare-section-inner">
          <h2>{l.architecture}</h2>
          <ul className="healthcare-arch-list">
            {content.architecturePoints.map((point, i) => (
              <li key={i}>
                <CheckCircle2 size={18} className="healthcare-check-icon" />
                <span>{textFor(lang, point)}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Huawei Product Foundation */}
      <section className="healthcare-section">
        <div className="healthcare-section-inner">
          <h2>{l.products}</h2>
          <div className="healthcare-products-grid">
            {content.products.map((prod) => (
              <div className="healthcare-product-card" key={prod.name}>
                <strong>{prod.name}</strong>
                <span>{textFor(lang, prod.role)}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Customer Outcomes / CTA */}
      <section className="healthcare-section healthcare-section-cta">
        <div className="healthcare-section-inner">
          <h2>{l.outcomes}</h2>
          <ul className="healthcare-outcomes-list">
            {content.outcomes.map((outcome, i) => (
              <li key={i}>
                <CheckCircle2 size={18} className="healthcare-check-icon" />
                <span>{textFor(lang, outcome)}</span>
              </li>
            ))}
          </ul>
          <div className="healthcare-cta-row">
            <a
              className="primary-action"
              href="https://e.huawei.com/en/contact-us"
              target="_blank"
              rel="noreferrer"
              onClick={() =>
                trackClick({
                  click_target: "healthcare_consultation_cta",
                  click_section: "healthcare_cta",
                  destination: "https://e.huawei.com/en/contact-us",
                  entry_id: entry.id,
                  scenario_id: scenario.id,
                })
              }
            >
              {l.cta}
              <ArrowRight size={18} />
            </a>
            <a
              className="secondary-action light"
              href="#/solutions"
              onClick={() =>
                trackClick({
                  click_target: "healthcare_browse_all",
                  click_section: "healthcare_cta",
                  destination: "#/solutions",
                  entry_id: entry.id,
                  scenario_id: scenario.id,
                })
              }
            >
              {l.browseAll}
            </a>
          </div>
        </div>
      </section>
    </main>
  );
}
