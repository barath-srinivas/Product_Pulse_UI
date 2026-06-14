import type { PipelineStep } from "../lib/api";

interface Props {
  steps: PipelineStep[];
  status?: string;
  error?: string | null;
}

function stepIcon(status: PipelineStep["status"]): string {
  switch (status) {
    case "completed":
      return "✓";
    case "active":
      return "●";
    case "failed":
      return "✕";
    default:
      return "○";
  }
}

export default function AgentConsole({ steps, status, error }: Props) {
  return (
    <div className="card">
      <h2>AI Agent Console</h2>
      <p style={{ margin: "0 0 1rem", color: "var(--muted)", fontSize: "0.9rem" }}>
        Pipeline execution {status ? `— ${status}` : ""}
      </p>
      {error && <div className="error-banner">{error}</div>}
      {steps.map((step) => (
        <div key={step.id} className="pipeline-step">
          <div className={`pipeline-icon ${step.status}`}>{stepIcon(step.status)}</div>
          <span style={{ fontWeight: step.status === "active" ? 600 : 400 }}>{step.label}</span>
        </div>
      ))}
    </div>
  );
}
