#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "Starting AthensOne on http://127.0.0.1:8000"
echo "  Citizen Map:      http://127.0.0.1:8000/web/citizen.html"
echo "  Operator Console: http://127.0.0.1:8000/web/operator.html"
echo "  AI Register:      http://127.0.0.1:8000/web/ai-register.html"
echo "  OpenAPI Docs:     http://127.0.0.1:8000/docs"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
