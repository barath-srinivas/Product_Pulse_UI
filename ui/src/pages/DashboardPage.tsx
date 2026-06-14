import { useCallback, useEffect, useState } from "react";
import AgentConsole from "../components/AgentConsole";
import CustomerVoice from "../components/CustomerVoice";
import OverviewCard from "../components/OverviewCard";
import TopThemes from "../components/TopThemes";
import TrendChart from "../components/TrendChart";
import {
  api,
  type CustomerVoice as CustomerVoiceData,
  type Overview,
  type ThemeItem,
  type Trends,
} from "../lib/api";

export default function DashboardPage() {
  const [weeks, setWeeks] = useState<string[]>([]);
  const [week, setWeek] = useState("2026-W24");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [themes, setThemes] = useState<ThemeItem[]>([]);
  const [trends, setTrends] = useState<Trends | null>(null);
  const [voice, setVoice] = useState<CustomerVoiceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (selectedWeek: string) => {
    setLoading(true);
    setError(null);
    try {
      const [ov, th, tr, cv] = await Promise.all([
        api.getOverview(selectedWeek),
        api.getThemes(selectedWeek),
        api.getTrends(),
        api.getCustomerVoice(selectedWeek),
      ]);
      setOverview(ov);
      setThemes(th.themes);
      setTrends(tr);
      setVoice(cv);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    api
      .getWeeks()
      .then((res) => {
        setWeeks(res.weeks);
        if (res.weeks.length > 0) {
          setWeek((w) => (res.weeks.includes(w) ? w : res.weeks[res.weeks.length - 1]));
        }
      })
      .catch(() => setWeeks([]));
  }, []);

  useEffect(() => {
    if (week) load(week);
  }, [week, load]);

  const seedDemo = async () => {
    try {
      await api.seedDemo();
      const res = await api.getWeeks();
      setWeeks(res.weeks);
      if (res.weeks.length) setWeek(res.weeks[res.weeks.length - 1]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Seed failed");
    }
  };

  return (
    <div className="page">
      <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginBottom: "1.25rem" }}>
        <label>
          <span style={{ color: "var(--muted)", marginRight: "0.5rem" }}>Week</span>
          <select className="select" value={week} onChange={(e) => setWeek(e.target.value)}>
            {weeks.length === 0 && <option value={week}>{week}</option>}
            {weeks.map((w) => (
              <option key={w} value={w}>
                {w}
              </option>
            ))}
          </select>
        </label>
        {weeks.length === 0 && (
          <button type="button" className="btn btn-secondary" onClick={seedDemo}>
            Load demo data
          </button>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}
      {loading && <p style={{ color: "var(--muted)" }}>Loading…</p>}

      {!loading && overview && (
        <>
          <div className="grid-2" style={{ marginBottom: "1rem" }}>
            <OverviewCard data={overview} />
            <TopThemes themes={themes} />
          </div>
          {trends && trends.weeks.length > 0 && (
            <div style={{ marginBottom: "1rem" }}>
              <TrendChart trends={trends} />
            </div>
          )}
          {voice && <CustomerVoice data={voice} />}
          <div style={{ marginTop: "1rem" }}>
            <AgentConsole
              steps={[
                { id: "1", label: "Reviews Retrieved", status: "completed" },
                { id: "2", label: "Reviews Clustered", status: "completed" },
                { id: "3", label: "Themes Generated", status: "completed" },
                { id: "4", label: "Quotes Validated", status: "completed" },
                { id: "5", label: "Report Created", status: "completed" },
                { id: "6", label: "Email Delivered", status: "completed" },
              ]}
              status="completed"
            />
          </div>
        </>
      )}
    </div>
  );
}
