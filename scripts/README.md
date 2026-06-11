# Development scripts

Helper entry points for manual verification during phased implementation. The operator CLI (`pulse run`, etc.) arrives in **Phase 7**.

| Phase | Script (planned) | Purpose |
|-------|------------------|---------|
| 0 | — | Use `pytest` and `pip install -e ".[dev]"` |
| 1 | `fetch_reviews.py` | Google Play ingest for Groww ✓ |
| 2 | `run_reasoning.py` | Scrub → BGE embed → cluster → Groq LLM → `report.json` ✓ |
| 3 | `render_report.py` | `PulseReport` → Doc plain-text section + email JSON ✓ |
| 4 | `test_doc_append.py` | Docs append smoke via hosted `/append_to_doc` ✓ |
| 5 | `test_email_draft.py` | Gmail draft smoke via `/create_email_draft` ✓ |
| 6 | `python -m pulse.orchestrator` | Full wired pipeline + SQLite ledger ✓ |
| 7 | `pulse` CLI | `run`, `dry-run`, `backfill`, `status` ✓ |
| 8 | `staging_checklist.py` | Phase 8 sign-off helper + `docs/runbook.md` ✓ |
| 9 | `production_checklist.py`, `scheduled_run.*` | Production go-live + Monday IST scheduler ✓ |

## Phase 1 — fetch reviews

```bash
python scripts/fetch_reviews.py --week 2026-W23
python scripts/fetch_reviews.py --force   # allow low review count (dev only)
```

Output files (overwritten each run):

- `data/reviews/groww_actual.json` — all fetched reviews (trimmed fields)
- `data/reviews/groww_normalized.json` — filtered English reviews

Live integration test (optional):

```bash
set RUN_LIVE_INGEST=1
pytest tests/integration/test_ingest_live.py -v
```

## Phase 2 — reasoning (Groq)

```bash
# Mock Groq + TF-IDF (fast, no API keys)
python scripts/run_reasoning.py --mock-llm --tfidf --input tests/fixtures/reasoning_reviews_sample.json

# From raw audit JSON (rebuilds Review list with review_id)
python scripts/run_reasoning.py --mock-llm --from-raw --week 2026-W24

# Live Groq + BGE (requires GROQ_API_KEY in .env)
python scripts/run_reasoning.py --week 2026-W24
```

Output: `report.json` (`PulseReport` with `llm_provider: groq`, `llm_model: llama-3.3-70b-versatile`). Embeddings: local BGE-small (first run downloads model weights).

## Phase 3 — render (Doc plain-text section + email teaser)

```bash
# From fixture report (no config/products.yaml required for paths below)
python scripts/render_report.py --report tests/fixtures/report_groww_sample.json

# From live report.json (uses config/products.yaml for display name, doc id, recipients)
python scripts/render_report.py --report report.json
```

Output: `doc_section.json` (`DocStructuredReport` with `section_anchor` + plain `content` for append-only Docs MCP) and `email.json` (Gmail teaser payload).

## Phase 4 — Docs append (hosted delivery API)

Requires `GOOGLE_MCP_API_KEY` in `.env` (must match Railway `API_KEY` on [Baraths-MCP-Server](https://github.com/barath-srinivas/Baraths-MCP-Server)). Set `google_doc.document_id` in `config/products.yaml` or pass `--doc-id`.

```bash
# Health check only
python scripts/test_doc_append.py --health-only

# Preview payload without HTTP call
python scripts/test_doc_append.py --dry-run

# Append fixture content to test Doc
python scripts/test_doc_append.py --doc-id YOUR_GOOGLE_DOC_ID

# Append from rendered doc_section.json
python scripts/test_doc_append.py --doc-section doc_section.json --doc-id YOUR_GOOGLE_DOC_ID
```

On success, prints `document_id` and `appended_chars`. Verify the section text in the Google Doc browser UI.

## Phase 5 — Gmail draft (hosted delivery API)

Requires `GOOGLE_MCP_API_KEY` in `.env`. Uses plain-text `body_text` from the Phase 3 email renderer (teaser only — no full report). Pass `--to` for a test inbox, or use `stakeholders.to` from `config/products.yaml`.

```bash
# Health check only
python scripts/test_email_draft.py --health-only

# Preview payload without HTTP call
python scripts/test_email_draft.py --dry-run --to you@example.com

# Draft to a single test inbox from fixture
python scripts/test_email_draft.py --to you@example.com

# Draft from rendered email.json to all configured stakeholders
python scripts/test_email_draft.py --email email.json
```

On success, prints `draft_id` and `message_id` per recipient. Open Gmail drafts on the Railway-connected account to verify.

## Phase 6 — orchestrator (full pipeline + ledger)

Wires ingest → reason → render → Docs append → Gmail drafts with SQLite idempotency at `runs/ledger.db`.

```bash
# Full run (mock Groq + TF-IDF-friendly for quick dev if you pass --mock-llm)
python -m pulse.orchestrator --product groww --week 2026-W24 --mock-llm

# Re-run same week — ledger short-circuits (no duplicate delivery)
python -m pulse.orchestrator --product groww --week 2026-W24

# Recompute insights; delivery stays idempotent
python -m pulse.orchestrator --product groww --week 2026-W24 --force --mock-llm

# Retry delivery only (after partial email failure)
python -m pulse.orchestrator --product groww --week 2026-W24 --from-stage delivery
```

Requires `GOOGLE_MCP_API_KEY` for delivery stages. Report artifact saved to `runs/groww/{iso_week}/report.json`.

## Phase 7 — CLI

Preferred operator entry point (wraps the orchestrator):

```bash
pip install -e ".[dev]"

# Full run
pulse run --product groww --week 2026-W24 --mock-llm

# Dry run (no delivery HTTP)
pulse dry-run --product groww --week 2026-W24 --mock-llm --out report.json

# Backfill week range
pulse backfill --product groww --from-week 2026-W22 --to-week 2026-W24

# Ledger status
pulse status --product groww --week 2026-W24
```

## Phase 8 — staging E2E + safety audit

```bash
cp config/products.staging.example.yaml config/products.yaml
pytest tests/unit/test_safety_audit.py -v
pytest tests/integration/test_staging_e2e.py -v
python scripts/staging_checklist.py --week 2026-W24
pulse run --product groww --week 2026-W24 --mock-llm
# Idempotency: second run should print skipped=true
pulse run --product groww --week 2026-W24
```

Runbook: [`docs/runbook.md`](../docs/runbook.md)

## Phase 9 — production go-live (draft-mode) + scheduler

```bash
cp config/products.production.example.yaml config/products.yaml
python scripts/production_checklist.py
pulse run --product groww
# Test scheduler wrapper (logs to runs/scheduler/)
powershell -ExecutionPolicy Bypass -File scripts\scheduled_run.ps1   # Windows
./scripts/scheduled_run.sh                                            # Linux / macOS
```

Scheduler setup: [`docs/scheduler.md`](../docs/scheduler.md)  
Production sign-off: `docs/production-signoff.template.md`

## Phase 0 verification

```bash
pip install -e ".[dev]"
pytest tests/unit/test_config.py tests/unit/test_iso_week.py -v
ruff check src tests
```

## Config

Copy `config/products.example.yaml` to `config/products.yaml` and set real values before delivery phases:

```bash
cp config/products.example.yaml config/products.yaml
```

`config/products.yaml` is gitignored; the example file is committed.
