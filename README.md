# Product Review Pulse

Automated weekly insight report from **Google Play** reviews for **Groww**, delivered via a **hosted Google delivery API** on Railway (Docs append + Gmail drafts).

## Status

**Phase 9** — Production go-live (draft-mode) + Monday IST scheduler ([`docs/scheduler.md`](docs/scheduler.md)).

Phases 1–8 complete. Production uses the real Google Doc and stakeholder list with `delivery.email_mode: draft` until the hosted Railway API supports send.

## Web UI (dashboard + operator)

- [`docs/ui.md`](docs/ui.md) — Vite + React on Vercel, FastAPI on Railway
- [`docs/deploymentplan.md`](docs/deploymentplan.md) — step-by-step Railway + Vercel deploy
- Local: `pulse-api` + `cd ui && npm run dev`

## Documentation

- [`docs/context.md`](docs/context.md) — product scope
- [`docs/architecture.md`](docs/architecture.md) — technical design
- [`docs/implementation-plan.md`](docs/implementation-plan.md) — phased build plan
- [`docs/deploymentplan.md`](docs/deploymentplan.md) — Railway + Vercel deployment
- [`docs/runbook.md`](docs/runbook.md) — operations, staging sign-off, audit SQL
- [`docs/scheduler.md`](docs/scheduler.md) — Monday 08:00 IST cron / Task Scheduler
- [`docs/edge-case.md`](docs/edge-case.md) — corner cases and QA catalog

## Quick start

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
pytest tests/unit/ -v
pulse run --product groww --week 2026-W24 --mock-llm
pulse dry-run --product groww --mock-llm
pulse status --product groww --week 2026-W24
```

## CLI

| Command | Purpose |
|---------|---------|
| `pulse run` | Full pipeline: ingest → reason → render → Docs append → Gmail drafts |
| `pulse dry-run` | Ingest + reason + render only; writes `report.json` (no delivery HTTP) |
| `pulse backfill` | Run `pulse run` over `--from-week` … `--to-week` |
| `pulse status` | Show ledger summary for product + ISO week |

```bash
# Standard weekly run (current ISO week in Asia/Kolkata)
pulse run --product groww

# Dry run — no Railway API calls
pulse dry-run --product groww --out report.json --mock-llm

# Backfill a range of weeks
pulse backfill --product groww --from-week 2026-W20 --to-week 2026-W24

# Check ledger for a week
pulse status --product groww --week 2026-W24

# Retry delivery after partial failure
pulse run --product groww --week 2026-W24 --from-stage delivery
```

## Staging sign-off (Phase 8)

```bash
cp config/products.staging.example.yaml config/products.yaml
pytest tests/unit/test_safety_audit.py tests/integration/test_staging_e2e.py -v
python scripts/staging_checklist.py --week 2026-W24
pulse run --product groww --week 2026-W24 --mock-llm
```

See [`docs/runbook.md`](docs/runbook.md) for the full checklist and failure recovery.

## Production go-live (Phase 9, draft-mode)

```bash
cp config/products.production.example.yaml config/products.yaml
cp .env.example .env   # GROQ_API_KEY, GOOGLE_MCP_API_KEY
python scripts/production_checklist.py
pulse run --product groww
```

Register the weekly scheduler per [`docs/scheduler.md`](docs/scheduler.md) (Monday 08:00 `Asia/Kolkata`). Drafts are created in Gmail; send manually until the hosted API supports `email_mode: send`.

Set `GROQ_API_KEY` in `.env` for live Groq summarization (`llama-3.3-70b-versatile`). Embeddings use local **BGE-small** (`BAAI/bge-small-en-v1.5`) — no paid embedding API.

Copy environment template:

```bash
cp .env.example .env
cp config/products.production.example.yaml config/products.yaml
```

## Configuration

| File | Purpose |
|------|---------|
| `config/products.production.example.yaml` | Production Doc id + stakeholders (copy to `products.yaml`) |
| `config/products.staging.example.yaml` | Staging Doc + dev recipients |
| `config/pulse.yaml` | Review window, BGE embeddings, clustering, Groq LLM quotas, delivery mode |
| `config/mcp-servers.json` | Hosted Google delivery API URL + endpoints |

## License

Internal project — see repository owner for terms.
