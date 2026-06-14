# Scheduler: Weekly Product Review Pulse

Automate `pulse run --product groww` every **Monday 08:00** in **Asia/Kolkata** (`config/pulse.yaml` → `schedule.cron: "0 8 * * 1"`).

**Prerequisites**

1. Production config: `cp config/products.production.example.yaml config/products.yaml`
2. Secrets in `.env`: `GROQ_API_KEY`, `GOOGLE_MCP_API_KEY`
3. Package installed: `pip install -e .` (or use project `.venv`)
4. Phase 8 staging sign-off complete ([`runbook.md`](runbook.md) §3)

**Draft-mode production:** `delivery.email_mode` stays `draft` until the hosted Railway API supports send. Scheduled runs append to the production Doc and create Gmail drafts; operators send manually from the OAuth inbox.

---

## Wrapper scripts

Both scripts log to `runs/scheduler/pulse-run_YYYY-MM-DD_HHMMSS.log` and run the current ISO week (IST).

| Platform | Script |
|----------|--------|
| Linux / macOS / cron | `scripts/scheduled_run.sh` |
| Windows Task Scheduler | `scripts/scheduled_run.ps1` |

Manual test:

```bash
# Linux / macOS
chmod +x scripts/scheduled_run.sh
./scripts/scheduled_run.sh

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File scripts\scheduled_run.ps1
```

---

## Linux / macOS — cron

Edit crontab (`crontab -e`):

```cron
# Product Review Pulse — Monday 08:00 IST
0 8 * * 1 TZ=Asia/Kolkata /path/to/Product_Review_Pulse/scripts/scheduled_run.sh
```

Replace `/path/to/Product_Review_Pulse` with the absolute repository path.

**Notes**

- `TZ=Asia/Kolkata` ensures the 08:00 trigger uses IST regardless of server timezone (EC-TIME-02).
- The script writes its own timestamped log under `runs/scheduler/`.
- If the server uses UTC, `0 8 * * 1` with `TZ=Asia/Kolkata` still fires at 08:00 IST on Monday.

Verify cron entry:

```bash
crontab -l | grep scheduled_run
```

---

## Windows — Task Scheduler

1. Open **Task Scheduler** → **Create Task**
2. **General:** name `Product Review Pulse`, run whether user is logged on or not
3. **Triggers:** Weekly, Monday, **08:00:00**, time zone **(UTC+05:30) Chennai, Kolkata, Mumbai, New Delhi**
4. **Actions:** Start a program
   - **Program:** `powershell.exe`
   - **Arguments:** `-ExecutionPolicy Bypass -File "D:\Cursor Files\Product_Review_Pulse\scripts\scheduled_run.ps1"`
   - **Start in:** `D:\Cursor Files\Product_Review_Pulse`
5. **Settings:**
   - Check **Run task as soon as possible after a scheduled start is missed** (laptops off at 08:00)
   - Allow task to run on demand; stop if runs longer than 2 hours

**One-liner (elevated PowerShell)** — adjust paths:

```powershell
$Action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument '-ExecutionPolicy Bypass -File "D:\Cursor Files\Product_Review_Pulse\scripts\scheduled_run.ps1"' `
  -WorkingDirectory "D:\Cursor Files\Product_Review_Pulse"
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "08:00"
# Windows 11 22H2+: add -TimeZoneId "India Standard Time" to the trigger line above
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName "ProductReviewPulse" -Action $Action -Trigger $Trigger `
  -Settings $Settings -Description "Weekly Groww review pulse (draft-mode production)"
```

Test on demand:

```powershell
Start-ScheduledTask -TaskName "ProductReviewPulse"
Get-Content (Get-ChildItem runs\scheduler\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
```

---

## GitHub Actions (Railway production)

Use this when `pulse-api` runs on **Railway** and you want an external cron instead of a local VM, laptop, or Railway Cron.

Workflow: [`.github/workflows/scheduler.yml`](../.github/workflows/scheduler.yml)

| Setting | Value |
|---------|--------|
| Schedule | Monday **08:00 IST** (`30 2 * * 1` UTC — GitHub Actions uses UTC) |
| Trigger | `POST /api/runs` with `{"product":"groww"}` |
| Poll | `GET /api/runs/jobs/{job_id}` until `completed` or `failed` |
| Manual run | **Actions → Weekly Pulse Scheduler → Run workflow** |

### Setup

1. Merge the workflow to your **default branch** (`main`). Scheduled runs only fire from the default branch.
2. Add repository secret **Settings → Secrets and variables → Actions**:

| Secret | Value |
|--------|--------|
| `PULSE_API_URL` | Railway `pulse-api` base URL (no trailing slash), e.g. `https://productpulseui-production.up.railway.app` |

3. Confirm Railway has production env vars (`GROQ_API_KEY`, `GOOGLE_MCP_API_KEY`, `CORS_ORIGINS`) and `config/products.yaml` points at the production Doc.

### Verify

- **GitHub:** Actions tab → latest **Weekly Pulse Scheduler** run → green check.
- **Operator UI:** run appears under recent runs; pipeline steps reach `completed`.
- **CLI (against production API):** `pulse status --product groww` from Railway shell, or check the dashboard.

**Notes**

- Same idempotency as local runs: a second trigger the same ISO week is skipped (EC-TIME-06).
- GitHub may delay scheduled workflows by a few minutes under load; the cron still targets Monday 08:00 IST.
- Logs live in the GitHub Actions run output, not `runs/scheduler/` (that path is for local wrapper scripts).

See also [`deploymentplan.md`](deploymentplan.md) §3.8 (external cron options).

---

## Post-run verification

```bash
pulse status --product groww
```

Check the latest log in `runs/scheduler/` and ledger row (`status=completed`, `doc_document_id`, `gmail_draft_id`).

**Idempotency:** A second trigger the same ISO week exits with `skipped=true` — expected (EC-TIME-06).

**Missed run:** If the scheduler was down on Monday, run manually:

```bash
pulse run --product groww --week YYYY-Www
```

---

## Related

- [`runbook.md`](runbook.md) — failure recovery, OAuth refresh
- [`implementation-plan.md`](implementation-plan.md) — Phase 9 acceptance criteria
