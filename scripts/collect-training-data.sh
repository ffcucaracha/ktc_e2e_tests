#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/ktc_frontend"
E2E_DIR="$ROOT_DIR/ktc_e2e_tests"
REBUILD="${E2E_REBUILD:-false}"
RESTART_BACKEND="${E2E_RESTART_BACKEND:-false}"

is_true() {
  [[ "$1" == "1" || "$1" == "true" ]]
}

cd "$FRONTEND_DIR"

if is_true "$REBUILD"; then
  docker compose up -d --build postgres ktc-backend
  AI_ENABLED=false docker compose up -d --build --force-recreate --wait --wait-timeout 120 backend
elif is_true "$RESTART_BACKEND"; then
  docker compose up -d --no-recreate postgres ktc-backend
  AI_ENABLED=false docker compose up -d --force-recreate --wait --wait-timeout 120 backend
else
  # Data collection must not disturb an already running application stack.
  # --no-recreate starts missing/stopped services but preserves running containers.
  docker compose up -d --no-recreate postgres ktc-backend backend
fi

cd "$E2E_DIR"
mkdir -p "$E2E_DIR/artifacts"
: > "$E2E_DIR/artifacts/training-data-runs.jsonl"

if is_true "$REBUILD" || ! docker image inspect ktc_e2e_tests-tests >/dev/null 2>&1; then
  docker compose -f docker-compose.selenium.yml build tests
fi

docker compose -f docker-compose.selenium.yml run --rm --no-deps \
  tests pytest -q -s tests/test_training_data_collection.py

echo
echo "Training sessions collected. Manifest: artifacts/training-data-runs.jsonl"
echo "Export ML JSONL from ktc_frontend/backend when enough sessions are accumulated."
