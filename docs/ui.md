# UI: Dashboard & Operator Console

React dashboard on **Vercel** + FastAPI backend on **Railway**.

## Architecture

```
Vercel (ui/)          Railway (pulse-api)
  React + Vite    →     FastAPI + pulse pipeline
  VITE_API_URL          CORS_ORIGINS, GROQ_API_KEY, GOOGLE_MCP_API_KEY
                              ↓
                        Railway MCP (Docs + Gmail)
```

## What is Vite?

**Vite** is the frontend build tool (not hosting). It:

- Runs `npm run dev` with hot reload on port **5173**
- Proxies `/api` to your local `pulse-api` during development
- Builds static files to `ui/dist/` for Vercel

You deploy the **built app**, not Vite itself.

---

## Local development

### 1. Backend

```bash
pip install -e ".[dev,ui]"
cp config/products.staging.example.yaml config/products.yaml
cp .env.example .env

# Seed 5 weeks of demo dashboard data (optional)
curl -X POST http://127.0.0.1:8000/api/dashboard/seed-demo

pulse-api
# → http://127.0.0.1:8000/health
```

### 2. Frontend

```bash
cd ui
cp .env.example .env.local
npm install
npm run dev
# → http://localhost:5173
```

**Local Vite behavior:** leave `VITE_API_URL` empty in `.env.local`. The app calls `/api/...` and Vite proxies to `http://127.0.0.1:8000` (see `ui/vite.config.ts`).

---

## Vercel (frontend)

### Project settings

| Setting | Value |
|---------|--------|
| Root Directory | `ui` |
| Framework | Vite |
| Build Command | `npm run build` |
| Output Directory | `dist` |

`ui/vercel.json` is included for SPA routing.

### Environment variables (Vercel)

| Variable | Example | Required |
|----------|---------|----------|
| `VITE_API_URL` | `https://your-pulse-api.up.railway.app` | **Yes** |
| `VITE_ENABLE_OPERATOR` | `false` | For public deploy (hides Operator tab) |

No trailing slash. Rebuild after changing env vars (Vite bakes them at build time).

---

## Railway (backend)

### Start command

```bash
pulse-api
```

Or:

```bash
uvicorn pulse.api.main:app --host 0.0.0.0 --port $PORT
```

### Environment variables (Railway)

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | Groq summarization |
| `GOOGLE_MCP_API_KEY` | Docs + Gmail delivery |
| `GOOGLE_MCP_BASE_URL` | Optional MCP override |
| `CORS_ORIGINS` | `https://your-app.vercel.app,http://localhost:5173` |
| `PORT` | Set by Railway |

### Persistent storage

Mount a **volume** at `/app/runs` (or project root `runs/`) so `ledger.db` and `report.json` artifacts survive redeploys.

### Backfill historical weeks

```bash
pulse backfill --product groww --from-week 2026-W20 --to-week 2026-W24
```

Or seed demo fixtures:

```bash
curl -X POST https://your-pulse-api.up.railway.app/api/dashboard/seed-demo
```

---

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check |
| GET | `/api/dashboard/overview` | Ask 1 — overview card |
| GET | `/api/dashboard/themes` | Ask 2 — top themes |
| GET | `/api/dashboard/trends` | Ask 3 — trend chart |
| GET | `/api/dashboard/customer-voice` | Ask 4 — sentiment + emerging |
| GET | `/api/dashboard/weeks` | Available ISO weeks |
| POST | `/api/dashboard/seed-demo` | Load fixture weeks (dev) |
| POST | `/api/runs` | Operator — trigger run |
| GET | `/api/runs/jobs/{job_id}` | Live pipeline status |
| GET | `/api/runs` | Recent runs from ledger |

---

## Vite config reference

File: `ui/vite.config.ts`

| Setting | Purpose |
|---------|---------|
| `server.proxy['/api']` | Local dev → `pulse-api` |
| `VITE_API_PROXY_TARGET` | Override proxy target (default `127.0.0.1:8000`) |
| `build.outDir` | `dist` for Vercel |

File: `ui/src/lib/api.ts`

- If `VITE_API_URL` is set → all requests go to Railway
- If empty → relative `/api` paths (proxied in dev)

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Dashboard 404 / no data | Run `seed-demo` or `pulse backfill`; check `runs/groww/*/report.json` |
| CORS error on Vercel | Set `CORS_ORIGINS` on Railway to your exact Vercel URL |
| API calls hit localhost from Vercel | Set `VITE_API_URL` on Vercel and redeploy |
| Run button fails | Ensure `config/products.yaml` exists on Railway; check API logs |
