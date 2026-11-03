import { ArrowRight, Boxes, ChevronRight, ClipboardCheck, CloudUpload, MessageCircle } from "lucide-react";
import { trackClick } from "../../analytics";
import type { Lang } from "../../data/i18n";

const heroCopy = {
  es: {
    title: "Migración y modernización de aplicaciones",
    subtitle:
      "Rutas prácticas para mover cargas, bases de datos, escritorios virtuales y contenedores desde cualquier nube o datacenter hacia Huawei Cloud.",
    capabilities: ["Evaluación", "Migración", "Modernización"],
    primary: "Comenzar migración",
    secondary: "Hablar con un experto en migración",
  },
  en: {
    title: "Migration and Application Modernization",
    subtitle:
      "Practical paths for moving workloads, databases, virtual desktops, and containers from any cloud or datacenter into Huawei Cloud.",
    capabilities: ["Assessment", "Migration", "Modernization"],
    primary: "Start Migration",
    secondary: "Talk to Migration Expert",
  },
  zh: {
    title: "迁移与应用现代化",
    subtitle: "从任意云或数据中心将工作负载、数据库、虚拟桌面和容器迁移到华为云的实用路径。",
    capabilities: ["评估", "迁移", "现代化"],
    primary: "开始迁移",
    secondary: "咨询迁移专家",
  },
  pg: {
    title: "Migration and Application Modernization",
    subtitle:
      "Practical paths for moving workloads, databases, virtual desktops, and containers from any cloud or datacenter into Huawei Cloud.",
    capabilities: ["Assessment", "Migration", "Modernization"],
    primary: "Start Migration",
    secondary: "Talk to Migration Expert",
  },
} satisfies Record<
  Lang,
  {
    title: string;
    subtitle: string;
    capabilities: string[];
    primary: string;
    secondary: string;
  }
>;

const networkNodes = [
  { label: "AWS", x: 124, y: 126 },
  { label: "Azure", x: 344, y: 78 },
  { label: "VMware", x: 584, y: 136 },
  { label: "Google Cloud", x: 614, y: 306 },
  { label: "Kubernetes", x: 484, y: 452 },
  { label: "SAP", x: 250, y: 452 },
  { label: "OpenStack", x: 108, y: 310 },
];

const center = { x: 360, y: 280 };

function connectionPath(x: number, y: number) {
  const controlX = (x + center.x) / 2;
  const controlY = (y + center.y) / 2 - 32;
  return `M ${x} ${y} Q ${controlX} ${controlY} ${center.x} ${center.y}`;
}

