import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Trends } from "../lib/api";

const COLORS = ["#00d68f", "#4dabf7", "#ffaa00", "#ff6b6b", "#b197fc"];

interface Props {
  trends: Trends;
}

export default function TrendChart({ trends }: Props) {
  const themeNames = [...new Set(trends.series.map((s) => s.theme_name))].slice(0, 5);

  const chartData = trends.weeks.map((week) => {
    const row: Record<string, string | number> = { week };
    for (const name of themeNames) {
      const point = trends.series.find((s) => s.iso_week === week && s.theme_name === name);
      row[name] = point?.review_share_pct ?? 0;
    }
    return row;
  });

  return (
    <div className="card">
      <h2>Trend Chart</h2>
      <p style={{ margin: "0 0 1rem", color: "var(--muted)", fontSize: "0.9rem" }}>
        Theme frequency over time (% of reviews)
      </p>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2d3a4f" />
          <XAxis dataKey="week" stroke="#8b9cb3" tick={{ fontSize: 11 }} />
          <YAxis stroke="#8b9cb3" unit="%" tick={{ fontSize: 11 }} />
          <Tooltip
            contentStyle={{ background: "#1a2332", border: "1px solid #2d3a4f" }}
          />
          <Legend />
          {themeNames.map((name, i) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
