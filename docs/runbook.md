# Runbook: Weekly Product Review Pulse (Groww)

Operator guide for staging E2E, production runs, failure recovery, and audit.  
**Related:** [`implementation-plan.md`](implementation-plan.md) · [`edge-case.md`](edge-case.md) · [`architecture.md`](architecture.md)

---

## 1. Environments

| Environment | Config | Email mode | Doc |
|-------------|--------|------------|-----|
| **Staging (Phase 8)** | `config/products.yaml` from `products.staging.example.yaml` | `draft` | Staging Google Doc |
| **Production (Phase 9)** | `config/products.yaml` from `products.production.example.yaml` | `draft` (manual send until hosted API supports `send`) | Production Google Doc |

**Pulse agent secrets (`.env`):**

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | Groq summarization |
| `GOOGLE_MCP_API_KEY` | Railway delivery API (`X-API-Key`) |
| `GOOGLE_MCP_BASE_URL` | Optional Railway URL override |

**Railway (`Baraths-MCP-Server`) secrets:** `API_KEY`, `GOOGLE_CREDENTIALS_JSON`, `GOOGLE_TOKEN_JSON`

---

## 2. Standard operations

### Weekly run (production)

```bash
pulse run --product groww
```

Defaults to current ISO week in `Asia/Kolkata` (see `config/pulse.yaml`).

### Dry run (no delivery)

```bash
pulse dry-run --product groww --out report.json --mock-llm
```

Never calls Railway. Use for pre-flight validation.

### Check run status

```bash
pulse status --product groww --week 2026-W24
```

### Backfill

```bash
pulse backfill --product groww --from-week 2026-W20 --to-week 2026-W24
```

---

## 3. Staging sign-off (Phase 8)

### 3.1 Setup

```bash
cp config/products.staging.example.yaml config/products.yaml
# Edit document_id and stakeholders.to with staging values
cp .env.example .env   # set GROQ_API_KEY, GOOGLE_MCP_API_KEY
```

Confirm `config/pulse.yaml` has `delivery.email_mode: draft`.

### 3.2 Automated checks

```bash
pytest tests/unit/test_safety_audit.py -v
pytest tests/integration/test_staging_e2e.py -v
python scripts/staging_checklist.py --week 2026-W24
```

### 3.3 Staging E2E run

```bash
pulse run --product groww --week 2026-W24 --mock-llm
pulse status --product groww --week 2026-W24
```

Optional live Groq (uses quota):

```bash
pulse run --product groww --week 2026-W24
```

### 3.4 Idempotency test

```bash
pulse run --product groww --week 2026-W24
# Expect: skipped=true, no new Doc section, no new drafts
```

### 3.5 Manual checklist

Use the **editable sign-off file** (markdown checkboxes — tick by editing `[ ]` → `[x]`):

```bash
# Already created for 2026-W24; or copy the template for another week:
cp docs/staging-signoff.template.md docs/staging-signoff.md
```

Open `docs/staging-signoff.md` in Cursor and check off each item as you verify it.

| # | Check |
|---|-------|
| 1 | Draft email **Read full report** link opens the staging Google Doc |
| 2 | Doc section contains `[anchor:groww-YYYY-Www]` marker |
| 3 | Email is teaser-only (no full quotes / action list) |
| 4 | Re-run same week does **not** duplicate Doc section |
| 5 | PII spot-check: no emails/phones in published quotes |
| 6 | Product/support stakeholder approves sample pulse quality |

**Sign-off:** fill in **Approved by** and **Date** at the bottom of `docs/staging-signoff.md`

---

## 4. Safety audit summary (P0)

Automated in `tests/unit/test_safety_audit.py`:

| Edge case | Coverage |
|-----------|----------|
| EC-PII-01/02 | Email/phone redaction |
| EC-PII-06 | Quotes from scrubbed corpus only |
| EC-INJECT-01/02 | Untrusted review delimiters + system policy |
| EC-LLM-02 / EC-QUOTE-01 | Quote validation |
| EC-RENDER-04 | HTML escape in email |
| EC-GMAIL-01 | `email_mode: draft` in staging |
| EC-ORCH-01 | Ledger idempotency (integration test) |

Adversarial fixture: `tests/fixtures/reviews_adversarial.json`

---

## 5. Failure recovery

| Failure | Ledger status | Recovery |
|---------|---------------|----------|
| Ingest fails (low reviews, Play error) | `failed` | Fix cause; `pulse run --product groww --week YYYY-Www` |
| Groq / reasoning fails | `failed` | Check `GROQ_API_KEY`, quota; re-run full pipeline |
| Doc append fails | `delivering` | Fix Railway OAuth / Doc permissions; `pulse run --from-stage delivery` |
| Email draft fails (partial) | `delivering` | `pulse run --from-stage delivery` (ledger keeps partial drafts) |
| Completed week re-run | `completed` | Exits `skipped=true` — expected idempotency |
| Recompute insights same week | `completed` | `pulse run --force` (delivery still skipped) |

