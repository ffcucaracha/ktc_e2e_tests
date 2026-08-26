#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/ktc_frontend"
E2E_DIR="$ROOT_DIR/ktc_e2e_tests"
REBUILD="${E2E_REBUILD:-false}"
RESTART_BACKEND="${E2E_RESTART_BACKEND:-false}"
E2E_OPERATOR_PASSWORD="${E2E_OPERATOR_PASSWORD:-change-me-e2e-operator-password}"
E2E_OPERATOR_USERNAMES="${E2E_OPERATOR_USERNAMES:-e2e-operator,e2e-operator-02,e2e-operator-03,e2e-operator-04,e2e-operator-05}"

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

# Seed every data-collection operator explicitly. The loop is intentionally compatible
# with both the old single-operator seeder and the new multi-operator seeder, so a running
# backend does not have to be rebuilt just to add the four additional accounts.
IFS=',' read -r -a operator_usernames <<< "$E2E_OPERATOR_USERNAMES"
for raw_username in "${operator_usernames[@]}"; do
  username="$(echo "$raw_username" | xargs)"
  [[ -n "$username" ]] || continue
  docker compose exec -T \
    -e E2E_OPERATOR_COUNT=1 \
    -e E2E_OPERATOR_USERNAME="$username" \
    -e E2E_OPERATOR_FULL_NAME="Dataset ${username}" \
    -e E2E_OPERATOR_PASSWORD="$E2E_OPERATOR_PASSWORD" \
    backend python -m app.commands.seed_e2e_admin >/dev/null
done

cd "$E2E_DIR"
mkdir -p "$E2E_DIR/artifacts"
: > "$E2E_DIR/artifacts/training-data-runs.jsonl"

if is_true "$REBUILD" || ! docker image inspect ktc_e2e_tests-tests >/dev/null 2>&1; then
  docker compose -f docker-compose.selenium.yml build tests
fi

E2E_OPERATOR_USERNAMES="$E2E_OPERATOR_USERNAMES" \
E2E_OPERATOR_PASSWORD="$E2E_OPERATOR_PASSWORD" \
docker compose -f docker-compose.selenium.yml run --rm --no-deps \
  -e E2E_OPERATOR_USERNAMES="$E2E_OPERATOR_USERNAMES" \
  -e E2E_OPERATOR_PASSWORD="$E2E_OPERATOR_PASSWORD" \
  tests pytest -q -s tests/test_training_data_collection_multi_operator.py

echo
echo "Training sessions collected across operators: $E2E_OPERATOR_USERNAMES"
echo "Manifest: artifacts/training-data-runs.jsonl"
echo "Export ML JSONL from ktc_frontend/backend when enough sessions are accumulated."
