#!/usr/bin/env bash
# Start the API (port 8000) and the web app (port 3000) together. Ctrl+C stops both.
set -e
cd "$(dirname "$0")"
[ -f api/.env ] && set -a && . api/.env && set +a
(cd api && python -m uvicorn app.main:app --reload --port 8000) &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT
cd web && npm run dev
