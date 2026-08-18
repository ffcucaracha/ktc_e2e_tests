#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/ktc_frontend"
E2E_DIR="$ROOT_DIR/ktc_e2e_tests"
REBUILD="${E2E_REBUILD:-false}"

BUILD_ARGS=()
if [[ "$REBUILD" == "1" || "$REBUILD" == "true" ]]; then
  BUILD_ARGS=(--build)
fi

cd "$FRONTEND_DIR"
docker compose up -d "${BUILD_ARGS[@]}" postgres ktc-backend
AI_ENABLED=false docker compose up -d "${BUILD_ARGS[@]}" --force-recreate --wait --wait-timeout 120 backend

cd "$E2E_DIR"
mkdir -p "$E2E_DIR/artifacts"
: > "$E2E_DIR/artifacts/training-data-runs.jsonl"

if [[ "$REBUILD" == "1" || "$REBUILD" == "true" ]] || ! docker image inspect ktc_e2e_tests-tests >/dev/null 2>&1; then
  docker compose -f docker-compose.selenium.yml build tests
fi

docker compose -f docker-compose.selenium.yml run --rm --no-deps \
  tests pytest -q -s tests/test_training_data_collection.py

echo
echo "Training sessions collected. Manifest: artifacts/training-data-runs.jsonl"
echo "Export ML JSONL from ktc_frontend/backend when enough sessions are accumulated."
