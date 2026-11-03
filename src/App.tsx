import { useEffect, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  Calculator,
  Layers3,
} from "lucide-react";
import { ChatPortal } from "./components/ChatPortal";
import { McpServerPage } from "./components/McpServerPage";
import { MigrationExplorer } from "./components/MigrationExplorer";
import { QuoteEstimatorHub } from "./components/QuoteEstimatorHub";
import { SolutionDetailPage } from "./components/SolutionDetailPage";
import { SolutionExplorer, getValidSolutionEntry } from "./components/SolutionExplorer";
import { initAnalytics, trackClick, trackPageView } from "./analytics";
import { copy, type Lang } from "./data/i18n";
import { solutionEntries, solutionEntryCards, textFor } from "./data/solutions";

type Route = "home" | "estimator" | "solutionsIndex" | "solution" | "migration" | "mcp" | "hld" | "proposal";

function getInitialLang(): Lang {
  const stored = window.localStorage.getItem("huawei-latam-smb-lang");
  return stored === "en" || stored === "zh" || stored === "pg" ? stored : "es";
}

function getRoute(): Route {
  if (window.location.hash.startsWith("#/estimator")) {
    return "estimator";
  }
  if (window.location.hash.startsWith("#/migration")) {
    return "migration";
  }
  if (window.location.hash.startsWith("#/mcp")) {
    return "mcp";
  }
  if (window.location.hash.startsWith("#/hld")) {
    return "hld";
  }
  if (window.location.hash.startsWith("#/proposal")) {
    return "proposal";
  }
  if (window.location.hash.startsWith("#/solutions/")) {
    return "solution";
  }
  if (/^#\/solutions(?:[?#]|$)/.test(window.location.hash)) {
    return "solutionsIndex";
  }
  return "home";
}

const SOLUTION_ID_REDIRECTS: Record<string, string> = {
  "datacenter-onprem-migration": "vmware-migration",
  "ai-coding": "ai-coding-opencode",
};

