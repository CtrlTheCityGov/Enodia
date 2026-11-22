#!/usr/bin/env bash
# Start AthensOne for the presentation: mock sandbox, pinned date, deterministic demo cases.
# Usage (from athensone/):  bash scripts/run_demo.sh        (then open the URLs below)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
UV=.venv/bin/uvicorn; [ -x "$UV" ] || UV="$PY -m uvicorn"
export MOCK="${MOCK:-1}" DEMO_MODE="${DEMO_MODE:-1}" STOA_TODAY="${STOA_TODAY:-2026-11-22}"
PORT="${PORT:-8000}"
echo "Starting AthensOne on http://127.0.0.1:$PORT  (MOCK=$MOCK, STOA_TODAY=$STOA_TODAY)"
echo "  Citizen Map:      http://127.0.0.1:$PORT/web/citizen.html"
echo "  Operator Console: http://127.0.0.1:$PORT/web/operator.html"
echo "  My reports:       http://127.0.0.1:$PORT/web/track.html"
echo "  OpenAPI Docs:     http://127.0.0.1:$PORT/docs"
( for i in $(seq 1 30); do
    sleep 1
    if curl -fsS -X POST "http://127.0.0.1:$PORT/api/admin/demo-seed" -H "X-Operator-Key: ${OPERATOR_KEY:-}" >/dev/null 2>&1; then
      echo "Demo cases seeded (Ερμού: real Diavgeia record · Υμηττού: SEED with full contract)."; break; fi
  done ) &
exec $UV app.main:app --host 127.0.0.1 --port "$PORT"
