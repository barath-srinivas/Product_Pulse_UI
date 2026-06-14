import { useCallback, useEffect, useRef, useState } from "react";
import AgentConsole from "../components/AgentConsole";
import { api, type RunDetail, type RunSummary } from "../lib/api";

const DEFAULT_WEEK_HINT = "2026-W24";

export default function OperatorPage() {
  const [week, setWeek] = useState("");
  const [force, setForce] = useState(false);
  const [forceDelivery, setForceDelivery] = useState(false);
  const [mockLlm, setMockLlm] = useState(false);
  const [dryRun, setDryRun] = useState(false);
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState<RunDetail | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadRuns = useCallback(async () => {
    try {
      const res = await api.listRuns();
      setRuns(res.runs);
    } catch {
      /* ledger may be empty */
    }
  }, []);

  useEffect(() => {
    loadRuns();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [loadRuns]);

  const pollJob = (jobId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const detail = await api.getJob(jobId);
        setJob(detail);
        if (detail.status === "completed" || detail.status === "failed") {
          setRunning(false);
          if (pollRef.current) clearInterval(pollRef.current);
          loadRuns();
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Poll failed");
        setRunning(false);
      }
    }, 1500);
  };

  const handleRun = async () => {
    setError(null);
    setRunning(true);
    setJob(null);
    try {
      const body: {
        product: string;
        week?: string;
        force: boolean;
        force_delivery: boolean;
        mock_llm: boolean;
        dry_run: boolean;
      } = {
        product: "groww",
        force,
        force_delivery: forceDelivery,
        mock_llm: mockLlm,
        dry_run: dryRun,
      };
      if (week.trim()) body.week = week.trim();
      const { job_id } = await api.triggerRun(body);
      pollJob(job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Run failed to start");
      setRunning(false);
    }
  };

  return (
    <div className="page">
      <div className="card" style={{ marginBottom: "1rem" }}>
        <h2>Manual Run</h2>
        <p style={{ margin: "0 0 1rem", color: "var(--muted)", fontSize: "0.9rem" }}>
          Trigger a pulse outside the Monday schedule. For live backfill: turn off Dry run and Mock
          LLM, type the ISO week, and enable Force delivery when re-appending to a cleared Doc.
        </p>
        <div style={{ marginBottom: "0.75rem" }}>
          <label>
            <span style={{ color: "var(--muted)", marginRight: "0.5rem" }}>ISO week (optional)</span>
            <input
              className="select"
              placeholder="e.g. 2026-W20 (required for backfill weeks)"
              value={week}
              onChange={(e) => setWeek(e.target.value)}
              style={{ width: "min(100%, 280px)" }}
            />
          </label>
          {!week.trim() && (
            <p style={{ margin: "0.35rem 0 0", color: "var(--warn)", fontSize: "0.85rem" }}>
              Week is empty — run will use the current ISO week ({DEFAULT_WEEK_HINT}), not W20–W23.
            </p>
          )}
        </div>
        <div className="checkbox-row">
          <label>
            <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
            Dry run (no Docs / Gmail)
          </label>
          <label>
            <input type="checkbox" checked={mockLlm} onChange={(e) => setMockLlm(e.target.checked)} />
            Mock LLM (no Groq quota)
          </label>
          <label>
            <input
              type="checkbox"
              checked={force}
              onChange={(e) => {
                const on = e.target.checked;
                setForce(on);
                if (on) setForceDelivery(true);
              }}
            />
            Force re-run (recompute report)
          </label>
          <label>
            <input
              type="checkbox"
              checked={forceDelivery}
              onChange={(e) => setForceDelivery(e.target.checked)}
            />
            Force delivery (re-append Doc + new drafts)
          </label>
        </div>
        {dryRun && (
          <p style={{ margin: "0 0 0.75rem", color: "var(--warn)", fontSize: "0.85rem" }}>
            Dry run is on — no Google Doc append and no Gmail drafts will be created.
          </p>
        )}
        {force && !forceDelivery && !dryRun && (
          <p style={{ margin: "0 0 0.75rem", color: "var(--warn)", fontSize: "0.85rem" }}>
            Force re-run without Force delivery will skip Doc/Gmail if this week was already
            delivered.
          </p>
        )}
        <button type="button" className="btn" onClick={handleRun} disabled={running}>
          {running ? "Running…" : "Run Pulse"}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {job && (
        <div style={{ marginBottom: "1rem" }}>
          <AgentConsole
            steps={job.pipeline_steps}
            status={job.status}
            error={job.error}
          />
        </div>
      )}

      <div className="card">
        <h2>Recent Runs</h2>
        {runs.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>No runs in ledger yet.</p>
        ) : (
          <table className="metrics">
            <thead>
              <tr>
                <td style={{ fontWeight: 600, color: "var(--muted)" }}>Week</td>
                <td style={{ fontWeight: 600, color: "var(--muted)" }}>Status</td>
                <td style={{ fontWeight: 600, color: "var(--muted)" }}>Reviews</td>
                <td style={{ fontWeight: 600, color: "var(--muted)" }}>Drafts</td>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id}>
                  <td>{r.iso_week}</td>
                  <td>{r.status}</td>
                  <td>{r.review_count ?? "—"}</td>
                  <td>{r.status === "completed" ? r.gmail_draft_count : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
