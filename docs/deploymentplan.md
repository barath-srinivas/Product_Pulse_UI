# Deployment Plan: Product Review Pulse

Deploy the **React dashboard** on **Vercel** and the **FastAPI backend (`pulse-api`)** on **Railway**.

**Related docs:** [`ui.md`](ui.md) · [`architecture.md`](architecture.md) · [`runbook.md`](runbook.md) · [`scheduler.md`](scheduler.md)

---

## 1. Architecture overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Vercel (ui/)                                                           │
│  React + Vite static site                                               │
│  Env: VITE_API_URL → Railway pulse-api URL                              │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTPS (CORS)
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Railway — pulse-api (this repo, repo root)                             │
│  FastAPI + pulse pipeline + SQLite ledger                               │
│  Env: GROQ_API_KEY, GOOGLE_MCP_API_KEY, CORS_ORIGINS                    │
│  Volume: /app/runs (ledger.db + report.json artifacts)                  │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTPS + X-API-Key
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Railway — google-mcp-server (separate repo, prerequisite)              │
│  Google Docs append + Gmail draft API                                   │
│  https://web-production-facdf.up.railway.app                          │
└─────────────────────────────────────────────────────────────────────────┘
```

| Component | Platform | Source | Purpose |
|-----------|----------|--------|---------|
| Web UI | **Vercel** | `ui/` | Dashboard + operator console |
| `pulse-api` | **Railway** | repo root | REST API, pipeline orchestration |
| Google delivery API | **Railway** | [Baraths-MCP-Server](https://github.com/barath-srinivas/Baraths-MCP-Server) | Docs append + Gmail drafts (already hosted) |

**Deploy order:** Railway backend first → note the public URL → deploy Vercel with `VITE_API_URL` pointing at Railway.

---

## 2. Prerequisites

### Accounts & access

- [Railway](https://railway.app) account with a project for `pulse-api`
- [Vercel](https://vercel.com) account linked to your Git provider
- [Groq](https://console.groq.com) API key for LLM summarization
- Access to the hosted Google delivery API (`GOOGLE_MCP_API_KEY` must match Railway `API_KEY` on the MCP server)

### Repository readiness

- Git repo pushed to GitHub/GitLab/Bitbucket (Vercel and Railway deploy from Git)
- Production config prepared:

```bash
cp config/products.production.example.yaml config/products.yaml
# Edit document_id and stakeholder emails
```

- `config/pulse.yaml` and `config/mcp-servers.json` committed (no secrets in these files)
- **Do not commit** `.env`, `runs/`, or `data/` (gitignored)

### Local smoke test (recommended)

```bash
pip install -e ".[dev,ui]"
cp .env.example .env   # fill GROQ_API_KEY, GOOGLE_MCP_API_KEY
pulse-api                # → http://127.0.0.1:8000/health

cd ui && npm install && npm run dev   # → http://localhost:5173
```

---

## 3. Railway — `pulse-api` backend

### 3.1 Create the service

1. **New Project** → **Deploy from GitHub repo** → select this repository.
2. Railway auto-detects Python via Nixpacks (`railway.toml` sets `builder = "NIXPACKS"`).
3. **Root directory:** leave as repo root (not `ui/`).
4. **Service name:** e.g. `pulse-api`.

### 3.2 Build settings

| Setting | Value |
|---------|--------|
| Builder | Dockerfile (see `Dockerfile`) — full source copied before `pip install .` |
| Install | `pip install .` inside Docker build |
| Start command | `pulse-api` |

> **Note:** Nixpacks copies only `pyproject.toml` before `pip install .`, which installs the console script but not the `pulse` package (`ModuleNotFoundError`). The Dockerfile copies the full repo first.

`railway.toml` already defines:

```toml
[deploy]
startCommand = "pulse-api"
healthcheckPath = "/health"
healthcheckTimeout = 120
```

Equivalent manual start:

```bash
uvicorn pulse.api.main:app --host 0.0.0.0 --port $PORT
```

> **Note:** `fastapi` and `uvicorn` are included in main `dependencies` for Railway's default `pip install .`.

### 3.3 Environment variables

Set in **Railway → Service → Variables**:

| Variable | Required | Example / notes |
|----------|----------|-----------------|
| `GROQ_API_KEY` | **Yes** | Groq console API key |
| `GOOGLE_MCP_API_KEY` | **Yes** | Must match MCP server `API_KEY` |
| `GOOGLE_MCP_BASE_URL` | No | Default: `https://web-production-facdf.up.railway.app` |
| `CORS_ORIGINS` | **Yes** (prod) | `https://your-app.vercel.app,http://localhost:5173` |
| `PORT` | Auto | Set by Railway — do not override |

