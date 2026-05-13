type NormalizedRoute = "/" | "/solutions" | "/solutions/:id" | "/estimator";

type ClickEventParams = {
  click_target: string;
  click_section: string;
  destination: string;
  domain_id?: string;
  solution_id?: string;
  entry_id?: string;
  scenario_id?: string;
  region_key?: string;
  evs_key?: string;
};

type PageViewParams = {
  entry?: string;
};

type GtagCommand = "config" | "event" | "js";

declare global {
  interface Window {
    __GA_MEASUREMENT_ID__?: string;
  }
  interface Window {
    dataLayer: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

const measurementId = import.meta.env.VITE_GA_MEASUREMENT_ID?.trim();
let lastPageViewKey = "";

function analyticsEnabled() {
  return Boolean(measurementId);
}

function currentHash() {
  return window.location.hash || "#/";
}

function currentLanguage() {
  const lang = document.documentElement.lang || "es";
  return lang.toLowerCase();
}

function routeContextFromHash(hash = currentHash()): { route: NormalizedRoute; entry?: string; solutionId?: string } {
  if (hash.startsWith("#/estimator")) {
    return { route: "/estimator" };
  }

  const solutionMatch = hash.match(/^#\/solutions\/([^/?#]+)/);
  if (solutionMatch) {
    return { route: "/solutions/:id", solutionId: decodeURIComponent(solutionMatch[1]) };
  }

  if (/^#\/solutions(?:[?#]|$)/.test(hash)) {
    const query = hash.match(/^#\/solutions\?(.+)$/)?.[1];
    const entry = query ? new URLSearchParams(query).get("entry") ?? undefined : undefined;
    return { route: "/solutions", entry };
  }

  return { route: "/" };
}

function pageViewKey(hash = currentHash()) {
  const { route, entry, solutionId } = routeContextFromHash(hash);
  return [route, entry ?? "", solutionId ?? ""].join("|");
}

function gtag(command: GtagCommand, target: string | Date, params?: Record<string, unknown>) {
  window.gtag?.(command, target, params);
}

async function loadAnalytics() {
  return;
}

export function initAnalytics() {
  void loadAnalytics();
}

export function trackPageView(params: PageViewParams = {}) {
  if (!analyticsEnabled()) {
    return;
  }

  const hash = currentHash();
  const key = pageViewKey(hash);
  if (key === lastPageViewKey) {
    return;
  }
  lastPageViewKey = key;

  const { route, entry } = routeContextFromHash(hash);
  void loadAnalytics().then(() => {
    gtag("event", "page_view", {
      send_to: measurementId,
      page_title: document.title,
      page_location: window.location.href,
      page_path: route,
      route,
      lang: currentLanguage(),
      ...(entry ? { entry } : {}),
      ...(params.entry ? { entry: params.entry } : {}),
    });
  });
}

export function trackClick(params: ClickEventParams) {
  if (!analyticsEnabled()) {
    return;
  }

  const { route } = routeContextFromHash();
  void loadAnalytics().then(() => {
    gtag("event", "site_click", {
      send_to: measurementId,
      ...params,
      route,
      lang: currentLanguage(),
    });
  });
}
