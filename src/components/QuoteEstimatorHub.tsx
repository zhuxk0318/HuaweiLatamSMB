/**
 * QuoteEstimatorHub — Quote mode switcher.
 *
 * Visible modes:
 * - Infrastructure Quote → PricingEstimator (rvtools mode, inventory-based)
 * - Cloud Billing Quote  → FlexibleQuoteEstimator (cloud_billing) → /api/quotes/cloud-billing/...
 *
 * Others Quote is hidden from the UI but its component/type/API code is kept
 * for future restoration. Legacy ?mode=others / mode=flexible hashes fall back
 * to the rvtools (Infrastructure Quote) view instead of showing a blank page.
 */
import { useEffect, useState } from "react";
import { trackClick } from "../analytics";
import type { Lang } from "../data/i18n";
import { FlexibleQuoteEstimator } from "./FlexibleQuoteEstimator";
import { PricingEstimator as RvToolsPricingEstimator } from "./PricingEstimator";

type QuoteMode = "rvtools" | "cloud_billing" | "others";

const uiCopy = {
  es: {
    title: "Quote mode",
    rvtools: "Infrastructure Quote",
    cloudBilling: "Cloud Billing Quote",
    others: "Others Quote",
  },
  en: {
    title: "Quote mode",
    rvtools: "Infrastructure Quote",
    cloudBilling: "Cloud Billing Quote",
    others: "Others Quote",
  },
  zh: {
    title: "报价模式",
    rvtools: "基础架构报价",
    cloudBilling: "云账单报价",
    others: "其他报价",
  },
  pg: {
    title: "Quote mode",
    rvtools: "Infrastructure Quote",
    cloudBilling: "Cloud Billing Quote",
    others: "Others Quote",
  },
} satisfies Record<Lang, Record<string, string>>;

function parseQuoteMode(value: string | null): QuoteMode {
    if (value === "cloud_billing") return "cloud_billing";
    // Others Quote is hidden from the UI. Legacy ?mode=others / mode=flexible
    // hashes fall back to the Infrastructure (rvtools) view.
    return "rvtools";
}

function setModeHash(mode: QuoteMode) {
    window.location.hash = `#/estimator?mode=${mode}`;
}

export function QuoteEstimatorHub({ lang }: { lang: Lang }) {
  const t = uiCopy[lang];
  const [mode, setMode] = useState<QuoteMode>("rvtools");

  useEffect(() => {
    const syncMode = () => {
      const hash = window.location.hash;
      const query = hash.match(/^#\/estimator\?(.+)$/)?.[1];
      const nextMode = new URLSearchParams(query ?? "").get("mode");
      setMode(parseQuoteMode(nextMode));
    };
    syncMode();
    window.addEventListener("hashchange", syncMode);
    return () => window.removeEventListener("hashchange", syncMode);
  }, []);

  return (
    <section className="pricing-section">
      <div className="quote-mode-switch">
        <strong>{t.title}</strong>
        <div className="segmented-control compact">
          <button
            type="button"
            className={mode === "rvtools" ? "active" : ""}
            onClick={() => {
              trackClick({ click_target: "quote_mode_rvtools", click_section: "estimator", destination: "rvtools" });
              setModeHash("rvtools");
            }}
          >
            {t.rvtools}
          </button>
          <button
            type="button"
            className={mode === "cloud_billing" ? "active" : ""}
            onClick={() => {
              trackClick({ click_target: "quote_mode_cloud_billing", click_section: "estimator", destination: "cloud_billing" });
              setModeHash("cloud_billing");
            }}
          >
            {t.cloudBilling}
          </button>
        </div>
      </div>
      {mode === "rvtools" ? (
        <RvToolsPricingEstimator lang={lang} />
      ) : (
        <FlexibleQuoteEstimator lang={lang} quoteMode={mode} />
      )}
    </section>
  );
}