Copy from [`.env.example`](../.env.example). Never commit real keys.

### 3.4 Config files on Railway

`config/products.yaml`, `config/pulse.yaml`, and `config/mcp-servers.json` ship with the repo. For production:

1. Copy and edit `config/products.production.example.yaml` → `config/products.yaml` **before** pushing, or
2. Use Railway **Variables** + a build hook if you later externalize config (not required for v1).

Confirm `delivery.email_mode: draft` in `config/pulse.yaml` until the MCP server supports send.

### 3.5 Persistent volume (critical)

Dashboard data lives in `runs/`:

- `runs/ledger.db` — run history and idempotency
- `runs/groww/{iso_week}/report.json` — dashboard source files

**Without a volume, redeploys wipe all dashboard data.**

1. Railway → **pulse-api** service → **Volumes** → **Add Volume**
2. Mount path: `/app/runs` (or match your working directory + `runs/`)
3. Redeploy after attaching

### 3.6 Generate public URL

1. **Settings → Networking → Generate Domain**
2. Note the URL, e.g. `https://pulse-api-production.up.railway.app`
3. Verify:

```bash
curl https://your-pulse-api.up.railway.app/health
# {"status":"ok"}
```

### 3.7 Seed or backfill dashboard data

After first deploy (empty `runs/`):

**Option A — demo fixtures (quick UI check):**

```bash
curl -X POST https://your-pulse-api.up.railway.app/api/dashboard/seed-demo
```

**Option B — real historical weeks (Railway shell or one-off job):**

```bash
pulse backfill --product groww --from-week 2026-W20 --to-week 2026-W24
```

**Option C — full production run:**

```bash
pulse run --product groww --week 2026-W24
```

Use **Railway → Service → Shell** for CLI commands, or trigger runs from the Operator tab in the UI.

### 3.8 Weekly scheduler on Railway

The CLI scheduler (`scripts/scheduled_run.sh`) is designed for a long-lived VM or laptop. On Railway, pick one:

| Approach | When to use |
|----------|-------------|
| **Operator UI** (`POST /api/runs`) | Manual/ad-hoc runs from Vercel |
| **Railway Cron** (if available on your plan) | `pulse run --product groww` Monday 08:00 IST |
| **External cron** (GitHub Actions, cron-job.org) | `curl -X POST …/api/runs` with appropriate payload |
| **Local Task Scheduler / crontab** | Keep using [`scheduler.md`](scheduler.md) against production API |

See [`scheduler.md`](scheduler.md) for IST cron expressions and wrapper scripts.

---

## 4. Vercel — React frontend

### 4.1 Create the project

