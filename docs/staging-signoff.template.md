# Staging sign-off — Groww (Phase 8)

Copy this file and tick items as you complete manual review:

```bash
cp docs/staging-signoff.template.md docs/staging-signoff.md
```

**How to tick:** In Cursor/VS Code, edit each line and change `[ ]` to `[x]`.

**ISO week:** YYYY-Www  
**Reviewer:**  
**Date:**

---

## Manual checklist (runbook §3.5)

- [ ] Draft email **Read full report** link opens the staging Google Doc
- [ ] Doc section contains `[anchor:groww-YYYY-Www]` marker
- [ ] Email is teaser-only (no full quotes / action list)
- [ ] Re-run same week does **not** duplicate Doc section (`pulse run` → `skipped=true`)
- [ ] PII spot-check: no emails/phones in published quotes
- [ ] Product/support stakeholder approves sample pulse quality

## Reference (your staging run)

| Item | Value |
|------|-------|
| Doc | https://docs.google.com/document/d/YOUR_DOC_ID/edit |
| Report JSON | `runs/groww/YYYY-Www/report.json` |
| Ledger | `pulse status --product groww --week YYYY-Www` |

## Sign-off

**Approved by:** _____________________  
**Date:** _____________________  
**Notes:**