function getSolutionId() {
  const match = window.location.hash.match(/^#\/solutions\/([^/?#]+)/);
  if (!match) return null;
  const raw = decodeURIComponent(match[1]);
  const redirect = SOLUTION_ID_REDIRECTS[raw];
  if (redirect) {
    const rest = window.location.hash.slice(match[0].length);
    window.location.replace(`#/solutions/${redirect}${rest}`);
    return redirect;
  }
  return raw;
}

function getSolutionsEntryId() {
  const query = window.location.hash.match(/^#\/solutions\?(.+)$/)?.[1];
  if (!query) {
    return undefined;
  }
  const entry = new URLSearchParams(query).get("entry") ?? undefined;
  return getValidSolutionEntry(entry);
}

function scrollForRoute(route: Route) {
  if (route === "estimator" || route === "solution" || route === "solutionsIndex" || route === "migration" || route === "mcp" || route === "hld" || route === "proposal") {
    window.scrollTo({ top: 0 });
    return;
  }

  const hashId = window.location.hash.replace(/^#/, "");
  if (!hashId || hashId === "/") {
    window.scrollTo({ top: 0 });
    return;
  }

  window.requestAnimationFrame(() => {
    document.getElementById(hashId)?.scrollIntoView();
  });
}

const estimatorCta = {
  es: {
    kicker: "Cloud Estimator",
    title: "Estime ECS y EVS desde RVTools",
    body:
      "Use el cotizador como herramienta separada para revisar regiones, precios cacheados y estimados mensuales antes de una migración cloud.",
    action: "Abrir cotizador",
  },
  en: {
    kicker: "Cloud Estimator",
    title: "Estimate ECS and EVS from RVTools",
    body:
      "Use the estimator as a separate tool to review regions, cached pricing, and monthly estimates before a cloud migration.",
    action: "Open estimator",
  },
  zh: {
    kicker: "云报价器",
    title: "基于 RVTools 估算 ECS 与 EVS",
    body:
      "将报价器作为独立工具使用，在云迁移前查看区域、本地缓存价格和月度估算结果。",
    action: "打开报价器",
  },
  pg: {
    kicker: "Cotação Cloud",
    title: "Estime ECS e EVS desde RVTools",
    body:
      "Use o cotação como ferramenta separada para revisar regiões, preços em cache e estimativas mensais antes de uma migração cloud.",
    action: "Abrir cotação",
  },
} satisfies Record<Lang, { kicker: string; title: string; body: string; action: string }>;


const footerCtas = [
  {
    label: "Contact Sales",
    href: "https://www.huaweicloud.com/intl/en-us/contact-sales.html",
  },
  {
    label: "After-Sales",
    href: "https://console-intl.huaweicloud.com/ticket/?region=ap-southeast-1&locale=en-us#/ticketindex/createIndex",
  },
  {
    label: "Self Service",
    href: "https://www.huaweicloud.com/intl/en-us/service/help-tools.html",
  },
];

const footerLegalLinks = [
  ["Site Terms", "https://www.huaweicloud.com/intl/en-us/declaration-sg/sa_st.html"],
  ["Privacy Statement", "https://www.huaweicloud.com/intl/en-us/declaration-sg/sa_prp_intl.html"],
];

const footerSocialLinks = [
  {
    label: "Twitter",
    href: "https://twitter.com/HuaweiCloud1",
    icon: "https://res-static.hc-cdn.cn/cloudbu-site/intl/en-us/推特-default.png",
    iconHover: "https://res-static.hc-cdn.cn/cloudbu-site/intl/en-us/推特-hover.png",
  },
  {
    label: "YouTube",
    href: "https://www.youtube.com/user/HuaweiCloudComputing",
    icon: "https://res-static.hc-cdn.cn/cloudbu-site/intl/en-us/yunying/new-header/1692235623225415471.png",
    iconHover: "https://res-static.hc-cdn.cn/cloudbu-site/intl/en-us/形状结合备份.svg",
  },
  {
    label: "LinkedIn",
    href: "https://www.linkedin.com/showcase/3718023",
    icon: "https://res-static.hc-cdn.cn/cloudbu-site/intl/en-us/yunying/new-header/1692235623231746773.png",
    iconHover: "https://res-static.hc-cdn.cn/cloudbu-site/intl/en-us/形状备份.svg",
  },
];

const footerGroups = [
  {
    title: "Explore Huawei Cloud",
    links: [
      ["Why Us", "https://www.huaweicloud.com/intl/en-us/about/index.html"],
      ["Customer Stories", "https://www.huaweicloud.com/intl/en-us/cases.html"],
      ["Trust Center", "https://www.huaweicloud.com/intl/en-us/securecenter/overallsafety.html"],
      ["Legal", "https://www.huaweicloud.com/intl/en-us/declaration-sg/sa_cua.html"],
      ["Press Releases", "https://www.huaweicloud.com/intl/en-us/news.html"],
    ],
  },
  {
    title: "Featured Services",
    links: [
      ["Elastic Cloud Server (ECS)", "https://www.huaweicloud.com/intl/en-us/product/ecs.html"],
      ["Elastic IP (EIP)", "https://www.huaweicloud.com/intl/en-us/product/eip.html"],
      ["RDS for MySQL", "https://www.huaweicloud.com/intl/en-us/product/mysql.html"],
      ["Elastic Volume Service (EVS)", "https://www.huaweicloud.com/intl/en-us/product/evs.html"],
      ["MapReduce Service (MRS)", "https://www.huaweicloud.com/intl/en-us/product/mrs.html"],
    ],
  },
  {
    title: "Service and Support",
    links: [
      ["Documentation", "https://support.huaweicloud.com/intl/en-us/index.html"],
      ["Contact Us", "https://www.huaweicloud.com/intl/en-us/contact-sales.html"],
      ["Public Notices", "https://www.huaweicloud.com/intl/en-us/notice.1.html"],
      ["Support Plans", "https://www.huaweicloud.com/intl/en-us/service/supportplans.html"],
      ["Service Health Dashboard", "https://status.service.huaweicloud.com/intl/#/home"],
    ],
  },
  {
    title: "Account and Payment",
    links: [
      ["Top Up", "https://account-intl.huaweicloud.com/usercenter/#/userindex/balanceRecharge"],
      ["Invoices", "https://account-intl.huaweicloud.com/usercenter/?locale=en-us#/userindex/invoiceCenter"],
      ["Billing Center", "https://account-intl.huaweicloud.com/usercenter/?locale=en-us#/userindex/allview"],
      ["My Account", "https://account-intl.huaweicloud.com/usercenter/?locale=en-us#/accountindex/accountInfo"],
      ["Payment Method", "https://account-intl.huaweicloud.com/usercenter/?locale=en-us#/userindex/creditsList"],
    ],
  },
  {
    title: "Quick Links",
    links: [
      ["Huawei Corporate", "https://www.huawei.com/en/"],
      ["Huawei Enterprise", "https://e.huawei.com/en/"],
      ["Huawei Consumer Business", "https://consumer.huawei.com/en/?utm_source=huaweicloud&utm_medium=footer"],
      ["Huawei Developers", "https://developer.huawei.com/consumer/en/"],
    ],
  },
];

function SiteHeader({
  lang,
  route,
  setLang,
}: {
  lang: Lang;
  route: Route;
  setLang: (lang: Lang) => void;
}) {
  const t = copy[lang];
    const activeRoute = route === "solution" && window.location.hash.includes("from=migration") ? "migration" : route;

  return (
    <header className={activeRoute === "migration" ? "site-header migration-site-header" : "site-header"}>
      <a
        className="brand"
        href="#/"
        aria-label="Huawei LATAM SMB Solutions"
        onClick={() =>
          trackClick({
            click_target: "nav_logo",
            click_section: "header",
            destination: "#/",
          })
        }
      >
        <img src="/assets/huawei/huawei-logo.png" alt="Huawei" />
        <span>LATAM SMB Solutions</span>
      </a>
      <nav className="main-nav" aria-label="Primary">
        <a
          className={activeRoute === "home" ? "nav-active" : ""}
          href="#/"
          onClick={() =>
            trackClick({
              click_target: "nav_home",
              click_section: "header",
              destination: "#/",
            })
          }
        >
          {t.nav.home}
        </a>
        <a
          className={activeRoute === "solutionsIndex" || activeRoute === "solution" ? "nav-active" : ""}
          href="#/solutions"
          onClick={() =>
            trackClick({
              click_target: "nav_solutions",
              click_section: "header",
              destination: "#/solutions",
            })
          }
        >
          {t.nav.solutions}
        </a>
        <a
          className={activeRoute === "migration" ? "nav-active" : ""}
          href="#/migration"
          onClick={() =>
            trackClick({
              click_target: "nav_migration",
              click_section: "header",
              destination: "#/migration",
            })
          }
        >
          {t.nav.migration}
        </a>
        <a
          className={activeRoute === "mcp" ? "nav-active" : ""}
          href="#/mcp"
          onClick={() =>
            trackClick({
              click_target: "nav_mcp",
              click_section: "header",
              destination: "#/mcp",
            })
          }
        >
          {t.nav.mcp}
        </a>
        <a
          className={activeRoute === "estimator" ? "nav-active" : ""}
          href="#/estimator"
          onClick={() =>
            trackClick({
              click_target: "nav_estimator",
              click_section: "header",
              destination: "#/estimator",
            })
          }
        >
          {t.nav.pricing}
        </a>
        <a
          className={activeRoute === "hld" ? "nav-active" : ""}
          href="#/hld"
          onClick={() =>
            trackClick({
              click_target: "nav_hld",
              click_section: "header",
              destination: "#/hld",
            })
          }
        >
          {t.nav.hld}
        </a>
        <a
          className={activeRoute === "proposal" ? "nav-active" : ""}
          href="#/proposal"
          onClick={() =>
            trackClick({
              click_target: "nav_proposal",
              click_section: "header",
              destination: "#/proposal",
            })
          }
        >
          {t.nav.proposal}
        </a>
      </nav>
      <div className="language-toggle" aria-label="Language">
        {/* <button
          type="button"
          className={lang === "pg" ? "active" : ""}
          onClick={() => {
            trackClick({
              click_target: "language_pg",
              click_section: "header",
              destination: "pg",
            });
            setLang("pg");
          }}
        >
          PG
        </button> */}
        <button
          type="button"
          className={lang === "es" ? "active" : ""}
          onClick={() => {
            trackClick({
              click_target: "language_es",
              click_section: "header",
              destination: "es",
            });
            setLang("es");
          }}
        >
          ES
        </button>
        <button
          type="button"
          className={lang === "en" ? "active" : ""}
          onClick={() => {
            trackClick({
              click_target: "language_en",
              click_section: "header",
              destination: "en",
            });
            setLang("en");
          }}
        >
          EN
        </button>
        <button
          type="button"
          className={lang === "zh" ? "active" : ""}
          onClick={() => {
            trackClick({
              click_target: "language_zh",
              click_section: "header",
              destination: "zh",
            });
            setLang("zh");
          }}
        >
          中
        </button>
      </div>
    </header>
  );
}

function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="footer-nav">
        <div className="footer-wrapper footer-main">
          <div className="footer-nav-left">
            <div className="footer-submenu-links">
              {footerCtas.map(({ label, href }) => (
                <a className="footer-submenu-link" href={href} key={label} target="_blank" rel="noreferrer">
                  {label}
                </a>
              ))}
            </div>
            <ul className="footer-law-mb">
              {footerLegalLinks.map(([label, href]) => (
                <li key={label}>
                  <a href={href} target="_blank" rel="noreferrer">
                    {label}
                  </a>
                </li>
              ))}
            </ul>
            <ul className="footer-nav-icons" aria-label="Huawei Cloud social links">
              {footerSocialLinks.map((link) => (
                <li key={link.label}>
                  <a className="footer-icon-wrapper" href={link.href} target="_blank" rel="noreferrer" aria-label={link.label}>
                    <i className="footer-icon" style={{ backgroundImage: `url("${link.icon}")` }} />
                    <i className="footer-icon-hover" style={{ backgroundImage: `url("${link.iconHover}")` }} />
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div className="footer-link-grid">
            {footerGroups.map((group) => (
              <section className="footer-link-group" key={group.title}>
                <h2>{group.title}</h2>
                {group.links.map(([label, href]) => (
                  <a href={href} key={label} target="_blank" rel="noreferrer">
                    {label}
                  </a>
                ))}
              </section>
            ))}
          </div>
        </div>
      </div>

      <div className="footer-copyright-container">
        <div className="footer-wrapper footer-bottom">
          <span>© 2026, Huawei Cloud Computing Technologies Co., Ltd. and/or its affiliates. All rights reserved.</span>
          <ul className="footer-law">
            {footerLegalLinks.map(([label, href]) => (
              <li key={label}>
                <a href={href} target="_blank" rel="noreferrer">
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </footer>
  );
}

function HomePage({ lang }: { lang: Lang }) {
  const t = copy[lang];
  const cta = estimatorCta[lang];

  return (
    <main id="top">
      <section className="hero-section">
        <div className="hero-bg">
          <video
            className="hero-video"
            src="/assets/huawei/maas-banner.mp4"
            autoPlay
            muted
            loop
            playsInline
            aria-hidden="true"
          />
        </div>
        <div className="hero-content">
          <span className="section-kicker">{t.hero.eyebrow}</span>
          <h1>{t.hero.title}</h1>
          <p>{t.hero.body}</p>
          <div className="hero-actions">
            <a
              className="primary-action"
              href="#highlights"
              onClick={() =>
                trackClick({
                  click_target: "hero_view_highlights",
                  click_section: "home_hero",
                  destination: "#highlights",
                })
              }
            >
              <ArrowDown size={18} />
              {t.hero.primary}
            </a>
            <a
              className="secondary-action"
              href="#/solutions"
              onClick={() =>
                trackClick({
                  click_target: "hero_explore_solutions",
                  click_section: "home_hero",
                  destination: "#/solutions",
                })
              }
            >
              <Layers3 size={18} />
              {t.hero.secondary}
            </a>
          </div>
        </div>
      </section>

      <section id="highlights" className="content-section">
        <div className="section-heading">
          <span className="section-kicker">Highlights</span>
          <h2>{t.sections.highlights}</h2>
          <p>{t.sections.highlightsBody}</p>
        </div>
        <div className="value-proposition-panel">
          <img
            src="/assets/huawei/huawei_cloud_smb_value_propositions_with_descriptions.svg"
            alt="Huawei Cloud SMB value propositions"
          />
        </div>
      </section>

      <section className="estimator-cta-section">
        <div>
          <span className="section-kicker">{cta.kicker}</span>
          <h2>{cta.title}</h2>
          <p>{cta.body}</p>
        </div>
        <a
          className="primary-action estimator-action"
          href="#/estimator"
          onClick={() =>
            trackClick({
              click_target: "home_estimator_cta",
              click_section: "home_estimator_cta",
              destination: "#/estimator",
            })
          }
        >
          <Calculator size={18} />
          {cta.action}
          <ArrowRight size={18} />
        </a>
      </section>

      <section className="content-section solution-entry-section">
        <div className="section-heading">
          <span className="section-kicker">Solution Playbook</span>
          <h2>{t.sections.solutions}</h2>
          <p>{t.sections.solutionsBody}</p>
        </div>
        <div className="solution-domain-entry-grid">
          {solutionEntryCards.map((card) => {
            if (card.kind === "internal") {
              const entry = card.entry;
              return (
                <a
                  className="solution-domain-entry"
                  href={`#/solutions?entry=${entry.id}`}
                  key={entry.id}
                  onClick={() =>
                    trackClick({
                      click_target: "home_solution_entry",
                      click_section: "home_solution_entries",
                      destination: `#/solutions?entry=${entry.id}`,
                      entry_id: entry.id,
                    })
                  }
                >
                  <img src={entry.heroImage} alt="" loading="lazy" />
                  <span className="solution-domain-entry-overlay" />
                  <span className="solution-domain-entry-content">
                    <strong>{textFor(lang, entry.title)}</strong>
                    <small>{textFor(lang, entry.summary)}</small>
                    <span className="solution-domain-entry-action">
                      {lang === "es" ? "Explorar escenarios" : "Explore scenarios"}
                      <ArrowRight size={16} />
                    </span>
                  </span>
                </a>
              );
            }
            const url = lang === "es" ? card.externalUrls.es : card.externalUrls.en;
            return (
              <a
                className="solution-domain-entry solution-domain-entry-external"
                href={url}
                key={card.id}
                target="_blank"
                rel="noreferrer"
                onClick={() =>
                  trackClick({
                    click_target: "home_solution_entry_external",
                    click_section: "home_solution_entries",
                    destination: url,
                    entry_id: card.id,
                  })
                }
              >
                <img src={card.heroImage} alt="" loading="lazy" />
                <span className="solution-domain-entry-overlay" />
                <span className="solution-domain-entry-content">
                  <strong>{textFor(lang, card.title)}</strong>
                  <small>{textFor(lang, card.summary)}</small>
                  <span className="solution-domain-entry-action">
                    {lang === "es" ? "Abrir solución oficial" : "Open official solution"}
                    <ArrowRight size={16} />
                  </span>
                </span>
              </a>
            );
          })}
        </div>
      </section>
    </main>
  );
}

function SolutionsIndexPage({ lang }: { lang: Lang }) {
  const t = copy[lang];
  const [initialEntryId, setInitialEntryId] = useState(getSolutionsEntryId);

  useEffect(() => {
    const handleHashChange = () => setInitialEntryId(getSolutionsEntryId());
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  return (
    <main id="top" className="solutions-index-page">
      <section className="content-section">
        <div className="section-heading split-heading">
          <div>
            <span className="section-kicker">Solution Playbook</span>
            <h1>{t.sections.solutions}</h1>
            <p>{t.sections.solutionsBody}</p>
          </div>
          <a
            className="primary-action estimator-action"
            href="#/estimator"
            onClick={() =>
              trackClick({
                click_target: "solutions_estimator_cta",
                click_section: "solutions_header",
                destination: "#/estimator",
              })
            }
          >
            <Calculator size={18} />
            {copy[lang].nav.pricing}
          </a>
        </div>
        <SolutionExplorer lang={lang} initialEntryId={initialEntryId} />
      </section>
    </main>
  );
}

function EstimatorPage({ lang }: { lang: Lang }) {
  return (
    <main id="top" className="estimator-page">
      <QuoteEstimatorHub lang={lang} />
    </main>
  );
}

function MigrationPage({ lang }: { lang: Lang }) {
  return (
    <main id="top" className="migration-page">
      <MigrationExplorer lang={lang} />
    </main>
  );
}

function App() {
  const [lang, setLang] = useState<Lang>(getInitialLang);
  const [route, setRoute] = useState<Route>(getRoute);
  const [solutionId, setSolutionId] = useState<string | null>(getSolutionId);
  const [locationHash, setLocationHash] = useState(window.location.hash || "#/");

  useEffect(() => {
    initAnalytics();
  }, []);

  useEffect(() => {
    const handleHashChange = () => {
      const nextRoute = getRoute();
      setRoute(nextRoute);
      setSolutionId(getSolutionId());
      setLocationHash(window.location.hash || "#/");
      scrollForRoute(nextRoute);
    };
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  useEffect(() => {
    window.localStorage.setItem("huawei-latam-smb-lang", lang);
    document.documentElement.lang = lang;
  }, [lang]);

  useEffect(() => {
    document.title =
      route === "estimator"
        ? "Huawei LATAM - Cloud Estimator"
        : route === "solutionsIndex"
          ? "Huawei LATAM - Solution Playbook"
        : route === "solution"
          ? "Huawei LATAM - Solution Detail"
        : route === "migration"
          ? "Huawei LATAM - Migration & Modernization"
        : route === "mcp"
          ? "Huawei LATAM - MCP Server"
        : route === "hld"
          ? "Huawei LATAM - HLD Design"
        : route === "proposal"
          ? "Huawei LATAM - Proposal"
          : "Huawei LATAM - SMB Advisor";
  }, [route, solutionId]);

  useEffect(() => {
    trackPageView();
  }, [locationHash, route, solutionId]);

  useEffect(() => {
    scrollForRoute(route);
  }, []);

  return (
    <div className="site-shell">
      {route === "home" || route === "hld" || route === "proposal" ? (
        <ChatPortal lang={lang} setLang={setLang} />
      ) : (
        <>
          <SiteHeader lang={lang} route={route} setLang={setLang} />
          {route === "estimator" ? (
            <EstimatorPage lang={lang} />
          ) : route === "migration" ? (
            <MigrationPage lang={lang} />
          ) : route === "mcp" ? (
            <McpServerPage lang={lang} />
          ) : route === "solution" ? (
            <SolutionDetailPage lang={lang} solutionId={solutionId} />
          ) : route === "solutionsIndex" ? (
            <SolutionsIndexPage lang={lang} />
          ) : (
            <HomePage lang={lang} />
          )}
          <SiteFooter />
        </>
      )}
    </div>
  );
}

export default App;
