#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/ktc_frontend"
E2E_DIR="$ROOT_DIR/ktc_e2e_tests"

cd "$FRONTEND_DIR"
docker compose up -d --build postgres ktc-backend ai-service

CORS_ORIGINS=http://localhost:5173,http://frontend:5173 \
VITE_API_BASE_URL=http://backend:8000/api/v1 \
VITE_WS_BASE_URL=ws://backend:8000/ws/v1 \
docker compose up -d --build --force-recreate backend frontend

cd "$E2E_DIR"
mkdir -p "$E2E_DIR/artifacts/screenshots"
find "$E2E_DIR/artifacts/screenshots" -maxdepth 1 -type f -name '*presentation*.png' -delete

trap 'docker compose -f "$E2E_DIR/docker-compose.selenium.yml" down' EXIT

docker compose -f docker-compose.selenium.yml up -d selenium

docker compose -f docker-compose.selenium.yml run --rm tests \
  pytest -q -s -m presentation tests/test_presentation_screenshots.py

echo "Presentation screenshots: $E2E_DIR/artifacts/screenshots"
