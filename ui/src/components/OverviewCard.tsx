import type { Overview } from "../lib/api";

interface Props {
  data: Overview;
}

export default function OverviewCard({ data }: Props) {
  return (
    <div className="card">
      <h2>Overview</h2>
      <p style={{ margin: "0 0 1rem", fontSize: "1.35rem", fontWeight: 700 }}>
        {data.display_name} Weekly Pulse
      </p>
      <p style={{ margin: "0 0 1.25rem", color: "var(--muted)" }}>Week: {data.iso_week}</p>
      <div className="grid-2">
        <div>
          <div className="stat-value">{data.review_count.toLocaleString()}</div>
          <div className="stat-label">Reviews Analyzed</div>
        </div>
        <div>
          <div className="stat-value">{data.theme_count}</div>
          <div className="stat-label">Themes Found</div>
        </div>
        <div>
          <div className="stat-value">{data.avg_rating?.toFixed(1) ?? "—"}</div>
          <div className="stat-label">Avg Rating of last 10 weeks</div>
        </div>
      </div>
    </div>
  );
}
