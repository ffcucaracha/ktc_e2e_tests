#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# The video walkthrough must use a local visible Chrome window so OBS/Kooha/etc.
# can capture it. Do not route this run through the Docker Selenium container.
unset SELENIUM_REMOTE_URL

export E2E_BASE_URL="${E2E_BASE_URL:-http://localhost:5173}"
export DEMO_PACE="${DEMO_PACE:-1.0}"
export DEMO_AI_WARNING_WAIT_SECONDS="${DEMO_AI_WARNING_WAIT_SECONDS:-35}"
export DEMO_RESULT_WAIT_SECONDS="${DEMO_RESULT_WAIT_SECONDS:-420}"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

echo "Championship video demo"
echo "  app:             $E2E_BASE_URL"
echo "  pace:            $DEMO_PACE"
echo "  ML warning wait: ${DEMO_AI_WARNING_WAIT_SECONDS}s"
echo "  result/LLM wait: ${DEMO_RESULT_WAIT_SECONDS}s"
echo
echo "Start screen recording now. Chrome will open in 5 seconds..."
sleep 5

"$PYTHON" -m pytest -s -q -m video_demo tests/test_video_demo.py
