import type { ThemeItem } from "../lib/api";

interface Props {
  themes: ThemeItem[];
}

export default function TopThemes({ themes }: Props) {
  return (
    <div className="card">
      <h2>Top Themes</h2>
      {themes.map((t) => (
        <div key={t.rank} className="theme-row">
          <span className="theme-name">
            {t.icon} {t.theme_name}
          </span>
          <span className="theme-pct">{t.review_share_pct}% of reviews</span>
        </div>
      ))}
    </div>
  );
}
