# Production sign-off — Groww (Phase 9, draft-mode)

Copy this file and tick items as you complete production go-live:

```bash
cp docs/production-signoff.template.md docs/production-signoff.md
cp config/products.production.example.yaml config/products.yaml
```

**How to tick:** In Cursor/VS Code, edit each line and change `[ ]` to `[x]`.

**ISO week:** YYYY-Www  
**Reviewer:**  
**Date:**

---

## Config & scheduler

- [ ] `config/products.yaml` copied from `products.production.example.yaml`
- [ ] `delivery.email_mode: draft` in `config/pulse.yaml` (hosted API v1)
- [ ] `.env` has `GROQ_API_KEY` and `GOOGLE_MCP_API_KEY`
- [ ] Scheduler registered: Monday 08:00 IST ([`scheduler.md`](scheduler.md))
- [ ] `python scripts/production_checklist.py` passes preflight

## First production run

- [ ] `pulse run --product groww` → `status=completed`
- [ ] Production Doc section appended with `[anchor:groww-YYYY-Www]`
- [ ] Gmail drafts created for all `stakeholders.to` (manual send OK in draft-mode)
- [ ] Re-run same week → `skipped=true` (no duplicate Doc section)
- [ ] `pulse status --product groww --week YYYY-Www` shows ledger row

## Stakeholder review

- [ ] Draft email **Read full report** link opens the **production** Google Doc
- [ ] Email is teaser-only (no full quotes / action list)
- [ ] PII spot-check on published quotes
- [ ] Product/support stakeholder approves pulse quality

## Reference

| Item | Value |
|------|-------|
| Doc | https://docs.google.com/document/d/YOUR_PRODUCTION_DOC_ID/edit |
| Report JSON | `runs/groww/YYYY-Www/report.json` |
| Scheduler log | `runs/scheduler/pulse-run_*.log` |
| Ledger | `pulse status --product groww --week YYYY-Www` |

## Sign-off

**Approved by:** _____________________  
**Date:** _____________________  
**Notes:**
