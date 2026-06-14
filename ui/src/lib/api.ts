/**
 * API client for Product Review Pulse backend.
 *
 * Local dev:  uses relative /api (Vite proxy → pulse-api)
 * Vercel:      uses VITE_API_URL from environment (Railway backend)
 */

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

function url(path: string): string {
  return `${API_BASE}${path}`;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url(path), init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export interface Overview {
  product_id: string;
  display_name: string;
  iso_week: string;
  review_count: number;
  theme_count: number;
  avg_rating: number | null;
}

export interface ThemeItem {
  theme_name: string;
  review_share_pct: number;
  review_count: number;
  rank: number;
  icon: string;
}

export interface Trends {
  product_id: string;
  weeks: string[];
  series: { iso_week: string; theme_name: string; review_share_pct: number }[];
}

export interface CustomerVoice {
  product_id: string;
  iso_week: string;
  review_count: number;
  positive_pct: number;
  negative_pct: number;
  neutral_pct: number;
  top_themes: ThemeItem[];
  emerging_issues: { theme_name: string; change_pct: number }[];
}

export interface PipelineStep {
  id: string;
  label: string;
  status: "pending" | "active" | "completed" | "failed";
}

export interface RunDetail {
  run_id: string;
  product_id: string;
  iso_week: string;
  status: string;
  review_count: number | null;
  error: string | null;
  job_type?: "run" | "backfill";
  pipeline_steps: PipelineStep[];
  backfill_weeks?: string[];
  backfill_current_week?: string | null;
  backfill_completed?: string[];
  backfill_skipped?: string[];
  backfill_failed?: Record<string, string>;
}

export interface RunSummary {
  run_id: string;
  product_id: string;
  iso_week: string;
  status: string;
  review_count: number | null;
  doc_document_id: string | null;
  gmail_draft_count: number;
  started_at: string;
  completed_at: string | null;
  error: string | null;
}

export const api = {
  getWeeks: (product = "groww") =>
    fetchJson<{ weeks: string[] }>(`/api/dashboard/weeks?product=${product}`),

  seedDemo: () =>
    fetchJson<{ status: string }>("/api/dashboard/seed-demo", { method: "POST" }),

  getOverview: (week: string, product = "groww") =>
    fetchJson<Overview>(`/api/dashboard/overview?product=${product}&week=${week}`),

  getThemes: (week: string, product = "groww") =>
    fetchJson<{ themes: ThemeItem[] }>(`/api/dashboard/themes?product=${product}&week=${week}`),

  getTrends: (product = "groww", weeks = 12) =>
    fetchJson<Trends>(`/api/dashboard/trends?product=${product}&weeks=${weeks}`),

  getCustomerVoice: (week: string, product = "groww") =>
    fetchJson<CustomerVoice>(`/api/dashboard/customer-voice?product=${product}&week=${week}`),

  triggerRun: (body: {
    product?: string;
    week?: string;
    force?: boolean;
    force_delivery?: boolean;
    mock_llm?: boolean;
    dry_run?: boolean;
  }) =>
    fetchJson<{ job_id: string }>("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  triggerBackfill: (body: {
    product?: string;
    from_week: string;
    to_week: string;
    force?: boolean;
    force_delivery?: boolean;
    mock_llm?: boolean;
    stop_on_error?: boolean;
  }) =>
    fetchJson<{ job_id: string; weeks: string[] }>("/api/runs/backfill", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  getJob: (jobId: string) => fetchJson<RunDetail>(`/api/runs/jobs/${jobId}`),

  listRuns: (product = "groww") =>
    fetchJson<{ runs: RunSummary[] }>(`/api/runs?product=${product}`),
};