export function MigrationHeroBanner({ lang }: { lang: Lang }) {
  const copy = heroCopy[lang];

  return (
    <section className="hero-section cloud-hero migration-hero-banner" aria-labelledby="migration-hero-title">
      <div className="cloud-hero-background" aria-hidden="true">
        <span className="cloud-hero-orb cloud-hero-orb-primary" />
        <span className="cloud-hero-orb cloud-hero-orb-secondary" />
        <span className="cloud-hero-particle cloud-hero-particle-one" />
        <span className="cloud-hero-particle cloud-hero-particle-two" />
        <span className="cloud-hero-particle cloud-hero-particle-three" />
      </div>

      <div className="cloud-hero-inner">
        <div className="cloud-hero-copy">
          <h1 id="migration-hero-title">{copy.title}</h1>
          <p className="cloud-hero-subtitle">{copy.subtitle}</p>

          <ul className="cloud-hero-capabilities" aria-label="Cloud migration service capabilities">
            {copy.capabilities.map((item, index) => {
              const Icon = [ClipboardCheck, CloudUpload, Boxes][index];
              return (
                <li key={item}>
                  <span className="migration-capability">
                    <span className="migration-capability-icon"><Icon size={25} aria-hidden="true" /></span>
                    <span>{item}</span>
                  </span>
                  {index < copy.capabilities.length - 1 ? <ChevronRight className="migration-capability-arrow" size={24} aria-hidden="true" /> : null}
                </li>
              );
            })}
          </ul>

          <div className="hero-actions cloud-hero-actions">
            <a
              className="primary-action cloud-hero-primary"
              href="#/migration"
              onClick={(event) => {
                event.preventDefault();
                document.getElementById("migration-scenarios")?.scrollIntoView({ behavior: "smooth" });
                trackClick({
                  click_target: "migration_hero_start_migration",
                  click_section: "migration_hero",
                  destination: "#/migration#migration-scenarios",
                });
              }}
            >
              {copy.primary}
              <ArrowRight size={20} />
            </a>
            <a
              className="secondary-action cloud-hero-secondary"
              href="https://www.huaweicloud.com/intl/en-us/contact-sales.html"
              target="_blank"
              rel="noreferrer"
              onClick={() =>
                trackClick({
                  click_target: "migration_hero_talk_to_expert",
                  click_section: "migration_hero",
                  destination: "https://www.huaweicloud.com/intl/en-us/contact-sales.html",
                })
              }
            >
              <MessageCircle size={20} />
              {copy.secondary}
            </a>
          </div>
        </div>

        <div className="cloud-hero-visual" aria-label="Source platforms connected to Huawei Cloud">
          <div className="cloud-network-card">
            <svg
              className="cloud-network-svg"
              viewBox="0 0 720 560"
              role="img"
              aria-labelledby="migration-network-title migration-network-desc"
            >
              <title id="migration-network-title">Cloud migration network</title>
              <desc id="migration-network-desc">
                AWS, Azure, VMware, Google Cloud, OpenStack, Kubernetes, and SAP connected to Huawei Cloud.
              </desc>
              <defs>
                <radialGradient id="migrationCenterGlow" cx="50%" cy="50%" r="58%">
                  <stop offset="0%" stopColor="#ffffff" stopOpacity="0.98" />
                  <stop offset="42%" stopColor="#ffe7ea" stopOpacity="0.68" />
                  <stop offset="100%" stopColor="#c7000b" stopOpacity="0" />
                </radialGradient>
                <linearGradient id="migrationLinkGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#8f98a8" stopOpacity="0.16" />
                  <stop offset="48%" stopColor="#c7000b" stopOpacity="0.58" />
                  <stop offset="100%" stopColor="#f14a55" stopOpacity="0.62" />
                </linearGradient>
                <filter id="migrationSoftGlow" x="-35%" y="-35%" width="170%" height="170%">
                  <feGaussianBlur stdDeviation="7" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              <g className="network-low-poly" aria-hidden="true">
                <path d="M96 196 L248 78 L424 112 Z" />
                <path d="M424 112 L620 210 L488 438 Z" />
                <path d="M98 332 L248 78 L488 438 Z" />
              </g>

              <g className="network-links">
                {networkNodes.map((node) => {
                  const path = connectionPath(node.x, node.y);
                  return (
                    <g key={`link-${node.label}`}>
                      <path className="network-link" d={path} />
                      <path className="network-link-flow" d={path} />
                      <circle className="network-pulse" r="4">
                        <animateMotion
                          dur={`${5.4 + (node.x % 5) * 0.35}s`}
                          begin={`${(node.y % 7) * 0.24}s`}
                          repeatCount="indefinite"
                          path={path}
                        />
                      </circle>
                    </g>
                  );
                })}
              </g>

              <g className="network-center-node" filter="url(#migrationSoftGlow)">
                <circle cx={center.x} cy={center.y} r="104" fill="url(#migrationCenterGlow)" />
                <circle className="network-center-ring" cx={center.x} cy={center.y} r="72" />
                <circle className="network-center-core" cx={center.x} cy={center.y} r="58" />
                <text x={center.x} y={center.y - 7} textAnchor="middle">Huawei</text>
                <text x={center.x} y={center.y + 28} textAnchor="middle">Cloud</text>
              </g>

              <g className="network-nodes">
                {networkNodes.map((node) => (
                  <g
                    className="network-node"
                    key={node.label}
                    style={{ animationDelay: `${(node.x + node.y) % 4}s` }}
                  >
                    <circle className="network-node-glow" cx={node.x} cy={node.y} r="46" />
                    <rect x={node.x - 62} y={node.y - 28} width="124" height="56" rx="18" />
                    <text x={node.x} y={node.y + 6} textAnchor="middle">{node.label}</text>
                  </g>
                ))}
              </g>
            </svg>
          </div>
        </div>
      </div>
    </section>
  );
}
