import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CustomerVoice as CustomerVoiceData } from "../lib/api";

interface Props {
  data: CustomerVoiceData;
}

export default function CustomerVoice({ data }: Props) {
  const barData = data.top_themes.map((t) => ({
    name: t.theme_name.length > 22 ? `${t.theme_name.slice(0, 20)}…` : t.theme_name,
    pct: t.review_share_pct,
  }));

  return (
    <div className="card">
      <h2>Customer Voice</h2>
      <table className="metrics">
        <tbody>
          <tr>
            <td>Reviews</td>
            <td>{data.review_count.toLocaleString()}</td>
          </tr>
          <tr>
            <td>Positive</td>
            <td>{data.positive_pct}%</td>
          </tr>
          <tr>
            <td>Negative</td>
            <td>{data.negative_pct}%</td>
          </tr>
          <tr>
            <td>Neutral</td>
            <td>{data.neutral_pct}%</td>
          </tr>
        </tbody>
      </table>

      <h2 style={{ marginTop: "1.5rem" }}>Top 5 Themes</h2>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={barData} layout="vertical" margin={{ left: 8, right: 16 }}>
          <XAxis type="number" unit="%" stroke="#8b9cb3" />
          <YAxis type="category" dataKey="name" width={140} stroke="#8b9cb3" tick={{ fontSize: 11 }} />
          <Tooltip contentStyle={{ background: "#1a2332", border: "1px solid #2d3a4f" }} />
          <Bar dataKey="pct" fill="#00d68f" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>

      <h2 style={{ marginTop: "1.5rem" }}>Emerging Issues</h2>
      <table className="metrics">
        <thead>
          <tr>
            <td style={{ fontWeight: 600, color: "var(--muted)" }}>Theme</td>
            <td style={{ fontWeight: 600, color: "var(--muted)", textAlign: "right" }}>Change</td>
          </tr>
        </thead>
        <tbody>
          {data.emerging_issues.length === 0 ? (
            <tr>
              <td colSpan={2} style={{ color: "var(--muted)" }}>
                No matching themes with prior week
              </td>
            </tr>
          ) : (
            data.emerging_issues.map((issue) => (
              <tr key={issue.theme_name}>
                <td>{issue.theme_name}</td>
                <td className={issue.change_pct > 0 ? "emerging-up" : ""}>
                  {issue.change_pct > 0 ? "+" : ""}
                  {issue.change_pct}%
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