### Delivery-only retry

```bash
pulse run --product groww --week 2026-W24 --from-stage delivery
```

Requires `runs/groww/2026-W24/report.json` from a prior successful reason stage.

---

## 6. Railway / Google OAuth

### Health check

```bash
python scripts/test_doc_append.py --health-only
```

### Token refresh (`invalid_grant`)

1. Re-authenticate locally in [Baraths-MCP-Server](https://github.com/barath-srinivas/Baraths-MCP-Server)
2. Update Railway env `GOOGLE_TOKEN_JSON`
3. Redeploy / restart service
4. Re-run `python scripts/test_doc_append.py --dry-run`

### API key mismatch (`401`)

- Pulse `.env` `GOOGLE_MCP_API_KEY` must match Railway `API_KEY`

### Doc permission errors

- Confirm OAuth Google account has **edit** access to `google_doc.document_id`

---

## 7. Ledger audit (SQLite)

**Database:** `runs/ledger.db`

### Latest run for a week

```sql
SELECT run_id, product_id, iso_week, status, review_count,
       doc_document_id, gmail_draft_id, started_at, completed_at, error
FROM runs
WHERE product_id = 'groww' AND iso_week = '2026-W24'
ORDER BY started_at DESC
LIMIT 1;
```

### All completed runs

```sql
SELECT iso_week, review_count, doc_document_id, completed_at
FROM runs
WHERE product_id = 'groww' AND status = 'completed'
ORDER BY completed_at DESC;
```

### Failed / stuck runs

```sql
SELECT iso_week, status, error, started_at
FROM runs
WHERE product_id = 'groww' AND status IN ('failed', 'delivering')
ORDER BY started_at DESC;
```

### CLI equivalent

```bash
pulse status --product groww --week 2026-W24
```

---

## 8. Production go-live (Phase 9, draft-mode)

### 8.1 Setup

```bash
cp config/products.production.example.yaml config/products.yaml
# Confirm document_id and stakeholders.to
python scripts/production_checklist.py
```

Confirm `config/pulse.yaml` has `delivery.email_mode: draft` and `schedule.cron: "0 8 * * 1"`.

### 8.2 First production run

```bash
pulse run --product groww
pulse status --product groww
```

Verify production Doc section, Gmail drafts (send manually in draft-mode), and ledger `status=completed`.

### 8.3 Sign-off

```bash
cp docs/production-signoff.template.md docs/production-signoff.md
```

Tick items in `docs/production-signoff.md` as you verify each check.

---

## 9. Scheduler

**Schedule:** Monday 08:00 `Asia/Kolkata` — `0 8 * * 1` (see `config/pulse.yaml`).

Full setup: [`scheduler.md`](scheduler.md) (cron + Windows Task Scheduler).

```bash
# Linux / macOS cron
0 8 * * 1 TZ=Asia/Kolkata /path/to/Product_Review_Pulse/scripts/scheduled_run.sh

# Windows — register via Task Scheduler or:
powershell -ExecutionPolicy Bypass -File scripts\scheduled_run.ps1
```

Logs: `runs/scheduler/pulse-run_*.log`

**Missed Monday run:** `pulse run --product groww --week YYYY-Www` (EC-TIME-07).

---

## 10. Troubleshooting quick reference

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `skipped=true` on rerun | Ledger idempotency (expected) | Use `--force` to recompute insights only |
| Duplicate Doc sections | Ran before Phase 6 ledger / manual append | Avoid manual `test_doc_append.py` for same week |
| No Gmail drafts | Wrong OAuth inbox / draft-only account | Check Railway-connected Gmail Drafts folder |
| `insufficient reviews` | Below `min_reviews_required` | Widen window or `--force` (dev only) |
| Groq 429 | TPM exceeded | Wait 60s; pipeline paces automatically |
| `unknown product_id` | Typo in `--product` | Only `groww` configured in v1 |

---

## 11. Document index

| Document | Purpose |
|----------|---------|
| [`runbook.md`](runbook.md) | This file |
| [`scheduler.md`](scheduler.md) | Cron / Task Scheduler setup |
| [`edge-case.md`](edge-case.md) | Full edge-case catalog |
| [`implementation-plan.md`](implementation-plan.md) | Phase map |
| [`mcp-servers/README.md`](../mcp-servers/README.md) | Railway delivery API |
