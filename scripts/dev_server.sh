#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

export AOE_N_GPU_LAYERS="${AOE_N_GPU_LAYERS:-0}"
export AOE_THREADS="${AOE_THREADS:-8}"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${AOE_PORT:-8100}"
