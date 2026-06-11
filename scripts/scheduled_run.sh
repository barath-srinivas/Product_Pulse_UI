#!/usr/bin/env bash
# Weekly scheduled pulse run — Monday 08:00 Asia/Kolkata (see docs/scheduler.md).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

LOG_DIR="${PROJECT_ROOT}/runs/scheduler"
mkdir -p "${LOG_DIR}"
TIMESTAMP="$(TZ=Asia/Kolkata date +%Y-%m-%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/pulse-run_${TIMESTAMP}.log"

if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
  PYTHON="${PROJECT_ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  PYTHON="python"
fi

{
  echo "=== pulse scheduled run ${TIMESTAMP} IST ==="
  echo "cwd=${PROJECT_ROOT}"
  "${PYTHON}" -m pulse.cli run --product groww
  echo "=== exit 0 ==="
} >>"${LOG_FILE}" 2>&1
