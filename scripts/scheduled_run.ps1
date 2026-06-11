# Weekly scheduled pulse run — Monday 08:00 Asia/Kolkata (see docs/scheduler.md).
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot "runs\scheduler"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Tz = [System.TimeZoneInfo]::FindSystemTimeZoneById("India Standard Time")
$Timestamp = [System.TimeZoneInfo]::ConvertTimeFromUtc(
    [DateTime]::UtcNow, $Tz
).ToString("yyyy-MM-dd_HHmmss")
$LogFile = Join-Path $LogDir "pulse-run_$Timestamp.log"

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
} else {
    throw "Python not found. Install Python 3.11+ or create .venv in the project root."
}

$Lines = @(
    "=== pulse scheduled run $Timestamp IST ==="
    "cwd=$ProjectRoot"
)

$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$Output = & $Python -m pulse.cli run --product groww 2>&1 | ForEach-Object { "$_" }
$ExitCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap

$Lines += ($Output -join [Environment]::NewLine).TrimEnd()
if ($ExitCode -eq 0) {
    $Lines += "=== exit 0 ==="
} else {
    $Lines += "=== exit $ExitCode ==="
}
$Lines | Set-Content -Path $LogFile -Encoding utf8
Write-Output ($Output -join [Environment]::NewLine)
exit $ExitCode
