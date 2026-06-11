# Google delivery API (hosted)

Google Docs append and Gmail draft creation are handled by a **hosted REST API** on Railway — not by stdio MCP servers in this repository.

**Source:** [Baraths-MCP-Server](https://github.com/barath-srinivas/Baraths-MCP-Server) (FastAPI + Google Docs/Gmail APIs).

| Item | Value |
|------|--------|
| **Base URL** | `https://web-production-facdf.up.railway.app` |
| **Health** | `GET /health` → `{"status":"ok"}` |
| **Docs append** | `POST /append_to_doc` — `{ "doc_id", "content" }` (plain text) |
| **Gmail draft** | `POST /create_email_draft` — `{ "to", "subject", "body" }` (plain text) |
| **Auth** | `X-API-Key` header on every mutating request |
| **OAuth / tokens** | Managed on Railway (`GOOGLE_CREDENTIALS_JSON`, `GOOGLE_TOKEN_JSON`) — not in this repo |

## Pulse agent wiring (Phases 4–6)

| File | Purpose |
|------|---------|
| `config/mcp-servers.json` | Base URL and endpoint paths |
| `.env` | `GOOGLE_MCP_API_KEY` (must match Railway `API_KEY`) |
| `src/pulse/delivery/google_mcp_client.py` | HTTPS client |

**Idempotency:** the hosted API does not dedupe by anchor or ISO week. The run ledger (Phase 6) must prevent duplicate appends/drafts for the same `(product_id, iso_week)`.

## Environment variables

| Variable | Where | Notes |
|----------|-------|-------|
| `GOOGLE_MCP_API_KEY` | Pulse agent `.env` | Sent as `X-API-Key` on `POST` requests |
| `GOOGLE_MCP_BASE_URL` | Pulse agent `.env` (optional) | Overrides `baseUrl` in `mcp-servers.json` |
| `API_KEY` | Railway env | Must match pulse agent `GOOGLE_MCP_API_KEY` |
| `GOOGLE_CREDENTIALS_JSON` | Railway env | OAuth client JSON from Google Cloud |
| `GOOGLE_TOKEN_JSON` | Railway env | Saved OAuth token (refresh handled server-side) |

## Endpoint contracts

### `POST /append_to_doc`

**Request:**

```json
{
  "doc_id": "YOUR_DOCUMENT_ID",
  "content": "Plain-text section from DocStructuredReport.content\n"
}
```

**Success response:**

```json
{
  "status": "success",
  "result": {
    "document_id": "YOUR_DOCUMENT_ID",
    "appended_chars": 944,
    "replies": []
  }
}
```

### `POST /create_email_draft` (Phase 5)

**Request:**

```json
{
  "to": "recipient@example.com",
  "subject": "Groww Weekly Review Pulse — 2026-W24",
  "body": "Plain-text teaser from EmailPayload.body_text"
}
```

**Success response:**

```json
{
  "status": "success",
  "result": {
    "draft_id": "...",
    "message_id": "...",
    "to": "recipient@example.com",
    "subject": "..."
  }
}
```

## Smoke tests

**Health:**

```bash
curl https://web-production-facdf.up.railway.app/health
```

**Docs append (curl):**

```bash
curl -X POST https://web-production-facdf.up.railway.app/append_to_doc \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $GOOGLE_MCP_API_KEY" \
  -d '{"doc_id":"YOUR_DOC_ID","content":"Test line from pulse.\n"}'
```

**Docs append (pulse script):**

```bash
python scripts/test_doc_append.py --health-only
python scripts/test_doc_append.py --dry-run
python scripts/test_doc_append.py --doc-id YOUR_DOC_ID
```

**Gmail draft (curl):**

```bash
curl -X POST https://web-production-facdf.up.railway.app/create_email_draft \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $GOOGLE_MCP_API_KEY" \
  -d '{"to":"you@example.com","subject":"Pulse test","body":"Teaser body."}'
```

**Gmail draft (pulse script):**

```bash
python scripts/test_email_draft.py --health-only
python scripts/test_email_draft.py --dry-run
python scripts/test_email_draft.py --to you@example.com
python scripts/test_email_draft.py --email email.json
```

Uses plain-text `body_text` from `EmailPayload` (not HTML). One draft per recipient in `stakeholders.to[]`.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `401 Invalid or missing X-API-Key` | Set `GOOGLE_MCP_API_KEY` in pulse `.env`; must match Railway `API_KEY` |
| `502 Google Docs API error` | Confirm Railway OAuth token is valid; re-auth and update `GOOGLE_TOKEN_JSON` |
| `500 Missing credentials` | Set `GOOGLE_CREDENTIALS_JSON` on Railway (see [MCP server README](https://github.com/barath-srinivas/Baraths-MCP-Server/blob/main/README.md)) |
| `invalid_grant` on token refresh | Delete and regenerate OAuth token on Railway |
| Append succeeds but text missing | Confirm the signed-in Google account can edit the target Doc |
| Duplicate sections on rerun | Expected without ledger — Phase 6 ledger guards prevent re-append for same ISO week |
| Duplicate drafts on rerun | Expected without ledger — Phase 6 tracks `draft_id` per `(product_id, iso_week)` |
| Draft not visible in Gmail | Confirm Railway OAuth account matches the inbox you are checking |
| Local MCP server approval prompt | Local dev uses terminal `Approve? (y/n)` when `API_KEY` is unset; Railway uses API key only |

## Local development (MCP server)

For local testing without Railway, run the MCP server from [Baraths-MCP-Server](https://github.com/barath-srinivas/Baraths-MCP-Server):

```bash
python server.py
```

Point the pulse agent at it:

```bash
GOOGLE_MCP_BASE_URL=http://127.0.0.1:8080
```

Without `API_KEY` on the server, each request prompts for terminal approval. With `API_KEY` set locally, behavior matches Railway (header auth, no prompt).
