import { Bot, CloudCog, DatabaseZap, Gauge, Globe2, ShieldCheck } from "lucide-react";
import { highlights, type Highlight } from "../data/highlights";
import type { Lang } from "../data/i18n";

type HighlightsProps = {
  lang: Lang;
};

const iconMap: Record<Highlight["icon"], typeof Bot> = {
  ai: Bot,
  security: ShieldCheck,
  migration: CloudCog,
  local: Globe2,
  cost: Gauge,
  smb: DatabaseZap,
};

export function Highlights({ lang }: HighlightsProps) {
  return (
    <div className="highlight-grid">
      {highlights.map((highlight) => {
        const Icon = iconMap[highlight.icon];
        return (
          <article className="highlight-card" key={highlight.icon}>
            <span className="highlight-icon">
              <Icon size={22} />
            </span>
            <h3>{highlight.title[lang]}</h3>
            <p>{highlight.body[lang]}</p>
          </article>
        );
      })}
    </div>
  );
}
