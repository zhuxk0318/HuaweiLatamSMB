import { useState } from "react";
import { trackClick } from "../analytics";
import type { Lang } from "../data/i18n";
import { FlexibleQuoteEstimator } from "./FlexibleQuoteEstimator";
import { PricingEstimator as RvToolsPricingEstimator } from "./PricingEstimator";

type QuoteMode = "rvtools" | "flexible";

const uiCopy = {
  es: {
    title: "Quote mode",
    rvtools: "RVTools Quote",
    flexible: "Flexible Quote",
  },
  en: {
    title: "Quote mode",
    rvtools: "RVTools Quote",
    flexible: "Flexible Quote",
  },
} satisfies Record<Lang, Record<string, string>>;

export function QuoteEstimatorHub({ lang }: { lang: Lang }) {
  const t = uiCopy[lang];
  const [mode, setMode] = useState<QuoteMode>("rvtools");

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
              setMode("rvtools");
            }}
          >
            {t.rvtools}
          </button>
          <button
            type="button"
            className={mode === "flexible" ? "active" : ""}
            onClick={() => {
              trackClick({ click_target: "quote_mode_flexible", click_section: "estimator", destination: "flexible" });
              setMode("flexible");
            }}
          >
            {t.flexible}
          </button>
        </div>
      </div>
      {mode === "rvtools" ? <RvToolsPricingEstimator lang={lang} /> : <FlexibleQuoteEstimator lang={lang} />}
    </section>
  );
}