1. [Vercel Dashboard](https://vercel.com/new) → **Import Git Repository** → select this repo.
2. Configure the project:

| Setting | Value |
|---------|--------|
| **Root Directory** | `ui` |
| **Framework Preset** | Vite |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |
| **Install Command** | `npm install` |

[`ui/vercel.json`](../ui/vercel.json) is already included for SPA routing:

```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

### 4.2 Environment variables

Set in **Vercel → Project → Settings → Environment Variables**:

| Variable | Environment | Required | Value |
|----------|-------------|----------|-------|
| `VITE_API_URL` | Production | **Yes** | `https://your-pulse-api.up.railway.app` (no trailing slash) |
| `VITE_ENABLE_OPERATOR` | Production | Recommended | `false` for public dashboard-only deploy |
| `VITE_API_URL` | Preview | Optional | Staging Railway URL or same as production |

> Vite bakes `VITE_*` variables at **build time**. Changing env vars requires a **redeploy**.

Reference: [`ui/.env.example`](../ui/.env.example)

### 4.3 Deploy

1. Click **Deploy** (or push to the connected branch for auto-deploy).
2. Note the Vercel URL, e.g. `https://product-review-pulse.vercel.app`.
3. **Update Railway `CORS_ORIGINS`** to include the exact Vercel URL (and redeploy `pulse-api` if CORS was set before Vercel existed).

### 4.4 Custom domain (optional)

1. Vercel → **Domains** → add your domain.
2. Add the custom domain to Railway `CORS_ORIGINS`.
3. Redeploy both services after URL changes.

---

## 5. Post-deploy verification

### 5.1 Backend checks

```bash
# Health
curl https://your-pulse-api.up.railway.app/health

# Dashboard weeks (may be empty until seed/backfill)
curl "https://your-pulse-api.up.railway.app/api/dashboard/weeks?product=groww"

# Overview (replace week after data exists)
curl "https://your-pulse-api.up.railway.app/api/dashboard/overview?product=groww&week=2026-W24"
```

### 5.2 Frontend checks

1. Open the Vercel URL in a browser.
2. Confirm the dashboard loads (Overview, Themes, Trends, Customer Voice).
3. If empty: run `seed-demo` or `backfill` on Railway (§3.7).
4. Open DevTools → Network: API calls should go to your Railway host, not `localhost`.

### 5.3 End-to-end operator run (if Operator tab enabled)

1. Set `VITE_ENABLE_OPERATOR=true` on Vercel and redeploy (or use local dev).
2. Operator tab → trigger a **dry run** with mock LLM first.
3. Confirm `GET /api/runs/jobs/{job_id}` returns progressing pipeline steps.
4. For a live run, ensure `GROQ_API_KEY` is set and Groq quota is available.

### 5.4 Production checklist script

From Railway shell or local machine pointed at production config:

```bash
python scripts/production_checklist.py
```

See [`runbook.md`](runbook.md) for staging sign-off and audit SQL.

---

## 6. Environment variable reference

### Railway (`pulse-api`)

| Variable | Used by | Purpose |
|----------|---------|---------|
| `GROQ_API_KEY` | Pipeline / operator runs | Groq `llama-3.3-70b-versatile` summarization |
| `GOOGLE_MCP_API_KEY` | Delivery client | `X-API-Key` for Docs + Gmail API |
| `GOOGLE_MCP_BASE_URL` | Delivery client | Override for `config/mcp-servers.json` base URL |
| `CORS_ORIGINS` | FastAPI CORS middleware | Comma-separated allowed browser origins |
| `PORT` | `pulse-api` entrypoint | HTTP listen port (Railway-injected) |

### Vercel (`ui/`)

| Variable | Used by | Purpose |
|----------|---------|---------|
| `VITE_API_URL` | `ui/src/lib/api.ts` | Railway API base URL for all fetches |
| `VITE_ENABLE_OPERATOR` | `ui/src/App.tsx` | `false` hides Operator tab in production |

### Hosted Google MCP server (separate Railway project)

Not part of this repo deploy, but required for delivery:

| Variable | Purpose |
|----------|---------|
| `API_KEY` | Must equal pulse agent `GOOGLE_MCP_API_KEY` |
| `GOOGLE_CREDENTIALS_JSON` | Google OAuth client |
| `GOOGLE_TOKEN_JSON` | OAuth refresh token |

See [`mcp-servers/README.md`](../mcp-servers/README.md).

---

## 7. CI/CD and redeploys

| Event | Railway | Vercel |
|-------|---------|--------|
| Push to `main` | Auto-rebuild + restart `pulse-api` | Auto-build + deploy `ui/` |
| Env var change | Redeploy service | **Redeploy required** (Vite env baked at build) |
| Config change (`products.yaml`) | Redeploy (or git push) | No redeploy needed |
| Volume attached | Data persists across redeploys | N/A (static files) |

**First Railway deploy** downloads BGE embedding model weights (~130 MB) on the first pipeline run — expect a longer cold start.

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Dashboard empty / 404 on API | No `runs/groww/*/report.json` | `seed-demo`, `backfill`, or `pulse run` on Railway |
| CORS error in browser | `CORS_ORIGINS` missing Vercel URL | Add exact origin (scheme + host, no path); redeploy Railway |
| API calls hit `localhost` from Vercel | `VITE_API_URL` unset | Set on Vercel Production env; redeploy |
| `pulse-api` crash on start | Slow ML import or OOM | Ensure `pulse.pipeline.__init__` stays lightweight; check Railway logs |
| Data lost after redeploy | No volume on `runs/` | Attach Railway volume at `/app/runs` |
| Run button fails | Missing secrets or config | Check Railway logs; verify `GROQ_API_KEY`, `products.yaml` |
| Delivery fails | MCP key mismatch or OAuth expired | Verify `GOOGLE_MCP_API_KEY`; check MCP server health |
| Operator tab visible publicly | `VITE_ENABLE_OPERATOR` not `false` | Set on Vercel; redeploy |

### Useful log locations

- **Railway:** Service → **Deployments** → **View Logs**
- **Vercel:** Project → **Deployments** → build/runtime logs
- **Ledger audit:** `runs/ledger.db` (Railway shell + `sqlite3`)

```sql
SELECT iso_week, status, review_count, completed_at
FROM run_records
WHERE product_id = 'groww'
ORDER BY iso_week DESC;
```

---

## 9. Security notes

- **Vercel holds no secrets** — only the public Railway API URL.
- **Railway `pulse-api`** holds `GROQ_API_KEY` and `GOOGLE_MCP_API_KEY` only; no Google OAuth JSON.
- **Google OAuth** lives only on the hosted MCP server Railway project.
- Dashboard is **public in v1** (no auth). Set `VITE_ENABLE_OPERATOR=false` on public Vercel deploys.
- Use `delivery.email_mode: draft` until automated send is implemented on the MCP server.

---

## 10. Quick reference — deploy checklist

- [ ] Groq API key obtained
- [ ] Google MCP API key matches hosted MCP server
- [ ] `config/products.yaml` production values committed (or present on Railway)
- [ ] Railway service created from repo root
- [ ] Install: default Nixpacks `pip install .`
- [ ] Start: `pulse-api`
- [ ] Railway env vars set (`GROQ_API_KEY`, `GOOGLE_MCP_API_KEY`, `CORS_ORIGINS`)
- [ ] Volume mounted at `/app/runs`
- [ ] Railway domain generated; `/health` returns `ok`
- [ ] Dashboard data seeded or backfilled
- [ ] Vercel project created with root `ui`
- [ ] `VITE_API_URL` set to Railway URL
- [ ] `VITE_ENABLE_OPERATOR=false` for public deploy
- [ ] Vercel deploy successful; dashboard loads
- [ ] `CORS_ORIGINS` updated with Vercel URL
- [ ] Optional: weekly scheduler registered ([`scheduler.md`](scheduler.md))
- [ ] `python scripts/production_checklist.py` passes

---

## 11. File reference

| File | Role in deploy |
|------|----------------|
| [`Dockerfile`](../Dockerfile) | Full-source Docker build (fixes `ModuleNotFoundError: pulse`) |
| [`railway.toml`](../railway.toml) | Dockerfile builder, start command, health check |
| [`ui/vercel.json`](../ui/vercel.json) | SPA rewrites for client-side routing |
| [`ui/vite.config.ts`](../ui/vite.config.ts) | Dev proxy; build output `dist/` |
| [`pyproject.toml`](../pyproject.toml) | Python deps; `pulse-api` console script |
| [`.env.example`](../.env.example) | Railway backend env template |
| [`ui/.env.example`](../ui/.env.example) | Vercel frontend env template |
| [`config/products.production.example.yaml`](../config/products.production.example.yaml) | Production product/Doc/stakeholders |
| [`config/mcp-servers.json`](../config/mcp-servers.json) | Hosted delivery API endpoints |
